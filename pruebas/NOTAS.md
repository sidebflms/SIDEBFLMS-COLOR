# NOTAS — `pruebas/`: la primera prueba con material real

Registro técnico para quien retome esto. Lo que tiene que leer Mario está en
[`COMO-HACER-LA-PRIMERA-PRUEBA.md`](COMO-HACER-LA-PRIMERA-PRUEBA.md).

**Todo lo de aquí está medido sobre material sintético.** Ninguna cifra ni ningún umbral
de esta carpeta se ha contrastado con material real: el script se ha escrito para eso y
todavía no se ha ejecutado sobre material real.

---

## 0 · Qué hay y quién escribe

| Archivo | Qué hace | ¿Escribe en disco? |
|---|---|---|
| `primera_real.py` | la línea de órdenes: simulacro, ejecución, informe | sólo a través de la guarda |
| `guarda.py` | **la única puerta de escritura**: sólo dentro de `pruebas/trabajo/`, nunca en un origen ni en `/Volumes`, nunca sobreescribe | sí, y es el único del script |
| `origen.py` | lista los brutos de las rutas dadas, sin salir de ellas | no |
| `lectura.py` | ffmpeg sólo hacia la memoria (`pipe:1`), sin `FFREPORT`, desde `/` | no |
| `localizar.py` | dónde está cada bruto dentro del máster | no |
| `medir.py` | encuadre fino, T1, T5, cobertura | no |
| `informe.py` · `cifras_ref.py` · `coste.py` | informe, lectura de `CIFRAS.md`, estimación | no |
| `sintetico.py` | fabrica el montaje sintético de los tests | **sí** (en la carpeta que se le pase) |
| `medir_coste.py` | mide costes y escribe `coste_medido.json` | **sí** (carpeta temporal y ese JSON) |

`tests/test_pruebas_guarda.py` recorre el AST de los ocho módulos del script y falla si
alguno escribe sin la guarda o importa `sintetico`/`medir_coste`/`tests`/`core.resolve`
(con control negativo). `tests/test_pruebas_primera_real.py` ejecuta el script de verdad
contra un origen con `chmod` de sólo lectura y compara listado, tamaños, `mtime` de
ficheros y carpetas y `sha256`, antes y después.

---

## 1 · Localización: el montaje sintético y lo que salió

Montaje de `sintetico.py`: 5 brutos de 640×360 a 25 fps (60 fotogramas, panorámicas y un
objeto que se mueve por su cuenta) y un máster de 480×270 con CDL + LUT conocidos:
A reencuadrado al 75 %, B entero, D al 60 %, B de 5 fotogramas, D entero (segunda vez),
fundido de 6 fotogramas y E (toma gemela de A) al 90 %. C no aparece.

Comando: `.venv/bin/python -m pytest tests/test_pruebas_localizar.py -s` · 16-09-2026.

| Plano | Encaje (fino · verificaciones) | Cociente frente a otro bruto | Confianza |
|---|---|---|---|
| A, 75 % | 0.971 · 0.968, 0.971 | 7.87 (E) | alta |
| B, entero | 0.996 · 0.996, 0.996 | 35.56 | alta |
| D, 60 % | 0.953 · 0.939, 0.947 | 7.32 | alta |
| B, 5 fotogramas | 0.996 · sin verificación | 40.53 | **baja** (corto, sin verificar) |
| D, entero | 0.998 · 0.998 | 42.11 | alta |
| E, 90 %, tras el fundido | 0.962 · 0.966 | 9.95 (A) | alta |

**5 de 5 planos largos localizados**, con el desfase exacto al fotograma, escala dentro del
3 % y esquina dentro de 0.02. **0 fotogramas asignados a un bruto equivocado.** C sale como
no encontrado; el plano de 5 fotogramas sale descartado y dice por qué.

**La trampa de la toma gemela**, quitando la toma buena de la lista:

| Sin | Lo que intenta con la otra toma | Confianza |
|---|---|---|
| E | A sobre los fotogramas de E: encaje 0.472, verificación 0.321, cociente 1.25 | baja: descartado |
| A | E sobre los fotogramas de A: encaje 0.380 / 0.399, cociente 1.27 / 1.30 | baja: descartado |

