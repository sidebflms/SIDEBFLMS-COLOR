"""ASC CDL en XML: `.cc`, `.ccc` y `.cdl`.

LAS TRES FORMAS DEL MISMO ANIMAL
--------------------------------
El estándar ASC define tres envoltorios para exactamente el mismo contenido, y
lo único que los distingue de verdad es la extensión:

* `.cc`  -> `<ColorCorrection>` suelto. **Uno** solo.
* `.ccc` -> `<ColorCorrectionCollection>` con N `<ColorCorrection>` dentro.
* `.cdl` -> `<ColorDecisionList>` con N `<ColorDecision>`, cada uno con su
            `<ColorCorrection>`.

Aquí se escriben las tres según la extensión que pidas, y se leen las tres sin
preguntar (y también con espacio de nombres `urn:ASC:CDL:...`, que unas
herramientas ponen y otras no).

POR QUÉ `xml.etree.ElementTree` DE LA BIBLIOTECA ESTÁNDAR Y NO `defusedxml`
---------------------------------------------------------------------------
Porque `defusedxml` no está instalado en el venv y no se puede instalar (cero
red). Así que la defensa se hace a mano, y son tres cosas:

1. **Tope de tamaño** (`MAX_BYTES_CDL`, 8 MB). Un `.cdl` de verdad son 600
   bytes; 8 MB ya es absurdo, y corta el ataque de "fichero gigante".
2. **Se rechaza cualquier `<!DOCTYPE` o `<!ENTITY`** antes de parsear. Esto es
   lo que mata el *billion laughs* y las entidades externas de un plumazo: sin
   DTD no hay entidades que expandir. Un `.cdl` legítimo no lleva DTD nunca.
3. Expat, el parser que hay debajo de ElementTree, **no resuelve entidades
   externas por su cuenta** en Python (no hace peticiones de red ni abre
   ficheros): ante una entidad no declarada lanza. Con el punto 2 encima, la
   superficie que queda es la del propio expat parseando XML bien formado.

Lo que NO cubre: una bomba de anidamiento (miles de elementos anidados) puede
agotar la pila de expat. El tope de 8 MB lo limita a algo que Python aguanta.
Si algún día entra `defusedxml` en el venv, sustituir `_parsear` por
`defusedxml.ElementTree.fromstring` y borrar el punto 2.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from core.contracts import CDL

from .errores import ErrorFormatoCDL, describe_ruta

__all__ = [
    "MAX_BYTES_CDL",
    "EXTENSIONES_CDL",
    "leer_cdl",
    "leer_cdls",
    "escribir_cdl",
    "escribir_cdls",
    "cdl_a_xml",
]

#: Un `.cdl` de verdad ocupa menos de 1 KB. 8 MB es un techo ridículamente
#: generoso que sigue siendo barato de parsear.
MAX_BYTES_CDL: int = 8 * 1024 * 1024

#: Extensiones que sabemos escribir, y qué raíz le toca a cada una.
EXTENSIONES_CDL: tuple[str, ...] = (".cc", ".ccc", ".cdl")

_PROHIBIDO = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _sin_ns(tag: str) -> str:
    """'{urn:ASC:CDL:v1.2}SOPNode' -> 'SOPNode'."""
    return tag.rpartition("}")[2]


def _numero_texto(v: float) -> str:
    """Formatea un float para el XML: bonito si se puede, exacto siempre.

    Primero se prueba con 6 decimales (que es lo que todo el mundo espera ver en
    un `.cdl`); si eso NO vuelve a dar el mismo float, se cae a `repr`, que es la
    representación más corta que hace ida y vuelta exacta. La ida y vuelta manda
    sobre la estética.
    """
    bonito = f"{v:.6f}"
    if float(bonito) == float(v):
        return bonito
    return repr(float(v))


def _leer_texto(ruta: Path) -> str:
    nombre = describe_ruta(ruta)
    if not ruta.exists():
        raise ErrorFormatoCDL(f"no existe el fichero '{ruta}'")
    if ruta.is_dir():
        raise ErrorFormatoCDL(f"'{nombre}' es una carpeta, no un fichero CDL")
    tam = ruta.stat().st_size
    if tam == 0:
        raise ErrorFormatoCDL(f"el fichero '{nombre}' está vacío")
    if tam > MAX_BYTES_CDL:
        raise ErrorFormatoCDL(
            f"'{nombre}' ocupa {tam / 1024 / 1024:.1f} MB; un CDL son menos de 2 KB, "
            "esto no es un CDL"
        )
    if not os.access(ruta, os.R_OK):
        raise ErrorFormatoCDL(f"no tengo permiso para leer '{nombre}'")
    try:
        crudo = ruta.read_bytes()
    except PermissionError as exc:
        raise ErrorFormatoCDL(f"no tengo permiso para leer '{nombre}'") from exc
    except OSError as exc:
        raise ErrorFormatoCDL(f"no puedo leer '{nombre}': {exc}") from exc
    try:
        return crudo.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ErrorFormatoCDL(
            f"'{nombre}' no es texto UTF-8 válido (byte {exc.start}); no parece un XML"
        ) from exc


def _parsear(texto: str, *, nombre: str) -> ET.Element:
    """Parsea el XML con las tres defensas del docstring del módulo."""
    if _PROHIBIDO.search(texto):
        raise ErrorFormatoCDL(
            f"'{nombre}' trae un DOCTYPE o una ENTITY: un CDL legítimo nunca lleva DTD, "
            "y por ahí es por donde entran las bombas de entidades. No lo abro."
        )
    try:
        return ET.fromstring(texto)
    except ET.ParseError as exc:
        raise ErrorFormatoCDL(f"'{nombre}' no es XML bien formado: {exc}") from exc


def _trio(elem: ET.Element | None, *, que: str, nombre: str, defecto: tuple[float, float, float]):
    if elem is None or elem.text is None or not elem.text.split():
        return defecto
    campos = elem.text.replace(",", " ").split()
    if len(campos) != 3:
        raise ErrorFormatoCDL(
            f"'{nombre}': <{que}> tiene que llevar 3 números separados por espacios, "
            f"y lleva {len(campos)} ('{elem.text.strip()[:40]}')"
        )
    valores = []
    for c in campos:
        try:
            valores.append(float(c))
        except ValueError as exc:
            raise ErrorFormatoCDL(
                f"'{nombre}': <{que}> tiene un valor que no es un número: '{c}'"
            ) from exc
    if not all(np.isfinite(valores)):
        raise ErrorFormatoCDL(f"'{nombre}': <{que}> tiene valores no finitos: {valores}")
    return (valores[0], valores[1], valores[2])


def _hijo(padre: ET.Element, tag: str) -> ET.Element | None:
    for hijo in padre:
        if _sin_ns(hijo.tag) == tag:
            return hijo
    return None


def _buscar_todos(raiz: ET.Element, tag: str) -> list[ET.Element]:
    encontrados: list[ET.Element] = []
    if _sin_ns(raiz.tag) == tag:
        encontrados.append(raiz)
    for elem in raiz.iter():
        if elem is not raiz and _sin_ns(elem.tag) == tag:
            encontrados.append(elem)
    return encontrados


def _cdl_desde_elemento(cc: ET.Element, *, nombre: str) -> tuple[str | None, CDL]:
    sop = _hijo(cc, "SOPNode")
    # Ojo: `a or b` con Elements NO vale. Un Element sin hijos es "falso" para
    # Python (y encima está deprecado), así que un <SatNode/> vacío se colaría
    # por la rama equivocada. Hay que preguntar por `is None` a mano.
    sat = _hijo(cc, "SatNode")
    if sat is None:
        sat = _hijo(cc, "SATNode")
    if sop is None and sat is None:
        raise ErrorFormatoCDL(
            f"'{nombre}': el <ColorCorrection> no tiene ni <SOPNode> ni <SatNode>; está vacío"
        )

    slope = _trio(_hijo(sop, "Slope") if sop is not None else None,
                  que="Slope", nombre=nombre, defecto=(1.0, 1.0, 1.0))
    offset = _trio(_hijo(sop, "Offset") if sop is not None else None,
                   que="Offset", nombre=nombre, defecto=(0.0, 0.0, 0.0))
    power = _trio(_hijo(sop, "Power") if sop is not None else None,
                  que="Power", nombre=nombre, defecto=(1.0, 1.0, 1.0))

    saturacion = 1.0
    if sat is not None:
        nodo_sat = _hijo(sat, "Saturation")
        if nodo_sat is not None and nodo_sat.text and nodo_sat.text.strip():
            try:
                saturacion = float(nodo_sat.text.strip())
            except ValueError as exc:
                raise ErrorFormatoCDL(
                    f"'{nombre}': <Saturation> no es un número ('{nodo_sat.text.strip()[:40]}')"
                ) from exc
            if not np.isfinite(saturacion):
                raise ErrorFormatoCDL(f"'{nombre}': <Saturation> no es finito ({saturacion})")

    try:
        cdl = CDL(slope=slope, offset=offset, power=power, saturation=saturacion)
    except ValueError as exc:
        # El caso de verdad: un .cdl con Power 0. `CDL` lo rechaza a propósito,
        # y aquí lo traducimos a algo que se pueda enseñar en la GUI.
        raise ErrorFormatoCDL(
            f"'{nombre}': el CDL del fichero no es válido -> {exc}. "
            "Un Power de 0 o negativo no es un grado, es un error del que lo exportó."
        ) from exc
    return (cc.get("id"), cdl)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def leer_cdls(ruta: str | Path) -> list[tuple[str | None, CDL]]:
    """Lee TODOS los `<ColorCorrection>` de un `.cc`, `.ccc` o `.cdl`.

    Devuelve una lista de `(id, CDL)`; el `id` es el atributo del XML, o `None`
    si el fichero no lo trae (que es legal y bastante habitual).
    """
    ruta = Path(ruta)
    nombre = describe_ruta(ruta)
    raiz = _parsear(_leer_texto(ruta), nombre=nombre)
    elementos = _buscar_todos(raiz, "ColorCorrection")
    if not elementos:
        raise ErrorFormatoCDL(
            f"'{nombre}' no tiene ni un <ColorCorrection> (la raíz es "
            f"<{_sin_ns(raiz.tag)}>); no es un fichero ASC CDL"
        )
    return [_cdl_desde_elemento(cc, nombre=nombre) for cc in elementos]


def leer_cdl(ruta: str | Path) -> CDL:
    """Lee el PRIMER `<ColorCorrection>` del fichero y devuelve su `CDL`.

    Es lo que quiere el 95% de las llamadas. Si el fichero trae varios y te
    importan todos, usa `leer_cdls`.
    """
    return leer_cdls(ruta)[0][1]


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------


def _elemento_cc(cdl: CDL, cc_id: str | None) -> ET.Element:
    cc = ET.Element("ColorCorrection")
    if cc_id:
        cc.set("id", cc_id)
    sop = ET.SubElement(cc, "SOPNode")
    ET.SubElement(sop, "Slope").text = " ".join(_numero_texto(v) for v in cdl.slope)
    ET.SubElement(sop, "Offset").text = " ".join(_numero_texto(v) for v in cdl.offset)
    ET.SubElement(sop, "Power").text = " ".join(_numero_texto(v) for v in cdl.power)
    sat = ET.SubElement(cc, "SatNode")
    ET.SubElement(sat, "Saturation").text = _numero_texto(cdl.saturation)
    return cc


def cdl_a_xml(cdl: CDL, *, cc_id: str | None = None, envoltorio: str = ".cc") -> str:
    """El XML de un CDL como cadena, sin tocar el disco. Útil para la GUI."""
    return _documento([(cc_id, cdl)], envoltorio=envoltorio)


def _documento(items: list[tuple[str | None, CDL]], *, envoltorio: str) -> str:
    env = envoltorio.lower()
    if env == ".cc":
        if len(items) != 1:
            raise ErrorFormatoCDL(
                f"un fichero .cc lleva UN solo ColorCorrection y me has dado {len(items)}; "
                "usa .ccc o .cdl para una colección"
            )
        cc_id, cdl = items[0]
        raiz = _elemento_cc(cdl, cc_id)
    elif env == ".ccc":
        raiz = ET.Element("ColorCorrectionCollection")
        for cc_id, cdl in items:
            raiz.append(_elemento_cc(cdl, cc_id))
    elif env == ".cdl":
        raiz = ET.Element("ColorDecisionList")
        for cc_id, cdl in items:
            decision = ET.SubElement(raiz, "ColorDecision")
            decision.append(_elemento_cc(cdl, cc_id))
    else:
        raise ErrorFormatoCDL(
            f"no sé escribir la extensión '{envoltorio}'; las que conozco son "
            f"{', '.join(EXTENSIONES_CDL)}"
        )
    ET.indent(raiz, space="  ")
    cuerpo = ET.tostring(raiz, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + cuerpo + "\n"


def escribir_cdls(
    items: list[tuple[str | None, CDL]],
    ruta: str | Path,
    *,
    crear_directorios: bool = False,
) -> Path:
    """Escribe una colección de CDL. El envoltorio lo elige la EXTENSIÓN de la ruta."""
    ruta = Path(ruta)
    nombre = describe_ruta(ruta)
    if not items:
        raise ErrorFormatoCDL("no me has dado ni un CDL que escribir")

    texto = _documento(list(items), envoltorio=ruta.suffix)

    if not ruta.parent.exists():
        if not crear_directorios:
            raise ErrorFormatoCDL(
                f"la carpeta '{ruta.parent}' no existe; créala tú o llama con "
                "crear_directorios=True"
            )
        ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
    except PermissionError as exc:
        raise ErrorFormatoCDL(f"no tengo permiso para escribir en '{nombre}'") from exc
    except OSError as exc:
        raise ErrorFormatoCDL(f"no puedo escribir '{nombre}': {exc}") from exc
    return ruta


def escribir_cdl(
    cdl: CDL,
    ruta: str | Path,
    *,
    cc_id: str | None = None,
    crear_directorios: bool = False,
) -> Path:
    """Escribe UN CDL. La extensión manda: `.cc`, `.ccc` o `.cdl`.

    Sin BOM, saltos Unix, UTF-8, con la declaración XML delante. Ida y vuelta
    exacta con `leer_cdl` (ver `_numero_texto` para el porqué del formato).
    """
    return escribir_cdls([(cc_id, cdl)], ruta, crear_directorios=crear_directorios)
