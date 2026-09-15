# CAPACIDADES — qué puede y qué no puede hacer SIDEBFLMS COLOR

Sin adornos. Lo que no está aquí, no está.

---

## Lo que la app hace

### Igualar cámaras
Lleva varios planos al espacio de una referencia. Medido sobre material sintético con las
cuatro cámaras de la casa (FX3, Canon, Lumix, DJI): **ΔE2000 medio entre cámaras de 17.67
a 0.66**, y el peor par suelto se queda en 0.98. Con piel oscura sale igual o mejor.

Lo que sale es un **CDL**: diez números que puedes leer, entender y retocar a mano en el
nodo 2. No es una caja negra.

### Sacar el grado de un plano ya coloreado
Le das el original y el coloreado del mismo plano y te devuelve el grado en dos capas: un
CDL y un LUT. Sobre un grado conocido lo recupera con **ΔE2000 medio de 0.14 y máximo de
1.74** en la zona con datos.

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
Un solo plano cubre **165 celdas de las 35.937** de un LUT de 33³. El otro 99.5% está
extrapolado. La app te enseña un mapa con las celdas que tienen datos reales y las que
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
- **La huella de contenido no mira el color.** Dos escenas con la misma composición y
  colores distintos le parecen la misma.
- **Un plano sin gradar no vuelve exacto** por la ida y vuelta: deja 0.31 ΔE2000 de
  media, por el suavizado del relleno de huecos.
- **Los seis espacios de color son todos D65.** Si entra un DCI-P3, hay que probar la
  adaptación cromática antes de fiarse.
