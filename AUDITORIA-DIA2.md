# AUDITORÍA DÍA 2 — los cuatro casos que se decidieron sin contraste

Auditor independiente. No escribí nada de este código. Intérprete: `.venv/bin/python`
del repo. No se ha tocado `core/`, `gui/`, `probe/` ni git. No se ha abierto Resolve ni
se ha importado su módulo de scripting. Todo lo que se ejecuta vive en memoria o en
`tmp_path`.

**Veredictos, de un vistazo**

| Caso | Qué se arbitró | Veredicto |
|---|---|---|
| 1 | `== 1` → `== 2` en las asignaciones de la vía de escape | **Confirmado** (con el test reforzado) |
| 2 | `==` → `>=` contando `_exigir_version_propia` en el fuente | **Confirmado el código, revertido el test** |
| 3 | El hallazgo E-3 (envenenar la clase base) pasa a afirmar el arreglo | **Confirmado** |
| 4 | El `xfail` de la viñeta sola | **Confirmado el `xfail`, revertida su razón** |

**Sobre la contaminación (lo pregunta el encargo y contesto primero).** Hice el paso 2
—mi juicio— antes de leer el commit `4825901` y antes de leer los comentarios nuevos
de `tests/revision/test_ola1_resolve.py`, que no abrí hasta tener escritos y en verde
mis propios tests. **Pero me contaminé parcialmente en el caso 3, y de forma
inevitable**: el paso 1 manda leer el código actual, y `core/resolve/live.py` lleva en
el `__init__` un comentario de doce líneas que explica el hallazgo E-3 y por qué se
arregló así. O sea que supe la tesis del orquestador sobre el caso 3 antes de formar
la mía. Lo digo porque es verdad; lo compenso comprobando el caso 3 por
comportamiento y no por lectura, y ampliándolo a la pregunta que el comentario **no**
contesta (si hay más atributos con la misma asimetría).

---

## Caso 1 · `test_la_via_de_escape_existe_hay_que_nombrarla_y_no_se_activa_de_pasada`

### Qué afirmaba el test original

```python
# Y nadie dentro de `core/` la usa.
usos = [...]  # líneas de core/*.py que empiezan por "self.PELIGRO" y llevan "="
assert len(usos) == 1, f"la via de escape se asigna en mas de un sitio de core/: {usos}"
```

El comentario y la aserción no dicen lo mismo, y ahí está todo el caso. El comentario
afirma una **propiedad**: dentro de `core/` nadie enciende la vía de escape. La
aserción cuenta **sitios**: exactamente una línea de `core/` asigna el atributo en la
instancia. En el momento en que G lo escribió, ese único sitio era
`FakeResolve.__init__`.

### ¿Era cierto sobre el código de hoy? No, y no podía serlo

Hoy hay dos asignaciones, porque el arreglo de E-3 añadió la de `LiveResolve.__init__`:

```
core/resolve/fake.py:233:        self.PELIGRO_escribir_fuera_de_la_version = PELIGRO_escribir_fuera_de_la_version
core/resolve/live.py:122:        self.PELIGRO_escribir_fuera_de_la_version = PELIGRO_escribir_fuera_de_la_version
```

Y aquí está lo que me hizo decidir: **ese «1» del test original era exactamente la
forma que tenía el bug**. Que sólo hubiera un sitio significaba que sólo una de las dos
implementaciones se blindaba, que es literalmente el hallazgo E-3 que el propio
revisor documentó tres tests más abajo. Dejar el `== 1` no habría protegido nada:
habría **exigido** que el bug siguiera ahí.

### Mi juicio, formado antes de leer ninguna justificación

Dos cosas, y son independientes:

1. **Subir a 2 es correcto.** No hay lectura razonable en la que `== 1` siga siendo lo
   que se quiere afirmar después del arreglo.
2. **Ninguna de las dos versiones afirma lo que dice el comentario.** Ni `== 1` ni
   `== 2` miran el **valor** que se asigna. Un
   `self.PELIGRO_escribir_fuera_de_la_version = True` a pelo en cualquier sitio de
   `core/` pasaría los dos tests mientras el recuento cuadrara. La propiedad que
   protege al usuario —*ninguna línea de `core/` enciende la vía de escape*— no está
   comprobada por nadie, ni antes ni después del arbitraje.

