"""Arranca la interfaz contra `FakeResolve`. **Nunca contra Resolve de verdad.**

    QT_QPA_PLATFORM=offscreen .venv/bin/python -m gui        # sin ventana
    .venv/bin/python -m gui                                  # con ventana
"""

from __future__ import annotations

import sys
from pathlib import Path

from gui.ventana import VentanaPrincipal, crear_app

#: Día 6: mientras no haya una carpeta de presets configurable por el
#: usuario, la biblioteca del paso 4 del modo fácil se siembra —si existe—
#: desde `tests/luts_reales/`, el material real de Mario para desarrollo.
#: Es sólo lectura y no se versiona (ver `.gitignore`); en un checkout sin
#: esa carpeta, la app arranca igual, con la biblioteca vacía.
_CARPETA_LUTS_DESARROLLO = Path(__file__).resolve().parent.parent / "tests" / "luts_reales"

#: Día 9 (continuación): looks propios de `core.looks`, generados —no
#: copiados de ningún sitio—. Se reescriben en cada arranque: son
#: deterministas y baratos (rejilla 33³, unos pocos ms para los tres), así
#: que no hace falta versionarlos ni arriesgarse a que queden desactualizados
#: tras cambiar `core/looks/presets.py`. Carpeta gitignored, igual que
#: `tests/media/out/` para el material sintético.
_CARPETA_LOOKS_GENERADOS = Path(__file__).resolve().parent.parent / "generados" / "looks"


def _biblioteca_de_desarrollo() -> tuple:
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.looks import sembrar_generados

    sembrar_generados(_CARPETA_LOOKS_GENERADOS)

    # El paso 4 es "look": una conversión de espacio de color (día 6,
    # clasificada con core.io.qc.clasificar_lut) no pertenece ahí, es
    # configuración técnica del paso 1 "ordenar la casa". Se filtra aquí, no
    # en `ejecutar_look`, para que la función siga sirviendo genéricamente a
    # cualquier biblioteca que le pasen (una futura carpeta "sólo looks" no
    # necesitaría este filtro). Los looks generados van tras los reales de
    # Mario cuando los hay, para no mover el preset por defecto (índice 0)
    # de quien ya tenía `tests/luts_reales/` poblada.
    reales = tuple(
        p for p in sembrar_desde_carpeta(_CARPETA_LUTS_DESARROLLO) if p.clasificacion != "conversion"
    )
    generados = tuple(
        p for p in sembrar_desde_carpeta(_CARPETA_LOOKS_GENERADOS) if p.clasificacion != "conversion"
    )
    return reales + generados


def main(argv: list[str] | None = None) -> int:
    app = crear_app(argv if argv is not None else sys.argv)
    ventana = VentanaPrincipal(biblioteca=_biblioteca_de_desarrollo())
    ventana.resize(1440, 900)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
