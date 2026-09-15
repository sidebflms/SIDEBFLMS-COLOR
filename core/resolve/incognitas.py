"""Las seis incognitas de la API de Resolve, todas en un solo sitio.

Manana Mario ejecuta `probe/api_probe.py` con Resolve abierto y le da una
respuesta a cada una de las seis. Cuando las tenga, **se cambian estas seis
constantes y ya**: ningun otro archivo de la app tiene que tocarse.

Hasta entonces, el valor por defecto de cada una es **el pesimista**. Si hoy
asumimos lo peor y manana resulta que Resolve puede mas, la app mejora. Si
asumimos lo mejor y manana resulta que no, la app miente.

Las seis:

=====  ===============================================================
F0-1   ¿`ExportStills(..., 'drx')` funciona en su build?
F0-2   ¿El still exportado lleva el grado aplicado o el material limpio?
F0-3   ¿`SetLUT()` acepta un `.dctl`?
F0-4   ¿Su instalacion es descarga directa o Mac App Store?
F0-5   ¿Hace falta `OpenPage("color")` antes de graduar por script?
F0-6   ¿Python 3.12 arm64 importa `fusionscript` limpiamente?
=====  ===============================================================

Ojo con una septima que NO esta aqui a proposito, porque no cambia el codigo:
si `AddVersion()` deja el grafo de nodos heredado o lo deja en blanco. No
cambia el codigo porque la comprobacion de "¿hay tres nodos?" se hace igual en
los dos casos (ver `bridge.verificar_estructura_nodos`). Lo que si cambia es si
la app **sirve para algo**, porque la API no sabe crear nodos. Esta explicado en
`core/resolve/NOTAS.md` y el probe tambien lo mide.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TipoInstalacion = Literal["descarga", "mac_app_store"]

#: Carpeta de LUTs de la instalacion por **descarga directa** (la de la web de
#: Blackmagic). Es una ruta absoluta del sistema y la app NO escribe ahi por su
#: cuenta: solo la muestra y la usa para calcular rutas relativas.
LUT_DIR_DESCARGA = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"

#: Carpeta de LUTs de la instalacion del **Mac App Store**, que vive dentro del
#: contenedor sandbox de la app. Relativa a la carpeta personal del usuario.
LUT_DIR_MAS_RELATIVO = (
    "Library/Containers/com.blackmagic-design.DaVinciResolveAppStore/Data"
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
)

#: Formatos que `album.ExportStills()` admite segun la documentacion.
FORMATOS_EXPORT_STILL: tuple[str, ...] = (
    "dpx",
    "cin",
    "tif",
    "jpg",
    "png",
    "ppm",
    "bmp",
    "xpm",
    "drx",
)

#: Paginas validas de `OpenPage()`.
PAGINAS_RESOLVE: tuple[str, ...] = (
    "media",
    "cut",
    "edit",
    "fusion",
    "color",
    "fairlight",
    "deliver",
)


@dataclass(frozen=True)
class Incognitas:
    """Las seis respuestas. Instanciala una vez y pasala al puente.

    Todos los valores por defecto son los conservadores: asumen que Resolve NO
    puede, o que hace falta el paso extra.
    """

    #: TODO(F0-1) ¿`album.ExportStills(stills, dir, prefijo, 'drx')` produce un
    #: .drx de verdad en su build? Conservador: NO. Con False, la app no ofrece
    #: la exportacion de PowerGrades a .drx y `export_stills` devuelve [].
    export_drx_funciona: bool = False

    #: TODO(F0-2) ¿El still que sale de `GrabStill()` + `ExportStills()` lleva el
    #: grado aplicado, o es el material limpio? Conservador: LIMPIO. Con False,
    #: la app NO usa stills como "antes/despues" ni para medir el grado: se mide
    #: sobre el fichero de origen y punto.
    still_lleva_grado: bool = False

    #: TODO(F0-3) ¿`timelineItem.SetLUT(n, ruta)` traga un `.dctl`? Conservador:
    #: NO. Con False, el nodo 3 (look) solo acepta `.cube`, que es lo que la app
    #: genera de todas formas.
    setlut_acepta_dctl: bool = False

    #: TODO(F0-4) ¿Descarga directa o Mac App Store? Cambia la carpeta de LUTs
    #: entera (la del MAS vive en un contenedor sandbox). Conservador no aplica
    #: aqui: no hay opcion "segura", hay una que es la correcta y otra que no.
    #: Por defecto la descarga directa, que es con mucho la mas frecuente en
    #: instalaciones de Studio con llave. Si esta mal, `SetLUT` fallara con
    #: "LUT no encontrado" y la app tiene que ensenar la ruta que esta usando.
    instalacion: TipoInstalacion = "descarga"

    #: TODO(F0-5) ¿Hace falta `OpenPage("color")` antes de escribir grado por
    #: script? Conservador: SI. Llamarlo de mas no rompe nada (solo cambia de
    #: pagina); no llamarlo cuando hacia falta deja escrituras silenciosas que
    #: no se aplican, que es muchisimo peor.
    requiere_open_page: bool = True

    #: TODO(F0-6) ¿El Python 3.12 arm64 de Mario importa `fusionscript`
    #: limpiamente? None = todavia no se sabe (es lo que hay hoy). El probe lo
    #: rellena. La app no depende de este valor para nada: solo lo ensena.
    fusionscript_importable: bool | None = None

    def describir(self) -> tuple[str, ...]:
        """Frases en castellano para ensenar en la GUI. Sin jerga."""
        return (
            f"F0-1 exportar .drx: {'si' if self.export_drx_funciona else 'no (asumido)'}",
            f"F0-2 el still lleva el grado: "
            f"{'si' if self.still_lleva_grado else 'no, sale limpio (asumido)'}",
            f"F0-3 SetLUT acepta .dctl: {'si' if self.setlut_acepta_dctl else 'no (asumido)'}",
            f"F0-4 instalacion: {self.instalacion}",
            f"F0-5 hace falta abrir la pagina de color: "
            f"{'si (asumido)' if self.requiere_open_page else 'no'}",
            f"F0-6 fusionscript importable: "
            f"{'sin comprobar' if self.fusionscript_importable is None else self.fusionscript_importable}",
        )


#: La instancia que usa todo el mundo mientras no sepamos mas.
INCOGNITAS_CONSERVADORAS = Incognitas()


def lut_dir(incognitas: Incognitas = INCOGNITAS_CONSERVADORAS, home: Path | str | None = None) -> str:
    """Carpeta de LUTs de Resolve, segun el tipo de instalacion.

    **No mira el disco.** Construye la cadena y ya; comprobar cual de las dos
    existe es trabajo del probe, que lo ejecuta Mario en su maquina. `home` se
    puede inyectar para que los tests no dependan de la carpeta personal real.
    """
    # TODO(F0-4) Aqui y solo aqui se decide la carpeta de LUTs.
    if incognitas.instalacion == "mac_app_store":
        base = Path(home) if home is not None else Path.home()
        return str(base / LUT_DIR_MAS_RELATIVO)
    return LUT_DIR_DESCARGA


def extensiones_lut_aceptadas(incognitas: Incognitas = INCOGNITAS_CONSERVADORAS) -> tuple[str, ...]:
    """Extensiones que el puente deja pasar a `SetLUT`."""
    # TODO(F0-3) Unico sitio donde se decide si el .dctl entra.
    if incognitas.setlut_acepta_dctl:
        return (".cube", ".dctl")
    return (".cube",)


def formatos_export_disponibles(
    incognitas: Incognitas = INCOGNITAS_CONSERVADORAS,
) -> tuple[str, ...]:
    """Formatos de `ExportStills` que la app se atreve a ofrecer."""
    # TODO(F0-1) Unico sitio donde se decide si el .drx esta disponible.
    if incognitas.export_drx_funciona:
        return FORMATOS_EXPORT_STILL
    return tuple(f for f in FORMATOS_EXPORT_STILL if f != "drx")


def still_sirve_para_medir(incognitas: Incognitas = INCOGNITAS_CONSERVADORAS) -> bool:
    """¿Puedo usar un still exportado como "el clip ya graduado"?

    Si sale limpio, no: medir sobre el equivaldria a medir el material de
    origen, y la app estaria comparando una cosa consigo misma.
    """
    # TODO(F0-2) Unico sitio donde se decide si el still lleva el grado.
    return incognitas.still_lleva_grado


__all__ = [
    "FORMATOS_EXPORT_STILL",
    "INCOGNITAS_CONSERVADORAS",
    "LUT_DIR_DESCARGA",
    "LUT_DIR_MAS_RELATIVO",
    "PAGINAS_RESOLVE",
    "Incognitas",
    "TipoInstalacion",
    "extensiones_lut_aceptadas",
    "formatos_export_disponibles",
    "lut_dir",
    "still_sirve_para_medir",
]
