"""T3 (igualado de cuatro camaras), medido de fuera y por DOS caminos.

LA DECISION QUE HABIA QUE TOMAR, Y POR QUE SE TOMA ASI
------------------------------------------------------
Para fabricar las cuatro camaras hay que convertir la escena a cuatro espacios
de captura y volver. Esa conversion se puede hacer con `core.color.convert`
(que es parte de lo que se esta midiendo) o con `colour-science`.

* Si se hace con el repo, se mide **el emparejador** con las conversiones del
  repo dadas por buenas.
* Si se hace con `colour`, se miden **las dos cosas a la vez**: si las matrices
  del repo estuvieran mal, el emparejador tendria que recuperar tambien ese
  error, y el numero de despues subiria.

Lo honesto es dar **las dos cifras**, y es lo que se hace: `A` con colour y `B`
con el repo. La cifra de titular de este informe es la **A (con colour)**,
porque es la unica de las dos que no da nada por bueno; la B esta al lado
precisamente para poder atribuir la diferencia.

Y hay una tercera medida que las hace interpretables: los primarios de los
cuatro espacios de captura en colour-science coinciden DIGITO A DIGITO con los
de `core/color/spaces.py` (comprobado en `test_metrica.py`), y las cuatro
curvas ya estaban verificadas contra colour en el propio repo. O sea que si A y
B salen parecidas, no es casualidad: es que el puente no aporta diferencia.

Entrada unica al repo: `core.matching.emparejar`. No se llama a
`igualar_camaras`, que es la funcion que el autor del modulo escribio para
probarse a si mismo.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from core.matching import emparejar
from tests.medicion import escena as E
from tests.medicion import metrica as M

pytestmark = pytest.mark.medicion


def _informe(nombre: str, **cifras) -> None:
    linea = "  ".join(f"{k}={v:.6g}" for k, v in cifras.items())
    print(f"\n[MEDICION {nombre}] {linea}")


def _de_medio_entre_pares(imagenes: list[np.ndarray]) -> tuple[float, float]:
    """(media de los 6 pares, peor par). ΔE2000 con colour-science."""
    valores = [
        M.resumen_de(M.delta_e2000_wg(a, b))["medio"]
        for a, b in itertools.combinations(imagenes, 2)
    ]
    return float(np.mean(valores)), float(np.max(valores))


def _camaras_con_colour(lineal: np.ndarray) -> list[np.ndarray]:
    """Las cuatro camaras, convertidas SOLO con colour-science."""
    salida = []
    for i in range(4):
        slope, offset = E.DESVIOS[i]
        captado = E.lineal709_a_camara_colour(lineal, i)
        desviado = E.aplicar_cdl(captado, slope, offset, (1.0, 1.0, 1.0), 1.0)
        salida.append(E.camara_a_trabajo_colour(desviado, i).astype(np.float32))
    return salida


def _camaras_con_el_repo(lineal: np.ndarray) -> list[np.ndarray]:
    """Las mismas cuatro, convertidas con `core.color.convert`.

    Es la variante que da por buenas las conversiones del repo. La desviacion
    de balance sigue siendo MI `aplicar_cdl`, no `CDL.apply`.
    """
    from core.color import convert  # noqa: PLC0415

    salida = []
    for i, espacio in enumerate(E.CAMARAS_REPO):
        slope, offset = E.DESVIOS[i]
        captado = convert(lineal.astype(np.float64), "linear_rec709", espacio)
        desviado = E.aplicar_cdl(captado, slope, offset, (1.0, 1.0, 1.0), 1.0)
        salida.append(
            convert(desviado, espacio, "davinci_wg_intermediate").astype(np.float32)
        )
    return salida


def _igualar(camaras: list[np.ndarray]) -> list[np.ndarray]:
    """La FX3 manda; las otras tres se llevan a ella con `emparejar`."""
    referencia = camaras[0]
    igualadas = [referencia]
    for imagen in camaras[1:]:
        match = emparejar(imagen.reshape(-1, 3), referencia.reshape(-1, 3))
        igualadas.append(match.cdl.apply(imagen).astype(np.float32))
    return igualadas


def _medir(nombre: str, camaras: list[np.ndarray]) -> tuple[float, float]:
    antes, peor_antes = _de_medio_entre_pares(camaras)
    igualadas = _igualar(camaras)
    despues, peor_despues = _de_medio_entre_pares(igualadas)
    _informe(
        nombre,
        antes=antes,
        despues=despues,
        mejora=antes / max(despues, 1e-9),
        peor_par_antes=peor_antes,
        peor_par_despues=peor_despues,
    )
    return antes, despues


def test_T3_igualado_de_cuatro_camaras_A_conversiones_de_colour():
    """LA CIFRA DE TITULAR. Criterio publicado: > 8.0 antes y < 2.0 despues.
    Publicado: 17.674 -> 0.661."""
    antes, despues = _medir("T3-A-colour", _camaras_con_colour(E.escena_lineal()))
    assert antes > 8.0, f"mi montaje no parte de suficiente desajuste: {antes:.3f}"
    assert despues < 2.0, f"no llega al criterio: {despues:.3f}"


def test_T3_igualado_de_cuatro_camaras_B_conversiones_del_repo():
    """La misma medida dando por buenas las conversiones de `core.color`.

    Si A y B salen iguales, el puente de espacios del repo no aporta error y la
    cifra del T3 mide el emparejador y nada mas.
    """
    antes, despues = _medir("T3-B-repo", _camaras_con_el_repo(E.escena_lineal()))
    assert antes > 8.0, f"mi montaje no parte de suficiente desajuste: {antes:.3f}"
    assert despues < 2.0, f"no llega al criterio: {despues:.3f}"


def test_T3_cuanto_se_separan_los_dos_caminos():
    """La diferencia entre A y B, pixel a pixel, camara a camara."""
    lineal = E.escena_lineal()
    a = _camaras_con_colour(lineal)
    b = _camaras_con_el_repo(lineal)
    peor = 0.0
    for i, (x, y) in enumerate(zip(a, b, strict=True)):
        de = M.resumen_de(M.delta_e2000_wg(x, y))
        print(
            f"\n[MEDICION T3-caminos] camara={E.CAMARAS_COLOUR[i][0]!r} "
            f"de_medio={de['medio']:.6g} de_max={de['max']:.6g}"
        )
        peor = max(peor, de["max"])
    assert peor < 0.05, (
        f"las conversiones de colour y las del repo no llevan las camaras al mismo sitio: "
        f"{peor:.4f} ΔE2000 en el peor pixel"
    )


def test_T3_ningun_par_suelto_se_esconde_detras_de_la_media():
    """Una media de 0.6 con un par a 5 seria una media que miente."""
    igualadas = _igualar(_camaras_con_colour(E.escena_lineal()))
    _, peor = _de_medio_entre_pares(igualadas)
    _informe("T3-peor-par", peor=peor)
    assert peor < 2.0, f"el peor par se queda en {peor:.3f}"
