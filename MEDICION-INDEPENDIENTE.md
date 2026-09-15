# MEDICIÓN INDEPENDIENTE — SIDEBFLMS COLOR

Fecha: **2026-09-15**. Medidor: agente independiente, que no ha escrito nada de
`core/`, `gui/` ni `probe/` y hoy tampoco ha escrito nada ahí.

**Qué es esto.** Las cuatro cifras de titular del proyecto son autoinformadas:
las midió el mismo proceso que escribió el código. Esto es volver a medirlas
desde fuera, con material propio, métrica propia y entrando sólo por la API
pública.

**Qué NO es esto.** No se ha arreglado nada. Donde una cifra no sale, se dice y
se para.

---

## 0. Antes de nada: mi vara de medir, validada

Esto va primero porque si la métrica estuviera mal, ninguna de las cuatro
cifras de abajo significaría nada.

| Comprobación | Resultado |
|---|---|
| Mi ΔE2000 (`colour.difference.delta_E_CIE2000`) contra los 34 pares de Sharma, Wu y Dalal (2005) | **error máximo 4.9499e-05** |
| El ΔE2000 del repo (`core.color.delta_e2000_lab`) contra los mismos 34 pares | **error máximo 4.9499e-05** |
| Mi camino de espacios (DWG/DI → XYZ → L\*a\*b\* con `colour`) contra el del repo, sobre mi escena entera | **L\*a\*b\* difiere 2.22e-13 · ΔE2000 difiere 1.60e-13** |
| Primarios de las 4 cámaras: `colour` contra `core/color/spaces.py` | **error 0 (dígito a dígito)** |
| Mi CDL y mi trilineal contra `CDL.apply` / `LUT3D.apply` | **0 y 3.33e-16** |

**Conclusión: mi ΔE2000 y el del repo son la misma función, con un error de
1.6e-13 sobre imágenes reales.** Los 4.9e-05 contra Sharma no son error de
ninguna de las dos implementaciones: es el redondeo a cuatro decimales de la
tabla publicada, y las dos se desvían exactamente lo mismo.

**Y mi camino de conversión de espacios coincide con el del repo** (2.2e-13 en
L\*a\*b\*). Esto era lo que podía haber sido un hallazgo de primer orden, y no
lo es: el puente DaVinci Wide Gamut / DaVinci Intermediate del repo lleva los
colores al mismo sitio que `colour-science`. Bien.

Comando:

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
.venv/bin/python -m pytest tests/medicion/test_metrica.py -s -p no:randomly
```

Consecuencia importante para leer la tabla de abajo: **ninguna diferencia entre
mis cifras y las publicadas se explica por la métrica.** Si difieren, difieren
por el material o por el montaje.

---

## 1. La tabla

| | Criterio | Publicado | Mío | Veredicto |
|---|---|---|---|---|
| **T1** ingeniería inversa | ΔE2000 medio < 1.0 · máx < 3.0 | 0.1415 · 1.7409 | **0.1687 · 2.8867** | **difiere** (criterio cumplido, cifra 1.19x y 1.66x peor) |
| **T2** lo que no es un LUT | no decir 100% LUT, y señalar la zona | 70.0% reproducible, solape 99.4% | **90.8% reproducible, solape 0.0%** de la zona más fuerte | **difiere** (la mitad de "no es 100% LUT" **coincide**; la de "señalar la zona" **no se reproduce**) |
| **T3** igualado de 4 cámaras | > 8.0 antes · < 2.0 después | 17.674 → 0.661 | **15.499 → 1.085** | **difiere** (criterio cumplido, el "después" es 1.64x peor) |
| **T4** QC de LUT | caza los 3 malos, identidad limpia | 3/3, limpia en 17³/33³/65³ | **3/3, limpia en 17³/33³/65³** | **coincide** |

Detalle, comando y atribución de cada una, abajo.

---

## 1.b Las dos cifras que faltan en la tabla de titulares

Van aquí arriba porque son las que de verdad deciden y ninguna de las dos es la
que se publica.

### a) La cobertura del cubo: **el 99.3% del `.cube` que se entrega está inventado**

| Montaje | Celdas con dato | De un total de | Cobertura | Inventado por el relleno |
|---|---|---|---|---|
| **Mi escena** (720x405, 24 parches saturados, piel, especular, sombra) | **264** | 35.937 | **0.73%** | **99.27%** |
| **La del repo** (`studio_scene`, 640x360) | **165** | 35.937 | **0.46%** | **99.54%** |

Un plano no cubre ni de lejos las 35.937 celdas de un cubo de 33. Las que no
tiene, el relleno de huecos las **inventa** (extrapola y suaviza), y
`coverage.counts == 0` dice exactamente cuáles. Está dicho en
`core/reverse/NOTAS.md` y en `BITACORA.md`, pero **no está en la tabla de
titulares y debería**: es el número que contesta la pregunta que Mario hará de
verdad, que no es "¿qué ΔE tiene esto?" sino **"¿me puedo fiar de este `.cube`
con un plano distinto del que lo generó?"**.

Y es lo que limita el T1 de verdad: el 0.1687 se mide sobre el mismo plano del
que salió el LUT. Sobre otro plano, el color caería en celdas inventadas.

Comandos (fecha de medida: 2026-09-15):

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
# mía — línea [MEDICION T1-cobertura] celdas_con_dato=264 ... fraccion=0.00734619
.venv/bin/python -m pytest "tests/medicion/test_t1_t2.py::test_T1_el_mapa_de_cobertura_no_marca_como_real_lo_que_se_invento" -s -p no:randomly
# la del repo — línea [T1-cobertura] celdas_con_dato=165.0000 ... fraccion=0.0046
.venv/bin/python -m pytest "tests/test_entregables.py::test_T1_el_mapa_de_cobertura_no_miente" -s -p no:randomly
```

