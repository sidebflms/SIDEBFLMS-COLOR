"""T5: ¿sirve el grado extraido de UN plano para los OTROS planos?

Se extrae el grado del par (A, A') con `core.reverse.invertir_grado` y se aplica
a otra escena B -- `lut.apply(cdl.apply(B))`, lo que haria el colorista -- y se
compara con B', que es B pasada por el grado conocido de verdad. Todo lo que no
es `invertir_grado` y las dataclases que devuelve sale de `t5_material.py`.

COMO SE EJECUTA, Y POR QUE ASI
------------------------------
Contra la copia congelada `.snapshots/v0.3.0`, con ese directorio como `cwd`:

    cd "<repo>/.snapshots/v0.3.0" && PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python \\
        -m pytest ../../tests/fuera_de_plano -s -p no:cacheprovider \\
        --import-mode=importlib --noconftest

* `--import-mode=importlib`: en el modo por defecto (`prepend`) pytest mete la
  raiz del REPO VIVO en `sys.path[0]` antes de importar este archivo, porque
  `tests/` y esta carpeta son paquetes, y `import core` resolveria al vivo.
  Es exactamente el resultado fantasma del dia 3.
* `--noconftest`: `tests/conftest.py` del repo vivo importa `core` y
  `tests.media`; no lo necesito y no quiero que decida nada.
* `PYTHONDONTWRITEBYTECODE=1`: que importar `core` no escriba `.pyc` dentro de
  `.snapshots/`.
* Este archivo mete SU PROPIA carpeta en `sys.path` para importar
  `t5_material` como modulo suelto (con `importlib` no hay paquete `tests`
  que valga: el `tests` del `cwd` es el de la copia y no tiene esta carpeta).

Y por si alguien lo lanza de otra forma: `EN_COPIA` comprueba donde resolvio
`core`, y si no es la copia congelada los tests se SALTAN diciendo por que. Las
cifras de `MEDICION-T5.md` son de v0.3.0 y no valen para otro codigo.
"""

from __future__ import annotations

import csv
import functools
import os
import sys
from pathlib import Path

import numpy as np
import pytest

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

import t5_material as M  # noqa: E402

import core  # noqa: E402

CORE_FILE = str(Path(core.__file__).resolve())
EN_COPIA = "/.snapshots/v0.3.0/core/" in CORE_FILE
_PERMITIR_VIVO = os.environ.get("T5_PERMITIR_REPO_VIVO") == "1"

pytestmark = pytest.mark.skipif(
    not (EN_COPIA or _PERMITIR_VIVO),
    reason=(
        f"T5 mide v0.3.0 y `core` ha resuelto a {CORE_FILE}. Ejecutalo desde "
        "`.snapshots/v0.3.0` con `../../.venv/bin/python -m pytest ../../tests/fuera_de_plano -s "
        "-p no:cacheprovider --import-mode=importlib --noconftest` (ver MEDICION-T5.md), o "
        "pon T5_PERMITIR_REPO_VIVO=1 sabiendo que las cifras ya no seran las publicadas."
    ),
)

LOOKS = ("global", "secundarias")
SEMILLA_A = 5001
SEMILLA_B = 7001
UMBRAL_MAX = 3.0

#: Tramos de `solape_histogramas(A, B)`. Los cortes son mios y estan escritos
#: antes de mirar el ΔE por nivel (se miro el ΔE por punto, no por tramo).
NIVELES: tuple[tuple[str, float], ...] = (
    ("N1 casi identicas (solape >= 0.55)", 0.55),
    ("N2 parecidas (0.30 <= solape < 0.55)", 0.30),
    ("N3 distintas (0.10 <= solape < 0.30)", 0.10),
    ("N4 muy distintas (solape < 0.10)", 0.0),
)
#: Radios en el dominio del LUT (0..1). Una celda de 33 mide 1/32 = 0.03125.
RADIOS: tuple[float, ...] = (0.0025, 0.005, 0.01)
TRAMOS_DISTANCIA: tuple[tuple[float, float], ...] = (
    (0.0, 0.0025), (0.0025, 0.005), (0.005, 0.01), (0.01, 0.02), (0.02, 0.04), (0.04, 9.0),
)
TRAMOS_MIN_COUNTS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 4), (4, 20), (20, 200), (200, 10**9),
)


def _imprimir(etiqueta: str, **cifras) -> None:
    partes = []
    for k, v in cifras.items():
        partes.append(f"{k}={v:.6g}" if isinstance(v, float) else f"{k}={v}")
    print(f"[T5 {etiqueta}] " + "  ".join(partes))


