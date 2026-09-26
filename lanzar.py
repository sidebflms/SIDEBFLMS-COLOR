"""Arranca la interfaz intentando conectar a un Resolve real ya abierto.

    QT_QPA_PLATFORM=offscreen .venv/bin/python lanzar.py     # sin ventana
    .venv/bin/python lanzar.py                               # con ventana

DÍA 9 (continuación 8). Vive FUERA de `gui/` a propósito: `tests/
test_gui_regla_de_oro.py::test_la_gui_no_importa_el_puente_de_verdad`
garantiza que ningún fichero de `gui/` mencione siquiera
`LiveResolve`/`DaVinciResolveScript`/`fusionscript` — así la regla de oro se
audita con un `grep` sobre un solo paquete, sin tener que rastrear lógica.
Este script SÍ puede importar `LiveResolve`, porque no es parte de `gui/`.

QUÉ HACE, Y QUÉ NO
--------------------
Intenta `LiveResolve.conectar()` + `gui.estado_real.construir_estado_real()`
(clips reales, análisis real con ffmpeg, emparejamiento real). **Nunca
escribe** en ese intento — sólo conecta, lista y analiza; escribir en Resolve
sigue siendo, exclusivamente, lo que hace
`gui.pantalla_aplicar.aplicar()`/`aplicar_cancelable()` cuando el propio
usuario pulsa "Aplicar" desde la pantalla, con la regla de oro de siempre. Si
Resolve no está abierto, no hay timeline, o ningún clip se puede analizar,
cae a `gui.datos_demo.estado_demo()` (datos de demostración) sin romper el
arranque — se avisa por consola, no en silencio.

Para el arranque siempre-demo, sin ningún intento de tocar Resolve, sigue
existiendo `python -m gui` (`gui/__main__.py`), sin cambios.
"""

from __future__ import annotations

import sys

from gui.__main__ import _CARPETA_PERFILES_TRABAJO, _biblioteca_de_desarrollo
from gui.ventana import VentanaPrincipal, crear_app


def _estado_inicial():
    """Intenta conectar a un Resolve real ya abierto y construir el estado
    a partir de su timeline actual. Si algo falla —Resolve cerrado, sin
    proyecto, sin timeline, sin ningún clip analizable—, cae a datos de
    demostración. Nunca escribe nada: sólo conecta, lista y analiza."""
    from core.contracts import ResolveError
    from core.resolve.live import LiveResolve
    from gui.datos_demo import estado_demo
    from gui.estado_real import SinClipsReales, construir_estado_real

    try:
        puente = LiveResolve.conectar()
        estado = construir_estado_real(puente)
    except (ResolveError, SinClipsReales) as exc:
        print(
            f"[SIDEB COLOR] no se ha podido usar el Resolve real ({exc}); "
            "arranco con datos de demostración."
        )
        return estado_demo()
    print(f"[SIDEB COLOR] conectado a Resolve real: {estado.notas[0] if estado.notas else ''}")
    return estado


def main(argv: list[str] | None = None) -> int:
    app = crear_app(argv if argv is not None else sys.argv)
    ventana = VentanaPrincipal(
        _estado_inicial(),
        biblioteca=_biblioteca_de_desarrollo(),
        perfiles_carpeta=str(_CARPETA_PERFILES_TRABAJO),
    )
    ventana.resize(1440, 900)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
