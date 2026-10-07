# ACTUALIZACIONES — SIDEBFLMS COLOR

Cambios que afectan a **cómo se ve o se usa la app**, en orden inverso (lo último,
arriba). Para el detalle técnico, medidas y qué hacer al actualizar, ver
`BITACORA.md`.

## SUITE 2/3 · 2026-10-07 — cabecera de marca, botones y pastilla de la suite

- **Cabecera de marca** en la esquina superior izquierda: casete + wordmark SIDEBFLMS
  (la B en naranja) y debajo «COLOR» en Akira (o Montserrat 800 si Akira no está).
- **Títulos de pantalla** en Akira, **sin tildes** (el archivo no las tiene): `CLIPS`,
  `COMPARAR`, `APLICAR`, `REVERSE`, `PASO A PASO`. La navegación del carril sigue con el
  texto completo («Antes / después», «Ingeniería inversa»).
- **Botones en píldora**, con el texto en frase (no en mayúsculas). El botón primario es
  `#bb4223` y al pasar el ratón sube a `#e8451d`, como en la web.
- **Insignia de confianza en píldora**, sin perder su forma (relleno + 3 barras /
  contorno + 2 / discontinuo + 1).
- **Conexión con Resolve por forma**: disco lleno (conectado) / contorno discontinuo
  (desconectado), además de la palabra.
- **Fila seleccionada de la tabla**: un filete naranja de 2 px a la izquierda y un velo
  neutro, en vez de un bloque naranja.
- **Ventana:** el mínimo sube de alto, de 738 a **745** px (el ancho se queda en 1017).

## SUITE 1/3 · 2026-10-07 — colores, tipografía, radios y cristal de la suite SIDEBFLMS

Las apps de SIDEBFLMS pasan a parecer una suite: los colores de sidebflms.com y su
modo cristal, manteniendo la personalidad de cada app.

- **Colores:** fondo antracita `#1e1e1e` (ya no el negro cálido), texto crema
  `#f2ece4`, texto secundario sólido `#938e89` (se acabaron las opacidades de texto).
  Los naranjas de marca no cambian.
- **Tipografía:** Montserrat en todo (texto, rótulos y cifras); **ya no hay
  monoespaciada**: las cifras van en Montserrat tabular y alinean a la derecha igual.
  Los títulos usan **Akira Expanded** si está disponible, y si no, Montserrat 800.
- **Cristal:** los paneles son translúcidos con filo degradado (naranja abajo a la
  derecha), brillo superior y un fondo con curvas de nivel. En Qt es una
  **aproximación** (ver `BITACORA.md`).
- **Radios:** 8 px en controles, 16 px en paneles.
- **Se queda igual:** confianza por forma, rombo de desajuste, cero rojo, cifras a la
  derecha, carril de 186 px, y el entorno neutro alrededor de la imagen.
- **Ventana:** el mínimo pasa de 1016×742 a **1017×738**.

**Si eres Mario y quieres Akira en tu Mac:** copia
`SIDEBFLMS TIPOGRAFIA (c SIDEBFLMS).otf` a `gui/fuentes/` (está en `.gitignore`: no se
sube) o instálala en el sistema. Sin ella la app funciona igual, con Montserrat 800.
