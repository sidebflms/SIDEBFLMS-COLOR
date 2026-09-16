"""Tests de la puntuacion de confianza.

Lo que se prueba: que la formula es monotona en cada metrica (empeorar algo
nunca sube la nota), que los umbrales de alta/media/baja salen SIEMPRE de
`confidence_level()` y no de una copia, que las razones estan en castellano y
ordenadas, y que una clave mal escrita se ve enseguida.
"""

from __future__ import annotations

import pytest

from core.contracts import CONFIDENCE_ALTA, CONFIDENCE_MEDIA, Confidence, confidence_level
from core.matching.confianza import (
    METRICAS_ACEPTADAS,
    PENA_DESAJUSTE,
    UMBRALES,
    puntuar_confianza,
)

#: Un caso perfecto del que partir para ir empeorando cosas de una en una.
PERFECTO = {
    "n_muestras": 60000,
    "solape": 0.99,
    "condicion": 1e3,
    "residuo_de": 0.1,
    "extrapolacion": 0.0,
    "ganancia": 1.1,
    "fraccion_no_finita": 0.0,
    "desajuste": False,
}


def test_todo_perfecto_da_uno_y_alta():
    c = puntuar_confianza(**PERFECTO)
    assert isinstance(c, Confidence)
    assert c.score == pytest.approx(1.0)
    assert c.level == "alta"


def test_el_nivel_sale_de_confidence_level_y_no_de_una_copia():
    """Si alguien redefine los umbrales aqui, esto se pone rojo."""
    for score in (0.0, 0.2, 0.44, CONFIDENCE_MEDIA, 0.6, CONFIDENCE_ALTA, 0.9, 1.0):
        # Se fabrica una nota concreta jugando con el residuo.
        c = puntuar_confianza(residuo_de=0.0)
        assert c.level == confidence_level(c.score)
        assert confidence_level(score) in ("alta", "media", "baja")


@pytest.mark.parametrize(
    "clave,peor",
    [
        ("n_muestras", 30),
        ("solape", 0.45),
        ("condicion", 1e9),
        ("residuo_de", 6.0),
        ("extrapolacion", 0.3),
        ("ganancia", 50.0),
        ("fraccion_no_finita", 0.2),
    ],
)
def test_empeorar_una_metrica_baja_la_nota(clave, peor):
    base = puntuar_confianza(**PERFECTO).score
    peorado = dict(PERFECTO)
    peorado[clave] = peor
    assert puntuar_confianza(**peorado).score < base


@pytest.mark.parametrize("clave", [k for k in UMBRALES])
def test_cada_metrica_en_su_extremo_malo_da_subnota_cero(clave):
    peorado = dict(PERFECTO)
    peorado[clave] = UMBRALES[clave][1]
    c = puntuar_confianza(**peorado)
    assert c.metrics[f"subnota_{clave}"] == pytest.approx(0.0)
    assert c.score == pytest.approx(0.0)
    assert c.level == "baja"


def test_el_desajuste_de_contenido_multiplica_y_no_se_compensa():
    """Un ajuste numericamente impecable con desajuste de contenido NO puede
    salir 'alta'. Es lo que evita que se iguale un retrato con un prado."""
    bueno = puntuar_confianza(**PERFECTO)
    con_desajuste = puntuar_confianza(**{**PERFECTO, "desajuste": True})
    assert con_desajuste.score == pytest.approx(bueno.score * PENA_DESAJUSTE)
    assert con_desajuste.level != "alta"


def test_la_primera_razon_es_el_desajuste_cuando_lo_hay():
    c = puntuar_confianza(**{**PERFECTO, "desajuste": True})
    assert "no parecen la misma escena" in c.reasons[0]


