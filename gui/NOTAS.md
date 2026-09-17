# NOTAS — `gui/`

Qué se decidió, qué se descartó y por qué.

**Una advertencia sobre este documento.** La interfaz la escribió el agente H la
noche del 14 al 15 de septiembre de 2026, y ese agente **murió por el límite de
la API antes de escribir una sola línea de estas notas**. Lo que sigue lo he
reconstruido yo (agente GUI · día 2) leyendo el código, los comentarios que sí
dejó, `git show fb8dfb1` y las capturas. Donde he podido deducir el porqué, lo
digo. Donde no, lo digo también: hay un apartado entero, el §10, que se llama
**«lo que no he podido averiguar»**, y está ahí a propósito. Una nota que dice
«esto no sé por qué es así» vale más que una explicación inventada que suene
bien.

Lo que empieza por **[día 2]** lo decidió el agente de GUI del día 2. Lo que
empieza por **[día 3]** lo he decidido yo.

---

## 1. La confianza se representa POR FORMA, y la forma es ésta

`gui/identidad.py:FormaConfianza` y `gui/widgets.py:pintar_insignia_confianza`.

| Nivel | Recuadro | Medidor | Color del trazo |
|---|---|---|---|
| `alta` | **relleno sólido** | 3 escalones de 3 | `brand-500` sobre relleno `brand-600` |
| `media` | **contorno continuo** | 2 de 3 | `brand-400` |
| `baja` | **contorno DISCONTINUO** | 1 de 3 | `brand-400` al 55% |

**Por qué esa forma y no un semáforo.** Dos motivos, y los dos están en
`docs/IDENTIDAD.md`:

1. **Verde/ámbar/rojo pisaría los tokens del inventario.** `#00d492`
   («Disponible»), `#ffb900` («Reservado») y `#ff6a3d` («Fuera») son de otro
   sistema en producción de la casa y están reservados. Un semáforo aquí diría
   cosas que no quiere decir a quien conoce el inventario.
2. **Y el rojo no es color de error en esta marca.** Una confianza baja no es
   una alarma ni una acción destructiva: es un número bajo. Pintarlo de rojo
   sería usar el vocabulario de «vas a borrar algo» para decir «este dato es
   flojo».

**Por qué relleno / contorno / contorno discontinuo y no tres intensidades del
mismo naranja.** Porque tres intensidades del mismo tono se distinguen mal en
una captura al 50%, se distinguen peor en una pantalla mal calibrada y no se
distinguen en absoluto en blanco y negro. Relleno contra contorno contra
contorno discontinuo es una diferencia de **geometría**, no de color: aguanta
las tres cosas. Está comprobado en
`tests/test_gui_identidad.py::test_las_tres_formas_se_distinguen_en_blanco_y_negro`,
que convierte las tres insignias a gris y exige que sigan siendo distintas.

**El medidor de escalones es redundante a propósito.** Repite la misma
información que la forma del recuadro. La redundancia es el punto: si alguien
mira la tabla de reojo, lo que ve son tres barritas llenas o una; si la mira de
cerca, lee «ALTA 97%».

**El nivel no lo decide la GUI.** `FormaConfianza.de_nivel()` traduce
`Confidence.level`, que viene de `core.contracts.confidence_level()`, que es el
único sitio del proyecto donde un número se convierte en alta/media/baja
(`CONTRATOS.md`). Aquí no hay ni un umbral, y hay un test que lo vigila
(`test_la_gui_no_reimplementa_confidence_level`).

---

## 2. El antes/después: se eligió la cortinilla

`gui/pantalla_comparar.py`. El docstring del módulo ya lo contaba y lo recojo
aquí porque es la decisión visual más grande de la app.

Se consideraron tres y se hizo **una sola, bien**:

* **Lado a lado — descartada.** Con 16:9 a la mitad de ancho cada plano queda
  pequeñísimo, y sobre todo: el ojo tiene que comparar dos sitios distintos de
  la pantalla. Para diferencias de 1-2 ΔE eso no funciona; es lo que hace que
  dos tomas parezcan iguales en una revisión y distintas en la sala.
* **Alternar (A/B parpadeando) — descartada como opción principal.** Es la que
  mejor detecta diferencias pequeñas, y el agente H lo dice. La descartó porque
  **no se puede capturar**: una captura de un parpadeo es una de las dos
  imágenes y ya, y este encargo se juzga con capturas.
* **Cortinilla — elegida.** El borde pone los dos planos *en contacto*, que es
  donde el ojo detecta una diferencia de color mínima, y una captura quieta
  enseña las dos mitades a la vez.

La cortinilla se arrastra con el ratón y se mueve con las flechas (Mayús para
fino, Inicio/Fin a los extremos), y la posición se lee en monoespaciada.

**El «después» no es una simulación.** Es `MatchResult.cdl.apply()`, o sea la
fórmula del contrato, que es exactamente la que Resolve ejecuta en el nodo 2.
Hay un test que lo comprueba comparando array contra array
(`test_el_despues_es_el_cdl_del_contrato_aplicado_al_antes`).

**La pantalla no arranca en la referencia.** `_primero_util()` salta el clip de
referencia, porque arrancar ahí deja la cortinilla enseñando la misma imagen a
los dos lados y los dos ΔE a 0.00: una pantalla de comparación que no compara
nada. Salía así en la primera tanda de capturas.

---

## 3. La anchura mínima real

**[día 4] 973 × 727.** El ancho no se ha movido; el alto sube 76 px. El motivo y
lo que se hizo para que no fuera más está en el §15. Y una corrección de método:
el alto se mide ahora **a la anchura mínima y en las cuatro pantallas**, no en la
ventana de 1440. Medido como antes saldría 713, que es un mínimo que la pantalla
de ingeniería inversa no cumple a 973 px (ahí la leyenda del mapa parte en dos
líneas).

**[día 3] Hoy son 973 × 651 px.** No es un número elegido: es lo que contesta
`VentanaPrincipal.minimumSizeHint()` después de un `ensurePolished()` sobre
todos los hijos, que es lo que hace `anchura_minima()`. Sin el `ensurePolished`
sale más pequeño de lo real y la captura sale engañosa.

**966 la noche del 14, 985 el día 2, 973 × 651 hoy.** Los dos cambios de hoy:

* **El ancho baja 12 px.** Las cinco columnas de cifras de la tabla de clips han
  dejado de medirse por su cabecera (§13). Ocupaban 439 px de los 492 de la
  tabla; ahora ocupan 345. La tabla pide 480 en vez de 492 y **el nombre del
  clip tiene sus 124 px garantizados**. Que la ventana encoja más no es un
  efecto secundario: es lo que sobraba de pagar por unas cabeceras de tres
  palabras.
* **El alto sube 8 px.** Las cifras grandes vuelven a ser grandes (§12). El
  panel de ingeniería inversa, que es el más alto de los cuatro, pide 564 px.

Y una comprobación que conviene tener: con el `font-size: 13px` aplanado puesto
otra vez sobre el árbol de hoy, la ventana pediría **1028 × 655**. La escala
aplanada no era «más pequeña»: era uniforme, y al subir a 13 px todo el texto
de 10, 11 y 12 salía **más ancha**.

