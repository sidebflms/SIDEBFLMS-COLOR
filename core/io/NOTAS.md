# NOTAS — agente D · io

Qué decidí, qué descarté y por qué. Lo concreto primero.

---

## 1. Los ejes del `.cube` (convención 4)

Lo único de este módulo que, si está mal, no se nota hasta que Mario ve una
imagen azul donde debería ser roja.

| Sitio | Orden |
|---|---|
| `LUT3D.table` | `[ri, gi, bi] -> (r,g,b)`. **Eje 0 = ROJO.** |
| Fichero `.cube` | el **rojo** varía más rápido: línea = `((bi*N)+gi)*N+ri` |
| Imagen HALD | el **azul** varía más rápido: es `table.reshape(-1,3)` a pelo |

O sea que el `.cube` y el HALD usan órdenes **opuestos**, y es correcto: son dos
formatos distintos con dos convenciones distintas. Está encapsulado en
`orden_fichero_desde_tabla()` / `tabla_desde_orden_fichero()` (una sola
permutación, `transpose(2,1,0,3)`, que es involutiva) y en `hald_image()` /
`lut_from_hald()`. Nadie más debería escribir un `transpose` en todo el proyecto.

Tests que lo vigilan, por si alguien "optimiza" alguna de las dos:

- `test_ida_y_vuelta_un_lut_que_solo_toca_el_rojo` — escribe un LUT que sólo
  baja el rojo, lo lee, y comprueba que sigue bajando el ROJO y no el azul.
- `test_en_el_fichero_el_rojo_es_el_que_varia_mas_rapido` — mira las líneas del
  fichero de texto directamente.
- `test_en_el_hald_el_azul_es_el_que_varia_mas_rapido` — la otra mitad.
- `test_el_hald_de_la_identidad_es_el_del_generador` — ata mi HALD al
  `generate.hald(17)` del orquestador. Si divergen, se ve al momento.
- `test_un_cube_leido_con_los_ejes_cambiados_se_notaria` — comprueba que los
  tests de arriba no son tautológicos (el error clásico, `reshape` sin
  transponer, produce de verdad una tabla distinta).

---

## 2. Límite de tamaño de LUT: **129**

`LUT_SIZE_MAX_LECTURA = 129`.

El razonamiento, en memoria de tabla `float32`:

| N | celdas | RAM de la tabla |
|---|---|---|
| 65 (el mayor que soportamos) | 274.625 | 3,3 MB |
| **129 (el tope)** | 2.146.689 | **25,7 MB** |
| 256 | 16.777.216 | 201 MB |
| 4096 | 6,9e10 | 824 GB |

La app sólo produce 17/33/65, pero por ahí circulan LUT de 64 y de 128 hechos
con otras herramientas y sería absurdo no poder abrirlos; 129 los cubre con
margen. Por encima de eso ya no hay caso de uso real, sólo ficheros rotos o
maliciosos: un `.cube` de **40 bytes** que diga `LUT_3D_SIZE 4096` pediría 824 GB
y tumbaría la máquina. El error se lanza **antes de reservar nada**.

Hay además un tope de fichero (`MAX_BYTES_CUBE = 128 MB`) para el caso de un
`.cube` de texto de 10 GB, que no declara nada absurdo pero tampoco es un LUT.

**Qué descarté:** validar contra `LUT_SIZES_SOPORTADOS` (17/33/65) al leer. Es
lo que hace el contrato *al generar*, pero rechazar un LUT de 64 que viene de
fuera es hostil sin ganar nada. Al escribir tampoco se valida: si un test quiere
un LUT de tamaño 2, que lo escriba.

### Cabeceras de tamaño repetidas (revisión ola 1, D-2)

Rechazaba `LUT_3D_SIZE` y `LUT_1D_SIZE` **a la vez** con un mensaje claro, pero
dos `LUT_3D_SIZE` con valores **distintos** se los tragaba en silencio quedándose
con el último. Es la misma ambigüedad y el mismo riesgo (un exportador roto que
corta y pega, un fichero concatenado), y además el más traicionero de los dos:
no da error, simplemente lee una tabla que no es la que el fichero declara.

Ahora se rechaza, diciendo los dos valores y en qué líneas están. Vale para
`LUT_3D_SIZE` y para `LUT_1D_SIZE`.

**Lo que NO rechazo:** la misma cabecera repetida con el **mismo** valor. Ahí no
hay ambigüedad que resolver, y ser estricto gratis es tan malo como ser laxo:
Mario no puede abrir el `.cube` del cliente y da igual lo bien defendido que
esté. Hay un test por cada uno de los tres casos.

---

## 3. Cómo se mide el banding, exactamente

Para cada eje de entrada `a` y cada canal de salida `c`:

```
d1  = diff(tabla[..., c], eje=a)      # el paso entre celdas contiguas
d2  = diff(d1, eje=a)                 # cuánto CAMBIA el paso
escala = mediana(|d1|)
```