def test_las_razones_van_de_la_pega_mas_grave_a_la_mas_leve():
    c = puntuar_confianza(
        n_muestras=60000,
        solape=0.99,
        condicion=1e3,
        residuo_de=7.5,  # casi el peor -> subnota 0.1
        extrapolacion=0.15,  # a medias -> subnota ~0.66
        ganancia=1.0,
        fraccion_no_finita=0.0,
    )
    assert len(c.reasons) >= 2
    assert "ΔE2000" in c.reasons[0]
    assert "extrapolando" in c.reasons[1]


def test_cuando_no_hay_nada_que_objetar_lo_dice_igual():
    """La GUI enseña `reasons` tal cual; nunca puede quedarse en blanco."""
    c = puntuar_confianza(**PERFECTO)
    assert len(c.reasons) == 1
    assert "no hay nada que objetar" in c.reasons[0]


def test_las_razones_estan_en_castellano():
    c = puntuar_confianza(n_muestras=30, solape=0.45, residuo_de=5.0, extrapolacion=0.3)
    texto = " ".join(c.reasons).lower()
    for palabra in ("pixeles", "plano", "correccion"):
        assert palabra in texto


def test_las_metricas_crudas_viajan_con_el_resultado():
    c = puntuar_confianza(**PERFECTO, distancia_contenido=0.42)
    assert c.metrics["n_muestras"] == 60000
    assert c.metrics["distancia_contenido"] == pytest.approx(0.42)
    assert c.metrics["nota"] == pytest.approx(c.score)
    assert UMBRALES, "no hay nada que comprobar: `UMBRALES` esta vacio"
    for clave in UMBRALES:
        assert f"subnota_{clave}" in c.metrics


def test_las_metricas_que_no_se_pasan_no_cuentan():
    solo_una = puntuar_confianza(residuo_de=0.0)
    assert solo_una.score == pytest.approx(1.0)
    assert "subnota_solape" not in solo_una.metrics


def test_sin_ninguna_metrica_la_nota_es_media_y_se_dice_por_que():
    c = puntuar_confianza()
    assert c.score == pytest.approx(0.5)
    assert "valor por defecto" in c.reasons[0]


def test_una_clave_mal_escrita_lanza():
    """A proposito: un `residuos=` en vez de `residuo_de=` no puede salir como
    una nota silenciosamente optimista."""
    with pytest.raises(TypeError, match="residuos"):
        puntuar_confianza(residuos=1.0)
    with pytest.raises(TypeError):
        puntuar_confianza(cobertura=0.5)


def test_las_claves_documentadas_son_las_que_acepta():
    assert METRICAS_ACEPTADAS, (
        "no hay nada que comprobar: `METRICAS_ACEPTADAS` esta vacio y el bucle no llamaria ni una vez"
    )
    for clave in METRICAS_ACEPTADAS:
        puntuar_confianza(**{clave: 1.0})


def test_una_metrica_no_finita_cuenta_como_lo_peor():
    """Una condicion infinita (covarianza de rango 1) no puede dar buena nota."""
    c = puntuar_confianza(**{**PERFECTO, "condicion": float("inf")})
    assert c.metrics["subnota_condicion"] == pytest.approx(0.0)
    assert c.level == "baja"


def test_la_nota_siempre_esta_entre_cero_y_uno():
    extremos = [
        {},
        {"n_muestras": 0},
        {"n_muestras": 10**9, "solape": 2.0, "condicion": 0.0, "residuo_de": -5.0},
        {"extrapolacion": 5.0, "ganancia": 1e9, "fraccion_no_finita": 3.0, "desajuste": True},
    ]
    for kw in extremos:
        c = puntuar_confianza(**kw)
        assert 0.0 <= c.score <= 1.0, kw


def test_una_sola_pega_gorda_no_deja_la_nota_en_alta():
    """El minimo pesa: seis subnotas perfectas y una de 0.3 no pueden dar
    'alta'. Esa es la razon de que la formula sea `sqrt(min * geometrica)` y no
    una media a secas."""
    c = puntuar_confianza(**{**PERFECTO, "residuo_de": 5.9})  # subnota ~0.3
    assert c.metrics["subnota_residuo_de"] < 0.35
    assert c.level == "media"
