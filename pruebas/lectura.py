"""Leer fotogramas del origen con ffmpeg, en sentido unico: del disco a la memoria.

GARANTIAS DE ESTE ARCHIVO
-------------------------
- Todas las llamadas a ffmpeg pasan por `_ffmpeg_a_memoria`, que **exige** que la
  salida sea `pipe:1` (la memoria del proceso) y rechaza cualquier orden que
  lleve `-y`, `-report` o un segundo destino. ffmpeg no puede escribir un fichero
  si no se le da uno.
- Se borra `FFREPORT` del entorno: con esa variable puesta ffmpeg escribe un
  registro en la carpeta actual. Y la carpeta actual del proceso es `/`, donde
  no se puede escribir de todas formas.
- Los metadatos salen de `core.analysis.sondear` (ffprobe), que tampoco escribe.

LOS TRES MODOS DE LECTURA
-------------------------
1. `recorrer(ruta, ancho, fps=None)`: todo el clip a baja resolucion, fotograma
   a fotograma, como un generador. Para escanear el master (`fps=None`: todos
   los fotogramas, sin duplicar ni tirar ninguno) y los brutos (`fps=2`: dos
   muestras por segundo).
2. `ventana(ruta, info, primero, n, ancho)`: `n` fotogramas consecutivos a partir
   del indice `primero`. Para afinar a que fotograma exacto corresponde.
3. `fotograma_completo(ruta, info, indice)`: un fotograma a resolucion completa,
   16 bits sin perdida. Es lo que se mide.

El indice de fotograma se traduce a instante con el mismo truco que
`core.analysis.frames`: pedir `(indice - 0.5) / fps` con `-ss` antes de `-i`, que
devuelve exactamente el fotograma `indice` (medido alli y aqui).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from core.analysis import InfoMedio, sondear
from core.paths import ffmpeg as _ruta_ffmpeg

__all__ = [
    "ErrorLectura",
    "InfoMedio",
    "alto_para",
    "fotograma_completo",
    "recorrer",
    "sondear",
    "ventana",
]

#: Segundos antes de dar por colgada una lectura corta (ventana o fotograma).
TIMEOUT_CORTO_S: float = 300.0

_PROHIBIDO_EN_ORDEN: frozenset[str] = frozenset({"-y", "-report", "-f_strict", "-dump_attachment"})


class ErrorLectura(RuntimeError):
    """ffmpeg no ha podido leer lo que se le pedia."""


def alto_para(info: InfoMedio, ancho: int) -> int:
    """Alto par que conserva la proporcion del fichero a `ancho` pixeles."""
    alto = int(round(ancho * info.alto / max(info.ancho, 1) / 2.0)) * 2
    return max(alto, 2)


def _orden(args: list[str]) -> tuple[list[str], dict[str, str]]:
    if not args or args[-1] != "pipe:1":
        raise ErrorLectura("orden de ffmpeg sin `pipe:1` al final: me niego a lanzarla")
    if sum(1 for a in args if a.startswith("pipe:")) != 1:
        raise ErrorLectura("orden de ffmpeg con mas de un destino: me niego a lanzarla")
    for a in args:
        if a in _PROHIBIDO_EN_ORDEN:
            raise ErrorLectura(f"orden de ffmpeg con `{a}`: me niego a lanzarla")
    cmd = [_ruta_ffmpeg(), "-nostdin", "-hide_banner", "-v", "error", "-n", *args]
    entorno = {k: v for k, v in os.environ.items() if k != "FFREPORT"}
    return cmd, entorno


def _ffmpeg_a_memoria(args: list[str], timeout: float = TIMEOUT_CORTO_S) -> bytes:
    cmd, entorno = _orden(args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout, check=False, env=entorno, cwd="/"
        )
    except subprocess.TimeoutExpired as e:
        raise ErrorLectura(f"ffmpeg se ha colgado mas de {timeout:.0f} s") from e
    if proc.returncode != 0:
        detalle = proc.stderr.decode(errors="replace").strip().splitlines()
        raise ErrorLectura(detalle[-1] if detalle else f"ffmpeg salio con {proc.returncode}")
    return proc.stdout


def _instante(indice: int, fps: float) -> float | None:
    if indice <= 0 or fps <= 0:
        return None
    return (indice - 0.5) / fps


def _a_float(crudo: bytes, alto: int, ancho: int, n: int) -> np.ndarray:
    por = alto * ancho * 3 * 2
    k = min(n, len(crudo) // por)
    if k == 0:
        return np.zeros((0, alto, ancho, 3), dtype=np.float32)
    arr = np.frombuffer(crudo[: k * por], dtype="<u2").reshape(k, alto, ancho, 3)
    return arr.astype(np.float32) / 65535.0


def recorrer(
    ruta: str | Path, info: InfoMedio, ancho: int, *, fps: float | None = None
) -> Iterator[np.ndarray]:
    """Genera fotogramas (alto, ancho, 3) float32 0..1 en valores de codigo."""
    alto = alto_para(info, ancho)
    filtro = f"scale={ancho}:{alto}:flags=area"
    if fps is not None:
        filtro = f"fps={fps:g}," + filtro
    args = ["-i", str(ruta), "-map", "0:v:0", "-vf", filtro]
    if fps is None:
        args += ["-fps_mode", "passthrough"]
    args += ["-f", "rawvideo", "-pix_fmt", "rgb48le", "pipe:1"]
    cmd, entorno = _orden(args)
    por = alto * ancho * 3 * 2
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=entorno,
        cwd="/",
    )
    assert proc.stdout is not None
    try:
        while True:
            crudo = proc.stdout.read(por)
            if not crudo or len(crudo) < por:
                break
            arr = np.frombuffer(crudo, dtype="<u2").reshape(alto, ancho, 3)
            yield arr.astype(np.float32) / 65535.0
    finally:
        proc.stdout.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
        if proc.stderr is not None:
            proc.stderr.close()


def ventana(
    ruta: str | Path, info: InfoMedio, primero: int, n: int, ancho: int | None
) -> np.ndarray:
    """(k, alto, ancho, 3) con los fotogramas `primero .. primero+n-1` (k <= n)."""
    primero = max(int(primero), 0)
    if ancho is None:
        ancho_s, alto_s = info.ancho, info.alto
    else:
        ancho_s, alto_s = int(ancho), alto_para(info, int(ancho))
    args: list[str] = []
    t = _instante(primero, info.fps)
    if t is not None:
        args += ["-ss", f"{t:.6f}"]
    args += ["-i", str(ruta), "-map", "0:v:0", "-frames:v", str(int(n))]
    if ancho is not None:
        args += ["-vf", f"scale={ancho_s}:{alto_s}:flags=area"]
    args += ["-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb48le", "pipe:1"]
    return _a_float(_ffmpeg_a_memoria(args), alto_s, ancho_s, int(n))


def fotograma_completo(ruta: str | Path, info: InfoMedio, indice: int) -> np.ndarray:
    """(alto, ancho, 3) uint16: los valores de codigo tal cual, sin perdida."""
    f = ventana(ruta, info, indice, 1, None)
    if f.shape[0] == 0:
        raise ErrorLectura(f"no he podido leer el fotograma {indice} de {Path(ruta).name}")
    return np.round(f[0] * 65535.0).astype(np.uint16)
