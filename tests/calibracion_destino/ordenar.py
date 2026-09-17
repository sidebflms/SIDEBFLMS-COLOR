"""¿Ordenar en vez de certificar mejora el triaje? Mide precisión@5/@10.

POR QUÉ EXISTE (día 6)
-----------------------
`CALIBRACION-CONFIANZA-DESTINO.md` (día 5) midió que ninguna combinación de
`FeaturesDestino` llega al 95% que hacía falta para CERTIFICAR. Mario decidió
que el paso 5 del modo fácil no necesita certificar, necesita ORDENAR una
lista de candidatos de peor a mejor. Este script mide si eso funciona mejor
que las señales crudas sin ajustar, y publica las cifras que van a
`CIFRAS.md` §17.

EL HALLAZGO QUE SE INTENTA APROVECHAR
---------------------------------------
El día 5 (§3.2/§5 del informe) midió que `cobertura_destino` predice bien
DENTRO de cada una de 8 clases de material (rejilla × compresión × recorte),
pero el umbral de "cobertura buena" cambia mucho de una clase a otra. Aquí se
prueba la hipótesis: normalizar por clase (z-score dentro de la clase) antes
de comparar entre clips de clases distintas debería ordenar mejor que
comparar las señales crudas sin ajustar.

QUÉ SE MIDE
-----------
1. Estadísticas de calibración por clase (media y desviación de
   `cobertura_destino`, `log1p(muestras_p10_zona)` y `log1p(planos_acumulados)`
   dentro de cada una de las 8 clases informadas, más 2 clases "desconocida"
   marginando compresión/recorte dentro de cada rejilla, más 1 global). Se
   imprimen listas para pegar en `core/reverse/orden_repaso.py` (la misma
   fórmula que usa ese módulo en producción: si algo cambia aquí, hay que
   volver a pegar).
2. Precisión@5 y precisión@10 en LOTES SIMULADOS de candidatos (tamaño fijo,
   ver `TAM_LOTE`; no hay un "grupo natural" en el encargo real — el paso 5
   junta clips de un timeline entero — así que se simulan lotes mezclando
   filas fuera de plano de distintas extracciones, que es lo más parecido a
   "lo que se enseñaría junto"), para tres variantes:
   * **calibrado, informado**: normaliza por la clase EXACTA (compresión y
     recorte tal y como los conoce el arnés de calibración).
   * **calibrado, desconocido**: normaliza sólo por `tam_rejilla` (la única
     información de clase que existe de verdad sobre un clip real hoy: ver
     el docstring de `core/reverse/orden_repaso.py`).
   * **ingenuo**: las mismas señales, SIN normalizar por clase.
   Más una línea de referencia: la precisión esperada de un orden al azar
   (`k / TAM_LOTE`), para poder decir "mejor que azar" con un número al lado.

Uso (después de `medir.py`, que ya dejó los CSV en `datos/`):

    .venv/bin/python -m tests.calibracion_destino.ordenar
    .venv/bin/python -m tests.calibracion_destino.ordenar | grep "CALD orden"
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

from tests.calibracion_destino.analizar import cargar, col

warnings.filterwarnings("ignore")

TAM_LOTE = 20  # candidatos por lote simulado
N_PERMUTACIONES = 20  # particiones distintas de todo el conjunto en lotes
SEMILLA = 20260917
DESV_MINIMA = 1e-6  # guarda de division: ninguna clase con desviacion 0 divide por 0


# ---------------------------------------------------------------------------
# 1. Estadisticas de calibracion por clase
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _EstadisticasClase:
    n: int
    media_cobertura: float
    desv_cobertura: float
    media_log_muestras: float
    desv_log_muestras: float
    media_log_planos: float
    desv_log_planos: float


def _stats_de(filas: list[dict]) -> _EstadisticasClase:
    cobertura = col(filas, "cobertura_destino")
    log_muestras = np.log1p(col(filas, "muestras_p10_zona"))
    log_planos = np.log1p(col(filas, "planos_acumulados"))
    return _EstadisticasClase(
        n=len(filas),
        media_cobertura=float(np.mean(cobertura)), desv_cobertura=float(np.std(cobertura)),
        media_log_muestras=float(np.mean(log_muestras)), desv_log_muestras=float(np.std(log_muestras)),
        media_log_planos=float(np.mean(log_planos)), desv_log_planos=float(np.std(log_planos)),
    )


def calcular_estadisticas_por_clase(filas: list[dict]) -> dict[tuple, _EstadisticasClase]:
    """Las 8 clases informadas + 2 "desconocida" (por rejilla) + 1 global.

    Misma partición que usa `core/reverse/orden_repaso.py` en producción: si
    esta función cambia, hay que repetir la medición y pegar los números
    nuevos allí (están citados con el comando exacto de este fichero).
    """
    estadisticas: dict[tuple, _EstadisticasClase] = {}
    for tam in (17.0, 33.0):
        for c in (0.0, 1.0):
            for rc in (0.0, 1.0):
                sel = [r for r in filas if r["tam_lut"] == tam and r["compresion"] == c
                       and r["recorte"] == rc]
                if sel:
                    estadisticas[(int(tam), bool(c), bool(rc))] = _stats_de(sel)
        sel_rejilla = [r for r in filas if r["tam_lut"] == tam]
        if sel_rejilla:
            estadisticas[(int(tam), None, None)] = _stats_de(sel_rejilla)
    estadisticas[(0, None, None)] = _stats_de(filas)  # global, colchon final
    return estadisticas


def imprimir_estadisticas(estadisticas: dict[tuple, _EstadisticasClase]) -> None:
    print("[CALD orden estadisticas] clave=(tam_rejilla, compresion, recorte); "
          "None=desconocida/marginada")
    for clave in sorted(estadisticas, key=lambda k: (k[0], k[1] is None, k[2] is None, k[1], k[2])):
        e = estadisticas[clave]
        print(f"[CALD orden estadisticas] {clave}: n={e.n:4d} "
              f"cobertura media={e.media_cobertura:.4f} desv={e.desv_cobertura:.4f} | "
              f"log_muestras media={e.media_log_muestras:.4f} desv={e.desv_log_muestras:.4f} | "
              f"log_planos media={e.media_log_planos:.4f} desv={e.desv_log_planos:.4f}")
    print("[CALD orden estadisticas] --- listo para pegar en core/reverse/orden_repaso.py ---")
    for clave in sorted(estadisticas, key=lambda k: (k[0], k[1] is None, k[2] is None, k[1], k[2])):
        e = estadisticas[clave]
        print(f"    {clave}: ({e.media_cobertura:.6f}, {e.desv_cobertura:.6f}, "
              f"{e.media_log_muestras:.6f}, {e.desv_log_muestras:.6f}, "
              f"{e.media_log_planos:.6f}, {e.desv_log_planos:.6f}),  # n={e.n}")


# ---------------------------------------------------------------------------
# 2. Puntuaciones internas: calibrada (por clase) e ingenua (sin normalizar)
# ---------------------------------------------------------------------------


def _z(valor: float, media: float, desv: float) -> float:
    return (float(valor) - media) / max(desv, DESV_MINIMA)


def _clave_fila(fila: dict, *, informado: bool) -> tuple:
    tam = int(fila["tam_lut"])
    if not informado:
        return (tam, None, None)
    return (tam, bool(fila["compresion"]), bool(fila["recorte"]))


def puntuacion_calibrada(fila: dict, estadisticas: dict[tuple, _EstadisticasClase], *,
                          informado: bool) -> float:
    """Media de tres z-scores DENTRO de la clase del candidato. Más alto =
    mejor (se ordena de peor a mejor, o sea ascendente en esta puntuacion).

    `variance_zona` se excluye a proposito: su signo se invierte dentro de la
    clase comprimida incluso separando por clase (día 5, §3.2/§6.1) — no es
    algo que la normalización arregle, es un problema de cómo se calcula la
    señal. Meterla empeoraría el orden justo en el material más difícil.
    """
    clave = _clave_fila(fila, informado=informado)
    e = estadisticas.get(clave) or estadisticas[(int(fila["tam_lut"]), None, None)] \
        or estadisticas[(0, None, None)]
    z_cobertura = _z(fila["cobertura_destino"], e.media_cobertura, e.desv_cobertura)
    z_muestras = _z(np.log1p(fila["muestras_p10_zona"]), e.media_log_muestras, e.desv_log_muestras)
    z_planos = _z(np.log1p(fila["planos_acumulados"]), e.media_log_planos, e.desv_log_planos)
    return float(np.mean([z_cobertura, z_muestras, z_planos]))


def puntuacion_ingenua(fila: dict) -> float:
    """Las mismas tres señales, SIN normalizar por clase: cobertura y
    log(muestras)/log(planos) crudos, para que la escala sea comparable entre
    sí (si no, `muestras_p10_zona` con valores de cientos aplastaría a
    `cobertura_destino` en 0..1). Es el control: si el orden calibrado no le
    saca ventaja, normalizar por clase no está ayudando de verdad."""
    return float(np.mean([
        fila["cobertura_destino"],
        np.log1p(fila["muestras_p10_zona"]) / 10.0,
        np.log1p(fila["planos_acumulados"]) / 10.0,
    ]))


# ---------------------------------------------------------------------------
# 3. Precision@k en lotes simulados
# ---------------------------------------------------------------------------


def precision_en_k(orden_predicho: list[int], orden_verdad: list[int], k: int) -> float:
    """De los k primeros del orden predicho (peor a mejor), cuántos están
    entre los k primeros de la verdad (mismo criterio: peor a mejor)."""
    return len(set(orden_predicho[:k]) & set(orden_verdad[:k])) / k


def medir_variante(filas: list[dict], puntuar, *, k5: int = 5, k10: int = 10) -> tuple[float, float, float, float]:
    """Recorre `N_PERMUTACIONES` particiones de `filas` en lotes de `TAM_LOTE`
    y devuelve (media_p5, desv_p5, media_p10, desv_p10) sobre todos los lotes.

    Partir en vez de muestrear con reemplazo: cada fila entra una vez por
    permutación, así que con `N_PERMUTACIONES` altas cada fila pasa por
    muchos lotes distintos sin sesgar hacia las filas más "fáciles" de
    agrupar juntas."""
    p5s: list[float] = []
    p10s: list[float] = []
    n = len(filas)
    n_lotes = n // TAM_LOTE
    for perm in range(N_PERMUTACIONES):
        rng = np.random.default_rng(SEMILLA + perm)
        orden_global = rng.permutation(n)
        for lote_i in range(n_lotes):
            idxs = orden_global[lote_i * TAM_LOTE: (lote_i + 1) * TAM_LOTE]
            lote = [filas[i] for i in idxs]
            de_max = col(lote, "de_max")
            # verdad: peor (de_max mas alto) primero
            orden_verdad = list(np.argsort(-de_max))
            puntuaciones = np.array([puntuar(r) for r in lote])
            # prediccion: puntuacion mas BAJA = peor, primero
            orden_predicho = list(np.argsort(puntuaciones))
            p5s.append(precision_en_k(orden_predicho, orden_verdad, k5))
            p10s.append(precision_en_k(orden_predicho, orden_verdad, k10))
    return float(np.mean(p5s)), float(np.std(p5s)), float(np.mean(p10s)), float(np.std(p10s))


def comparar_pareado(filas: list[dict], puntuar_a, puntuar_b, *, nombre_a: str, nombre_b: str,
                      k: int = 5) -> None:
    """Sobre los MISMOS lotes (misma partición), ¿en cuántos gana cada
    variante? Es la prueba de que la mejora no es un efecto de agregado: si
    calibrado gana en la mayoría de los lotes uno a uno, no es casualidad de
    cómo se promedia."""
    n = len(filas)
    n_lotes = n // TAM_LOTE
    gana_a, gana_b, empate = 0, 0, 0
    diffs: list[float] = []
    for perm in range(N_PERMUTACIONES):
        rng = np.random.default_rng(SEMILLA + perm)
        orden_global = rng.permutation(n)
        for lote_i in range(n_lotes):
            idxs = orden_global[lote_i * TAM_LOTE: (lote_i + 1) * TAM_LOTE]
            lote = [filas[i] for i in idxs]
            de_max = col(lote, "de_max")
            orden_verdad = list(np.argsort(-de_max))
            pa = precision_en_k(list(np.argsort([puntuar_a(r) for r in lote])), orden_verdad, k)
            pb = precision_en_k(list(np.argsort([puntuar_b(r) for r in lote])), orden_verdad, k)
            diffs.append(pa - pb)
            if pa > pb:
                gana_a += 1
            elif pb > pa:
                gana_b += 1
            else:
                empate += 1
    total = gana_a + gana_b + empate
    print(f"[CALD orden pareado] {nombre_a} vs {nombre_b} en precision@{k}, mismos {total} lotes: "
          f"{nombre_a} gana {gana_a} ({gana_a / total:.1%}) | {nombre_b} gana {gana_b} "
          f"({gana_b / total:.1%}) | empate {empate} ({empate / total:.1%}) | "
          f"diferencia media {np.mean(diffs):+.4f}")


def main() -> None:
    simple = cargar("simple_*.csv")
    lote = cargar("lote_*.csv")
    fuera = [r for r in simple + lote if r["fuera_de_plano"] == 1.0]
    print(f"[CALD orden guardia] filas fuera de plano: {len(fuera)} | "
          f"tam_lote={TAM_LOTE} n_permutaciones={N_PERMUTACIONES} "
          f"lotes_por_permutacion={len(fuera) // TAM_LOTE}")

    estadisticas = calcular_estadisticas_por_clase(fuera)
    imprimir_estadisticas(estadisticas)

    baseline5, baseline10 = 5.0 / TAM_LOTE, 10.0 / TAM_LOTE
    print(f"[CALD orden baseline] orden al azar (referencia, no medido): "
          f"precision@5={baseline5:.3f} precision@10={baseline10:.3f}")

    for nombre, puntuar in (
        ("calibrado_informado", lambda r: puntuacion_calibrada(r, estadisticas, informado=True)),
        ("calibrado_desconocido", lambda r: puntuacion_calibrada(r, estadisticas, informado=False)),
        ("ingenuo", puntuacion_ingenua),
    ):
        m5, s5, m10, s10 = medir_variante(fuera, puntuar)
        print(f"[CALD orden precision] {nombre}: precision@5={m5:.3f} (+/-{s5:.3f}) "
              f"precision@10={m10:.3f} (+/-{s10:.3f})")

    comparar_pareado(
        fuera,
        lambda r: puntuacion_calibrada(r, estadisticas, informado=True),
        puntuacion_ingenua,
        nombre_a="calibrado_informado", nombre_b="ingenuo", k=5,
    )
    comparar_pareado(
        fuera,
        lambda r: puntuacion_calibrada(r, estadisticas, informado=True),
        puntuacion_ingenua,
        nombre_a="calibrado_informado", nombre_b="ingenuo", k=10,
    )
    comparar_pareado(
        fuera,
        lambda r: puntuacion_calibrada(r, estadisticas, informado=False),
        puntuacion_ingenua,
        nombre_a="calibrado_desconocido", nombre_b="ingenuo", k=5,
    )

    print("[CALD orden fin]")


if __name__ == "__main__":
    main()
