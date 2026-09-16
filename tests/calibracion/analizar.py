"""Confianza declarada contra error real: correlaciones, tramos, umbrales e intervalos.

Uso (desde la raíz del repo, después de `medir`):

    .venv/bin/python -m tests.calibracion.analizar            # todo
    .venv/bin/python -m tests.calibracion.analizar | grep "CAL spearman"

Lee `tests/calibracion/datos/*_320_*.csv` (la medida principal) y, si están,
`*_640_sel.csv` (la comprobación de resolución). Escribe `score_vs_error.png`.
Cada bloque de la salida lleva una etiqueta `[CAL …]` para poder sacarlo con `grep`.

CRITERIOS
---------
* `reverse`: cumple = ΔE2000 **máximo** < `LIMITE_T1_DELTA_E_MAXIMO` (3.0), sobre todos los
  píxeles del plano. La pregunta que importa es **fuera de plano** (`fuera_de_plano = 1`).
* `matching`: cumple = ΔE2000 **medio** del clip < `LIMITE_T3_DELTA_E_PEOR_PAR` (2.0), que es
  la cifra con la que T3 juzga cada par. Se da también el máximo < 3.0.

INTERVALOS
----------
Bootstrap **por escena** (`semilla_escena`), no por fila: en `reverse` las cinco filas fuera
de plano de una extracción comparten score, y las cuatro condiciones de compresión y recorte
comparten escena y grado. Remuestrear filas sueltas fingiría más independencia de la que hay.
1.000 remuestreos, semilla fija, percentiles 2.5 y 97.5.
"""

from __future__ import annotations

import contextlib
import csv
import glob
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from core.umbrales import (
    CONFIDENCE_ALTA,
    CONFIDENCE_MEDIA,
    LIMITE_T1_DELTA_E_MAXIMO,
    LIMITE_T3_DELTA_E_PEOR_PAR,
)
from tests.calibracion.medir import huella_core

warnings.filterwarnings("ignore")

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "datos"
B_BOOT = 1000
SEMILLA_BOOT = 20260916
TRAMOS = (0.0, 0.2, CONFIDENCE_MEDIA, CONFIDENCE_ALTA, 0.9, 0.99, 1.0000001)


def cargar(patron: str) -> list[dict]:
    filas: list[dict] = []
    for f in sorted(glob.glob(str(DATOS / patron))):
        with open(f, newline="") as fh:
            filas.extend(csv.DictReader(fh))
    for r in filas:
        for k, v in list(r.items()):
            if k in ("motor", "level", "reasons", "riqueza", "plano", "fuerza",
                     "disparidad_tipo", "huella_core"):
                continue
            with contextlib.suppress(TypeError, ValueError):
                r[k] = float(v)
    return filas


def col(filas: list[dict], k: str) -> np.ndarray:
    return np.array([float(r[k]) for r in filas], dtype=np.float64)


def rho(filas: list[dict], k: str) -> float:
    s = col(filas, "score")
    if len(filas) < 5 or np.ptp(s) == 0:
        return float("nan")
    return float(spearmanr(s, col(filas, k))[0])


