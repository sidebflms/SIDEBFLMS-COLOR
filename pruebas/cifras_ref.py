"""Leer las cifras sinteticas de referencia de `CIFRAS.md`, sin copiarlas a mano.

POR QUE NO ESTAN ESCRITAS EN EL CODIGO
--------------------------------------
Si mañana cambian, el informe de la prueba real no puede quedarse con las viejas.
Asi que se leen del archivo cada vez que se genera un informe.

COMO SE LEE, Y POR QUE ASI
--------------------------
`CIFRAS.md` va a seguir cambiando (orden de filas, columnas nuevas, tablas
nuevas). Por eso **no se lee por posicion de fila ni por el texto exacto de una
celda**:

- Se recorren **todas** las tablas Markdown del archivo y cada fila se convierte
  en un diccionario por **nombre de columna** (`Criterio`, `Cifra`, `Valor`,
  `Cifra que decide`, `Límite`, `Montaje`, `Comando`, `Fecha`...).
- Una cifra se busca por **palabras**: el criterio (`T1`, `T5`, `cobertura`) y lo
  que se mide (`máximo`, `medio`). Sin tildes, sin mayusculas, sin negritas.
- Si no aparece, se devuelve `None` y el informe escribe **«no disponible en
  CIFRAS.md»**. Nunca se inventa un valor ni se falla.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .guarda import RAIZ_REPO

__all__ = [
    "NO_DISPONIBLE",
    "RUTA_CIFRAS",
    "Referencia",
    "buscar",
    "leer_tablas",
    "referencias_para_informe",
]

RUTA_CIFRAS: Path = RAIZ_REPO / "CIFRAS.md"

NO_DISPONIBLE = "no disponible en CIFRAS.md"

_COLUMNAS_NOMBRE = ("criterio", "cifra")
_COLUMNAS_VALOR = ("cifra que decide", "valor")


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", t).strip().lower()


def _limpia(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.replace("**", "").replace("`", "")).strip()


def _celdas(linea: str) -> list[str]:
    t = linea.strip()
    if t.startswith("|"):
        t = t[1:]
    if t.endswith("|"):
        t = t[:-1]
    return [c.strip() for c in t.split("|")]


def leer_tablas(texto: str) -> list[dict[str, str]]:
    """Todas las filas de todas las tablas, como {columna normalizada: celda cruda}.

    Cada fila lleva ademas `_seccion` con el ultimo encabezado `#` visto antes.
    """
    filas: list[dict[str, str]] = []
    lineas = texto.splitlines()
    seccion = ""
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if linea.lstrip().startswith("#"):
            seccion = linea.strip("# ").strip()
        es_tabla = (
            linea.strip().startswith("|")
            and i + 1 < len(lineas)
            and re.match(r"^\s*\|?\s*:?-{3,}", lineas[i + 1] or "")
        )
        if not es_tabla:
            i += 1
            continue
        cabecera = [_normal(c) for c in _celdas(linea)]
        i += 2
        while i < len(lineas) and lineas[i].strip().startswith("|"):
            celdas = _celdas(lineas[i])
            fila = {cabecera[k]: celdas[k] for k in range(min(len(cabecera), len(celdas)))}
            fila["_seccion"] = seccion
            filas.append(fila)
            i += 1
    return filas


@dataclass(frozen=True)
class Referencia:
    etiqueta: str  # criterio / cifra, limpio
    valor: str  # la celda del valor, limpia (tal cual la escribe CIFRAS.md)
    numero: float | None  # el numero sacado de la celda, si se puede sin ambiguedad
    limite: str | None
    montaje: str | None
    comando: str | None
    fecha: str | None


def _numero(valor: str) -> float | None:
    """El numero de una celda. Ignora el '2000' de 'ΔE2000' y los '33³'.

    Con un '%' se queda con el numero justo antes del ultimo '%'. Si hay varios
    numeros separados por una flecha (antes -> despues) no elige: None.
    """
    t = _normal(valor)
    t = re.sub(r"(Δ|delta ?)?e ?2000", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\d+³", " ", t)
    if "→" in t or "->" in t:
        return None
    pct = re.findall(r"(-?\d+(?:\.\d+)?)\s*%", t)
    if pct:
        return float(pct[-1])
    nums = re.findall(r"-?\d+\.\d+|-?\d+", t)
    if len(nums) == 1:
        return float(nums[0])
    return None


def _contiene_palabras(texto: str, palabras: tuple[str, ...]) -> bool:
    t = _normal(texto)
    return all(re.search(rf"(?<![a-z0-9]){re.escape(_normal(p))}(?![a-z0-9])", t) for p in palabras)


def buscar(
    filas: list[dict[str, str]], criterio: tuple[str, ...], que: tuple[str, ...] = (),
    excluir: tuple[str, ...] = (),
) -> list[Referencia]:
    """Filas cuyo nombre+valor contienen todas las palabras de `criterio` y `que`."""
    salida: list[Referencia] = []
    for f in filas:
        nombre = next((f[c] for c in _COLUMNAS_NOMBRE if c in f), None)
        valor = next((f[c] for c in _COLUMNAS_VALOR if c in f), None)
        if nombre is None or valor is None:
            continue
        junto = f"{nombre} {valor}"
        if not _contiene_palabras(nombre, criterio) and not _contiene_palabras(junto, criterio):
            continue
        if que and not _contiene_palabras(junto, que):
            continue
        if excluir and any(_contiene_palabras(junto, (x,)) for x in excluir):
            continue
        salida.append(
            Referencia(
                etiqueta=_limpia(nombre),
                valor=_limpia(valor),
                numero=_numero(valor),
                limite=_limpia(f["limite"]) if "limite" in f else None,
                montaje=_limpia(f["montaje"]) if "montaje" in f else None,
                comando=_limpia(f["comando"]) if "comando" in f else None,
                fecha=_limpia(f["fecha"]) if "fecha" in f else None,
            )
        )
    return salida


#: Lo que el informe pone al lado de cada cifra real: (clave, criterio, que, excluir).
CONSULTAS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    ("t1_max", ("t1",), ("maximo",), ("identidad", "sin gradar")),
    ("t1_medio", ("t1",), ("medio",), ("identidad", "sin gradar")),
    ("cobertura", ("cobertura",), (), ()),
    ("t5_max", ("t5",), ("maximo",), ()),
    ("t5_medio", ("t5",), ("medio",), ()),
)


def referencias_para_informe(ruta: Path | None = None) -> dict[str, list[Referencia] | str]:
    """{clave: [Referencia...]} o {clave: NO_DISPONIBLE}. Nunca lanza por el contenido."""
    ruta = RUTA_CIFRAS if ruta is None else ruta
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return {clave: NO_DISPONIBLE for clave, *_ in CONSULTAS}
    filas = leer_tablas(texto)
    salida: dict[str, list[Referencia] | str] = {}
    for clave, criterio, que, excluir in CONSULTAS:
        encontradas = buscar(filas, criterio, que, excluir)
        salida[clave] = encontradas if encontradas else NO_DISPONIBLE
    return salida
