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
