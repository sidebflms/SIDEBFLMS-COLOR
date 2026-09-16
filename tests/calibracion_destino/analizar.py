"""Señales de `FeaturesDestino` contra el ΔE2000 real: ¿predicen, y con qué corte?

Uso (desde la raíz del repo, después de `medir`):

    .venv/bin/python -m tests.calibracion_destino.analizar
    .venv/bin/python -m tests.calibracion_destino.analizar | grep "CALD spearman"

Lee `tests/calibracion_destino/datos/simple_*.csv` y `lote_*.csv`. Cada bloque
de la salida lleva una etiqueta `[CALD …]` para poder sacarlo con `grep`, igual
que `tests/calibracion/analizar.py` del día 4 (etiqueta `[CAL …]`, sin la D).

CRITERIO
--------
Igual que el día 4: cumple = ΔE2000 **máximo** < `LIMITE_T1_DELTA_E_MAXIMO`
(3.0) del plano de destino, sobre todos los píxeles. La pregunta que importa
es la fuera de plano (`fuera_de_plano = 1`): ¿me llevo este LUT a otro plano?

INTERVALOS
----------
Bootstrap por escena (`semilla_escena`), 1.000 remuestreos, semilla fija,
percentiles 2.5 y 97.5. Una escena agrupa las filas de una misma extracción
(los 6 planos de destino comparten `cobertura_cubo`, `planos_acumulados`, etc:
remuestrear filas sueltas fingiría más independencia de la que hay).

QUÉ MIDE DE MÁS RESPECTO AL DÍA 4
-----------------------------------
* Las 4 señales nuevas, cada una sola: Spearman global y DENTRO de cada clase
  de material (compresión × recorte × rejilla), porque el día 4 encontró una
  paradoja de Simpson exactamente ahí.
* `planos_acumulados`, que sólo varía en el bloque `lote`.
* Monotonía de `muestras_p10_zona` / `muestras_mediana_zona`: el día 4 avisó
  de que los peores errores fuera de plano no salían de celdas vacías sino de
  celdas con 7-14 muestras, así que aquí se comprueba por tramos, no se asume.
* Una nota combinada candidata (geométrica de rampas sobre las 4 señales,
  igual de forma que `core.matching.confianza.puntuar_confianza`) y el mismo
  criterio de umbral del día 4: el menor corte t tal que el extremo inferior
  del IC95 del % que cumple sea >= 95%.
"""

from __future__ import annotations

import contextlib
import csv
import glob
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from core.umbrales import LIMITE_T1_DELTA_E_MAXIMO

warnings.filterwarnings("ignore")

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "datos"
B_BOOT = 1000
SEMILLA_BOOT = 20260916
LIM = LIMITE_T1_DELTA_E_MAXIMO

SENALES = ("cobertura_destino", "muestras_p10_zona", "muestras_mediana_zona",
           "variance_zona", "planos_acumulados")


def cargar(patron: str) -> list[dict]:
    filas: list[dict] = []
    for f in sorted(glob.glob(str(DATOS / patron))):
        with open(f, newline="") as fh:
            filas.extend(csv.DictReader(fh))
    for r in filas:
        for k, v in list(r.items()):
            if k in ("bloque", "riqueza", "plano", "fuerza", "huella_core"):
                continue
            with contextlib.suppress(TypeError, ValueError):
                r[k] = float(v)
    return filas


def col(filas: list[dict], k: str) -> np.ndarray:
    return np.array([float(r[k]) for r in filas], dtype=np.float64)


def f3(x: float) -> str:
    return "  nan" if not np.isfinite(x) else f"{x:+.3f}"


def _rho(s: np.ndarray, e: np.ndarray) -> float:
    if s.size < 5 or np.ptp(s) == 0 or np.ptp(e) == 0:
        return float("nan")
    return float(spearmanr(s, e)[0])


def bootstrap(filas: list[dict], estadistico, clave: str = "semilla_escena") -> tuple[float, float]:
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


def auc(score: np.ndarray, cumple: np.ndarray) -> float:
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


# ---------------------------------------------------------------------------
# Bloques
# ---------------------------------------------------------------------------


