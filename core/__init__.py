"""SIDEBFLMS COLOR - nucleo Qt-agnostico.

REGLA DE ARQUITECTURA: nada dentro de `core/` importa PySide6 ni
DaVinciResolveScript. Si un test de core necesita Qt, el diseno esta mal.
"""

__version__ = "0.1.0"
