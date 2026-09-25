"""Analizar una LISTA de clips, uno a uno, con estado reanudable.

El hueco que `BITACORA.md` señalaba como real, dos noches seguidas: `core.
analysis` tenía funciones POR CLIP (`analizar_clip`) con una jerarquía de
errores tipada (`ErrorAnalisis` y sus hijas) que ya "nunca sale como
traceback" — pero nada en el repo iteraba sobre una LISTA llamando a esas
funciones con manejo de fallo por clip y estado persistido entre llamadas.
Sin eso, "reanudable" no significaba nada: no hay nada que reanudar si no se
sabe qué se hizo ya.

Construido sobre `core.batch.ejecutar_lote` — no reinventa la ejecución por
trozos/cancelable/reanudable, sólo le pone encima el vocabulario de
`core.analysis` (rutas, `ClipAnalysis`, `ErrorAnalisis`).

QUÉ GUARDA EL MANIFIESTO, Y QUÉ NO
------------------------------------
El manifiesto (heredado de `core.batch`) guarda **qué clips se analizaron
bien y cuáles fallaron, con su mensaje — no el `ClipAnalysis` entero**. Un
`ClipAnalysis` lleva arrays de numpy (la huella, la muestra de píxeles) que
no son JSON de forma directa; guardarlos habría acoplado el motor genérico a
este tipo concreto. Consecuencia práctica: si el proceso se reinicia entre
medias, una segunda llamada con el mismo `manifiesto` **no vuelve a llamar a
ffmpeg sobre los clips que ya salieron bien** (que es el ahorro real — ffmpeg
es lo caro), pero `ResultadoLoteAnalisis.analisis` de esa segunda llamada
sólo trae los `ClipAnalysis` de los clips analizados EN ESA LLAMADA, no los
de una llamada anterior — `ResultadoLoteAnalisis.hechos` sí lista TODOS los
que están bien, vengan de esta llamada o de una anterior, para que quien
llame sepa qué le falta reconstruir si de verdad necesita los números de un
clip que ya se dio por bueno hace tiempo.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from core.analysis.errores import ErrorAnalisis
from core.analysis.stats import analizar_clip
from core.batch import ProgresoLote, ejecutar_lote
from core.contracts import ClipAnalysis

__all__ = ["ResultadoLoteAnalisis", "analizar_lote"]


@dataclass(frozen=True)
class ResultadoLoteAnalisis:
    #: `ClipAnalysis` de los clips analizados DE VERDAD en esta llamada
    #: (no incluye los que se saltaron por venir ya "hecho" del manifiesto).
    analisis: dict[str, ClipAnalysis]
    #: Mensaje de `ErrorAnalisis`, por clip_id, sólo de los que fallaron EN
    #: ESTA llamada (un fallo de una llamada anterior que no se ha vuelto a
    #: reintentar no aparece aquí).
    fallos: dict[str, str]
    #: True si `debe_cancelar()` paró el lote antes de terminar.
    cancelado: bool
    #: TODOS los clip_id que están "hecho" -- de esta llamada o de una
    #: anterior leída del manifiesto.
    hechos: tuple[str, ...]
    #: Los que no se llegaron ni a intentar (el lote se canceló antes de
    #: llegar a ellos).
    pendientes: tuple[str, ...]


def analizar_lote(
    clips: Mapping[str, str | Path],
    *,
    manifiesto: str | Path | None = None,
    reintentar_fallidos: bool = True,
    callback_progreso: Callable[[ProgresoLote], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
    n_fotogramas: int | None = None,
    guardar_pixeles: bool = False,
) -> ResultadoLoteAnalisis:
    """Analiza `clips` (clip_id -> ruta) uno a uno con `core.analysis.
    analizar_clip`, aislando el fallo de cada uno (`ErrorAnalisis` y sus
    hijas: fichero que no existe, formato que no se entiende, ffmpeg roto o
    sin instalar, clip truncado — nunca un traceback por un clip suelto).

    `manifiesto`, si se da, hace esto reanudable de verdad: una segunda
    llamada con la misma ruta no vuelve a analizar los clips que ya salieron
    bien la vez anterior (ver el docstring del módulo sobre qué SÍ y qué NO
    persiste). Los que fallaron se reintentan por defecto
    (`reintentar_fallidos=True`) porque ffmpeg puede fallar por algo
    transitorio (disco ocupado un momento) tanto como por algo permanente
    (fichero corrupto de verdad).

    `n_fotogramas`/`guardar_pixeles` se pasan tal cual a `analizar_clip` para
    cada clip, si se dan (si no, se usan los valores por defecto de esa
    función).
    """
    analisis: dict[str, ClipAnalysis] = {}
    mensajes_fallo: dict[str, str] = {}

    def _uno(clip_id: str) -> None:
        ruta = clips[clip_id]
        kwargs: dict[str, object] = {"clip_id": clip_id, "guardar_pixeles": guardar_pixeles}
        if n_fotogramas is not None:
            kwargs["n_fotogramas"] = n_fotogramas
        try:
            resultado = analizar_clip(ruta, **kwargs)
        except ErrorAnalisis as exc:
            mensajes_fallo[clip_id] = str(exc)
            raise
        analisis[clip_id] = resultado

    resultado_lote = ejecutar_lote(
        list(clips.keys()),
        _uno,
        excepciones=(ErrorAnalisis,),
        manifiesto=manifiesto,
        reintentar_fallidos=reintentar_fallidos,
        callback_progreso=callback_progreso,
        debe_cancelar=debe_cancelar,
    )

    pendientes = tuple(cid for cid in clips if cid not in resultado_lote.resultados)

    return ResultadoLoteAnalisis(
        analisis=analisis,
        fallos=mensajes_fallo,
        cancelado=resultado_lote.cancelado,
        hechos=resultado_lote.hechos,
        pendientes=pendientes,
    )
