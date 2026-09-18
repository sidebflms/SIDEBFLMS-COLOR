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

DÍA 7: MONOTONÍA RELAJADA PARA "LOOK" (`TOL_MONOTONIA_LOOK`)
--------------------------------------------------------------
La sección 4 de este archivo mide la distribución real de reversiones de
monotonía en los 71 LUT "look" y confirma el umbral fijado en
`core.umbrales.TOL_MONOTONIA_LOOK`. Cifras completas y el comando reproducible
en `CIFRAS.md` §19. Resumen: el umbral relajado sigue cazando los LUT rotos a
propósito de T4 con margen, pero **no arregla la mayoría de los falsos
positivos reales**: 63 de los 71 LUT "look" siguen disparando `no_monotonia`
incluso con la tolerancia más ancha que protege a T4, porque su peor salto
real (mediana 0,028 por archivo) es mayor que el techo que hay que respetar
(0,01). Con clasificación automática, el material real pasa de 76/79 a 70/79
disparando `no_monotonia` — una mejora real pero pequeña, no la solución.

También se documenta aquí un bug real encontrado al medir el día 7 y
CORREGIDO en la sesión de seguimiento: el `break` de
`core.io.qc._monotonia()` cortaba el bucle de los tres ejes en cuanto la
lista de problemas llegaba a `MAX_PROBLEMAS_POR_CODIGO` (20), así que
`metricas["celdas_no_monotonas"]` y `metricas["peor_caida_monotonia"]`
**infracontaban** en 67 de los 79 archivos reales cuando el eje que se
procesaba primero ya llenaba esa lista él solo. Nunca afectó a si
`no_monotonia` se detecta (el código se añade a `informe.codigos()` en
cuanto el primer eje con problemas se procesa) ni a la lista pública de
`problemas` (ya estaba acotada por el mismo presupuesto restante,
`MAX_PROBLEMAS_POR_CODIGO - len(problemas)`, sin necesitar el `break`), sólo
a la magnitud de `total`/`peor` que se enseña. El `break` era redundante y se
borró; ver `test_bug_el_break_de_monotonia_infracuenta_en_jota_lut_fitz` más
abajo, ahora un test de regresión que confirma la cifra corregida.

DÍA 8: LA PRUEBA DEL EJE — ¿DÓNDE OCURREN LAS REVERSIONES, NO CUÁNTAS?
------------------------------------------------------------------------
El 70/79 de arriba no bajó apenas con la tolerancia por clase (76/79 -> 70/79).
Hipótesis de Mario, sin probar hasta hoy: `_monotonia()` exige que el canal
`c` suba al mover el eje `c` para CUALQUIER combinación fija de los otros dos
ejes — recorre las n² líneas paralelas del cubo, no sólo la diagonal neutra
R=G=B. Pedirle a un LUT de "look" (que mezcla canales a propósito, eso es lo
que hace un grado) que no tenga ni una reversión en NINGÚN punto del cubo es
mucho más estricto que pedirle que no la tenga a lo largo del gris. Sección 5
mide las dos reglas sobre los 79 archivos: **todo el cubo (la regla de
`_monotonia()` hoy) sigue confirmando 70/79; sólo la diagonal neutra R=G=B
baja a 3/79.** La hipótesis se confirma. Cifras y nombres en `CIFRAS.md` §21
y `BITACORA.md` D8-0. No se ha tocado `core/io/qc.py::_monotonia()` ni ningún
umbral: esto es sólo la medida, la decisión de qué hacer con ella queda para
Mario.

DÍA 9: ¿SÓLO EL EJE PROPIO, SIN LAS n² COMBINACIONES? (medición distinta de D8-0)
------------------------------------------------------------------------------
Encargo nuevo de Mario, delegado de nuevo a una sesión limpia por el mismo motivo
que D8-0 (quien diseñó `TOL_MONOTONIA_LOOK` y la diagonal neutra no arbitra su
propia hipótesis): "mide cuántos saltan SOLO en su eje propio (R barriendo el eje
R, G el G, B el B), en vez de barrer los tres ejes para los tres canales". Esto es
DISTINTO de la diagonal neutra de la sección 5: la diagonal mueve los TRES canales
A LA VEZ por una sola línea (R=G=B); aquí se mueve UN canal cada vez, con los
otros dos FIJOS en el centro del cubo (no en la diagonal) — tres líneas sueltas,
no n² combinaciones y no un movimiento conjunto de los tres.