### ¿Coincido con el orquestador?

Sí, y su razón escrita (`«antes este test exigia exactamente 1 sitio, y ese 1 era justo
el bug — solo el falso se blindaba»`) es la misma que se me ocurrió a mí, dicha mejor.
No es una racionalización: es el diagnóstico correcto.

Lo que **no** dice su comentario es que el test sigue midiendo el número de sitios y no
la propiedad. Lo añado yo en `tests/auditoria/test_dia2_regla_de_oro.py`, recorriendo
el AST de todo `core/` y comprobando que cada asignación o pone `False` literal o
reenvía un parámetro homónimo cuyo valor por defecto es `False`. Ese test no se rompe
porque aparezca un tercer puente y no pasa porque alguien encienda la vía de escape.

### Veredicto: **confirmado**

El arbitraje es correcto. Recomendación (no es un fallo, es una mejora): sustituir el
recuento por la comprobación de valor, que es inmune tanto al `1` como al `2`.

### Evidencia ejecutada

```
$ .venv/bin/python -m pytest tests/auditoria/test_dia2_regla_de_oro.py -q -s
[AUD1] core/resolve/bridge.py:256 -> False literal OK
[AUD1] core/resolve/fake.py:233 -> parametro homonimo (defecto False: True) OK
[AUD1] core/resolve/live.py:122 -> parametro homonimo (defecto False: True) OK
```

(«defecto False: True» se lee «¿su valor por defecto es `False`? sí».)

```
$ grep -rn "PELIGRO_escribir_fuera_de_la_version" core/ | grep "self\."
core/resolve/live.py:122:        self.PELIGRO_escribir_fuera_de_la_version = PELIGRO_escribir_fuera_de_la_version
core/resolve/fake.py:233:        self.PELIGRO_escribir_fuera_de_la_version = PELIGRO_escribir_fuera_de_la_version
```

---

## Caso 2 · `test_la_regla_de_oro_vive_en_la_clase_base_asi_que_LiveResolve_la_hereda`

### Qué afirmaba el test original

```python
assert fuente_live.count("_exigir_version_propia") == len(ESCRITURAS_DE_GRADO)  # == 5
assert fuente_fake.count("_exigir_version_propia") == len(ESCRITURAS_DE_GRADO)
```

Es decir: el nombre de la regla aparece en el **texto** del fichero exactamente cinco
veces, una por escritura de grado.

### ¿Era cierto sobre el código de hoy? No, y por un motivo que no es un fallo

`live.py` menciona el nombre **seis** veces: las cinco llamadas y una más en el
docstring de `current_version()`, donde se explica qué pasa si `GetCurrentVersion()`
se porta raro. `fake.py` lo menciona cinco. O sea que el `==` se puso rojo por
**documentación añadida**, no por una protección que faltara.

### Mi juicio, formado antes de leer ninguna justificación

Contar apariciones de un nombre en el texto fuente **no es una forma sólida** de
afirmar que las cinco escrituras están protegidas, y no lo es en ninguna de las dos
direcciones:

- con `==`, escribir una línea de prosa que mencione la regla pone el test en rojo sin
  que nada esté roto (es justo lo que pasó);
- con `>=`, el test pasa aunque de las cinco menciones **ninguna** sea una llamada. Un
  `live.py` con cinco párrafos de comentario hablando de `_exigir_version_propia` y
  cero llamadas lo pasa en verde. Y ése es el escenario que este test existe para
  impedir: que la regla de oro sea una red que sólo exista en el puente falso.

O sea que el `>=` no es una aserción más floja: en la práctica no es una aserción. El
comentario que lo acompaña dice «lo que se quiere afirmar es que NO FALTA ninguna
escritura sin comprobar», y ésa es exactamente la única cosa que un `>=` sobre un
recuento de texto **no** afirma.

**Sí hay una forma mejor, y es el sitio donde más valor puedo aportar.** Dos, de hecho,
y las escribí las dos:

