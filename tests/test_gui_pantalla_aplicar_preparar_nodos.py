"""`gui.pantalla_aplicar.PantallaAplicar`: el botón "preparar nodos" (día 9,
continuación 11) — la única vía real que queda para el bloqueo de los 3
nodos (`ApplyGradeFromDRX` no existe, confirmado el día anterior): que Mario
prepare UN clip a mano y la app propague esa estructura al resto por
script, con `core.resolve.copiar_grado_seguro` (ya existía, sólo le faltaba
un botón).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.resolve import FakeResolve  # noqa: E402
from core.resolve.fake import _Nodo  # noqa: E402
from gui import datos_demo as dd  # noqa: E402
from gui.ventana import VentanaPrincipal, crear_app  # noqa: E402


def _app():
    return crear_app([])


def _estado_con_una_plantilla():
    """`estado_demo()` con TODOS los clips a 1 nodo (el caso real confirmado:
    AddVersion no hereda nodos) salvo el primero, con 3 -- simula que Mario
    ya lo preparó a mano en Resolve antes de abrir la app."""
    estado = dd.estado_demo()
    refs = [c.ref for c in estado.clips]
    puente = FakeResolve(
        clips=refs, nodos_por_clip=1, project_name="SIDEB · DEMO", timeline_name="TL 01 MONTAJE"
    )
    plantilla_id = refs[0].clip_id
    clip_interno = puente._clip(plantilla_id)
    version = puente._version_actual(clip_interno)
    version.nodos = [_Nodo(index=1), _Nodo(index=2), _Nodo(index=3)]
    estado.puente = puente
    return estado, plantilla_id


def _enfocar_clip(pantalla, clip_id: str) -> None:
    from PySide6.QtCore import Qt

    for i in range(pantalla.lista.count()):
        if pantalla.lista.item(i).data(Qt.ItemDataRole.UserRole) == clip_id:
            pantalla.lista.setCurrentRow(i)
            return
    raise AssertionError(f"no se ha encontrado el clip {clip_id!r} en la lista")


def test_sin_clip_enfocado_avisa_y_no_hace_nada(monkeypatch):
    _app()
    estado, _plantilla_id = _estado_con_una_plantilla()
    v = VentanaPrincipal(estado)
    try:
        v.ir_a(2)
        v.p_aplicar.lista.setCurrentRow(-1)
        avisos = []
        import gui.pantalla_aplicar as pa_mod

        monkeypatch.setattr(pa_mod.QMessageBox, "warning", lambda *a, **k: avisos.append(a))
        v.p_aplicar.btn_preparar_nodos.click()
        assert avisos
    finally:
        v.close()


def test_sin_destinos_marcados_avisa_y_no_hace_nada(monkeypatch):
    _app()
    estado, plantilla_id = _estado_con_una_plantilla()
    v = VentanaPrincipal(estado)
    try:
        v.ir_a(2)
        v.p_aplicar._marcar_todos(False)
        _enfocar_clip(v.p_aplicar, plantilla_id)
        avisos = []
        import gui.pantalla_aplicar as pa_mod

        monkeypatch.setattr(pa_mod.QMessageBox, "warning", lambda *a, **k: avisos.append(a))
        v.p_aplicar.btn_preparar_nodos.click()
        assert avisos
    finally:
        v.close()


def test_copia_la_estructura_y_desbloquea_el_plan():
    _app()
    estado, plantilla_id = _estado_con_una_plantilla()
    resto_ids = [c.clip_id for c in estado.clips if c.clip_id != plantilla_id]

    v = VentanaPrincipal(estado)
    try:
        v.ir_a(2)
        v.p_aplicar._marcar_todos(True)
        _enfocar_clip(v.p_aplicar, plantilla_id)
        assert v.p_aplicar.clip_enfocado() == plantilla_id

        plan_antes = v.p_aplicar.plan_actual()
        bloqueados_antes = {linea.clip_id for linea in plan_antes.bloqueados}
        assert set(resto_ids) <= bloqueados_antes  # bloqueados por nodos, antes de preparar
        assert plantilla_id not in bloqueados_antes  # la plantilla ya tenía sus 3 nodos

        v.p_aplicar.btn_preparar_nodos.click()

        plan_despues = v.p_aplicar.plan_actual()
        bloqueados_despues = {linea.clip_id for linea in plan_despues.bloqueados}
        assert not (set(resto_ids) & bloqueados_despues)  # ya no bloqueados por nodos
        assert "copiada" in v.p_aplicar.texto_resultado.toPlainText().lower()
    finally:
        v.close()


def test_no_se_copia_a_si_misma_la_plantilla():
    """Marcar la plantilla junto con el resto no debe intentar copiarla sobre
    sí misma -- `_preparar_nodos_desde_plantilla` la excluye de los destinos."""
    _app()
    estado, plantilla_id = _estado_con_una_plantilla()
    resto_ids = [c.clip_id for c in estado.clips if c.clip_id != plantilla_id]

    v = VentanaPrincipal(estado)
    try:
        v.ir_a(2)
        v.p_aplicar._marcar_todos(True)  # la plantilla tambien queda marcada
        _enfocar_clip(v.p_aplicar, plantilla_id)
        v.p_aplicar.btn_preparar_nodos.click()  # no debe lanzar ni avisar de error
        mensaje = v.p_aplicar.texto_resultado.toPlainText()
        assert f"copiada a {len(resto_ids)} clip" in mensaje
        for cid in resto_ids:
            assert cid in mensaje  # los destinos reales sí aparecen
    finally:
        v.close()
