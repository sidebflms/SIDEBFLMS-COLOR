"""Integracion de `core.colormgmt` con `FakeResolve`.

El test que pide el encargo tal cual: "una timeline simulada con las cuatro
camaras mezcladas queda con el espacio de entrada correcto en cada clip, y
los casos ambiguos salen agrupados para preguntar, no resueltos a lo loco."

`FakeResolve` acepta `clips: list[ClipRef]` ya hechos, asi que no hace falta
tocar `core.resolve.fake` para simular metadata: la metadata vive en el
`ClipRef` mismo, que es lo que `list_clips()` devuelve tal cual.
"""

from __future__ import annotations

from core.colormgmt import agrupar_ambiguos, detectar_espacios_timeline, verificar_proyecto
from core.contracts import NODE_NORMALIZACION, ClipRef
from core.resolve import FakeResolve


def _clip(clip_id: str, index: int, name: str, **kw) -> ClipRef:
    return ClipRef(
        clip_id=clip_id, name=name, track=1, index=index, start_frame=index * 100, end_frame=index * 100 + 50, **kw
    )


def _timeline_mixto() -> list[ClipRef]:
    return [
        # Completos: las cuatro camaras del encargo, cada una segura.
        _clip("c1", 1, "A001C001.mov", file_path="/vol/SONY/A001C001.mov",
              camera_manufacturer="Sony", camera_type="ILME-FX3", gamma_notes="S-Log3"),
        _clip("c2", 2, "B001C001.mov", file_path="/vol/LUMIX/B001C001.mov",
              camera_manufacturer="Panasonic", camera_type="DC-S5M2", gamma_notes="V-Log"),
        _clip("c3", 3, "C001C001.mov", file_path="/vol/CANON/C001C001.mov",
              camera_manufacturer="Canon", gamma_notes="Canon Log 3"),
        _clip("c4", 4, "D001C001.mov", file_path="/vol/DJI/D001C001.mov",
              camera_manufacturer="DJI", gamma_notes="D-Log"),
        # Incompletos: dos clips de la misma carpeta Sony, sin curva declarada.
        _clip("c5", 5, "A001C002.mov", file_path="/vol/SONY/A001C002.mov", camera_manufacturer="Sony"),
        _clip("c6", 6, "A001C003.mov", file_path="/vol/SONY/A001C003.mov", camera_manufacturer="Sony"),
        # Sin ningun metadato, carpeta propia.
        _clip("c7", 7, "X001.mov", file_path="/vol/SIN_DATOS/X001.mov"),
        # Contradictorio: declara curva de Sony pero el fabricante puesto es DJI.
        _clip("c8", 8, "raro.mov", file_path="/vol/RARO/raro.mov", camera_manufacturer="DJI", gamma_notes="S-Log3"),
    ]


def test_timeline_mixto_cuatro_camaras_mas_incompletos_y_contradictorios():
    fake = FakeResolve(clips=_timeline_mixto())
    clips = fake.list_clips()
    dets = detectar_espacios_timeline(clips)
    por_clip = {d.clip_id: d for d in dets}

    # Las cuatro completas: correctas y seguras, cada una en su espacio.
    assert por_clip["c1"].space == "slog3_sgamut3cine" and por_clip["c1"].segura
    assert por_clip["c2"].space == "vlog_vgamut" and por_clip["c2"].segura
    assert por_clip["c3"].space == "clog3_cinemagamut" and por_clip["c3"].segura
    assert por_clip["c4"].space == "dlog_dgamut" and por_clip["c4"].segura

    # Las incompletas y la sin datos: NO se resuelven solas.
    assert not por_clip["c5"].segura
    assert not por_clip["c6"].segura
    assert not por_clip["c7"].segura

    # La contradictoria: tampoco, y lo dice.
    assert not por_clip["c8"].segura
    assert "no cuadra" in por_clip["c8"].razon


def test_los_casos_ambiguos_salen_agrupados_no_resueltos_a_lo_loco():
    fake = FakeResolve(clips=_timeline_mixto())
    clips = fake.list_clips()
    dets = detectar_espacios_timeline(clips)
    grupos = agrupar_ambiguos(clips, dets)

    ids_agrupados = {cid for g in grupos for cid in g.clip_ids}
    # Los cuatro clips completos y seguros NUNCA aparecen en un grupo.
    assert ids_agrupados.isdisjoint({"c1", "c2", "c3", "c4"})
    # Los cuatro restantes si, cada uno en su carpeta/grupo.
    assert ids_agrupados == {"c5", "c6", "c7", "c8"}

    grupo_sony = next(g for g in grupos if "c5" in g.clip_ids)
    assert set(grupo_sony.clip_ids) == {"c5", "c6"}
    assert grupo_sony.sugerencia_espacio == "slog3_sgamut3cine"

    # Cada grupo trae con que fotograma enseñar la pregunta.
    assert all(g.frame_muestra_clip_id in g.clip_ids for g in grupos)


def test_verificador_de_doble_conversion_sobre_el_mismo_timeline():
    """Uno de los clips completos (Sony) tiene, ademas, un LUT de conversion
    puesto a mano en el nodo de normalizacion: doble conversion."""
    fake = FakeResolve(clips=_timeline_mixto())
    # Escribimos el LUT directamente en el estado interno del falso: no hace
    # falta pasar por la version SIDEB COLOR para esta comprobacion, que solo
    # lee `list_nodes()`.
    fake._clips["c1"].versiones[fake._clips["c1"].actual].nodos[NODE_NORMALIZACION - 1].lut_path = (
        "Sony/S-Log3 to Rec709.cube"
    )

    clips = fake.list_clips()
    project = fake.project_info()
    nodos_por_clip = {c.clip_id: fake.list_nodes(c.clip_id) for c in clips}
    dets = detectar_espacios_timeline(clips)

    avisos = verificar_proyecto(project, clips, nodos_por_clip, dets)
    dobles = [a for a in avisos if a.tipo == "doble_conversion"]
    assert len(dobles) == 1
    assert dobles[0].clip_id == "c1"

    contradicciones = [a for a in avisos if a.tipo == "curva_no_cuadra"]
    assert len(contradicciones) == 1
    assert contradicciones[0].clip_id == "c8"
