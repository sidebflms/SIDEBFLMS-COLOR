"""El bundle `.sidebcolor`: ida y vuelta, y defensa contra zips hostiles.

Un `.sidebcolor` puede llegar por WeTransfer desde una casa de post que no
conocemos. La mitad de este archivo son ataques.
"""

from __future__ import annotations

import io
import json
import pickle
import zipfile

import numpy as np
import pytest

from core.contracts import (
    CDL,
    FINGERPRINT_LEN,
    LUT3D,
    PERCENTILE_LEVELS,
    SAT_BINS,
    ClipAnalysis,
    ColorSession,
    ColorStats,
    Confidence,
    MatchResult,
)
from core.io import ErrorBundle, ErrorFormatoCube, abrir_sesion, guardar_sesion

# ---------------------------------------------------------------------------
# Fabricar una sesión de mentira pero completa
# ---------------------------------------------------------------------------


def _stats(rng) -> ColorStats:
    return ColorStats(
        mean=rng.random(3),
        std=rng.random(3),
        cov=rng.random((3, 3)),
        percentiles=rng.random((len(PERCENTILE_LEVELS), 3)),
        black_point=rng.random(3),
        white_point=rng.random(3),
        saturation_hist=rng.random(SAT_BINS),
        skin_locus=rng.random(3),
        skin_fraction=0.31,
        n_samples=123456,
    )


def _sesion_completa(rng) -> ColorSession:
    analisis_a = ClipAnalysis(
        clip_id="A001_C003",
        path="/no/existe/A001_C003.mov",
        stats=_stats(rng),
        fingerprint=rng.random(FINGERPRINT_LEN).astype(np.float32),
        width=3840,
        height=2160,
        frame_count=250,
        sampled_frames=8,
        source_space="slog3_sgamut3cine",
        pixels=rng.random((500, 3)).astype(np.float32),
        warnings=("poca piel detectada",),
    )
    analisis_b = ClipAnalysis(
        clip_id="B002_C001",
        path="/no/existe/B002_C001.mov",
        stats=_stats(rng),
        fingerprint=rng.random(FINGERPRINT_LEN).astype(np.float32),
        width=1920,
        height=1080,
        frame_count=0,
        sampled_frames=4,
        source_space=None,
        pixels=None,  # el caso opcional
        warnings=(),
    )
    lut = LUT3D(
        table=rng.random((17, 17, 17, 3)).astype(np.float32),
        domain_min=(-0.1, -0.1, -0.1),
        domain_max=(1.5, 1.5, 1.5),
        title="Look de Mario",
    )
    emparejamiento = MatchResult(
        cdl=CDL(slope=(1.1, 0.95, 1.02), offset=(0.0, 0.01, -0.01), power=(1.0, 0.98, 1.0)),
        lut=lut,
        confidence=Confidence(
            score=0.81,
            level="alta",
            reasons=("las dos escenas tienen piel", "cobertura del cubo del 62%"),
            metrics={"delta_e": 1.4, "cobertura": 0.62},
        ),
        delta_e_before=6.2,
        delta_e_after=1.4,
        content_mismatch=False,
        notes=("nodo 2",),
    )
    sin_lut = MatchResult(
        cdl=CDL.identity(),
        lut=None,
        confidence=Confidence(score=0.2, level="baja", reasons=("escenas incompatibles",)),
        delta_e_before=12.0,
        delta_e_after=11.8,
        content_mismatch=True,
    )
    return ColorSession(
        project_name="SIDEBFLMS — piloto",
        created_at="2026-09-15T02:34:00+02:00",
        app_version="0.1.0",
        reference_clip_id="A001_C003",
        analyses={"A001_C003": analisis_a, "B002_C001": analisis_b},
        matches={"B002_C001": emparejamiento, "C003_C009": sin_lut},
        look_lut=lut,
        notes=("hecho de noche", "revisar el nodo 3"),
    )