def _medir(resultado, x: np.ndarray, x_prima: np.ndarray, arbol_a) -> dict[str, float]:
    """Aplica el grado extraido a `x` y lo compara con `x_prima`.

    Mascaras, las dos sobre `cdl_extraido(x)`, que es el dominio del LUT:
    * «celda cercana»: la celda mas cercana esta cubierta (`covered_mask`, >= 4
      muestras), o esta inventada (`counts == 0`), o esta en medio (1..3). Es la
      definicion que usa el repo para su «zona cubierta».
    * «estricta»: los OCHO nodos que usa la interpolacion estan cubiertos, o los
      ocho estan inventados. Un pixel con la celda cercana cubierta puede estar
      apoyandose en vecinos inventados; esta mascara lo separa.

    Y dos desgloses que no son del repo sino mios, porque las mascaras de
    celda resultaron no explicar el error (ver MEDICION-T5.md):
    * por DISTANCIA (euclidea, en el dominio del LUT) al pixel de A mas cercano
      pasado por el mismo CDL extraido. `arbol_a` es un cKDTree de esos pixeles;
    * por el MINIMO de `counts` entre los ocho nodos que usa la interpolacion.
    """
    post = resultado.cdl.apply(np.asarray(x, dtype=np.float64))
    pred = resultado.lut.apply(post)
    de = M.delta_e2000(x_prima, pred).reshape(-1)
    # L* > 100 = por encima del blanco difuso (brillos especulares, HDR). Ahi el
    # ΔE2000 no es una medida perceptual valida (el Lab no esta definido para
    # eso), asi que cada cifra se da tambien SIN esos pixeles: «sdr».
    m_sdr = M.trabajo_a_lab(x_prima).reshape(-1, 3)[:, 0] <= 100.0

    counts = np.asarray(resultado.coverage.counts).reshape(-1)
    cubierta = np.asarray(resultado.coverage.covered_mask()).reshape(-1)
    cerca = M.celda_mas_cercana(post)
    m_cub = cubierta[cerca]
    m_inv = counts[cerca] == 0
    m_medio = ~m_cub & ~m_inv
    nodos = M.nodos_trilineales(post)
    m_cub8 = cubierta[nodos].all(axis=0)
    m_inv8 = (counts[nodos] == 0).all(axis=0)

    out: dict[str, float] = {}
    for nombre, mascara in (
        ("todo", None),
        ("cub", m_cub),
        ("inv", m_inv),
        ("medio", m_medio),
        ("cub8", m_cub8),
        ("inv8", m_inv8),
        ("sdr", m_sdr),
        ("cubsdr", m_cub & m_sdr),
        ("invsdr", m_inv & m_sdr),
        ("cub8sdr", m_cub8 & m_sdr),
        ("inv8sdr", m_inv8 & m_sdr),
    ):
        for k, v in M.resumen(de, mascara).items():
            out[f"{nombre}_{k}"] = v
    n = float(de.size)
    out["frac_px_cub"] = float(m_cub.sum()) / n
    out["frac_px_inv"] = float(m_inv.sum()) / n
    out["frac_px_cub8"] = float(m_cub8.sum()) / n
    out["frac_px_inv8"] = float(m_inv8.sum()) / n
    out["frac_px_hdr"] = float((~m_sdr).sum()) / n
    out["frac_fuera_dominio"] = float(((post < 0) | (post > 1)).any(axis=-1).mean())

    dist, _ = arbol_a.query(np.clip(post.reshape(-1, 3), 0.0, 1.0), k=1)
    for radio in RADIOS:
        out[f"frac_px_a_{radio:g}"] = float((dist < radio).mean())
    for k, (lo, hi) in enumerate(TRAMOS_DISTANCIA):
        m = (dist >= lo) & (dist < hi)
        out[f"dist{k}_n"] = float(m.sum())
        out[f"dist{k}_suma"] = float(de[m].sum())
        out[f"dist{k}_max"] = float(de[m].max()) if m.any() else float("nan")
    min_counts = counts[nodos].min(axis=0)
    for k, (lo, hi) in enumerate(TRAMOS_MIN_COUNTS):
        m = (min_counts >= lo) & (min_counts < hi)
        out[f"minc{k}_n"] = float(m.sum())
        out[f"minc{k}_suma"] = float(de[m].sum())
        out[f"minc{k}_max"] = float(de[m].max()) if m.any() else float("nan")
    return out


def _nivel(solape: float) -> str:
    """El nivel de disparidad es un TRAMO del numero, no un adjetivo."""
    for nombre, minimo in NIVELES:
        if solape >= minimo:
            return nombre
    return NIVELES[-1][0]


