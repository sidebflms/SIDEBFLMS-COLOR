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

Lo que empieza por **[día 2]** lo he decidido yo, no el agente H.

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

**Hoy son 985 × 643 px.** No es un número elegido: es lo que contesta
`VentanaPrincipal.minimumSizeHint()` después de un `ensurePolished()` sobre
todos los hijos, que es lo que hace `anchura_minima()`. Sin el `ensurePolished`
sale más pequeño de lo real y la captura sale engañosa.

**Era 966 la noche del 14. [día 2] Lo he subido a 985, y no para que algo
quepa.** He quitado tres números puestos a ojo que se quedaban cortos:

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

**Ojo con las tipografías.** 985 es el número **con las alternativas** (Helvetica
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
6. **La columna CLIP se queda en 56 px a la anchura mínima** y enseña «A…a» (a
   1024 px, en 66: «A00…oma»). **Éste no lo he arreglado**, y está como
   `xfail(strict=True)` con el motivo entero en el test. El resumen:
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

1. **Por qué `Cifra` acepta un `px=` que la hoja de estilo ignora.** Los tamaños
   que pide el código (17, 18, 22, 24, 26 px para las cifras grandes) **no se
   aplican**: el QSS los pisa y todas las cifras salen a 13 px. Lo he
   comprobado quitando la hoja de estilo: la misma etiqueta pasa de 13 px a 22.
   **No sé si el agente H lo sabía.** Hay dos pistas que apuntan a que no: la
   hoja de estilo define una regla `QLabel#cifraGrande { font-size: 26px }` que
   **no usa nadie**, y los `px=` están elegidos con criterio (22 para el ΔE de
   la ficha, 26 para «cabe en un .cube»), que es lo que uno hace cuando cree que
   funcionan. **No lo he tocado**: la interfaz que Mario ha visto y le gusta es
   la de 13 px uniformes, y arreglarlo cambiaría el aspecto de las cuatro
   pantallas. Es una decisión suya, no mía.
2. **Por qué el sustituto de `reverse_puente` usa una rejilla de 17 y no de 33.**
   El comentario dice que es «un motivo de pantalla, no de calidad» —con 33 el
   mapa de cobertura sale prácticamente en negro— y eso me parece razonable y
   comprobable. Lo que no sé es si además se midió el coste en calidad de
   invertir a 17, o si se dio por bueno porque el sustituto era provisional.
3. **Por qué `INSIGNIA_ANCHO` es 108 y no otro número.** Cabe «ALTA 97%» con el
   medidor delante, pero no he encontrado la medición que lo fijó. Puede ser
   ajuste a ojo.
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

## 12. Qué probar la próxima vez

* **La ventana no se ha probado a más de 1440 px.** Los `setMaximumWidth` del
  lateral de comparar (300) y del selector de clip (460) no se han mirado en una
  pantalla de 2560.
* **No hay ni un test de teclado de verdad** (`QTest.keyClick`). La cortinilla se
  mueve llamando a `set_posicion()`, que es lo que hace el manejador, pero el
  manejador en sí no se ejercita.
* **Las capturas no enseñan la tipografía de la marca.** Inter, Chakra Petch y
  JetBrains Mono no están instaladas en este Mac. El layout, el color, los
  tamaños y el tracking sí son los buenos; las letras no.
