"""`core.reverse.relleno.base_afin`: sólo el camino de error, no la mecánica
de relleno (esa se prueba indirectamente en `tests/test_reverse_bordes.py`
y en los tests de `invertir_grado`).
"""

from __future__ import annotations

import numpy as np

from core.reverse.relleno import base_afin, rejilla_de_entradas


def test_si_eigvalsh_no_converge_cae_a_la_identidad(monkeypatch):
    """Bug real encontrado en revisión: `eigvalsh` no estaba protegido contra
    `LinAlgError`, a diferencia de `solve` en la misma función — pese a que
    el docstring promete que un sistema mal condicionado "se cae con
    elegancia a la identidad". `LinAlgError` en `eigvalsh` es casi imposible
    de provocar con datos reales (la matriz es simétrica por construcción),
    así que se fuerza con monkeypatch: lo que importa es el camino de
    error, no reproducir la causa exacta."""
    n = 5
    entradas = rejilla_de_entradas(n)
    valores = entradas.copy()
    mascara = np.ones((n, n, n), dtype=bool)
    pesos = np.ones((n, n, n), dtype=np.float64)

    def _eigvalsh_que_no_converge(*a, **k):
        raise np.linalg.LinAlgError("Eigenvalues did not converge")

    monkeypatch.setattr(np.linalg, "eigvalsh", _eigvalsh_que_no_converge)
    resultado = base_afin(entradas, valores, mascara, pesos)
    np.testing.assert_array_equal(resultado, entradas)
