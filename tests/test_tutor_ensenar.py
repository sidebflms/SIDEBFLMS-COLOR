"""`core.tutor.ensenar`: las dos lecciones obligatorias del encargo (día 8,
tarea 2.4) siempre están, y la lección del CDL sólo aparece cuando hay un
`MatchResult` de verdad que explicar."""

from __future__ import annotations

from core.analysis import analizar_imagen
from core.contracts import CDL, Confidence, MatchResult
from core.tutor.catalogo import ContextoTutor
from core.tutor.ensenar import ensenar


def test_las_dos_lecciones_minimas_del_encargo_siempre_estan():
    ids = {leccion.id for leccion in ensenar()}
    assert "tres_tipos_de_lut" in ids
    assert "exposicion_no_en_el_look" in ids


def test_sin_contexto_no_hay_leccion_de_cdl():
    ids = {leccion.id for leccion in ensenar(None)}
    assert "cdl_de_este_clip" not in ids


def test_con_un_cdl_identidad_la_leccion_lo_dice(estudio_trabajo):
    analisis = analizar_imagen(estudio_trabajo, clip_id="x")
    match = MatchResult(
        cdl=CDL(), lut=None, confidence=Confidence(score=1.0, level="alta"),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=False,
    )
    ctx = ContextoTutor(analisis=analisis, match=match)
    cdl_leccion = next(leccion for leccion in ensenar(ctx) if leccion.id == "cdl_de_este_clip")
    assert "identidad" in cdl_leccion.texto


def test_con_un_cdl_con_offset_la_leccion_menciona_exposicion(estudio_trabajo):
    analisis = analizar_imagen(estudio_trabajo, clip_id="x")
    match = MatchResult(
        cdl=CDL(offset=(0.05, 0.05, 0.05)), lut=None,
        confidence=Confidence(score=1.0, level="alta"),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=False,
    )
    ctx = ContextoTutor(analisis=analisis, match=match)
    cdl_leccion = next(leccion for leccion in ensenar(ctx) if leccion.id == "cdl_de_este_clip")
    assert "exposición" in cdl_leccion.texto


def test_ninguna_leccion_menciona_confianza(estudio_trabajo):
    analisis = analizar_imagen(estudio_trabajo, clip_id="x")
    match = MatchResult(
        cdl=CDL(offset=(0.05, 0.0, -0.02)), lut=None,
        confidence=Confidence(score=0.3, level="baja"),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=False,
    )
    ctx = ContextoTutor(analisis=analisis, match=match)
    for leccion in ensenar(ctx):
        assert "confianza" not in leccion.texto.lower()
