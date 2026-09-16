"""Material sintetico para probar la primera prueba SIN tocar material real.

Fabrica "brutos" (clips con movimiento y contenido distinto entre si) y un
"master" montado con trozos de ellos: con un grado conocido, reencuadres,
un bruto que no aparece, uno que aparece dos veces, una toma gemela, un plano
muy corto y un fundido. Y devuelve **la verdad**: que trozo de que bruto esta
en que fotogramas del master, con que escala y que desplazamiento.

ESTE ARCHIVO SI ESCRIBE FICHEROS, y es el unico de `pruebas/` junto a la guarda
y `medir_coste.py`: escribe los clips sinteticos en la carpeta que se le pase
(la `tmp_path` de pytest o una carpeta temporal). `primera_real.py` no lo importa
nunca; hay un test que lo comprueba.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.color import from_working, to_working
from core.contracts import CDL, LUT3D

__all__ = [
    "CDL_SINTETICO",
    "Tramo",
    "Montaje",
    "escena",
    "fabricar_montaje",
    "grado_sintetico",
    "lut_sintetico",
]

FPS: int = 25

#: El grado "entregado" del montaje sintetico. Se aplica sobre DaVinci Intermediate,
#: que es logaritmico: ahi un slope de 1.08 ya convierte un gris en naranja y recorta
#: gama (la primera version lo hacia, y el cian salia amarillo). Estos valores
#: calientan y separan sin salirse: un gris 0.5 sale (0.53, 0.50, 0.45).
CDL_SINTETICO = CDL(
    slope=(1.02, 1.00, 0.98),
    offset=(0.004, 0.000, -0.004),
    power=(0.98, 1.00, 1.02),
    saturation=1.06,
)


def lut_sintetico(n: int = 17) -> LUT3D:
    """Un look monotono suave: curva en S y sombras a frio."""
    t = LUT3D.identity(n).table.astype(np.float64)
    x = np.clip(t, 0.0, 1.0)
    s = np.clip(x + 0.04 * np.sin(np.pi * x) * (x - 0.5) * 2.0, 0.0, 1.0)
    s[..., 2] = np.clip(s[..., 2] * 0.99 + 0.01 * (1.0 - x[..., 2]), 0.0, 1.0)
    return LUT3D(table=s.astype(np.float32), title="look sintetico")


def grado_sintetico(codigo: np.ndarray) -> np.ndarray:
    """Valores de codigo Rec.709 -> valores de codigo Rec.709 gradados."""
    w = to_working(np.asarray(codigo, dtype=np.float32), "rec709")
    g = lut_sintetico().apply(CDL_SINTETICO.apply(w))
    return np.asarray(from_working(np.asarray(g, dtype=np.float32), "rec709"), dtype=np.float32)


def _srgb_eotf(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    alto = ((np.maximum(v, 0.04045) + 0.055) / 1.055) ** 2.4
    return np.where(v <= 0.04045, v / 12.92, alto)


def escena(seed: int, ancho: int, alto: int) -> np.ndarray:
    """Lienzo (alto, ancho, 3) en valores de codigo 0..1 con estructura propia.

    Formas suaves de colores, rayas y una textura fina. Dos semillas distintas
    dan composiciones distintas; es lo que la localizacion tiene que separar.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float64)
    base = rng.uniform(0.15, 0.45, 3)
    ang = rng.uniform(0, np.pi)
    img = base[None, None, :] + 0.25 * (
        (np.cos(ang) * xx / ancho + np.sin(ang) * yy / alto)[..., None] - 0.5
    ) * rng.uniform(0.5, 1.0, 3)
    for _ in range(int(rng.integers(14, 22))):
        cy, cx = rng.uniform(0, alto), rng.uniform(0, ancho)
        ry, rx = rng.uniform(0.03, 0.18) * alto * 2, rng.uniform(0.03, 0.18) * ancho
        d = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
        a = np.clip(3.0 * (1.0 - d), 0.0, 1.0)[..., None]
        col = rng.uniform(0.05, 0.95, 3)
        img = img * (1.0 - a) + col * a
    for _ in range(int(rng.integers(4, 8))):
        # rayas finas: bordes con orientacion
        th = rng.uniform(0, np.pi)
        c = rng.uniform(-0.3, 0.3)
        dist = np.cos(th) * (xx / ancho - 0.5) + np.sin(th) * (yy / alto - 0.5) - c
        a = (np.abs(dist) < rng.uniform(0.002, 0.006)).astype(np.float64)[..., None]
        img = img * (1.0 - a) + rng.uniform(0.0, 1.0, 3) * a
    img += rng.normal(0.0, 0.01, img.shape)
    return np.clip(img, 0.0, 1.0).astype(np.float32)