def _comparar(a: ColorSession, b: ColorSession) -> None:
    """`ColorSession` es `eq=False`, así que hay que comparar a mano. Se compara
    TODO, y los arrays con igualdad exacta: 'equivalente' quiere decir eso."""
    assert (a.project_name, a.created_at, a.app_version) == (
        b.project_name,
        b.created_at,
        b.app_version,
    )
    assert a.reference_clip_id == b.reference_clip_id
    assert a.notes == b.notes

    assert a.analyses.keys() == b.analyses.keys()
    for k in a.analyses:
        x, y = a.analyses[k], b.analyses[k]
        assert (x.clip_id, x.path, x.width, x.height) == (y.clip_id, y.path, y.width, y.height)
        assert (x.frame_count, x.sampled_frames) == (y.frame_count, y.sampled_frames)
        assert x.source_space == y.source_space
        assert x.warnings == y.warnings
        assert np.array_equal(x.fingerprint, y.fingerprint)
        assert (x.pixels is None) == (y.pixels is None)
        if x.pixels is not None:
            assert np.array_equal(x.pixels, y.pixels)
        for campo in ColorStats._ARRAY_FIELDS:
            assert np.allclose(getattr(x.stats, campo), getattr(y.stats, campo))
        assert np.allclose(x.stats.skin_locus, y.stats.skin_locus)
        assert x.stats.skin_fraction == y.stats.skin_fraction
        assert x.stats.n_samples == y.stats.n_samples

    assert a.matches.keys() == b.matches.keys()
    for k in a.matches:
        x, y = a.matches[k], b.matches[k]
        assert x.cdl == y.cdl
        assert x.confidence == y.confidence
        assert (x.delta_e_before, x.delta_e_after) == (y.delta_e_before, y.delta_e_after)
        assert x.content_mismatch == y.content_mismatch
        assert x.notes == y.notes
        assert (x.lut is None) == (y.lut is None)
        if x.lut is not None:
            assert np.array_equal(x.lut.table, y.lut.table)

    assert (a.look_lut is None) == (b.look_lut is None)
    if a.look_lut is not None:
        assert np.array_equal(a.look_lut.table, b.look_lut.table)
        assert a.look_lut.title == b.look_lut.title
        assert a.look_lut.domain_min == b.look_lut.domain_min
        assert a.look_lut.domain_max == b.look_lut.domain_max


# ---------------------------------------------------------------------------
# Ida y vuelta
# ---------------------------------------------------------------------------


def test_ida_y_vuelta_de_una_sesion_completa(tmp_path, rng):
    ses = _sesion_completa(rng)
    ruta = guardar_sesion(ses, tmp_path / "piloto.sidebcolor")
    _comparar(ses, abrir_sesion(ruta))


def test_las_tablas_de_lut_vuelven_bit_a_bit(tmp_path, rng):
    """No 'parecidas': idénticas. Con valores adversarios, además: los
    minúsculos son donde 9 decimales se habrían quedado cortos."""
    tabla = rng.random((9, 9, 9, 3)).astype(np.float32)
    tabla[0, 0, 0] = [1e-7, 1e-12, 0.0]
    tabla[1, 2, 3] = [12.3456789, -0.5, 1.0000001]
    ses = ColorSession(
        project_name="p",
        created_at="x",
        app_version="0.1.0",
        reference_clip_id=None,
        look_lut=LUT3D(table=tabla),
    )
    vuelta = abrir_sesion(guardar_sesion(ses, tmp_path / "s.sidebcolor"))
    assert np.array_equal(vuelta.look_lut.table, tabla)


def test_una_sesion_vacia_tambien_va_y_viene(tmp_path):
    ses = ColorSession(
        project_name="",
        created_at="2026-01-01T00:00:00",
        app_version="0.1.0",
        reference_clip_id=None,
    )
    vuelta = abrir_sesion(guardar_sesion(ses, tmp_path / "vacia.sidebcolor"))
    assert vuelta.analyses == {} and vuelta.matches == {} and vuelta.look_lut is None


def test_el_zip_se_puede_abrir_con_el_finder(tmp_path, rng):
    """Es un zip normal, con nombres que se entienden. Si algún día hay que
    rescatar un `.cube` de una sesión rota, se hace a mano."""
    ruta = guardar_sesion(_sesion_completa(rng), tmp_path / "s.sidebcolor")
    nombres = zipfile.ZipFile(ruta).namelist()
    assert "session.json" in nombres
    assert "luts/look.cube" in nombres
    assert any(n.startswith("arrays/") and n.endswith("_fingerprint.npy") for n in nombres)
    doc = json.loads(zipfile.ZipFile(ruta).read("session.json"))
    assert doc["formato"] == "sidebcolor"


def test_directorio_que_no_existe(tmp_path):
    ses = ColorSession(project_name="p", created_at="x", app_version="0.1.0", reference_clip_id=None)
    destino = tmp_path / "no" / "existe" / "s.sidebcolor"
    with pytest.raises(ErrorBundle) as e:
        guardar_sesion(ses, destino)
    assert "no existe" in str(e.value)
    guardar_sesion(ses, destino, crear_directorios=True)
    assert destino.is_file()


def test_no_guarda_un_lut_con_nan(tmp_path):
    from core.io import lut_con_nan

    ses = ColorSession(
        project_name="p",
        created_at="x",
        app_version="0.1.0",
        reference_clip_id=None,
        look_lut=lut_con_nan(5),
    )
    with pytest.raises(ErrorFormatoCube):
        guardar_sesion(ses, tmp_path / "nan.sidebcolor")


# ---------------------------------------------------------------------------
# Zips hostiles
# ---------------------------------------------------------------------------


