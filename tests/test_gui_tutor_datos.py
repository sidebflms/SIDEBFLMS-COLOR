"""`gui.tutor_datos`: el puente entre `EstadoDemo` y `core.tutor`, sin lógica
de reglas propia — sólo que reúna los datos correctos."""

from __future__ import annotations

from gui import datos_demo as dd
from gui.tutor_datos import construir_contexto, frases_de_clip, lecciones_de_clip


def test_construir_contexto_con_estado_demo_completo():
    estado = dd.estado_demo()
    clip = estado.clips[0]
    ctx = construir_contexto(estado, clip)
    assert ctx is not None
    assert ctx.analisis.clip_id == clip.clip_id
    assert ctx.match is clip.match
    assert ctx.qc_look is estado.informe_lut


def test_sin_imagen_no_hay_contexto():
    estado = dd.estado_demo()
    clip = estado.clips[0]
    clip.original = None
    assert construir_contexto(estado, clip) is None


def test_frases_de_clip_sin_imagen_es_vacio():
    estado = dd.estado_demo()
    clip = estado.clips[0]
    clip.original = None
    assert frases_de_clip(estado, clip) == ()


def test_lecciones_de_clip_siempre_da_las_dos_minimas_aunque_no_haya_imagen():
    estado = dd.estado_demo()
    clip = estado.clips[0]
    clip.original = None
    ids = {leccion.id for leccion in lecciones_de_clip(estado, clip)}
    assert "tres_tipos_de_lut" in ids
    assert "exposicion_no_en_el_look" in ids


def test_el_clip_de_referencia_no_se_compara_consigo_mismo():
    """Si el clip que se está mirando ES el de referencia, no hay
    `analisis_referencia` que comparar contra sí mismo."""
    estado = dd.estado_demo()
    referencia = estado.por_id(estado.referencia_id)
    ctx = construir_contexto(estado, referencia)
    assert ctx is not None
    assert ctx.analisis_referencia is None


def test_estado_vacio_no_lanza():
    estado = dd.estado_vacio()
    assert estado.clips == []
    # No hay clips que mirar; nada que probar sobre construir_contexto aquí,
    # pero frases/lecciones sobre la ausencia de clip no deben ni llamarse
    # -- lo comprueba la pantalla, no este módulo.


def test_frases_reales_salen_del_catalogo_de_core_tutor():
    estado = dd.estado_demo()
    clip = estado.clips[0]
    frases = frases_de_clip(estado, clip)
    from core.tutor import CATALOGO

    ids_catalogo = {r.id for r in CATALOGO}
    for f in frases:
        assert f.regla_id in ids_catalogo
