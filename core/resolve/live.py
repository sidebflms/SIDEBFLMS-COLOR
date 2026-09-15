"""`LiveResolve`: el puente de verdad. **NO SE HA EJECUTADO NUNCA.**

=============================================================================
AVISO, Y VA EN SERIO
  Ni una linea de este archivo se ha ejecutado jamas. Se escribio de noche, con
  Resolve cerrado y sin licencia, a partir de la lista de llamadas verificadas
  de la API. Es un punto de partida para manana, no codigo probado.

  ANTES DE USARLO: ejecuta `probe/api_probe.py`. Si el probe no contesta las
  seis preguntas, esto no se toca.
=============================================================================

La regla de oro la hereda de `BaseResolveBridge`, igual que `FakeResolve`: si la
version activa del clip no es de la app, las cinco escrituras de grado lanzan
`EscrituraFueraDeVersion` antes de llamar a Resolve. Cuesta una llamada de mas a
`GetCurrentVersion` por escritura, y merece la pena.

Este es el UNICO archivo de `core/` que importa `DaVinciResolveScript`, y lo
importa **dentro de una funcion**. `core.resolve.__init__` no lo importa, asi
que abrir la app no roza Resolve. Para usarlo hay que pedirlo a proposito:

    from core.resolve.live import LiveResolve      # import explicito
    bridge = LiveResolve.conectar()                # aqui si se habla con Resolve

Todo lo demas de la app sigue hablando con `ResolveBridge`, asi que cambiar
`FakeResolve` por esto no deberia tocar ni una linea de la GUI.

LO QUE HAY QUE VERIFICAR CUANDO SE ESTRENE (esta anotado con `# SIN VERIFICAR`)
  * el identificador estable de un clip: aqui se construye con pista+posicion,
    porque la API verificada no da ningun id;
  * el nombre de un album de la galeria: `GetAlbumName` no esta en la lista de
    llamadas verificadas, asi que se usa con `hasattr` y si no esta se numeran;
  * `ExportStills` devuelve un bool, no la lista de ficheros: aqui se mira que
    ha aparecido en el directorio antes y despues.
"""

from __future__ import annotations

import os

from core.contracts import (
    CDL,
    VERSION_NAME,
    ClipRef,
    NodeInfo,
    ProjectInfo,
    ResolveError,
    StillRef,
)
from core.resolve.bridge import (
    BaseResolveBridge,
    ClipNoEncontrado,
    GrupoNoEncontrado,
    OperacionNoDisponible,
    ResolveNoConectado,
    TimelineNoAbierto,
    validar_nombre_version,
)
from core.resolve.incognitas import (
    INCOGNITAS_CONSERVADORAS,
    PAGINAS_RESOLVE,
    Incognitas,
    lut_dir,
)

#: `AddVersion` y compania piden el tipo de version: 0 = local, 1 = remota.
VERSION_LOCAL = 0

#: Capa del grafo de nodos. La app solo trabaja en la primera.
CAPA = 1

_RUTAS_MODULOS = (
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve"
    "/Developer/Scripting/Modules",
    os.path.expanduser(
        "~/Library/Containers/com.blackmagic-design.DaVinciResolveAppStore/Data"
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve"
        "/Developer/Scripting/Modules"
    ),
)


def _importar_modulo():
    """Importa `DaVinciResolveScript`. Es el unico import de Resolve del nucleo."""
    import sys

    api = os.environ.get("RESOLVE_SCRIPT_API")
    candidatas = ([os.path.join(api, "Modules")] if api else []) + list(_RUTAS_MODULOS)
    for ruta in candidatas:
        if os.path.isdir(ruta) and ruta not in sys.path:
            sys.path.append(ruta)
    try:
        import DaVinciResolveScript as dvr  # noqa: N813
    except ImportError as exc:
        raise OperacionNoDisponible(
            "no encuentro el modulo de scripting de Resolve. Ejecuta primero "
            "`python3 probe/api_probe.py --solo-diagnostico`, que te dice exactamente que "
            f"variables de entorno faltan. ({exc})"
        ) from exc
    return dvr


