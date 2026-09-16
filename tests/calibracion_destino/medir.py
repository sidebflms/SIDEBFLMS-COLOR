"""Genera casos con verdad conocida, extrae LUTs y mide si `FeaturesDestino`
(`core.reverse.confianza_destino`) predice el ΔE2000 real de CADA plano de
destino.

REUTILIZA `tests/calibracion/material.py` ENTERO
--------------------------------------------------
Mismas escenas, mismo grado conocido, mismo códec, mismo ΔE2000 independiente
(`colour-science`) que usó el agente de calibración del día 4. Es el mismo
generador de material del repo, importado tal cual: si algo se ve distinto
entre `CALIBRACION-CONFIANZA.md` y este paquete, no es porque el material haya
cambiado.

DOS BLOQUES DE CASOS
---------------------
* `simple`: una extracción por caso (`invertir_grado`, `planos_acumulados=1`),
  barriendo riqueza × compresión × recorte × rejilla (17³ y 33³). Menos
  semillas que el día 4 (6 en vez de 10) porque aquí hay que pagar TAMBIÉN el
  bloque `lote`.
* `lote`: varias tomas de la MISMA paleta con el MISMO grado, acumuladas con
  `core.reverse.invertir_grado_lote`, con `planos_acumulados` en
  {1, 2, 3, 5, 8}. Es la única forma de que esa señal varíe: en `simple` vale
  siempre 1. Como las tomas del lote comparten grado a propósito (no es un
  test de coherencia), se pasa `verificar_coherencia=False`: no hay nada que
  discrepe y verificarlo sólo pagaría N ajustes de LUT de más sin medir nada
  nuevo.

En los dos bloques cada extracción se evalúa contra los mismos 6 planos de
destino que usó el día 4: el propio (para `lote`, la primera toma acumulada) y
5 "fuera de plano" (otra toma de la misma paleta, tono +15°, tono +60° y +0.7
pasos, tono +150° con más saturación, otra paleta). `calcular_features_destino`
necesita el plano de destino en el MISMO dominio que `coverage` (el cubo,
DESPUÉS del CDL): se le pasa `cdl.apply(plano)`, igual que hace
`tests/calibracion/medir.py` para `frac_px_en_celda_cubierta`.

Uso (desde la raíz del repo, en primer plano):

    .venv/bin/python -m tests.calibracion_destino.medir simple --desde 0 --hasta 60
    .venv/bin/python -m tests.calibracion_destino.medir lote   --desde 0 --hasta 25

Cada ejecución escribe un CSV en `tests/calibracion_destino/datos/`.

GUARDIA
-------
Igual que el día 4: al empezar imprime de dónde resuelve `core` y la huella
sha256 (AST) de los ficheros que calculan las señales y hacen la extracción.
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
             "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import ast  # noqa: E402
import csv  # noqa: E402
import hashlib  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from multiprocessing import get_context  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")

RAIZ = Path(__file__).resolve().parents[2]
DATOS = Path(__file__).resolve().parent / "datos"

#: Ficheros que deciden lo que se mide aquí: las señales nuevas y todo lo que
#: usan para llegar a `coverage` (extracción de uno o varios planos).
FICHEROS_VIGILADOS = (
    "core/reverse/confianza_destino.py",
    "core/reverse/acumulacion.py",
    "core/reverse/invertir.py",
    "core/reverse/lote.py",
    "core/contracts.py",
)

RESOLUCION = (180, 320)  # (alto, ancho), igual que el día 4 a 320×180
SEMILLAS_SIMPLE = 6  # 5 riquezas x 6 x 2 compresiones x 2 recortes = 120 extracciones
FUERZAS = ("suave", "fuerte")
PLANOS_ACUMULADOS_LOTE = (1, 2, 3, 5, 8)
REPETICIONES_LOTE = 2  # 5 riquezas x 5 valores de N x 2 compresiones x 2 repeticiones = 100 casos


def huella_core() -> str:
    """sha256 del AST (sin comentarios) de `FICHEROS_VIGILADOS`. Ver `tests/calibracion/medir.py`."""
    h = hashlib.sha256()
    for f in FICHEROS_VIGILADOS:
        h.update(ast.dump(ast.parse((RAIZ / f).read_text(encoding="utf-8"))).encode())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Enumeración de casos (determinista)
# ---------------------------------------------------------------------------


def casos_simple() -> list[dict]:
    from tests.calibracion.material import RIQUEZAS

    casos = []
    for i_r, riqueza in enumerate(RIQUEZAS):
        for semilla in range(SEMILLAS_SIMPLE):
            for comp in (0, 1):
                for recorte in (0, 1):
                    casos.append({
                        "bloque": "simple", "riqueza": riqueza, "compresion": comp,
                        "recorte": recorte, "semilla": semilla,
                        "fuerza": FUERZAS[semilla % 2],
                        "planos_acumulados": 1,
                        "semilla_escena": 81_000 + 100 * i_r + semilla,
                        "semilla_grado": 47_000 + 100 * i_r + semilla,
                    })
    return casos


def casos_lote() -> list[dict]:
    from tests.calibracion.material import RIQUEZAS

    casos = []
    for i_r, riqueza in enumerate(RIQUEZAS):
        for i_n, n_planos in enumerate(PLANOS_ACUMULADOS_LOTE):
            for comp in (0, 1):
                for rep in range(REPETICIONES_LOTE):
                    casos.append({
                        "bloque": "lote", "riqueza": riqueza, "compresion": comp,
                        "recorte": 0, "semilla": rep,
                        "fuerza": FUERZAS[rep % 2],
                        "planos_acumulados": n_planos,
                        # una semilla base por caso: cada una de las N tomas sale de
                        # sumarle un offset grande y distinto (igual que hace el día 4
                        # para separar la escena "propia" de las variantes de B).
                        "semilla_escena": 62_000 + 1_000 * i_r + 100 * i_n + rep,
                        "semilla_grado": 53_000 + 1_000 * i_r + 100 * i_n + rep,
                    })
    return casos


# ---------------------------------------------------------------------------
# Lo común a los dos bloques
# ---------------------------------------------------------------------------


def _plano(lin: np.ndarray, recorte: int, comp: int, directorio: str | None) -> np.ndarray:
    from tests.calibracion import material as m

    if recorte:
        lin = m.recorte_altas_luces(lin)
    enc = m.a_trabajo(lin)
    if comp:
        enc = m.h264_ida_y_vuelta(enc, directorio)
    return enc


def _planos_destino(pal, semilla_base: int, alto: int, ancho: int, recorte: int, comp: int,
                     directorio: str | None) -> list[tuple[str, np.ndarray]]:
    """Los 5 planos "fuera de plano" del día 4, a partir de la paleta de la escena
    "propia" (que cada llamante añade aparte, porque su semilla es distinta en
    `simple` y en `lote`)."""
    from tests.calibracion import material as m

    planos = []
    for k, tipo in enumerate(m.VARIANTES_B):
        lin_b = m.escena(m.variante(pal, tipo), semilla_base + 7919 * (k + 1), alto, ancho)
        planos.append((tipo, _plano(lin_b, recorte, comp, directorio)))
    return planos


def _filas_de_extraccion(
    *, caso: dict, idx: int, tam_lut: int, cdl, lut, coverage, planos: list[tuple[str, np.ndarray]],
    verdades: dict, disparidad: dict, cobertura_cubo: float, t_ext: float, directorio: str | None,
) -> list[dict]:
    """A partir de un `(cdl, lut, coverage)` ya extraído, una fila por plano de
    destino: las 4 señales de `FeaturesDestino` + el ΔE2000 real (colour) de
    ESE plano tras aplicar el grado extraído."""
    from core.reverse.confianza_destino import calcular_features_destino
    from tests.calibracion import material as m

    filas = []
    for nombre, p in planos:
        fuente = cdl.apply(p)
        feats = calcular_features_destino(
            coverage, fuente, planos_acumulados=int(caso["planos_acumulados"])
        )
        pred = lut.apply(fuente)
        res = m.resumen_con_sdr(*m.delta_e2000_y_luminancia(pred, verdades[nombre]))
        fila = {
            "idx": idx, "bloque": caso["bloque"], "riqueza": caso["riqueza"],
            "compresion": caso["compresion"], "recorte": caso["recorte"],
            "semilla": caso["semilla"], "fuerza": caso["fuerza"], "tam_lut": tam_lut,
            "plano": nombre, "fuera_de_plano": int(nombre != "propio"),
            "disparidad": disparidad[nombre],
            "planos_acumulados": int(caso["planos_acumulados"]),
            "cobertura_cubo": cobertura_cubo,
            "cobertura_destino": feats.cobertura_destino,
            "muestras_p10_zona": feats.muestras_p10_zona,
            "muestras_mediana_zona": feats.muestras_mediana_zona,
            "variance_zona": feats.variance_zona,
            "n_pixeles_destino": feats.n_pixeles_destino,
            "de_max": res["max"], "de_p95": res["p95"], "de_medio": res["medio"],
            "de_max_sdr": res["max_sdr"], "de_p95_sdr": res["p95_sdr"],
            "de_medio_sdr": res["medio_sdr"], "frac_px_l_mayor_100": res["frac_px_l_mayor_100"],
            "semilla_escena": caso["semilla_escena"],
            "t_extraccion_s": t_ext, "huella_core": HUELLA,
        }
        filas.append(fila)
    return filas


# ---------------------------------------------------------------------------
# simple: una extracción, planos_acumulados = 1
# ---------------------------------------------------------------------------


def medir_caso_simple(args: tuple[int, dict, str | None]) -> list[dict]:
    from core.reverse import invertir_grado
    from tests.calibracion import material as m

    idx, caso, directorio = args
    alto, ancho = RESOLUCION
    pal = m.RIQUEZAS[caso["riqueza"]]
    grado = m.grado_aleatorio(caso["semilla_grado"], caso["fuerza"])

    lin_a = m.escena(pal, caso["semilla_escena"], alto, ancho)
    enc_a = _plano(lin_a, caso["recorte"], caso["compresion"], directorio)
    col_a = m.aplicar_grado(grado, enc_a)
    if caso["compresion"]:
        col_a = m.h264_ida_y_vuelta(col_a, directorio)

    planos = [("propio", enc_a)] + _planos_destino(
        pal, caso["semilla_escena"], alto, ancho, caso["recorte"], caso["compresion"], directorio
    )
    verdades = {nombre: m.aplicar_grado(grado, p) for nombre, p in planos}
    disparidad = {nombre: m.interseccion_histogramas(enc_a, p) for nombre, p in planos}

    filas = []
    for tam in (17, 33):
        t0 = time.perf_counter()
        r = invertir_grado(enc_a.astype(np.float32), col_a.astype(np.float32), tam_lut=tam)
        t_ext = time.perf_counter() - t0
        filas.extend(_filas_de_extraccion(
            caso=caso, idx=idx, tam_lut=tam, cdl=r.cdl, lut=r.lut, coverage=r.coverage,
            planos=planos, verdades=verdades, disparidad=disparidad,
            cobertura_cubo=float(r.coverage.coverage_fraction()), t_ext=t_ext, directorio=directorio,
        ))
    return filas


# ---------------------------------------------------------------------------
# lote: N tomas de la MISMA paleta y el MISMO grado, acumuladas
# ---------------------------------------------------------------------------


def medir_caso_lote(args: tuple[int, dict, str | None]) -> list[dict]:
    from core.reverse import invertir_grado_lote
    from tests.calibracion import material as m

    idx, caso, directorio = args
    alto, ancho = RESOLUCION
    pal = m.RIQUEZAS[caso["riqueza"]]
    grado = m.grado_aleatorio(caso["semilla_grado"], caso["fuerza"])
    n_planos = int(caso["planos_acumulados"])

    pares = []
    encs = []
    for k in range(n_planos):
        # Offset grande y distinto por toma, para que no sean el mismo encuadre
        # (si lo fueran, "acumular 8 planos" sería acumular el mismo dato 8 veces).
        lin_k = m.escena(pal, caso["semilla_escena"] + 131 * k, alto, ancho)
        enc_k = _plano(lin_k, caso["recorte"], caso["compresion"], directorio)
        col_k = m.aplicar_grado(grado, enc_k)
        if caso["compresion"]:
            col_k = m.h264_ida_y_vuelta(col_k, directorio)
        pares.append((enc_k.astype(np.float32), col_k.astype(np.float32)))
        encs.append(enc_k)
    enc_a = encs[0]  # la toma "propia": es la que hace de referencia de paleta

    planos = [("propio", enc_a)] + _planos_destino(
        pal, caso["semilla_escena"], alto, ancho, caso["recorte"], caso["compresion"], directorio
    )
    verdades = {nombre: m.aplicar_grado(grado, p) for nombre, p in planos}
    disparidad = {nombre: m.interseccion_histogramas(enc_a, p) for nombre, p in planos}

    t0 = time.perf_counter()
    r = invertir_grado_lote(
        pares, tam_lut=33, verificar_coherencia=False, diagnosticar_planos=False,
    )
    t_ext = time.perf_counter() - t0
    return _filas_de_extraccion(
        caso=caso, idx=idx, tam_lut=33, cdl=r.cdl, lut=r.lut, coverage=r.coverage,
        planos=planos, verdades=verdades, disparidad=disparidad,
        cobertura_cubo=float(r.coverage.coverage_fraction()), t_ext=t_ext, directorio=directorio,
    )


HUELLA = huella_core()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bloque", choices=("simple", "lote"))
    ap.add_argument("--desde", type=int, default=0)
    ap.add_argument("--hasta", type=int, default=None)
    ap.add_argument("--casos", type=str, default=None, help="lista de índices separada por comas")
    ap.add_argument("--procesos", type=int, default=4)
    a = ap.parse_args()

    import core

    todos = casos_simple() if a.bloque == "simple" else casos_lote()
    if a.casos:
        indices = [int(x) for x in a.casos.split(",")]
        sufijo = "sel"
    else:
        hasta = len(todos) if a.hasta is None else min(a.hasta, len(todos))
        indices = list(range(a.desde, hasta))
        sufijo = f"{indices[0]:03d}_{indices[-1] + 1:03d}"
    print(f"[CALD guardia] core.__file__={core.__file__}")
    print(f"[CALD guardia] huella sha256[:12] de {', '.join(FICHEROS_VIGILADOS)} = {HUELLA}")
    print(f"[CALD guardia] {a.bloque}: {len(indices)} casos de {len(todos)}, {a.procesos} procesos")

    directorio = os.environ.get("TMPDIR")
    trabajo = [(i, todos[i], directorio) for i in indices]
    funcion = medir_caso_simple if a.bloque == "simple" else medir_caso_lote
    t0 = time.perf_counter()
    filas: list[dict] = []
    if a.procesos > 1:
        with get_context("spawn").Pool(a.procesos) as pool:
            for bloque in pool.imap(funcion, trabajo):
                filas.extend(bloque)
    else:
        for t in trabajo:
            filas.extend(funcion(t))
    DATOS.mkdir(parents=True, exist_ok=True)
    destino = DATOS / f"{a.bloque}_{sufijo}.csv"
    columnas: list[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with destino.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    print(f"[CALD hecho] {len(filas)} filas -> {destino.relative_to(RAIZ)} "
          f"en {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
