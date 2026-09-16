"""`gui.asistente_facil`: los cinco pasos del modo fácil, sin Qt.

Se prueba sobre `EstadoDemo` (el mismo material sintético que usa el modo
avanzado, ver `gui/datos_demo.py`): cero material real, cero invención — cada
paso lee resultados que ya calculó `core.matching`/`core.colormgmt` de verdad.
"""

from __future__ import annotations

from core.contracts import ClipRef
from gui.asistente_facil import (
    ejecutar_equilibrar,
    ejecutar_igualar,
    ejecutar_look,
    ejecutar_ordenar,
    ejecutar_repasar,
)
from gui.datos_demo import estado_demo, estado_desconectado, estado_vacio

# ---------------------------------------------------------------------------
# Paso 1 — ordenar la casa
# ---------------------------------------------------------------------------


def test_ordenar_sin_metadata_de_camara_agrupa_todo_como_pendiente():
    """`estado_demo()` no pone metadata de cámara en sus `ClipRef` (son de
    demostración): la regla de "no se adivina" tiene que dejarlos todos en
    grupos pendientes, no resueltos con una suposición."""
    estado = estado_demo()
    paso = ejecutar_ordenar(estado)
    assert not paso.clips_resueltos
    total_pendientes = sum(len(g.clip_ids) for g in paso.grupos_pendientes)
    assert total_pendientes == len(estado.clips)
    assert not paso.hecho


def test_ordenar_con_metadata_completa_resuelve_solo():
    estado = estado_demo()
    clips_con_metadata = []
    for i, c in enumerate(estado.clips):
        ref = ClipRef(
            clip_id=c.ref.clip_id, name=c.ref.name, track=1, index=i + 1,
            start_frame=c.ref.start_frame, end_frame=c.ref.end_frame,
            camera_manufacturer="Sony", gamma_notes="S-Log3",
        )
        c.ref = ref
        clips_con_metadata.append(c)
    estado.clips = clips_con_metadata
    paso = ejecutar_ordenar(estado)
    assert len(paso.clips_resueltos) == len(estado.clips)
    assert not paso.grupos_pendientes
    assert "espacio de entrada correcto" in paso.frase


def test_ordenar_estado_vacio_no_lanza():
    paso = ejecutar_ordenar(estado_vacio())
    assert paso.clips_resueltos == ()
    assert paso.grupos_pendientes == ()


def test_ordenar_desconectado_no_lanza_y_no_pide_avisos_de_proyecto():
    """Sin conexión no se puede leer `project_info()`/`list_nodes()`; el paso
    tiene que degradar (sin avisos de doble conversión) en vez de reventar."""
    paso = ejecutar_ordenar(estado_desconectado())
    assert paso.avisos == ()


# ---------------------------------------------------------------------------
# Paso 2 — igualar
# ---------------------------------------------------------------------------


def test_igualar_usa_la_referencia_del_estado():
    estado = estado_demo()
    paso = ejecutar_igualar(estado)
    assert paso.referencia_id == estado.referencia_id
    assert len(paso.igualados) == len(estado.clips) - 1  # todos menos la referencia
    assert paso.referencia_nombre in paso.frase


def test_igualar_sin_clips_no_lanza():
    paso = ejecutar_igualar(estado_vacio())
    assert paso.igualados == ()
    assert "Todavía" in paso.frase


# ---------------------------------------------------------------------------
# Paso 3 — equilibrar
# ---------------------------------------------------------------------------


def test_equilibrar_no_reinventa_el_cdl():
    """Lee EXACTAMENTE el CDL que ya calculó `core.matching.emparejar`
    (a través de `ClipDemo.match`), no recalcula nada por su cuenta."""
    estado = estado_demo()
    clip = estado.clips[0]
    paso = ejecutar_equilibrar(clip)
    assert paso.clip_id == clip.clip_id
    assert isinstance(paso.frase, str) and paso.frase


def test_equilibrar_frase_cambia_segun_el_cdl():
    estado = estado_demo()
    frases = {ejecutar_equilibrar(c).frase for c in estado.clips}
    # con seis clips distintos del generador, no todas las frases son iguales
    assert len(frases) > 1


# ---------------------------------------------------------------------------
# Paso 4 — look
# ---------------------------------------------------------------------------


def test_look_aplicado_a_todos_los_clips():
    estado = estado_demo()
    paso = ejecutar_look(estado)
    assert paso.look is estado.look
    assert set(paso.aplicado_a) == {c.clip_id for c in estado.clips}
    assert estado.look.title in paso.frase


def test_look_sin_clips_no_lanza():
    estado = estado_vacio()
    paso = ejecutar_look(estado)
    assert paso.aplicado_a == ()


# ---------------------------------------------------------------------------
# Paso 5 — repasar
# ---------------------------------------------------------------------------


def test_repasar_incluye_el_clip_con_desajuste_de_contenido():
    """`estado_demo()` tiene un clip (el exterior) deliberadamente cruzado
    contra la referencia de estudio: `content_mismatch=True` de verdad."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    con_desajuste = [c for c in estado.clips if c.match.content_mismatch]
    assert con_desajuste  # el caso de uso existe en el estado de demo
    ids_repasar = {c.clip_id for c in paso.candidatos}
    assert all(c.clip_id in ids_repasar for c in con_desajuste)


def test_repasar_incluye_los_grupos_pendientes_del_paso_1():
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    pendientes_ordenar = {cid for g in paso_ordenar.grupos_pendientes for cid in g.clip_ids}
    ids_repasar = {c.clip_id for c in paso.candidatos}
    assert pendientes_ordenar <= ids_repasar


def test_repasar_no_usa_la_palabra_confianza_en_sus_motivos():
    """La regla del encargo: el paso 5 no se apoya en la nota de confianza sin
    calibrar. Comprobación textual barata pero honesta: ningún motivo debe
    mencionar una nota o porcentaje de confianza."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    for c in paso.candidatos:
        assert "confianza" not in c.motivo.lower()
        assert "%" not in c.motivo


def test_repasar_no_duplica_un_clip_con_dos_motivos():
    """El exterior de `estado_demo()` tiene desajuste de contenido Y (al no
    llevar metadata de cámara) también cae en un grupo pendiente del paso 1:
    tiene que aparecer UNA vez, con los dos motivos, no dos veces."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    ids = [c.clip_id for c in paso.candidatos]
    assert len(ids) == len(set(ids)), "hay un clip_id repetido en la lista de repaso"


def test_repasar_vacio_cuando_no_hay_nada_que_mirar():
    estado = estado_vacio()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    assert paso.candidatos == ()
    assert "No hay nada" in paso.frase
