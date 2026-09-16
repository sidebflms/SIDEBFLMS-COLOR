"""La calibración de la confianza: el material, la medida publicada y el hallazgo.

Lo que afirma cada test y por qué está en `CALIBRACION-CONFIANZA.md`. Resumen:

* El material no depende de lo que mide, y la ida y vuelta por h264 no mete un cambio de
  matriz que se confundiría con ruido de compresión.
* Las cifras publicadas salen de los CSV de `datos/` (sin volver a medir: eso es
  `python -m tests.calibracion.medir`, que tarda minutos).
* **El hallazgo, en vivo y en un solo caso**: una extracción limpia con `score == 1.0`
  («alta», «no hay nada que objetar») cuyo máximo va de 2.41 en su plano a 7.05 en
  otro. Centinela en verde con las cifras, y un `xfail(strict=True)` con lo que «alta»
  debería garantizar y hoy no garantiza.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import numpy as np
import pytest

from core.umbrales import CONFIDENCE_ALTA, LIMITE_T1_DELTA_E_MAXIMO
from tests.calibracion import material as m

AQUI = Path(__file__).resolve().parent
COMANDO = ".venv/bin/python -m pytest tests/calibracion -q -rx"
HAY_FFMPEG = shutil.which("ffmpeg") is not None or Path("/opt/homebrew/bin/ffmpeg").is_file()

#: El caso del centinela: `pobre`, grado fuerte, sin compresión ni recorte.
CASO_CENTINELA = 44


# ---------------------------------------------------------------------------
# El material
# ---------------------------------------------------------------------------


def test_el_material_no_importa_core():
    arbol = ast.parse((AQUI / "material.py").read_text())
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            assert all(a.name.split(".")[0] != "core" for a in nodo.names)
        if isinstance(nodo, ast.ImportFrom):
            assert (nodo.module or "").split(".")[0] != "core", nodo.module


@pytest.mark.skipif(not HAY_FFMPEG, reason="sin ffmpeg no hay ida y vuelta por h264")
def test_la_ida_y_vuelta_por_h264_no_cambia_la_matriz():
    """Medido: `make_clip` codifica con la matriz BT.601 (la de por defecto de swscale)
    aunque etiquete BT.709. Decodificando con BT.709 una rampa sale con error medio
    0.027; con BT.601, 0.0046. El material decodifica con BT.601 para que lo que quede
    sea compresión y no un cambio de matriz."""
    alto, ancho = 180, 320
    rampa = np.zeros((alto, ancho, 3))
    rampa[..., 0] = np.linspace(0, 1, ancho)[None, :]
    rampa[..., 1] = np.linspace(0, 1, alto)[:, None]
    rampa[..., 2] = 0.4
    vuelta = m.h264_ida_y_vuelta(rampa)
    assert float(np.abs(vuelta - rampa).mean()) < 0.01


def test_el_grado_conocido_es_un_grado_y_no_la_identidad():
    enc = m.a_trabajo(m.escena(m.RIQUEZAS["media"], 5, 90, 160))
    for fuerza, (lo, hi) in (("suave", (1.5, 15.0)), ("fuerte", (4.0, 35.0))):
        medio = m.resumen(m.delta_e2000(enc, m.aplicar_grado(m.grado_aleatorio(3, fuerza), enc)))["medio"]
        assert lo < medio < hi, (fuerza, medio)


# ---------------------------------------------------------------------------
# Las cifras publicadas salen de los CSV
# ---------------------------------------------------------------------------


def _csv():
    from tests.calibracion.analizar import cargar

    rev = cargar("reverse_320_[0-9]*.csv")
    mat = cargar("matching_320_[0-9]*.csv")
    if not rev or not mat:
        pytest.skip("faltan los CSV de tests/calibracion/datos: .venv/bin/python -m tests.calibracion.medir")
    return rev, mat


def test_reverse_33_sin_compresion_da_siempre_score_uno_con_cualquier_error():
    rev, _ = _csv()
    limpias = [r for r in rev if r["tam_lut"] == 33.0 and r["compresion"] == 0.0]
    assert len(limpias) == 600  # 100 extracciones x 6 planos
    assert all(r["score"] == 1.0 for r in limpias)
    fuera = np.array([r["de_max"] for r in limpias if r["fuera_de_plano"] == 1.0])
    assert fuera.min() < 1.0 and fuera.max() > 20.0
    assert 0.10 < float(np.mean(fuera < LIMITE_T1_DELTA_E_MAXIMO)) < 0.25


def test_ningun_umbral_de_score_deja_el_95_por_ciento_bajo_el_limite():
    rev, mat = _csv()
    grupos = {
        "reverse 17 fuera": ([r for r in rev if r["tam_lut"] == 17.0 and r["fuera_de_plano"] == 1.0], "de_max", 3.0),
        "reverse 33 fuera": ([r for r in rev if r["tam_lut"] == 33.0 and r["fuera_de_plano"] == 1.0], "de_max", 3.0),
        "reverse 33 propio": ([r for r in rev if r["tam_lut"] == 33.0 and r["fuera_de_plano"] == 0.0], "de_max", 3.0),
        "matching": (mat, "de_medio", 2.0),
    }
    for nombre, (filas, k, limite) in grupos.items():
        s = np.array([r["score"] for r in filas])
        c = np.array([r[k] for r in filas]) < limite
        mejor = max(c[s >= t].mean() for t in np.unique(s) if (s >= t).sum() >= 20)
        assert mejor < 0.95, (nombre, mejor)


# ---------------------------------------------------------------------------
# El hallazgo, en vivo
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def centinela() -> dict[str, dict]:
    from tests.calibracion.medir import casos_reverse, medir_caso_reverse

    caso = casos_reverse()[CASO_CENTINELA]
    assert caso["compresion"] == 0 and caso["recorte"] == 0
    filas = medir_caso_reverse((CASO_CENTINELA, caso, 320, None))
    return {r["plano"]: r for r in filas if r["tam_lut"] == 33}


def test_centinela_una_extraccion_score_uno_y_maximos_de_2_4_a_7_0(centinela):
    """Lo que hoy pasa, con sus cifras (las filas del caso 44 en `datos/reverse_320_000_100.csv`).

    Si salta, algo ha cambiado en la confianza o en `invertir_grado`: hay que volver a
    medir, no retocar estos números.
    """
    propio = centinela["propio"]
    assert propio["score"] == 1.0 and propio["level"] == "alta"
    assert "no hay nada que objetar" in propio["reasons"]
    assert propio["de_max"] == pytest.approx(2.4121, abs=0.01)
    assert {p: r["score"] for p, r in centinela.items()} == dict.fromkeys(centinela, 1.0)
    assert centinela["otra_toma"]["de_max"] == pytest.approx(3.6594, abs=0.01)
    assert centinela["tono_60_exp"]["de_max"] == pytest.approx(7.0464, abs=0.01)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "La confianza de core.reverse no ve el plano al que se va a aplicar el grado: se calcula "
        "solo con el par de extracción (n_muestras, solape, condición, ΔE MEDIO en su plano y "
        "desajuste). Caso 44 (pobre, grado fuerte, sin compresión, 320×180, 33³): score 1.0 "
        "«alta» y ΔE2000 máximo 3.6594 en otra toma de la misma paleta, 7.0464 con el tono "
        "girado 60°, frente a 2.4121 en su plano. Sobre 200 extracciones, entre los casos «alta» "
        "fuera de plano el 89.7% (33³) y el 95.8% (17³) pasan de 3.0. Límite: "
        "LIMITE_T1_DELTA_E_MAXIMO = 3.0. Comando: " + COMANDO + " y "
        ".venv/bin/python -m tests.calibracion.analizar | grep 'CAL captura'. Para cerrarlo haría "
        "falta una confianza que mire el plano de destino, y eso es rediseñar la confianza, no "
        "calibrar umbrales."
    ),
)
def test_alta_en_reverse_garantiza_maximo_bajo_3_en_otro_plano(centinela):
    for plano, r in centinela.items():
        if plano != "propio" and r["score"] >= CONFIDENCE_ALTA:
            assert r["de_max"] < LIMITE_T1_DELTA_E_MAXIMO, (plano, r["de_max"])