@functools.cache
def barrido() -> tuple[list[dict], list[dict]]:
    """Todo el barrido: 2 looks x 6 escenas A x (A->A + 6 escenas B)."""
    from scipy.spatial import cKDTree

    from core.reverse import invertir_grado

    filas: list[dict] = []
    refs: list[dict] = []
    for look in LOOKS:
        tabla = M.tabla_look(look)
        for ia, pal in enumerate(M.PALETAS_A):
            a = M.escena_trabajo(pal, SEMILLA_A + ia)
            a_prima = M.colorear(a, tabla)
            # Un NaN en el material lo descartaria el repo EN SILENCIO para la cifra.
            assert np.isfinite(a).all() and np.isfinite(a_prima).all(), pal.nombre
            r = invertir_grado(a, a_prima)
            cob_a = r.coverage.coverage_fraction()
            con_dato_a = float((np.asarray(r.coverage.counts) > 0).mean())
            aviso = any("cubre el" in razon for razon in r.confidence.reasons)
            fuerza = M.resumen(M.delta_e2000(a, a_prima))
            post_a = r.cdl.apply(a.astype(np.float64)).reshape(-1, 3)
            arbol = cKDTree(np.clip(post_a, 0.0, 1.0))
            # Cuanto se separa el CDL extraido del conocido, sobre los pixeles de A.
            cdl_dif = float(np.abs(post_a - M.aplicar_cdl(a).reshape(-1, 3)).max())

            ref = {"look": look, "A": pal.nombre, "B": "A->A (mismo plano)", "cob_A": cob_a,
                   "con_dato_A": con_dato_a, "solape_hist": 1.0, "celdas_B_en_A": 1.0,
                   "aviso_cobertura": aviso, "fuerza_grado_medio": fuerza["medio"],
                   "repo_de_max": float(r.delta_e_max),
                   "repo_de_max_cubierto": float(r.confidence.metrics["de_max_cubierto"]),
                   "repo_de_medio_cubierto": float(r.confidence.metrics["de_medio_cubierto"]),
                   "cdl_extraido": (r.cdl.slope, r.cdl.offset, r.cdl.power, r.cdl.saturation),
                   "cdl_dif_max_sobre_A": cdl_dif, "nivel": "referencia"}
            ref.update(_medir(r, a, a_prima, arbol))
            refs.append(ref)

            for jb, (etiqueta, pal_b) in enumerate(M.paletas_b(pal)):
                b = M.escena_trabajo(pal_b, SEMILLA_B + 100 * ia + jb)
                b_prima = M.colorear(b, tabla)
                assert np.isfinite(b).all() and np.isfinite(b_prima).all(), (pal.nombre, etiqueta)
                fila = {"look": look, "A": pal.nombre, "B": etiqueta, "cob_A": cob_a,
                        "con_dato_A": con_dato_a,
                        "solape_hist": M.solape_histogramas(a, b),
                        "celdas_B_en_A": M.fraccion_celdas_b_en_a(a, b),
                        "aviso_cobertura": aviso}
                fila["nivel"] = _nivel(fila["solape_hist"])
                fila.update(_medir(r, b, b_prima, arbol))
                filas.append(fila)
    return filas, refs


def _corte(filas: list[dict], var: str, metrica: str = "todo_max") -> dict[str, float]:
    """Menor valor de `var` a partir del cual TODOS los puntos quedan por debajo de 3.0.

    `peor_que_falla` = el mayor `var` entre los puntos que NO bajan de 3.0.
    `corte` = el menor `var` de los que bajan, por encima de ese. NaN = no hay corte.
    """
    fallan = [f[var] for f in filas if not f[metrica] < UMBRAL_MAX]
    pasan = [f[var] for f in filas if f[metrica] < UMBRAL_MAX]
    peor = max(fallan) if fallan else float("nan")
    candidatos = [v for v in pasan if not fallan or v > peor]
    return {
        "n_puntos": float(len(filas)),
        "n_bajan_de_3": float(len(pasan)),
        "peor_que_falla": peor,
        "corte": min(candidatos) if candidatos else float("nan"),
    }


def _spearman(x: list[float], y: list[float]) -> float:
    from scipy.stats import spearmanr

    return float(spearmanr(x, y).statistic)


# ---------------------------------------------------------------------------
# Guardia: contra que codigo se esta midiendo
# ---------------------------------------------------------------------------


def test_t5_guardia_core_resuelve_a_la_copia_congelada():
    import core.reverse

    print(f"\n[T5 guardia] core.__file__={CORE_FILE}")
    print(f"[T5 guardia] core.reverse.__file__={Path(core.reverse.__file__).resolve()}")
    print(f"[T5 guardia] t5_material.__file__={Path(M.__file__).resolve()}")
    assert EN_COPIA, CORE_FILE
    assert "/.snapshots/v0.3.0/core/reverse/" in str(Path(core.reverse.__file__).resolve())


# ---------------------------------------------------------------------------
# El material es plausible
# ---------------------------------------------------------------------------


