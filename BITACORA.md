# BITÁCORA — noche del 14 al 15 de septiembre de 2026

Buenos días, Mario.

---

## 1. Semáforo

| Módulo | Estado |
|---|---|
| `core/color` — espacios, curvas, Oklab, ΔE2000 | **funciona** |
| `core/analysis` — fotogramas, estadística, huella | **funciona** |
| `core/matching` — MKL, ajuste de CDL, confianza | **funciona** |
| `core/io` — `.cube`, HALD, QC, ASC CDL, bundle | **funciona** |
| `core/resolve` + `probe` — puente y sonda | **funciona** |
| `core/reverse` — ingeniería inversa | **funciona con reservas** — no tiene tests propios ni `NOTAS.md`: el agente murió a media faena |
| `gui` — cuatro pantallas | **funciona con reservas** — igual: ni un test de interfaz, ni `NOTAS.md` |
| Tipografía de marca | **no llegó** — ninguna de las tres familias está instalada y no se pueden descargar |

**1.393 tests en verde, 1 en rojo declarado (xfail), `ruff` limpio, `main` verde.**
Se rompió el trabajo de tres agentes a media noche por el límite de la API; lo que
dejaron a medias está terminado o marcado, no disimulado.

---

## 2. Las cuatro cifras

Las medí yo aparte, con mi propio montaje, sin llamar a las funciones que cada agente
escribió para probarse a sí mismo. Están en `tests/test_entregables.py`.

| | Criterio | Resultado |
|---|---|---|
| **T1 · ida y vuelta de la ingeniería inversa** | ΔE2000 medio < 1.0 · máximo < 3.0 | **0.1415** · **1.7409** |
| **T2 · detección de lo que no es un LUT** | no puede decir 100% LUT, y señalar la zona | dice **70.0%** reproducible; la zona que señala **solapa el 100%** con la ventana real |
| **T3 · igualado de cuatro cámaras** | > 8.0 antes · < 2.0 después | **17.674** → **0.661** |
| **T4 · QC de LUT** | caza los tres, identidad limpia | caza los **3**; identidad limpia en 17³, 33³ y 65³ |

Cifras de apoyo, por si alguna media escondiera algo:

- T3, el **peor par suelto** (no la media): **0.981**. Con piel oscura: 16.910 → **0.382**.
- T1, cobertura real de un solo plano: **165 celdas de 35.937**, el 0.46% del cubo.
  Las otras 35.772 están **inventadas**, y el mapa de cobertura dice cuáles.
- Las cuatro curvas de cámara contra `colour-science`: error máximo **0.0**, no «aproximadamente».

---

## 3. Qué puedes tocar ya esta mañana

**Lo primero, y son dos minutos:**

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
python3 probe/api_probe.py --solo-diagnostico
```

No abre Resolve, no se conecta y **no escribe nada**. Sólo te dice si tu Python puede
hablar con Resolve. Lo ejecuté yo anoche y ya contestó dos de las seis preguntas (§6).

**La interfaz, sin Resolve y sin tocar nada:**

```bash
.venv/bin/python -m gui
```

Habla con un Resolve falso. No puede tocar tu material ni aunque quiera.

**Las capturas**, si prefieres mirarlas antes: carpeta `capturas/`, índice en §7.

**La suite entera** (tarda dos minutos):

```bash
.venv/bin/python -m pytest -q
```

---

## 4. Lo que decidí yo solo, y que podrías querer cambiar

1. **LUT de 33³ y no de 65³.** 35.937 celdas bastan para un look y, al invertir un
   grado, dejan muchísimas más muestras por celda. Con 65³ un solo plano cubriría el
   0.06% del cubo en vez del 0.46%, o sea que el 99.94% sería invento.
   Se cambia en `core/contracts.py:LUT_SIZE_DEFAULT`.
2. **Una rama por agente, no.** El encargo pedía `agente/a-color`, `agente/b-analisis`…
   Siete agentes trabajando a la vez en un mismo árbol no pueden tener cada uno su rama
   activa: al hacer `checkout` uno se lleva por delante lo que los otros tienen sin
   guardar. Lo que hice: todos escriben en archivos **disjuntos** (`PROPIEDAD.md`), yo
   hago **un commit por agente** en la rama `noche`, y a `main` sólo va lo que está en
   verde y revisado. El historial sigue diciendo quién hizo qué.
3. **El espacio de trabajo es DaVinci WG/Intermediate**, no lineal. En lineal la
   covarianza la mandan los especulares y el sol, y el emparejamiento se va detrás de
   ellos. Está razonado en `core/matching/NOTAS.md`.
4. **La regla de oro pasó de convención a código.** El revisor demostró que se podía
   escribir un grado sin crear la versión antes. Ahora `core/resolve/bridge.py` corta
   las cinco escrituras si la versión activa no es de la app. **Esto tiene un riesgo que
   creamos nosotros anoche y está en §5.**
5. **`rgb_to_lab` cambió para los negativos**, prolongando el tramo lineal en vez de
   espejar la potencia. La ITU los espeja en la BT.1361; `colour-science` los prolonga.
   Elegí poder decir «nuestras curvas son la misma función que las suyas, punto».
   Se revierte con dos líneas en `core/color/transfer.py`.
6. **El umbral de banding del QC se queda en 0.02** aunque marca la gamma `x**(1/2.2)`
   como banding. Está medido: el LUT se desvía 11/255 de la curva que dice representar
   incluso con 65 puntos, o sea que es verdad. Es una decisión de gusto sobre material
   real y la tomaría contigo delante. `core/io/qc.py:SALTO_MINIMO_BANDING`.
7. **`LUTQualityReport` vive en `core/io/qc.py` y no en los contratos.** Sólo viaja de
   `io` a la GUI. Si mañana lo necesita un tercero, se mueve tal cual.
8. **Las tipografías.** Inter, Chakra Petch y JetBrains Mono **no están instaladas** en
   este Mac y no podía descargarlas. La app las pide primero y cae a Helvetica Neue y
   Menlo. **Las capturas de esta noche NO enseñan la tipografía de la marca**: el
   layout, el color y el tracking sí son los buenos, las letras no. Instala las tres y
   la app las coge sola. Detalle en `docs/IDENTIDAD.md`.
9. **`#ff6a3d` es a la vez `brand-400` y el estado «Fuera» del inventario.** Interpreté
   que lo reservado es **el tratamiento de pastilla**, no el hex, así que se usa como
   texto e icono de marca sobre oscuro —que es su función declarada— y nunca como
   pastilla al 12%/25%. Si no te cuadra, se cambia en `gui/identidad.py`.
