"""`gui.estado_real.construir_estado_real`: un `EstadoDemo` (mismo tipo que
usa toda la pantalla) construido a partir de un timeline REAL — clips reales
vía `puente.list_clips()`, análisis real vía `core.analysis.lote`,
emparejamiento real vía `core.matching.emparejar_analisis`.

Nada de ffmpeg ni de vídeo real: `analizar_clip` se sustituye por
`analizar_imagen` sobre una imagen sintética pequeña (mismo patrón que
`test_analysis_lote.py`, pero con un `ClipAnalysis` de VERDAD -- hace falta
para que `emparejar_analisis` tenga con qué trabajar, no vale un doble vacío).
`extraer_fotogramas` (el fotograma para el antes/después) también se
sustituye, por la misma razón: no hay fichero real que leer en un test.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

import gui.estado_real as estado_real_mod  # noqa: E402
from core.analysis import analizar_imagen  # noqa: E402
from core.contracts import ClipRef  # noqa: E402
from core.resolve import FakeResolve  # noqa: E402
from gui.estado_real import SinClipsReales, construir_estado_real  # noqa: E402


def _imagen(semilla: int) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return rng.random((8, 8, 3)).astype(np.float32)


def _puente_con_rutas(n: int, *, con_ruta: int | None = None) -> FakeResolve:
    """`FakeResolve` con `file_path` puesto a mano -- por defecto no lo trae
    (`core/resolve/fake.py`: "no hay material real y no lo va a haber")."""
    con_ruta = n if con_ruta is None else con_ruta
    refs = [
        ClipRef(
            clip_id=f"clip{i:03d}",
            name=f"Clip {i}",
            track=1,
            index=i,
            start_frame=0,
            end_frame=99,
            file_path=f"/material/clip{i:03d}.mov" if i <= con_ruta else None,
        )
        for i in range(1, n + 1)
    ]
    return FakeResolve(clips=refs, nodos_por_clip=3)


@pytest.fixture(autouse=True)
def _dobles(monkeypatch):
    """Sustituye ffmpeg por análisis/lectura en memoria, determinista por ruta."""

    def analizar_clip_falso(ruta, *, clip_id=None, **kwargs):
        semilla = abs(hash(ruta)) % (2**32)
        return analizar_imagen(_imagen(semilla), clip_id=clip_id)

    def extraer_fotogramas_falso(ruta, *, n_fotogramas=1, **kwargs):
        semilla = abs(hash(ruta)) % (2**32)
        return _imagen(semilla)[None, ...]  # (1, alto, ancho, 3)

    # analizar_lote importa analizar_clip dentro de core.analysis.lote, no en
    # estado_real -- hay que parchear ahi, que es donde de verdad se llama.
    import core.analysis.lote as lote_mod

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar_clip_falso)
    monkeypatch.setattr(estado_real_mod, "extraer_fotogramas", extraer_fotogramas_falso)


def test_construye_un_clipdemo_por_clip_con_fichero():
    puente = _puente_con_rutas(3)
    estado = construir_estado_real(puente)

    assert len(estado.clips) == 3
    assert estado.puente is puente
    assert estado.referencia_id in {c.clip_id for c in estado.clips}
    assert estado.referencia_img is not None
    for c in estado.clips:
        assert c.original is not None
        assert c.match is not None


def test_los_clips_sin_fichero_no_entran():
    puente = _puente_con_rutas(5, con_ruta=2)
    estado = construir_estado_real(puente)
    assert len(estado.clips) == 2


def test_sin_ningun_clip_con_fichero_lanza_sinclipsreales():
    puente = _puente_con_rutas(3, con_ruta=0)
    with pytest.raises(SinClipsReales):
        construir_estado_real(puente)


def test_referencia_explicita_se_respeta_si_se_pudo_analizar():
    puente = _puente_con_rutas(3)
    estado = construir_estado_real(puente, referencia_clip_id="clip002")
    assert estado.referencia_id == "clip002"


def test_referencia_explicita_que_no_existe_cae_a_la_primera():
    puente = _puente_con_rutas(3)
    estado = construir_estado_real(puente, referencia_clip_id="no-existe")
    assert estado.referencia_id == "clip001"


def test_un_fallo_de_analisis_no_tumba_la_construccion_y_se_cuenta(monkeypatch):
    import core.analysis.lote as lote_mod

    def analizar_con_un_fallo(ruta, *, clip_id=None, **kwargs):
        if clip_id == "clip002":
            from core.analysis.errores import ErrorFFmpeg

            raise ErrorFFmpeg("fichero truncado")
        semilla = abs(hash(ruta)) % (2**32)
        return analizar_imagen(_imagen(semilla), clip_id=clip_id)

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar_con_un_fallo)

    puente = _puente_con_rutas(3)
    estado = construir_estado_real(puente)

    ids = {c.clip_id for c in estado.clips}
    assert ids == {"clip001", "clip003"}
    assert any("clip002" in n and "fichero truncado" in n for n in estado.notas)


def test_notas_dicen_cuantos_se_analizaron():
    puente = _puente_con_rutas(4)
    estado = construir_estado_real(puente)
    assert any("4 de 4" in n for n in estado.notas)
