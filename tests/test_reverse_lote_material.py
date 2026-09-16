"""Material del modo por lote: un «proyecto» sintético de 40 planos con UN grado.

NO TIENE TESTS. Vive en un `test_reverse_lote*.py` porque es el único nombre de
archivo de tests que este agente puede crear; pytest lo recoge y no encuentra
nada que ejecutar, que es lo correcto.

QUÉ FABRICA
-----------
* `look_conocido()`: el grado del proyecto, CDL + LUT 33³ en ese orden (el
  contrato). Es un look propio —curva S con pivote, sombras frías, altas
  cálidas, compresión de la croma alta, pieles/naranjas +sat y verdes -sat— y no
  una copia del de `tests/fuera_de_plano/`, que es del medidor independiente.
* `plano_lineal(tipo, semilla)`: una escena en luz lineal Rec.709 de uno de
  cuatro tipos —retrato, exterior, interior, noche— con la paleta, la
  exposición y la composición sacadas de la semilla. No pretenden parecer
  fotos: pretenden tener la variedad de colores de un trabajo real.
* `proyecto(n)`: los `n` originales ya en el espacio de trabajo, alternando los
  cuatro tipos.
* `correccion_extra(nombre)`: lo que un colorista añade a UN plano encima del
  look común («este más cálido», «este más frío», «este más abierto»).

RESOLUCIÓN
----------
Por defecto 320×180, por la carga de la máquina el día 4. La cobertura del cubo
depende de cuántos colores distintos hay, no de cuántos píxeles; la tabla de
`test_reverse_lote_cobertura.py` lo comprueba con planos a 640×360 y da las dos
cifras.
"""

from __future__ import annotations

import numpy as np

from core.contracts import CDL, LUT3D, LUT_SIZE_DEFAULT
from tests.conftest import a_trabajo
from tests.media import generate as gen

ANCHO_LOTE = 320
ALTO_LOTE = 180
TIPOS = ("retrato", "exterior", "interior", "noche")
SEMILLA_PROYECTO = 20260916

#: El CDL del proyecto: un balance suave, ni identidad ni disparate.
CDL_PROYECTO = CDL(
    slope=(1.05, 1.00, 0.96),
    offset=(0.008, 0.000, -0.004),
    power=(0.97, 1.00, 1.03),
    saturation=1.06,
)

_LUMA = np.array([0.2126, 0.7152, 0.0722])


