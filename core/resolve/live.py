"""`LiveResolve`: el puente de verdad.

=============================================================================
ESTADO, día 9 (continuación 8-9): YA SE HA EJECUTADO, de verdad
  Se escribió de noche, con Resolve cerrado, a partir de la lista de llamadas
  verificadas de la API — eso seguía siendo cierto hasta el 2026-09-25. Ese
  día, con permiso explícito de Mario y contra su Resolve real (Studio
  21.1.0.17), se ejecutaron de verdad: `list_clips`, `list_nodes`,
  `project_info`, y (vía `gui/estado_real.py` + `lanzar.py`) el camino
  completo de construir un `EstadoDemo` real. Sigue siendo cierto que NINGUNA
  escritura de color (`add_version`/`set_cdl`/`set_lut`) se ha ejecutado
  nunca contra Resolve real — lo que sí se probó por separado, con llamadas
  sueltas fuera de este archivo, fue `probe/api_probe.py` (que no pasa por
  `LiveResolve`, ver su propio módulo).
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

`gui/` tiene PROHIBIDO importar esto (`tests/test_gui_regla_de_oro.py::
test_la_gui_no_importa_el_puente_de_verdad`) — quien conecta de verdad es
`lanzar.py`, en la raíz del repo, no ningún fichero de `gui/`.

LO QUE SE HA VERIFICADO CONTRA RESOLVE REAL (2026-09-25)
  * el identificador estable de un clip: `GetUniqueId()` SÍ existe y da un
    UUID estable de verdad — ya no hace falta la construcción por
    pista+posición salvo como respaldo si algún Resolve más viejo no lo trae;
  * `GetAlbumName` SÍ existe y es invocable;
  * `GetNodeEnabled` NO es invocable en esta build, pese a que `hasattr`
    decía que sí (bug real encontrado y arreglado, ver `_llamable` más abajo);
  * `AddVersion()` NO hereda el árbol de nodos: la versión nueva empieza
    siempre con un solo nodo (`core/resolve/NOTAS.md` §4);
  * `ApplyGradeFromDRX` **NO EXISTE** como método de `TimelineItem` en esta
    build (comprobado con `dir(item)` completo, no sólo probando la llamada)
    — la vía "aplicar un PowerGrade de plantilla" que se apuntaba como
    posible solución al punto anterior queda descartada tal cual se pensó.
    `CopyGrades` sí existe y sí está cableado (`copy_grades`): una vez que
    UN clip tenga los 3 nodos preparados a mano, se podría propagar por
    script a los demás — sin construir todavía esa pieza.

LO QUE SIGUE SIN VERIFICAR (anotado con `# SIN VERIFICAR`)
  * `colorGroup.GetName()`: no se ha podido probar, el proyecto de pruebas
    usado no tenía ningún grupo de color;
  * `ExportStills` devuelve un bool, no la lista de ficheros: aqui se mira que
    ha aparecido en el directorio antes y despues (parcialmente confirmado
    para `.drx` vía `probe/api_probe.py`, no vía este archivo).
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
    nombre_de_version,
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


def _llamable(obj, nombre: str) -> bool:
    """¿`obj.nombre` es un método de verdad que se puede llamar?

    **NO usar `hasattr(obj, nombre)` para esto** — confirmado el día 9 contra
    Resolve real (Studio 21.1.0.17): los objetos remotos de Fusion devuelven
    `None` para un método que no existe en esa build, en vez de lanzar
    `AttributeError`. `hasattr` sólo comprueba que `getattr` no reviente, así
    que decía `True` para `GetNodeEnabled` aunque su valor fuera `None` —
    `list_nodes()` reventaba con `TypeError: 'NoneType' object is not
    callable` la primera vez que se probó contra un timeline real. Esta
    función mira el valor de verdad, no si acceder a él revienta.
    """
    return callable(getattr(obj, nombre, None))


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

    def __init__(
        self,
        resolve,
        incognitas: Incognitas = INCOGNITAS_CONSERVADORAS,
        PELIGRO_escribir_fuera_de_la_version: bool = False,
    ) -> None:
        self._resolve = resolve
        self.incognitas = incognitas
        # OJO, hallazgo E-3 de la revision: esto TIENE que asignarse en la
        # instancia, igual que en FakeResolve. Si se deja heredado de la clase
        # base, cualquiera que escriba
        # `BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True` en
        # cualquier sitio apaga la regla de oro AQUI, en el puente de verdad, y
        # la deja puesta en el falso. O sea: todos los tests en verde esta noche
        # y ni una proteccion el dia que esto hable con Resolve. Hay un test que
        # compara los dos __init__ leyendo el AST para que no vuelva a pasar.
        self.PELIGRO_escribir_fuera_de_la_version = PELIGRO_escribir_fuera_de_la_version
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
    def _id(item, track: int, posicion: int) -> str:
        # CONFIRMADO el 2026-09-25 contra Resolve real (Studio 21.1.0.17):
        # `TimelineItem.GetUniqueId()` SI existe y da un UUID estable de
        # verdad (comprobado pidiendolo dos veces seguidas sobre el mismo
        # clip). Se usa cuando esta disponible -- ya no hace falta volver a
        # llamar a `list_clips()` solo porque alguien reordeno el timeline.
        # Con `_llamable`, no `hasattr` (ver el bug real de `GetNodeEnabled`
        # en este mismo modulo): un Resolve mas viejo sin este metodo no
        # tiene por que devolver un valor invocable.
        if _llamable(item, "GetUniqueId"):
            return str(item.GetUniqueId())
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
                clip_id = self._id(item, pista, posicion)
                self._cache[clip_id] = item
                ruta = None
                # CONFIRMADO el 2026-09-25 contra Resolve real (SUPUESTOS.md
                # fila B): estas cinco claves de GetClipProperty existen tal
                # cual. Hasta el día 9 (continuación 10) esta función no las
                # leía -- el resto de la app (core.colormgmt) nunca veía
                # metadata de cámara real, sólo `None`.
                manufacturer = tipo = gamma = notas = espacio = None
                mpi = item.GetMediaPoolItem()
                if mpi is not None:
                    ruta = mpi.GetClipProperty("File Path") or None
                    manufacturer = mpi.GetClipProperty("Camera Manufacturer") or None
                    tipo = mpi.GetClipProperty("Camera Type") or None
                    gamma = mpi.GetClipProperty("Gamma Notes") or None
                    notas = mpi.GetClipProperty("Camera Notes") or None
                    espacio = mpi.GetClipProperty("Input Color Space") or None
                clips.append(
                    ClipRef(
                        clip_id=clip_id,
                        name=str(item.GetName()),
                        track=pista,
                        index=posicion,
                        start_frame=int(item.GetStart()),
                        end_frame=int(item.GetEnd()),
                        file_path=ruta,
                        camera_manufacturer=manufacturer,
                        camera_type=tipo,
                        gamma_notes=gamma,
                        camera_notes=notas,
                        input_color_space=espacio,
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
                    enabled=bool(grafo.GetNodeEnabled(i)) if _llamable(grafo, "GetNodeEnabled") else True,
                    lut_path=(grafo.GetLUT(i) or None),
                )
            )
        return nodos

    # -- versiones -----------------------------------------------------------

    def version_names(self, clip_id: str) -> list[str]:
        return list(self._item(clip_id).GetVersionNameList(VERSION_LOCAL) or [])

    def current_version(self, clip_id: str) -> str:
        """Nombre de la version activa, o cadena vacia si no hay forma de saberlo.

        La regla de oro pregunta esto en CADA escritura, asi que es la llamada
        mas critica de todo el puente y la que menos se ha probado: **nadie la
        ha visto contestar contra Resolve de verdad.**

        Aqui no se decide nada: se traduce. `nombre_de_version()` (de
        `bridge.py`) es el unico sitio del proyecto que interpreta la respuesta
        —una cadena, o un diccionario con `versionName`— y devuelve `""` para
        todo lo demas. Quien decide es `_exigir_version_propia`, que con un `""`
        bloquea con `VersionIndeterminada` y un mensaje que explica que mirar.

        Aqui no se adivina un nombre ni se inventa un `SIDEB COLOR` por defecto:
        eso convertiria un fallo de la API en una escritura encima del usuario.

        **Si la llamada revienta, la excepcion sale.** No se traga: para las
        escrituras ya la recoge `_version_activa_o_rota()`, que la convierte en
        el mismo `VersionIndeterminada` que las otras tres respuestas raras; y
        para quien pregunte por su cuenta (`asegurar_version`, la GUI) es mejor
        ver el error de verdad que un `""` que parece una respuesta.
        """
        return nombre_de_version(self._item(clip_id).GetCurrentVersion())

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
        self._exigir_version_propia(clip_id, self._version_activa_o_rota(clip_id), "set_cdl")
        return bool(item.SetCDL(cdl.as_resolve_payload(idx)))

    def set_lut(self, clip_id: str, node_index: int, lut_rel_path: str) -> bool:
        item = self._item(clip_id)
        idx = self._validar_nodo(node_index, int(self._grafo(item).GetNumNodes()))
        ruta = self._validar_lut(lut_rel_path)
        self._exigir_version_propia(clip_id, self._version_activa_o_rota(clip_id), "set_lut")
        return bool(item.SetLUT(idx, ruta))

    def get_lut(self, clip_id: str, node_index: int) -> str | None:
        item = self._item(clip_id)
        idx = self._validar_nodo(node_index, int(self._grafo(item).GetNumNodes()))
        return item.GetLUT(idx) or None

    def set_node_enabled(self, clip_id: str, node_index: int, enabled: bool) -> bool:
        grafo = self._grafo(self._item(clip_id))
        idx = self._validar_nodo(node_index, int(grafo.GetNumNodes()))
        self._exigir_version_propia(clip_id, self._version_activa_o_rota(clip_id), "set_node_enabled")
        return bool(grafo.SetNodeEnabled(idx, bool(enabled)))

    def copy_grades(self, source_clip_id: str, target_clip_ids: list[str]) -> bool:
        if not target_clip_ids:
            return False
        destinos = [self._item(cid) for cid in target_clip_ids]
        # CopyGrades reemplaza el arbol de nodos del destino entero: se
        # comprueban TODOS antes de tocar ninguno.
        for cid in target_clip_ids:
            self._exigir_version_propia(cid, self._version_activa_o_rota(cid), "copy_grades")
        return bool(self._item(source_clip_id).CopyGrades(destinos))

    def reset_all_grades(self, clip_id: str) -> bool:
        self._exigir_version_propia(clip_id, self._version_activa_o_rota(clip_id), "reset_all_grades")
        return bool(self._grafo(self._item(clip_id)).ResetAllGrades())

    def refresh_lut_list(self) -> bool:
        return bool(self._proyecto().RefreshLUTList())

    # -- grupos de color -------------------------------------------------------

    def _nombre_grupo(self, grupo) -> str | None:
        # SIN VERIFICAR: `colorGroup.GetName()` no esta en la lista
        # verificada. Si no existe, este grupo no se puede identificar por
        # nombre — se salta en vez de reventar (ver `_llamable`).
        if not _llamable(grupo, "GetName"):
            return None
        return str(grupo.GetName())

    def _grupo(self, name: str):
        for grupo in self._proyecto().GetColorGroupsList() or []:
            if self._nombre_grupo(grupo) == name:
                return grupo
        raise GrupoNoEncontrado(f"no existe el grupo de color {name!r}")

    def color_groups(self) -> list[str]:
        return [
            nombre
            for g in (self._proyecto().GetColorGroupsList() or [])
            if (nombre := self._nombre_grupo(g)) is not None
        ]

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
        """Pone un LUT en el grafo post-clip de un GRUPO de color.

        ESTE CAMINO QUEDA FUERA DE LA REGLA DE ORO, Y NO PUEDE ESTAR DENTRO
        -----------------------------------------------------------------
        Las cinco escrituras de grado de un clip comprueban la version activa
        antes de tocar nada. Esta **no**, porque un grafo post-clip de un grupo
        no es de ningun clip: no tiene versiones, asi que no hay nada que
        comprobar. No es un descuido del arreglo R-0; es que aqui esa red de
        seguridad no existe.

        Lo que eso significa en la practica, y hay que decirlo claro: **escribir
        el LUT de un grupo pisa lo que el usuario tuviera en ese nodo, sin red y
        sin deshacer.** El grado de los clips no se toca (eso sigue a salvo en
        sus versiones), pero el look del grupo sí.

        Lo que SÍ protege aqui:

        * el grupo tiene que existir (si no, `GrupoNoEncontrado`);
        * el indice de nodo se valida contra los nodos que hay de verdad, y en
          un post-clip de grupo **el look es el nodo 1, no `NODE_LOOK`**;
        * la ruta del LUT se valida igual que en todas partes.

        Y lo que se puede hacer desde fuera, que es lo unico que hay: leer antes
        lo que hubiera con `GetLUT` sobre ese mismo grafo y apuntarlo, para
        poder devolverlo. La app no lo hace hoy porque no usa grupos.

        Ver NOTAS.md, apartado 2.8.
        """
        grafo = self._grupo(group).GetPostClipNodeGraph()
        if grafo is None:
            raise ResolveError(f"el grupo {group!r} no devuelve su grafo post-clip")
        # OJO: el grafo post-clip de un grupo empieza con UN nodo. Aqui el look
        # es el nodo 1, no NODE_LOOK. Esta explicado en NOTAS.md.
        idx = self._validar_nodo(node_index, int(grafo.GetNumNodes()))
        return bool(grafo.SetLUT(idx, self._validar_lut(lut_rel_path)))

    def clip_color_group(self, clip_id: str) -> str | None:
        """Nombre del grupo de color del clip, o `None` si no está en ninguno.

        SOLO LECTURA y fuera del Protocol. Verificado contra Resolve Studio
        21.1.0.17 el 2026-09-26 (timeline temporal, ya borrada):
        `TimelineItem.GetColorGroup()` devuelve `None` sin grupo y un
        `ColorGroup` con `GetName()` funcional después de asignarlo.
        """
        item = self._item(clip_id)
        if not _llamable(item, "GetColorGroup"):
            return None
        grupo = item.GetColorGroup()
        return None if grupo is None else self._nombre_grupo(grupo)

    def group_post_clip_lut(self, group: str) -> str | None:
        """LUT que trae el nodo 1 del post-clip de un grupo, o `None`. SOLO
        LECTURA y fuera del Protocol: es lo que hay que mirar ANTES de que un
        look de grupo se sume al de la app."""
        grafo = self._grupo(group).GetPostClipNodeGraph()
        if grafo is None or int(grafo.GetNumNodes()) < 1:
            return None
        return grafo.GetLUT(1) or None

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
        # verificadas. Si no existe, el album se queda sin nombre legible
        # (ver `_llamable`: confirmado en esta build que SÍ existe, pero se
        # deja la guarda por si otra versión de Resolve no la trae).
        if gallery is not None and _llamable(gallery, "GetAlbumName"):
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
