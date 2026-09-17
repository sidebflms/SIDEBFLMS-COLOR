# FORMATO `.drx` — lo confirmado y lo supuesto

**Día 6 (17-09-2026).** Hasta ayer `core/io/drx.py` era un inspector honesto que no
asumía nada porque no había ningún `.drx` real que mirar. Hoy Mario dejó diez, en
`tests/powergrades_reales/` (solo lectura, nunca se versionan, ver `.gitignore`). Este
documento dice qué se pudo confirmar mirándolos y comparándolos, y qué sigue siendo una
suposición razonable sin verificar.

**Regla de este documento:** cada afirmación dice **en cuántos de los 10 archivos** se
comprobó. Si no lleva ese número, es una suposición, y se marca como tal explícitamente.

---

## 0 · Antes de parsear nada: qué son los diez archivos, físicamente

Los diez, mirados con `file(1)` y a mano con un editor hex antes de escribir una sola
línea de parser:

| Archivo | Tamaño | Tipo (`file`) |
|---|---|---|
| `Still …_1.1.1.drx` | 30.630 B | XML 1.0, ASCII, UTF-8 |
| `Still …_1.162.1.drx` | 57.291 B | ídem |
| `Still …_1.2.1.drx` | 31.788 B | ídem |
| `Still …_1.3.1.drx` | 30.758 B | ídem |
| `Still …_1.38.1.drx` | 370.140 B | ídem |
| `Still …_1.5.1.drx` | 33.472 B | ídem |
| `Still …_1.52.1.drx` | 421.583 B | ídem |
| `Still …_1.6.1.drx` | 23.415 B | ídem |
| `Still …_2.4.1.drx` | 29.226 B | ídem |
| `Still …_I.Still.drx` | 60.556 B | ídem |

**Confirmado en 10 de 10: son texto XML plano, codificación UTF-8, sin compresión ni
cifrado a nivel de archivo.** La suposición de foro ("`.drx` es XML") era correcta —
pero incompleta, ver §2.

**Todos los nombres empiezan por `Still `**, no por el nombre del PowerGrade. Los diez
son *Gallery Stills* exportados de la galería de Resolve (`Save Still`/`Export`), no
"PowerGrades" en el sentido de un archivo separado de un álbum de PowerGrades. Esto
importa: en el modelo de datos de Resolve, un **PowerGrade es un Still con grado
asociado guardado en un álbum especial de la galería** — el formato de archivo es el
mismo (confirmado: los diez usan el mismo elemento raíz y la misma estructura, sea cual
sea su complejidad de grado). El código de este repo puede tratar "leer un `.drx`" como
una sola función sin distinguir still/PowerGrade a nivel de archivo.

---

## 1 · La capa XML

**Elemento raíz: `<Gallery::GyStill DbId="…">`, confirmado en 10 de 10.**

Etiquetas de segundo nivel (metadata plana), confirmadas en 10 de 10: `FieldsBlob`,
`SrcHint`, `SrcType`, `GalleryPath`, `Label`, `RecTC`, `SrcTC`, `DpxDescriptor`,
`Width`, `Height`, `BitDepth`, `PAR`, `Endianship`, `CreateTime`, `pClipFullVer`,
`pTrackVer`, `PrimaryCCMode`, `Vsr`. Tres etiquetas más aparecen sólo en algunos:
`ReelName`, `ClipThumbnails`, `TrackThumbnails` (SUPUESTO: probablemente presentes sólo
cuando el clip de origen tiene esos metadatos; no se ha aislado la condición exacta).

**Hallazgo que cambia cómo hay que parsear esto: los nombres de etiqueta usan DOS
puntos** — `<Gallery::GyStill>`, `<ListMgt::LmVersion>`, `<BtThumnail>` (sin doble
punto, ese es un nombre simple). Confirmado en 10 de 10.

Esto **no es XML válido según "Namespaces in XML"**: un nombre local no puede contener
`:`. `xml.etree.ElementTree.fromstring()` de Python lo rechaza (`not well-formed
(invalid token)`) porque construye su parser `expat` interno con
`namespace_separator` fijado — a diferencia de `expat.ParserCreate()` a secas, cuyo
valor por defecto es `None` (sin procesar namespaces), y que sí lo acepta. La solución,
implementada en `core/io/drx.py::_parsear_xml_sin_namespaces`, es construir el árbol a
mano con `expat.ParserCreate()` + `ElementTree.TreeBuilder`. **No es un archivo roto:
es Resolve escribiendo XML con un formador de nombres que no respeta esa regla del
estándar**, y cualquier lector tiene que desactivar el procesamiento de namespaces para
leerlo.

