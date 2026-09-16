"""`invertir_grado_lote`: N pares (original, coloreado) del mismo trabajo -> UN grado.

LA IDEA
-------
Si el colorista tiene el máster coloreado entero y los brutos enteros, y todos
los planos llevan el mismo look, no hace falta sacar el grado de un plano y
rezar para que valga en los demás (`MEDICION-T5.md`: no vale). Se pueden sumar
las correspondencias de todos los planos contra **la misma** transformación.

Y se suman de verdad, no se promedian LUTs: el ajuste del LUT es un problema de
mínimos cuadrados cuyos estadísticos suficientes (`A^T y`, `A^T A`, `D`) se
suman plano a plano (`core.reverse.acumulacion.Estadisticos`). Un lote de un
solo plano con `informacion="suma_w"` da **el mismo LUT, bit a bit,** que
`invertir_grado`.

UNA DIFERENCIA A PROPÓSITO CON `invertir_grado`
-----------------------------------------------
Por defecto el lote mide cuánto sabe cada nodo con `suma de w^2` y no con
`suma de w` (`informacion="suma_w2"`, ver `LAMBDA_SUAVIDAD_W2` en `relleno.py`).
Con muchos planos mejora tanto la zona cubierta como los propios planos; con un
solo plano y un look de secundarias estrechas empeora lo típico, y por eso
`invertir_grado` no lo usa. Cifras en `core/reverse/NOTAS.md` §12.

LA TRAMPA, Y POR QUÉ ESTE MÓDULO SE NIEGA A CAER EN ELLA CALLADO
-----------------------------------------------------------------
Si el colorista corrigió planos por separado (uno más cálido, otro más frío),
sumarlos mezcla grados distintos y sale un LUT que **no es de ninguno** y que
tiene buena cara. Eso es peor que no acumular. Así que antes de ajustar,
`comprobar_coherencia` mira si los planos llevan **el mismo color de entrada al
mismo color de salida**:

1. Se suman los estadísticos de todos los planos y, para cada plano `p`, se
   **restan los suyos**: eso es el grado ajustado con los demás, sin volver a
   leer un píxel (arranque en caliente, `ITERACIONES_COHERENCIA` vueltas).
2. Se toman los píxeles de `p` cuyos **ocho** nodos tienen datos de los demás
   (`MUESTRAS_MINIMAS_CELDA`). Ahí, y sólo ahí, el grado de los demás sabe algo.
3. Se compara lo que ese grado predice con la salida real de `p`, en ΔE2000
   (mediana), y se le **resta** la mediana del mismo ΔE frente al LUT ajustado
   solo con `p`. Lo que queda es lo que el grado de los demás explica PEOR que
   el suyo propio: el ruido, la compresión o el grano del coloreado no lo
   explica ninguno de los dos y se cancela.
4. Si algún plano pasa de `UMBRAL_DISCREPANCIA_LOTE`, se saca **el peor**, se
   recalcula todo sin él y se repite. Así un plano bueno que comparte colores
   con uno malo no se queda marcado: en cuanto sale el malo, baja.

POR QUÉ ASÍ Y NO DE OTRA FORMA (`core/reverse/NOTAS.md` §12)
-----------------------------------------------------------
* **Píxel con píxel (vecino más cercano), descartado.** En este espacio de
  trabajo un paso de 0.001 en un solo canal de un gris medio ya son del orden de
  1 ΔE2000 (`[lote sensibilidad del espacio]` en
  `tests/test_reverse_lote_determinacion.py`). Dos píxeles «vecinos» a 0.005
  pueden diferir varios ΔE llevando el mismo grado. El grado de los demás, en
  cambio, interpola dentro de la celda.
* **Sin restar el suelo propio, descartado.** Con ruido en el coloreado (del
  orden de una compresión) un proyecto coherente sale con planos discrepantes;
  restando el suelo, no. Cifras con su comando en `[lote suelo]` del mismo test.

LO QUE TODAVÍA LE ENGAÑA
------------------------
Una viñeta (o cualquier cosa espacial) común a todos los planos. Con viñeta, un
mismo color de entrada sale distinto según dónde está en el cuadro, así que un
plano con ese color en las esquinas y otro con él en el centro **sí** llevan
mapas de color distintos, y el LUT acumulado **sí** falla en ellos. Pero la causa
no es «otro grado». Medido: viñeta 0.45 en 8 planos -> 3 marcados
(`[lote vineta]` en `tests/test_reverse_lote.py`).
`invertir_grado_lote` cruza el aviso con el diagnóstico espacial de cada plano y
lo dice.

Lo que no se puede comprobar se dice: un plano que no comparte ningún color con
los demás sale en `sin_comparar`, no en «coherente».

LO QUE NO HACE
--------------
* No decide por el colorista. Con `excluir_discrepantes=False` (defecto) ajusta
  con todos y **avisa** (razón la primera, nota y confianza multiplicada por
  `PENA_LOTE_INCOHERENTE`). Con `True` ajusta sin los planos discrepantes y lo
  dice.
* No ve una corrección que solo toca colores que ningún otro plano tiene: ahí no
  hay con qué comparar. Es un límite de la idea, no del código.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from core.color import delta_e2000, rgb_to_lab
from core.contracts import (
    CDL,
    LUT3D,
    LUT_SIZE_DEFAULT,
    WORKING_SPACE,
    ColorSpaceName,
    Confidence,
    CoverageMap,
    ReverseDiagnosis,
    ReverseResult,
    confidence_level,
)
from core.matching import (
    ajustar_cdl,
    desajuste_de_contenido,
    puntuar_confianza,
    solape_de_distribuciones,
)
from core.reverse.acumulacion import (
    Estadisticos,
    estadisticos_de_correspondencias,
    fraccion_fuera_de_dominio,
    pesos_trilineales,
)
from core.reverse.alineado import alinear
from core.reverse.diagnostico import diagnosticar
from core.reverse.invertir import (
    MAX_PIXELES_CDL,
    InformacionDeNodo,
    _ajustar_lut,
    _condicion,
    _mascara_cubierta,
    _submuestra,
)
from core.reverse.relleno import celdas_con_dato, rejilla_de_entradas
from core.umbrales import (
    MUESTRAS_MINIMAS_CDL,
    MUESTRAS_MINIMAS_CELDA,
    PENA_LOTE_INCOHERENTE,
    PIXELES_COMPARTIDOS_MINIMOS_LOTE,
    UMBRAL_COBERTURA_BAJA,
    UMBRAL_DISCREPANCIA_LOTE,
    UMBRAL_FUERA_DE_DOMINIO_AVISO,
)

__all__ = [
    "ITERACIONES_COHERENCIA",
    "MUESTRAS_COHERENCIA",
    "InformeCoherencia",
    "PlanoDelLote",
    "comprobar_coherencia",
    "invertir_grado_lote",
]

#: Píxeles por plano que entran en la comprobación de coherencia. Es un
#: parámetro de coste, no un umbral: la mediana de 20.000 ΔE ya no se mueve.
MUESTRAS_COHERENCIA: int = 20_000

#: Vueltas de Jacobi del ajuste «sin el plano p», arrancando del ajuste con
#: todos. Coste, no criterio: con 15 vueltas en caliente en vez de 60 en frío la
#: comprobación tarda unas 3.5 veces menos. **La comparación con 60 en frío se
#: hizo durante el desarrollo con una versión anterior de la puntuación y no
#: tiene comando: no medido con el código actual.** Lo que sí está medido es el
#: resultado final (`tests/test_reverse_lote.py`).
ITERACIONES_COHERENCIA: int = 15


# ---------------------------------------------------------------------------
# Lo que devuelve la comprobación
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanoDelLote:
    """El veredicto de coherencia de UN plano frente al resto."""

    indice: int
    nombre: str
    #: **La cifra que decide.** `de_frente_a_los_demas - de_suelo_propio`: cuánto
    #: peor explica este plano el grado de los demás que su propio LUT, en ΔE2000
    #: (medianas). Es la de la ronda en la que se le sacó (si discrepa) o la de
    #: la última ronda (si no). `nan` si no comparte colores con los demás.
    exceso_de: float
    #: Mediana del ΔE2000 entre la salida real de este plano y lo que predice el
    #: grado ajustado con los DEMÁS planos, en los píxeles cuyos ocho nodos
    #: tienen datos de los demás.
    de_frente_a_los_demas: float
    #: Mediana del ΔE2000, en esos mismos píxeles, frente al LUT ajustado SOLO
    #: con este plano: lo que ningún LUT explica (ruido, compresión, viñeta).
    de_suelo_propio: float
    #: Cuántos píxeles (de su submuestra) entran en esa mediana.
    pixeles_compartidos: int
    #: Desvío medio (L*, a*, b*) de ESTE plano frente al grado de los demás en
    #: los colores compartidos. b* > 0 = más cálido/amarillo, a* > 0 = más
    #: magenta, L* > 0 = más claro.
    desvio_lab: tuple[float, float, float]
    discrepa: bool
    #: Ronda (1, 2, ...) en la que se le sacó; 0 si no se le sacó.
    ronda: int = 0


@dataclass(frozen=True)
class InformeCoherencia:
    planos: tuple[PlanoDelLote, ...]
    discrepantes: tuple[int, ...]
    sin_comparar: tuple[int, ...]
    #: True si ningún plano discrepa. Ojo: un plano que no comparte colores con
    #: nadie no cuenta como discrepante, así que mira también `sin_comparar`.
    coherente: bool
    #: True si se sacó a la mitad o más de los planos comparables: entonces no hay
    #: una mayoría que sirva de referencia y la lista de discrepantes no es fiable.
    sin_mayoria: bool
    avisos: tuple[str, ...]


# ---------------------------------------------------------------------------
# Coherencia
# ---------------------------------------------------------------------------

#: (exceso, píxeles compartidos, desvío Lab, frente a los demás, suelo propio)
_Puntos = tuple[float, int, np.ndarray, float, float]
_SIN_PUNTOS: _Puntos = (float("nan"), 0, np.full(3, np.nan), float("nan"), float("nan"))


def comprobar_coherencia(
    pares: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    nombres: Sequence[str] | None = None,
    tam_lut: int = LUT_SIZE_DEFAULT,
    space: ColorSpaceName = WORKING_SPACE,
    umbral: float = UMBRAL_DISCREPANCIA_LOTE,
    cdl: CDL | None = None,
    informacion: InformacionDeNodo = "suma_w2",
    restar_suelo: bool = True,
) -> InformeCoherencia:
    """¿Llevan todos los planos el mismo color de entrada al mismo de salida?

    `pares` son `(original, coloreado)` **ya alineados** (lo hace
    `invertir_grado_lote`). `cdl` es el CDL común con el que se lleva la entrada
    al dominio del LUT; si no se da, se ajusta con todos los planos. Ver el
    docstring del módulo para el método.

    `restar_suelo=False` puntúa sin restar el residuo del LUT propio de cada
    plano. **Sólo existe para poder medir por qué se resta** (ver
    `tests/test_reverse_lote_determinacion.py`); no lo uses para decidir nada.
    """
    nombres = _nombres(nombres, len(pares))
    srcs, dsts = [], []
    for original, coloreado in pares:
        s = np.asarray(original, dtype=np.float64).reshape(-1, 3)
        d = np.asarray(coloreado, dtype=np.float64).reshape(-1, 3)
        if s.shape != d.shape:
            raise ValueError(
                f"los pares tienen que venir alineados y del mismo tamaño: {s.shape} frente a {d.shape}"
            )
        fin = np.isfinite(s).all(axis=1) & np.isfinite(d).all(axis=1)
        srcs.append(s[fin])
        dsts.append(d[fin])
    if cdl is None:
        cdl = _cdl_del_lote(srcs, dsts)
    fuentes = [cdl.apply(s) for s in srcs]
    n = int(tam_lut)
    estadisticos = [
        estadisticos_de_correspondencias(f, d, n, con_gram=True)
        for f, d in zip(fuentes, dsts, strict=True)
    ]
    return _coherencia(
        fuentes,
        dsts,
        estadisticos,
        nombres,
        space=space,
        umbral=umbral,
        informacion=informacion,
        restar_suelo=restar_suelo,
    )


def _coherencia(
    fuentes: list[np.ndarray],
    dsts: list[np.ndarray],
    estadisticos: list[Estadisticos],
    nombres: list[str],
    *,
    space: ColorSpaceName,
    umbral: float,
    informacion: InformacionDeNodo,
    restar_suelo: bool = True,
) -> InformeCoherencia:
    n_planos = len(fuentes)
    if n_planos == 0:
        return InformeCoherencia((), (), (), True, False, ())
    n = estadisticos[0].n
    entradas = rejilla_de_entradas(n)
    muestras = [
        (_submuestra(f, MUESTRAS_COHERENCIA), _submuestra(d, MUESTRAS_COHERENCIA))
        for f, d in zip(fuentes, dsts, strict=True)
    ]
    labs = [rgb_to_lab(d, space) for _, d in muestras]
    trilineales = [pesos_trilineales(u, n)[0] for u, _ in muestras]

    propios: dict[int, LUT3D] = {}

    def lut_propio(p: int) -> LUT3D:
        """El grado de `p` ajustado SOLO con `p`: lo que un LUT puede explicar de
        este plano. Su residuo es el suelo (ruido, viñeta, compresión) que no
        tiene nada que ver con que `p` lleve otro grado."""
        if p not in propios:
            est = estadisticos[p]
            propios[p] = _ajustar_lut(
                est, celdas_con_dato(est.cobertura()), entradas, informacion=informacion
            )
        return propios[p]

    def puntuar(dentro: list[int]) -> dict[int, _Puntos]:
        total = Estadisticos.vacios(n, con_gram=True)
        for p in dentro:
            total = total + estadisticos[p]
        lut_total = _ajustar_lut(
            total, celdas_con_dato(total.cobertura()), entradas, informacion=informacion
        )
        puntos = {}
        for p in dentro:
            sin = total - estadisticos[p]
            medidas = celdas_con_dato(sin.cobertura())
            u, y = muestras[p]
            compartido = (sin.counts[trilineales[p]] >= MUESTRAS_MINIMAS_CELDA).all(axis=0)
            if int(compartido.sum()) < PIXELES_COMPARTIDOS_MINIMOS_LOTE or not medidas.any():
                puntos[p] = _SIN_PUNTOS[:1] + (int(compartido.sum()),) + _SIN_PUNTOS[2:]
                continue
            lut = _ajustar_lut(
                sin,
                medidas,
                entradas,
                iteraciones=ITERACIONES_COHERENCIA,
                inicial=lut_total,
                informacion=informacion,
            )
            pred = lut.apply(u[compartido])
            de = np.asarray(delta_e2000(pred, y[compartido], space), dtype=np.float64)
            if restar_suelo:
                suelo = np.asarray(
                    delta_e2000(lut_propio(p).apply(u[compartido]), y[compartido], space),
                    dtype=np.float64,
                )
            else:
                suelo = np.zeros(1)
            desvio = (labs[p][compartido] - rgb_to_lab(pred, space)).mean(axis=0)
            puntos[p] = (
                float(np.median(de) - np.median(suelo)),
                int(compartido.sum()),
                desvio,
                float(np.median(de)),
                float(np.median(suelo)),
            )
        return puntos

    dentro = list(range(n_planos))
    sacados: dict[int, tuple[_Puntos, int]] = {}
    ronda = 0
    puntos: dict[int, _Puntos] = {}
    comparables: set[int] = set()
    while len(dentro) > 1:
        ronda += 1
        puntos = puntuar(dentro)
        if ronda == 1:
            comparables = {p for p, v in puntos.items() if np.isfinite(v[0])}
        candidatos = [p for p, v in puntos.items() if np.isfinite(v[0]) and v[0] > umbral]
        if not candidatos:
            break
        peor = max(candidatos, key=lambda p: puntos[p][0])
        sacados[peor] = (puntos[peor], ronda)
        dentro.remove(peor)
        if len(sacados) * 2 >= max(len(comparables), 1):
            break
    if len(dentro) <= 1 and not puntos:
        puntos = {p: _SIN_PUNTOS for p in dentro}

    sin_mayoria = bool(comparables) and len(sacados) * 2 >= len(comparables)
    planos = []
    for p in range(n_planos):
        if p in sacados:
            (exceso, cuantos, desvio, frente, suelo), r = sacados[p]
        else:
            exceso, cuantos, desvio, frente, suelo = puntos.get(p, _SIN_PUNTOS)
            r = 0
        planos.append(
            PlanoDelLote(
                indice=p,
                nombre=nombres[p],
                exceso_de=float(exceso),
                de_frente_a_los_demas=float(frente),
                de_suelo_propio=float(suelo),
                pixeles_compartidos=int(cuantos),
                desvio_lab=tuple(float(v) for v in desvio),
                discrepa=p in sacados,
                ronda=r,
            )
        )

    discrepantes = tuple(sorted(sacados))
    sin_comparar = tuple(
        p for p in range(n_planos) if p not in sacados and not np.isfinite(planos[p].exceso_de)
    )
    avisos: list[str] = []
    if sin_mayoria:
        avisos.append(
            f"Los planos no llevan un grado común: después de sacar {len(sacados)} de "
            f"{len(comparables)} planos comparables sigue sin haber una mayoría que coincida. "
            "No puedo decir cuáles son los buenos, y acumularlos daría un LUT que no es de "
            "ninguno."
        )
    elif discrepantes:
        detalle = "; ".join(_describir(planos[p]) for p in discrepantes)
        avisos.append(
            f"{len(discrepantes)} de {n_planos} planos no llevan el mismo grado que el resto: "
            f"en los colores que comparten, su salida se aparta más de {umbral:.1f} ΔE2000 "
            f"(mediana) de lo que hacen los demás. {detalle}. Acumularlos con los demás mezcla "
            "grados distintos."
        )
    if sin_comparar and n_planos > 1:
        avisos.append(
            f"{len(sin_comparar)} planos no comparten colores con los demás y no he podido "
            "comprobar si llevan el mismo grado: "
            + ", ".join(nombres[p] for p in sin_comparar)
            + "."
        )
    return InformeCoherencia(
        planos=tuple(planos),
        discrepantes=discrepantes,
        sin_comparar=sin_comparar,
        coherente=not discrepantes,
        sin_mayoria=sin_mayoria,
        avisos=tuple(avisos),
    )


def _describir(plano: PlanoDelLote) -> str:
    dl, da, db = plano.desvio_lab
    if abs(db) >= abs(da):
        tinte = "más cálido" if db > 0 else "más frío"
    else:
        tinte = "más magenta" if da > 0 else "más verde"
    # La luz se nombra cuando mueve al menos la mitad que el color: un plano más
    # abierto suele salir también más cálido, y decir sólo «más cálido» engaña.
    if abs(dl) >= 0.5 * float(np.hypot(da, db)):
        tinte = ("más claro" if dl > 0 else "más oscuro") + f" y {tinte}"
    return (
        f"{plano.nombre}: {plano.exceso_de:.2f} ΔE, {tinte} "
        f"(L* {dl:+.1f}, a* {da:+.1f}, b* {db:+.1f})"
    )


def _nombres(nombres: Sequence[str] | None, n_planos: int) -> list[str]:
    salida = list(nombres) if nombres is not None else [f"plano {i + 1}" for i in range(n_planos)]
    if len(salida) != n_planos:
        raise ValueError(f"hay {n_planos} pares y {len(salida)} nombres")
    return salida


def _cdl_del_lote(srcs: list[np.ndarray], dsts: list[np.ndarray]) -> CDL:
    """Un CDL para todo el lote. Cada plano aporta la misma parte del presupuesto
    de píxeles, para que un plano grande no se coma el CDL. Con un solo plano es
    exactamente el submuestreo de `invertir_grado`."""
    n_validos = sum(s.shape[0] for s in srcs)
    if n_validos < MUESTRAS_MINIMAS_CDL:
        return CDL.identity()
    tope = max(MAX_PIXELES_CDL // max(len(srcs), 1), 1)
    return ajustar_cdl(
        np.concatenate([_submuestra(s, tope) for s in srcs]),
        np.concatenate([_submuestra(d, tope) for d in dsts]),
    )


# ---------------------------------------------------------------------------
# El ajuste por lote
# ---------------------------------------------------------------------------


def invertir_grado_lote(
    pares: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    nombres: Sequence[str] | None = None,
    tam_lut: int = LUT_SIZE_DEFAULT,
    space: ColorSpaceName = WORKING_SPACE,
    min_muestras: int = MUESTRAS_MINIMAS_CELDA,
    excluir_discrepantes: bool = False,
    diagnosticar_planos: bool = True,
    informacion: InformacionDeNodo = "suma_w2",
    verificar_coherencia: bool = True,
) -> ReverseResult:
    """Recupera UN grado (CDL + LUT) de muchos planos que lo comparten.

    `pares` es una secuencia de `(original, coloreado)`, cada uno `(alto, ancho,
    3)` en `space`, y cada pareja del mismo plano y encuadre (se alinean una a
    una igual que en `invertir_grado`). Los planos pueden tener tamaños
    distintos entre sí.

    Devuelve un `ReverseResult` como el de `invertir_grado`, con:

    * `cdl`, `lut`, `coverage`: los del lote entero;
    * `delta_e_*`: sobre TODOS los píxeles válidos de los planos usados; los de
      la zona cubierta en `confidence.metrics["de_*_cubierto"]`;
    * `diagnosis`: la del plano **peor** (menor `lut_reproducible`), y en
      `notes` cuál es y la de cada plano;
    * métricas del lote en `confidence.metrics`: `lote_planos`,
      `lote_planos_usados`, `lote_discrepantes`, `lote_sin_comparar`,
      `lote_de_discrepancia_max`;
    * el detalle de coherencia por plano en `notes` y, si hay discrepancia, la
      primera razón de `confidence.reasons` y la nota multiplicada por
      `PENA_LOTE_INCOHERENTE`. Para tenerlo como datos, llama a
      `comprobar_coherencia` con los pares alineados.

    Opciones:

    * `excluir_discrepantes`: ajustar sin los planos que no llevan el mismo
      grado (si hay una mayoría clara). Por defecto se ajusta con todos y se avisa.
    * `diagnosticar_planos`: el diagnóstico espacial de cada plano. Es lo más
      caro después de la coherencia; sin él `diagnosis.lut_reproducible` es `nan`.
    * `informacion`: `"suma_w2"` (defecto del lote) o `"suma_w"` (el de
      `invertir_grado`).
    * `verificar_coherencia`: `False` salta la comprobación (y lo dice en las
      notas). Existe para medir la cobertura sin pagarla, no para usarla a ciegas.

    Ejemplo::

        from core.reverse import invertir_grado_lote

        resultado = invertir_grado_lote(
            [(bruto_1, master_1), (bruto_2, master_2), (bruto_3, master_3)],
            nombres=["A001C003", "A001C007", "A002C001"],
        )
        resultado.lut.apply(resultado.cdl.apply(otro_bruto))
        resultado.confidence.metrics["lote_discrepantes"]   # 0.0 si todo cuadra
    """
    pares = list(pares)
    n_planos = len(pares)
    if n_planos == 0:
        raise ValueError("invertir_grado_lote necesita al menos un par (original, coloreado)")
    nombres = _nombres(nombres, n_planos)
    n = int(tam_lut)
    notas: list[str] = []

    # ------------------------------------------------------------------
    # Alinear cada pareja, y quedarse con los píxeles finitos.
    # ------------------------------------------------------------------
    alineados = []
    infos = []
    for (original, coloreado), nombre in zip(pares, nombres, strict=True):
        a, b, info = alinear(original, coloreado)
        notas.extend(f"[{nombre}] {nota}" for nota in info["notas"])
        alineados.append((a, b))
        infos.append(info)

    todos_src, todos_dst, todos_fin = [], [], []
    for a, b in alineados:
        s_ = a.reshape(-1, 3).astype(np.float64)
        d_ = b.reshape(-1, 3).astype(np.float64)
        fin = np.isfinite(s_).all(axis=1) & np.isfinite(d_).all(axis=1)
        todos_src.append(s_[fin])
        todos_dst.append(d_[fin])
        todos_fin.append(fin)
    total_px = sum(int(f.size) for f in todos_fin)
    n_validos_todos = sum(x.shape[0] for x in todos_src)
    if n_validos_todos == 0:
        raise ValueError("ningún plano del lote tiene un solo píxel finito")

    # ------------------------------------------------------------------
    # Capa 1: un CDL para todo el lote.
    # ------------------------------------------------------------------
    cdl = _cdl_del_lote(todos_src, todos_dst)
    if n_validos_todos < MUESTRAS_MINIMAS_CDL:
        notas.append(
            f"Solo hay {n_validos_todos} pixeles validos en todo el lote, menos de "
            f"{MUESTRAS_MINIMAS_CDL}. No ajusto CDL."
        )
    todas_fuentes = [cdl.apply(x) for x in todos_src]
    estadisticos_plano = [
        estadisticos_de_correspondencias(f, d, n, con_gram=True)
        for f, d in zip(todas_fuentes, todos_dst, strict=True)
    ]

    # ------------------------------------------------------------------
    # ¿Llevan el mismo grado? Antes de sumar nada.
    # ------------------------------------------------------------------
    if verificar_coherencia:
        coherencia = _coherencia(
            todas_fuentes,
            todos_dst,
            estadisticos_plano,
            nombres,
            space=space,
            umbral=UMBRAL_DISCREPANCIA_LOTE,
            informacion=informacion,
        )
    else:
        coherencia = InformeCoherencia(
            planos=(),
            discrepantes=(),
            sin_comparar=tuple(range(n_planos)) if n_planos > 1 else (),
            coherente=True,
            sin_mayoria=False,
            avisos=(
                ("NO he comprobado si los planos llevan el mismo grado "
                 "(verificar_coherencia=False).",)
                if n_planos > 1
                else ()
            ),
        )
    usados = list(range(n_planos))
    if excluir_discrepantes and coherencia.discrepantes and not coherencia.sin_mayoria:
        usados = [p for p in usados if p not in coherencia.discrepantes]
        notas.append(
            "He dejado FUERA del ajuste los planos que no llevan el mismo grado: "
            + ", ".join(nombres[p] for p in coherencia.discrepantes)
            + "."
        )
    notas.extend(coherencia.avisos)
    if coherencia.planos and n_planos > 1:
        notas.append(
            "Coherencia por plano (ΔE2000 que el grado de los demás explica peor que el suyo "
            "propio, en medianas): "
            + ", ".join(
                f"{pl.nombre} {pl.exceso_de:.2f}" + (" DISCREPA" if pl.discrepa else "")
                for pl in coherencia.planos
            )
            + "."
        )

    dsts = [todos_dst[p] for p in usados]
    buenos = [todos_fin[p] for p in usados]
    fuentes = [todas_fuentes[p] for p in usados]
    n_validos = sum(x.shape[0] for x in dsts)
    fraccion_no_finita = float(1.0 - n_validos_todos / total_px) if total_px else 1.0
    if fraccion_no_finita > 0.0:
        notas.append(
            f"He descartado el {fraccion_no_finita * 100:.2f}% de los pixeles del lote por traer "
            "NaN o infinito."
        )

    # ------------------------------------------------------------------
    # Capa 2: el LUT, sumando los estadísticos de los planos usados.
    # ------------------------------------------------------------------
    fuera = float(
        sum(fraccion_fuera_de_dominio(f) * f.shape[0] for f in fuentes) / max(n_validos, 1)
    )
    if fuera > UMBRAL_FUERA_DE_DOMINIO_AVISO:
        notas.append(
            f"El {fuera * 100:.2f}% de los pixeles del lote, despues del CDL, se sale del dominio "
            "0..1 del LUT. Ahi el LUT sujeta al borde y el color no se transforma."
        )
    estadisticos = Estadisticos.vacios(n, con_gram=True)
    for p in usados:
        estadisticos = estadisticos + estadisticos_plano[p]
    medidas = celdas_con_dato(estadisticos.cobertura(min_muestras))
    entradas = rejilla_de_entradas(n)
    if not medidas.any() or fuera >= 1.0:
        lut = LUT3D(table=entradas.astype(np.float32), title="SIDEB COLOR (sin cobertura)")
        notas.append(
            "Ningun pixel del lote cae dentro del dominio 0..1 del LUT: devuelvo la identidad."
        )
    else:
        lut = _ajustar_lut(estadisticos, medidas, entradas, informacion=informacion)

    varianza = Estadisticos.vacios(n)
    for f, d in zip(fuentes, dsts, strict=True):
        varianza = varianza + estadisticos_de_correspondencias(f, d, n, tabla=lut)
    cobertura: CoverageMap = varianza.cobertura(min_muestras)
    fraccion_cubierta = cobertura.coverage_fraction()
    con_dato = celdas_con_dato(cobertura)
    notas.append(
        f"Cobertura del lote ({len(usados)} planos): {int(con_dato.sum())} celdas de {n**3} han "
        f"visto al menos un pixel, y de esas {int(cobertura.covered_mask().sum())} llegan a "
        f"{min_muestras} muestras ({fraccion_cubierta * 100:.2f}% del cubo). Las otras "
        f"{int((~con_dato).sum())} estan INVENTADAS: son exactamente las de "
        "`coverage.counts == 0`."
    )

    # ------------------------------------------------------------------
    # Medidas, diagnóstico por plano y confianza.
    # ------------------------------------------------------------------
    des, des_cub = [], []
    diagnosticos: list[tuple[int, ReverseDiagnosis]] = []
    hay_desajuste, distancia_max, razones_contenido = False, 0.0, []
    for k, p in enumerate(usados):
        a, b = alineados[p]
        pred = lut.apply(cdl.apply(a.astype(np.float64)))
        de = np.asarray(delta_e2000(pred, b.astype(np.float64), space), dtype=np.float64)
        de = de.reshape(-1)[buenos[k]]
        fin = np.isfinite(de)
        cub = _mascara_cubierta(fuentes[k], cobertura, n) & fin
        des.append(de[fin])
        des_cub.append(de[cub])
        if fin.any():
            notas.append(
                f"[{nombres[p]}] ΔE2000 con el grado del lote: medio {de[fin].mean():.3f}, "
                f"máximo {de[fin].max():.3f}."
            )
        if diagnosticar_planos:
            diagnosticos.append((p, diagnosticar(a, b, cdl, lut, cobertura, space=space)))
        desajuste, distancia, razones = desajuste_de_contenido(a, b)
        if desajuste:
            hay_desajuste = True
            razones_contenido.extend(f"[{nombres[p]}] {r}" for r in razones[:1])
        distancia_max = max(distancia_max, float(distancia))
    de_todo = np.concatenate(des) if des else np.array([])
    de_cub = np.concatenate(des_cub) if des_cub else np.array([])

    def _resumen(v: np.ndarray) -> tuple[float, float, float]:
        if v.size == 0:
            return float("nan"), float("nan"), float("nan")
        return float(v.mean()), float(np.percentile(v, 95)), float(v.max())

    de_medio, de_p95, de_max = _resumen(de_todo)
    de_medio_cub, de_p95_cub, de_max_cub = _resumen(de_cub)

    # Un plano marcado como discrepante que ADEMAS tiene zonas espaciales (vineta,
    # ventana...) puede no llevar otro grado: con una vineta, el mismo color sale
    # distinto segun donde este en el cuadro. Se diagnostica tambien a los
    # excluidos para poder decirlo.
    con_espacial: list[int] = []
    if diagnosticar_planos:
        por_plano = dict(diagnosticos)
        for p in coherencia.discrepantes:
            if p not in por_plano:
                a, b = alineados[p]
                por_plano[p] = diagnosticar(a, b, cdl, lut, cobertura, space=space)
            if por_plano[p].hotspots:
                con_espacial.append(p)
    if con_espacial:
        notas.append(
            "Ojo con el aviso de coherencia: "
            + ", ".join(nombres[p] for p in con_espacial)
            + " tienen ademas zonas que un LUT no puede reproducir (vineta, ventana...). Con "
            "algo asi el mismo color sale distinto segun donde este en el cuadro, y la "
            "discrepancia puede venir de ahi y no de que lleven otro grado."
        )

    if diagnosticos:
        peor_plano, diagnosis = min(diagnosticos, key=lambda x: x[1].lut_reproducible)
        notas.append(
            f"Diagnostico: devuelvo el del plano peor, {nombres[peor_plano]} "
            f"(reproducible {diagnosis.lut_reproducible:.3f}). Por plano: "
            + ", ".join(f"{nombres[p]} {d.lut_reproducible:.3f}" for p, d in diagnosticos)
            + "."
        )
    else:
        diagnosis = ReverseDiagnosis(
            lut_reproducible=float("nan"),
            is_pure_lut=False,
            spatial_residual=None,
            hotspots=(),
            notes=("No se ha pedido diagnostico por plano (diagnosticar_planos=False).",),
        )
    if hay_desajuste:
        notas.append(
            "AVISO GORDO: en algun plano el original y el coloreado no parecen la misma escena. "
            + " ".join(razones_contenido[:2])
        )

    tope = max(200_000 // len(usados), 1)
    src_sub = np.concatenate([_submuestra(todos_src[p], tope) for p in usados])
    dst_sub = np.concatenate([_submuestra(d, tope) for d in dsts])
    solape = solape_de_distribuciones(lut.apply(cdl.apply(src_sub)), dst_sub)
    confianza = puntuar_confianza(
        n_muestras=int(n_validos),
        solape=float(solape),
        condicion=float(_condicion(src_sub)),
        residuo_de=de_medio,
        fraccion_no_finita=fraccion_no_finita,
        desajuste=bool(hay_desajuste),
        distancia_contenido=float(distancia_max),
    )
    de_discrepancia = [pl.exceso_de for pl in coherencia.planos if np.isfinite(pl.exceso_de)]
    del total_px
    extra = {
        "de_medio_cubierto": de_medio_cub,
        "de_p95_cubierto": de_p95_cub,
        "de_max_cubierto": de_max_cub,
        "fraccion_celdas_cubiertas": float(fraccion_cubierta),
        "celdas_inventadas": float((~con_dato).sum()),
        "fraccion_px_en_celda_cubierta": float(de_cub.size) / max(int(de_todo.size), 1),
        "lut_reproducible": float(diagnosis.lut_reproducible),
        "fraccion_fuera_de_dominio": float(fuera),
        "lote_planos": float(n_planos),
        "lote_planos_usados": float(len(usados)),
        "lote_discrepantes": float(len(coherencia.discrepantes)),
        "lote_sin_comparar": float(len(coherencia.sin_comparar)),
        "lote_de_discrepancia_max": float(max(de_discrepancia)) if de_discrepancia else float("nan"),
    }
    confianza = _razones_del_lote(
        confianza,
        extra,
        fraccion_cubierta,
        infos,
        nombres,
        coherencia,
        excluidos=len(usados) < n_planos,
        con_espacial=[nombres[p] for p in con_espacial],
    )
    return ReverseResult(
        cdl=cdl,
        lut=lut,
        coverage=cobertura,
        diagnosis=diagnosis,
        delta_e_mean=de_medio,
        delta_e_p95=de_p95,
        delta_e_max=de_max,
        confidence=confianza,
        notes=tuple(notas),
    )


def _razones_del_lote(
    confianza: Confidence,
    extra: dict[str, float],
    fraccion: float,
    infos: list[dict],
    nombres: list[str],
    coherencia: InformeCoherencia,
    *,
    excluidos: bool,
    con_espacial: list[str],
) -> Confidence:
    """Las razones que solo conoce el lote. La nota solo se toca por coherencia."""
    razones = list(confianza.reasons)
    score = confianza.score
    if fraccion < UMBRAL_COBERTURA_BAJA:
        razones.append(
            f"Todo el lote junto solo cubre el {fraccion * 100:.2f}% del cubo: casi todo el LUT "
            "esta extrapolado."
        )
    no_fiables = [nombres[i] for i, info in enumerate(infos) if not info["fiable"]]
    if no_fiables:
        razones.insert(
            0,
            "No puedo garantizar que original y coloreado sean el mismo encuadre en: "
            + ", ".join(no_fiables)
            + ".",
        )
    if not coherencia.coherente and not excluidos:
        aviso = coherencia.avisos[0]
        if con_espacial:
            aviso += (
                " Ojo: " + ", ".join(con_espacial) + " tienen además algo espacial (viñeta, "
                "ventana): puede que no lleven otro grado sino algo que un LUT no reproduce."
            )
        razones.insert(0, aviso)
        score = score * PENA_LOTE_INCOHERENTE
    elif not coherencia.coherente:
        razones.insert(
            0,
            f"He excluido {len(coherencia.discrepantes)} planos que no llevan el mismo grado; el "
            "LUT es el del resto.",
        )
    metricas = dict(confianza.metrics)
    metricas.update(extra)
    return Confidence(
        score=score,
        level=confidence_level(score),
        reasons=tuple(razones),
        metrics=metricas,
    )
