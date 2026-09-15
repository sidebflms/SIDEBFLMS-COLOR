"""`FakeResolve`: Resolve de mentira, pero que se comporta como el de verdad.

Es contra esto que se prueba **toda** la app, GUI incluida. Por eso no devuelve
`True` a todo: mantiene un grafo de nodos por clip y por version, sabe que una
version nueva se queda seleccionada, se queja de las rutas de LUT absolutas
igual que se quejara Resolve, y sabe fingir averias para que la GUI pueda probar
el camino de error.

QUE NO HACE, A PROPOSITO
------------------------
**No hay `get_cdl()`.** La API real no sabe leer el grado de un clip: `SetCDL`
es de solo escritura y `GetCDL` no existe. Si `FakeResolve` lo ofreciera, esta
noche alguien escribiria codigo que lee el CDL y manana ese codigo no
funcionaria. Los CDL escritos se guardan en `_grados_escritos`, que empieza por
guion bajo porque **es solo para los tests**.

COMO SE FINGE UNA AVERIA
------------------------
    fake = FakeResolve(n_clips=3)
    fake.fallar_en("set_lut")                      # lanza ResolveError siempre
    fake.fallar_en("set_cdl", "disco lleno", veces=1)  # una vez y se cura
    fake.devolver_false_en("add_version")          # devuelve False, sin excepcion
    fake.dejar_de_fallar("set_lut")                # o dejar_de_fallar() para todo

El nombre de la operacion es el del metodo del `Protocol`. Si te equivocas al
escribirlo salta un `ValueError`, para que un typo no haga que el test pase por
el motivo equivocado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

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
    NodoInvalido,
    ResolveNoConectado,
    TimelineNoAbierto,
    validar_nombre_version,
)
from core.resolve.incognitas import (
    FORMATOS_EXPORT_STILL,
    INCOGNITAS_CONSERVADORAS,
    PAGINAS_RESOLVE,
    Incognitas,
    lut_dir,
)

#: Los 24 metodos del Protocol `ResolveBridge`. Son los nombres validos para
#: `fallar_en()`. Hay un test que comprueba que esta lista sigue cuadrando con
#: el Protocol, para que no se despiste si manana cambia.
OPERACIONES: tuple[str, ...] = (
    "is_connected",
    "project_info",
    "open_page",
    "list_clips",
    "list_nodes",
    "version_names",
    "current_version",
    "add_version",
    "load_version",
    "set_cdl",
    "set_lut",
    "get_lut",
    "set_node_enabled",
    "copy_grades",
    "reset_all_grades",
    "refresh_lut_list",
    "color_groups",
    "add_color_group",
    "delete_color_group",
    "set_group_post_clip_lut",
    "grab_still",
    "gallery_albums",
    "create_powergrade_album",
    "export_stills",
)

#: Las que devuelven bool y por tanto admiten `devolver_false_en()`.
OPERACIONES_BOOL: frozenset[str] = frozenset(
    {
        "is_connected",
        "open_page",
        "add_version",
        "load_version",
        "set_cdl",
        "set_lut",
        "set_node_enabled",
        "copy_grades",
        "reset_all_grades",
        "refresh_lut_list",
        "add_color_group",
        "delete_color_group",
        "set_group_post_clip_lut",
        "create_powergrade_album",
    }
)

#: Nombre de la version que Resolve crea sola en cada clip.
VERSION_INICIAL = "Version 1"

#: Album que trae la galeria de fabrica.
ALBUM_INICIAL = "Stills 1"


# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------


@dataclass
class _Nodo:
    index: int
    label: str = ""
    enabled: bool = True
    lut_path: str | None = None
    cdl: CDL | None = None  # guardado solo para los tests; no se expone


@dataclass
class _Version:
    nombre: str
    nodos: list[_Nodo]


@dataclass
class _Clip:
    ref: ClipRef
    versiones: dict[str, _Version]
    actual: str


@dataclass
class _Grupo:
    nombre: str
    clips: list[str] = field(default_factory=list)
    post_clip: list[_Nodo] = field(default_factory=list)


@dataclass
class _Still:
    still_id: str
    album: str
    label: str = ""


@dataclass
class _Fallo:
    modo: str  # "lanzar" | "false"
    mensaje: str
    restantes: int | None  # None = para siempre


@dataclass(frozen=True)
class GradoEscrito:
    """Una escritura de CDL, tal y como quedo registrada. Solo para tests."""

    clip_id: str
    version: str
    node_index: int
    cdl: CDL


# ---------------------------------------------------------------------------
# FakeResolve
# ---------------------------------------------------------------------------


class FakeResolve(BaseResolveBridge):
    """Implementacion falsa pero seria de `core.contracts.ResolveBridge`."""

    def __init__(
        self,
        n_clips: int = 3,
        *,
        clips: list[ClipRef] | None = None,
        nodos_por_clip: int = 3,
        etiquetas: tuple[str, ...] = (),
        incognitas: Incognitas = INCOGNITAS_CONSERVADORAS,
        timeline_abierto: bool = True,
        conectado: bool = True,
        version_hereda_grafo: bool = True,
        nodos_post_clip_grupo: int = 1,
        project_name: str = "PRUEBA SIDEB",
        timeline_name: str = "TL 01",
        color_science: str = "DaVinci YRGB Color Managed",
        timeline_color_space: str = "DaVinci WG/Intermediate",
        resolve_version: str = "21.1.0 (FakeResolve)",
        is_studio: bool = True,
        home: str | None = None,
    ) -> None:
        """
        `version_hereda_grafo` es la septima incognita, la que no esta numerada:
        no sabemos si `AddVersion` deja el grafo de nodos heredado o lo deja en
        blanco. Por defecto hereda (el caso nominal); ponlo a False para probar
        que la app avisa en vez de escribir en un nodo que no existe.

        `nodos_post_clip_grupo` es 1 a proposito: el grafo post-clip de un grupo
        de color empieza con UN nodo, asi que ahi el look es el nodo 1, no el 3.
        """
        self.incognitas = incognitas
        self._conectado = conectado
        self._timeline_abierto = timeline_abierto
        self._version_hereda_grafo = version_hereda_grafo
        self._nodos_post_clip_grupo = max(1, int(nodos_post_clip_grupo))
        self._pagina = "edit"
        self._lut_list_refrescada = False
        self._fallos: dict[str, _Fallo] = {}
        self._home = home

        self._proyecto = ProjectInfo(
            name=project_name,
            timeline_name=timeline_name if timeline_abierto else "",
            color_science=color_science,
            timeline_color_space=timeline_color_space,
            lut_dir=lut_dir(incognitas, home=home),
            resolve_version=resolve_version,
            is_studio=is_studio,
        )

        refs = clips if clips is not None else _clips_de_prueba(n_clips)
        self._clips: dict[str, _Clip] = {}
        for ref in refs:
            self._clips[ref.clip_id] = _Clip(
                ref=ref,
                versiones={VERSION_INICIAL: _Version(VERSION_INICIAL, _nodos_nuevos(nodos_por_clip, etiquetas))},
                actual=VERSION_INICIAL,
            )

        self._grupos: dict[str, _Grupo] = {}
        self._albumes: dict[str, list[_Still]] = {ALBUM_INICIAL: []}
        self._album_actual = ALBUM_INICIAL
        self._contador_stills = 0

        # --- SOLO PARA TESTS ---------------------------------------------
        #: Todas las escrituras de CDL en orden. La API real no deja leer el
        #: grado de un clip, asi que esto NO tiene equivalente en Resolve y no
        #: puede usarse desde la app. Es para que los tests puedan mirar.
        self._grados_escritos: list[GradoEscrito] = []
        #: Nombres de operacion en el orden en que se llamaron.
        self._llamadas: list[str] = []
        #: Avisos que el falso quiere dejar por escrito (p.ej. un .drx que no
        #: se exporto porque la incognita F0-1 dice que hoy asumimos que no).
        self._avisos: list[str] = []

    # -- infraestructura de simulacion ------------------------------------

    def fallar_en(self, operacion: str, mensaje: str | None = None, veces: int | None = None) -> None:
        """Hace que `operacion` lance `ResolveError`. `veces=None` = siempre."""
        self._registrar_fallo(operacion, "lanzar", mensaje or f"fallo simulado en {operacion}", veces)

    def devolver_false_en(self, operacion: str, veces: int | None = None) -> None:
        """Hace que `operacion` devuelva False sin lanzar. Solo operaciones bool."""
        if operacion not in OPERACIONES_BOOL:
            raise ValueError(
                f"{operacion!r} no devuelve bool, asi que no puede 'devolver False'. "
                f"Usa fallar_en({operacion!r})."
            )
        self._registrar_fallo(operacion, "false", "", veces)

    def dejar_de_fallar(self, operacion: str | None = None) -> None:
        """Quita un fallo simulado, o todos si no se dice cual."""
        if operacion is None:
            self._fallos.clear()
            return
        _validar_operacion(operacion)
        self._fallos.pop(operacion, None)

    def conectar(self) -> None:
        self._conectado = True

    def desconectar(self) -> None:
        """Simula que Resolve se ha cerrado a media faena."""
        self._conectado = False

    def _registrar_fallo(self, operacion: str, modo: str, mensaje: str, veces: int | None) -> None:
        _validar_operacion(operacion)
        if veces is not None and veces < 1:
            raise ValueError("'veces' tiene que ser >= 1, o None para siempre")
        self._fallos[operacion] = _Fallo(modo=modo, mensaje=mensaje, restantes=veces)

    def _guardia(self, operacion: str) -> bool:
        """Registra la llamada y aplica el fallo simulado si lo hay.

        Devuelve True si la operacion tiene que contestar False.
        """
        self._llamadas.append(operacion)
        fallo = self._fallos.get(operacion)
        if fallo is None:
            return False
        if fallo.restantes is not None:
            fallo.restantes -= 1
            if fallo.restantes <= 0:
                del self._fallos[operacion]
        if fallo.modo == "lanzar":
            raise ResolveError(fallo.mensaje)
        return True

    def _exigir_conexion(self) -> None:
        if not self._conectado:
            raise ResolveNoConectado(
                "no hay conexion con DaVinci Resolve. Abrelo, comprueba que es Studio y "
                "que el scripting externo esta en 'Local' en Preferencias > System > General."
            )

    def _exigir_timeline(self) -> None:
        self._exigir_conexion()
        if not self._timeline_abierto:
            raise TimelineNoAbierto(
                "no hay ningun timeline abierto. Abre uno en la pagina de edicion o de color."
            )

    def _clip(self, clip_id: str) -> _Clip:
        self._exigir_timeline()
        clip = self._clips.get(clip_id)
        if clip is None:
            conocidos = ", ".join(self._clips) or "(ninguno)"
            raise ClipNoEncontrado(f"no existe el clip {clip_id!r}. En el timeline hay: {conocidos}")
        return clip

    def _version_actual(self, clip: _Clip) -> _Version:
        return clip.versiones[clip.actual]

    # -- conexion y contexto ----------------------------------------------

    def is_connected(self) -> bool:
        if self._guardia("is_connected"):
            return False
        return self._conectado

    def project_info(self) -> ProjectInfo:
        self._guardia("project_info")
        self._exigir_conexion()
        return self._proyecto

    def open_page(self, page: str) -> bool:
        if self._guardia("open_page"):
            return False
        self._exigir_conexion()
        if page not in PAGINAS_RESOLVE:
            raise ResolveError(
                f"{page!r} no es una pagina de Resolve. Las validas: {', '.join(PAGINAS_RESOLVE)}"
            )
        self._pagina = page
        return True

    @property
    def pagina_actual(self) -> str:
        return self._pagina

    # -- clips --------------------------------------------------------------

    def list_clips(self) -> list[ClipRef]:
        self._guardia("list_clips")
        self._exigir_timeline()
        return [c.ref for c in self._clips.values()]

    def list_nodes(self, clip_id: str) -> list[NodeInfo]:
        self._guardia("list_nodes")
        clip = self._clip(clip_id)
        return [
            NodeInfo(index=n.index, label=n.label, enabled=n.enabled, lut_path=n.lut_path)
            for n in self._version_actual(clip).nodos
        ]

    # -- versiones ----------------------------------------------------------

    def version_names(self, clip_id: str) -> list[str]:
        self._guardia("version_names")
        return list(self._clip(clip_id).versiones)

    def current_version(self, clip_id: str) -> str:
        self._guardia("current_version")
        return self._clip(clip_id).actual

    def add_version(self, clip_id: str, name: str = VERSION_NAME) -> bool:
        if self._guardia("add_version"):
            return False
        clip = self._clip(clip_id)
        nombre = validar_nombre_version(name)
        if nombre in clip.versiones:
            # Resolve no duplica nombres: contesta que no y se queda como estaba.
            return False
        if self._version_hereda_grafo:
            nodos = [replace(n) for n in self._version_actual(clip).nodos]
        else:
            nodos = _nodos_nuevos(1, ())
        clip.versiones[nombre] = _Version(nombre, nodos)
        # Crear una version la deja seleccionada. Esto es la semantica real y es
        # justo lo que hace que escribir despues sea seguro.
        clip.actual = nombre
        return True

    def load_version(self, clip_id: str, name: str) -> bool:
        if self._guardia("load_version"):
            return False
        clip = self._clip(clip_id)
        nombre = validar_nombre_version(name)
        if nombre not in clip.versiones:
            return False
        clip.actual = nombre
        return True

    # -- escritura de color --------------------------------------------------

    def set_cdl(self, clip_id: str, node_index: int, cdl: CDL) -> bool:
        if self._guardia("set_cdl"):
            return False
        clip = self._clip(clip_id)
        version = self._version_actual(clip)
        idx = self._validar_nodo(node_index, len(version.nodos))
        if not isinstance(cdl, CDL):
            raise ResolveError(f"set_cdl espera un CDL, llego {type(cdl).__name__}")
        # `as_resolve_payload` valida de paso que el indice es 1-based y deja el
        # diccionario tal cual se lo pasariamos a Resolve.
        cdl.as_resolve_payload(idx)
        version.nodos[idx - 1].cdl = cdl
        self._grados_escritos.append(
            GradoEscrito(clip_id=clip_id, version=version.nombre, node_index=idx, cdl=cdl)
        )
        return True

    def set_lut(self, clip_id: str, node_index: int, lut_rel_path: str) -> bool:
        if self._guardia("set_lut"):
            return False
        clip = self._clip(clip_id)
        version = self._version_actual(clip)
        idx = self._validar_nodo(node_index, len(version.nodos))
        ruta = self._validar_lut(lut_rel_path)
        version.nodos[idx - 1].lut_path = ruta
        return True

    def get_lut(self, clip_id: str, node_index: int) -> str | None:
        self._guardia("get_lut")
        clip = self._clip(clip_id)
        version = self._version_actual(clip)
        idx = self._validar_nodo(node_index, len(version.nodos))
        return version.nodos[idx - 1].lut_path

    def set_node_enabled(self, clip_id: str, node_index: int, enabled: bool) -> bool:
        if self._guardia("set_node_enabled"):
            return False
        clip = self._clip(clip_id)
        version = self._version_actual(clip)
        idx = self._validar_nodo(node_index, len(version.nodos))
        version.nodos[idx - 1].enabled = bool(enabled)
        return True

    def copy_grades(self, source_clip_id: str, target_clip_ids: list[str]) -> bool:
        if self._guardia("copy_grades"):
            return False
        origen = self._clip(source_clip_id)
        if not target_clip_ids:
            # Lista vacia: no se ha copiado a nadie. No es una averia, es un no.
            return False
        destinos = [self._clip(cid) for cid in target_clip_ids]
        nodos = self._version_actual(origen).nodos
        for destino in destinos:
            actual = self._version_actual(destino)
            actual.nodos = [replace(n) for n in nodos]
            for n in actual.nodos:
                if n.cdl is not None:
                    self._grados_escritos.append(
                        GradoEscrito(
                            clip_id=destino.ref.clip_id,
                            version=actual.nombre,
                            node_index=n.index,
                            cdl=n.cdl,
                        )
                    )
        return True

    def reset_all_grades(self, clip_id: str) -> bool:
        if self._guardia("reset_all_grades"):
            return False
        clip = self._clip(clip_id)
        for n in self._version_actual(clip).nodos:
            n.cdl = None
            n.lut_path = None
            n.enabled = True
        return True

    def refresh_lut_list(self) -> bool:
        if self._guardia("refresh_lut_list"):
            return False
        self._exigir_conexion()
        self._lut_list_refrescada = True
        return True

    @property
    def lut_list_refrescada(self) -> bool:
        return self._lut_list_refrescada

    # -- grupos de color -----------------------------------------------------

    def color_groups(self) -> list[str]:
        self._guardia("color_groups")
        self._exigir_conexion()
        return list(self._grupos)

    def add_color_group(self, name: str) -> bool:
        if self._guardia("add_color_group"):
            return False
        self._exigir_conexion()
        if not isinstance(name, str) or not name.strip():
            raise ResolveError("un grupo de color necesita un nombre")
        nombre = name.strip()
        if nombre in self._grupos:
            return False
        self._grupos[nombre] = _Grupo(
            nombre=nombre, post_clip=_nodos_nuevos(self._nodos_post_clip_grupo, ())
        )
        return True

    def delete_color_group(self, name: str) -> bool:
        if self._guardia("delete_color_group"):
            return False
        self._exigir_conexion()
        if name not in self._grupos:
            return False
        del self._grupos[name]
        return True

    def set_group_post_clip_lut(self, group: str, node_index: int, lut_rel_path: str) -> bool:
        if self._guardia("set_group_post_clip_lut"):
            return False
        self._exigir_conexion()
        grupo = self._grupos.get(group)
        if grupo is None:
            conocidos = ", ".join(self._grupos) or "(ninguno)"
            raise GrupoNoEncontrado(f"no existe el grupo de color {group!r}. Hay: {conocidos}")
        idx = self._validar_nodo(node_index, len(grupo.post_clip))
        ruta = self._validar_lut(lut_rel_path)
        grupo.post_clip[idx - 1].lut_path = ruta
        return True

    def nodos_post_clip(self, group: str) -> list[NodeInfo]:
        """Estado del grafo post-clip de un grupo. No esta en el Protocol: es
        para que los tests y la GUI de depuracion puedan mirar."""
        grupo = self._grupos.get(group)
        if grupo is None:
            raise GrupoNoEncontrado(f"no existe el grupo de color {group!r}")
        return [
            NodeInfo(index=n.index, label=n.label, enabled=n.enabled, lut_path=n.lut_path)
            for n in grupo.post_clip
        ]

    # -- galeria -------------------------------------------------------------

    def grab_still(self) -> StillRef:
        self._guardia("grab_still")
        self._exigir_timeline()
        self._contador_stills += 1
        still = _Still(still_id=f"still{self._contador_stills:03d}", album=self._album_actual)
        self._albumes[self._album_actual].append(still)
        return StillRef(still_id=still.still_id, album=still.album, label=still.label)

    def gallery_albums(self) -> list[str]:
        self._guardia("gallery_albums")
        self._exigir_conexion()
        return list(self._albumes)

    def create_powergrade_album(self, name: str) -> bool:
        if self._guardia("create_powergrade_album"):
            return False
        self._exigir_conexion()
        if not isinstance(name, str) or not name.strip():
            raise ResolveError("un album necesita un nombre")
        nombre = name.strip()
        if nombre in self._albumes:
            return False
        self._albumes[nombre] = []
        return True

    def set_current_still_album(self, name: str) -> bool:
        """`gallery.SetCurrentStillAlbum`. No esta en el Protocol pero la API si
        lo tiene, y `grab_still` necesita saber en que album cae el still."""
        self._exigir_conexion()
        if name not in self._albumes:
            return False
        self._album_actual = name
        return True

    def export_stills(
        self, stills: list[StillRef], directory: str, prefix: str, fmt: str
    ) -> list[str]:
        """Escribe ficheros DE VERDAD, y **solo** dentro de `directory`.

        Los ficheros no son imagenes: son un texto que dice de donde salen. Si
        algun dia hacen falta pixeles de verdad, se genera con
        `tests/media/generate.py`, no aqui.
        """
        self._guardia("export_stills")
        self._exigir_conexion()
        formato = str(fmt).lower()
        if formato not in FORMATOS_EXPORT_STILL:
            raise ResolveError(
                f"formato {fmt!r} no valido. ExportStills admite: "
                f"{', '.join(FORMATOS_EXPORT_STILL)}"
            )
        if not stills:
            return []
        if not isinstance(prefix, str) or not prefix.strip():
            raise ResolveError("ExportStills necesita un prefijo para los ficheros")
        if any(c in prefix for c in ("/", "\\", "..")):
            raise ResolveError(f"el prefijo {prefix!r} no puede contener separadores de ruta")
        if not os.path.isdir(directory):
            raise ResolveError(f"el directorio de salida no existe: {directory!r}")

        conocidos = {s.still_id for lista in self._albumes.values() for s in lista}
        desconocidos = [s.still_id for s in stills if s.still_id not in conocidos]
        if desconocidos:
            raise ResolveError(f"estos stills no estan en la galeria: {', '.join(desconocidos)}")

        # TODO(F0-1) Si el .drx no funciona en su build, ExportStills devuelve
        # una lista vacia y no escribe nada. Es justo lo que hay que simular.
        if formato == "drx" and not self.incognitas.export_drx_funciona:
            self._avisos.append(
                "ExportStills('drx') no ha escrito nada: la incognita F0-1 sigue sin verificar "
                "y hoy asumimos que no funciona."
            )
            return []

        escritos: list[str] = []
        for i, still in enumerate(stills, start=1):
            ruta = os.path.join(directory, f"{prefix}{i:03d}.{formato}")
            marca = "con el grado aplicado" if self.incognitas.still_lleva_grado else "SIN grado"
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(
                    f"FakeResolve still {still.still_id} album={still.album} formato={formato} "
                    f"({marca}, incognita F0-2)\n"
                )
            escritos.append(ruta)
        return escritos

    # -- inspeccion SOLO PARA TESTS -----------------------------------------

    def _cdl_escrito(self, clip_id: str, node_index: int, version: str | None = None) -> CDL | None:
        """El CDL que hay ahora mismo en ese nodo. **Solo para tests**: en
        Resolve de verdad esto no se puede leer (no existe `GetCDL`)."""
        clip = self._clips.get(clip_id)
        if clip is None:
            raise ClipNoEncontrado(f"no existe el clip {clip_id!r}")
        nombre = version or clip.actual
        if nombre not in clip.versiones:
            raise ResolveError(f"el clip {clip_id!r} no tiene la version {nombre!r}")
        nodos = clip.versiones[nombre].nodos
        if node_index < 1 or node_index > len(nodos):
            raise NodoInvalido(f"nodo {node_index} fuera de rango (hay {len(nodos)})")
        return nodos[node_index - 1].cdl

    def _lut_escrito(self, clip_id: str, node_index: int, version: str | None = None) -> str | None:
        """El LUT de un nodo de una version concreta. Solo para tests: el
        `get_lut` publico solo mira la version activa, como la API real."""
        clip = self._clips.get(clip_id)
        if clip is None:
            raise ClipNoEncontrado(f"no existe el clip {clip_id!r}")
        nombre = version or clip.actual
        if nombre not in clip.versiones:
            raise ResolveError(f"el clip {clip_id!r} no tiene la version {nombre!r}")
        nodos = clip.versiones[nombre].nodos
        if node_index < 1 or node_index > len(nodos):
            raise NodoInvalido(f"nodo {node_index} fuera de rango (hay {len(nodos)})")
        return nodos[node_index - 1].lut_path


# ---------------------------------------------------------------------------
# Ayudas de construccion
# ---------------------------------------------------------------------------


def _validar_operacion(operacion: str) -> None:
    if operacion not in OPERACIONES:
        raise ValueError(
            f"{operacion!r} no es una operacion del puente. Las validas: {', '.join(OPERACIONES)}"
        )


def _nodos_nuevos(cuantos: int, etiquetas: tuple[str, ...]) -> list[_Nodo]:
    if cuantos < 1:
        raise ValueError("un clip de Resolve siempre tiene al menos un nodo")
    nodos = []
    for i in range(1, cuantos + 1):
        # Por defecto sin etiqueta, que es lo realista: `GetNodeLabel` devuelve
        # cadena vacia mientras nadie las ponga a mano, y la API NO tiene
        # `SetNodeLabel`, asi que la app no puede ponerlas.
        etiqueta = etiquetas[i - 1] if i - 1 < len(etiquetas) else ""
        nodos.append(_Nodo(index=i, label=etiqueta))
    return nodos


def _clips_de_prueba(n: int) -> list[ClipRef]:
    """Un timeline de mentira de `n` clips seguidos, de 120 fotogramas cada uno."""
    if n < 0:
        raise ValueError("n_clips no puede ser negativo")
    clips = []
    inicio = 0
    for i in range(1, n + 1):
        clips.append(
            ClipRef(
                clip_id=f"clip{i:03d}",
                name=f"A001_C{i:03d}",
                track=1,
                index=i,
                start_frame=inicio,
                end_frame=inicio + 119,
                file_path=None,  # no hay material real y no lo va a haber
            )
        )
        inicio += 120
    return clips


__all__ = [
    "ALBUM_INICIAL",
    "OPERACIONES",
    "OPERACIONES_BOOL",
    "VERSION_INICIAL",
    "FakeResolve",
    "GradoEscrito",
]
