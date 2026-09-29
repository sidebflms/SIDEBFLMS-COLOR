"""`core.resolve.live`: sin conexión a Resolve real no se puede probar todo
(`LiveResolve.conectar()` de verdad, y las cinco escrituras de color, siguen
sin ejecutarse en un test automatizado), pero `_llamable`, `_id`, y la
resistencia a un `self._resolve` que se porta mal son lógica pura y merecen
su test:

- `_llamable` nace de un bug real encontrado el día 9 contra Resolve real
  (Studio 21.1.0.17): `list_nodes()` reventaba con
  `TypeError: 'NoneType' object is not callable` porque
  `hasattr(grafo, "GetNodeEnabled")` decía `True` aunque el valor de ese
  atributo fuera `None`, no un método.
- `_id` usa `GetUniqueId()` cuando está disponible (confirmado ese mismo día
  que sí lo está, y que da un UUID estable), con la construcción antigua por
  pista+posición como respaldo si algún Resolve más viejo no lo trae.
- `_proyecto`/`_timeline` traducen cualquier excepción cruda de Resolve (cerrado,
  colgado, conexión de scripting caída) a `ResolveNoConectado`/`TimelineNoAbierto`,
  que es lo único que la GUI captura (ver `core/resolve/bridge.py`).
- `_item` no se fía de la caché de clips si Resolve ha cambiado de proyecto o de
  timeline desde el último `list_clips()`: el respaldo pista+posición de `_id()`
  no es globalmente único, así que sin esta comprobación un `clip_id` reciclado
  en otro proyecto devolvería un `TimelineItem` de un timeline distinto.

`LiveResolve` no importa `DaVinciResolveScript` en su `__init__`: sólo
`conectar()` lo hace. Por eso estos dobles construyen la instancia a mano, con
un `resolve` de mentira, sin tocar Resolve para nada.
"""

from __future__ import annotations

import pytest

from core.resolve.bridge import ClipNoEncontrado, ResolveNoConectado, TimelineNoAbierto
from core.resolve.live import LiveResolve, _llamable


class _ConMetodoDeVerdad:
    def Metodo(self):
        return 42


class _ConAtributoNone:
    """El caso real: el atributo EXISTE (hasattr diría True) pero vale None
    -- lo que devuelven, contra Resolve real, los métodos no implementados
    en un objeto remoto de Fusion."""

    Metodo = None


class _SinElAtributo:
    pass


def test_llamable_dice_si_para_un_metodo_de_verdad():
    assert _llamable(_ConMetodoDeVerdad(), "Metodo") is True


def test_llamable_dice_no_si_el_atributo_existe_pero_es_none():
    """El caso que rompió list_nodes() contra Resolve real: hasattr() habría
    dicho True aquí, y por eso NO se usa hasattr en core.resolve.live."""
    obj = _ConAtributoNone()
    assert hasattr(obj, "Metodo") is True  # confirma que hasattr se equivocaría
    assert _llamable(obj, "Metodo") is False


def test_llamable_dice_no_si_el_atributo_no_existe():
    assert _llamable(_SinElAtributo(), "Metodo") is False


class _ItemConGetUniqueId:
    def GetUniqueId(self):
        return "0ef258ff-f098-442d-93ee-8995db2f40b6"


class _ItemSinGetUniqueId:
    """El caso `hasattr` mentiría: GetUniqueId "existe" pero vale None,
    igual que GetNodeEnabled en el bug real de _llamable."""

    GetUniqueId = None


def test_id_usa_get_unique_id_cuando_esta_disponible():
    item = _ItemConGetUniqueId()
    assert LiveResolve._id(item, 1, 1) == "0ef258ff-f098-442d-93ee-8995db2f40b6"


def test_id_cae_a_pista_posicion_si_get_unique_id_no_es_invocable():
    item = _ItemSinGetUniqueId()
    assert LiveResolve._id(item, 2, 7) == "v2-007"


# ---------------------------------------------------------------------------
# Dobles minimos de la API de Resolve, para probar _proyecto/_timeline/_item
# sin abrir Resolve. Solo implementan lo que estos tres metodos tocan.
# ---------------------------------------------------------------------------