def auc(score: np.ndarray, cumple: np.ndarray) -> float:
    """P(score de un caso que cumple > score de uno que no), empates a medias."""
    pos, neg = score[cumple], score[~cumple]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    orden = np.concatenate([pos, neg])
    rangos = _rangos(orden)
    return float((rangos[: pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def _rangos(x: np.ndarray) -> np.ndarray:
    idx = np.argsort(x, kind="mergesort")
    r = np.empty_like(x, dtype=np.float64)
    xs = x[idx]
    i = 0
    while i < xs.size:
        j = i
        while j + 1 < xs.size and xs[j + 1] == xs[i]:
            j += 1
        r[idx[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def bootstrap(filas: list[dict], estadistico, clave: str = "semilla_escena") -> tuple[float, float]:
    """IC95 remuestreando ESCENAS enteras. `estadistico(idx)` recibe índices de fila."""
    llaves = np.array([r[clave] for r in filas])
    grupos = [np.flatnonzero(llaves == k) for k in np.unique(llaves)]
    rng = np.random.default_rng(SEMILLA_BOOT)
    vals = []
    for _ in range(B_BOOT):
        elegidas = rng.integers(0, len(grupos), size=len(grupos))
        v = estadistico(np.concatenate([grupos[i] for i in elegidas]))
        if np.isfinite(v):
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def _rho_arr(s: np.ndarray, e: np.ndarray) -> float:
    if s.size < 5 or np.ptp(s) == 0:
        return float("nan")
    return float(spearmanr(s, e)[0])


def f3(x: float) -> str:
    return "  nan" if not np.isfinite(x) else f"{x:+.3f}"


# ---------------------------------------------------------------------------
# Bloques
# ---------------------------------------------------------------------------


def bloque_distribucion(nombre: str, filas: list[dict], unidad: str) -> None:
    s = col(filas, "score")
    pct = np.percentile(s, [0, 5, 10, 25, 50, 75, 90, 95, 100])
    niveles = {lv: sum(r["level"] == lv for r in filas) for lv in ("alta", "media", "baja")}
    print(f"[CAL distribucion {nombre}] n={len(filas)} {unidad} | percentiles 0/5/10/25/50/75/90/95/100 = "
          + " ".join(f"{p:.3f}" for p in pct))
    print(f"[CAL distribucion {nombre}] score==1.0: {np.mean(s == 1.0):.3f} | >=0.99: "
          f"{np.mean(s >= 0.99):.3f} | en (0.45, 0.75): {np.mean((s > 0.45) & (s < 0.75)):.3f} | "
          f"niveles alta/media/baja = {niveles['alta']}/{niveles['media']}/{niveles['baja']}")
    hist, bordes = np.histogram(s, bins=20, range=(0, 1))
    print(f"[CAL distribucion {nombre}] histograma 20 bins 0..1: " + " ".join(str(h) for h in hist))


def bloque_spearman(etiqueta: str, filas: list[dict], sufijo: str = "") -> None:
    rmax, rp95, rmed = (rho(filas, f"de_{k}{sufijo}") for k in ("max", "p95", "medio"))
    s = col(filas, "score")
    print(f"[CAL spearman{sufijo} {etiqueta}] n={len(filas):4d} score_distintos={len(np.unique(s)):4d} "
          f"| rho max {f3(rmax)} | p95 {f3(rp95)} | medio {f3(rmed)}")


def bloque_tramos(etiqueta: str, filas: list[dict], k_criterio: str, limite: float) -> None:
    s = col(filas, "score")
    print(f"[CAL tramos {etiqueta}] criterio: de_{k_criterio} < {limite}")
    for lo, hi in zip(TRAMOS[:-1], TRAMOS[1:], strict=True):
        sel = [r for r, v in zip(filas, s, strict=True) if lo <= v < hi]
        if not sel:
            print(f"[CAL tramos {etiqueta}] [{lo:.2f}, {min(hi, 1.0):.2f}{']' if hi > 1 else ')'} n=   0")
            continue
        mx, p95, med = col(sel, "de_max"), col(sel, "de_p95"), col(sel, "de_medio")
        crit = col(sel, f"de_{k_criterio}")
        escenas = len({r["semilla_escena"] for r in sel})
        print(f"[CAL tramos {etiqueta}] [{lo:.2f}, {min(hi, 1.0):.2f}{']' if hi > 1 else ')'} "
              f"n={len(sel):4d} escenas={escenas:3d} | máx mediana {np.median(mx):6.2f} "
              f"| p95 mediana {np.median(p95):5.2f} | medio mediana {np.median(med):5.2f} "
              f"| cumple {np.mean(crit < limite):.3f} ({int(np.sum(crit < limite))}) "
              f"| máx<3 {np.mean(mx < LIMITE_T1_DELTA_E_MAXIMO):.3f}")


def bloque_umbral(etiqueta: str, filas: list[dict], k_criterio: str, limite: float) -> None:
    """ALTA = menor score t tal que, entre los casos con score >= t, cumple >= 95%.

    Se exige al **extremo inferior** del intervalo bootstrap, no a la estimación puntual:
    con pocos casos por encima de t, un 95% puntual puede ser ruido.
    """
    s = col(filas, "score")
    cumple = col(filas, f"de_{k_criterio}") < limite
    print(f"[CAL umbral {etiqueta}] criterio ALTA: fracción que cumple (de_{k_criterio} < {limite}) "
          f"entre los casos con score >= t, con IC95 bootstrap por escena; se pide IC inferior >= 0.95")
    mejor = None
    for t in [0.0, 0.2, CONFIDENCE_MEDIA, 0.6, CONFIDENCE_ALTA, 0.8, 0.9, 0.95, 0.99, 1.0]:
        sel = [r for r, v in zip(filas, s, strict=True) if v >= t - 1e-12]
        if not sel:
            continue

        c_sel = col(sel, f"de_{k_criterio}") < limite
        lo, hi = bootstrap(sel, lambda idx, c=c_sel: float(np.mean(c[idx])))
        print(f"[CAL umbral {etiqueta}] t={t:.2f} n={len(sel):4d} cumple={c_sel.mean():.3f} "
              f"IC95=[{lo:.3f}, {hi:.3f}]")
        if mejor is None and np.isfinite(lo) and lo >= 0.95:
            mejor = t
    # búsqueda fina por si hubiera un t que no esté en la lista
    fino = None
    mejor_frac, mejor_t, mejor_n = -1.0, float("nan"), 0
    for t in np.unique(s):
        sel_c = cumple[s >= t]
        if sel_c.size < 20:
            continue
        if sel_c.mean() > mejor_frac:
            mejor_frac, mejor_t, mejor_n = float(sel_c.mean()), float(t), int(sel_c.size)
        if fino is None and sel_c.mean() >= 0.95:
            fino = float(t)
    print(f"[CAL umbral {etiqueta}] RESULTADO: t con IC inferior >= 0.95 en la rejilla: "
          f"{'ninguno' if mejor is None else f'{mejor:.2f}'} | t con estimación puntual >= 0.95 "
          f"y n >= 20 en todos los scores distintos: {'ninguno' if fino is None else f'{fino:.3f}'} "
          f"| lo mejor con n >= 20: {mejor_frac:.3f} (score >= {mejor_t:.4f}, n={mejor_n})")


def bloque_auc(etiqueta: str, filas: list[dict], k_criterio: str, limite: float) -> None:
    s = col(filas, "score")
    c = col(filas, f"de_{k_criterio}") < limite
    lo, hi = bootstrap(filas, lambda idx: auc(s[idx], c[idx]))
    print(f"[CAL auc {etiqueta}] criterio de_{k_criterio} < {limite}: cumplen {int(c.sum())} de "
          f"{len(filas)} | AUC del score = {auc(s, c):.3f} IC95=[{lo:.3f}, {hi:.3f}] (0.5 = no predice)")


def bloque_rho_ic(etiqueta: str, filas: list[dict], k: str) -> None:
    s, e = col(filas, "score"), col(filas, k)
    lo, hi = bootstrap(filas, lambda idx: _rho_arr(s[idx], e[idx]))
    print(f"[CAL rho_ic {etiqueta}] rho(score, {k}) = {f3(rho(filas, k))} IC95=[{f3(lo)}, {f3(hi)}]")


def bloque_constante(etiqueta: str, filas: list[dict]) -> None:
    """Qué error hay debajo de un score idéntico: si el score no se mueve, no puede predecir."""
    s = col(filas, "score")
    if not filas:
        return
    uno = [r for r in filas if r["score"] == 1.0]
    mx = col(uno, "de_max") if uno else np.array([np.nan])
    print(f"[CAL constante {etiqueta}] score==1.0 en {len(uno)} de {len(filas)} "
          f"(score min {s.min():.3f}) | con score 1.0, máx: min {np.nanmin(mx):.2f} mediana "
          f"{np.nanmedian(mx):.2f} máx {np.nanmax(mx):.2f} | cumple máx<3: "
          f"{np.nanmean(mx < LIMITE_T1_DELTA_E_MAXIMO) if uno else float('nan'):.3f}")


def bloque_material(rev: list[dict], mat: list[dict]) -> None:
    """Cómo es el material: fuerza del grado, disparidad, brillos y qué hace el igualado."""
    propio = [r for r in rev if r["plano"] == "propio" and r["tam_lut"] == 33.0]
    for fuerza in ("suave", "fuerte"):
        v = col([r for r in propio if r["fuerza"] == fuerza], "fuerza_grado_medio")
        print(f"[CAL material reverse] grado {fuerza}: ΔE2000 medio entre original y coloreado "
              f"min {v.min():.2f} mediana {np.median(v):.2f} máx {v.max():.2f}")
    for plano in ("otra_toma", "tono_15", "tono_60_exp", "tono_150_sat", "otra_paleta"):
        sel = [r for r in rev if r["plano"] == plano and r["tam_lut"] == 33.0]
        d = col(sel, "disparidad")
        cub = col(sel, "frac_px_en_celda_cubierta")
        print(f"[CAL material reverse] plano {plano}: disparidad (intersección de histogramas 17³) "
              f"min {d.min():.3f} mediana {np.median(d):.3f} máx {d.max():.3f} | píxeles en celda "
              f"cubierta (33³) mediana {np.median(cub):.3f}")
    cob = col(propio, "cobertura_cubo")
    print(f"[CAL material reverse] cobertura del cubo 33³ por extracción: min {cob.min():.4f} "
          f"mediana {np.median(cob):.4f} máx {cob.max():.4f} | píxeles con L*>100 en la verdad: "
          f"mediana {np.median(col(rev, 'frac_px_l_mayor_100')):.4f} máx {col(rev, 'frac_px_l_mayor_100').max():.4f}")
    for disp in ("identica", "otra_toma", "tono_15", "tono_60_exp", "tono_150_sat", "otra_paleta"):
        sel = [r for r in mat if r["disparidad_tipo"] == disp]
        alta = [r for r in sel if r["level"] == "alta"]
        print(f"[CAL material matching] {disp}: disparidad mediana {np.median(col(sel, 'disparidad')):.3f} "
              f"| ΔE medio sin tocar mediana {np.median(col(sel, 'sin_tocar_de_medio')):.2f} -> igualado "
              f"{np.median(col(sel, 'de_medio')):.2f} | «alta» {len(alta)} de {len(sel)}, de esas cumplen "
              f"medio<2: {sum(r['de_medio'] < LIMITE_T3_DELTA_E_PEOR_PAR for r in alta)}")


def bloque_captura(filas_rev: list[dict]) -> None:
    """¿«ALTA» con el máximo por encima de 3.0 es raro o lo normal?"""
    for tam in (17.0, 33.0):
        for fuera, nombre in ((0.0, "en su plano"), (1.0, "fuera de plano")):
            sel = [r for r in filas_rev if r["tam_lut"] == tam and r["fuera_de_plano"] == fuera]
            alta = [r for r in sel if r["level"] == "alta"]
            alta100 = [r for r in sel if r["score"] >= 0.995]
            n_nc = sum(r["de_max"] >= LIMITE_T1_DELTA_E_MAXIMO for r in alta)
            n_nc100 = sum(r["de_max"] >= LIMITE_T1_DELTA_E_MAXIMO for r in alta100)
            print(f"[CAL captura {int(tam)}^3 {nombre}] ALTA: {len(alta)} de {len(sel)}; de esas, máx >= 3.0: "
                  f"{n_nc} ({n_nc / max(len(alta), 1):.3f}) | «100%» (score >= 0.995): {len(alta100)}; "
                  f"máx >= 3.0: {n_nc100} ({n_nc100 / max(len(alta100), 1):.3f})")
            # y lo que ve la GUI en su plano: el máximo del repo contra el coloreado
            if fuera == 0.0:
                n_repo = sum(r["repo_de_max_propio"] >= LIMITE_T1_DELTA_E_MAXIMO for r in alta100)
                print(f"[CAL captura {int(tam)}^3 {nombre}] mismo recuento con el máximo que "
                      f"enseña la pantalla (repo, contra el coloreado): {n_repo} de {len(alta100)}")


def bloque_componentes(nombre: str, filas: list[dict]) -> None:
    """Qué subnota mueve el score: fracción de casos donde cada una baja de 1."""
    partes = []
    for k in ("n_muestras", "solape", "condicion", "residuo_de", "extrapolacion", "ganancia",
              "fraccion_no_finita"):
        v = col(filas, f"sub_{k}")
        if np.all(np.isnan(v)):
            continue
        partes.append(f"{k} <1: {np.nanmean(v < 0.999):.3f}")
    partes.append(f"desajuste: {np.mean(col(filas, 'desajuste') == 1.0):.3f}")
    print(f"[CAL componentes {nombre}] " + " | ".join(partes))


def bloque_desajuste(nombre: str, filas: list[dict], clave_cond: str) -> None:
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for r in filas:
        grupos[(int(r["compresion"]), int(r["recorte"]))].append(r)
    for (c, rc), sel in sorted(grupos.items()):
        print(f"[CAL desajuste {nombre}] compresion={c} recorte={rc}: desajuste en "
              f"{np.mean(col(sel, 'desajuste') == 1.0):.3f} de {len(sel)} {clave_cond}")


def bloque_resolucion(motor: str, criterio: str, limite: float) -> None:
    alta_res = cargar(f"{motor}_640_sel.csv")
    if not alta_res:
        print(f"[CAL resolucion {motor}] no hay {motor}_640_sel.csv: no comprobado")
        return
    baja_res = {(r["caso"], r.get("tam_lut", 0.0), r.get("plano", "")): r
                for r in cargar(f"{motor}_320_[0-9]*.csv")}
    pares = [(baja_res[(r["caso"], r.get("tam_lut", 0.0), r.get("plano", ""))], r) for r in alta_res]
    s1 = np.array([a["score"] for a, _ in pares])
    s2 = np.array([b["score"] for _, b in pares])
    mismo_nivel = np.mean([a["level"] == b["level"] for a, b in pares])
    c1 = np.array([a[f"de_{criterio}"] < limite for a, _ in pares])
    c2 = np.array([b[f"de_{criterio}"] < limite for _, b in pares])
    r_err = spearmanr([a[f"de_{criterio}"] for a, _ in pares], [b[f"de_{criterio}"] for _, b in pares])[0]
    print(f"[CAL resolucion {motor}] {len(pares)} filas 320×180 contra 640×360 | |Δscore| mediana "
          f"{np.median(np.abs(s1 - s2)):.3f} máx {np.max(np.abs(s1 - s2)):.3f} | mismo nivel "
          f"{mismo_nivel:.3f} | rho de_{criterio} 320 vs 640 {r_err:+.3f} | cumple 320: {c1.mean():.3f} "
          f"640: {c2.mean():.3f}")
    if motor == "reverse":
        for tam in (17.0, 33.0):
            for c in (0.0, 1.0):
                sa = np.array([b["score"] for a, b in pares if b["tam_lut"] == tam and b["compresion"] == c])
                sb = np.array([a["score"] for a, b in pares if a["tam_lut"] == tam and a["compresion"] == c])
                print(f"[CAL resolucion reverse] {int(tam)}^3 compresion={int(c)}: score==1.0 en "
                      f"640: {np.mean(sa == 1.0):.3f} (min {sa.min():.3f}) | 320: "
                      f"{np.mean(sb == 1.0):.3f} (min {sb.min():.3f})")
    print(f"[CAL resolucion {motor}] rho(score, de_{criterio}) 320: "
          f"{f3(float(spearmanr(s1, [a[f'de_{criterio}'] for a, _ in pares])[0]))} | 640: "
          f"{f3(float(spearmanr(s2, [b[f'de_{criterio}'] for _, b in pares])[0]))} | AUC 320: "
          f"{auc(s1, c1):.3f} 640: {auc(s2, c2):.3f}")


# ---------------------------------------------------------------------------
# PNG sin instalar nada: OpenCV, que ya es dependencia del proyecto
# ---------------------------------------------------------------------------


def dibujar(rev: list[dict], mat: list[dict], destino: Path) -> None:
    import cv2

    paneles = [
        ("reverse 17^3 fuera de plano: max", [r for r in rev if r["tam_lut"] == 17 and r["fuera_de_plano"] == 1], "de_max", LIMITE_T1_DELTA_E_MAXIMO),
        ("reverse 33^3 fuera de plano: max", [r for r in rev if r["tam_lut"] == 33 and r["fuera_de_plano"] == 1], "de_max", LIMITE_T1_DELTA_E_MAXIMO),
        ("reverse 33^3 en su plano: max", [r for r in rev if r["tam_lut"] == 33 and r["fuera_de_plano"] == 0], "de_max", LIMITE_T1_DELTA_E_MAXIMO),
        ("matching: medio", mat, "de_medio", LIMITE_T3_DELTA_E_PEOR_PAR),
    ]
    w, h, m = 520, 420, 60
    lienzo = np.full((h * 2, w * 2, 3), 255, np.uint8)
    rng = np.random.default_rng(1)
    for i, (titulo, filas, k, limite) in enumerate(paneles):
        ox, oy = (i % 2) * w, (i // 2) * h
        x0, y0, x1, y1 = ox + m, oy + 30, ox + w - 20, oy + h - m
        cv2.rectangle(lienzo, (x0, y0), (x1, y1), (0, 0, 0), 1)
        ymin, ymax = np.log10(0.1), np.log10(100.0)

        def py(v: float, y0=y0, y1=y1, ymin=ymin, ymax=ymax) -> int:
            t = (np.log10(np.clip(v, 0.1, 100.0)) - ymin) / (ymax - ymin)
            return int(y1 - t * (y1 - y0))

        def px(s: float, x0=x0, x1=x1) -> int:
            return int(x0 + s * (x1 - x0))

        for d in (0.1, 1, 10, 100):
            cv2.line(lienzo, (x0 - 4, py(d)), (x0, py(d)), (0, 0, 0), 1)
            cv2.putText(lienzo, f"{d:g}", (ox + 8, py(d) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        for sx in (0.0, 0.25, 0.5, 0.75, 1.0):
            cv2.putText(lienzo, f"{sx:.2f}", (px(sx) - 14, y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        for tx, color in ((CONFIDENCE_MEDIA, (160, 160, 160)), (CONFIDENCE_ALTA, (160, 160, 160))):
            cv2.line(lienzo, (px(tx), y0), (px(tx), y1), color, 1)
        cv2.line(lienzo, (x0, py(limite)), (x1, py(limite)), (0, 0, 220), 1)
        for r in filas:
            jit = rng.uniform(-0.006, 0.006)
            color = (200, 90, 20) if r[k] < limite else (40, 40, 40)
            cv2.circle(lienzo, (px(min(max(r["score"] + jit, 0), 1)), py(r[k])), 2, color, -1)
        cv2.putText(lienzo, titulo, (x0, oy + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        cv2.putText(lienzo, "score", (x1 - 40, y1 + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.imwrite(str(destino), lienzo)


def main() -> None:
    rev = cargar("reverse_320_[0-9]*.csv")
    mat = cargar("matching_320_[0-9]*.csv")
    huellas = {r["huella_core"] for r in rev + mat}
    print(f"[CAL guardia] filas reverse={len(rev)} matching={len(mat)} | huellas en los CSV={sorted(huellas)} "
          f"| huella actual={huella_core()} | umbrales vigentes ALTA={CONFIDENCE_ALTA} MEDIA={CONFIDENCE_MEDIA}")

    # Comprobación cruzada de la métrica: sin compresión, la verdad en su plano ES el
    # coloreado que recibe el motor, así que mi máximo (colour) y el del repo (core.color)
    # tienen que coincidir.
    limpias = [r for r in rev if r["plano"] == "propio" and r["compresion"] == 0.0]
    dif = np.abs(col(limpias, "de_max") - col(limpias, "repo_de_max_propio"))
    dif_m = np.abs(col(limpias, "de_medio") - col(limpias, "repo_de_medio_propio"))
    print(f"[CAL guardia] máximo en su plano sin compresión, colour frente a core.color: "
          f"{len(limpias)} filas, diferencia máx {dif.max():.2e} (medio: {dif_m.max():.2e})")

    lim1, lim3 = LIMITE_T1_DELTA_E_MAXIMO, LIMITE_T3_DELTA_E_PEOR_PAR
    bloque_material(rev, mat)
    extr = {t: [r for r in rev if r["tam_lut"] == t and r["plano"] == "propio"] for t in (17.0, 33.0)}

    # 1. distribuciones
    for t in (17.0, 33.0):
        bloque_distribucion(f"reverse {int(t)}^3", extr[t], "extracciones")
        bloque_componentes(f"reverse {int(t)}^3", extr[t])
    bloque_distribucion("matching", mat, "pares")
    bloque_componentes("matching", mat)
    for t in (17.0, 33.0):
        bloque_desajuste(f"reverse {int(t)}^3", extr[t], "extracciones")
    bloque_desajuste("matching", mat, "pares")

    # 2. correlaciones
    for sufijo in ("", "_sdr"):
        for t in (17.0, 33.0):
            base = [r for r in rev if r["tam_lut"] == t]
            for fuera, nombre in ((1.0, "fuera"), (0.0, "propio")):
                sel = [r for r in base if r["fuera_de_plano"] == fuera]
                bloque_spearman(f"reverse {int(t)}^3 {nombre} | todo", sel, sufijo)
                for cond in ("riqueza", "compresion", "recorte", "fuerza"):
                    for valor in sorted({r[cond] for r in sel}, key=str):
                        bloque_spearman(f"reverse {int(t)}^3 {nombre} | {cond}={valor}",
                                        [r for r in sel if r[cond] == valor], sufijo)
                if fuera == 1.0:
                    for plano in ("otra_toma", "tono_15", "tono_60_exp", "tono_150_sat", "otra_paleta"):
                        bloque_spearman(f"reverse {int(t)}^3 {nombre} | plano={plano}",
                                        [r for r in sel if r["plano"] == plano], sufijo)
                bloque_spearman(f"reverse {int(t)}^3 {nombre} | sin desajuste",
                                [r for r in sel if r["desajuste"] == 0.0], sufijo)
                bloque_spearman(f"reverse {int(t)}^3 {nombre} | score >= ALTA",
                                [r for r in sel if r["score"] >= CONFIDENCE_ALTA], sufijo)
        bloque_spearman("matching | todo", mat, sufijo)
        for cond in ("riqueza", "compresion", "recorte", "fuerza", "disparidad_tipo"):
            for valor in sorted({r[cond] for r in mat}, key=str):
                bloque_spearman(f"matching | {cond}={valor}", [r for r in mat if r[cond] == valor], sufijo)
        bloque_spearman("matching | sin desajuste", [r for r in mat if r["desajuste"] == 0.0], sufijo)
        bloque_spearman("matching | score >= ALTA", [r for r in mat if r["score"] >= CONFIDENCE_ALTA], sufijo)

    # 2a. el cruce que importa: dentro de UNA clase de material (compresión × recorte)
    for t in (17.0, 33.0):
        for fuera, nombre in ((1.0, "fuera"), (0.0, "propio")):
            for c in (0.0, 1.0):
                for rc in (0.0, 1.0):
                    sel = [r for r in rev if r["tam_lut"] == t and r["fuera_de_plano"] == fuera
                           and r["compresion"] == c and r["recorte"] == rc]
                    et = f"reverse {int(t)}^3 {nombre} | compresion={int(c)} recorte={int(rc)}"
                    bloque_spearman(et, sel)
                    bloque_auc(et, sel, "max", lim1)
                    bloque_constante(et, sel)
    for c in (0.0, 1.0):
        for rc in (0.0, 1.0):
            sel = [r for r in mat if r["compresion"] == c and r["recorte"] == rc]
            et = f"matching | compresion={int(c)} recorte={int(rc)}"
            bloque_spearman(et, sel)
            bloque_auc(et, sel, "medio", lim3)
    for disp in ("identica", "otra_toma", "tono_15", "tono_60_exp", "tono_150_sat", "otra_paleta"):
        sel = [r for r in mat if r["disparidad_tipo"] == disp]
        print(f"[CAL desajuste matching] disparidad={disp}: desajuste en "
              f"{np.mean(col(sel, 'desajuste') == 1.0):.3f} de {len(sel)} | cumple medio<2 "
              f"{np.mean(col(sel, 'de_medio') < lim3):.3f} | score mediana {np.median(col(sel, 'score')):.3f}")

    # 2b. por extracción: el score es uno por extracción; el error fuera de plano, la mediana
    for t in (17.0, 33.0):
        por_caso: dict[float, list[dict]] = defaultdict(list)
        for r in rev:
            if r["tam_lut"] == t and r["fuera_de_plano"] == 1.0:
                por_caso[r["caso"]].append(r)
        agregadas = []
        for caso, sel in por_caso.items():
            agregadas.append({"score": sel[0]["score"], "semilla_escena": sel[0]["semilla_escena"],
                              "de_max": float(np.median(col(sel, "de_max"))),
                              "de_p95": float(np.median(col(sel, "de_p95"))),
                              "de_medio": float(np.median(col(sel, "de_medio"))), "caso": caso})
        bloque_spearman(f"reverse {int(t)}^3 por extracción (mediana de los 5 planos)", agregadas)
        bloque_rho_ic(f"reverse {int(t)}^3 por extracción", agregadas, "de_max")
        bloque_rho_ic(f"reverse {int(t)}^3 fuera", [r for r in rev if r["tam_lut"] == t and r["fuera_de_plano"] == 1.0], "de_max")
        bloque_rho_ic(f"reverse {int(t)}^3 fuera sin desajuste",
                      [r for r in rev if r["tam_lut"] == t and r["fuera_de_plano"] == 1.0 and r["desajuste"] == 0.0], "de_max")
    bloque_rho_ic("matching", mat, "de_medio")
    bloque_rho_ic("matching sin desajuste", [r for r in mat if r["desajuste"] == 0.0], "de_medio")

    # 3. tramos, AUC y umbrales
    for t in (17.0, 33.0):
        for fuera, nombre in ((1.0, "fuera"), (0.0, "propio")):
            sel = [r for r in rev if r["tam_lut"] == t and r["fuera_de_plano"] == fuera]
            et = f"reverse {int(t)}^3 {nombre}"
            bloque_tramos(et, sel, "max", lim1)
            bloque_auc(et, sel, "max", lim1)
            bloque_auc(et + " (p95)", sel, "p95", lim1)
            bloque_auc(et + " (sdr)", sel, "max_sdr", lim1)
            bloque_umbral(et, sel, "max", lim1)
    bloque_tramos("matching", mat, "medio", lim3)
    bloque_auc("matching", mat, "medio", lim3)
    bloque_auc("matching (máx)", mat, "max", lim1)
    bloque_auc("matching sin desajuste", [r for r in mat if r["desajuste"] == 0.0], "medio", lim3)
    bloque_auc("matching identica", [r for r in mat if r["disparidad_tipo"] == "identica"], "medio", lim3)
    bloque_umbral("matching", mat, "medio", lim3)
    bloque_umbral("matching (máx)", mat, "max", lim1)

    # 4. la captura
    bloque_captura(rev)

    # 5. resolución
    bloque_resolucion("reverse", "max", lim1)
    bloque_resolucion("matching", "medio", lim3)

    destino = AQUI / "score_vs_error.png"
    dibujar(rev, mat, destino)
    print(f"[CAL png] {destino.relative_to(AQUI.parents[1])}")


if __name__ == "__main__":
    main()
