"""`core.io.biblioteca`: la biblioteca de presets y el bundle de UN look suelto.

Dos grupos: mecánica sobre un LUT sintético (no depende de material real) y
el viaje completo contra `tests/luts_reales/` / `tests/powergrades_reales/`
(se saltan solos si esas carpetas no existen).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from core.contracts import CDL, LUT3D  # noqa: E402
from core.io.biblioteca import (
    Preset,
    abrir_preset,
    exportar_preset,
    generar_miniatura,
    nombre_legible,
    sembrar_desde_carpeta,
    sembrar_desde_drx,
)
from core.io.errores import ErrorBundle  # noqa: E402


def _lut_de_prueba() -> LUT3D:
    base = LUT3D.identity(5)
    cdl = CDL(slope=(1.05, 0.98, 0.95), offset=(0.01, 0.0, 0.0), power=(1.0, 1.0, 1.0))
    tabla = np.clip(cdl.apply(base.table), 0.0, 1.0).astype(np.float32)
    return LUT3D(table=tabla, title="prueba")


# ---------------------------------------------------------------------------
# 1. Mecánica, sin material real
# ---------------------------------------------------------------------------


def test_nombre_legible_quita_extension_y_limpia_espacios():
    assert nombre_legible("SIDEBFLMS  NIGHT   SONY.cube") == "SIDEBFLMS NIGHT SONY"
    assert nombre_legible(Path("carpeta/4 (-) AMSTERDAM SILVER V2.cube")) == "4 (-) AMSTERDAM SILVER V2"


def test_exportar_y_abrir_ida_y_vuelta_exacta(tmp_path: Path):
    lut = _lut_de_prueba()
    preset = Preset(id="prueba", nombre="Prueba", tamano_rejilla=lut.size, ruta_origen="/nada")
    destino = exportar_preset(preset, lut, tmp_path / "mi_look")
    assert destino.suffix == ".sidebcolor"
    assert destino.exists()

    abierto = abrir_preset(destino)
    assert abierto.preset.nombre == "Prueba"
    assert abierto.preset.tamano_rejilla == lut.size
    assert np.array_equal(abierto.lut.table, lut.table), "el LUT no vuelve bit a bit"
    assert abierto.avisos == ()
    assert abierto.miniatura is None


def test_exportar_anade_extension_si_falta(tmp_path: Path):
    lut = _lut_de_prueba()
    preset = Preset(id="x", nombre="X", tamano_rejilla=lut.size, ruta_origen="/nada")
    destino = exportar_preset(preset, lut, tmp_path / "sin_extension")
    assert destino.name == "sin_extension.sidebcolor"


def test_miniatura_viaja_en_el_bundle(tmp_path: Path):
    lut = _lut_de_prueba()
    miniatura = generar_miniatura(lut)
    assert miniatura.shape[2] == 3
    preset = Preset(id="x", nombre="X", tamano_rejilla=lut.size, ruta_origen="/nada")
    destino = exportar_preset(preset, lut, tmp_path / "con_mini", miniatura=miniatura)
    abierto = abrir_preset(destino)
    assert abierto.miniatura is not None
    assert abierto.miniatura.shape[:2] == miniatura.shape[:2]


def test_avisa_de_dependencia_no_incluida(tmp_path: Path):
    """El caso central de la tarea 4: un preset que venía de un PowerGrade con
    OTRO LUT encadenado (conversión de cámara) tiene que avisar de ese LUT al
    abrirse — el bundle nunca lo incluye, sólo el look."""
    lut = _lut_de_prueba()
    preset = Preset(
        id="x",
        nombre="X",
        tamano_rejilla=lut.size,
        ruta_origen="/nada",
        dependencias_declaradas=("Sony/SLog3SGamut3.CineToLC-709.cube",),
    )
    destino = exportar_preset(preset, lut, tmp_path / "con_dependencia")
    abierto = abrir_preset(destino)
    assert len(abierto.avisos) == 1
    assert "SLog3SGamut3.CineToLC-709.cube" in abierto.avisos[0]


def test_abrir_preset_sobre_un_zip_ajeno_lanza_con_mensaje_claro(tmp_path: Path):
    import zipfile

    ruta = tmp_path / "no_es_preset.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("otra_cosa.txt", "hola")
    with pytest.raises(ErrorBundle, match="preset.json"):
        abrir_preset(ruta)


def test_abrir_preset_con_zip_slip_lo_rechaza(tmp_path: Path):
    """Reutiliza las mismas defensas que `core.io.bundle` — comprobación de
    que de verdad están conectadas, no sólo importadas."""
    import zipfile

    ruta = tmp_path / "malicioso.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("../fuera.json", "{}")
        zf.writestr("preset.json", "{}")
        zf.writestr("look.cube", "LUT_3D_SIZE 2\n")
    with pytest.raises(ErrorBundle):
        abrir_preset(ruta)


def test_sembrar_desde_carpeta_inexistente_no_lanza(tmp_path: Path):
    assert sembrar_desde_carpeta(tmp_path / "no_existe") == []


def test_sembrar_desde_carpeta_con_cubes(tmp_path: Path):
    from core.io.cube import escribir_cube

    lut = _lut_de_prueba()
    escribir_cube(lut, tmp_path / "Mi Look Bonito.cube")
    (tmp_path / "sub").mkdir()
    escribir_cube(lut, tmp_path / "sub" / "Otro Look.cube")

    presets = sembrar_desde_carpeta(tmp_path)
    nombres = {p.nombre for p in presets}
    assert nombres == {"Mi Look Bonito", "Otro Look"}
    assert all(p.tamano_rejilla == lut.size for p in presets)


# ---------------------------------------------------------------------------
# 2. Contra material real. Se saltan solos si no hay carpetas.
# ---------------------------------------------------------------------------

_CARPETA_LUTS = Path(__file__).parent / "luts_reales"
_CARPETA_DRX = Path(__file__).parent / "powergrades_reales"

pytestmark_luts = pytest.mark.skipif(
    not _CARPETA_LUTS.is_dir() or not any(_CARPETA_LUTS.rglob("*.cube")),
    reason="no hay tests/luts_reales/ con .cube reales",
)
pytestmark_drx = pytest.mark.skipif(
    not _CARPETA_DRX.is_dir() or not any(_CARPETA_DRX.glob("*.drx")),
    reason="no hay tests/powergrades_reales/ con .drx reales",
)


@pytestmark_luts
def test_siembra_real_no_esta_vacia():
    presets = sembrar_desde_carpeta(_CARPETA_LUTS)
    assert len(presets) > 10, "la biblioteca real de Mario tiene decenas de LUTs"
    assert all(p.tamano_rejilla in (17, 33, 65) for p in presets)
    # ningun preset con nombre vacio o igual a la ruta completa
    assert all(p.nombre and ".cube" not in p.nombre for p in presets)


@pytestmark_luts
def test_el_viaje_completo_con_un_lut_real(tmp_path: Path):
    """El caso EXACTO de la tarea 4, punto 3: crear un bundle, abrirlo en una
    carpeta limpia como si fuera otro equipo, comprobar que el LUT vuelve
    intacto."""
    from core.io.cube import leer_cube

    presets = sembrar_desde_carpeta(_CARPETA_LUTS)
    elegido = presets[0]
    lut_original = leer_cube(elegido.ruta_origen)

    otro_equipo = tmp_path / "otro_mac_limpio"
    otro_equipo.mkdir()
    destino = exportar_preset(elegido, lut_original, otro_equipo / "preset_viajero")

    abierto = abrir_preset(destino)
    assert np.array_equal(abierto.lut.table, lut_original.table)
    assert abierto.preset.nombre == elegido.nombre


@pytestmark_luts
@pytestmark_drx
def test_siembra_desde_drx_real_con_doble_lut_avisa_de_la_dependencia():
    """El PowerGrade '_1.1.1.drx' referencia DOS LUTs (conversión Sony + look
    BALI GREEN, ver core/io/FORMATO-DRX.md §3.2). El preset sembrado desde él
    tiene que llevar sólo el look y declarar la conversión como dependencia."""
    ruta_drx = _CARPETA_DRX / "Still 2026-09-17 102835_1.1.1.drx"
    if not ruta_drx.exists():
        pytest.skip("no está el .drx de referencia con doble LUT")
    resultado = sembrar_desde_drx(ruta_drx, _CARPETA_LUTS)
    assert resultado is not None
    preset, lut = resultado
    assert "BALI GREEN" in preset.nombre
    assert preset.dependencias_declaradas == ("Sony/SLog3SGamut3.CineToLC-709.cube",)


@pytestmark_luts
@pytestmark_drx
def test_bundle_desde_drx_real_avisa_al_abrir_en_otro_equipo(tmp_path: Path):
    ruta_drx = _CARPETA_DRX / "Still 2026-09-17 102835_1.1.1.drx"
    if not ruta_drx.exists():
        pytest.skip("no está el .drx de referencia con doble LUT")
    resultado = sembrar_desde_drx(ruta_drx, _CARPETA_LUTS)
    assert resultado is not None
    preset, lut = resultado
    destino = exportar_preset(preset, lut, tmp_path / "bali_green_viajero")
    abierto = abrir_preset(destino)
    assert len(abierto.avisos) == 1
    assert "SLog3SGamut3" in abierto.avisos[0]