Sección 6 mide esa regla exacta sobre los 79 archivos: **36/79** disparan
`no_monotonia` sólo en su eje propio (con los otros dos fijos en el centro),
frente a 70/79 con todo el cubo y 3/79 con la diagonal neutra de D8-0. El
resultado NO es una confirmación tan limpia como la diagonal: 36/79 reduce el
recuento casi a la mitad, pero se queda lejos del 3/79 — muchos LUT "look" siguen
invirtiendo su propio canal incluso en la línea central, no sólo en zonas
extremas de tinte. Cifras y nombres en `CIFRAS.md` §22 y `BITACORA.md` D9-0. No
se ha tocado `core/io/qc.py::_monotonia()` ni ningún umbral: esto es sólo la
medida.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.io import (
    CODIGO_BANDING,
    CODIGO_LUT_PLANO,
    CODIGO_NO_MONOTONIA,
    clasificar_lut,
    leer_cube,
    qc_lut,
)
from core.io.lut_malos import lut_no_monotono
from core.umbrales import (
    SALTO_MINIMO_BANDING,
    TOL_MONOTONIA,
    TOL_MONOTONIA_LOOK,
    UMBRAL_BANDING,
    UMBRAL_SOMBRAS,
)

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
def test_los_peores_no_monotonos_son_jota_lut_fitz_y_cinco_sony():
    """Corregido el bug del `break` (ver
    `test_bug_el_break_de_monotonia_infracuenta_en_jota_lut_fitz`): la caída
    más grande de TODO el material real es `Jota_lut_fitz.cube` (-0,315, eje
    azul), no una de las variantes Sony — antes quedaba oculta porque
    `qc_lut()` cortaba el escaneo en el eje rojo (-0,180) antes de llegar al
    azul. Las otras cinco peores (>0,22 sobre 0..1) siguen siendo variantes
    del mismo LUT de monitor Sony: 'SECRET SAUCE/A4 MONITOR LUTs V2/SONY
    Slog3 Monitor LUTs V2/'. Es información para Mario, no algo que esta app
    vaya a arreglar."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    peores = sorted(
        _RUTAS,
        key=lambda r: qc_lut(leer_cube(r)).metricas["peor_caida_monotonia"],
    )[:6]
    nombres = [str(r.relative_to(_CARPETA)) for r in peores]
    assert nombres[0] == "Jota_lut_fitz.cube", nombres
    assert all("SONY Slog3 Monitor LUTs V2" in n for n in nombres[1:]), nombres


@pytestmark_reales
def test_bug_el_break_de_monotonia_infracuenta_en_jota_lut_fitz():
    """Bug real encontrado al medir el día 7, CORREGIDO en la sesión de
    seguimiento: `_monotonia()` cortaba el bucle de los tres ejes en cuanto
    la lista de problemas llegaba a `MAX_PROBLEMAS_POR_CODIGO` (20). En un
    LUT con miles de reversiones ya en el primer eje procesado, eso
    significaba que los ejes siguientes NUNCA se examinaban, y
    `peor_caida_monotonia` / `celdas_no_monotonas` salían más pequeños que
    la realidad.

    Ejemplo concreto: `Jota_lut_fitz.cube` es el peor LUT "look" de TODO el
    material real (peor reversión de verdad: -0,315, en el eje azul). Antes
    del fix, `qc_lut()` cortaba antes de llegar al eje azul y reportaba
    -0,180 (el peor del eje rojo, que se procesa primero) — por eso no
    aparecía entre los "6 peores Sony" de
    `test_los_peores_no_monotonos_son_jota_lut_fitz_y_cinco_sony`. El fix fue
    borrar el `break` redundante: la lista pública de `problemas` ya estaba
    acotada por el presupuesto restante (`MAX_PROBLEMAS_POR_CODIGO -
    len(problemas)`), así que sólo cambió la magnitud de `total`/`peor`, no
    qué se detecta ni la lista de problemas que se enseña.

    Este test ahora es de REGRESIÓN: confirma que `qc_lut()` coincide con el
    cálculo directo sin recorte."""
    ruta = _CARPETA / "Jota_lut_fitz.cube"
    if not ruta.exists():
        pytest.skip("no está 'Jota_lut_fitz.cube'")
    table = np.asarray(leer_cube(ruta).table, dtype=np.float64)

    def peor_real(tabla: np.ndarray) -> float:
        peor = 0.0
        for eje in range(3):
            d = np.diff(tabla[..., eje], axis=eje)
            if (d < 0).any():
                peor = min(peor, float(d.min()))
        return peor

    informe = qc_lut(leer_cube(ruta))
    assert peor_real(table) == pytest.approx(-0.31504, abs=1e-4)
    assert informe.metricas["peor_caida_monotonia"] == pytest.approx(
        peor_real(table), abs=1e-9
    ), (
        "si esto deja de coincidir, o volvió el bug del break, o el material "
        "cambió — hay que revisarlo, no borrarlo sin mirar"
    )


# ---------------------------------------------------------------------------
# 4. Día 7: distribución real de reversiones en "look" y TOL_MONOTONIA_LOOK.
#    Cifras completas en CIFRAS.md §19.
# ---------------------------------------------------------------------------


def _peor_reversion_por_eje(table: np.ndarray) -> float:
    """Magnitud (positiva) de la peor caída de monotonía diagonal, escaneando
    los TRES ejes siempre (sin el corte de `MAX_PROBLEMAS_POR_CODIGO` que
    tiene `_monotonia()` — ver el bug de arriba). Es lo que hace falta para
    medir la distribución real sin que el recorte de la lista pública la
    distorsione."""
    peor = 0.0
    for eje in range(3):
        d = np.diff(table[..., eje], axis=eje)
        if (d < 0).any():
            peor = max(peor, float(-d.min()))
    return peor


@pytestmark_reales
def test_distribucion_de_reversiones_en_luts_look():
    """La medida detrás de `TOL_MONOTONIA_LOOK`: por cada uno de los 71 LUT
    "look", el peor salto de monotonía diagonal (sin recorte de ningún tipo).
    La mediana POR ARCHIVO (0,028) es casi tres veces el techo que hay que
    respetar por T4 (0,01): la mayoría de las reversiones "normales de un
    look" no caben en ningún umbral que siga cazando el LUT roto de T4."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    peores_look = [
        _peor_reversion_por_eje(np.asarray(leer_cube(r).table, dtype=np.float64))
        for r in _RUTAS
        if clasificar_lut(leer_cube(r)) == "look"
    ]
    assert len(peores_look) == 71
    arr = np.array(peores_look)
    assert int((arr == 0.0).sum()) == 2, "sólo 2 LUT look sin ninguna reversión"
    assert float(np.median(arr)) == pytest.approx(0.02808, abs=1e-4)
    assert float(arr.max()) == pytest.approx(0.31504, abs=1e-4)