1. **Por AST.** Para cada una de las cinco escrituras, en las dos clases, se busca en el
   cuerpo del método una `ast.Call` a `self._exigir_version_propia(...)`. Inmune al `==`
   (los comentarios no son llamadas) y al `>=` (los docstrings tampoco).
2. **Por comportamiento, y también en `LiveResolve`.** Es lo que de verdad faltaba. Se
   instancia `LiveResolve` con un **doble de la API** (objetos que fingen ser
   `TimelineItem` y grafo de nodos y que anotan cada llamada que reciben) y se
   comprueba que las cinco escrituras lanzan `EscrituraFueraDeVersion` **y que el
   registro de llamadas a la API queda vacío** — o sea que la regla salta *antes* de
   tocar nada, no después. Esto no roza Resolve: `LiveResolve.__init__` sólo guarda el
   objeto que se le pasa, y el módulo de scripting sólo se importa dentro de
   `conectar()`, que aquí no se llama.

   Con el doble se comprueba además el camino bueno (dentro de `SIDEB COLOR` sí
   escribe), la rama `VersionIndeterminada` (`""`, `None`, `"   "`, `0`) y que
   `copy_grades` mira **todos** los destinos antes de copiar a ninguno.

### ¿Coincido con el orquestador?

**A medias, y la mitad en la que no coincido importa.**

Coincido en el diagnóstico: tiene razón en que el `==` se rompió por su propio
comentario y no por una protección ausente, y por tanto **hace bien en no «arreglar» el
código**. El código está bien: las cinco escrituras llaman a la regla en las dos
implementaciones, y lo he comprobado ejecutando `LiveResolve`, que es más de lo que
hacía ningún test del repo.

No coincido en el remedio. Cambiar `==` por `>=` convierte un test frágil en un test
vacío, y lo deja con el mismo nombre y la misma apariencia de red de seguridad. Es el
tipo de arreglo que se toma por bueno precisamente porque nadie lo contrasta: pasa a
verde, el número sigue saliendo, y nadie vuelve a mirarlo.

### Veredicto: **confirmado el código, revertido el test**

- El veredicto del orquestador sobre el **código** (está bien, el test estaba mal
  planteado): **confirmado**.
- Su **reescritura del test**: **revertida**. No hay que volver al `==` —eso sería
  volver a la fragilidad—, hay que sustituir las dos líneas por la comprobación de
  AST + comportamiento, que ya está escrita en
  `tests/auditoria/test_dia2_regla_de_oro.py`. No es urgente (no hay ningún fallo
  detrás), pero mientras no se haga el repo tiene un test menos de los que cree tener.

### Evidencia ejecutada

```
[AUD2-AST] FakeResolve.copy_grades: llama
[AUD2-AST] FakeResolve.reset_all_grades: llama
[AUD2-AST] FakeResolve.set_cdl: llama
[AUD2-AST] FakeResolve.set_lut: llama
[AUD2-AST] FakeResolve.set_node_enabled: llama
[AUD2-AST] LiveResolve.copy_grades: llama
[AUD2-AST] LiveResolve.reset_all_grades: llama
[AUD2-AST] LiveResolve.set_cdl: llama
[AUD2-AST] LiveResolve.set_lut: llama
[AUD2-AST] LiveResolve.set_node_enabled: llama

[AUD2-texto] live.py menciona _exigir_version_propia 6 veces
[AUD2-texto] fake.py menciona _exigir_version_propia 5 veces
[AUD2-texto] llamadas de verdad en LiveResolve: 5 de 5

[AUD2-vivo] set_cdl -> ['SetCDL']
[AUD2-vivo] set_lut -> ['SetLUT(3,SIDEB/look.cube)']
[AUD2-vivo] set_node_enabled -> ['SetNodeEnabled(1,False)']
[AUD2-vivo] copy_grades -> ['CopyGrades']
[AUD2-vivo] reset_all_grades -> ['ResetAllGrades']
```

Los cinco `test_AUD2_en_LiveResolve_la_regla_salta_ANTES_de_tocar_la_api[...]` pasan
con el registro de la API vacío, y los cuatro de `VersionIndeterminada` también. Ahí
está la diferencia entre 6 y 5 que rompió el `==`: una mención en prosa.

---

