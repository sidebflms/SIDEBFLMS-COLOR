"""El tutor: explicar, dar opciones y enseñar, apoyado en el análisis medido.

Día 8, tarea 2. Estaba a cero desde el día 1 — nunca se le asignó a nadie — y
con el modo fácil redefinido para alguien que sólo sabe aplicar un LUT, el
tutor no es un extra: es casi el producto. Hoy el modo fácil dice qué ha
hecho; el tutor es lo que le enseña algo.

CÓMO ESTÁ HECHO, EN UNA FRASE
--------------------------------
Puro, determinista, sin Resolve y sin red — se apoya en `core.analysis`
(medido) y en `core.io.qc` (medido y validado el día 7), nunca en el puente
(`core.resolve`, que va detrás de incógnitas sin verificar). La única pieza
que SÍ toca el puente es `opciones.aplicar_opciones_como_versiones`, y lo hace
por la interfaz (`ResolveBridge`/`FakeResolve`), nunca a pelo.

- `catalogo` — el catálogo de reglas: condición sobre una característica
  medida -> frase, con su validación cruzada contra `CIFRAS.md` §20.
- `explicar` — recorre el catálogo sobre un clip y junta lo que dispara.
- `ensenar` — el porqué de las decisiones, con el material delante.
- `opciones` — variantes de intensidad de un look, listas para Resolve.

Ver `NOTAS.md` para lo que se decidió no escribir, y por qué.
"""

from __future__ import annotations

from core.tutor.catalogo import CATALOGO, ContextoTutor, Frase, ReglaTutor, ResultadoRegla
from core.tutor.ensenar import Leccion, ensenar
from core.tutor.explicar import explicar
from core.tutor.opciones import (
    INTENSIDADES,
    OpcionLook,
    aplicar_opciones_como_versiones,
    generar_opciones,
)

__all__ = [
    "CATALOGO",
    "INTENSIDADES",
    "ContextoTutor",
    "Frase",
    "Leccion",
    "OpcionLook",
    "ReglaTutor",
    "ResultadoRegla",
    "aplicar_opciones_como_versiones",
    "ensenar",
    "explicar",
    "generar_opciones",
]