**`<Body>` (dentro de `pClipFullVer` y `pTrackVer`) es texto hexadecimal ASCII de un
blob binario — nunca contenido XML.** Confirmado en 20 de 20 (2 por archivo × 10). Cada
carácter par de hex = un byte. Todo el resto de esta investigación es sobre ese blob.

**El resto de etiquetas de metadata son texto plano legible** (fechas ISO, timecodes,
enteros) y no se han investigado más allá de leerlas literalmente — no hacía falta para
las tareas del día 6.

---

## 2 · El blob de `<Body>`: cabecera + Zstandard + Protocol Buffers

### 2.1 La cabecera

**Confirmado en 20 de 20 `<Body>`: el primer byte, tras decodificar el hex, es
`0x81`.** No se sabe qué codifica — no varía entre los 10 archivos ni entre
`pClipFullVer`/`pTrackVer`, así que no se ha podido aislar su función por comparación.
SUPUESTO: es un byte de versión de formato o un flag de tipo de compresión, fijado a un
único valor observado porque Resolve 21.1 sólo ha escrito ese valor hasta ahora.

### 2.2 El resto es un frame Zstandard

**Confirmado en 20 de 20: los bytes a partir del segundo descomprimen con
Zstandard** (`zstandard.ZstdDecompressor().decompress(...)`, sin diccionario). Se probó
primero con la CLI `zstd -d` del sistema, luego con la librería Python `zstandard`
(añadida como dependencia del proyecto: `pyproject.toml`).

Compresión observada (crudo comprimido → descomprimido), de menor a mayor: 100→106 B
hasta 5.966→42.046 B. El ratio de compresión no es constante (varía de ~1.1× a ~7×
según el contenido), coherente con Zstandard a nivel de compresión por defecto sobre
datos con mucha repetición estructural (protobuf con muchos campos de longitud fija).

### 2.3 El contenido descomprimido es Protocol Buffers, sin `.proto` publicado

**Confirmado en 20 de 20: el blob descomprimido parsea limpiamente como secuencia de
campos del *wire format* de Protocol Buffers** (tag = `numero_campo << 3 | wire_type`,
seguido del valor según `wire_type` ∈ {0 varint, 1 64-bit, 2 length-delimited, 5
32-bit}) — implementado en `core/io/drx_protobuf.py`, sin depender de `protoc` ni de la
librería `protobuf` (no hace falta el `.proto`, que Blackmagic no publica: el wire
format en sí es suficiente para leer valores, sólo no da nombres a los campos).

**No hay ningún campo con `wire_type` desconocido ni bytes sobrantes en ninguno de los
20 blobs** — es una señal fuerte de que la lectura del wire format es correcta y
completa, no una coincidencia sobre un formato distinto.

---

## 3 · El grafo de color dentro del protobuf

Trabajando sólo sobre el `<Body>` de `pClipFullVer` (el primero de los dos; el de
`pTrackVer` se trata en §3.4):

### 3.1 Los nodos

**Confirmado en 10 de 10: el campo 1 del mensaje raíz es un submensaje (el "grafo"), y
dentro de él, el campo 7 se repite una vez por nodo del grafo de color.** Cada
repetición de campo 7 es, a su vez, un submensaje cuyo campo 1 es un entero — el índice
del nodo.

**Hallazgo importante, confirmado en 2 de 10 (los dos archivos de "trabajo real":
`_1.38.1` y `_1.52.1`): el índice de nodo NO es 1-based por clip.** Esos dos archivos
traen 18 y 22 nodos con índices **260 a 281** (consecutivos, pero no empezando en 1). En
los otros 8 archivos (grados más sencillos, de 2 a 5 nodos) los índices sí van de 1 a N.
La lectura más probable: **el índice es un contador incremental de todo el proyecto de
Resolve** (cada nodo que se crea, en cualquier clip, se lleva el siguiente número), no
un índice reiniciado por clip como asume hoy `core.contracts.NODE_NORMALIZACION=1` /
`NODE_BALANCE=2` / `NODE_LOOK=3`. **Esto es SUPUESTO, no confirmado del todo**: no se ha
podido comparar contra lo que Resolve muestra en la página de color para ese mismo
proyecto (no hay conexión a Resolve, ver los límites del encargo). Si se confirma, tiene
una consecuencia de diseño: **`NodoDRX.indice` de este módulo no se puede usar
directamente como "posición 1/2/3 del nodo en la página de color"**, y `core/io/drx.py`
lo documenta así explícitamente para que nadie lo use mal más adelante.

