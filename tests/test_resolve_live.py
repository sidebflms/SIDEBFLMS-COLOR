"""`core.resolve.live`: sin conexión a Resolve real no hay mucho que probar
(`LiveResolve` "no se ha ejecutado nunca" — ver su propio docstring), pero
`_llamable` es lógica pura y merece su test, sobre todo porque nace de un
bug real encontrado el día 9 contra Resolve real (Studio 21.1.0.17):
`list_nodes()` reventaba con `TypeError: 'NoneType' object is not callable`
porque `hasattr(grafo, "GetNodeEnabled")` decía `True` aunque el valor de
ese atributo fuera `None`, no un método.
"""

from __future__ import annotations

from core.resolve.live import _llamable


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
