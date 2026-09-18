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

AUDITORÍA DEL DÍA 7: ¿CONTRA QUÉ SE HA VISTO CADA NÚMERO?
-----------------------------------------------------------
Día 7 (17-09-2026), primer día con material real de Mario disponible (79 `.cube`
en `tests/luts_reales/`, 10 `.drx` en `tests/powergrades_reales/`, los dos de
sólo lectura). Cada constante lleva ahora, además de su razón de ser, una
etiqueta **«AUDITORÍA DÍA 7»** que dice si se ha visto alguna vez contra
material real o sólo contra ejemplos sintéticos fabricados para fallar
(`core/io/lut_malos.py`, `tests/media/generate.py`, `tests/calibracion*`).
Detalle completo, cifras y comandos en `CIFRAS.md` §20; la regla que motiva
esto está en `CONTRATOS.md`, "Ningún umbral se da por bueno sin verlo contra
material real".

De las 44 constantes de este módulo (43 auditadas contra material real ese
mismo día por un segundo agente en paralelo — ver más abajo — más
`TOL_MONOTONIA_LOOK`, calibrada por un primer agente el mismo día 7 y sumada
aquí al fusionar los dos trabajos):

* **8 VALIDADO CON MATERIAL REAL** — las seis de `core/io/qc.py`
  (`UMBRAL_BANDING`, `SALTO_MINIMO_BANDING`, `UMBRAL_SOMBRAS`, `TOL_GAMUT`,
  `UMBRAL_RECORRIDO_LUT_PLANO`, `TOL_MONOTONIA`), `LUT_SIZE_DEFAULT` (parcial)
  y `TOL_MONOTONIA_LOOK` (calibrada desde cero contra los 71 `.cube` "look",
  no descubierta disparando contra un valor antiguo). Son justo las que se
  PUEDEN pasar por los 79 `.cube` reales con el código que ya existe
  (`qc_lut`, `leer_cube`) sin inventar nada.
* **0 SOLO SINTÉTICO** — no queda ninguna: todo lo que era de `core/io` y
  sólo se había visto contra `lut_malos.py` se pasó hoy por los 79 `.cube`
  reales y se movió arriba.
* **36 NO VALIDABLE TODAVÍA** — el resto: `core/matching`, `core/reverse` y
  `core/analysis`. Deciden sobre PARES DE FOTOGRAMAS o CLIPS reales
  (ingeniería inversa, emparejamiento, huella, piel), y eso no existe hoy:
  el material de hoy es LUTs ya terminados y metadatos de PowerGrade, no
  metraje de vídeo. Necesitan brutos + máster de un trabajo real de Mario.

**El patrón que sospechaba Mario, confirmado por el barrido completo:** de los
8 umbrales que SÍ se pudieron poner delante de material real, los 3 que son
criterios de "esto está mal" (banding, monotonía, y ya antes la MAD de viñeta
del día 2) disparan de forma sistemática contra material real limpio y
profesional — no son casualidades aisladas, es lo que pasa cada vez que un
umbral calibrado sólo contra ejemplos fabricados para fallar se pone delante
de trabajo de verdad. `TOL_MONOTONIA_LOOK`, calibrada desde cero contra esa
misma distribución real, confirma el patrón desde el otro lado: ni relajando
la tolerancia con la propia medida real por delante se puede limpiar más del
11% de los LUT "look" sin dejar de proteger el LUT roto de T4 (`CIFRAS.md`
§19). Los otros 4 (los dos de gamut/plano y, parcialmente, `LUT_SIZE_DEFAULT`)
SÍ resistieron intactos. No se ha podido extender el barrido a los 36
restantes por falta de metraje, así que no se sabe si el patrón es igual de
fuerte ahí — es la pregunta abierta más grande que deja este día.