class LiveResolve(BaseResolveBridge):
    """Implementacion real de `core.contracts.ResolveBridge`. Sin estrenar."""

    def __init__(self, resolve, incognitas: Incognitas = INCOGNITAS_CONSERVADORAS) -> None:
        self._resolve = resolve
        self.incognitas = incognitas
        # Dos cachés separadas a proposito: `list_clips` reconstruye la de
        # clips entera, y no puede llevarse por delante los stills cogidos.
        self._cache: dict[str, object] = {}
        self._stills: dict[str, object] = {}

    @classmethod
    def conectar(cls, incognitas: Incognitas = INCOGNITAS_CONSERVADORAS) -> LiveResolve:
        """Se conecta a un Resolve que ya este abierto. No lo lanza."""
        dvr = _importar_modulo()
        resolve = dvr.scriptapp("Resolve")
        if resolve is None:
            raise ResolveNoConectado(
                "no hay nadie al otro lado. Comprueba que DaVinci Resolve Studio esta abierto "
                "y que en Preferencias > System > General el 'External scripting using' esta "
                "en 'Local'."
            )
        return cls(resolve, incognitas)

    # -- interno -----------------------------------------------------------

    def _proyecto(self):
        pm = self._resolve.GetProjectManager()
        proyecto = pm.GetCurrentProject() if pm else None
        if proyecto is None:
            raise ResolveNoConectado("no hay ningun proyecto abierto en Resolve")
        return proyecto

    def _timeline(self):
        timeline = self._proyecto().GetCurrentTimeline()
        if timeline is None:
            raise TimelineNoAbierto("no hay ningun timeline abierto en Resolve")
        return timeline

    @staticmethod
    def _id(track: int, posicion: int) -> str:
        # SIN VERIFICAR: la API verificada no da un identificador estable de
        # clip, asi que se construye con pista + posicion. Si alguien reordena
        # el timeline con la app abierta, los ids dejan de cuadrar; por eso la
        # app tiene que volver a llamar a `list_clips` despues de cada edicion.
        return f"v{track}-{posicion:03d}"

    def _item(self, clip_id: str):
        if clip_id not in self._cache:
            self.list_clips()
        item = self._cache.get(clip_id)
        if item is None:
            raise ClipNoEncontrado(f"no existe el clip {clip_id!r} en el timeline actual")
        return item

    def _grafo(self, item):
        grafo = item.GetNodeGraph(CAPA)
        if grafo is None:
            raise ResolveError("Resolve no devuelve el grafo de nodos de ese clip")
        return grafo

    # -- conexion y contexto ------------------------------------------------

    def is_connected(self) -> bool:
        try:
            return self._resolve is not None and bool(self._resolve.GetProductName())
        except Exception:  # noqa: BLE001 - un puente caido no puede tumbar la GUI
            return False

    def project_info(self) -> ProjectInfo:
        proyecto = self._proyecto()
        timeline = proyecto.GetCurrentTimeline()
        producto = str(self._resolve.GetProductName())
        return ProjectInfo(
            name=str(proyecto.GetName()),
            timeline_name=str(timeline.GetName()) if timeline else "",
            color_science=str(proyecto.GetSetting("colorScienceMode")),
            timeline_color_space=str(proyecto.GetSetting("colorSpaceTimeline")),
            lut_dir=lut_dir(self.incognitas),
            resolve_version=str(self._resolve.GetVersionString()),
            is_studio="studio" in producto.lower(),
        )

    def open_page(self, page: str) -> bool:
        if page not in PAGINAS_RESOLVE:
            raise ResolveError(f"{page!r} no es una pagina de Resolve")
        return bool(self._resolve.OpenPage(page))

    # -- clips ---------------------------------------------------------------

    def list_clips(self) -> list[ClipRef]:
        timeline = self._timeline()
        self._cache.clear()
        clips: list[ClipRef] = []
        for pista in range(1, int(timeline.GetTrackCount("video")) + 1):
            for posicion, item in enumerate(timeline.GetItemListInTrack("video", pista) or [], 1):
                clip_id = self._id(pista, posicion)
                self._cache[clip_id] = item
                ruta = None
                mpi = item.GetMediaPoolItem()
                if mpi is not None:
                    ruta = mpi.GetClipProperty("File Path") or None
                clips.append(
                    ClipRef(
                        clip_id=clip_id,
                        name=str(item.GetName()),
                        track=pista,
                        index=posicion,
                        start_frame=int(item.GetStart()),
                        end_frame=int(item.GetEnd()),
                        file_path=ruta,
                    )
                )
        return clips

    def list_nodes(self, clip_id: str) -> list[NodeInfo]:
        item = self._item(clip_id)
        grafo = self._grafo(item)
        nodos = []
        # SIN VERIFICAR: `GetNodeEnabled` no esta en la lista de llamadas
        # verificadas (si lo esta `SetNodeEnabled`). Si no existe, se asume
        # activado, que es lo que pasa el 99% de las veces.
        for i in range(1, int(grafo.GetNumNodes()) + 1):
            nodos.append(
                NodeInfo(
                    index=i,
                    label=str(grafo.GetNodeLabel(i) or ""),
                    enabled=bool(grafo.GetNodeEnabled(i))
                    if hasattr(grafo, "GetNodeEnabled")
                    else True,
                    lut_path=(grafo.GetLUT(i) or None),
                )
            )
        return nodos

    # -- versiones -----------------------------------------------------------

    def version_names(self, clip_id: str) -> list[str]:
        return list(self._item(clip_id).GetVersionNameList(VERSION_LOCAL) or [])

    def current_version(self, clip_id: str) -> str:
        actual = self._item(clip_id).GetCurrentVersion()
        if isinstance(actual, dict):
            return str(actual.get("versionName", ""))
        return str(actual or "")

    def add_version(self, clip_id: str, name: str = VERSION_NAME) -> bool:
        return bool(self._item(clip_id).AddVersion(validar_nombre_version(name), VERSION_LOCAL))

    def load_version(self, clip_id: str, name: str) -> bool:
        return bool(
            self._item(clip_id).LoadVersionByName(validar_nombre_version(name), VERSION_LOCAL)
        )

    # -- escritura de color ---------------------------------------------------

    def set_cdl(self, clip_id: str, node_index: int, cdl: CDL) -> bool:
        item = self._item(clip_id)
        idx = self._validar_nodo(node_index, int(self._grafo(item).GetNumNodes()))
        self._exigir_version_propia(clip_id, self.current_version(clip_id), "set_cdl")
        return bool(item.SetCDL(cdl.as_resolve_payload(idx)))

    def set_lut(self, clip_id: str, node_index: int, lut_rel_path: str) -> bool:
        item = self._item(clip_id)
        idx = self._validar_nodo(node_index, int(self._grafo(item).GetNumNodes()))
        ruta = self._validar_lut(lut_rel_path)
        self._exigir_version_propia(clip_id, self.current_version(clip_id), "set_lut")
        return bool(item.SetLUT(idx, ruta))

    def get_lut(self, clip_id: str, node_index: int) -> str | None:
        item = self._item(clip_id)
        idx = self._validar_nodo(node_index, int(self._grafo(item).GetNumNodes()))
        return item.GetLUT(idx) or None

    def set_node_enabled(self, clip_id: str, node_index: int, enabled: bool) -> bool:
        grafo = self._grafo(self._item(clip_id))
        idx = self._validar_nodo(node_index, int(grafo.GetNumNodes()))
        self._exigir_version_propia(clip_id, self.current_version(clip_id), "set_node_enabled")
        return bool(grafo.SetNodeEnabled(idx, bool(enabled)))

    def copy_grades(self, source_clip_id: str, target_clip_ids: list[str]) -> bool:
        if not target_clip_ids:
            return False
        destinos = [self._item(cid) for cid in target_clip_ids]
        # CopyGrades reemplaza el arbol de nodos del destino entero: se
        # comprueban TODOS antes de tocar ninguno.
        for cid in target_clip_ids:
            self._exigir_version_propia(cid, self.current_version(cid), "copy_grades")
        return bool(self._item(source_clip_id).CopyGrades(destinos))

    def reset_all_grades(self, clip_id: str) -> bool:
        self._exigir_version_propia(clip_id, self.current_version(clip_id), "reset_all_grades")
        return bool(self._grafo(self._item(clip_id)).ResetAllGrades())

    def refresh_lut_list(self) -> bool:
        return bool(self._proyecto().RefreshLUTList())

    # -- grupos de color -------------------------------------------------------

    def _grupo(self, name: str):
        # SIN VERIFICAR: `colorGroup.GetName()` no esta en la lista verificada.
        for grupo in self._proyecto().GetColorGroupsList() or []:
            if str(grupo.GetName()) == name:
                return grupo
        raise GrupoNoEncontrado(f"no existe el grupo de color {name!r}")

    def color_groups(self) -> list[str]:
        return [str(g.GetName()) for g in (self._proyecto().GetColorGroupsList() or [])]

    def add_color_group(self, name: str) -> bool:
        if not name.strip():
            raise ResolveError("un grupo de color necesita un nombre")
        return self._proyecto().AddColorGroup(name.strip()) is not None

    def delete_color_group(self, name: str) -> bool:
        try:
            grupo = self._grupo(name)
        except GrupoNoEncontrado:
            return False
        return bool(self._proyecto().DeleteColorGroup(grupo))

    def set_group_post_clip_lut(self, group: str, node_index: int, lut_rel_path: str) -> bool:
        grafo = self._grupo(group).GetPostClipNodeGraph()
        if grafo is None:
            raise ResolveError(f"el grupo {group!r} no devuelve su grafo post-clip")
        # OJO: el grafo post-clip de un grupo empieza con UN nodo. Aqui el look
        # es el nodo 1, no NODE_LOOK. Esta explicado en NOTAS.md.
        idx = self._validar_nodo(node_index, int(grafo.GetNumNodes()))
        return bool(grafo.SetLUT(idx, self._validar_lut(lut_rel_path)))

    # -- galeria ----------------------------------------------------------------

    def _album_actual(self):
        gallery = self._proyecto().GetGallery()
        if gallery is None:
            raise ResolveError("Resolve no devuelve la galeria del proyecto")
        album = gallery.GetCurrentStillAlbum()
        if album is None:
            raise ResolveError("no hay ningun album seleccionado en la galeria")
        return gallery, album

    def grab_still(self) -> StillRef:
        still = self._timeline().GrabStill()
        if still is None:
            raise ResolveError("GrabStill no ha devuelto nada")
        _gallery, album = self._album_actual()
        # SIN VERIFICAR: los stills no traen identificador. Se numeran por orden
        # dentro del album y se guarda el objeto para poder exportarlo luego.
        indice = len(album.GetStills() or [])
        clave = f"still{indice:03d}"
        self._stills[clave] = still
        return StillRef(still_id=clave, album=self._nombre_album(album), label="")

    def _nombre_album(self, album) -> str:
        gallery = self._proyecto().GetGallery()
        # SIN VERIFICAR: `GetAlbumName` no esta en la lista de llamadas
        # verificadas. Si no existe, el album se queda sin nombre legible.
        if gallery is not None and hasattr(gallery, "GetAlbumName"):
            return str(gallery.GetAlbumName(album))
        return "(album actual)"

    def gallery_albums(self) -> list[str]:
        gallery = self._proyecto().GetGallery()
        if gallery is None:
            return []
        albumes = gallery.GetGalleryPowerGradeAlbums() or []
        return [self._nombre_album(a) for a in albumes]

    def create_powergrade_album(self, name: str) -> bool:
        if not name.strip():
            raise ResolveError("un album necesita un nombre")
        gallery = self._proyecto().GetGallery()
        if gallery is None:
            return False
        return gallery.CreateGalleryPowerGradeAlbum(name.strip()) is not None

    def export_stills(
        self, stills: list[StillRef], directory: str, prefix: str, fmt: str
    ) -> list[str]:
        if not stills:
            return []
        if not os.path.isdir(directory):
            raise ResolveError(f"el directorio de salida no existe: {directory!r}")
        objetos = [self._stills.get(s.still_id) for s in stills]
        if any(o is None for o in objetos):
            raise ResolveError(
                "alguno de esos stills no lo ha cogido esta sesion; vuelve a hacer GrabStill"
            )
        _gallery, album = self._album_actual()
        antes = set(os.listdir(directory))
        # SIN VERIFICAR: ExportStills devuelve un bool, no la lista de ficheros.
        # Por eso se mira el directorio antes y despues.
        album.ExportStills(objetos, directory, prefix, str(fmt).lower())
        nuevos = sorted(set(os.listdir(directory)) - antes)
        return [os.path.join(directory, n) for n in nuevos]


__all__ = ["CAPA", "VERSION_LOCAL", "LiveResolve"]
