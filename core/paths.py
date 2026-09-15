"""Localizacion de binarios externos y rutas del repo.

Las apps lanzadas desde el Dock en macOS NO heredan el PATH del shell, asi que
`shutil.which` puede fallar para ffmpeg aunque en la terminal funcione. Por eso
caemos a las rutas habituales de Homebrew (arm64 y x86_64) antes de rendirnos.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_FALLBACK_DIRS = (
    "/opt/homebrew/bin",  # Homebrew arm64
    "/usr/local/bin",  # Homebrew x86_64 / instalaciones manuales
    "/opt/local/bin",  # MacPorts
    "/usr/bin",
)


class ExecutableNotFound(RuntimeError):
    """El binario externo no esta disponible en esta maquina."""


def resolve_executable(name: str, *, required: bool = True) -> str | None:
    """Devuelve la ruta absoluta de `name`, o None si no esta y required=False."""
    env_override = os.environ.get(f"SIDEBCOLOR_{name.upper()}")
    if env_override and Path(env_override).is_file() and os.access(env_override, os.X_OK):
        return env_override

    found = shutil.which(name)
    if found:
        return found

    for directory in _FALLBACK_DIRS:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    if required:
        raise ExecutableNotFound(
            f"No encuentro '{name}'. Instalalo (brew install {name}) o define "
            f"SIDEBCOLOR_{name.upper()} con la ruta absoluta."
        )
    return None


def ffmpeg() -> str:
    return resolve_executable("ffmpeg")  # type: ignore[return-value]


def ffprobe() -> str:
    return resolve_executable("ffprobe")  # type: ignore[return-value]


def have_ffmpeg() -> bool:
    return resolve_executable("ffmpeg", required=False) is not None
