"""Generador de material sintetico reproducible.

TODO el material con el que se prueba SIDEBFLMS COLOR sale de aqui. No se abre
ni un solo fichero de Mario, ni un disco externo, ni /Volumes. Semilla fija:
dos ejecuciones dan exactamente los mismos pixeles.

CONVENCION DE SALIDA
--------------------
Las funciones `make_*` devuelven **escena-lineal**: float32 (alto, ancho, 3),
RGB, valores >= 0 que PUEDEN pasar de 1.0 (los especulares y el cielo lo hacen,
y tienen que hacerlo: si todo cupiera en 0..1 no estariamos probando nada).
El 18% de gris esta en 0.18.

Quien necesite el espacio de trabajo lo codifica con `core.color`. Este modulo
no importa nada de `core/` a proposito: es el suelo sobre el que se apoya todo
lo demas y no puede depender de lo que esta probando.

Escrituras: SOLO dentro de `tests/media/out/` o en la ruta que le pases. Nada
mas. `out/` esta en .gitignore y se regenera con `python tests/media/generate.py`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SEED = 20260914
MEDIA_DIR = Path(__file__).resolve().parent
OUT_DIR = MEDIA_DIR / "out"


# ---------------------------------------------------------------------------
# Utilidades de codificacion (internas, solo para escribir PNG de vista previa)
# ---------------------------------------------------------------------------


def srgb_eotf(v: np.ndarray) -> np.ndarray:
    """sRGB no-lineal -> lineal. Solo para construir escenas y guardar PNG."""
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((np.maximum(v, 0.0) + 0.055) / 1.055) ** 2.4)


def srgb_oetf(v: np.ndarray) -> np.ndarray:
    """Lineal -> sRGB no-lineal."""
    v = np.asarray(v, dtype=np.float64)
    v = np.maximum(v, 0.0)
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def _from_srgb8(rgb8: tuple[int, int, int]) -> np.ndarray:
    """Un color dado en sRGB 0-255 -> escena-lineal."""
    return srgb_eotf(np.array(rgb8, dtype=np.float64) / 255.0)


# ---------------------------------------------------------------------------
# Cartas y rampas
# ---------------------------------------------------------------------------

#: ColorChecker clasico de 24 parches, valores sRGB 8 bits publicados por
#: X-Rite. Fila 0 arriba-izquierda. No son medidas espectrales: son los valores
#: de referencia sRGB, que es lo que necesitamos para probar ida y vuelta.
COLORCHECKER_SRGB: tuple[tuple[int, int, int], ...] = (
    (115, 82, 68), (194, 150, 130), (98, 122, 157), (87, 108, 67), (133, 128, 177), (103, 189, 170),
    (214, 126, 44), (80, 91, 166), (193, 90, 99), (94, 60, 108), (157, 188, 64), (224, 163, 46),
    (56, 61, 150), (70, 148, 73), (175, 54, 60), (231, 199, 31), (187, 86, 149), (8, 133, 161),
    (243, 243, 242), (200, 200, 200), (160, 160, 160), (122, 122, 121), (85, 85, 85), (52, 52, 52),
)

#: Tonos de piel sinteticos, de mas claro a mas oscuro, en sRGB 8 bits.
#: Cubren el rango que a Mario le importa de verdad: si el emparejamiento solo
#: funciona con pieles claras, no funciona.
SKIN_TONES_SRGB: tuple[tuple[int, int, int], ...] = (
    (247, 216, 195),
    (233, 190, 163),
    (213, 162, 128),
    (176, 123, 88),
    (124, 80, 53),
    (77, 48, 31),
)


def colorchecker(patch_px: int = 64, gap_px: int = 8) -> np.ndarray:
    """Carta de 24 parches, 6x4. Escena-lineal."""
    rows, cols = 4, 6
    h = rows * patch_px + (rows + 1) * gap_px
    w = cols * patch_px + (cols + 1) * gap_px
    img = np.full((h, w, 3), _from_srgb8((30, 30, 30)), dtype=np.float64)
    for idx, srgb in enumerate(COLORCHECKER_SRGB):
        r, c = divmod(idx, cols)
        y = gap_px + r * (patch_px + gap_px)
        x = gap_px + c * (patch_px + gap_px)
        img[y : y + patch_px, x : x + patch_px] = _from_srgb8(srgb)
    return img.astype(np.float32)


def ramp_gray(width: int = 512, height: int = 64, stops: float = 12.0) -> np.ndarray:
    """Rampa de gris en paradas de luz: de -stops/2 a +stops/2 alrededor del 18%."""
    ev = np.linspace(-stops / 2, stops / 2, width)
    values = 0.18 * (2.0**ev)
    img = np.repeat(values[None, :, None], height, axis=0)
    return np.repeat(img, 3, axis=2).astype(np.float32)


def ramp_rgb(width: int = 512, height: int = 192) -> np.ndarray:
    """Tres rampas apiladas, una por canal primario, mas una neutra."""
    band = height // 4
    t = np.linspace(0.0, 1.0, width)
    lin = srgb_eotf(t)
    img = np.zeros((band * 4, width, 3), dtype=np.float64)
    for i, mask in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1))):
        img[i * band : (i + 1) * band] = lin[None, :, None] * np.array(mask)
    return img.astype(np.float32)


def hald(lut_size: int = 17) -> np.ndarray:
    """Imagen HALD CLUT: todas las entradas de un cubo `lut_size`, como imagen.

    La imagen es cuadrada de lado `lut_size**2` cuando lut_size es cuadrado
    perfecto; si no, se usa el lado mas ajustado y se rellena con negro. Los
    valores van en 0..1 y NO son escena-lineal: son coordenadas de LUT.
    """
    n = lut_size
    side = int(np.ceil(np.sqrt(n**3)))
    grid = np.linspace(0.0, 1.0, n)
    r, g, b = np.meshgrid(grid, grid, grid, indexing="ij")
    entries = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    img = np.zeros((side * side, 3), dtype=np.float32)
    img[: entries.shape[0]] = entries
    return img.reshape(side, side, 3)


def gradient(width: int = 640, height: int = 360, *, kind: str = "diagonal") -> np.ndarray:
    """Degradado suave. Sirve para cazar banding: si el LUT escalona, se ve."""
    yy, xx = np.mgrid[0:height, 0:width]
    u = xx / max(width - 1, 1)
    v = yy / max(height - 1, 1)
    if kind == "diagonal":
        t = (u + v) / 2
    elif kind == "radial":
        t = np.sqrt((u - 0.5) ** 2 + (v - 0.5) ** 2) / np.sqrt(0.5)
    else:
        t = u
    base = srgb_eotf(t)
    tint = np.stack([base * 1.0, base * 0.92, base * 0.84], axis=-1)
    return tint.astype(np.float32)


def noise_field(
    width: int = 640, height: int = 360, *, sigma: float = 0.02, seed: int = SEED
) -> np.ndarray:
    """Ruido gaussiano centrado en el 18%. Para probar robustez estadistica."""
    rng = np.random.default_rng(seed)
    img = 0.18 + rng.normal(0.0, sigma, size=(height, width, 3))
    return np.maximum(img, 0.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Escenas de estudio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scene:
    """Una escena sintetica con su verdad conocida."""

    name: str
    image: np.ndarray  # (h, w, 3) float32 escena-lineal
    skin_mask: np.ndarray  # (h, w) bool: donde hay piel de verdad
    skin_tone_index: int


def _soft_disk(h: int, w: int, cy: float, cx: float, ry: float, rx: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    d = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    return np.clip(1.5 - 1.5 * d, 0.0, 1.0)


def studio_scene(
    *,
    width: int = 640,
    height: int = 360,
    skin_tone_index: int = 2,
    seed: int = SEED,
    key_ev: float = 0.0,
) -> Scene:
    """Retrato sintetico de estudio: fondo, sujeto, pelo, ropa, especular y ruido.

    No pretende parecer una foto. Pretende tener lo que hace dificil el color:
    una piel dominante, un fondo de otro tono, negros con detalle, un especular
    que se sale de rango y grano. Con eso ya se rompen la mayoria de los
    algoritmos que solo funcionan con cartas.
    """
    rng = np.random.default_rng(seed + skin_tone_index * 977)
    img = np.zeros((height, width, 3), dtype=np.float64)

    # Fondo: gris con un degradado de caida a la derecha y un tinte frio leve.
    yy, xx = np.mgrid[0:height, 0:width]
    falloff = 0.55 + 0.45 * (1.0 - xx / max(width - 1, 1)) ** 1.4
    wall = _from_srgb8((96, 100, 110))
    img += wall * falloff[..., None]

    # Sujeto: cabeza + cuello + hombros.
    cy, cx = height * 0.44, width * 0.46
    head = _soft_disk(height, width, cy, cx, height * 0.26, height * 0.20)
    neck = _soft_disk(height, width, cy + height * 0.28, cx, height * 0.16, height * 0.09)
    shoulders = _soft_disk(height, width, height * 1.05, cx, height * 0.42, width * 0.42)
    skin_alpha = np.clip(head + neck, 0.0, 1.0)
    cloth_alpha = np.clip(shoulders - skin_alpha, 0.0, 1.0)

    skin = _from_srgb8(SKIN_TONES_SRGB[skin_tone_index])
    # Modelado: la luz principal viene de arriba-izquierda.
    shading = 0.62 + 0.55 * _soft_disk(height, width, cy - height * 0.09, cx - width * 0.05,
                                       height * 0.30, height * 0.26)
    img = img * (1.0 - skin_alpha[..., None]) + (skin * shading[..., None]) * skin_alpha[..., None]

    cloth = _from_srgb8((38, 44, 58))
    img = img * (1.0 - cloth_alpha[..., None]) + cloth * cloth_alpha[..., None]

    # Pelo: oscuro pero con detalle, no negro plano.
    hair = np.clip(
        _soft_disk(height, width, cy - height * 0.17, cx, height * 0.20, height * 0.23)
        - head * 0.85,
        0.0,
        1.0,
    )
    hair_col = _from_srgb8((44, 33, 28))
    img = img * (1.0 - hair[..., None]) + hair_col * hair[..., None]

    # Especular en la frente: se sale de 1.0 a proposito.
    spec = _soft_disk(height, width, cy - height * 0.13, cx - width * 0.035, height * 0.045,
                      height * 0.035)
    img += spec[..., None] * 2.4

    # Exposicion y grano.
    img *= 2.0**key_ev
    img += rng.normal(0.0, 0.004, size=img.shape)
    img = np.maximum(img, 0.0)

    mask = skin_alpha > 0.55
    mask &= hair < 0.2
    mask &= spec < 0.2
    return Scene(
        name=f"estudio_piel{skin_tone_index}_ev{key_ev:+.1f}",
        image=img.astype(np.float32),
        skin_mask=mask,
        skin_tone_index=skin_tone_index,
    )


def exterior_scene(*, width: int = 640, height: int = 360, seed: int = SEED) -> Scene:
    """Exterior: cielo quemado, vegetacion, camino. Deliberadamente INCOMPATIBLE
    con `studio_scene` — es la pareja del test de desajuste de contenido."""
    rng = np.random.default_rng(seed + 4242)
    yy, xx = np.mgrid[0:height, 0:width]
    v = yy / max(height - 1, 1)
    img = np.zeros((height, width, 3), dtype=np.float64)

    horizon = 0.42
    sky_t = np.clip(v / horizon, 0.0, 1.0)
    sky = _from_srgb8((150, 185, 230)) * (2.6 - 1.4 * sky_t[..., None])
    ground_t = np.clip((v - horizon) / (1 - horizon), 0.0, 1.0)
    grass = _from_srgb8((72, 96, 44)) * (0.5 + 0.9 * ground_t[..., None])
    is_sky = (v < horizon)[..., None]
    img = np.where(is_sky, sky, grass)

    # Camino claro cruzando en diagonal.
    path = np.exp(-(((xx - width * 0.5) - (yy - height * 0.6) * 0.8) ** 2) / (2 * 42.0**2))
    path *= (v > horizon)
    img = img * (1 - path[..., None] * 0.9) + _from_srgb8((176, 162, 138)) * path[..., None] * 0.9

    # Sol quemado.
    sun = _soft_disk(height, width, height * 0.14, width * 0.78, height * 0.07, height * 0.07)
    img += sun[..., None] * 9.0

    img += rng.normal(0.0, 0.006, size=img.shape)
    img = np.maximum(img, 0.0)
    return Scene(
        name="exterior",
        image=img.astype(np.float32),
        skin_mask=np.zeros((height, width), dtype=bool),
        skin_tone_index=-1,
    )


# ---------------------------------------------------------------------------
# Degradaciones espaciales: lo que un LUT NO puede reproducir (test T2)
# ---------------------------------------------------------------------------


def apply_vignette(img: np.ndarray, *, strength: float = 0.45, power: float = 2.2) -> np.ndarray:
    """Vineta radial. Multiplicativa, centrada, suave."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx - (w - 1) / 2) / ((w - 1) / 2)
    v = (yy - (h - 1) / 2) / ((h - 1) / 2)
    d = np.sqrt(u**2 + v**2) / np.sqrt(2)
    gain = 1.0 - strength * d**power
    return (np.asarray(img, dtype=np.float64) * gain[..., None]).astype(np.float32)


