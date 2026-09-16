"""Acumulacion de correspondencias origen -> destino en la rejilla del cubo.

LA IDEA
-------
Cada pixel da un par: un color de entrada y el color que ese pixel tiene en el
plano ya coloreado. Millones de pares, 35.937 celdas. Hay que repartirlos.

UN SOLO REPARTO, Y ES EL TRILINEAL
-----------------------------------
Un pixel no cae "en una celda": cae **entre ocho nodos**, y contribuye a los
ocho con los mismos pesos con los que `LUT3D.apply()` los va a interpolar
despues. El reparto trilineal es el adjunto exacto de esa interpolacion, y es lo
que convierte el ajuste del LUT en un problema de minimos cuadrados bien
planteado en vez de en una media de cajones.

Lo probe de las dos formas antes de decidirlo. Repartiendo "al nodo mas
cercano", el valor que acaba en el nodo es la media de los destinos de una caja
de 1/32 de lado, y al interpolar aparece un sesgo de primer orden: sobre el
retrato del generador daba **2.3 dE2000 de media** frente a las **0.3** del
reparto trilineal con refinado. Esta en NOTAS.md.

QUE ES ENTONCES `counts`
------------------------
`CoverageMap.counts[i,j,k]` = **cuantos pixeles reales usan ese nodo al
interpolar**, o sea cuantos tienen peso trilineal > 0 en el. Es la definicion
operativa de "cuantas muestras determinan el valor de esta celda", que es la
pregunta que de verdad importa, y tiene tres propiedades que ninguna otra tiene:

* es entera y se reproduce con tres lineas de numpy, asi que un test puede
  comprobarla sin fiarse de este archivo;
* `counts == 0` es **exactamente** el conjunto de celdas que nadie ha tocado y
  que por tanto hay que inventarse. Ni una mas, ni una menos. Esa es la promesa
  del mapa de cobertura y se cumple por construccion, no por buena voluntad;
* `covered_mask()` (`counts >= min_samples`) sale gratis y significa lo que
  dice: celdas con dato suficiente para fiarse.

La alternativa era contar al nodo mas cercano. La descarte porque entonces hay
celdas con `counts == 0` que **si** estan determinadas por datos (les llega peso
de un pixel vecino), y el mapa diria "inventada" de una celda medida. Un mapa de
cobertura que miente por el lado que sea es peor que no tenerlo.

LA VARIANZA, QUE ES LA PRUEBA DEL TEST T2
-----------------------------------------
`CoverageMap.variance[i,j,k]` es la varianza **ponderada** del residuo de los
pixeles que usan ese nodo, promediada sobre los tres canales. Dos modos:

* **sin tabla** (lo que hace la funcion publica por si sola): el residuo es el
  destino en bruto, o sea la varianza mide "este color de entrada, ¿sale siempre
  igual?". Tiene un **suelo** que no es un defecto del grado sino de la rejilla:
  el vecindario de un nodo abarca 1/16 del dominio y dentro de el el grado
  cambia de verdad. Medido sobre el material del generador, ese suelo esta en
  ~1e-4 (sigma ~0.01).
* **con tabla** (lo que hace `invertir_grado` al final): el residuo es
  `destino - lo que predice el LUT ya ajustado`. Ese no tiene suelo de rejilla y
  es el numero que hay que mirar para decir "esto no es un LUT".

Si un mismo color de entrada unas veces sale de una manera y otras de otra, la
varianza sube y **ahi esta la prueba fisica de que hay algo espacial**. No es
una heuristica: es que la definicion de LUT es "misma entrada, misma salida".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.contracts import LUT3D, LUT_SIZE_DEFAULT, CoverageMap
from core.umbrales import MUESTRAS_MINIMAS_CELDA

__all__ = [
    "DOMINIO_MAX",
    "DOMINIO_MIN",
    "PESO_DE_MUESTRA",
    "VECINOS_GRAM",
    "Estadisticos",
    "acumular_correspondencias",
    "desplazamiento_de_codigo",
    "estadisticos_de_correspondencias",
    "pesos_trilineales",
]

#: Peso trilineal a partir del cual se considera que un pixel **es una muestra**
#: de esa celda. 1/8 exacto, y el numero no es arbitrario: 1/8 es el peso que un
#: pixel da a cada uno de sus ocho nodos cuando cae justo en el centro de la
#: celda, o sea el peso MINIMO que puede tener el nodo que mas le importa. De
#: ahi salen tres propiedades que hacen que todo lo demas funcione:
#:
#: * todo pixel es muestra de al menos un nodo (el que mas peso le da, que
#:   siempre tiene >= 1/8). Ningun pixel se pierde;
#: * `counts >= 1` implica `suma de pesos >= 1/8`, o sea que **nunca se divide
#:   por un peso microscopico**. Sin este corte, una celda que recibe 1e-12 de
#:   peso de un pixel lejano se "ajusta" a ese pixel, el paso de Jacobi se
#:   amplifica por 1e12 y el LUT sale con escalones. Lo medi: 52 celdas no
#:   monotonas y 120 escalones de banding, todas con peso mediano 0.0;
#: * `counts == 0` sigue significando exactamente "ningun pixel se apoya de
#:   verdad en esta celda", que es la definicion util de celda inventada.
PESO_DE_MUESTRA: float = 1.0 / 8.0

#: El dominio de los LUT que genera este modulo es SIEMPRE 0..1. No es pereza:
#: un `.cube` con DOMAIN_MIN/MAX distinto de 0..1 se lee distinto segun quien lo
#: lea, y lo que se entrega tiene que abrirse igual en Resolve, en Nuke y en el
#: visor de al lado. Lo que se sale de 0..1 se sujeta al borde (igual que hace
#: `LUT3D.apply`) y se cuenta, y el recuento sale en las notas del resultado.
DOMINIO_MIN: float = 0.0
DOMINIO_MAX: float = 1.0


def pesos_trilineales(origen: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """`(M, 3)` de colores -> `(8, M)` indices planos y `(8, M)` pesos.

    Los indices son sobre el cubo aplanado de `n**3` celdas con el orden
    `[ri, gi, bi]` de la convencion 4. Los ocho pesos de cada pixel suman 1.
    """
    px = np.asarray(origen, dtype=np.float64).reshape(-1, 3)
    t = np.clip((px - DOMINIO_MIN) / (DOMINIO_MAX - DOMINIO_MIN), 0.0, 1.0)
    pos = t * (n - 1)
    i0 = np.clip(np.floor(pos).astype(np.int64), 0, n - 2)
    f = pos - i0
    i1 = i0 + 1
    idx = np.empty((8, px.shape[0]), dtype=np.int64)
    w = np.empty((8, px.shape[0]), dtype=np.float64)
    for k in range(8):
        kr, kg, kb = (k >> 2) & 1, (k >> 1) & 1, k & 1
        ir = np.where(kr, i1[:, 0], i0[:, 0])
        ig = np.where(kg, i1[:, 1], i0[:, 1])
        ib = np.where(kb, i1[:, 2], i0[:, 2])
        idx[k] = (ir * n + ig) * n + ib
        w[k] = (
            (f[:, 0] if kr else 1.0 - f[:, 0])
            * (f[:, 1] if kg else 1.0 - f[:, 1])
            * (f[:, 2] if kb else 1.0 - f[:, 2])
        )
    return idx, w


#: Numero de vecinos de un nodo en la matriz de Gram del ajuste: el propio nodo
#: y los 26 que comparten celda con el. Dos nodos que no comparten celda no
#: aparecen nunca juntos en la interpolacion de un pixel, asi que su entrada en
#: `A^T A` es cero por construccion.
VECINOS_GRAM: int = 27

#: Codigo de la plantilla que es el propio nodo (desplazamiento (0, 0, 0)).
CODIGO_CENTRO_GRAM: int = 13


def desplazamiento_de_codigo(codigo: int) -> tuple[int, int, int]:
    """Codigo 0..26 de la plantilla de Gram -> `(dr, dg, db)` en {-1, 0, 1}."""
    return (codigo // 9 - 1, (codigo // 3) % 3 - 1, codigo % 3 - 1)


@dataclass
class Estadisticos:
    """Todo lo que el ajuste del LUT necesita saber de los pixeles, SIN los pixeles.

    POR QUE EXISTE (dia 4, modo por lote)
    -------------------------------------
    Ajustar el LUT es resolver `A t = y` por minimos cuadrados. El refinado de
    Jacobi solo usa `A^T y`, `A^T A` y la diagonal `D = suma de pesos`, y las
    tres cosas **se suman** entre planos: `A^T A` de dos planos juntos es la
    suma de las de cada uno. Asi que se pueden acumular 40 planos sin tener en
    memoria 40 planos de pesos trilineales (8 x 9 millones de float64 = 590 MB
    solo los pesos), y el ajuste de un plano y el de cuarenta son **el mismo
    codigo**.

    Campos, todos sobre el cubo aplanado de `n**3` nodos:

    * `suma_w` `(n^3,)`: suma de pesos trilineales = `D` = canal 3 del acumulado.
    * `suma_wy` `(n^3, 3)`: suma ponderada de destinos = `A^T y`.
    * `counts` `(n^3,)`: pixeles con peso >= `PESO_DE_MUESTRA` (el `counts` del
      `CoverageMap`).
    * `gram` `(n^3, 27)` o `None`: `A^T A` en plantilla de 27 vecinos
      (`desplazamiento_de_codigo`). Su columna 13 es la diagonal, `suma de w^2`.
    * `suma_wr`, `suma_wr2` `(n^3, 3)`: sumas ponderadas del residuo y de su
      cuadrado, para la varianza del `CoverageMap`.
    """

    n: int
    suma_w: np.ndarray
    suma_wy: np.ndarray
    counts: np.ndarray
    gram: np.ndarray | None
    suma_wr: np.ndarray
    suma_wr2: np.ndarray
    n_pixeles: int = 0

    @staticmethod
    def vacios(n: int, *, con_gram: bool = False) -> Estadisticos:
        celdas = int(n) ** 3
        return Estadisticos(
            n=int(n),
            suma_w=np.zeros(celdas, dtype=np.float64),
            suma_wy=np.zeros((celdas, 3), dtype=np.float64),
            counts=np.zeros(celdas, dtype=np.int64),
            gram=np.zeros((celdas, VECINOS_GRAM), dtype=np.float64) if con_gram else None,
            suma_wr=np.zeros((celdas, 3), dtype=np.float64),
            suma_wr2=np.zeros((celdas, 3), dtype=np.float64),
        )

    def __add__(self, otro: Estadisticos) -> Estadisticos:
        if self.n != otro.n:
            raise ValueError(f"no se suman estadisticos de cubos distintos: {self.n} y {otro.n}")
        gram = None
        if self.gram is not None and otro.gram is not None:
            gram = self.gram + otro.gram
        return Estadisticos(
            n=self.n,
            suma_w=self.suma_w + otro.suma_w,
            suma_wy=self.suma_wy + otro.suma_wy,
            counts=self.counts + otro.counts,
            gram=gram,
            suma_wr=self.suma_wr + otro.suma_wr,
            suma_wr2=self.suma_wr2 + otro.suma_wr2,
            n_pixeles=self.n_pixeles + otro.n_pixeles,
        )

    def __sub__(self, otro: Estadisticos) -> Estadisticos:
        """Quitar un plano del total. Lo usa quien quiera un ajuste sin un plano."""
        negado = Estadisticos(
            n=otro.n,
            suma_w=-otro.suma_w,
            suma_wy=-otro.suma_wy,
            counts=-otro.counts,
            gram=None if otro.gram is None else -otro.gram,
            suma_wr=-otro.suma_wr,
            suma_wr2=-otro.suma_wr2,
            n_pixeles=-otro.n_pixeles,
        )
        return self + negado

    def acumulado(self) -> np.ndarray:
        """`(n, n, n, 4)`: canales 0..2 suma ponderada de destinos, 3 suma de pesos."""
        n = self.n
        acc = np.empty((n**3, 4), dtype=np.float64)
        acc[:, :3] = self.suma_wy
        acc[:, 3] = self.suma_w
        return acc.reshape(n, n, n, 4)

    def cobertura(self, min_muestras: int = MUESTRAS_MINIMAS_CELDA) -> CoverageMap:
        n = self.n
        peso = np.maximum(self.suma_w, 1e-12)[:, None]
        varianza = np.maximum(self.suma_wr2 / peso - (self.suma_wr / peso) ** 2, 0.0).mean(axis=1)
        varianza[self.counts < 2] = 0.0  # con una muestra no hay varianza que medir
        return CoverageMap(
            counts=self.counts.reshape(n, n, n).astype(np.int32),
            variance=varianza.reshape(n, n, n).astype(np.float32),
            min_samples=int(min_muestras),
        )

    def diagonal_gram(self) -> np.ndarray:
        """`(n^3,)`: la diagonal de `A^T A`, o sea `suma de w^2` por nodo."""
        if self.gram is None:
            raise ValueError("estos estadisticos se calcularon sin la matriz de Gram")
        return self.gram[:, CODIGO_CENTRO_GRAM]

    def aplicar_gram(self, tabla: np.ndarray) -> np.ndarray:
        """`A^T A t` para una tabla `(n, n, n, 3)`. Devuelve `(n^3, 3)`.

        Es exactamente `sum_k bincount(idx_k, w_k * sum_l w_l t[idx_l])`, que es
        lo que hacia el bucle por pixel de `_ajustar_lut` hasta el dia 3, pero
        sobre 27 vecinos por nodo en vez de sobre todos los pixeles.
        """
        if self.gram is None:
            raise ValueError("estos estadisticos se calcularon sin la matriz de Gram")
        n = self.n
        t = np.asarray(tabla, dtype=np.float64).reshape(n, n, n, 3)
        tp = np.pad(t, ((1, 1), (1, 1), (1, 1), (0, 0)), mode="edge")
        g = self.gram.reshape(n, n, n, VECINOS_GRAM)
        out = np.zeros((n, n, n, 3), dtype=np.float64)
        for codigo in range(VECINOS_GRAM):
            dr, dg, db = desplazamiento_de_codigo(codigo)
            vecino = tp[1 + dr : n + 1 + dr, 1 + dg : n + 1 + dg, 1 + db : n + 1 + db]
            out += g[..., codigo, None] * vecino
        return out.reshape(n**3, 3)


def estadisticos_de_correspondencias(
    original: np.ndarray,
    coloreado: np.ndarray,
    tam_lut: int = LUT_SIZE_DEFAULT,
    *,
    tabla: LUT3D | np.ndarray | None = None,
    con_gram: bool = False,
) -> Estadisticos:
    """Los estadisticos suficientes de un par, sumables con los de otros pares.

    Misma entrada que `acumular_correspondencias`. `con_gram=True` calcula
    ademas `A^T A` (64 `bincount` mas por pixel: solo hace falta para ajustar).
    """
    n = int(tam_lut)
    if n < 2:
        raise ValueError(f"tam_lut tiene que ser >= 2, llego {n}")
    src = np.asarray(original, dtype=np.float64).reshape(-1, 3)
    dst = np.asarray(coloreado, dtype=np.float64).reshape(-1, 3)
    if src.shape != dst.shape:
        raise ValueError(
            f"original y coloreado no tienen el mismo numero de pixeles: "
            f"{src.shape} vs {dst.shape}"
        )

    bueno = np.isfinite(src).all(axis=1) & np.isfinite(dst).all(axis=1)
    src = src[bueno]
    dst = dst[bueno]

    est = Estadisticos.vacios(n, con_gram=con_gram)
    est.n_pixeles = int(src.shape[0])
    if src.shape[0] == 0:
        return est

    if tabla is None:
        residuo = dst
    else:
        lut = tabla if isinstance(tabla, LUT3D) else LUT3D(table=np.asarray(tabla, dtype=np.float32))
        residuo = dst - lut.apply(src)

    celdas = n**3
    idx, w = pesos_trilineales(src, n)
    for k in range(8):
        wk = w[k]
        vive = wk >= PESO_DE_MUESTRA
        est.counts += np.bincount(idx[k][vive], minlength=celdas)
        est.suma_w += np.bincount(idx[k], weights=wk, minlength=celdas)
        for c in range(3):
            est.suma_wy[:, c] += np.bincount(idx[k], weights=wk * dst[:, c], minlength=celdas)
            est.suma_wr[:, c] += np.bincount(idx[k], weights=wk * residuo[:, c], minlength=celdas)
            est.suma_wr2[:, c] += np.bincount(
                idx[k], weights=wk * residuo[:, c] ** 2, minlength=celdas
            )

    if con_gram:
        plano = np.zeros(celdas * VECINOS_GRAM, dtype=np.float64)
        for k in range(8):
            bk = ((k >> 2) & 1, (k >> 1) & 1, k & 1)
            base = idx[k] * VECINOS_GRAM
            for m in range(8):
                bm = ((m >> 2) & 1, (m >> 1) & 1, m & 1)
                codigo = (bm[0] - bk[0] + 1) * 9 + (bm[1] - bk[1] + 1) * 3 + (bm[2] - bk[2] + 1)
                plano += np.bincount(
                    base + codigo, weights=w[k] * w[m], minlength=celdas * VECINOS_GRAM
                )
        est.gram = plano.reshape(celdas, VECINOS_GRAM)
    return est


def acumular_correspondencias(
    original: np.ndarray,
    coloreado: np.ndarray,
    tam_lut: int = LUT_SIZE_DEFAULT,
    *,
    min_muestras: int = MUESTRAS_MINIMAS_CELDA,
    tabla: LUT3D | np.ndarray | None = None,
) -> tuple[np.ndarray, CoverageMap]:
    """Reparte los pares (origen -> destino) por el cubo.

    `original` y `coloreado` pueden ser `(alto, ancho, 3)` o `(M, 3)`; tienen que
    tener el mismo numero de pixeles y venir **ya alineados** (ver `alinear`).
    Los pixeles con algun valor no finito se descartan en bloque.

    Devuelve `(acumulado, cobertura)`:

    * `acumulado` es `(N, N, N, 4)` float64. **Los canales 0..2 son la suma
      PONDERADA de destinos y el canal 3 es la suma de pesos.** Van juntos a
      proposito: sin los pesos, la suma de destinos no se puede convertir en una
      media y la funcion no serviria por si sola. `rellenar_huecos` divide.
    * `cobertura` es el `CoverageMap`: `counts` = cuantos pixeles usan cada nodo
      al interpolar, `variance` = varianza ponderada del residuo en ese nodo.

    `tabla` es opcional: si se pasa un `LUT3D` (o su tabla), la varianza se mide
    contra lo que predice ese LUT en vez de contra el destino en bruto.

    Desde el dia 4 es una envoltura de `estadisticos_de_correspondencias`, con
    las mismas operaciones en el mismo orden: el resultado es identico bit a bit
    al de antes (lo comprueba `tests/test_reverse_lote.py`).
    """
    est = estadisticos_de_correspondencias(original, coloreado, tam_lut, tabla=tabla)
    return est.acumulado(), est.cobertura(min_muestras)


def fraccion_fuera_de_dominio(origen: np.ndarray) -> float:
    """Fraccion de pixeles de entrada que se salen de 0..1 y que, por tanto, el
    LUT va a sujetar al borde en vez de transformar de verdad."""
    px = np.asarray(origen, dtype=np.float64).reshape(-1, 3)
    finito = np.isfinite(px).all(axis=1)
    if not finito.any():
        return 0.0
    px = px[finito]
    fuera = ((px < DOMINIO_MIN) | (px > DOMINIO_MAX)).any(axis=1)
    return float(fuera.mean())
