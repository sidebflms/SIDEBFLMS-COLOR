"""Cierra el círculo: de `ParametrosLook` a ficheros `.cube` reales, listos
para que `core.io.biblioteca.sembrar_desde_carpeta` los recoja.

Deliberadamente NO reinventa la escritura: usa `core.io.cube.escribir_cube`,
el mismo camino que cualquier otro `.cube` del proyecto — así que un LUT
generado aquí hereda automáticamente las mismas garantías (ASCII, sin BOM,
saltos Unix, disco lleno convertido en `ErrorFormatoCube`, no en un `OSError`
crudo — ver `BITACORA.md`, "Endurece core/io").
"""

from __future__ import annotations

from pathlib import Path

from core.io.cube import escribir_cube
from core.looks.generador import ParametrosLook, generar_look
from core.looks.presets import PRESETS
from core.umbrales import LUT_SIZE_DEFAULT

__all__ = ["sembrar_generados"]


def _nombre_fichero(parametros: ParametrosLook) -> str:
    """El nombre de fichero es `parametros.nombre`, NO la clave del
    diccionario (`"teal_naranja_clasico"`): `core.io.biblioteca.nombre_legible`
    saca el nombre que se enseña en el selector directamente del nombre de
    fichero (sin extensión, sin des-slugificar guiones bajos) — así que el
    botón de la GUI enseña "SIDEB COLOR — Teal & Naranja clásico", no
    "teal_naranja_clasico"."""
    return f"{parametros.nombre}.cube"


def sembrar_generados(
    carpeta: str | Path,
    *,
    presets: dict[str, ParametrosLook] = PRESETS,
    n: int = LUT_SIZE_DEFAULT,
) -> list[Path]:
    """Genera y escribe un `.cube` por cada preset de `presets` dentro de
    `carpeta` (se crea si no existe). Devuelve las rutas escritas, en el
    mismo orden que `sorted(presets)` — determinista, para que dos llamadas
    seguidas den la misma lista sin depender del orden de un diccionario.

    No hace nada con Resolve ni con la biblioteca ya sembrada: sólo escribe
    ficheros. Sembrar de verdad la biblioteca de la app sigue siendo
    `core.io.biblioteca.sembrar_desde_carpeta(carpeta)`, sobre esta misma
    carpeta, después — así lo hace `gui.__main__` (ver `BITACORA.md`).
    """
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for clave in sorted(presets):
        parametros = presets[clave]
        lut = generar_look(parametros, n=n)
        rutas.append(escribir_cube(lut, destino / _nombre_fichero(parametros)))
    return rutas