**Era 966 la noche del 14. [día 2] Se subió a 985, y no para que algo quepa:**
se quitaron tres números puestos a ojo que se quedaban cortos.

| Dónde | Decía | Necesita de verdad |
|---|---|---|
| columna derecha del panel de ingeniería inversa | 300 px | **366** — para que «cabe en un .cube», «ΔE medio», «ΔE p95» y «ΔE peor» quepan en la misma fila |
| ficha del clip (`FichaClip`) | 240 px | **246** — para el rótulo «desajuste de contenido» con su rombo delante |
| rótulos de acento (`Rotulo(acento=True)`) | fuente construida a 10px | **11px**, que es lo que la hoja de estilo pinta; el tracking absoluto se quedaba en el de 10px y salía 0,145em donde la identidad pide 0,15-0,18 |

Los tres eran bugs de recorte de texto de verdad, contados en el §9.

**Qué es lo que fija esa anchura.** Las piezas que no pueden encoger sin mentir:
la tabla de clips con sus columnas de cifras y su insignia, los tres campos de
cuatro decimales del editor de CDL, y la fila de cuatro rótulos del
diagnóstico. Todo el texto variable (nombres de clip, rutas, avisos) va en
widgets que se recortan con puntos suspensivos o en vistas que eliden solas, y
por eso **no** empuja el mínimo hacia arriba.

**[día 2] Y ahora la anchura mínima no depende del estado.** Antes, con cero
clips, la tabla se escondía; un widget escondido no cuenta para el layout, y la
ventana se dejaba encoger hasta 911 px. Ahí sí se recortaba texto. `PantallaClips`
fija ahora su anchura mínima en el constructor, con la tabla y la ficha como
testigos, y ya no se mueve.

**Ojo con las tipografías.** 973 es el número **con las alternativas** (Helvetica
Neue y Menlo). Si Mario instala Inter, Chakra Petch y JetBrains Mono, las
métricas cambian y el número también. No es un fallo, es otra tipografía; el
test que fija el número se salta solo si detecta alguna de las tres instalada.

---

## 4. Los colores que hicieron falta y no estaban en la identidad

`docs/IDENTIDAD.md` trae nueve colores y ni uno más. Hicieron falta cuatro cosas
que no están:

| Qué hacía falta | Qué se hizo | Por qué |
|---|---|---|
| texto secundario | `brand-50` al **62%** | la identidad no trae un token de texto apagado |
| texto tenue | `brand-50` al **40%** | ídem |
| borde | `brand-50` al **12%** | ídem |
| borde fuerte | `brand-50` al **22%** | ídem |

**La regla que se siguió: bajar la opacidad de un color que sí está, nunca
mezclar hexadecimales a ojo.** Y hay un motivo concreto para no inventar grises:
`#71717b` es el gris «De baja» del inventario, y cualquier gris que se inventara
acabaría pareciéndose. Está en el docstring de `idn.rgba()`.

Hay un test que comprueba que en `gui/identidad.py` no aparece ni un
hexadecimal que no sea de la identidad o de la lista de tokens del inventario
(`test_la_paleta_de_la_gui_es_exactamente_la_de_la_identidad`), y otro que barre
`gui/` entera buscando cualquier «rojo de alarma»
(`test_no_hay_ningun_rojo_de_error_en_toda_la_gui`).

**Sobre `#3ad6cf`.** Es a la vez `cyan-glow` («único, para datos secundarios») y
el token de estado «En taller». Se usa **sólo** como color de texto o de línea
para datos secundarios: el ΔE después de la tabla, las cifras de referencia.
Nunca con tratamiento de pastilla. Es la misma interpretación que
`docs/IDENTIDAD.md` hace con `#ff6a3d`.

---

## 5. `#ff6a3d`: como texto e iconos sí, como pastilla nunca

Esto Mario lo ha confirmado y **está escrito en `gui/identidad.py`, junto a
`BRAND_400`**, para que se vea al ir a usar el color y no en un rincón.

En pastilla (fondo al 12%, borde al 25%, texto pleno) ese hexadecimal significa
**«Fuera»** en el inventario de SIDEBFLMS. Pintar aquí una pastilla `#ff6a3d`
diría «Fuera» a cualquiera que conozca el inventario y contaminaría los dos
sistemas a la vez.

Lo que sí se hace, porque es su función declarada: texto, iconos, líneas y
trazos de marca sobre superficie oscura.

**Es comprobable**, y se comprueba de tres formas, porque una pastilla se puede
pintar de tres (`tests/test_gui_identidad.py`):

1. **Por hoja de estilo** — ninguna declaración de `background` de
   `hoja_de_estilo()` lleva `#ff6a3d` ni su `rgba(...)`.
2. **Por `setStyleSheet` local** — se lee el árbol de sintaxis de `gui/*.py` y
   ninguna llamada a `setStyleSheet` pone fondo con ese color.
3. **Pintando** — se renderiza la insignia de confianza, que es **la única
   pastilla de la app**, en los tres niveles, y se le mira un píxel de dentro:
   `alta` sale `brand-600`, `media` y `baja` salen el fondo. Ninguna sale
   `#ff6a3d` ni una mezcla suya.

**Lo que sí lleva `#ff6a3d` con relleno es el rombo de desajuste**, y no es una
excepción: es que un rombo no es una pastilla. Es la única forma de rombo de
toda la interfaz y hay un test que comprueba que las cuatro esquinas de su caja
siguen siendo fondo, que es justo lo que una pastilla no haría.

---

## 6. Cómo se protege el texto del recorte

Ésta es la parte que más trabajo ha dado, porque el recorte de texto al
redimensionar es el fallo recurrente de la app hermana de ingest.

### `EtiquetaElidida` (`gui/widgets.py`)

Un `QLabel` normal pide de **ancho mínimo lo que mida su texto entero**. O sea
que un solo nombre de clip de 120 caracteres hace que la ventana no se pueda
encoger. `EtiquetaElidida` le da la vuelta con tres piezas, y las tres importan:

* **`sizeHint()`** devuelve el ancho del texto entero, para que en una ventana
  holgada el layout le dé lo que necesita.
* **`minimumSizeHint()`** devuelve `ancho_minimo_px` (40 por defecto), para que
  al estrujar la ventana el widget **ceda** en vez de empujar la anchura mínima
  hacia arriba. **Ésta es la pieza que arregla el fallo de ingest.**
* **El texto se recorta contra el ancho MENOS los márgenes**, no contra
  `width()` a secas. Con márgenes puestos, `width()` se pasa por lo que midan
  los márgenes y el texto sale cortado a lo bruto justo en el borde. Fue un bug
  real de la noche del 14: el pie del carril salía como «escribe en «SIDEB
  COLOF».

Y siempre que elide, el texto entero se queda en el **tooltip**. Nada se pierde.

### `Rotulo` — y por qué NO cede ancho

`Rotulo` hereda de `EtiquetaElidida`, y el agente H lo hizo así para que un
rótulo largo pusiera puntos suspensivos en vez de comerse la última letra en
silencio.

**[día 2] Le he cambiado el `minimumSizeHint()`: ahora devuelve el texto
entero.** Un rótulo es el vocabulario fijo de la app —lo escribe la app, es
corto, y está puesto para decir qué es cada cosa—, así que recortado no informa
de nada: «SLO…» no es «slope» y «CABE …» no es «cabe en un .cube». Si un rótulo
no cabe, lo que tiene que crecer es la anchura mínima de la ventana, que para
eso se mide.

