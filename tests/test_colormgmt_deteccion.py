"""Detector de camara y tabla de decision (`core.colormgmt.deteccion`).

La regla que se prueba una y otra vez aqui es la del encargo: **lo que no se
sabe con seguridad no se adivina**. Cada camino que termina en `segura=False`
tiene su test, no solo los caminos que aciertan.
"""

from __future__ import annotations

from core.colormgmt import agrupar_ambiguos, detectar_espacio_clip, detectar_espacios_timeline
from core.colormgmt.deteccion import REGLAS_DECISION
from core.contracts import ClipRef


def _clip(clip_id: str = "c1", name: str = "A001C001", **kw) -> ClipRef:
    return ClipRef(clip_id=clip_id, name=name, track=1, index=1, start_frame=0, end_frame=100, **kw)


# ---------------------------------------------------------------------------
# Las cuatro camaras del encargo, mas Rec.709
# ---------------------------------------------------------------------------


def test_sony_fx3_por_gamma_y_fabricante():
    d = detectar_espacio_clip(_clip(camera_manufacturer="Sony", camera_type="ILME-FX3", gamma_notes="S-Log3"))
    assert d.segura
    assert d.space == "slog3_sgamut3cine"
    assert "Sony" in d.razon


def test_panasonic_lumix_por_gamma_y_fabricante():
    d = detectar_espacio_clip(_clip(camera_manufacturer="Panasonic", camera_type="DC-S5M2", gamma_notes="V-Log"))
    assert d.segura
    assert d.space == "vlog_vgamut"


def test_canon_por_gamma_y_fabricante():
    d = detectar_espacio_clip(_clip(camera_manufacturer="Canon", gamma_notes="Canon Log 3"))
    assert d.segura
    assert d.space == "clog3_cinemagamut"


def test_dji_por_gamma_y_fabricante():
    d = detectar_espacio_clip(_clip(camera_manufacturer="DJI", gamma_notes="D-Log"))
    assert d.segura
    assert d.space == "dlog_dgamut"


def test_rec709_declarado():
    d = detectar_espacio_clip(_clip(input_color_space="Rec.709"))
    assert d.segura
    assert d.space == "rec709"


def test_camera_notes_con_curva_y_gamut_juntos():
    """Formato tipico de Resolve: 'Camera Notes' trae 'S-Gamut3.Cine/S-Log3' entero."""
    d = detectar_espacio_clip(_clip(camera_manufacturer="Sony", camera_notes="S-Gamut3.Cine/S-Log3"))
    assert d.segura
    assert d.space == "slog3_sgamut3cine"


def test_todas_las_reglas_citan_una_fuente():
    """Punto 2 del encargo: la tabla tiene que decir DE DONDE sale cada mapeo."""
    for regla in REGLAS_DECISION:
        assert regla.fuente, f"{regla.nombre} no cita fuente"


# ---------------------------------------------------------------------------
# Lo que no se sabe con seguridad (punto 3 del encargo)
# ---------------------------------------------------------------------------


def test_sin_metadata_no_se_adivina():
    d = detectar_espacio_clip(_clip())
    assert not d.segura
    assert d.space is None
    assert "no hay metadatos" in d.razon


def test_fabricante_sin_curva_no_se_aplica_solo():
    d = detectar_espacio_clip(_clip(camera_manufacturer="Sony"))
    assert not d.segura
    # lleva una mejor conjetura, pero no se aplica sola
    assert d.space == "slog3_sgamut3cine"
    assert "no declara curva" in d.razon


def test_curva_que_no_cuadra_con_el_fabricante():
    """El clip dice ser Panasonic pero declara la curva de Sony: contradiccion."""
    d = detectar_espacio_clip(_clip(camera_manufacturer="Panasonic", gamma_notes="S-Log3"))
    assert not d.segura
    assert d.space == "slog3_sgamut3cine"  # la curva manda sobre el fabricante como conjetura
    assert "no cuadra" in d.razon


def test_dos_curvas_a_la_vez_no_se_elige_sola():
    d = detectar_espacio_clip(_clip(gamma_notes="S-Log3", camera_notes="V-Log"))
    assert not d.segura
    assert d.space is None
    assert "mas de una curva" in d.razon