Se marca banding sólo si **las dos** condiciones se cumplen:

```
|d2| > UMBRAL_BANDING * max(escala, 1e-6)    # UMBRAL_BANDING = 3.0
|d2| > SALTO_MINIMO_BANDING                  # = 0.02
```

**Por qué la segunda derivada y no el salto entre celdas vecinas.** Una rampa con
pendiente fuerte pero *constante* (un LUT que multiplica por 3) tiene saltos
enormes entre celdas y no produce ni una banda. Lo que se ve es el **cambio** de
pendiente. Eso es `d2`.

**Por qué dos condiciones y no una.** La relativa (umbral 3) es la que detecta el
escalón. La absoluta (0.02) es la que protege de los falsos positivos: en un LUT
casi plano la mediana es microscópica y el ruido de `float32` la supera tres
veces sin que se vea nada. **Es la absoluta la que mantiene limpio el LUT
identidad** (su `d2` es del orden de 1e-8), no la relativa; por eso se puede
tener el umbral relativo bajo sin manchar la identidad.

**Por qué 0.02 y no otro número.** 0.02 en unidades de salida son ~5/255. Por
debajo de eso una banda no se ve en un degradado limpio ni buscándola.

**Por qué 3 y no 6.** Empecé con 6 y no cazaba un escalón de 0.3 en un LUT de 17
(el paso típico ahí es 0.044, y 6× son 0.26... justo por encima). Un escalón de
0.3 sobre un rango de 1.0 es una banda evidentísima. Bajé a 3 y comprobé que la
identidad, una curva en S de contraste y un CDL realista convertido a LUT siguen
pasando limpios en 17, 33 y 65 (hay un test por cada caso).

### Lo que NO pasa limpio, y por qué el umbral se queda como está

**Revisión ola 1, D-1.** El revisor midió los falsos positivos sobre siete LUT
legítimos. Cinco de siete pasan limpios en 17, 33 y 65. El que no pasa es la
**curva de gamma de salida `x**(1/2.2)`**, que es el LUT más común que existe, y
no pasa en ninguno de los tres tamaños.

Lo medí antes de decidir nada, sobre una rampa de 2001 muestras (la curva
gemela, `t**0.45`):

| N | error máx. del LUT vs. la curva real | peor quiebro en la rampa |
|---|---|---|
| 17 | 0,082 (21/255) | 0,4/255 |
| 33 | 0,060 (15/255) | 0,3/255 |
| 65 | 0,044 (11/255) | 0,6/255 |

**Decisión: NO subo el umbral.** Tres razones, en orden de peso:

1. **Es un verdadero positivo.** Incluso con 65 puntos, el LUT se desvía 11/255
   de la curva que dice representar. Eso no es ruido del detector: es que una
   rejilla uniforme no puede con una pendiente casi infinita pegada al negro.
   Callarlo sería esconder un defecto real del formato.
2. **El contrapeso está probado.** `test_el_qc_encuentra_el_escalon_de_verdad_cuando_lo_hay`
   (del revisor) exige que un salto de 0.3 en mitad de la rampa se siga
   cazando. Subir `SALTO_MINIMO_BANDING` de 0.02 a 0.05 callaría la gamma...
   y empezaría a acercarse peligrosamente a callar escalones de verdad en LUT
   de 65, donde el paso típico es 0.0104.
3. **Las dos vías que el revisor propone están cerradas por sus propios tests.**
   Sugiere "excluir el primer y el último intervalo": eso dejaría la gamma
   limpia y pondría rojo su
   `test_cuantos_falsos_positivos_da_el_qc_sobre_luts_legitimos`, que **afirma**
   que esa curva sale sucia en los tres tamaños. Y sugiere "contar posiciones
   distintas del eje": eso cambiaría `celdas_con_banding`, que su otro test
   **afirma** que vale `3*n*n`. La única salida compatible con las dos
   afirmaciones es la que he tomado (ver abajo), y me parece además la correcta.

Queda por escrito el matiz honesto: el artefacto visible en la imagen es un
quiebro de pendiente (0,6/255 de segunda derivada), no un escalón duro. El
detector está del lado sensible. **Si a Mario le cansa**, el botón es
`SALTO_MINIMO_BANDING`; pero entonces hay que volver a mirar el punto 2.

### Día 2: el aviso estaba bien detectado y mal contado

Mario lo zanjó, y tenía razón la parte que no habíamos mirado: el problema no
era **que** avisara, era **qué decía**. El mensaje mandaba a arreglar algo que,
en un LUT de salida, no está roto. Sus palabras: *si el LUT incluye la
conversión a Rec.709, los escalones en sombras son esperables y no son un
defecto.*

Así que **el detector no se ha tocado** —ni un umbral, ni un número, y está
comprobado con un test que el recuento de escalones de la gamma de salida sigue
siendo exactamente el mismo (3, uno por eje, en 17, 33 y 65)— y se ha reescrito
el mensaje. Ahora dice dónde está el escalón, cuánto mide, y **qué significa que
esté ahí**:

- **En sombras** (`EXPLICACION_SOMBRAS`): que si el LUT lleva la conversión a
  Rec.709 o cualquier gamma de salida, eso es esperable y no es un defecto,
  porque la curva sube casi en vertical pegada al negro y una rejilla uniforme
  no puede seguirla ni con 65 puntos. Y que es un aviso, no un error: no bloquea
  nada, y sólo hay algo que arreglar si la banda se ve en la imagen.
- **En los medios** (`EXPLICACION_MEDIOS`): lo contrario, que eso no es el
  achatamiento normal de una gamma y sí merece un vistazo.

Lo segundo es lo que hace que lo primero sirva de algo: un mensaje que dijera
«tranquilo, esto es normal» en todos los casos es un mensaje que nadie vuelve a
leer.

**`UMBRAL_SOMBRAS = 0.125`** decide cuál de las dos frases sale, y **sólo eso**.
Es un octavo del recorrido de la rejilla: con 17 puntos son los dos primeros
intervalos, con 33 los cuatro primeros y con 65 los ocho primeros, o sea la
misma zona de la imagen mida lo que mida el LUT. Medido: la gamma de salida cae
en la posición 0 en los tres tamaños, así que se explica como sombras en los
tres. Hay un test que fija la frontera con un solo LUT (la celda 4 de un 33 cae
dentro, la 5 fuera) y otro que comprueba que mover esto no cambia ni un escalón
detectado.

Y de paso se comprobó lo que el aviso dice de sí mismo, porque decirlo en el
texto no basta: `gravedad == "aviso"` en todos, `hay_errores` sigue siendo
`False`, y el `.cube` se escribe y se vuelve a leer sin que nadie proteste. Tres
tamaños, tres formas de comprobarlo.

---

## 3.bis Exportar a 65³: dónde está y por qué no es un parámetro de `escribir_cube`

**33 se queda.** Mario lo confirmó con su razón: es el estándar de facto, y 65
sobre todo infla el archivo y da problemas de compatibilidad con cámaras y
monitores de campo. `LUT_SIZE_DEFAULT` sigue siendo 33 y además vive en
`core/contracts.py`, que no es de este agente.

Lo que sí hace falta es poder entregar un 65 cuando lo piden. Está en
**`core/io/remuestreo.py`**: `remuestrear_lut(lut, TAMANO_ENTREGA_FINAL)`.

**Por qué una función y no `escribir_cube(..., tamano=65)`**, que era la otra
opción sobre la mesa. Porque remuestrear es una operación con nombre propio y
tiene que verse en la línea que la pide. Un `tamano=65` colado entre los
parámetros de un escritor da a entender que el fichero *se escribe* con más
resolución, y lo que pasa de verdad es que **se interpola**. La firma de
`escribir_cube` no ha cambiado y hay un test que lo vigila: si mañana acepta un
tamaño, remuestrear deja de verse y alguien exportará a 65 creyendo que ha
ganado precisión.

**Y no gana ninguna.** Ésta es la parte que hay que tener clara antes de
enseñársela a nadie: un LUT de 33 **ya es** una función —`apply()` interpola
trilinealmente— y pasar a 65 es preguntarle esa misma función en más puntos.
Además, como 65 = 2·33 − 1, los puntos nuevos caen justo sobre los viejos y sus
puntos medios, así que la función resultante es **idéntica**, no parecida.

Medido sobre 200.000 colores aleatorios, `lut33.apply(x)` contra
`remuestrear_lut(lut33, 65).apply(x)`:

| LUT de partida (33) | diferencia máxima | en unidades de 255 |
|---|---|---|
| identidad | 2,2e-16 | 0,00000006 |
| curva en S de contraste | 2,2e-16 | 0,00000006 |
| gamma de salida `x**(1/2.2)` | 3,0e-08 | 0,0000076 |
| **CDL realista** (el peor) | **5,7e-08** | **0,0000146** |

O sea: cinco millonésimas de un nivel de 8 bits, que es el error de escribir el
mismo número en `float32`. Lo único que se gana de verdad es un fichero 7,6
veces más grande (medido con este CDL y 6 decimales: 0,93 MB → 7,07 MB) que
algunas cámaras y monitores de
campo no saben leer.

El test que lo fija tolera 1e-6, y hay **otro** que exige que siga siendo del
orden de 5,7e-08, para que la cifra escrita aquí no se convierta en mentira sin
que nadie se entere.

**Bajar sí pierde**, y por eso `explicacion_remuestreo()` dice cosas distintas
en cada dirección. Medido, 33 → 17: la curva en S y el CDL pierden 0,7/255
(nada), pero **la gamma de salida pierde 0,065, o sea 16,6 niveles de 255**.
Eso no es simétrico con lo de subir y no se puede contar igual.

Tres cosas que decidí solo aquí:

