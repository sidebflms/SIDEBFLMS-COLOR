"""UMBRALES DE DECISIÓN de SIDEBFLMS COLOR. Un criterio, un sitio.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
El día 2 se encontró que `gui/reverse_puente.py` tenía **su propia definición**,
más floja, de «esto es un LUT puro»: `reproducible > 0.92` a secas, frente al
0.95 **y** percentil 95 por debajo de 1.0 ΔE2000 que pide el núcleo. Y la GUI
caía a ese criterio ante cualquier excepción del núcleo, o sea que un fallo
degradaba **en silencio** a la versión permisiva para decir la frase más
peligrosa de la aplicación.

Eso no es un bug suelto: es una clase de bug. Aparece siempre que un criterio de
decisión se puede escribir dos veces. Este archivo existe para que no se pueda.

QUÉ ENTRA AQUÍ Y QUÉ NO
-----------------------
Aquí entra un número si cumple **una** de estas tres:

1. **Está duplicado**: el mismo criterio definido en dos sitios.
2. **Es un literal suelto** dentro de una decisión, sin nombre, en medio del
   código.
3. **Determina un veredicto que el usuario ve**: alta/media/baja, «es un LUT
   puro», «esto es banding», «estas dos escenas no son comparables», «esta celda
   tiene datos». Si el número decide lo que Mario lee en pantalla, vive aquí.

**Lo que no cumpla ninguna se queda en su módulo.** `SEMILLA_MUESTREO`,
`TIMEOUT_S`, `MAX_PIXELES_ESTADISTICA`, `REJILLA_LUMA`, `BINS_ORIENTACION`,
`MAX_BYTES_CUBE`, `SIGMA_RADIAL`… son **parámetros de implementación**: sólo le
importan a su módulo, y traerlos aquí construiría un módulo-Dios que acopla todo
con todo. Eso sería una regresión, no un arreglo. Hay ~115 constantes con nombre
en `core/`; la mayoría están bien donde están.

LA UNIDAD ES PARTE DEL NÚMERO
-----------------------------
Cada constante lleva su unidad escrita. No es burocracia: un `1.0` que es
ΔE2000 y un `0.95` que es una fracción no son la misma clase de número, y
confundirlos es exactamente cómo aparece un criterio más flojo en otro módulo.

DÓNDE NO SE SABE, SE DICE
-------------------------
Varios de estos valores no tienen justificación documentada en ningún sitio: ni
en el código, ni en los commits, ni en la bitácora, ni en los `NOTAS.md`. Están
marcados **«NO SE SABE POR QUÉ VALE ESTO»**. Un «no se sabe» es información; una
justificación plausible inventada es una mentira que alguien se creerá.

REGLA DE DEPENDENCIAS
---------------------
**Este módulo no importa NADA de `core/`.** Ni `contracts`, ni `paths`, ni
numpy. Así `core/contracts.py` puede importarlo sin ciclos, y así no hay forma de
que un umbral dependa de otra cosa que no sea sí mismo.

CÓMO SE MANTIENE
----------------
`tests/test_umbrales_literales.py` recorre el AST de `core/` y se pone rojo si
aparece una comparación contra un literal numérico no trivial fuera de aquí.
Tiene una lista de excepciones explícita y corta; si esa lista crece sin freno,
el test dejó de servir.
"""

from __future__ import annotations

