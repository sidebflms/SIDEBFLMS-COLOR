"""Bloque 4 (día 9): rendimiento con timeline larga, medido antes de que alguien
lo pregunte en caliente.

La investigación inicial avisó de que cada llamada a la API de Resolve es un
ida y vuelta entre procesos y que iterar clips escala mal. Nadie lo había
medido nunca. Los multicámaras de festival de SIDEBFLMS son largos: 5-6
cámaras, horas de material — así que se mide con 50, 200 y 500 clips, contra
`FakeResolve` (nunca contra Resolve real).

QUÉ SE MIDE Y POR QUÉ CADA UNO CORRE EN SU PROPIO PROCESO
-----------------------------------------------------------
`resource.getrusage(...).ru_maxrss` es un **máximo histórico del proceso**:
nunca baja. Medir los tres tamaños dentro del mismo proceso Python daría una
cifra de "memoria máxima" contaminada por el tamaño anterior (el pico de 500
incluiría el trabajo ya hecho para 50 y 200). Por eso cada tamaño se lanza en
un subproceso limpio (`python -c ...`) y se mide su propio pico, aislado.

Dos fases se miden por separado, porque son dos costes de naturaleza distinta:

1. **Construir el estado** (`gui.datos_demo.estado_muchos(n)`): esto SÍ hace
   trabajo real de emparejamiento (`core.matching.empareja`), no lo finge.
   Es el coste más parecido al de analizar N clips de verdad.
2. **Aplicar el lote** (`gui.pantalla_aplicar.aplicar`): el camino real que
   usa la pantalla de aplicar, con `FakeResolve` contando cada llamada al
   puente en `puente._llamadas` (ya lo hacía FakeResolve; no hay que
   instrumentar nada nuevo). Esta es la fase que se ejecuta síncronamente en
   el hilo de la GUI cuando alguien pulsa "Aplicar al lote" — su duración
   ES la duración del cuelgue de la interfaz, porque
   `PantallaAplicar._ejecutar()` no hace nada incremental durante el bucle
   (una sola llamada a `aplicar()`, una sola actualización de HTML al final;
   comprobado leyendo el código, no supuesto).

En `resource.ru_maxrss`, macOS da **bytes**; Linux da **KiB**. Esto sólo se
ejecuta en macOS (la máquina de Mario), así que se asume bytes y se dice.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

TAMANOS: tuple[int, ...] = (50, 200, 500)

_SCRIPT = """
import json
import resource
import sys
import time

sys.path.insert(0, {raiz!r})

from gui import datos_demo as dd
from gui.pantalla_aplicar import aplicar

n = {n}
t0 = time.perf_counter()
estado = dd.estado_muchos(n)
t1 = time.perf_counter()

puente = estado.puente
antes = len(puente._llamadas)
resultados = aplicar(estado, [c.clip_id for c in estado.clips])
t2 = time.perf_counter()

llamadas = len(puente._llamadas) - antes
ok = sum(1 for r in resultados if r.ok)
pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

