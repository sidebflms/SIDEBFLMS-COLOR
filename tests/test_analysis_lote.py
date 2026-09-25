"""`core.analysis.lote.analizar_lote`: el orquestador de "analiza esta
timeline entera" que `BITACORA.md` señalaba como hueco real ("no existe
ningún orquestador... con estado reanudable").

No usa vídeo real ni ffmpeg: `analizar_clip` se sustituye por un doble de
prueba barato (mismo patrón que el resto de la suite usa para lo caro o lo
externo) — lo que se prueba aquí es la ORQUESTACIÓN (aislar fallos,
reanudar, cancelar), no `analizar_clip` en sí, que ya tiene sus propios
tests en `test_analysis_stats.py`.
"""

from __future__ import annotations

import pytest

import core.analysis.lote as lote_mod
from core.analysis.errores import ErrorFFmpeg
from core.analysis.lote import analizar_lote
from core.batch import ProgresoLote


class _AnalisisFalso:
    """Doble barato de `ClipAnalysis`: sólo hace falta que sea distinguible
    por clip, no que tenga los campos reales."""

    def __init__(self, clip_id: str) -> None:
        self.clip_id = clip_id


def _analizar_clip_falso(ruta, *, clip_id=None, **kwargs):  # noqa: ANN001
    return _AnalisisFalso(clip_id)


def test_todos_bien_devuelve_un_clipanalysis_por_clip(monkeypatch):
    monkeypatch.setattr(lote_mod, "analizar_clip", _analizar_clip_falso)
    clips = {"c1": "/x/c1.mov", "c2": "/x/c2.mov"}

    resultado = analizar_lote(clips)

    assert set(resultado.analisis) == {"c1", "c2"}
    assert resultado.analisis["c1"].clip_id == "c1"
    assert resultado.fallos == {}
    assert set(resultado.hechos) == {"c1", "c2"}
    assert resultado.pendientes == ()
    assert resultado.cancelado is False


def test_un_fallo_no_tumba_el_lote_y_se_aisla(monkeypatch):
    def analizar(ruta, *, clip_id=None, **kwargs):  # noqa: ANN001
        if clip_id == "c2":
            raise ErrorFFmpeg("ffmpeg no ha podido leer el fichero")
        return _AnalisisFalso(clip_id)

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar)
    clips = {"c1": "/x/c1.mov", "c2": "/x/c2.mov", "c3": "/x/c3.mov"}

    resultado = analizar_lote(clips)

    assert set(resultado.analisis) == {"c1", "c3"}
    assert resultado.fallos == {"c2": "ffmpeg no ha podido leer el fichero"}
    assert set(resultado.hechos) == {"c1", "c3"}


def test_una_excepcion_que_no_es_erroranalisis_se_propaga(monkeypatch):
    """Un bug de verdad (no un fallo esperable de análisis) tiene que verse,
    no taparse -- mismo criterio que aplicar()/aplicar_cancelable."""

    def analizar(ruta, *, clip_id=None, **kwargs):  # noqa: ANN001
        raise ValueError("esto es un bug, no un ErrorAnalisis")

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar)

    with pytest.raises(ValueError, match="esto es un bug"):
        analizar_lote({"c1": "/x/c1.mov"})


# ---------------------------------------------------------------------------
# Reanudable
# ---------------------------------------------------------------------------


def test_reanudar_no_vuelve_a_llamar_a_analizar_clip_para_lo_ya_hecho(monkeypatch, tmp_path):
    ruta_manifiesto = tmp_path / "manifiesto.json"
    llamadas = []

    def analizar(ruta, *, clip_id=None, **kwargs):  # noqa: ANN001
        llamadas.append(clip_id)
        return _AnalisisFalso(clip_id)

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar)
    clips = {"c1": "/x/c1.mov", "c2": "/x/c2.mov", "c3": "/x/c3.mov"}

    analizar_lote(clips, manifiesto=ruta_manifiesto)
    assert llamadas == ["c1", "c2", "c3"]

    llamadas.clear()
    resultado = analizar_lote(clips, manifiesto=ruta_manifiesto)
    assert llamadas == []  # nada que reanalizar: los tres ya estaban "hecho"
    assert set(resultado.hechos) == {"c1", "c2", "c3"}
    # Pero esta llamada NO los analizó -- no están en `analisis` esta vez.
    assert resultado.analisis == {}


def test_reanudar_tras_ffmpeg_roto_a_mitad_solo_reintenta_lo_pendiente(monkeypatch, tmp_path):
    """El escenario concreto que describe BITACORA.md: ffmpeg falla a mitad
    de un lote grande. Reanudar no repite los que ya salieron bien."""
    ruta_manifiesto = tmp_path / "manifiesto.json"
    llamadas_1 = []

    def analizar_1(ruta, *, clip_id=None, **kwargs):  # noqa: ANN001
        llamadas_1.append(clip_id)
        if clip_id == "c3":
            raise ErrorFFmpeg("ffmpeg ha reventado a mitad del lote")
        return _AnalisisFalso(clip_id)

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar_1)
    clips = {"c1": "/x/1", "c2": "/x/2", "c3": "/x/3", "c4": "/x/4"}

    r1 = analizar_lote(clips, manifiesto=ruta_manifiesto, debe_cancelar=lambda: "c3" in llamadas_1 and "c4" not in llamadas_1)
    # c3 fallo, y justo despues se cancela (simulando que el operador para el
    # proceso al ver el fallo) -- c4 se queda pendiente.
    assert "c4" not in r1.analisis
    assert r1.cancelado is True

    llamadas_2 = []

    def analizar_2(ruta, *, clip_id=None, **kwargs):  # noqa: ANN001
        llamadas_2.append(clip_id)
        return _AnalisisFalso(clip_id)

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar_2)
    r2 = analizar_lote(clips, manifiesto=ruta_manifiesto)

    # c1 y c2 NO se reanalizan (ya estaban "hecho"); c3 se reintenta (fallo);
    # c4 se intenta por primera vez (pendiente de antes).
    assert set(llamadas_2) == {"c3", "c4"}
    assert set(r2.hechos) == {"c1", "c2", "c3", "c4"}
    assert r2.fallos == {}


# ---------------------------------------------------------------------------
# Cancelar y progreso
# ---------------------------------------------------------------------------


def test_cancelar_deja_pendientes_los_que_no_se_intentaron(monkeypatch):
    monkeypatch.setattr(lote_mod, "analizar_clip", _analizar_clip_falso)
    clips = {"c1": "/x/1", "c2": "/x/2", "c3": "/x/3"}

    vistos = []

    def callback(p: ProgresoLote) -> None:
        vistos.append(p.resultado.item_id)

    resultado = analizar_lote(
        clips, callback_progreso=callback, debe_cancelar=lambda: len(vistos) >= 1
    )

    assert len(resultado.analisis) == 1
    assert len(resultado.pendientes) == 2
    assert resultado.cancelado is True


def test_callback_progreso_por_clip(monkeypatch):
    monkeypatch.setattr(lote_mod, "analizar_clip", _analizar_clip_falso)
    clips = {"c1": "/x/1", "c2": "/x/2"}
    progresos: list[ProgresoLote] = []
    analizar_lote(clips, callback_progreso=progresos.append)
    assert [p.resultado.item_id for p in progresos] == ["c1", "c2"]
    assert all(p.total == 2 for p in progresos)
