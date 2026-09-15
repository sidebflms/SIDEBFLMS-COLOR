"""Emparejamiento completo: de dos nubes de pixeles a un `MatchResult`.

EL CAMINO, DE PRINCIPIO A FIN
-----------------------------
1. Se limpian las dos listas (filas no finitas fuera) y se submuestrean con
   semilla fija, para que dos ejecuciones den el mismo resultado.
2. `transporte_mkl` da la aplicacion afin ideal `T(x) = A x + b` que lleva la
   distribucion del origen a la de la referencia. **Esta es la verdad contra la
   que se mide todo lo demas.**
3. Se construye el destino de cada pixel del origen como `T(x)`. Esto es lo que
   permite que las dos listas midan distinto: no se empareja pixel con pixel, se
   empareja el origen consigo mismo transportado.
4. `ajustar_cdl` busca el CDL que mas se parece a `T` sobre esos pixeles. Un CDL
   no puede hacer un giro de color (su matriz es diagonal mas saturacion), asi
   que casi nunca lo iguala exactamente: lo que sobra es el residuo.
5. Si se pide `con_lut`, se construye un LUT 3D del **residuo**, pensado para ir
   DESPUES del CDL (nodo 3 detras del nodo 2). Ver `_lut_de_residuo`.

QUE SIGNIFICAN `delta_e_before` Y `delta_e_after`
-------------------------------------------------
Con dos listas de pixeles que no se corresponden una a una, "el ΔE entre el
plano y la referencia" no esta definido: no hay parejas que restar. Lo que si
esta definido, y es lo que mide la app:

    delta_e_before = ΔE2000 medio entre el origen y su transporte ideal T(origen)
    delta_e_after  = ΔE2000 medio entre lo corregido y ese mismo T(origen)

O sea: **"cuanto habia que mover el plano"** y **"cuanto le falta todavia"**.
Si el origen y la referencia ya son la misma distribucion, `T` es la identidad y
los dos salen ~0, que es lo que tiene que pasar.

Cuando los dos planos SI se corresponden pixel a pixel (el caso de las cuatro
camaras: la misma escena grabada de cuatro maneras), lo que interesa es el ΔE
directo entre imagenes, y eso lo mide `core.matching.camaras`, no esto.

POLITICA DE NaN: AQUI ME DESVIO DE `core.color`, Y LO DIGO
-----------------------------------------------------------
`core.color` propaga los NaN a proposito, para que un plano roto no de un numero
plausible. Aqui **no** se puede: un `CDL` con un NaN dentro no existe (el
constructor lanza), asi que propagar significaria no poder devolver nada.

Lo que hago: las filas no finitas se **descartan** del ajuste, y a cambio
(a) se cuenta cuantas eran y se pasa como `fraccion_no_finita` a la confianza,
que la baja, y (b) sale una nota en `MatchResult.notes` diciendo el porcentaje.
O sea: no se barre bajo la alfombra, se cuenta. Si NO queda ni un pixel finito,
entonces si se lanza `ValueError`.
"""

from __future__ import annotations

import numpy as np

from core.color import delta_e2000_mean
from core.contracts import (
    CDL,
    LUT3D,
    LUT_SIZE_DEFAULT,
    WORKING_SPACE,
    ClipAnalysis,
    Confidence,
    MatchResult,
)
from core.matching.cdl_fit import SEMILLA, ajustar_cdl, aplicar_cdl_inverso, submuestrea
from core.matching.confianza import puntuar_confianza
from core.matching.contenido import desajuste_de_contenido
from core.matching.mkl import (
    aplicar_mkl,
    ganancias,
    media_y_covarianza,
    pixeles_finitos,
    transporte_mkl_de_estadistica,
)

__all__ = [
    "MAX_PIXELES_EMPAREJAR",
    "coeficiente_bhattacharyya",
    "emparejar",
    "emparejar_analisis",
    "fraccion_extrapolada",
    "solape_de_distribuciones",
]

