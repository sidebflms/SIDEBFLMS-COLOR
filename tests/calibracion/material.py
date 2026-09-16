"""Material de la calibración de la confianza: escenas, grados conocidos, códec y métrica.

NO IMPORTA `core`
-----------------
Nada de este archivo importa `core`. Las escenas, los grados conocidos, las cámaras,
la conversión al espacio de trabajo, el ΔE2000 y la disparidad salen de numpy, de
`colour-science` y de ffmpeg. Lo único que se toma prestado del repo es
`tests/media/generate.make_clip` (el encargo lo ofrece para el ruido de compresión) y
su `srgb_eotf`, que es la inversa exacta de la curva que `make_clip` aplica al
escribir. No se reutiliza material de nadie: ni escenas de `tests/media`, ni de
`tests/medicion`, ni de `tests/fuera_de_plano`.

CONVENCIONES
------------
* Las escenas son **escena-lineal Rec.709**, float64, pueden pasar de 1.0.
* El **espacio de trabajo** es el del contrato: primarios DaVinci Wide Gamut y curva
  DaVinci Intermediate. `a_trabajo` / `de_trabajo` son los dos puentes.
* Un **grado conocido** (`Grado`) opera sobre valores codificados del espacio de
  trabajo, igual que un CDL + LUT en Resolve: primero un CDL ASC y después un look
  no lineal suave (curva en S sobre la luma, virado de sombras y altas luces, y una
  secundaria que gira y satura una banda de tono). Es **una función**, no un LUT de
  rejilla: el colorista no gradúa en 33³.
* La **resolución** es un parámetro. Las escenas se dibujan en coordenadas
  normalizadas, así que la misma semilla da la misma composición a 320×180 y a
  640×360 (el grano, no: es por píxel).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import colour
import numpy as np
from colour.difference import delta_E_CIE2000
from colour.models import oetf_DaVinciIntermediate, oetf_inverse_DaVinciIntermediate

from tests.media.generate import make_clip, srgb_eotf

_DWG = colour.RGB_COLOURSPACES["DaVinci Wide Gamut"]
_REC709 = colour.RGB_COLOURSPACES["ITU-R BT.709"]
_D65_XY = np.array([0.3127, 0.3290])
_M_709_A_DWG = np.asarray(
    colour.matrix_RGB_to_RGB(_REC709, _DWG, chromatic_adaptation_transform=None)
)
_M_DWG_A_709 = np.linalg.inv(_M_709_A_DWG)
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


# ---------------------------------------------------------------------------
# Puentes de espacio y métrica (colour-science)
# ---------------------------------------------------------------------------


def a_trabajo(lin709: np.ndarray) -> np.ndarray:
    """Escena-lineal Rec.709 -> espacio de trabajo codificado (DWG / DI)."""
    lin = np.asarray(lin709, dtype=np.float64) @ _M_709_A_DWG.T
    return np.asarray(oetf_DaVinciIntermediate(lin), dtype=np.float64)


def de_trabajo(enc: np.ndarray) -> np.ndarray:
    """Espacio de trabajo codificado -> escena-lineal Rec.709."""
    lin = np.asarray(oetf_inverse_DaVinciIntermediate(np.asarray(enc, dtype=np.float64)))
    return lin @ _M_DWG_A_709.T


def lab_de_trabajo(enc: np.ndarray) -> np.ndarray:
    lin = np.asarray(oetf_inverse_DaVinciIntermediate(np.asarray(enc, dtype=np.float64)))
    xyz = colour.RGB_to_XYZ(lin, _DWG, illuminant=None, apply_cctf_decoding=False)
    return np.asarray(colour.XYZ_to_Lab(xyz, _D65_XY), dtype=np.float64)


def delta_e2000(a_enc: np.ndarray, b_enc: np.ndarray) -> np.ndarray:
    """ΔE2000 por píxel entre dos imágenes del espacio de trabajo, con `colour`."""
    return np.asarray(delta_E_CIE2000(lab_de_trabajo(a_enc), lab_de_trabajo(b_enc)))


def delta_e2000_y_luminancia(pred_enc: np.ndarray, verdad_enc: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """ΔE2000 por píxel y L* de la verdad (para separar lo que pasa del blanco difuso)."""
    lab_v = lab_de_trabajo(verdad_enc)
    de = np.asarray(delta_E_CIE2000(lab_de_trabajo(pred_enc), lab_v))
    return de, lab_v[..., 0]


def resumen_con_sdr(de: np.ndarray, l_verdad: np.ndarray) -> dict[str, float]:
    """`resumen` sobre todo, y el mismo con sufijo `_sdr` quitando L* de la verdad > 100.

    Por encima del blanco difuso el ΔE2000 no es una medida perceptual válida. La cifra
    que decide es la de todos los píxeles; la `_sdr` va al lado para saber si lo que
    manda son los brillos.
    """
    todo = resumen(de)
    sdr = resumen(np.asarray(de)[np.asarray(l_verdad) <= 100.0])
    return {**todo, **{f"{k}_sdr": v for k, v in sdr.items()},
            "frac_px_l_mayor_100": float((np.asarray(l_verdad) > 100.0).mean())}


def resumen(de: np.ndarray) -> dict[str, float]:
    v = np.asarray(de, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"max": float("nan"), "p95": float("nan"), "medio": float("nan")}
    return {"max": float(v.max()), "p95": float(np.percentile(v, 95)), "medio": float(v.mean())}


def interseccion_histogramas(a_enc: np.ndarray, b_enc: np.ndarray, n: int = 17) -> float:
    """Disparidad de contenido como número: `sum(min(pA, pB))` en una rejilla n³.

    Se calcula sobre los valores **codificados sin grado**. 1 = ocupan las mismas celdas
    en la misma proporción; 0 = no comparten ninguna.
    """

    def _h(x: np.ndarray) -> np.ndarray:
        i = np.rint(np.clip(x.reshape(-1, 3), 0.0, 1.0) * (n - 1)).astype(np.int64)
        idx = (i[:, 0] * n + i[:, 1]) * n + i[:, 2]
        h = np.bincount(idx, minlength=n**3).astype(np.float64)
        return h / h.sum()

    return float(np.minimum(_h(a_enc), _h(b_enc)).sum())


# ---------------------------------------------------------------------------
# Escenas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paleta:
    nombre: str
    tono_centro: float  # grados
    tono_ancho: float  # grados
    sat_min: float
    sat_max: float
    exposicion: float  # pasos respecto a gris medio
    disp_exposicion: float  # pasos
    objetos: int
    brillos: int


#: Cinco niveles de riqueza de color: es lo que barre la cobertura del cubo.
RIQUEZAS: dict[str, Paleta] = {
    "muy_pobre": Paleta("muy_pobre", 30.0, 6.0, 0.03, 0.12, 0.0, 0.4, 2, 0),
    "pobre": Paleta("pobre", 40.0, 25.0, 0.08, 0.35, 0.0, 0.7, 4, 1),
    "media": Paleta("media", 60.0, 100.0, 0.08, 0.55, 0.0, 1.0, 8, 2),
    "rica": Paleta("rica", 200.0, 230.0, 0.05, 0.75, 0.0, 1.3, 14, 3),
    "muy_rica": Paleta("muy_rica", 0.0, 360.0, 0.02, 0.90, 0.0, 1.6, 24, 4),
}


def _hsv_a_lineal(h: float, s: float, v: float) -> np.ndarray:
    """Color de tono h (grados), saturación s y valor v display-referred -> lineal."""
    h = (h % 360.0) / 60.0
    i = int(np.floor(h)) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    rgb = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return np.asarray(srgb_eotf(np.asarray(rgb)), dtype=np.float64)


def escena(paleta: Paleta, semilla: int, alto: int, ancho: int) -> np.ndarray:
    """Escena-lineal Rec.709 (alto, ancho, 3). Determinista por `semilla`."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float64)
    v = yy / max(alto - 1, 1)
    u = xx / max(ancho - 1, 1)
    gris = 0.18 * 2.0**paleta.exposicion

    def color() -> np.ndarray:
        h = paleta.tono_centro + rng.uniform(-0.5, 0.5) * paleta.tono_ancho
        s = rng.uniform(paleta.sat_min, paleta.sat_max)
        c = _hsv_a_lineal(h, s, 0.8)
        c = c / max(float(c @ _LUMA), 1e-6)  # luma 1
        return c * gris * 2.0 ** rng.uniform(-paleta.disp_exposicion, paleta.disp_exposicion)

    c1, c2 = color(), color()
    ang = rng.uniform(0, np.pi)
    t = np.clip(0.5 + (u - 0.5) * np.cos(ang) + (v - 0.5) * np.sin(ang), 0, 1)[..., None]
    img = c1 * (1 - t) + c2 * t
    img = img * (0.55 + 0.45 * (1 - v))[..., None]

    aspecto = ancho / alto
    for _ in range(paleta.objetos):
        c = color()
        cy, cx = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        ry, rx = rng.uniform(0.05, 0.25), rng.uniform(0.05, 0.25) / aspecto
        dy, dx = (v - cy) / ry, (u - cx) / rx
        if rng.uniform() < 0.5:
            d = np.sqrt(dy**2 + dx**2)
        else:
            d = np.maximum(np.abs(dy), np.abs(dx))
        borde = 1.5 / (min(ry * alto, rx * ancho) + 1e-9)
        m = np.clip((1.0 - d) / borde, 0.0, 1.0)[..., None]
        modelado = 2.0 ** (1.2 * (0.5 - np.clip(dy * 0.5 + dx * 0.3 + 0.5, 0, 1)))
        img = img * (1 - m) + (c * modelado[..., None]) * m

    for _ in range(paleta.brillos):
        cy, cx = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        r = rng.uniform(0.01, 0.03)
        g = np.exp(-(((v - cy) ** 2) + ((u - cx) * aspecto) ** 2) / (2 * r**2))[..., None]
        img = img + g * rng.uniform(2.0, 8.0) * np.array([1.0, 0.97, 0.9])

    grano = rng.standard_normal(img.shape) * 0.012 * np.sqrt(np.maximum(img, 0.0) + 1e-4)
    return np.maximum(img + grano, 0.0)


