"""QC de LUT (`core.io.qc.qc_lut`) contra material real de Mario.

Contra `tests/luts_reales/*.cube` (y sus subcarpetas), 79 archivos el día 6
(17-09): 10 `PowerGrades` de un rodaje real y ~35 `.cube` de trabajos suyos, en
realidad 79 contando subcarpetas. Carpeta ignorada por git, SOLO LECTURA: estos
tests se saltan solos si no existe o está vacía, igual que hace
`tests/test_io_drx.py` con `tests/powergrades_reales/`.

DOS GRUPOS DE TESTS
--------------------
1. Que `qc_lut()` no lance sobre NINGÚN `.cube` real, y que el tamaño de
   rejilla que se lee sea el que el propio archivo declara (no una suposición:
   el encargo suponía ~1,4 MB por archivo de 65³; medido, van de 0,5 MB los de
   33³ a 7,6 MB los de 65³ — la cifra de tamaño de fichero no era exacta, pero
   la conclusión sí lo era: hay `.cube` de 65³ de verdad).
2. Las cifras concretas de `CIFRAS.md` §13: clasificación conversión/look de
   cada LUT, quién dispara banding y en qué zona, y qué LUT no son monótonos
   de verdad. Si el material de `tests/luts_reales/` cambia (Mario añade o
   quita algo), estos tests con cifras exactas se saltan solos en vez de dar
   un falso rojo: lo dice el mensaje de skip.

EL CRITERIO DE "CONVERSIÓN" VS. "LOOK" (día 6, no estaba en el repo)
---------------------------------------------------------------------
Se mide, no se lee del nombre del archivo: se aplica el LUT a una rampa de
gris neutro de 17 puntos (`(t, t, t)` para `t` de 0 a 1) y se mide cuánto se
separan R, G y B a la salida (`max - min` sobre los tres canales, el peor
punto de la rampa). Un cambio de curva de transferencia + primarios — que es
lo que hace una conversión de espacio de color de verdad — preserva el
neutro: si entra gris, sale gris. Un "look" con tinte deliberado en las
sombras o las luces no.

Medido sobre los 79 archivos, esa cifra tiene un hueco limpio: los 8 LUT que
son manuales de fábrica o de monitor "CLEAN" (sin ningún look encima) caen
TODOS por debajo de 0,0072; el siguiente LUT real salta a 0,0264 — un factor
3,7 de hueco, no un corte a ciegas en mitad de una nube continua de puntos.
`_UMBRAL_CHROMA_CONVERSION = 0.015` cae justo en medio de ese hueco.

Esto NO es un criterio calibrado contra un conjunto de validación con verdad
conocida (no la hay para "esto es una conversión" en el sentido en que sí la
hay para ΔE2000). Es una medida razonable, explícita, y con el hueco real
delante para quien quiera discutirla — que es lo que pedía el encargo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.io import CODIGO_BANDING, CODIGO_LUT_PLANO, leer_cube, qc_lut
from core.umbrales import SALTO_MINIMO_BANDING, UMBRAL_BANDING, UMBRAL_SOMBRAS

_CARPETA = Path(__file__).parent / "luts_reales"
_RUTAS = sorted(_CARPETA.rglob("*.cube")) if _CARPETA.is_dir() else []

pytestmark_reales = pytest.mark.skipif(
    not _RUTAS,
    reason=(
        "no hay LUT reales en tests/luts_reales/ (carpeta ignorada por git, solo "
        "lectura). Cuando Mario deje material ahí, estos tests confirman las cifras "
        "de CIFRAS.md §13."
    ),
)

#: Fracción 0..1 (chroma máxima sobre la rampa de gris de 17 puntos). Por
#: debajo, se clasifica como conversión de espacio de color; por encima, look.
#: Ver el docstring del módulo para el hueco medido que justifica este corte.
_UMBRAL_CHROMA_CONVERSION = 0.015

_N_RAMPA = 17
_RAMPA = np.linspace(0.0, 1.0, _N_RAMPA)
_NEUTROS = np.stack([_RAMPA, _RAMPA, _RAMPA], axis=-1)


def _chroma_maxima_en_gris(lut) -> float:
    """Cuánto se separan R, G y B al aplicar el LUT a gris neutro puro."""
    salida = lut.apply(_NEUTROS)
    return float((salida.max(axis=-1) - salida.min(axis=-1)).max())


def _clasificar(lut) -> str:
    return "conversion" if _chroma_maxima_en_gris(lut) <= _UMBRAL_CHROMA_CONVERSION else "look"


def _escalones_por_zona(table: np.ndarray) -> tuple[int, int]:
    """(escalones en sombras, escalones en medios).

    Reimplementa a propósito la parte de `core.io.qc._banding` que decide la
    zona de cada escalón, pero SIN el recorte de `MAX_PROBLEMAS_POR_CODIGO`:
    la lista pública que devuelve `qc_lut` está cortada a 20 problemas por
    código y no sirve para contar un total de verdad sobre un LUT de 65³ con
    cientos de escalones. Si se toca `core/io/qc.py::_banding` o
    `UMBRAL_SOMBRAS`, esto hay que revisarlo a la vez.
    """
    piso = 1e-6
    sombras = medios = 0
    for eje in range(3):
        if table.shape[eje] < 3:
            continue
        otros = tuple(a for a in range(3) if a != eje)
        for canal in range(3):
            v = table[..., canal]
            d1 = np.diff(v, axis=eje)
            d2 = np.diff(d1, axis=eje)
            if d2.size == 0:
                continue
            escala = float(np.median(np.abs(d1)))
            limite = UMBRAL_BANDING * max(escala, piso)
            abs_d2 = np.abs(d2)
            mal = (abs_d2 > limite) & (abs_d2 > SALTO_MINIMO_BANDING)
            if not mal.any():
                continue
            por_posicion = mal.sum(axis=otros)
            n_eje = int(table.shape[eje])
            for pos in np.argwhere(por_posicion > 0).ravel():
                nivel_entrada = (int(pos) + 1) / (n_eje - 1)
                if nivel_entrada <= UMBRAL_SOMBRAS:
                    sombras += 1
                else:
                    medios += 1
    return sombras, medios


# ---------------------------------------------------------------------------
# 1. qc_lut() no lanza sobre ningún .cube real.
# ---------------------------------------------------------------------------


@pytestmark_reales
@pytest.mark.parametrize("ruta", _RUTAS, ids=lambda r: r.name)
def test_qc_no_lanza_sobre_ningun_lut_real(ruta: Path):
    lut = leer_cube(ruta)
    informe = qc_lut(lut)  # si esto lanza, el test falla solo
    assert informe.size == lut.size


@pytestmark_reales
def test_tamanos_de_rejilla_del_material_de_hoy():
    """79 archivos el 17-09: 43 de 33³ y 36 de 65³. Ninguno es 17³."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    tamanos = [leer_cube(r).size for r in _RUTAS]
    assert tamanos.count(33) == 43
    assert tamanos.count(65) == 36


