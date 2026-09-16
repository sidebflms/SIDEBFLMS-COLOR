"""Cuanto espacio y cuanto tiempo va a costar la prueba, ANTES de hacerla.

Los costes unitarios no estan escritos aqui: se leen de `pruebas/coste_medido.json`,
que genera `pruebas/medir_coste.py` midiendo sobre material sintetico en esta
maquina. Si ese fichero no esta, la estimacion dice «no medido» en vez de
inventar.

LA CUENTA (la misma que esta escrita en el instructivo)
-------------------------------------------------------
Tiempo:
  escanear master  = fotogramas_master x (decodificar x MPx_master + proceso_master)
  escanear brutos  = fotogramas_brutos x decodificar x MPx_bruto
                   + segundos_brutos x proceso_bruto
  localizar        = puntos x localizar_por_punto
                   + planos x (afinar_por_plano + fotogramas_ventana x decodificar x MPx_bruto)
  extraer          = planos x (extraer_fijo x 2 + extraer_mpx x (MPx_bruto + MPx_master))
  T1               = planos x invertir_por_mpx x MPx_analisis
  T5               = planos x (planos - 1) x t5_por_mpx x MPx_analisis

Espacio en `pruebas/trabajo/` (el disco del ordenador):
  por plano = PNG 16 bits del bruto + PNG 16 bits del master + hoja de contacto
  PNG 16 bits: como mucho 6 bytes por pixel (3 canales x 2 bytes; es aritmetica,
  no medida). Lo medido en sintetico sale por debajo; con grano real, mas cerca
  del maximo. La estimacion usa **el maximo**.

"planos" se estima como el numero de brutos: no se sabe cuantos apareceran
hasta escanear. Si un bruto sale dos veces, hay un plano mas; si no sale, uno
menos.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .guarda import RAIZ_REPO

__all__ = ["RUTA_COSTE", "Estimacion", "estimar", "leer_coste"]

RUTA_COSTE: Path = RAIZ_REPO / "pruebas" / "coste_medido.json"

#: 3 canales x 2 bytes: el tope de un PNG de 16 bits sin comprimir. Aritmetica.
BYTES_POR_PIXEL_PNG16_MAX: float = 6.0


def leer_coste(ruta: Path = RUTA_COSTE) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@dataclass
class Estimacion:
    planos: int
    fotogramas_a_disco: int
    bytes_disco: float
    segundos: float | None  # None = no medido
    desglose_s: dict[str, float]
    memoria_bytes: float | None
    nota: str


def estimar(
    *,
    master: tuple[int, int, int],  # (ancho, alto, fotogramas)
    brutos: list[tuple[int, int, int, float]],  # (ancho, alto, fotogramas, segundos)
    ancho_analisis: int,
    paso: int,
    coste: dict | None,
) -> Estimacion:
    mw, mh, mn = master
    planos = len(brutos)
    mpx_m = mw * mh / 1e6
    fotos = 2 * planos
    bytes_disco = 0.0
    for bw, bh, _, _ in brutos:
        bytes_disco += BYTES_POR_PIXEL_PNG16_MAX * (bw * bh + mw * mh)
    hoja = float(coste.get("hoja_bytes_por_plano", 0.0)) if coste else 0.0
    bytes_disco += planos * hoja + 200_000  # informe .md + .json

    if not coste:
        return Estimacion(planos, fotos, bytes_disco, None, {}, None,
                          "no medido: falta pruebas/coste_medido.json "
                          "(se genera con .venv/bin/python pruebas/medir_coste.py)")

    dec = coste["decodificar_s_por_fotograma_mpx"]
    t: dict[str, float] = {}
    t["escanear master"] = mn * (dec * mpx_m + coste["escaneo_master_s_por_fotograma"])
    t["escanear brutos"] = sum(
        bn * dec * (bw * bh / 1e6) + bs * coste["escaneo_bruto_s_por_segundo"]
        for bw, bh, bn, bs in brutos
    )
    puntos = math.ceil(mn / max(paso, 1))
    mpx_b_medio = (sum(bw * bh for bw, bh, _, _ in brutos) / max(planos, 1)) / 1e6
    t["localizar"] = puntos * coste["localizar_s_por_punto"] + planos * (
        coste["afinar_s_por_plano_sin_leer"]
        + coste["fotogramas_leidos_por_plano"] * dec * mpx_b_medio
        + coste["lecturas_por_plano"] * coste["extraer_s_por_fotograma_fijo"]
    )
    t["extraer fotogramas"] = planos * (
        2 * coste["extraer_s_por_fotograma_fijo"]
        + coste["extraer_s_por_fotograma_mpx"] * (mpx_b_medio + mpx_m)
    )
    aw = max(min(ancho_analisis, mw // 2), 16)  # la misma regla que medir.preparar_pareja
    mpx_a = aw * (aw * mh / max(mw, 1)) / 1e6
    t["T1 (sacar el grado)"] = planos * coste["invertir_s_por_mpx"] * mpx_a
    t["T5 (aplicarlo a los demas)"] = (
        planos * max(planos - 1, 0) * coste["t5_s_por_pareja_mpx"] * mpx_a
    )

    memoria = mn * coste["memoria_bytes_por_fotograma_master"] + sum(
        bs * coste["memoria_bytes_por_segundo_bruto"] for _, _, _, bs in brutos
    )
    return Estimacion(
        planos, fotos, bytes_disco, sum(t.values()), t, memoria,
        f"costes medidos el {coste.get('fecha', '?')} en esta maquina sobre material sintetico "
        f"({coste.get('comando', '?')}). Con material de camara no se ha medido: un H.265 o un "
        f"4K decodifica a otra velocidad que el ProRes sintetico, y no se sabe hacia que lado",
    )
