"""Grupos de color: SÓLO LECTURA (día 9, continuación 15, punto 5).

`core.resolve.grupos.info_grupo_de_clip` + `clip_color_group`/
`group_post_clip_lut` (extras fuera del Protocol) + el aviso del plan de
`PantallaAplicar`. Nada de esto escribe en ningún grupo — el último test lo
comprueba mirando el estado del grupo antes y después.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from core.contracts import ResolveError  # noqa: E402
from core.resolve import FakeResolve  # noqa: E402
from core.resolve.grupos import info_grupo_de_clip  # noqa: E402
from core.resolve.live import LiveResolve  # noqa: E402


def _fake() -> FakeResolve:
    return FakeResolve(n_clips=3)


def test_clip_sin_grupo_da_none():
    assert info_grupo_de_clip(_fake(), "clip001") is None


def test_clip_en_grupo_sin_look_de_grupo():
    f = _fake()
    f.add_color_group("FABRIK")
    f.asignar_clip_a_grupo("clip001", "FABRIK")
    info = info_grupo_de_clip(f, "clip001")
    assert info is not None and info.nombre == "FABRIK" and info.look_rel is None
    assert "FABRIK" in info.aviso()


def test_clip_en_grupo_con_look_de_grupo_avisa_del_lut():
    f = _fake()
    f.add_color_group("FABRIK")
    f.set_group_post_clip_lut("FABRIK", 1, "SIDEB/otro.cube")
    f.asignar_clip_a_grupo("clip002", "FABRIK")
    info = info_grupo_de_clip(f, "clip002")
    assert info.look_rel == "SIDEB/otro.cube"
    assert "SIDEB/otro.cube" in info.aviso() and "POR ENCIMA" in info.aviso()


def test_un_clip_solo_pertenece_a_un_grupo():
    f = _fake()
    f.add_color_group("A")
    f.add_color_group("B")
    f.asignar_clip_a_grupo("clip001", "A")
    f.asignar_clip_a_grupo("clip001", "B")
    assert f.clip_color_group("clip001") == "B"


def test_desconectado_no_tumba_el_plan_da_none():
    f = FakeResolve(n_clips=1, conectado=False)
    with pytest.raises(ResolveError):
        f.clip_color_group("clip001")  # el puente sí lanza...
    assert info_grupo_de_clip(f, "clip001") is None  # ...la función pura no


def test_un_puente_sin_los_metodos_extra_da_none():
    class Viejo:
        pass

    assert info_grupo_de_clip(Viejo(), "x") is None


def test_mirar_no_escribe_en_el_grupo():
    f = _fake()
    f.add_color_group("FABRIK")
    f.set_group_post_clip_lut("FABRIK", 1, "SIDEB/otro.cube")
    f.asignar_clip_a_grupo("clip001", "FABRIK")
    antes = [(n.index, n.lut_path) for n in f.nodos_post_clip("FABRIK")]
    info_grupo_de_clip(f, "clip001")
    assert [(n.index, n.lut_path) for n in f.nodos_post_clip("FABRIK")] == antes


# --- LiveResolve, con dobles (sin Resolve real) --------------------------------


class _Grafo:
    def GetNumNodes(self):  # noqa: N802
        return 1

    def GetLUT(self, i):  # noqa: N802
        return "SIDEB/g.cube"


class _Grupo:
    def GetName(self):  # noqa: N802
        return "FABRIK"

    def GetPostClipNodeGraph(self):  # noqa: N802
        return _Grafo()


class _ItemConGrupo:
    def GetColorGroup(self):  # noqa: N802
        return _Grupo()


class _ItemSinGrupo:
    def GetColorGroup(self):  # noqa: N802
        return None


class _ItemViejo:
    GetColorGroup = None  # el atributo existe pero vale None (hasattr mentiría)


def _live(item) -> LiveResolve:
    live = LiveResolve.__new__(LiveResolve)
    live._item = lambda clip_id: item  # type: ignore[method-assign]
    return live


def test_live_devuelve_el_nombre_del_grupo():
    assert _live(_ItemConGrupo()).clip_color_group("c") == "FABRIK"


def test_live_sin_grupo_da_none():
    assert _live(_ItemSinGrupo()).clip_color_group("c") is None


def test_live_con_get_color_group_no_invocable_da_none():
    assert _live(_ItemViejo()).clip_color_group("c") is None


# --- el aviso llega al plan de "Aplicar" ------------------------------------------


def test_el_plan_avisa_del_grupo_y_no_bloquea():
    from gui import datos_demo as dd
    from gui.pantalla_aplicar import construir_plan

    estado = dd.estado_demo()
    refs = [c.ref for c in estado.clips]
    puente = FakeResolve(clips=refs, nodos_por_clip=3)
    puente.add_color_group("FABRIK")
    puente.set_group_post_clip_lut("FABRIK", 1, "SIDEB/otro.cube")
    puente.asignar_clip_a_grupo(refs[0].clip_id, "FABRIK")
    estado.puente = puente

    plan = construir_plan(estado, [refs[0].clip_id, refs[1].clip_id])

    con_grupo, sin_grupo = plan.lineas
    assert con_grupo.puede  # es un aviso, no un bloqueo
    assert any("FABRIK" in a and "SIDEB/otro.cube" in a for a in con_grupo.avisos)
    assert not any("grupo de color" in a for a in sin_grupo.avisos)