1. **Se permite bajar de tamaño**, en vez de prohibirlo. Alguien tendrá un
   cacharro que sólo lee 17, y negarse sin más no le sirve; lo que hace falta es
   que sepa lo que pierde, y eso lo dice la explicación.
2. **La frase para el usuario vive aquí, no en la GUI** (`explicacion_remuestreo`).
   El que sabe lo que cuesta remuestrear es este módulo; si la frase la escribe
   quien pone el botón, acaba diciendo lo que él creía.
3. **Se valida el tamaño contra 2..129, no contra `LUT_SIZES_SOPORTADOS`**, por
   coherencia con la lectura: si aceptamos leer un LUT de 64 que viene de fuera,
   no tiene sentido negarnos a escribir uno.

### El recuento: un escalón no son doce mil celdas (D-1, lo que SÍ arreglé)

Lo que de verdad estaba mal no era el umbral, era **el número**. Un escalón vive
en una *posición* de la rejilla, pero la tabla es un cubo: la misma
discontinuidad aparece en las `n*n` líneas paralelas a ese eje. Contando celdas,
un único escalón en un LUT de 65 salía como **12.675**. Ese número le dice a
Mario que el LUT está roto cuando lo que hay es un escalón en un sitio.

Antes: `LUT de 65: banding (20).` y veinte avisos en la GUI, todos el mismo
defecto.
Ahora: `LUT de 65: banding (3 escalones).` y tres avisos, uno por eje, cada uno
diciendo *"en el primer intervalo de la rejilla (pegado al negro) ... es UN
escalón, pero se repite en 4225 líneas paralelas del cubo"*.

Concretamente:

- Los `ProblemaQC` de banding van **agrupados por `(eje, canal, posición)`**, con
  el campo nuevo `repeticiones` diciendo en cuántas líneas paralelas aparece, y
  `celda` señalando la peor de ellas.
- **`metricas["escalones_de_banding"]`** es el número honesto y es el que usa
  `resumen()`. Es nuevo.
- **`metricas["celdas_con_banding"]`** sigue existiendo, en bruto, sin tocar:
  no es falso, simplemente no es para enseñarlo. (Y el revisor lo tiene fijado
  en un test, que es otra razón para no cambiarlo.)
- De paso, **`resumen()` ya no cuenta la lista recortada**. Antes, con un LUT
  entero de NaN, decía "(20)" porque la lista se corta en
  `MAX_PROBLEMAS_POR_CODIGO`; ahora coge el total real de `metricas` y dice
  "14739 valores". Mismo pecado que el del banding, en otro sitio.

---

## 4. Qué hice con `LUT_1D_SIZE`: **convertirlo, no rechazarlo**

Un LUT 1D es una curva por canal: `f_r`, `f_g`, `f_b` independientes. El cubo 3D
equivalente existe y es exacto:

```
tabla[ri, gi, bi] = (f_r(ri/(N-1)), f_g(gi/(N-1)), f_b(bi/(N-1)))
```

Se remuestrea a `tamano_3d_desde_1d` (33 por defecto) con interpolación lineal.
**Hay pérdida en la curva** y es inevitable: los LUT 1D vienen normalmente con
1024 o 4096 entradas, y un cubo de 1024 son 12,9 GB. Nadie sensato quiere eso.

Descarté lanzar un error porque un `.cube` 1D es un fichero perfectamente
legítimo que alguien va a soltar en la GUI algún día, y "no sé leer esto" cuando
sí sé es una mala respuesta. Descarté también adivinar el tamaño de destino a
partir del 1D: 33 es el `LUT_SIZE_DEFAULT` del proyecto y quien quiera otro lo
pide por parámetro.

---

## 5. `xml.etree.ElementTree` de la stdlib, y por qué basta

**`defusedxml` no está instalado en el venv y no se puede instalar (cero red).**
Así que la defensa va a mano, y son tres cosas:

1. **Tope de tamaño** (`MAX_BYTES_CDL = 8 MB`). Un `.cdl` de verdad son ~600
   bytes. Corta el ataque de "fichero gigante" y limita de paso lo que expat
   puede llegar a anidar.
2. **Se rechaza cualquier `<!DOCTYPE` o `<!ENTITY`** antes de parsear, con un
   `re.search` sobre el texto. Esto mata de un plumazo el *billion laughs* y el
   XXE: sin DTD no hay entidades que expandir ni ficheros externos que abrir. Un
   `.cdl` legítimo no lleva DTD nunca. Hay un test con cada ataque.
3. Expat, que es el parser de debajo, **no resuelve entidades externas por su
   cuenta en Python**: no hace peticiones de red ni abre ficheros, y ante una
   entidad no declarada lanza. Con el punto 2 encima, lo que queda es expat
   parseando XML bien formado.