### b) Los dos márgenes ajustados: **0.11 y 0.094**

| | Lo que se publica | Lo que de verdad decide | Límite | Margen suyo | Margen mío |
|---|---|---|---|---|---|
| **T1** | el medio: 0.1415 | **el máximo: 1.7409 → mío 2.8867** | < 3.0 | 1.26 | **0.11** |
| **T3** | la media: 0.661 | **el peor par: 0.981 → mío 1.906** | < 2.0 | 1.02 | **0.094** |

Dicho tal cual: **el titular del T1 es el medio, pero el que suspende es el
máximo; el titular del T3 es la media, pero el que suspende es el peor par.** Con
su material los dos van holgados; con el mío, T1 pasa por **0.11** y el peor par
del T3 por **0.094**. Publicar la media y el caso peor juntos costaría una línea
y quitaría la ambigüedad.

Comandos (fecha de medida: 2026-09-15):

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
# T1 máximo mío — línea [MEDICION T1] de_max_cubierto=2.88672
.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -p no:randomly -k T1
# T3 peor par mío — línea [MEDICION T3-peor-par] peor=1.90573
.venv/bin/python -m pytest tests/medicion/test_t3.py -s -p no:randomly
# los dos suyos — líneas [T1] de_max_cubierto=1.7409 y [T3-peor-par] peor=0.9810
.venv/bin/python -m pytest tests/test_entregables.py -s -p no:randomly
```

---

## 2. T1 — ingeniería inversa · **difiere**

### Cifra

```
[MEDICION T1] de_medio_cubierto=0.168689  de_max_cubierto=2.88672  de_p95_cubierto=0.436776
              de_medio_todo=0.168689  de_max_todo=2.88672
              fraccion_pixeles_cubiertos=1  cobertura_del_cubo=0.00734619
[MEDICION T1-lo-que-dice-el-repo] de_medio_cubierto=0.168689  de_max_cubierto=2.88672
              de_medio_todo=0.168689  de_max_todo=2.88672
[MEDICION T1-cobertura] celdas_con_dato=264  total=35937  fraccion=0.00734619  celdas_que_mienten=0
```

### Comando

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -p no:randomly -k T1
```

### Sobre qué material

Mi escena `escena_trabajo()` (720x405, semilla 20260915): fondo en degradado de
temperatura, 24 parches de color en rejilla, figura de piel, reflejo especular
por encima del blanco difuso, sombra profunda en la esquina inferior izquierda
y grano sembrado proporcional a la raíz de la señal. Construida en
escena-lineal Rec.709 y llevada al espacio de trabajo **con `colour-science`**.
No se parece a `studio_scene`.

