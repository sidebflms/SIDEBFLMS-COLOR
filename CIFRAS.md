# CIFRAS — de dónde sale cada número del proyecto

**Ninguna cifra se publica sin poder decir de dónde salió.** La regla está en
[`CONTRATOS.md`](CONTRATOS.md); esto es el registro.

«Publicar» es cualquiera de estas cinco: `BITÁCORA.md`, el `reason` de un `xfail` o un
`skip`, un comentario del código, un `NOTAS.md`, o un texto que se vea en la interfaz.

**Si un número no tiene fila aquí, no se publica: se escribe «no medido».**

> **Por qué existe este archivo.** La noche del 14-09-2026 se publicó un `xfail` que
> decía `lut_reproducible = 0.851` y `R² = 0.076`. Los dos estaban medidos **sobre un
> montaje distinto del que usaba el test**. Los reales eran `0.7319` y `0.2887`, y no era
> un error de precisión: **cambiaba el diagnóstico**. Lo cazó una auditoría independiente
> al día siguiente. Ver `AUDITORIA-DIA2.md`, caso 4.

---

## Antes de nada: los comandos de este archivo están verificados

Todos se ejecutaron el **16-09-2026** y todos seleccionan tests reales que pasan. Se
copian y se pegan tal cual desde la raíz del repo. Si alguno deja de funcionar, la fila
deja de valer: **una cifra cuyo comando no corre es una cifra sin procedencia.**

---

## Cómo leer una fila

**El montaje es tan importante como el valor.** Dos cifras correctas medidas sobre
montajes distintos no son comparables, y confundirlas es exactamente lo que pasó.

Por eso muchas filas están **por duplicado**: el montaje del repo (`tests/test_entregables.py`)
y el montaje independiente (`tests/medicion/`, escrito el día 3 por un agente que no
escribió el código y con ΔE2000 de `colour-science`, no del repo). **Las dos son ciertas.**

---

## 1 · Las cuatro cifras de titular

> **Cambio del día 4.** Hasta el día 3 el titular de T1 y T3 era **la media**. Pero el
> criterio lo suspende **el máximo** (T1) y **el peor par** (T3), y la media es la cifra
> holgada. **Desde hoy el titular es la que decide**, con su margen al límite al lado. La
> media se sigue dando, detrás. Las filas son las mismas de antes, con los mismos comandos
> verificados: sólo cambia el orden y se añade el margen.

### Los titulares: la cifra que decide, y cuánto le falta para suspender

| Criterio | Cifra que decide | Límite | **Margen** | Montaje | Comando | Fecha |
|---|---|---|---|---|---|---|
| **T1** ingeniería inversa | **ΔE2000 máximo 2.8867** | < 3.0 | **0.11** | independiente: escena 720×405 semilla 20260915, ΔE de `colour` | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T1` | 15-09 |
| T1, montaje del repo | ΔE2000 máximo 1.7409 | < 3.0 | 1.26 | repo: retrato 640×360 piel 2, CDL+LUT conocidos | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T1` | 15-09 |
| **T3** igualado de cámaras | **ΔE2000 peor par 1.906** | < 2.0 | **0.094** | independiente: escena propia, desviaciones más suaves, ΔE de `colour` | `.venv/bin/python -m pytest tests/medicion/test_t3.py -s` | 15-09 |
| T3, montaje del repo | ΔE2000 peor par 0.981 | < 2.0 | 1.02 | repo: 4 cámaras desde el retrato | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T3` | 15-09 |
| **T2** lo que no es un LUT | no dice 100% LUT **y** señala la zona | — | cualitativo | repo: viñeta 0.45 + ventana (440,30,170,120), sobre la imagen codificada | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T2` | 15-09 |
| T2, montaje independiente | **la zona señalada NO cae en la ventana** (solape 0.0000) | — | **no cumple** | viñeta 0.42 + ventana (96,250,190,110), **en luz lineal** | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T2` | 15-09 |
| **T4** QC de LUT | 3 de 3 cazados, 0 avisos sobre la identidad | 3/3 y 0 | exacto | 3 LUT fabricados; `LUT3D.identity(n)` en 17³, 33³, 65³ | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T4` | 15-09 |

**Leer así:** T1 y T3 cumplen en los dos montajes, pero **en el montaje independiente
pasan por un 4-5%**, sobre material sintético limpio. Con ruido, compresión o un plano
distinto del que se extrajo, no hay garantía de que sigan cumpliendo. T5 (día 4) mide
justo eso.

### Detrás: las medias y el resto de cifras de los mismos montajes

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| T1 ΔE2000 medio, zona cubierta · repo | 0.1415 | repo | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T1` | 15-09 |
| T1 ΔE2000 medio · independiente | 0.1687 | independiente | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T1` | 15-09 |
| T2 fracción reproducible en un `.cube` · repo | 0.7002 | repo | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T2` | 15-09 |
| T2 solape de la zona señalada · repo | 0.9941 | repo | ídem | 15-09 |
| T2 fracción reproducible · independiente | 0.90836 | independiente | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T2` | 15-09 |
| T3 ΔE2000 medio entre cámaras, antes → después · repo | 17.674 → 0.661 | repo | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T3` | 15-09 |
| T3 antes → después · independiente | 15.499 → 1.085 | independiente | `.venv/bin/python -m pytest tests/medicion/test_t3.py -s` | 15-09 |

### La cifra que faltaba en la tabla de titulares

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| **Cobertura del cubo, un solo plano** | **165 de 35.937 = 0.46%** | repo, LUT 33³ | `.venv/bin/python -m pytest tests/test_entregables.py -s -k cobertura` | 15-09 |
| Cobertura · montaje independiente | 264 de 35.937 = 0.73% | escena propia | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k cobertura` | 15-09 |

**O sea que el 99.5% del `.cube` que se entrega está inventado por el relleno de huecos.**
No estaba en ningún titular y es lo primero que habría que decir al entregar un LUT.

---

## 2 · Validación de la métrica

