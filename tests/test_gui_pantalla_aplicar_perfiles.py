"""`gui.pantalla_aplicar.PantallaAplicar`: el selector + botón de "perfil de
trabajo" (día 9, continuación 10) — el "un botón" que pidió Mario.

**CUIDADO DELIBERADO CON `lut_dir`**: igual que en `test_gui_perfiles_trabajo.py`,
todos los `FakeResolve` de aquí se construyen con
`incognitas=Incognitas(instalacion="mac_app_store")` y `home=tmp_path`, para
que la carpeta de LUTs "de Resolve" caiga dentro de `tmp_path` — nunca en la
carpeta real del sistema (`dd.estado_demo()` por defecto SÍ apuntaría ahí,
así que aquí no se usa el estado de demostración de siempre).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

from core.contracts import CDL, ClipRef, Confidence, MatchResult  # noqa: E402
from core.io.perfiles import guardar_perfil  # noqa: E402
from core.perfiles import PerfilCamara, PerfilTrabajo  # noqa: E402
from core.resolve import FakeResolve  # noqa: E402
from core.resolve.incognitas import Incognitas  # noqa: E402
from gui.datos_demo import ClipDemo, EstadoDemo  # noqa: E402
from gui.ventana import VentanaPrincipal, crear_app  # noqa: E402


def _match_identidad() -> MatchResult:
    return MatchResult(
        cdl=CDL(), lut=None, confidence=Confidence(score=1.0, level="alta", reasons=(), metrics={}),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=False,
    )


def _clip(clip_id: str, manufacturer: str | None) -> ClipDemo:
    ref = ClipRef(
        clip_id=clip_id, name=clip_id, track=1, index=1, start_frame=0, end_frame=99,
        camera_manufacturer=manufacturer,
    )
    return ClipDemo(ref=ref, match=_match_identidad())


def _estado_sandbox(tmp_path: Path) -> EstadoDemo:
    clips = [_clip("c1", "GoPro"), _clip("c2", "DJI")]
    incognitas = Incognitas(instalacion="mac_app_store")
    puente = FakeResolve(clips=[c.ref for c in clips], incognitas=incognitas, home=str(tmp_path), nodos_por_clip=3)
    return EstadoDemo(clips=clips, puente=puente)


def _app():
    return crear_app([])


def test_sin_carpeta_de_perfiles_el_selector_queda_deshabilitado(tmp_path):
    _app()
    estado = _estado_sandbox(tmp_path)
    v = VentanaPrincipal(estado)  # perfiles_carpeta=None por defecto
    try:
        assert not v.p_aplicar.selector_perfil.isEnabled()
        assert not v.p_aplicar.btn_aplicar_perfil.isEnabled()
    finally:
        v.close()


def test_carpeta_sin_perfiles_deja_el_selector_deshabilitado(tmp_path):
    _app()
    estado = _estado_sandbox(tmp_path)
    v = VentanaPrincipal(estado, perfiles_carpeta=str(tmp_path / "perfiles"))
    try:
        assert not v.p_aplicar.selector_perfil.isEnabled()
    finally:
        v.close()


def test_con_perfiles_guardados_el_selector_los_lista(tmp_path):
    carpeta = tmp_path / "perfiles"
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), carpeta / "fabrik", crear_directorios=True)
    guardar_perfil(PerfilTrabajo(nombre="Boda"), carpeta / "boda", crear_directorios=True)

    _app()
    estado = _estado_sandbox(tmp_path)
    v = VentanaPrincipal(estado, perfiles_carpeta=str(carpeta))
    try:
        selector = v.p_aplicar.selector_perfil
        assert selector.isEnabled()
        nombres = {selector.itemText(i) for i in range(selector.count())}
        assert nombres == {"boda", "fabrik"}
    finally:
        v.close()


def test_pulsar_aplicar_perfil_pone_look_rel_en_los_clips_reconocidos(tmp_path):
    carpeta = tmp_path / "perfiles"
    perfil = PerfilTrabajo(
        nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro", cdl_base=CDL(saturation=1.1)),)
    )
    guardar_perfil(perfil, carpeta / "fabrik", crear_directorios=True)

    _app()
    estado = _estado_sandbox(tmp_path)
    v = VentanaPrincipal(estado, perfiles_carpeta=str(carpeta))
    try:
        v.ir_a(2)  # pantalla de aplicar
        indice_fabrik = v.p_aplicar.selector_perfil.findText("fabrik")
        assert indice_fabrik >= 0
        v.p_aplicar.selector_perfil.setCurrentIndex(indice_fabrik)
        v.p_aplicar.btn_aplicar_perfil.click()

        por_id = {c.clip_id: c for c in estado.clips}
        assert por_id["c1"].look_rel is not None  # GoPro: reconocido por el perfil
        assert por_id["c2"].look_rel is None  # DJI: no esta en el perfil
        assert "Fabrik" in v.p_aplicar.texto_resultado.toPlainText()
    finally:
        v.close()


def test_perfil_que_no_se_puede_cargar_no_rompe_la_pantalla(tmp_path, monkeypatch):
    carpeta = tmp_path / "perfiles"
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), carpeta / "fabrik", crear_directorios=True)
    (carpeta / "fabrik" / "perfil.json").write_text("json roto {{{", encoding="utf-8")

    import gui.pantalla_aplicar as pa_mod

    avisos = []
    monkeypatch.setattr(pa_mod.QMessageBox, "warning", lambda *a, **k: avisos.append(a))

    _app()
    estado = _estado_sandbox(tmp_path)
    v = VentanaPrincipal(estado, perfiles_carpeta=str(carpeta))
    try:
        v.ir_a(2)
        v.p_aplicar.btn_aplicar_perfil.click()
        assert avisos  # se avisa
    finally:
        v.close()