El coloreado es `LUT(CDL(original))` **en ese orden**, que es el contrato, con
mi CDL (`slope=(1.085, 0.995, 0.925)`, `offset=(0.018, -0.002, -0.014)`,
`power=(0.935, 1.010, 1.065)`, `sat=1.18`) y mi LUT de 33 (contraste con pivote
en 0.42, sombras a verde-azul, altas a cálido, y un acoplamiento rojo-verde
para que el LUT no sea separable por canales). Fabricado con **mi** CDL y **mi**
trilineal, no con `CDL.apply` / `LUT3D.apply`.

### Sobre qué píxeles

Lo publicado es "en la zona con cobertura". Según `core/reverse/invertir.py`
eso significa: píxeles cuya **celda más cercana** del cubo tiene ≥ `min_samples`
(4) muestras reales, buscando la celda sobre el **original ya pasado por el
CDL** (que es el dominio del LUT) y con los valores sujetos a 0..1. Esa máscara
la recalculo yo con numpy puro a partir de `resultado.cdl` y
`resultado.coverage.covered_mask()`, que son API pública.

**Aviso para que nadie compare dos números que no son comparables: en mi escena
el 100% de los píxeles cae en la zona con cobertura** (`fraccion_pixeles_cubiertos=1`),
así que "zona cubierta" y "plano entero" me dan el mismo número. En la suya no
tiene por qué. Doy los dos, y son iguales.

### Cuánto difiere y qué lo explica

- Medio: 0.1687 contra 0.1415 → **+19%**.
- Máximo: 2.8867 contra 1.7409 → **+66%**, y a **0.11 de incumplir el criterio de 3.0**.

**Lo explica el material, no la métrica, y esto está medido y no supuesto.** La
línea `T1-lo-que-dice-el-repo` es el número que el propio repo se autoinforma
(`confidence.metrics["de_medio_cubierto"]`) sobre **mi** montaje: 0.168689 y
2.88672, **idénticos dígito a dígito a los míos**. O sea que sobre el mismo
material los dos medidores dan exactamente lo mismo. La diferencia con 0.1415 /
1.7409 es enteramente que mi escena es otra.

Y es una escena más dura a propósito: 264 celdas del cubo con dato frente a las
165 de la suya (0.73% de cobertura frente a 0.46%), con parches saturados que
llegan a esquinas del cubo donde el relleno de huecos tiene menos vecinos de los
que fiarse. **El máximo a 2.89 es el dato que me preocuparía**: el criterio del
encargo es 3.0 y una escena con más variedad cromática ya lo roza. No digo que
esté mal; digo que el margen de esa cifra es más estrecho de lo que 1.7409
sugiere.

### Comprobación de apoyo

El mapa de cobertura no miente: recontando trilinealmente sobre el dominio del
LUT (post-CDL) con numpy puro, **0 celdas dicen tener datos sin tenerlos**.

---

## 3. T2 — detección de lo que no es un LUT · **difiere**

### Cifra

```
[MEDICION T2-etiquetas] ['zona local']
[MEDICION T2] lut_reproducible=0.90836  is_pure_lut=0  n_hotspots=2
[MEDICION T2-cajas] mia=(96, 250, 190, 110)
[MEDICION T2-cajas]   'zona local' (0,284,31,29) mag=12.7255 solape=0.0000
[MEDICION T2-cajas]   'zona local' (89,301,251,104) mag=11.3772 solape=0.4294
[MEDICION T2-zona] residuo_dentro=0.368935  residuo_fuera=0.0778981  razon=4.73613
              mejor_solape_de_cualquier_hotspot=0.429436
              fraccion_top500_residuo_en_mi_ventana=0.936
[MEDICION T2-zona-mas-fuerte] solape=0  magnitud=12.7255
[MEDICION T2-contrapeso] lut_reproducible=0.993971  is_pure_lut=1  n_hotspots=0
```

`tests/medicion/test_t1_t2.py::test_T2_la_zona_senalada_cae_donde_esta_mi_ventana`
**queda marcado `@pytest.mark.xfail(strict=True)`**, con el criterio y el montaje
**intactos**. No se arregla y no se afloja: `strict=True` significa que si algún
día pasa, pytest lo marca como `XPASS` y falla, que es justo lo que se quiere —
el día que esto se cierre, nos enteramos.

