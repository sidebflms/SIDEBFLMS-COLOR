"""`gui.pantalla_aplicar.aplicar_cancelable`: la MISMA escritura que
`aplicar()` (mismo `aplicar_grado_seguro`, mismo `ResolveError` por clip),
envuelta en `core.batch.ejecutar_lote` para poder pararse a mitad — la pieza
que `BITACORA.md` señalaba como hueco (Bloque 3, punto 8: "no hay forma de
cancelar `aplicar()` a mitad").
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.batch import ProgresoLote  # noqa: E402
from core.contracts import VERSION_NAME  # noqa: E402
from gui import datos_demo as dd  # noqa: E402
from gui.pantalla_aplicar import aplicar, aplicar_cancelable  # noqa: E402


def test_sin_cancelar_da_los_mismos_resultados_que_aplicar():
    """No es una segunda implementación de la regla de oro: sobre el mismo
    estado, sin cancelar nunca, tiene que dar exactamente lo mismo que
    `aplicar()` -- mismos clips, mismo ok, misma versión, mismo mensaje."""
    est1 = dd.estado_demo()
    est2 = dd.estado_demo()
    ids = [c.clip_id for c in est1.clips]

    normales = aplicar(est1, ids)
    cancelables = aplicar_cancelable(est2, ids)

    assert [r.clip_id for r in normales] == [r.clip_id for r in cancelables]
    assert [(r.ok, r.version, r.mensaje) for r in normales] == [
        (r.ok, r.version, r.mensaje) for r in cancelables
    ]


def test_una_averia_de_una_sola_vez_se_cura_igual_que_en_aplicar():
    est = dd.estado_demo()
    est.puente.fallar_en("set_cdl", "disco lleno", veces=1)
    resultados = aplicar_cancelable(est, [c.clip_id for c in est.clips])
    fallidos = [r for r in resultados if not r.ok]
    buenos = [r for r in resultados if r.ok]
    assert len(fallidos) == 1
    assert "disco lleno" in fallidos[0].mensaje
    assert len(buenos) == len(est.clips) - 1
    for r in buenos:
        assert r.version == VERSION_NAME


def test_un_clip_que_desaparece_no_tumba_el_lote():
    """Mismo escenario y misma garantía que
    test_gui_estados.py::test_un_clip_que_desaparece_de_la_timeline_no_tumba_el_lote:
    el clip SIGUE apareciendo en los resultados (con ok=False), no
    desaparece del lote -- lo que no existe es su escritura en Resolve."""
    est = dd.estado_demo()
    assert len(est.clips) >= 2
    desaparecido = est.clips[0].clip_id
    del est.puente._clips[desaparecido]

    resultados = aplicar_cancelable(est, [c.clip_id for c in est.clips])
    por_id = {r.clip_id: r for r in resultados}

    assert len(resultados) == len(est.clips)
    assert not por_id[desaparecido].ok
    assert "no existe el clip" in por_id[desaparecido].mensaje


# ---------------------------------------------------------------------------
# Lo nuevo: cancelar de verdad a mitad
# ---------------------------------------------------------------------------


def test_cancelar_a_mitad_para_de_escribir_de_verdad():
    """No es sólo que el resultado se corte -- Resolve (FakeResolve) no
    recibe NINGUNA llamada para los clips posteriores al punto de
    cancelación. Cancelar de mentira (que igual escribe todo y sólo recorta
    la lista al final) no sería la garantía que pide BITACORA.md."""
    est = dd.estado_demo()
    ids = [c.clip_id for c in est.clips]
    assert len(ids) >= 3, "hace falta margen para distinguir 'se paró a mitad' de 'se paró al final'"

    vistos = []

    def debe_cancelar() -> bool:
        return len(vistos) >= 2

    def callback(p: ProgresoLote) -> None:
        vistos.append(p.resultado.item_id)

    resultados = aplicar_cancelable(est, ids, callback_progreso=callback, debe_cancelar=debe_cancelar)

    assert len(resultados) == 2
    assert [r.clip_id for r in resultados] == ids[:2]
    # Los clips NO intentados no dejaron ninguna huella en Resolve.
    llamadas_por_clip_no_intentado = [
        ll for ll in est.puente._llamadas if any(cid in ll for cid in ids[2:])
    ]
    assert llamadas_por_clip_no_intentado == []


def test_callback_progreso_recibe_un_progreso_por_clip():
    est = dd.estado_demo()
    ids = [c.clip_id for c in est.clips]
    progresos: list[ProgresoLote] = []
    aplicar_cancelable(est, ids, callback_progreso=progresos.append)
    assert [p.resultado.item_id for p in progresos] == ids
    assert all(p.total == len(ids) for p in progresos)


def test_sin_debe_cancelar_hace_el_lote_entero_igual_que_aplicar():
    est = dd.estado_demo()
    ids = [c.clip_id for c in est.clips]
    resultados = aplicar_cancelable(est, ids)
    assert len(resultados) == len(ids)
