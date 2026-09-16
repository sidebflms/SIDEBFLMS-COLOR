"""Gestion de color automatica: "ordenar la casa" del modo facil.

Detecta a que espacio de entrada pertenece cada clip a partir de sus
metadatos de camara, decide con una tabla explicita (nunca adivina), y avisa
de la doble conversion, que es el fallo silencioso mas comun con material
mezclado. Todo puro: no toca Resolve, trabaja sobre `ClipRef`, `ProjectInfo` y
`NodeInfo` tal y como los expone `core.resolve.ResolveBridge`.

    from core.colormgmt import detectar_espacio_clip, agrupar_ambiguos, verificar_proyecto

Ver `core/colormgmt/NOTAS.md` para el porque de cada decision de diseno.
"""

from __future__ import annotations

from core.colormgmt.deteccion import (
    REGLAS_DECISION,
    ReglaDeteccion,
    agrupar_ambiguos,
    detectar_espacio_clip,
    detectar_espacios_timeline,
)
from core.colormgmt.verificacion import verificar_proyecto

__all__ = [
    "REGLAS_DECISION",
    "ReglaDeteccion",
    "agrupar_ambiguos",
    "detectar_espacio_clip",
    "detectar_espacios_timeline",
    "verificar_proyecto",
]