El `reason` lleva las cifras reales de este mismo montaje, el caso en que sí
pasa, qué haría falta para cerrarlo y el comando que reproduce las dos cosas,
como pide la regla de las cifras de `CONTRATOS.md`. Se lee entero con:

```bash
.venv/bin/python -m pytest "tests/medicion/test_t1_t2.py::test_T2_la_zona_senalada_cae_donde_esta_mi_ventana" -rx
```

### Comando

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
.venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -p no:randomly -k T2
```

### Sobre qué material

El mismo coloreado del T1 **más una viñeta y una ventana fabricadas por mí**:
viñeta radial de fuerza 0.42 con exponente 1.7, y ventana rectangular en
`(x=96, y=250, w=190, h=110)` con ganancia 1.55 y borde difuminado con dos pasadas
de caja separable de radio 9. Las dos se aplican **en luz lineal** (decodificar
DaVinci Intermediate, multiplicar, recodificar), porque una viñeta es un
obturado óptico y una ventana es un foco, y ahí es donde son multiplicativas de
verdad.

### Qué coincide y qué no

| Mitad del criterio | Resultado |
|---|---|
| "no puede decir 100% LUT" | **COINCIDE**: `is_pure_lut=False`, `lut_reproducible=0.908 < 1.0`, deja `spatial_residual`, emite 2 hotspots |
| "tiene que señalar la zona" | **NO SE REPRODUCE**: la zona local más fuerte es `(0,284,31,29)` y solapa **el 0%** con mi ventana |
| el contrapeso (sin nada espacial, decir que SÍ es un LUT) | **COINCIDE**: `is_pure_lut=True`, `reproducible=0.9940` |

Y la cifra de titular: **90.8% reproducible frente al 70.0% publicado**.

### Cuánto difiere y qué lo explica

Lo he atribuido, y la causa está medida:

```
[MEDICION T2-atribucion] luz-lineal (la mia): reproducible=0.9084 pure=False n_hotspots=2 mejor_solape=0.4294
[MEDICION T2-atribucion] codificada (la suya): reproducible=0.6844 pure=False n_hotspots=8 mejor_solape=0.9020
[MEDICION T2-atribucion]   'vineta' (0,0,720,405) mag=8.2429 solape=0.0717
[MEDICION T2-atribucion]   'textura' (0,0,720,405) mag=8.2429 solape=0.0717
[MEDICION T2-atribucion]   'zona local' (98,257,229,105) mag=30.1847 solape=0.8053
[MEDICION T2-atribucion]   'zona local' (97,245,34,51) mag=25.6266 solape=0.9020
```

Comando:

```bash
.venv/bin/python -m pytest "tests/medicion/test_t1_t2.py::test_T2_atribucion_luz_lineal_contra_imagen_codificada" -s -p no:randomly
```

**Con la MISMA viñeta y la MISMA ventana, aplicadas sobre la imagen codificada
en vez de en luz lineal (que es lo que hace el repo), sale 0.6844 contra el
0.7002 publicado, aparece la etiqueta `vineta`, y la zona local más fuerte
solapa 0.8053 con mi ventana: pasaría el criterio de >0.8.** O sea que **la
cifra publicada del T2 se reproduce con material distinto en cuanto se usa su
misma convención**. Lo que no se reproduce es con la mía.

La razón física es sencilla: una ganancia de 0.58x encima de una curva
logarítmica es un desplazamiento constante enorme; en luz lineal es una
multiplicación suave. Mi montaje perturba mucho menos, y **es en ese régimen
suave donde el detector se descompone.**

### Lo que de verdad me llama la atención aquí

El detector **sí sabe dónde está la ventana**: el 93.6% de los 500 píxeles de
mayor residuo caen dentro de mi caja, y el residuo medio dentro es 4.74 veces
el de fuera. **Lo que falla no es el detector, es cómo recorta las cajas.** La
zona que declara "más fuerte" es un cuadrito de 31x29 en la esquina inferior
izquierda, que es donde mi escena tiene sombra profunda: con muy poca luz, el
campo de logaritmo de ganancia es ruidoso y el pico se va ahí.

Lo he aislado con una sonda (`test_T2_de_donde_sale_cada_hotspot_vineta_ventana_y_sombra`):

```
[MEDICION T2-sonda] sombra=True  caso=ventana-sola reproducible=0.9759 n_hotspots=3
[MEDICION T2-sonda]   'zona local' (0,274,41,41)    mag=5.8230 solape=0.0000   <-- la esquina oscura
[MEDICION T2-sonda]   'zona local' (95,334,35,30)   mag=4.6865 solape=0.8419
[MEDICION T2-sonda]   'zona local' (249,267,32,88)  mag=4.6830 solape=1.0000
[MEDICION T2-sonda] sombra=False caso=ventana-sola reproducible=0.9410 n_hotspots=4
[MEDICION T2-sonda]   'zona local' (117,368,101,37) mag=8.8267 solape=0.0000
[MEDICION T2-sonda]   'zona local' (57,244,226,120) mag=7.1337 solape=0.7585
```

Dos cosas, y las dos son hallazgos:

1. **Con sombra profunda en el cuadro, el hotspot más fuerte es la sombra, no
   la ventana.** Material de rodaje real tiene esquinas a oscuras casi siempre.
2. **Quitando la sombra tampoco se arregla**: el más fuerte pasa a ser
   `(117,368,101,37)` con solape 0. O sea que la inestabilidad del recorte de
   cajas no es sólo culpa de mi sombra.

Y una tercera: **mi viñeta sola NUNCA se etiqueta como `vineta`** en luz lineal
(emite dos `zona local`), aunque sí lo haga cuando se aplica sobre la imagen
codificada. El arreglo del día 2 que dejó el etiquetado de viñetas funcionando
está calibrado para viñetas aplicadas en el dominio codificado; con una viñeta
óptica suave no dispara.

**Esto NO lo arreglo y no propongo cómo.** Lo dejo medido.

---

## 4. T3 — igualado de cuatro cámaras · **difiere**

### Cifra

```
[MEDICION T3-A-colour] antes=15.4989  despues=1.08474  mejora=14.2881
                       peor_par_antes=24.8375  peor_par_despues=1.90573
