"""Que ficheros se leen: SOLO los que se han pedido por argumento.

LA REGLA
--------
Nada de autodescubrimiento. El script no busca material por el disco, no mira
`/Volumes` "para ver que hay" y no adivina donde estan los brutos:

- `--master` es **un fichero**. Una carpeta no vale: el master es una pieza.
- `--brutos` son ficheros o carpetas. Si es una carpeta, se recorre **esa
  carpeta y nada mas**, sin seguir enlaces simbolicos que salgan de ella (un
  enlace que apunta a algo de dentro se acepta; uno que apunta fuera se ignora
  y se dice).
- Se niega a recorrer carpetas que no pueden ser una carpeta de brutos: `/`,
  `/Volumes`, la carpeta personal entera. Pasar una de esas es, casi seguro, un
  error al escribir la ruta, y recorrerla seria justo el autodescubrimiento que
  esta prohibido.
- Hay un tope de ficheros por carpeta (`MAX_FICHEROS_POR_CARPETA`). Si se pasa,
  no se sigue: se pide una ruta mas concreta.

Este modulo **no abre ningun fichero**: solo lista nombres y tamanos con `stat`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "EXTENSIONES_VIDEO",
    "EXTENSIONES_RAW",
    "MAX_FICHEROS_POR_CARPETA",
    "OrigenRechazado",
    "Listado",
    "listar_brutos",
    "validar_master",
]

#: Lo que se intenta leer como video. ffmpeg decide luego si puede.
EXTENSIONES_VIDEO: frozenset[str] = frozenset(
    {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".mts", ".m2ts", ".webm"}
)

#: RAW de camara: ffmpeg no los decodifica. Se listan como "no legibles" y se
#: explica que hay que pasar un ProRes/DNx sacado de ellos.
EXTENSIONES_RAW: frozenset[str] = frozenset(
    {".braw", ".r3d", ".crm", ".ari", ".arx", ".nev", ".dng", ".cine"}
)

#: Tope de ficheros de video dentro de UNA carpeta de brutos. Un trabajo normal
#: son decenas de clips; mil es que la ruta apunta a un disco entero. No es un
#: umbral de calidad, es un freno de seguridad.
MAX_FICHEROS_POR_CARPETA: int = 1000

_RAICES_PROHIBIDAS: tuple[Path, ...] = (
    Path("/"),
    Path("/Volumes"),
    Path("/Users"),
    Path.home(),
)


class OrigenRechazado(ValueError):
    """La ruta de origen no se puede usar tal cual. El mensaje dice por que."""


@dataclass
class Listado:
    ficheros: list[Path] = field(default_factory=list)
    ignorados: list[tuple[str, str]] = field(default_factory=list)  # (ruta, motivo)


def _abs(p: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.fspath(p)))


def validar_master(ruta: str | os.PathLike[str]) -> Path:
    p = _abs(ruta)
    if not p.exists():
        raise OrigenRechazado(f"El master no existe: {p}")
    if p.is_dir():
        raise OrigenRechazado(
            f"--master tiene que ser UN fichero (la pieza entregada), y {p} es una carpeta."
        )
    if p.suffix.lower() in EXTENSIONES_RAW:
        raise OrigenRechazado(
            f"El master {p.name} es un formato RAW que ffmpeg no lee. Exporta el master "
            f"entregado en ProRes, DNxHR o H.264/H.265."
        )
    return p


def _rechazar_raiz(p: Path) -> None:
    r = p.resolve()
    for prohibida in _RAICES_PROHIBIDAS:
        try:
            igual = r == prohibida.resolve()
        except OSError:  # pragma: no cover - raiz inaccesible
            igual = False
        if igual:
            raise OrigenRechazado(
                f"No recorro {p}: es una carpeta demasiado general para ser una carpeta de "
                f"brutos, y recorrerla seria buscar material por el disco. Pasa la carpeta "
                f"concreta del trabajo."
            )


def _es_video(nombre: str) -> bool:
    return Path(nombre).suffix.lower() in EXTENSIONES_VIDEO


def _basura(nombre: str) -> bool:
    # `._loquesea` son los metadatos que macOS deja en discos exFAT/FAT.
    return nombre.startswith("._") or nombre.startswith(".")


def listar_brutos(rutas: list[str | os.PathLike[str]]) -> Listado:
    """Lista los ficheros de bruto a partir de las rutas dadas. No abre ninguno."""
    salida = Listado()
    vistos: set[Path] = set()

    def anadir(p: Path) -> None:
        clave = p.resolve()
        if clave in vistos:
            return
        vistos.add(clave)
        salida.ficheros.append(p)

    for bruta in rutas:
        p = _abs(bruta)
        if not p.exists():
            salida.ignorados.append((str(p), "no existe"))
            continue
        if p.is_file():
            if p.suffix.lower() in EXTENSIONES_RAW:
                salida.ignorados.append(
                    (str(p), "formato RAW de camara: ffmpeg no lo lee (pasa un ProRes/DNx)")
                )
            else:
                anadir(p)
            continue
        if not p.is_dir():
            salida.ignorados.append((str(p), "no es ni fichero ni carpeta"))
            continue

        _rechazar_raiz(p)
        raiz = p.resolve()
        encontrados = 0
        # followlinks=False: no se entra en carpetas enlazadas. Los ficheros
        # enlazados se miran uno a uno abajo.
        for carpeta, subcarpetas, nombres in os.walk(raiz, followlinks=False):
            subcarpetas[:] = sorted(s for s in subcarpetas if not _basura(s))
            for nombre in sorted(nombres):
                f = Path(carpeta) / nombre
                if _basura(nombre):
                    continue
                suf = f.suffix.lower()
                if suf in EXTENSIONES_RAW:
                    salida.ignorados.append(
                        (str(f), "formato RAW de camara: ffmpeg no lo lee (pasa un ProRes/DNx)")
                    )
                    continue
                if not _es_video(nombre):
                    continue
                if f.is_symlink():
                    destino = f.resolve()
                    if not destino.is_relative_to(raiz):
                        salida.ignorados.append(
                            (str(f), f"enlace simbolico que sale de la carpeta (a {destino})")
                        )
                        continue
                if not f.is_file():
                    continue
                encontrados += 1
                if encontrados > MAX_FICHEROS_POR_CARPETA:
                    raise OrigenRechazado(
                        f"{p} tiene mas de {MAX_FICHEROS_POR_CARPETA} videos. Eso no parece "
                        f"la carpeta de brutos de un trabajo sino un disco entero. Pasa una "
                        f"ruta mas concreta."
                    )
                anadir(f)
    return salida
