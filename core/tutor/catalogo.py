"""El catálogo de reglas del tutor: condición sobre lo medido -> frase.

LA REGLA QUE HACE ESTO HONESTO (día 8, tarea 2.1)
----------------------------------------------------
El tutor es un generador de frases, y los generadores de frases inventan. Para
que éste no lo haga:

1. Cada regla es **condición sobre una característica medida -> frase**. Nada
   de consejos genéricos de colorimetría que podrían salir de cualquier
   tutorial — si una regla no necesita `ContextoTutor` para decidir si dispara
   y qué decir, no es una regla de este catálogo.
2. Cada `ReglaTutor` lleva su `validacion` puesta a mano, cruzada contra la
   auditoría de umbrales del día 7 (`CIFRAS.md` §20) o contra lo que se ha
   medido después:

   - `"validado"` — el umbral que usa se ha visto contra material real y
     discrimina (no dispara con todo el material real, sólo con lo que de
     verdad se sale). La frase puede afirmar.
   - `"descriptiva"` — no hay umbral de "esto está mal": la regla reporta un
     HECHO medido (un valor, una diferencia con la referencia), no un
     veredicto. Puede decir el hecho con seguridad; la explicación de POR QUÉ
     pasa, si la lleva, va con matiz ("puede ser", "es lo típico de").
   - `"no_validable"` — el umbral que usa vive en la lista de 36 del día 7 que
     no se ha podido probar contra material real (necesita metraje que no
     existe). La regla SÍ puede escribirse, pero la frase tiene que llevar
     matiz siempre — nunca afirma un veredicto con un umbral que no se ha
     visto contra la realidad que decide.
   - `"solo_sintetico"` — como el anterior pero el umbral se ha visto SÓLO
     contra ejemplos fabricados para fallar, nunca contra material real. Hoy
     no hay ninguna regla en esta categoría (todo lo de `core/io/qc.py` que
     estaba aquí ya se validó el día 7); se deja el valor por si hace falta.

3. **Si una regla necesita una característica que no se está midiendo, no se
   escribe la regla.** Lo que se hace en su lugar es anotar en `NOTAS.md` qué
   haría falta medir — ver la sección "Lo que no se escribió, y por qué".

CÓMO SE LEE UNA REGLA
----------------------
`evaluar(ContextoTutor) -> ResultadoRegla | None`. `None` significa "esta
regla no tiene nada que decir sobre este clip" — no es un fallo, es la
mayoría de los casos: un clip sin defectos no tiene por qué disparar nada.
`explicar.explicar()` recorre el catálogo entero y junta lo que SÍ disparó.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from core.color import convert
from core.contracts import WORKING_SPACE, ClipAnalysis, DeteccionEspacio, MatchResult
from core.io import CODIGO_GAMUT, CODIGO_LUT_PLANO, LUTQualityReport
from core.matching.contenido import UMBRAL_DESAJUSTE, UMBRAL_HUELLA
from core.umbrales import SUELO_NEGRO_VISIBLE_TUTOR, SUELO_SATURACION_ALTA_TUTOR, TOL_GAMUT

Validacion = Literal["validado", "descriptiva", "no_validable", "solo_sintetico"]


@dataclass(frozen=True)
class ContextoTutor:
    """Todo lo que una regla puede mirar. Nunca toca Resolve ni la red.

    `analisis`/`analisis_referencia` salen de `core.analysis.analizar_imagen`
    (o `analizar_clip`) sobre el fotograma del clip y, si hay una referencia
    elegida, el de ella. `qc_look` es el informe de `core.io.qc.qc_lut` sobre
    el look que está aplicado ahora mismo — `None` si todavía no hay ninguno.
    """

    analisis: ClipAnalysis
    analisis_referencia: ClipAnalysis | None = None
    deteccion: DeteccionEspacio | None = None
    match: MatchResult | None = None
    qc_look: LUTQualityReport | None = None


@dataclass(frozen=True)
class ResultadoRegla:
    """Lo que devuelve una regla que SÍ dispara: las dos partes que dependen
    de este clip en concreto. El resto de `Frase` (característica, umbral,
    validación, referencia de cifras) es siempre el mismo para esa regla y
    vive en `ReglaTutor`."""

    texto: str  # modo fácil: la frase entera, sin jerga
    valor_medido: str  # modo avanzado: el hecho medido, en texto legible


@dataclass(frozen=True)
class Frase:
    """Una regla que disparó sobre un clip concreto, con toda su trazabilidad."""

    regla_id: str
    texto: str
    caracteristica: str
    valor_medido: str
    umbral: str | None
    validacion: Validacion
    cifras_ref: str


@dataclass(frozen=True)
class ReglaTutor:
    """Una fila del catálogo. La metadata es fija; `evaluar` es lo único que
    mira el clip."""

    id: str
    caracteristica: str  # qué mide, en una frase
    # Nombre de la constante en core.umbrales, o None si la regla no usa
    # ningún umbral (p.ej. content_mismatch, que es un booleano ya decidido
    # por core.matching). Una regla "descriptiva" SÍ puede tener umbral: lo
    # que decide es CUÁNDO hay algo que contar, no si algo "está mal".
    umbral_nombre: str | None
    umbral_valor: str | None  # el valor, ya formateado, o None si es descriptiva
    validacion: Validacion
    cifras_ref: str
    evaluar: Callable[[ContextoTutor], ResultadoRegla | None]


# ---------------------------------------------------------------------------
# Grupo A — sobre el look aplicado, vía core.io.qc.qc_lut (validado día 7)
# ---------------------------------------------------------------------------


def _regla_look_plano(ctx: ContextoTutor) -> ResultadoRegla | None:
    if ctx.qc_look is None:
        return None
    problemas = ctx.qc_look.por_codigo(CODIGO_LUT_PLANO)
    if not problemas:
        return None
    return ResultadoRegla(
        texto=(
            "El look que tienes puesto convierte toda la imagen a un solo color. "
            "Antes de aplicarlo a más clips, comprueba que es el archivo que querías."
        ),
        valor_medido=f"código lut_plano en el informe de calidad del look: {problemas[0].mensaje}",
    )


def _regla_look_gamut(ctx: ContextoTutor) -> ResultadoRegla | None:
    if ctx.qc_look is None:
        return None
    problemas = ctx.qc_look.por_codigo(CODIGO_GAMUT)
    if not problemas:
        return None
    n = int(ctx.qc_look.metricas.get("valores_fuera_de_gamut", len(problemas)))
    return ResultadoRegla(
        texto=(
            f"El look que tienes puesto saca algunos valores fuera del rango normal "
            f"({n} en la rejilla del LUT). Resolve los recorta al aplicarlos — es "
            f"habitual en looks de mucho contraste, pero si no era la intención, "
            f"conviene revisarlo."
        ),
        valor_medido=f"gamut: {n} valores de la rejilla fuera de 0..1",
    )


# ---------------------------------------------------------------------------
# Grupo B — descriptivas sobre el material, vía core.analysis.ColorStats
# ---------------------------------------------------------------------------

def _porcentaje_rec709(punto_working_space: np.ndarray) -> float:
    """Un punto (3,) de `WORKING_SPACE` -> porcentaje 0..100, pasado por la
    curva de cámara Rec.709 (BT.709-6) para que sea un número que se lee como
    "tanto por ciento de recorrido tonal", no un código crudo del espacio de
    trabajo (`davinci_wg_intermediate`, que es logarítmico y NO tiene el negro
    en 0)."""
    img = np.asarray(punto_working_space, dtype=np.float64).reshape(1, 1, 3)
    convertido = np.asarray(convert(img, WORKING_SPACE, "rec709"))
    return float(np.clip(convertido.reshape(3).mean(), 0.0, 1.0) * 100.0)


def _regla_punto_negro(ctx: ContextoTutor) -> ResultadoRegla | None:
    negro_ws = np.asarray(ctx.analisis.stats.black_point, dtype=np.float64)
    porcentaje = _porcentaje_rec709(negro_ws)
    if porcentaje < SUELO_NEGRO_VISIBLE_TUTOR * 100.0:
        return None
    if ctx.deteccion is not None and ctx.deteccion.segura and ctx.deteccion.space not in (None, "rec709"):
        motivo = f" El material viene marcado como {ctx.deteccion.space}: el negro sin normalizar es lo esperado en log."
    else:
        motivo = " Conviene comprobar si el material está en log y todavía no se ha normalizado."
    return ResultadoRegla(
        texto=f"Los negros de este plano están en torno al {porcentaje:.0f}%, no a cero.{motivo}",
        valor_medido=(
            f"black_point (percentil 1 en WORKING_SPACE) = {negro_ws.tolist()}, "
            f"equivalente a {porcentaje:.1f}% pasado por la curva de cámara Rec.709"
        ),
    )


def _regla_saturacion_extendida(ctx: ContextoTutor) -> ResultadoRegla | None:
    hist = np.asarray(ctx.analisis.stats.saturation_hist, dtype=np.float64)
    if hist.sum() <= 0:
        return None
    cuarto = max(1, hist.shape[0] // 4)
    fraccion_alta = float(hist[-cuarto:].sum())
    if fraccion_alta < SUELO_SATURACION_ALTA_TUTOR:
        return None
    porcentaje = fraccion_alta * 100.0
    return ResultadoRegla(
        texto=(
            f"La saturación de este plano toca el máximo en el {porcentaje:.0f}% del "
            f"cuadro. Puede perder detalle o empastarse en el render si no se controla "
            f"— conviene vigilar esa zona al aplicar el look."
        ),
        valor_medido=(
            f"fracción del histograma de saturación en el cuarto más alto = {fraccion_alta:.4f} "
            f"({int(hist.shape[0] * 0.75)}-{hist.shape[0]} de {hist.shape[0]} bins)"
        ),
    )


#: Umbrales de `_piel()`/`skin_mask_oklab` (`core.umbrales.FRACCION_PIEL_MINIMA`,
#: `PIXELES_PIEL_MINIMOS`) ya deciden si hay piel bastante para fiarse del
#: locus — si `skin_locus` no es `None`, esa comprobación ya pasó. Lo único
#: que hace esta regla es la resta de tono entre dos locus YA calculados, así
#: que no necesita su propio umbral de disparo — dispara siempre que HAY dato
#: en los dos lados, y deja que la cifra hable.
def _regla_piel_vs_referencia(ctx: ContextoTutor) -> ResultadoRegla | None:
    if ctx.analisis_referencia is None:
        return None
    locus = ctx.analisis.stats.skin_locus
    locus_ref = ctx.analisis_referencia.stats.skin_locus
    if locus is None or locus_ref is None:
        return None
    tono = float(np.degrees(np.arctan2(locus[2], locus[1])) % 360.0)
    tono_ref = float(np.degrees(np.arctan2(locus_ref[2], locus_ref[1])) % 360.0)
    diferencia = (tono - tono_ref + 180.0) % 360.0 - 180.0  # -180..180, con signo
    if abs(diferencia) < 1.0:
        return None
    direccion = "hacia verde" if diferencia < 0 else "hacia rojo"
    return ResultadoRegla(
        texto=(
            f"La piel de este plano está a {abs(diferencia):.0f}° de tono {direccion} "
            f"respecto a la del clip de referencia."
        ),
        valor_medido=(
            f"tono de skin_locus (Oklab, grados) = {tono:.1f}°; referencia = {tono_ref:.1f}°; "
            f"diferencia = {diferencia:+.1f}°"
        ),
    )


# ---------------------------------------------------------------------------
# Grupo C — emparejamiento, vía core.matching (no_validable, día 7 §20:
# core/matching entero está en la lista de 36 sin poder verse contra material
# real todavía — sólo se ha probado contra 3.600 casos sintéticos del día 4).
# Nunca se usa `confidence` aquí: el día 4 midió que esa nota no predice el
# error (`CALIBRACION-CONFIANZA.md`), la misma razón por la que el paso 5 del
# modo fácil tampoco la usa (ver `gui/asistente_facil.py`).
# ---------------------------------------------------------------------------


def _regla_contenido_no_coincide(ctx: ContextoTutor) -> ResultadoRegla | None:
    if ctx.match is None or not ctx.match.content_mismatch:
        return None
    return ResultadoRegla(
        texto=(
            "Este plano no se parece al clip de referencia. Míralo antes de dar el "
            "trabajo por bueno — puede que el emparejamiento se haya equivocado de clip."
        ),
        valor_medido="MatchResult.content_mismatch = True",
    )


# ---------------------------------------------------------------------------
# El catálogo
# ---------------------------------------------------------------------------

CATALOGO: tuple[ReglaTutor, ...] = (
    ReglaTutor(
        id="look_plano",
        caracteristica="el look aplicado aplasta toda la imagen a un solo color (core.io.qc, código lut_plano)",
        umbral_nombre="UMBRAL_RECORRIDO_LUT_PLANO",
        umbral_valor="1e-6",
        validacion="validado",
        cifras_ref="CIFRAS.md §20 (0 de 79 falsos positivos en material real)",
        evaluar=_regla_look_plano,
    ),
    ReglaTutor(
        id="look_gamut",
        caracteristica="el look aplicado saca valores fuera de 0..1 (core.io.qc, código gamut)",
        umbral_nombre="TOL_GAMUT",
        umbral_valor=f"{TOL_GAMUT:.6f}",
        validacion="validado",
        cifras_ref="CIFRAS.md §20 (0 de 79 falsos positivos en material real)",
        evaluar=_regla_look_gamut,
    ),
    ReglaTutor(
        id="punto_negro",
        caracteristica="el punto negro (percentil 1) del plano, convertido a la curva de cámara Rec.709",
        umbral_nombre="SUELO_NEGRO_VISIBLE_TUTOR",
        umbral_valor=f"{SUELO_NEGRO_VISIBLE_TUTOR:.2f}",
        validacion="descriptiva",
        cifras_ref="—",
        evaluar=_regla_punto_negro,
    ),
    ReglaTutor(
        id="saturacion_extendida",
        caracteristica="fracción de la imagen en el cuarto más alto del histograma de saturación",
        umbral_nombre="SUELO_SATURACION_ALTA_TUTOR",
        umbral_valor=f"{SUELO_SATURACION_ALTA_TUTOR:.2f}",
        validacion="descriptiva",
        cifras_ref="—",
        evaluar=_regla_saturacion_extendida,
    ),
    ReglaTutor(
        id="piel_vs_referencia",
        caracteristica="diferencia de tono (Oklab) entre el locus de piel de este plano y el de la referencia",
        umbral_nombre=None,
        umbral_valor=None,
        validacion="descriptiva",
        cifras_ref="—",
        evaluar=_regla_piel_vs_referencia,
    ),
    ReglaTutor(
        id="contenido_no_coincide",
        caracteristica="desajuste de contenido con la referencia (core.matching.contenido)",
        umbral_nombre="UMBRAL_DESAJUSTE / UMBRAL_HUELLA",
        umbral_valor=f"{UMBRAL_DESAJUSTE} / {UMBRAL_HUELLA}",
        validacion="no_validable",
        cifras_ref="CIFRAS.md §20 (core.matching: necesita pares de clips reales, no existen todavía)",
        evaluar=_regla_contenido_no_coincide,
    ),
)

__all__ = [
    "CATALOGO",
    "ContextoTutor",
    "Frase",
    "ReglaTutor",
    "ResultadoRegla",
    "Validacion",
]
