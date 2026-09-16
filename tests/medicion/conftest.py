"""Configuracion local del arnes de medicion independiente.

NO importa `tests/conftest.py` ni ninguna de sus fixtures: el material de esta
carpeta se fabrica aqui. Lo unico que hace es registrar el marcador `medicion`,
porque el proyecto corre con `--strict-markers` y `pyproject.toml` no es mio.
"""

from __future__ import annotations


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "medicion: medicion independiente de las cuatro cifras de titular (no es codigo de produccion)",
    )