Sin esto, las cifras de arriba no valdrían: si el ΔE2000 del repo estuviera mal, sus
tests y sus medidas fallarían igual y saldría verde.

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| ΔE2000 del repo vs. `colour-science` | error máx **1.6e-13** | imágenes reales del arnés independiente | `.venv/bin/python -m pytest tests/medicion/ -s -k metrica` | 15-09 |
| Camino de conversión de espacios, repo vs. `colour` | error máx **2.2e-13** en L\*a\*b\* | ídem | ídem | 15-09 |
| ΔE2000 contra los pares de Sharma, Wu y Dalal (2005) | error máx **4.9499e-05** | los 34 pares publicados | ídem | 15-09 |
| Las 6 curvas de cámara vs. `colour-science` | **0.0e+00** en todo el dominio, de −2.88 a +11.5 | 4.011 muestras | `.venv/bin/python -m pytest tests/revision/test_ola1_color.py -k colour` | 15-09 |

El error de Sharma es el redondeo a 4 decimales de la tabla publicada, no un desvío.

---

## 3 · Ingeniería inversa

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| Ida y vuelta de un plano **sin gradar** | **0.3122** medio · **6.3554** máx | mismo plano contra sí mismo; el CDL sale identidad exacta | `.venv/bin/python -m pytest tests/test_entregables.py -s -k identidad` | 15-09 |
| R² radial del campo de **ganancia**, viñeta 0.55 | **0.879** | retrato + viñeta sola | `.venv/bin/python -m pytest tests/test_reverse_espacial.py -s -k tabla` | 15-09 |
| Correlación con el radio, viñeta 0.55 | **−0.875** | ídem — el signo distingue viñeta de ventana | ídem | 15-09 |
| R² radial del campo de **ΔE2000**, viñeta 0.55 | 0.2887 | ídem — **el campo que NO servía** | ídem | 15-09 |
| Error del centro de viñeta estimado | 22.4 px (viñeta 0.55) · 17.8 px (0.35) | sobre 640×360 | ídem | 15-09 |
| IoU de la ventana detectada | **0.977** (sola) · 0.909 (bajo viñeta) | caja real (440,30,170,120) | ídem | 15-09 |

### El límite abierto de T2 (§4 de `MEDICION-INDEPENDIENTE.md`)

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| Magnitud de la zona declarada **principal** | **12.725531826505737** | montaje independiente, viñeta y ventana **en luz lineal** | `.venv/bin/python -m pytest "tests/medicion/test_t1_t2.py::test_T2_la_zona_senalada_cae_donde_esta_mi_ventana" -rx` | 15-09 |
| Magnitud de la zona **correcta** | **11.377186278350779** | ídem | ídem | 15-09 |
| Margen entre las dos | **11.85%** | ídem — no es un empate | ídem | 15-09 |
| Píxeles de mayor residuo dentro de la ventana real | **93.6%** de los 500 mayores | ídem — **el detector la ve; falla la caja** | ídem | 15-09 |
| Solape con la convención del repo (imagen codificada) | **0.8053** — pasaría | misma viñeta y ventana, aplicadas como las aplica el repo | ídem | 15-09 |

---

## 4 · Color y emparejamiento

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| Recuperación de un CDL conocido, con parejas | error de parámetro **4.4e-16** | 7 CDL distintos sobre el retrato | `.venv/bin/python -m pytest tests/test_matching_cdl.py -s` | 15-09 |
| Recuperación **sin** parejas, con `power ≠ 1` | error **0.137** | listas de distinta longitud, vía MKL | ídem | 15-09 |
| Huella: invariancia al grado | **0.9967** | retrato vs. retrato + CDL fuerte + LUT de look | `.venv/bin/python -m pytest tests/test_analysis_huella.py -s` | 15-09 |
| Huella: separación entre escenas | **0.0000** | retrato vs. exterior al sol | ídem | 15-09 |
| Hueco del umbral de huella | peor comparable **0.7561** · mejor no comparable **0.2193** | 30 pares medidos | `.venv/bin/python -m pytest tests/test_matching_huella.py -s -k hueco` | 15-09 |
| Máscara de piel: exhaustividad, tono más claro → más oscuro | 0.967 · 1.000 · 1.000 · 1.000 · 0.992 · **0.900** | los 6 tonos del generador | `.venv/bin/python -m pytest tests/test_color_perceptual.py -s -k piel` | 15-09 |
| Falsos positivos de piel sobre el exterior | 1.75% | el camino de tierra, que es color piel | ídem | 15-09 |
| Error de mapear sRGB a Rec.709 | **+57%** en un gris de 0.045 lineal | por eso existe el espacio `srgb` | `.venv/bin/python -m pytest tests/test_color_spaces.py -s -k srgb` | 15-09 |
| `delta_e2000(negro exacto, 1e-30)` antes del arreglo | **8.5679** | bug de `L* = −16` en el cero | `git show a01209c` | 15-09 |
| ídem después | **0.0** | `.venv/bin/python -m pytest tests/test_color_perceptual.py -k negro` | 15-09 |

---

## 5 · LUT y formatos

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| Desviación de remuestrear 33³ → 65³ | **5.7e-08** (0.0000146 sobre 255) | 200.000 colores aleatorios, 4 LUT | `.venv/bin/python -m pytest tests/test_io_remuestreo.py -s` | 15-09 |
| Tamaño del fichero, 33³ → 65³ | **0.93 MB → 7.07 MB** (×7.6) | ídem | ídem | 15-09 |
| Desviación de bajar 33³ → 17³ | **0.065** (16.6 sobre 255) | gamma de salida | ídem | 15-09 |
| Desvío de una gamma `x**(1/2.2)` respecto a su curva | **11/255** incluso con 65 puntos | por eso el QC avisa y es verdad | `.venv/bin/python -m pytest tests/test_io_qc.py -s -k gamma` | 15-09 |

**Por qué 65³ no añade información:** 65 = 2·33 − 1, así que los puntos nuevos caen justo
sobre los viejos y sus puntos medios. No es «casi el mismo LUT»: es el mismo, hasta el
redondeo del `float32`.

---

## 6 · Umbrales sin medida detrás

**Esto también es una cifra: la de los números que nadie ha justificado nunca.** Están
todos en `core/umbrales.py`, cada uno marcado como «no se sabe» en vez de con una
justificación inventada.

