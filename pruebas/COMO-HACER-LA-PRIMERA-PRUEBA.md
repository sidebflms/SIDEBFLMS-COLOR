# Cómo hacer la primera prueba con material real

Para Mario. Se lee en diez minutos.

**Qué es esta prueba.** Le das al programa un trabajo tuyo ya entregado: el máster
coloreado y los brutos con los que se hizo. El programa busca dónde sale cada bruto dentro
del máster, saca el grado de cada plano y mide dos cosas: si ese grado se puede reproducir
sobre su propio plano (**T1**) y si el grado de un plano sirve para los demás (**T5**). No
toca Resolve, no toca tus discos y no decide nada: te da cifras y te explica qué significan.

**Lo más importante:** el programa **sólo lee** tus discos. Todo lo que escribe va a una
carpeta dentro del propio programa, en el disco del ordenador. Más abajo, en el punto 6,
está cómo comprobarlo tú mismo.

---

## 1 · Qué material hace falta

### El máster coloreado

El fichero que entregaste, tal cual.

- **Vale:** ProRes, DNxHR, H.264 o H.265, en `.mov`, `.mp4` o `.mxf`. Con bandas negras
  también vale: el programa las detecta y mide sólo la imagen.
- **No vale:**
  - un **DCP** (va en otro espacio de color, XYZ, que el programa no lee);
  - una **secuencia de imágenes** (DPX, EXR, TIFF sueltos): tiene que ser un vídeo;
  - un máster con **rótulos encima de casi todos los planos**: funciona, pero descartará
    muchos planos (el rótulo no está en el bruto).

### Los brutos

Los originales de cámara, **los mismos ficheros con los que se montó**.

- **Deberían valer** los de la FX3, la Lumix, la DJI y la Canon si están en MP4, MOV o MXF:
  son formatos que el programa sabe abrir. **Todavía no se ha probado con ficheros de cada
  cámara**; si alguno no se abre, el programa lo dice (casi siempre ya en el simulacro) y
  sigue con los demás.
- **No valen los RAW** (BRAW, R3D, Canon RAW, ProRes RAW): el programa no los sabe abrir. Si
  el trabajo se rodó en RAW, exporta cada clip a ProRes 4444 **entero, sin recortar, sin
  cambiar la duración y sin ninguna corrección ni LUT**.
- **Si son log, hay que decirlo** (lo casi normal en la FX3). Los ficheros casi nunca lo
  dicen y el programa asumiría Rec.709. Se dice con `--espacio-brutos` (ver el punto 4):

  | Cámara y perfil | Lo que hay que poner |
  |---|---|
  | Sony S-Log3 / S-Gamut3.Cine | `slog3_sgamut3cine` |
  | Panasonic V-Log | `vlog_vgamut` |
  | Canon Log 3 | `clog3_cinemagamut` |
  | DJI D-Log | `dlog_dgamut` |
  | Rec.709 normal | no hace falta poner nada |

- **Si mezclaste cámaras con perfiles log distintos**, de momento hay que hacer la prueba
  una vez por cámara, pasando sólo los brutos de esa cámara.

### Qué pasa si faltan brutos, o si sobran

- **Si falta alguno**, no pasa nada: esos planos del máster salen en el informe como «sin
  bruto» y se sigue con el resto.
- **Si sobran** (descartes, otras tomas), tampoco: salen como «no aparecen en el máster».
  Sólo cuestan tiempo de búsqueda.
- **Ojo con las copias:** si el mismo clip está dos veces (por ejemplo, la tarjeta y su
  copia de seguridad), el programa no sabe cuál de los dos es y **descarta el plano**. Pasa
  una sola copia.
- **Las tomas parecidas** (toma 1 y toma 2 del mismo plano) no deberían ser problema: el
  programa distingue la buena por lo que se mueve en cuadro, y si no puede, descarta el
  plano y lo dice. Esto está probado con material sintético, no con tomas reales.

---

## 2 · Cuánto espacio hace falta