[MEDICION T3-B-repo]   antes=15.4989  despues=1.08536  mejora=14.28
                       peor_par_antes=24.8369  peor_par_despues=1.90677
[MEDICION T3-caminos] camara='FX3 (S-Log3 / S-Gamut3.Cine)'  de_medio=1.59625e-08  de_max=7.47614e-05
[MEDICION T3-caminos] camara='Canon (C-Log3 / Cinema Gamut)' de_medio=0            de_max=0
[MEDICION T3-caminos] camara='Lumix (V-Log / V-Gamut)'       de_medio=6.74445e-05  de_max=0.000161496
[MEDICION T3-caminos] camara='DJI (D-Log / D-Gamut)'         de_medio=0.0040267    de_max=0.0131486
[MEDICION T3-peor-par] peor=1.90573
```

### Comando

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
.venv/bin/python -m pytest tests/medicion/test_t3.py -s -p no:randomly
```

### La decisión que había que tomar, y por qué la tomo así

Para fabricar las cuatro cámaras hay que convertir entre espacios, y esa
conversión se puede hacer con `core.color.convert` (que es parte de lo que se
mide) o con `colour-science`.

**Doy las dos, y la de titular es la de `colour` (A).** Razón: la A es la única
de las dos que no da nada por bueno — si las matrices del repo estuvieran mal,
el emparejador tendría que recuperar también ese error y el "después" subiría.
La B está al lado para poder **atribuir**: si A y B salen iguales, la cifra mide
el emparejador y nada más.

Y salen iguales: **1.08474 contra 1.08536**, y las dos versiones de cada cámara
se separan como mucho **0.0131 ΔE2000 en el peor píxel** (la DJI; la Canon es
bit a bit idéntica). Los primarios coinciden dígito a dígito y las curvas ya
estaban verificadas contra `colour` en el propio repo, así que no es casualidad.

**Conclusión: el puente de espacios del repo no aporta error medible al T3.**

### Sobre qué material

Mi escena en escena-lineal Rec.709 → los cuatro espacios de captura
(S-Log3/S-Gamut3.Cine, C-Log3/Cinema Gamut, V-Log/V-Gamut, D-Log/D-Gamut) → mi
desviación de balance por cámara (slope y offset propios, distintos de los del
repo) → vuelta al espacio de trabajo. La FX3 manda; las otras tres se llevan a
ella con `emparejar` y se aplica el `cdl` que devuelve. **No se llama a
`igualar_camaras`**, que es la función que el autor del módulo escribió para
probarse a sí mismo. ΔE2000 medio de los 6 pares, con mi métrica, sobre todos
los píxeles del plano.

