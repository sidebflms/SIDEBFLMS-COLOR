"""`core.io.drx`: dos grupos de tests con propósitos MUY distintos.

1. Contra un XML fabricado a mano: prueba que el parser hace lo que dice que
   hace. **No prueba que el .drx real sea así** — es sólo la mecánica.
2. Contra `tests/powergrades_reales/*.drx`, PowerGrades de verdad de Mario:
   se saltan solos si la carpeta no existe o está vacía (tarea 4 del día 5,
   punto 2: "si la carpeta no existe, deja los tests marcados para saltarse
   solos"). Cuando Mario deje material ahí, estos son los que confirman —o
   desmienten— el formato real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.io.drx import (
    avisar_dependencias_faltantes,
    buscar_rutas_referenciadas,
    inspeccionar_drx,
)

# ---------------------------------------------------------------------------
# 1. Mecánica del parser, sobre XML fabricado. NO es una afirmación sobre el
#    formato real de un .drx: ver el docstring del módulo.
# ---------------------------------------------------------------------------

_XML_SINTETICO = """<?xml version="1.0" encoding="UTF-8"?>
<PowerGrade>
  <Node index="1" type="Serial">
    <Lut3D path="LUTs/Sony/S-Log3 to Rec709.cube" />
  </Node>
  <Node index="2" type="Serial">
    <Cdl slope="1.0 1.0 1.0" offset="0.0 0.0 0.0" power="1.0 1.0 1.0" />
  </Node>
</PowerGrade>
"""


@pytest.fixture
def drx_sintetico(tmp_path: Path) -> Path:
    ruta = tmp_path / "prueba.drx"
    ruta.write_text(_XML_SINTETICO, encoding="utf-8")
    return ruta


def test_inspeccionar_xml_valido(drx_sintetico: Path):
    info = inspeccionar_drx(drx_sintetico)
    assert info.es_xml
    assert info.tag_raiz == "PowerGrade"
    assert not info.advertencias
    vocab = dict(info.vocabulario)
    assert vocab["Node"] == 2
    assert vocab["Lut3D"] == 1
    assert vocab["Cdl"] == 1


def test_inspeccionar_no_xml_no_lanza(tmp_path: Path):
    ruta = tmp_path / "binario.drx"
    ruta.write_bytes(b"\x00\x01\x02BLACKMAGIC\xff\xfe")
    info = inspeccionar_drx(ruta)
    assert not info.es_xml
    assert info.tag_raiz is None
    assert info.advertencias  # dice que no es XML, no lanza


def test_buscar_rutas_referenciadas(drx_sintetico: Path):
    rutas = buscar_rutas_referenciadas(drx_sintetico)
    assert any("S-Log3 to Rec709.cube" in r for r in rutas)


def test_avisar_dependencias_faltantes_cuando_no_existe(drx_sintetico: Path, tmp_path: Path):
    carpeta_vacia = tmp_path / "sin_luts"
    carpeta_vacia.mkdir()
    faltantes = avisar_dependencias_faltantes(drx_sintetico, (carpeta_vacia,))
    assert any("S-Log3 to Rec709.cube" in f for f in faltantes)


def test_avisar_dependencias_encontradas_por_nombre(drx_sintetico: Path, tmp_path: Path):
    """El PowerGrade referencia 'LUTs/Sony/S-Log3 to Rec709.cube' (ruta de OTRA
    máquina); si el .cube existe en la carpeta de LUTs local con ese nombre,
    aunque en otra subcarpeta, no debe avisar."""
    carpeta = tmp_path / "mis_luts" / "otra_estructura"
    carpeta.mkdir(parents=True)
    (carpeta / "S-Log3 to Rec709.cube").write_text("LUT_3D_SIZE 2\n")
    faltantes = avisar_dependencias_faltantes(drx_sintetico, (tmp_path / "mis_luts",))
    assert not faltantes


# ---------------------------------------------------------------------------
# 2. Contra PowerGrades reales de Mario. Se saltan solos si no hay material.
# ---------------------------------------------------------------------------

_CARPETA_REALES = Path(__file__).parent / "powergrades_reales"
_DRX_REALES = sorted(_CARPETA_REALES.glob("*.drx")) if _CARPETA_REALES.is_dir() else []

pytestmark_reales = pytest.mark.skipif(
    not _DRX_REALES,
    reason=(
        "no hay PowerGrades reales en tests/powergrades_reales/ (carpeta ignorada por git, "
        "solo lectura). Tarea 4 del día 5: cuando Mario deje material ahí, estos tests "
        "confirman el formato real."
    ),
)


@pytestmark_reales
@pytest.mark.parametrize("ruta", _DRX_REALES, ids=lambda r: r.name)
def test_powergrade_real_se_puede_inspeccionar_sin_lanzar(ruta: Path):
    """El primer hecho que importa: ¿es XML de verdad, o la suposición de foro
    estaba equivocada? Este test no afirma nada del resultado — solo que
    `inspeccionar_drx` no revienta con un archivo real, y deja constancia en
    `info` de lo que encontró para que se pueda mirar a mano."""
    info = inspeccionar_drx(ruta)
    assert info.tamano_bytes > 0