**Lo que NO cubre:** una bomba de anidamiento (miles de elementos anidados) puede
agotar la pila de expat. El tope de 8 MB lo acota a algo que Python aguanta, pero
no lo elimina. Si algún día entra `defusedxml` en el venv, se sustituye
`_parsear` por `defusedxml.ElementTree.fromstring` y se puede borrar el punto 2.

---

## 6. Precisión al escribir: 6 decimales normalmente, **9 cifras significativas** en el bundle

`escribir_cube(..., decimales=6)` por defecto, que es lo que todo el mundo
espera en un `.cube` y lo que Resolve lee sin pestañear.

`decimales=None` activa el modo exacto: `%.9g`, o sea **nueve cifras
significativas**, que es la garantía de ida y vuelta del `float32` en IEEE 754.

**La trampa en la que caí y que conviene dejar escrita:** empecé usando 9
*decimales* para el bundle, razonando que el espaciado del float32 cerca de 1.0
es 1,2e-7 y 9 decimales redondean con error 5e-10. Cierto para valores cercanos a
1, y falso para el resto: el espaciado del float32 **se encoge** según baja el
valor (a 1e-4 el espaciado es 7,6e-12) mientras que el número de decimales no. El
test con una tabla aleatoria lo cazó. Las cifras significativas sí se adaptan.

El precio de `%.9g` es notación científica por debajo de 1e-4 (`1.2e-05`). La
lee `float()` y la lee el `atof` de C, así que Resolve también; pero como no
tengo forma de comprobarlo esta noche, los `.cube` que se entregan a Resolve
salen con los 6 decimales de siempre y el `%.9g` sólo se usa **dentro** del
`.sidebcolor`, que sólo abre esta app.

Hay un test que documenta explícitamente que con 6 decimales la ida y vuelta
**no** es exacta (`test_con_seis_decimales_la_ida_y_vuelta_NO_es_exacta`). No es
un bug, es el formato.

---

## 7. Directorio que no existe al escribir: **se lanza**, no se crea

Vale para `escribir_cube`, `escribir_cdl`, `escribir_cdls` y `guardar_sesion`.
Todas aceptan `crear_directorios=True` para lo contrario.

Dos razones. La convención 7 de CONTRATOS dice que `core/` no escribe fuera de la
ruta que le pasan, y fabricar un árbol de carpetas entero por una ruta mal
tecleada es justo lo que no queremos. Y práctica: si la GUI pide guardar en
`/Volumes/DISCO_QUE_NO_ESTA_MONTADO/luts/`, prefiero un error que un
`/Volumes/...` recién creado en el disco de arranque.

---

## 8. El `.sidebcolor`: qué defensas lleva y contra qué

Un `.sidebcolor` puede llegar por WeTransfer desde una casa de post que no
conocemos. Al abrirlo:

- **Zip-slip**: se rechaza el archivo **entero** si cualquier entrada tiene ruta
  absoluta, un `..`, una barra invertida o dos puntos. Hoy no se extrae nada al
  disco (todo se lee en memoria con `zf.open`), así que el ataque no llegaría a
  ninguna parte igualmente; la comprobación está puesta para el día que alguien
  añada un "extraer miniaturas a una carpeta". Test con cinco rutas distintas.
- **Zip-bomba**: se suma el tamaño descomprimido que declara el índice y se corta
  en `MAX_DESCOMPRIMIDO` (256 MB). Y **como el índice puede mentir**, cada
  entrada se lee además con un tope duro ceñido a lo que esa entrada declara
  (`_leer_entrada`).
- **Número de entradas**: tope de 10.000, por el zip con un millón de ficheros
  vacíos.
- **`np.load(..., allow_pickle=False)`**, siempre. Éste es el agujero de verdad:
  con `allow_pickle=True`, abrir un `.sidebcolor` que te han mandado por correo
  **ejecuta el código que lleve dentro**. Hay un test que mete un `.npy` con un
  pickle y comprueba que falla en vez de deserializarlo. Ese flag no se toca.
- **`json.dumps(..., allow_nan=False)`** al guardar: un NaN suelto en la sesión
  produciría un JSON no estándar que otros lectores rechazan. Mejor fallar aquí.

`MAX_DESCOMPRIMIDO` en 256 MB: da para una sesión con varios LUT de 65 (9,6 MB
de texto cada uno en modo exacto) y muestras de píxeles grandes, y sigue cabiendo
de sobra en la RAM de cualquier Mac.

### Una corrección a la revisión, para que nadie construya encima

El revisor fabricó un zip cuyo índice central **miente** (declara 10 bytes, trae
400 MB), la defensa aguantó, y dejó escrito que el precio es que
"un fichero de 400 KB obliga a leer un cuarto de giga a memoria antes de decir
que no".

**Lo medí y no es cierto**, ni con el código de antes ni con el de ahora.
`zipfile.ZipExtFile` limita por su cuenta la lectura al `file_size` del
directorio central —o sea, a los 10 bytes que declara el atacante— y verifica el
CRC al llegar al final, que es donde salta. Con el zip del propio revisor: 300 MB
reales, 299 KB en disco, `BadZipFile` en **0,057 s**, sin descomprimir nada.

