# NOTAS — agente E · resolve

Qué decidí, qué descarté y por qué. Escrito la noche del 15 de septiembre de 2026,
con Resolve cerrado y sin licencia en la máquina, así que **nada de esto se ha
probado contra Resolve de verdad**.

---

## 1. Qué hay aquí

| Archivo | Qué es |
|---|---|
| `incognitas.py` | Las seis preguntas sin responder, como constantes. Es lo que se cambia mañana. |
| `bridge.py` | Las excepciones, las validaciones y **la secuencia segura** de escritura. |
| `fake.py` | `FakeResolve`. Es contra lo que se prueba toda la app esta noche. |
| `live.py` | El puente de verdad. **Sin estrenar.** No lo importa nadie al arrancar. |
| `__init__.py` | Lo que se usa. Importarlo NO toca Resolve. |

Importar `core.resolve` no carga `DaVinciResolveScript`, ni `fusionscript`, ni
PySide6. Hay un test que lo comprueba en un proceso limpio
(`tests/test_resolve_probe.py::test_importar_core_resolve_no_carga_resolve`), por
si algún día a alguien se le ocurre enganchar `live.py` al `__init__`.

---

## 2. La regla de oro, y dónde está escrita

**Nada destructivo.** Antes de escribir un solo número se crea (o se selecciona,
si ya estaba) la versión `SIDEB COLOR`, y todo se escribe ahí. El grado que tenía
Mario se queda intacto en su versión.

Eso vive en `bridge.aplicar_grado_seguro()`, que es el único camino por el que la
app debería escribir color. El orden es:

1. Abrir la página de color (si la incógnita F0-5 dice que hace falta).
2. Crear o seleccionar la versión `SIDEB COLOR`. **Nada se escribe antes de esto.**
3. Comprobar que están los tres nodos. Si no están, se para aquí.
4. CDL al nodo 2.
5. LUT al nodo 3.
6. Releer el LUT con `GetLUT` para confirmar que cuajó.

El paso 6 no se puede hacer con el CDL, y esa es la primera cosa importante de
esta nota.

---

## 3. Lo que quise hacer y la API no deja

Esto es lo que más te va a servir, así que va entero y sin adornos.

### 3.1 No se puede leer el grado de un clip

`SetCDL` es de sólo escritura. **`GetCDL` no existe.** No hay forma de preguntarle
a Resolve "¿qué grado tiene ahora mismo este clip?".

Qué quería hacer y no puedo:

- Leer el balance que ya tenías y ajustarlo un poco en vez de escribir desde cero.
- Confirmar que un `SetCDL` se aplicó de verdad. Un `SetCDL` que devuelve `True`
  y no hace nada es indistinguible de uno que funciona.
- Enseñar en la GUI el grado actual del clip.

Qué hice en su lugar:

- La app **siempre escribe desde cero** en su propia versión. Nunca lee y modifica.
  Por eso lo de la versión aparte no es sólo prudencia: es que no hay alternativa.
- La verificación posterior a la escritura se hace con el LUT, que sí se puede
  releer (`GetLUT`), y se avisa si no coincide.
- El sitio donde `FakeResolve` guarda los CDL escritos se llama `_grados_escritos`
  y empieza por guion bajo **a propósito**: es para los tests. Si `FakeResolve`
  expusiera un `get_cdl()`, alguien escribiría esta noche código que mañana no
  funciona, y lo descubriríamos delante del cliente.

### 3.2 No se pueden crear nodos. Ninguno.

No hay `AddNode`, ni borrar, ni reordenar, ni cambiar el tipo de un nodo. Lo único
que la API sabe hacer con un grafo es contar nodos, leer etiquetas, activar y
desactivar, y poner un LUT o un CDL en uno que ya exista.

**Esto es lo más gordo de todo el encargo**, porque el diseño de tres nodos
(normalización / balance / look) da por hecho que los tres nodos están ahí.

