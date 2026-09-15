"""Sacar fotogramas de un clip (o de una imagen suelta) sin perder precision.

COMO SE SACAN LOS FOTOGRAMAS
----------------------------
Por tuberia `rawvideo` en **16 bits** (`rgb48le`), nunca PNG de 8 bits: un
PNG de 8 bits tira cuatro de los doce bits utiles de un ProRes y luego las
estadisticas mienten en el tercer decimal.

Los fotogramas se **reparten por todo el clip**, no se cogen del principio: se
piden los `n` indices igualmente espaciados entre el primer fotograma y el
ultimo. Coger los 12 primeros de un plano de 10 segundos seria medir medio
segundo y llamarlo plano. El detalle sucio de como se traduce un indice de
fotograma a un `-ss` que ffmpeg entienda esta en `_instantes`, y tiene su test.

BINARIOS
--------
Siempre por `core.paths.ffmpeg()` / `ffprobe()`, nunca `shutil.which` a pelo: una
app lanzada desde el Dock en macOS no hereda el PATH del shell.

IMAGENES SUELTAS
----------------
Los PNG/EXR/TIFF no pasan por ffmpeg: se leen con OpenCV, que devuelve los
float32 del EXR tal cual (con negativos y con los especulares por encima de 1.0,
que es justo lo que un rgb48le recortaria).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.color import to_working
from core.contracts import ColorSpaceName
from core.paths import ExecutableNotFound
from core.paths import ffmpeg as _ffmpeg
from core.paths import ffprobe as _ffprobe

from .errores import (
    ErrorFFmpeg,
    FicheroNoEncontrado,
    FormatoNoSoportado,
    HerramientaNoDisponible,
)

#: Fotogramas por defecto. Ver NOTAS.md: 12 es el punto donde deja de moverse la
#: media de un plano normal y todavia se analiza un clip en menos de un segundo.
N_FOTOGRAMAS_POR_DEFECTO: int = 12

#: Extensiones que se leen como imagen fija (con OpenCV, no con ffmpeg).
EXTENSIONES_IMAGEN: frozenset[str] = frozenset(
    {".png", ".exr", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp", ".hdr"}
)

#: Extensiones de imagen que vienen en escena-lineal en vez de codificadas.
EXTENSIONES_LINEALES: frozenset[str] = frozenset({".exr", ".hdr"})

#: Espacio que se asume cuando no hay forma de deducirlo. Ver NOTAS.md §"que
#: espacio asumo": para video es Rec.709 (OETF de camara, no gamma de pantalla).
ESPACIO_ASUMIDO_VIDEO: ColorSpaceName = "rec709"

#: Lo mismo para una imagen fija en coma flotante (EXR): escena-lineal Rec.709,
#: que es lo que escribe `tests/media/generate.py:write_exr`.
ESPACIO_ASUMIDO_LINEAL: ColorSpaceName = "linear_rec709"

#: Segundos que se le dan a ffmpeg/ffprobe antes de darlo por colgado.
TIMEOUT_S: float = 120.0

#: Metadatos de ffprobe -> espacio de origen. Solo lo que sabemos afirmar.
_TRANSFER_A_ESPACIO: dict[str, ColorSpaceName] = {
    "bt709": "rec709",
    "smpte170m": "rec709",
    "iec61966-2-1": "rec709",  # sRGB; ver NOTAS.md, no es identico pero casi
    "bt470bg": "rec709",
}


@dataclass(frozen=True)
class InfoMedio:
    """Lo que ffprobe (o OpenCV) sabe decir del fichero antes de decodificar."""

    ruta: str
    ancho: int
    alto: int
    n_fotogramas: int  # 0 = no se sabe
    duracion: float  # segundos, 0.0 = no se sabe
    fps: float  # 0.0 = no se sabe
    codec: str
    es_imagen: bool
    space_deducido: ColorSpaceName | None  # None = ffprobe no dijo nada util


# ---------------------------------------------------------------------------
# Sondeo
# ---------------------------------------------------------------------------


def _exigir_fichero(ruta: str | Path) -> Path:
    p = Path(ruta)
    if not p.exists():
        raise FicheroNoEncontrado(f"No existe el fichero: {p}")
    if p.is_dir():
        raise FicheroNoEncontrado(f"Esperaba un fichero y {p} es una carpeta.")
    if not p.is_file():
        raise FicheroNoEncontrado(f"{p} no es un fichero legible.")
    if p.stat().st_size == 0:
        raise FormatoNoSoportado(f"El fichero esta vacio (0 bytes): {p}")
    return p


def _binario(cual: str) -> str:
    try:
        return _ffmpeg() if cual == "ffmpeg" else _ffprobe()
    except ExecutableNotFound as e:
        raise HerramientaNoDisponible(str(e)) from e


def _fraccion(texto: str | None) -> float:
    """'25/1' -> 25.0. Devuelve 0.0 si no hay nada aprovechable."""
    if not texto or texto in ("0/0", "N/A"):
        return 0.0
    try:
        if "/" in texto:
            num, den = texto.split("/", 1)
            d = float(den)
            return float(num) / d if d else 0.0
        return float(texto)
    except ValueError:
        return 0.0


def _entero(texto: str | None) -> int:
    if not texto or texto == "N/A":
        return 0
    try:
        return int(float(texto))
    except ValueError:
        return 0


def sondear(ruta: str | Path) -> InfoMedio:
    """Metadatos del fichero. No decodifica ni un pixel de imagen."""
    p = _exigir_fichero(ruta)
    if p.suffix.lower() in EXTENSIONES_IMAGEN:
        return _sondear_imagen(p)
    return _sondear_video(p)


def _sondear_imagen(p: Path) -> InfoMedio:
    img = _leer_imagen(p)
    alto, ancho = img.shape[:2]
    lineal = p.suffix.lower() in EXTENSIONES_LINEALES
    return InfoMedio(
        ruta=str(p),
        ancho=int(ancho),
        alto=int(alto),
        n_fotogramas=1,
        duracion=0.0,
        fps=0.0,
        codec=p.suffix.lower().lstrip("."),
        es_imagen=True,
        space_deducido=ESPACIO_ASUMIDO_LINEAL if lineal else ESPACIO_ASUMIDO_VIDEO,
    )


def _sondear_video(p: Path) -> InfoMedio:
    exe = _binario("ffprobe")
    cmd = [
        exe, "-v", "error", "-print_format", "json",
        "-select_streams", "v:0", "-show_streams", "-show_format", str(p),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as e:
        raise ErrorFFmpeg(f"ffprobe se ha quedado colgado con {p.name} (mas de {TIMEOUT_S:.0f} s).") from e
    if proc.returncode != 0:
        detalle = proc.stderr.decode(errors="replace").strip().splitlines()
        motivo = detalle[-1] if detalle else "sin detalle"
        raise FormatoNoSoportado(f"ffprobe no reconoce {p.name} como medio valido: {motivo}")
    try:
        datos = json.loads(proc.stdout.decode(errors="replace") or "{}")
    except json.JSONDecodeError as e:
        raise ErrorFFmpeg(f"No entiendo la respuesta de ffprobe sobre {p.name}.") from e

    flujos = datos.get("streams") or []
    if not flujos:
        raise FormatoNoSoportado(f"{p.name} no tiene ninguna pista de video.")
    v = flujos[0]
    ancho, alto = _entero(v.get("width")), _entero(v.get("height"))
    if ancho <= 0 or alto <= 0:
        raise FormatoNoSoportado(f"{p.name} no declara una resolucion valida.")

    fps = _fraccion(v.get("avg_frame_rate")) or _fraccion(v.get("r_frame_rate"))
    duracion = _fraccion(v.get("duration")) or _fraccion((datos.get("format") or {}).get("duration"))
    n = _entero(v.get("nb_frames"))
    if n <= 0 and duracion > 0 and fps > 0:
        n = max(int(round(duracion * fps)), 1)
    if duracion <= 0 and n > 0 and fps > 0:
        duracion = n / fps

    transfer = str(v.get("color_transfer") or "").lower()
    primarios = str(v.get("color_primaries") or "").lower()
    space = _TRANSFER_A_ESPACIO.get(transfer) or _TRANSFER_A_ESPACIO.get(primarios)

    return InfoMedio(
        ruta=str(p),
        ancho=ancho,
        alto=alto,
        n_fotogramas=max(n, 0),
        duracion=max(duracion, 0.0),
        fps=max(fps, 0.0),
        codec=str(v.get("codec_name") or "?"),
        es_imagen=False,
        space_deducido=space,
    )


# ---------------------------------------------------------------------------
# Imagenes fijas
# ---------------------------------------------------------------------------


def _leer_imagen(p: Path) -> np.ndarray:
    """(alto, ancho, 3) float32 con los valores del fichero, sin recortar."""
    import cv2

    datos = cv2.imread(str(p), cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
    if datos is None:
        raise FormatoNoSoportado(
            f"No he podido abrir {p.name} como imagen. Si es un video, quita la extension "
            f"de imagen; si es un EXR, comprueba que OpenCV trae soporte OpenEXR."
        )
    arr = np.asarray(datos)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise FormatoNoSoportado(f"{p.name} no tiene tres canales de color (forma {arr.shape}).")
    arr = arr[..., :3][..., ::-1]  # OpenCV entrega BGR

    if arr.dtype == np.uint8:
        return (arr.astype(np.float32) / 255.0).copy()
    if arr.dtype == np.uint16:
        return (arr.astype(np.float32) / 65535.0).copy()
    return np.ascontiguousarray(arr, dtype=np.float32)


# ---------------------------------------------------------------------------
# Decodificacion de video
# ---------------------------------------------------------------------------


def _decodificar_uno(exe: str, p: Path, t: float | None, ancho: int, alto: int) -> np.ndarray | None:
    """Un fotograma en el instante `t`. None si ffmpeg no ha podido darlo."""
    cmd = [exe, "-v", "error", "-nostdin"]
    if t is not None and t > 0:
        cmd += ["-ss", f"{t:.6f}"]
    cmd += [
        "-i", str(p), "-map", "0:v:0", "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb48le", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return None
    esperado = ancho * alto * 3 * 2
    if proc.returncode != 0 or len(proc.stdout) < esperado:
        return None
    crudo = np.frombuffer(proc.stdout[:esperado], dtype="<u2").reshape(alto, ancho, 3)
    return crudo.astype(np.float32) / 65535.0


def _instantes(info: InfoMedio, k: int) -> list[float | None]:
    """Instantes de busqueda, en segundos, repartidos por TODO el clip.

    Con `-ss` antes de `-i`, ffmpeg entrega **el primer fotograma cuyo pts es >=
    el instante pedido**. Eso tiene dos consecuencias que costaron un rato medir
    (y estan afirmadas en `test_analysis_frames.py`):

    - Pedir el CENTRO del fotograma `i` devuelve el fotograma `i+1`, no el `i`.
    - Pedir el centro del ULTIMO fotograma no devuelve nada: ffmpeg se planta
      detras del final del fichero y saca cero bytes con codigo de salida 0.

    Por eso se pide medio fotograma ANTES del que se quiere: `(idx - 0.5)/fps`
    cae siempre dentro del fotograma anterior y el que sale es exactamente
    `idx`, incluido el ultimo del clip. Si no hay fps fiable se cae a fracciones
    de la duracion, empezando cada tramo en su borde (nunca en el final).
    """
    if k <= 1:
        return [None]
    if info.fps > 0 and info.n_fotogramas > 1:
        indices = np.unique(np.round(np.linspace(0, info.n_fotogramas - 1, k)).astype(np.int64))
        return [None if j == 0 else float((j - 0.5) / info.fps) for j in indices]
    if info.duracion > 0:
        return [None if i == 0 else info.duracion * i / k for i in range(k)]
    return [None] * k


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def extraer_fotogramas_con_avisos(
    ruta: str | Path,
    *,
    n_fotogramas: int = N_FOTOGRAMAS_POR_DEFECTO,
    space: ColorSpaceName | None = None,
) -> tuple[np.ndarray, tuple[str, ...], InfoMedio, ColorSpaceName]:
    """Como `extraer_fotogramas` pero devolviendo ademas avisos, metadatos y el
    espacio de origen que se ha acabado usando. Es lo que consume `analizar_clip`.
    """
    if int(n_fotogramas) < 1:
        raise ValueError(f"n_fotogramas tiene que ser >= 1, no {n_fotogramas}")
    n_fotogramas = int(n_fotogramas)

    info = sondear(ruta)
    avisos: list[str] = []

    origen: ColorSpaceName
    if space is not None:
        origen = space
    elif info.space_deducido is not None:
        origen = info.space_deducido
        if not info.es_imagen:
            avisos.append(
                f"El espacio de origen no se ha pedido; lo he deducido de los metadatos "
                f"del fichero: {origen}."
            )
    else:
        origen = ESPACIO_ASUMIDO_VIDEO
        avisos.append(
            f"El fichero no trae metadatos de color utiles. Asumo {origen} "
            f"(OETF de camara BT.709). Si el material es log, pasa `space=` a mano."
        )

    if info.es_imagen:
        bruto = _leer_imagen(Path(info.ruta))[None, ...]
        if n_fotogramas > 1:
            avisos.append(
                f"Es una imagen fija: hay 1 fotograma y se pedian {n_fotogramas}."
            )
    else:
        bruto, mas_avisos = _decodificar_video(info, n_fotogramas)
        avisos.extend(mas_avisos)

    trabajo = np.stack([to_working(f, origen) for f in bruto]).astype(np.float32)
    return trabajo, tuple(avisos), info, origen


def _decodificar_video(info: InfoMedio, n_fotogramas: int) -> tuple[np.ndarray, list[str]]:
    exe = _binario("ffmpeg")
    p = Path(info.ruta)
    avisos: list[str] = []

    disponibles = info.n_fotogramas if info.n_fotogramas > 0 else n_fotogramas
    k = min(n_fotogramas, disponibles)
    if k < n_fotogramas:
        if disponibles == 1:
            avisos.append("El clip tiene un solo fotograma; se analiza ese.")
        else:
            avisos.append(
                f"El clip solo tiene {disponibles} fotogramas y se pedian {n_fotogramas}; "
                f"se analizan los {k} que hay."
            )

    instantes = _instantes(info, k)
    fotogramas: list[np.ndarray] = []
    fallidos = 0
    for t in instantes:
        f = _decodificar_uno(exe, p, t, info.ancho, info.alto)
        if f is None:
            fallidos += 1
            continue
        fotogramas.append(f)

    if not fotogramas:
        # Ultimo intento: sin buscar, el primer fotograma del fichero.
        f = _decodificar_uno(exe, p, None, info.ancho, info.alto)
        if f is not None:
            return np.stack([f]), [
                *avisos,
                "No he podido leer ningun fotograma por posicion (clip truncado o "
                "indice roto); he analizado solo el primero.",
            ]
        raise ErrorFFmpeg(
            f"ffmpeg no ha conseguido decodificar ni un fotograma de {p.name}. "
            f"El fichero esta truncado, corrupto o el codec no esta soportado."
        )

    if fallidos:
        avisos.append(
            f"{fallidos} de {len(instantes)} fotogramas no se han podido decodificar "
            f"(clip truncado o corrupto); el analisis sale de los {len(fotogramas)} que si."
        )
    return np.stack(fotogramas), avisos


def extraer_fotogramas(
    ruta: str | Path,
    *,
    n_fotogramas: int = N_FOTOGRAMAS_POR_DEFECTO,
    space: ColorSpaceName | None = None,
) -> np.ndarray:
    """(k, alto, ancho, 3) float32 **en el espacio de trabajo**.

    `k` es como mucho `n_fotogramas`, y menos si el clip no da para tanto (una
    imagen fija, un clip de dos fotogramas, o un fichero truncado del que solo se
    salvan algunos).

    `space` es el espacio de ORIGEN del material. Con `None` se intenta deducir de
    los metadatos del fichero y, si no hay manera, se asume `rec709`. Para un EXR
    se asume `linear_rec709`. Ver NOTAS.md.

    Lanza `ErrorAnalisis` (o una hija) con un mensaje en castellano si el fichero
    no existe, no es un medio, esta truncado del todo, o no hay ffmpeg.
    """
    fotogramas, _, _, _ = extraer_fotogramas_con_avisos(
        ruta, n_fotogramas=n_fotogramas, space=space
    )
    return fotogramas


__all__ = [
    "ESPACIO_ASUMIDO_LINEAL",
    "ESPACIO_ASUMIDO_VIDEO",
    "EXTENSIONES_IMAGEN",
    "InfoMedio",
    "N_FOTOGRAMAS_POR_DEFECTO",
    "extraer_fotogramas",
    "extraer_fotogramas_con_avisos",
    "sondear",
]
