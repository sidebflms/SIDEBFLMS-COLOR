# SUPUESTOS — SIDEBFLMS COLOR

Día 8. Mario ha decidido seguir construyendo por delante de la validación contra
Resolve real, a propósito — el probe no se va a ejecutar por ahora. Es una decisión
legítima, pero sólo si el riesgo que se acumula está inventariado, no invisible. Este
documento es ese inventario: una fila por cada cosa que el proyecto da por cierta sin
haberla comprobado contra la realidad que decide (Resolve de verdad, o — para lo que
no depende de Resolve — material o especificación que todavía no hemos podido cruzar).

**Regla del día 8, ver también `CONTRATOS.md`:** ningún supuesto nuevo se hace sin su
fila aquí el mismo día que se hace. Si construyes algo hoy y te apoyas en algo que no
está medido, esta es la primera parada, no la última.

**Cómo leer cada fila.** Cinco datos, siempre en el mismo orden:

- **Qué suponemos** — la frase, sin jerga.
- **De dónde sale** — una de cuatro etiquetas, para poder distinguir de un vistazo lo
  sólido de la fe:
  - **DOCUMENTACIÓN OFICIAL** — está en un manual o white paper publicado por quien
    manda (Blackmagic, el fabricante de la cámara, un estándar ITU).
  - **OBSERVACIÓN DE MATERIAL REAL** — se ha medido contra archivos reales de Mario
    (LUTs, `.drx`), pero la muestra es pequeña o de una sola procedencia.
  - **INFERENCIA NUESTRA** — una deducción razonable, construida aquí, sin fuente
    externa que la respalde.
  - **FORO/COMUNIDAD** — de foros, hilos, respuestas de terceros sin relación oficial
    con quien manda.
- **Qué depende de ella** — archivos y funciones concretas.
- **Qué cambia si es falsa, y cuánto cuesta rehacerlo**.
- **Cómo se verificaría** — el experimento o la fuente que lo confirmaría el día que
  se pueda.

---

## A · Las preguntas del probe (`probe/api_probe.py`) y la séptima incógnita

Las nueve preguntas que el probe le haría a Resolve si se ejecutara. Cada una tiene
hoy una respuesta **conservadora** puesta a mano en el código — nunca la respuesta
optimista — precisamente para que un supuesto equivocado falle callado (la app no
ofrece algo que sí podría) en vez de sonoro (la app promete algo que no puede cumplir).

### A0 · V-0 — `GetCurrentVersion()` devuelve un nombre de versión usable

- **Qué suponemos:** que Resolve, para cualquier clip abierto, contesta a
  `GetCurrentVersion()` con un nombre de versión legible (o un diccionario con clave
  `versionName`/`name`), de forma consistente entre clips.
- **De dónde sale:** INFERENCIA NUESTRA, apoyada en foros de terceros sobre la API de
  Resolve — no hay confirmación oficial de Blackmagic de esta forma de respuesta.
- **Qué depende de ella:** literalmente toda escritura de la app. `core/resolve/bridge.py`
  pregunta la versión antes de cada escritura para no pisar el grado del usuario («la
  regla de oro»); si Resolve no contesta un nombre usable, la app se **niega** a
  escribir, no adivina.
- **Qué cambia si es falsa:** si `GetCurrentVersion()` no da un nombre fiable, la app
  no tiene forma segura de saber en qué versión está escribiendo, y toda la protección
  contra sobrescribir el grado del usuario deja de tener con qué trabajar. No es un
  parche pequeño: es la precondición de la que depende toda escritura.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta V-0 — la primera que hace el
  probe, y la más importante ("mira primero la V-0" es literalmente el primer aviso
  del informe). Ver `core/resolve/NOTAS.md` §comentarios en torno a la línea 140.

### A1 · F0-1 — `ExportStills(..., 'drx')` produce un `.drx` de verdad

