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

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| **T1** ΔE2000 medio, zona cubierta | **0.1415** | repo: retrato 640×360 piel 2, CDL+LUT conocidos | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T1` | 15-09 |
| **T1** ΔE2000 máximo, zona cubierta | **1.7409** | ídem | ídem | 15-09 |
| T1 medio · montaje independiente | 0.1687 | escena 720×405 semilla 20260915, ΔE de `colour` | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T1` | 15-09 |
| **T1 máximo · montaje independiente** | **2.8867** | ídem — **a 0.11 del límite de 3.0** | ídem | 15-09 |
| **T2** fracción reproducible en un `.cube` | **0.7002** | repo: viñeta 0.45 + ventana (440,30,170,120) ganancia 1.6, **sobre la imagen codificada** | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T2` | 15-09 |
| **T2** solape de la zona señalada | **0.9941** | ídem | ídem | 15-09 |
| T2 reproducible · montaje independiente | 0.90836 | viñeta 0.42 + ventana (96,250,190,110), **en luz lineal** | `.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T2` | 15-09 |
| **T2 solape · montaje independiente** | **0.0000** | ídem — **no se reproduce**, ver §4 | ídem | 15-09 |
| **T3** ΔE2000 medio entre cámaras, antes | **17.674** | repo: 4 cámaras desde el retrato, desviaciones del repo | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T3` | 15-09 |
| **T3** ΔE2000 medio entre cámaras, después | **0.661** | ídem | ídem | 15-09 |
| T3 peor par suelto, después | 0.981 | ídem | ídem | 15-09 |
| T3 antes/después · independiente | 15.499 → 1.085 | escena propia, desviaciones más suaves, ΔE de `colour` | `.venv/bin/python -m pytest tests/medicion/test_t3.py -s` | 15-09 |
| **T3 peor par · independiente** | **1.906** | ídem — **a 0.094 del límite de 2.0** | ídem | 15-09 |
| **T4** LUT malos cazados | **3 de 3** | 3 LUT fabricados: no monótono, escalón, fuera de gamut | `.venv/bin/python -m pytest tests/test_entregables.py -s -k T4` | 15-09 |
| **T4** avisos sobre la identidad | **0**, en 17³, 33³ y 65³ | `LUT3D.identity(n)` | ídem | 15-09 |

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
