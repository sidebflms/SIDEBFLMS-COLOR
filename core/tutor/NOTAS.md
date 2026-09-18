# NOTAS — `core.tutor`

Día 8, tarea 2. El tutor estaba a cero desde el día 1: nunca se le asignó a
nadie. Con el modo fácil redefinido para alguien que sólo sabe aplicar un
LUT, no es un extra — es casi el producto. Hoy el modo fácil dice qué ha
hecho; el tutor es lo que le enseña algo.

## Lo que no se escribió, y por qué (tarea 2.1, punto 3 del encargo)

La regla del catálogo es explícita: si una regla necesita una característica
que no se está midiendo, no se escribe la regla — se anota qué haría falta
medir. Esto es esa lista.

### Una regla de "exposición incorrecta"

**Lo que haría falta**: un umbral en stops (o en desviación de un punto medio
esperado) validado contra material real de que "esto está sub/sobreexpuesto".
No existe. `core.matching` calcula un CDL que iguala un clip a una
referencia, pero eso mide DIFERENCIA respecto a otro clip, no si la
exposición en sí es correcta — no hay un concepto de "exposición correcta"
en el sistema sin una referencia externa, y toda referencia externa que se
podría usar (una carta de color, un fotómetro) está fuera de lo que la app
mide hoy.

### Una regla de "el look tiene banding real"

**Por qué no, aunque el umbral SÍ está validado**: `UMBRAL_BANDING`/
`SALTO_MINIMO_BANDING` están en VALIDADO (día 7, `CIFRAS.md` §20) — pero
disparan en **79 de 79** LUTs reales (`CIFRAS.md` §17). Una regla que
siempre dispara no dice nada sobre ESTE look en particular: no discrimina,
así que no cumple la vara de "una frase concreta sobre este clip" de la
tarea 2.2. Se deja fuera del catálogo de "explicar", aunque la comprobación
en sí sigue viva en `core.io.qc.qc_lut()` para lo que ya la usa.

### Una regla de "monotonía del look rota"

**Por qué no, con el hallazgo del día 8 delante**: `TOL_MONOTONIA_LOOK`
(D7-1) sólo limpia 8 de 71 LUT "look" reales — sigue sin discriminar bien
por sí sola. La prueba del eje de hoy (D8-0, `CIFRAS.md` §21) SÍ encontró
una operacionalización que discrimina de verdad (sólo la diagonal neutra:
3 de 79, no 70 de 79) — pero es una medida sobre una comprobación que
`core/io/qc.py::_monotonia()` no implementa todavía (sigue recorriendo todo
el cubo). Escribir una regla del tutor contra un cálculo que no vive en el
detector oficial sería duplicar lógica y desincronizarse en el primer cambio
de umbral. Cuando (si) se decida rediseñar `_monotonia()` para mirar sólo la
diagonal, esta regla se puede escribir contra `core.io.qc` directamente.

### Un "veredicto" de saturación con la palabra "mal" o "roto"

**Lo que haría falta**: un umbral de "cuánta saturación en el histograma es
demasiada" validado contra material real — no existe (no está ni en la
lista de 36 del día 7: nadie ha definido ese umbral todavía, ni siquiera
como sintético). La regla `saturacion_extendida` existe igualmente, pero
como DESCRIPTIVA (reporta el hecho medido, nunca un veredicto) y con el
verbo en condicional ("puede perder detalle"), nunca en indicativo
("pierde"/"se empasta").

### Un locus de piel "ideal" o "saludable" contra el que comparar

**Lo que haría falta**: una referencia validada de "así debería verse una
piel bien expuesta y bien balanceada" — no existe en este proyecto.
`core.color.perceptual.SKIN_OKLAB_LIMITES` es un rango de DETECCIÓN (qué
píxeles cuentan como piel), calibrado contra los seis tonos sintéticos de
`tests/media/generate.py`, no un punto de referencia de "piel correcta". Por
eso `piel_vs_referencia` compara el clip contra el CLIP DE REFERENCIA que
Mario ya eligió en el paso 2 del modo fácil (igualar), nunca contra un
"ideal" inventado — es una comparación relativa y medible, no una
afirmación sobre qué color de piel es "correcto".

## Un supuesto real que se coló al construir, con su fila en `SUPUESTOS.md`

`_regla_saturacion_extendida` y `_regla_punto_negro` calculan sobre
`ColorStats`, que vive en `WORKING_SPACE` (`davinci_wg_intermediate`,
**logarítmico** — el negro NO está en código 0). Se descubrió a medio
construir, probando la regla de saturación contra un primario puro de
Rec.709 escena-lineal: al convertirlo a `WORKING_SPACE`, la saturación HSV
(`(max-min)/max`) cae a ~0.48, no a 1.0, porque la curva log comprime cada
canal de forma distinta cerca de los extremos.

