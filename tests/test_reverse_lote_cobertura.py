"""La cifra que justifica o entierra el modo por lote.

¿Cuánto cubo se llena acumulando 1, 3, 5, 10, 20 y 40 planos de un mismo
trabajo? Y, como `MEDICION-T5.md` enseñó que la cobertura sola no cuenta la
historia, ¿cuántos de los nodos «cubiertos» están poco determinados, y cómo de
bien sale un color nuevo que cae en la zona cubierta?

Comando de todas las cifras (etiquetas `[lote cobertura]`,
`[lote determinacion]` y `[lote resolucion]`):

    .venv/bin/python -m pytest tests/test_reverse_lote_cobertura.py -s -q

MONTAJE
-------
* Proyecto sintético de `tests/test_reverse_lote_material.py`: 40 planos
  (retrato, exterior, interior y noche, alternando), **320×180**, UN grado
  conocido (CDL + LUT 33³). La resolución baja es por la carga de la máquina; el
  test `[lote resolucion]` compara con 640×360.
* `invertir_grado_lote` sin comprobación de coherencia ni diagnóstico (no
  cambian ni la cobertura ni el LUT, sólo cuestan).
* Error en celdas cubiertas: 8 puntos al azar (semilla 0) por celda con los 8
  nodos a >= 4 muestras, ΔE2000 del repo contra el grado conocido evaluado en la
  antiimagen del punto por el CDL extraído.

NO es T5: no se aplica el grado a planos que no han entrado en el lote. Eso lo
mide el medidor independiente.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.reverse import invertir_grado_lote
from tests.test_reverse_lote_material import (
    colorear,
    error_en_celdas_cubiertas,
    look_conocido,
    proyecto,
)

PLANOS = (1, 3, 5, 10, 20, 40)


def _max(v: np.ndarray) -> float:
    return float(v.max()) if v.size else float("nan")


def _pct(v: np.ndarray, umbral: float) -> float:
    return float((v > umbral).mean() * 100.0) if v.size else float("nan")


@pytest.mark.lento
def test_cobertura_y_determinacion_frente_al_numero_de_planos():
    cdl, lut = look_conocido()
    originales = proyecto(max(PLANOS))
    pares = [(o, colorear(o, cdl, lut)) for o in originales]

    filas: dict[tuple[int, str], dict[str, float]] = {}
    for n_planos in PLANOS:
        conteos = None
        for informacion in ("suma_w", "suma_w2"):
            r = invertir_grado_lote(
                pares[:n_planos],
                diagnosticar_planos=False,
                verificar_coherencia=False,
                informacion=informacion,
            )
            c = np.asarray(r.coverage.counts).ravel()
            if conteos is None:
                conteos = c
                cub = c >= 4
                print(
                    f"[lote cobertura] planos={n_planos} con_dato={int((c > 0).sum())} "
                    f"cubiertas={int(cub.sum())} pct_cubo={cub.mean() * 100:.3f} "
                    f"nodos_1_3={int(((c >= 1) & (c <= 3)).sum())} "
                    f"nodos_4_15={int(((c >= 4) & (c <= 15)).sum())} "
                    f"nodos_16_63={int(((c >= 16) & (c <= 63)).sum())} "
                    f"nodos_64_mas={int((c >= 64).sum())} "
                    f"frac_cubiertas_4_15={((c >= 4) & (c <= 15)).sum() / max(int(cub.sum()), 1):.3f}"
                )
            else:
                # La cobertura no depende de cómo se ajuste el LUT.
                assert np.array_equal(conteos, c)

            e = error_en_celdas_cubiertas(r, originales[:n_planos], cdl, lut)
            de, flojo, dist = e["de"], e["min_nodo"], e["distancia"]
            fila = {
                "celdas": e["celdas"],
                "puntos": int(de.size),
                "max": _max(de),
                "pct3": _pct(de, 3.0),
                "max_flojo": _max(de[flojo <= 15]),
                "pct3_flojo": _pct(de[flojo <= 15], 3.0),
                "max_cerca": _max(de[dist < 0.0025]),
                "max_lejos": _max(de[dist >= 0.01]),
                "propios_max": float(r.confidence.metrics["de_max_cubierto"]),
                "propios_medio": float(r.confidence.metrics["de_medio_cubierto"]),
            }
            filas[(n_planos, informacion)] = fila
            print(
                f"[lote determinacion] planos={n_planos} informacion={informacion} "
                f"celdas_8_nodos={fila['celdas']} puntos={fila['puntos']} "
                f"de_max={fila['max']:.2f} pct_mayor_3={fila['pct3']:.1f} "
                f"de_max_nodo_flojo_4_15={fila['max_flojo']:.2f} "
                f"pct_mayor_3_nodo_flojo={fila['pct3_flojo']:.1f} "
                f"de_max_a_menos_de_0.0025={fila['max_cerca']:.2f} "
                f"de_max_a_0.01_o_mas={fila['max_lejos']:.2f} "
                f"propios_planos_medio_cub={fila['propios_medio']:.3f} "
                f"propios_planos_max_cub={fila['propios_max']:.3f}"
            )

    assert filas[(40, "suma_w2")]["celdas"] > filas[(1, "suma_w2")]["celdas"]
    # Lo que justifica el defecto del lote (`informacion="suma_w2"`): con 40 planos,
    # menos puntos por encima de 3 ΔE en la zona cubierta que con el ajuste de un plano.
    assert filas[(40, "suma_w2")]["pct3"] <= filas[(40, "suma_w")]["pct3"], filas


@pytest.mark.lento
def test_la_cobertura_casi_no_depende_de_la_resolucion():
    """La cobertura depende de cuántos colores distintos hay, no de cuántos
    píxeles. Se comprueba con los mismos planos a 320×180 y a 640×360."""
    cdl, lut = look_conocido()
    for n_planos in (1, 3):
        valores = {}
        for ancho, alto in ((320, 180), (640, 360)):
            originales = proyecto(n_planos, ancho=ancho, alto=alto)
            r = invertir_grado_lote(
                [(o, colorear(o, cdl, lut)) for o in originales],
                diagnosticar_planos=False,
                verificar_coherencia=False,
            )
            valores[ancho] = r.coverage.coverage_fraction() * 100.0
        print(
            f"[lote resolucion] planos={n_planos} pct_cubo_320x180={valores[320]:.3f} "
            f"pct_cubo_640x360={valores[640]:.3f}"
        )
        assert valores[640] >= valores[320] * 0.5