__all__ = [
    "AREA_MINIMA_HOTSPOT",
    "CONFIDENCE_ALTA",
    "CONFIDENCE_MEDIA",
    "DELTA_E_INDISTINGUIBLE",
    "FRACCION_DE_PICO",
    "FRACCION_PIEL_MINIMA",
    "LUT_SIZE_DEFAULT",
    "MUESTRAS_MINIMAS_CDL",
    "MUESTRAS_MINIMAS_CELDA",
    "PENA_DESAJUSTE",
    "PIXELES_PIEL_MINIMOS",
    "RAMPAS_DE_CONFIANZA",
    "SALTO_MINIMO_BANDING",
    "SUELO_GANANCIA_LOCAL",
    "TOL_GAMUT",
    "TOL_MONOTONIA",
    "UMBRAL_BANDING",
    "UMBRAL_COBERTURA_BAJA",
    "UMBRAL_CORRELACION_FIABLE",
    "UMBRAL_CROMA_EXPLICABLE",
    "UMBRAL_DESAJUSTE",
    "UMBRAL_DE_HOTSPOT",
    "UMBRAL_DE_PURO",
    "UMBRAL_FUERA_DE_DOMINIO_AVISO",
    "UMBRAL_HUELLA",
    "UMBRAL_MONOTONIA_RADIAL",
    "UMBRAL_MOVIMIENTO_NULO",
    "UMBRAL_NEUTRA_TOTAL",
    "UMBRAL_PERFIL_EXPLICABLE",
    "UMBRAL_R2_LINEAL",
    "UMBRAL_R2_RADIAL",
    "UMBRAL_RECORRIDO_GANANCIA",
    "UMBRAL_RECORRIDO_LINEAL",
    "UMBRAL_RECORRIDO_LUT_PLANO",
    "UMBRAL_REPRODUCIBLE_PURO",
    "UMBRAL_SOMBRAS",
    "UMBRAL_SUBNOTA_EXPLICABLE",
    "UMBRAL_TEXTURA",
]


# ===========================================================================
# 1. La base perceptual: el único ΔE2000 que decide cosas
# ===========================================================================

#: **Unidad: ΔE2000.** Umbral clásico de «dos colores que, puestos uno al lado
#: del otro, no se distinguen». Es la unidad de medida de casi todo lo que esta
#: app decide sobre color, y **estaba escrito tres veces**: en
#: `reverse.diagnostico.UMBRAL_DE_HOTSPOT`, en `reverse.diagnostico.UMBRAL_DE_PURO`
#: y en el extremo bueno de la rampa `residuo_de` de `matching.confianza`, los
#: tres con el mismo comentario dicho con otras palabras. Ahora se escribe una vez.
DELTA_E_INDISTINGUIBLE: float = 1.0


# ===========================================================================
# 2. Confianza: alta / media / baja
#    Es el veredicto más visible de la app: sale en la lista de clips.
# ===========================================================================

#: **Unidad: fracción 0..1** sobre `Confidence.score`. A partir de aquí, «alta».
#: Vive aquí y no en `core/contracts.py` por la razón de este archivo: es el
#: criterio que `CONTRATOS.md` ya declaraba único («no redefinas umbrales en tu
#: módulo») y lo único que faltaba era que estuviera donde se pueda importar sin
#: arrastrar los contratos enteros.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** No hay ninguna medida detrás del 0.75 ni en
#: el código, ni en los commits, ni en `BITACORA.md`, ni en los `NOTAS.md`.
CONFIDENCE_ALTA: float = 0.75

#: **Unidad: fracción 0..1.** Por debajo de aquí, «baja». Entre las dos, «media».
#:
#: **NO SE SABE POR QUÉ VALE ESTO**, igual que `CONFIDENCE_ALTA`.
CONFIDENCE_MEDIA: float = 0.45

#: **Unidad: fracción 0..1 (multiplicador).** Cuánto se multiplica la nota de
#: confianza cuando el detector de contenido dice que las dos escenas no son
#: comparables. Multiplica a propósito y no resta: un desajuste de contenido no
#: es «una pega más», es que el número de abajo no significa lo que parece.
#: Con 0.35, una nota perfecta baja a 0.35 = «baja», que es lo que hay que
#: enseñar. Ver `core/matching/NOTAS.md` §3.
PENA_DESAJUSTE: float = 0.35

#: **Unidad: fracción 0..1** sobre una subnota. Por debajo de esto, la subnota
#: se convierte en una **frase en castellano** dentro de `Confidence.reasons`,
#: que es texto que Mario lee. Era un literal suelto en
#: `core/matching/confianza.py`. 0.85 es «casi perfecto pero no del todo»: por
#: encima no hay nada que explicar.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** No hay medida detrás del 0.85.
UMBRAL_SUBNOTA_EXPLICABLE: float = 0.85

