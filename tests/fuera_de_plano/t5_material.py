"""Material del T5, fabricado aqui: escenas, grado conocido, metrica y disparidad.

NO IMPORTA `core`
-----------------
Nada de este archivo importa `core`. Las escenas, el CDL conocido, los dos looks
conocidos, la aplicacion del grado, la conversion a L*a*b* y el ΔE2000 salen de
numpy y de `colour-science`. Asi un fallo de `CDL.apply` o `LUT3D.apply` no se
cancela solo: el coloreado conocido (B') se fabrica con MI aplicacion y la
prediccion con la del repo, y si se separan, sale en la cifra.

Tampoco importa `tests/media/generate.py`, `tests/conftest.py`,
`tests/test_entregables.py` ni `tests/medicion/`.

LAS ESCENAS
-----------
Una escena es un fondo en degradado, N objetos (elipses y rectangulos) con un
color de paleta y un modelado de luz interno de ~2 pasos, unos brillos
especulares opcionales y grano proporcional a la raiz de la senal. Todo en
escena-lineal Rec.709 y llevado al espacio de trabajo (DWG / DaVinci
Intermediate) con `colour`.

La paleta manda: centro y anchura de tono, rango de saturacion, exposicion y
dispersion de exposicion, numero de objetos. **Anchura de tono y numero de
objetos** es lo que barre la cobertura de A; **girar el tono, mover la
exposicion y cambiar la saturacion** es lo que barre la disparidad entre A y B.

LA DISPARIDAD ES UN NUMERO
--------------------------
`solape_histogramas(A, B)`: histogramas 3D de 33^3 (celda mas cercana, en el
espacio de trabajo EN BRUTO, sin ningun grado) normalizados a suma 1, y la
interseccion `sum(min(pA, pB))`. 1 = las dos escenas ocupan las mismas celdas en
la misma proporcion; 0 = no comparten ni una. No depende de lo que extraiga el
repo: es una propiedad del par de escenas.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import colour
import numpy as np
from colour.difference import delta_E_CIE2000
from colour.models import oetf_DaVinciIntermediate, oetf_inverse_DaVinciIntermediate

ALTO = 360
ANCHO = 640
TAM_LUT = 33

_DWG = colour.RGB_COLOURSPACES["DaVinci Wide Gamut"]
_REC709 = colour.RGB_COLOURSPACES["ITU-R BT.709"]
_D65_XY = np.array([0.3127, 0.3290])
_M_709_A_DWG = np.asarray(
    colour.matrix_RGB_to_RGB(_REC709, _DWG, chromatic_adaptation_transform=None)
)
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


# ---------------------------------------------------------------------------
# Puentes de espacio (colour-science)
# ---------------------------------------------------------------------------


def lineal709_a_trabajo(lin: np.ndarray) -> np.ndarray:
    """Escena-lineal Rec.709 -> DWG / DaVinci Intermediate. Los dos son D65: sin CAT."""
    dwg = np.asarray(lin, dtype=np.float64) @ _M_709_A_DWG.T
    return np.asarray(oetf_DaVinciIntermediate(dwg), dtype=np.float64)


def trabajo_a_lab(img: np.ndarray) -> np.ndarray:
    """DWG / DaVinci Intermediate -> CIE L*a*b* D65 2 grados, todo con `colour`."""
    lin = np.asarray(oetf_inverse_DaVinciIntermediate(np.asarray(img, dtype=np.float64)))
    xyz = colour.RGB_to_XYZ(lin, _DWG, illuminant=None, apply_cctf_decoding=False)
    return np.asarray(colour.XYZ_to_Lab(xyz, _D65_XY), dtype=np.float64)


def delta_e2000(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """ΔE2000 por pixel entre dos imagenes del espacio de trabajo, con `colour`."""
    return np.asarray(delta_E_CIE2000(trabajo_a_lab(a), trabajo_a_lab(b)), dtype=np.float64)


def resumen(de: np.ndarray, mascara: np.ndarray | None = None) -> dict[str, float]:
    """Medio, p95, maximo, n y fraccion > 3.0 de un campo de ΔE (no finitos fuera)."""
    v = np.asarray(de, dtype=np.float64).reshape(-1)
    if mascara is not None:
        v = v[np.asarray(mascara, dtype=bool).reshape(-1)]
    v = v[np.isfinite(v)]
    if v.size == 0:
        nan = float("nan")
        return {"medio": nan, "p95": nan, "max": nan, "n": 0.0, "frac_mayor_3": nan}
    return {
        "medio": float(v.mean()),
        "p95": float(np.percentile(v, 95)),
        "max": float(v.max()),
        "n": float(v.size),
        "frac_mayor_3": float((v > 3.0).mean()),
    }


# ---------------------------------------------------------------------------
# Paletas y escenas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paleta:
    """Lo que describe de que colores esta hecha una escena."""

    nombre: str
    tono_centro: float  # grados
    tono_ancho: float  # grados, anchura TOTAL del abanico
    sat_min: float  # saturacion HSV de pantalla, 0..1
    sat_max: float
    exposicion: float  # pasos respecto a gris 18%
    exposicion_ancho: float  # dispersion (pasos) entre objetos
    n_objetos: int
    brillos: int = 1
    #: True = el fondo es un barrido de tono (horizontal) x exposicion y
    #: saturacion (vertical) en vez de un degradado entre dos colores. No es un
    #: plano «normal»: existe para llevar la cobertura de A mas alla del ~1%.
    fondo_gamut: bool = False


def _hsv_a_rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    """HSV -> RGB de pantalla, vectorizado. h en grados."""
    h = np.mod(h, 360.0) / 60.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    tabla = np.stack(
        [
            np.stack([v, t, p], -1),
            np.stack([q, v, p], -1),
            np.stack([p, v, t], -1),
            np.stack([p, q, v], -1),
            np.stack([t, p, v], -1),
            np.stack([v, p, q], -1),
        ],
        0,
    )
    return tabla[i, np.arange(np.size(i))]


def colores_de_paleta(pal: Paleta, n: int, rng: np.random.Generator) -> np.ndarray:
    """n colores en escena-lineal Rec.709 sacados de la paleta. (n, 3)."""
    h = pal.tono_centro + rng.uniform(-0.5, 0.5, n) * pal.tono_ancho
    s = rng.uniform(pal.sat_min, pal.sat_max, n)
    pantalla = _hsv_a_rgb(h, s, np.ones(n))
    lin = pantalla**2.2
    # Normalizo a luma 0.18 y aplico la exposicion del objeto.
    luma = np.maximum(lin @ _LUMA, 1e-6)
    pasos = pal.exposicion + rng.uniform(-0.5, 0.5, n) * pal.exposicion_ancho
    return lin / luma[:, None] * (0.18 * 2.0**pasos)[:, None]


def escena_lineal(pal: Paleta, semilla: int) -> np.ndarray:
    """Escena-lineal Rec.709, (ALTO, ANCHO, 3) float64, >= 0."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:ALTO, 0:ANCHO].astype(np.float64)
    u, v = xx / (ANCHO - 1), yy / (ALTO - 1)

    # Fondo: degradado entre dos colores de la paleta, apagado 1.5 pasos, con
    # caida de luz lateral.
    c1, c2 = colores_de_paleta(pal, 2, rng) * 2.0**-1.5
    caida = 0.35 + 0.65 * (1.0 - u) ** 1.2 if rng.uniform() < 0.5 else 0.35 + 0.65 * u**1.2
    img = (c1 * (1 - v)[..., None] + c2 * v[..., None]) * caida[..., None]
    if pal.fondo_gamut:
        # Barrido: tono en horizontal; en vertical, bandas de saturacion
        # (8 bandas) y dentro de cada banda una rampa de exposicion.
        fase = rng.uniform(0.0, 1.0)
        h = pal.tono_centro + (np.mod(u + fase, 1.0) - 0.5) * pal.tono_ancho
        banda = np.minimum(np.floor(v * 8.0), 7.0) / 7.0
        s = pal.sat_min + (pal.sat_max - pal.sat_min) * banda
        rampa = np.mod(v * 8.0, 1.0)
        pantalla = _hsv_a_rgb(h.reshape(-1), s.reshape(-1), np.ones(h.size)).reshape(ALTO, ANCHO, 3)
        lin = pantalla**2.2
        luma = np.maximum(lin @ _LUMA, 1e-6)
        pasos = pal.exposicion + (rampa - 0.5) * pal.exposicion_ancho
        img = lin / luma[..., None] * (0.18 * 2.0**pasos)[..., None]

    cols = colores_de_paleta(pal, pal.n_objetos, rng)
    for k in range(pal.n_objetos):
        cx, cy = rng.uniform(0.05, 0.95) * ANCHO, rng.uniform(0.05, 0.95) * ALTO
        rx, ry = rng.uniform(0.05, 0.16) * ANCHO, rng.uniform(0.07, 0.24) * ALTO
        if rng.uniform() < 0.5:
            d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
            dentro = d <= 1.0
            modelado = 0.35 + 1.05 * np.clip(1.0 - d, 0.0, 1.0) ** 0.7
        else:
            dentro = (np.abs(xx - cx) <= rx) & (np.abs(yy - cy) <= ry)
            ang = rng.uniform(0, 2 * np.pi)
            g = ((xx - cx) * np.cos(ang) + (yy - cy) * np.sin(ang)) / max(rx, ry)
            modelado = 0.35 + 1.05 * np.clip(0.5 + 0.5 * g, 0.0, 1.0)
        img = np.where(dentro[..., None], cols[k] * modelado[..., None], img)

    for _ in range(pal.brillos):
        sx, sy = rng.uniform(0.1, 0.9) * ANCHO, rng.uniform(0.1, 0.9) * ALTO
        g = np.exp(-(((xx - sx) / 12.0) ** 2 + ((yy - sy) / 12.0) ** 2))
        img = img + g[..., None] * np.array([1.9, 1.85, 1.75])

    img = img + rng.normal(0.0, 0.006, img.shape) * np.sqrt(np.clip(img, 0, None) + 0.01)
    return np.clip(img, 0.0, None)