## Caso 3 · `test_HALLAZGO_envenenar_la_clase_base_apaga_la_regla_en_Live_pero_no_en_Fake`

### Qué afirmaba el test original

Que `BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True` suelto por ahí
apagaba la regla de oro **en `LiveResolve`** (que heredaba el atributo de clase) y no
en `FakeResolve` (que lo reasignaba en la instancia). O sea, documentaba el bug y lo
dejaba en verde a propósito, con una nota: «si esto pasa a False, E ha arreglado la
asimetría y este test hay que borrarlo».

### ¿Era cierto sobre el código de hoy? No: el bug está cerrado

`LiveResolve.__init__` ahora hace `self.PELIGRO_escribir_fuera_de_la_version = ...`,
igual que el falso. Lo comprobé envenenando yo la clase base, en las dos
implementaciones, y **no me quedé en el atributo**: comprobé que la escritura sigue
bloqueada de verdad en `LiveResolve` contra el doble de la API, y que el registro de
llamadas queda vacío.

### Mi juicio, formado antes de leer ninguna justificación

El arreglo es correcto y el test reescrito afirma algo verdadero y útil. El propio
revisor había dejado escrito el criterio de caducidad de su test, y se cumplió.

Fui a la segunda parte del encargo: **¿hay más atributos de clase con la misma
asimetría?** Lo comprobé de forma sistemática, no a ojo: se enumeran todos los
atributos de datos declarados en `BaseResolveBridge` (los del `vars()` y los anotados
con valor) y se mira, para cada uno, si aparece en el `__dict__` de una instancia de
`FakeResolve` y en el de una de `LiveResolve`. Cualquier atributo que una blinde y la
otra no es la misma trampa.

Resultado: `BaseResolveBridge` declara **dos** atributos de clase,
`PELIGRO_escribir_fuera_de_la_version` e `incognitas`, y **las dos implementaciones
blindan los dos**. Donde había uno no hay dos: la simetría está completa hoy. Y el test
queda escrito para que si mañana alguien añade un tercer atributo de clase a la base y
sólo lo reasigna en uno de los dos puentes, salte solo.

### ¿Coincido con el orquestador?

Sí, sin reservas. Aquí es donde mi juicio llegó contaminado (el porqué del arreglo está
escrito en `live.py`, que el procedimiento manda leer en el paso 1), así que en vez de
fiarme de la lectura lo comprobé ejecutando las dos clases con la base envenenada. La
conclusión no depende de lo que diga el comentario.

Un matiz que el orquestador no dice y conviene anotar: cerrar E-3 ha hecho que la vía
de escape **ya no se pueda activar globalmente**. Quien la necesite (los tests que
montan «el grado que el usuario ya tenía», o el probe) tiene que pedirla por
constructor o por instancia, que es lo correcto, pero es un cambio de comportamiento
que no está en `CAPACIDADES.md`.

### Veredicto: **confirmado**

### Evidencia ejecutada

```
[AUD3] con la base envenenada: Fake=False Live=False
[AUD3] atributos de clase de BaseResolveBridge: ['PELIGRO_escribir_fuera_de_la_version', 'incognitas']
[AUD3] PELIGRO_escribir_fuera_de_la_version: instancia en Fake=True instancia en Live=True
[AUD3] incognitas: instancia en Fake=True instancia en Live=True
[AUD3] FakeResolve.__init__ acepta PELIGRO_escribir_fuera_de_la_version con defecto False
[AUD3] LiveResolve.__init__ acepta PELIGRO_escribir_fuera_de_la_version con defecto False
```

Y con la base envenenada, `vivo.set_cdl("v1-001", NODE_BALANCE, CDL())` sigue lanzando
`EscrituraFueraDeVersion` con el registro de llamadas a la API vacío.

---

## Caso 4 · el `xfail` de `test_T2_una_vineta_sola_se_etiqueta_como_vineta`

Aquí está el hallazgo de esta auditoría.

### (a) ¿La razón escrita describe el fallo real? **No. Las cifras son falsas.**

La razón dice, literalmente:

> «una vineta SOLA se detecta como no-reproducible (**lut_reproducible=0.851**) pero NO
> se etiqueta como 'vineta'. El perfil radial da **R2=0.076, muy por debajo del 0.30**
> que pide el detector, porque el residuo lo domina el desajuste general del LUT y no
> la caída radial.»