@pytestmark_reales
def test_tol_monotonia_look_limpia_solo_8_de_71_luts_look():
    """La tensión dicha con cifras: `TOL_MONOTONIA_LOOK` (0,005, con margen
    real bajo el techo de T4) sólo deja limpios 8 de los 71 LUT "look" reales.
    Los otros 63 (89%) SIGUEN disparando `no_monotonia` porque su peor caída
    real supera el techo. La hipótesis de Mario (la monotonía relajada es
    correcta para un look) es cierta conceptualmente, pero no resuelve la
    mayoría de los falsos positivos de material real: el hueco entre "look
    legítimo" y "techo que protege T4" no es un hueco limpio, es una zona
    gris."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    look = [r for r in _RUTAS if clasificar_lut(leer_cube(r)) == "look"]
    assert len(look) == 71
    disparan = sum(
        1
        for r in look
        if CODIGO_NO_MONOTONIA in qc_lut(leer_cube(r), clasificacion="look").codigos()
    )
    assert disparan == 63


@pytestmark_reales
def test_no_monotonia_con_clasificacion_automatica_baja_de_76_a_70_de_79():
    """El titular del día 7: clasificando cada uno de los 79 archivos con
    `clasificar_lut()` y usando esa clasificación en `qc_lut()`, el recuento
    de `no_monotonia` baja de 76/79 (regla de ayer, estricta para todos) a
    70/79. Una mejora real (6 archivos menos) pero pequeña: la hipótesis de
    Mario no estaba mal, pero no arregla la mayoría del material real."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")
    disparan_regla_nueva = 0
    for r in _RUTAS:
        lut = leer_cube(r)
        clase = clasificar_lut(lut)
        if CODIGO_NO_MONOTONIA in qc_lut(lut, clasificacion=clase).codigos():
            disparan_regla_nueva += 1
    assert disparan_regla_nueva == 70