Lo digo porque es un dato del que alguien podría tirar para "optimizar" la
lectura, y saldría a resolver un problema que no existe.

Aun así he ceñido el tope de `_leer_entrada` a lo que declara la entrada, porque
**sí** tapa un caso que el CRC no cubre: un atacante que controla el zip entero
puede declarar 10 bytes *y* poner el CRC correcto de esos 10 bytes. Ahí no hay
error de CRC y esta comprobación es la única que queda. Es cinturón y tirantes,
no el cinturón. Test:
`test_un_indice_mentiroso_se_rechaza_y_sale_baratisimo`, que fija tanto el
rechazo como que sale barato.

Y otra precisión del revisor que sí es correcta y conviene tener presente: el
billion-laughs en UTF-16 no lo para el `re.search` de `<!DOCTYPE` (en UTF-16 no
casa), lo para **la capa de antes**, que decodifica como UTF-8 estricto. O sea
que la defensa está en dos sitios y el orden importa: si algún día alguien
"mejora" la lectura del CDL aceptando otros encodings, tiene que mover el filtro
de DOCTYPE a después de la decodificación, no antes. Ya está así (se filtra sobre
el texto ya decodificado), pero dejarlo escrito cuesta dos líneas.

---

## 9. `LUTQualityReport` y `ProblemaQC` se quedan en `core/io/qc.py`

Lo pregunté en la ronda 1 y está resuelto: **se quedan aquí**. `contracts.py` es
para lo que cruza entre agentes; este informe sólo viaja de `io` a la GUI, y la
GUI ya importa `core.io`. Es la opción reversible: si mañana lo necesita un
tercero, se mueve tal cual.

---

## 10. Cosas que decidí solo y Mario podría querer cambiar

1. **`SALTO_MINIMO_BANDING = 0.02`** — el punto 3. La revisión de la ola 1 lo
   confirmó con números y decidí **no subirlo** (argumentado allí). Si aun así
   los avisos de banding cansan, esto es lo que hay que tocar, pero mirando
   antes el contrapeso del escalón de 0.3.
2. **Salirse de gamut es *aviso*, no *error*.** Un LUT de look puede salirse a
   propósito y Resolve recorta. Si Mario prefiere que sea error, es una línea.
3. **6 decimales por defecto en `escribir_cube`.** Es lo convencional, pero si
   algún día se ve banding en Resolve con LUT nuestros, subirlo a 8 es gratis.
4. **Los `.cube` de dentro del bundle usan notación científica** para valores
   minúsculos. Si alguien saca un `.cube` del zip a mano y su herramienta no la
   entiende, hay que reescribirlo con `escribir_cube`.
5. **`LUT_1D_SIZE` se remuestrea a 33** en vez de rechazarse. Es una decisión con
   pérdida.
6. **`leer_cdl()` devuelve el primer `ColorCorrection` y calla** si el fichero
   trae más. `leer_cdls()` los da todos. Quizá debería avisar.
7. **El `TITLE` del `.cube` se recorta a 100 caracteres** y las comillas se
   convierten en apóstrofos. Dentro del bundle el título va aparte en el JSON,
   así que ahí no se pierde nada.


---

## DÍA 3 · dónde viven ahora los umbrales de decisión

El hallazgo más grave del día 2 no fue ninguno de los cuatro casos auditados:
fue que **`gui/reverse_puente.py` tenía su propia definición, más floja, de
«esto es un LUT puro»** (0.92 a secas, frente al 0.95 **y** el percentil 95 por
debajo de 1.0 ΔE2000 que pide el núcleo), y que la GUI caía a ese criterio ante
cualquier excepción. Eso no es un bug suelto: es una clase de bug, la de un
criterio que se puede escribir dos veces.

Los umbrales de este módulo que **deciden un veredicto que Mario lee** se han
mudado a **`core/umbrales.py`**, que es desde hoy el único sitio donde se
escribe un criterio de decisión. Aquí se reexportan con el mismo nombre de
siempre, así que nada de lo que importaba de este módulo se ha roto.

**Ni un valor se ha movido.** Lo afirma `tests/test_umbrales.py`, que lleva la
tabla de valores de origen tecleada desde el código anterior al barrido, y lo
confirman las cuatro cifras de titular de `tests/test_entregables.py`, que
salen idénticas.

Lo que **no** se ha mudado son los parámetros de implementación: sólo le
importan a este módulo y llevarlos a un archivo común habría creado un
módulo-Dios que acopla todo con todo.

`tests/test_umbrales_literales.py` recorre el AST de `core/` y se pone rojo si
vuelve a aparecer un literal de umbral suelto.

**De este módulo se han mudado** los cuatro que deciden un código de problema
que Mario lee antes de que se escriba nada en Resolve: `UMBRAL_BANDING`,
`SALTO_MINIMO_BANDING`, `UMBRAL_SOMBRAS`, `TOL_MONOTONIA` y `TOL_GAMUT`.