10. **Reescribí tres tests del revisor** cuando ya se había caído por el límite de API.
    Afirmaban un fallo que su autor acababa de arreglar. Está dicho en el código quién
    los tocó y por qué.

---

## 5. Sin resolver

**Por orden de lo que más me preocupa.**

1. **Nadie ha visto nunca `GetCurrentVersion()` contestar contra Resolve de verdad, y
   ahora la llamamos en cada escritura.** Es el riesgo que creamos anoche al cerrar el
   agujero de la regla de oro. Si devuelve una cadena vacía o un `None`, **bloquea todas
   las escrituras** y la app no sirve para nada hasta que alguien mire. Lo mitigué: hay
   una excepción aparte (`VersionIndeterminada`) con un mensaje que explica qué mirar, y
   el probe lo pregunta. **Es lo primero que hay que comprobar, antes incluso que las
   seis incógnitas.**
2. **`core/reverse` no tiene ni un test propio ni `NOTAS.md`.** El agente cayó por el
   límite de API. El módulo funciona —lo prueban T1 y T2, que son míos— pero nadie lo ha
   atacado por los bordes y no está escrito por qué decidió lo que decidió. Es el módulo
   más complejo del proyecto y el que menos red tiene.
3. **`gui` no tiene ni un test ni `NOTAS.md`**, por lo mismo. Lo que sí hay son 25
   capturas que miré una a una, y dos bugs que arreglé después de mirarlas.
4. **Una viñeta sola no se etiqueta como «viñeta».** Se detecta que no es un LUT puro,
   pero no se emite el hotspot. Está como `xfail(strict=True)` en
   `tests/test_entregables.py`.
   **CORREGIDO EL DÍA 2:** las dos cifras que había aquí —«reproducible 0.851» y
   «R²=0.076»— **eran falsas**, medidas sobre un montaje distinto del que usa el test.
   Las cazó la auditoría independiente. Las reales son **0.7319** y **R²=0.2887**, y el
   diagnóstico cambia de sentido: no es que el residuo no sea radial, es que **de las
   tres puertas del detector pasan dos** (monotonía 0.8803 ≥ 0.80 y recorrido 9.1073 ≥
   1.0) y sólo cierra la del ajuste, por un 4%. Ver `AUDITORIA-DIA2.md`, caso 4.
5. **La ida y vuelta de un plano sin gradar no vuelve exacta**: 0.312 ΔE2000 de media y
   6.36 en el peor píxel, con el CDL saliendo identidad exacta. Lo que no vuelve exacto
   es el LUT, porque el relleno de huecos suaviza y ese suavizado se cuela en las celdas
   del borde de la zona con datos. Con el 0.46% de cobertura que da un plano, hay
   muchísimo borde. Es la primera cifra que mirar si alguien toca el relleno.
6. **El mismo plano contra sí mismo sale con `is_pure_lut = False`**, que es confuso. El
   diagnóstico entra por la rama «esto no es un grado, es el mismo plano» y ahí el
   residuo del relleno supera el umbral. No es grave, pero está feo.
7. **La huella de contenido no lleva ningún descriptor de color**, a propósito. Como
   ahora decide ella sola el desajuste de contenido, dos escenas con la misma
   composición y colores completamente distintos le parecerían la misma. Con material
   sintético no pasa; con material tuyo, ni idea.
8. **`es_version_nuestra` va por nombre.** Una versión que hayas llamado `SIDEB COLOR
   pruebas` se da por nuestra. La API no marca quién creó una versión, así que puede que
   no tenga arreglo, pero que esté dicho.
9. **Material log sin metadatos se asume Rec.709.** Un S-Log3 sin etiquetar se
   decodifica mal y **todas las estadísticas salen plausibles y equivocadas**. Sólo hay
   un aviso. Es el fallo silencioso más probable de todo el proyecto.
