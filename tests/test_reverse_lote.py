"""Modo por lote de `core.reverse`: N planos del mismo trabajo -> UN grado.

Tres bloques:

1. **La contabilidad** (rápidos): los estadísticos se suman como si los píxeles
   fueran juntos, `A^T A` es `A^T A`, `acumular_correspondencias` no ha cambiado
   ni un bit, y un lote de un plano es `invertir_grado`.
2. **La trampa** (lentos): un proyecto coherente NO avisa —tampoco con ruido en
   el coloreado— y uno con 3 de 20 planos corregidos aparte avisa y señala esos 3.
3. **Lo que hace `invertir_grado_lote` con el aviso**: baja la confianza, lo pone
   la primera razón, excluye si se le pide, y matiza cuando hay algo espacial.

Cómo sacar las cifras (se imprimen con `-s`):

    .venv/bin/python -m pytest tests/test_reverse_lote.py -s -q

Material: `tests/test_reverse_lote_material.py`, 320×180, sin disco ni red.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from core.contracts import LUT3D
from core.reverse import (
    PESO_DE_MUESTRA,
    acumular_correspondencias,
    comprobar_coherencia,
    estadisticos_de_correspondencias,
    invertir_grado,
    invertir_grado_lote,
    pesos_trilineales,
)
from core.umbrales import UMBRAL_DISCREPANCIA_LOTE
from tests.media import generate as gen
from tests.test_reverse_lote_material import (
    colorear,
    correccion_escalada,
    look_conocido,
    nombre_de_plano,
    proyecto,
)

#: Los tres planos del proyecto de 20 que el colorista corrigió aparte, y cómo.
DISCREPANTES = {3: "mas_calido", 8: "mas_frio", 14: "mas_abierto"}


@pytest.fixture(scope="module")
def proyecto20():
    cdl, lut = look_conocido()
    originales = proyecto(20)
    coloreados = [colorear(o, cdl, lut) for o in originales]
    nombres = [nombre_de_plano(i) for i in range(20)]
    return originales, coloreados, nombres


def _con_discrepantes(originales, coloreados, fuerza: float = 1.0):
    cdl, lut = look_conocido()
    salida = list(coloreados)
    for i, nombre in DISCREPANTES.items():
        salida[i] = colorear(correccion_escalada(nombre, fuerza).apply(originales[i]), cdl, lut)
    return salida


def _imprimir(etiqueta: str, informe) -> None:
    for pl in informe.planos:
        print(
            f"[{etiqueta}] {pl.nombre} exceso={pl.exceso_de:.3f} "
            f"frente_a_los_demas={pl.de_frente_a_los_demas:.3f} suelo={pl.de_suelo_propio:.3f} "
            f"px={pl.pixeles_compartidos} ronda={pl.ronda} discrepa={pl.discrepa}"
        )
    print(f"[{etiqueta}] discrepantes={informe.discrepantes} sin_mayoria={informe.sin_mayoria} "
          f"sin_comparar={informe.sin_comparar}")
    for aviso in informe.avisos:
        print(f"[{etiqueta}] aviso: {aviso}")


# ---------------------------------------------------------------------------
# 1. La contabilidad
# ---------------------------------------------------------------------------


def _nube(semilla: int, m: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(semilla)
    src = rng.random((m, 3)) * 1.1 - 0.05
    return src, np.abs(src) ** 1.2 + 0.01


def test_los_estadisticos_de_dos_planos_suman_como_los_pixeles_juntos():
    a_src, a_dst = _nube(1, 3000)
    b_src, b_dst = _nube(2, 2000)
    tabla = LUT3D.identity(9)
    por_separado = estadisticos_de_correspondencias(
        a_src, a_dst, 9, con_gram=True, tabla=tabla
    ) + estadisticos_de_correspondencias(b_src, b_dst, 9, con_gram=True, tabla=tabla)
    juntos = estadisticos_de_correspondencias(
        np.concatenate([a_src, b_src]), np.concatenate([a_dst, b_dst]), 9, con_gram=True, tabla=tabla
    )
    for campo in ("suma_w", "suma_wy", "counts", "gram", "suma_wr", "suma_wr2"):
        np.testing.assert_allclose(getattr(por_separado, campo), getattr(juntos, campo), atol=1e-9)
    assert por_separado.n_pixeles == juntos.n_pixeles == 5000

    solo_b = juntos - estadisticos_de_correspondencias(a_src, a_dst, 9, con_gram=True, tabla=tabla)
    np.testing.assert_allclose(solo_b.gram, estadisticos_de_correspondencias(
        b_src, b_dst, 9, con_gram=True).gram, atol=1e-9)


def test_la_plantilla_de_gram_es_exactamente_AtA():
    src, dst = _nube(3, 4000)
    n = 9
    est = estadisticos_de_correspondencias(src, dst, n, con_gram=True)
    idx, w = pesos_trilineales(src, n)
    filas = np.repeat(np.arange(src.shape[0]), 8)
    a = sp.csr_matrix((w.T.ravel(), (filas, idx.T.ravel())), shape=(src.shape[0], n**3))
    t = np.random.default_rng(4).random((n, n, n, 3))
    esperado = np.stack([a.T @ (a @ t.reshape(-1, 3)[:, c]) for c in range(3)], axis=1)
    np.testing.assert_allclose(est.aplicar_gram(t), esperado, atol=1e-12)
    np.testing.assert_allclose(
        est.diagonal_gram(), np.asarray(a.multiply(a).sum(axis=0)).ravel(), atol=1e-12
    )
    np.testing.assert_allclose(est.suma_wy, np.stack([a.T @ dst[:, c] for c in range(3)], 1))


def test_acumular_correspondencias_da_lo_mismo_que_el_bucle_del_dia_3():
    """El bucle de antes, copiado aquí tal cual. Si la envoltura nueva cambia un
    solo bit, el T1 de un plano deja de estar garantizado."""
    src, dst = _nube(5, 6000)
    n = 17
    tabla = LUT3D.identity(n)
    for con_tabla in (None, tabla):
        acumulado, cobertura = acumular_correspondencias(src, dst, n, tabla=con_tabla)

        celdas = n**3
        esperado = np.zeros((celdas, 4))
        residuo = dst if con_tabla is None else dst - con_tabla.apply(src)
        idx, w = pesos_trilineales(src, n)
        counts = np.zeros(celdas, dtype=np.int64)
        suma_r = np.zeros((celdas, 3))
        suma_r2 = np.zeros((celdas, 3))
        for k in range(8):
            vive = w[k] >= PESO_DE_MUESTRA
            counts += np.bincount(idx[k][vive], minlength=celdas)
            esperado[:, 3] += np.bincount(idx[k], weights=w[k], minlength=celdas)
            for c in range(3):
                esperado[:, c] += np.bincount(idx[k], weights=w[k] * dst[:, c], minlength=celdas)
                suma_r[:, c] += np.bincount(idx[k], weights=w[k] * residuo[:, c], minlength=celdas)
                suma_r2[:, c] += np.bincount(
                    idx[k], weights=w[k] * residuo[:, c] ** 2, minlength=celdas
                )
        peso = np.maximum(esperado[:, 3], 1e-12)[:, None]
        varianza = np.maximum(suma_r2 / peso - (suma_r / peso) ** 2, 0.0).mean(axis=1)
        varianza[counts < 2] = 0.0

        assert np.array_equal(acumulado, esperado.reshape(n, n, n, 4))
        assert np.array_equal(cobertura.counts, counts.reshape(n, n, n).astype(np.int32))
        assert np.array_equal(cobertura.variance, varianza.reshape(n, n, n).astype(np.float32))


def test_un_lote_de_un_plano_es_invertir_grado(proyecto20):
    originales, coloreados, _ = proyecto20
    uno = invertir_grado(originales[0], coloreados[0])
    lote = invertir_grado_lote([(originales[0], coloreados[0])], informacion="suma_w")
    assert np.array_equal(uno.lut.table, lote.lut.table)
    assert uno.cdl == lote.cdl
    assert np.array_equal(uno.coverage.counts, lote.coverage.counts)
    assert uno.delta_e_max == lote.delta_e_max
    assert lote.confidence.metrics["lote_planos"] == 1.0


def test_el_lote_no_acepta_pares_vacios_ni_nombres_que_no_cuadran(proyecto20):
    originales, coloreados, _ = proyecto20
    with pytest.raises(ValueError):
        invertir_grado_lote([])
    with pytest.raises(ValueError):
        invertir_grado_lote([(originales[0], coloreados[0])], nombres=["a", "b"])


def test_planos_de_distinto_tamano_entran_en_el_mismo_lote(proyecto20):
    originales, coloreados, _ = proyecto20
    cdl, lut = look_conocido()
    pequeno = proyecto(2, ancho=160, alto=90)[1]
    resultado = invertir_grado_lote(
        [(originales[0], coloreados[0]), (pequeno, colorear(pequeno, cdl, lut))],
        diagnosticar_planos=False,
    )
    assert resultado.confidence.metrics["lote_planos_usados"] == 2.0
    assert np.isfinite(resultado.delta_e_mean)


# ---------------------------------------------------------------------------
# 2. La trampa: coherente frente a 3 de 20 corregidos aparte
# ---------------------------------------------------------------------------


@pytest.mark.lento
def test_un_proyecto_coherente_no_avisa(proyecto20):
    """El falso positivo importa igual: si avisa siempre, nadie lo leerá."""
    originales, coloreados, nombres = proyecto20
    informe = comprobar_coherencia(list(zip(originales, coloreados, strict=True)), nombres=nombres)
    _imprimir("lote coherente", informe)
    peor = max(pl.exceso_de for pl in informe.planos)
    print(f"[lote coherente] exceso_max={peor:.4f} umbral={UMBRAL_DISCREPANCIA_LOTE}")
    assert informe.coherente, informe.avisos
    assert not informe.sin_mayoria
    assert informe.sin_comparar == ()
    assert peor < UMBRAL_DISCREPANCIA_LOTE


@pytest.mark.lento
def test_un_proyecto_coherente_con_ruido_en_el_coloreado_tampoco_avisa(proyecto20):
    """Ruido gaussiano de 0.004 en el coloreado. Sin restar el suelo propio, esto
    daba 10 de 20 planos discrepantes y «sin mayoría» (ver NOTAS §12)."""
    originales, coloreados, nombres = proyecto20
    rng = np.random.default_rng(5)
    ruidosos = [c + rng.normal(0.0, 0.004, c.shape).astype(np.float32) for c in coloreados]
    informe = comprobar_coherencia(list(zip(originales, ruidosos, strict=True)), nombres=nombres)
    _imprimir("lote coherente con ruido", informe)
    assert informe.coherente, informe.avisos
    assert max(pl.exceso_de for pl in informe.planos) < UMBRAL_DISCREPANCIA_LOTE


@pytest.mark.lento
def test_tres_de_veinte_corregidos_aparte_avisa_y_senala_esos_tres(proyecto20):
    originales, coloreados, nombres = proyecto20
    mezclados = _con_discrepantes(originales, coloreados)
    informe = comprobar_coherencia(list(zip(originales, mezclados, strict=True)), nombres=nombres)
    _imprimir("lote 3 de 20", informe)

    assert informe.discrepantes == tuple(sorted(DISCREPANTES)), informe.avisos
    assert not informe.sin_mayoria
    buenos = [pl.exceso_de for pl in informe.planos if not pl.discrepa]
    assert max(buenos) < UMBRAL_DISCREPANCIA_LOTE
    # Dice hacia dónde: el cálido sale con b* positivo y el frío con b* negativo.
    assert informe.planos[3].desvio_lab[2] > 0
    assert informe.planos[8].desvio_lab[2] < 0
    assert informe.planos[14].desvio_lab[0] > 0
    aviso = informe.avisos[0]
    for i in DISCREPANTES:
        assert nombres[i] in aviso


@pytest.mark.lento
def test_la_sensibilidad_frente_a_la_fuerza_de_la_correccion(proyecto20):
    """No es un criterio: es la curva, para saber desde dónde avisa. Cada fila
    dice cuánto mueve la corrección su propio plano (mediana ΔE2000) y cuánto
    puntúa. Por debajo de 1 ΔE de mediana, no avisar es lo que se pretende."""
    from core.color import delta_e2000

    originales, coloreados, nombres = proyecto20
    cdl, lut = look_conocido()
    for fuerza in (0.25, 0.5):
        mezclados = _con_discrepantes(originales, coloreados, fuerza)
        informe = comprobar_coherencia(
            list(zip(originales, mezclados, strict=True)), nombres=nombres
        )
        for i in DISCREPANTES:
            propia = float(np.median(delta_e2000(mezclados[i], coloreados[i])))
            pl = informe.planos[i]
            print(
                f"[lote sensibilidad] fuerza={fuerza} {pl.nombre} {DISCREPANTES[i]} "
                f"mediana_propia={propia:.3f} exceso={pl.exceso_de:.3f} discrepa={pl.discrepa}"
            )
            if propia > 2.0 * UMBRAL_DISCREPANCIA_LOTE:
                assert pl.discrepa
        buenos = [pl.exceso_de for pl in informe.planos if pl.indice not in DISCREPANTES]
        print(f"[lote sensibilidad] fuerza={fuerza} exceso_max_buenos={max(buenos):.3f}")
        assert not any(pl.discrepa for pl in informe.planos if pl.indice not in DISCREPANTES)


# ---------------------------------------------------------------------------
# 3. Lo que hace `invertir_grado_lote` con el aviso
# ---------------------------------------------------------------------------


@pytest.mark.lento
def test_el_lote_incoherente_lo_dice_primero_y_baja_la_confianza(proyecto20):
    originales, coloreados, nombres = proyecto20
    mezclados = _con_discrepantes(originales, coloreados)
    resultado = invertir_grado_lote(
        list(zip(originales, mezclados, strict=True)), nombres=nombres, diagnosticar_planos=False
    )
    m = resultado.confidence.metrics
    print(f"[lote avisa] nivel={resultado.confidence.level} score={resultado.confidence.score:.3f} "
          f"discrepantes={m['lote_discrepantes']} exceso_max={m['lote_de_discrepancia_max']:.3f}")
    print(f"[lote avisa] razon0: {resultado.confidence.reasons[0]}")
    assert m["lote_discrepantes"] == 3.0
    assert m["lote_planos_usados"] == 20.0
    assert resultado.confidence.level == "baja"
    assert "no llevan el mismo grado" in resultado.confidence.reasons[0]


@pytest.mark.lento
def test_excluir_discrepantes_ajusta_sin_ellos():
    cdl, lut = look_conocido()
    originales = proyecto(8)
    coloreados = [colorear(o, cdl, lut) for o in originales]
    coloreados[5] = colorear(correccion_escalada("mas_frio", 1.0).apply(originales[5]), cdl, lut)
    nombres = [nombre_de_plano(i) for i in range(8)]
    resultado = invertir_grado_lote(
        list(zip(originales, coloreados, strict=True)),
        nombres=nombres,
        excluir_discrepantes=True,
        diagnosticar_planos=False,
    )
    m = resultado.confidence.metrics
    print(f"[lote excluir] usados={m['lote_planos_usados']} discrepantes={m['lote_discrepantes']} "
          f"nivel={resultado.confidence.level} razon0={resultado.confidence.reasons[0]}")
    assert m["lote_discrepantes"] == 1.0
    assert m["lote_planos_usados"] == 7.0
    assert any("FUERA del ajuste" in nota and nombres[5] in nota for nota in resultado.notes)


@pytest.mark.lento
def test_excluir_discrepantes_recalcula_el_cdl_sin_el_plano_que_deja_fuera():
    """Bug real: `excluir_discrepantes=True` dejaba el plano fuera del LUT pero
    el CDL (Capa 1) seguía siendo el ajustado con TODOS los planos, incluido el
    discrepante — la nota "he dejado FUERA del ajuste" era falsa a medias. El
    CDL devuelto tiene que ser, bit a bit, el que sale de ajustar SÓLO con los
    planos usados — no sólo "distinto del contaminado", sino el mismo que
    ajustar el lote limpio desde cero."""
    cdl, lut = look_conocido()
    originales = proyecto(8)
    coloreados = [colorear(o, cdl, lut) for o in originales]
    coloreados[5] = colorear(correccion_escalada("mas_frio", 1.0).apply(originales[5]), cdl, lut)
    nombres = [nombre_de_plano(i) for i in range(8)]
    pares = list(zip(originales, coloreados, strict=True))

    con_exclusion = invertir_grado_lote(
        pares, nombres=nombres, excluir_discrepantes=True, diagnosticar_planos=False
    )
    assert con_exclusion.confidence.metrics["lote_planos_usados"] == 7.0

    limpio = [p for i, p in enumerate(pares) if i != 5]
    nombres_limpio = [n for i, n in enumerate(nombres) if i != 5]
    sin_el_discrepante = invertir_grado_lote(
        limpio,
        nombres=nombres_limpio,
        verificar_coherencia=False,  # ya se sabe que estos 7 son coherentes entre si
        diagnosticar_planos=False,
    )

    for campo in ("slope", "offset", "power"):
        np.testing.assert_allclose(
            getattr(con_exclusion.cdl, campo),
            getattr(sin_el_discrepante.cdl, campo),
            atol=1e-9,
            err_msg=f"CDL.{campo}: excluir_discrepantes no ha recalculado el CDL sin el plano 5",
        )

    contaminado = invertir_grado_lote(
        pares, nombres=nombres, excluir_discrepantes=False, diagnosticar_planos=False
    )
    diferencia = max(
        float(np.max(np.abs(np.array(getattr(con_exclusion.cdl, campo))
                             - np.array(getattr(contaminado.cdl, campo)))))
        for campo in ("slope", "offset", "power")
    )
    assert diferencia > 1e-6, (
        "el CDL con excluir_discrepantes=True es indistinguible del CDL contaminado con "
        "todos los planos: la recomputacion no esta teniendo ningun efecto"
    )


@pytest.mark.lento
def test_con_vineta_el_aviso_dice_que_puede_ser_algo_espacial():
    """El límite conocido: una viñeta común a todos hace que el mismo color salga
    distinto según dónde esté. Si eso marca planos, el aviso tiene que decir que
    puede no ser otro grado."""
    cdl, lut = look_conocido()
    originales = proyecto(8)
    coloreados = [gen.apply_vignette(colorear(o, cdl, lut), strength=0.45) for o in originales]
    nombres = [nombre_de_plano(i) for i in range(8)]
    resultado = invertir_grado_lote(list(zip(originales, coloreados, strict=True)), nombres=nombres)
    m = resultado.confidence.metrics
    print(f"[lote vineta] discrepantes={m['lote_discrepantes']} razon0={resultado.confidence.reasons[0]}")
    if m["lote_discrepantes"] > 0:
        assert any("zonas que un LUT no puede reproducir" in nota for nota in resultado.notes)