#: Los dos extremos de cada rampa de la nota de confianza: `(valor con subnota
#: 1, valor con subnota 0)`.
#:
#: **Unidad: una distinta por clave**, y por eso va escrita dentro, al lado de
#: cada rampa: aquí conviven píxeles, fracciones, ΔE2000 y un número de
#: condición, y son justo la clase de números que no hay que confundir. La
#: nota final es `sqrt(min(subnotas) * media_geometrica(subnotas))` por
#: `PENA_DESAJUSTE`; la fórmula entera está en `core/matching/NOTAS.md` §3.
RAMPAS_DE_CONFIANZA: dict[str, tuple[float, float]] = {
    # Unidad: número de píxeles; la rampa va en log10. 24 píxeles no es nada
    # para diez parámetros; 20.000 ya es de sobra.
    "n_muestras": (20000.0, 24.0),
    # Unidad: fracción 0..1 de solape de los histogramas reales DESPUÉS del
    # transporte. Medido: el mismo plano a otra exposición da 0.99, el mismo
    # decorado con otra persona 0.78-0.92, medio fotograma 0.88, y un exterior
    # contra un retrato 0.45. El corte va entre medias.
    "solape": (0.90, 0.40),
    # Unidad: número de condición de la covarianza del origen (adimensional),
    # rampa en log10. Medido sobre el material del generador: un retrato de
    # estudio da 1.1e3, un exterior 1.3e3, una carta de color 77 y un campo de
    # ruido 5. O sea que 1e3 NO es una nube degenerada, es una escena normal. El
    # corte está donde deja de haber información: un degradado de un solo tono
    # da 1.1e10 y una rampa de gris 1e299.
    "condicion": (1e5, 1e10),
    # Unidad: ΔE2000 medio del residuo del ajuste. El extremo bueno es
    # `DELTA_E_INDISTINGUIBLE`; 8.0 es un error que se ve desde la puerta.
    "residuo_de": (DELTA_E_INDISTINGUIBLE, 8.0),
    # Unidad: fracción 0..1 de la referencia que cae fuera del rango observado
    # en el origen.
    "extrapolacion": (0.02, 0.40),
    # Unidad: factor de estirado (adimensional) de la matriz de transporte.
    # El 100.0 coincide con `core.matching.mkl.GANANCIA_MAX`, que es el recorte
    # duro. Se dejan separados a propósito: uno puntúa, el otro recorta.
    "ganancia": (4.0, 100.0),
    # Unidad: fracción 0..1 de píxeles que venían con NaN o infinito.
    "fraccion_no_finita": (0.0, 0.25),
}


# ===========================================================================
# 3. «Esto es un LUT puro» — la frase más peligrosa de la aplicación
#    Decir «esto cabe en un .cube» cuando no cabe manda a Mario a entregar un
#    LUT que no reproduce el grado y a enterarse delante de un cliente. El
#    fallo, donde haya que elegir, va hacia el otro lado.
# ===========================================================================

#: **Unidad: fracción 0..1** de `lut_reproducible` («de todo lo que este grado
#: mueve el color, me llevo este tanto por uno»). Una de las **tres** condiciones
#: de `is_pure_lut`, junto con `UMBRAL_DE_PURO` y «cero hotspots».
#:
#: **Éste es el número del hallazgo del día 2**: `gui/reverse_puente.py` usaba
#: 0.92 a secas en su lugar, y además sin la condición del percentil 95.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Lo dice ya `core/reverse/NOTAS.md` §9: de
#: dónde sale el 0.95 no lo dice ni el código, ni el commit, ni la bitácora. No
#: se ha tocado.
UMBRAL_REPRODUCIBLE_PURO: float = 0.95

#: **Unidad: ΔE2000**, aplicado al **percentil 95** del residuo. Segunda
#: condición de `is_pure_lut`: «el 95% del fotograma cae por debajo de lo que el
#: ojo distingue».
UMBRAL_DE_PURO: float = DELTA_E_INDISTINGUIBLE

#: **Unidad: ΔE2000.** Por debajo de esto no hay nada que señalar como hotspot:
#: es residuo que no se ve.
UMBRAL_DE_HOTSPOT: float = DELTA_E_INDISTINGUIBLE