#: Tope de pixeles que entran al emparejamiento. 60.000 son ya cuatro veces mas
#: de los que necesita una gaussiana de tres dimensiones y mantiene el ΔE2000
#: (que es caro) en decimas de segundo.
MAX_PIXELES_EMPAREJAR: int = 60000


def coeficiente_bhattacharyya(
    mu_a: np.ndarray, cov_a: np.ndarray, mu_b: np.ndarray, cov_b: np.ndarray
) -> float:
    """Cuanto se pisan dos gaussianas, en 0..1. 1 = identicas, 0 = ajenas.

    **No es la que puntua la confianza**: para eso esta
    `solape_de_distribuciones`, y el porque esta escrito ahi. Esta se queda
    porque es la medida clasica y a alguien le va a hacer falta para ordenar
    candidatos a referencia partiendo solo de un `ColorStats`.

    Es `exp(-D_B)` con la distancia de Bhattacharyya clasica. Se calcula con
    `eigh` y con un piso en los autovalores por lo mismo de siempre: la
    covarianza puede ser singular y `det` de una singular es 0, que en un
    logaritmo es -inf.
    """
    mu_a = np.asarray(mu_a, dtype=np.float64).reshape(3)
    mu_b = np.asarray(mu_b, dtype=np.float64).reshape(3)
    ca = np.asarray(cov_a, dtype=np.float64).reshape(3, 3)
    cb = np.asarray(cov_b, dtype=np.float64).reshape(3, 3)
    media = 0.5 * (ca + cb)
    media = 0.5 * (media + media.T)

    lam_m, vec_m = np.linalg.eigh(media)
    escala = float(max(lam_m.max(initial=0.0), 1e-30))
    piso = 1e-12 * escala
    lam_m = np.maximum(lam_m, piso)
    inv = (vec_m / lam_m) @ vec_m.T

    d = mu_a - mu_b
    termino_media = 0.125 * float(d @ inv @ d)

    def _logdet(m: np.ndarray) -> float:
        lam = np.maximum(np.linalg.eigvalsh(0.5 * (m + m.T)), piso)
        return float(np.sum(np.log(lam)))

    termino_cov = 0.5 * (_logdet(media) - 0.5 * (_logdet(ca) + _logdet(cb)))
    dist = termino_media + max(termino_cov, 0.0)
    return float(np.exp(-min(dist, 700.0)))


def solape_de_distribuciones(a_px: np.ndarray, b_px: np.ndarray, *, bins: int = 8) -> float:
    """Cuanto se pisan DE VERDAD dos nubes de pixeles. 0..1, 1 = identicas.

    Coeficiente de Bhattacharyya entre los dos histogramas 3D reales, no entre
    dos gaussianas ajustadas.

    POR QUE SOBRE LOS HISTOGRAMAS Y NO SOBRE LAS GAUSSIANAS, Y POR QUE DESPUES
    DEL TRANSPORTE: el solape en crudo entre el plano y la referencia **no mide
    nada util en esta app**. Lo medi: un plano con un grado fuerte encima da
    solape 0.00 contra el mismo plano sin grado, y ese es justo el caso para el
    que existe el programa. Lo que si dice algo es el solape del plano **ya
    transportado** contra la referencia: el transporte MKL iguala la media y la
    covarianza por construccion, asi que si despues de eso los dos histogramas
    siguen sin pisarse, es que a estas dos nubes no les basta una aplicacion afin
    y la correccion se queda corta por mucho que las medias cuadren.

    El rango de los bins sale de los percentiles 0.5-99.5 de las dos nubes
    juntas (no del min/max, para que un unico especular no meta todo lo demas en
    una sola celda), y se suaviza con media cuenta por celda.
    """
    a = np.asarray(a_px, dtype=np.float64).reshape(-1, 3)
    b = np.asarray(b_px, dtype=np.float64).reshape(-1, 3)
    a = a[np.isfinite(a).all(axis=1)]
    b = b[np.isfinite(b).all(axis=1)]
    if a.shape[0] == 0 or b.shape[0] == 0:
        return 0.0
    juntas = np.concatenate([a, b], axis=0)
    bajo = np.percentile(juntas, 0.5, axis=0)
    alto = np.percentile(juntas, 99.5, axis=0)
    ancho = alto - bajo
    degenerado = ancho <= 1e-12
    alto = np.where(degenerado, bajo + 1.0, alto)
    rango = [(float(bajo[c]), float(alto[c])) for c in range(3)]

    def _hist(px: np.ndarray) -> np.ndarray:
        h, _ = np.histogramdd(np.clip(px, bajo, alto), bins=bins, range=rango)
        h = h.reshape(-1) + 0.5
        return h / h.sum()

    return float(np.clip(np.sum(np.sqrt(_hist(a) * _hist(b))), 0.0, 1.0))


