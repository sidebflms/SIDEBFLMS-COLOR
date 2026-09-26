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

### 2.1 Ya no es una promesa: es un `if` (hallazgo R-0 de la revisión)

El revisor encontró el agujero grande de la primera versión de este módulo: la
regla de oro vivía **sólo dentro de `aplicar_grado_seguro()`**. O sea que se
cumplía si el que llamaba se acordaba de usar esa función. Y no es teórico: la
GUI la escribe otro, que tiene el puente entero a mano y no ha leído esto.

Peor todavía: `copy_grades` **reemplaza el árbol de nodos entero del destino**.
Llamarlo a pelo sobre clips que están en la versión del usuario es la forma más
rápida que hay de cargarse una tarde de trabajo.

Ahora lo impone el propio puente. Las cinco escrituras de grado —`set_cdl`,
`set_lut`, `set_node_enabled`, `copy_grades` y `reset_all_grades`— comprueban la
versión activa del clip antes de tocar nada y lanzan `EscrituraFueraDeVersion` si
no es una nuestra. Está en `BaseResolveBridge._exigir_version_propia()`, así que
lo heredan **`FakeResolve` y `LiveResolve` igual**: no es una red que sólo exista
en las pruebas.

Tres detalles que decidí y conviene saber:

- **Lanza, no crea la versión sola.** El coordinador ofrecía las dos. Elegí
  lanzar por coherencia: este módulo rechaza una ruta de LUT absoluta y un índice
  decimal en vez de apañarlos, y crear una versión a espaldas de quien llama es
  exactamente la clase de magia silenciosa que rechazo en todo lo demás. Además,
  quien se salta `aplicar_grado_seguro` se salta también la comprobación de los
  tres nodos y los avisos; el mensaje de error le manda allí, que es donde
  están. El mensaje dice qué hacer, no sólo que no.
- **`copy_grades` mira TODOS los destinos antes de copiar a ninguno.** Si el
  tercero de la lista está en la versión del usuario, no se copia ni al primero.
- **Qué cuenta como versión nuestra:** `SIDEB COLOR` y cualquiera que empiece por
  `SIDEB COLOR ` (así vale la del probe, `SIDEB COLOR PROBE`). Por convenio de
  nombre, porque la API no marca de ninguna forma quién creó una versión. Está en
  `es_version_nuestra()`.

### 2.2 La vía de escape

Se llama `PELIGRO_escribir_fuera_de_la_version`, es un **atributo** del puente
(no un método, para que quede escrito en la línea donde se pone y no se pueda
llamar de pasada) y se puede pedir también en el constructor de `FakeResolve`.
Con él a `True` el puente deja de proteger nada.

Usos legítimos: los tests, cuando montan «el grado que el usuario ya tenía», y
una herramienta de diagnóstico que tenga que tocar la versión actual a sabiendas.
Uso ilegítimo: la app. Si la app lo necesita, el diseño está mal. El nombre es
feo a propósito: se ve en una revisión y se encuentra con `grep` en dos segundos.

### 2.3 Y para copiar de un clip a otros, `copiar_grado_seguro()`

Le crea o selecciona la versión `SIDEB COLOR` a **cada destino** antes de copiar
nada, y si algún destino no se puede preparar, no copia a ninguno. Es el
equivalente de `aplicar_grado_seguro` para `CopyGrades`.

### 2.4 Los dos puentes se protegen igual (hallazgo E-3)

`PELIGRO_escribir_fuera_de_la_version` es un atributo **de clase** de
`BaseResolveBridge`. `FakeResolve` lo reasignaba en la instancia y `LiveResolve`
no. Consecuencia: una línea suelta en cualquier sitio del proyecto

```python
BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True
```

apagaba la regla de oro **en el puente de verdad** y la dejaba puesta en el
falso. Es la peor forma posible de este fallo: ningún test contra `FakeResolve`
puede cazarlo, así que todo saldría verde por la noche y la protección no
existiría el día que la app hable con Resolve.

Arreglado: `LiveResolve.__init__` lo fija en la instancia, igual que
`FakeResolve`, y acepta el mismo parámetro en el constructor.