# ---------------------------------------------------------------------------
# Timeline completo
# ---------------------------------------------------------------------------


def test_timeline_mixto_cuatro_camaras():
    clips = [
        _clip("c1", "A001", camera_manufacturer="Sony", gamma_notes="S-Log3"),
        _clip("c2", "B001", camera_manufacturer="Panasonic", gamma_notes="V-Log"),
        _clip("c3", "C001", camera_manufacturer="Canon", gamma_notes="C-Log3"),
        _clip("c4", "D001", camera_manufacturer="DJI", gamma_notes="D-Log"),
    ]
    dets = detectar_espacios_timeline(clips)
    assert [d.space for d in dets] == [
        "slog3_sgamut3cine",
        "vlog_vgamut",
        "clog3_cinemagamut",
        "dlog_dgamut",
    ]
    assert all(d.segura for d in dets)


# ---------------------------------------------------------------------------
# Agrupacion de ambiguos
# ---------------------------------------------------------------------------


def test_agrupar_ambiguos_por_carpeta():
    clips = [
        _clip("c1", "clip1.mov", file_path="/vol/SONY_A/clip1.mov"),
        _clip("c2", "clip2.mov", file_path="/vol/SONY_A/clip2.mov"),
        _clip("c3", "clip3.mov", camera_manufacturer="Sony", gamma_notes="S-Log3", file_path="/vol/otra/clip3.mov"),
    ]
    grupos = agrupar_ambiguos(clips)
    assert len(grupos) == 1  # solo c1 y c2 son ambiguos; c3 es seguro y no entra
    grupo = grupos[0]
    assert set(grupo.clip_ids) == {"c1", "c2"}
    assert grupo.sugerencia_espacio is None
    assert "42" not in grupo.pregunta  # no hardcodea el numero de otro caso
    assert "2 clips" in grupo.pregunta


def test_agrupar_ambiguos_con_pista_parcial_consistente():
    """Los 42 clips de la Sony sin curva declarada: una sola pregunta, con conjetura."""
    clips = [
        _clip(f"c{i}", f"clip{i}.mov", camera_manufacturer="Sony", file_path="/vol/SONY/clip.mov")
        for i in range(42)
    ]
    grupos = agrupar_ambiguos(clips)
    assert len(grupos) == 1
    assert len(grupos[0].clip_ids) == 42
    assert grupos[0].sugerencia_espacio == "slog3_sgamut3cine"
    assert "42 clips parecen ser" in grupos[0].pregunta


def test_agrupar_ambiguos_por_prefijo_de_nombre_sin_ruta():
    clips = [
        _clip("c1", "A001C001"),
        _clip("c2", "A001C002"),
        _clip("c3", "B001C001"),
    ]
    grupos = agrupar_ambiguos(clips)
    claves = {g.grupo_id for g in grupos}
    assert claves == {"nombre:A", "nombre:B"}


def test_agrupar_ambiguos_da_un_frame_de_muestra():
    clips = [_clip("c1", "clip1.mov", file_path="/vol/X/clip1.mov"), _clip("c2", "clip2.mov", file_path="/vol/X/clip2.mov")]
    grupos = agrupar_ambiguos(clips)
    assert grupos[0].frame_muestra_clip_id in {"c1", "c2"}


def test_agrupar_ambiguos_vacio_si_todo_es_seguro():
    clips = [_clip("c1", camera_manufacturer="Sony", gamma_notes="S-Log3")]
    assert agrupar_ambiguos(clips) == []


def test_agrupar_ambiguos_orden_estable():
    """Los grupos salen ordenados por grupo_id: la GUI y los tests dependen de esto."""
    clips = [
        _clip("c1", "x.mov", file_path="/vol/Z/x.mov"),
        _clip("c2", "y.mov", file_path="/vol/A/y.mov"),
    ]
    grupos = agrupar_ambiguos(clips)
    assert [g.grupo_id for g in grupos] == sorted(g.grupo_id for g in grupos)
