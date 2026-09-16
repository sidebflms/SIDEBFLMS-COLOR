"""Leer las cifras sinteticas de referencia de `CIFRAS.md`, sin copiarlas a mano.

POR QUE NO ESTAN ESCRITAS EN EL CODIGO
--------------------------------------
Si mañana cambian, el informe de la prueba real no puede quedarse con las viejas.
Asi que se leen del archivo cada vez que se genera un informe.

COMO SE LEE, Y POR QUE ASI
--------------------------
`CIFRAS.md` va a seguir creciendo, y cualquier fila de cualquier seccion puede
mencionar «T1» y «maximo» sin ser el titular de T1. Ya paso: la seccion 8 trajo
«T1 A->A maximo en escena rica (A5)», y un lector por patron la cogia como si
fuera el maximo de T1. Asi que **no se busca por patron en todo el archivo**:

- **El titular de T1 se lee SOLO de la tabla de titulares**, que se reconoce por
  sus columnas (`Criterio | Cifra que decide | Limite | Margen`), no por su
  posicion ni por el titulo de la seccion.
- **Cada una de las demas cifras se lee de SU seccion, a proposito y por nombre**
  (ver `CONSULTAS`): el medio de T1 de la subseccion «Detras» y la cobertura de
  «La cifra que faltaba», las dos de la misma seccion que la tabla de titulares;
  T5 de la seccion cuyo titulo habla de T5, y solo las filas que empiezan por
  «T5 maximo en B» y «T5 medio en B». Una fila de otra seccion no entra nunca.
- Dentro de su tabla, cada fila se lee por **nombre de columna**, sin tildes, sin
  mayusculas y sin negritas.
- Si no aparece, el informe escribe **«no disponible en CIFRAS.md»**. Nunca se
  inventa un valor ni se falla.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .guarda import RAIZ_REPO

__all__ = [
    "COLUMNAS_TITULARES",
    "CONSULTAS",
    "Consulta",
    "NO_DISPONIBLE",
    "RUTA_CIFRAS",
    "Referencia",
    "buscar",
    "leer_tablas",
    "referencias_para_informe",
]

RUTA_CIFRAS: Path = RAIZ_REPO / "CIFRAS.md"

NO_DISPONIBLE = "no disponible en CIFRAS.md"

#: Las columnas por las que se reconoce la tabla de titulares (normalizadas).
COLUMNAS_TITULARES: tuple[str, ...] = ("criterio", "cifra que decide", "limite", "margen")

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

    Cada fila lleva ademas `_seccion` (ultimo encabezado de nivel 1 o 2),
    `_subseccion` (ultimo de nivel 3 o mas dentro de esa seccion) y `_titulares`
    ("si" si su tabla tiene las columnas de la tabla de titulares).
    """
    filas: list[dict[str, str]] = []
    lineas = texto.splitlines()
    seccion = ""
    subseccion = ""
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        cabecera_md = re.match(r"^(#{1,6})\s+(.*)$", linea.strip())
        if cabecera_md:
            nivel = len(cabecera_md.group(1))
            if nivel <= 2:
                seccion, subseccion = cabecera_md.group(2).strip(), ""
            else:
                subseccion = cabecera_md.group(2).strip()
        es_tabla = (
            linea.strip().startswith("|")
            and i + 1 < len(lineas)
            and re.match(r"^\s*\|?\s*:?-{3,}", lineas[i + 1] or "")
        )
        if not es_tabla:
            i += 1
            continue
        cabecera = [_normal(c) for c in _celdas(linea)]
        es_titulares = set(COLUMNAS_TITULARES) <= set(cabecera)
        i += 2
        while i < len(lineas) and lineas[i].strip().startswith("|"):
            celdas = _celdas(lineas[i])
            fila = {cabecera[k]: celdas[k] for k in range(min(len(cabecera), len(celdas)))}
            fila["_seccion"] = seccion
            fila["_subseccion"] = subseccion
            fila["_titulares"] = "si" if es_titulares else ""
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