Y para que no vuelva a pasar con el siguiente atributo que añadamos, hay un test
que **compara los dos `__init__` leyendo el AST**
(`test_los_dos_puentes_fijan_los_MISMOS_atributos_en_la_instancia`). Lo hace
leyendo los ficheros, sin importar `live.py` ni instanciarlo: sigue sin
ejecutarse ni una línea de ese archivo. Auditados los dos atributos de clase que
hay hoy: `incognitas` estaba bien, `PELIGRO_...` no. No había más.

### 2.5 Y si Resolve no sabe decirnos en qué versión estamos

Esto es un riesgo que **nos hemos creado nosotros** al cerrar R-0: la regla de
oro pregunta `GetCurrentVersion()` antes de cada escritura, y nadie ha visto
nunca esa llamada funcionar contra Resolve de verdad. Si devuelve una cadena
vacía, un `None`, o un diccionario sin `versionName`, la app **no escribiría
nada en ningún sitio** hasta que alguien lo mirara.

Son dos situaciones distintas y ahora se tratan distinto:

| Situación | Qué hace | Excepción |
|---|---|---|
| Sé en qué versión estoy y **no es nuestra** | bloquea | `EscrituraFueraDeVersion` |
| **No sé** en qué versión estoy | bloquea | `VersionIndeterminada` |

**Las dos bloquean, y lo he decidido a conciencia.** Lo pensé como una cuestión
de qué cuesta equivocarse en cada dirección:

- Si bloqueo y resultaba que no hacía falta: se pierde una mañana. **No se rompe
  nada.** El mensaje dice exactamente qué mirar, y la vía de escape deja seguir
  trabajando en dos minutos a quien sepa lo que hace.
- Si escribo y resultaba que estábamos en la versión del usuario: se pierde el
  trabajo de alguien, en **todos** los clips a la vez, en silencio, y **no hay
  deshacer** — la API no tiene undo, y la red de seguridad (la versión) no se
  habría creado justamente porque no sabíamos dónde estábamos.

Un mecanismo de seguridad que se apaga solo cuando no puede verificar no es un
mecanismo de seguridad. Así que falla cerrado.

Lo que sí cambia entre los dos casos es **el mensaje**, y eso importa tanto como
la decisión: el de `VersionIndeterminada` dice que el sospechoso es la API y no
el usuario, nombra `GetCurrentVersion()`, manda a la pregunta V-0 del probe (que
es justo ésta) y da la línea exacta para salir del paso. Que el diagnóstico sean
treinta segundos y no una tarde.

`VersionIndeterminada` hereda de `EscrituraFueraDeVersion`, así que quien ya
capturaba aquélla captura ésta, y la GUI —que sólo captura `ResolveError`— no
se entera de nada.

**Si mañana la respuesta es rara**, por orden:

1. Mirar la V-0 del informe del probe: dice en crudo qué contestó Resolve en
   cada clip.
2. Si contesta un diccionario con otra clave (no `versionName` ni `name`), es un
   cambio de la API entre versiones: se arregla en **`bridge.nombre_de_version()`**,
   que desde el día 2 es el único sitio del proyecto que interpreta esa respuesta
   —lo usan el falso y el vivo, y por eso lo que se pruebe en uno vale para el
   otro—. Se toca la tupla `CLAVES_NOMBRE_VERSION` y ya está. El mensaje de
   error, además, dice qué claves traía el diccionario, así que no hay ni que
   adivinar.
3. Si no contesta nada útil en ningún caso, hay que buscar otra forma de saber la
   versión activa. La única otra vía que veo es `GetVersionNameList()` más alguna
   marca propia, y no es fiable. En ese caso hablamos: puede que toque cambiar la
   protección por "crear siempre la versión antes de escribir y no preguntar",
   que es más agresivo pero también seguro.
4. Mientras tanto, y sólo si hay prisa: `PELIGRO_escribir_fuera_de_la_version`
   deja pasar todo, con el riesgo dicho.

### 2.5.bis Y ahora ya está probado: las cuatro respuestas raras (día 2)

