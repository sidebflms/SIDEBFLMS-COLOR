"""Que centralizar los umbrales no haya movido ninguno, y que nadie tenga otro.

Este archivo es el contrapeso del barrido de `test_umbrales_literales.py`. Aquel
comprueba que no hay umbrales escritos a pelo; éste comprueba **dos cosas que
aquél no puede ver**:

1. **Que ningún valor se ha movido al mudarse.** La tabla de abajo lleva el
   valor que cada constante tenía en su módulo **antes** del barrido, copiado del
   código de origen. Si alguien cambia un umbral, esto se pone rojo y hay que
   decir por qué a mano. Un umbral no se toca de pasada.
2. **Que el nombre que exporta cada módulo es el MISMO objeto** que el de
   `core.umbrales`. Reexportar está bien —no rompe a quien importaba de antes—,
   pero si mañana alguien sustituye el reexport por una copia con otro valor,
   volvemos al bug de `gui/reverse_puente.py`: dos definiciones, la de fuera más
   floja, y nadie se entera.
"""

from __future__ import annotations

import pytest

from core import umbrales

#: Nombre -> valor **tal y como estaba escrito en su módulo antes de mudarse**.
#: Esto no es una copia del módulo (eso no afirmaría nada): es la lista de
#: origen, tecleada desde el código anterior al barrido.
VALORES_DE_ORIGEN: dict[str, object] = {
    # Dia 4: los dos limites de los criterios de entrega, del encargo del dia 1.
    "LIMITE_T1_DELTA_E_MAXIMO": 3.0,
    "LIMITE_T3_DELTA_E_PEOR_PAR": 2.0,
    # core/contracts.py
    "CONFIDENCE_ALTA": 0.75,
    "CONFIDENCE_MEDIA": 0.45,
    "LUT_SIZE_DEFAULT": 33,
    # core/reverse/diagnostico.py
    "UMBRAL_DE_HOTSPOT": 1.0,
    "UMBRAL_DE_PURO": 1.0,
    "UMBRAL_REPRODUCIBLE_PURO": 0.95,
    "UMBRAL_R2_RADIAL": 0.30,
    "UMBRAL_MONOTONIA_RADIAL": 0.55,
    "UMBRAL_RECORRIDO_GANANCIA": 0.12,
    "UMBRAL_R2_LINEAL": 0.50,
    "UMBRAL_RECORRIDO_LINEAL": 0.10,
    "SUELO_GANANCIA_LOCAL": 0.08,
    "FRACCION_DE_PICO": 0.40,
    "UMBRAL_TEXTURA": 2.5,
    "AREA_MINIMA_HOTSPOT": 0.002,
    # core/reverse/diagnostico.py, escritos como literal suelto
    "UMBRAL_MOVIMIENTO_NULO": 0.05,
    # core/reverse/diagnostico.py e invertir.py: el mismo literal, dos veces
    "UMBRAL_COBERTURA_BAJA": 0.005,
    # core/reverse/invertir.py
    "MUESTRAS_MINIMAS_CDL": 64,
    "UMBRAL_FUERA_DE_DOMINIO_AVISO": 0.001,
    # core/reverse/acumulacion.py, invertir.py y contracts.py: el mismo 4
    "MUESTRAS_MINIMAS_CELDA": 4,
    # core/reverse/alineado.py
    "UMBRAL_CORRELACION_FIABLE": 0.50,
    # core/io/qc.py
    "UMBRAL_BANDING": 3.0,
    "SALTO_MINIMO_BANDING": 0.02,
    "UMBRAL_SOMBRAS": 0.125,
    "UMBRAL_RECORRIDO_LUT_PLANO": 1e-6,
    "TOL_MONOTONIA": 1e-5,
    "TOL_GAMUT": 1.0 / 2048.0,
    # core/matching/contenido.py
    "UMBRAL_DESAJUSTE": 0.70,
    "UMBRAL_HUELLA": 0.50,
    "UMBRAL_CROMA_EXPLICABLE": 0.35,
    "UMBRAL_PERFIL_EXPLICABLE": 0.12,
    # core/matching/confianza.py
    "PENA_DESAJUSTE": 0.35,
    "UMBRAL_SUBNOTA_EXPLICABLE": 0.85,
    # core/analysis/stats.py
    "FRACCION_PIEL_MINIMA": 0.005,
    "PIXELES_PIEL_MINIMOS": 64,
    "UMBRAL_NEUTRA_TOTAL": 0.999,
    # la base perceptual, que estaba escrita tres veces
    "DELTA_E_INDISTINGUIBLE": 1.0,
}

