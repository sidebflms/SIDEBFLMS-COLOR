"""`ensenar()`: el porqué de las decisiones, con el material de Mario delante.

Tarea 2.4 del día 8: nada de teoría de colorimetría genérica — cada lección
usa vocabulario y objetos que la app YA tiene delante (el `clasificacion` que
mide `core.io.qc.clasificar_lut`, el CDL de tres nodos que ya escribe
`core.resolve.bridge`, el `MatchResult` de este clip concreto). Si una lección
no puede engancharse a algo medido de este proyecto, no es una lección de este
módulo — es un tutorial genérico, y de esos ya hay de sobra en internet.

Puro, determinista, sin Resolve y sin red — igual que `explicar()`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.contracts import CDL, NODE_BALANCE, NODE_LOOK, NODE_NORMALIZACION
from core.tutor.catalogo import ContextoTutor
from core.umbrales import UMBRAL_OFFSET_MENCIONABLE_TUTOR, UMBRAL_SLOPE_MENCIONABLE_TUTOR

__all__ = ["Leccion", "ensenar"]


@dataclass(frozen=True)
class Leccion:
    id: str
    titulo: str
    texto: str


def _leccion_tres_tipos_de_lut(ctx: ContextoTutor | None) -> Leccion:
    """LUT de conversión, LUT de look, y grade: la distinción que hace falta
    para no confundir "aplicar un LUT" con "gradar"."""
    partes = [
        "Un LUT de CONVERSIÓN cambia de un espacio de color a otro sin decisión "
        "artística: pasa el log de una cámara concreta a Rec.709, y nada más — "
        "dos personas distintas, con la misma cámara, sacan el mismo resultado. "
        "Un LUT de LOOK es una decisión de estilo horneada en una tabla: un "
        "viraje de tono, un contraste concreto, algo que alguien eligió a "
        "propósito. Un GRADE es más que eso: es todo el trabajo por clip — "
        "exposición, balance de color, y el look — nunca cabe en un solo LUT "
        "porque cada clip necesita un ajuste distinto antes del mismo look."
    ]
    if ctx is not None and ctx.qc_look is not None:
        partes.append(
            f"El look que tienes puesto ahora ({ctx.qc_look.size}³) es justo eso: "
            "una tabla fija, la misma para cualquier clip al que se la apliques."
        )
    return Leccion(
        id="tres_tipos_de_lut",
        titulo="LUT de conversión, LUT de look, y grade — no son lo mismo",
        texto=" ".join(partes),
    )


def _leccion_exposicion_no_va_en_el_look(ctx: ContextoTutor | None) -> Leccion:
    """Por qué la exposición nunca va dentro de un look: el diseño de tres
    nodos de esta app (`core.contracts.NODE_NORMALIZACION/BALANCE/LOOK`) no es
    arbitrario, es la razón de esta lección hecha código."""
    partes = [
        f"Esta app siempre escribe tres nodos, en este orden: el nodo {NODE_NORMALIZACION} "
        "normaliza el espacio de entrada de CADA clip (distinto según la cámara), el "
        f"nodo {NODE_BALANCE} ajusta exposición y balance de color de ESE clip concreto, y "
        f"el nodo {NODE_LOOK} aplica el mismo look — la misma tabla, sin cambios — a todos "
        "los clips del proyecto. Si la exposición se horneara dentro del look, el look "
        "dejaría de ser una tabla reutilizable: cada clip necesitaría su propia copia "
        "del look, ajustada a su propia exposición, y ya no sería un look, serían "
        "tantos grades sueltos como clips. Por eso el nodo de exposición/balance va "
        "SIEMPRE antes del look, y por separado."
    ]
    if ctx is not None and ctx.match is not None:
        cdl = ctx.match.cdl
        offset_medio = float(np.mean(cdl.offset))
        if abs(offset_medio) > UMBRAL_OFFSET_MENCIONABLE_TUTOR:
            direccion = "subido" if offset_medio > 0 else "bajado"
            partes.append(
                f"En este clip, ese ajuste de exposición ya está hecho en el nodo "
                f"{NODE_BALANCE}: se ha {direccion} antes de llegar al look — el look "
                "en sí no ha tenido que cambiar nada para este clip en concreto."
            )
    return Leccion(
        id="exposicion_no_en_el_look",
        titulo="Por qué la exposición nunca va dentro de un look",
        texto=" ".join(partes),
    )


def _leccion_cdl(ctx: ContextoTutor | None) -> Leccion | None:
    """Qué significa cada parte del CDL que la app escribe — sólo si hay un
    CDL concreto de este clip que enseñar; si no, no hay nada que explicar
    sobre un dato que no existe."""
    if ctx is None or ctx.match is None:
        return None
    cdl: CDL = ctx.match.cdl
    if cdl.is_identity():
        return Leccion(
            id="cdl_de_este_clip",
            titulo="El ajuste de este clip",
            texto=(
                "Este clip no ha necesitado ningún ajuste de exposición ni de balance "
                "de color respecto a la referencia: el CDL que se le aplica es la "
                "identidad — entra igual que sale."
            ),
        )
    offset = float(np.mean(cdl.offset))
    slope_desv = float(np.std(cdl.slope))
    frases = []
    if abs(offset) > UMBRAL_OFFSET_MENCIONABLE_TUTOR:
        frases.append(
            f"el `offset` medio es {offset:+.3f} — eso es la exposición: sube o baja "
            "el nivel entero de la imagen por igual"
        )
    if slope_desv > UMBRAL_SLOPE_MENCIONABLE_TUTOR:
        frases.append(
            f"el `slope` se separa {slope_desv:.3f} entre canales — eso es balance de "
            "color: cada canal (R, G, B) se multiplica por un número distinto"
        )
    if not frases:
        frases.append("el ajuste es pequeño, por debajo de lo que vale la pena nombrar aparte")
    return Leccion(
        id="cdl_de_este_clip",
        titulo="El ajuste de este clip, con sus propios números",
        texto=f"En el CDL que se aplica a este clip, {', y '.join(frases)}.",
    )


def ensenar(contexto: ContextoTutor | None = None) -> tuple[Leccion, ...]:
    """Las lecciones que aplican hoy. `contexto=None` da el mínimo fijo del
    encargo (los dos temas obligatorios); con contexto, cada lección se
    engancha a los datos concretos de este clip cuando los hay."""
    lecciones = [
        _leccion_tres_tipos_de_lut(contexto),
        _leccion_exposicion_no_va_en_el_look(contexto),
    ]
    extra = _leccion_cdl(contexto)
    if extra is not None:
        lecciones.append(extra)
    return tuple(lecciones)
