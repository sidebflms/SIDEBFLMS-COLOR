"""Transporte lineal de Monge-Kantorovich (MKL), solucion cerrada.

QUE RESUELVE
------------
Dadas dos nubes de pixeles (origen y destino) modeladas como gaussianas
multivariantes, existe UNA sola aplicacion afin `y = A x + b` que lleva la
primera a la segunda con el menor coste de transporte cuadratico, y tiene
solucion cerrada (Pitie y Kokaram, *The linear Monge-Kantorovitch linear
colour mapping for example-based colour transfer*, 2007):

    A = Sx^(-1/2) ( Sx^(1/2) Sy Sx^(1/2) )^(1/2) Sx^(-1/2)
    b = mu_y - A mu_x

`A` sale **simetrica y semidefinida positiva**, y cumple `A Sx A = Sy`. Eso es
lo que hace que el transporte de ida y el de vuelta sean uno el inverso del
otro, y que transportar una distribucion a si misma de la identidad exacta.

POR QUE `eigh` Y NO `scipy.linalg.sqrtm`
---------------------------------------
`sqrtm` es para matrices generales: pasa por Schur, devuelve `complex128` en
cuanto hay un autovalor negativo de redondeo y no da ninguna garantia de
simetria. Aqui las tres matrices que hay que enraizar son simetricas por
construccion, asi que `numpy.linalg.eigh` es a la vez mas rapido, exacto en la
simetria y, sobre todo, **me deja ver y sujetar los autovalores negativos**
antes de la raiz. Un autovalor de -1e-19 (que sale continuamente: es ruido de
redondeo de una covarianza) elevado a 1/2 mete un complejo en una tuberia de
float y a partir de ahi todo es NaN.

COVARIANZA SINGULAR: COMO LA REGULARIZO (esto importa)
------------------------------------------------------
`Sx` es singular mas a menudo de lo que parece: una imagen de un solo color, un
plano en blanco y negro (R=G=B, rango 1), un canal reventado, un solo pixel.
Entonces `Sx^(-1/2)` no existe.

Lo facil seria sumar `eps*I` y seguir. No lo hago, porque el resultado es peor
que el problema: en una direccion donde el origen **no tiene ninguna varianza**,
la formula pide una ganancia `sqrt(lambda_y / eps)`, o sea que cuanto mas
pequeno pongas el epsilon mas amplificas una direccion de la que no sabes
absolutamente nada. Con `eps = 1e-10` y una varianza de destino normal eso son
ganancias de 1e5: ruido de grano convertido en manchas de color.

Lo que hago: descompongo `Sx = U diag(l) U^T`, sujeto `l` a >= 0, y llamo
**degenerada** a toda direccion con `l_i <= TOL_RANGO * max(l)`. En esas
direcciones sustituyo `l_i` por la varianza que el DESTINO tiene en esa misma
direccion (`u_i^T Sy u_i`). El efecto es que la ganancia en una direccion sin
informacion sale **~1**: no se toca lo que no se puede medir, en vez de
inventarselo. Si tampoco el destino tiene varianza ahi, cae a un piso absoluto
proporcional a la escala del problema (`_piso_absoluto`), que solo existe para
que no haya una division por cero.

Ademas, como red de seguridad ultima, los autovalores de `A` (que son
literalmente las ganancias del estirado, porque `A` es simetrica) se sujetan a
`GANANCIA_MAX`. Con las escenas reales nunca salta; esta para que un caso
patologico de un cliente a las dos de la manana de un numero feo en vez de un
infinito.

PRECISION Y NaN
---------------
Las matrices se calculan siempre en float64. `aplicar_mkl` respeta la precision
de la imagen que le entra (float32 -> float32), igual que hace `core.color`.
Un NaN de entrada sale NaN, porque es un producto de matrices y se propaga solo.
`transporte_mkl`, en cambio, **descarta** las filas no finitas antes de estimar
media y covarianza: un pixel roto no es una observacion de la distribucion, y si
no se descartara la covarianza entera saldria NaN y no habria transporte ninguno
que devolver. Quien quiera enterarse de cuantos habia tiene `fraccion_no_finita`.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "GANANCIA_MAX",
    "TOL_RANGO",
    "aplicar_mkl",
    "covarianza_regularizada",
    "ganancias",
    "media_y_covarianza",
    "pixeles_finitos",
    "sanea_pixeles",
    "transporte_mkl",
    "transporte_mkl_de_estadistica",
]

#: Una direccion propia de Sx con autovalor por debajo de esto (relativo al
#: mayor) se considera sin informacion. 1e-8 es ~la mitad de los digitos de un
#: float64: por debajo de ahi el autovalor es ruido de la propia estimacion.
TOL_RANGO: float = 1e-8

#: Tope de estirado en cualquier direccion. Red de seguridad, no parte del
#: metodo: con material real no se toca nunca.
GANANCIA_MAX: float = 100.0


def sanea_pixeles(px: np.ndarray, quien: str = "pixeles") -> np.ndarray:
    """(..., 3) -> (N, 3) float64. No filtra nada, solo valida la forma."""
    arr = np.asarray(px, dtype=np.float64)
    if arr.ndim == 0 or arr.shape[-1] != 3:
        raise ValueError(f"{quien}: esperaba (..., 3), llego {np.shape(px)}")
    return arr.reshape(-1, 3)


def pixeles_finitos(px: np.ndarray, quien: str = "pixeles") -> tuple[np.ndarray, float]:
    """(N, 3) sin filas no finitas, y la fraccion que se ha tirado."""
    arr = sanea_pixeles(px, quien)
    if arr.shape[0] == 0:
        return arr, 0.0
    bueno = np.isfinite(arr).all(axis=1)
    fraccion = float(1.0 - bueno.mean())
    return arr[bueno], fraccion


def media_y_covarianza(px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Media (3,) y covarianza (3, 3) de una lista de pixeles finitos.

    Con menos de dos muestras la covarianza no esta definida: devuelvo ceros,
    que es lo que corresponde (no hay dispersion observada) y lo que la
    regularizacion de `transporte_mkl` sabe tratar.
    """
    arr = sanea_pixeles(px, "media_y_covarianza")
    if arr.shape[0] == 0:
        raise ValueError("no hay ni un pixel del que sacar la estadistica")
    mu = arr.mean(axis=0)
    if arr.shape[0] < 2:
        return mu, np.zeros((3, 3), dtype=np.float64)
    cov = np.cov(arr, rowvar=False, ddof=1)
    return mu, np.asarray(cov, dtype=np.float64).reshape(3, 3)