def apply_window(
    img: np.ndarray,
    *,
    box: tuple[int, int, int, int],
    gain: float = 1.35,
    tint: tuple[float, float, float] = (1.0, 0.97, 0.92),
    feather: int = 24,
) -> np.ndarray:
    """Una 'ventana' rectangular con caida suave: sube y calienta una zona.

    Es lo que un colorista hace con un power window, y es exactamente lo que un
    LUT 3D no puede reproducir, porque depende de DONDE esta el pixel.
    """
    h, w = img.shape[:2]
    x, y, bw, bh = box
    mask = np.zeros((h, w), dtype=np.float64)
    mask[max(y, 0) : y + bh, max(x, 0) : x + bw] = 1.0
    if feather > 0:
        k = np.exp(-0.5 * (np.arange(-3 * feather, 3 * feather + 1) / feather) ** 2)
        k /= k.sum()
        mask = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, mask)
        mask = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, mask)
    factor = 1.0 + mask[..., None] * (np.array(tint) * gain - 1.0)
    return (np.asarray(img, dtype=np.float64) * factor).astype(np.float32)


# ---------------------------------------------------------------------------
# Escritura de ficheros
# ---------------------------------------------------------------------------


def write_png16(path: str | Path, linear_img: np.ndarray) -> Path:
    """Guarda escena-lineal como PNG 16 bits codificado en sRGB (vista previa).

    Hay perdida: se recorta a 1.0. Es para MIRAR, no para medir.
    """
    import cv2

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    enc = np.clip(srgb_oetf(linear_img), 0.0, 1.0)
    data = (enc * 65535.0 + 0.5).astype(np.uint16)
    cv2.imwrite(str(path), data[..., ::-1])  # cv2 quiere BGR
    return path


