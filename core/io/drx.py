"""Inspector de `.drx` (PowerGrades / stills de DaVinci Resolve).

SIN VERIFICAR CONTRA UN .drx REAL. Blackmagic no publica el formato, y hasta
hoy sólo hay suposiciones de foro (que es XML). Este módulo NO da por
confirmada esa suposición: **lee lo que encuentre e informa de ello tal
cual**, sin mapear a un esquema inventado. La confirmación de verdad —
estructura exacta, qué nodos trae, qué referencia por ruta en vez de
incrustar— es la tarea 4 del día 5 y depende de que Mario deje PowerGrades
reales en `tests/powergrades_reales/` (ver `.gitignore`: esa carpeta nunca se
versiona, nunca se sobrescribe, nunca se mueve).

Mientras esa carpeta esté vacía o no exista, `tests/test_io_drx.py` se salta
solo (`pytest.mark.skipif`) en vez de fallar o de inventar una verdad.

QUÉ HACE HOY, EXACTAMENTE
--------------------------
1. `inspeccionar_drx(ruta)`: intenta parsear el archivo como XML. Si lo es,
   reporta la etiqueta raíz y, para cada tipo de etiqueta que aparece en el
   árbol, cuántas veces aparece — un mapa del vocabulario del archivo, no una
   interpretación de qué significa cada uno. Si NO es XML, lo dice y no
   lanza: un `.drx` binario tumbaría esta suposición a la primera, y "no sé
   leerlo" es una respuesta honesta.
2. `buscar_rutas_referenciadas(ruta)`: sobre el texto crudo del archivo,
   busca patrones que parezcan una ruta de archivo (algo con `/` o `\\` y una
   extensión conocida de LUT: `.cube`, `.dctl`, `.3dl`, `.png`, `.tif`, etc.).
   Es una búsqueda de texto, no una lectura de esquema — la finalidad es sólo
   el avisador de dependencias (punto 3 de la tarea 4): decir qué archivos
   externos parece necesitar el PowerGrade, para poder comprobar si existen
   en la máquina donde se va a aplicar.
3. `avisar_dependencias_faltantes(ruta, carpetas_busqueda)`: cruza lo que
   encuentra (2) con el disco, y dice qué rutas referenciadas NO existen en
   ninguna de las carpetas dadas. Un PowerGrade que referencia un LUT ausente
   se aplica mal y en silencio (Resolve no avisa); esto es lo que hace que lo
   diga antes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

__all__ = [
    "EXTENSIONES_DEPENDENCIA",
    "InfoDRX",
    "inspeccionar_drx",
    "buscar_rutas_referenciadas",
    "avisar_dependencias_faltantes",
]

#: Extensiones que, si aparecen al final de algo que parece una ruta dentro
#: del `.drx`, cuentan como "posible dependencia externa". Lista abierta a
#: proposito: mejor un falso positivo (una ruta que en realidad no importa)
#: que callarse una dependencia real. `.dat` y `.look` se añaden porque
#: aparecen citados en foros como formatos de PowerGrade auxiliares, SIN
#: VERIFICAR.
EXTENSIONES_DEPENDENCIA: tuple[str, ...] = (
    ".cube",
    ".3dl",
    ".dctl",
    ".png",
    ".tif",
    ".tiff",
    ".dpx",
    ".exr",
    ".dat",
    ".look",
)

#: Un fragmento de texto que parece una ruta: al menos un separador de
#: carpeta y termina en una de las extensiones de arriba. No exige que exista
#: en disco (eso lo hace `avisar_dependencias_faltantes`).
_PATRON_RUTA = re.compile(
    r"[\w./\\ :-]+(?:" + "|".join(re.escape(e) for e in EXTENSIONES_DEPENDENCIA) + r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InfoDRX:
    """Lo que se ha podido leer de un `.drx`, SIN interpretar su significado."""

    ruta: str
    es_xml: bool
    tag_raiz: str | None
    #: Cuenta de cada nombre de etiqueta en todo el árbol (namespace incluido
    #: tal cual lo da ElementTree), ordenado por frecuencia descendente.
    vocabulario: tuple[tuple[str, int], ...]
    profundidad_maxima: int
    tamano_bytes: int
    advertencias: tuple[str, ...] = field(default_factory=tuple)


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
    """Lee `ruta` y describe lo que hay, sin asumir que es un esquema conocido.

    Nunca lanza por un archivo con forma inesperada: un `.drx` real puede no
    ser XML en absoluto, y esta función existe precisamente para poder decir
    eso con datos en vez de con una suposición de foro.
    """
    p = Path(ruta)
    datos = p.read_bytes()
    advertencias: list[str] = []

    try:
        raiz = ET.fromstring(datos)
    except ET.ParseError as exc:
        return InfoDRX(
            ruta=str(p),
            es_xml=False,
            tag_raiz=None,
            vocabulario=(),
            profundidad_maxima=0,
            tamano_bytes=len(datos),
            advertencias=(f"no parsea como XML: {exc}. La suposición de foro (que .drx es XML) no se cumple aquí.",),
        )

    contador: dict[str, int] = {}
    _contar_etiquetas(raiz, contador)
    vocabulario = tuple(sorted(contador.items(), key=lambda kv: (-kv[1], kv[0])))

    if len(datos) == 0:
        advertencias.append("el archivo está vacío.")

    return InfoDRX(
        ruta=str(p),
        es_xml=True,
        tag_raiz=raiz.tag,
        vocabulario=vocabulario,
        profundidad_maxima=_profundidad(raiz),
        tamano_bytes=len(datos),
        advertencias=tuple(advertencias),
    )


def buscar_rutas_referenciadas(ruta: str | Path) -> tuple[str, ...]:
    """Fragmentos de texto del archivo que PARECEN una ruta a un recurso externo.

    Búsqueda de texto sobre el contenido crudo (funciona parseé o no como
    XML): un atributo `path="../LUTs/mirar.cube"` se encuentra igual si el
    XML tiene una estructura rara. Duplicados eliminados, orden estable.
    """
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    vistos: list[str] = []
    vistos_set: set[str] = set()
    for m in _PATRON_RUTA.finditer(texto):
        frag = m.group(0).strip()
        if frag and frag not in vistos_set:
            vistos_set.add(frag)
            vistos.append(frag)
    return tuple(vistos)


def avisar_dependencias_faltantes(
    ruta: str | Path, carpetas_busqueda: tuple[str | Path, ...]
) -> tuple[str, ...]:
    """De `buscar_rutas_referenciadas`, cuáles no aparecen en ninguna carpeta dada.

    Comprueba dos formas: la ruta tal cual (si es absoluta o relativa al
    directorio actual) y el nombre de archivo solo, buscado dentro de cada
    carpeta de `carpetas_busqueda` (recursivo). Un PowerGrade suele
    referenciar LUTs por ruta relativa a la instalación de Resolve de quien
    lo grabó, así que comparar sólo el nombre de archivo es lo único robusto
    entre máquinas distintas.
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