# ---------------------------------------------------------------------------
# 2. Clasificación conversión / look, y el patrón de banding del día 6.
# ---------------------------------------------------------------------------

#: Los 8 que clasifican como conversión de espacio de color, por ruta exacta
#: relativa a tests/luts_reales/. Confirmado el 17-09: son manuales de fábrica
#: (DJI, GPLOG) o un LUT de monitor explícitamente "CLEAN" (sin look encima).
_CONVERSION_ESPERADAS = {
    "DJI Mavic 4 Pro D-Log M to Rec.709 V1.cube",
    "DJI Mavic 4 Pro D-Log to Rec.709 V1.cube",
    "DJI Mini 5 Pro D-Log M to Rec.709 LUT.cube",
    "DJI OSMO Pocket 4 D-Log to Rec.709 V1.0.cube",
    "DJI_ZENMUSE_X9_DLog_To_Rec709.cube",
    "GPLOG LUT 2.cube",
    "GPLOG LUT.cube",
    "SECRET SAUCE/A4 MONITOR LUTs V2/SONY Slog3 Monitor LUTs V2/SLog3-Rec709 "
    "CLEAN/SLog3.cine-Rec709.cube",
}


@pytestmark_reales
def test_clasificacion_conversion_son_estos_8_y_solo_estos():
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    encontrados = {
        str(r.relative_to(_CARPETA)) for r in _RUTAS if _clasificar(leer_cube(r)) == "conversion"
    }
    assert encontrados == _CONVERSION_ESPERADAS


@pytestmark_reales
def test_los_8_lut_de_conversion_disparan_banding():
    """La pregunta central del día 6: ¿se repite con material real el patrón
    de banding en un LUT de conversión que se decidió el día 3? Sí, los 8 lo
    disparan (y de hecho los 71 "look" también: ver CIFRAS.md §13)."""
    rutas = [r for r in _RUTAS if str(r.relative_to(_CARPETA)) in _CONVERSION_ESPERADAS]
    if len(rutas) != 8:
        pytest.skip(f"no está el material de conversión esperado (hay {len(rutas)}, no 8)")
    assert rutas, "guardado arriba: con len(rutas) == 8 esto nunca está vacío"
    for ruta in rutas:
        informe = qc_lut(leer_cube(ruta))
        assert CODIGO_BANDING in informe.codigos(), ruta.name