def test_t5_el_grado_conocido_es_plausible():
    """Ni identidad ni disparate: `qc_lut` limpio, lejos de la identidad, y mi
    aplicacion del grado coincide con la del repo (si no, B' y la prediccion
    diferirian por la aplicacion y no por el LUT)."""
    from core.contracts import CDL, LUT3D
    from core.io import qc_lut

    identidad = np.stack(np.meshgrid(*[np.linspace(0, 1, M.TAM_LUT)] * 3, indexing="ij"), -1)
    cdl = CDL(M.CDL_SLOPE, M.CDL_OFFSET, M.CDL_POWER, M.CDL_SAT)
    a = M.escena_trabajo(M.PALETAS_A[1], SEMILLA_A + 1)
    for look in LOOKS:
        tabla = M.tabla_look(look)
        lut = LUT3D(table=tabla.astype(np.float32))
        qc = qc_lut(lut)
        dif_aplicacion = float(np.abs(M.colorear(a, tabla) - lut.apply(cdl.apply(a))).max())
        _imprimir(
            f"material {look}",
            qc_ok=qc.ok,
            codigos=",".join(qc.codigos()) or "-",
            celdas_no_monotonas=qc.metricas.get("celdas_no_monotonas", float("nan")),
            escalones_banding=qc.metricas.get("escalones_de_banding", float("nan")),
            max_dist_identidad=float(np.abs(tabla - identidad).max()),
            dif_mi_aplicacion_vs_repo=dif_aplicacion,
        )
        assert qc.ok, qc.codigos()
        assert float(np.abs(tabla - identidad).max()) > 0.05
        # float32 del coloreado: la diferencia es redondeo, no aplicacion.
        assert dif_aplicacion < 1e-5


# ---------------------------------------------------------------------------
# La medida
# ---------------------------------------------------------------------------