def _recorte(img: np.ndarray, x: float, y: float, w: float, h: float, ancho: int, alto: int):
    import cv2

    H, W = img.shape[:2]
    x0, y0 = int(round(x * W)), int(round(y * H))
    x1, y1 = int(round((x + w) * W)), int(round((y + h) * H))
    trozo = img[y0:y1, x0:x1]
    return cv2.resize(trozo, (ancho, alto), interpolation=cv2.INTER_AREA)


def _clip(ruta: Path, fotogramas: list[np.ndarray]) -> Path:
    """ProRes 4444 etiquetado Rec.709 a partir de valores de codigo."""
    from tests.media.generate import make_clip

    lineal = np.stack([_srgb_eotf(f) for f in fotogramas]).astype(np.float32)
    # make_clip codifica en sRGB: pasarle la inversa deja los valores de codigo intactos.
    return make_clip(ruta, lineal, fps=FPS, codec="prores")


@dataclass(frozen=True)
class Tramo:
    """Un trozo del master y de donde sale. Coordenadas del recorte normalizadas."""

    bruto: str
    master_desde: int  # primer fotograma del master
    n: int  # fotogramas
    bruto_desde: int  # primer fotograma del bruto
    escala: float  # ancho del recorte / ancho del bruto
    x: float  # esquina del recorte, 0..1 del ancho del bruto
    y: float


@dataclass(frozen=True)
class Montaje:
    master: Path
    brutos: dict[str, Path]
    tramos: tuple[Tramo, ...]
    no_aparecen: tuple[str, ...]
    ancho_master: int
    alto_master: int


def _fotogramas_bruto(seed: int, ancho: int, alto: int, n: int, paso: tuple[float, float],
                      gemela_de: int | None = None) -> list[np.ndarray]:
    """Un bruto con movimiento de camara: una ventana que se desplaza sobre un lienzo."""
    margen = 1.35
    W, H = int(ancho * margen), int(alto * margen)
    lienzo = escena(gemela_de if gemela_de is not None else seed, W, H)
    if gemela_de is not None:
        # Toma gemela: el mismo decorado con cosas movidas y otro grano. Es la
        # trampa mas probable con material real (toma 1 / toma 2).
        otra = escena(seed, W, H)
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:H, 0:W]
        cy, cx = rng.uniform(0.3, 0.7) * H, rng.uniform(0.3, 0.7) * W
        m = (((yy - cy) / (0.28 * H)) ** 2 + ((xx - cx) / (0.22 * W)) ** 2 < 1.0)[..., None]
        lienzo = np.where(m, otra, lienzo)
        lienzo = np.clip(lienzo + np.random.default_rng(seed + 7).normal(0, 0.01, lienzo.shape),
                         0, 1).astype(np.float32)
    # Algo que se mueve POR SU CUENTA dentro del cuadro (un "actor"). Sin esto,
    # una panoramica pura sobre un decorado quieto es ambigua: el fotograma k con
    # un recorte y el k+1 con el recorte desplazado dan la misma imagen, y no hay
    # manera de saber el fotograma exacto. Con material real lo rompen el
    # paralaje y lo que se mueve en cuadro; aqui lo rompe este objeto.
    rng = np.random.default_rng(seed + 99)
    actor = escena(seed + 1000, 120, 120)
    radio = 0.16 * alto
    yy, xx = np.mgrid[0:alto, 0:ancho]
    ax0, ay0 = rng.uniform(0.2, 0.4) * ancho, rng.uniform(0.3, 0.6) * alto
    vx, vy = rng.uniform(2.5, 4.0), rng.uniform(-1.5, 1.5)
    salida = []
    for k in range(n):
        ox = min(max(0.0, paso[0] * k), W - ancho)
        oy = min(max(0.0, paso[1] * k), H - alto)
        x0, y0 = int(ox), int(oy)
        cuadro = lienzo[y0 : y0 + alto, x0 : x0 + ancho].copy()
        cx, cy = ax0 + vx * k, ay0 + vy * k
        d = np.hypot(xx - cx, yy - cy)
        a = np.clip((radio - d) / 2.0, 0.0, 1.0)[..., None]
        iy = np.clip(((yy - cy) / (2 * radio) + 0.5) * 119, 0, 119).astype(int)
        ix = np.clip(((xx - cx) / (2 * radio) + 0.5) * 119, 0, 119).astype(int)
        cuadro = cuadro * (1.0 - a) + actor[iy, ix] * a
        salida.append(cuadro.astype(np.float32))
    return salida


