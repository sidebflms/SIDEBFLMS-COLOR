"""AUDITORIA DIA 2 - Caso 4: el `xfail` de la vineta sola.

Tres preguntas distintas, y aqui se miden las tres con numeros:

(a) ¿La razon escrita en el `xfail` describe el fallo real?
(b) ¿Es un limite de verdad o un rojo disfrazado de verde?
(c) ¿Cual es la gravedad? En esta app decir "esto es un LUT" cuando no lo es
    es mucho peor que callarse.

No modifica nada de produccion. Solo mide y deja las cifras en la salida.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import LUT_SIZE_DEFAULT
from core.reverse import invertir_grado
from core.reverse.diagnostico import (
    UMBRAL_DE_HOTSPOT,
    UMBRAL_MONOTONIA_RADIAL,
    UMBRAL_R2_RADIAL,
    _pearson,
    _perfil_radial,
    _r2,
    _suavizar,
    mapa_de_residuo,
)
from tests.media import generate as gen
from tests.test_entregables import (
    _fabricar_coloreado,
    _lut_de_look_conocido,
)


def _con_vineta(estudio_trabajo):
    base = _fabricar_coloreado(estudio_trabajo, _lut_de_look_conocido())
    return gen.apply_vignette(base, strength=0.55).astype(np.float32)


def test_AUD4_que_puerta_es_la_que_se_cierra(estudio_trabajo, capsys):
    """(a) ¿Falla por el R2 radial, como dice el `xfail`, o por otra cosa?"""
    coloreado = _con_vineta(estudio_trabajo)
    resultado = invertir_grado(estudio_trabajo, coloreado)
    d = resultado.diagnosis

    residuo, movimiento = mapa_de_residuo(
        estudio_trabajo, coloreado, resultado.cdl, resultado.lut
    )
    h, w = residuo.shape
    finitos = np.isfinite(residuo)
    res_medio = float(residuo[finitos].mean())
    radio = max(min(h, w) // 48, 1)
    suave = _suavizar(np.where(finitos, residuo, res_medio), radio)
    modelo, perfil, centros = _perfil_radial(suave)
    r2 = _r2(suave, modelo)
    crece = _pearson(perfil, centros)
    recorrido = float(perfil.max() - perfil.min())

    print(f"\n[AUD4-a] imagen={h}x{w} radio_suavizado={radio}")
    print(f"[AUD4-a] lut_reproducible={d.lut_reproducible:.4f} is_pure_lut={d.is_pure_lut}")
    print(f"[AUD4-a] residuo medio={res_medio:.4f} movimiento medio={movimiento.mean():.4f}")
    print(
        f"[AUD4-a] PUERTA 1 R2 radial ={r2:.4f} (hace falta >= {UMBRAL_R2_RADIAL}) "
        f"-> {'PASA' if r2 >= UMBRAL_R2_RADIAL else 'CIERRA'}"
    )
    print(
        f"[AUD4-a] PUERTA 2 monotonia ={crece:.4f} (hace falta >= {UMBRAL_MONOTONIA_RADIAL}) "
        f"-> {'PASA' if crece >= UMBRAL_MONOTONIA_RADIAL else 'CIERRA'}"
    )
    print(
        f"[AUD4-a] PUERTA 3 recorrido ={recorrido:.4f} (hace falta >= {UMBRAL_DE_HOTSPOT}) "
        f"-> {'PASA' if recorrido >= UMBRAL_DE_HOTSPOT else 'CIERRA'}"
    )
    print(f"[AUD4-a] perfil radial (24 coronas) = {np.round(perfil, 3).tolist()}")
    print(f"[AUD4-a] etiquetas emitidas = {[hp.label for hp in d.hotspots]}")
    for n in d.notes:
        print(f"[AUD4-a] nota: {n}")

    # La afirmacion del xfail: la que cierra es la del R2 radial.
    assert r2 < UMBRAL_R2_RADIAL, "el R2 radial YA pasa el umbral: el xfail esta obsoleto"


def test_AUD4_el_perfil_radial_SI_existe_lo_que_falla_es_el_R2(estudio_trabajo):
    """(b) ¿Limite de fondo o eleccion de un parametro?

    Si el perfil radial por coronas es claramente monotono y con recorrido de
    sobra, la caida radial ESTA en el residuo: lo que no cuadra es la metrica
    con la que se decide (un R2 pixel a pixel contra un residuo que ademas
    lleva el error del ajuste del LUT). Se prueba subiendo SOLO el suavizado,
    sin tocar umbrales.
    """
    coloreado = _con_vineta(estudio_trabajo)
    resultado = invertir_grado(estudio_trabajo, coloreado)
    residuo, _ = mapa_de_residuo(estudio_trabajo, coloreado, resultado.cdl, resultado.lut)
    h, w = residuo.shape
    finitos = np.isfinite(residuo)
    base = np.where(finitos, residuo, float(residuo[finitos].mean()))

    print("\n[AUD4-b] efecto del radio de suavizado sobre las tres puertas:")
    filas = []
    for divisor in (48, 24, 12, 6, 3):
        radio = max(min(h, w) // divisor, 1)
        suave = _suavizar(base, radio)
        modelo, perfil, centros = _perfil_radial(suave)
        r2 = _r2(suave, modelo)
        crece = _pearson(perfil, centros)
        recorrido = float(perfil.max() - perfil.min())
        filas.append((divisor, radio, r2, crece, recorrido))
        print(
            f"[AUD4-b] min(h,w)//{divisor:<2} radio={radio:<3} R2={r2:.4f} "
            f"monotonia={crece:.4f} recorrido={recorrido:.4f}"
        )

    # La caida radial existe: monotonia y recorrido pasan con el radio de hoy.
    _, _, _, crece0, recorrido0 = filas[0]
    assert crece0 >= UMBRAL_MONOTONIA_RADIAL, (
        f"ni siquiera la monotonia pasa ({crece0:.4f}): entonces no hay vineta que detectar "
        f"y el xfail estaria mal por otro motivo"
    )
    assert recorrido0 >= UMBRAL_DE_HOTSPOT, f"recorrido {recorrido0:.4f}"


def test_AUD4_gravedad_el_fallo_va_hacia_el_lado_seguro(estudio_trabajo):
    """(c) Gravedad: lo grave seria decir "es un LUT" cuando no lo es.

    Se comprueba que con la vineta puesta la app NO dice que sea puro LUT y
    que la fraccion reproducible baja de forma visible respecto al caso sin
    vineta. Si ademas no dice NADA de la vineta, eso es el coste real.
    """
    limpio = _fabricar_coloreado(estudio_trabajo, _lut_de_look_conocido())
    d_limpio = invertir_grado(estudio_trabajo, limpio).diagnosis
    d_vineta = invertir_grado(estudio_trabajo, _con_vineta(estudio_trabajo)).diagnosis

    print(
        f"\n[AUD4-c] sin vineta : reproducible={d_limpio.lut_reproducible:.4f} "
        f"puro={d_limpio.is_pure_lut} etiquetas={[h.label for h in d_limpio.hotspots]}"
    )
    print(
        f"[AUD4-c] con vineta : reproducible={d_vineta.lut_reproducible:.4f} "
        f"puro={d_vineta.is_pure_lut} etiquetas={[h.label for h in d_vineta.hotspots]}"
    )
    print(f"[AUD4-c] spatial_residual con vineta = {d_vineta.spatial_residual}")

    assert d_limpio.is_pure_lut, "el caso limpio ya no se reconoce como LUT puro"
    assert not d_vineta.is_pure_lut, (
        "GRAVE: con una vineta encima la app dice que el grado es un LUT puro. "
        "Eso manda al usuario a exportar un .cube que no reproduce el grado."
    )
    assert d_vineta.lut_reproducible < d_limpio.lut_reproducible - 0.05, (
        "la vineta ni siquiera baja la fraccion reproducible de forma visible"
    )
    # Lo que SI se pierde: alguna senal de que hay algo espacial.
    hay_senal = bool(d_vineta.hotspots) or d_vineta.spatial_residual is not None
    print(f"[AUD4-c] ¿queda alguna senal de que hay algo espacial? {hay_senal}")


def test_AUD4_el_criterio_T2_del_encargo_si_se_cumple(estudio_trabajo):
    """El criterio literal del encargo es "vineta Y ventana", y ese pasa.

    Importa para juzgar el `xfail`: lo que esta en rojo es un caso extra que
    el orquestador anadio por encima del criterio, no el criterio.
    """
    from tests.test_entregables import CAJA_VENTANA, _coloreado_con_lo_espacial

    d = invertir_grado(estudio_trabajo, _coloreado_con_lo_espacial(estudio_trabajo)).diagnosis
    print(
        f"\n[AUD4-T2] vineta+ventana: puro={d.is_pure_lut} "
        f"etiquetas={[h.label for h in d.hotspots]} caja_real={CAJA_VENTANA}"
    )
    assert not d.is_pure_lut
    assert d.hotspots, "con vineta Y ventana no senala ninguna zona"


@pytest.mark.parametrize("size", [LUT_SIZE_DEFAULT])
def test_AUD4_sin_efectos_colaterales(size):
    """Recordatorio de que estos tests no escriben nada fuera de memoria."""
    assert size in (17, 33, 65)