AÑADIDO EL DÍA 8: CUATRO CONSTANTES MÁS, FUERA DE LA AUDITORÍA DE ARRIBA
---------------------------------------------------------------------------
Los recuentos de arriba (44 constantes, 8 validadas) son del día 7 y se
dejan tal cual — son una foto de ese día, no una cifra que se reescriba cada
vez que se añade algo. `SUELO_NEGRO_VISIBLE_TUTOR`, `SUELO_SATURACION_ALTA_TUTOR`,
`UMBRAL_OFFSET_MENCIONABLE_TUTOR` y `UMBRAL_SLOPE_MENCIONABLE_TUTOR` se
sumaron el día 8, al construir `core/tutor/`, y caen en NO VALIDABLE por
inferencia nuestra: no calibradas contra material real, ver `SUPUESTOS.md`
fila G3. El módulo tiene 48 constantes en total a partir de hoy.
"""

from __future__ import annotations

__all__ = [
    "AREA_MINIMA_HOTSPOT",
    "PENA_LOTE_INCOHERENTE",
    "PIXELES_COMPARTIDOS_MINIMOS_LOTE",
    "UMBRAL_DISCREPANCIA_LOTE",
    "LIMITE_T1_DELTA_E_MAXIMO",
    "LIMITE_T3_DELTA_E_PEOR_PAR",
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
    "SUELO_NEGRO_VISIBLE_TUTOR",
    "SUELO_SATURACION_ALTA_TUTOR",
    "TOL_GAMUT",
    "TOL_MONOTONIA",
    "TOL_MONOTONIA_LOOK",
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
    "UMBRAL_OFFSET_MENCIONABLE_TUTOR",
    "UMBRAL_PERFIL_EXPLICABLE",
    "UMBRAL_R2_LINEAL",
    "UMBRAL_R2_RADIAL",
    "UMBRAL_RECORRIDO_GANANCIA",
    "UMBRAL_RECORRIDO_LINEAL",
    "UMBRAL_RECORRIDO_LUT_PLANO",
    "UMBRAL_REPRODUCIBLE_PURO",
    "UMBRAL_SLOPE_MENCIONABLE_TUTOR",
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** La MÉTRICA (ΔE2000) está validada
#: contra los 34 pares publicados de Sharma, Wu y Dalal (`CIFRAS.md` §2), pero eso
#: comprueba la fórmula, no si «1.0 = imperceptible» sigue siendo cierto sobre
#: metraje real de Mario (su compresión, su monitor). Haría falta grado real
#: aplicado a footage suyo para verlo. Ver `CIFRAS.md` §20.
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
#: **SIN CALIBRAR, Y NO PORQUE NO SE HAYA INTENTADO (día 4).** Se midió contra
#: 200 extracciones de `core.reverse` (×2 rejillas, en su plano y en 5 planos más)
#: y 720 pares de `core.matching`, con verdad conocida y ΔE2000 de `colour-science`
#: (`CALIBRACION-CONFIANZA.md`). Resultado: **la nota no predice el error que
#: decide**, así que no hay dónde poner este número:
#:
#: * `reverse`, 33³, material sin comprimir: la nota vale **1.0 en las 100
#:   extracciones** mientras el ΔE2000 máximo fuera de plano va de 0.50 a 39.26.
#:   Una constante no ordena nada (AUC 0.500). La correlación global (Spearman
#:   −0.55) sale entera de que la compresión baja la nota y sube el error a la vez;
#:   dentro de cada clase de material es nula o del signo contrario.
#: * Ningún corte deja el 95% de los casos por encima bajo el límite: lo mejor que
#:   da la nota es 17.0% fuera de plano en `reverse` 33³ (6.4% en 17³) y 51.1%
#:   (medio < 2.0, con score >= 0.968) en `matching`.
#:
#: Así que el 0.75 **sigue sin medida detrás** y no se ha movido: cambiarlo no
#: haría que «alta» signifique nada. Arreglarlo es rediseñar la nota, no el umbral.
#: Comando: `.venv/bin/python -m tests.calibracion.analizar | grep "CAL umbral"`.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** La calibración de arriba usó 3.600
#: casos SINTÉTICOS con verdad conocida (día 4), no material de Mario. Decidir si
#: predice algo sobre sus clips reales necesita parejas de clips suyos con el
#: error real medido — vídeo, no `.cube` ni `.drx`. Ver `CIFRAS.md` §20.
CONFIDENCE_ALTA: float = 0.75

#: **Unidad: fracción 0..1.** Por debajo de aquí, «baja». Entre las dos, «media».
#:
#: **SIN CALIBRAR**, por lo mismo que `CONFIDENCE_ALTA`. Y medido: en `reverse` la
#: nota es bimodal —cerca de 1, o multiplicada por `PENA_DESAJUSTE` hacia 0.3— y
#: **ninguna** de las 400 extracciones cae entre 0.45 y 0.75, así que «media» no
#: sale nunca y mover este número no cambia ningún veredicto. En `matching` el
#: tramo por debajo de 0.45 cumple en un 8% y el de 0.45–0.75 en un 17%, con
#: intervalos que se pisan: los datos no separan ahí «revisar» de «no sirve».
#: Comando: `.venv/bin/python -m tests.calibracion.analizar | grep "CAL tramos"`.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que `CONFIDENCE_ALTA`:
#: sólo visto contra los 3.600 casos sintéticos del día 4. Necesita clips reales
#: de Mario emparejados, con error conocido. Ver `CIFRAS.md` §20.
CONFIDENCE_MEDIA: float = 0.45

#: **Unidad: fracción 0..1 (multiplicador).** Cuánto se multiplica la nota de
#: confianza cuando el detector de contenido dice que las dos escenas no son
#: comparables. Multiplica a propósito y no resta: un desajuste de contenido no
#: es «una pega más», es que el número de abajo no significa lo que parece.
#: Con 0.35, una nota perfecta baja a 0.35 = «baja», que es lo que hay que
#: enseñar. Ver `core/matching/NOTAS.md` §3.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Decide cuánto penalizar cuando dos
#: CLIPS no parecen la misma escena: necesita pares de clips reales de Mario, no
#: `.cube` ni `.drx`. Ver `CIFRAS.md` §20.
PENA_DESAJUSTE: float = 0.35

#: **Unidad: fracción 0..1** sobre una subnota. Por debajo de esto, la subnota
#: se convierte en una **frase en castellano** dentro de `Confidence.reasons`,
#: que es texto que Mario lee. Era un literal suelto en
#: `core/matching/confianza.py`. 0.85 es «casi perfecto pero no del todo»: por
#: encima no hay nada que explicar.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** No hay medida detrás del 0.85.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Decide una frase sobre la subnota
#: de emparejamiento de dos CLIPS: necesita pares de clips reales, no `.cube` ni
#: `.drx`. Ver `CIFRAS.md` §20.
UMBRAL_SUBNOTA_EXPLICABLE: float = 0.85

#: Los dos extremos de cada rampa de la nota de confianza: `(valor con subnota
#: 1, valor con subnota 0)`.
#:
#: **Unidad: una distinta por clave**, y por eso va escrita dentro, al lado de
#: cada rampa: aquí conviven píxeles, fracciones, ΔE2000 y un número de
#: condición, y son justo la clase de números que no hay que confundir. La
#: nota final es `sqrt(min(subnotas) * media_geometrica(subnotas))` por
#: `PENA_DESAJUSTE`; la fórmula entera está en `core/matching/NOTAS.md` §3.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Las siete rampas están medidas
#: contra el generador sintético del proyecto (comentario de cada clave, abajo),
#: nunca contra un emparejamiento real de clips de Mario. Necesita pares de
#: clips reales. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Decide un veredicto de ingeniería
#: INVERSA (original vs. reconstruido con el grado extraído): necesita pares de
#: fotogramas reales de Mario (bruto + máster), que no existen hoy — sólo hay
#: `.cube` y `.drx` finales, no el origen para invertir. Ver `CIFRAS.md` §20.
UMBRAL_REPRODUCIBLE_PURO: float = 0.95

#: **Unidad: ΔE2000**, aplicado al **percentil 95** del residuo. Segunda
#: condición de `is_pure_lut`: «el 95% del fotograma cae por debajo de lo que el
#: ojo distingue».
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que
#: `UMBRAL_REPRODUCIBLE_PURO`: necesita ingeniería inversa sobre fotogramas
#: reales de Mario, que no existen hoy. Ver `CIFRAS.md` §20.
UMBRAL_DE_PURO: float = DELTA_E_INDISTINGUIBLE

#: **Unidad: ΔE2000.** Por debajo de esto no hay nada que señalar como hotspot:
#: es residuo que no se ve.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo: necesita ingeniería
#: inversa sobre fotogramas reales de Mario. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Sólo se ha visto contra el mismo
#: plano sintético contra sí mismo (arriba). Necesita pares reales de Mario
#: (bruto vs. máster) para saber si 0.05 ΔE2000 medio separa bien «no se gradó»
#: de «se gradó poco» en su material. Ver `CIFRAS.md` §20.
UMBRAL_MOVIMIENTO_NULO: float = 0.05

#: **Unidad: número de píxeles válidos.** Por debajo de esto no se ajusta CDL:
#: se devuelve la identidad y se dice en las notas. Diez parámetros con cuatro
#: píxeles es ruido con forma de grado.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** `core/reverse/NOTAS.md` §9 lo da como razón
#: cualitativa sin ningún número detrás.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Necesita píxeles reales de un
#: ajuste de CDL sobre footage de Mario; hoy no hay fotogramas, sólo `.cube` y
#: `.drx` ya terminados. Ver `CIFRAS.md` §20.
MUESTRAS_MINIMAS_CDL: int = 64

#: **Unidad: fracción 0..1** de píxeles que, después del CDL, se salen del
#: dominio 0..1 del LUT. Por encima de esto se avisa en las notas de que ahí el
#: LUT sujeta al borde y el color no se transforma. Era un literal `0.001`
#: suelto en `core/reverse/invertir.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Es un 0.1% de los píxeles; no hay medida
#: detrás.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Necesita píxeles reales tras
#: aplicar un CDL a footage de Mario. No hay fotogramas hoy. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Decide cobertura de celda al
#: acumular píxeles reales durante la ingeniería inversa: necesita footage de
#: Mario para acumular, que no existe hoy. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Además, D4-1 midió que este aviso
#: «avisa al revés» sobre material SINTÉTICO (salta en las escenas que mejor se
#: portan fuera de plano, calla en las peores) — con más razón hace falta footage
#: real de Mario antes de tocarlo. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Detecta viñeta en el campo de
#: ganancia de un fotograma real gradado: necesita footage de Mario, no `.cube`
#: ni `.drx`. Sólo visto contra viñetas sintéticas fabricadas por
#: `tests/media/generate.py`. Ver `CIFRAS.md` §20.
UMBRAL_R2_RADIAL: float = 0.30

#: **Unidad: |Pearson| (0..1)** del perfil radial contra el radio. En valor
#: absoluto a propósito: una viñeta que **aclara** hacia fuera es igual de
#: imposible de meter en un LUT que una que oscurece, y el signo se reporta
#: aparte («oscurece» / «aclara»).
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que `UMBRAL_R2_RADIAL`:
#: sólo visto contra viñetas sintéticas. Ver `CIFRAS.md` §20.
UMBRAL_MONOTONIA_RADIAL: float = 0.55

#: **Unidad: logaritmo natural de ganancia** (0.12 ≈ 0.17 paradas de luz entre
#: el centro y el borde). Recorrido mínimo del perfil radial. Medido: «nada
#: espacial» da 0.000 y «grano fuerte» 0.004; la viñeta más floja probada (0.35)
#: da 0.27.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo: viñetas y grano
#: sintéticos, no footage de Mario. Ver `CIFRAS.md` §20.
UMBRAL_RECORRIDO_GANANCIA: float = 0.12

#: **Unidad: R² (fracción 0..1)** de un plano inclinado sobre lo que queda del
#: campo de ganancia tras restarle el modelo radial. Cuánta varianza tiene que
#: explicar para llamarlo degradado. Es la puerta más fácil de disparar sin
#: querer —casi cualquier residuo tiene algo de inclinación— y por eso se pide
#: más que en la radial.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Detecta degradado (ventana/luz
#: entrando) sobre footage real: sólo visto contra ventanas sintéticas. Necesita
#: footage de Mario. Ver `CIFRAS.md` §20.
UMBRAL_R2_LINEAL: float = 0.50

#: **Unidad: logaritmo natural de ganancia.** Recorrido mínimo de ese plano
#: inclinado de un lado a otro del fotograma.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que `UMBRAL_R2_LINEAL`:
#: sólo visto contra ventanas sintéticas. Ver `CIFRAS.md` §20.
UMBRAL_RECORRIDO_LINEAL: float = 0.10

#: **Unidad: ΔE2000 (desviación típica)** del residuo de **alta** frecuencia.
#: Por encima de esto se declara textura: grano, enfoque, reducción de ruido,
#: halación. Medido: sin nada 0.11, compresión h264 fuerte 0.5-0.9, viñeta o
#: ventana 1.3-1.7 (que es el error del ajuste del LUT en los bordes del
#: contenido, no textura del material) y grano de verdad 3.83. El margen real es
#: 3.83 contra 1.44, un factor 2.7, así que este umbral no puede bajar de ~2.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** El grano y la compresión reales de
#: las cámaras de Mario pueden no parecerse al grano sintético del generador.
#: Necesita footage suyo. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Ya hay una discrepancia sin
#: resolver entre dos fuentes sintéticas (arriba); zanjarla, y validarlo de
#: verdad, necesita footage real de Mario. Ver `CIFRAS.md` §20.
SUELO_GANANCIA_LOCAL: float = 0.08

#: **Unidad: fracción 0..1** de la altura del pico sobre la mediana. El contorno
#: de la zona local se traza aquí. Es un criterio **sin escala**: una ventana de
#: +15% se recorta igual de bien que una de +60%, y no hay ningún número
#: calibrado contra un caso concreto.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** El contorno de zona local se traza
#: sobre residuo real; necesita footage de Mario con una zona local de verdad
#: (ventana, foco de luz). Ver `CIFRAS.md` §20.
FRACCION_DE_PICO: float = 0.40

#: **Unidad: fracción 0..1 del área del fotograma.** Área mínima de una
#: componente conexa para que cuente como zona. El 0.2% del cuadro.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Hay razón cualitativa («por debajo es
#: grano, no una zona»), pero ninguna medida. Lo dice `core/reverse/NOTAS.md` §9.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Necesita footage real de Mario con
#: grano de sus cámaras y una zona local real para comparar tamaños. Ver
#: `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** La huella se mide sobre fotogramas
#: reales de dos clips; el hueco de arriba viene de material sintético del
#: generador. Necesita clips reales de Mario. Ver `CIFRAS.md` §20.
UMBRAL_HUELLA: float = 0.50

#: **Unidad: suma de dos distancias adimensionales** (`perfil` + `croma`, con
#: peso 1 cada una). Es la vía **débil**: sólo decide cuando no hay huella en los
#: dos lados. El hueco medido es de sólo 0.14 (de 0.612 a 0.753) y un grado muy
#: agresivo lo cruza. Ver `core/matching/NOTAS.md` §4.1.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que `UMBRAL_HUELLA`:
#: hueco medido en material sintético. Necesita clips reales. Ver `CIFRAS.md` §20.
UMBRAL_DESAJUSTE: float = 0.70

#: **Unidad: distancia de Hellinger (0..1)** entre los histogramas 2D de
#: cromaticidad. Por encima de esto sale una frase en castellano explicando que
#: los colores no están repartidos igual. **No decide el desajuste**: decide
#: texto que Mario lee. Era un literal `0.35` suelto en
#: `core/matching/contenido.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.**
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Decide una frase sobre dos CLIPS
#: reales; necesita pares de clips de Mario. Ver `CIFRAS.md` §20.
UMBRAL_CROMA_EXPLICABLE: float = 0.35

#: **Unidad: diferencia media de percentiles de luma normalizados**
#: (adimensional). Igual que el anterior: por encima sale la frase de que el
#: reparto de luces y sombras es distinto. Era un literal `0.12` suelto.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.**
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que
#: `UMBRAL_CROMA_EXPLICABLE`: necesita clips reales de Mario. Ver `CIFRAS.md` §20.
UMBRAL_PERFIL_EXPLICABLE: float = 0.12

#: **Unidad: correlación de gradientes (0..1)** entre original y coloreado
#: después de alinear. Por debajo de esto decimos que **no nos fiamos de que sean
#: el mismo encuadre**, y eso sale como nota y como razón de confianza: «el grado
#: puede ser un promedio de dos escenas». Medido: el mismo plano da > 0.9; un
#: retrato contra un exterior da ~0.0.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Medido sobre escenas sintéticas
#: del generador; necesita alinear fotogramas reales de Mario. Ver `CIFRAS.md`
#: §20.
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
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL.** Medido contra los 79 `.cube`
#: de `tests/luts_reales/`: dispara en los 79 de 79 (8 LUT de conversión + 71
#: «look»). Mismo patrón que la MAD de viñeta (día 2) y que `TOL_MONOTONIA`: un
#: umbral calibrado en sintético dispara siempre en material real. **No se toca
#: hoy** — está decidido a conciencia desde el día 1 (ver el comentario de
#: `SALTO_MINIMO_BANDING`) y el hallazgo ya estaba anticipado. Ver `CIFRAS.md`
#: §20. Comando: `.venv/bin/python -m pytest tests/test_io_qc_reales.py -q -k banding`.
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
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL.** Misma medición que
#: `UMBRAL_BANDING` (los dos deciden juntos): dispara en los 79 de 79 `.cube`
#: reales. Confirma con datos de verdad la decisión ya tomada de no subirlo. Ver
#: `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL.** Medido contra los 8 `.cube`
#: de conversión reales de `tests/luts_reales/`: 50 escalones caen en sombras y
#: 1182 en medios (96%) — lo CONTRARIO de lo que el texto viejo de
#: `EXPLICACION_MEDIOS` en `core/io/qc.py` daba a entender. Cambió el TEXTO del
#: aviso, no este número ni lo que se marca. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL.** Ninguno de los 79 `.cube`
#: reales de `tests/luts_reales/` dispara `lut_plano`: 0 de 79 falsos positivos.
#: Ver `CIFRAS.md` §20. Comando:
#: `.venv/bin/python -m pytest tests/test_io_qc_reales.py -q -k gamut_fuera_ni_nan`.
UMBRAL_RECORRIDO_LUT_PLANO: float = 1e-6

#: **Unidad: valores de salida del LUT** (0..1). Tolerancia de monotonía: por
#: debajo de esto una bajada es ruido de `float32`, no un LUT que baja.
#:
#: **Sólo para LUT de conversión de espacio de color** (`core.io.qc.clasificar_lut`
#: → `"conversion"`), donde la monotonía diagonal estricta SÍ es la condición
#: correcta: una curva de transferencia + primarios tiene que subir siempre en
#: la dirección tonal. Para un LUT de look ver `TOL_MONOTONIA_LOOK`.
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL, Y ES EL TERCER HALLAZGO DEL
#: MISMO PATRÓN.** Medido contra los 79 `.cube` reales de `tests/luts_reales/`:
#: `no_monotonia` (un ERROR, no un aviso) dispara en 76 de 79 sin clasificar por
#: clase (70 de 79 con la clasificación conversión/look de `TOL_MONOTONIA_LOOK`,
#: ver abajo), incluidos 8 manuales de fábrica de DJI. Mismo patrón que la MAD
#: de viñeta (día 2) y que `UMBRAL_BANDING`: un umbral calibrado sólo contra
#: `core/io/lut_malos.py` dispara sistemáticamente contra material real.
#: La cifra "peor caída real: −0.230" que circuló durante el día resultó ser un
#: INFRACONTEO: `core/io/qc.py::_monotonia()` corta el bucle de ejes al llegar a
#: `MAX_PROBLEMAS_POR_CODIGO` (20), así que en 67 de 79 archivos el peor salto
#: real (hasta −0.315, en `Jota_lut_fitz.cube`) nunca se llega a mirar. No
#: afecta a si se detecta el error, sólo a la magnitud que se enseña — bug
#: dejado medido y con nombre, no corregido hoy (cambiaría un test de día 6
#: ajeno a este encargo). Ver `CIFRAS.md` §19 y §20.
TOL_MONOTONIA: float = 1e-5

#: **Unidad: valores de salida del LUT** (0..1). Tolerancia de monotonía PARA
#: UN LUT DE "LOOK" (`core.io.qc.clasificar_lut(lut) == "look"`), no para uno
#: de conversión de espacio de color. Día 7: Mario decidió que la monotonía
#: diagonal estricta es correcta para una conversión (tiene que subir siempre
#: en la dirección tonal) pero no para un look, donde un viraje de tono baja
#: un canal a propósito mientras sube otro — eso es el look, no un fallo.
#:
#: **Medido contra los 71 `.cube` reales clasificados "look" de
#: `tests/luts_reales/`** (mismo cálculo que `core.io.qc._monotonia`: por eje,
#: `diff` a lo largo del eje, magnitud de los valores negativos).
#: Percentiles de las 2.270.401 reversiones individuales medidas: mediana
#: 0.000183, p90 = 0.00499, p95 = 0.0111, p99 = 0.0417, máximo 0.315. Por
#: ARCHIVO (el peor salto de cada uno de los 71): sólo 2 no tienen ninguna
#: reversión; la mediana del peor salto POR ARCHIVO es 0.028 — casi tres
#: veces el techo de abajo.
#:
#: **El techo duro, que no se cruza**: `core/io/lut_malos.py::lut_no_monotono`
#: usa `caida=0.01` por defecto (catálogo de LUT rotos de T4), y
#: `tests/test_entregables.py::test_T4_caza_un_lut_no_monotono` construye el
#: suyo con una caída de 0.02. Los dos tienen que seguir cazándose con la
#: tolerancia relajada, con margen real y no pegados al límite. Este valor deja
#: **2x de margen** bajo el más bajo de los dos (0.01) y 4x bajo el otro
#: (0.02): comprobado a mano y con test, con `qc_lut(lut_no_monotono(caida=X),
#: clasificacion="look", tol_monotonia_look=TOL_MONOTONIA_LOOK)` para
#: `X = 0.01` y `X = 0.02` — `CODIGO_NO_MONOTONIA` sigue apareciendo en los
#: dos. El punto exacto donde una tolerancia relajada deja de cazar es la
#: propia tolerancia (`_monotonia` usa `d < -tol`, sin suavizado): con este
#: valor, `caida=0.005` ya NO se caza y `caida=0.006` sí — confirma que el
#: margen es real y no está pegado al límite por casualidad.
#:
#: **La tensión, dicha tal cual**: con este valor, de los 71 LUT "look" reales
#: sólo 8 quedan limpios de `no_monotonia`; los otros 63 (89%) SIGUEN
#: disparando, porque su peor salto real es mayor que el techo que protege a
#: T4. Subir el umbral por encima de 0.01 limpiaría más archivos, pero
#: dejaría de cazar el LUT roto de `lut_no_monotono(caida=0.01)` — es decir,
#: relajaría de más. **No hay un umbral único que absorba la monotonía
#: "normal de un look" real Y siga protegiendo el LUT roto de T4**: el hueco
#: entre "reversión de look legítima" (mediana 0.028 por archivo) y "techo que
#: protege T4" (0.01) no es un hueco limpio como el de
#: `UMBRAL_CHROMA_CONVERSION` — es una zona gris de verdad. Ver
#: `CIFRAS.md` §19 para las cifras completas y el comando reproducible.
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL.** Es justo lo que dice el
#: comentario de arriba: calibrado y validado contra los 71 `.cube` reales
#: clasificados "look", no contra sintéticos. Único de los "7 validados" que
#: se calibró HOY contra material real desde cero, en vez de descubrir que un
#: valor antiguo disparaba contra él.
TOL_MONOTONIA_LOOK: float = 0.005

#: **Unidad: valores de salida del LUT** (0..1). Tolerancia de gamut: 1/2048 es
#: medio escalón de 11 bits. Por debajo no se ve.
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL.** Ninguno de los 79 `.cube`
#: reales de `tests/luts_reales/` sale con valores fuera de gamut: 0 de 79 falsos
#: positivos. Ver `CIFRAS.md` §20. Comando:
#: `.venv/bin/python -m pytest tests/test_io_qc_reales.py -q -k gamut_fuera_ni_nan`.
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
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Necesita fotogramas reales de
#: Mario con piel de verdad; `studio_scene` es sintética. Ver `CIFRAS.md` §20.
FRACCION_PIEL_MINIMA: float = 0.005

#: **Unidad: número de píxeles.** La otra mitad de la condición anterior: para
#: que en una miniatura pequeña no baste con dos píxeles de piel.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que
#: `FRACCION_PIEL_MINIMA`. Ver `CIFRAS.md` §20.
PIXELES_PIEL_MINIMOS: int = 64

#: **Unidad: fracción 0..1** del histograma de saturación que cae en el primer
#: bin. Por encima de esto se avisa de que «la imagen es prácticamente neutra
#: entera: no hay color que emparejar». Era un literal `0.999` suelto en
#: `core/analysis/stats.py`.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** `core/analysis/NOTAS.md` §4.5 lo dice con
#: sus palabras: «es un umbral a ojo, pensado para rampas y cartas de gris; en
#: material real con un plano muy desaturado podría saltar sin que haga falta».
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** El propio `NOTAS.md` ya avisa del
#: riesgo con material real; comprobarlo necesita fotogramas reales de Mario, no
#: `.cube` ni `.drx`. Ver `CIFRAS.md` §20.
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
#:
#: **AUDITORÍA DÍA 7 — VALIDADO CON MATERIAL REAL (parcial, dicho con honestidad).**
#: De los 79 `.cube` reales de `tests/luts_reales/`, 43 son 33³ y 36 son 65³ (0 de
#: 17³): 33³ no es un capricho del proyecto, es un tamaño de entrega tan habitual
#: en LUTs reales como 65³. **Esto NO valida el razonamiento de cobertura** de
#: arriba (0.46% vs. 0.06% del cubo al invertir UN grado): esos 79 archivos son
#: LUTs ya terminados, no productos de nuestra propia ingeniería inversa sobre
#: footage de Mario, que es lo único que probaría esa parte. Ver `CIFRAS.md` §20,
#: fila de tamaños de rejilla. Comando:
#: `.venv/bin/python -m pytest tests/test_io_qc_reales.py -q -k tamanos`.
LUT_SIZE_DEFAULT: int = 33


# ---------------------------------------------------------------------------
# Límites de los criterios de entrega (día 4)
# ---------------------------------------------------------------------------
#
# Desde el día 4 el titular de T1 y T3 es la cifra que DECIDE -el máximo y el
# peor par-, con su margen al límite al lado. La interfaz enseña ese margen, así
# que los dos límites tienen que vivir aquí y no escritos a mano en `gui/`.
#
# OJO CON LO QUE SON: **no son medidas.** Son los criterios que fijó el encargo
# del día 1 («ΔE2000 máximo < 3.0», «ΔE2000 entre cámaras < 2.0 después»). Nadie
# ha medido que 3.0 o 2.0 sean el sitio donde un colorista empieza a notar algo:
# son objetivos, y se escriben aquí como objetivos para que nadie los lea como
# un umbral perceptual calibrado.

#: **Unidad: ΔE2000.** Límite del ΔE2000 **máximo** de la ingeniería inversa
#: (T1). Por encima, el criterio no se cumple.
#:
#: **Criterio del encargo del día 1, no medido.**
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** Comprobarlo contra material real
#: necesita ejecutar T1 (ingeniería inversa) sobre footage de Mario; hoy T1 sólo
#: se ha medido con escenas sintéticas (días 1-4). Ver `CIFRAS.md` §20.
LIMITE_T1_DELTA_E_MAXIMO: float = 3.0

#: **Unidad: ΔE2000.** Límite del ΔE2000 del **peor par** de cámaras después de
#: igualarlas (T3).
#:
#: **Criterio del encargo del día 1, no medido.** El encargo lo escribía sobre
#: la media; desde el día 4 se aplica al peor par, que es la cifra que decide.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que
#: `LIMITE_T1_DELTA_E_MAXIMO`: necesita T3 sobre cámaras reales de Mario. Ver
#: `CIFRAS.md` §20.
LIMITE_T3_DELTA_E_PEOR_PAR: float = 2.0


# ===========================================================================
# 10. Modo por lote (día 4): ¿llevan todos los planos el mismo grado?
#     Decide si Mario lee «estos 3 planos no llevan el mismo grado que el
#     resto». Un aviso que salta siempre no lo lee nadie; uno que no salta
#     entrega un LUT que no es de ningún plano con buena cara.
# ===========================================================================

#: **Unidad: ΔE2000, mediana** sobre los colores que un plano comparte con los
#: demás, entre su salida real y la que predice el grado ajustado con los
#: demás. Por encima, `core.reverse.comprobar_coherencia` dice que ese plano no
#: lleva el mismo grado que el resto.
#:
#: **Por qué este valor**: es `DELTA_E_INDISTINGUIBLE`. Si en la mitad de los
#: colores compartidos la diferencia no llega a lo que el ojo distingue, mezclar
#: ese plano con los demás no cambia nada que se vea. **Medido** en el proyecto
#: sintético de 20 planos (`.venv/bin/python -m pytest tests/test_reverse_lote.py
#: -s -q`): el plano más alto de un proyecto coherente puntúa 0.0992, y una
#: corrección extra puntúa más o menos lo que ella misma mueve su plano (mediana
#: propia 1.071 -> 1.156; 0.531 -> 0.553, que no avisa). **En material real, con
#: compresión de verdad, no medido.**
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA.** El propio comentario de arriba ya
#: lo decía: falta footage real de varios planos del mismo trabajo de Mario. Ver
#: `CIFRAS.md` §20.
UMBRAL_DISCREPANCIA_LOTE: float = DELTA_E_INDISTINGUIBLE

#: **Unidad: píxeles** de la submuestra de un plano (20.000 como mucho) cuyos
#: ocho nodos tienen datos de los demás planos. Por debajo, ese plano sale en
#: `sin_comparar`: no hay con qué decir si lleva el mismo grado.
#:
#: **NO SE SABE POR QUÉ VALE ESTO** más allá de «una mediana de menos de 200
#: valores se mueve con poco». Es el 1% de la submuestra.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que
#: `UMBRAL_DISCREPANCIA_LOTE`: necesita varios planos reales del mismo trabajo.
#: Ver `CIFRAS.md` §20.
PIXELES_COMPARTIDOS_MINIMOS_LOTE: int = 200

#: **Unidad: fracción 0..1 (multiplicador)** de `Confidence.score` cuando el lote
#: no es coherente y aun así se ajusta con todos (`excluir_discrepantes=False`).
#: Multiplica por lo mismo que `PENA_DESAJUSTE`, y por la misma razón: un LUT
#: que mezcla dos grados no es «una pega más», es que el número de arriba no
#: significa lo que parece. Con 0.35 una nota perfecta baja a «baja».
#:
#: **NO SE SABE POR QUÉ VALE ESTO** aparte de copiar el criterio de
#: `PENA_DESAJUSTE`, que tampoco tiene medida detrás.
#:
#: **AUDITORÍA DÍA 7 — NO VALIDABLE TODAVÍA**, por lo mismo que `PENA_DESAJUSTE`
#: y `UMBRAL_DISCREPANCIA_LOTE`: necesita varios planos reales. Ver `CIFRAS.md`
#: §20.
PENA_LOTE_INCOHERENTE: float = PENA_DESAJUSTE


# ===========================================================================
# 10. El tutor (día 8) — cuándo hay algo que vale la pena decir
# ===========================================================================
#
# Los cuatro de aquí abajo NO son umbrales de "esto está mal" — el catálogo
# del tutor (`core/tutor/catalogo.py`) los usa en reglas marcadas
# `"descriptiva"`: nunca afirman un veredicto, sólo deciden cuándo una
# característica medida vale la pena convertirse en una frase. Aun así viven
# aquí y no como literales sueltos en `core/tutor/`, por el mismo motivo que
# el resto del archivo: deciden algo que Mario lee en pantalla (criterio 3
# de la cabecera de este módulo), así que es un criterio de decisión, aunque
# la decisión sea "¿hablo o me callo?" y no "¿esto pasa o no pasa?".


#: **Unidad: fracción 0..1**, sobre el punto negro (percentil 1) ya pasado
#: por la curva de cámara Rec.709 (`core.tutor.catalogo._porcentaje_rec709`).
#: Por debajo de esto, `_regla_punto_negro` no dice nada: no hay negro
#: levantado que valga la pena mencionar.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Es una décima de la resolución de un
#: `uint8` (1/255), elegida a ojo para no reportar ruido de cuantización
#: como si fuera un negro levantado de verdad — no calibrada contra material
#: real. Ver `SUPUESTOS.md`, fila G3.
SUELO_NEGRO_VISIBLE_TUTOR: float = 0.02

#: **Unidad: fracción 0..1** del histograma de saturación
#: (`ColorStats.saturation_hist`) que hace falta en el cuarto de bins más
#: alto para que `_regla_saturacion_extendida` diga algo.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Elegido a ojo (un cuarto del
#: histograma), no calibrado. Además se mide sobre `WORKING_SPACE`
#: (logarítmico), así que es probablemente CONSERVADOR — ver
#: `core/tutor/NOTAS.md` y `SUPUESTOS.md`, fila G1/G3.
SUELO_SATURACION_ALTA_TUTOR: float = 0.05

#: **Unidad: valores de CDL `offset`** (en `WORKING_SPACE`, el mismo espacio
#: en el que vive el CDL del contrato). Por debajo de esto, un ajuste de
#: exposición no vale la pena mencionarlo en las lecciones del tutor
#: (`core.tutor.ensenar._leccion_exposicion_no_va_en_el_look`,
#: `_leccion_cdl`) — el mismo umbral en los dos sitios, es la misma pregunta
#: ("¿este offset es ruido o un ajuste de verdad?") hecha dos veces.
#:
#: **NO SE SABE POR QUÉ VALE ESTO.** Elegido a ojo, no calibrado contra
#: material real. Ver `SUPUESTOS.md`, fila G3.
UMBRAL_OFFSET_MENCIONABLE_TUTOR: float = 0.01

#: **Unidad: desviación típica entre los tres canales de `CDL.slope`.** Por
#: debajo de esto, `core.tutor.ensenar._leccion_cdl` no menciona el balance
#: de color: los tres canales están lo bastante juntos como para no ser un
#: ajuste real.
#:
#: **NO SE SABE POR QUÉ VALE ESTO**, misma historia que
#: `UMBRAL_OFFSET_MENCIONABLE_TUTOR`. Ver `SUPUESTOS.md`, fila G3.
UMBRAL_SLOPE_MENCIONABLE_TUTOR: float = 0.01
