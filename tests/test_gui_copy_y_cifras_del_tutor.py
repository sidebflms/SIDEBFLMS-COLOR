"""Copy de la auditoría de diseño del 2026-10-06 (bloque 7).

* Tildes en la pregunta de «no reconozco la cámara» (`core/colormgmt/deteccion.py`):
  decía «camara» y «¿De que camara son…».
* Los números de «El tutor» salían con 17 cifras (`0.13566423773765565`, el
  `repr` de un `float`). Ahora se **muestran** a 4 decimales y el valor completo
  va en el tooltip. Sólo se redondea al mostrar: lo que mide `core.tutor` no se toca.
"""

from __future__ import annotations

import re

import pytest

from core.contracts import ClipRef
from gui.datos_demo import estado_demo
from gui.tutor_datos import frases_de_clip, redondear_para_mostrar
from tests.test_gui_apoyo import app_qt, asentar, ventana

# ---------------------------------------------------------------------------
# Tildes
# ---------------------------------------------------------------------------


def test_la_pregunta_de_camara_desconocida_lleva_tildes():
    from core.colormgmt import agrupar_ambiguos

    refs = [
        ClipRef(clip_id=f"c{i}", name=f"A00{i}_clip", track=1, index=i, start_frame=0, end_frame=9)
        for i in range(1, 4)
    ]
    grupos = agrupar_ambiguos(refs)
    assert grupos, "sin metadata de cámara tiene que haber al menos un grupo que preguntar"
    pregunta = grupos[0].pregunta
    assert "cámara" in pregunta and "¿De qué cámara son" in pregunta
    assert "camara" not in pregunta.replace("cámara", "")
    assert "que camara" not in pregunta


# ---------------------------------------------------------------------------
# Cifras del tutor
# ---------------------------------------------------------------------------


def test_redondear_deja_4_decimales_en_un_float_largo():
    assert redondear_para_mostrar("x = [0.13566423773765565, 0.142531401515007]") == "x = [0.1357, 0.1425]"


def test_redondear_respeta_negativos_y_los_decimales_justos():
    assert redondear_para_mostrar("-0.123456789") == "-0.1235"
    assert redondear_para_mostrar("0.02 y 10.3% y 0.1234") == "0.02 y 10.3% y 0.1234"
    assert redondear_para_mostrar("0.12345") == "0.1235"


def test_redondear_no_toca_lo_que_no_es_un_decimal_largo():
    assert redondear_para_mostrar("SUELO_NEGRO_VISIBLE_TUTOR = 0.02") == "SUELO_NEGRO_VISIBLE_TUTOR = 0.02"
    assert redondear_para_mostrar("versión 21.1.0.17") == "versión 21.1.0.17"
    assert redondear_para_mostrar("sin números") == "sin números"


def test_el_panel_del_tutor_muestra_4_decimales_y_el_tooltip_el_valor_completo():
    app_qt()
    estado = estado_demo()
    v = ventana(estado)
    largos = re.compile(r"\d+\.\d{5,}")
    visto = 0
    try:
        v.ir_a(1)
        for clip in estado.clips:
            if not any(largos.search(f.valor_medido) for f in frases_de_clip(estado, clip)):
                continue
            v.p_comparar.seleccionar(clip.clip_id)
            asentar()
            texto = v.p_comparar.texto_tutor.text()
            assert not largos.search(texto), f"quedan cifras largas: {texto[:200]}"
            tooltip = v.p_comparar.texto_tutor.toolTip()
            assert largos.search(tooltip), "el tooltip tiene que traer el valor completo"
            visto += 1
    finally:
        v.close()
    assert visto, "el test se ha quedado ciego: ningún clip de la demo trae cifras largas"


def test_lo_que_mide_el_tutor_no_se_redondea_en_el_nucleo():
    estado = estado_demo()
    largos = re.compile(r"\d+\.\d{5,}")
    assert any(
        largos.search(f.valor_medido) for c in estado.clips for f in frases_de_clip(estado, c)
    ), "el valor completo tiene que seguir en `Frase`: sólo se redondea al mostrar"


@pytest.mark.parametrize("texto", ["", "—"])
def test_redondear_aguanta_textos_vacios(texto):
    assert redondear_para_mostrar(texto) == texto
