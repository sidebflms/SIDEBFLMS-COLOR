"""Generación paramétrica de looks (día 9): un PowerGrade nuevo a partir de
parámetros con nombre, no de una tabla 3D copiada de otro sitio.

Nace del encargo de tener una librería grande de PowerGrades: en vez de
depender sólo de conseguir más ficheros ajenos (con sus problemas de
licencia, ver `SUPUESTOS.md` fila I1), se puede generar contenido nuevo con
la misma técnica que usan los packs profesionales de verdad.

- `generador` — `ParametrosLook` -> `LUT3D`, la pieza pura y determinista.
- `presets` — una biblioteca semilla de `ParametrosLook` con nombre,
  hechos a mano y marcados como tal (ver `SUPUESTOS.md` fila I2).
- `biblioteca` — `sembrar_generados()`, de los presets a ficheros `.cube`
  reales en disco, listos para `core.io.biblioteca.sembrar_desde_carpeta`.

Puro, determinista, sin Resolve y sin red — el LUT que sale de aquí se
escribe a disco con `core.io.cube.escribir_cube`, igual que cualquier otro.
"""

from __future__ import annotations

from core.looks.biblioteca import sembrar_generados
from core.looks.generador import ParametrosLook, VentanaSecundaria, generar_look
from core.looks.presets import PRESETS

__all__ = [
    "PRESETS",
    "ParametrosLook",
    "VentanaSecundaria",
    "generar_look",
    "sembrar_generados",
]
