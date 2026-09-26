"""`core.resolve.live`: sin conexión a Resolve real no se puede probar todo
(`LiveResolve.conectar()` de verdad, y las cinco escrituras de color, siguen
sin ejecutarse en un test automatizado), pero `_llamable` y `_id` son lógica
pura y merecen su test:

- `_llamable` nace de un bug real encontrado el día 9 contra Resolve real
  (Studio 21.1.0.17): `list_nodes()` reventaba con
  `TypeError: 'NoneType' object is not callable` porque
  `hasattr(grafo, "GetNodeEnabled")` decía `True` aunque el valor de ese
  atributo fuera `None`, no un método.
- `_id` usa `GetUniqueId()` cuando está disponible (confirmado ese mismo día
  que sí lo está, y que da un UUID estable), con la construcción antigua por
  pista+posición como respaldo si algún Resolve más viejo no lo trae.
"""

from __future__ import annotations

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
