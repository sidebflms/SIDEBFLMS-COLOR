"""Las cifras detrás de las dos decisiones del modo por lote que tocan el ajuste.

1. **`informacion="suma_w2"` es el defecto del lote y NO el de `invertir_grado`.**
   Aquí están las dos caras: T1 con un plano (mejora), un look de secundarias
   estrechas con un plano (empeora lo típico) y ese mismo look con 40 planos
   (mejora).
2. **La coherencia resta el suelo propio de cada plano.** Aquí está lo que pasa
   sin restarlo cuando el coloreado trae ruido.

Y una cifra de apoyo: cuánto ΔE2000 es un paso de 0.001 en el espacio de trabajo.

Comando de todas (etiquetas `[lote ...]`):

    .venv/bin/python -m pytest tests/test_reverse_lote_determinacion.py -s -q

Nada de esto es T5: ningún grado se aplica a un plano que no entró en el ajuste.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import delta_e2000
from core.reverse import comprobar_coherencia, invertir_grado, invertir_grado_lote
from tests.conftest import a_trabajo
from tests.media import generate as gen
from tests.test_reverse_lote_material import (
    colorear,
    error_en_celdas_cubiertas,
    look_conocido,
    look_duro,
    nombre_de_plano,
    proyecto,
)

VARIANTES = ("suma_w", "suma_w2")


def test_cuanto_es_un_paso_de_0_001_en_el_espacio_de_trabajo():
    gris = np.array([[0.527, 0.541, 0.550]])
    for canal, nombre in enumerate("RGB"):
        paso = np.zeros(3)
        paso[canal] = 0.001
        de = float(delta_e2000(gris + paso, gris)[0])
        print(f"[lote sensibilidad del espacio] gris=(0.527,0.541,0.550) canal={nombre} paso=0.001 de={de:.3f}")
        assert de > 0.0


@pytest.mark.lento
def test_T1_con_las_dos_formas_de_medir_la_informacion_de_un_nodo(estudio_trabajo):
    from tests.test_entregables import _fabricar_coloreado, _lut_de_look_conocido

    coloreado = _fabricar_coloreado(estudio_trabajo, _lut_de_look_conocido())
    for informacion in VARIANTES:
        r = invertir_grado(estudio_trabajo, coloreado, informacion=informacion)
        m = r.confidence.metrics
        print(
            f"[lote T1 informacion] informacion={informacion} "
            f"de_medio_cubierto={m['de_medio_cubierto']:.4f} de_max_cubierto={m['de_max_cubierto']:.4f}"
        )


@pytest.mark.lento
def test_look_de_secundarias_estrechas_con_un_plano():
    """La cara mala de `suma_w2`: A->A de 11 planos, uno a uno."""
    cdl, lut = look_duro()
    planos = [a_trabajo(gen.studio_scene(skin_tone_index=k).image) for k in (0, 2, 4)] + proyecto(8)
    for informacion in VARIANTES:
        maximos = []
        for original in planos:
            r = invertir_grado(original, colorear(original, cdl, lut), informacion=informacion)
            maximos.append(float(r.confidence.metrics["de_max_cubierto"]))
        maximos = np.array(maximos)
        print(
            f"[lote look duro un plano] informacion={informacion} planos={maximos.size} "
            f"de_max_cubierto_mediana={np.median(maximos):.3f} peor={maximos.max():.3f} "
            f"planos_mayor_3={int((maximos > 3.0).sum())} todos={np.round(maximos, 2).tolist()}"
        )


@pytest.mark.lento
def test_look_de_secundarias_estrechas_con_40_planos():
    cdl, lut = look_duro()
    originales = proyecto(40)
    pares = [(o, colorear(o, cdl, lut)) for o in originales]
    for informacion in VARIANTES:
        r = invertir_grado_lote(
            pares, diagnosticar_planos=False, verificar_coherencia=False, informacion=informacion
        )
        e = error_en_celdas_cubiertas(r, originales, cdl, lut)
        de = e["de"]
        m = r.confidence.metrics
        print(
            f"[lote look duro 40 planos] informacion={informacion} celdas_8_nodos={e['celdas']} "
            f"de_max={de.max():.2f} pct_mayor_3={(de > 3).mean() * 100:.1f} "
            f"propios_planos_medio_cub={m['de_medio_cubierto']:.3f} "
            f"propios_planos_max_cub={m['de_max_cubierto']:.3f}"
        )


@pytest.mark.lento
def test_la_coherencia_con_ruido_con_y_sin_restar_el_suelo():
    cdl, lut = look_conocido()
    originales = proyecto(20)
    coloreados = [colorear(o, cdl, lut) for o in originales]
    nombres = [nombre_de_plano(i) for i in range(20)]
    for sigma in (0.002, 0.004):
        rng = np.random.default_rng(5)
        ruidosos = [c + rng.normal(0.0, sigma, c.shape).astype(np.float32) for c in coloreados]
        for restar in (False, True):
            informe = comprobar_coherencia(
                list(zip(originales, ruidosos, strict=True)), nombres=nombres, restar_suelo=restar
            )
            print(
                f"[lote suelo] proyecto_coherente ruido_sigma={sigma} restar_suelo={restar} "
                f"discrepantes_falsos={len(informe.discrepantes)} sin_mayoria={informe.sin_mayoria} "
                f"exceso_max={max(p.exceso_de for p in informe.planos):.3f}"
            )
            if restar:
                assert informe.coherente