10. **`core/color` nunca se ha ejercitado con dos puntos blancos distintos.** Los ocho
    espacios son D65 y el camino de adaptación de Bradford está escrito y probado pero
    no usado. El día que entre un DCI-P3, probarlo antes de fiarse.

---

## 6. Lo que necesito de ti

**Uno.** Ejecuta el probe con Resolve Studio abierto, un proyecto de pruebas y un
timeline con al menos un clip:

```bash
python3 probe/api_probe.py --informe ~/Desktop/informe_resolve.json
```

Te va a decir exactamente qué va a tocar y **espera a que escribas `s`**. Hasta entonces
sólo lee. Crea la versión `SIDEB COLOR PROBE` en un solo clip y deja seleccionada la tuya
al terminar. Mándame el `.json`.

**Dos.** Las seis incógnitas. **Dos ya están contestadas** por lo que ejecuté anoche —sin
conectarme a nada, sólo mirando si el módulo se importa:

| | Pregunta | Estado |
|---|---|---|
| F0-1 | ¿`ExportStills(..., 'drx')` funciona? | pendiente |
| F0-2 | ¿El still lleva el grado o el material limpio? | pendiente |
| F0-3 | ¿`SetLUT()` acepta un `.dctl`? | pendiente |
| F0-4 | ¿Descarga directa o Mac App Store? | **contestada: descarga directa** |
| F0-5 | ¿Hace falta `OpenPage("color")`? | pendiente |
| F0-6 | ¿Python 3.12 arm64 importa `fusionscript`? | **contestada: sí**, con el 3.12.14 del venv |

Todo lo que depende de ellas está aislado en `core/resolve/incognitas.py`, con valor
conservador (asumir que no se puede) y una marca `# TODO(F0-n)` cada una. Cuando me
mandes el informe, son seis constantes.

**Y una séptima que no estaba en la lista y que importa más que todas:** ¿`AddVersion`
hereda el árbol de nodos, o la versión nueva empieza en blanco? **Si empieza en blanco,
la app no puede funcionar**, porque la API no sabe crear nodos y no habría nodo 2 ni 3.
El probe la mide y la contesta.

**Tres.** Instala Inter, Chakra Petch y JetBrains Mono si quieres ver la interfaz con la
tipografía de verdad.

**Cuatro.** Dime si te cuadran las decisiones 1, 6 y 9 del apartado 4. Son las tres que
tomé a ciegas sin material real delante.

---

## 7. Índice de capturas

Todas en `capturas/`, generadas con `QT_QPA_PLATFORM=offscreen` y regenerables con
`QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python gui/capturas.py`.
La anchura mínima real de la ventana es **966 px**.

| Archivo | Qué se ve |
|---|---|
| `01-clips-1440/1024/966.png` | Lista de clips con su confianza y por qué la tiene. La confianza se distingue **por forma**, no por semáforo |
| `02-comparar-1440/1024/966.png` | Antes / después de un clip |
| `03-aplicar-1440/1024/966.png` | Qué va a pasar **antes** de que pase: qué nodo, qué versión, qué LUT |
| `04-reverse-1440/1024/966.png` | Ingeniería inversa: el CDL editable, el mapa de cobertura con las celdas inventadas a cuadros, y el diagnóstico |
| `05-clips-cero.png` | Cero clips |
| `06-clips-uno.png` | Un clip |
| `07-clips-doscientos(-minimo).png` | Doscientos clips, y lo mismo a la anchura mínima |
| `08-comparar-sin-imagen.png` | Comparar sin imagen cargada |
| `09-clips-confianza-baja.png` | Confianza baja en todos: cuatro contornos discontinuos seguidos |
| `10-aplicar-desconectado(-minimo).png` | Resolve desconectado: el botón se apaga y se explica por qué |
| `11-aplicar-lut-malo.png` | El look no pasa el QC: se avisa **antes** de escribirlo, y en naranja de marca, no en rojo |
| `12-aplicar-resultado.png` | Después de aplicar: qué se escribió y en qué versión |
| `13-aplicar-averia.png` | Avería simulada en `set_lut`: el lote sigue y el fallo se cuenta |
| `14-reverse-cobertura-casi-nula.png` | Rejilla de 65³ con un solo fotograma: casi todo inventado |
| `15-reverse-sin-vineta.png` | El mismo grado sin viñeta: el diagnóstico cambia |

**Las miré una a una**, y arreglé dos cosas después de mirarlas: a 966 px los rótulos del
CDL salían «SLO…», «OFF…», «PO…», «SAT…», y el pie del carril salía «escribe en «SIDEB
COL…» incluso a 1440. Las dos están arregladas y recapturadas.

---

## 8. Cómo se trabajó, por si hay que repetirlo

Nueve agentes en cuatro olas, cada uno con archivos en propiedad exclusiva
(`PROPIEDAD.md`). Nadie mergeó su propio trabajo. El revisor **ejecutaba, no leía**: se
fabricó él mismo los ficheros hostiles y pegó la salida real.

Encontró **siete fallos**, todos reales y todos aceptados. El más grave: se podía escribir
un grado sin pasar por `AddVersion`, o sea que «nada destructivo» era una convención y no
una garantía.

Tres cosas que me parecen el mejor síntoma de que la noche fue honesta:

- El agente de color descubrió que **su propia afirmación de NOTAS.md era falsa** porque
  sólo barría valores positivos, y lo dijo.
- El agente de emparejamiento **midió su propia recomendación de la ronda anterior**,
  comprobó que no funcionaba, y dejó la tabla escrita para que el siguiente no repita la
  idea.
- El revisor **se equivocó en dos datos y se corrigió a sí mismo**.

Y dos fallos míos, por si sirven: conté la cobertura del cubo con la convención
equivocada dos veces seguidas (la acumulación es trilineal y el dominio del LUT es el
original **ya pasado por el CDL**), y fabriqué un «LUT no monótono» que no lo era, porque
restaba menos que el paso de rejilla. El QC tenía razón al no avisar.

---
---

# DÍA 2 — 15 de septiembre de 2026

Buenos días otra vez, Mario. Lo de anoche sigue arriba sin tocar; esto se añade debajo.

**Lo primero que tienes que saber:** una de las cifras que te di anoche era **falsa**.
Está corregida y explicada en §D2-1. No cambia ninguno de los cuatro resultados, pero
sí cambiaba el diagnóstico de un problema, y por eso va lo primero.

---

## D2-0 · Semáforo

| | Ayer | Hoy |
|---|---|---|
| `core/color`, `core/analysis`, `core/matching` | funciona | funciona |
| `core/io` | funciona | funciona · **+65³ de entrega, aviso de banding reescrito** |
| `core/resolve` + `probe` | funciona | funciona · **`GetCurrentVersion()` blindado** |
| `core/reverse` | funciona **con reservas** (sin tests ni notas) | **funciona** · 34 tests, `NOTAS.md`, **viñeta arreglada** |
| `gui` | funciona **con reservas** (sin tests ni notas) | **funciona** · 102 tests, `NOTAS.md`, **6 bugs arreglados** |
| Auditoría de lo arbitrado anoche | no existía | **hecha, por alguien que no era parte** |

**1.699 tests en verde, 1 rojo declarado, `ruff` limpio.** Ayer eran 1.393.

---

## D2-1 · Lo que hice mal anoche, y lo encontró la auditoría

Anoche, con el revisor ya muerto por el límite de API, me encontré tres de sus tests en
rojo y decidí **yo solo** —siendo a la vez quien había tocado el código y quien
arbitraba— que los tests estaban mal. Hoy lo ha auditado alguien que no escribió nada de
eso, formando su juicio antes de leer mi justificación. Veredictos:

| Caso | Veredicto |
|---|---|
| 1 · vía de escape `== 1` → `== 2` | **confirmado** |
| 2 · regla de oro `==` → `>=` | **código confirmado, test revertido** |
| 3 · hallazgo E-3 cerrado | **confirmado** |
| 4 · el `xfail` de la viñeta | **`xfail` confirmado, su razón revertida** |

Tres de cuatro bien. Los dos errores, y los dos importan:

**El `>=` del caso 2 no era una aserción más floja: no era una aserción.** El test contaba
apariciones de un nombre en el texto fuente. Cambiarlo a `>=` lo hace pasar aunque las
cinco menciones estén en un comentario y no haya ni una llamada — que es exactamente el
escenario que ese test existía para impedir. El auditor dejó escrita la comprobación por
AST, que sí lo afirma.

**Las dos cifras que puse en el `xfail` de la viñeta eran falsas.** Dije
`lut_reproducible = 0.851` y `R² = 0.076`; lo real es **0.7319** y **0.2887**. Estaban
medidas sobre un montaje distinto del que usaba el test, y no es un detalle de precisión:
con 0.076 la lectura era «el residuo no tiene nada de radial», o sea un problema
estructural; con 0.2887 la lectura es que **de las tres puertas del detector pasaban dos**
y sólo cerraba la tercera, por un 4%. Mandaba a buscar un problema de fondo donde había un
umbral rozando. Corregido en los dos sitios donde estaba, con un aviso dentro de que la
versión anterior mentía, porque puede que ya la hubieras leído.

**La regla que se rompió, ahora explícita y aplicada todo el día:** no se arbitra un
desacuerdo en el que uno es parte. Hoy, cuando dos tests ajenos se han puesto en rojo por
cambios de otros, la decisión la ha tomado el auditor, no yo.

---

## D2-2 · Lo que el auditor encontró y valía más que los cuatro casos

**`gui/reverse_puente.py` tenía su propia definición de «esto es un LUT puro», y era más
floja que la del núcleo** (0.92 a secas, frente a 0.95 **y** percentil 95 por debajo de
1.0 ΔE). Y no era código muerto: la GUI se caía a ese sustituto ante **cualquier**
excepción de `core.reverse`.

O sea: un fallo del núcleo degradaba **en silencio** al criterio permisivo, y con ese
criterio la pantalla escribía «Es un LUT puro: todo el grado cabe en el .cube». Que es la
frase más peligrosa que puede decir esta app, y degradaba justo en la dirección grave.

Arreglado: **la GUI ya no emite ese veredicto nunca.** Si el núcleo no ha contestado, la
pantalla dice que no se ha podido decidir, y la caída **se ve**, con un aviso que nombra
la excepción (captura `16-reverse-sustituto.png`). Tres barridos por AST impiden que se
cuele otro umbral en `gui/`.