- **Qué suponemos:** que exportar un still a formato `'drx'` funciona en la build de
  Mario. Conservador: **NO** — con la respuesta por defecto, `formatos_export_disponibles()`
  quita `"drx"` de la lista y la app no ofrece exportar PowerGrades.
- **De dónde sale:** INFERENCIA NUESTRA — `FORMATOS_EXPORT_STILL` sale de la
  documentación pública de `ExportStills`, pero que el formato `drx` específicamente
  funcione en esta build no está confirmado.
- **Qué depende de ella:** `core/resolve/incognitas.py::formatos_export_disponibles`,
  `Incognitas.export_drx_funciona`, y por extensión cualquier flujo que quiera sacar un
  PowerGrade real de Resolve para procesarlo con `core/io/drx.py`.
- **Qué cambia si es falsa:** ninguno — es la conservadora, así que "falsa" es el
  estado por defecto y la app ya está construida para eso. Si resulta ser **verdadera**
  lo que cambia es que se puede activar la exportación real.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-1.

### A2 · F0-2 — el still exportado lleva el grado aplicado, no el material limpio

- **Qué suponemos:** que `GrabStill()` + `ExportStills()` producen una imagen CON el
  grado del clip ya horneado. Conservador: **NO**, sale limpio — con la respuesta por
  defecto, `still_sirve_para_medir()` devuelve `False` y la app nunca usa un still como
  "antes/después".
- **De dónde sale:** INFERENCIA NUESTRA.
- **Qué depende de ella:** `core/resolve/incognitas.py::still_sirve_para_medir`.
- **Qué cambia si es falsa:** nada — conservadora por defecto. Si resulta verdadera,
  se abre un camino de medición «antes/después» sin tener que exportar `.cube` aparte.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-2.

### A3 · F0-3 — `SetLUT()` acepta un `.dctl`

- **Qué suponemos:** que el nodo de look puede llevar un `.dctl` además de un `.cube`.
  Conservador: **NO** — `extensiones_lut_aceptadas()` sólo deja pasar `.cube`.
- **De dónde sale:** INFERENCIA NUESTRA.
- **Qué depende de ella:** `core/resolve/incognitas.py::extensiones_lut_aceptadas`.
- **Qué cambia si es falsa:** nada, es lo que ya se asume — y de todas formas es lo
  que la app genera hoy (`.cube`), así que esta incógnita no bloquea nada actual.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-3.

### A4 · F0-4 — tipo de instalación (descarga directa / Mac App Store)

- **Qué suponemos:** que la instalación de Resolve de Mario es de **descarga directa**
  (no Mac App Store) — no hay opción "segura" aquí, una de las dos es la correcta.
- **De dónde sale:** INFERENCIA NUESTRA — "con mucho la más frecuente en instalaciones
  de Studio con llave", pero sin confirmarlo en esta máquina.
- **Qué depende de ella:** `core/resolve/incognitas.py::lut_dir` — decide la carpeta
  de LUTs ENTERA (la del Mac App Store vive dentro de un contenedor sandbox, ruta
  completamente distinta).
- **Qué cambia si es falsa:** `SetLUT` fallaría con "LUT no encontrado" en cuanto se
  use contra Resolve real; hay que enseñar la ruta que está usando para que se note
  rápido, no en silencio.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-4 — o, más simple,
  mirando a mano dónde está instalado Resolve en esta máquina.

### A5 · F0-5 — hace falta `OpenPage("color")` antes de escribir grado por script

- **Qué suponemos:** que sí hace falta. Conservador: **SÍ** — la app siempre abre la
  página de color antes de escribir (llamarlo de más no rompe nada; no llamarlo cuando
  hacía falta deja escrituras silenciosas que no se aplican).
- **De dónde sale:** INFERENCIA NUESTRA.
- **Qué depende de ella:** `core/resolve/bridge.py` (línea ~496, marcada `TODO(F0-5)`).
- **Qué cambia si es falsa:** nada roto — es una llamada de más, inofensiva. Si se
  confirma que no hace falta, se podría quitar por rendimiento, pero no es prioritario.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-5.