Ejecutando exactamente ese montaje contra el código de hoy, con el intérprete del repo
y dos veces seguidas para descartar aleatoriedad:

```
[AUD4-a] imagen=360x640 radio_suavizado=7
[AUD4-a] lut_reproducible=0.7319 is_pure_lut=False
[AUD4-a] residuo medio=4.6544 movimiento medio=17.3625
[AUD4-a] PUERTA 1 R2 radial =0.2887 (hace falta >= 0.3) -> CIERRA
[AUD4-a] PUERTA 2 monotonia =0.8803 (hace falta >= 0.8) -> PASA
[AUD4-a] PUERTA 3 recorrido =9.1073 (hace falta >= 1.0) -> PASA
```

Las dos cifras están mal, y en la dirección que hace parecer el problema más profundo
de lo que es:

| Lo que dice la razón | Lo que sale de verdad |
|---|---|
| `lut_reproducible = 0.851` | **0.7319** |
| `R² radial = 0.076` | **0.2887** |
| «muy por debajo del 0.30» | **falla por 0.012**, un 4 % |

Lo único que la razón acierta es **cuál** de las tres puertas se cierra: es la del R²
radial. Las otras dos pasan de sobra (la monotonía, 0.88 sobre 0.80; el recorrido,
9.11 dE2000 sobre 1.0).

Y la explicación tampoco se sostiene tal y como está escrita. «El residuo lo domina el
desajuste general del LUT y no la caída radial» sugiere que la caída radial apenas está
ahí. Está ahí, y se ve a simple vista en el perfil por coronas —del centro al borde,
de 1.9 a 11.0 dE2000, monótono en los últimos dos tercios—:

```
[AUD4-a] perfil radial (24 coronas) = [1.889, 2.087, 2.76, 2.648, 3.008, 3.892, 4.214,
 4.45, 4.443, 4.247, 3.906, 3.681, 3.55, 3.674, 3.942, 4.522, 5.138, 5.573, 6.214,
 7.085, 8.033, 8.89, 9.995, 10.996]
```

Lo que pasa es otra cosa, y es más concreta: el R² se calcula **píxel a píxel** sobre
un residuo suavizado con un radio de `min(h,w)//48` = 7 px, y a esa escala el residuo
todavía lleva encima el error del ajuste del LUT, que es ruido de alta frecuencia y
dependiente del contenido. No es que no haya viñeta: es que se mide con una lupa
demasiado fina. Subiendo **sólo** el radio de suavizado, sin tocar ni un umbral, la
puerta se abre:

```
[AUD4-b] efecto del radio de suavizado sobre las tres puertas:
[AUD4-b] min(h,w)//48 radio=7   R2=0.2887 monotonia=0.8803 recorrido=9.1073
[AUD4-b] min(h,w)//24 radio=15  R2=0.3107 monotonia=0.8837 recorrido=8.9824
[AUD4-b] min(h,w)//12 radio=30  R2=0.3345 monotonia=0.8914 recorrido=8.4277
[AUD4-b] min(h,w)//6  radio=60  R2=0.3665 monotonia=0.9056 recorrido=7.1574
[AUD4-b] min(h,w)//3  radio=120 R2=0.4130 monotonia=0.9225 recorrido=5.4731
```

Esto **no** es una propuesta de arreglo —no toco producción, y cambiar ese radio afecta
a la detección de ventanas y degradados, que hay que volver a medir—. Es la prueba de
que lo que hay documentado como límite de fondo es, en realidad, una calibración que se
queda a un 4 % y para la que ya hay una pista concreta.

**Esto importa**, y no es puntillismo. La razón del `xfail` está escrita para que
mañana «cueste diez minutos y no una tarde». Quien la lea va a buscar un problema
estructural en el detector con un R² de 0.076, y lo que hay es un umbral que se queda a
0.012. La documentación que manda a alguien en la dirección equivocada es peor que no
tener documentación: la misma cifra está copiada en **`BITACORA.md`, apartado 5, punto
4**, así que el error está en los dos sitios donde se va a mirar.

