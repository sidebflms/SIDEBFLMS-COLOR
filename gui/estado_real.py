"""`EstadoDemo` construido a partir de un Resolve REAL, no de datos sintéticos.

Reutiliza `EstadoDemo`/`ClipDemo` (`gui/datos_demo.py`) tal cual — las
pantallas ya saben pintar esos tipos; lo único que cambia es DE DÓNDE sale el
contenido: clips reales vía `puente.list_clips()`, análisis real vía
`core.analysis.lote.analizar_lote` (ffmpeg de verdad sobre el fichero de cada
clip), emparejamiento real vía `core.matching.emparejar_analisis`.

QUÉ TOCA Y QUÉ NO
------------------
Esta función SÍ toca disco (lee los ficheros de vídeo con ffmpeg) y SÍ habla
con el puente (`list_clips`) — no es `core/`, es `gui/`, donde eso está
permitido (`core/analysis` y `core/matching` siguen siendo puros; esto sólo
los orquesta contra rutas reales). **Nunca escribe en Resolve**: eso lo sigue
haciendo únicamente `gui.pantalla_aplicar.aplicar()`/`aplicar_cancelable()`,
con la regla de oro de siempre — construir el estado es sólo lectura+análisis.

SIN ESTRENAR CONTRA `LiveResolve` DE VERDAD
----------------------------------------------
La lógica de aquí (elegir referencia, analizar, emparejar, montar
`EstadoDemo`) está probada contra `FakeResolve` con `file_path` inyectado a
mano (`core.analysis.analizar_clip` sustituido por un doble, igual que en
`tests/test_analysis_lote.py` — no hace falta vídeo real para probar esta
orquestación). Lo que SÍ es nuevo hoy y no tenía ningún camino de prueba
posible sin Resolve real delante: `LiveResolve.list_clips()` devolviendo
`ClipRef` de verdad con `file_path` de verdad.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from core.analysis import extraer_fotogramas
from core.analysis.lote import ProgresoLote, analizar_lote
from core.contracts import ResolveBridge
from core.matching import desajuste_de_contenido, emparejar_analisis
from gui.datos_demo import LOOK_REL, ClipDemo, EstadoDemo

__all__ = ["SinClipsReales", "construir_estado_real"]


class SinClipsReales(RuntimeError):
    """El timeline actual no tiene ningún clip de vídeo con fichero en disco
    (p.ej. está vacío, o sólo trae generadores/títulos sin fichero)."""


def construir_estado_real(
    puente: ResolveBridge,
    *,
    referencia_clip_id: str | None = None,
    manifiesto: str | Path | None = None,
    callback_progreso: Callable[[ProgresoLote], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
) -> EstadoDemo:
    """Lista los clips del timeline actual, los analiza de verdad (ffmpeg) y
    los empareja contra una referencia — nada simulado.

    `referencia_clip_id`, si se da y se pudo analizar, es la referencia; si
    no, se usa el primero de los que sí se analizaron bien (orden de
    `puente.list_clips()`). Un clip que falla al analizar (`ErrorAnalisis`,
    ver `core.analysis.lote`) se queda fuera de `EstadoDemo.clips`, no tumba
    la construcción del estado — se cuenta en `EstadoDemo.notas`.

    Lanza `SinClipsReales` si no hay ningún clip con `file_path`, o si
    ninguno de los que lo tienen se pudo analizar.
    """
    refs = puente.list_clips()
    con_ruta = {r.clip_id: r.file_path for r in refs if r.file_path}
    if not con_ruta:
        raise SinClipsReales(
            "el timeline actual no tiene ningún clip con fichero en disco que analizar"
        )

    resultado = analizar_lote(
        con_ruta,
        manifiesto=manifiesto,
        callback_progreso=callback_progreso,
        debe_cancelar=debe_cancelar,
    )
    analizados = resultado.analisis
    if not analizados:
        raise SinClipsReales("ninguno de los clips del timeline se ha podido analizar")

    referencia_id = referencia_clip_id if referencia_clip_id in analizados else next(iter(analizados))
    analisis_referencia = analizados[referencia_id]

    # Un fotograma de verdad por clip, para el antes/después visual --
    # `ClipAnalysis.pixels` (si se pidiera) es una MUESTRA aplanada, no una
    # imagen (alto, ancho, 3): hace falta un fotograma real aparte.
    frames: dict[str, np.ndarray] = {}
    for clip_id in analizados:
        fotogramas = extraer_fotogramas(con_ruta[clip_id], n_fotogramas=1)
        frames[clip_id] = fotogramas[0]

    ref_por_id = {r.clip_id: r for r in refs}
    clips: list[ClipDemo] = []
    for clip_id, analisis in analizados.items():
        match = emparejar_analisis(analisis, analisis_referencia)
        razones: tuple[str, ...] = ()
        if match.content_mismatch:
            _, _, razones = desajuste_de_contenido(frames[clip_id], frames[referencia_id])
        clips.append(
            ClipDemo(
                ref=ref_por_id[clip_id],
                match=match,
                original=frames[clip_id],
                razones_desajuste=razones,
            )
        )

    notas = [
        f"conectado a Resolve real: {len(clips)} de {len(refs)} clip(s) del timeline analizados"
    ]
    if resultado.fallos:
        notas.append(
            "no se han podido analizar: "
            + ", ".join(f"{cid} ({msg})" for cid, msg in resultado.fallos.items())
        )
    if resultado.cancelado:
        notas.append(f"análisis cancelado a mitad — {len(resultado.pendientes)} clip(s) sin intentar")

    return EstadoDemo(
        clips=clips,
        puente=puente,
        referencia_id=referencia_id,
        referencia_img=frames[referencia_id],
        look=None,
        look_rel=LOOK_REL,
        notas=tuple(notas),
    )