**Y uno que no tenía nombre**: el `1e-6` de `if recorrido > 1e-6` de
`_lut_plano`, que es lo que decide el error «este LUT aplasta la imagen entera a
un solo color». Hoy es `UMBRAL_RECORRIDO_LUT_PLANO`. Estaba a doscientas líneas
de un `_PISO_ESCALA = 1e-6` que vale lo mismo y significa otra cosa (una guarda
de división), que es justo cómo se confunden dos criterios.

**Se quedan aquí**: `_PISO_ESCALA` (guarda de división),
`MAX_PROBLEMAS_POR_CODIGO` (tope de presentación), `MAX_BYTES_CUBE`,
`MAX_BYTES_CDL`, `MAX_DESCOMPRIMIDO`, `MAX_ENTRADAS`, `LUT_SIZE_MIN`,
`LUT_SIZE_MAX_LECTURA` y `TAMANO_ENTREGA_FINAL` — son límites de formato y de
seguridad de fichero, no criterios de calidad.

El punto 1 de «lo que dejo sin cerrar» sigue en pie tal cual: si algún día los
avisos de banding cansan, lo que hay que tocar es `SALTO_MINIMO_BANDING`, que
ahora está en `core/umbrales.py` con toda su historia escrita al lado.

---

## `drx.py` (día 5) — deliberadamente no confirma nada

`core/io/drx.py` NO es un lector de PowerGrades: es un inspector honesto. La
tarea 4 del día 5 pide "confirmar el formato real del `.drx`", y eso sólo se
puede hacer con un `.drx` real delante — Blackmagic no lo publica, y todo lo
que circula son suposiciones de foro (que es XML). Escribir un parser que
asuma una estructura de nodos concreta sin haber visto un archivo real sería
exactamente el tipo de invención que `CONTRATOS.md` prohíbe.

Así que el módulo hace lo mínimo defendible: parsea como XML si puede, cuenta
qué etiquetas aparecen (sin interpretar qué significan), y busca en el texto
crudo fragmentos que parezcan rutas a LUTs/imágenes externas, para el
avisador de dependencias. Todo declarado `SIN VERIFICAR` en el docstring.

Los tests (`tests/test_io_drx.py`) están partidos en dos grupos a propósito:
contra un XML fabricado a mano (prueba la mecánica, no el formato real) y
contra `tests/powergrades_reales/*.drx` (los PowerGrades de verdad de Mario),
que se saltan solos con `pytest.mark.skipif` mientras esa carpeta —ignorada
por git, solo lectura— esté vacía. Cuando Mario deje material ahí, ese
segundo grupo es el que dice si la suposición de foro se sostiene o no.

---

## `drx.py` (día 6) — con material real, deja de ser un inspector a ciegas

Mario dejó diez `.drx` reales. La suposición de foro del día 5 era correcta
("es XML"), pero incompleta: cada `<Body>` es un blob binario (hex →
Zstandard → Protocol Buffers sin `.proto` publicado) que el inspector del día
5 no tocaba. El detalle completo, confirmado-vs-supuesto, vive en
`core/io/FORMATO-DRX.md`, que es ahora la fuente de verdad de este módulo —
si algo de aquí y de ese documento discrepa, el documento manda.

**Dos hallazgos que obligaron a rediseñar, no sólo a extender:**

1. **`Gallery::GyStill` no es un nombre XML válido** (dos puntos en un nombre
   local viola "Namespaces in XML"). `ET.fromstring()` lo rechazaba con "not
   well-formed", así que `InfoDRX.es_xml` daba `False` en material real que
   SÍ era XML — un falso negativo que sólo se vio al probar con archivos de
   verdad, nunca con el XML fabricado del día 5 (que no tenía `::` porque no
   había ningún `.drx` real del que copiar el patrón). Arreglado con
   `_parsear_xml_sin_namespaces` (`expat.ParserCreate()` + `TreeBuilder` a
   mano, sin el `namespace_separator` que `ET.XMLParser` fija por dentro).
2. **`buscar_rutas_referenciadas` del día 5 buscaba texto en el XML crudo, y
   eso nunca iba a encontrar nada**: las rutas de LUT viven dentro del blob
   comprimido de `<Body>`, no como texto plano en ningún sitio del archivo.
   El módulo entero se reescribió alrededor de eso: `drx_protobuf.py` (wire
   format genérico, sin `.proto`, reutilizable y probado con mensajes
   fabricados a mano en `tests/test_io_drx_protobuf.py`) y `leer_grado()`
   (nodos + rutas de LUT, buscando el texto en TODO el subárbol de cada
   nodo, no en una ruta de campos fija — ver el porqué en
   `FORMATO-DRX.md` §3.3).