Para más inri: el commit que introdujo el `xfail` es `c108f19`, el último de la noche,
y `core/reverse/` no se ha tocado desde `4f94c8d`, que es anterior. O sea que **esas
cifras ya eran falsas en el momento en que se escribieron**. No es que el código
cambiara después.

### (b) ¿Es un `xfail` legítimo o un rojo disfrazado de verde? **Legítimo, por poco**

A favor, y pesa:

- Es `strict=True`. Si mañana alguien arregla el detector y el test pasa, la suite se
  pone roja y obliga a mirarlo. Un `xfail` no estricto sí habría sido un rojo escondido.
- **No enmascara el criterio del encargo.** El criterio T2 literal es «con viñeta **y**
  ventana encima, el diagnóstico NO puede decir que es 100 % LUT, y tiene que señalar
  la zona», y ése pasa en verde, en su propio test, sin `xfail`:
  ```
  [AUD4-T2] vineta+ventana: puro=False etiquetas=['zona local'] caja_real=(440, 30, 170, 120)
  ```
  Lo que está en `xfail` es un caso **extra** que el orquestador añadió por encima del
  criterio. Marcar en `xfail` algo que uno mismo añadió de más no es aflojar el listón:
  es no haberlo subido del todo.
- Está declarado en `BITACORA.md`, en el apartado «sin resolver», con nombre y número.

En contra, y por eso digo «por poco»: el `xfail` se añadió en el último commit de la
noche, con las cifras sin comprobar, en la misma hora en la que se etiquetó la versión.
El patrón —medir a ojo, escribir la razón, poner el `xfail`, cerrar— es exactamente el
que produce rojos disfrazados de verde. Aquí no lo es por el fondo, pero la forma en que
se hizo no permite distinguir una cosa de la otra sin ejecutarlo, que es lo que he hecho.

### (c) La gravedad real: **baja, y el fallo va hacia el lado seguro**

El encargo lo dice bien: decir «esto es un LUT» cuando no lo es es mucho peor que lo
contrario, porque manda al usuario a llevarse un `.cube` que no reproduce el grado.
**El fallo va en la dirección contraria**, y lo he comprobado:

```
[AUD4-c] sin vineta : reproducible=0.9922 puro=True  etiquetas=[]
[AUD4-c] con vineta : reproducible=0.7319 puro=False etiquetas=[]
[AUD4-c] ¿queda alguna senal de que hay algo espacial? True
```

Con la viñeta puesta, la app **no** dice que sea un LUT puro, la fracción reproducible
se desploma de 0.99 a 0.73, y el `spatial_residual` —el mapa que la GUI pinta— está
relleno. Además la nota que sale es honesta y bastante clara:

> «Me llevo el 73.2% del grado en un .cube. Lo que queda: 4.65 dE2000 de media, 11.56 en
> el percentil 95 y 19.62 en el peor píxel.»

Lo que se pierde es **la palabra «viñeta»**: el usuario ve que el 27 % del grado no cabe
en el `.cube` y ve el mapa de residuo, pero la app no le dice qué es lo que está
mirando. Es una pérdida de calidad del diagnóstico, no un riesgo de que se lleve un LUT
malo creyéndolo bueno.

Con un matiz que sí conviene vigilar: el `0.7319` es tan bajo que nadie lo va a
confundir con «esto cabe en un LUT». Si el mismo agujero apareciera con una viñeta
suave —un residuo pequeño, radial, con la fracción reproducible en 0.93— el usuario
vería un 93 % y ninguna etiqueta, y ahí la decisión de llevárselo o no sí sería
delicada. Ese caso no está probado por nadie.

### Veredicto: **confirmado el `xfail`, revertida su razón**

- **El `xfail` se queda.** Es legítimo: estricto, documentado, y por encima de un
  criterio que se cumple aparte.
- **La razón escrita hay que corregirla, y con ella el punto 4 de `BITACORA.md`.** Es
  la única cosa de este informe que pediría hacer antes de que nadie vuelva al
  proyecto: son treinta segundos y evita que alguien pierda la tarde que el `xfail`
  decía ahorrar.

---

## ¿Hay algo más que se colara esa última hora?

