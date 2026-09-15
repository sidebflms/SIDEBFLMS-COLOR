"""Fixtures compartidas. Propiedad del orquestador.

Si necesitas un fixture que sirva a varios agentes, pidelo. Los tuyos, en tu
propio archivo de test.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import to_working
from core.contracts import WORKING_SPACE
from core.paths import have_ffmpeg
from tests.media import generate as gen


def a_trabajo(img: np.ndarray) -> np.ndarray:
    """Escena-lineal del generador -> espacio de trabajo.

    El generador produce escena-lineal en primarios Rec.709; todo el nucleo
    opera en WORKING_SPACE. Este es el unico puente, y esta aqui para que no
    haya cinco versiones distintas repartidas por los tests.
    """
    return to_working(img, "linear_rec709")


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


@pytest.fixture(scope="session")
def estudio_trabajo(escena_estudio) -> np.ndarray:
    """El retrato de estudio, ya en el espacio de trabajo."""
    return a_trabajo(escena_estudio.image)


@pytest.fixture(scope="session")
def exterior_trabajo(escena_exterior) -> np.ndarray:
    """El exterior, ya en el espacio de trabajo."""
    return a_trabajo(escena_exterior.image)


@pytest.fixture(scope="session")
def pieles_trabajo(escenas_pieles) -> list[np.ndarray]:
    """Los seis tonos de piel, ya en el espacio de trabajo."""
    return [a_trabajo(e.image) for e in escenas_pieles]


@pytest.fixture(scope="session")
def espacio_trabajo() -> str:
    return WORKING_SPACE