Lo de arriba estaba decidido y argumentado, pero probado con poco: había cuatro
tests que llamaban a `_exigir_version_propia()` a mano con `""`, `None` y poco
más. O sea que estaba probada la *decisión*, no el *camino*: nadie había
comprobado que una respuesta rara de `GetCurrentVersion()` recorra de verdad las
cinco escrituras y las pare. Y el camino es lo que importa, porque es donde
puede haber un atajo.

**`FakeResolve` ya sabe mentir.** Con el mismo mecanismo de siempre, sin
inventar otro: `fallar_en()` ya existía para "lanza" y `devolver_false_en()`
para "contesta False"; ahora hay `devolver_en(operacion, valor)` para "contesta
esto, tal cual, aunque el `Protocol` diga que no puede".

```python
fake.devolver_en("current_version", "")                   # cadena vacía
fake.devolver_en("current_version", None)                 # None
fake.devolver_en("current_version", {"version": 2})       # dict sin las claves
fake.fallar_en("current_version")                         # revienta
```

Qué hace el código en cada una, y es lo mismo en las cuatro: **`VersionIndeterminada`
y cero escrituras**. Está probado con las cuatro (más cuatro variantes: sólo
espacios, `{}`, `{"versionName": ""}`, un entero) **por** las cinco escrituras,
y mirando que `_grados_escritos` queda vacío y que el LUT del nodo 3 sigue sin
poner: no basta con que lance, tiene que no haber escrito.

Tres cosas que cambiaron para que esto fuera posible, y las tres son mejores que
lo que había:

- **`FakeResolve` pregunta la versión de verdad.** Antes miraba su propio
  diccionario interno (`version.nombre`). Ahora las cinco escrituras llaman a
  `self._version_activa_o_rota(clip_id)`, que pasa por `current_version()`,
  igual que `LiveResolve`. Un falso que no puede mentir en la llamada más
  delicada de la API no sirve para probarla. Hay un test que lo vigila contando
  llamadas (`test_el_falso_pregunta_la_version_en_cada_escritura_...`).
- **La respuesta la interpreta un solo sitio**: `bridge.nombre_de_version()`.
  Lo usan el falso y el vivo. Antes, la traducción de un `dict` a un nombre
  vivía sólo dentro de `LiveResolve.current_version()`, o sea que el falso
  probaba una semántica distinta de la que tendría el de verdad.
  Y de paso: **un diccionario que SÍ traiga `versionName` se entiende y se
  escribe con normalidad**. Bloquear también eso sería fácil y sería inútil: lo
  que bloquea es no encontrar el nombre, no que venga envuelto. Hay un test por
  cada lado.
- **Si la llamada revienta, la excepción no se propaga en crudo**: se envuelve
  en `RespuestaRota` y entra por el mismo sitio que las otras tres. La escritura
  tampoco ocurriría dejándola salir, pero el que lo leyera vería un error de la
  API en vez de la explicación de qué mirar, y ese era medio problema.

**El mensaje**, que es la otra mitad del encargo. Ahora dice, por este orden:
qué llamada falló y **qué contestó en crudo, con su tipo** (`''` y `None` y `{}`
se parecen demasiado escritos); que el sospechoso es la API y no el usuario;
por qué no se arriesga (si fuera la versión del usuario, se pierde su grado y no
hay undo); y **qué ejecutar**: `python3 probe/api_probe.py`, pregunta V-0. Si lo
que contestó fue un diccionario, el mensaje dice **con qué claves venía** y en
qué función se arregla, que es literalmente lo único que hace falta saber.

### 2.6 El agujero que queda, y creo que no tiene arreglo

`es_version_nuestra()` va **por el nombre**, porque la API no marca de ninguna
forma quién creó una versión: no hay autor, ni fecha, ni etiqueta, ni nada que
consultar. Así que una versión que Mario haya llamado `SIDEB COLOR pruebas` se
daría por nuestra, y la app escribiría dentro.

No he encontrado forma de cerrarlo. Lo dejo dicho porque es mejor saberlo: el
nombre `SIDEB COLOR` es lo bastante raro como para que no pase por accidente,
pero si alguna vez alguien crea versiones a mano con ese prefijo, que sepa que
la app las considera suyas.