Miré el `4825901` entero (no sólo los tests) y el `fb8dfb1` con los mismos ojos. La GUI
es de otro y no la he auditado a fondo; esto es lo que huele.

### 1. La GUI tiene su propia definición de «es un LUT puro», y es más floja que la del núcleo

**Es lo que más me preocupa de las tres.** `gui/reverse_puente.py` trae un sustituto
completo de `core.reverse` (`_invertir_sustituto`), escrito cuando el agente F todavía
no había aterrizado, con su propio criterio:

```python
puro = reproducible > 0.92 and not puntos     # gui/reverse_puente.py:174
```

El núcleo pide otra cosa y más estricta: `UMBRAL_REPRODUCIBLE_PURO = 0.95` **y** que el
percentil 95 del residuo esté por debajo de 1.0 dE2000. Y la pantalla, con ese `puro`,
escribe:

> «Es un LUT puro: todo el grado cabe en el .cube.» — `gui/pantalla_reverse.py:644`

O sea: hay dos definiciones de la frase más peligrosa de la aplicación, y la que vive
en la GUI es la permisiva. Un grado con 0.93 de reproducible sería «LUT puro» por el
sustituto y «no puro» por el núcleo.

Y el sustituto **no es código muerto**. `invertir()` se cae a él ante *cualquier*
excepción de `core.reverse`:

```python
except Exception as exc:  # pragma: no cover
    fallo = f"{ORIGEN_SUSTITUTO} (core.reverse fallo: {exc!r})"
    return _invertir_sustituto(...), fallo
```

Está bien pensado que la pantalla no se quede en blanco, y está bien que el origen se
escriba en la interfaz. Pero el resultado es que un fallo de `core.reverse` degrada en
silencio a un criterio más flojo para decir «esto cabe en un `.cube`», que es justo la
dirección que el encargo señala como grave. Dicho sea de paso, la ironía: el sustituto
**sí** etiqueta viñetas (`label="vineta"` para los bloques del borde), o sea que en la
ruta degradada el usuario vería la palabra que en la ruta buena no ve.

Esto además choca con `CONTRATOS.md`, que es explícito: *«`confidence_level()` —
**único** sitio donde un número se convierte en alta/media/baja. No redefinas umbrales
en tu módulo»*. El espíritu es evidente y el umbral de «LUT puro» lo incumple.

Lo dejo dicho, no lo toco: `gui/` no es mío y el arreglo (que el sustituto importe los
umbrales del núcleo, o que se le quite la capacidad de decir «puro») es de una línea
pero hay que decidirlo.

### 2. `gui/` y `core/reverse/` siguen sin un solo test *commiteado*

Está reconocido en `BITACORA.md` (puntos 2 y 3 de «sin resolver»), así que no es un
hallazgo, pero conviene ponerlo al lado del punto 1: los dos módulos que entraron sin
revisión en la última hora son exactamente los dos que no tienen ni un test propio ni
`NOTAS.md`. Las 4.203 líneas de `fb8dfb1` no las ha leído nadie más que quien las
escribió, y el único contraste son 25 capturas miradas a ojo. El hallazgo del punto 1
lo encontré leyendo un fichero durante diez minutos.

**Nota de honestidad, escrita al terminar.** Mientras yo auditaba, **otro agente estaba
trabajando en `gui/` a la vez**. Al pasar la suite completa al final me aparecieron dos
ficheros que no existían cuando empecé (`tests/test_gui_texto.py`,
`tests/test_gui_apoyo.py`, sin commitear) y cuatro ficheros de `gui/` modificados en el
árbol de trabajo. Dos de esos tests nuevos están en rojo:

```
FAILED tests/test_gui_texto.py::test_ninguna_etiqueta_se_recorta_a_la_anchura_minima
FAILED tests/test_gui_texto.py::test_la_columna_del_nombre_de_clip_no_desaparece
2 failed, 1437 passed, 1 xfailed in 229.00s
```

**Eso no es un hallazgo mío y no lo cuento como tal**: es trabajo en curso de otro, sin
terminar y sin commitear, y no lo he tocado ni lo he mirado más allá de comprobar que no
afecta a lo que yo auditaba. `core/` no tiene ni una modificación pendiente en el árbol,
así que los cuatro casos de este informe están medidos contra código limpio. Lo digo
sólo para que nadie lea «2 failed» en la suite y piense que se lo he escondido, o que lo
he roto yo.