**En el disco del ordenador**, no en los de producción. El programa no copia los brutos:
sólo guarda **dos fotogramas por plano** (uno del bruto y uno del máster, sin pérdida) y
una hoja de contacto pequeña para que veas cada pareja.

**La cuenta, por plano del máster:**

| Brutos | Máster | Como mucho, por plano |
|---|---|---|
| 4K UHD (3840×2160) | HD | **63 MB** |
| 4K DCI (4096×2160) | HD | **66 MB** |
| HD | HD | **25 MB** |

**No depende de cuántos minutos dure el máster**, sino de cuántos planos tenga. Ejemplos:

- 15 planos, brutos en 4K UHD: **menos de 1 GB**.
- 30 planos, brutos en 4K UHD: **menos de 2 GB**.

El simulacro (punto 4) te da la cifra exacta para tu trabajo antes de escribir nada.

> **De dónde sale.** Cada fotograma sin pérdida ocupa como mucho 6 bytes por píxel (es
> una cuenta, no una medida): un fotograma 4K UHD, 50 MB; uno HD, 12 MB. Medido sobre
> material sintético, ocupan entre 5.0 y 5.3 bytes por píxel, así que el máximo está
> cerca de lo real. La hoja de contacto, 185 KB. Todo en `pruebas/coste_medido.json`,
> que se regenera con `.venv/bin/python pruebas/medir_coste.py`.

---

## 3 · Cuánto tarda

**La cuenta:**

| Qué | Cuánto |
|---|---|
| por cada **minuto de máster** (HD, 25 fps) | **unos 34 s** (8 s de leerlo y 26 s de buscar) |
| por cada **minuto de brutos** en 4K UHD | **unos 29 s** |
| por cada **minuto de brutos** en HD | **unos 8 s** |
| por cada **plano** encontrado | **unos 11 s** (sacar el grado es lo que más tarda: 9 s) |
| T5: por cada **pareja de planos** | **0.3 s**, y las parejas son planos × (planos − 1) |

Ejemplos, con la cuenta hecha por el propio programa:

- Máster HD de **1 minuto**, **15 brutos 4K** de 30 s: **unos 8 minutos**.
- Máster HD de **2 minutos**, **30 brutos 4K** de 40 s: **unos 21 minutos** (casi la mitad
  es leer los brutos).

> **Una advertencia honesta.** Estos tiempos se midieron en este Mac con vídeo sintético
> en ProRes. Los ficheros de cámara reales (el H.265 de 10 bits de la FX3, por ejemplo) se
> leen a otra velocidad, y **no se sabe si más rápido o más lento**. Tómalo como una
> orientación, no como una promesa.

Mientras trabaja, la memoria que usa es pequeña: unos 15 MB por minuto de máster y
10 MB por minuto de brutos.

---

## 4 · El comando exacto

Abre **Terminal** y entra en la carpeta del programa:

```
cd "/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color"
```

> **Truco para las rutas:** escribe el comando hasta donde va la ruta y **arrastra el
> fichero o la carpeta desde el Finder a la ventana de Terminal**: se pega sola. Déjala
> entre comillas si tiene espacios.

Las rutas de estos ejemplos son **inventadas** (`DISCO_DE_EJEMPLO`, `TRABAJO_DE_EJEMPLO`):
pon las tuyas.

### Primero, el simulacro (no escribe nada)

```
.venv/bin/python pruebas/primera_real.py \
    --master "/Volumes/DISCO_DE_EJEMPLO/TRABAJO_DE_EJEMPLO/MASTER_DE_EJEMPLO.mov" \
    --brutos "/Volumes/DISCO_DE_EJEMPLO/TRABAJO_DE_EJEMPLO/BRUTOS_DE_EJEMPLO" \
    --espacio-brutos slog3_sgamut3cine
```

Te dice qué ficheros leería, qué no puede leer y por qué, qué carpetas protege, cuánto
espacio ocuparía y cuánto tardaría. **No crea ni la carpeta de trabajo.** Revisa sobre todo:

- que la lista de brutos es la que esperas;
- que el espacio de color de cada fichero es el correcto;
- que el espacio y el tiempo te cuadran.