class _ItemDeMentira:
    GetUniqueId = None  # fuerza el respaldo pista+posicion, igual que arriba

    def __init__(self, name: str = "clip"):
        self._name = name

    def GetName(self):
        return self._name

    def GetStart(self):
        return 0

    def GetEnd(self):
        return 100

    def GetMediaPoolItem(self):
        return None


class _TimelineDeMentira:
    def __init__(self, name: str, items: list | None = None):
        self._name = name
        self._items = items or []

    def GetName(self):
        return self._name

    def GetTrackCount(self, _tipo):
        return 1

    def GetItemListInTrack(self, _tipo, pista):
        return self._items if pista == 1 else []


class _ProyectoDeMentira:
    def __init__(self, name: str, timeline: _TimelineDeMentira | None):
        self._name = name
        self._timeline = timeline

    def GetName(self):
        return self._name

    def GetCurrentTimeline(self):
        return self._timeline


class _ProjectManagerDeMentira:
    def __init__(self, proyecto):
        self.proyecto = proyecto

    def GetCurrentProject(self):
        return self.proyecto


class _ResolveDeMentira:
    """El doble completo: cambiar `.pm.proyecto` simula un cambio de proyecto
    en mitad de la sesion, sin que nadie llame a `conectar()` otra vez."""

    def __init__(self, proyecto):
        self.pm = _ProjectManagerDeMentira(proyecto)

    def GetProjectManager(self):
        return self.pm


class _ResolveQueNoResponde:
    """`GetProjectManager()` revienta -- Resolve cerrado o colgado, tal cual
    se vio el dia 9: la capa de scripting no siempre devuelve `None` con
    calma cuando algo va mal."""

    def GetProjectManager(self):
        raise RuntimeError("no hay conexion con la app")


class _ProjectManagerQueNoResponde:
    def GetCurrentProject(self):
        raise RuntimeError("la app no contesta")


def test_proyecto_traduce_getprojectmanager_roto_en_resolvenoconectado():
    bridge = LiveResolve(_ResolveQueNoResponde())
    with pytest.raises(ResolveNoConectado, match="no responde"):
        bridge._proyecto()


def test_proyecto_traduce_getcurrentproject_roto_en_resolvenoconectado():
    resolve = _ResolveDeMentira(None)
    resolve.pm = _ProjectManagerQueNoResponde()
    bridge = LiveResolve(resolve)
    with pytest.raises(ResolveNoConectado, match="no responde"):
        bridge._proyecto()


def test_proyecto_sin_proyecto_abierto_sigue_dando_el_mensaje_claro():
    """Caso ya cubierto antes de este cambio: sigue funcionando igual, sin
    excepcion cruda de por medio -- Resolve contesta `None` con calma."""
    bridge = LiveResolve(_ResolveDeMentira(None))
    with pytest.raises(ResolveNoConectado, match="no hay ningun proyecto abierto"):
        bridge._proyecto()


def test_timeline_traduce_excepcion_cruda_en_resolvenoconectado():
    class _ProyectoQueNoResponde:
        def GetCurrentTimeline(self):
            raise RuntimeError("boom")

    resolve = _ResolveDeMentira(_ProyectoQueNoResponde())
    bridge = LiveResolve(resolve)
    with pytest.raises(ResolveNoConectado, match="no responde"):
        bridge._timeline()


def test_timeline_sin_timeline_abierto_sigue_siendo_timelinenoabierto():
    proyecto = _ProyectoDeMentira("Proyecto", None)
    bridge = LiveResolve(_ResolveDeMentira(proyecto))
    with pytest.raises(TimelineNoAbierto):
        bridge._timeline()