### A6 · F0-6 — Python 3.12 arm64 importa `fusionscript` limpiamente

- **Qué suponemos:** nada todavía — es la única de las seis que empieza en `None`
  ("no se sabe") en vez de con una respuesta conservadora, porque la app no depende de
  este valor para nada funcional: sólo se enseña en el informe.
- **De dónde sale:** sin clasificar — es una pregunta de diagnóstico del entorno, no
  una decisión de producto.
- **Qué depende de ella:** nada funcional. Sólo informativo.
- **Qué cambia si es falsa:** nada en la app; sí en el diagnóstico de por qué algo no
  conecta si algún día se prueba contra Resolve real.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-6.

### A7 · F0-7 — `SetClipProperty` acepta `"Input Color Space"` por clip

- **Qué suponemos:** que se puede fijar el espacio de entrada de cada clip por script,
  y que `GetClipProperty()` sin argumentos lista todas las claves reales que Resolve
  expone (de donde salen, en teoría, los nombres usados en la fila B más abajo).
- **De dónde sale:** INFERENCIA NUESTRA. Hoy `core.colormgmt` **no escribe nada en
  Resolve**: sólo detecta y avisa (`core/colormgmt/deteccion.py`,
  `core/colormgmt/verificacion.py`), precisamente porque esto no está confirmado.
- **Qué depende de ella:** el campo `clip_input_color_space_editable`, que **todavía
  no existe** en `core/resolve/incognitas.py` — hay que añadirlo el día que llegue la
  respuesta (ver `core/colormgmt/NOTAS.md`, sección "Lo que falta, deliberadamente").
- **Qué cambia si es falsa:** si no se puede escribir el espacio de entrada por clip,
  "ordenar la casa" (paso 1 del modo fácil) se queda para siempre en "detecta y
  pregunta", nunca en "detecta y aplica". Hay una alternativa ya prevista en el
  encargo del día 7 (plantilla `.drx` con el CST montado, una por cámara) si esto sale
  que no.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-7.

### A8 · F0-8 — `SetSetting` acepta los ajustes de gestión de color del proyecto

- **Qué suponemos:** que `project.SetSetting()` acepta `colorScienceMode`,
  `colorSpaceTimeline`, `colorSpaceOutput` y que, tras escribirlos, `GetSetting()` los
  devuelve confirmando el cambio.
- **De dónde sale:** INFERENCIA NUESTRA.
- **Qué depende de ella:** el mismo hueco que F0-7 en `core/colormgmt` — la vía
  "ajustes de proyecto" como alternativa o complemento a fijar el espacio por clip.
- **Qué cambia si es falsa:** una de las tres vías posibles (ajustes de proyecto,
  LUTs, plantilla de nodos) para resolver la gestión de color queda descartada; las
  otras dos siguen en pie.
- **Cómo se verificaría:** `probe/api_probe.py`, pregunta F0-8.

### A9 · La séptima incógnita (sin numerar) — `AddVersion()` hereda el árbol de nodos, o empieza en blanco

- **Qué suponemos:** que `AddVersion()` **hereda** el árbol de nodos del grado
  anterior. Es el caso nominal que simula `FakeResolve` por defecto
  (`version_hereda_grafo=True`).
- **De dónde sale:** INFERENCIA NUESTRA.
- **Qué depende de ella:** el diseño de tres nodos fijos entero (`core.contracts.NODE_NORMALIZACION
  = 1`, `NODE_BALANCE = 2`, `NODE_LOOK = 3`) y todo lo que escribe sobre esa
  numeración — `core/resolve/bridge.py::verificar_estructura_nodos` y quien lo llama.
- **Qué cambia si es falsa: es la fila más grave de todo este documento.** Si la
  versión nueva empieza en blanco (un solo nodo) y la API no deja crear nodos —
  confirmado que no deja, ver `core/resolve/NOTAS.md` §3.2 — **la app no puede
  escribir nada en absoluto**. No es un supuesto que degrade una función: es la
  precondición de la que depende que la app sirva para algo. No se ha metido en
  `Incognitas` (las seis) porque no cambia una sola línea de código — la comprobación
  "¿hay tres nodos?" es la misma en los dos casos — lo que cambia es si esa
  comprobación pasa alguna vez.