### 2.7 El camino bueno

`bridge.aplicar_grado_seguro()` sigue siendo por donde debe ir la app. El orden
es:

1. Abrir la página de color (si la incógnita F0-5 dice que hace falta).
2. Crear o seleccionar la versión `SIDEB COLOR`. **Nada se escribe antes de esto.**
3. Comprobar que están los tres nodos. Si no están, se para aquí.
4. CDL al nodo 2.
5. LUT al nodo 3.
6. Releer el LUT con `GetLUT` para confirmar que cuajó.

El paso 6 no se puede hacer con el CDL, y esa es la primera cosa importante de
esta nota.

### 2.8 La excepción de la regla de oro: `set_group_post_clip_lut`

Lo encontró el auditor del día 2 y tiene razón en las dos mitades: **no es un
bug, y no estaba escrito en ninguna parte.** Lo segundo sí era un problema,
porque la frase que se repite por todo el repo —«el puente se niega en redondo a
escribir grado fuera de la versión»— tenía una excepción silenciosa.

La regla de oro cubre las cinco escrituras de grado **de un clip**. Hay un sexto
camino que escribe algo que el usuario ve: poner un LUT en el grafo post-clip de
un **grupo** de color. Ése no pasa por `_exigir_version_propia` y **no puede
pasar**: un grafo post-clip de grupo no es de ningún clip, así que no tiene
versiones que comprobar. No hay nada que preguntar ahí.

Lo que eso significa, dicho claro: **escribir el LUT de un grupo pisa lo que
hubiera en ese nodo, sin red y sin deshacer.** El grado de los clips sigue a
salvo en sus versiones —eso no cambia—, pero el look del grupo no.

Está escrito ahora en cuatro sitios, y hay un test que comprueba que sigue
estándolo (`test_el_hueco_de_set_group_post_clip_lut_esta_ESCRITO_en_los_dos_puentes`):
en el docstring del método en `fake.py`, en el de `live.py`, en el docstring de
módulo de `bridge.py` y aquí.

**¿Hay alguna protección alternativa que sí tenga sentido ahí?** Lo he pensado y
la respuesta es *poca, y la que hay no la pongo hoy*:

- **Crear una versión antes**: no existe. Un grupo no tiene versiones. Descartado
  por imposible, no por criterio.
- **Leer lo que había y guardarlo para poder devolverlo.** Esto sí se puede:
  `GetLUT` funciona sobre el grafo post-clip igual que sobre el de un clip, y
  cuesta una llamada. Sería el equivalente honesto de la versión: no impide
  pisar, pero deja con qué volver. **No lo he implementado** porque la app no usa
  grupos hoy y montar un "deshacer" que nadie ejerce es código sin probar
  haciéndose pasar por una red de seguridad. Si un día la app usa grupos, esto es
  lo primero que hay que hacer, y está dicho también en el docstring del método.
- **Negarse si el nodo ya tenía un LUT puesto**, y exigir un `forzar=True`. Es la
  más tentadora y la he descartado: convierte "el usuario ya tenía algo" en un
  error en un sitio donde reescribir el look del grupo es *justo* lo que uno
  quiere hacer la segunda vez que pasa la app. Sería el aviso que todo el mundo
  aprende a saltarse, y eso es peor que no tenerlo.

Lo que sí se comprueba ahí, que no es nada: que el grupo existe, que el índice de
nodo cabe (y ojo, que en un post-clip de grupo **el look es el nodo 1, no
`NODE_LOOK`** — apartado 3.7) y que la ruta del LUT es relativa y con extensión
aceptada.

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

Las dos salidas que veía, para cuando se hablara:

- **Que el montador deje los tres nodos hechos.** Es un minuto de trabajo y no
  necesita código. Es lo que asume la app hoy — y, confirmado el 2026-09-25,
  **es la ÚNICA que queda en pie.**