def _sesion_minima_json() -> str:
    return json.dumps(
        {
            "formato": "sidebcolor",
            "formato_version": 1,
            "sesion": {
                "project_name": "p",
                "created_at": "x",
                "app_version": "0.1.0",
                "reference_clip_id": None,
                "analyses": {},
                "matches": {},
                "look_lut": None,
                "notes": [],
            },
        }
    )


@pytest.mark.parametrize(
    "ruta_mala",
    [
        "../../fuera.txt",
        "/etc/passwd",
        "luts/../../../fuera.cube",
        "..\\..\\windows\\system32\\x.dll",
        "C:/Users/mario/x.txt",
    ],
)
def test_zip_slip_una_entrada_que_se_sale_tumba_el_archivo_entero(tmp_path, ruta_mala):
    """Zip-slip. Aquí nunca se extrae nada al disco, pero la comprobación tiene
    que estar puesta ANTES de que a alguien se le ocurra añadir un 'extraer
    miniaturas' y la convierta en un agujero de verdad."""
    ruta = tmp_path / "malicioso.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", _sesion_minima_json())
        zf.writestr(ruta_mala, "te he pillado")
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    msg = str(e.value)
    assert "peligrosa" in msg and "No lo abro" in msg


def test_zip_bomba_por_tamano_declarado(tmp_path):
    """Un zip cuyo índice declara gigabytes se rechaza sin descomprimir nada."""
    ruta = tmp_path / "bomba.sidebcolor"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", _sesion_minima_json())
        zf.writestr("relleno.bin", b"\x00" * (4 * 1024 * 1024))
    # Con un tope bajito, el mismo fichero tiene que dar error.
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta, max_descomprimido=1024 * 1024)
    assert "zip-bomba" in str(e.value)
    # Y con el tope normal se abre sin problema.
    assert abrir_sesion(ruta).project_name == "p"


def test_zip_con_demasiadas_entradas(tmp_path):
    from core.io import MAX_ENTRADAS

    ruta = tmp_path / "muchas.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", _sesion_minima_json())
        for i in range(MAX_ENTRADAS + 1):
            zf.writestr(f"basura/{i}", b"")
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "entradas" in str(e.value)


def test_un_npy_con_pickle_dentro_no_se_ejecuta(tmp_path):
    """EL agujero de verdad de este módulo. `np.load` con `allow_pickle=True`
    ejecuta lo que le metan dentro; el flag va a False y no se toca.

    Aquí se fabrica un .npy de objetos (que sólo se puede cargar con pickle) y
    se comprueba que abrir la sesión falla en vez de deserializarlo."""
    buf = io.BytesIO()
    np.save(buf, np.array([{"soy": "un objeto"}], dtype=object), allow_pickle=True)
    assert pickle.dumps  # el .npy de arriba lleva un pickle dentro, por definición

    ruta = tmp_path / "pickle.sidebcolor"
    doc = json.loads(_sesion_minima_json())
    doc["sesion"]["analyses"] = {
        "x": {
            "clip_id": "x",
            "path": "/x",
            "stats": ColorStats(
                mean=np.zeros(3),
                std=np.zeros(3),
                cov=np.zeros((3, 3)),
                percentiles=np.zeros((len(PERCENTILE_LEVELS), 3)),
                black_point=np.zeros(3),
                white_point=np.zeros(3),
                saturation_hist=np.zeros(SAT_BINS),
                skin_locus=None,
                skin_fraction=0.0,
                n_samples=1,
            ).to_dict(),
            "fingerprint": "arrays/malo.npy",
            "width": 1,
            "height": 1,
            "frame_count": 0,
            "sampled_frames": 0,
            "source_space": None,
            "pixels": None,
            "warnings": [],
        }
    }
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(doc))
        zf.writestr("arrays/malo.npy", buf.getvalue())

    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "no es un .npy legible" in str(e.value)


def test_no_es_un_zip(tmp_path):
    ruta = tmp_path / "texto.sidebcolor"
    ruta.write_text("esto no es un zip ni de lejos")
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "no es un zip" in str(e.value)


def test_fichero_vacio(tmp_path):
    ruta = tmp_path / "v.sidebcolor"
    ruta.write_bytes(b"")
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "vacío" in str(e.value)


def test_fichero_que_no_existe(tmp_path):
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(tmp_path / "ni_idea.sidebcolor")
    assert "no existe" in str(e.value)


def test_zip_sin_session_json(tmp_path):
    ruta = tmp_path / "sin.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("otra_cosa.txt", "hola")
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "session.json" in str(e.value)


def test_session_json_que_no_es_json(tmp_path):
    ruta = tmp_path / "roto.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", "{esto no es json")
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "no es JSON válido" in str(e.value)


