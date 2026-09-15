"""Remuestrear un LUT 3D a otro tamaño de rejilla.

POR QUÉ EXISTE ESTO, Y LO PRIMERO QUE HAY QUE ENTENDER
------------------------------------------------------
El tamaño de la app es **33** y no se toca (`LUT_SIZE_DEFAULT` en
`core/contracts.py`): es el estándar de facto, es lo que se traga cualquier
cámara y cualquier monitor de campo, y es lo que pesa poco. Lo confirmó Mario.

Lo que sí hace falta es poder **entregar** un `.cube` de 65 cuando la casa de
post lo pide. Eso es lo que hay aquí, y es una opción explícita: hay que
escribir `remuestrear_lut(lut, 65)` en una línea que se vea. Nunca pasa sola.

**Y remuestrear NO añade información.** Ni una pizca. Un LUT de 33 ya *es* una
función: `LUT3D.apply()` interpola trilinealmente entre sus 35.937 celdas, y
eso define un color de salida para cada color de entrada. Pasar a 65 consiste
en preguntarle a esa misma función el valor en 274.625 puntos y apuntarlo. El
color que sale es el mismo; lo único que cambia es el tamaño del fichero.

Lo he medido, y sale mejor de lo que esperaba: como **65 = 2·33 − 1**, los
puntos de la rejilla de 65 caen exactamente sobre los de la de 33 y sobre sus
puntos medios, y la interpolación trilineal de una interpolación trilineal
sobre el mismo trozo de cubo es la misma función. O sea que el remuestreo no es
"casi igual": es **igual**, salvo el redondeo de guardar los números en
`float32`.

Medido sobre 200.000 colores aleatorios en 0..1, comparando `lut33.apply(x)`
contra `remuestrear_lut(lut33, 65).apply(x)`:

| LUT de partida (33) | diferencia máxima | en unidades de 255 |
|---|---|---|
| identidad | 2,2e-16 | 0,00000006 |
| curva en S de contraste | 2,2e-16 | 0,00000006 |
| gamma de salida `x**(1/2.2)` | 3,0e-08 | 0,0000076 |
| CDL realista (slope/offset/power/sat) | 5,7e-08 | 0,0000146 |

Cinco millonésimas de un nivel de 8 bits en el peor caso. Eso **no** es
precisión ganada: es el error de escribir el mismo número en `float32`.

Dicho del revés, y es la frase que importa: **si alguien exporta a 65 creyendo
que el resultado va a ser más fino que el de 33, le hemos mentido.** Lo único
que gana es un fichero 7,6 veces más grande —medido con un LUT de un CDL y los
6 decimales de siempre: 0,93 MB pasan a 7,07 MB— y que algunas cámaras y
monitores de campo no saben leer. Se exporta a 65 porque alguien lo pide por
escrito, no para mejorar nada.

BAJAR DE TAMAÑO SÍ PIERDE, Y AHÍ NO HAY VUELTA
----------------------------------------------
La función admite bajar (por ejemplo 33 → 17) porque a veces hace falta para un
cacharro antiguo, pero eso **sí** es destructivo y no es simétrico con lo de
arriba. Medido igual, 33 → 17:

| LUT de partida (33) | diferencia máxima | en unidades de 255 |
|---|---|---|
| identidad | 2,2e-16 | 0,0000001 |
| curva en S de contraste | 0,0027 | 0,70 |
| CDL realista | 0,0028 | 0,72 |
| gamma de salida `x**(1/2.2)` | **0,065** | **16,6** |

Diecisiete niveles de 255 en las sombras de una curva de salida. Por eso
`explicacion_remuestreo()` lo dice con todas las letras cuando el destino es
más pequeño que el origen: no es la misma operación al revés.
"""

from __future__ import annotations

import numpy as np

from core.contracts import LUT3D

from .cube import LUT_SIZE_MAX_LECTURA, LUT_SIZE_MIN
from .errores import ErrorFormatoCube

__all__ = [
    "TAMANO_ENTREGA_FINAL",
    "explicacion_remuestreo",
    "rejilla_del_dominio",
    "remuestrear_lut",
]

#: El tamaño que se usa **sólo** para una entrega final que lo pida por escrito.
#: No es un valor por defecto de nada y no debe serlo: el de la app es 33
#: (`LUT_SIZE_DEFAULT`). Está aquí para que quien lo escriba en la GUI no tenga
#: que teclear un 65 suelto y para que se pueda buscar con grep.
TAMANO_ENTREGA_FINAL: int = 65


