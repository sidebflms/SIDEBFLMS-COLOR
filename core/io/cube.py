"""Lectura y escritura de LUT en formato `.cube` (Iridas / Adobe).

EL ORDEN DE LOS EJES, QUE ES LO ÚNICO QUE IMPORTA DE VERDAD AQUÍ
----------------------------------------------------------------
Convención 4 de `CONTRATOS.md`: `LUT3D.table` se indexa `[ri, gi, bi] -> (r, g, b)`,
o sea que **el eje 0 es el ROJO**.

En el FICHERO `.cube`, en cambio, el rojo es el que varía más rápido: las tres
primeras líneas de un LUT de tamaño 3 son (r=0,g=0,b=0), (r=1,g=0,b=0),
(r=2,g=0,b=0). Dicho de otra forma, el índice de línea es
`((bi * N) + gi) * N + ri`.

Por lo tanto:

* **escribir**: `table.transpose(2, 1, 0, 3).reshape(-1, 3)`
* **leer**: `datos.reshape(N, N, N, 3).transpose(2, 1, 0, 3)`

(las dos son la misma permutación, que es involutiva: `(2,1,0)` aplicada dos
veces es la identidad).

Si esto se invierte, el proyecto entero produce LUT con el rojo y el azul
cambiados y nadie se entera hasta que se ve una imagen azul donde debería ser
roja. Por eso `tests/test_io_cube.py::test_ida_y_vuelta_un_lut_que_solo_toca_el_rojo`
existe y por eso no se toca.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

from core.contracts import LUT3D, LUT_SIZE_DEFAULT

from .errores import ErrorFormatoCube, describe_ruta

__all__ = [
    "LUT_SIZE_MIN",
    "LUT_SIZE_MAX_LECTURA",
    "MAX_BYTES_CUBE",
    "leer_cube",
    "escribir_cube",
    "cube_desde_texto",
    "cube_a_texto",
    "orden_fichero_desde_tabla",
    "tabla_desde_orden_fichero",
]

#: Tamaño mínimo legal de rejilla. Lo impone `LUT3D` (con 1 muestra por eje no
#: hay nada que interpolar).
LUT_SIZE_MIN: int = 2

#: Tamaño máximo que aceptamos LEER. La app sólo produce 17/33/65, pero por ahí
#: circulan LUT de 64 y de 128 hechos con otras herramientas y sería absurdo no
#: poder abrirlos.
#:
#: Por qué 129 y no más: 129**3 = 2.146.689 celdas x 3 canales x 4 bytes = 25,7 MB
#: de tabla en float32, que es asumible. El siguiente escalón habitual (256) son
#: 201 MB **por LUT**, y un `.cube` declarando `LUT_3D_SIZE 4096` pediría 824 GB.
#: El límite no es estético: es lo que evita que un fichero de 40 bytes tumbe la
#: aplicación.
LUT_SIZE_MAX_LECTURA: int = 129

#: Tamaño máximo del fichero en bytes. Un `.cube` de 129 pesa ~64 MB con líneas
#: de 30 caracteres; 128 MB deja margen de sobra para ficheros con comentarios y
#: mucho espaciado, y corta en seco un fichero de texto de 10 GB.
MAX_BYTES_CUBE: int = 128 * 1024 * 1024

#: Caracteres que tratamos como separador además del espacio en blanco. Hay
#: exportadores que separan con comas o con punto y coma.
_SEPARADORES_EXTRA = ",;"


# ---------------------------------------------------------------------------
# La permutación de ejes (convención 4)
# ---------------------------------------------------------------------------


def orden_fichero_desde_tabla(table: np.ndarray) -> np.ndarray:
    """`(N, N, N, 3)` indexada [r, g, b] -> `(N**3, 3)` en orden de fichero."""
    return np.asarray(table).transpose(2, 1, 0, 3).reshape(-1, 3)


def tabla_desde_orden_fichero(datos: np.ndarray, size: int) -> np.ndarray:
    """`(N**3, 3)` en orden de fichero -> `(N, N, N, 3)` indexada [r, g, b]."""
    return np.asarray(datos).reshape(size, size, size, 3).transpose(2, 1, 0, 3)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def _leer_texto(ruta: Path) -> str:
    """Lee el fichero como texto, o explica en castellano por qué no puede."""
    nombre = describe_ruta(ruta)
    if not ruta.exists():
        raise ErrorFormatoCube(f"no existe el fichero '{ruta}'")
    if ruta.is_dir():
        raise ErrorFormatoCube(f"'{nombre}' es una carpeta, no un fichero .cube")
    try:
        tam = ruta.stat().st_size
    except OSError as exc:  # pragma: no cover - depende del sistema de ficheros
        raise ErrorFormatoCube(f"no puedo consultar '{nombre}': {exc}") from exc
    if tam == 0:
        raise ErrorFormatoCube(f"el fichero '{nombre}' está vacío")
    if tam > MAX_BYTES_CUBE:
        mb = tam / (1024 * 1024)
        raise ErrorFormatoCube(
            f"'{nombre}' ocupa {mb:.0f} MB y el máximo para un .cube son "
            f"{MAX_BYTES_CUBE // (1024 * 1024)} MB; no parece un LUT"
        )
    if not os.access(ruta, os.R_OK):
        raise ErrorFormatoCube(f"no tengo permiso para leer '{nombre}'")
    try:
        crudo = ruta.read_bytes()
    except PermissionError as exc:
        raise ErrorFormatoCube(f"no tengo permiso para leer '{nombre}'") from exc
    except OSError as exc:
        raise ErrorFormatoCube(f"no puedo leer '{nombre}': {exc}") from exc

    if b"\x00" in crudo[:4096]:
        raise ErrorFormatoCube(
            f"'{nombre}' es un fichero binario, no un .cube de texto "
            "(he encontrado bytes nulos en la cabecera)"
        )
    for bom in (b"\xff\xfe", b"\xfe\xff"):
        if crudo.startswith(bom):
            raise ErrorFormatoCube(
                f"'{nombre}' está en UTF-16; un .cube tiene que ser texto ASCII/UTF-8"
            )
    try:
        # utf-8-sig se come el BOM de UTF-8 si lo hay.
        return crudo.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ErrorFormatoCube(
            f"'{nombre}' no es texto UTF-8 válido (byte {exc.start}); no parece un .cube"
        ) from exc


#: Una palabra clave del formato. `nan` e `inf` también encajan aquí, por eso
#: siempre se comprueba después si el token es en realidad un número.
_ES_IDENTIFICADOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _es_numero(texto: str) -> bool:
    try:
        float(texto)
    except ValueError:
        return False
    return True


def _trocear(linea: str) -> list[str]:
    """Parte una línea en campos aguantando tabuladores, comas y punto y coma."""
    for sep in _SEPARADORES_EXTRA:
        linea = linea.replace(sep, " ")
    return linea.split()


def _numero(texto: str, *, nombre: str, n_linea: int, que: str) -> float:
    try:
        valor = float(texto)
    except ValueError as exc:
        raise ErrorFormatoCube(
            f"'{nombre}', línea {n_linea}: {que} tiene que ser un número, llegó '{texto}'"
        ) from exc
    if not np.isfinite(valor):
        raise ErrorFormatoCube(
            f"'{nombre}', línea {n_linea}: {que} no es un número finito ('{texto}')"
        )
    return valor


def _entero(texto: str, *, nombre: str, n_linea: int, que: str) -> int:
    try:
        return int(texto)
    except ValueError as exc:
        raise ErrorFormatoCube(
            f"'{nombre}', línea {n_linea}: {que} tiene que ser un número entero, llegó '{texto}'"
        ) from exc


def _trio(campos: list[str], *, nombre: str, n_linea: int, que: str) -> tuple[float, float, float]:
    if len(campos) == 1:  # algunos exportadores escriben un solo valor escalar
        v = _numero(campos[0], nombre=nombre, n_linea=n_linea, que=que)
        return (v, v, v)
    if len(campos) != 3:
        raise ErrorFormatoCube(
            f"'{nombre}', línea {n_linea}: {que} necesita 3 números (o 1), llegaron {len(campos)}"
        )
    vals = [_numero(c, nombre=nombre, n_linea=n_linea, que=que) for c in campos]
    return (vals[0], vals[1], vals[2])


def leer_cube(
    ruta: str | Path,
    *,
    tamano_3d_desde_1d: int = LUT_SIZE_DEFAULT,
    tamano_maximo: int = LUT_SIZE_MAX_LECTURA,
) -> LUT3D:
    """Lee un `.cube` y devuelve un `LUT3D` con la convención 4 del proyecto.

    Soporta `LUT_3D_SIZE`, `TITLE`, `DOMAIN_MIN`, `DOMAIN_MAX`,
    `LUT_3D_INPUT_RANGE`, comentarios `#`, líneas en blanco y separadores raros
    (tabuladores, comas, punto y coma).

    `LUT_1D_SIZE`: se **convierte a 3D**, no se rechaza. Un LUT 1D es una curva
    por canal, o sea `f_r`, `f_g`, `f_b` independientes; el cubo equivalente es
    `tabla[ri, gi, bi] = (f_r(ri/(N-1)), f_g(gi/(N-1)), f_b(bi/(N-1)))`. Se
    remuestrea a `tamano_3d_desde_1d` (33 por defecto) porque los LUT 1D suelen
    venir con 1024 o 4096 entradas y un cubo de 1024 no cabe en memoria. Hay
    pérdida en la curva; está documentada en `NOTAS.md`.

    Levanta `ErrorFormatoCube` (con mensaje en castellano) ante cualquier
    fichero corrupto, vacío, binario, sin permisos, inexistente o absurdo.
    """
    ruta = Path(ruta)
    return cube_desde_texto(
        _leer_texto(ruta),
        nombre=describe_ruta(ruta),
        tamano_3d_desde_1d=tamano_3d_desde_1d,
        tamano_maximo=tamano_maximo,
    )


def cube_desde_texto(
    texto: str,
    *,
    nombre: str = "(en memoria)",
    tamano_3d_desde_1d: int = LUT_SIZE_DEFAULT,
    tamano_maximo: int = LUT_SIZE_MAX_LECTURA,
) -> LUT3D:
    """Igual que `leer_cube` pero sobre una cadena ya leída.

    Existe porque el bundle `.sidebcolor` lleva los `.cube` dentro de un zip y
    no tiene sentido pasarlos por el disco para volver a leerlos.
    """
    size_3d: int | None = None
    size_1d: int | None = None
    linea_size = 0
    titulo: str | None = None
    dmin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    dmax: tuple[float, float, float] = (1.0, 1.0, 1.0)
    filas: list[tuple[float, float, float]] = []
    max_filas: int | None = None

    for n_linea, linea_cruda in enumerate(texto.splitlines(), start=1):
        linea = linea_cruda.split("#", 1)[0].strip()
        if not linea:
            continue
        campos = _trocear(linea)
        clave = campos[0].upper()

        if clave in ("LUT_3D_SIZE", "LUT_1D_SIZE"):
            if len(campos) < 2:
                raise ErrorFormatoCube(f"'{nombre}', línea {n_linea}: {clave} sin valor")
            valor = _entero(campos[1], nombre=nombre, n_linea=n_linea, que=clave)
            anterior = size_3d if clave == "LUT_3D_SIZE" else size_1d
            if anterior is not None and anterior != valor:
                # D-2 de la revisión de la ola 1. Rechazábamos `LUT_3D_SIZE` y
                # `LUT_1D_SIZE` a la vez con un mensaje claro, pero dos
                # `LUT_3D_SIZE` distintos se tragaban en silencio quedándose con
                # el último. Es la MISMA ambigüedad (un fichero cortado y pegado
                # por un exportador roto) y el mismo riesgo: si el que manda es
                # el segundo, la tabla que se lee no es la que el fichero dice.
                raise ErrorFormatoCube(
                    f"'{nombre}', línea {n_linea}: {clave} está declarado dos veces con "
                    f"valores distintos ({anterior} en la línea {linea_size} y {valor} aquí); "
                    "no sé cuál de los dos es el bueno"
                )
            if clave == "LUT_3D_SIZE":
                size_3d = valor
            else:
                size_1d = valor
            linea_size = n_linea
            continue
        if clave == "TITLE":
            titulo = linea[len("TITLE") :].strip().strip('"').strip()
            continue
        if clave == "DOMAIN_MIN":
            dmin = _trio(campos[1:], nombre=nombre, n_linea=n_linea, que="DOMAIN_MIN")
            continue
        if clave == "DOMAIN_MAX":
            dmax = _trio(campos[1:], nombre=nombre, n_linea=n_linea, que="DOMAIN_MAX")
            continue
        if clave in ("LUT_3D_INPUT_RANGE", "LUT_1D_INPUT_RANGE"):
            if len(campos) != 3:
                raise ErrorFormatoCube(
                    f"'{nombre}', línea {n_linea}: {clave} necesita 2 números, "
                    f"llegaron {len(campos) - 1}"
                )
            lo = _numero(campos[1], nombre=nombre, n_linea=n_linea, que=clave)
            hi = _numero(campos[2], nombre=nombre, n_linea=n_linea, que=clave)
            dmin, dmax = (lo, lo, lo), (hi, hi, hi)
            continue

        # Si no es una palabra clave conocida, tiene que ser una fila de datos.
        # Ojo: 'nan' e 'inf' PARECEN palabras clave y son números; si se colaran
        # por la rama de "palabra clave desconocida" el mensaje sería absurdo.
        # Y una vez que ha empezado la tabla, cualquier cosa rara es una fila de
        # datos corrupta, no una palabra clave: el error es más útil así.
        if _ES_IDENTIFICADOR.match(campos[0]) and not _es_numero(campos[0]) and not filas:
            raise ErrorFormatoCube(
                f"'{nombre}', línea {n_linea}: no entiendo la palabra clave '{campos[0]}'"
            )

        if max_filas is None:
            max_filas = _filas_esperadas(
                size_3d, size_1d, nombre=nombre, n_linea=linea_size, tamano_maximo=tamano_maximo
            )
        if len(filas) >= max_filas:
            raise ErrorFormatoCube(
                f"'{nombre}': el fichero declara {max_filas} líneas de datos pero tiene más "
                f"(sobra al menos la línea {n_linea}); el tamaño declarado no cuadra"
            )
        if len(campos) != 3:
            raise ErrorFormatoCube(
                f"'{nombre}', línea {n_linea}: cada línea de datos son 3 números, "
                f"llegaron {len(campos)} ('{linea[:60]}')"
            )
        filas.append(_trio(campos, nombre=nombre, n_linea=n_linea, que="un valor de la tabla"))

    if size_3d is None and size_1d is None:
        raise ErrorFormatoCube(
            f"'{nombre}' no declara ni LUT_3D_SIZE ni LUT_1D_SIZE; no es un .cube válido"
        )
    if size_3d is not None and size_1d is not None:
        raise ErrorFormatoCube(
            f"'{nombre}' declara LUT_3D_SIZE y LUT_1D_SIZE a la vez; no sé cuál de los dos leer"
        )

    esperadas = _filas_esperadas(
        size_3d, size_1d, nombre=nombre, n_linea=linea_size, tamano_maximo=tamano_maximo
    )
    if len(filas) != esperadas:
        que = "LUT_3D_SIZE" if size_3d is not None else "LUT_1D_SIZE"
        declarado = size_3d if size_3d is not None else size_1d
        raise ErrorFormatoCube(
            f"'{nombre}': {que} dice {declarado}, o sea {esperadas} líneas de datos, "
            f"pero he encontrado {len(filas)}"
        )

    datos = np.asarray(filas, dtype=np.float32)
    if size_3d is not None:
        table = tabla_desde_orden_fichero(datos, size_3d)
    else:
        table = _cubo_desde_1d(datos, tamano_3d_desde_1d, nombre=nombre)

    return _construir_lut(table, dmin, dmax, titulo, nombre=nombre)


def _filas_esperadas(
    size_3d: int | None,
    size_1d: int | None,
    *,
    nombre: str,
    n_linea: int,
    tamano_maximo: int,
) -> int:
    if size_3d is not None:
        if not (LUT_SIZE_MIN <= size_3d <= tamano_maximo):
            raise ErrorFormatoCube(
                f"'{nombre}', línea {n_linea}: LUT_3D_SIZE tiene que estar entre "
                f"{LUT_SIZE_MIN} y {tamano_maximo}, y llegó {size_3d}"
            )
        return size_3d**3
    if size_1d is None:
        # Han llegado datos antes de declarar el tamaño: el fichero no lo dice.
        raise ErrorFormatoCube(
            f"'{nombre}' tiene líneas de datos pero no declara ni LUT_3D_SIZE ni "
            "LUT_1D_SIZE antes que ellas; no es un .cube válido"
        )
    if not (LUT_SIZE_MIN <= size_1d <= 65536):
        raise ErrorFormatoCube(
            f"'{nombre}', línea {n_linea}: LUT_1D_SIZE tiene que estar entre "
            f"{LUT_SIZE_MIN} y 65536, y llegó {size_1d}"
        )
    return size_1d


def _cubo_desde_1d(curvas: np.ndarray, tamano: int, *, nombre: str) -> np.ndarray:
    """Convierte tres curvas 1D (una por canal) en un cubo 3D separable."""
    if not (LUT_SIZE_MIN <= tamano <= LUT_SIZE_MAX_LECTURA):
        raise ErrorFormatoCube(
            f"'{nombre}': para convertir un LUT 1D a 3D hace falta un tamaño entre "
            f"{LUT_SIZE_MIN} y {LUT_SIZE_MAX_LECTURA}, y me han pedido {tamano}"
        )
    n1d = curvas.shape[0]
    origen = np.linspace(0.0, 1.0, n1d)
    destino = np.linspace(0.0, 1.0, tamano)
    ejes = [np.interp(destino, origen, curvas[:, c].astype(np.float64)) for c in range(3)]
    tabla = np.empty((tamano, tamano, tamano, 3), dtype=np.float32)
    tabla[..., 0] = ejes[0][:, None, None]
    tabla[..., 1] = ejes[1][None, :, None]
    tabla[..., 2] = ejes[2][None, None, :]
    return tabla


def _construir_lut(
    table: np.ndarray,
    dmin: tuple[float, float, float],
    dmax: tuple[float, float, float],
    titulo: str | None,
    *,
    nombre: str,
) -> LUT3D:
    kwargs = {"table": table, "domain_min": dmin, "domain_max": dmax}
    if titulo:
        kwargs["title"] = titulo
    try:
        return LUT3D(**kwargs)
    except ValueError as exc:
        # El único camino que queda aquí es un DOMAIN_MIN >= DOMAIN_MAX: el
        # tamaño ya lo hemos validado antes y la forma la construimos nosotros.
        raise ErrorFormatoCube(f"'{nombre}': {exc}") from exc


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------


def _limpiar_titulo(titulo: str) -> str:
    """El TITLE va entre comillas: fuera comillas, saltos de línea y de paso lo
    recortamos, que hay parsers que se atragantan con títulos kilométricos."""
    limpio = titulo.replace('"', "'").replace("\r", " ").replace("\n", " ").strip()
    return limpio[:100]


def _spec_numero(decimales: int | None) -> str:
    """Formato de número para el cuerpo del `.cube`.

    `decimales=None` significa **exacto**: `.9g`, o sea 9 cifras SIGNIFICATIVAS,
    que es la garantía de ida y vuelta del float32 (IEEE 754). Ojo con la
    diferencia, que es justo donde es fácil equivocarse: 9 *decimales* redondean
    bien un valor de 0,9 pero destrozan uno de 0,000012, porque el espaciado del
    float32 se encoge con el valor. 9 cifras significativas se adaptan.

    El precio de `.9g` es que por debajo de 1e-4 aparece notación científica
    (`1.2e-05`). Es XML... perdón, es texto: `float()` la lee sin pestañear, y
    `atof` de C —que es lo que usa Resolve— también. Sólo se usa en el bundle
    `.sidebcolor`, donde manda la exactitud; los `.cube` que se le entregan a
    Resolve salen con los 6 decimales de toda la vida.
    """
    if decimales is None:
        return ".9g"
    if not (1 <= decimales <= 12):
        raise ErrorFormatoCube(
            f"'decimales' tiene que estar entre 1 y 12 (o None para exacto), y llegó {decimales}"
        )
    return f".{decimales}f"


def cube_a_texto(
    lut: LUT3D, *, decimales: int | None = 6, escribir_dominio: bool = True
) -> str:
    """El contenido completo de un `.cube`, como cadena. Sin tocar el disco.

    Lo usan `escribir_cube` y el bundle `.sidebcolor` (que mete el texto
    directamente en el zip). `decimales=None` da ida y vuelta exacta en float32.
    """
    table = np.asarray(lut.table, dtype=np.float32)
    if not np.isfinite(table).all():
        cuantos = int((~np.isfinite(table)).sum())
        raise ErrorFormatoCube(
            f"el LUT tiene {cuantos} valores no finitos (NaN o infinito) y un .cube con NaN "
            "revienta en Resolve; pasa antes por qc_lut() y arréglalo"
        )
    spec = _spec_numero(decimales)

    lineas: list[str] = []
    titulo = _limpiar_titulo(lut.title)
    if titulo:
        lineas.append(f'TITLE "{titulo}"')
    lineas.append(f"LUT_3D_SIZE {lut.size}")
    if escribir_dominio:
        fmt_dom = lambda t: " ".join(format(float(v), spec) for v in t)  # noqa: E731
        lineas.append(f"DOMAIN_MIN {fmt_dom(lut.domain_min)}")
        lineas.append(f"DOMAIN_MAX {fmt_dom(lut.domain_max)}")
    lineas.append("")

    plano = orden_fichero_desde_tabla(table).astype(np.float64)
    # Un join directo va sobrado incluso con 65**3 = 274.625 líneas, y es mucho
    # más controlable que np.savetxt (que mete su propio separador y su propio
    # salto de línea según la plataforma).
    cuerpo = "\n".join(
        f"{format(fila[0], spec)} {format(fila[1], spec)} {format(fila[2], spec)}"
        for fila in plano
    )
    return "\n".join(lineas) + "\n" + cuerpo + "\n"


def escribir_cube(
    lut: LUT3D,
    ruta: str | Path,
    *,
    decimales: int | None = 6,
    crear_directorios: bool = False,
    escribir_dominio: bool = True,
) -> Path:
    """Escribe un `.cube` que Resolve lee sin rechistar.

    * codificación ASCII, **sin BOM**
    * saltos de línea Unix (`\\n`), también en macOS y en Windows
    * `LUT_3D_SIZE` antes de los datos
    * 6 decimales por defecto (`decimales=None` da ida y vuelta exacta en
      float32 a costa de notación científica en los valores minúsculos; es lo
      que usa el bundle `.sidebcolor`)

    **El directorio de destino tiene que existir.** Si no existe se lanza
    `ErrorFormatoCube` en vez de crearlo a la chita callando: la convención 7 de
    CONTRATOS dice que `core/` no escribe fuera de la ruta que le pasan, y
    fabricar un árbol de carpetas entero por un error de tecleo es justo lo que
    no queremos. Quien quiera crearlo, `crear_directorios=True` y a correr.

    Devuelve la ruta escrita.
    """
    ruta = Path(ruta)
    nombre = describe_ruta(ruta)
    texto = cube_a_texto(lut, decimales=decimales, escribir_dominio=escribir_dominio)

    if not ruta.parent.exists():
        if not crear_directorios:
            raise ErrorFormatoCube(
                f"la carpeta '{ruta.parent}' no existe; créala tú o llama con "
                "crear_directorios=True"
            )
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorFormatoCube(f"no puedo crear la carpeta '{ruta.parent}': {exc}") from exc

    try:
        # newline="\n" obliga a saltos Unix pase lo que pase; encoding ascii sin
        # BOM. El título ya viene saneado, pero si trae un acento lo sustituimos
        # antes que romper la escritura.
        with open(ruta, "w", encoding="ascii", newline="\n", errors="replace") as fh:
            fh.write(texto)
    except PermissionError as exc:
        raise ErrorFormatoCube(f"no tengo permiso para escribir en '{nombre}'") from exc
    except OSError as exc:
        raise ErrorFormatoCube(f"no puedo escribir '{nombre}': {exc}") from exc
    return ruta