### Umbrales: puestos a mano y NO medidos sobre material real

`NCC_NADA` 0.60 · `NCC_PLENO` 0.90 · `MARGEN_NADA` 1.0 · `MARGEN_PLENO` 2.5 ·
`FOTOGRAMAS_FIABLES` 12 · `UMBRAL_CORTE` 0.35 · `TEXTURA_MINIMA` 0.15. Y el paso de nota a
nivel es `core.contracts.confidence_level`, cuyos `CONFIDENCE_ALTA`/`_MEDIA` tampoco están
medidos (`CIFRAS.md` §6). Sobre sintético los encajes correctos están entre 0.939 y 0.998;
**con grano, compresión y el reescalado de un máster real es probable que salgan más bajos,
y el script descartará planos buenos**. Es el lado seguro del error, y el informe enseña
los encajes de lo descartado para poder recalibrar con la primera prueba.

---

## 2 · El prefiltro de la estructura (`SIGMA_PREFILTRO` = 1.2)

Comando: `.venv/bin/python -m pytest tests/test_pruebas_medir.py -s -k prefiltro` · 16-09-2026.

**Frente a los fotogramas vecinos (±3), el prefiltro NO separa mejor.** Sube todos los
encajes, el correcto y los vecinos, y el margen medio baja de **+0.0592** (sin) a
**+0.0215** (con). Con prefiltro el correcto sigue ganando en los 5 planos.

Lo escribí al revés durante el desarrollo, leyendo unas cifras sueltas; la tabla del test
lo corrigió. **El motivo real por el que se queda** es este otro, medido de punta a punta:

Comando: `.venv/bin/python -m pytest tests/test_pruebas_medir.py -s -k sin_prefiltro`

| | Apariciones aceptadas en un fotograma equivocado |
|---|---|
| con prefiltro | **ninguna** |
| sin prefiltro | **E, fotogramas 123–134, desfase −74 cuando la verdad es −89**, con confianza alta |

El test es un centinela: si un día sin prefiltro deja de equivocarse, falla y pide volver
a medir.

---

## 3 · Medir el grado: a la mitad de resolución y con registro subpíxel

Comando: `.venv/bin/python -m pytest tests/test_pruebas_medir.py -s -k mitad` · 16-09-2026.
Pareja con la geometría **verdadera**, fotograma del centro de cada plano reencuadrado. El
«suelo» es el ΔE2000 del **grado verdadero** aplicado al bruto ya encajado: lo mejor que se
puede medir sobre esa pareja.

| T1 ΔE2000 medio, zona cubierta | A | D 60 % | D entero | E | media |
|---|---|---|---|---|---|
| resolución completa, sin subpíxel | 0.570 | 0.958 | 0.430 | 1.101 | 0.765 |
| resolución completa, subpíxel | 0.571 | 1.127 | 0.429 | 0.776 | 0.726 |
| mitad, sin subpíxel | 0.321 | 0.496 | 0.289 | 2.442 | 0.887 |
| **mitad, subpíxel (lo que hace el script)** | **0.323** | **0.483** | **0.291** | **0.891** | **0.497** |
| suelo (grado verdadero) en esa misma pareja | 0.329 | 0.451 | 0.251 | 0.781 | — |

- **Medir a la mitad** es lo que más aporta: un grado no lineal no conmuta con el reescalado
  con que se hizo el máster, y reducir los dos lo diluye.
- **El registro subpíxel** es neutro en tres planos y decisivo en E (2.442 → 0.891).
- Con las dos cosas, **el T1 medio queda a menos de 0.11 del grado verdadero** en los
  cuatro planos.

**El máximo no baja igual**, y no es un fallo de la medida: el grado verdadero deja en
esas mismas parejas máximos de 7.24, 13.82, 6.42 y 28.67. Están en los bordes (píxeles
mezclados). Por eso el informe da, al lado del máximo, el máximo **lejos de bordes** (se
quita el 15 % de píxeles con más gradiente, `medir.FRACCION_BORDES`, valor puesto a mano).

---

## 4 · Costes: de dónde salen las cifras del instructivo