### Cuánto difiere y qué lo explica

- Antes: 15.499 contra 17.674 → **-12%**. Mis desviaciones de balance son algo
  más suaves que las suyas; el montaje parte de menos desajuste. Sigue muy por
  encima del 8.0 que pide el criterio.
- Después: **1.085 contra 0.661 → 1.64x peor**. Criterio cumplido (< 2.0), pero
  con menos margen del que 0.661 sugiere.
- **Peor par: 1.906**, contra el 0.981 que informa el repo. Eso está a **0.094
  de incumplir**. Es el número más ajustado de todo el informe.

Qué lo explica: mi escena tiene mucho más volumen de color (24 parches
saturados que se van a las esquinas de cada gamut) y un reflejo especular por
encima del blanco difuso. Un CDL de diez parámetros es una aplicación afín por
canal más una potencia: cuanto más ancha es la nube de color y más se sale del
gamut de destino, menos puede un CDL solo. La suya, con menos extensión
cromática, le deja al CDL un problema más fácil.

**No es un fallo. Es que la cifra de 0.661 depende bastante de la escena, y
0.661 no es el caso peor.** Con material de verdad (parches de cámara, gamas de
color amplias) el número está más cerca de 1.1, y el peor par cerca de 1.9.

---

## 5. T4 — QC de LUT · **coincide**

### Cifra

```
[MEDICION T4-trampa] retroceso=0.05  paso_de_rejilla=0.03125
[MEDICION T4-identidad-17] avisos=0  ok=True  codigos=[]
[MEDICION T4-identidad-33] avisos=0  ok=True  codigos=[]
[MEDICION T4-identidad-65] avisos=0  ok=True  codigos=[]
[MEDICION T4-no monotono]    avisos=21  codigos=['banding', 'no_monotonia']  dice_donde=True
[MEDICION T4-banding]        avisos=26  codigos=['banding', 'gamut']         dice_donde=True
[MEDICION T4-fuera de gamut] avisos=20  codigos=['gamut']                    dice_donde=True
[MEDICION T4] cazados=3/3
[MEDICION T4-no-monotono-donde] n=20  primeras_celdas=[(9, 0, 0), (9, 0, 1), (9, 0, 2)]
[MEDICION T4-ida-y-vuelta-no_monotono] codigos=['banding', 'no_monotonia']
[MEDICION T4-ida-y-vuelta-banding]     codigos=['banding', 'gamut']
[MEDICION T4-ida-y-vuelta-gamut]       codigos=['gamut']
[MEDICION T4-identidad-fichero-17] error_max=0.0  ok=True  avisos=0
[MEDICION T4-identidad-fichero-33] error_max=0.0  ok=True  avisos=0
[MEDICION T4-identidad-fichero-65] error_max=0.0  ok=True  avisos=0
```