**Lo que NO se intentó**: escribir el `.proto` completo de Blackmagic
recíprocamente (nombrar todos los campos, entender los valores de rueda de
color). No hacía falta para las tareas del día 6 — nodos y rutas de LUT — y
habría sido trabajo especulativo sobre campos que no se necesitan todavía. Si
algún día hace falta leer el CDL numérico de un nodo, `drx_protobuf.py` ya
da el árbol completo; sólo falta identificar qué IDs de parámetro son cuáles,
con más material de comparación del que hay hoy.

**Dependencia nueva**: `zstandard` (pyproject.toml). Se prefirió sobre
invocar el binario `zstd` del sistema por subprocess porque es lo único que
garantiza que el lector funcione igual en el Mac de Mario, en CI, y en
cualquier máquina que no tenga `zstd` en el `PATH`.

---

## `biblioteca.py` (día 6) — un preset NO es una sesión

Deliberadamente un módulo aparte de `core.io.bundle`, con su propio esquema
de zip (`preset.json` + `look.cube` + `miniatura.png` opcional), aunque
comparte la extensión `.sidebcolor`. La alternativa —forzar un preset suelto
dentro de una `ColorSession` completa, con un solo `MatchResult` de mentira—
habría sido más confuso: un preset no tiene clips, no tiene análisis, no
tiene referencia. Es sólo un LUT con procedencia.

**Sí reutiliza las defensas de `bundle.py`** (`_abrir_zip`, `_revisar_zip`,
`_leer_entrada`, todas con `_` porque son privadas del módulo, importadas
directamente porque `biblioteca.py` vive en el mismo paquete): zip-slip y
zip-bomba no se reimplementan con las mismas garantías "a ojo" — es
literalmente el mismo código probado, no una copia.

**La miniatura nunca es material real.** `generar_miniatura()` aplica el LUT
de Mario a una escena SINTÉTICA de `tests/media/generate.py` — el mismo
generador que usa el resto de la app. Es real el LUT, no la imagen.

**`sembrar_desde_drx()` es lo que conecta la tarea 1 (el lector de `.drx`) con
la tarea 4 (la biblioteca).** Cuando un PowerGrade real trae dos LUTs (el
caso confirmado en `FORMATO-DRX.md` §3.2: conversión + look), sólo el ÚLTIMO
—el look— se empaqueta como `look.cube`; el resto queda como
`dependencias_declaradas` y genera un aviso al abrir el bundle en otro
equipo. Es una decisión de diseño, no un descubrimiento: se podría haber
empaquetado la cadena completa (conversión + look) horneada en un solo LUT,
pero eso sería mentir sobre qué es cada cosa — un look no es una conversión
de cámara, y mezclarlos en el mismo `.cube` le quita a Mario la posibilidad
de aplicar el look sobre OTRA cámara distinta.

**Selector de presets en `gui/pantalla_facil.py`**: con los 79 presets reales
de Mario, mostrar una miniatura renderizada por cada uno habría sido caro y
no aportaba nada que el antes/después del paso ya no enseñara para el
elegido — el selector es sólo de nombre.

**Actualización, mismo día**: el agente de la tarea 2 midió y calibró el
criterio conversión/look sobre las 79 (`core.io.qc.clasificar_lut`, movido de
su test a producción — 8 conversión, 71 look, mismas cifras). El selector del
paso 4 ya filtra: la biblioteca que se le pasa a `PantallaFacil` excluye los
"conversion" ANTES de llegar a `ejecutar_look` (en `gui/__main__.py` y
`gui/capturas.py`, no dentro de `ejecutar_look` — esa función sigue siendo
genérica sobre cualquier biblioteca que le pasen, el filtro es cosa de quien
decide qué biblioteca sembrar para el modo fácil).

**Un bug real que se coló y que cazó el agente de la tarea 3 al ejecutar la
suite completa (no el suyo — el mío):** la primera versión de
`_miniatura_a_png`/`_png_a_array` usaba `tempfile.NamedTemporaryFile` para
convertir entre PNG y array vía `QImage`, y encima importaba `gui.imagen`
desde `core/io/`. Dos problemas de una vez: `tempfile` en `core/` viola el
contrato 7 (`tests/revision/test_ola1_limites.py::test_core_no_usa_tempfile...`,
que existe justo para cazar esto), y `core` importando `gui` invierte la
dirección de dependencias del proyecto entero. Arreglado con `cv2.imencode`/
`cv2.imdecode` (OpenCV, ya dependencia del proyecto): todo en memoria, sin
tocar disco, sin Qt. `exportar_preset` ganó el mismo parámetro
`crear_directorios=False` que ya tienen `escribir_cube`/`guardar_sesion`, por
la misma razón (no fabricar carpetas sin que se pida). El inventario de
`test_ola1_limites.py` se actualizó a propósito (es un test que existe para
saltar cuando aparece una escritura nueva, no para prohibirla) y se añadió
`exportar_preset` a la prueba dinámica que fotografía el repo antes/después.