La maquinaria de elidir se queda como **último recurso**: si alguien le pone un
`setMaximumWidth` por encima, saldrá con puntos y con el texto en el tooltip en
vez de cortarse a hachazos. Pero hay un test que comprueba que ese último
recurso no se usa en ninguna pantalla.

### El criterio del test, que es la parte difícil

`tests/test_gui_texto.py`. El problema es que `EtiquetaElidida` **sí** puede
elidir a propósito, así que el test tiene que distinguir «esto elide por diseño»
de «esto elide porque no cabe». El criterio que he elegido son tres reglas:

1. **Un `Rotulo` no elide nunca.** Vocabulario fijo, corto, escrito por la app.
2. **Una `EtiquetaElidida` que no es rótulo sí puede elidir**, porque lleva
   CONTENIDO de longitud desconocida (nombres de clip, rutas, el resumen del
   proyecto). Con dos condiciones que también se comprueban: el texto entero
   tiene que seguir en el tooltip, y lo que se ve tiene que ser un trozo útil
   (≥ 12 caracteres), no «A…».
3. **Un `QLabel` normal no puede quedarse corto.** Un `QLabel` a secas **no
   elide**: se come lo que no le cabe sin puntos suspensivos, sin tooltip y sin
   avisar. Para ésos la regla es que el texto quepa entero. Con `wordWrap` lo
   que tiene que caber es la palabra más larga, porque Qt parte por espacios
   pero no parte una palabra.

Y dos cosas que hacen que el test sea creíble:

* **Los detectores se prueban a sí mismos** en `tests/test_gui_apoyo.py`. Un
  detector de recorte que por un despiste no mirara nada pasaría siempre.
* **Hay dos controles negativos** que estropean la interfaz a propósito
  (`test_el_test_falla_si_un_rotulo_se_recorta` y su gemelo para `QLabel`) y
  comprueban que el detector lo caza. Un test de recorte que no se puede hacer
  fallar no vale nada.

El barrido se hace a la **anchura mínima real que diga Qt** (no a la constante),
sobre las cuatro pantallas y en siete estados: nominal, cero clips, un clip,
doscientos clips, confianza baja, Resolve desconectado y LUT que no pasa el QC.

---

## 7. La regla de oro, desde la interfaz

La pantalla de aplicar **no llama nunca a `set_cdl` ni a `set_lut` a pelo**. Todo
pasa por `core.resolve.aplicar_grado_seguro`, que crea o selecciona la versión
`SIDEB COLOR` antes de escribir un solo número.

Está comprobado de cuatro formas en `tests/test_gui_regla_de_oro.py`: espiando
`aplicar_grado_seguro`, mirando en qué versión cayeron las escrituras, mirando
que los nodos de `Version 1` siguen sin CDL y sin LUT, y leyendo el árbol de
sintaxis de `gui/` en busca de una llamada cruda o de la vía de escape
`PELIGRO_escribir_fuera_de_la_version`.

**No encontré ningún camino en la GUI que escriba sin pasar por ahí.**

**Hoy la GUI no copia grados de un clip a otro**, y está dejado por escrito a
propósito, no es un olvido: `copiar_grado_seguro` existe en el puente y es el
único camino seguro para `CopyGrades`, pero la interfaz no lo usa porque cada
clip lleva su propio CDL calculado contra la referencia. Hay un test que fallará
el día que aparezca un botón de «copiar a los demás», para que ese botón tenga
que salir por `copiar_grado_seguro`.

---

## 8. [día 2] La GUI no da veredictos

`gui/reverse_puente.py` tenía su propia definición de «es un LUT puro»:

```
GUI:     puro = reproducible > 0.92 and not puntos
núcleo:  reproducible >= 0.95  Y  p95 <= 1.0 ΔE2000
```

Tres cosas mal:

1. **Incumple `CONTRATOS.md`**: no se redefinen umbrales fuera del sitio donde
   viven. El sitio donde un número se convierte en un veredicto tiene que ser
   uno solo.
2. **Se salta el percentil 95**, que es justo la mitad de la condición del
   núcleo y la que impide que una media buena esconda un p95 malo.
3. **No era código muerto.** `invertir()` se cae al sustituto ante **cualquier**
   excepción de `core.reverse`, así que un fallo del núcleo degradaba en
   silencio al criterio permisivo, y con ese criterio la pantalla llega a
   escribir «Es un LUT puro: todo el grado cabe en el .cube».

Esa frase es la más peligrosa que puede decir esta app: manda a Mario a llevarse
un `.cube` que no reproduce el grado y a enterarse delante de un cliente. La
contraria sólo le hace trabajar de más.

**Lo que hay ahora:**

* El sustituto pone `is_pure_lut = False` **siempre**, y lo dice en las notas:
  no es «he medido que no lo es», es «aquí no se decide eso». Es el lado seguro
  del error.
* `invertir()` devuelve una `Inversion` con `del_nucleo` y `fallo`. La pantalla
  mira eso antes de pintar nada.
* Si el veredicto no viene del núcleo, la pantalla escribe **«No se ha podido
  decidir si es un LUT puro»**, que no es lo mismo que «no es puro» ni, sobre
  todo, que «es puro».
* **Y la caída se ve**: hay un aviso propio en la pantalla —«esto no lo ha
  calculado core.reverse»— con la excepción que saltó. Caerse a un sustituto
  está bien para poder trabajar; caerse en silencio a uno más permisivo, no.
  Está capturado en `capturas/16-reverse-sustituto.png`.
* El sustituto **tampoco clasifica las zonas calientes**. Antes etiquetaba como
  «viñeta» cualquier bloque que tocara un borde de una rejilla de 6×6, que es
  inventarse una afirmación sobre el grado a partir de dónde cae un cuadrado.
  Ahora pone «zona con residuo alto (sin clasificar)».

**Una precisión honesta sobre el alcance:** en el par de demostración el
criterio viejo **no llegaba a dispararse**, porque con un solo fotograma el
sustituto se lleva como mucho el 0,80 del grado. O sea que era una trampa
latente, no algo que ya estuviera saliendo en pantalla. Lo grave era que
existiera, y en un camino al que se cae ante cualquier excepción.

**Busqué más umbrales duplicados en `gui/` y no hay ninguno más.** Lo que queda
son umbrales de **redacción** o de **dibujo**, que no son veredictos y van con
nombre y comentario: `COBERTURA_BAJA_AVISO` (si se escribe una frase de aviso),
`DESTAQUE_MINIMO_BLOQUE` (si se dibuja un recuadro) y `BarraProporcion.umbral_hueco`
(si el resto de la barra se pinta discontinuo). Hay tres tests que barren `gui/`
con el árbol de sintaxis buscando comparaciones de una medida contra un número
suelto, `is_pure_lut=` con cualquier valor que no sea `False`, y cualquier uso
de `CONFIDENCE_ALTA` / `CONFIDENCE_MEDIA`.

---

## 9. [día 2] Los bugs que aparecieron al escribir los tests

Todos arreglados salvo el último, que está como `xfail` con el límite explicado.