#: **Unidad: ΔE2000 medio** entre original y coloreado. Por debajo de esto se
#: entiende que «el grado no mueve el color»: no hay fracción que calcular, y el
#: diagnóstico entra por la rama «esto no es un grado, es el mismo plano», que
#: escribe esa frase tal cual en pantalla y fija `lut_reproducible` a 1.0 o a
#: 0.0 de golpe. Era un literal `0.05` suelto, escrito **dos veces seguidas** en
#: la misma condición de `core/reverse/diagnostico.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Lo dice `core/reverse/NOTAS.md` §9: no hay
#: ninguna medida detrás. Y tiene un efecto lateral conocido y anotado: con los
#: dos planos idénticos, el residuo del relleno (0.3122) supera este mismo 0.05
#: y `is_pure_lut` sale `False`, que es confuso.
UMBRAL_MOVIMIENTO_NULO: float = 0.05

#: **Unidad: número de píxeles válidos.** Por debajo de esto no se ajusta CDL:
#: se devuelve la identidad y se dice en las notas. Diez parámetros con cuatro
#: píxeles es ruido con forma de grado.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** `core/reverse/NOTAS.md` §9 lo da como razón
#: cualitativa sin ningún número detrás.
MUESTRAS_MINIMAS_CDL: int = 64

#: **Unidad: fracción 0..1** de píxeles que, después del CDL, se salen del
#: dominio 0..1 del LUT. Por encima de esto se avisa en las notas de que ahí el
#: LUT sujeta al borde y el color no se transforma. Era un literal `0.001`
#: suelto en `core/reverse/invertir.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Es un 0.1% de los píxeles; no hay medida
#: detrás.
UMBRAL_FUERA_DE_DOMINIO_AVISO: float = 0.001


# ===========================================================================
# 4. «Esta celda tiene datos» — el mapa de cobertura
#    Es lo que la GUI pinta a cuadros, así que decide lo que Mario ve.
# ===========================================================================

#: **Unidad: número de píxeles reales** apoyados en una celda del cubo. A partir
#: de aquí `CoverageMap.covered_mask()` dice que la celda tiene dato
#: **suficiente para fiarse** (que es otra pregunta, y más estricta, que
#: `counts > 0` = «hay algún dato»).
#:
#: **Estaba escrito tres veces**: como valor por defecto de
#: `CoverageMap.min_samples` en `core/contracts.py`, y como valor por defecto del
#: parámetro `min_muestras` en `core.reverse.acumulacion.acumular_correspondencias`
#: y en `core.reverse.invertir.invertir_grado`. Los dos de `core/reverse` ya
#: apuntan aquí; **el de `core/contracts.py` sigue siendo una segunda escritura
#: del mismo 4**, y ese archivo es del orquestador, así que no se ha tocado. Lo
#: que sí hay es un test que salta si los dos dejan de coincidir
#: (`tests/test_umbrales.py::test_el_cuatro_de_la_cobertura_sigue_cuadrando_con_el_de_los_contratos`).
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** No hay medida detrás del 4.
MUESTRAS_MINIMAS_CELDA: int = 4

#: **Unidad: fracción 0..1** de celdas del cubo con dato real. Por debajo de
#: esto se avisa —en las notas del diagnóstico **y** en las razones de la
#: confianza— de que casi todo el LUT está extrapolado y de que parte del
#: residuo puede ser falta de datos y no algo espacial.
#:
#: **Estaba escrito dos veces**, como literal `0.005` suelto: en
#: `core/reverse/diagnostico.py` y en `core/reverse/invertir.py`. Es el mismo
#: criterio, produce dos frases distintas, y nadie garantizaba que siguieran
#: coincidiendo. Es exactamente la forma del bug de `gui/reverse_puente.py`.
#:
#: Para hacerse una idea de la escala: un solo plano cubre **165 celdas de
#: 35.937**, o sea el 0.46%, así que este umbral salta prácticamente siempre que
#: se invierte un grado a partir de un fotograma. Ver `core/reverse/NOTAS.md` §0.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** No hay medida detrás del 0.5%.
UMBRAL_COBERTURA_BAJA: float = 0.005


# ===========================================================================
# 5. Las cuatro formas que no caben en un LUT
#    viñeta / degradado / textura / zona local. Son las palabras que Mario lee
#    en el diagnóstico, así que los números que las deciden viven aquí.
#    El porqué de cada uno, medido, está en `core/reverse/NOTAS.md` §6.
# ===========================================================================

