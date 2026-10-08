"""Foco visible, nombres accesibles y atajos de teclado (auditoría de diseño
2026-10-06, bloque 4).

Antes: recorrer la app con Tab no cambiaba ni un píxel en la lista, la tabla ni el
visor (0 píxeles de diferencia al darles el foco): no se veía dónde estaba el
foco. Ahora tabla, lista, botones y visor lo muestran con un trazo `brand-400`
(#ff6a3d, como trazo: nunca pastilla ni relleno).

Se mide de verdad: se captura el widget sin foco y con foco y se cuentan los
píxeles distintos. Y se comprueba `hasFocus()`, porque un test que no llega a dar
el foco mediría 0 y «pasaría» por la razón equivocada.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QListWidget, QPushButton, QTableView, QWidget

from gui import identidad as idn
from gui.pantalla_comparar import VisorCortinilla
from gui.widgets import InsigniaConfianza, MarcaDesajuste
from tests.test_gui_apoyo import app_qt, asentar, demo, ventana

pytestmark = pytest.mark.gui

PANTALLAS = ("clips", "comparar", "aplicar", "reverse", "facil")


def _pixeles_que_cambian(w: QWidget) -> int:
    w.clearFocus()
    asentar(2)
    antes = w.grab().toImage()
    w.setFocus(Qt.FocusReason.TabFocusReason)
    asentar(2)
    assert w.hasFocus(), f"{type(w).__name__} no ha recibido el foco: el test no mide nada"
    despues = w.grab().toImage()
    assert antes.size() == despues.size()
    return sum(
        1
        for y in range(antes.height())
        for x in range(antes.width())
        if antes.pixel(x, y) != despues.pixel(x, y)
    )


def _primero_visible(v, clase, pantalla: int, **filtro):
    v.ir_a(pantalla)
    asentar()
    for w in v.findChildren(clase):
        if w.isVisible() and w.isEnabled() and all(getattr(w, k)() == val for k, val in filtro.items()):
            return w
    raise AssertionError(f"no hay {clase.__name__} visible en la pantalla {PANTALLAS[pantalla]}")


@pytest.mark.parametrize(
    "clase,pantalla",
    [(QTableView, 0), (VisorCortinilla, 1), (QListWidget, 2)],
    ids=["tabla de clips", "visor", "lista de Aplicar"],
)
def test_dar_foco_cambia_pixeles_en_tabla_lista_y_visor(clase, pantalla):
    app_qt()
    v = ventana(demo())
    try:
        w = _primero_visible(v, clase, pantalla)
        assert _pixeles_que_cambian(w) > 0
    finally:
        v.close()


def test_dar_foco_cambia_pixeles_en_los_botones():
    app_qt()
    v = ventana(demo())
    try:
        navegacion = _primero_visible(v, QPushButton, 0, objectName="navegacion")
        assert _pixeles_que_cambian(navegacion) > 0
        normal = _primero_visible(v, QPushButton, 2, objectName="")
        assert _pixeles_que_cambian(normal) > 0
    finally:
        v.close()


def test_el_foco_usa_el_naranja_de_marca_como_trazo_no_como_relleno():
    css = idn.hoja_de_estilo()
    # SUITE (rojo declarado): con los botones en pildora el foco de QPushButton y de
    # QListWidget es `border: 2px solid` (el relleno baja 1 px para no mover el layout), no
    # solo `border-color`; sigue siendo un TRAZO en brand-400, nunca un relleno.
    assert f"QTableView:focus {{ border-color: {idn.BRAND_400}; }}" in css
    for regla in ("QPushButton:focus", "QListWidget:focus"):
        assert f"{regla} {{ border: 2px solid {idn.BRAND_400};" in css, regla


def test_el_trazo_del_visor_es_de_dos_pixeles_en_brand_400():
    app_qt()
    v = ventana(demo())
    try:
        visor = _primero_visible(v, VisorCortinilla, 1)
        visor.clearFocus()
        asentar(2)
        sin = visor.grab().toImage()
        visor.setFocus(Qt.FocusReason.TabFocusReason)
        asentar(2)
        con = visor.grab().toImage()
        # Los 2 px del borde, en la fila central: el pixel del borde exterior y
        # el siguiente son los del trazo.
        y = con.height() // 2
        trazo = idn.color(idn.BRAND_400).rgb()
        assert con.pixel(0, y) != sin.pixel(0, y) and con.pixel(1, y) != sin.pixel(1, y)
        assert con.pixel(1, y) == trazo
        assert con.pixel(con.width() - 2, y) == trazo
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Nombres accesibles
# ---------------------------------------------------------------------------


def test_insignia_rombo_y_visor_tienen_nombre_accesible():
    app_qt()
    v = ventana(demo())
    try:
        visor = _primero_visible(v, VisorCortinilla, 1)
        assert visor.accessibleName() == "Visor antes y después"
        assert visor.accessibleDescription()
        insignias = v.findChildren(InsigniaConfianza)
        assert insignias, "no hay nada que comprobar: la ficha de Antes / después trae una insignia de confianza"
        for ins in insignias:
            assert ins.accessibleName().startswith("Confianza ")
            assert "%" in ins.accessibleName()
        assert MarcaDesajuste().accessibleName().startswith("Aviso: desajuste")
    finally:
        v.close()


def test_la_insignia_actualiza_su_nombre_accesible_con_la_confianza():
    app_qt()
    ins = InsigniaConfianza(idn.FormaConfianza.ALTA, 0.9)
    assert ins.accessibleName() == "Confianza alta, 90%"
    ins.actualizar(idn.FormaConfianza.BAJA, 0.3)
    assert ins.accessibleName() == "Confianza baja, 30%"


def test_las_celdas_de_insignia_y_aviso_de_la_tabla_dicen_su_contenido():
    from gui.pantalla_clips import COL_AVISO, COL_CONFIANZA

    app_qt()
    v = ventana(demo())
    try:
        tabla = _primero_visible(v, QTableView, 0)
        modelo = tabla.model()
        dichos = set()
        for fila in range(modelo.rowCount()):
            for col in (COL_CONFIANZA, COL_AVISO):
                t = modelo.index(fila, col).data(Qt.ItemDataRole.AccessibleTextRole)
                assert t, f"fila {fila}, columna {col}: la celda no dice nada a un lector de pantalla"
                dichos.add(t)
        assert any(t.startswith("Confianza ") for t in dichos)
    finally:
        v.close()


def test_ningun_boton_sin_texto_se_queda_sin_nombre_accesible():
    app_qt()
    v = ventana(demo())
    revisados = 0
    try:
        for i, nombre in enumerate(PANTALLAS):
            v.ir_a(i)
            asentar()
            botones = v.findChildren(QPushButton)
            assert botones, f"no hay nada que comprobar: {nombre} tiene botones (al menos los de navegación)"
            for b in botones:
                if b.isVisible():
                    revisados += 1
                    assert b.text().strip() or b.accessibleName().strip(), (
                        f"botón sin texto ni nombre accesible en {nombre}"
                    )
    finally:
        v.close()
    assert revisados > 5


# ---------------------------------------------------------------------------
# Cmd+1..4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("indice", [0, 1, 2, 3])
def test_ctrl_n_va_a_la_pantalla_n(indice):
    """«Ctrl» en Qt es Cmd en macOS."""
    app_qt()
    v = ventana(demo())
    try:
        v.ir_a((indice + 1) % 4)
        asentar()
        QTest.keyClick(v, Qt.Key(int(Qt.Key.Key_1) + indice), Qt.KeyboardModifier.ControlModifier)
        asentar()
        assert v.pila.currentIndex() == indice
    finally:
        v.close()


def test_los_botones_de_navegacion_anuncian_su_atajo():
    app_qt()
    v = ventana(demo())
    try:
        for i, boton in enumerate(v.grupo.buttons()):
            assert str(i + 1) in boton.toolTip(), boton.toolTip()
    finally:
        v.close()


def test_los_botones_de_navegacion_caben_en_el_carril():
    """El borde transparente del foco no puede ensanchar el botón: el carril mide
    186 px fijos y «INGENIERÍA INVERSA» va justa. (Con el cuerpo a 12 px del
    bloque 3, un borde de más la dejaba a 2 px de caber: se descuenta del relleno.)"""
    from gui.ventana import ANCHO_CARRIL

    app_qt()
    v = ventana(demo())
    try:
        for boton in [v.boton_modo_facil, *v.grupo.buttons()]:
            assert boton.sizeHint().width() <= ANCHO_CARRIL, (
                f"«{boton.text()}» pide {boton.sizeHint().width()} px y el carril mide {ANCHO_CARRIL}"
            )
    finally:
        v.close()