1. **Los rótulos del panel de ingeniería inversa se recortaban a 911 px.**
   «reji…», «cabe …», «mapa de cobertu…», «residuo espaci…». Sólo se llegaba a
   911 con el timeline vacío, porque al esconderse la tabla la ventana se dejaba
   encoger por debajo de su mínimo de siempre. Dos arreglos: la columna derecha
   ya no declara 300 px a ojo (Qt le calcula 366 del contenido) y la anchura
   mínima de la pantalla de clips ya no depende de cuántos clips haya.
2. **«desajuste de contenido» salía como «desajuste de conteni…» a la anchura
   mínima**, y salía justo cuando hay desajuste, que es cuando hace falta
   leerlo. La ficha declaraba 240 px de mínimo y necesita 246. Ahora se mide, y
   se mide **antes** de esconder el bloque, para que el mínimo no dependa de qué
   clip esté seleccionado.
3. **Los diez números del CDL de «antes/después» no salían en monoespaciada**, y
   los datos del LUT del panel de ingeniería inversa tampoco. Se les ponía
   `setFont(fuente_cifra(11))` a mano, pero **la hoja de estilo pisa a
   `setFont()`**: si ninguna regla del QSS que aplique al widget declara
   `font-family`, gana la regla `QWidget { font-family: Inter... }`. Se veía en
   la captura vieja `02-comparar-966`: las cuatro líneas del CDL no alineaban.
   Arreglado con un id propio (`QLabel#cifraApagada`) que sí declara la
   monoespaciada. **Incumplía una regla firme de la identidad.**
4. **El tracking de los rótulos de acento era 0,145em**, por debajo del
   0,15-0,18 de la identidad. Mismo origen: la fuente se construía a 10px y el
   QSS la pinta a 11px; el tracking absoluto (que el QSS no puede expresar) se
   quedaba en el de 10.
5. **«1 clips»** en el pie con un solo clip.
6. **La columna CLIP se quedaba en 56 px a la anchura mínima** y enseñaba «A…a»
   (a 1024 px, en 66: «A00…oma»). **[día 3] Arreglado, y está en el §13.** Lo
   que sigue es el diagnóstico del día 2, que era correcto. El resumen:
   `PantallaClips.ancho_minimo_util()` promete 124 px de nombre pero se equivoca
   al estimar —da 356 px a las cinco columnas fijas y de verdad ocupan 441,
   porque `ResizeToContents` las mide por el texto de la **cabecera** (fuente de
   rótulo con tracking), no por la cifra—. Garantizar los 124 px cuesta 82 px
   más de tabla, o sea 1063 px de ventana; y **por encima de 1024 la segunda
   anchura de captura de `docs/IDENTIDAD.md` deja de poder existir**. No es un
   arreglo, es una decisión de presupuesto de píxeles entre tres salidas
   —ventana más ancha, cabeceras más cortas, o insignia de confianza más
   estrecha— y ésa la toma Mario.

---

## 10. Lo que NO he podido averiguar

Va aparte y con su nombre, porque inventarme el porqué sería peor que dejarlo en
blanco.

1. ~~**Por qué `Cifra` acepta un `px=` que la hoja de estilo ignora.**~~
   **[día 3] RESUELTO, y era un bug, no una decisión de diseño.** Lo ha dicho
   Mario: lo que aprobó no es «la interfaz de 13 px uniformes», es un accidente
   con la jerarquía aplanada. La causa, la evidencia y el arreglo están en el
   §12. La pista que el día 2 apuntaba —la regla `#cifraGrande` que no usaba
   nadie— era buena: el agente H creía que los `px=` funcionaban.
2. **Por qué el sustituto de `reverse_puente` usa una rejilla de 17 y no de 33.**
   El comentario dice que es «un motivo de pantalla, no de calidad» —con 33 el
   mapa de cobertura sale prácticamente en negro— y eso me parece razonable y
   comprobable. Lo que no sé es si además se midió el coste en calidad de
   invertir a 17, o si se dio por bueno porque el sustituto era provisional.
3. ~~**Por qué `INSIGNIA_ANCHO` es 108 y no otro número.**~~ **[día 3] Medido:
   no sale de ningún sitio y además se queda corto.** Con el reparto que hace
   `pintar_insignia_confianza`, «ALTA 97%» necesita 99 px y «MEDIA 100%»
   necesita 115. Hoy no se ve porque una confianza del 100% sale `alta` y
   «ALTA» es la palabra más corta, o sea que es una trampa latente y no un
   fallo en pantalla. **No lo he subido a 115**: la columna CONFIANZA mide
   `INSIGNIA_ANCHO + 16` y es la más ancha de las fijas de la tabla, así que
   subirla sube la anchura mínima de la ventana, que es justo lo que el encargo
   de hoy pedía no hacer. Está anotado junto a la constante.
4. **Por qué `fila_dato()` existe.** Está exportada en `widgets.py` y **no la
   usa nadie**. Puede ser una pieza de una versión anterior del diseño o algo
   que se dejó preparado. La he dejado (le he quitado un `setMinimumWidth(0)`
   que contradecía la regla nueva de los rótulos), pero no sé para qué es.
5. **Por qué el submuestreo de `datos_demo` es `[::4]` y el del lote `[::8]`.**
   El comentario da el tiempo (0,15 s contra 0,08 s por clip) y dice que el CDL
   sale igual hasta el cuarto decimal, o sea que está medido. Lo que no sé es
   por qué 4 y 8 y no 2 y 6: no hay tabla de barrido.
6. **Si el orden de las cuatro pantallas se decidió o salió solo.** Clips →
   comparar → aplicar → ingeniería inversa es un orden de trabajo natural, pero
   no hay nada escrito.

---

## 11. Decisiones menores, por si alguien las revisa

* **`QTextBrowser` y no `QLabel` para el plan y el diagnóstico.** Un `QLabel`
  con texto enriquecido pide de ancho mínimo el de su línea más larga, y con la
  barra horizontal apagada eso no se ve como una barra que falta: se ve como
  texto cortado. El `QTextBrowser` envuelve y desplaza.
* **Punto decimal y no coma en el editor de CDL.** La configuración regional de
  este Mac es española y Qt escribía «1,1510»; pero un CDL se lee y se escribe
  con punto en los `.cc`, los `.cdl` y los `.cube`. Dos notaciones en la misma
  pantalla es una invitación a teclear mal un número. Se fuerza `QLocale.C`.
* **«sat» y no «saturación» en el editor de CDL.** No es por falta de sitio en
  abstracto: con la palabra entera esa columna se come 30 px que a la anchura
  mínima le hacen falta a los campos. «SAT» es como viene rotulado en cualquier
  panel de CDL.
* **«residuo espacial» y no «en el fotograma».** El segundo se recortaba a la
  anchura mínima; el primero cabe, dice lo mismo, y además es el nombre del
  campo del contrato (`ReverseDiagnosis.spatial_residual`), así que une los dos
  vocabularios.
* **El pie del carril va en dos líneas y NO elide.** «escribe en «SIDEB COLOR»»
  es la promesa de la app y salía cortada como «escribe en «SIDEB COL…» incluso
  a 1440, porque el carril mide 186 px fijos. Cortar justo el nombre de la
  versión deja la frase diciendo la mitad de lo que tiene que decir.