def escena_trabajo(pal: Paleta, semilla: int) -> np.ndarray:
    """La escena en el espacio de trabajo, float32 (contrato 1)."""
    return lineal709_a_trabajo(escena_lineal(pal, semilla)).astype(np.float32)


def desplazar(pal: Paleta, *, tono: float = 0.0, pasos: float = 0.0, sat: float = 1.0,
              ancho: float = 1.0, nombre: str = "") -> Paleta:
    """Otra paleta a partir de una: giro de tono, cambio de exposicion y saturacion."""
    return replace(
        pal,
        nombre=nombre or f"{pal.nombre}+{tono:g}deg{pasos:+g}EV x{sat:g}sat",
        tono_centro=pal.tono_centro + tono,
        tono_ancho=min(360.0, pal.tono_ancho * ancho),
        sat_min=float(np.clip(pal.sat_min * sat, 0.0, 0.97)),
        sat_max=float(np.clip(pal.sat_max * sat, 0.0, 0.97)),
        exposicion=pal.exposicion + pasos,
    )


#: Las escenas A, de mas pobre a mas rica de color. La «interior calido» es la
#: que se calibra contra el 0.46% del plano del repo (ver MEDICION-T5.md).
PALETAS_A: tuple[Paleta, ...] = (
    Paleta("A1 monocroma", 30.0, 12.0, 0.10, 0.30, -0.3, 1.0, 4, brillos=0),
    Paleta("A2 interior calido", 30.0, 50.0, 0.10, 0.55, -0.2, 2.0, 7),
    Paleta("A3 exterior", 90.0, 150.0, 0.10, 0.65, 0.0, 2.5, 10),
    Paleta("A4 variada", 0.0, 280.0, 0.05, 0.80, 0.0, 3.0, 16),
    Paleta("A5 muy variada", 0.0, 360.0, 0.02, 0.92, 0.0, 4.0, 28, brillos=2),
    Paleta("A6 barrido de gamut", 0.0, 360.0, 0.0, 0.92, 0.0, 6.0, 6, brillos=2,
           fondo_gamut=True),
)