@pytestmark_reales
def test_en_los_lut_de_conversion_la_mayoria_del_banding_esta_en_medios_no_en_sombras():
    """Esto es lo que motivó reescribir `EXPLICACION_MEDIOS` en
    `core/io/qc.py`: medido sobre los 8 LUT de conversión reales, 1182 de
    1232 escalones (96%) NO están pegados al negro. El texto viejo daba a
    entender justo lo contrario: que un escalón fuera de sombras era lo raro."""
    rutas = [r for r in _RUTAS if str(r.relative_to(_CARPETA)) in _CONVERSION_ESPERADAS]
    if len(rutas) != 8:
        pytest.skip(f"no está el material de conversión esperado (hay {len(rutas)}, no 8)")
    total_sombras = total_medios = 0
    for ruta in rutas:
        tabla = np.asarray(leer_cube(ruta).table, dtype=np.float64)
        sombras, medios = _escalones_por_zona(tabla)
        total_sombras += sombras
        total_medios += medios
    assert (total_sombras, total_medios) == (50, 1182)
    assert total_medios > total_sombras


@pytestmark_reales
def test_dji_mavic_4_pro_no_tiene_ni_un_escalon_en_sombras():
    """El ejemplo concreto que cita el comentario de `EXPLICACION_MEDIOS`: un
    manual de fábrica con 130 escalones de banding, y los 130 en medios,
    ninguno pegado al negro."""
    ruta = _CARPETA / "DJI Mavic 4 Pro D-Log to Rec.709 V1.cube"
    if not ruta.exists():
        pytest.skip("no está 'DJI Mavic 4 Pro D-Log to Rec.709 V1.cube'")
    informe = qc_lut(leer_cube(ruta))
    problemas = informe.por_codigo(CODIGO_BANDING)
    assert problemas, "tiene que seguir avisando de banding"
    # la lista pública está cortada a 20; de esos, ninguno se explica como sombras
    assert all("Merece un vistazo" in p.mensaje for p in problemas)
    assert all("ESPERABLES" not in p.mensaje for p in problemas)
    assert informe.metricas["escalones_de_banding"] == 130.0


# ---------------------------------------------------------------------------
# 3. Lo que sí es un problema real: limpio en gamut/NaN/plano, y no_monotonia
#    dispara en la mayoría del material (hallazgo del día 6, sin tocar).
# ---------------------------------------------------------------------------


@pytestmark_reales
def test_ningun_lut_real_tiene_gamut_fuera_ni_nan_ni_esta_plano():
    """Lo único que sale limpio del todo: cero avisos de gamut, cero
    NaN/infinitos y cero LUT planos en los 79 archivos."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    for ruta in _RUTAS:
        informe = qc_lut(leer_cube(ruta))
        assert informe.metricas["valores_fuera_de_gamut"] == 0.0, ruta.name
        assert informe.metricas["no_finitos"] == 0.0, ruta.name
        assert CODIGO_LUT_PLANO not in informe.codigos(), ruta.name


@pytestmark_reales
def test_no_monotonia_dispara_en_la_mayoria_del_material_real():
    """El hallazgo mayor del día 6, y el que NO se toca hoy (ver BITACORA.md):
    76 de 79 LUT reales -incluidos manuales de fábrica de DJI- disparan
    no_monotonia, que en `core/io/qc.py` es un ERROR, no un aviso. No se toca
    `TOL_MONOTONIA` ni el detector aquí: se deja medido, con nombre, para que
    alguien decida qué hacer con ello."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    con_no_monotonia = sum(
        1 for r in _RUTAS if qc_lut(leer_cube(r)).metricas["celdas_no_monotonas"] > 0
    )
    assert con_no_monotonia == 76


@pytestmark_reales
def test_dji_mavic_4_pro_tiene_una_caida_de_verdad_no_ruido_de_redondeo():
    """Nombre exacto para Mario: este manual de fábrica de DJI baja el canal
    rojo 0,0425 (~11/255) en un punto. No es ruido de los 6 decimales del
    fichero (que sería del orden de 1e-6): es cien veces mayor que eso."""
    ruta = _CARPETA / "DJI Mavic 4 Pro D-Log to Rec.709 V1.cube"
    if not ruta.exists():
        pytest.skip("no está 'DJI Mavic 4 Pro D-Log to Rec.709 V1.cube'")
    informe = qc_lut(leer_cube(ruta))
    assert informe.metricas["celdas_no_monotonas"] == 12.0
    assert informe.metricas["peor_caida_monotonia"] == pytest.approx(-0.04249, abs=1e-4)


@pytestmark_reales
def test_los_peores_no_monotonos_son_estos_seis_archivos_sony():
    """Las caídas más grandes de todas (>0,19 sobre 0..1, sobre 48/255) son
    seis variantes del mismo LUT de monitor Sony: 'SECRET SAUCE/A4 MONITOR
    LUTs V2/SONY Slog3 Monitor LUTs V2/'. Es información para Mario, no algo
    que esta app vaya a arreglar."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    peores = sorted(
        _RUTAS,
        key=lambda r: qc_lut(leer_cube(r)).metricas["peor_caida_monotonia"],
    )[:6]
    nombres = {str(r.relative_to(_CARPETA)) for r in peores}
    assert all("SONY Slog3 Monitor LUTs V2" in n for n in nombres), nombres
