"""Construye el `ContextoTutor` de un clip a partir de `EstadoDemo`/`ClipDemo`.

Es el único puente entre la GUI (que tiene el estado de la sesión: qué clip,
qué referencia, qué look) y `core.tutor` (que no sabe nada de `gui` ni de
Resolve). Nada de lógica de reglas aquí — sólo reunir lo que ya existe.
"""

from __future__ import annotations

import re

from core.analysis import analizar_imagen
from core.colormgmt import detectar_espacio_clip
from core.contracts import ClipAnalysis
from core.tutor import ContextoTutor, Frase, Leccion, ensenar, explicar
from gui.datos_demo import ClipDemo, EstadoDemo

__all__ = ["construir_contexto", "frases_de_clip", "lecciones_de_clip", "redondear_para_mostrar"]


def _analizar(clip: ClipDemo | None) -> ClipAnalysis | None:
    if clip is None or clip.original is None:
        return None
    return analizar_imagen(clip.original, clip_id=clip.clip_id)


def construir_contexto(estado: EstadoDemo, clip: ClipDemo) -> ContextoTutor | None:
    """`None` si no hay fotograma que analizar — no hay nada que el tutor
    pueda decir sobre un clip sin imagen, y decir eso es mejor que fingir."""
    analisis = _analizar(clip)
    if analisis is None:
        return None
    referencia = estado.por_id(estado.referencia_id) if estado.referencia_id else None
    return ContextoTutor(
        analisis=analisis,
        analisis_referencia=_analizar(referencia) if referencia is not clip else None,
        deteccion=detectar_espacio_clip(clip.ref),
        match=clip.match,
        qc_look=estado.informe_lut,
    )


def frases_de_clip(estado: EstadoDemo, clip: ClipDemo) -> tuple[Frase, ...]:
    contexto = construir_contexto(estado, clip)
    return explicar(contexto) if contexto is not None else ()


def lecciones_de_clip(estado: EstadoDemo, clip: ClipDemo) -> tuple[Leccion, ...]:
    contexto = construir_contexto(estado, clip)
    return ensenar(contexto)


#: Un decimal con cinco o más cifras detrás del punto. Lo que el tutor mide sale
#: de `repr(float)` (`0.13566423773765565`): exacto, pero ilegible en un panel.
_DECIMAL_LARGO = re.compile(r"(?<![\w.])-?\d+\.\d{5,}")

#: Decimales con los que se MUESTRA un número del tutor (auditoría de diseño
#: 2026-10-06: «3-4 decimales»). Sólo afecta a lo que se pinta: el valor completo
#: sigue en `Frase` y la GUI lo ofrece en el tooltip.
DECIMALES_MOSTRADOS = 4


def redondear_para_mostrar(texto: str, decimales: int = DECIMALES_MOSTRADOS) -> str:
    """Redondea a `decimales` los números con más cifras de las que se leen.

    **Sólo para mostrar.** No toca `Frase` ni lo que mide `core.tutor`: quien
    llama pinta esto y deja el texto original en el tooltip.
    """
    return _DECIMAL_LARGO.sub(lambda m: f"{float(m.group(0)):.{decimales}f}", texto)
