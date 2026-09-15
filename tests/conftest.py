"""Fixtures compartidas. Propiedad del orquestador.

Si necesitas un fixture que sirva a varios agentes, pidelo. Los tuyos, en tu
propio archivo de test.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.paths import have_ffmpeg
from tests.media import generate as gen


@pytest.fixture(scope="session")
def rng() -> np.random.Generator:
    return np.random.default_rng(gen.SEED)


@pytest.fixture(scope="session")
def carta() -> np.ndarray:
    """ColorChecker de 24 parches, escena-lineal."""
    return gen.colorchecker()


@pytest.fixture(scope="session")
def escena_estudio() -> gen.Scene:
    """Retrato de estudio, tono de piel medio."""
    return gen.studio_scene(skin_tone_index=2)


@pytest.fixture(scope="session")
def escenas_pieles() -> list[gen.Scene]:
    """Los seis tonos de piel. Si algo solo funciona con pieles claras, aqui se ve."""
    return [gen.studio_scene(skin_tone_index=i) for i in range(len(gen.SKIN_TONES_SRGB))]


@pytest.fixture(scope="session")
def escena_exterior() -> gen.Scene:
    """Exterior. Deliberadamente incompatible con el retrato de estudio."""
    return gen.exterior_scene()


@pytest.fixture(scope="session")
def rampa() -> np.ndarray:
    return gen.ramp_gray()


@pytest.fixture
def salida(tmp_path):
    """Carpeta temporal de escritura. NUNCA se escribe fuera de aqui."""
    d = tmp_path / "salida"
    d.mkdir()
    return d


requiere_ffmpeg = pytest.mark.skipif(not have_ffmpeg(), reason="ffmpeg no esta instalado")