def paletas_b(a: Paleta) -> tuple[tuple[str, Paleta], ...]:
    """Las B de cada A, en orden de disparidad pensada (la medida la da el numero).

    El nombre es solo una etiqueta: el nivel real lo dice `solape_histogramas`.
    """
    return (
        ("B0 misma paleta, otra toma", replace(a, nombre=a.nombre + " (otra toma)")),
        ("B1 casi identica", desplazar(a, tono=8, pasos=0.2)),
        ("B2 parecida", desplazar(a, tono=25, pasos=-0.5, sat=1.15)),
        ("B3 distinta", desplazar(a, tono=80, pasos=0.8, sat=1.3, ancho=1.3)),
        ("B4 muy distinta", desplazar(a, tono=170, pasos=-1.2, sat=1.5, ancho=1.6)),
        ("B5 opuesta", desplazar(a, tono=180, pasos=1.5, sat=0.4, ancho=0.6)),
    )


# ---------------------------------------------------------------------------
# Disparidad y ocupacion del cubo
# ---------------------------------------------------------------------------


def celda_mas_cercana(img: np.ndarray, n: int = TAM_LUT) -> np.ndarray:
    """(M,) indice plano de la celda mas cercana, sujetando a 0..1 como el LUT."""
    t = np.clip(np.asarray(img, dtype=np.float64).reshape(-1, 3), 0.0, 1.0) * (n - 1)
    i = np.rint(t).astype(np.int64)
    return (i[:, 0] * n + i[:, 1]) * n + i[:, 2]


