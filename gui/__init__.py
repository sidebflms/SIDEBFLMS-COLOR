"""Interfaz grafica de SIDEBFLMS COLOR (agente H).

Esta capa **consume** `core/` y nunca al reves. Aqui si se importa PySide6; en
`core/` no se importa jamas.

Lo que hay:

* `identidad`   — los colores, las fuentes y la hoja de estilo. Todo sale de
                  `docs/IDENTIDAD.md` y nada se inventa.
* `widgets`     — las piezas reutilizables (rotulos, cifras, insignia de
                  confianza, etiqueta que se recorta con puntos suspensivos).
* `imagen`      — numpy en espacio de trabajo -> `QImage` para pintar.
* `datos_demo`  — material de prueba para las capturas, **todo** generado por
                  `tests/media/generate.py`. Cero material real.
* `pantalla_*`  — las cuatro pantallas.
* `ventana`     — la ventana principal que las cose.
* `capturas`    — regenera `capturas/` entera de una sentada.

**La GUI habla siempre con `core.resolve.FakeResolve`.** Aqui no se importa
`DaVinciResolveScript` ni `core.resolve.live`.
"""

from __future__ import annotations

__all__ = ["identidad", "widgets", "imagen"]