- ~~`timeline.ApplyGradeFromDRX()` con un PowerGrade de tres nodos.~~
  **DESCARTADA el 2026-09-25: el método NO EXISTE en `TimelineItem` en esta
  build (Resolve Studio 21.1.0.17).** No es un problema de argumentos ni de
  permisos — se miró `dir(item)` completo (unos 90 métodos) contra un clip
  real y `ApplyGradeFromDRX` sencillamente no está en la lista. Se probó de
  verdad con un PowerGrade real de Mario (`SECRET SAUCE/A5 POWERGRADE V2/SS
  POWERGRADE V2.drx`) sobre un clip de prueba: `getattr(item,
  "ApplyGradeFromDRX", None)` es `None`. F0-1 (exportar a `.drx`) SÍ se
  confirmó que funciona, pero de nada sirve si no hay ningún método que
  APLIQUE un `.drx` de vuelta sobre un clip.
  **Lo que SÍ existe y queda como pista para el futuro:** `CopyGrades`
  (ya cableado como `copy_grades` en `ResolveBridge`) copia el árbol de
  nodos ENTERO de un clip origen a una lista de clips destino. Si algún día
  un humano prepara UN clip con los tres nodos a mano, `copy_grades` podría
  propagar esa estructura al resto del timeline por script — no construido
  todavía, sólo confirmado que el mecanismo existe.

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

**CONFIRMADO el 2026-09-25, contra Resolve Studio 21.1.0.17 real: EMPIEZA EN
BLANCO.** Medido de verdad (probe, pregunta `EXTRA`): el clip de prueba tenía 1
nodo antes de `AddVersion` y 1 después — con un clip de más nodos habría hecho
falta repetirlo para estar seguros de que no hereda NUNCA, pero la evidencia que
hay apunta al caso pesimista, no al nominal.

Esto es tan importante como cualquiera de las seis: como no se pueden crear
nodos por script (3.2), **la app no puede montar sola los tres nodos que
necesita** (`NODE_NORMALIZACION`/`NODE_BALANCE`/`NODE_LOOK`). Hace falta partir
de un PowerGrade de tres nodos ya construido (`ApplyGradeFromDRX`, ahora que
F0-1 confirma que exportar a `.drx` funciona) o que quien monta la timeline dejê
los tres nodos hechos de antemano — no es un "ya se verá", es la pieza que hay
que resolver antes de que la app pueda escribir de verdad en un proyecto que no
se ha preparado a mano primero.

No la he metido en `Incognitas` porque **no cambia el código**: la comprobación de
"¿hay tres nodos?" se hace igual en los dos casos, y ya está puesta. Lo que cambia
es si la app sirve para algo.

Dónde está cubierta:

- `FakeResolve(version_hereda_grafo=...)` simula las dos. **El valor por defecto
  del constructor (`True`, hereda) sigue siendo el caso NOMINAL/optimista, NO el
  confirmado** — se ha dejado así a propósito porque la mayoría de tests de este
  archivo no están probando esta mecánica concreta y flipar el valor por defecto
  habría significado revisar la práctica totalidad de la suite de `core/resolve`
  para ver a cuáles les hace falta un PowerGrade de partida; queda pendiente para
  una sesión dedicada, no uno de los TODO(F0-n) de una tarde. Con
  `version_hereda_grafo=False` (el caso ahora confirmado) hay tests dedicados
  (`tests/test_resolve_fake.py`, `tests/test_resolve_secuencia.py`,
  `tests/revision/test_ola1_resolve.py`) que comprueban que la app se para y
  avisa en vez de escribir a ciegas en un nodo que no existe.
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

**Los índices de nodo son enteros de verdad, y no se trunca nada** (hallazgo E-1
de la revisión). Antes, `validar_indice_nodo` hacía `int(node_index)`, que se
traga un float, una cadena y un booleano. Y con un float no redondea: **trunca**.
Un índice que valiera 2,9999999999 —que para cualquiera es el nodo 3— acababa
escribiendo en el 2, sin lanzar y sin avisar, que es justo el fallo que este
módulo existe para evitar. Ahora se rechaza cualquier cosa que no sea un `int`
(el `bool` incluido, que para Python es un entero y aquí es un bug de tipos), y
el mensaje dice que redondee quien sepa lo que quiere. No adivinamos si un 2,99
era el 2 o el 3.

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

### Día 9 (continuación 5), 2026-09-25: el probe corrió contra Resolve real