#: Los brutos del montaje: nombre -> (semilla, paso de la camara en px/fotograma, gemela de).
BRUTOS: dict[str, tuple[int, tuple[float, float], int | None]] = {
    "A_pan_derecha": (101, (2.0, 0.0), None),
    "B_casi_fijo": (202, (0.3, 0.2), None),
    "C_descarte": (303, (1.0, 1.0), None),
    "D_pan_abajo": (404, (0.0, 1.5), None),
    "E_gemela_de_A": (505, (1.2, 0.4), 101),
}

#: Los planos del master, en orden: (bruto, fotogramas, desde, escala, x, y).
PLANOS: tuple[tuple[str, int, int, float, float, float], ...] = (
    ("A_pan_derecha", 30, 10, 0.75, 0.20, 0.10),  # reencuadrado
    ("B_casi_fijo", 30, 5, 1.00, 0.0, 0.0),
    ("D_pan_abajo", 25, 0, 0.60, 0.30, 0.35),  # reencuadre fuerte
    ("B_casi_fijo", 5, 45, 1.00, 0.0, 0.0),  # plano muy corto
    ("D_pan_abajo", 25, 30, 1.00, 0.0, 0.0),  # D por segunda vez
    ("E_gemela_de_A", 25, 20, 0.90, 0.05, 0.08),  # entra con fundido
)

#: Fotogramas de fundido encadenado entre los dos ultimos planos.
FUNDIDO: int = 6

N_FOTOGRAMAS_BRUTO: int = 60


def _verdad(carpeta: Path, ancho_master: int = 480, alto_master: int = 270) -> Montaje:
    tramos: list[Tramo] = []
    cursor = 0
    for i, (nombre, n, desde, s, x, y) in enumerate(PLANOS):
        inicio = cursor - FUNDIDO if i == len(PLANOS) - 1 else cursor
        tramos.append(Tramo(nombre, inicio, n, desde, s, x, y))
        cursor = inicio + n
    return Montaje(
        master=Path(carpeta) / "master" / "master_entregado.mov",
        brutos={n: Path(carpeta) / "brutos" / f"{n}.mov" for n in BRUTOS},
        tramos=tuple(tramos),
        no_aparecen=("C_descarte",),
        ancho_master=ancho_master,
        alto_master=alto_master,
    )


def fabricar_montaje(carpeta: Path, *, ancho_bruto: int = 640, alto_bruto: int = 360,
                     ancho_master: int = 480, alto_master: int = 270) -> Montaje:
    """Escribe 5 brutos y un master en `carpeta` y devuelve la verdad del montaje."""
    carpeta = Path(carpeta)
    verdad = _verdad(carpeta, ancho_master, alto_master)
    fotos: dict[str, list[np.ndarray]] = {}
    for nombre, (seed, paso, gemela) in BRUTOS.items():
        fotos[nombre] = _fotogramas_bruto(
            seed, ancho_bruto, alto_bruto, N_FOTOGRAMAS_BRUTO, paso, gemela
        )
        _clip(verdad.brutos[nombre], fotos[nombre])

    aspecto = alto_master / ancho_master
    master: list[np.ndarray] = []
    for t in verdad.tramos:
        alto_rel = t.escala * ancho_bruto * aspecto / alto_bruto
        imgs = [
            grado_sintetico(_recorte(fotos[t.bruto][t.bruto_desde + k], t.x, t.y, t.escala,
                                     alto_rel, ancho_master, alto_master))
            for k in range(t.n)
        ]
        solape = len(master) - t.master_desde
        for k in range(solape):  # fundido encadenado
            a = (k + 1) / (solape + 1)
            master[t.master_desde + k] = (1 - a) * master[t.master_desde + k] + a * imgs[k]
        master.extend(imgs[solape:])
    _clip(verdad.master, master)
    return verdad


def montaje_compartido(base: Path) -> Montaje:
    """El montaje de `fabricar_montaje`, fabricado una sola vez por carpeta base.

    Para que varios ficheros de test de la misma sesion de pytest no lo fabriquen
    cada uno (tarda unos 15 s). Si ya esta fabricado en esa carpeta, se reutiliza.
    """
    carpeta = Path(base) / "montaje_pruebas"
    marca = carpeta / "LISTO"
    if marca.exists():
        return _verdad(carpeta)
    m = fabricar_montaje(carpeta)
    marca.write_text("ok\n")
    return m