def _suave(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def tabla_look(n: int = LUT_SIZE_DEFAULT) -> np.ndarray:
    """(n, n, n, 3) indexada [r, g, b]: el LUT del look del proyecto."""
    eje = np.linspace(0.0, 1.0, n)
    r, g, b = np.meshgrid(eje, eje, eje, indexing="ij")
    rgb = np.stack([r, g, b], -1)

    pivote = 0.42
    out = pivote + (rgb - pivote) * (1.0 + 0.10 * np.sin(np.pi * np.clip(rgb, 0.0, 1.0)))
    luma = rgb @ _LUMA
    sombras = (1.0 - _suave(luma, 0.05, 0.40)) ** 2
    altas = _suave(luma, 0.45, 0.90)
    out = out + np.stack([-0.004 * sombras, 0.010 * sombras, 0.026 * sombras], -1)
    out = out + np.stack([0.024 * altas, 0.008 * altas, -0.016 * altas], -1)

    lo = out @ _LUMA
    dif = out - lo[..., None]
    croma = np.linalg.norm(dif, axis=-1)
    dif = dif * (1.0 - 0.18 * _suave(croma, 0.12, 0.38))[..., None]

    # Secundarias suaves por tono, ponderadas por croma: pieles/naranjas +sat,
    # verdes -sat y un poco hacia amarillo.
    opa = dif[..., 0] - dif[..., 1]
    opb = 0.5 * (dif[..., 0] + dif[..., 1]) - dif[..., 2]
    tono = np.degrees(np.arctan2(opb, opa))
    peso = _suave(np.hypot(opa, opb), 0.01, 0.18)

    def ventana(centro: float, ancho: float) -> np.ndarray:
        d = np.abs((tono - centro + 180.0) % 360.0 - 180.0)
        return np.where(d < ancho, 0.5 + 0.5 * np.cos(np.pi * d / ancho), 0.0) * peso

    naranjas = ventana(40.0, 50.0)
    verdes = ventana(150.0, 60.0)
    dif = dif * (1.0 + 0.10 * naranjas - 0.20 * verdes)[..., None]
    dif = dif + np.stack([0.014 * verdes, 0.0 * verdes, -0.006 * verdes], -1)
    return np.clip(lo[..., None] + dif, 0.0, 1.0)


def tabla_look_duro(n: int = LUT_SIZE_DEFAULT) -> np.ndarray:
    """El look del proyecto MÁS dos secundarias estrechas (20° de ancho) y fuertes:
    rojos/pieles +60% de saturación y cian -60%. Es el contrapeso de la
    regularización: un prior de suavidad favorece looks suaves, y éste no lo es.
    `qc_lut` le pone avisos de banding, y es lo esperable."""
    t = tabla_look(n)
    lo = t @ _LUMA
    dif = t - lo[..., None]
    opa = dif[..., 0] - dif[..., 1]
    opb = 0.5 * (dif[..., 0] + dif[..., 1]) - dif[..., 2]
    tono = np.degrees(np.arctan2(opb, opa))
    peso = _suave(np.hypot(opa, opb), 0.02, 0.08)

    def ventana(centro: float, ancho: float) -> np.ndarray:
        d = np.abs((tono - centro + 180.0) % 360.0 - 180.0)
        return np.where(d < ancho, 0.5 + 0.5 * np.cos(np.pi * d / ancho), 0.0) * peso

    dif = dif * (1.0 + 0.6 * ventana(30.0, 20.0) - 0.6 * ventana(-150.0, 20.0))[..., None]
    return np.clip(lo[..., None] + dif, 0.0, 1.0)


def look_duro(n: int = LUT_SIZE_DEFAULT) -> tuple[CDL, LUT3D]:
    return CDL_PROYECTO, LUT3D(table=tabla_look_duro(n).astype(np.float32), title="look duro")


def look_conocido(n: int = LUT_SIZE_DEFAULT) -> tuple[CDL, LUT3D]:
    return CDL_PROYECTO, LUT3D(table=tabla_look(n).astype(np.float32), title="look del proyecto")


def colorear(original: np.ndarray, cdl: CDL, lut: LUT3D) -> np.ndarray:
    """El grado conocido: primero el CDL, luego el LUT. Ese orden es el contrato."""
    return lut.apply(cdl.apply(original)).astype(np.float32)


#: Correcciones que un colorista añade a un plano ENCIMA del look común. Se
#: aplican ANTES del look (en el nodo de balance), que es donde se hacen.
CORRECCIONES_EXTRA: dict[str, CDL] = {
    "mas_calido": CDL(slope=(1.06, 1.0, 0.93), offset=(0.004, 0.0, -0.004)),
    "mas_frio": CDL(slope=(0.94, 0.99, 1.07), offset=(-0.004, 0.0, 0.005)),
    "mas_abierto": CDL(slope=(1.10, 1.10, 1.10), power=(0.95, 0.95, 0.95)),
}


def correccion_escalada(nombre: str, fuerza: float) -> CDL:
    """La corrección `nombre` con su desvío de la identidad multiplicado por `fuerza`."""
    c = CORRECCIONES_EXTRA[nombre]
    return CDL(
        slope=tuple(1.0 + fuerza * (v - 1.0) for v in c.slope),
        offset=tuple(fuerza * v for v in c.offset),
        power=tuple(1.0 + fuerza * (v - 1.0) for v in c.power),
        saturation=1.0 + fuerza * (c.saturation - 1.0),
    )


# ---------------------------------------------------------------------------
# Escenas
# ---------------------------------------------------------------------------


def _hsv(h: float, s: float, v: float) -> np.ndarray:
    """HSV en sRGB codificado -> RGB lineal Rec.709."""
    h = (h % 360.0) / 60.0
    c = v * s
    x = c * (1.0 - abs(h % 2.0 - 1.0))
    i = int(h) % 6
    rgb = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][i]
    return gen.srgb_eotf(np.array(rgb) + (v - c))