def _empieza_por(texto: str, prefijo: str) -> bool:
    return re.match(rf"^{re.escape(_normal(prefijo))}(?![a-z0-9])", _normal(texto)) is not None


@dataclass(frozen=True)
class Consulta:
    """Donde esta una cifra, dicho a proposito.

    `donde`:
      - "titulares": solo la tabla de titulares;
      - "seccion_titulares": tablas de la MISMA seccion que la de titulares, cuya
        subseccion contiene `subseccion`;
      - "seccion": tablas de la seccion cuyo titulo contiene las palabras `seccion`.
    La fila tiene que EMPEZAR por `fila` y contener las palabras `que` (en nombre o valor).
    """

    clave: str
    donde: str
    fila: str
    que: tuple[str, ...] = ()
    subseccion: tuple[str, ...] = ()
    seccion: tuple[str, ...] = ()


#: Lo que el informe pone al lado de cada cifra real. Si hace falta otra, se anade aqui.
CONSULTAS: tuple[Consulta, ...] = (
    Consulta("t1_max", "titulares", fila="t1", que=("maximo",)),
    Consulta("t1_medio", "seccion_titulares", fila="t1", que=("medio",), subseccion=("detras",)),
    Consulta("cobertura", "seccion_titulares", fila="cobertura",
             subseccion=("cifra", "que", "faltaba")),
    Consulta("t5_max", "seccion", fila="t5 maximo en b", seccion=("t5",)),
    Consulta("t5_medio", "seccion", fila="t5 medio en b", seccion=("t5",)),
)


def _referencia(f: dict[str, str], nombre: str, valor: str) -> Referencia:
    return Referencia(
        etiqueta=_limpia(nombre),
        valor=_limpia(valor),
        numero=_numero(valor),
        limite=_limpia(f["limite"]) if "limite" in f else None,
        montaje=_limpia(f["montaje"]) if "montaje" in f else None,
        comando=_limpia(f["comando"]) if "comando" in f else None,
        fecha=_limpia(f["fecha"]) if "fecha" in f else None,
    )


def buscar(filas: list[dict[str, str]], consulta: Consulta) -> list[Referencia]:
    """Las filas que responden a `consulta`, y solo de donde dice la consulta."""
    secciones_titulares = {f["_seccion"] for f in filas if f.get("_titulares")}
    salida: list[Referencia] = []
    for f in filas:
        if consulta.donde == "titulares":
            if not f.get("_titulares"):
                continue
        elif consulta.donde == "seccion_titulares":
            if f.get("_titulares") or f.get("_seccion") not in secciones_titulares:
                continue
            if not _contiene_palabras(f.get("_subseccion", ""), consulta.subseccion):
                continue
        elif consulta.donde == "seccion":
            if not _contiene_palabras(f.get("_seccion", ""), consulta.seccion):
                continue
        else:  # pragma: no cover - error de programacion
            raise ValueError(f"consulta con `donde` desconocido: {consulta.donde}")
        nombre = next((f[c] for c in _COLUMNAS_NOMBRE if c in f), None)
        valor = next((f[c] for c in _COLUMNAS_VALOR if c in f), None)
        if nombre is None or valor is None:
            continue
        if not _empieza_por(nombre, consulta.fila):
            continue
        if consulta.que and not _contiene_palabras(f"{nombre} {valor}", consulta.que):
            continue
        salida.append(_referencia(f, nombre, valor))
    return salida


def referencias_para_informe(ruta: Path | None = None) -> dict[str, list[Referencia] | str]:
    """{clave: [Referencia...]} o {clave: NO_DISPONIBLE}. Nunca lanza por el contenido."""
    ruta = RUTA_CIFRAS if ruta is None else ruta
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return {c.clave: NO_DISPONIBLE for c in CONSULTAS}
    filas = leer_tablas(texto)
    salida: dict[str, list[Referencia] | str] = {}
    for c in CONSULTAS:
        encontradas = buscar(filas, c)
        salida[c.clave] = encontradas if encontradas else NO_DISPONIBLE
    return salida