def test_un_zip_que_no_es_nuestro(tmp_path):
    ruta = tmp_path / "ajeno.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", '{"formato": "otra_app"}')
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "SIDEBFLMS COLOR" in str(e.value)


def test_version_de_formato_del_futuro(tmp_path):
    ruta = tmp_path / "futuro.sidebcolor"
    doc = json.loads(_sesion_minima_json())
    doc["formato_version"] = 99
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(doc))
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "99" in str(e.value)


def test_falta_un_fichero_que_la_sesion_referencia(tmp_path, rng):
    ruta = guardar_sesion(_sesion_completa(rng), tmp_path / "s.sidebcolor")
    # Reescribimos el zip sin el .cube del look.
    contenido = {}
    with zipfile.ZipFile(ruta) as zf:
        for n in zf.namelist():
            contenido[n] = zf.read(n)
    contenido.pop("luts/look.cube")
    with zipfile.ZipFile(ruta, "w") as zf:
        for n, d in contenido.items():
            zf.writestr(n, d)
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "incompleto" in str(e.value) and "luts/look.cube" in str(e.value)


def test_a_la_sesion_le_falta_un_campo(tmp_path):
    ruta = tmp_path / "corta.sidebcolor"
    doc = json.loads(_sesion_minima_json())
    del doc["sesion"]["created_at"]
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(doc))
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "created_at" in str(e.value)


def test_un_cdl_guardado_con_power_cero(tmp_path):
    """Alguien edita el session.json a mano y pone Power 0. Error legible."""
    ruta = tmp_path / "p0.sidebcolor"
    doc = json.loads(_sesion_minima_json())
    doc["sesion"]["matches"] = {
        "x": {
            "cdl": {"slope": [1, 1, 1], "offset": [0, 0, 0], "power": [0, 1, 1], "saturation": 1},
            "lut": None,
            "confidence": {"score": 0.5, "level": "media", "reasons": [], "metrics": {}},
            "delta_e_before": 1.0,
            "delta_e_after": 1.0,
            "content_mismatch": False,
            "notes": [],
        }
    }
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(doc))
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta)
    assert "power" in str(e.value).lower()


def test_un_indice_mentiroso_se_rechaza_y_sale_baratisimo(tmp_path):
    """Índice del zip que MIENTE: declara 10 bytes y trae 32 MB.

    La revisión de la ola 1 dejó escrito que este ataque "obliga a leer un
    cuarto de giga a memoria antes de decir que no". Lo medí y **no es cierto**:
    `zipfile` limita la lectura al `file_size` del directorio central (los 10
    bytes que declara el atacante) y el CRC salta al llegar al final. Con el zip
    del revisor (300 MB reales, 299 KB en disco): `BadZipFile` en 0,057 s.

    Este test fija las dos cosas: que se rechaza, y que se rechaza sin
    descomprimir el contenido. Si algún día `zipfile` cambia de criterio, el
    tiempo lo delata.
    """
    import struct
    import time

    entrada = "arrays/gorda.npy"
    ruta = tmp_path / "mentira.sidebcolor"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", _sesion_minima_json())
        zf.writestr(entrada, b"\0" * (32 * 1024 * 1024))

    crudo = bytearray(ruta.read_bytes())
    pos, parcheadas = 0, 0
    while True:
        pos = crudo.find(b"PK\x01\x02", pos)
        if pos < 0:
            break
        largo = struct.unpack_from("<H", crudo, pos + 28)[0]
        if bytes(crudo[pos + 46 : pos + 46 + largo]).decode() == entrada:
            struct.pack_into("<I", crudo, pos + 24, 10)
            parcheadas += 1
        pos += 4
    ruta.write_bytes(bytes(crudo))
    assert parcheadas == 1
    assert ruta.stat().st_size < 1024 * 1024, "el zip de ataque tiene que ser pequeño"

    from core.io.bundle import _abrir_zip, _leer_entrada

    zf = _abrir_zip(ruta)
    inicio = time.perf_counter()
    try:
        with pytest.raises(ErrorBundle):
            _leer_entrada(zf, entrada, nombre="mentira", tope=256 * 1024 * 1024)
    finally:
        zf.close()
    assert time.perf_counter() - inicio < 1.0, "se ha descomprimido de verdad"


def test_una_entrada_mas_gorda_que_el_tope_global_se_corta(tmp_path):
    """La otra mitad: el índice dice la verdad pero la entrada no cabe."""
    ruta = tmp_path / "gorda.sidebcolor"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", _sesion_minima_json())
        zf.writestr("arrays/gorda.npy", b"\0" * (2 * 1024 * 1024))
    with pytest.raises(ErrorBundle) as e:
        abrir_sesion(ruta, max_descomprimido=1024 * 1024)
    assert "zip-bomba" in str(e.value)
