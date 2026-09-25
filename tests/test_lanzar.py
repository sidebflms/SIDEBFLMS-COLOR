"""`lanzar.py`: el lanzador que intenta conectar a Resolve real (día 9,
continuación 8), separado de `gui/` a propósito —`gui/` nunca importa
`LiveResolve`, lo garantiza
`test_gui_regla_de_oro.py::test_la_gui_no_importa_el_puente_de_verdad`—.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import lanzar  # noqa: E402


def test_estado_inicial_cae_a_demo_si_resolve_no_conecta(monkeypatch):
    """Sin Resolve real disponible, el arranque no se rompe -- cae a datos
    de demostración, como siempre."""
    from core.resolve.bridge import ResolveNoConectado
    from core.resolve.live import LiveResolve
    from gui.datos_demo import EstadoDemo

    def _conectar_que_falla(cls, incognitas=None):
        raise ResolveNoConectado("Resolve no está abierto (de prueba)")

    monkeypatch.setattr(LiveResolve, "conectar", classmethod(_conectar_que_falla))

    estado = lanzar._estado_inicial()
    assert isinstance(estado, EstadoDemo)
    assert estado.clips  # es el estado de demostración de siempre, con clips


def test_estado_inicial_cae_a_demo_si_no_hay_clips_analizables(monkeypatch):
    from core.resolve.live import LiveResolve
    from gui import estado_real as estado_real_mod
    from gui.datos_demo import EstadoDemo
    from gui.estado_real import SinClipsReales

    monkeypatch.setattr(LiveResolve, "conectar", classmethod(lambda cls, incognitas=None: object()))

    def _sin_clips(puente, **kwargs):
        raise SinClipsReales("nada que analizar (de prueba)")

    monkeypatch.setattr(estado_real_mod, "construir_estado_real", _sin_clips)

    estado = lanzar._estado_inicial()
    assert isinstance(estado, EstadoDemo)
    assert estado.clips


def test_estado_inicial_usa_el_real_si_la_conexion_funciona(monkeypatch):
    from core.resolve.live import LiveResolve
    from gui import estado_real as estado_real_mod

    centinela = object()
    monkeypatch.setattr(LiveResolve, "conectar", classmethod(lambda cls, incognitas=None: centinela))

    construido_con = {}

    def _construir_falso(puente, **kwargs):
        from core.resolve import FakeResolve
        from gui.datos_demo import EstadoDemo

        construido_con["puente"] = puente
        return EstadoDemo(clips=[], puente=FakeResolve(n_clips=0), notas=("de verdad",))

    monkeypatch.setattr(estado_real_mod, "construir_estado_real", _construir_falso)

    estado = lanzar._estado_inicial()
    assert construido_con["puente"] is centinela
    assert estado.notas == ("de verdad",)
