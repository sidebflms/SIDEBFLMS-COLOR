"""Mi material: escena propia, CDL propio, LUT propio, vineta y ventana propias.

Nada de aqui viene de `tests/media/generate.py`. La escena es otra a proposito:
si con material distinto salen cifras parecidas, las cifras valen mas.

QUE ES LA ESCENA
----------------
"Mesa de maquetas": un fondo en degradado de temperatura, 24 parches de color
saturados repartidos en rejilla, una figura de piel, un reflejo especular por
encima del blanco difuso, una zona de sombra profunda y grano sembrado. La
idea es tener MUCHO volumen de color: el cubo de 33 se llena mas cuanto mas
variada es la escena, y la cobertura es justo lo que decide sobre que pixeles
se mide el T1.

Se produce en **escena-lineal con primarios Rec.709** (0.18 = 18% de gris) y
de ahi se lleva al espacio de trabajo con `colour-science`, no con
`core.color.convert`.

LAS OPERACIONES DEL GRADO ESTAN REIMPLEMENTADAS AQUI
----------------------------------------------------
`aplicar_cdl` y `aplicar_lut` son mi version de la formula ASC CDL y de la
interpolacion trilineal. No llaman a `CDL.apply` ni a `LUT3D.apply`. El motivo
es el mismo de siempre: si fabricara el coloreado con la misma funcion con la
que luego se reconstruye, un fallo en esa funcion se cancelaria solo.

`tests/medicion/test_metrica.py` mide cuanto se separan mi version y la del
repo; si se separan poco, la eleccion no cambia ninguna cifra y queda dicho.
"""

from __future__ import annotations

import numpy as np

import colour
from colour.models import (
    log_encoding_CanonLog3,
    log_encoding_DJIDLog,
    log_encoding_SLog3,
    log_encoding_VLog,
    oetf_DaVinciIntermediate,
    oetf_inverse_DaVinciIntermediate,
)

#: Semilla unica del arnes. Todo lo aleatorio sale de aqui.
SEMILLA = 20260915

_DWG = colour.RGB_COLOURSPACES["DaVinci Wide Gamut"]
_REC709 = colour.RGB_COLOURSPACES["ITU-R BT.709"]

#: Las cuatro camaras, con su espacio en colour-science y su curva.
#: Los primarios de estos cuatro espacios en colour-science coinciden DIGITO A
#: DIGITO con los que declara `core/color/spaces.py`; esta comprobado en
#: `test_metrica.py::test_los_primarios_de_las_cuatro_camaras_coinciden`.
CAMARAS_COLOUR: tuple[tuple[str, str, object], ...] = (
    ("FX3 (S-Log3 / S-Gamut3.Cine)", "S-Gamut3.Cine", log_encoding_SLog3),
    ("Canon (C-Log3 / Cinema Gamut)", "Cinema Gamut", log_encoding_CanonLog3),
    ("Lumix (V-Log / V-Gamut)", "V-Gamut", log_encoding_VLog),
    ("DJI (D-Log / D-Gamut)", "DJI D-Gamut", log_encoding_DJIDLog),
)

#: Los mismos cuatro, con el nombre que les da `core.color` (para la variante
#: de T3 que usa las conversiones del repo).
CAMARAS_REPO: tuple[str, ...] = (
    "slog3_sgamut3cine",
    "clog3_cinemagamut",
    "vlog_vgamut",
    "dlog_dgamut",
)

#: Desviacion de balance y exposicion de cada camara: slope y offset por canal.
#: Son MIAS y distintas de las del repo; lo unico que comparten es el orden de
#: magnitud, porque una desviacion de rodaje es una desviacion de rodaje.
DESVIOS: tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...] = (
    ((1.000, 1.000, 1.000), (0.000, 0.000, 0.000)),
    ((1.050, 0.985, 0.955), (0.004, -0.001, -0.006)),
    ((0.965, 1.020, 1.070), (-0.007, 0.001, 0.005)),
    ((1.095, 1.030, 0.915), (0.009, 0.002, -0.009)),
)


# ---------------------------------------------------------------------------
# Puentes de espacio, todos con colour-science
# ---------------------------------------------------------------------------


