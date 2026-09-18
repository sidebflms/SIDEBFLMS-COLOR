"""Referencia externa -> look: ¿sirve un UNICO par para extraer un grado
aplicable a un material que no es el suyo? Medido contra el codigo VIVO de
hoy (dia 9), a proposito -- no contra la copia congelada de T5.

EL ENCARGO Y POR QUE ES EL MISMO PROBLEMA QUE T5
-------------------------------------------------
T5 (dia 4, `tests/fuera_de_plano/test_t5_fuera_de_plano.py`, congelado contra
`v0.3.0`) midio si el grado extraido de UN plano del propio rodaje sirve para
OTRO plano del mismo rodaje: no sirve (ΔE maximo > 3.0 en 12 de 12 pares
A->B, CIFRAS.md §8). Una referencia EXTERNA -- un fotograma de una pelicula
que le gusta al colorista, no material de SU proyecto -- es un caso todavia
mas estrecho del mismo problema: no hay "varios planos del mismo trabajo" de
los que sacar mas cobertura o promediar la extraccion (eso si puede hacerlo
el flujo de hoy con material real del propio proyecto). Por definicion solo
hay UN PAR: la imagen de referencia ya con el look (no existe "la misma
referencia sin gradar", eso es justo lo que la tiene de externa). Asi que
esta medicion hereda el montaje de T5 pero:

* corre contra `core.reverse.invertir_grado` TAL CUAL esta hoy (no hay guardia
  de copia congelada: aqui se quiere medir el repo vivo, a proposito);
* usa UNA sola escena A por look (una referencia real es una imagen, no las
  seis paletas que barre T5), y `t5_material.paletas_b` para las B a varios
  niveles de disparidad de CONTENIDO.

NADA DE ESTE ARCHIVO TOCA `core/` NI `gui/`. Solo lee `t5_material.py` (sin
ninguna dependencia de la copia congelada, ver su propio docstring) y llama a
`core.reverse.invertir_grado` por la API publica, exactamente como T5.

QUE SE MIDE, PASO A PASO
-------------------------
1. Escena A (`M.PALETAS_A[1]`, "A2 interior calido" -- ver mas abajo por que
   esta y no otra) + look sintetico conocido (`M.tabla_look` + `M.colorear`)
   = par (A, A'). Ese par ES la referencia externa.
2. `invertir_grado(A, A')` extrae `(cdl, lut)` -- "extraer el look" de la
   referencia.
3. `M.paletas_b(paleta_de_A)` da las 6 escenas B, cada una con su propia
   ETIQUETA de disparidad de contenido (B0..B5) -- se usa esa etiqueta tal
   cual como "nivel", sin inventar tramos propios (el encargo pide
   reutilizarla).
4. Por cada B: `B' = M.colorear(B, tabla)` (la MISMA funcion del paso 1, o
   sea la verdad fundamental de "como deberia quedar B con ese look"), y
   `prediccion = lut.apply(cdl.apply(B))` con el grado extraido en el paso 2.
   Se compara `prediccion` contra `B'` con `M.delta_e2000` + `M.resumen`.
5. Se repite para los DOS looks sinteticos que ofrece `M.tabla_look`
   ("global" y "secundarias" -- son los unicos dos que existen; pasar
   cualquier otro `tipo` cae en la rama "global", asi que no hay un tercero
   que no sea inventarlo a mano, y el encargo pide reutilizar `tabla_look`
   sin inventar sobre el).
6. Mismo criterio que T5 (`UMBRAL_MAX = 3.0` sobre el ΔE maximo) para poder
   comparar honestamente.

POR QUE "A2 INTERIOR CALIDO" Y NO OTRA
----------------------------------------
`M.PALETAS_A` va de la mas pobre en color (A1) a la mas rica (A6). Elegir la
mas favorable o la mas dura a mano sesgaria la medida. `M.PALETAS_A[1]`
("A2 interior calido") es la que T5 calibro contra el ~0.46% de cobertura del
plano real del propio repo (ver `MEDICION-T5.md`): es la unica de las seis
con una referencia externa de "esto se parece a un plano de verdad", asi que
es la eleccion menos arbitraria para representar "un fotograma cualquiera".

QUE NO ES ESTE ARCHIVO
-----------------------
No es una prueba de que algo "deberia" pasar o fallar: como T5, mide y
reporta (`test_referencia_externa_barrido_completo` no afirma nada sobre el
ΔE, solo lo imprime). Las unicas aserciones son de plausibilidad del propio
material (que el look sintetico no sea la identidad ni un disparate) y de
que el barrido produjo el numero de filas esperado -- guardias de que la
medida es valida, no del resultado que arroja.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path

import numpy as np
import pytest

_T5_DIR = Path(__file__).resolve().parent / "fuera_de_plano"
if str(_T5_DIR) not in sys.path:
    sys.path.insert(0, str(_T5_DIR))

import t5_material as M  # noqa: E402

from core.reverse import invertir_grado  # noqa: E402

LOOKS: tuple[str, ...] = ("global", "secundarias")
SEMILLA_A = 9101
SEMILLA_B = 9201
UMBRAL_MAX = 3.0  # mismo criterio de "falla" que T5 (CIFRAS.md §8)

#: La escena A -- la referencia externa -- es UNA sola paleta. Ver docstring.
PALETA_A = M.PALETAS_A[1]


def _informe(etiqueta: str, **cifras) -> None:
    partes = [f"{k}={v:.6g}" if isinstance(v, float) else f"{k}={v}" for k, v in cifras.items()]
    print(f"[REF-EXT {etiqueta}] " + "  ".join(partes))


def _predecir(resultado, x: np.ndarray) -> np.ndarray:
    """lut.apply(cdl.apply(x)) -- exactamente lo que haria el colorista con el grado extraido."""
    return resultado.lut.apply(resultado.cdl.apply(np.asarray(x, dtype=np.float64)))


@functools.cache
def barrido() -> tuple[list[dict], list[dict]]:
    """Para cada uno de los 2 looks: extrae de (A, A') y aplica a las 6 B de `paletas_b`."""
    filas: list[dict] = []
    refs: list[dict] = []
    a = M.escena_trabajo(PALETA_A, SEMILLA_A)

    for look in LOOKS:
        tabla = M.tabla_look(look)
        a_prima = M.colorear(a, tabla)
        assert np.isfinite(a).all() and np.isfinite(a_prima).all(), look

        resultado = invertir_grado(a, a_prima)
        fuerza = M.resumen(M.delta_e2000(a, a_prima))
        # A->A: si esto ya fallara, ni vale la pena mirar B (T5 ya midio que
        # A->A tambien puede fallar en escenas ricas: CIFRAS.md §8).
        de_aa = M.resumen(M.delta_e2000(a_prima, _predecir(resultado, a)))
        refs.append({
            "look": look,
            "de_aa_medio": de_aa["medio"],
            "de_aa_p95": de_aa["p95"],
            "de_aa_max": de_aa["max"],
            "cobertura_del_cubo": resultado.coverage.coverage_fraction(),
            "fuerza_grado_medio": fuerza["medio"],
        })

        for jb, (etiqueta, pal_b) in enumerate(M.paletas_b(PALETA_A)):
            b = M.escena_trabajo(pal_b, SEMILLA_B + jb)
            b_prima = M.colorear(b, tabla)
            assert np.isfinite(b).all() and np.isfinite(b_prima).all(), (look, etiqueta)

            prediccion = _predecir(resultado, b)
            de = M.delta_e2000(b_prima, prediccion)
            resumen = M.resumen(de)
            filas.append({
                "look": look,
                # La etiqueta la da `paletas_b`, tal cual (nada de tramos propios).
                "nivel": etiqueta,
                "solape_hist": M.solape_histogramas(a, b),
                "de_medio": resumen["medio"],
                "de_p95": resumen["p95"],
                "de_max": resumen["max"],
                "frac_mayor_3": resumen["frac_mayor_3"],
            })
    return filas, refs


# ---------------------------------------------------------------------------
# El material es plausible (mismo criterio que T5)
# ---------------------------------------------------------------------------


def test_referencia_externa_el_grado_conocido_es_plausible():
    """Ni identidad ni disparate, y mi `M.colorear` coincide con `lut.apply(cdl.apply())`
    del repo: si no coincidiera, B' y la prediccion diferirian por la aplicacion
    y no por lo que extrae `invertir_grado`."""
    from core.contracts import CDL, LUT3D
    from core.io import qc_lut

    identidad = np.stack(np.meshgrid(*[np.linspace(0, 1, M.TAM_LUT)] * 3, indexing="ij"), -1)
    cdl = CDL(M.CDL_SLOPE, M.CDL_OFFSET, M.CDL_POWER, M.CDL_SAT)
    a = M.escena_trabajo(PALETA_A, SEMILLA_A)
    for look in LOOKS:
        tabla = M.tabla_look(look)
        lut = LUT3D(table=tabla.astype(np.float32))
        qc = qc_lut(lut)
        dif_aplicacion = float(np.abs(M.colorear(a, tabla) - lut.apply(cdl.apply(a))).max())
        _informe(
            f"material {look}",
            qc_ok=qc.ok,
            codigos=",".join(qc.codigos()) or "-",
            max_dist_identidad=float(np.abs(tabla - identidad).max()),
            dif_mi_aplicacion_vs_repo=dif_aplicacion,
        )
        assert qc.ok, qc.codigos()
        assert float(np.abs(tabla - identidad).max()) > 0.05
        assert dif_aplicacion < 1e-5


# ---------------------------------------------------------------------------
# La medida
# ---------------------------------------------------------------------------


def test_referencia_externa_barrido_completo():
    """Imprime el barrido entero: por par (look, B), por nivel y por look.

    No afirma nada sobre si el ΔE sube o baja de 3.0 -- eso se decide y se
    escribe en BITACORA.md/CIFRAS.md, no en un `assert`. Las unicas
    aserciones de aqui son de que la medida es valida (numero de filas,
    valores finitos), no del resultado.
    """
    filas, refs = barrido()

    assert len(refs) == len(LOOKS)
    assert len(filas) == len(LOOKS) * 6  # 6 escenas B por look (`paletas_b`)

    print("\n[REF-EXT] ===== referencia A->A (extraigo de A, compruebo sobre A) =====")
    for r in refs:
        _informe(
            f"ref {r['look']}",
            cobertura_del_cubo=r["cobertura_del_cubo"],
            fuerza_grado_medio=r["fuerza_grado_medio"],
            de_aa_medio=r["de_aa_medio"], de_aa_p95=r["de_aa_p95"], de_aa_max=r["de_aa_max"],
        )
        assert np.isfinite(r["de_aa_max"])

    print("\n[REF-EXT] ===== A->B (extraigo de la referencia A, aplico a B, comparo con B') =====")
    for f in filas:
        _informe(
            f"AB {f['look']} | {f['nivel']}",
            solape_hist=f["solape_hist"],
            de_medio=f["de_medio"], de_p95=f["de_p95"], de_max=f["de_max"],
            frac_px_mayor_3=f["frac_mayor_3"],
            bajo_umbral=f["de_max"] < UMBRAL_MAX,
        )
        assert np.isfinite(f["de_max"])

    print("\n[REF-EXT] ===== por nivel de disparidad (etiqueta de `paletas_b`, ambos looks) =====")
    niveles = list(dict.fromkeys(f["nivel"] for f in filas))  # orden de aparicion, sin repetir
    for nivel in niveles:
        sel = [f for f in filas if f["nivel"] == nivel]
        _informe(
            f"nivel {nivel}",
            puntos=len(sel),
            solape_min=min(f["solape_hist"] for f in sel),
            solape_max=max(f["solape_hist"] for f in sel),
            mediana_max=float(np.median([f["de_max"] for f in sel])),
            peor_max=max(f["de_max"] for f in sel),
            mejor_max=min(f["de_max"] for f in sel),
            puntos_bajo_3=sum(f["de_max"] < UMBRAL_MAX for f in sel),
            de_puntos=len(sel),
        )

    print("\n[REF-EXT] ===== por look (las 6 B) =====")
    for look in LOOKS:
        sel = [f for f in filas if f["look"] == look]
        _informe(
            f"look {look}",
            puntos=len(sel),
            mediana_max=float(np.median([f["de_max"] for f in sel])),
            peor_max=max(f["de_max"] for f in sel),
            mejor_max=min(f["de_max"] for f in sel),
            puntos_bajo_3=f"{sum(f['de_max'] < UMBRAL_MAX for f in sel)}/{len(sel)}",
        )

    total_bajo_3 = sum(f["de_max"] < UMBRAL_MAX for f in filas)
    _informe(
        "resumen",
        puntos_bajo_3_de_umbral=f"{total_bajo_3}/{len(filas)}",
        peor_max_de_todos=max(f["de_max"] for f in filas),
        mejor_max_de_todos=min(f["de_max"] for f in filas),
        # Para comparar de un vistazo con el titular de T5 (CIFRAS.md §8):
        # "3.593 - 5.921; 0 de 12 bajo 3.0".
        referencia_T5="3.593-5.921 max, 0/12 bajo 3.0 (v0.3.0, dia 4)",
    )


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