Honestidad del que lo arregló, que agradezco: con el par de demostración el criterio viejo
no llegaba a dispararse. Era una trampa latente, no algo que ya saliera en pantalla.

---

## D2-3 · La ceguera a la viñeta: arreglada, y no era calibración

El umbral de zonas locales salía de `base + 4·1.4826·MAD` sobre el campo de residuos. **La
MAD es robusta frente a valores atípicos, y una viñeta no es un valor atípico**: afecta a
casi todos los píxeles del cuadro. El estimador se la tragaba como línea base. Era el
estadístico equivocado, no un número mal puesto.

Lo que lo resolvió fue **cambiar qué se mira**. Una viñeta es multiplicativa sobre la
imagen, así que su ΔE depende del brillo local y no sólo del radio; su **ganancia**, no:

| campo | viñeta | ventana | grano |
|---|---|---|---|
| ΔE2000 (R² radial) | 0.2887 | 0.0370 | 0.0559 — y **todo correla positivo**, porque el ΔE no tiene signo |
| **log de la ganancia** (R² radial) | **0.879** | 0.034 | — y el **signo** separa: la viñeta oscurece hacia fuera (−0.875), la ventana no (+0.058) |

Los seis casos, medidos:

| | montaje | resultado |
|---|---|---|
| T2a | viñeta 0.55 | **viñeta**, centro estimado a 22.4 px del real |
| T2a | viñeta 0.35 | **viñeta**, centro a 17.8 px |
| T2b | ventana sola | **zona local**, IoU **0.977** |
| T2c | viñeta + ventana | **las dos por separado**, IoU 0.909 |
| T2d | nada espacial | **ninguna etiqueta**, `is_pure_lut` |
| T2e | grano | **textura**, no ventana |
| T2f | h264 muy comprimido | **ninguna**, 94.41% reproducible |

**T1 y T2 salen idénticos a los de anoche** (0.1415 / 1.7409 y 70.0%), que es justo la
comprobación de que el arreglo está entero en el detector y no toca el ajuste del LUT.

---

## D2-4 · Las cuatro cifras, ayer y hoy

| | Criterio | Anoche | Hoy |
|---|---|---|---|
| T1 ingeniería inversa | ΔE medio <1.0 · máx <3.0 | 0.1415 · 1.7409 | **0.1415 · 1.7409** |
| T2 lo que no es un LUT | no decir 100% LUT, señalar la zona | 70.0%, solape 100% | **70.0%, solape 99.4%, y ahora etiqueta viñeta, ventana y textura** |
| T3 igualado de 4 cámaras | >8.0 antes · <2.0 después | 17.674 → 0.661 | **17.674 → 0.661** |
| T4 QC de LUT | caza los 3, identidad limpia | 3/3, limpia | **3/3, limpia** |

---

## D2-5 · Lo demás que entró hoy

- **65³ como opción de entrega final, nunca por defecto**, como pediste. Está en
  `core/io/remuestreo.py` y **no** como parámetro de `escribir_cube`, para que se vea en
  la línea que lo pide que se interpola y no se gana precisión. Un dato bonito: **65 =
  2·33 − 1**, así que los puntos nuevos caen sobre los viejos y sus puntos medios, y el
  LUT de 65 **no es casi el mismo: es el mismo** (desviación máxima 5.7e-08, o sea
  0.0000146 sobre 255). Lo único que se gana es un fichero 7.6 veces mayor: 0.93 MB →
  7.07 MB.
- **El aviso de banding ya dice lo que tú dijiste**: si el LUT incluye la conversión a
  Rec.709, los escalones en sombras son esperables y no son un defecto, es un aviso y no
  bloquea nada. Con un mensaje distinto para un escalón en los medios, para que el aviso
  no diga «tranquilo» siempre y nadie vuelva a leerlo. **El detector no se ha tocado.**
- **`#ff6a3d` escrito en `gui/identidad.py`**, no sólo en un documento, con un test que
  comprueba que ninguna pastilla lo usa de fondo.
- **`GetCurrentVersion()` blindado**: `FakeResolve` sabe simular las cuatro respuestas
  raras (vacía, `None`, diccionario sin las claves, y lanzar) y las cuatro por las cinco
  escrituras dan «no puedo garantizar la versión, no escribo» con **cero escrituras** — 40
  casos, y no basta con que lance: se comprueba que no queda grado escrito. Con
  contrapeso: un diccionario **con** el nombre dentro se entiende y sí escribe, porque si
  mañana la API contesta así la app tiene que funcionar.
- **Ctrl-C ya para el probe.** Tenía 24 `except BaseException` (el auditor contó 20; eran
  24) y un `suppress(BaseException)` que un barrido de los `except` no ve.
- **`set_group_post_clip_lut` queda fuera de la regla de oro**, porque un grafo post-clip
  de grupo no tiene versiones. No es un bug, pero no estaba escrito en ninguna parte. Ahora
  sí, en cuatro sitios y con un test que vigila que siga estándolo.

---

## D2-6 · Seis bugs de interfaz que sólo aparecieron al escribir los tests

