"""Desplegar el preset elegido en el selector de modo fácil al fichero real
que Resolve necesita (día 9, continuación 12: punto 2 de la lista de Mario).

Antes de esto, elegir un preset distinto en el paso "look" sólo cambiaba
`EstadoDemo.look` (el `LUT3D` en memoria, usado para la vista previa del
asistente) — `EstadoDemo.look_rel` (la ruta que `PantallaAplicar` de verdad
escribe con `SetLUT`) se quedaba siempre en `gui.datos_demo.LOOK_REL`, el
valor fijo por defecto. El asistente enseñaba una vista previa de un preset
y luego aplicaba otro distinto.

Mismo patrón que `gui/perfiles_trabajo.py` (escribir el `.cube` donde
`puente.project_info().lut_dir` dice de verdad, con `escribir_cube`), pero
para un preset suelto en vez de una tabla cámara→LUT: por eso vive en `gui/`
y no en `core/` (toca disco y habla con el puente).
"""

from __future__ import annotations

import re
from pathlib import Path

from core.contracts import LUT3D
from core.io.biblioteca import Preset
from core.io.cube import escribir_cube
from gui.datos_demo import EstadoDemo

__all__ = ["desplegar_preset_elegido"]

#: Dónde, dentro de la carpeta de LUTs de Resolve, viven los presets de la
#: biblioteca ya horneados — junto a `SIDEB/` (el look compartido de
#: siempre) y `SIDEB/perfiles` (los perfiles de trabajo), no mezclados con
#: LUTs de terceros.
_SUBCARPETA = "SIDEB/presets"


def _slug(texto: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return s or "preset"


def desplegar_preset_elegido(estado: EstadoDemo, *, preset: Preset, look: LUT3D) -> str:
    """Escribe `look` en la carpeta de LUTs REAL de Resolve y deja
    `estado.look`/`estado.look_rel` apuntando al fichero escrito.

    Devuelve la ruta relativa escrita. Escribe siempre, sin comprobar antes
    si "ya estaba" con ese contenido: el preset puede haberse releído de un
    `.cube` que cambió de contenido en disco, y Resolve no lee la LUT hasta
    `SetLUT`/`refresh_lut_list` (`PantallaAplicar.aplicar`), así que
    reescribir en cada elección no tiene coste observable.

    Puede lanzar `core.contracts.ResolveError` (si `project_info()` falla,
    p.ej. sin conexión) o `core.io.errores.ErrorFormatoCube` (disco lleno,
    sin permiso) — a quien llama le toca decidir qué decir de eso; aquí no
    se traga ninguna.
    """
    lut_dir = Path(estado.puente.project_info().lut_dir)
    ruta_relativa = f"{_SUBCARPETA}/{_slug(preset.id)}.cube"
    escribir_cube(look, lut_dir / ruta_relativa, crear_directorios=True)
    estado.look = look
    estado.look_rel = ruta_relativa
    return ruta_relativa