| Constante | Valor | Estado |
|---|---|---|
| **`CONFIDENCE_ALTA`** | **0.75** | **no medido** — y es el veredicto más visible de la app |
| **`CONFIDENCE_MEDIA`** | **0.45** | **no medido** — ídem |
| `UMBRAL_REPRODUCIBLE_PURO` | 0.95 | no medido |
| `UMBRAL_MOVIMIENTO_NULO` | 0.05 ΔE2000 | no medido |
| `UMBRAL_COBERTURA_BAJA` | 0.005 | no medido |
| `MUESTRAS_MINIMAS_CELDA` | 4 | no medido |
| `MUESTRAS_MINIMAS_CDL` | 64 | no medido |
| `AREA_MINIMA_HOTSPOT` | 0.002 | no medido |
| `UMBRAL_NEUTRA_TOTAL` | 0.999 | no medido |
| `UMBRAL_SUBNOTA_EXPLICABLE` | 0.85 | no medido |
| `UMBRAL_CROMA_EXPLICABLE` / `_PERFIL_` | 0.35 / 0.12 | no medido |

Y en sus módulos, también sin justificación: `LAMBDA_SUAVIDAD` 0.25, `CORONAS` 24,
`_BARRIDOS_EN_BUCLE` 10, `MARGEN_MEJORA` 0.01, `MAX_PIXELES_CDL` 60.000.

**Una discrepancia sin resolver:** el pico del grano más fuerte medido lo da
`core/reverse/diagnostico.py` como **0.045** y `core/reverse/NOTAS.md` §6.3 como
**0.0135**. Ninguna de las dos está verificada. Es justo la clase de cosa que este
archivo existe para no dejar pasar.

---

## 7 · Interfaz

Todas medidas el 16-09-2026, después de arreglar la escala tipográfica.

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| **Anchura mínima real de la ventana** | **973 × 651** | `minimumSizeHint()` de la ventana construida | `.venv/bin/python -m pytest tests/test_gui_texto.py -k anchura_minima` | 16-09 |
| ídem, el día 2 | 985 × 643 | antes de arreglar la tipografía | `git show v0.2.0:gui/NOTAS.md` | 15-09 |
| Lo que pediría con el `font-size` aplanado repuesto | 1028 × 655 | mismo árbol, reponiendo la línea del bug | **sin comando**: no hay test que lo fije. Medido por el agente de GUI, escrito en `gui/NOTAS.md:117`. Ver el aviso de abajo | 16-09 |
| Widgets que se pintan con el tamaño de letra que piden | **todos** | recorre la ventana entera y compara lo pedido con lo pintado | `.venv/bin/python -m pytest tests/test_gui_identidad.py -k tamano_de_letra` | 16-09 |
| Widgets que pedían fuente y NO la conseguían, antes | 41 de 96 | mismo barrido sobre el árbol de `v0.2.0` | **sin comando**: el árbol de `v0.2.0` ya no está montado. Cifra del informe del agente de GUI. Ver el aviso de abajo | 15-09 |
| Columna CLIP a la anchura mínima | 56 px → **124 px** | 200 clips | `.venv/bin/python -m pytest tests/test_gui_texto.py -k columna` | 16-09 |
| Columna CLIP a 1024 / 1440 px | 81 → **175** · 361 → **455** | ídem | ídem | 16-09 |
| Ancho total de las cinco columnas fijas | 439 px → **345 px** | `#` 42 · ΔE antes 63 · ΔE después 67 · confianza 124 · aviso 49 | ídem | 16-09 |
| Tracking de los rótulos en mayúsculas | 0.1594em y 0.1591em | dentro del 0.15–0.18 de la identidad | `.venv/bin/python -m pytest tests/test_gui_identidad.py -k tracking` | 15-09 |

> **AVISO, y es el motivo de que este archivo exista.** Dos filas de esta tabla —el
> «1028 × 655» y el «41 de 96»— **no tienen comando que las reproduzca**. Las midió el
> agente de GUI por su cuenta y están escritas en su informe y en `gui/NOTAS.md`, pero
> nadie más las ha podido comprobar. Según la regla de `CONTRATOS.md` **no deberían
> publicarse como medidas**, y aquí están marcadas como lo que son. Las dejo porque las
> dos describen el estado *anterior* al arreglo, que ya no se puede montar sin deshacerlo;
> pero si alguien las cita, que cite también esta línea.
>
> Lo encontré al verificar los comandos de este archivo uno a uno, que es exactamente
> para lo que sirve hacerlo.

### Dos cifras de la interfaz que están medidas y NO arregladas

| Cifra | Valor | Por qué no se arregla |
|---|---|---|
| `INSIGNIA_ANCHO` | **108 px**, y «MEDIA 100%» necesita **115** | La columna CONFIANZA mide `INSIGNIA_ANCHO + 16` y es la más ancha de las fijas: subirla **subiría la anchura mínima**, que es justo lo que no tocaba. Hoy no se ve porque un 100% siempre sale `alta`, y «ALTA» es la palabra más corta. |
| Tracking de las cabeceras de tabla | **0** | Límite de Qt, comprobado por dos vías: `setFont()` sobre el `QHeaderView` lo borra Qt en el siguiente `polish`, y `headerData(…, FontRole)` no cambia ni un píxel. Haría falta un `QHeaderView` propio que se pinte las secciones. |

---

## 8 · T5 — el LUT extraído de un plano, aplicado a otro plano (día 4)

**El caso de uso real**, que no se había medido: extraer el look de un plano y aplicarlo a
los demás del mismo trabajo. Medido por un agente independiente contra la copia congelada
de `v0.3.0`, con escenas propias y ΔE2000 de `colour-science`. Informe completo en
[`MEDICION-T5.md`](MEDICION-T5.md).

**El comando es el mismo para todas las filas**, y **hay que ejecutarlo desde la copia
congelada**, no desde la raíz (si no, mide el repo vivo y los tests se saltan diciendo por
qué):

```bash
git worktree add --detach .snapshots/v0.3.0 v0.3.0   # sólo si no existe
cd .snapshots/v0.3.0 && PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest ../../tests/fuera_de_plano -s -p no:cacheprovider --import-mode=importlib --noconftest -rxXs
```