**Cuántos nodos trae cada grado, confirmado por archivo:**

| Archivo | Nodos | LUTs referenciados |
|---|---|---|
| `_1.1.1` | 2 | 2 (conversión + look) |
| `_1.2.1` | 2 | 2 (conversión + look, mismos que `_1.1.1`) |
| `_1.6.1` | 2 | 1 |
| `_1.162.1` | 3 | 1 |
| `_1.3.1` | 4 | 1 |
| `_2.4.1` | 4 | 1 |
| `_1.5.1` | 5 | 1 |
| `_I.Still` | 5 | 1 |
| `_1.38.1` | 18 | 1 |
| `_1.52.1` | 22 | 1 |

### 3.2 Las herramientas de un nodo, y las rutas de LUT

**Confirmado en 10 de 10: al menos un nodo del grado referencia un LUT por ruta
relativa de texto**, encontrada como una hoja de texto en el subárbol del nodo (ver
§3.3 sobre por qué se buscó así y no por una ruta de campos fija). Ejemplos reales
(rutas completas, tal cual las escribió Resolve):

- `Sony/SLog3SGamut3.CineToLC-709.cube` (conversión de espacio de entrada, cámara Sony)
- `SIDEBFLMS/DJI OSMO Pocket 4 D-Log to Rec.709 V1.0.cube` (conversión, cámara DJI)
- `SIDEBFLMS/EKTAR 100 REC709 SONY.cube`, `SIDEBFLMS/EKTAR 100 SIDEB SONY.cube` (look)
- `SIDEBFLMS/SIDEBFLMS NIGHT SONY.cube` (look)
- `SIDEBFLMS/SECRET SAUCE/A1 SECRET SAUCE LUTs V2/4 (-) AMSTERDAM SILVER V2.cube`,
  `…/5 (-) BALI GREEN V2.cube` (look, de una biblioteca de LUTs organizada en
  subcarpetas)

**Confirmado en 2 de 10 (`_1.1.1`, `_1.2.1`): un mismo grado puede referenciar DOS LUTs
a la vez, en dos nodos distintos** — uno de conversión de espacio de cámara (`Sony/…`) y
otro de look (`SIDEBFLMS/SECRET SAUCE/…`). Esto confirma, con material real, el diseño
de nodos que la app ya asumía (normalización/conversión + look), aunque el *índice* de
esos nodos no sea 1 y 3 literalmente (ver §3.1).

Las rutas son **siempre relativas a la carpeta de LUTs de Resolve de la máquina donde se
grabó** (nunca absolutas, nunca con letra de unidad ni `/Users/…`). Confirmado en 10 de
10. Esto es lo que hace necesario el avisador de dependencias (§4): la misma carpeta de
LUTs en otro Mac puede tener una estructura de subcarpetas distinta.

**El ID de parámetro `2248147105` (un entero de 32 bits, no un nombre) es,
en los 8 casos donde se pudo aislar con más detalle, el que lleva el string de la
ruta.** Se documenta como dato adicional, pero el lector de este repo
(`core/io/drx.py::leer_grado`) **no depende de ese número exacto**: busca cualquier
string en todo el subárbol del nodo que termine en `.cube` o `.dctl` (§3.3). Fijar el ID
de campo habría sido más preciso pero más frágil (Resolve podría cambiar la
numeración de campos entre builds sin avisar; el propio protobuf de Google está
diseñado para que añadir/quitar campos no rompa a un lector viejo, pero mover el
*significado* de un número sí lo haría).

### 3.3 Por qué se buscó por texto en vez de fijar la ruta de campos exacta

La ruta completa de campos hasta el string de un LUT, medida a mano en un ejemplo, es:
`raiz.1` (grafo) `.7` (nodo, repetido) `.9` (herramienta) `.1` (ficha) `.6`
(parámetros) `.2` (grupo, repetido) `.3` (parámetro, repetido) `.1` = ID, `.2` =
valor. Siete niveles. Fijar esa ruta exacta en el lector sería frágil: si Resolve
inserta un campo intermedio en una build futura, la ruta se rompe entera y el lector
deja de encontrar nada, en silencio.

