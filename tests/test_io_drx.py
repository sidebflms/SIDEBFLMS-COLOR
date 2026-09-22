"""`core.io.drx`: tres grupos de tests.

1. Contra un `.drx` FABRICADO, pero con la estructura real confirmada el día 6
   (XML con `Gallery::GyStill`, `<Body>` = hex de un byte de cabecera + un
   frame Zstandard de un mensaje protobuf con nodos). Prueba la mecánica del
   lector sin depender de tener material real a mano.
2. Contra `tests/powergrades_reales/*.drx`, los PowerGrades de verdad de
   Mario: se saltan solos si la carpeta no existe o está vacía. Las cifras
   que comprueban están documentadas y explicadas en
   `core/io/FORMATO-DRX.md` — si uno de estos tests se pone rojo, ese
   documento es el que hay que revisar primero.
3. El avisador de dependencias contra `tests/luts_reales/`, con el mismo
   material real.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import zstandard

from core.io.drx import (
    BYTE_CABECERA_BODY,
    VERSIONES_RESOLVE_CONFIRMADAS,
    advertencia_version_desconocida,
    avisar_dependencias_faltantes,
    buscar_rutas_referenciadas,
    descomprimir_body,
    inspeccionar_drx,
    leer_grado,
    version_resolve,
)

# ---------------------------------------------------------------------------
# Construcción de un `.drx` sintético, con la estructura CONFIRMADA
# (core/io/FORMATO-DRX.md), no inventada.
# ---------------------------------------------------------------------------


def _varint(v: int) -> bytes:
    out = bytearray()
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _campo_bytes(numero: int, datos: bytes) -> bytes:
    return _varint((numero << 3) | 2) + _varint(len(datos)) + datos


def _campo_varint(numero: int, valor: int) -> bytes:
    return _varint((numero << 3) | 0) + _varint(valor)


def _nodo(indice: int, ruta_lut: bytes | None) -> bytes:
    contenido = _campo_varint(1, indice)
    if ruta_lut is not None:
        # anidado a un par de niveles, como el .drx real: el lector no debe
        # depender de la profundidad exacta (ver FORMATO-DRX.md §3.3).
        contenido += _campo_bytes(9, _campo_bytes(1, ruta_lut))
    return contenido


def _grafo(nodos: list[bytes]) -> bytes:
    out = b""
    for n in nodos:
        out += _campo_bytes(7, n)
    return out


def _body_hex(nodos: list[bytes]) -> str:
    """`<Body>` completo: cabecera + Zstandard(protobuf(grafo(nodos)))."""
    protobuf = _campo_bytes(1, _grafo(nodos))
    comprimido = zstandard.ZstdCompressor().compress(protobuf)
    crudo = bytes([BYTE_CABECERA_BODY]) + comprimido
    return crudo.hex()


def _drx_sintetico(
    nodos_clip: list[bytes],
    nodos_track: list[bytes] | None = None,
    *,
    comentario_version: str | None = '<!--DbAppVer="21.1.0.0017" DbPrjVer="17"-->',
) -> str:
    body_clip = _body_hex(nodos_clip)
    body_track = _body_hex(nodos_track or [])
    linea_version = f"{comentario_version}\n" if comentario_version is not None else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{linea_version}<Gallery::GyStill DbId="00000000-0000-0000-0000-000000000000">
 <Label>prueba</Label>
 <pClipFullVer>
  <ListMgt::LmVersion DbId="00000000-0000-0000-0000-000000000001">
   <Body>{body_clip}</Body>
  </ListMgt::LmVersion>
 </pClipFullVer>
 <pTrackVer>
  <ListMgt::LmVersion DbId="00000000-0000-0000-0000-000000000002">
   <Body>{body_track}</Body>
  </ListMgt::LmVersion>
 </pTrackVer>
</Gallery::GyStill>
"""