def bloque_spearman_senal(etiqueta: str, filas: list[dict], senal: str) -> None:
    if not filas or np.ptp(col(filas, senal)) == 0:
        print(f"[CALD spearman {senal}] {etiqueta}: n={len(filas)} — señal constante, rho no definido")
        return
    s = col(filas, senal)
    rmax, rp95, rmed = (_rho(s, col(filas, f"de_{k}")) for k in ("max", "p95", "medio"))
    print(f"[CALD spearman {senal}] {etiqueta}: n={len(filas):4d} valores_distintos={len(np.unique(s)):4d} "
          f"| rho max {f3(rmax)} | p95 {f3(rp95)} | medio {f3(rmed)}")


def bloque_rho_ic_senal(etiqueta: str, filas: list[dict], senal: str) -> None:
    if not filas or np.ptp(col(filas, senal)) == 0:
        return
    s, e = col(filas, senal), col(filas, "de_max")
    lo, hi = bootstrap(filas, lambda idx: _rho(s[idx], e[idx]))
    print(f"[CALD rho_ic {senal}] {etiqueta}: rho(señal, de_max) = "
          f"{f3(_rho(s, e))} IC95=[{f3(lo)}, {f3(hi)}]")


def bloque_tramos_senal(etiqueta: str, filas: list[dict], senal: str, n_tramos: int = 6) -> None:
    """Reparte en `n_tramos` por CUANTILES de la señal (no por valor fijo: las
    señales no tienen la misma escala que un score 0..1) y enseña la mediana
    del error en cada uno. Es la comprobación de monotonía que pide el
    encargo: "no asumas, mídelo"."""
    s = col(filas, senal)
    if not filas or np.ptp(s) == 0:
        return
    cortes = np.unique(np.percentile(s, np.linspace(0, 100, n_tramos + 1)))
    if cortes.size < 3:
        print(f"[CALD tramos {senal}] {etiqueta}: muy pocos valores distintos para tramos")
        return
    print(f"[CALD tramos {senal}] {etiqueta}: por cuantiles de {senal}")
    for lo, hi in zip(cortes[:-1], cortes[1:], strict=True):
        ultimo = hi == cortes[-1]
        sel_mask = (s >= lo) & ((s <= hi) if ultimo else (s < hi))
        sel = [r for r, m in zip(filas, sel_mask, strict=True) if m]
        if not sel:
            continue
        mx = col(sel, "de_max")
        print(f"[CALD tramos {senal}] {etiqueta}: [{lo:.3g}, {hi:.3g}{']' if ultimo else ')'} "
              f"n={len(sel):4d} | de_max mediana {np.median(mx):6.2f} min {mx.min():6.2f} "
              f"max {mx.max():6.2f} | cumple {np.mean(mx < LIM):.3f}")


def bloque_tramos_fijos_bajos(etiqueta: str, filas: list[dict], senal: str) -> None:
    """Tramos de ANCHO FIJO en la zona baja de `senal` (0, 4, 8, 16, 32, 64+):
    es la comprobación específica que pide el encargo por el hallazgo del día
    4 (los peores errores fuera de plano salían de celdas con 7-14 muestras,
    NO de celdas vacías). Con cuantiles ese rango queda todo en un solo tramo
    (la mitad de las filas tienen p10 = 0); aquí no."""
    s = col(filas, senal)
    cortes = [0, 1, 4, 8, 16, 32, 64, float("inf")]
    print(f"[CALD tramos_bajos {senal}] {etiqueta}: tramos de ancho fijo cerca de "
          f"MUESTRAS_MINIMAS_CELDA (4)")
    for lo, hi in zip(cortes[:-1], cortes[1:], strict=True):
        sel = [r for r, v in zip(filas, s, strict=True) if lo <= v < hi]
        if not sel:
            print(f"[CALD tramos_bajos {senal}] {etiqueta}: [{lo}, {hi}) n=   0")
            continue
        mx = col(sel, "de_max")
        print(f"[CALD tramos_bajos {senal}] {etiqueta}: [{lo}, {hi}) n={len(sel):4d} | "
              f"de_max mediana {np.median(mx):6.2f} min {mx.min():6.2f} max {mx.max():6.2f} | "
              f"cumple {np.mean(mx < LIM):.3f}")


def bloque_auc_senal(etiqueta: str, filas: list[dict], senal: str) -> None:
    s = col(filas, senal)
    if not filas or np.ptp(s) == 0:
        return
    c = col(filas, "de_max") < LIM
    lo, hi = bootstrap(filas, lambda idx: auc(s[idx], c[idx]))
    print(f"[CALD auc {senal}] {etiqueta}: cumplen {int(c.sum())} de {len(filas)} | "
          f"AUC = {auc(s, c):.3f} IC95=[{lo:.3f}, {hi:.3f}] (0.5 = no predice; "
          f"señales donde MENOS es mejor —variance_zona— dan AUC < 0.5 si predicen bien)")