def lineal709_a_trabajo(lineal: np.ndarray) -> np.ndarray:
    """Escena-lineal Rec.709 -> espacio de trabajo (DWG / DaVinci Intermediate)."""
    m = colour.matrix_RGB_to_RGB(_REC709, _DWG, chromatic_adaptation_transform=None)
    lin_dwg = np.asarray(lineal, dtype=np.float64) @ np.asarray(m).T
    return np.asarray(oetf_DaVinciIntermediate(lin_dwg), dtype=np.float64)


def trabajo_a_lineal_dwg(img: np.ndarray) -> np.ndarray:
    """Espacio de trabajo -> DWG escena-lineal."""
    return np.asarray(oetf_inverse_DaVinciIntermediate(np.asarray(img, dtype=np.float64)))


def lineal_dwg_a_trabajo(lin: np.ndarray) -> np.ndarray:
    """DWG escena-lineal -> espacio de trabajo."""
    return np.asarray(oetf_DaVinciIntermediate(np.asarray(lin, dtype=np.float64)))


def lineal709_a_camara_colour(lineal: np.ndarray, indice: int) -> np.ndarray:
    """Escena-lineal Rec.709 -> espacio de captura de la camara `indice`, con colour."""
    _, nombre, curva = CAMARAS_COLOUR[indice]
    destino = colour.RGB_COLOURSPACES[nombre]
    m = colour.matrix_RGB_to_RGB(_REC709, destino, chromatic_adaptation_transform=None)
    lin = np.asarray(lineal, dtype=np.float64) @ np.asarray(m).T
    return np.asarray(curva(lin), dtype=np.float64)


def camara_a_trabajo_colour(img: np.ndarray, indice: int) -> np.ndarray:
    """Espacio de captura de la camara `indice` -> espacio de trabajo, con colour."""
    _, nombre, curva = CAMARAS_COLOUR[indice]
    origen = colour.RGB_COLOURSPACES[nombre]
    # `cctf_decoding` del espacio no siempre es la curva que quiero (Cinema
    # Gamut la trae lineal en colour-science), asi que se decodifica con la
    # inversa explicita de la MISMA curva que se uso al codificar.
    lin = _decodificar(np.asarray(img, dtype=np.float64), curva)
    m = colour.matrix_RGB_to_RGB(origen, _DWG, chromatic_adaptation_transform=None)
    return np.asarray(oetf_DaVinciIntermediate(lin @ np.asarray(m).T), dtype=np.float64)


_INVERSAS = {
    log_encoding_SLog3: colour.models.log_decoding_SLog3,
    log_encoding_CanonLog3: colour.models.log_decoding_CanonLog3,
    log_encoding_VLog: colour.models.log_decoding_VLog,
    log_encoding_DJIDLog: colour.models.log_decoding_DJIDLog,
}


def _decodificar(x: np.ndarray, curva) -> np.ndarray:
    return np.asarray(_INVERSAS[curva](x), dtype=np.float64)


# ---------------------------------------------------------------------------
# La escena
# ---------------------------------------------------------------------------

#: 24 colores de los parches, en escena-lineal Rec.709. Elegidos a mano para
#: barrer el cubo: primarios, secundarios, pasteles, oscuros y grises.
_PARCHES = np.array([
    [0.520, 0.052, 0.041], [0.410, 0.230, 0.150], [0.090, 0.140, 0.330],
    [0.075, 0.190, 0.060], [0.220, 0.210, 0.420], [0.130, 0.510, 0.410],
    [0.640, 0.190, 0.020], [0.060, 0.090, 0.380], [0.480, 0.085, 0.120],
    [0.100, 0.035, 0.130], [0.330, 0.500, 0.060], [0.640, 0.360, 0.020],
    [0.030, 0.040, 0.260], [0.080, 0.290, 0.070], [0.380, 0.030, 0.040],
    [0.740, 0.520, 0.020], [0.440, 0.080, 0.290], [0.020, 0.230, 0.350],
    [0.900, 0.900, 0.880], [0.580, 0.585, 0.580], [0.350, 0.352, 0.352],
    [0.180, 0.180, 0.180], [0.070, 0.070, 0.071], [0.018, 0.018, 0.019],
], dtype=np.float64)

#: Tono de piel de la figura, escena-lineal Rec.709. Ni el mas claro ni el mas
#: oscuro: uno intermedio-oscuro, que es donde se ven antes los errores.
_PIEL = np.array([0.165, 0.093, 0.062], dtype=np.float64)