def fraccion_extrapolada(origen_px: np.ndarray, referencia_px: np.ndarray) -> float:
    """Que parte de la referencia cae fuera de la caja de color del origen.

    Se usa la caja min/max literal del origen, no percentiles: si el origen y la
    referencia son el mismo plano tiene que salir exactamente 0, y con
    percentiles saldrian las colas.
    """
    o = np.asarray(origen_px, dtype=np.float64).reshape(-1, 3)
    r = np.asarray(referencia_px, dtype=np.float64).reshape(-1, 3)
    if o.shape[0] == 0 or r.shape[0] == 0:
        return 0.0
    bajo, alto = o.min(axis=0), o.max(axis=0)
    fuera = (r < bajo).any(axis=1) | (r > alto).any(axis=1)
    return float(fuera.mean())


def _lut_de_residuo(cdl: CDL, a: np.ndarray, b: np.ndarray, tam: int) -> LUT3D:
    """LUT 3D que corrige lo que al CDL le falta. Va DESPUES del CDL.

    Se construye al reves: para cada punto `y` de la rejilla (que es un valor ya
    salido del CDL) se busca de que entrada venia, `x = cdl^-1(y)`, y se escribe
    en la celda el transporte ideal de esa entrada, `T(x) = A x + b`. Asi
    `LUT(CDL(x)) = T(x)` alli donde el CDL es invertible.

    Donde el CDL recorto (el `max(x, 0)` del estandar) la inversa no existe y lo
    que se escribe es el borde. Es la misma decision que toma `LUT3D.apply`
    fuera de dominio, asi que al menos es coherente.
    """
    eje = np.linspace(0.0, 1.0, tam, dtype=np.float64)
    rr, gg, bb = np.meshgrid(eje, eje, eje, indexing="ij")
    rejilla = np.stack([rr, gg, bb], axis=-1).reshape(-1, 3)
    entrada = aplicar_cdl_inverso(cdl, rejilla)
    salida = aplicar_mkl(entrada, a, b)
    tabla = np.asarray(salida, dtype=np.float32).reshape(tam, tam, tam, 3)
    return LUT3D(table=tabla, title="SIDEB COLOR - residuo")