def _disco(yy: np.ndarray, xx: np.ndarray, cy: float, cx: float, ry: float, rx: float) -> np.ndarray:
    d = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    return np.clip(1.5 - 1.5 * d, 0.0, 1.0)


def _rect(yy: np.ndarray, xx: np.ndarray, y0: float, x0: float, h: float, w: float) -> np.ndarray:
    return ((yy >= y0) & (yy < y0 + h) & (xx >= x0) & (xx < x0 + w)).astype(np.float64)


def _pinta(img: np.ndarray, alfa: np.ndarray, color: np.ndarray, luz: np.ndarray | float = 1.0) -> np.ndarray:
    capa = color[None, None, :] * np.asarray(luz)[..., None] if np.ndim(luz) else color * luz
    return img * (1.0 - alfa[..., None]) + capa * alfa[..., None]


def plano_lineal(tipo: str, semilla: int, ancho: int = ANCHO_LOTE, alto: int = ALTO_LOTE) -> np.ndarray:
    """(alto, ancho, 3) float32 en luz lineal Rec.709. Coordenadas normalizadas
    0..1 para que la composición no dependa de la resolución."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float64)
    yy /= alto
    xx /= ancho
    u = rng.uniform

    if tipo == "retrato":
        img = np.ones((alto, ancho, 3)) * _hsv(u(0, 360), u(0.05, 0.45), u(0.25, 0.65))
        img *= (0.5 + 0.5 * (1.0 - xx) ** u(0.5, 2.0))[..., None]
        cx = u(0.3, 0.7)
        cabeza = _disco(yy, xx, 0.42, cx, 0.24, 0.12)
        piel = gen.srgb_eotf(np.array(gen.SKIN_TONES_SRGB[int(rng.integers(len(gen.SKIN_TONES_SRGB)))]) / 255.0)
        luz = 0.55 + 0.6 * _disco(yy, xx, 0.34, cx - 0.04, 0.3, 0.16)
        img = _pinta(img, cabeza, piel, luz)
        ropa = np.clip(_disco(yy, xx, 1.05, cx, 0.42, 0.35) - cabeza, 0.0, 1.0)
        img = _pinta(img, ropa, _hsv(u(0, 360), u(0.1, 0.8), u(0.15, 0.7)), 0.7 + 0.3 * xx)
        pelo = np.clip(_disco(yy, xx, 0.26, cx, 0.2, 0.14) - cabeza * 0.85, 0.0, 1.0)
        img = _pinta(img, pelo, _hsv(u(10, 40), u(0.2, 0.6), u(0.08, 0.5)))
        img += _disco(yy, xx, 0.3, cx - 0.02, 0.03, 0.015)[..., None] * u(0.5, 2.5)
        img *= 2.0 ** u(-1.0, 1.0)
        ruido = 0.004
    elif tipo == "exterior":
        cielo = _hsv(u(190, 230) if u() < 0.6 else u(10, 40), u(0.05, 0.5), u(0.7, 1.0))
        hor = u(0.3, 0.6)
        img = cielo * (2.2 - 1.2 * np.clip(yy / hor, 0, 1))[..., None]
        suelo = _hsv(u(30, 130), u(0.2, 0.7), u(0.2, 0.6))
        img = np.where((yy > hor)[..., None], suelo * (0.5 + 0.9 * ((yy - hor) / (1 - hor)))[..., None], img)
        for _ in range(int(rng.integers(2, 6))):
            x0, w = u(0, 0.85), u(0.08, 0.25)
            h = u(0.15, 0.5)
            fachada = _rect(yy, xx, hor - h, x0, h, w)
            col = _hsv(u(0, 360), u(0.0, 0.4), u(0.3, 0.9))
            img = _pinta(img, fachada, col, np.where(xx < x0 + w * 0.6, 1.2, 0.55))
        img += _disco(yy, xx, u(0.05, 0.25), u(0.1, 0.9), 0.06, 0.035)[..., None] * u(2.0, 8.0)
        img *= 2.0 ** u(-0.7, 0.7)
        ruido = 0.006
    elif tipo == "interior":
        pared = _hsv(u(20, 45), u(0.2, 0.55), u(0.35, 0.7))
        img = pared * (0.35 + 0.65 * _disco(yy, xx, u(0.2, 0.5), u(0.2, 0.8), 0.9, 0.7))[..., None]
        img = _pinta(img, _rect(yy, xx, 0.72, 0.0, 0.3, 1.0), _hsv(u(15, 35), u(0.4, 0.8), u(0.15, 0.4)), 0.6 + 0.6 * xx)
        for _ in range(int(rng.integers(3, 7))):
            mueble = _rect(yy, xx, u(0.35, 0.75), u(0, 0.9), u(0.1, 0.3), u(0.05, 0.2))
            img = _pinta(img, mueble, _hsv(u(0, 360), u(0.1, 0.9), u(0.1, 0.8)), u(0.5, 1.0))
        ventana = _rect(yy, xx, u(0.08, 0.2), u(0.05, 0.7), u(0.2, 0.35), u(0.12, 0.25))
        img = _pinta(img, ventana, _hsv(u(195, 220), u(0.05, 0.3), 1.0), u(1.5, 3.0))
        img += _disco(yy, xx, u(0.2, 0.5), u(0.1, 0.9), 0.05, 0.03)[..., None] * _hsv(35, 0.5, 1.0) * u(2, 6)
        img *= 2.0 ** u(-1.2, 0.3)
        ruido = 0.005
    elif tipo == "noche":
        img = np.ones((alto, ancho, 3)) * _hsv(u(200, 250), u(0.3, 0.8), u(0.05, 0.2))
        img *= (0.4 + 0.8 * yy)[..., None]
        for _ in range(int(rng.integers(2, 5))):
            charco = _disco(yy, xx, u(0.4, 1.0), u(0, 1), u(0.15, 0.35), u(0.1, 0.25))
            img += charco[..., None] * _hsv(u(25, 40), u(0.6, 0.95), 1.0) * u(0.3, 1.2)
        for _ in range(int(rng.integers(2, 5))):
            neon = _rect(yy, xx, u(0.05, 0.6), u(0, 0.9), u(0.02, 0.08), u(0.1, 0.3))
            img = _pinta(img, neon, _hsv(rng.choice([300.0, 180.0, 0.0, 120.0, 270.0]), u(0.7, 1.0), 1.0), u(1.0, 3.0))
        img *= 2.0 ** u(-1.5, 0.0)
        ruido = 0.003
    else:
        raise ValueError(f"tipo de plano desconocido: {tipo}")

    img = img + rng.normal(0.0, ruido, size=img.shape)
    return np.maximum(img, 0.0).astype(np.float32)


def nombre_de_plano(i: int) -> str:
    return f"{i:02d}_{TIPOS[i % len(TIPOS)]}"


def proyecto(
    n: int, *, ancho: int = ANCHO_LOTE, alto: int = ALTO_LOTE, semilla: int = SEMILLA_PROYECTO
) -> list[np.ndarray]:
    """Los `n` primeros originales del proyecto, ya en el espacio de trabajo.
    El plano `i` es siempre el mismo, pidas 3 o 40."""
    return [
        a_trabajo(plano_lineal(TIPOS[i % len(TIPOS)], semilla + 7919 * i, ancho, alto))
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Medir cómo de bien queda determinado el grado DENTRO de la zona cubierta
# ---------------------------------------------------------------------------


def cdl_inverso(cdl: CDL, u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Entrada `x` tal que `cdl.apply(x) == u`, y máscara de dónde existe.

    La saturación ASC conserva la luma Rec.709, así que se deshace con 1/sat; la
    potencia, con 1/power sobre valores positivos; y slope/offset, despejando.
    Donde el paso de saturación deja un canal negativo no hay antiimagen (el
    `max(x, 0)` del estándar la ha borrado) y la máscara es False.
    """
    u = np.asarray(u, dtype=np.float64)
    luma = u @ _LUMA
    o = luma[..., None] + (u - luma[..., None]) / cdl.saturation
    valido = (o > 0.0).all(axis=-1)
    x = np.power(np.maximum(o, 0.0), 1.0 / np.asarray(cdl.power))
    return (x - np.asarray(cdl.offset)) / np.asarray(cdl.slope), valido