def variante(paleta: Paleta, tipo: str) -> Paleta:
    """Paleta de una escena B a partir de la de A. `tipo` fija la disparidad buscada."""
    if tipo == "otra_toma":
        return paleta
    if tipo == "tono_15":
        return replace(paleta, tono_centro=paleta.tono_centro + 15.0)
    if tipo == "tono_60_exp":
        return replace(paleta, tono_centro=paleta.tono_centro + 60.0,
                       exposicion=paleta.exposicion + 0.7)
    if tipo == "tono_150_sat":
        return replace(paleta, tono_centro=paleta.tono_centro + 150.0,
                       sat_max=min(paleta.sat_max * 1.4 + 0.1, 0.95),
                       exposicion=paleta.exposicion - 0.5)
    if tipo == "otra_paleta":
        otras = [p for p in RIQUEZAS.values() if p.nombre != paleta.nombre]
        o = otras[len(paleta.nombre) % len(otras)]
        return replace(o, tono_centro=o.tono_centro + 110.0, exposicion=0.9)
    raise ValueError(tipo)


#: Las variantes de B, de menos a más disparidad buscada. El nivel real lo da
#: `interseccion_histogramas`, no el nombre.
VARIANTES_B: tuple[str, ...] = ("otra_toma", "tono_15", "tono_60_exp", "tono_150_sat", "otra_paleta")