def _nucleo(
    origen_px: np.ndarray,
    referencia_px: np.ndarray,
    *,
    con_lut: bool,
    tam_lut: int,
    transporte: tuple[np.ndarray, np.ndarray] | None = None,
    desajuste: tuple[bool, float, tuple[str, ...]] | None = None,
    huellas: tuple[np.ndarray | None, np.ndarray | None] | None = None,
    n_muestras: int | None = None,
    notas_extra: tuple[str, ...] = (),
) -> MatchResult:
    o_bruto = np.asarray(origen_px, dtype=np.float64)
    r_bruto = np.asarray(referencia_px, dtype=np.float64)
    o, frac_o = pixeles_finitos(o_bruto, "emparejar(origen)")
    r, frac_r = pixeles_finitos(r_bruto, "emparejar(referencia)")
    if o.shape[0] == 0:
        raise ValueError("emparejar: el plano de origen no tiene ni un pixel valido")
    if r.shape[0] == 0:
        raise ValueError("emparejar: la referencia no tiene ni un pixel valido")

    notas: list[str] = list(notas_extra)
    frac_no_finita = max(frac_o, frac_r)
    if frac_no_finita > 0:
        notas.append(
            f"Se han descartado pixeles no finitos (NaN o infinito): {frac_o:.2%} del "
            f"plano y {frac_r:.2%} de la referencia."
        )

    (o,) = submuestrea(o, maximo=MAX_PIXELES_EMPAREJAR, semilla=SEMILLA)
    # MISMA semilla que el origen a proposito: si las dos listas son la misma,
    # se quedan con los mismos indices y emparejar un plano consigo mismo da la
    # identidad EXACTA en vez de "casi".
    (r,) = submuestrea(r, maximo=MAX_PIXELES_EMPAREJAR, semilla=SEMILLA)

    mu_o, cov_o = media_y_covarianza(o)
    mu_r, cov_r = media_y_covarianza(r)
    a, b = transporte if transporte is not None else transporte_mkl_de_estadistica(
        mu_o, cov_o, mu_r, cov_r
    )

    objetivo = aplicar_mkl(o, a, b)
    cdl = ajustar_cdl(o, objetivo)
    corregido = cdl.apply(o)

    lut: LUT3D | None = None
    if con_lut:
        lut = _lut_de_residuo(cdl, a, b, int(tam_lut))
        corregido = lut.apply(corregido)

    de_antes = delta_e2000_mean(o, objetivo, WORKING_SPACE)
    de_despues = delta_e2000_mean(corregido, objetivo, WORKING_SPACE)

    if desajuste is None:
        desajuste = desajuste_de_contenido(o, r, huellas=huellas)
    hay_desajuste, distancia, razones_contenido = desajuste

    lam_a = ganancias(a)
    # OJO con `min(initial=...)`: en numpy `initial` es el elemento neutro de la
    # reduccion, o sea que `min(initial=0.0)` devuelve SIEMPRE 0. Aqui se hace a
    # mano, que ademas deja claro el caso degenerado.
    lam_cov = np.clip(np.linalg.eigvalsh(0.5 * (cov_o + cov_o.T)), 0.0, None)
    mayor = float(np.max(lam_cov))
    menor = float(np.min(lam_cov))
    condicion = mayor / menor if menor > 0 else float("inf")

    confianza: Confidence = puntuar_confianza(
        n_muestras=int(n_muestras if n_muestras is not None else min(o.shape[0], r.shape[0])),
        solape=solape_de_distribuciones(objetivo, r),
        condicion=condicion,
        residuo_de=de_despues,
        extrapolacion=fraccion_extrapolada(o, r),
        ganancia=float(max(np.max(lam_a), 1.0)),
        fraccion_no_finita=frac_no_finita,
        desajuste=hay_desajuste,
        distancia_contenido=distancia,
    )
    notas.extend(razones_contenido)

    return MatchResult(
        cdl=cdl,
        lut=lut,
        confidence=confianza,
        delta_e_before=float(de_antes),
        delta_e_after=float(de_despues),
        content_mismatch=bool(hay_desajuste),
        notes=tuple(notas),
    )


def emparejar(
    origen_px: np.ndarray,
    referencia_px: np.ndarray,
    *,
    con_lut: bool = False,
    tam_lut: int = LUT_SIZE_DEFAULT,
    huellas: tuple[np.ndarray | None, np.ndarray | None] | None = None,
) -> MatchResult:
    """Lleva la distribucion de `origen_px` a la de `referencia_px`.

    Las dos listas son `(N, 3)` o `(alto, ancho, 3)` en `WORKING_SPACE` y **no
    tienen por que medir lo mismo**. Con `con_lut=True` se devuelve ademas un
    LUT 3D del residuo, pensado para aplicarse DESPUES del CDL.

    `huellas=(origen, referencia)` son las dos huellas de contenido de
    `ClipAnalysis.fingerprint`, y **conviene pasarlas**: sin ellas, el detector
    de desajuste de contenido se queda en los rasgos de pixeles, que con
    material muy gradado da falsos positivos (esta medido en
    `core/matching/NOTAS.md` §4). Si tienes los dos `ClipAnalysis` completos, usa
    `emparejar_analisis`, que ya las pasa.
    """
    return _nucleo(
        origen_px, referencia_px, con_lut=con_lut, tam_lut=tam_lut, huellas=huellas
    )