def test_t5_tabla_curva_y_corte():
    """Imprime la tabla entera, la referencia A->A, los cortes y los desgloses.
    Escribe `resultados_t5.csv` y `curva_t5.png` en esta carpeta. No afirma nada."""
    filas, refs = barrido()

    print("\n[T5] ===== referencia A->A (extraigo de A, compruebo sobre A) =====")
    for r in refs:
        _imprimir(
            f"ref {r['look']} | {r['A']}",
            cob_A=r["cob_A"], con_dato_A=r["con_dato_A"], aviso_cobertura=r["aviso_cobertura"],
            fuerza_grado_medio=r["fuerza_grado_medio"],
            todo_medio=r["todo_medio"], todo_p95=r["todo_p95"], todo_max=r["todo_max"],
            cub_medio=r["cub_medio"], cub_p95=r["cub_p95"], cub_max=r["cub_max"],
            frac_px_cub=r["frac_px_cub"],
            sdr_medio=r["sdr_medio"], sdr_p95=r["sdr_p95"], sdr_max=r["sdr_max"],
            frac_px_hdr=r["frac_px_hdr"],
            repo_de_max=r["repo_de_max"], repo_de_max_cubierto=r["repo_de_max_cubierto"],
        )
        slope, offset, power, sat = r["cdl_extraido"]
        print(f"[T5 cdl {r['look']} | {r['A']}] extraido slope={np.round(slope, 4).tolist()} "
              f"offset={np.round(offset, 4).tolist()} power={np.round(power, 4).tolist()} "
              f"sat={sat:.4f} | conocido slope={list(M.CDL_SLOPE)} offset={list(M.CDL_OFFSET)} "
              f"power={list(M.CDL_POWER)} sat={M.CDL_SAT} | dif_max_sobre_A="
              f"{r['cdl_dif_max_sobre_A']:.6g}")

    print("\n[T5] ===== A->B (extraigo de A, aplico a B, comparo con B') =====")
    for f in filas:
        _imprimir(
            f"AB {f['look']} | {f['A']} | {f['B']}",
            nivel=f["nivel"][:2],
            cob_A=f["cob_A"], solape_hist=f["solape_hist"], celdas_B_en_A=f["celdas_B_en_A"],
            frac_px_B_cub=f["frac_px_cub"], frac_px_B_inv=f["frac_px_inv"],
            frac_px_B_a_0005=f["frac_px_a_0.005"],
            todo_medio=f["todo_medio"], todo_p95=f["todo_p95"], todo_max=f["todo_max"],
            frac_px_mayor_3=f["todo_frac_mayor_3"],
            sdr_medio=f["sdr_medio"], sdr_p95=f["sdr_p95"], sdr_max=f["sdr_max"],
            frac_px_hdr=f["frac_px_hdr"],
            cub_medio=f["cub_medio"], cub_p95=f["cub_p95"], cub_max=f["cub_max"],
            inv_medio=f["inv_medio"], inv_p95=f["inv_p95"], inv_max=f["inv_max"],
            cub8_n=f["cub8_n"], cub8_max=f["cub8_max"], inv8_n=f["inv8_n"], inv8_max=f["inv8_max"],
            fuera_dominio=f["frac_fuera_dominio"],
        )

    print("\n[T5] ===== por nivel de disparidad (tramos de solape_hist) =====")
    for nombre, _ in NIVELES:
        sel = [f for f in filas if f["nivel"] == nombre]
        if not sel:
            _imprimir(f"nivel {nombre}", puntos=0)
            continue
        _imprimir(
            f"nivel {nombre}",
            puntos=len(sel),
            solape_min=min(f["solape_hist"] for f in sel),
            solape_max=max(f["solape_hist"] for f in sel),
            mediana_medio=float(np.median([f["todo_medio"] for f in sel])),
            peor_medio=max(f["todo_medio"] for f in sel),
            mediana_p95=float(np.median([f["todo_p95"] for f in sel])),
            peor_p95=max(f["todo_p95"] for f in sel),
            mediana_max=float(np.median([f["todo_max"] for f in sel])),
            mejor_max=min(f["todo_max"] for f in sel),
            peor_max=max(f["todo_max"] for f in sel),
            puntos_max_bajo_3=sum(f["todo_max"] < UMBRAL_MAX for f in sel),
            puntos_p95_bajo_3=sum(f["todo_p95"] < UMBRAL_MAX for f in sel),
            mediana_max_sdr=float(np.median([f["sdr_max"] for f in sel])),
            mejor_max_sdr=min(f["sdr_max"] for f in sel),
            peor_max_sdr=max(f["sdr_max"] for f in sel),
            puntos_max_sdr_bajo_3=sum(f["sdr_max"] < UMBRAL_MAX for f in sel),
        )

    print("\n[T5] ===== cortes: ¿a partir de que valor TODOS los puntos bajan de 3.0? =====")
    for grupo, sel in (("ambos looks", filas),
                       ("global", [f for f in filas if f["look"] == "global"]),
                       ("secundarias", [f for f in filas if f["look"] == "secundarias"])):
        for var in ("frac_px_cub", "cob_A", "solape_hist", "celdas_B_en_A", "frac_px_a_0.005"):
            for met in ("todo_max", "todo_p95", "sdr_max"):
                _imprimir(f"corte {grupo} | {var} | {met}", **_corte(sel, var, met))

    print("\n[T5] ===== ¿que variable explica mejor el error? (Spearman, n puntos A->B) =====")
    variables = ("frac_px_cub", "frac_px_cub8", "cob_A", "solape_hist", "celdas_B_en_A",
                 "frac_px_a_0.0025", "frac_px_a_0.005", "frac_px_a_0.01")
    for met in ("todo_max", "sdr_max", "todo_p95", "todo_medio"):
        y = [f[met] for f in filas]
        _imprimir(f"spearman {met}", n=len(filas),
                  **{v: _spearman([f[v] for f in filas], y) for v in variables})

    print("\n[T5] ===== desglose por mascara de celda (todos los A->B) =====")
    for zona in ("cub", "medio", "inv", "cub8", "inv8", "cubsdr", "invsdr", "cub8sdr", "inv8sdr"):
        con = [f for f in filas if f[f"{zona}_n"] > 0]
        maximos = [f[f"{zona}_max"] for f in con]
        peor = max(con, key=lambda f: f[f"{zona}_max"]) if con else None
        _imprimir(
            f"zona {zona}",
            pixeles_mayor_3=float(sum(f[f"{zona}_frac_mayor_3"] * f[f"{zona}_n"] for f in con)),
            peor_en=f"{peor['look']}|{peor['A'][:2]}|{peor['B'][:2]}" if peor else "-",
            puntos_con_pixeles=len(con),
            pixeles=float(sum(f[f"{zona}_n"] for f in con)),
            media_ponderada=(float(sum(f[f"{zona}_medio"] * f[f"{zona}_n"] for f in con))
                             / max(sum(f[f"{zona}_n"] for f in con), 1.0)),
            peor_max=max(maximos) if maximos else float("nan"),
            mediana_de_max=float(np.median(maximos)) if maximos else float("nan"),
            puntos_con_max_bajo_3=sum(m < UMBRAL_MAX for m in maximos),
            tasa_px_mayor_3=(float(sum(f[f"{zona}_frac_mayor_3"] * f[f"{zona}_n"] for f in con))
                             / max(sum(f[f"{zona}_n"] for f in con), 1.0)),
        )

    print("\n[T5] ===== ¿en que zona cae el PEOR pixel de cada par A->B? =====")
    for etiqueta, zonas in (("todo", ("cub", "medio", "inv")), ("sdr", ("cubsdr", "invsdr"))):
        cuenta = dict.fromkeys(zonas, 0)
        for f in filas:
            validas = [z for z in zonas if f[f"{z}_n"] > 0]
            cuenta[max(validas, key=lambda z: f[f"{z}_max"])] += 1
        _imprimir(f"peor pixel {etiqueta}", puntos=len(filas), **cuenta)

    for titulo, clave, tramos in (
        ("distancia al pixel de A mas cercano (dominio del LUT; celda = 0.03125)", "dist",
         TRAMOS_DISTANCIA),
        ("minimo de counts entre los 8 nodos de la interpolacion", "minc", TRAMOS_MIN_COUNTS),
    ):
        for grupo, sel in (("A->B", filas), ("A->A", refs)):
            print(f"\n[T5] ===== desglose por {titulo} · {grupo} =====")
            for k, (lo, hi) in enumerate(tramos):
                n = sum(f[f"{clave}{k}_n"] for f in sel)
                maximos = [f[f"{clave}{k}_max"] for f in sel if f[f"{clave}{k}_n"] > 0]
                _imprimir(
                    f"{clave} {grupo} [{lo:g}, {hi:g})",
                    pixeles=float(n),
                    fraccion=float(n) / sum(f["todo_n"] for f in sel),
                    medio=float(sum(f[f"{clave}{k}_suma"] for f in sel)) / max(n, 1.0),
                    peor_max=max(maximos) if maximos else float("nan"),
                )

    _escribir_csv(filas, refs)
    _dibujar(filas, refs)