* **`QLabel { background: transparent }` en la hoja de estilo.** Sin esa regla,
  la de `QWidget` les daba `#0a0908` y encima de un panel cada rótulo salía con
  su propio rectángulo negro detrás. Se veía en toda la primera tanda.
* **El mapa de cobertura distingue por TEXTURA, no por color.** Celda medida =
  parche relleno; celda inventada = tablero de ajedrez de dos tonos de
  superficie. Se lee en blanco y negro y no toma prestado ningún token del
  inventario. Hay un test que comprueba los dos tonos del tablero y que una
  celda medida no se pinta igual que una inventada.
* **El mapa de residuo es una rampa MONOCROMA de la familia de marca** (fondo →
  brand-600 → 500 → 400 → brand-50). Lo que cambia es la luminosidad, no el
  tono: no hay ningún semáforo escondido ahí.
* **Los tamaños de imagen se pintan sin suavizar** en `VistaMapa`: una celda del
  cubo es una celda, no un degradado.
* **`a_qimage()` copia los bytes.** `QImage` no toma posesión del buffer de
  numpy y si el array se libera, Qt pinta basura. Es un fallo que sólo se ve en
  la captura, o sea tarde.

---

## 12. [día 3] La escala tipográfica estaba rota, y la causa era una línea

### Qué pasaba

Todas las cifras grandes salían a 13 px: los 22 px del ΔE de la ficha del clip,
los 24 del «lo que cambia» de antes/después, los 26 del «cabe en un .cube». Y no
sólo las cifras: **el texto de cuerpo también**. Los 15 px del nombre del clip
en la ficha, los 12 del nombre de la referencia, los 10 del pie del carril —
todos a 13. La jerarquía entera aplanada, y en las dos direcciones: lo grande
encogía y lo pequeño crecía.

Medido sobre la ventana entera antes de tocar nada: **96 widgets pedían una
fuente de la identidad y 41 no conseguían el tamaño (o la familia) que pedían.**

### La causa, con la evidencia

Era esta línea de `hoja_de_estilo()`:

```
QWidget { ...; font-family: Inter...; font-size: 13px; }
```

Dos cosas que hay que saber de Qt para leerla:

1. **`QWidget` casa con TODOS los widgets de la app**, no sólo con los que son
   literalmente un `QWidget`. Un selector de tipo casa también con las
   subclases.
2. **Una propiedad de fuente declarada por una regla que casa le gana a
   `setFont()`**, y la mezcla es *por propiedad*: lo que la regla declara lo
   pone la regla, y lo que no declara se queda como lo dejó el widget.

O sea que esa línea le declaraba `font-size: 13px` a cada widget de la
interfaz, y ahí acababa cualquier `px=`. La regla `QLabel.cifra` sólo declara
`font-family`, así que la familia monoespaciada sí llegaba — y por eso se veía
sólo como «todas las cifras del mismo tamaño» y no como «las cifras salen en
Inter».

La prueba, en tres medidas sobre la misma etiqueta (una `QLabel` con
`setFont(fuente_cifra(26))` y la clase `cifra`):

```
sin hoja de estilo                          familia=JetBrains Mono  px=26
con la hoja del día 2                       familia=JetBrains Mono  px=13   <-- el bug
con la hoja sin font-size en QWidget        familia=JetBrains Mono  px=26
```

Y la mezcla por propiedad, en la misma tanda: `QLabel#titulo` declara
`font-weight: 700` y el código pedía 600 → sale 700 (gana la regla); no declara
tamaño → se queda el del `setFont()` (gana el código).

Eso **refina** lo que el auditor del día 2 midió («el QSS no compite con
`setFont()`, lo borra»). Lo que borraba era lo que declaraba, que resultaba ser
familia y tamaño para todo el mundo.

### El arreglo, y la regla que lo sostiene

**En la hoja de estilo no se declara `font-size` en ninguna regla. El tamaño lo
decide `fuente_texto()` / `fuente_cifra()` / `fuente_rotulo()` y nadie más.** El
tamaño base de la app lo pone `QApplication.setFont(fuente_texto(13))` en
`crear_app()`, que sí cede ante el `setFont()` de un widget.

Se le quitó el `font-size` a cinco reglas: `QWidget`, `QLabel#rotulo`,
`QLabel#titulo`, `QLabel#cifraApagada` y `QPushButton#navegacion`. Y se borró
`QLabel#cifraGrande`, que no usaba nadie y era una trampa esperando a que
alguien le pusiera ese id a una cifra de otro tamaño.

**La familia sí se queda en `QWidget`**, a propósito: es la única declaración
de fuente que interesa universal (que nada salga en la del sistema por un
descuido), y la de cada rol la traen las reglas de debajo. La contrapartida es
que un `setFont(fuente_cifra(...))` sobre una etiqueta sin marcar sigue sin dar
monoespaciada — que es justo lo que le pasaba a `ruta_look`, ver abajo.

**La excepción, con motivo medido: `QHeaderView::section`.** Es la única regla
que declara un tamaño, porque la cabecera de una tabla es un pseudo-elemento y
**no hay forma de vestirla desde el código**. Las dos que parecía que valdrían
están comprobadas y no valen:

* `QHeaderView.setFont(fuente_rotulo(10))` → Qt se la borra en el siguiente
  `polish` y la deja en la heredada (medido: pasa de «Chakra Petch 10 px» a
  «Inter 13 px» en cuanto el layout se asienta).
* `headerData(..., Qt.FontRole)` → el dibujo de la cabecera **no cambia ni un
  píxel**; manda la regla.

Consecuencia que hay que saber: como QSS no sabe escribir el tracking, **las
cabeceras de la tabla son el único rótulo en mayúsculas de la app que va sin el
0,15-0,18em de la identidad**. Para poder medir con la misma letra con la que se
pinta existe `idn.fuente_cabecera_tabla()`.

### Rol por rol, cómo quedó

| Rol | Antes | Ahora |
|---|---|---|
| texto de cuerpo (10, 11, 12, 13, 15 px) | **roto**, todo a 13 | cada uno el suyo |
| rótulos en mayúsculas (10 / 11 px) | bien: 0,1594em y 0,1591em | igual, y ahora el tamaño y el tracking salen los dos de `fuente_rotulo(px)` |
| cifras normales (11, 12, 13 px) | **roto** en 11 y 12 | cada una la suya |
| cifras grandes (17, 18, 22, 24, 26 px) | **roto**, todas a 13 | cada una la suya |
| código, rutas e IDs | **roto** en la ruta del `.cube` | monoespaciada de verdad |
| cabecera de tabla | 10 px sin tracking, y Qt la **medía** con otra letra (13 px) de la que **pintaba** | 10 px sin tracking (límite de Qt), medida con la misma que se pinta |

Tres cosas más que salieron al mirar rol por rol:

* **`ruta_look` (`pantalla_aplicar.py`)** pedía `fuente_cifra(11)` y salía en la
  de texto, porque sin la clase `cifra` la única regla que le declaraba familia
  era la universal. Es la ruta del `.cube`: una ruta con espacios elidida por el
  medio, o sea el sitio donde más se nota. Arreglado con
  `setProperty("class", "cifra")`.
