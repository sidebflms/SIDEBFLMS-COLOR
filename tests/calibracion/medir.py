"""Genera los pares con verdad conocida, pide la confianza a los motores y mide el error real.

Uso (desde la raíz del repo, en primer plano):

    .venv/bin/python -m tests.calibracion.medir reverse  --desde 0 --hasta 60
    .venv/bin/python -m tests.calibracion.medir matching --desde 0 --hasta 180
    .venv/bin/python -m tests.calibracion.medir reverse  --resol 640 --casos 0,17,...

Cada ejecución escribe un CSV en `tests/calibracion/datos/` con una fila por par
(extracción → plano de aplicación en `reverse`, clip → referencia en `matching`). Todo es
determinista: la semilla de cada caso sale de su índice.

QUÉ SE GUARDA DE CADA MOTOR
---------------------------
Lo que **declara**: `confidence.score`, `confidence.level`, `confidence.reasons` y las
métricas crudas y subnotas que la componen. Y lo que **pasa de verdad**: ΔE2000 máximo,
p95 y medio de `colour-science` entre lo que sale del motor y la verdad conocida.

LA VERDAD
---------
* `reverse`: la verdad en cualquier plano P es `grado(P)`, con el grado conocido aplicado
  por `material.aplicar_grado` (no por `CDL.apply` ni `LUT3D.apply`). La predicción es
  `lut.apply(cdl.apply(P))` con lo que devolvió `invertir_grado`. En su propio plano
  (`plano = propio`) y en cinco planos distintos (`fuera_de_plano = 1`). Con compresión,
  el original y el coloreado se comprimen **cada uno por su lado** para extraer, y la
  verdad de P se calcula sobre P ya comprimido: así el error mide el grado extraído, no
  el ruido del códec del plano de aplicación.
* `matching`: el clip es `O = cámara_O(S1)` y la referencia `R = look_R(cámara_R(S2))`.
  La verdad es lo que habría grabado la cámara R con el look R **de la escena del clip**:
  `look_R(cámara_R(cámara_O⁻¹(O)))`, calculada sobre O ya decodificado. La salida del
  motor es `cdl.apply(O)`, que es lo que la GUI aplica (`emparejar` sin `con_lut`, como
  `gui/datos_demo.py`). A la entrada se le pasan tantos píxeles como le pasa la GUI a
  640×360 (un paso de 4 → 14.400): la subnota `n_muestras` depende de eso.

GUARDIA
-------
Al empezar imprime de dónde ha resuelto `core` y la huella sha256 del código (AST) de los
ficheros que calculan la confianza. Si otro agente los cambia a mitad de la medida, la huella de las
filas deja de coincidir y se ve.
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

FICHEROS_DE_LA_CONFIANZA = (
    "core/umbrales.py",
    "core/contracts.py",
    "core/matching/confianza.py",
    "core/matching/empareja.py",
    "core/matching/contenido.py",
    "core/reverse/invertir.py",
)

RESOLUCIONES = {320: (180, 320), 640: (360, 640)}
SEMILLAS_REVERSE = 10  # 5 riquezas x 10 x 2 compresiones x 2 recortes = 200 extracciones
SEMILLAS_MATCHING = 6  # 5 riquezas x 6 x 6 disparidades x 2 x 2 = 720 pares
FUERZAS_REVERSE = ("suave", "fuerte")
FUERZAS_MATCHING = ("ninguno", "suave", "fuerte")
DISPARIDADES_MATCHING = ("identica", "otra_toma", "tono_15", "tono_60_exp", "tono_150_sat",
                         "otra_paleta")


def huella_core() -> str:
    """sha256 del **código** (el AST, sin comentarios) de los ficheros de la confianza.

    Sobre el AST y no sobre los bytes para que reescribir un comentario —como el de
    `CONFIDENCE_ALTA` al terminar esta medida— no la invalide, y cambiar un número sí.
    """
    h = hashlib.sha256()
    for f in FICHEROS_DE_LA_CONFIANZA:
        h.update(ast.dump(ast.parse((RAIZ / f).read_text(encoding="utf-8"))).encode())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Enumeración de casos (determinista)
# ---------------------------------------------------------------------------


def casos_reverse() -> list[dict]:
    from tests.calibracion.material import RIQUEZAS

    casos = []
    for i_r, riqueza in enumerate(RIQUEZAS):
        for semilla in range(SEMILLAS_REVERSE):
            for comp in (0, 1):
                for recorte in (0, 1):
                    casos.append({
                        "riqueza": riqueza, "compresion": comp, "recorte": recorte,
                        "semilla": semilla, "fuerza": FUERZAS_REVERSE[semilla % 2],
                        # la escena y el grado NO dependen de compresión ni recorte:
                        # así cada condición se compara contra el mismo par.
                        "semilla_escena": 91_000 + 100 * i_r + semilla,
                        "semilla_grado": 57_000 + 100 * i_r + semilla,
                    })
    return casos


def casos_matching() -> list[dict]:
    from tests.calibracion.material import RIQUEZAS

    casos = []
    for i_r, riqueza in enumerate(RIQUEZAS):
        for semilla in range(SEMILLAS_MATCHING):
            for i_d, disp in enumerate(DISPARIDADES_MATCHING):
                for comp in (0, 1):
                    for recorte in (0, 1):
                        casos.append({
                            "riqueza": riqueza, "disparidad_tipo": disp, "compresion": comp,
                            "recorte": recorte, "semilla": semilla,
                            "fuerza": FUERZAS_MATCHING[semilla % 3],
                            "semilla_escena": 31_000 + 100 * i_r + semilla,
                            "semilla_b": 41_000 + 100 * i_r + 10 * i_d + semilla,
                            "semilla_camaras": 71_000 + 100 * i_r + semilla,
                        })
    return casos


# ---------------------------------------------------------------------------
# Lo común a los dos motores
# ---------------------------------------------------------------------------


def _declarado(conf) -> dict:
    met = conf.metrics
    fila = {
        "score": float(conf.score),
        "level": conf.level,
        "reasons": " || ".join(conf.reasons),
        "n_reasons": len(conf.reasons),
    }
    for k in ("n_muestras", "solape", "condicion", "residuo_de", "extrapolacion", "ganancia",
              "fraccion_no_finita", "desajuste", "distancia_contenido"):
        fila[k] = float(met.get(k, float("nan")))
        fila[f"sub_{k}"] = float(met.get(f"subnota_{k}", float("nan")))
    return fila


def _plano(lin: np.ndarray, recorte: int, comp: int, directorio: str | None) -> np.ndarray:
    from tests.calibracion import material as m

    if recorte:
        lin = m.recorte_altas_luces(lin)
    enc = m.a_trabajo(lin)
    if comp:
        enc = m.h264_ida_y_vuelta(enc, directorio)
    return enc


# ---------------------------------------------------------------------------
# reverse
# ---------------------------------------------------------------------------


def medir_caso_reverse(args: tuple[int, dict, int, str | None]) -> list[dict]:
    from core.reverse import invertir_grado
    from tests.calibracion import material as m

    idx, caso, resol, directorio = args
    alto, ancho = RESOLUCIONES[resol]
    pal = m.RIQUEZAS[caso["riqueza"]]
    grado = m.grado_aleatorio(caso["semilla_grado"], caso["fuerza"])

    lin_a = m.escena(pal, caso["semilla_escena"], alto, ancho)
    enc_a = _plano(lin_a, caso["recorte"], caso["compresion"], directorio)
    col_a = m.aplicar_grado(grado, enc_a)
    if caso["compresion"]:
        col_a = m.h264_ida_y_vuelta(col_a, directorio)
    fuerza_medio = m.resumen(m.delta_e2000(enc_a, m.aplicar_grado(grado, enc_a)))["medio"]

    planos: list[tuple[str, np.ndarray]] = [("propio", enc_a)]
    for k, tipo in enumerate(m.VARIANTES_B):
        lin_b = m.escena(m.variante(pal, tipo), caso["semilla_escena"] + 7919 * (k + 1),
                         alto, ancho)
        planos.append((tipo, _plano(lin_b, caso["recorte"], caso["compresion"], directorio)))
    verdades = {nombre: m.aplicar_grado(grado, p) for nombre, p in planos}
    disparidad = {nombre: m.interseccion_histogramas(enc_a, p) for nombre, p in planos}

    filas = []
    for tam in (17, 33):
        t0 = time.perf_counter()
        r = invertir_grado(enc_a.astype(np.float32), col_a.astype(np.float32), tam_lut=tam)
        t_ext = time.perf_counter() - t0
        declarado = _declarado(r.confidence)
        cubiertas = r.coverage.covered_mask()
        for nombre, p in planos:
            pred = r.lut.apply(r.cdl.apply(p))
            res = m.resumen_con_sdr(*m.delta_e2000_y_luminancia(pred, verdades[nombre]))
            fuente = np.clip(r.cdl.apply(p).reshape(-1, 3), 0.0, 1.0) * (tam - 1)
            i = np.rint(fuente).astype(np.int64)
            frac_cub = float(cubiertas[i[:, 0], i[:, 1], i[:, 2]].mean())
            fila = {
                "motor": "reverse", "resol": resol, "caso": idx, **caso,
                "tam_lut": tam, "plano": nombre, "fuera_de_plano": int(nombre != "propio"),
                "disparidad": disparidad[nombre],
                "cobertura_cubo": float(r.coverage.coverage_fraction()),
                "frac_px_en_celda_cubierta": frac_cub,
                "fuerza_grado_medio": fuerza_medio,
                **declarado,
                "de_max": res["max"], "de_p95": res["p95"], "de_medio": res["medio"],
                "de_max_sdr": res["max_sdr"], "de_p95_sdr": res["p95_sdr"],
                "de_medio_sdr": res["medio_sdr"], "frac_px_l_mayor_100": res["frac_px_l_mayor_100"],
                "repo_de_max_propio": float(r.delta_e_max),
                "repo_de_p95_propio": float(r.delta_e_p95),
                "repo_de_medio_propio": float(r.delta_e_mean),
                "t_extraccion_s": t_ext, "huella_core": HUELLA,
            }
            filas.append(fila)
    return filas


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------


def medir_caso_matching(args: tuple[int, dict, int, str | None]) -> list[dict]:
    from core.matching import emparejar
    from tests.calibracion import material as m

    idx, caso, resol, directorio = args
    alto, ancho = RESOLUCIONES[resol]
    pal = m.RIQUEZAS[caso["riqueza"]]
    paso = ancho // 160  # 14.400 píxeles, lo mismo que la GUI a 640×360 con paso 4

    s1 = m.escena(pal, caso["semilla_escena"], alto, ancho)
    if caso["disparidad_tipo"] == "identica":
        s2 = s1
    else:
        s2 = m.escena(m.variante(pal, caso["disparidad_tipo"]), caso["semilla_b"], alto, ancho)
    m_o = m.camara_aleatoria(caso["semilla_camaras"])
    m_r = m.camara_aleatoria(caso["semilla_camaras"] + 1)
    if caso["fuerza"] == "ninguno":
        look = None
    else:
        look = m.grado_aleatorio(caso["semilla_camaras"] + 2, caso["fuerza"])

    def _con_look(enc: np.ndarray) -> np.ndarray:
        return enc if look is None else m.aplicar_grado(look, enc)

    o_enc = _plano(s1 @ m_o.T, caso["recorte"], caso["compresion"], directorio)
    r_enc = _plano(s2 @ m_r.T, caso["recorte"], 0, directorio)
    r_enc = _con_look(r_enc)
    if caso["compresion"]:
        r_enc = m.h264_ida_y_vuelta(r_enc, directorio)

    # La verdad: la escena que ha grabado O, vista por la cámara R con el look R.
    lin_o = m.de_trabajo(o_enc)
    verdad = _con_look(m.a_trabajo(lin_o @ (m_r @ np.linalg.inv(m_o)).T))

    t0 = time.perf_counter()
    res_match = emparejar(o_enc[::paso, ::paso].reshape(-1, 3),
                          r_enc[::paso, ::paso].reshape(-1, 3))
    t_ext = time.perf_counter() - t0
    salida = res_match.cdl.apply(o_enc)
    res = m.resumen_con_sdr(*m.delta_e2000_y_luminancia(salida, verdad))
    sin_tocar = m.resumen(m.delta_e2000(o_enc, verdad))
    return [{
        "motor": "matching", "resol": resol, "caso": idx, **caso,
        "disparidad": m.interseccion_histogramas(m.a_trabajo(s1), m.a_trabajo(s2)),
        **_declarado(res_match.confidence),
        "content_mismatch": int(res_match.content_mismatch),
        "repo_delta_e_after": float(res_match.delta_e_after),
        "de_max": res["max"], "de_p95": res["p95"], "de_medio": res["medio"],
        "de_max_sdr": res["max_sdr"], "de_p95_sdr": res["p95_sdr"],
        "de_medio_sdr": res["medio_sdr"], "frac_px_l_mayor_100": res["frac_px_l_mayor_100"],
        "sin_tocar_de_medio": sin_tocar["medio"], "sin_tocar_de_max": sin_tocar["max"],
        "t_extraccion_s": t_ext, "huella_core": HUELLA,
    }]


HUELLA = huella_core()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("motor", choices=("reverse", "matching"))
    ap.add_argument("--resol", type=int, default=320, choices=sorted(RESOLUCIONES))
    ap.add_argument("--desde", type=int, default=0)
    ap.add_argument("--hasta", type=int, default=None)
    ap.add_argument("--casos", type=str, default=None, help="lista de índices separada por comas")
    ap.add_argument("--procesos", type=int, default=4)
    a = ap.parse_args()

    import core

    todos = casos_reverse() if a.motor == "reverse" else casos_matching()
    if a.casos:
        indices = [int(x) for x in a.casos.split(",")]
        sufijo = "sel"
    else:
        hasta = len(todos) if a.hasta is None else min(a.hasta, len(todos))
        indices = list(range(a.desde, hasta))
        sufijo = f"{indices[0]:03d}_{indices[-1] + 1:03d}"
    print(f"[CAL guardia] core.__file__={core.__file__}")
    print(f"[CAL guardia] huella sha256[:12] de {', '.join(FICHEROS_DE_LA_CONFIANZA)} = {HUELLA}")
    print(f"[CAL guardia] {a.motor}: {len(indices)} casos de {len(todos)}, {a.resol}, "
          f"{a.procesos} procesos")

    directorio = os.environ.get("TMPDIR")
    trabajo = [(i, todos[i], a.resol, directorio) for i in indices]
    funcion = medir_caso_reverse if a.motor == "reverse" else medir_caso_matching
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
    destino = DATOS / f"{a.motor}_{a.resol}_{sufijo}.csv"
    columnas: list[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with destino.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    print(f"[CAL hecho] {len(filas)} filas -> {destino.relative_to(RAIZ)} "
          f"en {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