print(json.dumps({{
    "n": n,
    "t_construir_s": t1 - t0,
    "t_aplicar_s": t2 - t1,
    "llamadas_al_puente": llamadas,
    "clips_ok": ok,
    "pico_rss_bytes": pico,
}}))
"""


def _medir(n: int) -> dict:
    """Un tamaño, en un subproceso limpio — ver el docstring del módulo."""
    codigo = _SCRIPT.format(n=n, raiz=str(RAIZ))
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        timeout=300,
    )
    assert resultado.returncode == 0, (
        f"el subproceso de medición (n={n}) ha fallado:\n{resultado.stderr}"
    )
    lineas = [linea for linea in resultado.stdout.splitlines() if linea.strip()]
    assert lineas, f"el subproceso de medición (n={n}) no ha impreso nada:\n{resultado.stderr}"
    return json.loads(lineas[-1])


@pytest.fixture(scope="module")
def cifras() -> dict[int, dict]:
    """Los tres tamaños, medidos una sola vez y compartidos entre los tests
    de este módulo — lanzar el subproceso tres veces por test lo haría lento
    sin ganar nada: la medición es determinista para el mismo n."""
    return {n: _medir(n) for n in TAMANOS}


def test_rendimiento_del_lote_se_mide_y_se_imprime(cifras):
    """No hay un umbral de aprobado/suspenso aquí (nadie ha medido esto antes,
    así que no hay una cifra previa con la que comparar) — el test EXISTE
    para que la medición corra en la batería y las cifras salgan impresas en
    cada ejecución, no sólo la noche en que se escribió esto."""
    print()
    for n in TAMANOS:
        c = cifras[n]
        t_total = c["t_construir_s"] + c["t_aplicar_s"]
        print(
            f"[RENDIMIENTO] n={n:>3}  "
            f"construir={c['t_construir_s']:6.3f}s ({c['t_construir_s'] / n * 1000:6.2f} ms/clip)  "
            f"aplicar={c['t_aplicar_s']:6.3f}s ({c['t_aplicar_s'] / n * 1000:6.2f} ms/clip)  "
            f"total={t_total:6.3f}s  "
            f"llamadas_al_puente={c['llamadas_al_puente']:>5} ({c['llamadas_al_puente'] / n:4.1f}/clip)  "
            f"pico_rss={c['pico_rss_bytes'] / 1e6:7.1f} MB  "
            f"ok={c['clips_ok']}/{n}"
        )
        assert c["clips_ok"] == n, f"n={n}: no todos los clips se han aplicado bien"


def test_el_tiempo_de_aplicar_no_escala_claramente_peor_que_lineal(cifras):
    """Cuadrático seria devastador con 500 clips reales. Se compara el coste
    POR CLIP entre el tamaño más pequeño y el más grande: si escalara mal
    (cuadrático, por ejemplo), el coste por clip a n=500 sería varias veces
    el de n=50, no aproximadamente el mismo. Margen 2.5x: generoso a
    propósito (contención de CPU de la máquina compartida puede mover esto
    sin que sea un problema real del código), pero suficiente para cazar un
    O(n²) de verdad, que multiplicaría por ~10x entre 50 y 500."""
    pequeno = cifras[TAMANOS[0]]
    grande = cifras[TAMANOS[-1]]
    ms_clip_pequeno = pequeno["t_aplicar_s"] / pequeno["n"] * 1000
    ms_clip_grande = grande["t_aplicar_s"] / grande["n"] * 1000
    razon = ms_clip_grande / ms_clip_pequeno if ms_clip_pequeno > 0 else float("inf")
    print(f"\n[RENDIMIENTO] ms/clip a n={pequeno['n']}: {ms_clip_pequeno:.3f}  "
          f"ms/clip a n={grande['n']}: {ms_clip_grande:.3f}  razón: {razon:.2f}x")
    assert razon < 2.5, (
        f"el coste por clip de aplicar() sube {razon:.2f}x entre n={pequeno['n']} y "
        f"n={grande['n']} — parece escalar peor que lineal, revisar aplicar_grado_seguro"
    )


def test_las_llamadas_al_puente_por_clip_son_constantes(cifras):
    """Si `aplicar_grado_seguro` pidiera un dato de Resolve varias veces por
    clip de forma que creciera con n (en vez de ser un número fijo por
    clip), aquí es donde se vería: llamadas/clip constante confirma que no
    hay una lectura redundante que dependa del tamaño del lote."""
    por_clip = {n: cifras[n]["llamadas_al_puente"] / n for n in TAMANOS}
    print(f"\n[RENDIMIENTO] llamadas al puente por clip: {por_clip}")
    minimo, maximo = min(por_clip.values()), max(por_clip.values())
    assert maximo - minimo < 1.0, (
        f"las llamadas al puente por clip varían con n ({por_clip}) — algo en "
        "aplicar_grado_seguro depende del tamaño del lote, no sólo del clip"
    )