def bloque_auc_por_clase(etiqueta: str, filas: list[dict], senal: str) -> None:
    """AUC DENTRO de cada clase (tam_lut × compresión × recorte), sin bootstrap
    (algunas clases tienen muy pocos "cumple"): es la comprobación de que el
    AUC global no es una paradoja de Simpson, la misma que hizo el día 4 con
    `[CAL auc … | compresion=X recorte=Y]`."""
    for tam in (17.0, 33.0):
        for c in (0.0, 1.0):
            for rc in (0.0, 1.0):
                sel = [r for r in filas if r["tam_lut"] == tam and r["compresion"] == c
                       and r["recorte"] == rc]
                if not sel:
                    continue
                s = col(sel, senal)
                cu = col(sel, "de_max") < LIM
                print(f"[CALD auc_clase {senal}] {etiqueta} | tam={int(tam)} compresion={int(c)} "
                      f"recorte={int(rc)}: n={len(sel):4d} cumplen={int(cu.sum()):3d} "
                      f"AUC={auc(s, cu):.3f}")


def bloque_distribucion(etiqueta: str, filas: list[dict]) -> None:
    for senal in SENALES:
        s = col(filas, senal)
        if s.size == 0:
            continue
        pct = np.percentile(s, [0, 5, 25, 50, 75, 95, 100])
        print(f"[CALD distribucion {senal}] {etiqueta}: n={len(filas)} percentiles "
              "0/5/25/50/75/95/100 = " + " ".join(f"{p:.4g}" for p in pct))


# ---------------------------------------------------------------------------
# Nota combinada candidata
# ---------------------------------------------------------------------------


def _rampa(v: np.ndarray, bien: float, mal: float, *, log: bool = False) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    if log:
        v = np.log10(np.maximum(v, 1e-12))
        bien, mal = np.log10(max(bien, 1e-12)), np.log10(max(mal, 1e-12))
    if bien == mal:
        return np.where(v == bien, 1.0, 0.0)
    return np.clip((v - mal) / (bien - mal), 0.0, 1.0)


def nota_combinada(filas: list[dict], *, rampa_muestras: tuple[float, float],
                    con_varianza: bool = False) -> np.ndarray:
    """Candidata: `sqrt(min * media_geometrica)` de las subnotas que SÍ tienen
    el mismo signo dentro de cada clase de material (cobertura, muestras_p10
    en log), la misma forma que `puntuar_confianza`.

    `con_varianza=True` añade `variance_zona` sólo para poder enseñar, en el
    propio `main`, cuánto empeora meterla: el bloque 1 encuentra que su signo
    se INVIERTE dentro de la clase comprimida (§ variance_zona en el informe),
    así que NO entra en la nota por defecto. `planos_acumulados` tampoco entra
    aquí: en el bloque `simple` vale 1 siempre, y una subnota que nunca sube de
    0 en la mitad de los datos hundiría el mínimo sin decir nada útil.
    """
    cobertura = col(filas, "cobertura_destino")
    muestras = col(filas, "muestras_p10_zona")
    sub_cob = np.clip(cobertura, 0.0, 1.0)
    sub_mue = _rampa(muestras, *rampa_muestras, log=True)
    subnotas = [sub_cob, sub_mue]
    if con_varianza:
        varianza = col(filas, "variance_zona")
        v_no_cero = varianza[varianza > 0]
        bien_v = float(np.percentile(v_no_cero, 5)) if v_no_cero.size else 1e-8
        mal_v = float(np.percentile(v_no_cero, 95)) if v_no_cero.size else 1.0
        subnotas.append(1.0 - _rampa(varianza, mal_v, bien_v, log=True))
    subnotas_arr = np.stack(subnotas, axis=0)
    minimo = subnotas_arr.min(axis=0)
    geometrica = np.exp(np.mean(np.log(np.maximum(subnotas_arr, 1e-12)), axis=0))
    return np.sqrt(minimo * geometrica)


