"""`core.reverse.orden_repaso`: aritmética del ORDEN, con casos calculados a
mano. No es una calibración (eso ya se hizo, ver `tests/calibracion_destino/
ordenar.py` y `CIFRAS.md` §14): aquí sólo se comprueba que la función hace lo
que dice que hace — ordena de peor a mejor, y normaliza por clase antes de
comparar.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.reverse.confianza_destino import FeaturesDestino
from core.reverse.orden_repaso import (
    _ESTADISTICAS_POR_CLASE,
    CandidatoOrden,
    ClaseMaterial,
    orden_de_repaso,
)


def _features(cobertura: float, muestras_p10: float = 100.0, planos: int = 1) -> FeaturesDestino:
    return FeaturesDestino(
        cobertura_destino=cobertura,
        muestras_p10_zona=muestras_p10,
        muestras_mediana_zona=muestras_p10,
        variance_zona=0.0,  # excluido a proposito de la puntuacion: cualquier valor da igual
        planos_acumulados=planos,
        n_pixeles_destino=1000,
    )


# ---------------------------------------------------------------------------
# Orden basico, misma clase
# ---------------------------------------------------------------------------


def test_dentro_de_la_misma_clase_ordena_por_cobertura_de_peor_a_mejor():
    clase = ClaseMaterial(tam_rejilla=33, compresion=False, recorte=False)
    peor = CandidatoOrden(id="peor", features=_features(0.30), clase=clase)
    medio = CandidatoOrden(id="medio", features=_features(0.70), clase=clase)
    mejor = CandidatoOrden(id="mejor", features=_features(0.99), clase=clase)
    # a proposito en un orden de entrada que no es el orden esperado
    orden = orden_de_repaso([mejor, peor, medio])
    assert orden == ["peor", "medio", "mejor"]


def test_mas_muestras_en_la_zona_tambien_cuenta_a_favor():
    clase = ClaseMaterial(tam_rejilla=33, compresion=False, recorte=False)
    pocas = CandidatoOrden(id="pocas", features=_features(0.80, muestras_p10=1.0), clase=clase)
    muchas = CandidatoOrden(id="muchas", features=_features(0.80, muestras_p10=5000.0), clase=clase)
    orden = orden_de_repaso([muchas, pocas])
    assert orden == ["pocas", "muchas"]


# ---------------------------------------------------------------------------
# La normalizacion por clase puede CAMBIAR el orden que darian las senales
# crudas: es la hipotesis central del encargo del dia 6, probada con un caso
# a mano.
# ---------------------------------------------------------------------------


def test_normalizar_por_clase_puede_invertir_el_orden_de_la_cobertura_cruda():
    """Clase A (17, comprimido, sin recorte): cobertura media medida 0.8638,
    desviacion 0.1685 — es una clase donde el LUT cubre mucho por defecto.
    Clase B (33, sin comprimir, con recorte): media 0.6502, desviacion
    0.3026 — una clase mas dificil, donde cubrir menos es lo normal.

    Un candidato de la clase A con cobertura 0.87 (justo por encima de SU
    media: para su clase, del monton) tiene, en crudo, mas cobertura que uno
    de la clase B con 0.85. Pero 0.85 en la clase B esta muy por encima de SU
    media (z ~ 0.66), mientras que 0.87 en la clase A esta pegado a la suya
    (z ~ 0.04). El orden calibrado por clase tiene que decir que A necesita
    MAS repaso que B, aunque en crudo A tenga mas cobertura: es exactamente
    lo que se midio en `CALIBRACION-CONFIANZA-DESTINO.md` (el umbral de
    "cobertura buena" no es el mismo en las dos clases).
    """
    clase_a = ClaseMaterial(tam_rejilla=17, compresion=True, recorte=False)
    clase_b = ClaseMaterial(tam_rejilla=33, compresion=False, recorte=True)
    media_log_muestras_a = _ESTADISTICAS_POR_CLASE[(17, True, False)][2]
    media_log_planos_a = _ESTADISTICAS_POR_CLASE[(17, True, False)][4]
    media_log_muestras_b = _ESTADISTICAS_POR_CLASE[(33, False, True)][2]
    media_log_planos_b = _ESTADISTICAS_POR_CLASE[(33, False, True)][4]
    # muestras_p10 y planos_acumulados puestos exactamente en la media de su
    # propia clase: su z-score da 0, y lo unico que mueve la puntuacion final
    # es la cobertura. Aisla la comparacion que se quiere probar.
    a = CandidatoOrden(
        id="clase_A_cobertura_alta_en_crudo",
        features=_features(0.87, muestras_p10=float(np.expm1(media_log_muestras_a)),
                            planos=round(float(np.expm1(media_log_planos_a)))),
        clase=clase_a,
    )
    b = CandidatoOrden(
        id="clase_B_cobertura_baja_en_crudo",
        features=_features(0.85, muestras_p10=float(np.expm1(media_log_muestras_b)),
                            planos=round(float(np.expm1(media_log_planos_b)))),
        clase=clase_b,
    )
    assert a.features.cobertura_destino > b.features.cobertura_destino  # confirma la premisa: en crudo, A > B

    orden = orden_de_repaso([a, b])
    assert orden == ["clase_A_cobertura_alta_en_crudo", "clase_B_cobertura_baja_en_crudo"], (
        "el orden calibrado por clase tiene que poner primero (peor) a A, aunque su "
        "cobertura cruda sea mayor: para SU clase, A esta en la media; B esta muy por "
        "encima de la suya"
    )


# ---------------------------------------------------------------------------
# Clase "desconocida" (compresion/recorte = None): el caso normal en
# produccion, ver el docstring del modulo.
# ---------------------------------------------------------------------------


def test_clase_desconocida_no_revienta_y_usa_la_calibracion_marginada():
    clase_conocida = ClaseMaterial(tam_rejilla=33, compresion=True, recorte=False)
    clase_desconocida = ClaseMaterial(tam_rejilla=33)  # compresion=None, recorte=None
    a = CandidatoOrden(id="a", features=_features(0.95), clase=clase_conocida)
    b = CandidatoOrden(id="b", features=_features(0.40), clase=clase_desconocida)
    orden = orden_de_repaso([a, b])
    assert orden == ["b", "a"]  # b tiene mucha menos cobertura: le toca primero de todas formas


def test_rejilla_nunca_vista_cae_al_colchon_global_sin_lanzar():
    clase_rara = ClaseMaterial(tam_rejilla=9)  # ninguna calibracion tiene tam_rejilla=9
    a = CandidatoOrden(id="a", features=_features(0.95), clase=clase_rara)
    b = CandidatoOrden(id="b", features=_features(0.10), clase=clase_rara)
    orden = orden_de_repaso([a, b])
    assert orden == ["b", "a"]


# ---------------------------------------------------------------------------
# Casos frontera
# ---------------------------------------------------------------------------


def test_lista_vacia_no_lanza():
    assert orden_de_repaso([]) == []


def test_un_solo_candidato_se_devuelve_tal_cual():
    clase = ClaseMaterial(tam_rejilla=33)
    a = CandidatoOrden(id="unico", features=_features(0.5), clase=clase)
    assert orden_de_repaso([a]) == ["unico"]


def test_el_orden_no_pierde_ni_duplica_candidatos():
    clase = ClaseMaterial(tam_rejilla=17, compresion=False, recorte=False)
    candidatos = [
        CandidatoOrden(id=f"c{i}", features=_features(cobertura=i / 10.0), clase=clase)
        for i in range(10)
    ]
    orden = orden_de_repaso(candidatos)
    assert sorted(orden) == sorted(c.id for c in candidatos)
    assert len(orden) == len(set(orden)) == 10


def test_orden_de_repaso_devuelve_solo_identificadores_no_numeros():
    """Salvaguarda directa de la restriccion del encargo: la API publica de
    este modulo no puede devolver nada que se pueda confundir con una nota."""
    clase = ClaseMaterial(tam_rejilla=33, compresion=False, recorte=False)
    candidatos = [CandidatoOrden(id=f"c{i}", features=_features(i / 10.0), clase=clase) for i in range(3)]
    orden = orden_de_repaso(candidatos)
    assert all(isinstance(x, str) for x in orden)


@pytest.mark.parametrize("clave", list(_ESTADISTICAS_POR_CLASE))
def test_todas_las_clases_calibradas_tienen_desviaciones_no_negativas(clave):
    """Guarda barata: una desviacion negativa en la tabla pegada a mano seria
    un error de transcripcion, no un dato real."""
    _, desv_cob, _, desv_mue, _, desv_pla = _ESTADISTICAS_POR_CLASE[clave]
    assert desv_cob >= 0.0
    assert desv_mue >= 0.0
    assert desv_pla >= 0.0