def _anatomia(look: str, indice_a: int, indice_b: int, mascara: str) -> None:
    """Imprime el peor pixel de un par A->B dentro de una mascara, con todo lo que
    hace falta para leerlo: entrada, nodos, distancia a A, L* y prediccion."""
    from scipy.spatial import cKDTree

    from core.reverse import invertir_grado

    tabla = M.tabla_look(look)
    pal = M.PALETAS_A[indice_a]
    a = M.escena_trabajo(pal, SEMILLA_A + indice_a)
    r = invertir_grado(a, M.colorear(a, tabla))
    etiqueta, pal_b = M.paletas_b(pal)[indice_b]
    b = M.escena_trabajo(pal_b, SEMILLA_B + 100 * indice_a + indice_b)
    b_prima = M.colorear(b, tabla)
    post = r.cdl.apply(b.astype(np.float64)).reshape(-1, 3)
    pred = r.lut.apply(post)
    de = M.delta_e2000(b_prima.reshape(-1, 3), pred)
    counts = np.asarray(r.coverage.counts).reshape(-1)
    cubierta = np.asarray(r.coverage.covered_mask()).reshape(-1)
    nodos = M.nodos_trilineales(post)
    sel = cubierta[nodos].all(axis=0) if mascara == "cub8" else np.ones(de.size, dtype=bool)
    i = int(np.flatnonzero(sel)[np.argmax(de[sel])])
    post_a = np.clip(r.cdl.apply(a.astype(np.float64)).reshape(-1, 3), 0.0, 1.0)
    dist, _ = cKDTree(post_a).query(np.clip(post[i], 0.0, 1.0))
    lab = M.trabajo_a_lab(b_prima.reshape(-1, 3)[i])
    print(
        f"[T5 anatomia {look} | {pal.nombre} | {etiqueta} | mascara={mascara}] "
        f"de={de[i]:.4f} pixel=({i // M.ANCHO},{i % M.ANCHO}) B={np.round(b.reshape(-1, 3)[i].astype(np.float64), 4).tolist()} "
        f"cdl_extraido(B)={np.round(post[i], 4).tolist()} counts_8_nodos={counts[nodos[:, i]].tolist()} "
        f"distancia_al_pixel_de_A_mas_cercano={dist:.4f} (celda=0.03125) "
        f"B'={np.round(b_prima.reshape(-1, 3)[i].astype(np.float64), 4).tolist()} prediccion={np.round(pred[i], 4).tolist()} "
        f"L*_de_B'={lab[0]:.2f}"
    )


def test_t5_anatomia_de_los_peores_pixeles():
    """Dos pixeles concretos, para que el desglose no sea solo agregados:
    el peor con los OCHO nodos cubiertos (secundarias, A4, B0) y el peor de todo
    el barrido (global, A6, B3). No afirma nada."""
    print()
    _anatomia("secundarias", 3, 0, "cub8")
    _anatomia("global", 5, 3, "todo")


# ---------------------------------------------------------------------------
# Los criterios, afirmados. Donde no se cumplen: xfail estricto con las cifras.
# ---------------------------------------------------------------------------

_CMD = (
    'cd .snapshots/v0.3.0 && PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest '
    '../../tests/fuera_de_plano -s -p no:cacheprovider --import-mode=importlib --noconftest'
)


