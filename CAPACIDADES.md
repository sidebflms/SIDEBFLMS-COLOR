# CAPACIDADES — qué puede y qué no puede hacer SIDEBFLMS COLOR

Sin adornos. Lo que no está aquí, no está.

---

## Lo que la app hace

### Ordenar la casa: detectar la cámara de cada clip y avisar de la doble conversión
Antes de igualar nada, hay que saber en qué espacio de color viene cada clip. La app lee
los metadatos de cámara (fabricante, curva) y decide con una tabla explícita, citada:
Sony S-Log3, Panasonic V-Log, Canon C-Log3, DJI D-Log, o Rec.709 si ya venía convertido.

**Lo que no se sabe con seguridad, no se adivina.** Un clip sin metadatos reconocibles, o
con una curva que contradice el fabricante declarado, no se resuelve solo: se agrupa con
los demás clips parecidos y se pregunta una sola vez por grupo, en castellano llano
(«estos 42 clips parecen de la Sony, ¿lo son?»), con un fotograma de muestra al lado.

También avisa de la **doble conversión**: cuando el proyecto ya convierte el color de
entrada automáticamente y ADEMÁS hay un LUT de conversión puesto a mano, el color se
convierte dos veces y el resultado sale con más contraste y saturación de la cuenta, sin
ningún mensaje de error. Es el fallo silencioso más común con material mezclado.

**Escribir la decisión en Resolve todavía no se puede**: depende de que el probe confirme
que `SetClipProperty` acepta el espacio de entrada por clip (pregunta F0-7, sin
responder). Hoy la app detecta y pregunta; no escribe nada por su cuenta.

### Un modo para quien no es colorista
Dos modos, mismo motor. El **modo fácil** es un asistente de cinco pasos —ordenar la
casa, igualar, equilibrar, look, repasar— sin un solo ΔE, CDL ni porcentaje de cobertura
en pantalla: una frase en castellano de qué se hizo, un antes/después grande, y
deshacer. El paso final («repasar») no usa la nota de confianza —está sin calibrar, ver
abajo— sino dos señales que sí están medidas: qué clips no se parecen a la referencia, y
qué clips quedaron sin resolver en el primer paso. El **modo avanzado** es todo lo que
sigue en este documento, sin cambios.

### Igualar cámaras
Lleva varios planos al espacio de una referencia. Medido sobre material sintético con las
cuatro cámaras de la casa (FX3, Canon, Lumix, DJI): **ΔE2000 medio entre cámaras de 17.67
a 0.66**, y el peor par suelto se queda en 0.98. Con piel oscura sale igual o mejor.

Lo que sale es un **CDL**: diez números que puedes leer, entender y retocar a mano en el
nodo 2. No es una caja negra.

### Sacar el grado de un plano ya coloreado — y hasta dónde te lo puedes llevar
Le das el original y el coloreado del mismo plano y te devuelve el grado en dos capas: un
CDL y un LUT.

**Lo que hay que saber antes de usarlo, medido el 16-09-2026:**

- **En su propio plano funciona**, con matices: el ΔE2000 máximo queda por debajo de 3.0 en
  los montajes normales (2.89 en el más exigente), pero **con una escena muy rica de color
  no llega ni ahí** (4.00).
- **Con un solo plano, NO te lo lleves a otros planos.** Medido: el máximo pasa de 3.0 en 12
  de 12 casos, incluso en otra toma con la misma paleta.
- **Acumulando varios planos del mismo trabajo, sí.** Con el **modo por lote** y **3 planos o
  más**, el grado sirve en los demás planos de ese trabajo: peor máximo 1.67 con 3 planos,
  0.76 con 40. Y si el colorista corrigió algún plano por separado, el modo **te dice cuál y
  hacia dónde** en vez de mezclarlo a ciegas.
- **No sirve con secundarias estrechas** (una corrección de un solo tono): con 40 planos le
  sigue faltando 1.20. No es falta de datos: **un LUT no puede reproducir eso.**
- **No sirve para planos de otro trabajo.**
- **Los números del nodo 2 (el CDL) no son los que puso el colorista.** El ajuste se queda
  con parte del contraste del LUT. Úsalos como punto de partida, no como lectura del grado.