#: **Unidad: R² (fracción 0..1)** del perfil radial sobre el **campo de
#: ganancia** (no sobre el ΔE2000). Cuánta varianza tiene que explicar la caída
#: radial para llamarlo viñeta. Medido: la viñeta más floja probada da 0.83 y una
#: ventana sola 0.034, o sea un factor 25. Se deja en 0.30 y no más arriba a
#: propósito: el falso positivo es el lado seguro.
#:
#: **Ojo con el mismo número sobre otro campo**: este 0.30 aplicado al ΔE2000
#: era la puerta que se quedaba a un 4% de abrirse y hacía ciego al detector.
UMBRAL_R2_RADIAL: float = 0.30

#: **Unidad: |Pearson| (0..1)** del perfil radial contra el radio. En valor
#: absoluto a propósito: una viñeta que **aclara** hacia fuera es igual de
#: imposible de meter en un LUT que una que oscurece, y el signo se reporta
#: aparte («oscurece» / «aclara»).
UMBRAL_MONOTONIA_RADIAL: float = 0.55

#: **Unidad: logaritmo natural de ganancia** (0.12 ≈ 0.17 paradas de luz entre
#: el centro y el borde). Recorrido mínimo del perfil radial. Medido: «nada
#: espacial» da 0.000 y «grano fuerte» 0.004; la viñeta más floja probada (0.35)
#: da 0.27.
UMBRAL_RECORRIDO_GANANCIA: float = 0.12

#: **Unidad: R² (fracción 0..1)** de un plano inclinado sobre lo que queda del
#: campo de ganancia tras restarle el modelo radial. Cuánta varianza tiene que
#: explicar para llamarlo degradado. Es la puerta más fácil de disparar sin
#: querer —casi cualquier residuo tiene algo de inclinación— y por eso se pide
#: más que en la radial.
UMBRAL_R2_LINEAL: float = 0.50

#: **Unidad: logaritmo natural de ganancia.** Recorrido mínimo de ese plano
#: inclinado de un lado a otro del fotograma.
UMBRAL_RECORRIDO_LINEAL: float = 0.10

#: **Unidad: ΔE2000 (desviación típica)** del residuo de **alta** frecuencia.
#: Por encima de esto se declara textura: grano, enfoque, reducción de ruido,
#: halación. Medido: sin nada 0.11, compresión h264 fuerte 0.5-0.9, viñeta o
#: ventana 1.3-1.7 (que es el error del ajuste del LUT en los bordes del
#: contenido, no textura del material) y grano de verdad 3.83. El margen real es
#: 3.83 contra 1.44, un factor 2.7, así que este umbral no puede bajar de ~2.
UMBRAL_TEXTURA: float = 2.5

#: **Unidad: norma del residuo de ganancia por canal** (adimensional, ≈ fracción
#: de ganancia). Suelo absoluto del umbral de zona local. 0.08 es un 8% de
#: ganancia local, algo más de un octavo de parada. Es lo que impide que el
#: contorno se dibuje sobre ruido cuando no hay pico.
#:
#: **Las dos fuentes de este módulo no dicen lo mismo y no lo arreglo yo**: el
#: comentario original de `core/reverse/diagnostico.py` daba el pico del grano
#: más fuerte probado en **0.045**, y `core/reverse/NOTAS.md` §6.3 lo da en
#: **0.0135**. Las dos coinciden en el resto: «nada espacial» 0.0006 y la
#: ventana 0.5945. No he medido ninguna de las dos, así que las dejo dichas con
#: su procedencia en vez de elegir una.
SUELO_GANANCIA_LOCAL: float = 0.08

#: **Unidad: fracción 0..1** de la altura del pico sobre la mediana. El contorno
#: de la zona local se traza aquí. Es un criterio **sin escala**: una ventana de
#: +15% se recorta igual de bien que una de +60%, y no hay ningún número
#: calibrado contra un caso concreto.
FRACCION_DE_PICO: float = 0.40

#: **Unidad: fracción 0..1 del área del fotograma.** Área mínima de una
#: componente conexa para que cuente como zona. El 0.2% del cuadro.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Hay razón cualitativa («por debajo es
#: grano, no una zona»), pero ninguna medida. Lo dice `core/reverse/NOTAS.md` §9.
AREA_MINIMA_HOTSPOT: float = 0.002