def _casos_referencia():
    casos = []
    for look in LOOKS:
        for pal in M.PALETAS_A:
            marcas = ()
            if pal.nombre == "A5 muy variada":
                marcas = (pytest.mark.xfail(strict=True, reason=XFAIL_A5.get(look, "")),)
            casos.append(pytest.param(look, pal.nombre, marks=marcas, id=f"{look}-{pal.nombre}"))
    return casos


_CRITERIO_T1 = ("criterio del T1: ΔE2000 maximo < 3.0 en la zona cubierta (ΔE de colour-science). "
                "Medido 16-09-2026 contra .snapshots/v0.3.0 con: ")
XFAIL_A5 = {
    "global": (
        "A->A sobre MI escena A5 «muy variada» (28 objetos, tono 360 grados, cobertura del cubo "
        "0.9600%), look global: cub_max = 4.0009 > 3.0 (el repo dice lo mismo: "
        "de_max_cubierto = 4.00095), con medio 0.1486 y p95 0.4332. El T1 publicado (1.7409) no "
        "aguanta una escena mas rica ni siquiera en el caso facil. Cerrarlo = que el ajuste del "
        "LUT baje de 3.0 sobre su propio plano con esta escena. " + _CRITERIO_T1 + _CMD
    ),
    "secundarias": (
        "A->A sobre MI escena A5 «muy variada» (cobertura 0.9628%), look con secundarias: "
        "cub_max = 3.8541 > 3.0 (repo: de_max_cubierto = 3.85405), medio 0.1541, p95 0.4504. "
        "Cerrarlo = que el ajuste del LUT baje de 3.0 sobre su propio plano con esta escena. "
        + _CRITERIO_T1 + _CMD
    ),
}


@pytest.mark.parametrize(("look", "nombre_a"), _casos_referencia())
def test_t5_referencia_A_a_A_max_bajo_3_en_zona_cubierta(look, nombre_a):
    """El criterio del T1 (max < 3.0 en la zona cubierta), en MI montaje, A->A."""
    _, refs = barrido()
    (r,) = [x for x in refs if x["look"] == look and x["A"] == nombre_a]
    assert r["cub_max"] < UMBRAL_MAX, f"{look} {nombre_a}: cub_max={r['cub_max']:.4f}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "EL CASO DE USO NO SE CUMPLE. Grado extraido de A2 «interior calido» (cobertura del cubo "
        "0.4063% look global / 0.4118% secundarias, el orden del 0.46% del repo) y aplicado a "
        "las 6 escenas B: ΔE2000 maximo en B >= 3.0 en 12 de 12 casos. Global: 4.6466 (misma "
        "paleta, otra toma, solape 0.7040), 4.4425, 5.1275, 4.6784, 3.7498, 3.7446. Secundarias: "
        "5.4789, 3.5931, 5.9213, 5.2552, 4.9963, 5.9154. Sin pixeles de L*>100 no cambia ninguno "
        "de los 12 salvo B3 global (4.4999). Referencia A->A del mismo montaje: 1.6949 / 1.5687. "
        "Lo que SI aguanta: medio 0.3378-1.6852, p95 0.9116-4.0102, pixeles > 3.0 entre 0.016% y "
        "14.15%. Criterio: max < 3.0 en todo B, ΔE de colour-science. Medido 16-09-2026 contra "
        ".snapshots/v0.3.0 con: " + _CMD + ". Cerrarlo = max < 3.0 en las 12, o decidir que el "
        "criterio fuera de plano es otro y escribirlo."
    ),
)
def test_t5_A_a_B_max_bajo_3_con_la_cobertura_de_un_plano_normal():
    """El caso de uso: grado extraido de un plano normal (A2, ~0.4% del cubo),
    aplicado a las seis B, en los dos looks. Criterio: max < 3.0 en todo B."""
    filas, _ = barrido()
    sel = [f for f in filas if f["A"] == "A2 interior calido"]
    malos = {f"{f['look']}|{f['B']}": round(f["todo_max"], 4) for f in sel
             if not f["todo_max"] < UMBRAL_MAX}
    assert not malos, malos


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Ni en lo facil. Nivel N1 (solape de histogramas 3D >= 0.55; medido 0.5659-0.7040): 14 "
        "pares A->B, y solo 2 bajan de 3.0 de maximo (A1 monocroma, cobertura 0.1530-0.1586%: 2.6771 "
        "y 2.7891). Los otros 12: 3.5931, 3.8513, 4.3342, 4.4425, 4.6466, 5.4789 (A1/A2) y "
        "9.5815, 18.9404, 24.9391, 26.1984, 42.4492, 44.3838 (A6, cobertura 4.66-4.78%; sin "
        "pixeles de L*>100 quedan 2.4991, 5.4521, 2.4403, 5.0626, 6.1121, 2.8180). p95 de los 14 "
        "<= 1.6804. Criterio: max < 3.0 en todo B, ΔE de colour-science. Medido 16-09-2026 contra "
        ".snapshots/v0.3.0 con: " + _CMD + ". Cerrarlo = max < 3.0 en los 14."
    ),
)
def test_t5_A_a_B_max_bajo_3_en_toda_escena_casi_identica():
    """Ni siquiera lo facil: todas las B del nivel N1 (solape >= 0.55), max < 3.0."""
    filas, _ = barrido()
    sel = [f for f in filas if f["nivel"].startswith("N1")]
    assert sel
    malos = {f"{f['look']}|{f['A']}|{f['B']}": round(f["todo_max"], 4) for f in sel
             if not f["todo_max"] < UMBRAL_MAX}
    assert not malos, malos


