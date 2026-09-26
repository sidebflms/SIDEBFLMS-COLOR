"""Guardar y cargar `PerfilTrabajo` por nombre (día 9, continuación 10).

Un perfil es una CARPETA, no un fichero suelto — igual de simple de mirar a
mano que un `.cube`, y sin la complicación de un zip (`core.io.bundle`/
`core.io.biblioteca` son para lo que viaja a otro Mac; un perfil de trabajo
vive en el disco de quien monta):

    <carpeta>/perfil.json     nombre + camaras conocidas (CDL en JSON)
    <carpeta>/look.cube       el look compartido, si el perfil trae uno
"""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path

from core.contracts import CDL
from core.io.cube import escribir_cube, leer_cube
from core.io.errores import ErrorFormatoCube, ErrorPerfil
from core.perfiles import PerfilCamara, PerfilTrabajo

__all__ = [
    "FICHERO_LOOK",
    "FICHERO_PERFIL",
    "borrar_perfil",
    "cargar_perfil",
    "guardar_perfil",
    "listar_perfiles",
]

FICHERO_PERFIL = "perfil.json"
FICHERO_LOOK = "look.cube"


def _cdl_a_dict(cdl: CDL) -> dict:
    return {
        "slope": list(cdl.slope),
        "offset": list(cdl.offset),
        "power": list(cdl.power),
        "saturation": cdl.saturation,
    }


def _cdl_desde_dict(datos: dict) -> CDL:
    return CDL(
        slope=tuple(datos.get("slope", (1.0, 1.0, 1.0))),
        offset=tuple(datos.get("offset", (0.0, 0.0, 0.0))),
        power=tuple(datos.get("power", (1.0, 1.0, 1.0))),
        saturation=float(datos.get("saturation", 1.0)),
    )


def guardar_perfil(perfil: PerfilTrabajo, carpeta: str | Path, *, crear_directorios: bool = False) -> Path:
    """Escribe `perfil` en `carpeta` (`perfil.json` + `look.cube` si trae look).

    Mismo criterio que `escribir_cube`/`guardar_sesion`: si `carpeta` no
    existe, se lanza en vez de crearla, salvo `crear_directorios=True`.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        if not crear_directorios:
            raise ErrorPerfil(
                f"la carpeta '{carpeta}' no existe; créala tú o llama con crear_directorios=True"
            )
        carpeta.mkdir(parents=True, exist_ok=True)

    datos = {
        "nombre": perfil.nombre,
        "camaras": [
            {
                "fabricante_contiene": c.fabricante_contiene,
                "tipo_contiene": c.tipo_contiene,
                "nombre_legible": c.nombre_legible,
                "cdl": _cdl_a_dict(c.cdl_base),
            }
            for c in perfil.camaras
        ],
    }
    (carpeta / FICHERO_PERFIL).write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")

    ruta_look = carpeta / FICHERO_LOOK
    if perfil.look is not None:
        escribir_cube(perfil.look, ruta_look, decimales=None)
    else:
        # Un perfil guardado dos veces, la segunda sin look, no debe dejar
        # el .cube de la vez anterior mintiendo sobre lo que hay.
        with contextlib.suppress(FileNotFoundError):
            ruta_look.unlink()
    return carpeta


def cargar_perfil(carpeta: str | Path) -> PerfilTrabajo:
    """Lee un perfil de `carpeta`. Lanza `ErrorPerfil` si `perfil.json` no
    existe, no es JSON válido, o el `look.cube` no se puede leer — un único
    tipo de error para que la GUI capture uno solo, igual que con
    `ResolveError`/`ErrorIO`."""
    carpeta = Path(carpeta)
    ruta_perfil = carpeta / FICHERO_PERFIL
    try:
        crudo = ruta_perfil.read_text(encoding="utf-8")
    except OSError as exc:
        raise ErrorPerfil(f"no se puede leer '{ruta_perfil}': {exc}") from exc
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise ErrorPerfil(f"'{ruta_perfil}' no es JSON válido: {exc}") from exc

    camaras = tuple(
        PerfilCamara(
            fabricante_contiene=str(c.get("fabricante_contiene", "")),
            tipo_contiene=str(c.get("tipo_contiene", "")),
            nombre_legible=str(c.get("nombre_legible", "")),
            cdl_base=_cdl_desde_dict(c.get("cdl", {})),
        )
        for c in datos.get("camaras", [])
    )

    look = None
    ruta_look = carpeta / FICHERO_LOOK
    if ruta_look.is_file():
        try:
            look = leer_cube(ruta_look)
        except ErrorFormatoCube as exc:
            raise ErrorPerfil(f"el look de este perfil no se puede leer: {exc}") from exc

    return PerfilTrabajo(nombre=str(datos.get("nombre", carpeta.name)), camaras=camaras, look=look)


def listar_perfiles(carpeta_raiz: str | Path) -> list[str]:
    """Nombres de las subcarpetas de `carpeta_raiz` que son un perfil de
    verdad (tienen `perfil.json` dentro). `[]` si `carpeta_raiz` no existe."""
    raiz = Path(carpeta_raiz)
    if not raiz.is_dir():
        return []
    return sorted(p.parent.name for p in raiz.glob(f"*/{FICHERO_PERFIL}"))


def borrar_perfil(carpeta: str | Path) -> None:
    """Borra la carpeta de un perfil, `perfil.json` incluido.

    Se niega si `carpeta` no tiene `perfil.json` dentro — es la comprobación
    de que de verdad es un perfil y no una carpeta cualquiera que alguien
    pasó por error; borrar una carpeta ajena por una ruta equivocada no es
    algo de lo que se pueda volver.
    """
    carpeta = Path(carpeta)
    if not (carpeta / FICHERO_PERFIL).is_file():
        raise ErrorPerfil(f"'{carpeta}' no tiene un {FICHERO_PERFIL}: no parece un perfil de trabajo")
    shutil.rmtree(carpeta)