def error_en_celdas_cubiertas(
    resultado,
    originales: list[np.ndarray],
    cdl_verdad: CDL,
    lut_verdad: LUT3D,
    *,
    puntos_por_celda: int = 8,
    semilla: int = 0,
) -> dict[str, np.ndarray]:
    """Error del grado extraído en puntos repartidos por TODA la celda, no sólo
    donde había píxeles, en las celdas cuyos 8 nodos tienen >= 4 muestras.

    Es la pregunta de `MEDICION-T5.md` §6 hecha desde dentro: un color nuevo que
    cae en una celda «cubierta», ¿sale bien? Devuelve por punto: `de` (ΔE2000
    contra el grado conocido), `min_nodo` (muestras del nodo más flojo de su
    celda) y `distancia` (al píxel real más cercano, en el dominio del LUT).
    """
    from scipy.spatial import cKDTree

    from core.color import delta_e2000
    from core.reverse.invertir import _submuestra
    from core.umbrales import MUESTRAS_MINIMAS_CELDA

    cnt = np.asarray(resultado.coverage.counts)
    n = cnt.shape[0]
    esquinas = [
        cnt[i : n - 1 + i, j : n - 1 + j, k : n - 1 + k]
        for i in (0, 1)
        for j in (0, 1)
        for k in (0, 1)
    ]
    minimo = np.minimum.reduce(esquinas)
    celdas = np.argwhere(minimo >= MUESTRAS_MINIMAS_CELDA)
    if celdas.size == 0:
        vacio = np.zeros(0)
        return {"de": vacio, "min_nodo": vacio, "distancia": vacio, "celdas": 0}
    rng = np.random.default_rng(semilla)
    puntos = (celdas[:, None, :] + rng.random((len(celdas), puntos_por_celda, 3))) / (n - 1)
    puntos = puntos.reshape(-1, 3)
    min_nodo = np.repeat(minimo[tuple(celdas.T)], puntos_por_celda)
    x, valido = cdl_inverso(resultado.cdl, puntos)
    verdad = colorear(x, cdl_verdad, lut_verdad).astype(np.float64)
    de = np.asarray(delta_e2000(resultado.lut.apply(puntos), verdad), dtype=np.float64)
    fuentes = np.concatenate(
        [_submuestra(resultado.cdl.apply(o.reshape(-1, 3).astype(np.float64)), 20_000) for o in originales]
    )
    distancia, _ = cKDTree(np.clip(fuentes, 0.0, 1.0)).query(puntos)
    ok = valido & np.isfinite(de)
    return {
        "de": de[ok],
        "min_nodo": min_nodo[ok],
        "distancia": distancia[ok],
        "celdas": int(len(celdas)),
    }