Se pueden pasar varias carpetas o ficheros sueltos detrás de `--brutos`, separados por un
espacio.

### Después, de verdad

**El mismo comando**, añadiendo `--ejecutar` al final:

```
.venv/bin/python pruebas/primera_real.py \
    --master "/Volumes/DISCO_DE_EJEMPLO/TRABAJO_DE_EJEMPLO/MASTER_DE_EJEMPLO.mov" \
    --brutos "/Volumes/DISCO_DE_EJEMPLO/TRABAJO_DE_EJEMPLO/BRUTOS_DE_EJEMPLO" \
    --espacio-brutos slog3_sgamut3cine \
    --ejecutar
```

Se puede parar en cualquier momento con **Ctrl + C**. Tus discos no se tocan en ningún
caso; como mucho queda una carpeta a medias dentro de `pruebas/trabajo/`, que puedes
borrar.

La ayuda completa, con todas las opciones: `.venv/bin/python pruebas/primera_real.py --help`

---

## 5 · Qué vas a ver, y cómo leer las cifras

### En la Terminal

Cinco pasos: leer el máster, leer los brutos, buscar cada bruto en el máster, sacar
fotogramas y medir T1, y T5. Al final, la ruta del informe:
`pruebas/trabajo/<fecha-hora>/informe.md`.

### En la carpeta del informe

- **`informe.md`**: el informe. Se abre con cualquier editor de texto.
- **`hojas/`**: una imagen por plano, **el bruto recortado a la izquierda y el máster a la
  derecha**. **Mira unas cuantas antes de creerte ninguna cifra**: tiene que ser la misma
  imagen con distinto color. Si no lo es, las cifras de ese plano no valen.
  Las marcadas `DESCARTADA` son planos que el programa no se atrevió a medir.
- **`fotogramas/`**: los fotogramas sin pérdida con los que se midió.
- **`informe.json`**: lo mismo en formato para programas.

### Cómo leer ΔE2000

Es la diferencia de color que ve un ojo:

| ΔE2000 | Qué significa |
|---|---|
| menos de 1 | no se distingue |
| de 1 a 3 | se nota comparando lado a lado |
| más de 3 | se ve |

Cada cifra sale en dos versiones: el **máximo** (el peor píxel) y el **medio**. El
**máximo va primero**, porque es el que suspende.

### Las tres cifras

**T1: el grado de un plano, aplicado a ese mismo plano.** Es el techo: si aquí sale mal,
no hay grado que llevarse de ese plano. En sintético el proyecto exige un máximo por
debajo de 3; el informe pone ese límite al lado, leído del registro de cifras del proyecto.

**T5: el grado de un plano, aplicado a los demás.** Es lo que de verdad importa. Hoy no
hay límite escrito para T5: es la primera vez que se mide.

**Cobertura del cubo:** qué parte del LUT tiene datos de verdad. Un plano solo cubre muy
poco (en sintético, alrededor del 1 % o menos) y el resto lo rellena el programa. No es un fallo; es
lo que hay que tener presente cuando se entrega un `.cube`.

### Qué es un buen resultado y qué es uno malo

**Nadie lo sabe todavía con material real: esta prueba es la primera.** Lo que sí se puede
decir:

- **Bueno:** T1 medio por debajo de 1, y el T1 máximo **lejos de bordes** bajo. Las hojas
  de contacto enseñan la misma imagen.
- **Malo:** T1 medio por encima de 1 en muchos planos, o máximos altos **también lejos de
  bordes**.
- **Máximo alto pero bajo lejos de bordes:** el problema son los bordes (un píxel de borde
  mezcla dos colores y el máster se reescaló con un filtro que no conocemos), **no el
  grado**. En sintético pasa incluso aplicando el grado exacto.

### Si T1 sale bien pero T5 sale mal

Significa que **cada plano, por separado, se puede reproducir, pero el grado de uno no
sirve para otro.** Hay dos motivos posibles, y el informe te deja distinguirlos:

1. **Se coloreó plano a plano**: cada plano lleva su corrección. Entonces un solo LUT para
   todo el trabajo no existe, y la herramienta tendrá que trabajar plano a plano.
2. **El plano de origen no vio esos colores**: el LUT de un interior no sabe qué hacer con
   un cielo, y se lo inventa. Compara en el informe la fila «sólo en colores que el plano
   de origen vio» con la de todos los píxeles. **Si en los colores vistos sale bien y en el
   total mal, es esto**, y la salida pasaría por sacar el grado de varios planos a la
   vez (hoy la herramienta lo saca de un plano cada vez).

---

## 6 · Lo que el programa garantiza que NO hace

- **No escribe en los discos de origen.** Todo lo que escribe pasa por una única puerta
  que sólo deja escribir dentro de `pruebas/trabajo/` del propio programa, nunca dentro de
  las carpetas del máster o de los brutos, y nunca en ningún disco externo. Además nunca
  sobreescribe nada. Está en el código (`pruebas/guarda.py`), y hay tests que lo prueban
  ejecutando el programa de verdad contra una carpeta bloqueada y comparando antes y
  después, fichero a fichero.
- **No busca material por su cuenta.** Sólo lee las rutas que le das. Si le pasas una
  carpeta, la recorre a ella y a sus subcarpetas, sin salir. Se niega a recorrer cosas como
  `/Volumes` entero o tu carpeta personal.
- **No se conecta a DaVinci Resolve.** Ni lo abre ni lo necesita.
- **No sale a internet.**
- **No se sube a GitHub** lo que extrae: la carpeta `pruebas/trabajo/` está excluida.

### Cómo comprobarlo tú mismo

**Antes de ejecutar**, apunta la hora exacta, por ejemplo `2026-09-20 10:15`.

**Después**, en Terminal, pide la lista de todo lo que haya cambiado en la carpeta de
brutos desde esa hora (cambia la ruta y la hora por las tuyas):

```
find "/Volumes/DISCO_DE_EJEMPLO/TRABAJO_DE_EJEMPLO/BRUTOS_DE_EJEMPLO" -newermt "2026-09-20 10:15"
```

Haz lo mismo con la carpeta del máster. **Si no aparece nada, no se ha tocado nada.**

Si aparece un `.DS_Store`, ese lo escribe el propio Finder cuando abres la carpeta, no el
programa. **Si aparece cualquier otra cosa, no sigas y avísame.**

Y si quieres ver la prueba de los tests:

```
.venv/bin/python -m pytest tests/test_pruebas_primera_real.py -s -k byte
```

Tiene que terminar diciendo `ORIGEN: identico byte a byte`.

---

## 7 · Si algo sale raro

| Qué ves | Qué suele ser | Qué hacer |
|---|---|---|
| Casi todos los planos **descartados**, con encajes de 0.8 o más | los umbrales están ajustados con material sintético y son demasiado estrictos para el real | nada: mándame el informe, se ajustan con estos números |
| Descartados con «**poca diferencia con otro bruto**» | tomas casi iguales, o el mismo clip dos veces | mira si hay copias duplicadas entre los brutos |
| Un bruto «**no se puede leer**» | RAW, o un formato que no sabe abrir | exporta ese clip a ProRes entero y sin corrección |
| **Colores muy raros** en todas las cifras (T1 alto en todo) | el espacio de color de los brutos no es el que se ha dicho | revisa `--espacio-brutos` en el simulacro |
| Tarda **mucho más** de lo estimado | los ficheros de cámara se leen más despacio que el sintético | déjalo terminar; o para con Ctrl + C, no pasa nada |
| Sale **ERROR** | un fallo del programa | se guarda en `error.txt` dentro de la carpeta del informe |

### Qué mandar

De la carpeta `pruebas/trabajo/<fecha-hora>/`:

- `informe.md` e `informe.json`;
- la carpeta `hojas/` (son pequeñas);
- `error.txt`, si lo hay;
- y copia y pega lo que salió en la Terminal.

**No hace falta mandar `fotogramas/`**: pesan mucho, y son imágenes de un trabajo de un
cliente.