- **`punto_negro`** se corrigió pasando el valor por la curva de cámara
  Rec.709 antes de mostrarlo como porcentaje (`_porcentaje_rec709`) — así el
  número que lee Mario es un tanto por ciento de recorrido tonal legible,
  no un código de trabajo interno.
- **`saturacion_extendida`** se dejó SIN corregir, calculando directamente
  sobre `ColorStats.saturation_hist` (ya en `WORKING_SPACE`): no había sitio
  en el presupuesto de hoy para recalcular saturación sobre píxeles
  convertidos (haría falta guardar los píxeles del análisis,
  `guardar_pixeles=True`, y convertirlos, más coste por clip). Consecuencia
  honesta: el umbral `_SUELO_SATURACION_ALTA = 0.05` es probablemente
  CONSERVADOR — sobre código log, un color realmente muy saturado en escena
  puede no llegar a marcar el bin más alto, así que esta regla es más
  probable que se quede corta (no avise cuando debería) que al revés. Fila
  añadida a `SUPUESTOS.md`.

## Leído seguido (tarea 2.6): `punto_negro` dispara en 7 de 7 clips de la demo

Leyendo las frases de los siete clips de `gui.datos_demo.estado_demo()` una detrás de
otra, `punto_negro` dispara en los siete, con la misma frase de seguimiento repetida
palabra por palabra ("Conviene comprobar si el material está en log y todavía no se ha
normalizado."). Es la misma forma del hallazgo de banding/monotonía de los días 6-7: una
regla que dispara siempre no distingue nada sobre ESTE clip en particular.

**Por qué no se saca del catálogo, a diferencia de banding**: la evidencia de banding era
79 de 79 archivos REALES de Mario — una muestra real, variada, de trabajos de verdad. Esto
es 7 de 7 clips de un generador SINTÉTICO (`tests/media/generate.py`), construido para
otro propósito (probar el emparejamiento, no representar la distribución real de puntos
negros). No hay base para concluir que el patrón se repetiría en material real variado —
tan fácil es que sí como que las escenas sintéticas comparten, por construcción, un nivel
de negro parecido y el material real de Mario no. Sacar la regla con esta evidencia sería
sobre-reaccionar a una muestra de un solo generador.

**Qué hacer si se repite en material real**: si el día que haya footage real
`punto_negro` también dispara casi siempre, es la señal de tratarla igual que se trató
banding — o quitarla del catálogo, o cambiar el suelo (`_SUELO_NEGRO_VISIBLE`), o
replantear qué cuenta como "vale la pena decir algo" para esta característica. No se
decide aquí, sin esa evidencia.

## Por qué "opciones" mezcla intensidad y no genera looks nuevos

La tarea pide "tres o cuatro variantes de un look". Generar looks
CREATIVAMENTE distintos (más cálido, más contrastado, otro viraje) sería
inventar una decisión artística que este módulo no tiene forma de justificar
con nada medido — exactamente lo que la regla de honestidad del catálogo
prohíbe para las frases, y por coherencia se aplica también aquí. La
variable que SÍ se puede generar sin inventar nada es la INTENSIDAD: cuánto
del look elegido se dejan entrar, por interpolación lineal celda a celda
entre la identidad y la rejilla del look — un cálculo, no una decisión de
estilo. Ver `opciones.py`.

## Sin conexión (tarea 2.5)

El motor de reglas (`catalogo`, `explicar`, `ensenar`) es puro Python +
NumPy: nunca importa nada de `gui`, nunca abre un socket, nunca depende de
que haya red. La capa que SÍ puede usar red — reescribir la prosa de las
frases con mejor estilo, proponer direcciones creativas — vive fuera de
`core/` a propósito (ver `gui/tutor_estilo.py`): es una capa de
presentación, nunca de decisión. Si no hay red, `gui/tutor_estilo.py`
devuelve las frases del motor sin tocar ni una palabra — no hay ninguna
función de color ni ninguna explicación que dependa de tener conexión.

**Demostrado con `disponible=False` forzado (`tests/test_gui_tutor_estilo.py`), no
apagando la red física de la máquina.** Esta sesión corre en un Mac compartido con otras
sesiones activas al mismo tiempo (comprobado con `ListAgents` antes de empezar el día):
cortar la red de verdad habría afectado a ese trabajo ajeno para una comprobación que el
forzado determinista ya cubre igual de bien — `hay_red()` decide con una única llamada a
`socket.create_connection`, y `reescribir_frases`/`reescribir_lecciones` sólo miran ese
booleano, así que forzarlo prueba EXACTAMENTE el mismo camino de código que cortar la red
de verdad probaría, sin el riesgo. Ver `BITACORA.md`, entrada del día 8.
