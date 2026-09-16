# NOTAS — `core.colormgmt`

Módulo del día 5, tarea 1: gestión de color automática, "ordenar la casa" del modo
fácil. Dos piezas independientes, cada una en su archivo:

- `deteccion.py` — detector de cámara + tabla de decisión + agrupación de ambiguos.
- `verificacion.py` — verificador de doble conversión.

Las dos son **puras**: no importan nada de `core.resolve`, no tocan Resolve, no
lanzan. Trabajan sobre `ClipRef`, `NodeInfo` y `ProjectInfo` tal cual los expone
`ResolveBridge` (`FakeResolve` o `LiveResolve`), y eso es justo lo que las hace
fáciles de probar: `tests/test_colormgmt_integracion.py` monta un `FakeResolve` con
`clips=[...]` — ni siquiera hace falta tocar `core/resolve/fake.py`, porque
`FakeResolve.list_clips()` ya devuelve el `ClipRef` que le diste tal cual.

## Por qué la metadata vive en `ClipRef` y no en un tipo propio

Podría haber sido un `ClipCameraInfo` aparte, con su propia función para "rellenarlo"
desde Resolve. Se descartó: habría sido una capa más para algo que ya vive en el
mismo sitio que el resto de metadata del clip (`file_path`), y `ClipRef` ya es
`frozen`, así que añadir cinco campos opcionales no rompe nada existente — todos los
`ClipRef(...)` de los tests anteriores al día 5 siguen construyéndose igual, con los
cinco campos nuevos en `None`.

## La regla de oro del punto 3 del encargo

"Si no se puede determinar con seguridad, no se adivina." Por eso
`detectar_espacio_clip` **nunca** devuelve `segura=True` sin una pista textual
inequívoca (una curva reconocida, o "Rec.709" explícito). En particular: **la
ausencia total de metadata NO se interpreta como Rec.709**, aunque en la práctica sea
lo más probable (mucho material que ya viene convertido no trae ninguna nota de
cámara). Asumirlo sería exactamente el tipo de adivinanza que el encargo prohíbe, y
el coste de equivocarse — aplicar una curva log a un clip que ya está en Rec.709, o
viceversa — es alto y silencioso.

Cuando hay una pista parcial pero no concluyente (fabricante sin curva, o curva que
contradice el fabricante declarado), `DeteccionEspacio.space` SÍ lleva la mejor
conjetura — pero `segura=False`, y esa conjetura sólo se usa para redactar una
pregunta mejor en `agrupar_ambiguos` (`GrupoAmbiguo.sugerencia_espacio`). Nunca se
aplica sola.

## El acoplamiento frágil entre los dos módulos, y por qué se dejó así

`verificacion.py` decide si una `DeteccionEspacio` insegura es una "contradicción"
(curva no cuadra con el fabricante) mirando si el texto `"no cuadra"` aparece en su
`razon`. Es frágil — depende de una frase exacta escrita en `deteccion.py` — y se
dejó así a propósito en vez de añadir un campo `tipo_inseguridad` al contrato: los
dos casos de `segura=False` que hoy existen (contradicción, y "no hay pista en
absoluto") tienen tratamiento idéntico en todos los demás sitios (van a un grupo
ambiguo igual), así que la única razón para distinguirlos es este aviso del
verificador. Si aparece un tercer caso que también necesite distinguirse, el campo
extra en `contracts.py` deja de ser prematuro y hay que añadirlo — hasta entonces,
`tests/test_colormgmt_verificacion.py::test_curva_no_cuadra_se_traslada_como_aviso`
es la única red de seguridad de este acoplamiento, y los dos módulos se prueban
siempre juntos.

## Lo que falta, deliberadamente

- **Aplicar la decisión en Resolve** (`SetClipProperty(clip, "Input Color Space",
  espacio)`) no está aquí: depende de que F0-7 del probe diga que sí. Mientras tanto
  `core.colormgmt` sólo decide y avisa; quien escribe en Resolve es un capítulo
  aparte, condicionado a `Incognitas.clip_input_color_space_editable` — campo que
  **aún no existe** en `core/resolve/incognitas.py` y hay que añadir cuando llegue
  la respuesta del probe (junto con el resto de F0-7/F0-8).
- **Ningún nombre de clave de `GetClipProperty` está confirmado.** Los cinco campos
  de `ClipRef` son la mejor lectura de foros y documentación de terceros, no de
  Blackmagic. El probe ampliado (F0-7) pide explícitamente "listar todas las claves
  que devuelve `GetClipProperty()` sin argumentos" — cuando Mario lo ejecute, hay que
  volver aquí y corregir los nombres si hace falta.
- **La heurística de "LUT que parece conversión de entrada"**
  (`verificacion._TOKENS_LUT_CONVERSION`) es de nombre de archivo, no de contenido:
  un LUT de conversión con un nombre raro no se detecta, y un look cuyo nombre
  contenga "input" por casualidad se marcaría mal. Es lo mejor que se puede hacer sin
  poder abrir el `.cube` y comprobar si es realmente una transformación de espacio de
  color (que sería otro proyecto entero).