Cada fila dice qué línea de la salida mirar. **Verificadas el 16-09** re-ejecutando el
comando: las cifras marcadas con ✔ salen idénticas.

| Cifra | Valor | Montaje | Línea de la salida | Fecha |
|---|---|---|---|---|
| **T5 máximo en B, plano normal (A2, 0.41% del cubo)** | **3.593 – 5.921; 0 de 12 bajo 3.0** ✔ | escena A2 contra 6 escenas B × 2 looks | `[T5 AB …]` con `A2 interior`, campo `todo_max` | 16-09 |
| T5 medio en B, plano normal | 0.338 – 1.685 | ídem | ídem, `todo_medio` | 16-09 |
| T5 p95 en B, plano normal | 0.912 – 4.010 | ídem | ídem, `todo_p95` | 16-09 |
| T5 pares A→B con máximo bajo 3.0 | **5 de 72** (11 de 72 quitando L\* > 100) | 6 A × 6 B × 2 looks | `[T5 nivel …]` | 16-09 |
| T5 corte de cobertura para máximo < 3.0 | **no existe** en 0.15% – 4.8% | ídem | `[T5 corte ambos looks … todo_max]` | 16-09 |
| T5 corte de fracción de B cubierta, para p95 < 3.0 | ≥ 0.8767 | ídem | `[T5 corte ambos looks … todo_p95]` | 16-09 |
| Correlación (Spearman) del máximo en B con la cobertura de A | **+0.780** — al revés de lo esperado | ídem | `[T5 spearman todo_max]` | 16-09 |
| Peor píxel en celda cubierta / a medias / inventada | 46 / 7 / 19 de 72 | ídem | `[T5 peor pixel todo]` | 16-09 |
| **T1 A→A máximo en escena rica (A5)** | **4.00095 / 3.85405 — NO cumple < 3.0** ✔ | escena A5, look global / con secundarias | `[T5 ref … A5 muy variada]`, `todo_max` | 16-09 |
| Power azul del CDL extraído, frente al conocido 1.02 | 1.193 – 1.466 | 12 extracciones | `[T5 cdl …]` | 16-09 |

**Lo que dicen juntas:** con un plano, el LUT **no sirve** fuera de su plano; **más
cobertura no arregla el máximo**, porque los peores errores vienen de nodos del cubo con
pocas muestras, no de celdas vacías; y el **titular de T1 «cumple» no es general**: con
una escena rica falla en su propio plano.

---

## 9 · T5 con el modo por lote (día 4, segunda vuelta)

Medido por el mismo agente independiente, contra **otra** copia congelada: `.snapshots/dia4-lote`
(commit `a90b59c`, la que ya tiene `invertir_grado_lote`). 640×360, ΔE2000 de `colour`.

```bash
git worktree add --detach .snapshots/dia4-lote a90b59c   # sólo si no existe
cd .snapshots/dia4-lote && PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest \
  ../../tests/fuera_de_plano/test_t5_lote.py -s -p no:cacheprovider --import-mode=importlib \
  --noconftest -rxXs -k <K>
```

**Cómo leer las filas:** «planos de fuera» son 12 planos **del mismo trabajo que no entraron
en el lote** (líneas `F00`–`F11` de la salida). Los planos `X00`–`X03` son **ajenos** al
trabajo y van aparte: mezclarlos cambia la cifra —me pasó a mí al verificarla, y el peor
máximo saltaba de 1.67 a 20.96—.

✔ = re-ejecutado el comando y salen idénticas.

| Cifra | Valor | `-k` | Fecha |
|---|---|---|---|
| **Lote de 3 planos, `suma_w2`, look global: peor máximo en planos de fuera** | **1.66778 — 12 de 12 bajo 3.0** ✔ | `t5l_global` | 16-09 |
| Lote de 3, `suma_w2`, look con secundarias | 1.9516 — 12 de 12 | `t5l_secundarias` | 16-09 |
| Lote de 40, `suma_w2`, global | **0.759774** ✔ | `t5l_global` | 16-09 |
| Lote de 40, `suma_w`, global | **2.90825 — 12 de 12, a 0.09 del límite** ✔ | `t5l_global` | 16-09 |
| Lote de 3, `suma_w`, global | 9.42269 — 7 de 12 ✔ | `t5l_global` | 16-09 |
| **Look de secundarias estrechas, lote de 40, `suma_w2`** | **4.1987 — 10 de 12. Falta 1.20. Falla en celdas CUBIERTAS** | `t5l_estrechas` | 16-09 |
| Planos ajenos al trabajo, lote de 40, peor máximo | 12.70 – 22.09 según look | los tres | 16-09 |
| Cobertura con 1 / 3 / 5 / 10 / 20 / 40 planos, 640×360 | 0.431 / 0.843 / 0.946 / 1.222 / 1.486 / **1.812 %** | `t5l_secundarias` | 16-09 |
| Un solo plano, montaje de la mañana: pares bajo 3.0, `suma_w` → `suma_w2` | global **1 → 21 de 36** · secundarias 4 → 15 de 36 | `t5l_manana` | 16-09 |
| Un solo plano, secundarias estrechas, A→A por encima de 3.0 | `suma_w` 4 de 11 · `suma_w2` **1 de 11** | `t5l_un_plano` | 16-09 |

**Lo que dicen juntas:** el lote **sí** resuelve el caso de uso **con looks suaves, en planos
del mismo trabajo, y con `suma_w2`** (que es el defecto del lote). No lo resuelve con
secundarias estrechas —un LUT no puede con ellas, tenga los datos que tenga— ni con planos
de otro trabajo.

**Cifra del autor del lote que NO se reproduce:** él midió que `suma_w2` empeora planos
sueltos con secundarias estrechas (7 de 11 por encima de 3.0, frente a 2). Con otro look
de secundarias estrechas sale al revés (1 de 11 frente a 4). No es la misma escena, así que
no se sabe si su cifra está mal: se sabe que **no generaliza**. No se publica como hecho.

---

