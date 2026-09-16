"""Verificador de doble conversion (`core.colormgmt.verificacion`).

Sin conexion a Resolve: se monta `ProjectInfo` y `NodeInfo` a mano, que es
justo lo que expone `ResolveBridge.project_info()` / `list_nodes()`.
"""

from __future__ import annotations

from core.colormgmt import verificar_proyecto
from core.contracts import NODE_NORMALIZACION, ClipRef, DeteccionEspacio, NodeInfo, ProjectInfo


def _proyecto(**kw) -> ProjectInfo:
    base = dict(
        name="PRUEBA",
        timeline_name="TL",
        color_science="DaVinci YRGB Color Managed",
        timeline_color_space="DaVinci Wide Gamut Intermediate",
        lut_dir="/tmp/luts",
        resolve_version="21.0",
        is_studio=True,
    )
    base.update(kw)
    return ProjectInfo(**base)


def _clip(clip_id: str = "c1", name: str = "clip") -> ClipRef:
    return ClipRef(clip_id=clip_id, name=name, track=1, index=1, start_frame=0, end_frame=100)


def _nodo(index: int, lut_path: str | None) -> NodeInfo:
    return NodeInfo(index=index, label="", enabled=True, lut_path=lut_path)


def test_doble_conversion_detectada():
    clip = _clip()
    nodos = {clip.clip_id: [_nodo(NODE_NORMALIZACION, "Sony/S-Log3 to Rec709.cube"), _nodo(2, None), _nodo(3, None)]}
    avisos = verificar_proyecto(_proyecto(), [clip], nodos)
    graves = [a for a in avisos if a.tipo == "doble_conversion"]
    assert len(graves) == 1
    assert graves[0].severidad == "grave"
    assert graves[0].clip_id == clip.clip_id
    assert "dos veces" in graves[0].mensaje


def test_sin_lut_de_conversion_no_hay_aviso():
    clip = _clip()
    nodos = {clip.clip_id: [_nodo(NODE_NORMALIZACION, None), _nodo(2, None), _nodo(3, "SIDEB/look.cube")]}
    avisos = verificar_proyecto(_proyecto(), [clip], nodos)
    assert not [a for a in avisos if a.tipo == "doble_conversion"]


def test_lut_de_look_en_nodo_1_no_se_confunde_con_conversion():
    """Un look puesto (por error de montaje) en el nodo 1 no es una curva de camara."""
    clip = _clip()
    nodos = {clip.clip_id: [_nodo(NODE_NORMALIZACION, "SIDEB/mi_look_bonito.cube")]}
    avisos = verificar_proyecto(_proyecto(), [clip], nodos)
    assert not [a for a in avisos if a.tipo == "doble_conversion"]


def test_sin_gestion_automatica_avisa_que_hay_que_convertir_a_mano():
    clip = _clip()
    avisos = verificar_proyecto(_proyecto(color_science="DaVinci YRGB"), [clip], {clip.clip_id: []})
    assert any(a.tipo == "espacio_trabajo_inesperado" and a.severidad == "aviso" for a in avisos)


def test_espacio_de_trabajo_inesperado_con_gestion_activada():
    clip = _clip()
    avisos = verificar_proyecto(
        _proyecto(timeline_color_space="Rec.709"), [clip], {clip.clip_id: []}
    )
    assert any(a.tipo == "espacio_trabajo_inesperado" for a in avisos)


def test_espacio_de_trabajo_esperado_no_avisa():
    clip = _clip()
    avisos = verificar_proyecto(_proyecto(), [clip], {clip.clip_id: []})
    assert not [a for a in avisos if a.tipo == "espacio_trabajo_inesperado"]


def test_curva_no_cuadra_se_traslada_como_aviso():
    clip = _clip()
    deteccion = DeteccionEspacio(
        clip_id=clip.clip_id,
        space="slog3_sgamut3cine",
        segura=False,
        razon="declara la curva de Sony pero el fabricante puesto es 'Panasonic', que no cuadra con esa curva.",
        regla="Sony FX3 (S-Log3 / S-Gamut3.Cine)",
    )
    avisos = verificar_proyecto(_proyecto(), [clip], {clip.clip_id: []}, detecciones=[deteccion])
    assert any(a.tipo == "curva_no_cuadra" and a.clip_id == clip.clip_id for a in avisos)


def test_deteccion_insegura_sin_contradiccion_no_genera_aviso_de_curva():
    """'Sin metadatos' o 'fabricante sin curva' no son una CONTRADICCION: van a
    la lista de grupos ambiguos, no a los avisos del verificador."""
    clip = _clip()
    deteccion = DeteccionEspacio(
        clip_id=clip.clip_id, space=None, segura=False, razon="no hay metadatos de camara reconocibles.", regla=None
    )
    avisos = verificar_proyecto(_proyecto(), [clip], {clip.clip_id: []}, detecciones=[deteccion])
    assert not [a for a in avisos if a.tipo == "curva_no_cuadra"]
