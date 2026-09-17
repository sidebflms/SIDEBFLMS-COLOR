"""Lector de `.drx` (PowerGrades / stills de DaVinci Resolve).

Día 6: con material real de Mario en `tests/powergrades_reales/`, la suposición
de foro del día 5 ("es XML") se confirmó, y además se pudo desmontar la parte
que antes era opaca. Todo lo que sigue está marcado como CONFIRMADO (en N de
los 10 archivos de referencia) o SUPUESTO en `core/io/FORMATO-DRX.md` — léelo
antes de tocar este módulo, es la fuente de verdad de lo que se sabe.

RESUMEN DEL FORMATO (detalle completo en FORMATO-DRX.md)
-----------------------------------------------------------
Un `.drx` es XML UTF-8 con un elemento raíz `<Gallery::GyStill>` (el `::` en
el nombre de la etiqueta hace que NO sea XML válido para un parser con
namespaces estrictos activados — `ElementTree`/`expat` con
`namespace_separator=None`, que es el valor por defecto en Python, lo
aceptan igual). Dentro hay metadata plana (`Width`, `Height`, `CreateTime`…)
y dos elementos `<Body>` (uno en `pClipFullVer`, el grado del clip; otro en
`pTrackVer`, el grado de pista/track) cuyo contenido es **texto hexadecimal**
de un blob binario:

    byte 0            : constante 0x81 en los 10 archivos de referencia
    bytes 1..         : un frame Zstandard válido

Al descomprimir, el resultado es **Protocol Buffers** sin esquema publicado
(`core/io/drx_protobuf.py` lo decodifica por wire format, sin `.proto`). Los
nodos del grafo de color viven en `campo 1 → campo 7 (repetido)`; cada nodo
lleva un índice (`campo 1` dentro del nodo) que NO es 1-based por clip — es
un contador global del proyecto (confirmado: los dos `.drx` de un trabajo
real traen índices 260-281, no 1-N). Las rutas de LUT referenciadas por un
nodo se buscan como texto entre TODAS las hojas del subárbol de ese nodo
(`drx_protobuf.hojas_bytes`), sin fijar la ruta de campos exacta hasta la
ruta — eso es deliberado: es más robusto a que Blackmagic mueva un campo de
sitio entre builds que fijar 7 niveles de campos anidados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.parsers import expat

import zstandard

from core.io.drx_protobuf import Campo, ErrorProtobuf, campos, hojas_bytes, parsear_mensaje

__all__ = [
    "EXTENSIONES_DEPENDENCIA",
    "BYTE_CABECERA_BODY",
    "VERSIONES_RESOLVE_CONFIRMADAS",
    "InfoDRX",
    "NodoDRX",
    "GradoDRX",
    "inspeccionar_drx",
    "descomprimir_body",
    "leer_grado",
    "buscar_rutas_referenciadas",
    "avisar_dependencias_faltantes",
    "version_resolve",
    "advertencia_version_desconocida",
]

#: Extensiones que cuentan como "posible dependencia externa" al buscar texto
#: en las hojas del protobuf. Lista abierta a propósito: mejor un falso
#: positivo (un string que por casualidad termina en ".cube") que callarse
#: una dependencia real. Sólo ".cube" y ".dctl" están CONFIRMADAS en material
#: real (ver FORMATO-DRX.md); el resto son SUPUESTAS por analogía.
EXTENSIONES_DEPENDENCIA: tuple[str, ...] = (
    ".cube",
    ".dctl",
    ".3dl",
    ".png",
    ".tif",
    ".tiff",
    ".dpx",
    ".exr",
)

#: CONFIRMADO en 20 de 20 `<Body>` (los dos, clip y pista, de los 10 archivos
#: de referencia): el primer byte del blob es siempre 0x81. No se sabe qué
#: codifica (¿versión de formato? ¿flag de compresión?) — se documenta como
#: constante porque de momento es indistinguible de un valor fijo, no porque
#: se entienda su significado.
BYTE_CABECERA_BODY: int = 0x81

#: CONFIRMADO en 10 de 10 archivos de referencia: la segunda línea del
#: archivo es un comentario XML `<!--DbAppVer="X.Y.Z.NNNN" DbPrjVer="N"-->`
#: con la versión de Resolve que lo escribió. Los diez son de la misma
#: versión — no hay ningún archivo de referencia de otra versión con el que
#: comprobar si el protobuf cambia de forma entre versiones.
_PATRON_VERSION_RESOLVE = re.compile(r'<!--DbAppVer="([^"]*)"')

#: Versiones de Resolve para las que este lector se ha comprobado contra
#: material real (los 10 archivos de `tests/powergrades_reales/`, ver
#: FORMATO-DRX.md). El formato del `<Body>` es protobuf SIN esquema
#: publicado (`core/io/drx_protobuf.py`) — los números de campo son estables
#: dentro de una build pero Blackmagic no promete que lo sigan siendo entre
#: versiones. Cualquier versión fuera de este conjunto es una incógnita: el
#: lector puede seguir funcionando bien (protobuf suele ser aditivo) o puede
#: estar leyendo campos que ya no significan lo mismo, en silencio. Añade
#: una versión aquí sólo después de confirmarla contra un `.drx` real de esa
#: versión, nunca por suposición.
VERSIONES_RESOLVE_CONFIRMADAS: frozenset[str] = frozenset({"21.1.0.0017"})

_PATRON_EXTENSION = re.compile(
    "(?:" + "|".join(re.escape(e) for e in EXTENSIONES_DEPENDENCIA) + ")$", re.IGNORECASE
)


def version_resolve(ruta: str | Path) -> str | None:
    """La versión de Resolve (`DbAppVer`) que escribió `ruta`, leída del
    comentario de cabecera del XML. `None` si no se encuentra — no lanza:
    no encontrarlo no es un archivo roto, es simplemente "no se sabe qué lo
    escribió", y quien llama decide qué hacer con esa incertidumbre.
    """
    try:
        cabecera = Path(ruta).read_text(encoding="utf-8", errors="replace")[:512]
    except OSError:
        return None
    m = _PATRON_VERSION_RESOLVE.search(cabecera)
    return m.group(1) if m else None


def advertencia_version_desconocida(version: str | None) -> str | None:
    """El aviso a mostrar para `version` (de `version_resolve`), o `None` si
    no hace falta avisar.

    Avisa, no bloquea (regla de `CONTRATOS.md`, día 7): un `.drx` de una
    versión nunca vista puede seguir leyéndose bien, pero si Resolve movió
    algún número de campo del protobuf entre versiones, el resultado sería
    un dato con FORMA plausible y VALOR incorrecto — leer mal en silencio,
    el peor fallo posible aquí. Que decida con esta información quien use el
    dato, no este módulo.
    """
    if version is None:
        return (
            "no se ha podido leer qué versión de Resolve escribió este archivo "
            "(falta el comentario de cabecera con DbAppVer) — se interpreta con "
            "el mismo lector que el resto, sin garantía de que la estructura del "
            "grado coincida."
        )
    if version not in VERSIONES_RESOLVE_CONFIRMADAS:
        confirmadas = ", ".join(sorted(VERSIONES_RESOLVE_CONFIRMADAS))
        return (
            f"escrito por Resolve {version}, una versión nunca comprobada contra "
            f"material real (sólo está confirmada {confirmadas}) — el formato del "
            "grado es protobuf sin esquema publicado y los campos podrían haberse "
            "movido entre versiones; los datos leídos podrían ser plausibles y "
            "estar equivocados."
        )
    return None


@dataclass(frozen=True)
class InfoDRX:
    """Lo que se ha podido leer de la CAPA XML de un `.drx` (sin descomprimir
    los `<Body>`). Sigue siendo útil para el primer vistazo: `es_xml`,
    vocabulario de etiquetas, tamaño."""

    ruta: str
    es_xml: bool
    tag_raiz: str | None
    vocabulario: tuple[tuple[str, int], ...]
    profundidad_maxima: int
    tamano_bytes: int
    #: Versión de Resolve (`DbAppVer`) que escribió el archivo, o `None` si
    #: no se encontró el comentario de cabecera. Ver `version_resolve`.
    version_resolve: str | None = None
    advertencias: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NodoDRX:
    """Un nodo del grafo de color, tal y como se ha podido leer del protobuf."""

    #: El índice tal cual aparece en el campo 1 del nodo. CONFIRMADO: NO es
    #: 1-based por clip, es un contador que parece global al proyecto — no lo
    #: uses para decidir "es el nodo 1/2/3 del diseño de la app" sin más.
    indice: int
    #: Rutas de LUT encontradas en el subárbol de este nodo, en el orden en
    #: que aparecen. Vacío si el nodo no referencia ningún LUT (p.ej. un nodo
    #: con sólo un CDL numérico).
    rutas_lut: tuple[str, ...]


@dataclass(frozen=True)
class GradoDRX:
    """El grado de UN `<Body>` (normalmente `pClipFullVer`, el del clip)."""

    nodos: tuple[NodoDRX, ...]

    @property
    def rutas_lut(self) -> tuple[str, ...]:
        """Todas las rutas de LUT del grado, de todos los nodos, sin duplicar."""
        vistas: list[str] = []
        for nodo in self.nodos:
            for r in nodo.rutas_lut:
                if r not in vistas:
                    vistas.append(r)
        return tuple(vistas)


def _parsear_xml_sin_namespaces(datos: bytes) -> ET.Element:
    """Como `ET.fromstring(datos)`, pero sin procesar `:` como separador de
    namespace.

    CONFIRMADO en los 10 archivos de referencia: el `.drx` usa nombres de
    etiqueta con DOS puntos, como `<Gallery::GyStill>` o
    `<ListMgt::LmVersion>`. Eso viola las reglas de "Namespaces in XML" (un
    nombre local no puede contener `:`), y `ET.fromstring()` lo rechaza como
    "not well-formed" — no porque el archivo esté roto, sino porque
    `ET.XMLParser` construye internamente su parser `expat` con
    `namespace_separator` fijado (a diferencia de `expat.ParserCreate()` a
    secas, cuyo valor por defecto es `None`, es decir, sin procesar
    namespaces en absoluto). La solución es construir el árbol a mano con
    `expat.ParserCreate()` + `ET.TreeBuilder`, que es exactamente lo que hace
    `ET.XMLParser` por dentro salvo por ese único parámetro.
    """
    parser = expat.ParserCreate()
    builder = ET.TreeBuilder()
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data
    parser.Parse(datos, True)
    return builder.close()


def _profundidad(elem: ET.Element) -> int:
    hijos = list(elem)
    if not hijos:
        return 1
    return 1 + max(_profundidad(h) for h in hijos)


def _contar_etiquetas(elem: ET.Element, contador: dict[str, int]) -> None:
    contador[elem.tag] = contador.get(elem.tag, 0) + 1
    for hijo in elem:
        _contar_etiquetas(hijo, contador)


def inspeccionar_drx(ruta: str | Path) -> InfoDRX:
    """Lee la capa XML de `ruta`. Nunca lanza por forma inesperada."""
    p = Path(ruta)
    datos = p.read_bytes()
    advertencias: list[str] = []

    try:
        raiz = _parsear_xml_sin_namespaces(datos)
    except expat.ExpatError as exc:
        return InfoDRX(
            ruta=str(p),
            es_xml=False,
            tag_raiz=None,
            vocabulario=(),
            profundidad_maxima=0,
            tamano_bytes=len(datos),
            advertencias=(f"no parsea como XML: {exc}.",),
        )

    contador: dict[str, int] = {}
    _contar_etiquetas(raiz, contador)
    vocabulario = tuple(sorted(contador.items(), key=lambda kv: (-kv[1], kv[0])))

    if len(datos) == 0:
        advertencias.append("el archivo está vacío.")

    version = version_resolve(p)
    aviso_version = advertencia_version_desconocida(version)
    if aviso_version is not None:
        advertencias.append(aviso_version)

    return InfoDRX(
        ruta=str(p),
        es_xml=True,
        tag_raiz=raiz.tag,
        vocabulario=vocabulario,
        profundidad_maxima=_profundidad(raiz),
        tamano_bytes=len(datos),
        version_resolve=version,
        advertencias=tuple(advertencias),
    )


def descomprimir_body(hex_body: str) -> bytes | None:
    """El contenido hexadecimal de un `<Body>` -> bytes descomprimidos.

    `None` si no tiene la forma esperada (demasiado corto, cabecera distinta
    de `BYTE_CABECERA_BODY`, o el resto no es un frame Zstandard válido) — se
    devuelve `None` en vez de lanzar porque un `Body` vacío (`<Body/>`, que sí
    aparece en material real cuando una versión no tiene grado propio) es un
    caso normal, no un error.
    """
    try:
        crudo = bytes.fromhex(hex_body)
    except ValueError:
        return None
    if len(crudo) < 2 or crudo[0] != BYTE_CABECERA_BODY:
        return None
    try:
        return zstandard.ZstdDecompressor().decompress(crudo[1:], max_output_size=256 * 1024 * 1024)
    except zstandard.ZstdError:
        return None


def _rutas_lut_en(msg: tuple[Campo, ...]) -> tuple[str, ...]:
    vistas: list[str] = []
    for h in hojas_bytes(msg):
        if not _PATRON_EXTENSION.search(h.decode("latin-1")):
            continue
        try:
            txt = h.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if txt not in vistas:
            vistas.append(txt)
    return tuple(vistas)


def leer_grado(datos_descomprimidos: bytes) -> GradoDRX | None:
    """Bytes ya descomprimidos (ver `descomprimir_body`) -> `GradoDRX`.

    `None` si no parsea como protobuf en absoluto (formato inesperado: dilo,
    no inventes un grado vacío que parecería "no hay nodos" en vez de "no sé
    leer esto").
    """
    try:
        msg = parsear_mensaje(datos_descomprimidos)
    except ErrorProtobuf:
        return None
    f1 = campos(msg, 1)
    if not f1 or not f1[0].es_submensaje:
        return GradoDRX(nodos=())
    grafo = f1[0].valor
    nodos = []
    for nodo_campo in campos(grafo, 7):
        if not nodo_campo.es_submensaje:
            continue
        nodo_msg = nodo_campo.valor
        idx_campos = campos(nodo_msg, 1)
        indice = idx_campos[0].valor if idx_campos and isinstance(idx_campos[0].valor, int) else -1
        nodos.append(NodoDRX(indice=indice, rutas_lut=_rutas_lut_en(nodo_msg)))
    return GradoDRX(nodos=tuple(nodos))


def buscar_rutas_referenciadas(ruta: str | Path) -> tuple[str, ...]:
    """Todas las rutas de LUT referenciadas por el `.drx`, del grado de CLIP
    (`pClipFullVer`, el primer `<Body>`) — que es el que importa para "qué
    hace falta para aplicar este PowerGrade".

    Si el archivo no tiene la forma esperada (no es XML, no hay `<Body>`, no
    descomprime, no parsea como protobuf) devuelve una tupla vacía: no lanza,
    porque "no encontré nada" y "el archivo es raro" son, para quien sólo
    quiere saber qué archivos hacen falta, la misma respuesta práctica.
    """
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    cuerpos = re.findall(r"<Body>([0-9a-f]*)</Body>", texto)
    if not cuerpos:
        return ()
    dec = descomprimir_body(cuerpos[0])
    if dec is None:
        return ()
    grado = leer_grado(dec)
    if grado is None:
        return ()
    return grado.rutas_lut


def avisar_dependencias_faltantes(
    ruta: str | Path, carpetas_busqueda: tuple[str | Path, ...]
) -> tuple[str, ...]:
    """De `buscar_rutas_referenciadas`, cuáles no aparecen en ninguna carpeta dada.

    Comprueba dos formas: la ruta tal cual (si es absoluta y existe) y el
    nombre de archivo solo, buscado recursivamente en cada carpeta. Las rutas
    que trae el `.drx` son relativas a la carpeta de LUTs de Resolve DE QUIEN
    LO GRABÓ (CONFIRMADO en material real: `SIDEBFLMS/SECRET SAUCE/A1 SECRET
    SAUCE LUTs V2/…`), que casi nunca coincide con la estructura de carpetas
    en la máquina de destino — comparar sólo por nombre es lo único robusto
    entre dos Mac distintos.
    """
    referencias = buscar_rutas_referenciadas(ruta)
    carpetas = [Path(c) for c in carpetas_busqueda]
    faltantes: list[str] = []
    for ref in referencias:
        candidato = Path(ref)
        if candidato.is_absolute() and candidato.exists():
            continue
        nombre = candidato.name
        encontrado = any(next(c.rglob(nombre), None) is not None for c in carpetas if c.is_dir())
        if not encontrado:
            faltantes.append(ref)
    return tuple(faltantes)
