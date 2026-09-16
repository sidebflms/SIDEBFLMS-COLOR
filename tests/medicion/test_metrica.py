"""PASO 0: validar mi vara de medir antes de medir nada con ella.

Si esto no pasa, ninguna de las cuatro cifras de abajo significa nada.

Tres comprobaciones:

1. Mi ΔE2000 contra los 34 pares de Sharma, Wu y Dalal (2005).
2. Mi camino de conversion (DWG/DI -> XYZ -> L*a*b*) contra el del repo.
3. Mi CDL y mi trilineal contra los del repo, para saber si la eleccion de
   con que fabrico el coloreado cambia o no las cifras.
"""

from __future__ import annotations

import numpy as np
import pytest
from colour.difference import delta_E_CIE2000

from tests.medicion import escena as E
from tests.medicion import metrica as M

pytestmark = pytest.mark.medicion


def _informe(nombre: str, **cifras) -> None:
    linea = "  ".join(f"{k}={v:.6g}" for k, v in cifras.items())
    print(f"\n[MEDICION {nombre}] {linea}")


def test_mi_delta_e2000_pasa_los_34_pares_de_sharma():
    """El estandar para verificar una implementacion de CIEDE2000."""
    r = M.validar_contra_sharma(delta_E_CIE2000)
    _informe("sharma-mio", **r)
    assert r["error_max"] < 1e-4, f"mi ΔE2000 se desvia de Sharma: {r['error_max']:.2e}"


def test_el_delta_e2000_del_repo_tambien_pasa_los_34_pares_de_sharma():
    """La otra mitad: si el del repo tambien pasa, la metrica no es el problema."""
    from core.color import delta_e2000_lab

    r = M.validar_contra_sharma(lambda a, b: delta_e2000_lab(a, b))
    _informe("sharma-repo", **r)
    assert r["error_max"] < 1e-4, f"el ΔE2000 del repo se desvia de Sharma: {r['error_max']:.2e}"


def test_mi_camino_de_espacios_coincide_con_el_del_repo():
    """DWG/DI -> L*a*b* por los dos caminos, sobre mi escena entera.

    Si esto NO coincidiera seria el hallazgo mas importante del dia: querria
    decir que el puente de espacios del repo lleva los colores a otro sitio
    que el de colour-science, y entonces todos los ΔE publicados estarian
    medidos en otra regla.
    """
    img = E.escena_trabajo()
    coloreada = E.coloreado(img, E.tabla_lut_conocida())
    r = M.comparar_con_el_repo(img, coloreada)
    _informe("camino-espacios", **r)
    assert r["lab_error_max"] < 1e-6, f"los dos L*a*b* no coinciden: {r['lab_error_max']:.3e}"
    assert r["de_error_max"] < 1e-6, f"los dos ΔE2000 no coinciden: {r['de_error_max']:.3e}"


def test_los_primarios_de_las_cuatro_camaras_coinciden():
    """colour-science y `core/color/spaces.py`, cromaticidad a cromaticidad."""
    import colour

    from core.color import SPACES

    peor = 0.0
    for (_, nombre_colour, _), nombre_repo in zip(
        E.CAMARAS_COLOUR, E.CAMARAS_REPO, strict=True
    ):
        a = np.asarray(colour.RGB_COLOURSPACES[nombre_colour].primaries, dtype=np.float64)
        b = np.asarray(SPACES[nombre_repo].primaries, dtype=np.float64)
        peor = max(peor, float(np.abs(a - b).max()))
    _informe("primarios-camaras", error_max=peor)
    assert peor == 0.0, f"los primarios no son los mismos: {peor:.3e}"


def test_mi_cdl_y_mi_trilineal_contra_los_del_repo():
    """Con que fabrico el coloreado, ¿cambia la cifra?

    Si mi CDL y mi trilineal dan lo mismo que `CDL.apply` y `LUT3D.apply`, la
    eleccion es irrelevante y el T1 no depende de ella. Si dieran distinto,
    habria que decir cual se uso y por que.
    """
    from core.contracts import CDL, LUT3D

    img = E.escena_trabajo().astype(np.float64)
    tabla = E.tabla_lut_conocida()

    cdl_repo = CDL(slope=E.CDL_SLOPE, offset=E.CDL_OFFSET, power=E.CDL_POWER,
                   saturation=E.CDL_SAT)
    err_cdl = float(np.abs(E.aplicar_cdl(img) - cdl_repo.apply(img)).max())

    lut_repo = LUT3D(table=tabla.astype(np.float32))
    base = E.aplicar_cdl(img)
    # La tabla del repo es float32 por contrato, asi que se compara contra la
    # MISMA tabla en float32; si no, se estaria midiendo el redondeo de dtype.
    err_lut = float(
        np.abs(E.aplicar_lut(tabla.astype(np.float32).astype(np.float64), base)
               - lut_repo.apply(base)).max()
    )
    _informe("cdl-y-trilineal", error_max_cdl=err_cdl, error_max_trilineal=err_lut)
    assert err_cdl < 1e-9, f"mi CDL y el del repo difieren: {err_cdl:.3e}"
    assert err_lut < 1e-9, f"mi trilineal y la del repo difieren: {err_lut:.3e}"
