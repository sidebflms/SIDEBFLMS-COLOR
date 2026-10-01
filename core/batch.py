"""Ejecución por lotes: por trozos, reanudable, cancelable, con fallo por
ítem aislado — la pieza de arquitectura que `BITACORA.md` lleva dos noches
señalando como hueco ("no existe ningún orquestador de 'analiza esta
timeline entera' con estado reanudable"; "no hay forma de cancelar
`aplicar()` a mitad"; "es la MISMA pieza de arquitectura... ejecución por
trozos con un punto de cancelación entre clip y clip").

QUÉ RESUELVE, CONCRETAMENTE
---------------------------
Antes de este módulo, cada sitio que necesitaba "iterar sobre una lista de
clips, aislando el fallo de cada uno" lo hacía a mano (`gui/pantalla_aplicar
.py::aplicar()` es el ejemplo real) — un bucle `for` síncrono, sin punto de
cancelación, sin estado persistido entre llamadas. Este módulo generaliza esa
forma, una sola vez, para que cualquier lote nuevo (analizar una timeline
entera, aplicar un lote, lo que haga falta mañana) la reutilice en vez de
reinventarla.

QUÉ NO RESUELVE, A PROPÓSITO
------------------------------
El manifiesto reanudable guarda **estado (hecho/fallo), no el resultado
entero**. Basta para lo que pide `BITACORA.md` ("un manifiesto clip_id ->
resultado-o-error, escrito de forma incremental... para poder reanudar
saltándose los ya hechos, y devolver un resumen con éxitos/fallos") — un
`ClipAnalysis` completo lleva arrays de numpy que no son JSON de forma
directa, y forzar esa serialización aquí habría acoplado un motor genérico a
un tipo concreto. Quien necesite recuperar el resultado ENTERO de un ítem ya
hecho en una ejecución anterior (no sólo saber que se hizo) tiene que
guardarlo él mismo, con el formato que le convenga — este módulo sólo le
ahorra volver a EJECUTAR `funcion` sobre ítems que ya sabe que terminaron bien.

CÓMO SE CANCELA DE VERDAD SIN HILOS
--------------------------------------
Este proyecto no usa `QThread` en ningún sitio (ver `gui/capturas.py`:
`app.processEvents()` es el patrón establecido para no bloquear Qt). En vez
de forzar hilos aquí, `ejecutar_lote` llama a `callback_progreso` DESPUÉS DE
CADA ÍTEM, antes de pasar al siguiente — quien lo llame desde la GUI puede,
dentro de ese callback, pintar una barra de progreso Y bombear el bucle de
eventos de Qt (`app.processEvents()`), dejando que un botón "Cancelar" se
pueda pulsar de verdad entre ítem e ítem. `debe_cancelar` se comprueba justo
antes de cada ítem nuevo (nunca a mitad de uno: un ítem se hace entero o no
se empieza, nunca a medias).

`CONCURRENCIA` (issue #3): PARALELO SÓLO SI SE PIDE, Y SÓLO HILOS
-------------------------------------------------------------------
Lo anterior sigue siendo cierto con `concurrencia=1` (el defecto): el camino
de código es LITERALMENTE el de siempre, sin tocar. `concurrencia>1` añade un
segundo camino con `ThreadPoolExecutor` — hilos, no procesos, porque `funcion`
en el caso real (`core.analysis.lote.analizar_lote` -> `analizar_clip` ->
`subprocess.run(ffmpeg)`) pasa la mayor parte del tiempo esperando a un
subproceso, con el GIL suelto; no hace falta pagar el coste de multiprocessing
para eso.

Sigue sin haber "cancelar a mitad de un ítem": los pendientes se procesan en
TROZOS de tamaño `concurrencia`, y `debe_cancelar()` se comprueba entre
trozos, nunca a mitad de uno — un trozo que ya se ha lanzado se termina
entero (hasta `concurrencia - 1` ítems de más de los que habría con
`concurrencia=1`, nunca ítems a medias). `callback_progreso` y la escritura
del manifiesto siguen pasando SIEMPRE en el hilo que llamó a `ejecutar_lote`
(nunca en un hilo trabajador): los trabajadores sólo ejecutan `funcion`, y el
hilo llamante recoge cada resultado con `as_completed` uno a uno. Eso importa
de verdad para quien llame desde la GUI con el patrón de `app.processEvents()`
de más arriba -- Qt no tolera que se le llame desde un hilo que no sea el
principal.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = [
    "EstadoItem",
    "ProgresoLote",
    "ResultadoItem",
    "ResultadoLote",
    "ejecutar_lote",
]

EstadoItem = Literal["hecho", "fallo"]


@dataclass(frozen=True)
class ResultadoItem:
    """Lo que le pasó a UN ítem del lote."""

    item_id: str
    estado: EstadoItem
    #: Sólo tiene contenido cuando `estado == "fallo"` — el texto de la
    #: excepción capturada, en el idioma que ya venga (esta capa no traduce).
    mensaje: str = ""


@dataclass(frozen=True)
class ProgresoLote:
    """Lo que recibe `callback_progreso` justo después de cada ítem —
    procesado de verdad esta vez, o encontrado ya hecho en el manifiesto."""

    #: Posición del ítem dentro de `item_ids`, 1-based (no cuenta cuántos se
    #: han EJECUTADO: cuenta posición, para que una barra de progreso sepa
    #: "voy por el 47 de 200" aunque los primeros 40 vinieran ya hechos).
    indice: int
    total: int
    resultado: ResultadoItem
    #: True si este resultado viene del manifiesto de una ejecución anterior
    #: (no se ha vuelto a llamar a `funcion` para él).
    reanudado: bool = False


@dataclass(frozen=True)
class ResultadoLote:
    """Lo que devuelve `ejecutar_lote` al terminar (o al cancelarse)."""

    resultados: dict[str, ResultadoItem]
    #: True si `debe_cancelar()` paró el lote antes de agotar `item_ids`.
    #: Los ítems que no se llegaron a intentar simplemente no están en
    #: `resultados` — ni "hecho" ni "fallo": no se sabe, todavía.
    cancelado: bool

    @property
    def hechos(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.resultados.items() if v.estado == "hecho")

    @property
    def fallidos(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.resultados.items() if v.estado == "fallo")


def _leer_manifiesto(ruta: Path) -> dict[str, ResultadoItem]:
    if not ruta.is_file():
        return {}
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(crudo, dict):
        return {}
    resultados: dict[str, ResultadoItem] = {}
    for item_id, datos in crudo.items():
        if not isinstance(datos, dict):
            continue
        estado = datos.get("estado")
        if estado not in ("hecho", "fallo"):
            continue
        resultados[item_id] = ResultadoItem(
            item_id=item_id, estado=estado, mensaje=str(datos.get("mensaje", ""))
        )
    return resultados


def _escribir_manifiesto(ruta: Path, resultados: dict[str, ResultadoItem]) -> None:
    crudo = {k: {"estado": v.estado, "mensaje": v.mensaje} for k, v in resultados.items()}
    # El manifiesto es sólo una optimización para reanudar: si no se puede
    # escribir (disco lleno, permisos), el lote sigue funcionando igual, sin
    # esa red de seguridad para la próxima vez.
    with contextlib.suppress(OSError):
        ruta.write_text(json.dumps(crudo, ensure_ascii=False), encoding="utf-8")


def _ejecutar_uno(
    funcion: Callable[[str], object], item_id: str, excepciones: tuple[type[Exception], ...]
) -> ResultadoItem:
    try:
        funcion(item_id)
    except excepciones as exc:
        return ResultadoItem(item_id=item_id, estado="fallo", mensaje=str(exc))
    return ResultadoItem(item_id=item_id, estado="hecho")


def _en_trozos(pendientes: list[tuple[int, str]], tamano: int) -> Iterator[list[tuple[int, str]]]:
    for inicio in range(0, len(pendientes), tamano):
        yield pendientes[inicio : inicio + tamano]


def ejecutar_lote(
    item_ids: Sequence[str],
    funcion: Callable[[str], object],
    *,
    excepciones: tuple[type[Exception], ...],
    manifiesto: str | Path | None = None,
    reintentar_fallidos: bool = True,
    callback_progreso: Callable[[ProgresoLote], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
    concurrencia: int = 1,
) -> ResultadoLote:
    """Llama a `funcion(item_id)` para cada `item_id` de `item_ids`, aislando
    el fallo de cada uno.

    `excepciones` es obligatorio y explícito a propósito, igual que
    `aplicar()` sólo captura `ResolveError`: cualquier excepción que NO esté
    en esa tupla se propaga y tumba el lote entero, porque es un bug del
    programa, no un fallo esperable de un ítem (disco lleno, clip corrupto,
    Resolve que no contesta). No adivines aquí qué es "esperable" — pásalo tú.

    `manifiesto`, si se da, es la ruta de un fichero JSON con el estado de
    cada ítem ya intentado. Al empezar, se lee (si existe) y los ítems que
    salieron "hecho" se SALTAN sin volver a llamar a `funcion` — es lo que
    hace esto "reanudable": una segunda llamada, con el mismo `manifiesto`,
    continúa donde lo dejó la anterior en vez de repetir trabajo ya hecho.
    Los que salieron "fallo" se reintentan por defecto
    (`reintentar_fallidos=True`) porque un fallo puede haber sido transitorio
    (disco lleno un momento, Resolve ocupado) — con `False` también se
    saltan, y se quedan con su mensaje de fallo de la vez anterior.

    `debe_cancelar`, si se da, se comprueba justo ANTES de cada ítem nuevo que
    vaya a ejecutarse de verdad (nunca para los que se saltan por ya estar
    hechos; con `concurrencia>1`, antes de cada TROZO nuevo — ver el docstring
    del módulo). Si devuelve `True`, el lote para ahí: los ítems que quedaban
    se quedan fuera de `ResultadoLote.resultados` (ni hecho ni fallo), y
    `ResultadoLote.cancelado` sale `True`. Volver a llamar con el mismo
    `manifiesto` retoma justo donde se paró.

    `concurrencia` (por defecto `1`, o sea el comportamiento de siempre, sin
    ningún cambio): con un entero mayor, procesa los ítems pendientes en
    trozos de ese tamaño con hasta `concurrencia` llamadas a `funcion` a la
    vez, en hilos (ver el docstring del módulo sobre por qué hilos y no
    procesos, y sobre en qué hilo se llama a `callback_progreso`).
    """
    if isinstance(concurrencia, bool) or not isinstance(concurrencia, int) or concurrencia < 1:
        raise ValueError(
            f"concurrencia tiene que ser un entero >= 1, y llego {concurrencia!r} "
            f"({type(concurrencia).__name__})"
        )

    ruta_manifiesto = Path(manifiesto) if manifiesto is not None else None
    resultados: dict[str, ResultadoItem] = (
        dict(_leer_manifiesto(ruta_manifiesto)) if ruta_manifiesto is not None else {}
    )
    total = len(item_ids)

    # Comun a los dos caminos: que ya esta "hecho" (o fallo sin reintentar) se
    # salta sin volver a llamar a `funcion`, avisando igual por el callback.
    pendientes: list[tuple[int, str]] = []
    for indice, item_id in enumerate(item_ids, start=1):
        existente = resultados.get(item_id)
        ya_vale = existente is not None and (
            existente.estado == "hecho" or not reintentar_fallidos
        )
        if ya_vale:
            if callback_progreso is not None:
                callback_progreso(
                    ProgresoLote(indice=indice, total=total, resultado=existente, reanudado=True)
                )
            continue
        pendientes.append((indice, item_id))

    cancelado = False

    if concurrencia == 1:
        # El camino de siempre, sin tocar: un item, una llamada, un resultado.
        for indice, item_id in pendientes:
            if debe_cancelar is not None and debe_cancelar():
                cancelado = True
                break
            resultado = _ejecutar_uno(funcion, item_id, excepciones)
            resultados[item_id] = resultado
            if ruta_manifiesto is not None:
                _escribir_manifiesto(ruta_manifiesto, resultados)
            if callback_progreso is not None:
                callback_progreso(ProgresoLote(indice=indice, total=total, resultado=resultado))
        return ResultadoLote(resultados=resultados, cancelado=cancelado)

    # concurrencia > 1: en trozos, con hilos dentro de cada trozo. El hilo que
    # llamo a ejecutar_lote es el UNICO que escribe en `resultados`, escribe
    # el manifiesto o llama a `callback_progreso` -- los trabajadores solo
    # ejecutan `funcion` y devuelven su `ResultadoItem`.
    with ThreadPoolExecutor(max_workers=concurrencia) as executor:
        for trozo in _en_trozos(pendientes, concurrencia):
            if debe_cancelar is not None and debe_cancelar():
                cancelado = True
                break
            futuros = {
                executor.submit(_ejecutar_uno, funcion, item_id, excepciones): (indice, item_id)
                for indice, item_id in trozo
            }
            for futuro in as_completed(futuros):
                indice, item_id = futuros[futuro]
                resultado = futuro.result()
                resultados[item_id] = resultado
                if ruta_manifiesto is not None:
                    _escribir_manifiesto(ruta_manifiesto, resultados)
                if callback_progreso is not None:
                    callback_progreso(
                        ProgresoLote(indice=indice, total=total, resultado=resultado)
                    )

    return ResultadoLote(resultados=resultados, cancelado=cancelado)