# ===========================================================================
# 6. «Estas dos escenas no son comparables»
#    Pone `MatchResult.content_mismatch`, que la GUI tiene que enseñar aunque
#    la confianza salga alta.
# ===========================================================================

#: **Unidad: distancia de huella, `1 - parecido`** (0..1). Se exige un parecido
#: de al menos 0.50. Punto medio del hueco **medido** con la huella real del
#: agente B: el peor par comparable da 0.756 de parecido y el mejor par no
#: comparable 0.219, así que el umbral deja 0.256 de margen por arriba y 0.281
#: por abajo. Tabla completa en `core/matching/NOTAS.md` §4.3.
UMBRAL_HUELLA: float = 0.50

#: **Unidad: suma de dos distancias adimensionales** (`perfil` + `croma`, con
#: peso 1 cada una). Es la vía **débil**: sólo decide cuando no hay huella en los
#: dos lados. El hueco medido es de sólo 0.14 (de 0.612 a 0.753) y un grado muy
#: agresivo lo cruza. Ver `core/matching/NOTAS.md` §4.1.
UMBRAL_DESAJUSTE: float = 0.70

#: **Unidad: distancia de Hellinger (0..1)** entre los histogramas 2D de
#: cromaticidad. Por encima de esto sale una frase en castellano explicando que
#: los colores no están repartidos igual. **No decide el desajuste**: decide
#: texto que Mario lee. Era un literal `0.35` suelto en
#: `core/matching/contenido.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.**
UMBRAL_CROMA_EXPLICABLE: float = 0.35

#: **Unidad: diferencia media de percentiles de luma normalizados**
#: (adimensional). Igual que el anterior: por encima sale la frase de que el
#: reparto de luces y sombras es distinto. Era un literal `0.12` suelto.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.**
UMBRAL_PERFIL_EXPLICABLE: float = 0.12

#: **Unidad: correlación de gradientes (0..1)** entre original y coloreado
#: después de alinear. Por debajo de esto decimos que **no nos fiamos de que sean
#: el mismo encuadre**, y eso sale como nota y como razón de confianza: «el grado
#: puede ser un promedio de dos escenas». Medido: el mismo plano da > 0.9; un
#: retrato contra un exterior da ~0.0.
UMBRAL_CORRELACION_FIABLE: float = 0.50


# ===========================================================================
# 7. QC de LUT: «esto es banding», «esto no es monótono», «esto se sale del
#    gamut», «este LUT es plano». Son los códigos de problema que la GUI pinta
#    antes de escribir nada en Resolve.
#    El porqué, medido, está en `core/io/NOTAS.md` §3.
# ===========================================================================

#: **Unidad: veces el paso típico** (adimensional). Cuántas veces el paso típico
#: tiene que saltarse un cambio de pendiente para contar como banding. Es la
#: condición **relativa**, la que detecta el escalón.
UMBRAL_BANDING: float = 3.0

#: **Unidad: valores de salida del LUT** (0..1). Condición **absoluta**: cambio
#: de pendiente mínimo para que cuente. 0.02 son ~5/255; por debajo no se ve una
#: banda ni buscándola. Es lo que protege de los falsos positivos: en un LUT casi
#: plano la mediana de pasos es microscópica y el ruido de `float32` la supera
#: tres órdenes de magnitud.
#:
#: **Está decidido a conciencia y no se sube.** Marca la gamma `x**(1/2.2)` como
#: banding, y está medido que es verdad: el LUT se desvía 11/255 de la curva que
#: dice representar incluso con 65 puntos. Es el punto 6 de `BITACORA.md` §4 y
#: el punto 1 de `core/io/NOTAS.md` §«lo que dejo sin cerrar».
SALTO_MINIMO_BANDING: float = 0.02