Y —esto es lo que no hace ninguna otra herramienta— te dice **qué parte del grado no cabe
en un LUT**, y de qué clase es:
| etiqueta | qué es | medido |
|---|---|---|
| **viñeta** | caída radial hacia los bordes | detectada con R² 0.88, y te da el centro estimado (a ~20 px del real) |
| **zona local** | una ventana o una secundaria | IoU 0.98 con la caja real |
| **degradado** | una rampa de un lado a otro del cuadro | — |
| **textura** | grano, enfoque, reducción de ruido | separado del resto por la energía de alta frecuencia |

Te dice además **qué porcentaje del grado te puedes llevar** en el `.cube` y te deja un
mapa de calor de dónde está lo que no se reproduce.

Un grano fuerte sale como **textura** y no como ventana; un h264 muy comprimido **no
dispara nada** y sigue diciendo que el grado cabe entero en un LUT. Los falsos positivos
importan tanto como los negativos, y ambos están probados.

### Decirte de qué se está inventando el color
Un solo plano cubre **165 celdas de las 35.937** de un LUT de 33³ — el **0.46%**. El otro
**99.5% está inventado** por el relleno de huecos, y conviene decirlo en voz alta al
entregar un `.cube`. La app te enseña un mapa con las celdas que tienen datos reales y las que
son invento. Eso no es un detalle: es la diferencia entre fiarte de un LUT y fiarte de
una suposición.

### Avisarte de que dos planos no son comparables
Un retrato de estudio contra un exterior al sol produce un número bonito y no significa
nada. La app lo marca, aunque la confianza salga alta.

### Controlar la calidad de un LUT
Caza no monotonía, escalones que provocan banding y excursión de gamut, dice en qué celda
y en qué eje, y un LUT identidad pasa limpio sin un solo aviso.

### Leer y escribir los formatos de verdad
`.cube` (17/33/65), HALD, ASC CDL (`.cc`/`.ccc`/`.cdl`), y su propio `.sidebcolor`. Ante
un fichero corrupto da un error **en castellano que dice qué pasa**, no un traceback.

Por defecto escribe **33³**, que es el estándar de facto. Puede **remuestrear a 65³ para
una entrega final**, como opción explícita y nunca por defecto — y lo dice claro: **no
añade información**. Como 65 = 2·33 − 1, el LUT de 65 es el mismo hasta el redondeo del
`float32` (desviación máxima 5.7e-08); lo único que cambia es que el fichero pasa de
0.93 MB a 7.07 MB.

### La confianza por clip: no la uses para decidir

**Medido el 16-09-2026: la confianza alta / media / baja no predice el error.** En la
ingeniería inversa vale «alta» casi siempre, también cuando el grado no sirve: el 96.5% de
los «alta» pasan del límite de 3.0 de máximo. Hasta que se rediseñe, **fíate del ΔE máximo
y de la cobertura del cubo, que sí están medidos**, y no de la palabra.

### No tocar tu grado
Todo se escribe en la versión `SIDEB COLOR`. El tuyo se queda en la suya, intacto. **No
es una convención: está impuesto en el código.** Si algo intenta escribir en la versión
del usuario, salta una excepción. Y si no se puede ni averiguar en qué versión está el
clip, tampoco escribe.

Ese último caso está probado a conciencia, porque es el más probable el primer día:
`GetCurrentVersion()` puede contestar una cadena vacía, un `None`, un diccionario sin las
claves esperadas, o reventar. **Las cuatro, por cada una de las cinco escrituras, dan
cero escrituras** y un mensaje que dice qué devolvió la API, que el sospechoso es la API
y no tú, y qué comando ejecutar. Hay una excepción escrita y sabida:
`set_group_post_clip_lut`, porque el grafo post-clip de un grupo de color no tiene
versiones.

**La interfaz no decide nunca** si un grado es «un LUT puro»: ese veredicto lo da el
núcleo y la pantalla lo pinta. Si el núcleo no ha podido contestar, la pantalla dice que
no se ha podido decidir — nunca se inventa una respuesta optimista.