def _muestra_gaussiana(mu: np.ndarray, cov: np.ndarray, n: int, semilla: int) -> np.ndarray:
    """Nube sintetica con la media y la covarianza que le digan.

    Se usa solo cuando un `ClipAnalysis` no trae pixeles. La covarianza puede no
    ser definida positiva (redondeo), asi que se muestrea por `eigh` con los
    autovalores sujetos a cero, no con `multivariate_normal`, que avisa o falla.
    """
    lam, vec = np.linalg.eigh(0.5 * (cov + cov.T))
    lam = np.clip(lam, 0.0, None)
    z = np.random.default_rng(semilla).standard_normal((n, 3))
    return (z * np.sqrt(lam)) @ vec.T + np.asarray(mu, dtype=np.float64).reshape(3)


def emparejar_analisis(
    origen: ClipAnalysis, referencia: ClipAnalysis, *, con_lut: bool = False
) -> MatchResult:
    """Lo mismo que `emparejar` pero a partir de dos `ClipAnalysis`.

    Usa `.pixels` si los dos los traen. Si falta alguno, se apoya en `.stats`
    (media y covarianza, que es exactamente lo que el transporte MKL necesita) y
    **sintetiza una nube gaussiana** para poder ajustar el CDL. El CDL que sale
    entonces es el del modelo gaussiano, no el de los pixeles reales del plano:
    queda dicho en `notes` y la confianza se calcula con el `n_samples` real del
    `ColorStats`, no con el numero de puntos inventados.

    **Es el camino bueno para el desajuste de contenido**: los dos `ClipAnalysis`
    traen `fingerprint`, y la huella es el instrumento que de verdad separa "otra
    escena" de "el mismo plano con un grado encima" (ver `contenido.py`). Con
    `emparejar` y listas de pixeles sueltas, sin pasar `huellas=`, se cae a los
    rasgos de pixeles, que es una via mas debil.

    No importa `core.analysis`: solo lee campos del contrato.
    """
    o_px = getattr(origen, "pixels", None)
    r_px = getattr(referencia, "pixels", None)
    notas: list[str] = []

    if o_px is not None and r_px is not None and np.size(o_px) and np.size(r_px):
        o = np.asarray(o_px, dtype=np.float64).reshape(-1, 3)
        r = np.asarray(r_px, dtype=np.float64).reshape(-1, 3)
        transporte = None
    else:
        notas.append(
            "Uno de los dos planos no traia pixeles guardados: el CDL se ha "
            "ajustado sobre una nube gaussiana con la media y la covarianza de "
            "su ColorStats, no sobre los pixeles de verdad."
        )
        n = 20000
        o = (
            np.asarray(o_px, dtype=np.float64).reshape(-1, 3)
            if o_px is not None and np.size(o_px)
            else _muestra_gaussiana(origen.stats.mean, origen.stats.cov, n, SEMILLA)
        )
        r = (
            np.asarray(r_px, dtype=np.float64).reshape(-1, 3)
            if r_px is not None and np.size(r_px)
            else _muestra_gaussiana(referencia.stats.mean, referencia.stats.cov, n, SEMILLA + 7)
        )
        # El transporte sale de la estadistica de verdad, no de la nube inventada.
        transporte = transporte_mkl_de_estadistica(
            origen.stats.mean, origen.stats.cov, referencia.stats.mean, referencia.stats.cov
        )

    n_muestras = min(
        int(getattr(origen.stats, "n_samples", 0) or o.shape[0]),
        int(getattr(referencia.stats, "n_samples", 0) or r.shape[0]),
    )
    return _nucleo(
        o,
        r,
        con_lut=con_lut,
        tam_lut=LUT_SIZE_DEFAULT,
        transporte=transporte,
        desajuste=desajuste_de_contenido(origen, referencia),
        n_muestras=n_muestras,
        notas_extra=tuple(notas),
    )