def escena_lineal(
    alto: int = 405, ancho: int = 720, *, semilla: int = SEMILLA, sombra: bool = True
) -> np.ndarray:
    """Mi escena, en escena-lineal con primarios Rec.709. (alto, ancho, 3) float64."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float64)
    u = xx / max(ancho - 1, 1)
    v = yy / max(alto - 1, 1)

    # 1. Fondo: degradado de temperatura (calido abajo-izquierda, frio arriba)
    #    con caida de luz hacia la derecha.
    caida = 0.30 + 0.70 * (1.0 - u) ** 1.3
    calido = np.array([0.34, 0.26, 0.17])
    frio = np.array([0.13, 0.17, 0.28])
    img = (calido * (1.0 - v)[..., None] + frio * v[..., None]) * caida[..., None]

    # 2. Rejilla de 24 parches (6 x 4) en la mitad superior izquierda.
    px0, py0, pw, ph, hueco = 40, 30, 62, 62, 14
    for k, color in enumerate(_PARCHES):
        cx = px0 + (k % 6) * (pw + hueco)
        cy = py0 + (k // 6) * (ph + hueco)
        img[cy:cy + ph, cx:cx + pw] = color

    # 3. Figura de piel: un ovalo grande a la derecha, con modelado suave.
    cy, cx = alto * 0.60, ancho * 0.74
    ry, rx = alto * 0.34, ancho * 0.17
    d = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    dentro = d <= 1.0
    modelado = 0.55 + 0.75 * np.clip(1.0 - d, 0.0, 1.0) ** 0.6
    piel = _PIEL * modelado[..., None]
    img = np.where(dentro[..., None], piel, img)

    # 4. Reflejo especular: por encima del blanco difuso, para que haya
    #    material claro de verdad y no solo 0..1 aplastado.
    sy, sx = alto * 0.30, ancho * 0.66
    g = np.exp(-(((yy - sy) / 16.0) ** 2 + ((xx - sx) / 16.0) ** 2))
    img = img + g[..., None] * np.array([2.6, 2.5, 2.3])

    # 5. Sombra profunda en la esquina inferior izquierda.
    #    `sombra=False` la quita, y solo se usa para AISLAR una cosa que se
    #    midio: el detector espacial emite una zona local espuria justo ahi.
    #    La escena por defecto SI la lleva; las cifras del informe son con ella.
    if sombra:
        campo = np.clip(
            1.0 - np.exp(-(((yy - alto) / 90.0) ** 2 + ((xx) / 110.0) ** 2)), 0.06, 1.0
        )
        img = img * campo[..., None]

    # 6. Grano sembrado, proporcional a la raiz de la senal (como el ruido de
    #    fotones), no uniforme: un grano plano no rompe nada en el cubo.
    img = img + rng.normal(0.0, 0.006, size=img.shape) * np.sqrt(np.clip(img, 0.0, None) + 0.01)
    return np.clip(img, 0.0, None)


def escena_trabajo(
    alto: int = 405, ancho: int = 720, *, semilla: int = SEMILLA, sombra: bool = True
) -> np.ndarray:
    """Mi escena, ya en el espacio de trabajo. (alto, ancho, 3) float32."""
    return lineal709_a_trabajo(
        escena_lineal(alto, ancho, semilla=semilla, sombra=sombra)
    ).astype(np.float32)


# ---------------------------------------------------------------------------
# El grado conocido: mi CDL y mi LUT
# ---------------------------------------------------------------------------

#: Mi CDL conocido. Distinto del que usa el repo en su T1, y a proposito un
#: poco mas fuerte: mas offset negativo en azul y mas saturacion.
CDL_SLOPE = (1.085, 0.995, 0.925)
CDL_OFFSET = (0.018, -0.002, -0.014)
CDL_POWER = (0.935, 1.010, 1.065)
CDL_SAT = 1.18

#: Pesos de luma Rec.709, los del estandar ASC para la saturacion.
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


def aplicar_cdl(
    rgb: np.ndarray,
    slope=CDL_SLOPE,
    offset=CDL_OFFSET,
    power=CDL_POWER,
    saturation: float = CDL_SAT,
) -> np.ndarray:
    """La formula ASC CDL, reimplementada aqui. NO llama a `CDL.apply`.

        x   = in * slope + offset
        x   = max(x, 0)          <- el clamp va ANTES de la potencia (ASC)
        out = x ** power
        out = luma + sat * (out - luma)
    """
    x = np.asarray(rgb, dtype=np.float64) * np.asarray(slope) + np.asarray(offset)
    x = np.maximum(x, 0.0)
    out = np.power(x, np.asarray(power))
    if saturation != 1.0:
        luma = out @ _LUMA
        out = luma[..., None] + saturation * (out - luma[..., None])
    return out


def tabla_lut_conocida(size: int = 33) -> np.ndarray:
    """Mi look conocido, como tabla (N, N, N, 3) float64 indexada [r, g, b].

    Es otro look que el del repo: subida de contraste con pivote en 0.42,
    sombras viradas a verde-azul, altas luces con un punto de calido, y una
    ligera compresion del rojo para que el LUT no sea separable por canales
    (un LUT que solo hace curvas por canal es un LUT facil, y no quiero uno
    facil).
    """
    ejes = np.linspace(0.0, 1.0, size, dtype=np.float64)
    r, g, b = np.meshgrid(ejes, ejes, ejes, indexing="ij")

    pivote = 0.42
    contraste = lambda x: np.clip(pivote + (x - pivote) * (1.10 + 0.22 * np.sin(np.pi * x)), 0, 1)  # noqa: E731
    nr = contraste(r)
    ng = contraste(g)
    nb = contraste(b)

    sombras = np.clip(1.0 - (r + g + b) / 1.4, 0.0, 1.0) ** 2
    ng = ng + 0.030 * sombras
    nb = nb + 0.055 * sombras

    altas = np.clip((r + g + b) / 2.2 - 0.55, 0.0, 1.0)
    nr = nr + 0.035 * altas
    nb = nb - 0.020 * altas

    # Acoplamiento entre canales: el rojo se comprime donde hay mucho verde.
    nr = nr - 0.045 * np.clip(g - 0.5, 0.0, 1.0) * np.clip(r, 0.0, 1.0)

    return np.clip(np.stack([nr, ng, nb], axis=-1), 0.0, 1.0)


def aplicar_lut(tabla: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Interpolacion trilineal propia, dominio 0..1 y sujecion al borde.

    Es el mismo contrato que promete `LUT3D.apply` (contrato 4 y docstring de
    `core/contracts.py`), pero escrito aqui. No llama a `LUT3D.apply`.
    """
    t = np.asarray(tabla, dtype=np.float64)
    n = t.shape[0]
    arr = np.asarray(rgb, dtype=np.float64)
    forma = arr.shape
    p = np.clip(arr.reshape(-1, 3), 0.0, 1.0) * (n - 1)
    i0 = np.clip(np.floor(p).astype(np.int64), 0, n - 2)
    f = p - i0
    out = np.zeros((p.shape[0], 3), dtype=np.float64)
    for kr in (0, 1):
        for kg in (0, 1):
            for kb in (0, 1):
                w = (
                    (f[:, 0] if kr else 1.0 - f[:, 0])
                    * (f[:, 1] if kg else 1.0 - f[:, 1])
                    * (f[:, 2] if kb else 1.0 - f[:, 2])
                )
                out += w[:, None] * t[i0[:, 0] + kr, i0[:, 1] + kg, i0[:, 2] + kb]
    return out.reshape(forma)