def bloque_umbral_por_clase(etiqueta: str, filas: list[dict], senal: str, *, n_min: int = 15) -> None:
    """El mismo criterio de umbral del día 4 pero DENTRO de cada clase de
    material, para no mezclar clases con tasas base de "cumple" muy distintas
    (17³ sin comprimir cumple ~5%, 33³ comprimido ~0.7%): mezclarlas en un solo
    umbral, como hace `bloque_umbral_nota` sobre "todo", puede esconder un
    corte que sí funciona dentro de una clase homogénea."""
    for tam in (17.0, 33.0):
        for c in (0.0, 1.0):
            for rc in (0.0, 1.0):
                sel = [r for r in filas if r["tam_lut"] == tam and r["compresion"] == c
                       and r["recorte"] == rc]
                if not sel:
                    continue
                s = col(sel, senal)
                cumple = col(sel, "de_max") < LIM
                mejor = None
                mejor_frac, mejor_t, mejor_n = -1.0, float("nan"), 0
                for t in np.unique(s):
                    sel_c = cumple[s >= t]
                    if sel_c.size < n_min:
                        continue
                    sub = [r for r, v in zip(sel, s, strict=True) if v >= t - 1e-12]
                    lo, hi = bootstrap(sub, lambda idx, cc=cumple[s >= t]: float(np.mean(cc[idx])))
                    if sel_c.mean() > mejor_frac:
                        mejor_frac, mejor_t, mejor_n = float(sel_c.mean()), float(t), int(sel_c.size)
                    if mejor is None and np.isfinite(lo) and lo >= 0.95:
                        mejor = t
                print(f"[CALD umbral_clase {senal}] {etiqueta} | tam={int(tam)} compresion={int(c)} "
                      f"recorte={int(rc)}: n={len(sel)} t_IC95>=0.95={'ninguno' if mejor is None else f'{mejor:.4f}'} "
                      f"| mejor con n>={n_min}: cumple={mejor_frac:.3f} en {senal}>={mejor_t:.4f} (n={mejor_n})")


def bloque_umbral_nota(etiqueta: str, filas: list[dict], nota: np.ndarray) -> None:
    cumple = col(filas, "de_max") < LIM
    print(f"[CALD umbral nota] {etiqueta}: criterio ALTA: fracción que cumple entre los casos con "
          f"nota >= t, IC95 bootstrap por escena; se pide IC inferior >= 0.95")
    filas2 = [dict(r, _nota=n) for r, n in zip(filas, nota, strict=True)]
    mejor = None
    for t in [0.0, 0.2, 0.4, 0.6, 0.75, 0.8, 0.9, 0.95, 0.99, 1.0]:
        sel = [r for r, v in zip(filas2, nota, strict=True) if v >= t - 1e-12]
        if not sel:
            continue
        c_sel = col(sel, "de_max") < LIM
        lo, hi = bootstrap(sel, lambda idx, c=c_sel: float(np.mean(c[idx])))
        print(f"[CALD umbral nota] {etiqueta}: t={t:.2f} n={len(sel):4d} cumple={c_sel.mean():.3f} "
              f"IC95=[{lo:.3f}, {hi:.3f}]")
        if mejor is None and np.isfinite(lo) and lo >= 0.95:
            mejor = t
    mejor_frac, mejor_t, mejor_n = -1.0, float("nan"), 0
    for t in np.unique(nota):
        sel_c = cumple[nota >= t]
        if sel_c.size < 20:
            continue
        if sel_c.mean() > mejor_frac:
            mejor_frac, mejor_t, mejor_n = float(sel_c.mean()), float(t), int(sel_c.size)
    print(f"[CALD umbral nota] {etiqueta}: RESULTADO: t con IC inferior >= 0.95: "
          f"{'ninguno' if mejor is None else f'{mejor:.2f}'} | lo mejor con n >= 20: "
          f"{mejor_frac:.3f} (nota >= {mejor_t:.4f}, n={mejor_n})")
    lo, hi = bootstrap(filas2, lambda idx: auc(nota[idx], cumple[idx]))
    print(f"[CALD umbral nota] {etiqueta}: AUC = {auc(nota, cumple):.3f} IC95=[{lo:.3f}, {hi:.3f}]")