@pytestmark_reales
def test_tol_monotonia_look_sigue_cazando_los_luts_rotos_de_t4_con_margen():
    """El techo duro (RESTRICCIONES DURAS del encargo del día 7): la versión
    relajada tiene que seguir cazando los LUT rotos a propósito de T4.
    `lut_no_monotono` usa `caida=0.01` por defecto (catálogo de T4) y el test
    T4 real construye el suyo con 0.02 (`tests/test_entregables.py::
    test_T4_caza_un_lut_no_monotono`); los dos siguen cazándose con
    `TOL_MONOTONIA_LOOK`, con 2x y 4x de margen respectivamente. No depende
    de material real (usa el generador de LUT rotos), pero vive aquí porque
    es la comprobación que justifica el valor fijado en `core/umbrales.py`."""
    for caida in (0.01, 0.02):
        informe = qc_lut(
            lut_no_monotono(size=17, eje=0, caida=caida),
            clasificacion="look",
            tol_monotonia_look=TOL_MONOTONIA_LOOK,
        )
        assert CODIGO_NO_MONOTONIA in informe.codigos(), (
            f"con caida={caida} el LUT roto de T4 tiene que seguir cazándose"
        )
    # Y el punto exacto donde deja de cazar está por debajo de los dos: no es
    # un margen de mentira, es un margen medido.
    justo_debajo = qc_lut(
        lut_no_monotono(size=17, eje=0, caida=TOL_MONOTONIA_LOOK * 0.99),
        clasificacion="look",
        tol_monotonia_look=TOL_MONOTONIA_LOOK,
    )
    assert CODIGO_NO_MONOTONIA not in justo_debajo.codigos()


# ---------------------------------------------------------------------------
# 5. Día 8: la prueba del eje — diagonal neutra (R=G=B) vs. todo el cubo.
#    Cifras completas en CIFRAS.md §21.
# ---------------------------------------------------------------------------


def _diagonal_no_monotona(table: np.ndarray, tol: float) -> bool:
    """¿Baja algún canal de salida a lo largo de la diagonal neutra R=G=B?

    Operacionalización de "sólo en su eje propio" (hipótesis de Mario, día
    8): en vez de exigir que el canal `c` suba al mover el eje `c` para
    CUALQUIER combinación fija de los otros dos ejes -que es lo que hace
    `core.io.qc._monotonia()` hoy: `v = table[..., eje]`, `diff(v,
    axis=eje)` recorre las n² líneas paralelas a ese eje, con canal==eje
    siempre, nunca canal contra un eje distinto-, se exige sólo que suba a
    lo largo del ÚNICO camino donde R, G y B se mueven juntos: la rampa de
    gris `(i, i, i)` para i=0..n-1. Son n puntos por canal, no n * n² = n³:
    la lectura más estricta posible de "eje propio" que sigue siendo mucho
    más laxa que "todo el cubo".
    """
    n = table.shape[0]
    diagonal = table[np.arange(n), np.arange(n), np.arange(n), :]  # (n, 3)
    d = np.diff(diagonal, axis=0)  # (n-1, 3): un delta por canal y por paso
    return bool((d < -tol).any())


