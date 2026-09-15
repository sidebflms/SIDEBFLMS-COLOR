"""Emparejamiento de color de SIDEBFLMS COLOR: llevar un plano al de al lado.

QUE HACE ESTE MODULO
--------------------
Le das los pixeles de un plano y los de una referencia (los dos en
`WORKING_SPACE`) y te devuelve un `MatchResult`: un `CDL` que lleva el primero
al segundo, opcionalmente un `LUT3D` para lo que al CDL no le da, un `Confidence`
que dice cuanto fiarte y **una bandera que avisa si las dos escenas no eran
comparables siquiera**.

Las cuatro piezas, cada una en su archivo:

* `mkl.py`       — transporte lineal de Monge-Kantorovich, solucion cerrada.
                   Es la verdad de referencia: la unica aplicacion afin que
                   lleva una nube de color a la otra con coste minimo.
* `cdl_fit.py`   — el CDL (diez parametros, no lineal en `power`) que mas se
                   parece a ese transporte, por minimos cuadrados con limites.
* `confianza.py` — la nota, con su formula escrita y sus razones en castellano.
* `contenido.py` — el detector de "estas dos escenas no son comparables".
* `empareja.py`  — el camino completo.
* `camaras.py`   — igualar un grupo de camaras contra una de ellas (el T3).

Cada archivo empieza con un docstring largo que explica las decisiones; y las
cifras medidas estan en `core/matching/NOTAS.md`.

LO QUE HAY QUE SABER ANTES DE USARLO
------------------------------------
1. **Origen y referencia no tienen por que medir lo mismo.** Aqui no se empareja
   pixel con pixel, se emparejan distribuciones.
2. **Todo entra en `WORKING_SPACE`**, como manda el contrato 3.
3. `delta_e_before` / `delta_e_after` son "cuanto habia que mover el plano" y
   "cuanto le falta todavia", medidos contra el transporte ideal. Esta explicado
   con detalle en `empareja.py`.
4. Los NaN **se descartan** en vez de propagarse (`core.color` los propaga). Es
   la unica desviacion del modulo respecto a la politica general y esta
   justificada en el docstring de `empareja.py`: un `CDL` con un NaN no existe.
5. **Pasa las huellas si las tienes.** El desajuste de contenido lo decide la
   huella de `ClipAnalysis` cuando esta, y es cuatro veces mejor que los rasgos
   de pixeles (`contenido.py` trae la tabla). `emparejar_analisis` ya las pasa;
   con `emparejar` hay que dar `huellas=(a, b)` a mano.
"""

from __future__ import annotations

from core.matching.camaras import (
    ResultadoCamaras,
    delta_e_medio_entre_pares,
    igualar_camaras,
)
from core.matching.cdl_fit import (
    LIMITES_CDL,
    ajustar_cdl,
    aplicar_cdl_inverso,
)
from core.matching.confianza import PENA_DESAJUSTE, UMBRALES, puntuar_confianza
from core.matching.contenido import (
    UMBRAL_DESAJUSTE,
    UMBRAL_HUELLA,
    desajuste_de_contenido,
    rasgos_de_contenido,
)
from core.matching.empareja import (
    coeficiente_bhattacharyya,
    emparejar,
    emparejar_analisis,
    fraccion_extrapolada,
    solape_de_distribuciones,
)
from core.matching.mkl import (
    GANANCIA_MAX,
    TOL_RANGO,
    aplicar_mkl,
    ganancias,
    media_y_covarianza,
    transporte_mkl,
    transporte_mkl_de_estadistica,
)

__all__ = [
    # transporte
    "transporte_mkl",
    "transporte_mkl_de_estadistica",
    "aplicar_mkl",
    "ganancias",
    "media_y_covarianza",
    "TOL_RANGO",
    "GANANCIA_MAX",
    # CDL
    "ajustar_cdl",
    "aplicar_cdl_inverso",
    "LIMITES_CDL",
    # emparejamiento
    "emparejar",
    "emparejar_analisis",
    "coeficiente_bhattacharyya",
    "fraccion_extrapolada",
    "solape_de_distribuciones",
    # confianza
    "puntuar_confianza",
    "UMBRALES",
    "PENA_DESAJUSTE",
    # contenido
    "desajuste_de_contenido",
    "rasgos_de_contenido",
    "UMBRAL_DESAJUSTE",
    "UMBRAL_HUELLA",
    # camaras
    "igualar_camaras",
    "delta_e_medio_entre_pares",
    "ResultadoCamaras",
]