#: **Unidad: nivel de ENTRADA del LUT** (0..1). Hasta aquí se considera que un
#: escalón está «en sombras». 0.125 es un octavo del recorrido de la rejilla: con
#: 17 puntos son los dos primeros intervalos, con 33 los cuatro primeros y con 65
#: los ocho primeros, o sea **siempre la misma zona de la imagen**, mida lo que
#: mida el LUT.
#:
#: **No cambia lo que se marca ni cuánto: cambia la REDACCIÓN.** Decide si el
#: aviso lleva la explicación de «esto es normal en un LUT de salida» o la de
#: «esto no es lo normal, míralo». Medido: la gamma de salida `x**(1/2.2)` marca
#: exactamente un escalón por eje y siempre en la posición 0, en 17, 33 y 65.
UMBRAL_SOMBRAS: float = 0.125

#: **Unidad: valores de salida del LUT** (0..1). Recorrido total por debajo del
#: cual se declara que **todas las celdas valen lo mismo** y el LUT «aplasta la
#: imagen entera a un solo color». Es un **error**, no un aviso, y cazó un fallo
#: real: un plano entero fuera del dominio ajustaba las 35.937 celdas contra una
#: sola esquina del cubo. Era un literal `1e-6` suelto en `core/io/qc.py`, en el
#: mismo fichero donde hay un `_PISO_ESCALA = 1e-6` que vale lo mismo y significa
#: otra cosa (una guarda de división), a unas ciento cuarenta líneas de
#: distancia. Dos números iguales con significados distintos y ninguno de los dos
#: con nombre en el sitio donde decide: así es como se confunden.
UMBRAL_RECORRIDO_LUT_PLANO: float = 1e-6

#: **Unidad: valores de salida del LUT** (0..1). Tolerancia de monotonía: por
#: debajo de esto una bajada es ruido de `float32`, no un LUT que baja.
TOL_MONOTONIA: float = 1e-5

#: **Unidad: valores de salida del LUT** (0..1). Tolerancia de gamut: 1/2048 es
#: medio escalón de 11 bits. Por debajo no se ve.
TOL_GAMUT: float = 1.0 / 2048.0


# ===========================================================================
# 8. Avisos sobre el material que Mario lee en la lista de clips
# ===========================================================================

#: **Unidad: fracción 0..1** de píxeles de la imagen clasificados como piel.
#: Por debajo de esto (**y** de `PIXELES_PIEL_MINIMOS`) no hay piel suficiente
#: para fiarse del locus: `ColorStats.skin_locus` sale `None` y se emite un
#: aviso. Es para que un plano general no se guíe por una cara de 20 píxeles.
#: Medido: los seis tonos de piel de `studio_scene` pasan de sobra (el peor, ~9%).
#: Elegido con la cabeza, **no medido contra un conjunto de validación**; lo dice
#: así `core/analysis/NOTAS.md` §2.
FRACCION_PIEL_MINIMA: float = 0.005

#: **Unidad: número de píxeles.** La otra mitad de la condición anterior: para
#: que en una miniatura pequeña no baste con dos píxeles de piel.
PIXELES_PIEL_MINIMOS: int = 64

#: **Unidad: fracción 0..1** del histograma de saturación que cae en el primer
#: bin. Por encima de esto se avisa de que «la imagen es prácticamente neutra
#: entera: no hay color que emparejar». Era un literal `0.999` suelto en
#: `core/analysis/stats.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** `core/analysis/NOTAS.md` §4.5 lo dice con
#: sus palabras: «es un umbral a ojo, pensado para rampas y cartas de gris; en
#: material real con un plano muy desaturado podría saltar sin que haga falta».
UMBRAL_NEUTRA_TOTAL: float = 0.999


# ===========================================================================
# 9. Tamaño de rejilla por defecto
# ===========================================================================

#: **Unidad: muestras por eje** de un LUT 3D. 33 y no 65: 33³ = 35.937 celdas,
#: suficiente para un look y con muchísimas más muestras por celda al invertir un
#: grado. Con 65³ un solo plano cubriría el 0.06% del cubo en vez del 0.46%, o
#: sea que el 99.94% sería invento. Es el punto 1 de `BITACORA.md` §4.
#:
#: Decide lo que Mario ve —la rejilla del mapa de cobertura y el tamaño del
#: `.cube` que se lleva— y lo miran dos módulos (`core.io` y `core.reverse`), así
#: que su sitio es éste. `core/contracts.py` lo reexporta para no romper a nadie.
LUT_SIZE_DEFAULT: int = 33