@pytestmark_reales
def test_prueba_del_eje_diagonal_neutra_confirma_la_hipotesis():
    """La prueba de diez minutos que pidió Mario el día 8.

    Para los 79 archivos reales, con la MISMA tolerancia por clase que usa
    `qc_lut()` hoy (`TOL_MONOTONIA` para conversión, `TOL_MONOTONIA_LOOK`
    para look, decidida por `clasificar_lut()`), se comparan dos reglas:

    * **todo el cubo** (la regla real de `_monotonia()` hoy): confirma el
      70/79 de `test_no_monotonia_con_clasificacion_automatica_baja_de_76_a_70_de_79`.
    * **sólo la diagonal neutra** (`_diagonal_no_monotona`, arriba): baja a
      **3/79**. La hipótesis de Mario se CONFIRMA: casi toda la reversión
      que dispara `no_monotonia` hoy ocurre lejos del gris -en zonas de
      tinte, donde la mezcla entre canales es justo lo que hace un look-, no
      a lo largo del eje neutro. Sólo 3 LUT "look" tienen una reversión real
      incluso en su propio gris: `EKTAR 100 REC709 SONY.cube`, `EKTAR 100
      SIDEB SONY.cube` y `Jota_lut_fitz.cube` (el mismo LUT con la reversión
      más grande de todo el material, D7-7/§19 -no es casualidad: si baja en
      el cubo, es candidato a que también baje en su gris).

    No se toca `core/io/qc.py::_monotonia()` ni ningún umbral aquí: es sólo
    la medida. Ver `CIFRAS.md` §21 y `BITACORA.md` D8-0 para la cifra con su
    comando y la propuesta que se deja para que Mario decida.
    """
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")

    dispara_cubo_completo = 0
    dispara_solo_diagonal = 0
    nombres_diagonal: list[str] = []
    for r in _RUTAS:
        lut = leer_cube(r)
        clase = clasificar_lut(lut)
        tol = TOL_MONOTONIA_LOOK if clase == "look" else TOL_MONOTONIA
        if CODIGO_NO_MONOTONIA in qc_lut(lut, clasificacion=clase).codigos():
            dispara_cubo_completo += 1
        table = np.asarray(lut.table, dtype=np.float64)
        if _diagonal_no_monotona(table, tol):
            dispara_solo_diagonal += 1
            nombres_diagonal.append(str(r.relative_to(_CARPETA)))

    assert dispara_cubo_completo == 70, (
        "esto tiene que seguir coincidiendo con el 70/79 de §19 (regla de hoy, "
        "todo el cubo); si cambia, el material o el detector cambiaron"
    )
    assert dispara_solo_diagonal == 3, nombres_diagonal
    assert sorted(nombres_diagonal) == sorted(
        [
            "EKTAR 100 REC709 SONY.cube",
            "EKTAR 100 SIDEB SONY.cube",
            "Jota_lut_fitz.cube",
        ]
    )


# ---------------------------------------------------------------------------
# 6. Día 9: la prueba del eje propio — tres líneas sueltas (R, G, B) con los
#    otros dos canales fijos en el centro, en vez de la diagonal neutra o
#    todo el cubo. Cifras completas en CIFRAS.md §22.
# ---------------------------------------------------------------------------


def _eje_propio_no_monotono(table: np.ndarray, tol: float) -> bool:
    """¿Baja el canal `c` a lo largo de la línea que barre SÓLO el eje `c`,
    con los otros dos canales fijos en el centro del cubo?

    Operacionalización de "salta sólo en su eje propio" (encargo de Mario,
    día 9, distinto del de día 8): en vez de la diagonal neutra
    (`_diagonal_no_monotona`, arriba, mueve los TRES canales A LA VEZ por
    R=G=B) o el cubo completo (`core.io.qc._monotonia()`, canal `c` contra
    eje `c` para las n² combinaciones de los otros dos ejes), aquí se mueve
    UN solo canal por vez, con los otros dos FIJOS en el punto medio del
    cubo (`(n - 1) // 2`, exacto para los tamaños 33 y 65 del material real,
    ambos impares) — el valor de referencia más natural, ya que fijar los
    otros dos en 0 o en el extremo no representa dónde vive el contenido
    real. Son sólo TRES líneas de `n` puntos cada una, no n² por eje:

        eje R: table[:, j0, k0, 0]   (j0 = k0 = centro)
        eje G: table[i0, :, k0, 1]   (i0 = k0 = centro)
        eje B: table[i0, j0, :, 2]   (i0 = j0 = centro)

    Un LUT "salta sólo en su eje propio" si ALGUNA de las tres líneas viola
    la monotonía con la tolerancia que le toque.
    """
    n = table.shape[0]
    centro = (n - 1) // 2
    lineas = (
        table[:, centro, centro, 0],
        table[centro, :, centro, 1],
        table[centro, centro, :, 2],
    )
    return any(bool((np.diff(v) < -tol).any()) for v in lineas)