Es el argumento de por qué la deuda de anoche había que pagarla. Tres se veían en las
capturas que dimos por buenas:

1. **Los diez números del CDL de «antes/después» no salían en monoespaciada.** **La hoja de
   estilo pisa a `setFont()`.** Incumplía una regla firme de la identidad, y se veía: las
   cuatro líneas no alineaban.
2. El tracking de los rótulos estaba a 0.145em, por debajo del 0.15 mínimo. Mismo origen.
3. Rótulos recortados a 911 px: con el timeline vacío la ventana bajaba de su propio mínimo.
4. «desajuste de contenido» se cortaba justo cuando hay desajuste.
5. «1 clips» en el pie.
6. La columna CLIP a la anchura mínima. **Éste no está arreglado**, ver abajo.

**La anchura mínima ha pasado de 966 a 985 px**, y no por meter nada nuevo: por quitar tres
números puestos a ojo. Ahora sale del contenido y ya no depende del estado. *(La §7 de
ayer dice 966; era correcto ayer y ya no lo es.)* Las capturas `*-966.png` son ahora
`*-985.png`.

---

## D2-7 · Sin resolver

1. **La columna CLIP a la anchura mínima enseña «A…a».** Arreglarlo cuesta 82 px y subiría
   la ventana a 1063, con lo que **la captura nominal de 1024 dejaría de poder existir**.
   Es un presupuesto de píxeles entre tres salidas y lo decides tú. Está como
   `xfail(strict=True)` con toda la aritmética. **Una tercera vía que no está evaluada:**
   que a la anchura mínima cedan las columnas de ΔE en vez de la del nombre — el nombre
   del clip es lo que identifica la fila, y un ΔE se puede leer en el panel de la derecha.
2. **Una viñeta sola saca 7 «zona local» de más en las esquinas.** No es ruido: el LUT
   absorbe la viñeta de forma dependiente del color. Se suprimen con dos líneas y el
   agente **decidió no hacerlo**, y estoy de acuerdo: el factor estaría ajustado sobre dos
   casos del mismo generador y se comería una ventana escondida bajo una viñeta fuerte, que
   es el lado peligroso. Lleva aviso por escrito y un test que vigila que el aviso siga ahí.
3. **Queda un `setFont()` pisado por la hoja de estilo**: `gui/pantalla_aplicar.py:286`, la
   ruta del `.cube`, que es justo donde la monoespaciada se nota. 32 widgets piden esa
   fuente y 31 la consiguen. Estético. **No lo he tocado yo** porque arreglarlo obliga a
   cambiar el test de cuarentena del auditor, y no quiero volver a arbitrar algo en lo que
   soy parte.
4. **Todos los `px=` de `Cifra` los ignora la hoja de estilo**: las cifras grandes (22, 26
   px) salen a 13. Está comprobado. **Es decisión tuya**: la interfaz que has visto y que
   te gusta es la de 13 px uniformes, y arreglarlo cambia el aspecto de las cuatro
   pantallas.
5. **Sigue sin haberse ejecutado nada contra un Resolve real.** Es lo de siempre y sigue
   siendo lo más importante.
6. Los límites de fondo de ayer siguen abiertos: material log sin etiquetar se asume
   Rec.709; la huella de contenido no mira el color; los seis espacios son D65.

---

## D2-8 · Lo que necesito de ti

1. **El probe, que sigue siendo lo primero.** Nada ha cambiado:
   `python3 probe/api_probe.py --solo-diagnostico` y luego, con Resolve abierto,
   `python3 probe/api_probe.py --informe ~/Desktop/informe_resolve.json`. Ahora la
   pregunta V-0 resume **los doce clips** y dice en crudo qué devuelve
   `GetCurrentVersion()` y de qué tipo, que es lo que hace falta para cerrar el riesgo.
2. **La columna CLIP** (D2-7 punto 1): ¿subimos la ventana a 1063, o que cedan los ΔE?
3. **Las cifras grandes de la interfaz** (D2-7 punto 4): ¿las dejamos a 13 px uniformes
   como están, o las arreglamos y cambia el aspecto?
4. Instala Inter, Chakra Petch y JetBrains Mono si quieres ver la interfaz con la
   tipografía de verdad. **Las capturas siguen sin enseñarla.**

---
---

# DÍA 3 — 15 al 16 de septiembre de 2026

Los días 1 y 2 siguen arriba sin tocar.

**Lo primero, porque cambia cómo hay que leer los titulares del proyecto:** las cuatro
cifras se han vuelto a medir desde fuera, y **no hay ninguna inventada** — eso estaba
bien. Lo que sí se ha descubierto es que **son honestas para su montaje, y su montaje es
más benévolo de lo que parecía**. Está entero en §D3-2.

---

## D3-0 · Semáforo

| | Día 2 | Hoy |
|---|---|---|
| Las cuatro cifras | autoinformadas | **remedidas desde fuera**, con arnés propio y ΔE2000 de `colour-science` |
| Procedencia de las cifras | no existía | **`CIFRAS.md`**, con montaje, comando y fecha de cada número |
| Umbrales dispersos | 1 duplicado conocido | **4 más encontrados**, todos centralizados en `core/umbrales.py` |
| Escala tipográfica | rota, y se creía una decisión | **arreglada** — era una línea |
| Columna del nombre de clip | «A…a» a la anchura mínima | **124 px**, y la ventana **encoge** de 985 a 973 |