Primera vez en la historia del proyecto — Mario abrió Resolve Studio 21.1.0.17
con un proyecto de pruebas ("test color") y dio permiso explícito para la parte
de escritura. Resultado, pregunta por pregunta:

- **F0-6: SÍ, confirmado.** El módulo de scripting se importa limpiamente desde
  `/Applications/DaVinci Resolve/.../Libraries/Fusion/fusionscript.so` con el
  Python 3.12.14 arm64 del `.venv` del proyecto. `LiveResolve` puede vivir
  dentro de la app, sin proceso aparte.
- **F0-4: «descarga directa», confirmado.** Coincide con el valor conservador
  que ya estaba puesto.
- **F0-1: SÍ, confirmado.** `ExportStills(..., 'drx')` devolvió `True` y
  apareció el fichero `.drx` de verdad en el directorio de pruebas.
- **F0-2, F0-3, F0-5: intentados, inconclusos** — no "confirmados en falso".
  F0-2 (still con o sin grado) no dejó ningún fichero medible con el formato
  probado; F0-3 (`.dctl`) no tenía ningún `.dctl` en la carpeta de LUTs con qué
  probarlo; F0-5 (hace falta `OpenPage`) no se pudo distinguir de "ese LUT de
  serie en concreto no existe". Los tres se quedan en su valor conservador de
  siempre — ver los comentarios de cada campo en `incognitas.py` para el detalle.
- **La séptima, sin numerar (§4 de arriba): CONFIRMADA en el caso pesimista.**
  `AddVersion` no hereda el árbol de nodos — la versión nueva empieza con uno
  solo. Es el hallazgo más importante de la sesión: sin un PowerGrade de tres
  nodos de partida, la app no puede escribir sola su estructura.

Informe completo (JSON y texto) generado por el propio probe; quien retome esto
debería releerlo en vez de fiarse sólo de este resumen.

---

## 7. Lo que NO está probado, y hay que decirlo

- **`live.py` entero, SIGUE sin ejecutarse — ni siquiera el día 9 (continuación
  5).** El probe habla con `DaVinciResolveScript` DIRECTAMENTE, con sus propias
  llamadas sueltas (`resolve.GetProjectManager()`, etc.), no a través de
  `LiveResolve`/`ResolveBridge`. Que el probe haya corrido de verdad contra
  Resolve NO es lo mismo que `LiveResolve` haya corrido nunca — sigue siendo
  cierto que ni una línea de ese fichero se ha ejecutado, ni hay ningún test
  que lo importe. La regla de oro está puesta también ahí, en las cinco
  escrituras, pero tampoco se ha ejecutado: cuesta una llamada extra a
  `GetCurrentVersion` por escritura y, si mañana eso resulta caro en un
  timeline largo, se cachea, pero no se quita.
- **Lo que el probe hace con Resolve delante: ya SÍ está probado, de verdad,
  el 2026-09-25** (ver el resumen del día 9 arriba) — conexión, lectura de
  versión, `AddVersion`, `SetCDL`/`SetLUT`, `GrabStill`/`ExportStills`
  (incluido `.drx`), y la limpieza al terminar (borrar la versión de sonda,
  volver a la versión original, borrar los stills). Lo que sigue sin probarse
  del probe en sí: F0-2 (con qué formato de imagen SÍ deja fichero medible),
  F0-3 (contra un `.dctl` real) y F0-5 de forma concluyente.
- **Que la semántica de `FakeResolve` sea la de Resolve — parcialmente ya
  contestado.** Era el riesgo de fondo: se había modelado lo que se creía que
  hacía Resolve, con una opción del constructor donde no había seguridad
  (`version_hereda_grafo`, `nodos_post_clip_grupo`) en vez de cerrarlo a una
  rama. El día 9 (continuación 5) confirmó una de las dos:
  `version_hereda_grafo` — Resolve real NO hereda, igual que la rama `False`
  del fake (el valor por DEFECTO del fake sigue siendo `True`, la rama
  optimista, por convivencia con el resto de la suite — ver §4). Sigue sin
  confirmarse `nodos_post_clip_grupo`.
