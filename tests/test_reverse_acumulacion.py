"""`core.reverse.acumulacion.pesos_trilineales`: sólo la validación de
entrada, no la mecánica del reparto trilineal (esa se prueba indirectamente
en `tests/test_entregables.py` y `tests/test_reverse_lote.py`).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.reverse.acumulacion import pesos_trilineales


def test_una_ultima_dimension_distinta_de_tres_lanza_con_mensaje_claro():
    """Bug real encontrado en revisión: a diferencia de
    `core.reverse.alineado.alinear` (que valida la forma explícitamente),
    esta función dejaba que `.reshape(-1, 3)` fallara en crudo -- o, peor,
    reshapeara en silencio una entrada con forma equivocada si el número
    total de elementos era casualidad divisible por 3."""
    rgba = np.zeros((4, 4, 4), dtype=np.float64)  # (h, w, 4): RGBA por error
    with pytest.raises(ValueError, match=r"esperaba \(\.\.\., 3\)"):
        pesos_trilineales(rgba, n=17)


def test_una_entrada_con_total_casualmente_divisible_por_tres_tambien_lanza():
    """El caso peligroso de verdad: sin la guarda, esto NO fallaría al hacer
    `.reshape(-1, 3)` (24 elementos son divisibles por 3), y mezclaría
    colores de píxeles distintos en silencio en vez de avisar."""
    forma_rara = np.zeros((2, 3, 4), dtype=np.float64)  # 24 elementos, no es (..., 3)
    with pytest.raises(ValueError, match=r"esperaba \(\.\.\., 3\)"):
        pesos_trilineales(forma_rara, n=17)


def test_una_forma_valida_no_lanza():
    px = np.array([[0.1, 0.2, 0.3], [0.9, 0.8, 0.7]], dtype=np.float64)
    idx, w = pesos_trilineales(px, n=17)
    assert idx.shape == (8, 2)
    assert w.shape == (8, 2)
    np.testing.assert_allclose(w.sum(axis=0), 1.0, atol=1e-9)