### Comando

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
.venv/bin/python -m pytest tests/medicion/test_t4.py -s -p no:randomly
```

### Sobre qué material

Tres LUT malos fabricados por mí, **sin tocar `core.io.catalogo_luts_malos` ni
ninguno de sus generadores**:

1. **No monótono**: el rojo de la celda 10 se pone al valor de la celda 9 menos
   **0.05**. La trampa del encargo está comprobada con una aserción propia
   (`test_T4_mi_lut_no_monotono_lo_es_de_verdad`): con tamaño 33 el paso de
   rejilla es 1/32 = **0.03125**, y un retroceso de 0.02 dejaría la celda 10 en
   0.2925, todavía por encima de la 9 (0.28125) — eso no invertiría nada y el
   QC tendría razón en no avisar. Mi retroceso es 0.05 > 0.03125: **invierte de
   verdad**.
2. **Banding**: escalón de +0.28 en media rejilla del eje verde.
3. **Fuera de gamut**: `t * 1.45 - 0.22`, se sale por los dos lados.

### Resultado

- **Los tres, cazados, cada uno con su código.** 3/3.
- **La identidad pasa limpia en 17³, 33³ y 65³**: 0 avisos, `ok=True`, y sigue
  limpia después de escribirla y releerla en `.cube` (error 0.0).
- Ninguno se "arregla" al pasar por el fichero.
- El no monótono **dice dónde**: celdas `(9, g, b)`. Señala la celda **desde la
  que** se retrocede, no la que retrocede. Es una convención tan válida como la
  otra (para la GUI hasta mejor: es la última que todavía iba bien), y la doy
  por buena; queda escrita porque a quien vuelva aquí le va a sorprender.

### Lo único que anoto

Hay **códigos cruzados que no estaban en el titular**: mi LUT no monótono
también dispara `banding` (razonable: un salto de 0.05 entre celdas contiguas
es una discontinuidad), y mi LUT con banding también dispara `gamut` (razonable:
+0.28 se sale de 1.0). No son falsos positivos, son consecuencias reales de mis
LUT. Lo anoto para que "3/3" no se lea como "cada LUT saca exactamente un
código": saca el suyo y a veces alguno más.

---

## 6. El árbol contra el que se ha medido

`core/` estaba **siendo editado por otros agentes mientras yo medía**. En medio
de una tanda, `core/reverse/acumulacion.py` llegó a no importar
(`NameError: name 'MUESTRAS_MINIMAS_CELDA' is not defined`); se resolvió solo en
menos de un minuto. No es mío, no lo he tocado, y lo menciono porque explicaría
cualquier rojo raro que alguien vea hoy.

`git HEAD` en el momento de medir:
`e1b734ca7e97eac8c20d47624e28f551647cc2c2` — "CONTRATOS: la regla de las cifras".

Con modificaciones sin comitear en `core/analysis/stats.py`, `core/contracts.py`,
`core/io/qc.py`, `core/matching/{confianza,contenido}.py`,
`core/reverse/{acumulacion,alineado,diagnostico,invertir}.py`, `gui/*` y un
`core/umbrales.py` nuevo.

**Para que eso no contaminara el informe, he corrido el arnés entero también
contra una copia limpia de HEAD** (`git archive HEAD` extraído a un directorio
temporal, con mi arnés copiado dentro, y borrado después):

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
rm -rf tests/medicion/.head_tmp && mkdir -p tests/medicion/.head_tmp
git archive HEAD | tar -x -C tests/medicion/.head_tmp
mkdir -p tests/medicion/.head_tmp/tests/medicion
cp tests/medicion/*.py tests/medicion/.head_tmp/tests/medicion/
cd tests/medicion/.head_tmp && "../../../.venv/bin/python" -m pytest tests/medicion -s -p no:randomly -p no:cacheprovider
cd ../../.. && rm -rf tests/medicion/.head_tmp
```

**Todas mis cifras salen idénticas dígito a dígito en HEAD y en el árbol de
trabajo.** Las ediciones en vuelo no mueven ninguna de las cuatro.

Y para separar "material distinto" de "cifra que ya no sale", he corrido
también los entregables del propio repo sobre HEAD:

```
[T1] de_medio_cubierto=0.1415  de_max_cubierto=1.7409  cobertura=0.0046
[T2] lut_reproducible=0.7002  is_pure_lut=0.0000  hotspots=3.0000
[T2-zona] residuo_dentro=0.5297  residuo_fuera=0.2144  razon=2.4705  solape=0.9941
[T3] antes=17.6738  despues=0.6612  mejora=26.7309
[T4-los-tres] cazados=3.0000
26 passed
```

**Las cuatro cifras publicadas se reproducen exactamente sobre el material del
repo.** No hay ninguna cifra inventada esta vez: son honestas *para su montaje*.
El objeto de este informe es que ese montaje es más benévolo que el mío.

---

## 7. Resumen en una línea por cifra

- **T1 · difiere.** 0.1687 · 2.8867 contra 0.1415 · 1.7409. Criterio cumplido.
  Lo explica el material y está demostrado: el propio repo, midiéndose a sí
  mismo sobre mi montaje, da mis mismos 0.168689 · 2.88672. El máximo queda a
  0.11 del límite de 3.0.
- **T2 · difiere** (queda como `xfail(strict=True)`, no arreglado). 90.8% contra
  70.0%, y el solape de la zona más fuerte es 0.0% contra 99.4%. La mitad "no dice 100% LUT" coincide; la mitad "señala la
  zona" no se reproduce con lo espacial aplicado en luz lineal. Con la misma
  viñeta y ventana aplicadas como las aplica el repo (sobre la imagen
  codificada) sale 0.6844 y solape 0.8053, o sea que **la cifra se reproduce con
  su convención y no con la mía**.
- **T3 · difiere.** 15.499 → 1.085 contra 17.674 → 0.661. Criterio cumplido. Da
  lo mismo convertir con `colour` o con `core.color` (1.08474 contra 1.08536),
  así que la cifra mide el emparejador y nada más. El peor par, 1.906, queda a
  0.094 del límite de 2.0.
- **T4 · coincide.** 3/3 con LUT malos míos y identidad limpia en 17³, 33³ y
  65³, también después de pasar por el fichero.

## 8. Lo que no me han preguntado y anoto igual

1. **`core/contracts.py` tiene modificaciones sin comitear.** `CONTRATOS.md`
   dice tres veces que está congelado y que ningún agente lo edita. Son 18
   líneas. No sé si están autorizadas, pero un contrato congelado que cambia
   mientras siete agentes escriben contra él es exactamente el tipo de cosa que
   luego nadie sabe explicar.
2. **Las dos cifras más ajustadas del proyecto no son las que se publican.** El
   titular del T1 es el medio (0.1415, muy holgado) pero el que decide es el
   máximo (1.7409 contra un límite de 3.0, y 2.89 con mi material). El titular
   del T3 es la media (0.661) pero el que decide es el peor par (0.981 suyo,
   1.906 mío, contra un límite de 2.0). Publicar la media y el peor par juntos
   costaría una línea y quitaría esa ambigüedad.
3. **El detector espacial sabe dónde está la cosa pero no sabe dibujar la
   caja.** 93.6% de los píxeles de mayor residuo caen dentro de mi ventana y el
   recorte declara como zona principal un cuadrito de 31x29 en una esquina
   oscura. Si la GUI enseña la caja del hotspot más fuerte, hoy le enseñaría a
   Mario el sitio equivocado en material con sombras profundas.
4. **El etiquetado de viñeta está calibrado para viñetas del dominio
   codificado.** Una viñeta óptica aplicada en luz lineal no dispara la etiqueta
   `vineta` con ninguna de las dos variantes de mi escena. La viñeta física de
   un objetivo es multiplicativa en luz, no en log.
5. **`colour-science` avisa con `RuntimeWarning: invalid value encountered in
   log10`** al codificar Canon Log 3 sobre mi escena. No produce ni un NaN
   (comprobado: 0.0% en las cuatro cámaras, por los dos caminos); es que
   `colour` evalúa las dos ramas de la función a trozos y descarta después. No
   es un problema del repo; lo anoto para que nadie persiga ese aviso.
6. **La cobertura del cubo es diminuta y eso es lo que de verdad limita el T1.**
   264 celdas de 35.937 con mi escena (0.73%), 165 con la suya (0.46%). El 99.3%
   del LUT que se entrega está inventado por el relleno de huecos. Está dicho en
   las notas del módulo y en `BITACORA.md`, pero no está en la tabla de titulares
   y debería: es el número que contesta "¿me puedo fiar de este `.cube` con un
   plano distinto?".

---

## 9. Qué es mío en este repo

- `MEDICION-INDEPENDIENTE.md` (este archivo).
- `tests/medicion/` — `__init__.py`, `conftest.py` (sólo registra el marcador
  `medicion`, porque `pyproject.toml` corre con `--strict-markers` y no es mío),
  `metrica.py`, `escena.py`, `test_metrica.py`, `test_t1_t2.py`, `test_t3.py`,
  `test_t4.py`.

Nada más. No he tocado `core/`, `gui/`, `probe/`, los tests de nadie,
`pyproject.toml` ni git.

Para correrlo entero:

```bash
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
.venv/bin/python -m pytest tests/medicion -s -p no:randomly
```

Resultado esperado hoy: **21 pasan, 1 `xfail`**
(`test_T2_la_zona_senalada_cae_donde_esta_mi_ventana`, con `strict=True`). Ese
`xfail` es el resultado, no un pendiente ni un problema del arnés. **No lo
arregles y vuelvas a medir en el mismo movimiento: eso es exactamente como se
cuela un número que no es.** Y no toques su montaje: aflojarlo lo haría
desaparecer sin haberlo arreglado.