def test_item_invalida_la_cache_si_resolve_cambia_de_proyecto():
    """El caso real que motiva `_firma_actual`: Mario cambia de proyecto sin
    cerrar la app. El respaldo pista+posicion de `_id()` da el mismo
    `clip_id` ("v1-001") en los dos, asi que sin invalidar la cache `_item`
    devolveria en silencio el `TimelineItem` del proyecto VIEJO."""
    timeline_a = _TimelineDeMentira("Timeline A", [_ItemDeMentira("clipA")])
    proyecto_a = _ProyectoDeMentira("Proyecto A", timeline_a)
    resolve = _ResolveDeMentira(proyecto_a)
    bridge = LiveResolve(resolve)

    clips = bridge.list_clips()
    assert [c.clip_id for c in clips] == ["v1-001"]
    item_viejo = bridge._item("v1-001")
    assert item_viejo.GetName() == "clipA"

    # Cambio de proyecto SIN pasar por list_clips() ni conectar() de nuevo --
    # exactamente lo que pasaria si Mario cambia de proyecto en la GUI de
    # Resolve mientras la app sigue conectada.
    timeline_b = _TimelineDeMentira("Timeline B", [_ItemDeMentira("clipB")])
    proyecto_b = _ProyectoDeMentira("Proyecto B", timeline_b)
    resolve.pm.proyecto = proyecto_b

    # Mismo clip_id ("v1-001") por el respaldo pista+posicion, pero es OTRO
    # objeto: _item tiene que refrescar la cache y devolver el de clipB, no
    # el clipA que tenia guardado.
    item_nuevo = bridge._item("v1-001")
    assert item_nuevo.GetName() == "clipB"
    assert item_nuevo is not item_viejo


def test_item_invalida_la_cache_si_el_timeline_cambia_de_nombre():
    """Mismo riesgo que el test anterior, pero cambiando de timeline dentro
    del mismo proyecto (p.ej. Mario abre otro timeline del mismo evento)."""
    timeline_1 = _TimelineDeMentira("Timeline 1", [_ItemDeMentira("t1")])
    proyecto = _ProyectoDeMentira("Proyecto", timeline_1)
    resolve = _ResolveDeMentira(proyecto)
    bridge = LiveResolve(resolve)

    bridge.list_clips()
    assert bridge._item("v1-001").GetName() == "t1"

    proyecto._timeline = _TimelineDeMentira("Timeline 2", [_ItemDeMentira("t2")])

    assert bridge._item("v1-001").GetName() == "t2"


def test_item_reutiliza_la_cache_si_nada_ha_cambiado():
    """Que la invalidacion no sea *demasiado* agresiva: si el proyecto y el
    timeline siguen siendo los mismos, `_item` no tiene que volver a listar
    -- se comprueba viendo que el objeto cacheado es el MISMO, no una copia
    recien construida por un `list_clips()` de mas."""
    timeline = _TimelineDeMentira("Timeline", [_ItemDeMentira("clip")])
    proyecto = _ProyectoDeMentira("Proyecto", timeline)
    bridge = LiveResolve(_ResolveDeMentira(proyecto))

    bridge.list_clips()
    primero = bridge._item("v1-001")
    segundo = bridge._item("v1-001")
    assert primero is segundo


def test_item_de_un_clip_que_no_existe_sigue_dando_clipnoencontrado():
    timeline = _TimelineDeMentira("Timeline", [_ItemDeMentira("clip")])
    proyecto = _ProyectoDeMentira("Proyecto", timeline)
    bridge = LiveResolve(_ResolveDeMentira(proyecto))
    with pytest.raises(ClipNoEncontrado):
        bridge._item("no-existe")


def test_item_no_revienta_si_no_puede_preguntar_la_firma_y_usa_la_cache():
    """La comprobacion de proyecto/timeline es una proteccion de MAS sobre una
    cache que ya existe, no una condicion para poder usarla. Si `self._resolve`
    no sabe contestar (aqui, un `object()` a pelo, igual que en
    `tests/auditoria/test_dia2_regla_de_oro.py::_live_con_dobles`, que rellena
    `_cache` a mano sin pasar nunca por `list_clips()`), `_item` tiene que
    seguir sirviendo lo que ya tenia en cache en vez de lanzar
    `ResolveNoConectado` en CADA lectura -- eso es justo lo que rompio esa
    suite la primera vez que se escribio esta proteccion."""
    bridge = LiveResolve(object())
    centinela = _ItemDeMentira("centinela")
    bridge._cache = {"v1-001": centinela}
    assert bridge._item("v1-001") is centinela