**1.817 tests en verde, 1 rojo declarado, `ruff` limpio.** Ayer 1.699.

---

## D3-1 · Lo que se hizo mal hoy, y lo cazó el procedimiento

Escribí `CIFRAS.md` por la mañana con la regla de que ningún número se publica sin su
comando. Por la tarde verifiqué los comandos uno a uno y **dos de las filas que yo mismo
acababa de escribir no seleccionaban ningún test**.

Las dos siguen en el archivo, marcadas como **«sin comando»**, porque describen el estado
anterior al arreglo y ése ya no se puede montar sin deshacerlo. Pero quedan señaladas.

Lo cuento porque es el mejor argumento a favor del archivo: **lo cazó el procedimiento el
mismo día que se estrenó, y a quien lo escribió.**

---

## D3-2 · Las cuatro cifras, medidas desde fuera

Un agente que no escribió nada del repo las volvió a medir con **su propio material, su
propio CDL y su propio LUT**, entrando sólo por la API pública, y calculando el ΔE2000 con
`colour-science` **y no con el del repo** — porque verificar las cifras de ΔE del repo
usando su propio ΔE es un círculo: si la métrica estuviera mal, los dos lados fallarían
igual y saldría verde.

**Primero, la buena noticia:** corrió su arnés también contra una copia limpia de
`git archive HEAD` y **las cifras publicadas se reproducen exactamente**. Su ΔE2000
coincide con el del repo con error **1.6e-13** y su camino de conversión de espacios con
**2.2e-13**; los dos pasan los 34 pares de Sharma. **No hay ninguna cifra inventada.**

**Y ahora lo que no se sabía:**

| | Publicado (montaje del repo) | Medido aparte (montaje propio) |
|---|---|---|
| T1 medio · **máximo** | 0.1415 · 1.7409 | 0.1687 · **2.8867** |
| T2 reproducible · solape | 70.0% · 0.9941 | 90.8% · **0.0000** |
| T3 antes → después · **peor par** | 17.674 → 0.661 · 0.981 | 15.499 → 1.085 · **1.906** |
| T4 | 3/3, identidad limpia | **coincide** |

Los cuatro criterios se siguen cumpliendo. Pero:

1. **Las dos cifras que de verdad deciden no son las que se publican.** En T1 manda el
   máximo, no el medio: **2.8867, a 0.11 del límite de 3.0**. En T3 manda el peor par, no
   la media: **1.906, a 0.094 del límite de 2.0**. Los titulares enseñan las holgadas.
2. **El solape de T2 no se reproduce**, y por un motivo concreto: el medidor aplicó la
   viñeta y la ventana **en luz lineal**, que es como se comporta una viñeta óptica de
   verdad; el repo las aplica sobre la imagen ya codificada. Con la convención del repo
   sale 0.8053 y pasaría.
3. **Falta una cifra en todos los titulares:** la cobertura del cubo es del **0.46%**. O
   sea que **el 99.5% del `.cube` que se entrega está inventado** por el relleno de huecos.
   Debería decirse al entregar un LUT.

### Y un hallazgo que vale por sí solo el encargo del día

**El detector espacial sabe dónde está la ventana, pero no sabe dibujar la caja.** El
**93.6%** de los píxeles de mayor residuo caen dentro de la ventana real, y el residuo
medio dentro es **4.74 veces** el de fuera — o sea que el mapa de calor acierta. Pero la
zona que declara **principal** es un cuadrito de 31×29 en una esquina en sombra, con
solape **0.0000**. La interfaz lista las zonas ordenadas por magnitud, así que **hoy la
primera línea señala el sitio equivocado**.

Las dos cajas se llevan un **11.85%**, o sea que no basta con retocar un umbral: el que
gana, gana por poco y por el motivo equivocado.

**No se ha arreglado hoy, a propósito.** Arreglar y volver a medir en el mismo movimiento
es exactamente cómo se cuela un número que no es. Queda como `xfail(strict=True)` con un
`reason` que cumple la regla nueva, más un test centinela **en verde** que aferra las dos
cajas y sus magnitudes: si mañana se mueven, salta ése diciendo qué cambió, en vez de un
`XPASS` que nadie sabe interpretar.

---

## D3-3 · Umbrales: cuatro duplicados más, ninguno conocido

El hallazgo grave del día 2 —la interfaz con su propia definición, más floja, de «LUT
puro»— no era un bug: era una **clase** de bug. Barrida del lado de `core/`:

| Criterio | Estaba escrito en |
|---|---|
| «el plano casi no cubre el cubo» (0.005) | `diagnostico.py` **y** `invertir.py`, literal suelto en los dos, con dos frases distintas |
| «esta celda tiene datos suficientes» (4) | `acumulacion.py`, `invertir.py` **y** `contracts.py` |
| ΔE2000 = 1.0, «dos colores indistinguibles» | tres constantes con el mismo comentario dicho de tres formas |
| `1e-6` en `qc.py` | guarda de división **y** criterio de «este LUT aplasta la imagen a un color» |