def coloreado(original: np.ndarray, tabla: np.ndarray) -> np.ndarray:
    """El coloreado conocido: **primero el CDL, luego el LUT**.

    Ese orden es el contrato (`core/reverse/__init__.py`: `coloreado ~=
    LUT(CDL(original))`). Si se invierte aqui, la medida deja de medir lo que
    dice medir.
    """
    return aplicar_lut(tabla, aplicar_cdl(np.asarray(original, dtype=np.float64))).astype(np.float32)


# ---------------------------------------------------------------------------
# Lo espacial: mi vineta y mi ventana (T2)
# ---------------------------------------------------------------------------

#: Mi ventana, en pixeles del fotograma (x, y, ancho, alto). No es la del repo.
CAJA_VENTANA = (96, 250, 190, 110)


def _campo_vineta(alto: int, ancho: int, fuerza: float) -> np.ndarray:
    """Ganancia multiplicativa radial: 1.0 en el centro, 1-fuerza en la esquina."""
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float64)
    cy, cx = (alto - 1) / 2.0, (ancho - 1) / 2.0
    radio = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2) / np.sqrt(2.0)
    return 1.0 - fuerza * np.clip(radio, 0.0, 1.0) ** 1.7


def _campo_ventana(alto: int, ancho: int, caja, ganancia: float, difuminado: int) -> np.ndarray:
    """Ganancia multiplicativa rectangular con borde difuminado."""
    x, y, w, h = caja
    campo = np.zeros((alto, ancho), dtype=np.float64)
    campo[y:y + h, x:x + w] = 1.0
    if difuminado > 0:
        # Caja separable aplicada dos veces: da un borde suave sin traerse
        # scipy, y sin usar el suavizado de nadie mas.
        k = np.ones(2 * difuminado + 1, dtype=np.float64)
        k /= k.sum()
        for _ in range(2):
            campo = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, campo)
            campo = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, campo)
    return 1.0 + (ganancia - 1.0) * campo