@pytestmark_reales
def test_prueba_del_eje_propio_centro_del_cubo_matiza_la_hipotesis():
    """El encargo de diez minutos que pidió Mario el día 9, distinto del de
    día 8: no la diagonal neutra (los tres canales moviéndose a la vez), sino
    tres líneas sueltas -una por eje- que mueven UN canal cada vez con los
    otros dos fijos en el centro del cubo. Ver `_eje_propio_no_monotono`
    arriba para la operacionalización exacta y por qué el centro (y no 0 ni
    el extremo) es el punto de referencia.

    Para los 79 archivos reales, con la MISMA tolerancia por clase que usa
    `qc_lut()` hoy:

    * **todo el cubo** (regla real de `_monotonia()` hoy): confirma el
      70/79 de la sección 5 y de
      `test_no_monotonia_con_clasificacion_automatica_baja_de_76_a_70_de_79`.
    * **sólo el eje propio, centro fijo** (`_eje_propio_no_monotono`):
      **36/79** (4/8 conversión + 32/71 look).

    El resultado NO confirma la hipótesis con la misma fuerza que la
    diagonal neutra de D8-0 (3/79): 36/79 reduce el recuento casi a la
    mitad respecto al cubo completo, pero se queda lejos del 3/79. La
    diferencia con la diagonal es real y explica el hueco: la diagonal exige
    que los TRES canales fallen a la vez en un único punto (R=G=B), mientras
    que aquí basta con que UN canal falle en su propia línea, con los otros
    dos en un valor fijo (el centro) que no es especialmente protector. Eso
    significa que muchos LUT "look" invierten su propio canal incluso a lo
    largo de esa línea central -no sólo en las combinaciones extremas de
    tinte que sí recorre el cubo completo-, así que restringir la
    comprobación a "el eje propio con los otros dos fijos" no es, por sí
    solo, una vía tan limpia como restringirla a la diagonal neutra. No se
    toca `core/io/qc.py::_monotonia()` ni ningún umbral aquí: es sólo la
    medida. Ver `CIFRAS.md` §22 y `BITACORA.md` D9-0."""
    if len(_RUTAS) != 79:
        pytest.skip(f"el material cambió: hay {len(_RUTAS)} archivos, no 79")

    dispara_cubo_completo = 0
    dispara_eje_propio = 0
    por_clase = {"conversion": 0, "look": 0}
    nombres_eje_propio: list[str] = []
    for r in _RUTAS:
        lut = leer_cube(r)
        clase = clasificar_lut(lut)
        tol = TOL_MONOTONIA_LOOK if clase == "look" else TOL_MONOTONIA
        if CODIGO_NO_MONOTONIA in qc_lut(lut, clasificacion=clase).codigos():
            dispara_cubo_completo += 1
        table = np.asarray(lut.table, dtype=np.float64)
        if _eje_propio_no_monotono(table, tol):
            dispara_eje_propio += 1
            por_clase[clase] += 1
            nombres_eje_propio.append(str(r.relative_to(_CARPETA)))

    assert dispara_cubo_completo == 70, (
        "esto tiene que seguir coincidiendo con el 70/79 de §19/§21; si cambia, "
        "el material o el detector cambiaron"
    )
    assert dispara_eje_propio == 36, nombres_eje_propio
    assert (por_clase["conversion"], por_clase["look"]) == (4, 32)