#: Fracción de píxeles (por su canal más alto) que quedan por encima del techo del sensor.
FRACCION_RECORTADA: float = 0.08


def recorte_altas_luces(lin: np.ndarray) -> np.ndarray:
    """Sensor que satura: recorte **por canal** en el percentil 92 del canal más alto.

    Un techo relativo a la escena y no un 1.0 fijo, para que el recorte muerda en todas
    las riquezas (una escena pobre sin brillos no llega nunca a 1.0 lineal). Recortar
    por canal gira el tono de lo recortado, que es lo que hace un sensor de verdad.
    """
    arr = np.asarray(lin, dtype=np.float64)
    techo = float(np.percentile(arr.max(axis=-1), 100.0 * (1.0 - FRACCION_RECORTADA)))
    return np.minimum(arr, techo)


# ---------------------------------------------------------------------------
# Grado conocido
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Grado:
    slope: tuple[float, float, float]
    offset: tuple[float, float, float]
    power: tuple[float, float, float]
    sat: float
    contraste: float  # fuerza de la S
    pivote: float
    tinte_sombras: tuple[float, float, float]
    tinte_altas: tuple[float, float, float]
    sec_tono: float  # grados, en el plano oponente
    sec_ancho: float  # grados
    sec_giro: float  # grados
    sec_sat: float  # factor extra de saturación en la banda


def grado_aleatorio(semilla: int, fuerza: str) -> Grado:
    rng = np.random.default_rng(semilla)
    k = {"suave": 0.4, "fuerte": 1.0}[fuerza]

    def tri(a: float) -> tuple[float, float, float]:
        return tuple(float(x) for x in rng.uniform(-a, a, 3))  # type: ignore[return-value]

    return Grado(
        slope=tuple(float(1 + x) for x in rng.uniform(-0.03 * k, 0.03 * k, 3)),  # type: ignore[arg-type]
        offset=tri(0.008 * k),
        power=tuple(float(1 + x) for x in rng.uniform(-0.03 * k, 0.03 * k, 3)),  # type: ignore[arg-type]
        sat=float(1 + rng.uniform(-0.15, 0.25) * k),
        contraste=float(rng.uniform(0.2, 0.9) * k),
        pivote=float(rng.uniform(0.35, 0.5)),
        tinte_sombras=tri(0.015 * k),
        tinte_altas=tri(0.015 * k),
        sec_tono=float(rng.uniform(0, 360)),
        sec_ancho=float(rng.uniform(25, 60)),
        sec_giro=float(rng.uniform(-25, 25) * k),
        sec_sat=float(rng.uniform(-0.3, 0.4) * k),
    )


