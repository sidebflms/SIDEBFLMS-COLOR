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