---

## Lo que la app NO hace, y no va a hacer

**Porque la API de DaVinci Resolve no lo permite.** No es pereza ni falta de tiempo: no
existe la llamada.

- **No puede leer tu grado actual.** `GetCDL()` no existe. `SetCDL` es de sólo escritura.
  Todo lo que la app sabe de un clip lo saca de mirar los fotogramas, no de preguntarle a
  Resolve.
- **No puede tocar lift / gamma / gain por separado.** Sólo el CDL entero.
- **No puede tocar curvas.**
- **No puede crear, borrar ni reordenar nodos.** Por eso el diseño es de tres nodos y no
  de siete: son los que la app puede dar por supuestos.
- **No puede hacer qualifiers, power windows ni máscaras.**
- **No puede añadir ni configurar OFX / ResolveFX**, ni Color Warper, ni Magic Mask, ni
  Color Match.
- Sobre el nodo 1, el de normalización, **no hace nada**: comprueba que exista y avisa si
  no. La gestión de color del proyecto es tuya.

**Por decisión de diseño:**

- No toca material. No copia, no transcodifica, no renombra, no borra.
- No sale a internet. Nunca.
- No escribe fuera de las rutas que se le dan.

**Porque todavía no se ha probado con material real:**

- **Todo lo medido es sobre material sintético.** La primera prueba con un trabajo tuyo está
  preparada (`pruebas/COMO-HACER-LA-PRIMERA-PRUEBA.md`) y **garantiza no escribir ni un
  byte en tus discos de origen**, pero no se ha ejecutado.

**Porque todavía no se ha probado contra Resolve de verdad:**

- **Nada de lo anterior se ha ejecutado contra un Resolve real.** Toda la app habla hoy
  con un Resolve falso que simula el grafo de nodos, las versiones, los grupos y la
  galería. Hasta que pase el `probe/api_probe.py`, lo que hay es un motor probado y un
  puente sin estrenar. Ver `BITACORA.md`, apartados 5 y 6.

---

## Límites conocidos que conviene tener en la cabeza

- **Material log sin etiquetar se asume Rec.709.** Un S-Log3 sin metadatos se decodifica
  mal y todas las estadísticas salen plausibles y equivocadas. Sólo hay un aviso.
- **Una viñeta sola saca 7 «zona local» de más** en las esquinas, además de la viñeta. No
  es ruido: el LUT absorbe la viñeta de forma dependiente del color. Se podrían suprimir,
  pero el filtro se comería una ventana escondida bajo una viñeta fuerte, que es el lado
  peligroso. Lleva aviso escrito.
- **El modelo de viñeta es isótropo**: una viñeta ovalada o anamórfica no encaja.
- **La caja de la zona señalada puede equivocarse aunque el mapa de calor acierte.**
  Medido el 15-09-2026: con una viñeta y una ventana suaves, el 93.6% de los píxeles de
  mayor residuo caen dentro de la ventana real, pero la zona que se declara **principal**
  es un cuadrito en una esquina en sombra. **Fíate del mapa de calor antes que de la
  primera línea de la lista.** Ver `MEDICION-INDEPENDIENTE.md` §4.
- **El etiquetado de viñeta está calibrado para el dominio codificado.** Una viñeta óptica
  aplicada en luz lineal —que es lo que hace una lente de verdad— no lo dispara.
- **Los dos márgenes más ajustados**, sobre un montaje independiente: el ΔE2000 **máximo**
  de la ingeniería inversa queda a **0.11** del límite de 3.0, y el **peor par** del
  igualado de cámaras a **0.094** del límite de 2.0. Los titulares publican la media, que
  es la cifra holgada.
- **La huella de contenido no mira el color.** Dos escenas con la misma composición y
  colores distintos le parecen la misma.
- **Un plano sin gradar no vuelve exacto** por la ida y vuelta: deja 0.31 ΔE2000 de
  media, por el suavizado del relleno de huecos.
- **Los seis espacios de color son todos D65.** Si entra un DCI-P3, hay que probar la
  adaptación cromática antes de fiarse.