def coloreado_con_lo_espacial(
    original: np.ndarray,
    tabla: np.ndarray,
    *,
    vineta: float = 0.42,
    ganancia_ventana: float = 1.55,
    difuminado: int = 9,
    caja=CAJA_VENTANA,
    en_lineal: bool = True,
) -> np.ndarray:
    """El coloreado conocido MAS una vineta y una ventana, fabricadas aqui.

    Con `en_lineal=True` (lo normal aqui) las dos se aplican **en luz lineal**,
    que es donde son multiplicativas de verdad: una vineta es un obturado
    optico y una ventana es un foco. Es una decision distinta de la del repo,
    que las aplica sobre la imagen ya codificada.

    `en_lineal=False` las aplica sobre la imagen codificada, como el repo. NO
    se usa para la cifra del informe: esta para poder ATRIBUIR la diferencia,
    porque la misma ganancia duele mucho mas sobre una curva log que sobre luz
    lineal, y eso solo o casi solo explica el hueco del T2.
    """
    base = coloreado(original, tabla)
    alto, ancho = base.shape[:2]
    g = _campo_vineta(alto, ancho, vineta) * _campo_ventana(
        alto, ancho, caja, ganancia_ventana, difuminado
    )
    if not en_lineal:
        return (np.asarray(base, dtype=np.float64) * g[..., None]).astype(np.float32)
    lin = trabajo_a_lineal_dwg(base)
    return lineal_dwg_a_trabajo(lin * g[..., None]).astype(np.float32)


# ---------------------------------------------------------------------------
# Los tres LUT malos (T4), fabricados aqui
# ---------------------------------------------------------------------------


def lut_no_monotono(size: int = 33) -> np.ndarray:
    """El rojo RETROCEDE de verdad al subir la entrada.

    OJO, que es la trampa del encargo: con tamano 33 el paso de rejilla es
    1/32 = 0.03125. Restar 0.02 a la celda 10 la deja en 0.28125 + 0.03125 -
    0.02 = 0.2925, que sigue siendo MAYOR que la celda 9 (0.28125): eso NO es
    no monotono. Aqui se copia el valor de la celda anterior y se le resta
    0.05, que es mas que el paso, asi que la inversion esta garantizada.
    """
    ejes = np.linspace(0.0, 1.0, size, dtype=np.float64)
    t = np.stack(np.meshgrid(ejes, ejes, ejes, indexing="ij"), axis=-1)
    t[10, :, :, 0] = t[9, :, :, 0] - 0.05
    return t


def lut_con_banding(size: int = 33) -> np.ndarray:
    """Un escalon de 0.28 a mitad de eje: en imagen se ve como una banda."""
    ejes = np.linspace(0.0, 1.0, size, dtype=np.float64)
    t = np.stack(np.meshgrid(ejes, ejes, ejes, indexing="ij"), axis=-1)
    t[:, size // 2:, :, :] += 0.28
    return t


def lut_fuera_de_gamut(size: int = 33) -> np.ndarray:
    """Expansion agresiva: la salida se sale de 0..1 por los dos lados."""
    ejes = np.linspace(0.0, 1.0, size, dtype=np.float64)
    t = np.stack(np.meshgrid(ejes, ejes, ejes, indexing="ij"), axis=-1)
    return t * 1.45 - 0.22


def tabla_identidad(size: int) -> np.ndarray:
    """La identidad, construida aqui y no con `LUT3D.identity`."""
    ejes = np.linspace(0.0, 1.0, size, dtype=np.float64)
    return np.stack(np.meshgrid(ejes, ejes, ejes, indexing="ij"), axis=-1)