#: Las siete rampas de la confianza, tal y como estaban en
#: `core/matching/confianza.py:UMBRALES`.
RAMPAS_DE_ORIGEN: dict[str, tuple[float, float]] = {
    "n_muestras": (20000.0, 24.0),
    "solape": (0.90, 0.40),
    "condicion": (1e5, 1e10),
    "residuo_de": (1.0, 8.0),
    "extrapolacion": (0.02, 0.40),
    "ganancia": (4.0, 100.0),
    "fraccion_no_finita": (0.0, 0.25),
}


@pytest.mark.parametrize("nombre", sorted(VALORES_DE_ORIGEN))
def test_ningun_umbral_se_movio_al_centralizarse(nombre):
    """Si esto se pone rojo, alguien cambió un umbral. No es un descuadre de
    formato: es una decisión de producto y hay que decirla en voz alta."""
    assert getattr(umbrales, nombre) == pytest.approx(VALORES_DE_ORIGEN[nombre])


def test_las_rampas_de_confianza_no_se_movieron():
    assert umbrales.RAMPAS_DE_CONFIANZA == RAMPAS_DE_ORIGEN


def test_la_tabla_de_origen_cubre_todo_lo_que_se_mudo():
    """Para que no se pueda añadir un umbral a `core.umbrales` sin anotarlo aquí."""
    assert umbrales.__all__, (
        "no hay nada que comprobar: `core.umbrales.__all__` esta vacio y la resta de abajo "
        "saldria vacia sin mirar nada"
    )
    faltan = set(umbrales.__all__) - set(VALORES_DE_ORIGEN) - {"RAMPAS_DE_CONFIANZA"}
    assert not faltan, f"umbrales sin valor de origen anotado: {sorted(faltan)}"


# ---------------------------------------------------------------------------
# Que el reexport sea un reexport y no una copia
# ---------------------------------------------------------------------------

#: (módulo que lo reexporta, nombre). Es la lista de sitios donde antes vivía la
#: definición y hoy vive sólo el nombre.
REEXPORTS: tuple[tuple[str, str], ...] = (
    ("core.contracts", "CONFIDENCE_ALTA"),
    ("core.contracts", "CONFIDENCE_MEDIA"),
    ("core.contracts", "LUT_SIZE_DEFAULT"),
    ("core.reverse.diagnostico", "UMBRAL_DE_HOTSPOT"),
    ("core.reverse.diagnostico", "UMBRAL_DE_PURO"),
    ("core.reverse.diagnostico", "UMBRAL_REPRODUCIBLE_PURO"),
    ("core.reverse.diagnostico", "UMBRAL_R2_RADIAL"),
    ("core.reverse.diagnostico", "UMBRAL_MONOTONIA_RADIAL"),
    ("core.reverse.diagnostico", "UMBRAL_RECORRIDO_GANANCIA"),
    ("core.reverse.diagnostico", "UMBRAL_R2_LINEAL"),
    ("core.reverse.diagnostico", "UMBRAL_RECORRIDO_LINEAL"),
    ("core.reverse.diagnostico", "SUELO_GANANCIA_LOCAL"),
    ("core.reverse.diagnostico", "FRACCION_DE_PICO"),
    ("core.reverse.diagnostico", "UMBRAL_TEXTURA"),
    ("core.reverse.diagnostico", "AREA_MINIMA_HOTSPOT"),
    ("core.reverse.invertir", "MUESTRAS_MINIMAS_CDL"),
    ("core.reverse.alineado", "UMBRAL_CORRELACION_FIABLE"),
    ("core.io.qc", "UMBRAL_BANDING"),
    ("core.io.qc", "SALTO_MINIMO_BANDING"),
    ("core.io.qc", "UMBRAL_SOMBRAS"),
    ("core.io.qc", "TOL_MONOTONIA"),
    ("core.io.qc", "TOL_GAMUT"),
    ("core.matching.contenido", "UMBRAL_DESAJUSTE"),
    ("core.matching.contenido", "UMBRAL_HUELLA"),
    ("core.matching.confianza", "PENA_DESAJUSTE"),
    ("core.analysis.stats", "FRACCION_PIEL_MINIMA"),
    ("core.analysis.stats", "PIXELES_PIEL_MINIMOS"),
    # `core.reverse` y `core.io` los vuelven a exportar desde el paquete.
    ("core.reverse", "UMBRAL_REPRODUCIBLE_PURO"),
    ("core.reverse", "UMBRAL_CORRELACION_FIABLE"),
    ("core.reverse", "MUESTRAS_MINIMAS_CDL"),
    ("core.io", "UMBRAL_SOMBRAS"),
    ("core.io", "UMBRAL_BANDING"),
)