**38 constantes a `core/umbrales.py`**, cada una con nombre, valor, **unidad** y una línea
de por qué. La unidad no estaba en ningún sitio, y es justo lo que evita confundir un
`1.0` que es ΔE2000 con un `0.95` que es una fracción.

**Y 95 se quedaron donde estaban, a propósito.** Semillas, topes de memoria, binning y
coeficientes publicados no son criterios de decisión; juntarlos habría creado un
módulo-Dios que acopla todo con todo. Un barrido que mueve las 115 está mal hecho.

Hay un test que recorre el AST y **falla si aparece un literal de umbral fuera de ese
módulo**. Caza `if reproducible > 0.92` aunque esté sin espacios o dentro de un ternario,
y no da la lata con `len(x) > 0`. Tiene **control negativo**: le planta a propósito el
literal del día 2 y comprueba que lo caza.

**Verificación independiente de que el traslado no cambió nada:** comparé todos los
literales numéricos que desaparecen de `core/` en ese commit contra las constantes que
aparecen. **Ningún valor cambió.** Tres números quedaban huérfanos y los tres estaban en
comentarios, no en código.

### Lo que salió del barrido y no esperaba nadie

**`CONFIDENCE_ALTA` = 0.75 y `CONFIDENCE_MEDIA` = 0.45 no tienen ninguna medida detrás.**
Ni en el código, ni en los commits, ni en la bitácora, ni en las notas. **Es el veredicto
más visible de la app** — lo que lees en cada clip — y los dos números salieron de la
nada. Están marcados como «no medido» en `core/umbrales.py` y en `CIFRAS.md` §6, junto a
otros once.

---

## D3-4 · La tipografía era una línea

```
QWidget { …; font-size: 13px; }
```

`QWidget` casa con **todos** los widgets, subclases incluidas; y una propiedad de fuente
declarada por una regla que casa **gana a `setFont()`**, mezclándose propiedad a propiedad.
Por eso la familia monoespaciada sí llegaba (la declara la regla `.cifra`) y el tamaño no
(sólo lo declaraba la universal). Medido sobre la misma etiqueta: **sin hoja 26 px, con la
hoja 13 px, con la hoja sin `font-size` en `QWidget` 26 px**.

La regla que lo sostiene: **la hoja de estilo no declara `font-size` en ninguna regla.**

Estaban rotos los cinco tamaños de texto, las cinco cifras grandes, dos de las cifras
normales, las entradas y la ruta del `.cube`. Ahora no falla ninguno.

**Una excepción con motivo medido:** las cabeceras de tabla son el único rótulo en
mayúsculas **sin el tracking de marca**, porque un `QHeaderView::section` es un
pseudo-elemento y no se puede vestir desde el código — comprobadas las dos vías.

**La columna del nombre de clip** pasa de 56 a **124 px** a la anchura mínima. El fondo era
que el ancho **se calculaba dos veces** y no coincidían. Y **la anchura mínima baja de 985
a 973 px**: los rótulos de 10 px vuelven a ser de 10 y no de 13.

*(El encargo de hoy decía «que sigue en 966×643». Era cierto el día 1; el día 2 pasó a 985
y hoy a 973×651.)*

---

## D3-5 · Sin resolver

1. **La caja principal del detector espacial señala el sitio equivocado** (§D3-2). Es lo
   primero de mañana.
2. **`CONFIDENCE_ALTA` y `CONFIDENCE_MEDIA` no están medidos**, y son lo que más se lee.
3. **El etiquetado de viñeta está calibrado para el dominio codificado**: una viñeta
   óptica aplicada en luz lineal —que es lo físicamente correcto— no lo dispara.
4. **`INSIGNIA_ANCHO` se queda 7 px corto** para «MEDIA 100%». No se ve hoy porque un 100%
   siempre sale `alta`. Subirlo subiría la anchura mínima.
5. **Las cabeceras de tabla, sin tracking**, por el límite de Qt de arriba.
6. **La auditoría del día 3 quedó a medias**: el agente se colgó dos veces. Alcanzó a
   verificar que el traslado de umbrales no cambió valores —lo confirmé yo aparte— pero
   **no llegó a revisar la tipografía ni la anchura mínima ni su propio test de
   cuarentena**, que hoy pasa en vacío (`test_AUDF_ninguna_etiqueta_pide_fuente_de_cifra…`:
   son 35 de 35 y su aserción es `0 <= 1`). **Queda pendiente y no lo arreglo yo**, porque
   soy parte.
7. **Sigue sin ejecutarse nada contra un Resolve real.** Lo de siempre, y lo más importante.

---

## D3-6 · Lo que necesito de ti

1. **El probe.** Sigue siendo lo primero y no ha cambiado.
2. **Los dos márgenes ajustados** (§D3-2): T1 pasa por 0.11 y T3 por 0.094 sobre montajes
   razonables. ¿Te vale así, o quieres que se aprieten antes de enseñárselo a un cliente?
3. **`CONFIDENCE_ALTA` = 0.75 y `CONFIDENCE_MEDIA` = 0.45**: nadie los midió nunca. ¿Los
   dejamos, o los calibramos contra material tuyo cuando lo haya?
4. **La convención de la viñeta** (§D3-5 punto 3): ¿la calibramos para luz lineal, que es
   lo que hace una lente de verdad?
