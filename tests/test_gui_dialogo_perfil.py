"""`gui.dialogo_perfil.DialogoPerfiles` (día 9, continuación 14): la pieza
que le faltaba a `core.io.perfiles.guardar_perfil` desde que se creó
(continuación 10) — existía en código, pero nada en la GUI lo llamaba. Un
perfil de trabajo sólo se podía montar a mano en Python.

Nada de `lut_dir` de Resolve aquí (a diferencia de `gui/perfiles_trabajo.py`):
este diálogo sólo lee/escribe en la carpeta de perfiles (`tmp_path` en los
tests) y en el `.cube` que el usuario elija a mano — nunca toca la carpeta
de LUTs real del sistema.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.contracts import CDL, LUT3D  # noqa: E402
from core.io.cube import escribir_cube  # noqa: E402
from core.io.perfiles import cargar_perfil, guardar_perfil, listar_perfiles  # noqa: E402
from core.perfiles import PerfilCamara, PerfilTrabajo  # noqa: E402
from gui.dialogo_perfil import DialogoPerfiles  # noqa: E402


def _app():
    if QApplication.instance() is None:
        QApplication([])
    return QApplication.instance()


def test_sin_perfiles_la_lista_esta_vacia_y_el_formulario_en_blanco(tmp_path):
    _app()
    d = DialogoPerfiles(tmp_path)
    assert d.lista.count() == 0
    assert d.campo_nombre.text() == ""
    assert d._filas_camara == []


def test_construye_con_un_perfil_ya_guardado_y_lo_lista(tmp_path):
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), tmp_path / "fabrik", crear_directorios=True)
    _app()
    d = DialogoPerfiles(tmp_path)
    assert [d.lista.item(i).text() for i in range(d.lista.count())] == ["fabrik"]


def test_seleccionar_un_perfil_lo_carga_en_el_formulario(tmp_path):
    perfil = PerfilTrabajo(
        nombre="Fabrik",
        camaras=(PerfilCamara(fabricante_contiene="gopro", cdl_base=CDL(saturation=1.2)),),
    )
    guardar_perfil(perfil, tmp_path / "fabrik", crear_directorios=True)
    _app()
    d = DialogoPerfiles(tmp_path)

    d.lista.setCurrentRow(0)

    assert d.campo_nombre.text() == "Fabrik"
    assert len(d._filas_camara) == 1
    assert d._filas_camara[0].campo_fabricante.text() == "gopro"
    assert d._filas_camara[0].editor_cdl.cdl().saturation == pytest.approx(1.2)


def test_nuevo_limpia_el_formulario_tras_haber_seleccionado_uno(tmp_path):
    guardar_perfil(
        PerfilTrabajo(nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro"),)),
        tmp_path / "fabrik", crear_directorios=True,
    )
    _app()
    d = DialogoPerfiles(tmp_path)
    d.lista.setCurrentRow(0)

    d.btn_nuevo.click()

    assert d.campo_nombre.text() == ""
    assert d._filas_camara == []
    assert d._carpeta_actual is None


def test_anadir_y_quitar_fila_camara(tmp_path):
    _app()
    d = DialogoPerfiles(tmp_path)
    d.btn_anadir_camara.click()
    d.btn_anadir_camara.click()
    assert len(d._filas_camara) == 2

    d._quitar_fila_camara(d._filas_camara[0])
    assert len(d._filas_camara) == 1


def test_guardar_perfil_nuevo_lo_deja_en_disco_y_en_la_lista(tmp_path):
    _app()
    d = DialogoPerfiles(tmp_path)
    d.campo_nombre.setText("Boda")
    d.btn_anadir_camara.click()
    d._filas_camara[0].campo_fabricante.setText("sony")
    d._filas_camara[0].editor_cdl.poner(CDL(saturation=1.1))

    d.btn_guardar.click()

    assert "boda" in listar_perfiles(tmp_path)
    releido = cargar_perfil(tmp_path / "boda")
    assert releido.nombre == "Boda"
    assert releido.camaras[0].fabricante_contiene == "sony"
    assert d.lista.currentItem().text() == "boda"


def test_guardar_con_nombre_vacio_avisa_y_no_guarda(tmp_path, monkeypatch):
    _app()
    d = DialogoPerfiles(tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a))

    d.btn_guardar.click()

    assert avisos
    assert listar_perfiles(tmp_path) == []


def test_guardar_nombre_que_coincide_con_uno_existente_pide_confirmacion(tmp_path, monkeypatch):
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), tmp_path / "fabrik", crear_directorios=True)
    _app()
    d = DialogoPerfiles(tmp_path)
    d.btn_nuevo.click()
    d.campo_nombre.setText("Fabrik")  # mismo slug que el ya guardado

    preguntas = []

    def _no(*a, **k):
        preguntas.append(a)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", _no)
    d.btn_guardar.click()

    assert preguntas
    # No se sobrescribió: sigue siendo el perfil original, sin cámaras nuevas.
    assert cargar_perfil(tmp_path / "fabrik").camaras == ()


def test_eliminar_perfil_pide_confirmacion_y_borra_si_se_acepta(tmp_path, monkeypatch):
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), tmp_path / "fabrik", crear_directorios=True)
    _app()
    d = DialogoPerfiles(tmp_path)
    d.lista.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    d.btn_eliminar.click()

    assert listar_perfiles(tmp_path) == []
    assert d.lista.count() == 0
    assert d._carpeta_actual is None


def test_eliminar_perfil_no_borra_si_se_rechaza_la_confirmacion(tmp_path, monkeypatch):
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), tmp_path / "fabrik", crear_directorios=True)
    _app()
    d = DialogoPerfiles(tmp_path)
    d.lista.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

    d.btn_eliminar.click()

    assert listar_perfiles(tmp_path) == ["fabrik"]


def test_examinar_look_deja_la_ruta_elegida_lista_para_guardar(tmp_path, monkeypatch):
    ruta_look = tmp_path / "un_look.cube"
    escribir_cube(LUT3D.identity(3), ruta_look)

    _app()
    d = DialogoPerfiles(tmp_path / "perfiles")
    d.campo_nombre.setText("Boda")
    monkeypatch.setattr(
        "gui.dialogo_perfil.QFileDialog.getOpenFileName", lambda *a, **k: (str(ruta_look), "")
    )

    d.btn_examinar_look.click()
    d.btn_guardar.click()

    releido = cargar_perfil(tmp_path / "perfiles" / "boda")
    assert releido.look is not None


def test_editar_perfil_existente_conserva_su_look_si_no_se_toca(tmp_path):
    perfil = PerfilTrabajo(nombre="Fabrik", look=LUT3D.identity(3))
    guardar_perfil(perfil, tmp_path / "fabrik", crear_directorios=True)

    _app()
    d = DialogoPerfiles(tmp_path)
    d.lista.setCurrentRow(0)
    d.campo_nombre.setText("Fabrik renombrado")  # se toca el nombre, no el look

    d.btn_guardar.click()

    releido = cargar_perfil(tmp_path / "fabrik")
    assert releido.nombre == "Fabrik renombrado"
    assert releido.look is not None


def test_quitar_look_de_un_perfil_existente_lo_borra_al_guardar(tmp_path):
    perfil = PerfilTrabajo(nombre="Fabrik", look=LUT3D.identity(3))
    guardar_perfil(perfil, tmp_path / "fabrik", crear_directorios=True)

    _app()
    d = DialogoPerfiles(tmp_path)
    d.lista.setCurrentRow(0)
    d.btn_quitar_look.click()

    d.btn_guardar.click()

    assert cargar_perfil(tmp_path / "fabrik").look is None