def _escribir_csv(filas: list[dict], refs: list[dict]) -> None:
    claves = [k for k in filas[0] if k != "cdl_extraido"]
    with open(_AQUI / "resultados_t5.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=claves, extrasaction="ignore")
        w.writeheader()
        for f in refs + filas:
            w.writerow({k: f.get(k, "") for k in claves})


def _dibujar(filas: list[dict], refs: list[dict]) -> None:
    """PNG sin matplotlib (no esta instalado): cv2, que ya es dependencia."""
    import cv2

    W, H, ML, MB, MT, MR = 620, 460, 70, 60, 40, 20
    colores = [(200, 80, 40), (40, 160, 230), (60, 180, 60), (180, 60, 180), (30, 30, 200),
               (40, 40, 40)]
    ymin, ymax = np.log10(0.1), np.log10(100.0)

    def panel(var: str, xmax: float, titulo: str, etiqueta_x: str) -> np.ndarray:
        img = np.full((H, W, 3), 255, np.uint8)
        x0, x1, y0, y1 = ML, W - MR, H - MB, MT

        def px(x: float, y: float) -> tuple[int, int]:
            yy = np.log10(min(max(y, 0.1), 100.0))
            return (int(x0 + (x1 - x0) * x / xmax), int(y0 + (y1 - y0) * (yy - ymin) / (ymax - ymin)))

        cv2.rectangle(img, (x0, y1), (x1, y0), (0, 0, 0), 1)
        for yv in (0.1, 0.3, 1, 3, 10, 30, 100):
            p = px(0, yv)
            cv2.line(img, (x0, p[1]), (x1, p[1]), (225, 225, 225), 1)
            cv2.putText(img, f"{yv:g}", (8, p[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        p3 = px(0, UMBRAL_MAX)
        cv2.line(img, (x0, p3[1]), (x1, p3[1]), (0, 0, 220), 2)
        for k in range(6):
            xv = xmax * k / 5
            p = px(xv, 0.1)
            cv2.putText(img, f"{xv:.3g}", (p[0] - 12, y0 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 0, 0), 1)
        for f in filas:
            ia = [p.nombre for p in M.PALETAS_A].index(f["A"])
            c = px(f[var], f["todo_max"])
            if f["look"] == "global":
                cv2.circle(img, c, 5, colores[ia], 2)
            else:
                cv2.rectangle(img, (c[0] - 4, c[1] - 4), (c[0] + 4, c[1] + 4), colores[ia], 2)
        for r in refs:
            ia = [p.nombre for p in M.PALETAS_A].index(r["A"])
            c = px(r[var], r["todo_max"])
            cv2.drawMarker(img, c, colores[ia], cv2.MARKER_STAR, 12, 2)
        cv2.putText(img, titulo, (x0, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        cv2.putText(img, etiqueta_x, (x0 + 120, H - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 0, 0), 1)
        return img

    izq = panel("frac_px_cub", 1.0, "dE2000 MAX en B (log) vs fraccion de B en celdas cubiertas",
                "fraccion de pixeles de B en celda cubierta por A")
    der = panel("cob_A", max(0.02, 1.1 * max(f["cob_A"] for f in filas)), "dE2000 MAX en B (log) vs cobertura del cubo de A",
                "cobertura de A (fraccion de 35937 celdas)")
    dist = panel("frac_px_a_0.005", 1.0, "dE2000 MAX en B (log) vs B a < 0.005 de un pixel de A",
                 "fraccion de B a menos de 0.005 de un pixel de A")
    leyenda = np.full((70, 3 * W, 3), 255, np.uint8)
    x = 10
    for ia, p in enumerate(M.PALETAS_A):
        nombre = p.nombre.encode("ascii", "replace").decode()
        cv2.putText(leyenda, nombre, (x, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, colores[ia], 1)
        x += 300
    cv2.putText(leyenda, "circulo = look global   cuadrado = look secundarias   estrella = A->A"
                "   linea roja = 3.0", (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.imwrite(str(_AQUI / "curva_t5.png"), np.vstack([np.hstack([izq, der, dist]), leyenda]))