def main() -> None:
    simple = cargar("simple_*.csv")
    lote = cargar("lote_*.csv")
    todo = simple + lote
    huellas = {r["huella_core"] for r in todo}
    print(f"[CALD guardia] filas simple={len(simple)} lote={len(lote)} total={len(todo)} | "
          f"huellas en los CSV={sorted(huellas)}")

    fuera_simple = [r for r in simple if r["fuera_de_plano"] == 1.0]
    fuera_lote = [r for r in lote if r["fuera_de_plano"] == 1.0]
    fuera_todo = fuera_simple + fuera_lote

    bloque_distribucion("todo, fuera de plano", fuera_todo)

    # 1. cada señal sola, global y dentro de cada clase de material
    for senal in ("cobertura_destino", "muestras_p10_zona", "muestras_mediana_zona", "variance_zona"):
        bloque_spearman_senal("simple, fuera de plano, TODO JUNTO", fuera_simple, senal)
        bloque_rho_ic_senal("simple, fuera de plano, TODO JUNTO", fuera_simple, senal)
        for tam in (17.0, 33.0):
            for c in (0.0, 1.0):
                for rc in (0.0, 1.0):
                    sel = [r for r in fuera_simple if r["tam_lut"] == tam and r["compresion"] == c
                           and r["recorte"] == rc]
                    bloque_spearman_senal(f"simple | tam={int(tam)} compresion={int(c)} recorte={int(rc)}",
                                          sel, senal)
        bloque_tramos_senal("simple, fuera de plano, TODO JUNTO", fuera_simple, senal)
        bloque_auc_senal("simple, fuera de plano, TODO JUNTO", fuera_simple, senal)
        if senal in ("cobertura_destino", "muestras_p10_zona"):
            bloque_auc_por_clase("simple, fuera de plano", fuera_simple, senal)
        if senal in ("muestras_p10_zona", "muestras_mediana_zona"):
            bloque_tramos_fijos_bajos("simple, fuera de plano, TODO JUNTO", fuera_simple, senal)
            bloque_tramos_fijos_bajos("lote, fuera de plano, TODO JUNTO", fuera_lote, senal)

    # 1b. lo mismo en el bloque lote, donde además varía planos_acumulados
    for senal in ("cobertura_destino", "muestras_p10_zona", "muestras_mediana_zona", "variance_zona"):
        bloque_spearman_senal("lote, fuera de plano, TODO JUNTO", fuera_lote, senal)
        for c in (0.0, 1.0):
            sel = [r for r in fuera_lote if r["compresion"] == c]
            bloque_spearman_senal(f"lote | compresion={int(c)}", sel, senal)

    # 2. planos_acumulados: sólo varía en `lote`
    bloque_spearman_senal("lote, fuera de plano, TODO JUNTO", fuera_lote, "planos_acumulados")
    bloque_rho_ic_senal("lote, fuera de plano, TODO JUNTO", fuera_lote, "planos_acumulados")
    bloque_tramos_senal("lote, fuera de plano, TODO JUNTO", fuera_lote, "planos_acumulados", n_tramos=5)
    for c in (0.0, 1.0):
        sel = [r for r in fuera_lote if r["compresion"] == c]
        bloque_spearman_senal(f"lote | compresion={int(c)}", sel, "planos_acumulados")
    bloque_auc_senal("lote, fuera de plano, TODO JUNTO", fuera_lote, "planos_acumulados")

    # 3. cobertura_destino SOLA (sin combinar con nada): ya es 0..1 por
    #    construcción, así que sirve de nota por sí misma.
    bloque_umbral_nota("todo, fuera de plano, SOLO cobertura_destino",
                       fuera_todo, col(fuera_todo, "cobertura_destino"))
    bloque_umbral_por_clase("simple, fuera de plano", fuera_simple, "cobertura_destino")

    # 4. nota combinada candidata (cobertura + muestras_p10), sobre TODO
    #    (simple + lote): dos rampas de "muestras_p10_zona" para ver cuánto cambia
    #    el resultado con dónde se ponga el corte.
    for bien, mal, nombre in ((200.0, 4.0, "200/4"), (1000.0, 8.0, "1000/8")):
        nota = nota_combinada(fuera_todo, rampa_muestras=(bien, mal))
        bloque_umbral_nota(f"todo, fuera de plano, cobertura+muestras_p10 rampa={nombre}",
                           fuera_todo, nota)

    # 5. lo mismo METIENDO variance_zona, para enseñar cuánto empeora (o no)
    #    incluir una señal cuyo signo se invierte dentro de la clase comprimida.
    nota_con_var = nota_combinada(fuera_todo, rampa_muestras=(200.0, 4.0), con_varianza=True)
    bloque_umbral_nota("todo, fuera de plano, cobertura+muestras_p10+variance (control)",
                       fuera_todo, nota_con_var)

    print("[CALD fin]")


if __name__ == "__main__":
    main()
