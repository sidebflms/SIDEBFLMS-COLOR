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

### Lo que NO pasa limpio y es discutible

Una curva `t**0.45` (gamma fuerte, tipo log→lin) en rejilla uniforme **se marca
como banding en los tres tamaños**, 65 incluido. Lo medí antes de decidir, sobre
una rampa de 2001 muestras:

| N | error máx. del LUT vs. la curva real | peor quiebro en la rampa |
|---|---|---|
| 17 | 0,082 (21/255) | 0,4/255 |
| 33 | 0,060 (15/255) | 0,3/255 |
| 65 | 0,044 (11/255) | 0,6/255 |

O sea: el aviso es un **verdadero positivo** (el LUT se desvía 11/255 de la
curva que dice representar, incluso con 65 puntos), pero el artefacto visible en
la imagen es un quiebro de pendiente suave, no un escalón duro. El detector está
del lado sensible a propósito. **Esto es lo primero que Mario podría querer
cambiar**: subir `SALTO_MINIMO_BANDING` de 0.02 a 0.05 lo callaría casi todo.
Está en `test_una_gamma_fuerte_cerca_del_negro_se_marca_como_banding`, escrito y
explicado.

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
  entrada se lee además con un tope duro de bytes (`_leer_entrada`).
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

---

## 9. Un tipo mío que quizá debería estar en `contracts.py`

`LUTQualityReport` y `ProblemaQC` los defino en `core/io/qc.py` porque no existen
en `core/contracts.py` y **no puedo tocar ese fichero**. Pero aparecen en la
firma pública de `qc_lut()`, que va a llamar la GUI, y CONTRATOS dice que lo que
cruza una frontera entre módulos vive en `contracts.py`. **Se lo dejo dicho al
orquestador**: si los quiere ahí, que los mueva; la forma es ésta y no cambia.

---

## 10. Cosas que decidí solo y Mario podría querer cambiar

1. **`SALTO_MINIMO_BANDING = 0.02`** — el punto 3. Si los avisos de banding
   cansan, esto es lo que hay que subir.
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
