# IDENTIDAD VISUAL — SIDEBFLMS COLOR

Sistema en producción de SIDEB FILMS. **Estos valores son literales y cerrados.**
Si algo pide un color que no está aquí, no se improvisa: se anota en `BITACORA.md`
y se usa el más cercano de la lista.

## Color

```
Marca         brand-500  #e8451d   acento / foco / activo
              brand-600  #bb4223   fondo de boton primario (el 500 no pasa AA)
              brand-400  #ff6a3d   texto e iconos de marca sobre oscuro
              brand-50   #fdf4ee
Acento frio   cyan-glow  #3ad6cf   unico, para datos secundarios
Superficies   fondo      #0a0908
              hondo      #0d0b08
              panel      #131110
              cristal    #16130f
```

Las superficies son **cálidas**, más rojo que azul. **Nada de negro puro.**

## Los tokens de estado NO son nuestros

```
Disponible #00d492 · Reservado #ffb900 · Fuera #ff6a3d
En taller  #3ad6cf · De baja   #71717b
```

Pastilla = fondo al 12%, borde al 25%, texto pleno. **Están reservados al inventario
y no se reutilizan para otra cosa.** En SIDEBFLMS COLOR:

- **La confianza por clip y el estado de cada módulo NO usan estos tokens.**
  Se diferencian **por forma** (relleno, contorno, borde discontinuo) dentro de la
  paleta de marca.

> **Un roce que hay que conocer:** `#ff6a3d` es a la vez `brand-400` y el estado
> «Fuera». Interpretación que se ha tomado aquí, y que Mario puede revocar: lo
> reservado es **el tratamiento de pastilla**, no el hex. Usar `#ff6a3d` como color
> de *texto o icono de marca sobre oscuro* es su función declarada y se usa. Lo que
> no se hace nunca es pintar una pastilla `#ff6a3d` con fondo al 12% y borde al 25%,
> porque eso sí diría «Fuera» a cualquiera que conozca el inventario.

## El rojo no es color de error

**Regla firme.** El naranja es el color de marca, no una alarma. El rojo sólo para
acciones destructivas. Un aviso, una advertencia o un valor bajo de confianza **no**
se pintan de rojo: se distinguen por forma y por texto.

## Tipografía

```
Inter                      texto
Chakra Petch 500/600/700   titulares y rotulos EN MAYUSCULAS,
                           tracking 0.15-0.18em, 10-11px
JetBrains Mono             cifras, codigos, IDs
```

**Toda cifra va en monoespaciada.** Sin excepción: ΔE, porcentajes de confianza,
valores de CDL, tamaños de LUT, identificadores de clip.

### Ninguna de las tres está instalada en este Mac

Comprobado con `QFontDatabase`: `Inter` NO, `Chakra Petch` NO, `JetBrains Mono` NO.
No se pueden descargar (límite de red de la noche: sólo PyPI). Las alternativas que
usa el código, en este orden, son:

| Marca | Alternativa | Qué se pierde |
|---|---|---|
| Inter | Helvetica Neue | Poco. Métricas parecidas, algo más de contraste de trazo. |
| Chakra Petch | Helvetica Neue en mayúsculas con el mismo tracking | **Bastante.** Chakra Petch es condensada y técnica; Helvetica es neutra. Los rótulos se ven más anchos y menos «de marca». |
| JetBrains Mono | Menlo | Poco. Ambas monoespaciadas de anchura parecida. |

**Consecuencia para las capturas de esta noche: NO enseñan la tipografía real de la
marca.** El layout, el color, los tamaños y el tracking sí son los buenos. Si Mario
instala las tres familias, la app las coge sola: la pila de fuentes ya las pide
primero.

## Capturas

Con `QT_QPA_PLATFORM=offscreen`, cada pantalla en **tres anchuras**: 1440, 1024 y
**la anchura mínima real de la ventana**. Esa última no es opcional: en la app
hermana de ingest el recorte de texto al redimensionar ha sido un fallo recurrente.

**Hay que mirar las capturas.** Si hay texto cortado sin elipsis, es un bug y se
arregla; no se entrega la captura y ya.
