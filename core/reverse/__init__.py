"""`core.reverse` — ingenieria inversa de un grado de color.

LA PREGUNTA
-----------
"Aqui esta el plano como salio de camara, y aqui esta el mismo plano ya
coloreado por otro. Dame el grado." Eso es lo que hace este modulo, y es la
funcion estrella de SIDEBFLMS COLOR: no hay nada que comprar que lo haga.

LA RESPUESTA, EN DOS CAPAS Y EN ESTE ORDEN
------------------------------------------
    coloreado ~= LUT( CDL( original ) )

**Primero el CDL, luego el LUT sobre el resultado.** El mismo orden que
`MatchResult` del agente C. El CDL son diez numeros que se leen, se entienden y
se retocan a mano, y que van al nodo 2 de Resolve por parametro. El LUT recoge
lo que el CDL no explica y va al nodo 3 como `.cube`.

Y LA PREGUNTA QUE DE VERDAD IMPORTA
-----------------------------------
No es "dame el grado": es **"¿cuanto de este grado me puedo llevar en un
`.cube`?"**. Una vineta, un power window o una secundaria dependen de DONDE esta
el pixel, y un LUT solo sabe de que COLOR es. `ReverseDiagnosis` contesta eso:
`lut_reproducible` (0..1), `is_pure_lut`, un mapa del residuo espacial y los
`Hotspot` con su caja y su etiqueta.

LA API
------
    invertir_grado(original, coloreado, ...) -> ReverseResult   # el camino entero
    alinear(original, coloreado)                                # por si vienen torcidos
    acumular_correspondencias(original, coloreado, tam_lut)     # pares -> rejilla
    rellenar_huecos(acumulado, cobertura) -> LUT3D              # inventar lo que falta
    diagnosticar(original, coloreado, cdl, lut, cobertura)      # el veredicto

LO QUE HAY QUE SABER ANTES DE USARLO
------------------------------------
1. Las dos imagenes entran en `WORKING_SPACE` y son **el mismo plano**. Si no lo
   son, el modulo lo dice (`desajuste_de_contenido` del agente C) y hunde la
   confianza, pero no se niega a responder: a veces el que pregunta sabe algo
   que el programa no sabe.
2. El dominio de los LUT que salen de aqui es **siempre 0..1**. Lo que se sale
   se sujeta al borde, igual que hace Resolve, y se cuenta en las notas.
3. **Un plano no cubre ni de lejos las 35.937 celdas de un cubo de 33.** Las que
   no tiene hay que inventarlas, y `CoverageMap` dice exactamente cuales:
   **celda inventada == `coverage.counts == 0`**, por construccion y no por
   buena voluntad. `covered_mask()` (`counts >= min_samples`) es mas estricta y
   contesta otra pregunta: no "¿hay dato?" sino "¿hay dato suficiente para
   fiarse?".
4. Los NaN se **descartan** (como hace `core.matching`), no se propagan, y la
   fraccion descartada sale en las notas y en la confianza. Un grado con un NaN
   dentro no es un grado.

Las decisiones, los limites del detector de vinetas y las cifras medidas de los
tests T1 y T2 estan en `core/reverse/NOTAS.md`.
"""

from __future__ import annotations

from core.reverse.acumulacion import (
    DOMINIO_MAX,
    DOMINIO_MIN,
    PESO_DE_MUESTRA,
    acumular_correspondencias,
    fraccion_fuera_de_dominio,
    pesos_trilineales,
)
from core.reverse.alineado import (
    MAX_DESPLAZAMIENTO_PX,
    UMBRAL_CORRELACION_FIABLE,
    alinear,
    correlacion_de_gradientes,
    redimensionar,
)
from core.reverse.diagnostico import (
    AREA_MINIMA_HOTSPOT,
    UMBRAL_DE_HOTSPOT,
    UMBRAL_DE_PURO,
    UMBRAL_MONOTONIA_RADIAL,
    UMBRAL_R2_LINEAL,
    UMBRAL_R2_RADIAL,
    UMBRAL_REPRODUCIBLE_PURO,
    diagnosticar,
    mapa_de_residuo,
)
from core.reverse.invertir import (
    ITERACIONES_REFINADO,
    MAX_PIXELES_CDL,
    MUESTRAS_MINIMAS_CDL,
    invertir_grado,
)
from core.reverse.relleno import (
    BARRIDOS_SUAVIZADO,
    LAMBDA_SUAVIDAD,
    base_afin,
    celdas_con_dato,
    extender_suave,
    media_de_vecinos,
    proyectar_monotona,
    rejilla_de_entradas,
    rellenar_huecos,
)

__all__ = [
    # el camino entero
    "invertir_grado",
    # las piezas, por si alguien quiere otra cosa
    "alinear",
    "acumular_correspondencias",
    "rellenar_huecos",
    "diagnosticar",
    "mapa_de_residuo",
    # utilidades
    "correlacion_de_gradientes",
    "redimensionar",
    "pesos_trilineales",
    "fraccion_fuera_de_dominio",
    "base_afin",
    "celdas_con_dato",
    "extender_suave",
    "media_de_vecinos",
    "proyectar_monotona",
    "rejilla_de_entradas",
    # constantes documentadas
    "DOMINIO_MIN",
    "DOMINIO_MAX",
    "MAX_DESPLAZAMIENTO_PX",
    "UMBRAL_CORRELACION_FIABLE",
    "BARRIDOS_SUAVIZADO",
    "LAMBDA_SUAVIDAD",
    "PESO_DE_MUESTRA",
    "ITERACIONES_REFINADO",
    "MAX_PIXELES_CDL",
    "MUESTRAS_MINIMAS_CDL",
    "AREA_MINIMA_HOTSPOT",
    "UMBRAL_DE_HOTSPOT",
    "UMBRAL_DE_PURO",
    "UMBRAL_REPRODUCIBLE_PURO",
    "UMBRAL_R2_RADIAL",
    "UMBRAL_MONOTONIA_RADIAL",
    "UMBRAL_R2_LINEAL",
]
