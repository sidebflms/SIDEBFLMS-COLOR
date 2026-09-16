"""T5, segunda vuelta: el grado ACUMULADO de N planos, aplicado a planos que no estan en el lote.

Se extrae con `core.reverse.invertir_grado_lote` (API publica) acumulando 1, 3, 5,
10, 20 y 40 planos de MI proyecto (`t5_lote_material.py`), con
`informacion="suma_w"` y con `"suma_w2"`, y se aplica a 12 planos del mismo
trabajo que NO han entrado en el lote (y a 4 ajenos). ΔE2000 de `colour`,
maximo delante.

COMO SE EJECUTA
---------------
Contra la copia congelada `.snapshots/dia4-lote` (commit a90b59c), con la misma
tecnica que la primera vuelta (ver el docstring de `test_t5_fuera_de_plano.py`).
Un look por invocacion, para no pasar de ~5 min seguidos con la maquina cargada:

    cd .snapshots/dia4-lote && PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest \\
        ../../tests/fuera_de_plano/test_t5_lote.py -s -p no:cacheprovider \\
        --import-mode=importlib --noconftest -rxXs -k <secundarias|global|estrechas|guardia|material>

Si `core` no resuelve a `.snapshots/dia4-lote`, todo se SALTA diciendo por que.
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

import t5_lote_material as L  # noqa: E402
import t5_material as M  # noqa: E402

import core  # noqa: E402

CORE_FILE = str(Path(core.__file__).resolve())
EN_COPIA_LOTE = "/.snapshots/dia4-lote/core/" in CORE_FILE

pytestmark = pytest.mark.skipif(
    not (EN_COPIA_LOTE or os.environ.get("T5_PERMITIR_REPO_VIVO") == "1"),
    reason=(
        f"T5-lote mide .snapshots/dia4-lote (a90b59c) y `core` ha resuelto a {CORE_FILE}. "
        "Ejecutalo desde `.snapshots/dia4-lote` con `../../.venv/bin/python -m pytest "
        "../../tests/fuera_de_plano/test_t5_lote.py -s -p no:cacheprovider "
        "--import-mode=importlib --noconftest` (ver MEDICION-T5.md, segunda vuelta)."
    ),
)

NS = (1, 3, 5, 10, 20, 40)
INFORMACIONES = ("suma_w", "suma_w2")
UMBRAL_MAX = 3.0
_CMD = (
    "cd .snapshots/dia4-lote && PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest "
    "../../tests/fuera_de_plano/test_t5_lote.py -s -p no:cacheprovider --import-mode=importlib "
    "--noconftest -rxXs -k "
)


def _imprimir(etiqueta: str, **cifras) -> None:
    partes = [f"{k}={v:.6g}" if isinstance(v, float) else f"{k}={v}" for k, v in cifras.items()]
    print(f"[T5L {etiqueta}] " + "  ".join(partes))


@functools.cache
def _planos_lote() -> tuple[tuple[str, np.ndarray], ...]:
    return tuple(L.plano_del_lote(i) for i in range(L.N_LOTE))


@functools.cache
def _planos_fuera() -> tuple[tuple[str, np.ndarray], ...]:
    return tuple(L.plano_fuera(j) for j in range(L.N_FUERA)) + tuple(
        L.plano_ajeno(k) for k in range(len(L.AJENAS))
    )


def _medir(r, x: np.ndarray, x_prima: np.ndarray) -> dict[str, float]:
    """Grado extraido sobre `x` contra `x_prima`. Mascaras sobre `cdl_extraido(x)`."""
    post = r.cdl.apply(np.asarray(x, dtype=np.float64))
    pred = r.lut.apply(post)
    de = M.delta_e2000(x_prima, pred).reshape(-1)
    sdr = M.trabajo_a_lab(x_prima).reshape(-1, 3)[:, 0] <= 100.0
    counts = np.asarray(r.coverage.counts).reshape(-1)
    cubierta = np.asarray(r.coverage.covered_mask()).reshape(-1)
    cerca = M.celda_mas_cercana(post)
    m_cub = cubierta[cerca]
    m_inv = counts[cerca] == 0
    out = {}
    for nombre, mascara in (("todo", None), ("sdr", sdr), ("cub", m_cub), ("inv", m_inv)):
        for k, v in M.resumen(de, mascara).items():
            out[f"{nombre}_{k}"] = v
    out["frac_px_cub"] = float(m_cub.mean())
    out["frac_px_inv"] = float(m_inv.mean())
    return out


def _histograma_de(planos) -> np.ndarray:
    h = np.zeros(M.TAM_LUT**3)
    for _, img in planos:
        h += np.bincount(M.celda_mas_cercana(img), minlength=M.TAM_LUT**3)
    return h / h.sum()


@functools.cache
def barrido(look: str) -> tuple[list[dict], list[dict]]:
    """Por cada N y cada `informacion`: un lote, su cobertura y los 16 planos de fuera."""
    from core.reverse import invertir_grado_lote

    tabla = L.tabla_look(look)
    lote = _planos_lote()
    pares = [(img, M.colorear(img, tabla)) for _, img in lote]
    for a, b in pares:
        assert np.isfinite(a).all() and np.isfinite(b).all()
    fuera = [(nombre, img, M.colorear(img, tabla)) for nombre, img in _planos_fuera()]

    filas: list[dict] = []
    lotes: list[dict] = []
    for n in NS:
        h_lote = _histograma_de(lote[:n])
        for info in INFORMACIONES:
            r = invertir_grado_lote(
                pares[:n], nombres=[nm for nm, _ in lote[:n]], diagnosticar_planos=False,
                verificar_coherencia=False, informacion=info,
            )
            counts = np.asarray(r.coverage.counts)
            m = r.confidence.metrics
            lotes.append({
                "look": look, "informacion": info, "N": n,
                "cobertura": r.coverage.coverage_fraction(),
                "nodos_1_3": int(((counts >= 1) & (counts < 4)).sum()),
                "nodos_4_15": int(((counts >= 4) & (counts < 16)).sum()),
                "nodos_16_63": int(((counts >= 16) & (counts < 64)).sum()),
                "nodos_64": int((counts >= 64).sum()),
                "repo_de_max_cubierto_en_el_lote": float(m["de_max_cubierto"]),
                "repo_de_medio_cubierto_en_el_lote": float(m["de_medio_cubierto"]),
                "planos_usados": float(m.get("lote_planos_usados", float("nan"))),
            })
            for nombre, x, x_prima in fuera:
                fila = {"look": look, "informacion": info, "N": n, "plano": nombre,
                        "ajeno": nombre.startswith("X"),
                        "montaje_en_lote": any(nombre[4:] == nm[4:] for nm, _ in lote[:n]),
                        "solape_con_lote": float(np.minimum(h_lote, _histograma_de([(nombre, x)])).sum())}
                fila.update(_medir(r, x, x_prima))
                filas.append(fila)
    _escribir_csv(look, filas, lotes)
    return filas, lotes


def _escribir_csv(look: str, filas: list[dict], lotes: list[dict]) -> None:
    for nombre, datos in ((f"resultados_t5_lote_{look}.csv", filas),
                          (f"lotes_t5_lote_{look}.csv", lotes)):
        with open(_AQUI / nombre, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(datos[0]))
            w.writeheader()
            w.writerows(datos)


def _resumen(filas: list[dict]) -> dict:
    mx = [f["todo_max"] for f in filas]
    sd = [f["sdr_max"] for f in filas]
    return {
        "planos": len(filas),
        "peor_max": max(mx), "mediana_max": float(np.median(mx)), "mejor_max": min(mx),
        "planos_max_bajo_3": sum(v < UMBRAL_MAX for v in mx),
        "peor_max_sdr": max(sd), "planos_max_sdr_bajo_3": sum(v < UMBRAL_MAX for v in sd),
        "mediana_p95": float(np.median([f["todo_p95"] for f in filas])),
        "peor_p95": max(f["todo_p95"] for f in filas),
        "mediana_medio": float(np.median([f["todo_medio"] for f in filas])),
        "peor_cub_max": max(f["cub_max"] for f in filas if f["cub_n"] > 0),
        "peor_inv_max": max((f["inv_max"] for f in filas if f["inv_n"] > 0), default=float("nan")),
        "mediana_frac_px_cub": float(np.median([f["frac_px_cub"] for f in filas])),
    }


def _informe(look: str) -> None:
    filas, lotes = barrido(look)
    print(f"\n[T5L] ===== {look}: cobertura del lote frente a N =====")
    for lo in lotes:
        _imprimir(f"cobertura {look} | {lo['informacion']} | N={lo['N']}",
                  **{k: v for k, v in lo.items() if k not in ("look", "informacion", "N")})
    print(f"\n[T5L] ===== {look}: cada plano de fuera =====")
    for f in filas:
        _imprimir(
            f"fuera {look} | {f['informacion']} | N={f['N']} | {f['plano']}",
            montaje_en_lote=f["montaje_en_lote"], solape_con_lote=f["solape_con_lote"],
            frac_px_cub=f["frac_px_cub"], todo_max=f["todo_max"], sdr_max=f["sdr_max"],
            todo_p95=f["todo_p95"], todo_medio=f["todo_medio"],
            frac_px_mayor_3=f["todo_frac_mayor_3"], cub_max=f["cub_max"], inv_max=f["inv_max"],
        )
    print(f"\n[T5L] ===== {look}: resumen, 12 planos del trabajo fuera del lote =====")
    for n in NS:
        for info in INFORMACIONES:
            sel = [f for f in filas if f["N"] == n and f["informacion"] == info and not f["ajeno"]]
            _imprimir(f"resumen {look} | {info} | N={n} | del trabajo", **_resumen(sel))
            sel_en = [f for f in sel if f["montaje_en_lote"]]
            if 0 < len(sel_en) < len(sel):
                _imprimir(f"resumen {look} | {info} | N={n} | montaje en el lote", **_resumen(sel_en))
    print(f"\n[T5L] ===== {look}: resumen, 4 planos ajenos al trabajo =====")
    for n in NS:
        for info in INFORMACIONES:
            sel = [f for f in filas if f["N"] == n and f["informacion"] == info and f["ajeno"]]
            _imprimir(f"ajenos {look} | {info} | N={n}", **_resumen(sel))


# ---------------------------------------------------------------------------


def test_t5l_guardia_core_resuelve_a_la_copia_dia4_lote():
    import core.reverse

    print(f"\n[T5L guardia] core.__file__={CORE_FILE}")
    print(f"[T5L guardia] core.reverse.__file__={Path(core.reverse.__file__).resolve()}")
    print(f"[T5L guardia] t5_lote_material.__file__={Path(L.__file__).resolve()}")
    assert EN_COPIA_LOTE, CORE_FILE
    assert hasattr(core.reverse, "invertir_grado_lote")
    import inspect

    firma = inspect.signature(core.reverse.invertir_grado_lote)
    print(f"[T5L guardia] defecto de informacion en invertir_grado_lote = "
          f"{firma.parameters['informacion'].default!r}")
    print(f"[T5L guardia] defecto de informacion en invertir_grado = "
          f"{inspect.signature(core.reverse.invertir_grado).parameters['informacion'].default!r}")


def test_t5l_material_looks():
    from core.contracts import LUT3D
    from core.io import qc_lut

    identidad = np.stack(np.meshgrid(*[np.linspace(0, 1, M.TAM_LUT)] * 3, indexing="ij"), -1)
    for look in ("global", "secundarias", "estrechas"):
        t = L.tabla_look(look)
        qc = qc_lut(LUT3D(table=t.astype(np.float32)))
        _imprimir(f"material {look}", qc_ok=qc.ok, codigos=",".join(qc.codigos()) or "-",
                  escalones_banding=qc.metricas.get("escalones_de_banding", float("nan")),
                  celdas_no_monotonas=qc.metricas.get("celdas_no_monotonas", float("nan")),
                  max_dist_identidad=float(np.abs(t - identidad).max()))
    lote, fuera = _planos_lote(), _planos_fuera()
    for nombre, img in lote[:4] + fuera:
        assert np.isfinite(img).all(), nombre
    _imprimir("material proyecto", planos_lote=len(lote), planos_fuera=len(fuera),
              solape_fuera_con_lote40_min=min(
                  float(np.minimum(_histograma_de(lote), _histograma_de([p])).sum())
                  for p in fuera[:L.N_FUERA]))


def test_t5l_secundarias():
    _informe("secundarias")


def test_t5l_global():
    _informe("global")


def test_t5l_estrechas():
    _informe("estrechas")


def _del_trabajo(look: str, info: str, n: int) -> list[dict]:
    filas, _ = barrido(look)
    return [f for f in filas if f["informacion"] == info and f["N"] == n and not f["ajeno"]]


def _sin_filas(look: str, info: str, n: int, sel: list[dict]) -> str:
    """Mensaje de la guarda: por que el filtro podria no traer los 12 planos de fuera.
    Sin esta guarda, un filtro vacio haria pasar el criterio sin mirar ni un plano."""
    return (
        f"esperaba {L.N_FUERA} planos de fuera del trabajo para look={look!r} "
        f"informacion={info!r} N={n} y hay {len(sel)}. Causas posibles: el look o la "
        f"`informacion` han cambiado de nombre, N no esta en NS={NS}, L.N_FUERA ha cambiado, "
        f"o `ajeno` ya no distingue los planos X del trabajo (nombres: "
        f"{sorted(f['plano'] for f in sel)})."
    )


def test_t5l_secundarias_criterio_lote_suma_w2_desde_3_planos():
    """Look `secundarias`, lote con suma_w2: max < 3.0 en los 12 planos de fuera desde N=3."""
    for n in (3, 5, 10, 20, 40):
        sel = _del_trabajo("secundarias", "suma_w2", n)
        assert len(sel) == L.N_FUERA, _sin_filas("secundarias", "suma_w2", n, sel)
        malos = {f["plano"]: round(f["todo_max"], 4) for f in sel if not f["todo_max"] < UMBRAL_MAX}
        assert not malos, (n, malos)


def test_t5l_global_criterio_lote_suma_w2_desde_1_plano():
    """Look `global`, lote con suma_w2: max < 3.0 en los 12 planos de fuera desde N=1."""
    for n in NS:
        sel = _del_trabajo("global", "suma_w2", n)
        assert len(sel) == L.N_FUERA, _sin_filas("global", "suma_w2", n, sel)
        malos = {f["plano"]: round(f["todo_max"], 4) for f in sel if not f["todo_max"] < UMBRAL_MAX}
        assert not malos, (n, malos)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Look `estrechas` (global + amarillos +55% y azules -55%, ventanas de 20 grados; qc_lut: "
        "67 escalones de banding, es lo esperable) con el lote de 40 planos y suma_w2: max < 3.0 "
        "en 10 de 12 planos de fuera. Fallan F01 exterior dia 4.1987 y F05 exterior dia 3.2471, "
        "los dos en celda CUBIERTA (99.999% y 99.350% de sus pixeles en celda cubierta, sin "
        "pixeles de L*>100): falta 1.1987 de margen. Con suma_w: 4.9702 y 3.4136. Medido "
        "16-09-2026 contra .snapshots/dia4-lote (a90b59c), ΔE de colour-science, con: "
        + _CMD + "t5l_estrechas. Cerrarlo = max < 3.0 en los 12."
    ),
)
def test_t5l_estrechas_criterio_lote_40_planos_suma_w2():
    malos = {f["plano"]: round(f["todo_max"], 4) for f in _del_trabajo("estrechas", "suma_w2", 40)
             if not f["todo_max"] < UMBRAL_MAX}
    assert not malos, malos


def test_t5l_cobertura_media_resolucion():
    """La cobertura frente a N con los MISMOS 40 planos a 320x180 (media de 2x2), para
    poder poner mi tabla al lado de la del autor, que midio a 320x180. Look
    `secundarias`; la cobertura no depende de `informacion`."""
    from core.reverse import invertir_grado_lote

    tabla = L.tabla_look("secundarias")

    def mitad(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[0] // 2 * 2, img.shape[1] // 2 * 2
        return img[:h, :w].reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3)).astype(np.float32)

    lote = [mitad(img) for _, img in _planos_lote()]
    pares = [(a, M.colorear(a, tabla)) for a in lote]
    print()
    for n in NS:
        r = invertir_grado_lote(pares[:n], diagnosticar_planos=False, verificar_coherencia=False)
        counts = np.asarray(r.coverage.counts)
        _imprimir(f"cobertura 320x180 secundarias | N={n}", alto=lote[0].shape[0],
                  ancho=lote[0].shape[1], cobertura=r.coverage.coverage_fraction(),
                  nodos_1_3=int(((counts >= 1) & (counts < 4)).sum()),
                  nodos_4_15=int(((counts >= 4) & (counts < 16)).sum()),
                  nodos_16_63=int(((counts >= 16) & (counts < 64)).sum()),
                  nodos_64=int((counts >= 64).sum()))


# ---------------------------------------------------------------------------
# La pregunta de UN plano con suma_w2 (lo que dice el autor, NOTAS §12.4)
# ---------------------------------------------------------------------------


def _un_plano(look: str) -> dict[str, int]:
    from core.reverse import invertir_grado

    tabla = L.tabla_look(look)
    lote = _planos_lote()[:11]
    fuera = [(nm, x, M.colorear(x, tabla)) for nm, x in _planos_fuera()[:L.N_FUERA]]
    print(f"\n[T5L] ===== {look}: UN plano, A->A y A->fuera, 11 planos =====")
    planos_mayor_3: dict[str, int] = {}
    for info in INFORMACIONES:
        propios, repo, peores_fuera, pares_bajo_3 = [], [], [], 0
        for nombre, a in lote:
            a_prima = M.colorear(a, tabla)
            r = invertir_grado(a, a_prima, informacion=info)
            yo = _medir(r, a, a_prima)
            propios.append(yo["cub_max"])
            repo.append(float(r.confidence.metrics["de_max_cubierto"]))
            maxs = [_medir(r, x, xp)["todo_max"] for _, x, xp in fuera]
            peores_fuera.append(max(maxs))
            pares_bajo_3 += sum(v < UMBRAL_MAX for v in maxs)
            _imprimir(f"un plano {look} | {info} | {nombre}", AA_cub_max=yo["cub_max"],
                      AA_todo_max=yo["todo_max"], repo_de_max_cubierto=repo[-1],
                      fuera_peor_max=max(maxs), fuera_mejor_max=min(maxs),
                      fuera_mediana_max=float(np.median(maxs)))
        _imprimir(
            f"un plano resumen {look} | {info}",
            AA_mediana_cub_max=float(np.median(propios)), AA_peor_cub_max=max(propios),
            AA_planos_mayor_3=sum(v > UMBRAL_MAX for v in propios),
            repo_mediana=float(np.median(repo)), repo_peor=max(repo),
            repo_planos_mayor_3=sum(v > UMBRAL_MAX for v in repo),
            fuera_pares=len(lote) * len(fuera), fuera_pares_max_bajo_3=pares_bajo_3,
            fuera_mediana_de_peores=float(np.median(peores_fuera)),
        )
        planos_mayor_3[info] = sum(v > UMBRAL_MAX for v in propios)
    return planos_mayor_3


def test_t5l_un_plano_estrechas():
    """Ademas de medir: el autor dice que con UN plano y secundarias estrechas suma_w2
    EMPEORA (7 de 11 > 3.0 frente a 2 de 11). Aqui se afirma lo que sale en MI montaje."""
    resumen = _un_plano("estrechas")
    assert resumen["suma_w2"] <= resumen["suma_w"], resumen


def test_t5l_un_plano_global():
    _un_plano("global")


# ---------------------------------------------------------------------------
# El montaje de esta mañana (72 pares de un plano), cambiando SOLO `informacion`
# ---------------------------------------------------------------------------


def _manana(look: str) -> None:
    """Las 6 escenas A y sus 6 B de la primera vuelta, mismas semillas, un plano,
    con `invertir_grado(..., informacion=...)`. Con `suma_w` tiene que reproducir
    las cifras de esta mañana (el autor dice que `invertir_grado` no ha cambiado)."""
    from core.reverse import invertir_grado

    semilla_a, semilla_b = 5001, 7001  # las de test_t5_fuera_de_plano.py
    tabla = M.tabla_look(look)
    print(f"\n[T5L] ===== montaje de esta mañana, {look}, 6 A x 6 B =====")
    for info in INFORMACIONES:
        maximos_a2, maximos, sdr = [], [], []
        for ia, pal in enumerate(M.PALETAS_A):
            a = M.escena_trabajo(pal, semilla_a + ia)
            r = invertir_grado(a, M.colorear(a, tabla), informacion=info)
            for jb, (etiqueta, pal_b) in enumerate(M.paletas_b(pal)):
                b = M.escena_trabajo(pal_b, semilla_b + 100 * ia + jb)
                med = _medir(r, b, M.colorear(b, tabla))
                maximos.append(med["todo_max"])
                sdr.append(med["sdr_max"])
                if ia == 1:
                    maximos_a2.append(med["todo_max"])
                _imprimir(f"manana {look} | {info} | {pal.nombre} | {etiqueta}",
                          todo_max=med["todo_max"], sdr_max=med["sdr_max"],
                          todo_p95=med["todo_p95"], todo_medio=med["todo_medio"],
                          cub_max=med["cub_max"], inv_max=med["inv_max"])
        _imprimir(f"manana resumen {look} | {info}", pares=len(maximos),
                  pares_max_bajo_3=sum(v < UMBRAL_MAX for v in maximos),
                  pares_max_sdr_bajo_3=sum(v < UMBRAL_MAX for v in sdr),
                  mediana_max=float(np.median(maximos)), peor_max=max(maximos),
                  A2_max_min=min(maximos_a2), A2_max_peor=max(maximos_a2),
                  A2_pares_max_bajo_3=sum(v < UMBRAL_MAX for v in maximos_a2))


def test_t5l_manana_secundarias():
    _manana("secundarias")


def test_t5l_manana_global():
    _manana("global")