### 3. `probe/api_probe.py`: 20 `except BaseException`

La `pregunta_v0_version_actual` que se añadió en `4825901` está bien pensada —es de
sólo lectura, va la primera, y pregunta justo por el riesgo que se creó esa noche—.
Pero usa `except BaseException`, como otras 19 veces en el fichero. Eso se traga
también `KeyboardInterrupt` y `SystemExit`: si alguien le da a Ctrl-C mientras el probe
recorre doce clips, no para — se anota como un error más por clip y sigue. En una
herramienta de diagnóstico que se ejecuta con Resolve delante y un proyecto real
abierto, que no se pueda parar con Ctrl-C es molesto y es fácil de evitar. Gravedad
baja; no es de esta última hora (el patrón viene de antes), pero el código nuevo lo
repite.

### 4. Un hueco en la regla de oro que nadie ha nombrado: `set_group_post_clip_lut`

La regla de oro cubre las cinco escrituras de grado del clip. Pero `LiveResolve`
—y `FakeResolve`— tienen un sexto camino que escribe algo que el usuario ve:

```python
def set_group_post_clip_lut(self, group: str, node_index: int, lut_rel_path: str) -> bool:
    grafo = self._grupo(group).GetPostClipNodeGraph()
    ...
    return bool(grafo.SetLUT(idx, self._validar_lut(lut_rel_path)))
```

No pasa por `_exigir_version_propia`, y **entiendo que no puede**: el grafo post-clip
de un grupo de color no es de un clip, así que no tiene versión que comprobar. O sea
que no es un bug del arreglo. Pero significa que la frase que se repite por todo el
repo —«el puente se niega en redondo a escribir grado fuera de la versión de la app»—
tiene una excepción que no está escrita en ningún sitio: escribir el LUT de un grupo
pisa lo que el usuario tuviera en ese nodo, sin red y sin deshacer. Merece dos líneas
en `core/resolve/NOTAS.md` diciendo que ese camino queda fuera de la regla y por qué.

### 5. Lo que sí está bien hecho, y conviene que conste

`VersionIndeterminada` es una buena decisión y está bien argumentada: bloquear cuando
no se sabe en qué versión estamos, heredar de `EscrituraFueraDeVersion` para que quien
ya capturaba siga capturando, y cambiar sólo el mensaje para decir que el sospechoso es
la API. El razonamiento asimétrico («si bloqueo de más se pierde una mañana; si escribo
de más se pierde el trabajo de alguien y no hay deshacer») es el correcto para esta
aplicación. Lo digo porque una auditoría que sólo enumera pegas da una idea falsa del
estado del repo: de los cuatro casos, tres son correctos, y el que no lo es, lo es por
la documentación y no por el código.

---

## Lo que haría falta para cerrar lo que queda abierto

Nada de este informe se ha quedado en «no concluyente». Lo que sí queda sin probar, y
lo digo para que conste:

- **La viñeta suave** (residuo pequeño, radial, fracción reproducible alrededor de
  0.93). Es el caso donde la falta de la etiqueta «viñeta» sí podría empujar a alguien
  a llevarse un `.cube` que no reproduce el grado. No lo he probado porque fabricarlo
  bien es calibrar una escena nueva, y eso ya es escribir tests de `core/reverse`, que
  no es mi encargo. Es el primer test que escribiría el agente que recoja ese módulo.
- **`LiveResolve` contra Resolve de verdad.** Todo lo que he comprobado del puente vivo
  es contra un doble que escribí yo. Que las cinco escrituras llamen a la regla está
  demostrado; que `GetCurrentVersion()` conteste algo usable sigue sin demostrar, y es
  el primer punto de «sin resolver» de la bitácora por buenos motivos. El probe ya lo
  pregunta.

---

*Auditoría ejecutada con `.venv/bin/python -m pytest`. Los tests de esta auditoría viven
en `tests/auditoria/` y no tocan nada de producción. 29 tests, todos en verde.*
