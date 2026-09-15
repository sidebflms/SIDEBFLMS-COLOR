"""Errores de entrada/salida de SIDEBFLMS COLOR.

Regla de la casa: **todo fichero que viene de fuera falla en castellano**. Un
`ValueError: invalid literal for int() with base 10: 'treinta y tres'` no le dice
nada a Mario a las tres de la mañana; "el fichero X, línea 4: LUT_3D_SIZE tiene
que ser un número entero, llegó 'treinta y tres'" sí.

Todos los errores de este paquete heredan de `ErrorIO`, para que la GUI pueda
capturar una sola cosa (igual que captura sólo `ResolveError` para Resolve).
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ErrorIO",
    "ErrorFormatoCube",
    "ErrorFormatoHald",
    "ErrorFormatoCDL",
    "ErrorBundle",
    "describe_ruta",
]


class ErrorIO(Exception):
    """Cualquier problema leyendo o escribiendo un fichero. La GUI captura esto."""


class ErrorFormatoCube(ErrorIO):
    """Un `.cube` que no se puede leer, o un LUT que no se puede escribir."""


class ErrorFormatoHald(ErrorIO):
    """Una imagen HALD CLUT con la forma o el tamaño equivocados."""


class ErrorFormatoCDL(ErrorIO):
    """Un `.cdl` / `.ccc` / `.cc` que no se puede leer o escribir."""


class ErrorBundle(ErrorIO):
    """Un `.sidebcolor` corrupto, hostil o de una versión que no entendemos."""


def describe_ruta(ruta: Path | str) -> str:
    """Nombre corto y legible de una ruta para meterlo en un mensaje de error.

    Se queda con el nombre del fichero: la ruta completa de un `tmp_path` de
    pytest ocupa media pantalla y no aporta nada.
    """
    return Path(ruta).name or str(ruta)