- **Cómo se verificaría:** el probe la mide aparte, como pregunta `EXTRA`: cuenta los
  nodos antes y después de `AddVersion()`. Ver `core/resolve/NOTAS.md` §4 ("La séptima
  incógnita, la que no está numerada").

---

## B · Los nombres de las claves de `GetClipProperty`

- **Qué suponemos:** que Resolve expone exactamente estas cinco claves, con estos
  nombres literales: `"Camera Manufacturer"`, `"Camera Type"`, `"Gamma Notes"`,
  `"Camera Notes"`, `"Input Color Space"`.
- **De dónde sale:** FORO/COMUNIDAD — "la mejor lectura de foros y documentación de
  terceros, no de Blackmagic" (`core/colormgmt/NOTAS.md`).
- **Qué depende de ella:** los cinco campos opcionales de `ClipRef`
  (`core/contracts.py`, líneas 481-492) y, por tanto, todo `core.colormgmt` — la
  detección de espacio de entrada por cámara (`core/colormgmt/deteccion.py`) no
  funciona si estas claves no existen o se llaman distinto.
- **Qué cambia si es falsa:** `core.colormgmt` dejaría de recibir metadata real de
  Resolve y trataría todos los clips como "sin metadata" — no rompe (el diseño ya
  trata el `None` como "no se sabe", nunca como Rec.709 por defecto), pero degrada la
  función entera a "siempre pregunta, nunca detecta sola". El arreglo es sencillo una
  vez se sepan los nombres reales: son cinco strings en un solo sitio.
- **Cómo se verificaría:** F0-7 pide explícitamente "listar todas las claves que
  devuelve `GetClipProperty()` sin argumentos" — cuando llegue la respuesta, volver a
  `core/colormgmt/NOTAS.md` y corregir los nombres si hace falta.

---

## C · El diseño de tres nodos fijos

- **Qué suponemos:** que la versión `SIDEB COLOR` que la app crea tiene siempre
  exactamente tres nodos, en este orden fijo: 1 normalización, 2 balance, 3 look
  (`core.contracts.NODE_NORMALIZACION/NODE_BALANCE/NODE_LOOK`).
- **De dónde sale:** INFERENCIA NUESTRA, condicionada a A9 de arriba (que
  `AddVersion()` herede el grafo) — si hereda del grado justo anterior y ESE grado ya
  tenía tres nodos en ese orden (porque la app los dejó así la vez anterior, o porque
  el usuario empezó con un timeline recién importado sin grado), la numeración se
  sostiene. Si el grado heredado tenía un número distinto de nodos, la app se para y
  avisa en vez de asumir (`bridge.verificar_estructura_nodos`).
- **Qué depende de ella:** toda escritura de grado — `core/resolve/bridge.py`, y todo
  lo que en el modo fácil/avanzado construye un CDL+LUT pensando en "el nodo 3 es el
  look".
- **Qué cambia si es falsa:** si el número de nodos no es tres, la app ya está
  diseñada para pararse y decirlo (no escribe a ciegas) — el coste no es un bug
  silencioso, es que la app se niega a trabajar hasta que el timeline tenga la
  estructura que espera. Distinto es el hallazgo de §3.1 de `FORMATO-DRX.md`: el
  índice de nodo dentro del `.drx` exportado **no es** necesariamente 1-based por
  clip (ver fila D3 más abajo) — eso afecta a LEER un `.drx` ajeno, no a la escritura
  propia de la app, que controla su propia numeración porque es ella quien la crea.
- **Cómo se verificaría:** contra Resolve real, escribiendo una versión de prueba y
  mirando la página de color a ojo. No lo mide el probe hoy.

---

## D · El formato `.drx` (protobuf sin esquema publicado)

Detalle completo en `core/io/FORMATO-DRX.md` — aquí sólo el resumen de qué se da por
sentado y de dónde sale, sin duplicar la explicación.

### D1 · Los números de campo del protobuf

- **Qué suponemos:** que campo 1 del mensaje raíz es el grafo, campo 7 dentro de él
  se repite una vez por nodo, y campo 1 dentro de cada nodo es su índice — y que estos
  números de campo son estables entre archivos y (sin confirmar) entre versiones de
  Resolve.
- **De dónde sale:** OBSERVACIÓN DE MATERIAL REAL — pero de **10 archivos, de una
  única versión de Resolve** (`21.1.0.0017`, confirmado en `core/io/FORMATO-DRX.md`
  §4b). No hay ningún `.drx` de otra versión con el que comprobar si los campos se
  mueven entre builds.
- **Qué depende de ella:** `core/io/drx_protobuf.py`, `core/io/drx.py` entero.
- **Qué cambia si es falsa** (en una versión de Resolve distinta): un `.drx` de esa
  versión se leería con datos con FORMA plausible y VALOR posiblemente incorrecto —
  el peor fallo posible aquí. Por eso `core/io/drx.py::version_resolve()` +
  `advertencia_version_desconocida()` (día 7) avisan explícitamente cuando ven una
  versión fuera de `VERSIONES_RESOLVE_CONFIRMADAS` (hoy, sólo la una que tenemos), en
  vez de leer mal en silencio.
- **Cómo se verificaría:** conseguir `.drx` reales de otra versión de Resolve y
  repetir la disección byte a byte. Ver `core/io/FORMATO-DRX.md` §6 para el método.

### D2 · El byte de cabecera `0x81`

- **Qué suponemos:** nada, en realidad — está marcado explícitamente como sin
  explicación. Se documenta aquí porque es un valor del que se depende (se comprueba
  que sea exactamente ese) sin saber qué significa.
- **De dónde sale:** OBSERVACIÓN DE MATERIAL REAL — constante en las 20 muestras (2
  por archivo × 10), así que no se ha podido aislar su función por comparación.
- **Qué depende de ella:** `core/io/drx.py::descomprimir_body` — rechaza cualquier
  `<Body>` cuyo primer byte no sea `0x81`.
- **Qué cambia si es falsa** (si en otra versión de Resolve el byte fuera distinto):
  `descomprimir_body` devolvería `None` para un `.drx` real perfectamente válido —
  fallo seguro (dice "no sé leer esto"), no un fallo silencioso.
- **Cómo se verificaría:** lo mismo que D1 — material de otra versión de Resolve.

### D3 · El índice de nodo como contador global de proyecto

- **Qué suponemos:** que el índice de nodo del `.drx` (campo 1 dentro del nodo) es un
  contador incremental de TODO el proyecto de Resolve, no un índice que empiece en 1
  por cada clip.
- **De dónde sale:** OBSERVACIÓN DE MATERIAL REAL — pero de sólo **2 de los 10**
  archivos (los dos "de trabajo real", con 18 y 22 nodos e índices 260-281). Los otros
  8 (grados sencillos, 2-5 nodos) no lo pueden confirmar ni desmentir, porque un
  índice 1-based por clip y un contador global coinciden en los primeros números.
- **Qué depende de ella:** ninguna función de la app hoy depende de que esto sea
  cierto — es una nota de precaución para no interpretar mal `NodoDRX.indice` como
  "posición 1/2/3 en la página de color" si alguien lo usa así en el futuro.
- **Qué cambia si es falsa:** nada se rompe (nada lo usa todavía); simplemente el
  comentario de aviso en `core/io/drx.py` dejaría de ser necesario.
- **Cómo se verificaría:** comparar contra lo que Resolve muestra en la página de
  color para ese mismo proyecto — necesita conexión a Resolve, que hoy no hay.

### D4 · Presencia condicional de `ReelName`/`ClipThumbnails`/`TrackThumbnails`

- **Qué suponemos:** que estas tres etiquetas aparecen sólo cuando el clip de origen
  tiene esos metadatos, y no por alguna otra condición no identificada.
- **De dónde sale:** OBSERVACIÓN DE MATERIAL REAL, de los 10 archivos — pero sin
  aislar la condición exacta.
- **Qué depende de ella:** nada crítico — son etiquetas de metadata plana que hoy no
  se usan para decidir nada en la app.
- **Qué cambia si es falsa:** nada funcional; sólo el comentario en
  `core/io/FORMATO-DRX.md` §1.
- **Cómo se verificaría:** más archivos reales con distintas combinaciones de
  metadata de origen.

### D5 · `pTrackVer` con contenido real

- **Qué suponemos:** nada todavía — es un hueco declarado, no un supuesto activo. Se
  incluye para que quede inventariado: **no hay ningún ejemplo en el material de
  Mario de un grado de pista (`pTrackVer`) con contenido**, así que todo lo que
  `core/io/drx.py` hace con `pTrackVer` sólo se ha probado contra el caso vacío.
- **De dónde sale:** OBSERVACIÓN DE MATERIAL REAL (ausencia de casos, en los 10
  archivos).
- **Qué depende de ella:** `core/io/drx.py::leer_grado` cuando se le pasa el `<Body>`
  de `pTrackVer` en vez de `pClipFullVer`.
- **Qué cambia si es falsa** (si un `pTrackVer` real tuviera una forma distinta a la
  esperada): el lector podría fallar de forma no probada — no hay test que lo cubra
  hoy, sólo el caso vacío.
- **Cómo se verificaría:** un archivo real con grado de pista (track) aplicado, no
  sólo de clip.

---

## E · La tabla de espacios de entrada por cámara

- **Qué suponemos, y qué NO se supone — hay dos cosas mezcladas y conviene
  separarlas:**
  1. Los **primarios y la curva de transferencia** de cada espacio
     (`core/color/spaces.py::SPACES`) SÍ salen de documentación oficial publicada por
     cada fabricante (ver la fuente exacta abajo) — esto NO es un supuesto, es un dato
     verificado contra la fuente que manda.
  2. El **mapeo de metadata textual a esa variante concreta** (`core/colormgmt/deteccion.py::REGLAS_DECISION`)
     — que si `camera_manufacturer` contiene "sony" y `gamma_notes` contiene
     "s-log3", el espacio es exactamente `S-Gamut3.Cine` y no alguna otra variante de
     gamut de Sony (existe también `S-Gamut3` a secas, con primarios distintos) — **eso
     SÍ es un supuesto**: asume que cuando la metadata sólo dice la curva (log) y el
     fabricante, sin especificar el gamut, la cámara usó la combinación más habitual.
- **De dónde sale:**
  - Primarios/curva: DOCUMENTACIÓN OFICIAL — Sony *Technical Summary for
    S-Gamut3.Cine/S-Log3*, Panasonic *V-Log/V-Gamut Reference Manual*, Canon *White
    Paper on Canon Log Gamma Curves*, DJI *D-Log/D-Gamut White Paper*, y BT.709-6 para
    Rec.709 (citas exactas en `core/color/spaces.py::SPACES`).
  - El mapeo metadata→variante: INFERENCIA NUESTRA.
- **Qué depende de ella:** `core/colormgmt/deteccion.py::REGLAS_DECISION` y todo el
  paso 1 del modo fácil ("ordenar la casa").
- **Qué cambia si es falsa:** si un clip real de Sony viene en `S-Gamut3` (no
  `.Cine`) y la metadata no lo distingue, la app aplicaría la conversión de entrada
  equivocada — un error silencioso de gestión de color, justamente la clase de fallo
  que el punto 3 del encargo ("si no se puede determinar con seguridad, no se
  adivina") quiere evitar. Mitigación parcial ya en el diseño: si la metadata es
  ambigua de cualquier forma, `detectar_espacio_clip` devuelve `segura=False` y no
  aplica nada sin preguntar — pero esta variante concreta de gamut-sin-especificar no
  se distingue como ambigua hoy, se asume sin más.
- **Cómo se verificaría:** clips reales con metadata que declare el gamut explícito
  (no sólo la curva), para medir cuántas veces coincide con la variante asumida.

---

## F · Los 36 umbrales sin validar contra material real

- **Qué suponemos:** que 36 de las 44 constantes de `core/umbrales.py` — las de
  `core/matching`, `core/reverse` y `core/analysis`, más `DELTA_E_INDISTINGUIBLE` y los
  dos límites de entrega T1/T3 — funcionan igual de bien contra material real que
  contra los ejemplos sintéticos (`core/io/lut_malos.py`, `tests/media/generate.py`,
  `tests/calibracion*`) contra los que sí se han probado.
- **De dónde sale:** INFERENCIA NUESTRA — y una sospecha con algo de evidencia en
  contra: de los 8 umbrales que SÍ se pudieron auditar contra material real el día 7,
  los 3 que son criterios de "esto está mal" (banding, monotonía, y antes la MAD de
  viñeta del día 2) dispararon sistemáticamente contra material real limpio y
  profesional. No hay garantía de que el mismo patrón no se repita en estos 36, pero
  tampoco hay medida que lo confirme.
- **Qué depende de ella:** ingeniería inversa de grado (`core/reverse`), emparejamiento
  de clips (`core/matching`), estadística de piel/neutro (`core/analysis`), y los
  criterios de entrega T1/T3. No se duplica la lista completa aquí — está en
  `CIFRAS.md` §20 ("Por qué los 36 restantes no se pudieron mover"), con ejemplos por
  módulo y qué haría falta para auditar cada grupo.
- **Qué cambia si es falsa:** cualquiera de estos umbrales podría estar disparando
  (o fallando en disparar) sistemáticamente contra material real profesional, igual
  que le pasó a banding y monotonía — sin saberlo, porque nadie lo ha podido
  comprobar todavía.
- **Cómo se verificaría:** brutos + máster de un trabajo real de Mario (lo que pide
  `pruebas/primera_real.py` desde el día 4) — es el cuello de botella más repetido de
  todo este documento: casi todo lo de `core/reverse`/`core/matching` necesita
  metraje real, no LUTs ni `.drx` terminados, y ese metraje todavía no existe en el
  repo.

---

## G · Supuestos hechos hoy, construyendo el tutor (tarea 2)

### G1 · La saturación del tutor se mide en código de trabajo, no en escena

- **Qué suponemos:** que el histograma de saturación de `core.analysis.ColorStats`
  (calculado en `WORKING_SPACE = davinci_wg_intermediate`, que es **logarítmico**) sirve
  para decidir "este plano tiene mucha saturación extrema" sin corregir nada.
- **De dónde sale:** INFERENCIA NUESTRA, y se descubrió a medio construir: probando la
  regla `saturacion_extendida` (`core/tutor/catalogo.py`) contra un primario puro de
  Rec.709 escena-lineal, la saturación cae a ~0,48 tras codificarse en `WORKING_SPACE`, no
  a 1,0 — la curva log comprime cada canal de forma distinta cerca de los extremos, así
  que "saturación" en código de trabajo no es lo mismo que "saturación en escena".
- **Qué depende de ella:** `core/tutor/catalogo.py::_regla_saturacion_extendida` y su
  umbral `_SUELO_SATURACION_ALTA = 0.05`.
- **Qué cambia si es falsa (o, más bien, ya que se sabe que es una aproximación floja):**
  la regla es probablemente CONSERVADORA — puede no avisar de un plano realmente muy
  saturado en escena porque su código de trabajo no llega al umbral. No hay caso conocido
  de lo contrario (avisar de más). Corregirlo significa guardar los píxeles del análisis
  (`guardar_pixeles=True`) y recalcular saturación sobre una conversión a un espacio
  display-referido antes de contar el histograma — no hubo presupuesto para eso hoy. Ver
  `core/tutor/NOTAS.md`.
- **Cómo se verificaría:** repetir la medición contra material real con saturación
  extrema conocida (una carta de color, un neón) y comparar el aviso con lo que se ve a
  ojo en un monitor calibrado.

### G2 · El punto negro se reporta pasado por la curva de cámara Rec.709

- **Qué suponemos:** que convertir `black_point` (percentil 1, en `WORKING_SPACE`) a la
  curva de cámara Rec.709 (BT.709-6) antes de mostrarlo como porcentaje da un número que
  se lee como "tanto por ciento de recorrido tonal" de forma razonable — no que sea
  EXACTAMENTE lo que un monitor de grado calibrado enseñaría en un waveform.
- **De dónde sale:** INFERENCIA NUESTRA. Rec.709 (la curva de cámara, no la de monitor)
  es el "camino conocido" más cercano de los que ya cita `core.color.spaces.SPACES` con
  fuente oficial (ITU-R BT.709-6), pero convertir un código de trabajo interno a esa curva
  con fines de "legibilidad" es una decisión de presentación nuestra, no un estándar de
  cómo mostrar puntos negros.
- **Qué depende de ella:** `core/tutor/catalogo.py::_porcentaje_rec709`,
  `_regla_punto_negro`.
- **Qué cambia si es falsa:** el NÚMERO que ve Mario en la frase podría no coincidir con
  lo que Resolve enseñaría en su propio waveform/vectorscope — seguiría siendo una medida
  real del material (no inventada), pero la lectura en "%" podría inducir a una
  comparación directa con Resolve que no es exacta.
- **Cómo se verificaría:** comparar el número de la frase contra el waveform de Resolve
  para el mismo fotograma, con Resolve real delante.

### G3 · Los "suelos" de las reglas descriptivas son arbitrarios, no medidos

- **Qué suponemos:** que `_SUELO_NEGRO_VISIBLE = 0.02` (2%) y
  `_SUELO_SATURACION_ALTA = 0.05` (5% del histograma en el cuarto más alto) son puntos
  razonables de "aquí hay algo que merece una frase" — no umbrales de "esto está mal": las
  dos reglas son `"descriptiva"` a propósito (`core/tutor/catalogo.py`), nunca afirman un
  veredicto.
- **De dónde sale:** INFERENCIA NUESTRA — números elegidos por sentido común (una décima
  de la resolución de un `uint8`, un cuarto del histograma), no calibrados contra material
  real. No están en la auditoría de `CIFRAS.md` §20 porque no son umbrales de
  `core/umbrales.py`: son puramente de "cuándo vale la pena decir algo", parte del
  contrato de la regla, no un criterio de calidad.
- **Qué depende de ella:** las dos reglas descriptivas del catálogo del tutor.
- **Qué cambia si es falsa:** las reglas podrían hablar de más (ruido, si el suelo es
  demasiado bajo) o de menos (silencio cuando debería decir algo, si es demasiado alto) —
  en cualquiera de los dos casos degrada la UTILIDAD del tutor, no su honestidad: la regla
  nunca afirma un veredicto, así que un suelo mal puesto no hace que mienta, sólo que
  hable en el momento equivocado.
- **Cómo se verificaría:** con material real y opiniones de Mario sobre qué planos
  merecían un aviso y cuáles no, ajustar los suelos por prueba y error — no hay atajo
  matemático para esto, es una calibración de producto, no de física.

### G4 · `opciones.py` depende de `AddVersion()` (ya inventariado en la fila A9)

No es un supuesto nuevo — es la fila A9 de la sección A, aplicada aquí: cada
`OpcionLook` se escribe como una versión de Resolve separada
(`core/tutor/opciones.py::aplicar_opciones_como_versiones`), y esa escritura entera
depende de que `AddVersion()` herede el árbol de nodos. Se referencia aquí en vez de
duplicarse porque es exactamente la misma incógnita, no una nueva.