* **Los dos bloques `#cifraApagada`** (el CDL de antes/después y los datos del
  LUT) ya no sacan el tamaño de la hoja: el id les da la familia y un
  `setFont(fuente_cifra(11))` el tamaño.
* **El selector de clip de antes/después** pedía `fuente_texto(13)` y la hoja lo
  pintaba monoespaciado, porque `QLineEdit, QComboBox...` declara la familia de
  cifra. Se ha cambiado la petición a `fuente_cifra(13)`, que además es lo
  correcto: lo que lista son nombres de clip, o sea identificadores. Pedir una
  cosa y pintar otra es el despiste que ha costado la escala entera.

### Lo que impide que vuelva

* `test_el_selector_universal_no_declara_tamano_de_letra`
* `test_la_hoja_de_estilo_solo_declara_un_tamano_de_letra_y_es_el_de_la_cabecera`
* `test_cada_widget_se_pinta_con_el_tamano_de_letra_que_pide` — el de fondo:
  intercepta cada `setFont()` de la construcción de la ventana entera y compara
  lo pedido con lo pintado, tamaño, familia y tracking.
* `test_la_ruta_del_cube_va_en_monoespaciada`

---

## 13. [día 3] Los anchos de columna: ceden los ΔE, no el nombre

**Decisión de Mario.** Un ΔE es un número de formato acotado; un nombre de clip
es lo que te dice qué fila estás mirando.

Lo que había: las cinco columnas que no son el nombre iban a `ResizeToContents`,
que **las mide por el texto de su cabecera** (que es lo más ancho que hay en
ellas, no la cifra), y la del nombre estiraba con un suelo de 56 px. A la
anchura mínima las cinco se llevaban 439 px de los 492 de la tabla y el nombre
se quedaba en 56: «A…a».

Lo que hay ahora:

* **Las cinco llevan un ancho fijo calculado**, `PantallaClips.anchos_fijos()`.
  Cada una se lleva lo que necesite la más ancha de sus dos cosas: la cifra (en
  monoespaciada de 12) o su propia cabecera (en la letra con la que el QSS la
  pinta). La del nombre es la única que estira.
* **Un solo cálculo para dos usos.** Con `anchos_fijos()` se fijan las columnas
  y con `anchos_fijos()` se calcula `ancho_minimo_util()`. Ése era el fondo del
  problema: el día 2 eran dos cuentas distintas y se llevaban 85 px de
  diferencia.
* **Los dos rótulos de ΔE van en dos líneas.** «ΔE DESPUÉS» seguido mide 63 px
  y obliga a una columna de 83; partido en «ΔE» / «DESPUÉS», la palabra más
  ancha mide 47 y la columna baja a 67. Los 16 px por columna son los que se
  lleva el nombre. **No se abrevia ninguna palabra**: «ΔE DESP.» habría costado
  lo mismo y diría menos.
* **`ancho_minimo_util()` cuenta ahora el envoltorio**: la barra de
  desplazamiento vertical (siempre puesta con doscientos clips) y los dos bordes
  del marco. Sin contarlos, los píxeles que faltan salen de la columna que
  estira, o sea del nombre.

Medido, con doscientos clips:

| ventana | columna CLIP antes | columna CLIP ahora |
|---|---|---|
| anchura mínima | 56 px («A…a») | **124 px** |
| 1024 px | 81 px | **175 px** |
| 1440 px | 361 px | **455 px** |

Y las cinco fijas pasan de 439 px a 345: `#` 42, ΔE antes 63, ΔE después 67,
confianza 124, aviso 49.

**Sin subir la anchura mínima**: ha bajado de 985 a 973. El `xfail(strict=True)`
de `test_la_columna_del_nombre_de_clip_no_desaparece` **se ha quitado** y el
test pasa de verdad. Y hay uno nuevo,
`test_ninguna_cabecera_de_la_tabla_sale_recortada`, que le pregunta al estilo
cuánto hueco le deja de verdad al texto de cada sección: si alguien alarga un
rótulo de cabecera o toca `RELLENO_CABECERA_PX`, salta antes que una captura.

---

## 14. Qué probar la próxima vez

* **La ventana no se ha probado a más de 1440 px.** Los `setMaximumWidth` del
  lateral de comparar (300) y del selector de clip (460) no se han mirado en una
  pantalla de 2560.
* **No hay ni un test de teclado de verdad** (`QTest.keyClick`). La cortinilla se
  mueve llamando a `set_posicion()`, que es lo que hace el manejador, pero el
  manejador en sí no se ejercita.
* **Las capturas no enseñan la tipografía de la marca.** Inter, Chakra Petch y
  JetBrains Mono no están instaladas en este Mac. El layout, el color, los
  tamaños y el tracking sí son los buenos; las letras no.
* **[día 3] Las cabeceras de la tabla van sin tracking**, y es un límite de Qt,
  no un descuido: son un pseudo-elemento de QSS, QSS no sabe escribir el
  tracking y ni `setFont()` ni `Qt.FontRole` llegan hasta ahí (§12). La salida
  sería un `QHeaderView` propio que se pinte las secciones él. No está hecho.
* **[día 3] `INSIGNIA_ANCHO` se queda 7 px corto para «MEDIA 100%»** (§10.3).
  Hoy no se ve; subirlo sube la anchura mínima de la ventana y hoy no tocaba.
* **[día 3] Nadie ha visto la interfaz a más de 1440 px** (sigue del día 2), y
  ahora además con la escala tipográfica de verdad.

---

## 15. [día 4] La cifra que decide, delante

**El encargo.** Hasta el día 3 el panel de ingeniería inversa ponía grande «cabe
en un .cube» y pequeñas las tres cifras de ΔE, con el máximo (rotulado «ΔE
peor») la última y en color secundario. Pero el criterio T1 lo suspende el
**máximo**, y medido desde fuera se queda a 0.11 del límite; la media es la cifra
holgada. Y la cobertura del cubo, que dice cuánto del LUT está medido y cuánto
inventado, era una cifra de 13 px en la esquina del mapa. Ver `CIFRAS.md` §1.

### Cómo quedó el panel

La columna derecha tiene ahora tres paneles, **y el diagnóstico va arriba**
(antes lo primero que se veía a la derecha era el mapa):

1. **Diagnóstico.** Fila 1: rótulo «ΔE2000 máximo» y, pegada a él, la marca
   `MarcaLimite` («NO CUMPLE · MARGEN -15.29»). Fila 2: el máximo a 26 px con
   «/ 3.0» al lado, y a la derecha, a 12 px, la media y el p95. Debajo, dos
   bloques gemelos a 26 px: «cabe en un .cube» y «cubo medido» (con «98.94%
   inventado» debajo), construidos por la misma función (`_bloque_titular`) para
   que no puedan salir a tamaños distintos. Y una línea: «Medido sobre este
   plano: en otro plano no está garantizado.»
2. **Mapa de cobertura**, con el recuento de celdas en la cabecera (pequeño).
3. **Qué NO es un LUT / residuo espacial**, en su propio panel.

### El límite: importado, y dicho como lo que es