## 10 · Detector espacial y ventana (día 4)

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| Zona principal en el montaje independiente | **la ventana** `(89,301,251,104)` — antes era la esquina | viñeta 0.42 + ventana en luz lineal | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T2` | 16-09 |
| **Solape de su caja con la ventana real** | **0.4294 — no cumple 0.80** | ídem | ídem | 16-09 |
| T1 y T2 del repo tras el cambio | idénticos: 0.1415 / 1.7409 y 0.7002 / 0.9941 | repo | `.venv/bin/python -m pytest tests/test_entregables.py -s -k "T1 or T2"` | 16-09 |

---

## 11 · Interfaz (actualiza §7)

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| **Tamaño mínimo real de la ventana** | **973 × 727** | medido **a 973 px de ancho** en las cuatro pantallas | `.venv/bin/python -m pytest tests/test_gui_texto.py -k anchura_minima_real` | 16-09 |
| ídem, midiendo `minimumSizeHint()` en ventana ancha | 973 × 713 — **no vale**: a 973 px la leyenda del mapa ocupa dos líneas | — | — | 16-09 |

---

## 12 · Calibración de la confianza (día 4)

Medido por un agente independiente: 3.600 casos sintéticos con verdad conocida (2.400 de
ingeniería inversa, 720 de igualado), 320×180 comprobado contra 640×360, ΔE2000 de `colour`.
Informe en [`CALIBRACION-CONFIANZA.md`](CALIBRACION-CONFIANZA.md).

```bash
.venv/bin/python -m pytest tests/calibracion -q -rx          # tests
.venv/bin/python -m tests.calibracion.analizar               # tablas; filtrar con grep
```

✔ = re-ejecutado el análisis el 16-09 y sale idéntico.

| Cifra | Valor | Línea de la salida | Fecha |
|---|---|---|---|
| **Valores distintos de la nota de `reverse`, 33³, fuera de plano, sin compresión** | **1 en 500 casos — la nota es constante** ✔ | `[CAL spearman reverse 33^3 fuera \| compresion=0.0]` | 16-09 |
| Máximo fuera de plano en esos mismos casos | 0.50 – 39.26 | `CALIBRACION-CONFIANZA.md` §3 | 16-09 |
| Spearman nota–máximo, `reverse` 17³ fuera de plano, todo junto | −0.290 ✔ (y −0.078 sin compresión: el todo junto es paradoja de Simpson) | `[CAL spearman reverse 17^3 fuera …]` | 16-09 |
| Fracción que cumple máximo < 3.0 entre los «alta» (nota ≥ 0.75), `reverse` 17³ fuera | **4.2%**, IC95 2.4 – 6.0% ✔ | `[CAL umbral reverse 17^3 fuera] t=0.75` | 16-09 |
| Mejor fracción que cumple con cualquier umbral, `reverse` 33³ fuera | 17.0%, IC95 13.8 – 20.6% | `[CAL umbral reverse 33^3 fuera]` | 16-09 |
| «alta» en su propio plano, rejilla 17³, que pasan de 3.0 | 165 de 171 (96.5%) | `CALIBRACION-CONFIANZA.md` §4 | 16-09 |
| Igualado de clips, misma escena: AUC de la nota para predecir que cumple | 0.399, IC95 0.233 – 0.587 | `CALIBRACION-CONFIANZA.md` §2 | 16-09 |
| **Umbrales resultantes** | **ninguno: 0.75 y 0.45 se quedan**, porque ningún corte llega al 95% | — | 16-09 |

**Sin verificar, y por eso no va como cifra:** que `make_clip(codec="h264")` del generador
codifica con matriz BT.601 y etiqueta BT.709 (error 0.027 frente a 0.0046). Lo midió a mano el
agente de calibración; no hay test que lo fije.

---

## 13 · Calibración de `FeaturesDestino` (día 5, tarea 2)

Medido por un agente independiente de quien escribió `core/reverse/confianza_destino.py`:
2.040 casos sintéticos con verdad conocida (1.440 de extracción de un solo plano, 600 de
extracción por lote con `planos_acumulados` de 1 a 8), 320×180, ΔE2000 de `colour`. Informe en
[`CALIBRACION-CONFIANZA-DESTINO.md`](CALIBRACION-CONFIANZA-DESTINO.md).

```bash
.venv/bin/python -m pytest tests/test_reverse_confianza_destino.py -q   # tests de aritmética
.venv/bin/python -m tests.calibracion_destino.analizar                  # tablas; filtrar con grep
```

| Cifra | Valor | Línea de la salida | Fecha |
|---|---|---|---|
| **Veredicto: ¿las señales predicen el error?** | **Sí, algo — mucho más que la nota actual — pero ninguna combinación limpia llega al 95%** | `CALIBRACION-CONFIANZA-DESTINO.md` veredicto | 16-09 |
| AUC de `cobertura_destino` dentro de cada una de las 8 clases de material | **0.726 – 0.966**, sin una sola inversión de signo (a diferencia de la nota actual, que daba 0.500 exacto) | `[CALD auc_clase cobertura_destino]` | 16-09 |
| Spearman `cobertura_destino`–máximo, `simple` fuera de plano, todo junto | −0.309, y de −0.403 a −0.460 dentro de cada clase (más fuerte dentro que fuera: no es paradoja de Simpson) | `[CALD spearman cobertura_destino] simple, fuera de plano, TODO JUNTO` y `… simple \|` | 16-09 |
| Mejor % que cumple con cualquier corte de `cobertura_destino`, dentro de la mejor clase (33³, sin comprimir, con recorte) | **82.4%** (n=17, cobertura ≥ 0.975) | `[CALD umbral_clase cobertura_destino]` \| `grep "tam=33 compresion=0 recorte=1"` | 16-09 |
| Mejor % que cumple, TODAS las clases mezcladas | 74.1% (n=27, nota combinada ≥ 0.9997) | `[CALD umbral nota] todo, fuera de plano, cobertura+muestras_p10 rampa=1000/8` | 16-09 |
| `muestras_p10_zona` entre 1 y 8: peor que 0 (celda vacía, puro relleno) | cumple 0.0% frente a 2.5% con 0 muestras — se repite el hallazgo del día 4 | `[CALD tramos_bajos muestras_p10_zona] simple, fuera de plano, TODO JUNTO` | 16-09 |
| `variance_zona`, AUC global vs. signo dentro de la clase comprimida | AUC global 0.248 (peor que azar); ρ **se invierte** de +0.29/+0.54 (sin comprimir) a −0.32/−0.68 (comprimido) | `[CALD auc variance_zona]` y `[CALD spearman variance_zona] simple \|` | 16-09 |
| Única combinación que cruza el 95% (con `variance_zona`, DESCARTADA por el punto anterior) | t=0.95, cumple 100% (n=26) IC95=[1.000,1.000] | `[CALD umbral nota] todo, fuera de plano, cobertura+muestras_p10+variance (control)` | 16-09 |
| Spearman `planos_acumulados`–máximo (sólo bloque `lote`) | −0.140, IC95 [−0.248, −0.019] — real pero modesto | `[CALD rho_ic planos_acumulados]` | 16-09 |
| ΔE máximo mediana con 1 plano acumulado vs. 8 | 5.07 → 3.56 (cumple 27.0% → 46.0%) | `[CALD tramos planos_acumulados]` | 16-09 |
| «Alta» reusando `CONFIDENCE_ALTA = 0.75` para la nota candidata (sin `variance_zona`) | cumple **29.2%** de las veces — por eso no se conecta a `confidence_level()` | `[CALD umbral nota] todo, fuera de plano, cobertura+muestras_p10 rampa=200/4` fila `t=0.75` | 16-09 |
| **Decisión** | **No se conecta a la GUI ni a `core.matching.confianza`.** `confianza_destino.py`, `core/umbrales.py`, `core/matching/confianza.py` y `core/contracts.py` sin tocar | — | 16-09 |

---

## 14 · El formato `.drx`, con material real (día 6)

Diez `.drx` reales de Mario en `tests/powergrades_reales/` (solo lectura, no versionados).
Detalle completo, con lo confirmado y lo supuesto separado, en
[`core/io/FORMATO-DRX.md`](core/io/FORMATO-DRX.md). Comando de todas las filas:

```bash
.venv/bin/python -m pytest tests/test_io_drx.py -v -k reales
```

| Cifra | Valor | Montaje | Fecha |
|---|---|---|---|
| **¿Es XML plano, como suponían los foros?** | **Sí, confirmado en 10 de 10** — pero con nombres de etiqueta (`Gallery::GyStill`) que violan namespaces y que `ElementTree.fromstring()` rechaza | 10 archivos, `file(1)` + parseo con `expat` sin namespaces | 17-09 |
| Byte de cabecera de `<Body>` | `0x81` en **20 de 20** `<Body>` (2 por archivo) | ídem | 17-09 |
| ¿El resto de `<Body>` es un frame Zstandard válido? | **Sí, 20 de 20**, descomprime con `zstandard` | ídem | 17-09 |
| ¿El contenido descomprimido es protobuf válido (wire format)? | **Sí, 20 de 20**, sin ningún campo con `wire_type` desconocido | `core/io/drx_protobuf.py::parsear_mensaje` | 17-09 |
| Nodos por grado (`pClipFullVer`), los 10 archivos | 2, 2, 2, 3, 4, 4, 5, 5, 18, 22 | `core/io/FORMATO-DRX.md` §3.1 | 17-09 |
| Archivos con al menos 1 LUT referenciado por ruta de texto | **10 de 10** | ídem | 17-09 |
| Archivos con 2 LUTs en el mismo grado (conversión + look) | **2 de 10** (`_1.1.1`, `_1.2.1`) | ídem §3.2 | 17-09 |
| Índice de nodo: ¿1-based por clip? | **No en los 2 archivos de trabajo real** (`_1.38.1`, `_1.52.1`): índices 260-281 consecutivos, no 1-N — SUPUESTO que es un contador global de proyecto | ídem §3.1 | 17-09 |
| `pTrackVer`, nodos con contenido | **0 de 10** (todos plantilla vacía) | ídem §3.4 | 17-09 |
| **Avisador de dependencias contra `tests/luts_reales/`** | **9 de 10 archivos: todas las rutas encontradas por nombre.** El único faltante es un LUT de fábrica de Sony (`Sony/SLog3SGamut3.CineToLC-709.cube`), no un LUT propio de Mario | `core/io/FORMATO-DRX.md` §4 | 17-09 |

**Nada de esto estaba adivinado hasta hoy**: el `core/io/drx.py` del día 5 era, a
propósito, un inspector que no asumía nada. Estas diez filas son lo primero que se
confirma contra archivos reales.

---

## 15 · Capturas deterministas (día 6, tarea 5)

```bash
.venv/bin/python -m pytest tests/test_gui_capturas_deterministas.py -v -m ""
```

| Cifra | Valor | Montaje | Fecha |
|---|---|---|---|
| Diferencias entre 2 ejecuciones seguidas de `gui.capturas.generar()` | **0 de ~30 archivos**, comparado por SHA-256 | proceso único | 17-09 |
| Diferencias con 3 procesos `yes` saturando la CPU en paralelo | **0 de ~30** | misma máquina, con carga | 17-09 |
| Diferencias con 2 invocaciones de `generar()` corriendo EN PARALELO entre sí | **0 de 31** | dos procesos Python compitiendo por CPU de verdad | 17-09 |
| Píxeles distintos fuera del carril de navegación, en las 26 capturas del modo avanzado vs. el commit del día 5 | **0 de 26** — toda la diferencia cae dentro de `x < ANCHO_CARRIL` (el botón "Modo fácil" nuevo) | comparación con Pillow, `ImageChops.difference` | 17-09 |
| Conclusión | Ya era determinista: el "ruido" del día 5 era el botón "Modo fácil" añadido ese día, revertido por error sin comparar a nivel de píxel. No se tocó ni fuente ni antialiasing ni escala. Ver `gui/NOTAS.md` | — | 17-09 |

---

## 16 · Biblioteca de presets y bundle `.sidebcolor` de preset (día 6, tarea 4)

```bash
.venv/bin/python -m pytest tests/test_io_biblioteca.py -v -k reales
```

| Cifra | Valor | Montaje | Fecha |
|---|---|---|---|
| Presets sembrados desde `tests/luts_reales/` | **79** `.cube` recursivos | `sembrar_desde_carpeta` | 17-09 |
| Tamaños de rejilla encontrados | 17, 33 y 65 — los tres soportados | ídem | 17-09 |
| Ida y vuelta del `.cube` dentro de un bundle | **exacta, bit a bit** (`np.array_equal`) | `test_el_viaje_completo_con_un_lut_real` | 17-09 |
| Preset sembrado desde un `.drx` real con 2 LUTs (`_1.1.1.drx`) | look = `5 (-) BALI GREEN V2`, 1 dependencia declarada (`Sony/SLog3SGamut3.CineToLC-709.cube`) | `sembrar_desde_drx` | 17-09 |
| Aviso al abrir ese bundle en una "carpeta limpia" (otro equipo) | **1 aviso**, nombrando exactamente el LUT de conversión que no viaja | `test_bundle_desde_drx_real_avisa_al_abrir_en_otro_equipo` | 17-09 |

**El viaje probado de verdad** (punto 3 de la tarea 4): se crea el bundle en un
`tempfile.mkdtemp()` (una carpeta que no existía antes, "como si fuera otro Mac"), se
abre desde ahí sin ningún acceso a `tests/luts_reales/`, y el LUT que sale es
bit a bit idéntico al original. Con un preset que dependía de un segundo LUT no
incluido, el aviso aparece — no se aplica a medias en silencio.

---

## 17 · `qc_lut()` contra LUT reales (día 6)

Primera vez que el QC de `core/io/qc.py` —hasta hoy sólo probado contra los LUT
sintéticos de `core/io/lut_malos.py`— se pasa contra material real: 79 `.cube` de
Mario en `tests/luts_reales/` (carpeta ignorada por git, solo lectura, ~35 en la
carpeta raíz más subcarpetas de `Osmo D-Log LUTs/`, `Osmo D-Log M LUTs/` y
`SECRET SAUCE/`). El detalle completo, archivo por archivo, está en
[`tests/test_io_qc_reales.py`](tests/test_io_qc_reales.py) — el docstring del
módulo explica el criterio de clasificación conversión/look con el mismo detalle
que aquí.

```bash
.venv/bin/python -m pytest tests/test_io_qc_reales.py -q -rA   # 88 tests: 79 por archivo + 9 con cifras agregadas
```

**El tamaño de fichero supuesto en el encargo (~1,4 MB por archivo de 65³) no era
exacto**: medido en disco, los `.cube` de 33³ pesan 0,5–0,8 MB y los de 65³,
7,5–7,6 MB. La conclusión sí era la correcta — hay `.cube` de 65³ de verdad—, pero
por el tamaño de rejilla que declara cada fichero (`LUT_3D_SIZE`, leído con
`leer_cube`), no por el peso en disco.

| Cifra | Valor | Comando | Fecha |
|---|---|---|---|
| **Tamaño de rejilla de los 79 archivos** | **43 de 33³, 36 de 65³** — ninguno de 17³ | `test_tamanos_de_rejilla_del_material_de_hoy` | 17-09 |
| **¿`qc_lut()` lanza sobre alguno?** | **No, ninguno de los 79** | `test_qc_no_lanza_sobre_ningun_lut_real` (parametrizado ×79) | 17-09 |
| **Clasificación conversión / look** (criterio: chroma máxima en una rampa de gris de 17 puntos ≤ 0,015 → conversión; hueco medido real entre 0,0072 y 0,0264, factor 3,7) | **8 conversión, 71 look** | `test_clasificacion_conversion_son_estos_8_y_solo_estos` | 17-09 |
| **¿Se repite con material real el patrón «banding esperable en LUT de conversión» del día 3?** | **Sí: los 8 LUT de conversión disparan banding.** Y también los 71 «look» — el aviso es prácticamente universal en material real, lo que refuerza que siga sin bloquear | `test_los_8_lut_de_conversion_disparan_banding` | 17-09 |
| **De los escalones de banding en los 8 LUT de conversión, ¿cuántos están pegados al negro (sombras) y cuántos no (medios)?** | **50 en sombras, 1182 en medios (96%)** — lo CONTRARIO de lo que el texto viejo de `EXPLICACION_MEDIOS` daba a entender (que fuera de sombras era lo raro) | `test_en_los_lut_de_conversion_la_mayoria_del_banding_esta_en_medios_no_en_sombras` | 17-09 |
| Ejemplo concreto: `DJI Mavic 4 Pro D-Log to Rec.709 V1.cube`, 130 escalones de banding | **los 130 en medios, 0 en sombras** | `test_dji_mavic_4_pro_no_tiene_ni_un_escalon_en_sombras` | 17-09 |
| **¿Algún LUT real con gamut fuera de rango, NaN/infinito o plano?** | **Ninguno de los 79** — lo único que sale limpio del todo | `test_ningun_lut_real_tiene_gamut_fuera_ni_nan_ni_esta_plano` | 17-09 |
| **¿Algún LUT real no monótono?** | **76 de 79**, incluidos los 8 manuales de fábrica (DJI, GPLOG). En `core/io/qc.py`, `no_monotonia` es un **ERROR**, no un aviso | `test_no_monotonia_dispara_en_la_mayoria_del_material_real` | 17-09 |
| Peor caída de monotonía de todo el material | **−0,230** (23% del recorrido 0..1), en las seis variantes de `SECRET SAUCE/A4 MONITOR LUTs V2/SONY Slog3 Monitor LUTs V2/…` | `test_los_peores_no_monotonos_son_estos_seis_archivos_sony` | 17-09 |
| Caída de monotonía en un manual de fábrica (no un «look»): `DJI Mavic 4 Pro D-Log to Rec.709 V1.cube` | **−0,04249** (~11/255), en 12 celdas — cien veces mayor que el ruido de redondeo de los 6 decimales del fichero (~1e-6) | `test_dji_mavic_4_pro_tiene_una_caida_de_verdad_no_ruido_de_redondeo` | 17-09 |

**Lo que esto cambió en `core/io/qc.py`:** el texto de `EXPLICACION_MEDIOS` (el
aviso de banding cuando el escalón NO está pegado al negro). Antes daba a entender
que estar fuera de sombras era señal de que algo iba mal; con material real de
conversión de espacio de color eso resultó ser lo NORMAL (96% de los escalones),
no la excepción. Cambio de **texto únicamente**: `UMBRAL_BANDING`,
`SALTO_MINIMO_BANDING` y `UMBRAL_SOMBRAS` no se han tocado, y siguen marcando
exactamente las mismas celdas que marcaban ayer (`EXPLICACION_SOMBRAS`, que ya
decía lo correcto, tampoco se ha tocado).

**Lo que esto NO cambió, y queda pendiente de una decisión que no es de hoy:**
`no_monotonia` dispara en 76 de los 79 archivos reales, con caídas de hasta 0,230
—no ruido de redondeo—, y es un **ERROR** en el diseño actual del QC, no un aviso.
Ni `TOL_MONOTONIA` ni el detector se han tocado: no estaba en el encargo de hoy y
no soy quien debe arbitrar si el criterio está mal o si son defectos de verdad en
esos LUT. Se deja medido, con nombre de archivo, para que se decida aparte. Ver
`BITACORA.md`, entrada del día 6.

---

## 18 · Orden de triaje del paso 5 (día 6): ranking, no calibración

`CALIBRACION-CONFIANZA-DESTINO.md` (día 5) midió que `FeaturesDestino` no llega al 95%
que hacía falta para CERTIFICAR. Mario decidió que el paso 5 del modo fácil no necesita
certificar, necesita ORDENAR: de una lista de candidatos, enseñar primero los que más
conviene mirar. Esto **no es una calibración nueva**: reutiliza las 1.700 filas "fuera de
plano" que ya midió el día 5 (`tests/calibracion_destino/datos/simple_000_120.csv` +
`lote_000_100.csv`, sin generar material nuevo) y las mide como un RANKING — precisión@5
y precisión@10 sobre lotes simulados de 20 candidatos, no como un umbral de "alta".

Montaje: cada fila "fuera de plano" es un candidato (un plano de destino con su
`FeaturesDestino` y su clase de material real: rejilla × compresión × recorte). Se
particiona el conjunto en lotes de 20 (20 particiones aleatorias distintas, semilla fija
— 1.700 lotes en total), y dentro de cada lote se compara el orden que da cada variante
contra el orden de verdad (ΔE2000 máximo real, de peor a mejor).

```bash
.venv/bin/python -m tests.calibracion_destino.ordenar               # tablas; filtrar con grep
.venv/bin/python -m tests.calibracion_destino.ordenar | grep "CALD orden"
.venv/bin/python -m pytest tests/test_reverse_orden_repaso.py -q    # aritmética del orden, a mano
```

| Cifra | Valor | Línea de la salida | Fecha |
|---|---|---|---|
| **Precisión@5 / @10, orden al azar (referencia)** | 0.250 / 0.500 | `[CALD orden baseline]` | 17-09 |
| **Precisión@5 / @10, orden INGENUO** (mismas señales, sin normalizar por clase) | 0.373 (±0.185) / 0.609 (±0.110) | `[CALD orden precision] ingenuo` | 17-09 |
| **Precisión@5 / @10, orden CALIBRADO por clase, informado** (compresión y recorte exactos, como los conoce el arnés de calibración) | **0.400 (±0.188) / 0.623 (±0.110)** | `[CALD orden precision] calibrado_informado` | 17-09 |
| **Precisión@5 / @10, orden CALIBRADO por clase, desconocido** (sólo `tam_rejilla` — el escenario realista de producción, ver `CONTRATOS.md`/informe final) | **0.400 (±0.185) / 0.629 (±0.108)** — igual o mejor que el "informado" | `[CALD orden precision] calibrado_desconocido` | 17-09 |
| Comparación PAREADA (mismos 1.700 lotes), calibrado_informado vs. ingenuo, precisión@5 | calibrado gana 451 lotes (26.5%), ingenuo gana 267 (15.7%), empate 982 — diferencia media +0.0261, no es ruido de agregado | `[CALD orden pareado] calibrado_informado vs ingenuo en precision@5]` | 17-09 |
| Comparación PAREADA, calibrado_informado vs. ingenuo, precisión@10 | calibrado gana 457 (26.9%), ingenuo gana 259 (15.2%), empate 984 — diferencia media +0.0140 | `[CALD orden pareado] calibrado_informado vs ingenuo en precision@10]` | 17-09 |
| Comparación PAREADA, calibrado_desconocido vs. ingenuo, precisión@5 | calibrado gana 304 (17.9%), ingenuo gana 96 (5.6%), empate 1300 — diferencia media +0.0261 | `[CALD orden pareado] calibrado_desconocido vs ingenuo en precision@5]` | 17-09 |
| **Decisión** | **Funciona razonablemente para triaje** (muy por encima de azar; consistentemente mejor que el ingenuo, no sólo en el agregado) → se implementa de verdad: `core/reverse/orden_repaso.py` (nuevo), conectado a `gui/asistente_facil.py::ejecutar_repasar` (nuevo parámetro `candidatos_orden`, opcional; con la GUI de demo de hoy, que no extrae LUT por ingeniería inversa, cae al orden simple declarado — ver el módulo) | — | 17-09 |

**Por qué "desconocido" (sólo rejilla) no es peor que "informado" (clase exacta):** no
es un empate por casualidad — la rejilla explica la mayor parte de la diferencia de escala
entre clases (medias de `cobertura_destino` de 0.82 en 17³ frente a 0.74 en 33³, ver las
estadísticas completas en `core/reverse/orden_repaso.py`); compresión y recorte mueven la
media dentro de esa rejilla, pero menos que la rejilla misma. Es una buena noticia para
producción: `core.contracts.ClipRef` no lleva códec ni marca de recorte hoy (no se ha
añadido: ver el informe final del encargo), y la calibración "desconocida" no necesita esa
información para rendir igual.

**Qué NO se implementó:** `variance_zona` se probó y se descartó de la fórmula de
puntuación — su signo se invierte dentro de la clase comprimida incluso separando por
clase (`CALIBRACION-CONFIANZA-DESTINO.md` §3.2/§6.1), así que meterla habría empeorado el
orden justo en el material más difícil. No hizo falta medirlo aparte para este informe:
es la misma medición que ya hizo el día 5.