@pytest.mark.parametrize(("modulo", "nombre"), REEXPORTS)
def test_el_nombre_de_siempre_sigue_estando_y_vale_lo_mismo(modulo, nombre):
    """Reexportar no puede romper a quien lo importaba de su sitio de antes."""
    import importlib

    mod = importlib.import_module(modulo)
    assert hasattr(mod, nombre), f"{modulo} ya no exporta {nombre}"
    assert getattr(mod, nombre) == pytest.approx(getattr(umbrales, nombre))


def test_las_rampas_siguen_llamandose_UMBRALES_en_matching_confianza():
    from core.matching import confianza

    assert confianza.UMBRALES is umbrales.RAMPAS_DE_CONFIANZA


def test_el_umbral_del_hallazgo_del_dia_2_sigue_siendo_el_estricto():
    """El bug: `gui/reverse_puente.py` decía `reproducible > 0.92` a secas.

    El criterio bueno son **tres** cosas a la vez, y dos de ellas son números que
    ahora viven en un solo sitio. Este test no prueba el detector: prueba que
    nadie ha aflojado el criterio al mudarlo, que es de lo que iba el día 2.
    """
    assert pytest.approx(0.95) == umbrales.UMBRAL_REPRODUCIBLE_PURO
    assert pytest.approx(1.0) == umbrales.UMBRAL_DE_PURO
    assert umbrales.UMBRAL_REPRODUCIBLE_PURO > 0.92, (
        "el criterio del nucleo tiene que seguir siendo MAS estricto que el 0.92 que "
        "tenia la GUI, que es justo lo que se arreglo el dia 2"
    )


def test_la_base_perceptual_es_de_verdad_la_misma_en_los_tres_sitios():
    """Estaba escrita tres veces con el mismo comentario dicho de tres formas."""
    from core.matching import confianza

    assert umbrales.UMBRAL_DE_PURO is umbrales.DELTA_E_INDISTINGUIBLE
    assert umbrales.UMBRAL_DE_HOTSPOT is umbrales.DELTA_E_INDISTINGUIBLE
    assert confianza.UMBRALES["residuo_de"][0] == pytest.approx(
        umbrales.DELTA_E_INDISTINGUIBLE
    )


def test_el_cuatro_de_la_cobertura_sigue_cuadrando_con_el_de_los_contratos():
    """`CoverageMap.min_samples` es la CUARTA escritura del mismo 4 y vive en
    `core/contracts.py`, que no es de este agente.

    Mientras no se pueda tocar, al menos que salte si alguien mueve uno de los
    dos: dos definiciones de «esta celda tiene datos» que dejen de coincidir es
    exactamente la forma del bug del dia 2.
    """
    import inspect

    from core.contracts import CoverageMap

    por_defecto = inspect.signature(CoverageMap).parameters["min_samples"].default
    assert por_defecto == umbrales.MUESTRAS_MINIMAS_CELDA, (
        "CoverageMap.min_samples y core.umbrales.MUESTRAS_MINIMAS_CELDA se han "
        "separado. Son el mismo criterio escrito dos veces; hay que unificarlos en "
        "core/contracts.py, que es del orquestador."
    )