def aplicar_grado(g: Grado, enc: np.ndarray) -> np.ndarray:
    """El grado conocido sobre valores codificados. Salida recortada a 0..1."""
    x = np.asarray(enc, dtype=np.float64)
    # 1) CDL ASC
    x = np.maximum(x * np.asarray(g.slope) + np.asarray(g.offset), 0.0) ** np.asarray(g.power)
    y = x @ _LUMA
    x = y[..., None] + g.sat * (x - y[..., None])
    # 2) curva en S sobre la luma (monótona: derivada de tanh > 0)
    y = x @ _LUMA
    k = max(g.contraste, 1e-6)
    y2 = g.pivote + np.tanh(k * (y - g.pivote)) / k * (1.0 + 0.25 * k)
    x = x + (y2 - y)[..., None]
    # 3) virado de sombras y de altas luces
    yc = np.clip(y2, 0.0, 1.0)[..., None]
    x = x + np.asarray(g.tinte_sombras) * (1 - yc) ** 2 + np.asarray(g.tinte_altas) * yc**2
    # 4) secundaria: gira y satura una banda de tono en el plano oponente
    y = x @ _LUMA
    c = x - y[..., None]
    a_ = c[..., 0] - c[..., 1]
    b_ = 0.5 * (c[..., 0] + c[..., 1]) - c[..., 2]
    tono = np.degrees(np.arctan2(b_, a_))
    croma = np.hypot(a_, b_)
    dt = (tono - g.sec_tono + 180.0) % 360.0 - 180.0
    w = np.exp(-0.5 * (dt / g.sec_ancho) ** 2) * np.clip(croma / 0.05, 0.0, 1.0)
    th = np.radians(g.sec_giro) * w
    f = 1.0 + g.sec_sat * w
    a2 = (a_ * np.cos(th) - b_ * np.sin(th)) * f
    b2 = (a_ * np.sin(th) + b_ * np.cos(th)) * f
    # vuelta de (a, b) a croma RGB con suma de luma nula
    m = np.array([[1.0, -1.0, 0.0], [0.5, 0.5, -1.0], _LUMA])
    minv = np.linalg.inv(m)
    c2 = np.stack([a2, b2, np.zeros_like(a2)], axis=-1) @ minv.T
    x = y[..., None] + c2
    return np.clip(x, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Cámaras (para el igualado de clips)
# ---------------------------------------------------------------------------


def camara_aleatoria(semilla: int) -> np.ndarray:
    """Matriz 3x3 en lineal Rec.709: ganancias por canal, diafonía y exposición."""
    rng = np.random.default_rng(semilla)
    m = np.diag(rng.uniform(0.8, 1.25, 3))
    m = m + rng.uniform(-0.08, 0.08, (3, 3)) * (1 - np.eye(3))
    return m * 2.0 ** rng.uniform(-0.7, 0.7)


# ---------------------------------------------------------------------------
# Códec: ida y vuelta por h264 con `make_clip`
# ---------------------------------------------------------------------------


def h264_ida_y_vuelta(enc: np.ndarray, directorio: str | None = None) -> np.ndarray:
    """Pasa una imagen del espacio de trabajo por h264 (yuv420p, 8 bits) y la devuelve.

    `make_clip` aplica `srgb_oetf` y recorta a 0..1; se le entrega `srgb_eotf(enc)` para
    que lo que llegue al códec sean **los valores codificados tal cual**. Se decodifica
    con ffmpeg a rgb48le diciendo la matriz y el rango de entrada, para que la vuelta
    no meta un cambio de matriz que no es ruido de compresión.
    """
    arr = np.clip(np.asarray(enc, dtype=np.float64), 0.0, 1.0)
    alto, ancho = arr.shape[:2]
    with tempfile.TemporaryDirectory(dir=directorio) as d:
        ruta = Path(d) / "par.mp4"
        make_clip(ruta, srgb_eotf(arr)[None].astype(np.float32), codec="h264")
        ffmpeg = "/opt/homebrew/bin/ffmpeg" if os.path.isfile("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(ruta),
            "-vf", "scale=in_color_matrix=bt601:in_range=tv:out_range=pc,format=rgb48le",
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb48le", "pipe:1",
        ]
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    px = np.frombuffer(out, dtype="<u2").reshape(alto, ancho, 3).astype(np.float64) / 65535.0
    return px
