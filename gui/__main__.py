"""Arranca la interfaz contra `FakeResolve`. **Nunca contra Resolve de verdad.**

    QT_QPA_PLATFORM=offscreen .venv/bin/python -m gui        # sin ventana
    .venv/bin/python -m gui                                  # con ventana
"""

from __future__ import annotations

import sys

from gui.ventana import VentanaPrincipal, crear_app


def main(argv: list[str] | None = None) -> int:
    app = crear_app(argv if argv is not None else sys.argv)
    ventana = VentanaPrincipal()
    ventana.resize(1440, 900)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