def _simetriza(m: np.ndarray) -> np.ndarray:
    return 0.5 * (m + m.T)


def _autovalores(m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """eigh con los autovalores negativos de redondeo sujetos a cero."""
    lam, vec = np.linalg.eigh(_simetriza(np.asarray(m, dtype=np.float64)))
    return np.clip(lam, 0.0, None), vec


def _de_autovalores(lam: np.ndarray, vec: np.ndarray) -> np.ndarray:
    return _simetriza((vec * lam) @ vec.T)


def _piso_absoluto(*escalas: float) -> float:
    """Piso de varianza para que no haya divisiones por cero.

    Relativo a la escala del problema, no una constante magica: con pixeles en
    0..1 sale ~1e-12, y con una imagen de valores enormes sube con ella.
    """
    escala = max([float(e) for e in escalas] + [0.0])
    return 1e-12 * max(escala, 1e-12)


def covarianza_regularizada(
    cov_origen: np.ndarray, cov_destino: np.ndarray
) -> tuple[np.ndarray, np.ndarray, int]:
    """Autovalores utilizables de Sx, sus vectores propios, y cuantas
    direcciones eran degeneradas.

    Ver la explicacion larga en el docstring del modulo: en las direcciones sin
    varianza de origen se copia la varianza del destino, para que la ganancia
    ahi salga ~1 en vez de dispararse.
    """
    lam, vec = _autovalores(cov_origen)
    lam_y, _ = _autovalores(cov_destino)
    escala_x = float(lam.max()) if lam.size else 0.0
    escala_y = float(lam_y.max()) if lam_y.size else 0.0
    piso = _piso_absoluto(escala_x, escala_y)

    # Varianza del destino a lo largo de cada direccion propia del origen.
    var_destino = np.einsum("ji,jk,ki->i", vec, _simetriza(cov_destino), vec)
    var_destino = np.clip(var_destino, 0.0, None)

    umbral = TOL_RANGO * escala_x
    degenerada = lam <= max(umbral, piso)
    lam_reg = np.where(degenerada, np.maximum(var_destino, piso), lam)
    lam_reg = np.maximum(lam_reg, piso)
    return lam_reg, vec, int(degenerada.sum())


def transporte_mkl(
    origen_px: np.ndarray, destino_px: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Solucion cerrada del transporte lineal origen -> destino.

    Devuelve `(A, b)` con `A` (3, 3) simetrica semidefinida positiva y `b` (3,),
    ambas float64, tales que `y = A @ x + b` lleva la media y la covarianza del
    origen a las del destino.

    Las dos listas **no tienen por que medir lo mismo**: aqui no se empareja
    pixel con pixel, se emparejan distribuciones. Las filas no finitas se
    descartan antes de estimar nada (ver el docstring del modulo).
    """
    o, _ = pixeles_finitos(origen_px, "transporte_mkl(origen)")
    d, _ = pixeles_finitos(destino_px, "transporte_mkl(destino)")
    if o.shape[0] == 0:
        raise ValueError("transporte_mkl: el origen no tiene ni un pixel finito")
    if d.shape[0] == 0:
        raise ValueError("transporte_mkl: el destino no tiene ni un pixel finito")

    mu_x, cov_x = media_y_covarianza(o)
    mu_y, cov_y = media_y_covarianza(d)
    return transporte_mkl_de_estadistica(mu_x, cov_x, mu_y, cov_y)


def transporte_mkl_de_estadistica(
    mu_origen: np.ndarray,
    cov_origen: np.ndarray,
    mu_destino: np.ndarray,
    cov_destino: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Lo mismo que `transporte_mkl` pero partiendo ya de media y covarianza.

    Existe porque un `ColorStats` trae exactamente eso y no siempre trae
    pixeles: con media y covarianza ya hay transporte, no hace falta sintetizar
    una nube para volver a medirle lo que ya se sabe.
    """
    mu_x = np.asarray(mu_origen, dtype=np.float64).reshape(3)
    mu_y = np.asarray(mu_destino, dtype=np.float64).reshape(3)
    cov_x = np.asarray(cov_origen, dtype=np.float64).reshape(3, 3)
    cov_y = _simetriza(np.asarray(cov_destino, dtype=np.float64).reshape(3, 3))
    if not (np.isfinite(mu_x).all() and np.isfinite(mu_y).all()):
        raise ValueError("transporte_mkl: la media no es finita")
    if not (np.isfinite(cov_x).all() and np.isfinite(cov_y).all()):
        raise ValueError("transporte_mkl: la covarianza no es finita")

    lam, vec, _ = covarianza_regularizada(cov_x, cov_y)

    raiz = _de_autovalores(np.sqrt(lam), vec)
    raiz_inv = _de_autovalores(1.0 / np.sqrt(lam), vec)

    medio = _simetriza(raiz @ cov_y @ raiz)
    lam_m, vec_m = _autovalores(medio)
    raiz_medio = _de_autovalores(np.sqrt(lam_m), vec_m)

    a = _simetriza(raiz_inv @ raiz_medio @ raiz_inv)

    # Red de seguridad: A es simetrica, asi que sus autovalores son las
    # ganancias del estirado y se pueden sujetar sin romper la simetria.
    lam_a, vec_a = _autovalores(a)
    if float(lam_a.max(initial=0.0)) > GANANCIA_MAX:
        a = _de_autovalores(np.clip(lam_a, 0.0, GANANCIA_MAX), vec_a)

    b = mu_y - a @ mu_x
    return a, b


def aplicar_mkl(img: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Aplica `y = A x + b` a una imagen (..., 3) o a una lista de pixeles.

    Conserva la forma y la precision de la entrada (float32 -> float32), igual
    que hace `core.color`. El calculo intermedio va en float64.
    """
    arr = np.asarray(img)
    if arr.ndim == 0 or arr.shape[-1] != 3:
        raise ValueError(f"aplicar_mkl: esperaba (..., 3), llego {arr.shape}")
    mat = np.asarray(a, dtype=np.float64).reshape(3, 3)
    off = np.asarray(b, dtype=np.float64).reshape(3)
    salida = np.asarray(arr, dtype=np.float64) @ mat.T + off
    destino = arr.dtype if np.issubdtype(arr.dtype, np.floating) else np.float32
    return salida.astype(destino, copy=False)


def ganancias(a: np.ndarray) -> np.ndarray:
    """Los tres factores de estirado de `A`, de menor a mayor.

    Como `A` es simetrica, sus autovalores SON las ganancias a lo largo de sus
    ejes propios. Sirve para contarle a la GUI cuanto esta estirando el color
    una correccion: por encima de ~4x ya es una barbaridad.
    """
    lam, _ = _autovalores(a)
    return lam