Comando: `.venv/bin/python pruebas/medir_coste.py` → `pruebas/coste_medido.json` ·
16-09-2026, en el Mac de Mario (arm64), ProRes 4444 sintético.

| Coste unitario | Valor |
|---|---|
| decodificar y reducir, por fotograma y megapíxel | 0.00221 s |
| extraer un fotograma completo | 0.0373 s + 0.0627 s por megapíxel |
| procesar el escaneo del máster, por fotograma | 0.00076 s |
| procesar el escaneo de brutos, por segundo de bruto | 0.0228 s |
| localizar, por punto de búsqueda (cada 12 fotogramas) | 0.206 s |
| T1 (`invertir_grado`), por megapíxel de análisis | 17.86 s → **9.3 s** por plano a 960×540 |
| T5, por pareja y megapíxel | 0.596 s → **0.31 s** por pareja a 960×540 |
| PNG de 16 bits, bytes por píxel | 4.96 liso · 5.28 con grano fuerte · **6 como máximo** (aritmética) |
| hoja de contacto | 185 KB |

La cuenta está en el docstring de `coste.py` y en el instructivo. **No se ha medido con
material de cámara**: un H.265 de 10 bits de la FX3 o un 4K decodifican a otra velocidad
que el ProRes sintético, y no se sabe hacia qué lado.

**Atribución que hay que saber:** todo el tiempo de localizar se reparte por punto de
búsqueda. En el montaje hay 6 planos en 14 puntos; con planos de más de ~28 fotogramas de
media la estimación peca por arriba, con planos más cortos, por abajo.

---

## 5 · Lo que NO sabe hacer todavía (y va a hacer falta)

1. **Un espacio de color para todos los brutos.** Si el trabajo mezcla cámaras log
   distintas (FX3 en S-Log3 y DJI en D-Log), hay que ejecutarlo una vez por cámara.
2. **RAW** (BRAW, R3D, Canon RAW, ProRes RAW): ffmpeg no los lee. Hace falta un ProRes
   del bruto entero, sin recortar ni corregir.
3. **Planos retocados en velocidad, volteados, rotados, estabilizados o con zoom animado
   fuerte**, pantalla partida, imagen dentro de imagen. Un zoom lento puede pasar (la
   verificación busca la escala en ±4.5 %); uno rápido, no.
4. **Recortes de menos de la mitad del ancho del bruto** (`--escala-minima`).
5. **Píxel no cuadrado** (anamórfico sin desanamorfizar).
6. **Rótulos o gráficos encima** bajan el encaje y pueden hacer descartar un plano bueno.
7. **Un solo fotograma por plano** para T1 y T5. Si ese fotograma tiene un destello o un
   desenfoque, el plano entero se mide mal.
8. **Umbrales de confianza sin calibrar con material real** (§1).
9. **El «lejos de bordes» tiene un 15 % puesto a mano.**
10. **Todos los espacios de trabajo son D65** (`CAPACIDADES.md`): un máster en DCI-P3 no
    está probado.

---

## 6 · Lo que se decidió y por qué, en una línea cada cosa

- **No se copia ningún bruto.** Se extraen dos fotogramas por plano (bruto y máster) en
  PNG de 16 bits, leídos directamente del origen. Un bruto puede pesar decenas de GB.
- **El máster se escanea a 128 px y los brutos a 256 px.** El doble en el bruto para que un
  recorte a la mitad siga teniendo 128 px reales.
- **Huella para acercarse, estructura para decidir.** La huella de `core.analysis` es ciega
  al color pero no a un reencuadre; por eso hay un banco de 15 recortes por muestra.
- **El margen se mide contra el mejor candidato de OTRO bruto, afinado igual que el
  propio.** Sin afinar al otro, el margen salía inflado.
- **El margen de una aparición es el del punto mediano**, no el peor (un punto dentro de
  un fundido encaja poco y no habla de ambigüedad) ni el mejor (una toma gemela es ambigua
  en todo el plano).
- **Sólo se miden las de confianza alta.** Un grado sacado del plano equivocado tiene muy
  buena cara; es lo peor que puede pasar.