En su lugar, `core/io/drx_protobuf.py::hojas_bytes` **aplana recursivamente TODO el
subárbol del nodo** y `core/io/drx.py::leer_grado` mira cada hoja de texto: si termina
en una extensión conocida (`.cube`, `.dctl`, …), es una referencia. Es menos preciso
(no distingue "el LUT de conversión" de "el LUT de look" salvo por el orden en que
aparecen) pero mucho más robusto a cambios de estructura entre versiones de Resolve —
y es exactamente lo que hacía falta para el avisador de dependencias (§4), que sólo
necesita saber QUÉ archivos hacen falta, no en qué campo exacto vive cada uno.

### 3.4 `pTrackVer` (el segundo `<Body>`)

**Confirmado en 10 de 10: el body de `pTrackVer` descomprime y parsea igual que el de
`pClipFullVer`, pero SIN ningún campo 7 con contenido** (0 nodos en los 10 casos). Es
la plantilla del "grado de pista/track" (el grafo post-clip de un grupo de color, o el
grado de la pista de timeline) — en ninguno de los diez ejemplos de Mario se usa. Trae
una matriz identidad 3×3 en uno de sus campos (`campo 15` dentro de un subcampo,
`0000803f` repetido en la diagonal = `1.0f`), coherente con "sin transformación".
**SUPUESTO**: no se ha visto ningún ejemplo real con grado de pista activo, así que no
se sabe si el patrón de nodos/LUT de §3.1-3.3 se aplicaría igual ahí.

---

## 4 · El avisador de dependencias, probado contra material real

Con `core/io/drx.py::avisar_dependencias_faltantes`, sobre los 10 archivos, comparando
contra `tests/luts_reales/` (recursivo, por nombre de archivo — nunca por ruta completa,
ver §3.2 sobre por qué las rutas no coinciden entre máquinas):

**9 de 10 archivos: todas las rutas referenciadas se encuentran.** El único caso con un
archivo faltante es `_1.1.1.drx` (y su gemelo `_1.2.1.drx`, mismo par de LUTs):
`Sony/SLog3SGamut3.CineToLC-709.cube` **no está** en `tests/luts_reales/`. Es
coherente con lo que se esperaría: ese LUT viene instalado de fábrica con Resolve (es
un LUT de conversión de cámara Sony, no un LUT personalizado de Mario), así que no
tendría por qué estar en la carpeta de LUTs propios que Mario copió — el aviso es
correcto igualmente: en un Mac SIN esa instalación de fábrica (o con Resolve
instalado en otra ruta), el PowerGrade se aplicaría mal y en silencio.

---

## 5 · Lo que queda abierto, explícitamente

1. **El significado exacto del byte de cabecera `0x81`** — constante en las 20
   muestras, así que no se pudo aislar comparando.
2. **Si el índice de nodo es de verdad un contador global de proyecto** (§3.1) — muy
   probable por la evidencia, no confirmado contra el propio Resolve.
3. **El significado de los demás IDs de parámetro** (posición del nodo en el lienzo,
   color de resaltado, y sobre todo los valores numéricos de rueda/CDL) — no hacía
   falta para las tareas del día 6 (nodos + rutas de LUT), así que no se ha investigado
   más allá de lo que aparece de pasada en este documento.
4. **`pTrackVer` con contenido real** — no hay ningún ejemplo en el material de Mario.
5. **Cualquier tipo de `.drx` que no sea un Still/PowerGrade** (p.ej. un `.drx` de
   timeline completo, si existe como formato de exportación distinto) — fuera del
   alcance de lo que Mario dejó.

## 6 · Cómo reproducir cualquier cifra de este documento

```bash
.venv/bin/python -m pytest tests/test_io_drx.py -q -k reales
```

Se salta solo si `tests/powergrades_reales/` no existe o está vacía. Los números
concretos de la tabla de §3.1 se pueden volver a sacar con:

```bash
.venv/bin/python -c "
from core.io.drx import buscar_rutas_referenciadas, descomprimir_body, leer_grado
import re, glob
for fn in sorted(glob.glob('tests/powergrades_reales/*.drx')):
    body = re.findall(r'<Body>([0-9a-f]*)</Body>', open(fn, encoding='utf-8').read())[0]
    grado = leer_grado(descomprimir_body(body))
    print(fn, len(grado.nodos), 'nodos,', grado.rutas_lut)
"
```
