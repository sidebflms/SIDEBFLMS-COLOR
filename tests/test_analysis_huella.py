"""La huella de contenido, y sobre todo LA prueba que la justifica.

Una huella que cambiara al graduar el plano no serviria para nada. Aqui se le
aplica a la misma escena un CDL fuerte y un LUT de look y se exige que la huella
siga diciendo que es el mismo plano; y a la vez, que un retrato de estudio y un
exterior al sol no se parezcan.

Los dos numeros medidos estan en `core/analysis/NOTAS.md` §3, y salen impresos en
el propio test si falla.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.analysis import (
    analizar_imagen,
    huella_de_contenido,
    parecido_de_huellas,
)
from core.contracts import CDL, FINGERPRINT_LEN
from core.io.lut_malos import lut_desde_curvas
from tests.conftest import a_trabajo

#: El CDL con el que se prueba la invariancia. No es sutil a proposito: cambia
#: los tres canales por separado, mete offset, cambia la gamma canal a canal y
#: sube la saturacion casi un 50%.
CDL_FUERTE = CDL(
    slope=(1.35, 0.92, 0.72),
    offset=(0.03, -0.02, 0.06),
    power=(0.85, 1.05, 1.25),
    saturation=1.45,
)


def lut_de_look(size: int = 33):
    """LUT separable con curva en S en el rojo y gamma distinta en verde y azul.

    La S es `t - 0.12*sin(2*pi*t)`, que es **monotona creciente** (su derivada,
    1 - 0.12*2*pi*cos, no llega a cambiar de signo porque 0.12 < 1/(2*pi)). Eso
    importa: un LUT no monotono no es un look, es un LUT roto, y para esos esta
    el QC del agente D.
    """
    t = np.linspace(0.0, 1.0, size)
    ese = np.clip(t - 0.12 * np.sin(2 * np.pi * t), 0.0, 1.0)
    assert np.all(np.diff(ese) > 0), "la curva en S de este test tiene que ser monotona"
    return lut_desde_curvas(ese, np.clip(t**1.06, 0, 1), np.clip(t**1.15, 0, 1), title="Look")


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------


def test_forma_tipo_y_norma(estudio_trabajo, exterior_trabajo, rampa, carta):
    for img in (estudio_trabajo, exterior_trabajo, a_trabajo(rampa), a_trabajo(carta)):
        h = huella_de_contenido(img)
        assert h.shape == (FINGERPRINT_LEN,)
        assert h.dtype == np.float32
        assert float(np.linalg.norm(h)) == pytest.approx(1.0, abs=1e-6)


def test_una_huella_consigo_misma_es_uno(estudio_trabajo):
    h = huella_de_contenido(estudio_trabajo)
    assert parecido_de_huellas(h, h) == pytest.approx(1.0, abs=1e-6)


def test_es_determinista(estudio_trabajo):
    a = huella_de_contenido(estudio_trabajo)
    b = huella_de_contenido(estudio_trabajo)
    assert np.array_equal(a, b)


def test_parecido_rechaza_vectores_de_otro_tamano(estudio_trabajo):
    h = huella_de_contenido(estudio_trabajo)
    with pytest.raises(ValueError, match="96"):
        parecido_de_huellas(h, np.zeros(10))
    with pytest.raises(ValueError, match="96"):
        parecido_de_huellas(np.zeros(95), h)


def test_el_parecido_nunca_se_sale_de_0_1(estudio_trabajo, exterior_trabajo, carta, rampa):
    huellas = [
        huella_de_contenido(i)
        for i in (estudio_trabajo, exterior_trabajo, a_trabajo(carta), a_trabajo(rampa))
    ]
    for a in huellas:
        for b in huellas:
            assert 0.0 <= parecido_de_huellas(a, b) <= 1.0


# ---------------------------------------------------------------------------
# LA prueba: invariancia al grado Y separacion entre escenas
# ---------------------------------------------------------------------------


def test_la_huella_aguanta_el_grado_y_separa_las_escenas(estudio_trabajo, exterior_trabajo):
    """Las dos cosas a la vez, que es lo dificil.

    Numeros medidos hoy (los mismos que estan en NOTAS.md §3):

    | que se mide | valor |
    |---|---|
    | estudio vs estudio + CDL fuerte | 0,9988 |
    | estudio vs estudio + LUT de look | 0,9979 |
    | **estudio vs estudio + CDL + LUT** | **0,9967** |
    | **estudio vs exterior** | **0,0000** (coseno crudo -0,0198) |

    Los umbrales de abajo dejan margen de sobra respecto a lo medido: no estan
    puestos al ras para que pase, estan puestos donde deja de ser cierto lo que
    se afirma.
    """
    lut = lut_de_look()
    original = huella_de_contenido(estudio_trabajo)
    solo_cdl = huella_de_contenido(CDL_FUERTE.apply(estudio_trabajo).astype(np.float32))
    solo_lut = huella_de_contenido(lut.apply(estudio_trabajo).astype(np.float32))
    ambos = huella_de_contenido(
        lut.apply(CDL_FUERTE.apply(estudio_trabajo)).astype(np.float32)
    )

    invariancia = parecido_de_huellas(original, ambos)
    separacion = parecido_de_huellas(original, huella_de_contenido(exterior_trabajo))

    assert parecido_de_huellas(original, solo_cdl) > 0.97, (
        f"el CDL mueve la huella: {parecido_de_huellas(original, solo_cdl):.4f}"
    )
    assert parecido_de_huellas(original, solo_lut) > 0.97, (
        f"el LUT mueve la huella: {parecido_de_huellas(original, solo_lut):.4f}"
    )
    assert invariancia > 0.95, f"invariancia al grado: {invariancia:.4f}"
    assert separacion < 0.25, f"separacion estudio/exterior: {separacion:.4f}"
    # Y lo que de verdad hace falta: que haya un hueco enorme entre las dos.
    assert invariancia - separacion > 0.7


def test_el_grado_cambia_el_color_de_verdad(estudio_trabajo):
    """Control del test de arriba: si el grado no hiciera nada, no probaria nada."""
    from core.analysis import estadisticas

    lut = lut_de_look()
    graduado = lut.apply(CDL_FUERTE.apply(estudio_trabajo)).astype(np.float32)
    antes = estadisticas(estudio_trabajo)
    despues = estadisticas(graduado)
    assert np.abs(despues.mean - antes.mean).max() > 0.05, "el grado casi no ha hecho nada"
    tvd = 0.5 * np.abs(despues.saturation_hist - antes.saturation_hist).sum()
    assert tvd > 0.2, f"la saturacion casi no se ha movido (TVD {tvd:.3f})"


def test_la_saturacion_sola_no_toca_la_huella(estudio_trabajo):
    """La formula del CDL deja la luma Rec.709 EXACTAMENTE igual al saturar, y la
    huella es toda de luma: asi que esto tiene que salir practicamente 1."""
    saturado = CDL(saturation=2.5).apply(estudio_trabajo).astype(np.float32)
    parecido = parecido_de_huellas(
        huella_de_contenido(estudio_trabajo), huella_de_contenido(saturado)
    )
    assert parecido > 0.999, parecido


def test_separa_tambien_de_la_carta_y_de_la_rampa(estudio_trabajo, carta, rampa):
    h = huella_de_contenido(estudio_trabajo)
    assert parecido_de_huellas(h, huella_de_contenido(a_trabajo(carta))) < 0.25
    assert parecido_de_huellas(h, huella_de_contenido(a_trabajo(rampa))) < 0.25


def test_el_mismo_plano_con_otra_piel_sigue_siendo_el_mismo_plano(pieles_trabajo):
    """Seis tonos de piel sobre la MISMA composicion: tienen que parecerse."""
    huellas = [huella_de_contenido(p) for p in pieles_trabajo]
    fuera_de_diagonal = [
        parecido_de_huellas(huellas[i], huellas[j])
        for i in range(len(huellas))
        for j in range(len(huellas))
        if i != j
    ]
    peor = min(fuera_de_diagonal)
    assert peor > 0.6, f"el peor par de tonos de piel se parece {peor:.4f}"


def test_aguanta_un_cambio_de_exposicion(escena_estudio):
    """+-2 pasos de luz. Medido: 0,958 y 0,949."""
    from tests.media import generate as gen

    base = huella_de_contenido(a_trabajo(escena_estudio.image))
    for ev in (2.0, -2.0):
        otra = a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=ev).image)
        assert parecido_de_huellas(base, huella_de_contenido(otra)) > 0.9, ev


# ---------------------------------------------------------------------------
# Casos degenerados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "img",
    [
        np.zeros((16, 16, 3), np.float32),
        np.ones((16, 16, 3), np.float32),
        np.full((16, 16, 3), 0.37, np.float32),
        np.full((1, 1, 3), 0.37, np.float32),
        np.full((1, 64, 3), 0.37, np.float32),
    ],
    ids=["negra", "blanca", "un color", "un pixel", "una fila"],
)
def test_las_imagenes_planas_dan_el_vector_uniforme(img):
    h = huella_de_contenido(img)
    assert float(np.linalg.norm(h)) == pytest.approx(1.0, abs=1e-6)
    assert np.allclose(h, 1.0 / np.sqrt(FINGERPRINT_LEN), atol=1e-6)


def test_dos_planas_se_parecen_entre_si_y_nada_a_un_plano_real(estudio_trabajo):
    negra = huella_de_contenido(np.zeros((8, 8, 3), np.float32))
    blanca = huella_de_contenido(np.ones((8, 8, 3), np.float32))
    assert parecido_de_huellas(negra, blanca) == pytest.approx(1.0, abs=1e-6)
    assert parecido_de_huellas(negra, huella_de_contenido(estudio_trabajo)) < 0.05


def test_una_huella_de_norma_cero_no_revienta_el_parecido(estudio_trabajo):
    h = huella_de_contenido(estudio_trabajo)
    assert parecido_de_huellas(h, np.zeros(FINGERPRINT_LEN)) == 0.0


def test_formas_imposibles():
    with pytest.raises(ValueError, match="esperaba"):
        huella_de_contenido(np.zeros((10, 10)))
    with pytest.raises(ValueError, match="ni un pixel"):
        huella_de_contenido(np.zeros((0, 10, 3)))


def test_el_nan_no_rompe_la_norma(estudio_trabajo):
    """La huella es lo unico del modulo que NO propaga NaN: el contrato exige
    norma 1 y un NaN la haria imposible. El aviso queda en `ClipAnalysis`."""
    sucia = np.array(estudio_trabajo, copy=True)
    sucia[10:20, 10:20] = np.nan
    h = huella_de_contenido(sucia)
    assert np.isfinite(h).all()
    assert float(np.linalg.norm(h)) == pytest.approx(1.0, abs=1e-6)
    assert parecido_de_huellas(h, huella_de_contenido(estudio_trabajo)) > 0.95
    assert any("no finitos" in w for w in analizar_imagen(sucia, clip_id="x").warnings)


def test_todo_nan_tambien_da_una_huella_valida():
    h = huella_de_contenido(np.full((8, 8, 3), np.nan, np.float32))
    assert float(np.linalg.norm(h)) == pytest.approx(1.0, abs=1e-6)