def write_exr(path: str | Path, linear_img: np.ndarray) -> Path:
    """Guarda escena-lineal sin perdida (float16). Es lo que hay que usar para
    medir: el PNG recorta los especulares y el log negativo."""
    import cv2

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(linear_img, dtype=np.float32)[..., ::-1]
    ok = cv2.imwrite(str(path), data)
    if not ok:
        raise RuntimeError(f"OpenCV no ha podido escribir EXR en {path} (falta soporte OpenEXR)")
    return path


def make_clip(
    path: str | Path,
    frames: list[np.ndarray] | np.ndarray,
    *,
    fps: int = 25,
    codec: str = "prores",
) -> Path:
    """Escribe un clip de video a partir de fotogramas escena-lineal.

    Se codifica en sRGB 16 bits y se mete por tuberia a ffmpeg. `codec`:
    'prores' (ProRes 4444, sin perdida visible, .mov) o 'h264' (.mp4, para
    probar el camino con perdida).

    Necesita ffmpeg. Si no esta, lanza. No hay plan B silencioso.
    """
    import shutil

    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg).is_file():
        raise RuntimeError("no encuentro ffmpeg; instalalo con: brew install ffmpeg")

    arr = np.asarray(frames, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[None]
    h, w = arr.shape[1:3]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if codec == "prores":
        out_args = ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuv444p10le"]
    elif codec == "h264":
        out_args = ["-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p"]
    else:
        raise ValueError(f"codec no soportado: {codec}")

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0", *out_args, str(path),
    ]
    payload = (np.clip(srgb_oetf(arr), 0, 1) * 65535.0 + 0.5).astype("<u2").tobytes()
    proc = subprocess.run(cmd, input=payload, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg fallo: {proc.stderr.decode(errors='replace')[:400]}")
    return path


# ---------------------------------------------------------------------------
# Catalogo: lo que se regenera al ejecutar el modulo
# ---------------------------------------------------------------------------


def build_all(out_dir: str | Path = OUT_DIR) -> dict[str, Path]:
    """Regenera el catalogo completo en `out_dir`. Devuelve nombre -> ruta."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    catalogo: dict[str, np.ndarray] = {
        "colorchecker": colorchecker(),
        "rampa_gris": ramp_gray(),
        "rampa_rgb": ramp_rgb(),
        "hald17": hald(17),
        "degradado": gradient(),
        "ruido": noise_field(),
        "exterior": exterior_scene().image,
    }
    for i in range(len(SKIN_TONES_SRGB)):
        catalogo[f"estudio_piel{i}"] = studio_scene(skin_tone_index=i).image

    for name, img in catalogo.items():
        written[name] = write_png16(out / f"{name}.png", img)

    escena = studio_scene(skin_tone_index=2).image
    written["clip_estudio"] = make_clip(
        out / "clip_estudio.mov", [escena, escena * 1.02, escena * 0.98], codec="prores"
    )
    return written


if __name__ == "__main__":
    for nombre, ruta in build_all().items():
        print(f"{nombre:24s} {ruta}")
