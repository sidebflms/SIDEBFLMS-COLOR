"""Material de la segunda vuelta de T5 (modo por lote), fabricado aqui.

NO IMPORTA `core` NI el material del autor del lote
---------------------------------------------------
Nada de `tests/test_reverse_lote_material.py` (leido, no usado). Las escenas salen
del generador de esta mañana (`t5_material.escena_trabajo`), el grado conocido
es el de esta mañana (mismo CDL, looks `global` y `secundarias`) mas un tercer
look nuevo, `estrechas`, para la pregunta de las secundarias estrechas.

EL PROYECTO
-----------
Un «trabajo» son cuatro montajes que se repiten, como en un rodaje: interior
calido, exterior de dia, noche fria y retrato. Cada plano es un montaje con otra
semilla (otra composicion) y con su paleta movida un poco: tono ±12 grados,
exposicion ±0.5 pasos, saturacion x0.85..1.15. Todos llevan EL MISMO grado.

* Planos del LOTE: `plano_del_lote(i)`, i = 0..39, montaje `i % 4`.
* Planos FUERA del lote, del mismo trabajo: `plano_fuera(j)`, j = 0..11, montaje
  `j % 4`, con semillas que el lote no usa. Es el caso de uso: los otros planos.
* Planos AJENOS al trabajo: `plano_ajeno(k)`, k = 0..3, paletas que ningun montaje
  tiene. Estan para ver el limite, no para el veredicto.

El orden del lote alterna montajes, asi que con 1 plano solo hay interior, con 3
faltan los retratos y a partir de 4 estan los cuatro.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import t5_material as M

MONTAJES: tuple[M.Paleta, ...] = (
    M.Paleta("interior calido", 30.0, 50.0, 0.10, 0.55, -0.2, 2.0, 7),
    M.Paleta("exterior dia", 90.0, 150.0, 0.10, 0.65, 0.3, 2.5, 10),
    M.Paleta("noche fria", 215.0, 60.0, 0.15, 0.60, -1.5, 2.5, 6, brillos=2),
    M.Paleta("retrato", 25.0, 30.0, 0.15, 0.50, -0.3, 1.5, 5),
)

AJENAS: tuple[M.Paleta, ...] = (
    M.Paleta("ajeno bosque", 120.0, 40.0, 0.20, 0.70, -0.5, 2.0, 8),
    M.Paleta("ajeno neon magenta", 300.0, 40.0, 0.50, 0.92, 0.0, 2.5, 8, brillos=2),
    M.Paleta("ajeno muy variada", 0.0, 360.0, 0.02, 0.92, 0.0, 4.0, 28, brillos=2),
    M.Paleta("ajeno desierto", 45.0, 25.0, 0.20, 0.45, 1.0, 1.5, 6),
)

SEMILLA_LOTE = 11_000
SEMILLA_FUERA = 21_000
SEMILLA_AJENO = 31_000
N_LOTE = 40
N_FUERA = 12


def _variante(pal: M.Paleta, semilla: int) -> M.Paleta:
    rng = np.random.default_rng(semilla + 777)
    s = rng.uniform(0.85, 1.15)
    return replace(
        pal,
        tono_centro=pal.tono_centro + rng.uniform(-12.0, 12.0),
        exposicion=pal.exposicion + rng.uniform(-0.5, 0.5),
        sat_min=float(np.clip(pal.sat_min * s, 0.0, 0.97)),
        sat_max=float(np.clip(pal.sat_max * s, 0.0, 0.97)),
    )


def plano_del_lote(i: int) -> tuple[str, np.ndarray]:
    pal = MONTAJES[i % len(MONTAJES)]
    semilla = SEMILLA_LOTE + i
    return f"L{i:02d} {pal.nombre}", M.escena_trabajo(_variante(pal, semilla), semilla)


def plano_fuera(j: int) -> tuple[str, np.ndarray]:
    pal = MONTAJES[j % len(MONTAJES)]
    semilla = SEMILLA_FUERA + j
    return f"F{j:02d} {pal.nombre}", M.escena_trabajo(_variante(pal, semilla), semilla)


def plano_ajeno(k: int) -> tuple[str, np.ndarray]:
    pal = AJENAS[k]
    semilla = SEMILLA_AJENO + k
    return f"X{k:02d} {pal.nombre}", M.escena_trabajo(pal, semilla)


def tabla_look(tipo: str, n: int = M.TAM_LUT) -> np.ndarray:
    """`global` y `secundarias` son los de esta mañana. `estrechas` es nuevo.

    `estrechas`: el look `global` MAS dos secundarias estrechas (ventana coseno
    de 20 grados de semiancho) y fuertes: amarillos (tono 100 del plano
    oponente) +55% de saturacion y azules (tono -90) -55%. Otros tonos y otro
    signo que los del look duro del autor (30 grados +60%, -150 grados -60%), a
    proposito: si lo que dice se reproduce con otro look, vale mas.
    """
    if tipo in ("global", "secundarias"):
        return M.tabla_look(tipo, n)
    if tipo != "estrechas":
        raise ValueError(tipo)
    t = M.tabla_look("global", n)
    lo = t @ np.array([0.2126, 0.7152, 0.0722])
    dif = t - lo[..., None]
    opa = dif[..., 0] - dif[..., 1]
    opb = 0.5 * (dif[..., 0] + dif[..., 1]) - dif[..., 2]
    tono = np.degrees(np.arctan2(opb, opa))
    peso = M._suave(np.hypot(opa, opb), 0.02, 0.08)

    def ventana(centro: float, semiancho: float) -> np.ndarray:
        d = np.abs((tono - centro + 180.0) % 360.0 - 180.0)
        return np.where(d < semiancho, 0.5 + 0.5 * np.cos(np.pi * d / semiancho), 0.0) * peso

    dif = dif * (1.0 + 0.55 * ventana(100.0, 20.0) - 0.55 * ventana(-90.0, 20.0))[..., None]
    return np.clip(lo[..., None] + dif, 0.0, 1.0)
