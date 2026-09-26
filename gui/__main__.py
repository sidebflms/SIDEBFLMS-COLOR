"""Arranca la interfaz contra `FakeResolve`. **Nunca contra Resolve de verdad.**

    QT_QPA_PLATFORM=offscreen .venv/bin/python -m gui        # sin ventana
    .venv/bin/python -m gui                                  # con ventana

Esto es a propósito, no un olvido: `tests/test_gui_regla_de_oro.py::
test_la_gui_no_importa_el_puente_de_verdad` garantiza que ningún fichero de
`gui/` mencione siquiera `LiveResolve`/`DaVinciResolveScript`/`fusionscript`
— así se puede auditar la regla de oro con un `grep`, sin tener que rastrear
lógica. El lanzador que SÍ intenta conectar a Resolve real (día 9,
continuación 8) vive fuera de este paquete: `lanzar.py`, en la raíz del
repo — importa `gui.ventana.VentanaPrincipal` igual que este módulo, pero
decide el estado inicial desde fuera, sin que `gui/` tenga que saber cómo.
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

#: Día 9 (continuación 4): packs de LUTs gratuitos de fuera, descargados y
#: metidos en el repo por decisión explícita de Mario — SÍ se versiona, a
#: diferencia de `tests/luts_reales/`. La procedencia y el texto de licencia
#: (o su ausencia) de cada fuente está en `luts_externos/<fuente>/PROCEDENCIA.md`;
#: una fuente (RocketStock) tiene una cláusula explícita de no-redistribución
#: y se incluyó de todos modos, con esa información ya en la mano — ver
#: `BITACORA.md`.
_CARPETA_LUTS_EXTERNOS = Path(__file__).resolve().parent.parent / "luts_externos"

#: Día 9 (continuación 4): con 475 `.cube` en `luts_externos/`, leer y
#: clasificar cada uno en CADA arranque de la app cuesta ~12 s medidos —
#: demasiado para un arranque. Un fichero de cache (gitignored, junto a
#: `generados/`, nunca dentro de una carpeta de material externo/de Mario)
#: hace que sólo se recalculen los ficheros nuevos o modificados desde la
#: última vez. Ver `core.io.biblioteca.sembrar_desde_carpeta`.
_CACHE_BIBLIOTECA = Path(__file__).resolve().parent.parent / "generados" / "biblioteca_cache.json"

#: Día 9 (continuación 10): perfiles de trabajo reutilizables (`core.
#: perfiles.PerfilTrabajo`, p.ej. "Fabrik") — ajustes de cámara conocidos por
#: la experiencia de Mario, no código ni material genérico. Gitignored, como
#: `tests/luts_reales/`: es su propia sintonía de negocio, no algo que
#: versionar con el motor.
_CARPETA_PERFILES_TRABAJO = Path(__file__).resolve().parent.parent / "perfiles_trabajo"


def _biblioteca_de_desarrollo() -> tuple:
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.looks import sembrar_generados

    # No depender de que `sembrar_generados` cree `generados/` como efecto
    # secundario antes de que la cache intente escribir ahi dentro.
    _CACHE_BIBLIOTECA.parent.mkdir(parents=True, exist_ok=True)
    sembrar_generados(_CARPETA_LOOKS_GENERADOS)

    # El paso 4 es "look": una conversión de espacio de color (día 6,
    # clasificada con core.io.qc.clasificar_lut) no pertenece ahí, es
    # configuración técnica del paso 1 "ordenar la casa". Se filtra aquí, no
    # en `ejecutar_look`, para que la función siga sirviendo genéricamente a
    # cualquier biblioteca que le pasen (una futura carpeta "sólo looks" no
    # necesitaría este filtro). Orden: reales de Mario primero (no mover el
    # preset por defecto, índice 0, de quien ya tenía `tests/luts_reales/`
    # poblada), luego los generados por `core.looks`, luego los externos.
    reales = tuple(
        p
        for p in sembrar_desde_carpeta(_CARPETA_LUTS_DESARROLLO, cache=_CACHE_BIBLIOTECA)
        if p.clasificacion != "conversion"
    )
    generados = tuple(
        p
        for p in sembrar_desde_carpeta(_CARPETA_LOOKS_GENERADOS, cache=_CACHE_BIBLIOTECA)
        if p.clasificacion != "conversion"
    )
    externos = tuple(
        p
        for p in sembrar_desde_carpeta(_CARPETA_LUTS_EXTERNOS, cache=_CACHE_BIBLIOTECA)
        if p.clasificacion != "conversion"
    )
    return reales + generados + externos


def main(argv: list[str] | None = None) -> int:
    app = crear_app(argv if argv is not None else sys.argv)
    ventana = VentanaPrincipal(
        biblioteca=_biblioteca_de_desarrollo(), perfiles_carpeta=str(_CARPETA_PERFILES_TRABAJO)
    )
    ventana.resize(1440, 900)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
