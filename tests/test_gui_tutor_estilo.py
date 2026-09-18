"""`gui.tutor_estilo`: la prueba en código de la tarea 2.5 del día 8.

"Sin red no se pierde ninguna función de color ni ninguna explicación: se
pierde el estilo." Hoy no hay ningún reescritor conectado, así que "se
pierde el estilo" se traduce, literalmente, en "las frases salen idénticas"
— con red o sin ella. Lo que este archivo demuestra es que la ausencia de
red NUNCA rompe nada río abajo, ni lanza, ni cambia el número de frases.
"""

from __future__ import annotations

import socket

from core.analysis import analizar_imagen
from core.tutor import ContextoTutor, ensenar, explicar
from gui.tutor_estilo import hay_red, reescribir_frases, reescribir_lecciones


def _contexto(estudio_trabajo) -> ContextoTutor:
    return ContextoTutor(analisis=analizar_imagen(estudio_trabajo, clip_id="x"))


def test_modo_avion_forzado_no_toca_las_frases(estudio_trabajo):
    """`disponible=False` simula modo avión sin depender de la red real de
    quien ejecute el test — es la comprobación de verdad de la tarea."""
    frases = explicar(_contexto(estudio_trabajo))
    resultado = reescribir_frases(frases, disponible=False)
    assert resultado == frases
    assert len(resultado) == len(frases)


def test_con_red_forzada_tampoco_se_pierde_ninguna_frase(estudio_trabajo):
    """Hoy no hay reescritor conectado: con red disponible, el camino
    también tiene que devolver las frases completas, nunca menos."""
    frases = explicar(_contexto(estudio_trabajo))
    resultado = reescribir_frases(frases, disponible=True)
    assert len(resultado) == len(frases)
    assert {f.regla_id for f in resultado} == {f.regla_id for f in frases}


def test_lecciones_tambien_sobreviven_en_modo_avion(estudio_trabajo):
    lecciones = ensenar(_contexto(estudio_trabajo))
    resultado = reescribir_lecciones(lecciones, disponible=False)
    assert resultado == lecciones


def test_sin_frases_no_lanza_en_ningun_modo():
    """El caso vacío (un clip sin nada que decir) no puede reventar la
    reescritura, con o sin red."""
    assert reescribir_frases((), disponible=False) == ()
    assert reescribir_frases((), disponible=True) == ()


def test_hay_red_nunca_lanza_aunque_la_conexion_falle(monkeypatch):
    """Cualquier fallo de socket —DNS roto, modo avión, firewall— se traduce
    en `False`, nunca en una excepción que suba hasta la GUI."""

    def _revienta(*_a, **_k):
        raise OSError("network is unreachable")

    monkeypatch.setattr(socket, "create_connection", _revienta)
    assert hay_red() is False


def test_hay_red_es_true_cuando_la_conexion_se_establece(monkeypatch):
    class _SocketFalso:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _SocketFalso())
    assert hay_red() is True