`LIMITE_T1_DELTA_E_MAXIMO` se importa de `core.umbrales`. Lo único que hace la
GUI con él es restar (`límite - máximo`) y comparar con `<`, que es como está
escrito el criterio del encargo. **Hay un test que cambia el límite en el espacio
de nombres de la pantalla y comprueba que el rótulo y el margen lo siguen**, y
otro que busca por AST un `3.0` o un `2.0` restado o comparado en `gui/`.

El límite **no es una medida perceptual** (docstring de `core/umbrales.py`), y la
pantalla lo dice en el tooltip de la marca y del «/ 3.0», y en una línea del
texto de diagnóstico: «es el objetivo que fijó el encargo, no una medida de dónde
empieza a notarse la diferencia».

Máximo exactamente igual al límite → «no cumple» (el encargo dice «< 3.0»).
Máximo no finito → «sin medir», sin margen.

### No cumplir no es rojo

`MarcaLimite` usa la gramática de la confianza: **relleno sólido brand-600**
cuando cumple, **contorno discontinuo brand-400 sin relleno** cuando no, y un
iconito que repite la forma (cuadrado lleno / cuadrado punteado). El texto dice
«no cumple» con todas las letras. La cifra grande no cambia de color. Hay test
que busca píxeles de rojo de alarma en la marca pintada, con control de que el
detector sí ve el naranja.

### Donde sólo hay media, se dice «medio»

`MatchResult.delta_e_before` / `delta_e_after` son **medias**, y el contrato no
trae el máximo por clip. **No se calcula en la GUI.** Se rotula lo que hay:

* tabla de clips: cabeceras en tres líneas, «ΔE / MEDIO / ANTES». En una línea
  «ΔE MEDIO» mide 49 px y ensancharía las dos columnas 8 px en total, o sea la
  ventana; en tres, la palabra más ancha sigue siendo «DESPUÉS»;
* ficha del clip: un rótulo común «ΔE medio» encima de «antes» y «después».
  «ΔE medio antes» + «ΔE medio después» seguidos piden 252 px y la ficha tiene
  246;
* antes/después: «ΔE medio antes» y «ΔE medio después».

Un test recorre todas las etiquetas de las cuatro pantallas y falla si alguna
nombra un ΔE sin decir si es medio, máximo o p95.

### El bug que salió en la primera captura: `TextoAjustado`

Primera captura a 973 px: el «18.29» salía a 19 px de alto de los 31 que
necesita, y el «1.06%» a 15, pisado por su barra. **Nada cortado a lo ancho, pero
aplastado a lo alto.** La causa, medida: un `QLabel` con `wordWrap` declara su
alto mínimo como si el texto cupiera en una línea (el mínimo de un layout no usa
`heightForWidth`). A 973 px la línea de alcance y la leyenda ocupan dos, la
columna creía que le sobraban ~15 px por etiqueta y se los quitaba al único panel
que no estira.

`gui.widgets.TextoAjustado` devuelve como alto mínimo el de `heightForWidth()` al
ancho actual y avisa al layout cuando cambia. Se usa en la línea de alcance y en
la leyenda del mapa. Test: a la anchura mínima ninguna cifra del diagnóstico
tiene menos alto que su mínimo; y un control que enseña que un `QLabel` normal sí
declara de menos.

### Lo que pagó el alto (651 → 727)

Sin tocar nada más, el panel nuevo subía el mínimo a 775 (y a 756 medido de
verdad, con `TextoAjustado`). Lo que se recortó:

| Qué | Antes | Ahora |
|---|---|---|
| alto mínimo del mapa de cobertura | 170 | 120 |
| alto mínimo del mapa de residuo | 110 | 90 |
| leyenda del mapa | 3 líneas | 2 a 973 px, 1 a 1440 |
| marca de límite | fila propia bajo la cifra | en la fila del rótulo |
| media y p95 | fila propia | a la derecha de la cifra |
| línea de alcance | 2 líneas a 973 | 1 (323 px de 361) |

**Lo que no se ha hecho y se podría:** meter la columna derecha en un
`QScrollArea` (como la izquierda) bajaría el alto mínimo mucho, pero a 973 × 727
el residuo quedaría debajo del pliegue. No lo he hecho sin preguntar.

### Qué campos faltan en el contrato

* **`MatchResult` no trae el ΔE máximo (ni p95) por clip.** Sin él, la tabla y la
  ficha enseñan la cifra holgada.
* **No hay margen ni «cumple» calculado por el núcleo.** La GUI resta y compara
  contra el límite importado; si algún día el criterio deja de ser un `<` simple,
  hay que moverlo al núcleo.
* **No hay forma de saber sobre cuántos planos se ha medido un `ReverseResult`.**
  La línea de alcance dice «este plano» porque el panel invierte un solo par; si
  el modo por lotes llega a la pantalla, esa frase tendrá que salir de un campo.

### [día 4, después] El test del mapa de cobertura no miraba lo medido

Lo encontró el revisor de tests vacíos. `test_el_mapa_de_cobertura_distingue_lo_medido_de_lo_inventado`
montaba `cortes=1`, o sea el corte b=0, y en la demo ese corte tiene **cero** celdas
cubiertas (17³, 52 cubiertas; por corte de b: 0,3,6,7,7,7,4,4,5,6,3,0,0,0,0,0,0). La mitad
«una celda medida no se pinta igual que una inventada» no comprobaba nada desde el día 2.

**No era un bug de la pantalla:** mirado a mano, el corte b=1 pinta sus 3 celdas medidas en
naranja (`#642918`, `#9e4125`, `#aa4628`) y las inventadas en tablero (`#0d0b08` / `#131110`).

Arreglo, en el montaje del test y no en la aserción: se pintan los `n` cortes en una fila con
`montaje_cobertura` y se recorta **el primer b con celdas cubiertas**, afirmando antes que existe.
Hoy es b=1. Y un control negativo repinta las celdas medidas con el tono de tablero que les toca y
comprueba que la aserción salta por la frase de lo medido. Sin cambio visible: no se regeneran
capturas.

---

## Modo fácil (día 5, tarea 3): `gui/asistente_facil.py` + `gui/pantalla_facil.py`

**Mismo motor, otra presentación.** `gui/asistente_facil.py` es lógica pura (sin Qt): cada
paso llama a las mismas funciones de `core` que ya usa el modo avanzado
(`core.colormgmt.detectar_espacios_timeline`/`agrupar_ambiguos`/`verificar_proyecto` para
«ordenar la casa», `core.matching.emparejar` —vía `ClipDemo.match`, que ya lo calcula— para
«igualar» y «equilibrar»). No hay un segundo camino de cálculo «simplificado»: lo que cambia
es qué se enseña y en qué orden, nunca cómo se calcula.

**Por qué el paso 5 (repasar) NO usa la confianza.** El día 4 midió que la nota de
`core.reverse`/`core.matching` no predice el error real (`CALIBRACION-CONFIANZA.md`). Ponerla
en el modo fácil —que es justo el público que menos puede juzgar por sí mismo si un número
«alta» merece confianza— habría sido mentir con apariencia de objetividad. En su lugar,
`ejecutar_repasar` usa dos señales que SÍ están medidas: `content_mismatch` (el día 4 confirmó
que distingue bien «misma escena» de «escena distinta») y los grupos de `core.colormgmt` que
el paso 1 no pudo resolver solo. Hay un test explícito de esto:
`tests/test_gui_asistente_facil.py::test_repasar_no_usa_la_palabra_confianza_en_sus_motivos`.