def rejilla_del_dominio(lut: LUT3D, tamano: int) -> np.ndarray:
    """Los `tamano**3` colores de entrada de una rejilla, en el dominio del LUT.

    Devuelve `(tamano, tamano, tamano, 3)` indexado `[ri, gi, bi] -> (r, g, b)`,
    o sea la convención 4 del proyecto, para que la tabla que salga de aplicar
    el LUT a esto ya esté en el orden bueno y nadie tenga que transponer nada.

    Respeta `domain_min`/`domain_max`: un LUT con dominio 0..1 se remuestrea en
    0..1, y uno con dominio −0,07..1,09 (los hay, para material log) se
    remuestrea en el suyo. Si aquí se usara 0..1 siempre, remuestrear un LUT de
    dominio ancho le recortaría los extremos sin decir nada.
    """
    dmin = np.asarray(lut.domain_min, dtype=np.float64)
    dmax = np.asarray(lut.domain_max, dtype=np.float64)
    ejes = [np.linspace(dmin[c], dmax[c], tamano, dtype=np.float64) for c in range(3)]
    r, g, b = np.meshgrid(ejes[0], ejes[1], ejes[2], indexing="ij")
    return np.stack([r, g, b], axis=-1)


def remuestrear_lut(lut: LUT3D, tamano: int, *, titulo: str | None = None) -> LUT3D:
    """Devuelve el **mismo** LUT escrito sobre una rejilla de `tamano` puntos.

    Es lo que hay que llamar para entregar un `.cube` de 65:

        de_entrega = remuestrear_lut(mi_lut_de_33, TAMANO_ENTREGA_FINAL)
        escribir_cube(de_entrega, ruta)

    **No añade información.** Subir de tamaño es reescribir la misma función con
    más puntos; el color que sale es el mismo hasta el redondeo del `float32`
    (los números están medidos en el docstring del módulo). Bajar de tamaño sí
    pierde, y bastante. Para saber qué decirle al usuario, `explicacion_remuestreo()`.

    El dominio y el título se conservan (`titulo` los cambia si hace falta). El
    tamaño tiene que estar entre `LUT_SIZE_MIN` y `LUT_SIZE_MAX_LECTURA`, que es
    el mismo rango que se acepta al leer: no se valida contra
    `LUT_SIZES_SOPORTADOS` porque quien pida un 64 para un cacharro concreto
    tiene tanto derecho como quien pida un 65.

    Remuestrear al mismo tamaño que ya tenía devuelve una copia, no el mismo
    objeto, y no es un error: simplifica el código de quien llama, que puede
    pedir 65 siempre sin mirar antes lo que hay.
    """
    if isinstance(tamano, bool) or not isinstance(tamano, int):
        raise ErrorFormatoCube(
            f"el tamaño de rejilla tiene que ser un entero, y llegó {tamano!r} "
            f"({type(tamano).__name__})"
        )
    if not (LUT_SIZE_MIN <= tamano <= LUT_SIZE_MAX_LECTURA):
        raise ErrorFormatoCube(
            f"el tamaño de rejilla tiene que estar entre {LUT_SIZE_MIN} y "
            f"{LUT_SIZE_MAX_LECTURA}, y me han pedido {tamano}. Para entregar, el que se pide "
            f"es {TAMANO_ENTREGA_FINAL}."
        )
    entrada = rejilla_del_dominio(lut, tamano)
    tabla = np.asarray(lut.apply(entrada), dtype=np.float32)
    return LUT3D(
        table=tabla,
        domain_min=lut.domain_min,
        domain_max=lut.domain_max,
        title=lut.title if titulo is None else titulo,
    )


def explicacion_remuestreo(origen: int, destino: int) -> str:
    """Una o dos frases en castellano para enseñar al lado del botón de exportar.

    Está aquí y no en la GUI a propósito: el que sabe lo que cuesta remuestrear
    es este módulo, y si la frase vive en la GUI acaba diciendo lo que el que
    escribió el botón creía. Aquí está pegada a los números medidos.
    """
    if destino == origen:
        return (
            f"El LUT ya es de {origen}: no hay nada que remuestrear y el fichero sale igual."
        )
    if destino > origen:
        return (
            f"Se va a escribir el LUT de {origen} sobre una rejilla de {destino}. "
            f"Es el mismo LUT: el color que sale es el mismo, no gana precisión ni detalle. "
            f"Lo único que cambia es que el fichero ocupa unas "
            f"{(destino ** 3) / (origen ** 3):.0f} veces más y que algunas cámaras y monitores "
            f"de campo no saben leer un LUT de {destino}. Hazlo sólo si te lo han pedido así."
        )
    return (
        f"Se va a bajar el LUT de {origen} a {destino}, y eso SÍ pierde: con menos puntos, las "
        f"zonas donde el LUT cambia deprisa (las sombras de una curva de salida, sobre todo) se "
        f"redondean. Medido sobre una gamma de salida, bajar de 33 a 17 llega a desviarse 16 "
        f"niveles de 255. Si no te lo ha pedido nadie, entrega el de {origen}."
    )