def histograma_3d(img: np.ndarray, n: int = TAM_LUT) -> np.ndarray:
    idx = celda_mas_cercana(img, n)
    h = np.bincount(idx, minlength=n**3).astype(np.float64)
    return h / h.sum()


def solape_histogramas(a: np.ndarray, b: np.ndarray, n: int = TAM_LUT) -> float:
    """sum(min(pA, pB)) sobre el cubo de n^3, en el espacio de trabajo en bruto."""
    return float(np.minimum(histograma_3d(a, n), histograma_3d(b, n)).sum())


def fraccion_celdas_b_en_a(a: np.ndarray, b: np.ndarray, n: int = TAM_LUT) -> float:
    """De las celdas que ocupa B (>= 1 pixel), que fraccion ocupa tambien A."""
    ha, hb = histograma_3d(a, n) > 0, histograma_3d(b, n) > 0
    return float((ha & hb).sum() / max(hb.sum(), 1))


# ---------------------------------------------------------------------------
# El grado conocido
# ---------------------------------------------------------------------------

#: CDL conocido: calido suave, algo de contraste de power, +8% saturacion.
CDL_SLOPE = (1.04, 1.00, 0.955)
CDL_OFFSET = (0.006, 0.000, -0.006)
CDL_POWER = (0.98, 1.00, 1.02)
CDL_SAT = 1.08


def aplicar_cdl(rgb: np.ndarray) -> np.ndarray:
    """ASC CDL escrito aqui (no `CDL.apply`). Clamp antes de la potencia."""
    x = np.asarray(rgb, dtype=np.float64) * np.asarray(CDL_SLOPE) + np.asarray(CDL_OFFSET)
    x = np.power(np.maximum(x, 0.0), np.asarray(CDL_POWER))
    luma = x @ _LUMA
    return luma[..., None] + CDL_SAT * (x - luma[..., None])