@pytest.fixture
def drx_sintetico(tmp_path: Path) -> Path:
    """Un `.drx` fabricado con dos nodos: uno de conversión, uno de look."""
    nodos = [
        _nodo(1, b"Sony/SLog3SGamut3.CineToLC-709.cube"),
        _nodo(2, b"SIDEBFLMS/mi_look.cube"),
    ]
    ruta = tmp_path / "prueba.drx"
    ruta.write_text(_drx_sintetico(nodos), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# 1. Mecánica del lector, sobre el .drx fabricado
# ---------------------------------------------------------------------------


def test_inspeccionar_acepta_los_dos_puntos_del_nombre_de_etiqueta(drx_sintetico: Path):
    """`Gallery::GyStill` NO es un nombre XML valido segun namespaces, y
    `ElementTree.fromstring()` a secas lo rechaza (ver FORMATO-DRX.md §1).
    El lector de este repo tiene que aceptarlo igualmente."""
    info = inspeccionar_drx(drx_sintetico)
    assert info.es_xml
    assert info.tag_raiz == "Gallery::GyStill"
    assert not info.advertencias
    vocab = dict(info.vocabulario)
    assert vocab["ListMgt::LmVersion"] == 2


def test_inspeccionar_binario_de_verdad_no_lanza(tmp_path: Path):
    ruta = tmp_path / "binario.drx"
    ruta.write_bytes(b"\x00\x01\x02BLACKMAGIC\xff\xfe")
    info = inspeccionar_drx(ruta)
    assert not info.es_xml
    assert info.advertencias


def test_inspeccionar_drx_que_no_existe_no_lanza(tmp_path: Path):
    """Bug real encontrado en revisión: el docstring de `inspeccionar_drx`
    prometía "nunca lanza por forma inesperada", pero un fichero inexistente
    (borrado, disco desmontado entre sembrar la biblioteca y elegir el
    preset) reventaba con `FileNotFoundError` crudo — un error de LECTURA,
    no de forma, pero la misma respuesta práctica para quien llama."""
    info = inspeccionar_drx(tmp_path / "no_existe.drx")
    assert not info.es_xml
    assert info.advertencias
    assert "no se puede leer" in info.advertencias[0]


def test_buscar_rutas_referenciadas_en_fichero_que_no_existe_no_lanza(tmp_path: Path):
    assert buscar_rutas_referenciadas(tmp_path / "no_existe.drx") == ()


# ---------------------------------------------------------------------------
# Deriva de versión de Resolve (día 7, tarea 4): avisar, no leer mal en
# silencio, cuando el `.drx` viene de una versión nunca comprobada.
# ---------------------------------------------------------------------------


def test_version_resolve_lee_el_comentario_de_cabecera(tmp_path: Path):
    ruta = tmp_path / "prueba.drx"
    ruta.write_text(_drx_sintetico([_nodo(1, None)]), encoding="utf-8")
    assert version_resolve(ruta) == "21.1.0.0017"


def test_version_resolve_none_si_no_hay_comentario(tmp_path: Path):
    ruta = tmp_path / "prueba.drx"
    ruta.write_text(_drx_sintetico([_nodo(1, None)], comentario_version=None), encoding="utf-8")
    assert version_resolve(ruta) is None


def test_advertencia_version_desconocida_para_version_confirmada():
    for v in VERSIONES_RESOLVE_CONFIRMADAS:
        assert advertencia_version_desconocida(v) is None


def test_advertencia_version_desconocida_para_version_nueva():
    aviso = advertencia_version_desconocida("99.9.9.9999")
    assert aviso is not None
    assert "99.9.9.9999" in aviso


def test_advertencia_version_desconocida_para_ausente():
    aviso = advertencia_version_desconocida(None)
    assert aviso is not None


def test_inspeccionar_drx_con_version_confirmada_no_avisa(tmp_path: Path):
    ruta = tmp_path / "prueba.drx"
    ruta.write_text(_drx_sintetico([_nodo(1, None)]), encoding="utf-8")
    info = inspeccionar_drx(ruta)
    assert info.version_resolve == "21.1.0.0017"
    assert not info.advertencias


def test_inspeccionar_drx_con_version_desconocida_avisa(tmp_path: Path):
    ruta = tmp_path / "prueba.drx"
    texto = _drx_sintetico(
        [_nodo(1, None)], comentario_version='<!--DbAppVer="30.0.0.0001" DbPrjVer="17"-->'
    )
    ruta.write_text(texto, encoding="utf-8")
    info = inspeccionar_drx(ruta)
    assert info.version_resolve == "30.0.0.0001"
    assert any("30.0.0.0001" in a for a in info.advertencias)


def test_inspeccionar_drx_sin_comentario_de_version_avisa(tmp_path: Path):
    ruta = tmp_path / "prueba.drx"
    ruta.write_text(_drx_sintetico([_nodo(1, None)], comentario_version=None), encoding="utf-8")
    info = inspeccionar_drx(ruta)
    assert info.version_resolve is None
    assert info.advertencias


def test_descomprimir_body_ida_y_vuelta():
    hexstr = _body_hex([_nodo(1, None)])
    dec = descomprimir_body(hexstr)
    assert dec is not None
    grado = leer_grado(dec)
    assert grado is not None
    assert len(grado.nodos) == 1
    assert grado.nodos[0].indice == 1


def test_descomprimir_body_cabecera_distinta_da_none():
    crudo = bytes([0x00]) + zstandard.ZstdCompressor().compress(b"x")
    assert descomprimir_body(crudo.hex()) is None


def test_descomprimir_body_vacio_da_none():
    assert descomprimir_body("") is None


def test_buscar_rutas_referenciadas(drx_sintetico: Path):
    rutas = buscar_rutas_referenciadas(drx_sintetico)
    assert rutas == ("Sony/SLog3SGamut3.CineToLC-709.cube", "SIDEBFLMS/mi_look.cube")


def test_avisar_dependencias_faltantes_cuando_no_existe(drx_sintetico: Path, tmp_path: Path):
    carpeta_vacia = tmp_path / "sin_luts"
    carpeta_vacia.mkdir()
    faltantes = avisar_dependencias_faltantes(drx_sintetico, (carpeta_vacia,))
    assert set(faltantes) == {"Sony/SLog3SGamut3.CineToLC-709.cube", "SIDEBFLMS/mi_look.cube"}


def test_avisar_dependencias_encontradas_por_nombre(drx_sintetico: Path, tmp_path: Path):
    """El .drx referencia 'SIDEBFLMS/mi_look.cube' (ruta de OTRA maquina); si
    el .cube existe localmente con ese nombre, aunque en otra subcarpeta, no
    debe avisar de ese en concreto."""
    carpeta = tmp_path / "mis_luts" / "otra_estructura"
    carpeta.mkdir(parents=True)
    (carpeta / "mi_look.cube").write_text("LUT_3D_SIZE 2\n")
    faltantes = avisar_dependencias_faltantes(drx_sintetico, (tmp_path / "mis_luts",))
    assert faltantes == ("Sony/SLog3SGamut3.CineToLC-709.cube",)


# ---------------------------------------------------------------------------
# 2. Contra PowerGrades reales de Mario. Se saltan solos si no hay material.
# ---------------------------------------------------------------------------

_CARPETA_REALES = Path(__file__).parent / "powergrades_reales"
_DRX_REALES = sorted(_CARPETA_REALES.glob("*.drx")) if _CARPETA_REALES.is_dir() else []
_CARPETA_LUTS = Path(__file__).parent / "luts_reales"

pytestmark_reales = pytest.mark.skipif(
    not _DRX_REALES,
    reason=(
        "no hay PowerGrades reales en tests/powergrades_reales/ (carpeta ignorada por git, "
        "solo lectura). Cuando Mario deje material ahí, estos tests confirman las cifras de "
        "core/io/FORMATO-DRX.md."
    ),
)

#: (nombre de archivo, nodos esperados, num de rutas de LUT esperadas), tal
#: y como se confirmó en core/io/FORMATO-DRX.md §3.1. Si Mario cambia o quita
#: alguno de estos diez archivos, este test se ajusta a la vez que el
#: documento — las dos cosas describen el mismo material.
_CIFRAS_ESPERADAS: dict[str, tuple[int, int]] = {
    "Still 2026-09-17 102835_1.1.1.drx": (2, 2),
    "Still 2026-09-17 102835_1.162.1.drx": (3, 1),
    "Still 2026-09-17 102835_1.2.1.drx": (2, 2),
    "Still 2026-09-17 102835_1.3.1.drx": (4, 1),
    "Still 2026-09-17 102835_1.38.1.drx": (18, 1),
    "Still 2026-09-17 102835_1.5.1.drx": (5, 1),
    "Still 2026-09-17 102835_1.52.1.drx": (22, 1),
    "Still 2026-09-17 102835_1.6.1.drx": (2, 1),
    "Still 2026-09-17 102835_2.4.1.drx": (4, 1),
    "Still 2026-09-17 102835_I.Still.drx": (5, 1),
}


@pytestmark_reales
@pytest.mark.parametrize("ruta", _DRX_REALES, ids=lambda r: r.name)
def test_powergrade_real_es_xml_con_la_raiz_esperada(ruta: Path):
    info = inspeccionar_drx(ruta)
    assert info.es_xml, f"{ruta.name} no parsea como XML: {info.advertencias}"
    assert info.tag_raiz == "Gallery::GyStill"


@pytestmark_reales
@pytest.mark.parametrize("ruta", _DRX_REALES, ids=lambda r: r.name)
def test_powergrade_real_body_tiene_cabecera_confirmada(ruta: Path):
    """Confirmado en 20 de 20 <Body> del material de referencia (dos por
    archivo): el primer byte, decodificado el hex, es BYTE_CABECERA_BODY."""
    import re

    texto = ruta.read_text(encoding="utf-8")
    cuerpos = re.findall(r"<Body>([0-9a-f]+)</Body>", texto)
    assert len(cuerpos) == 2, f"{ruta.name}: esperaba 2 <Body>, hay {len(cuerpos)}"
    for hexstr in cuerpos:
        assert bytes.fromhex(hexstr)[0] == BYTE_CABECERA_BODY


@pytestmark_reales
@pytest.mark.parametrize("ruta", _DRX_REALES, ids=lambda r: r.name)
def test_powergrade_real_nodos_y_luts_coinciden_con_lo_documentado(ruta: Path):
    esperado = _CIFRAS_ESPERADAS.get(ruta.name)
    if esperado is None:
        pytest.skip(f"{ruta.name} no está en las cifras documentadas de FORMATO-DRX.md")
    n_nodos_esperado, n_luts_esperado = esperado
    rutas = buscar_rutas_referenciadas(ruta)
    import re

    texto = ruta.read_text(encoding="utf-8")
    cuerpo0 = re.findall(r"<Body>([0-9a-f]+)</Body>", texto)[0]
    grado = leer_grado(descomprimir_body(cuerpo0))
    assert grado is not None
    assert len(grado.nodos) == n_nodos_esperado, f"{ruta.name}: nodos"
    assert len(rutas) == n_luts_esperado, f"{ruta.name}: rutas de LUT"


@pytestmark_reales
@pytest.mark.parametrize("ruta", _DRX_REALES, ids=lambda r: r.name)
def test_powergrade_real_version_confirmada_no_avisa(ruta: Path):
    """Los 10 archivos de referencia son de la misma versión de Resolve
    (`FORMATO-DRX.md`): confirma que sigue en `VERSIONES_RESOLVE_CONFIRMADAS`
    y que `inspeccionar_drx` no avisa de nada por versión con ellos."""
    info = inspeccionar_drx(ruta)
    assert info.version_resolve in VERSIONES_RESOLVE_CONFIRMADAS
    assert not info.advertencias


@pytestmark_reales
def test_avisador_de_dependencias_contra_material_real():
    """El caso exacto del punto 4 de la tarea 1: un PowerGrade con LUT, contra
    tests/luts_reales/. Confirmado: 9 de 10 archivos encuentran TODAS sus
    dependencias; el que falta es un LUT de fábrica de Sony (no algo que
    Mario tuviera que copiar) — ver FORMATO-DRX.md §4."""
    if not _CARPETA_LUTS.is_dir():
        pytest.skip("no hay tests/luts_reales/ con el que cruzar las dependencias")
    con_lut_de_fabrica = _CARPETA_REALES / "Still 2026-09-17 102835_1.1.1.drx"
    if not con_lut_de_fabrica.exists():
        pytest.skip("el archivo de referencia con el LUT de fábrica no está presente")
    faltantes = avisar_dependencias_faltantes(con_lut_de_fabrica, (_CARPETA_LUTS,))
    assert faltantes == ("Sony/SLog3SGamut3.CineToLC-709.cube",)
