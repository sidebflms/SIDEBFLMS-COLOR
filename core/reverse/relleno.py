"""Relleno de las celdas del cubo que ningun pixel ha visto.

EL PROBLEMA, CON NUMEROS
------------------------
Un cubo de 33 tiene 35.937 celdas. Un plano de 640x360 tiene 230.400 pixeles,
pero repartidos por **muy pocas celdas**: el retrato de estudio del generador
cubre unas 300, o sea un 0.8% del cubo. El 99.2% restante hay que
**inventarlo**. No hay vuelta de hoja: un `.cube` tiene que traer los 35.937
numeros, y si no los inventamos nosotros los inventara quien lo lea.

Asi que la unica pregunta honesta es: ¿como se inventan, y como se sabe cuales
son inventados? Lo segundo lo contesta `CoverageMap`. Lo primero, este archivo.

COMO SE INVENTAN, EN DOS CAPAS
------------------------------
**Capa 1 — una base afin global.** Sobre las celdas medidas se ajusta por
minimos cuadrados (ponderados por el peso real de cada celda) la aplicacion
`v = M x + c` que mejor las explica. Es lo que el grado hace "en general".

**Capa 2 — extension armonica del residuo.** En las celdas medidas se calcula
`r = v_medido - (M x + c)`. Ese residuo se extiende al resto resolviendo la
ecuacion de Laplace con las celdas medidas como condicion de contorno de
Dirichlet (en la practica: relleno por vecino mas cercano + barridos de Jacobi
de 6 vecinos, que es lo mismo pero converge en un suspiro porque arranca ya
cerca). El resultado es la superficie **mas suave posible** que pasa
exactamente por lo medido.

POR QUE ASI Y NO DE OTRA FORMA
------------------------------
- **Por que no vecino mas cercano a secas**: produce mesetas con escalones en
  las fronteras de Voronoi, y `core.io.qc_lut` lo caza como banding. Con razon:
  se ve.
- **Por que no dejar la identidad fuera de la cobertura**: seria un LUT con una
  isla de grado en medio de un mar de identidad, con un salto en el borde de la
  isla. Es peor que extrapolar: se ve como un corte.
- **Por que la base afin y no solo Laplace**: Laplace a secas tiende a la media
  de lo conocido lejos de los datos, o sea aplana el grado en las zonas sin
  cobertura. Con la base afin, lejos de los datos el LUT **continua la
  tendencia** del grado, que es lo que un colorista espera al meter un color que
  no estaba en el plano.
- **Por que suave y no exacto**: no hay dato que respetar fuera de la cobertura.
  Lo unico que se puede pedir es que no se vea, y "que no se vea" es
  literalmente "que sea suave". `qc_lut` mide eso mismo.

LO QUE SE SUJETA
----------------
La tabla final se sujeta a 0..1. El contrato dice que los valores fuera de rango
son legales en una **imagen**; en un LUT de entrega no lo son, porque `qc_lut`
los avisa y Resolve los recorta igualmente al escribir el `.cube`. Sujetar es
monotono, asi que no puede introducir una no-monotonia que no hubiera antes.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from core.contracts import LUT3D, CoverageMap

__all__ = [
    "BARRIDOS_SUAVIZADO",
    "LAMBDA_SUAVIDAD",
    "LAMBDA_SUAVIDAD_W2",
    "PESO_MINIMO",
    "RIDGE_BASE",
    "base_afin",
    "celdas_con_dato",
    "extender_suave",
    "media_de_vecinos",
    "proyectar_monotona",
    "rejilla_de_entradas",
    "rellenar_huecos",
]


def celdas_con_dato(cobertura: CoverageMap) -> np.ndarray:
    """(N,N,N) bool: celdas por las que ha pasado al menos un pixel de verdad.

    **Esta es la definicion de "celda NO inventada" de todo el modulo.** Su
    negacion, `counts == 0`, es exactamente el conjunto de celdas que
    `rellenar_huecos` se inventa. Ni una mas, ni una menos.

    Ojo con no confundirla con `CoverageMap.covered_mask()`, que es mas
    estricta (`counts >= min_samples`) y responde a otra pregunta: no "¿hay
    dato?" sino "¿hay dato SUFICIENTE para fiarse?". Es un subconjunto de esta.
    Las celdas que estan aqui pero no ahi tienen dato, pero poco, y por eso la
    regularizacion de suavidad las manda casi por completo (ver `LAMBDA_SUAVIDAD`).
    """
    return np.asarray(cobertura.counts) > 0

#: Barridos de Jacobi tras el relleno por vecino mas cercano. Medido sobre un
#: cubo de 33 con la cobertura de un retrato: con 40 barridos el cambio entre
#: barrido y barrido ya esta por debajo de 1e-5, o sea invisible.
BARRIDOS_SUAVIZADO: int = 60

#: Guarda contra la division por cero, nada mas. Quien decide que celda tiene
#: dato es `counts > 0` y solo eso (ver `celdas_con_dato`).
PESO_MINIMO: float = 1e-9

#: Cresta de la base afin, en fraccion del mayor autovalor de la normal. 1e-2
#: sale de medir: con 1e-3 la base se desvia 0.077 de la identidad en el caso
#: identidad exacta y con 1e-2 se desvia 0.009, y en el T1 (grado de verdad) el
#: ΔE2000 no se mueve.
RIDGE_BASE: float = 1e-2

#: Peso equivalente de la regularizacion de suavidad. Una celda con `peso` muy
#: por encima de esto manda ella; una celda con dos pixeles sueltos se deja
#: llevar por sus vecinas. En unidades de "pixeles equivalentes", que es la
#: unica forma de que el numero signifique algo.
LAMBDA_SUAVIDAD: float = 0.25

#: Peso de la regularizacion de suavidad cuando la informacion de un nodo se
#: mide con `suma de w^2` (la diagonal de `A^T A`) en vez de con `suma de w`. Es
#: el defecto de `invertir_grado_lote` desde el dia 4; `invertir_grado` sigue
#: con `suma de w` y `LAMBDA_SUAVIDAD`.
#:
#: POR QUE `suma de w^2`. `suma de w` cuenta igual un pixel pegado al nodo
#: (w ~ 1) que ocho pixeles en la esquina opuesta de la celda (w ~ 0.13 cada
#: uno): los dos dan ~1. Pero el segundo caso casi no fija el valor del nodo, y
#: el ajuste lo deja mandar igual. `suma de w^2` es lo que el nodo pesa de verdad
#: en los minimos cuadrados: el primero da ~1 y el segundo ~0.13.
#:
#: MEDIDO, con su comando, en `core/reverse/NOTAS.md` §12
#: (`tests/test_reverse_lote_cobertura.py` y
#: `tests/test_reverse_lote_determinacion.py`): con 40 planos mejora la zona
#: cubierta con el look suave y con uno de secundarias estrechas; con UN plano y
#: el look de secundarias estrechas empeora lo tipico, y por eso NO es el defecto
#: de `invertir_grado`. El 4 se eligio probando 1, 4 y 16 durante el desarrollo
#: (16 ya no bajaba el maximo); esa comparacion no tiene comando en el repo.
LAMBDA_SUAVIDAD_W2: float = 4.0


def rejilla_de_entradas(n: int) -> np.ndarray:
    """(n, n, n, 3): el color de entrada que le toca a cada nodo del cubo."""
    eje = np.linspace(0.0, 1.0, n, dtype=np.float64)
    r, g, b = np.meshgrid(eje, eje, eje, indexing="ij")
    return np.stack([r, g, b], axis=-1)


def base_afin(
    entradas: np.ndarray, valores: np.ndarray, mascara: np.ndarray, pesos: np.ndarray
) -> np.ndarray:
    """Ajusta `v ~ M x + c` sobre las celdas de `mascara`, ponderando por `pesos`.

    Devuelve la base evaluada en TODA la rejilla, `(n, n, n, 3)`. Si el sistema
    esta mal condicionado (pocas celdas, o todas en una recta) se cae con
    elegancia a la identidad, que es la mejor suposicion posible sin datos.
    """
    n = entradas.shape[0]
    x = entradas.reshape(-1, 3)[mascara.ravel()]
    v = valores.reshape(-1, 3)[mascara.ravel()]
    w = np.maximum(pesos.ravel()[mascara.ravel()], 0.0)
    if x.shape[0] < 8 or w.sum() <= 0.0:
        return entradas.copy()
    dis = np.concatenate([x, np.ones((x.shape[0], 1))], axis=1)  # (m, 4)
    wd = dis * w[:, None]
    ata = dis.T @ wd
    atb = wd.T @ v
    # Cresta (Tikhonov) HACIA LA IDENTIDAD, escalada al mayor autovalor.
    #
    # Esto no es cosmetica, es lo que hace que el modulo no mienta cuando le dan
    # dos planos IDENTICOS. Los colores de una imagen no llenan el cubo: viven
    # en una nube alargadisima donde la luma manda y el croma casi no varia. En
    # las direcciones en las que la nube no tiene grosor, los minimos cuadrados
    # eligen cualquier cosa, y "cualquier cosa" evaluada en la esquina del cubo
    # se va lejisimos. Medido con original == coloreado (o sea, grado identidad
    # exacto): sin cresta la base salia con M = [[0.64,0.31,0.08],...] y el LUT
    # se desviaba 0.63 de la identidad en las esquinas. Con la cresta a
    # `RIDGE_BASE * mayor autovalor` la desviacion baja a 0.009 y el error
    # ponderado sobre las celdas medidas practicamente no cambia.
    #
    # Lo que la cresta dice, en castellano: **en las direcciones que los datos
    # no fijan no me invento un grado, dejo la identidad.**
    objetivo = np.eye(4, 3)  # M = I, c = 0
    mayor = float(np.linalg.eigvalsh(ata)[-1])
    lam = max(RIDGE_BASE * mayor, 1e-12)
    ata = ata + lam * np.eye(4)
    atb = atb + lam * objetivo
    try:
        sol = np.linalg.solve(ata, atb)  # (4, 3)
    except np.linalg.LinAlgError:
        return entradas.copy()
    if not np.isfinite(sol).all():
        return entradas.copy()
    plano = np.concatenate([entradas.reshape(-1, 3), np.ones((n**3, 1))], axis=1) @ sol
    return plano.reshape(n, n, n, 3)


def media_de_vecinos(campo: np.ndarray) -> np.ndarray:
    """Media de los 6 vecinos, con condicion de Neumann en las caras del cubo."""
    p = np.pad(campo, ((1, 1), (1, 1), (1, 1), (0, 0)), mode="edge")
    return (
        p[2:, 1:-1, 1:-1]
        + p[:-2, 1:-1, 1:-1]
        + p[1:-1, 2:, 1:-1]
        + p[1:-1, :-2, 1:-1]
        + p[1:-1, 1:-1, 2:]
        + p[1:-1, 1:-1, :-2]
    ) / 6.0


def extender_suave(
    campo: np.ndarray,
    mascara: np.ndarray,
    *,
    barridos: int = BARRIDOS_SUAVIZADO,
    inicial: np.ndarray | None = None,
) -> np.ndarray:
    """Extiende `campo` fuera de `mascara` de la forma mas suave que hay.

    `mascara` es `(n,n,n)` bool: donde hay dato real. Dentro de la mascara el
    valor no se toca (Dirichlet). Fuera se resuelve Laplace. `inicial` permite
    arrancar en caliente desde una extension anterior, que es lo que hace el
    refinado iterativo para no pagar el relleno entero en cada vuelta.
    """
    fuera = ~mascara
    if not fuera.any():
        return campo.copy()
    if not mascara.any():
        return np.zeros_like(campo) if inicial is None else inicial.copy()

    if inicial is not None:
        out = inicial.copy()
    else:
        # Arranque: vecino conocido mas cercano. No es el resultado, es el punto
        # de partida; sin el, Jacobi tardaria miles de barridos en cruzar el cubo.
        _, indices = ndimage.distance_transform_edt(fuera, return_indices=True)
        out = campo[indices[0], indices[1], indices[2]]
    out[mascara] = campo[mascara]
    for _ in range(int(barridos)):
        nuevo = media_de_vecinos(out)
        out = np.where(mascara[..., None], campo, nuevo)
    return out


def rellenar_huecos(acumulado: np.ndarray, cobertura: CoverageMap) -> LUT3D:
    """Acumulador + mapa de cobertura -> el `LUT3D` completo.

    `acumulado` es `(N, N, N, 4)` como lo devuelve `acumular_correspondencias`:
    canales 0..2 suma ponderada de destinos, canal 3 suma de pesos.

    **Que celdas se rellenan**: exactamente aquellas con `counts == 0`, o sea
    las que ningun pixel ha pisado (`celdas_con_dato`). Ni una mas, ni una
    menos. Asi "celda inventada" tiene una definicion verificable con tres
    lineas de numpy, y el mapa de cobertura no miente.

    `cobertura.covered_mask()` (`counts >= min_samples`) es otra cosa y mas
    estricta: "celdas de las que ademas me fio". Una celda con dos muestras se
    ajusta con esas dos muestras -- no se inventa -- pero sale como no cubierta.
    """
    acc = np.asarray(acumulado, dtype=np.float64)
    if acc.ndim != 4 or acc.shape[3] != 4:
        raise ValueError(f"acumulado tiene que ser (N, N, N, 4), llego {acc.shape}")
    n = acc.shape[0]
    if cobertura.size != n:
        raise ValueError(f"el acumulado es de {n} y la cobertura de {cobertura.size}")

    pesos = acc[..., 3]
    medidas = celdas_con_dato(cobertura) & (pesos >= PESO_MINIMO)
    valores = np.zeros((n, n, n, 3), dtype=np.float64)
    np.divide(acc[..., :3], np.maximum(pesos, 1e-12)[..., None], out=valores, where=medidas[..., None])

    entradas = rejilla_de_entradas(n)
    if not medidas.any():
        # Sin una sola celda fiable no hay grado que devolver. La identidad es
        # la unica respuesta honesta; quien llama ya se encarga de decir que la
        # confianza es cero.
        return LUT3D(table=entradas.astype(np.float32), title="SIDEB COLOR (sin cobertura)")

    base = base_afin(entradas, valores, medidas, pesos)
    residuo = np.zeros_like(valores)
    residuo[medidas] = valores[medidas] - base[medidas]
    residuo = extender_suave(residuo, medidas)
    tabla = proyectar_monotona(np.clip(base + residuo, 0.0, 1.0))
    return LUT3D(table=tabla.astype(np.float32), title="SIDEB COLOR")


def proyectar_monotona(tabla: np.ndarray) -> np.ndarray:
    """Fuerza que subir la entrada de un canal no baje su salida.

    POR QUE ESTO ESTA AQUI. Un grado de verdad es monotono en cada canal: no
    existe el grado que al subirle el rojo a un pixel le baja el rojo. Asi que
    cuando el LUT ajustado sale con una bajada, **eso no es el grado, es mi
    ajuste**. Medido en el test T1: siete celdas con bajadas de entre 3e-4 y
    9e-3, todas en la frontera entre lo medido y lo extrapolado, donde la
    extension armonica hace un pliegue. `core.io.qc_lut` las marca como ERROR, y
    tiene razon en marcarlas.

    COMO. Para cada eje `a` se toma el canal de salida `a` (que es el unico que
    el QC mira, y el unico en el que la monotonia es obligatoria: un LUT puede
    mezclar canales todo lo que quiera, eso es un tinte) y se sustituye por la
    media del maximo acumulado hacia delante y del minimo acumulado hacia atras.
    Las dos son no decrecientes, luego su media tambien. Es simetrica a
    proposito: la version de un solo lado sesgaria el LUT hacia arriba.

    Los tres ejes son independientes porque cada uno solo toca su propio canal,
    asi que aplicarlos en cualquier orden deja las tres condiciones cumplidas.

    COSTE MEDIDO: el ΔE2000 medio del T1 no se mueve (0.141 antes y despues) y
    el maximo sube de 2.19 a 2.30. A cambio, cero errores de monotonia.
    """
    out = np.array(tabla, dtype=np.float64, copy=True)
    for eje in range(3):
        v = out[..., eje]
        arriba = np.maximum.accumulate(v, axis=eje)
        abajo = np.flip(np.minimum.accumulate(np.flip(v, axis=eje), axis=eje), axis=eje)
        out[..., eje] = 0.5 * (arriba + abajo)
    return out