def _suave(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def tabla_look(tipo: str, n: int = TAM_LUT) -> np.ndarray:
    """Tabla (n, n, n, 3) indexada [r, g, b] del look conocido.

    `global`: curva S con pivote 0.38 (DaVinci Intermediate), sombras a
    verde-azulado y altas luces a calido, y compresion suave de la croma alta.
    Todo depende de la luma y de la croma: ni un solo movimiento por tono.

    `secundarias`: lo mismo MAS tres secundarias por tono, suaves y ponderadas
    por croma (los neutros no se tocan): verdes hacia amarillo y -25% de
    saturacion, azules hacia cian, naranjas/pieles +12% de saturacion. Es la
    forma tipica de un look de teal & orange de verdad.
    """
    ejes = np.linspace(0.0, 1.0, n)
    r, g, b = np.meshgrid(ejes, ejes, ejes, indexing="ij")
    rgb = np.stack([r, g, b], -1)

    pivote = 0.38
    s_curva = lambda x: pivote + (x - pivote) * (1.04 + 0.12 * np.sin(np.pi * np.clip(x, 0, 1)))  # noqa: E731
    out = s_curva(rgb)
    luma = rgb @ _LUMA
    sombras = (1.0 - _suave(luma, 0.05, 0.45)) ** 2
    altas = _suave(luma, 0.40, 0.85)
    out = out + np.stack([0.0 * sombras, 0.018 * sombras, 0.032 * sombras], -1)
    out = out + np.stack([0.028 * altas, 0.006 * altas, -0.020 * altas], -1)

    lo = out @ _LUMA
    croma = np.linalg.norm(out - lo[..., None], axis=-1)
    comp = 1.0 - 0.22 * _suave(croma, 0.10, 0.35)
    out = lo[..., None] + comp[..., None] * (out - lo[..., None])

    if tipo == "secundarias":
        lo = out @ _LUMA
        dif = out - lo[..., None]
        # Tono en un plano oponente sencillo del propio espacio codificado.
        opa = dif[..., 0] - dif[..., 1]
        opb = 0.5 * (dif[..., 0] + dif[..., 1]) - dif[..., 2]
        tono = np.degrees(np.arctan2(opb, opa))
        peso_croma = _suave(np.hypot(opa, opb), 0.01, 0.20)

        def ventana(centro: float, ancho: float) -> np.ndarray:
            d = np.abs((tono - centro + 180.0) % 360.0 - 180.0)
            return np.where(d < ancho, 0.5 + 0.5 * np.cos(np.pi * d / ancho), 0.0) * peso_croma

        verdes = ventana(150.0, 70.0)
        azules = ventana(-60.0, 65.0)
        naranjas = ventana(45.0, 55.0)
        sat = 1.0 - 0.25 * verdes + 0.12 * naranjas
        dif = dif * sat[..., None]
        # Giro de verdes hacia amarillo (mas rojo, algo menos azul) y de azules
        # hacia cian (mas verde): desplazamientos pequenos y suaves.
        dif = dif + np.stack([0.020 * verdes, 0.0 * verdes, -0.008 * verdes], -1)
        dif = dif + np.stack([-0.006 * azules, 0.016 * azules, 0.0 * azules], -1)
        out = lo[..., None] + dif

    return np.clip(out, 0.0, 1.0)


def aplicar_lut(tabla: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Trilineal escrita aqui (no `LUT3D.apply`), dominio 0..1, sujecion al borde."""
    t = np.asarray(tabla, dtype=np.float64)
    n = t.shape[0]
    arr = np.asarray(rgb, dtype=np.float64)
    forma = arr.shape
    p = np.clip(arr.reshape(-1, 3), 0.0, 1.0) * (n - 1)
    i0 = np.clip(np.floor(p).astype(np.int64), 0, n - 2)
    f = p - i0
    out = np.zeros((p.shape[0], 3))
    for kr in (0, 1):
        for kg in (0, 1):
            for kb in (0, 1):
                w = ((f[:, 0] if kr else 1 - f[:, 0]) * (f[:, 1] if kg else 1 - f[:, 1])
                     * (f[:, 2] if kb else 1 - f[:, 2]))
                out += w[:, None] * t[i0[:, 0] + kr, i0[:, 1] + kg, i0[:, 2] + kb]
    return out.reshape(forma)


def colorear(img: np.ndarray, tabla: np.ndarray) -> np.ndarray:
    """El grado conocido: PRIMERO el CDL, LUEGO el LUT (contrato). float32."""
    return aplicar_lut(tabla, aplicar_cdl(img)).astype(np.float32)


def nodos_trilineales(img_post_cdl: np.ndarray, n: int = TAM_LUT) -> np.ndarray:
    """(8, M) indices planos de los ocho nodos que usa cada pixel al interpolar."""
    p = np.clip(np.asarray(img_post_cdl, dtype=np.float64).reshape(-1, 3), 0, 1) * (n - 1)
    i0 = np.clip(np.floor(p).astype(np.int64), 0, n - 2)
    out = np.empty((8, p.shape[0]), dtype=np.int64)
    k = 0
    for kr in (0, 1):
        for kg in (0, 1):
            for kb in (0, 1):
                out[k] = ((i0[:, 0] + kr) * n + i0[:, 1] + kg) * n + i0[:, 2] + kb
                k += 1
    return out