**El bug real que cazó la verificación visual (no un test):** la primera versión de
`ejecutar_repasar` sumaba candidatos de las dos señales SIN deduplicar por `clip_id`. Con
`estado_demo()` daba «8 clips que conviene que mires» cuando en realidad eran 7 (el clip del
exterior aparecía dos veces: por desajuste de contenido Y por falta de metadata de cámara). No
lo encontró ningún test —los tests puros no habían cubierto ese solape—, lo encontró mirar la
captura renderizada de verdad y hacer la cuenta a mano. Arreglado agrupando por `clip_id` con
los motivos concatenados; el test
`tests/test_gui_asistente_facil.py::test_repasar_no_duplica_un_clip_con_dos_motivos` lo fija.

**El otro bug que cazó la misma verificación:** `_clip_con_imagen()` cogía «el primer clip con
imagen», que en `estado_demo()` es precisamente el clip de referencia. Mostrar la referencia
emparejada contra sí misma en el paso «igualar» da un CDL casi identidad: el antes/después
salía visualmente idéntico y no demostraba nada. Arreglado con
`evitar_referencia=True` en los pasos que ajustan color.

**El conmutador (`gui/ventana.py`, `CLAVE_MODO_FACIL`).** Vive en el carril, por encima de la
navegación de las 4 pantallas del modo avanzado, que se oculta entera mientras el modo fácil
está activo (no tiene sentido navegar «clips / comparar / aplicar / reverse» dentro del
asistente). Se recuerda con `QSettings("SIDEBFLMS", "COLOR")`, por usuario del sistema — NO es
un ajuste del proyecto ni se versiona.

**Ojo con `QSettings` y macOS al escribir tests.** `cfprefsd` (el daemon de preferencias de
macOS) cachea el valor en memoria incluso después de borrar el `.plist` a mano
(`rm ~/Library/Preferences/com.sidebflms.COLOR.plist` no basta; hace falta
`defaults delete com.sidebflms.COLOR`, que sí invalida el caché). Y `QSettings.setDefaultFormat(IniFormat)`
+ `setPath(...)` apuntando a un directorio temporal **tampoco aísla el test**: en este mismo
día se comprobó que `QSettings("SIDEBFLMS", "COLOR").fileName()` seguía devolviendo la ruta del
`.plist` nativo real a pesar de haber forzado `IniFormat`. La única forma que funcionó de
verdad fue sustituir la clase entera por un stub en memoria vía `monkeypatch` (ver
`tests/test_gui_pantalla_facil.py::_SettingsFalso`). Cualquier test futuro que toque
`QSettings` en esta app debería partir de ese patrón, no del `IniFormat`.

**Escritura en Resolve: deliberadamente fuera de esta pantalla.** `PantallaFacil` es pura
previsualización — calcula y enseña, no escribe. «Deshacer» solo mueve el puntero de paso
porque no hay nada escrito de verdad que deshacer. Escribir en Resolve con la red de
seguridad de la versión `SIDEB COLOR` ya existe en el modo avanzado (`PantallaAplicar`), y
esta pantalla no lo duplica. Queda pendiente, para quien retome esto, decidir si el modo
fácil necesita su propio botón «Aplicar» al final del paso 5 (que llamaría a
`core.resolve.aplicar_grado_seguro`, ya probado) o si basta con dejar que quien lo use pase al
modo avanzado para el último paso.

**Lo que falta, con conocimiento de causa:**
- Sólo se ha probado con `estado_demo()`. Falta ejercitar el asistente contra
  `estado_vacio()`, `estado_desconectado()` y `estado_muchos()` con capturas (los tests puros
  de `asistente_facil` sí lo cubren; las capturas de `gui/capturas.py` sólo tienen el caso
  nominal).
- El paso 1 sólo enseña `grupos_pendientes[0]` cuando hay varios grupos ambiguos a la vez
  (en `estado_demo()`, sin metadata de cámara en ningún clip, hay dos). No hay forma de
  navegar entre preguntas dentro del mismo paso — habría que decidir si eso es un paso 1
  con sub-navegación o una lista de preguntas.
- «Equilibrar» (paso 3) no tiene, hoy, una operación propia en `core`: reutiliza el mismo CDL
  de «igualar» y sólo cambia la frase para hablar de exposición/balance en vez de igualado
  completo. Es honesto (no inventa un cálculo que no existe) pero es una simplificación real,
  documentada aquí para que no se lea como una función separada que no es.

---

## Capturas deterministas (día 6, tarea 5): el problema del día 5 no era el renderizado

El encargo del día 6 daba por hecho que había ruido de renderizado que fijar (fuente,
antialiasing, escala) porque el día 5 hubo que revertir 16 capturas del modo avanzado que
"cambiaron sin que se tocara ese código". Antes de tocar nada de eso, se comprobó
empíricamente — `tests/test_gui_capturas_deterministas.py` genera `capturas/` completa dos
veces (en directorios temporales, sin tocar el repo) y compara SHA-256 byte a byte.

**Resultado: cero diferencias**, en tres montajes distintos:

1. Dos ejecuciones seguidas, sin nada más corriendo.
2. Una ejecución con tres procesos `yes` saturando la CPU en paralelo.
3. **Dos invocaciones de `generar()` corriendo genuinamente en paralelo entre sí**
   (procesos Python distintos, compitiendo de verdad por CPU) — el escenario más parecido a
   lo que pasó el día 5, cuando el agente de calibración de la confianza corría en background
   mientras se regeneraban las capturas.

**La causa real, confirmada a nivel de píxel: no era ruido, era un cambio de diseño real
que se interpretó mal.** El día 5 se añadió el botón "Modo fácil" al carril de navegación
(`gui/ventana.py::_carril`), un elemento visible nuevo en TODAS las pantallas del modo
avanzado. Al comparar hoy, con Pillow, cada una de las 16 capturas «que cambiaron por
ruido» contra la versión del commit: la diferencia cae siempre, en los 26 archivos del
modo avanzado, DENTRO del carril (`x < ANCHO_CARRIL = 186`) y nunca fuera — 0 píxeles
distintos fuera del carril, en los 26. Es decir: las capturas cambiaron exactamente donde
tenían que cambiar (apareció un botón nuevo) y en ningún otro sitio.

**Conclusión: el día 5 se revirtieron por error 16 capturas que en realidad ya estaban
bien** — reflejaban correctamente el diseño nuevo — porque se las descartó como "ruido" sin
comparar a nivel de píxel qué había cambiado. No hubo nunca un problema de renderizado que
arreglar. Se han vuelto a regenerar hoy y se dejan en el commit del día 6 con el botón
visible, que es el estado correcto del código actual.

**Qué NO se tocó, y por qué**: no se fijó ninguna semilla de aleatoriedad (ya estaban fijas,
`tests/media/generate.py` usa `np.random.default_rng(seed)` en todos los sitios), no se forzó
ningún modo de antialiasing ni se cambió la fuente — no hacía falta, y tocar el renderizado sin
que haya un problema medido habría sido la misma clase de invención que el resto del proyecto
evita.
