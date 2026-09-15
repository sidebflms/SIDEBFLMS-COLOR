"""T3 — IGUALADO DE CUATRO CAMARAS. El test que decide si la noche ha servido.

QUE SE MONTA
------------
Una escena (el retrato de estudio), grabada por cuatro camaras distintas:

    FX3    S-Log3  / S-Gamut3.Cine     exposicion  0.0 EV   (es la referencia)
    Canon  C-Log3  / Cinema Gamut      exposicion -0.7 EV + ganancia calida
    Lumix  V-Log   / V-Gamut           exposicion +0.5 EV + ganancia fria
    DJI    D-Log   / D-Gamut           exposicion +0.9 EV + ganancia leve

Las curvas y los primarios son los de verdad (`core.color.convert`), no una
imitacion a ojo. Encima, cada camara lleva una desviacion de balance y de
exposicion como las que salen de un rodaje: nadie clava el balance en las cuatro.

Luego cada clip se lleva al espacio de trabajo, que es lo que haria la app con
lo que le dice el analisis, y el matcher tiene que devolverlas todas al espacio
de la referencia.

CRITERIO (del encargo, y no se toca)
------------------------------------
ΔE2000 medio entre camaras **< 2.0 despues**, partiendo de **> 8.0 antes**.

CIFRAS REALES MEDIDAS (estan tambien en core/matching/NOTAS.md):

    antes    9.889
    despues  0.296        -> se cumple, con un factor 33 de mejora

Par a par, antes -> despues:

    FX3-Canon    6.893 -> 0.285      Canon-Lumix  13.039 -> 0.477
    FX3-Lumix    6.183 -> 0.195      Canon-DJI    16.711 -> 0.404
    FX3-DJI     10.402 -> 0.190      Lumix-DJI     6.106 -> 0.226
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import convert, delta_e2000_mean
from core.contracts import WORKING_SPACE
from core.matching import delta_e_medio_entre_pares, igualar_camaras
from tests.media import generate as gen

#: nombre, espacio de la camara, exposicion en pasos, ganancia RGB del balance.
CAMARAS: tuple[tuple[str, str, float, tuple[float, float, float]], ...] = (
    ("FX3", "slog3_sgamut3cine", 0.0, (1.00, 1.00, 1.00)),
    ("Canon", "clog3_cinemagamut", -0.7, (1.08, 1.00, 0.88)),
    ("Lumix", "vlog_vgamut", 0.5, (0.93, 1.00, 1.12)),
    ("DJI", "dlog_dgamut", 0.9, (1.04, 0.98, 0.95)),
)

#: El criterio del encargo. NO SE TOCA.
DE_MAXIMO_DESPUES = 2.0
DE_MINIMO_ANTES = 8.0


def cuatro_camaras(*, skin_tone_index: int = 2) -> list[np.ndarray]:
    """La misma escena tal y como la habrian grabado las cuatro, ya en el
    espacio de trabajo (que es donde el nucleo opera, contrato 3)."""
    base = gen.studio_scene(skin_tone_index=skin_tone_index).image.astype(np.float64)
    imagenes = []
    for _, espacio, ev, ganancia in CAMARAS:
        lineal = base * (2.0**ev) * np.asarray(ganancia)
        codificada = convert(lineal.astype(np.float32), "linear_rec709", espacio)  # type: ignore[arg-type]
        imagenes.append(convert(codificada, espacio, WORKING_SPACE).astype(np.float64))  # type: ignore[arg-type]
    return imagenes


@pytest.fixture(scope="module")
def camaras() -> list[np.ndarray]:
    return cuatro_camaras()


# ---------------------------------------------------------------------------
# EL test
# ---------------------------------------------------------------------------


def test_igualado_de_cuatro_camaras(camaras):
    resultado = igualar_camaras(camaras, indice_referencia=0)

    # Las dos cifras del encargo, tal cual salen.
    assert resultado.delta_e_medio_antes > DE_MINIMO_ANTES, (
        f"el montaje no separa bastante las camaras: {resultado.delta_e_medio_antes:.3f}"
    )
    assert resultado.delta_e_medio_despues < DE_MAXIMO_DESPUES, (
        f"no se llega al criterio: {resultado.delta_e_medio_despues:.3f}"
    )

    # Y ademas ningun PAR suelto se queda fuera: la media podria esconder uno.
    peor = max(resultado.delta_e_por_par_despues.values())
    assert peor < DE_MAXIMO_DESPUES, f"el peor par se queda en {peor:.3f}"


def test_todos_los_pares_mejoran_y_ninguno_empeora(camaras):
    resultado = igualar_camaras(camaras, indice_referencia=0)
    for par, antes in resultado.delta_e_por_par_antes.items():
        assert resultado.delta_e_por_par_despues[par] < antes, par


def test_el_igualado_no_toca_la_referencia(camaras):
    resultado = igualar_camaras(camaras, indice_referencia=0)
    assert resultado.emparejamientos[0] is None
    np.testing.assert_array_equal(resultado.corregidas[0], camaras[0])


def test_da_igual_cual_de_las_cuatro_sea_la_referencia(camaras):
    """Si el resultado dependiera mucho de a cual se elige, la herramienta no
    seria de fiar: Mario elige la referencia por criterio artistico."""
    for i in range(len(CAMARAS)):
        resultado = igualar_camaras(camaras, indice_referencia=i)
        assert resultado.delta_e_medio_despues < DE_MAXIMO_DESPUES, CAMARAS[i][0]


def test_funciona_igual_con_piel_oscura():
    """El tono de piel mas oscuro es el que suele romper estas cosas."""
    resultado = igualar_camaras(cuatro_camaras(skin_tone_index=5), indice_referencia=0)
    assert resultado.delta_e_medio_antes > DE_MINIMO_ANTES
    assert resultado.delta_e_medio_despues < DE_MAXIMO_DESPUES


def test_ninguna_camara_sale_marcada_como_otra_escena(camaras):
    """Son la MISMA escena con otra camara y otro balance: si el detector de
    contenido las marcara, no valdria para nada."""
    resultado = igualar_camaras(camaras, indice_referencia=0)
    for nombre, m in zip([c[0] for c in CAMARAS], resultado.emparejamientos, strict=True):
        if m is None:
            continue
        assert m.content_mismatch is False, nombre
        assert m.confidence.level == "alta", (nombre, m.confidence.reasons)


def test_con_lut_tambien_cumple(camaras):
    resultado = igualar_camaras(camaras, indice_referencia=0, con_lut=True)
    assert resultado.delta_e_medio_despues < DE_MAXIMO_DESPUES
    for m in resultado.emparejamientos:
        if m is not None:
            assert m.lut is not None


def test_la_mejora_es_de_mas_de_un_orden_de_magnitud(camaras):
    resultado = igualar_camaras(camaras, indice_referencia=0)
    assert resultado.mejora > 10.0


# ---------------------------------------------------------------------------
# La funcion auxiliar
# ---------------------------------------------------------------------------


def test_delta_e_medio_entre_pares_cuenta_todos_los_pares(camaras):
    medio, por_par = delta_e_medio_entre_pares(camaras)
    assert len(por_par) == 6  # C(4, 2)
    assert medio == pytest.approx(float(np.mean(list(por_par.values()))))


def test_delta_e_medio_de_imagenes_identicas_es_cero(camaras):
    medio, _ = delta_e_medio_entre_pares([camaras[0], camaras[0]])
    assert medio == pytest.approx(0.0, abs=1e-9)


def test_imagenes_de_distinta_forma_lanzan(camaras):
    with pytest.raises(ValueError, match="misma forma"):
        delta_e_medio_entre_pares([camaras[0], camaras[0][:100]])


def test_una_sola_camara_lanza(camaras):
    with pytest.raises(ValueError, match="al menos dos"):
        igualar_camaras([camaras[0]])


def test_referencia_fuera_de_rango_lanza(camaras):
    with pytest.raises(ValueError, match="fuera de rango"):
        igualar_camaras(camaras, indice_referencia=9)


def test_la_conversion_de_camara_es_reversible_de_verdad():
    """Aviso: si esto fallara, el test de las cuatro camaras estaria midiendo el
    error de `core.color` y no el del emparejamiento. Sirve para saber a quien
    mirar cuando se ponga rojo."""
    base = gen.studio_scene(skin_tone_index=2).image.astype(np.float32)
    for _, espacio, _, _ in CAMARAS:
        ida = convert(base, "linear_rec709", espacio)  # type: ignore[arg-type]
        vuelta = convert(ida, espacio, "linear_rec709")  # type: ignore[arg-type]
        assert delta_e2000_mean(vuelta, base, "linear_rec709") < 0.01, espacio