Qué hice: `bridge.verificar_estructura_nodos()` cuenta los nodos antes de escribir
y, si hay menos de tres, **lanza** en vez de escribir. El mensaje dice claramente
que la API no sabe crear nodos y que hay que añadirlos a mano. Prefiero un error
honesto a un `SetCDL` en un nodo que no existe, que en la API real no falla con
estruendo: falla en silencio.

Las dos salidas que veo, para cuando lo hablemos:

- **Que el montador deje los tres nodos hechos.** Es un minuto de trabajo y no
  necesita código. Es lo que asume la app hoy.
- **`timeline.ApplyGradeFromDRX()` con un PowerGrade de tres nodos.** Funcionaría,
  pero **reemplaza el árbol de nodos entero**, así que sólo se puede hacer dentro
  de la versión `SIDEB COLOR` recién creada y nunca sobre la de nadie. No lo he
  implementado porque depende de F0-1 (si el `.drx` ni siquiera se puede exportar,
  montar el flujo entero alrededor de un `.drx` es construir sobre arena).

### 3.3 No se pueden etiquetar los nodos

`GetNodeLabel` existe. `SetNodeLabel` **no**. Así que la app no puede dejar el
nodo 2 llamado "SIDEB balance" para que lo reconozcas al abrir el proyecto. Por eso
`FakeResolve` deja las etiquetas vacías por defecto: es lo realista, y así ningún
código de la app acaba dependiendo de un nombre de nodo.

### 3.4 El balance tiene que caber en diez números

No hay lift/gamma/gain por parámetro, ni curvas, ni qualifiers, ni power windows,
ni OFX, ni Color Warper, ni Magic Mask, ni Color Match. Lo único que se puede
escribir por parámetro es el ASC CDL: slope, offset, power (tres cada uno) y
saturación. Diez números.

No es una limitación de la app: es el techo de la API. Todo lo que el agente C
calcule para el balance tiene que caber ahí o no se puede escribir.

### 3.5 No hay forma verificada de borrar una versión

`AddVersion` y `LoadVersionByName` están en la lista verificada.
`DeleteVersionByName` **no**. Consecuencias:

- La app **no promete** limpiar detrás de sí. Si creó `SIDEB COLOR`, se queda.
  Tampoco pasa nada: es una versión, ocupa nada y tu grado sigue en la tuya.
- Por eso `asegurar_version()` es idempotente: si `SIDEB COLOR` ya existe, la
  selecciona en vez de crear otra. Pasar la app dos veces por el mismo clip no
  deja `SIDEB COLOR 2`, `SIDEB COLOR 3`...
- El probe sí intenta borrar su versión de sonda, pero con `hasattr` y avisando
  de si el método existe o no. Eso también es información que nos hace falta.

### 3.6 No hay deshacer

No hay ninguna llamada de undo. El "deshacer" de esta app es: cargar otra vez tu
versión original. Eso funciona siempre y no depende de nada.

### 3.7 El look por grupo no es el nodo 3

Si el nodo 3 se pone en el grafo **post-clip de un grupo de color**, ahí el índice
es **1**, no 3: el grafo post-clip de un grupo empieza con un solo nodo. Es fácil
equivocarse porque la constante se llama `NODE_LOOK = 3`.

`FakeResolve` lo modela así (`nodos_post_clip_grupo=1`) y hay un test que
comprueba que pedir el nodo 3 de un post-clip revienta:
`test_el_look_de_un_grupo_es_el_nodo_1_del_post_clip_no_el_3`.

---

## 4. La séptima incógnita, la que no está numerada

**¿`AddVersion` hereda el árbol de nodos, o la versión nueva empieza en blanco?**

Si empieza en blanco, la versión `SIDEB COLOR` tiene un solo nodo y, como no se
pueden crear nodos (3.2), **la app no puede escribir nada**. Es tan importante como
cualquiera de las seis.

No la he metido en `Incognitas` porque **no cambia el código**: la comprobación de
"¿hay tres nodos?" se hace igual en los dos casos, y ya está puesta. Lo que cambia
es si la app sirve para algo.

Dónde está cubierta:

- `FakeResolve(version_hereda_grafo=...)` simula las dos. Por defecto hereda (el
  caso nominal); con `False` hay un test que comprueba que la app se para y avisa
  en vez de escribir a ciegas.
- El probe la mide: cuenta los nodos antes y después de `AddVersion` y la contesta
  en el informe como pregunta `EXTRA`.

---

## 5. Decisiones que tomé yo solo (y que puedes querer cambiar)

**Cuándo lanza y cuándo devuelve `False`.** Lanza `ResolveError` lo que es un error
de programa o una precondición rota: sin conexión, clip inexistente, índice de nodo
0, ruta de LUT absoluta, nombre de versión vacío, timeline cerrado. Devuelve `False`
lo que la API contesta que no sin que nadie haya hecho nada mal: versión duplicada,
cargar una versión que no está, copiar a una lista vacía de clips. Son respuestas,
no averías. Todas las excepciones heredan de `ResolveError`, que es lo único que la
GUI captura.

**Ser estricto con las rutas de LUT relativas.** Resolve se traga una ruta absoluta
y luego el nodo se queda sin LUT, sin decir nada. Es el peor fallo posible, así que
el puente corta antes: absolutas, `~`, `..` y extensiones no aceptadas lanzan.
Discutible, porque igual Resolve 21.1 sí acepta absolutas — pero si las acepta, lo
peor que pasa es que seamos más estrictos de la cuenta, y eso se relaja en una línea.

**El aviso de normalización mira la gestión de color del proyecto.** Un nodo 1 vacío
es perfectamente normal si el proyecto está en "DaVinci YRGB Color Managed", porque
entonces normaliza Resolve. Si el proyecto es "DaVinci YRGB" a secas y el nodo 1
está vacío, no normaliza nadie y el aviso salta. Sin esa distinción el aviso salía
siempre y se convertía en ruido que nadie lee.

**`FakeResolve.export_stills` escribe ficheros de texto, no imágenes.** Con la
extensión correcta, pero dentro pone una línea que dice de dónde salen. Si algún día
hacen falta píxeles de verdad, se generan con `tests/media/generate.py`, que es de
quien es.

**`FakeResolve` sólo escribe dentro del directorio que le pasan**, y se niega si no
existe o si el prefijo lleva separadores de ruta.

**El identificador de clip de `LiveResolve` es `v{pista}-{posición}`.** La API
verificada no da ningún id estable. Si alguien reordena el timeline con la app
abierta, los ids dejan de cuadrar: por eso hay que volver a llamar a `list_clips()`
después de cada edición. Si mañana el probe confirma que existe `GetUniqueId()`, se
cambia y es mejor.

---

## 6. Las seis incógnitas: dónde está cada una

Todas en `core/resolve/incognitas.py`, cada una marcada con `# TODO(F0-n)` en el
campo de la dataclass y otra vez en la función que la usa. Fuera de ese archivo no
hay más que dos marcas, las dos en `bridge.py` y `fake.py`, y hay un test que
comprueba que no se multiplican
(`test_la_decision_de_cada_incognita_esta_en_un_solo_sitio`).

Mañana: cambias los seis valores por defecto de `Incognitas` y no tocas nada más.

---

## 7. Lo que NO está probado, y hay que decirlo

- **`live.py` entero.** Ni una línea se ha ejecutado nunca. No hay ningún test que
  lo importe siquiera. Es un punto de partida, no código que funcione.
- **Todo lo que el probe hace con Resolve delante.** Lo que sí está probado del
  probe: que compila, que `--help` va, que sólo usa la biblioteca estándar, que no
  importa Resolve al cargarse, que el medidor de brillo de stills (con el que se
  responde F0-2) hace bien su trabajo, y que el camino de "no encuentro Resolve"
  suelta un mensaje decente en vez de un traceback.
- **Que la semántica de `FakeResolve` sea la de Resolve.** Es el riesgo de fondo de
  toda esta noche: he modelado lo que creo que hace Resolve. Donde no estoy seguro,
  lo he puesto como opción del constructor (`version_hereda_grafo`,
  `nodos_post_clip_grupo`) en vez de cerrarlo.
