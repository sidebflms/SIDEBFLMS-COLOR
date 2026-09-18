"""`PantallaFacil` y el conmutador de modo de `VentanaPrincipal`.

Los datos que se ven en pantalla se comparan siempre con lo que devuelven
las funciones puras de `gui.asistente_facil` (ya probadas en
`tests/test_gui_asistente_facil.py`): aquí lo que se prueba es que la
PANTALLA los pinta, no que el cálculo esté bien otra vez.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from gui import datos_demo as dd  # noqa: E402
from gui import ventana as ventana_mod  # noqa: E402
from gui.asistente_facil import ID_PASOS, ejecutar_ordenar  # noqa: E402
from gui.pantalla_facil import PantallaFacil  # noqa: E402
from gui.ventana import CLAVE_MODO_FACIL, VentanaPrincipal  # noqa: E402
from tests.test_gui_apoyo import app_qt, asentar  # noqa: E402

pytestmark = pytest.mark.gui


class _SettingsFalso:
    """Sustituye a `QSettings` en memoria: nada de esto toca el disco ni el
    daemon de preferencias del sistema (`cfprefsd` en macOS cachea el valor
    real incluso después de borrar el archivo, así que un `QSettings` de
    verdad —aunque apunte a un directorio temporal— no aísla el test)."""

    _ALMACEN: dict[tuple[str, str], dict[str, object]] = {}

    def __init__(self, organizacion: str, aplicacion: str) -> None:
        self._datos = self._ALMACEN.setdefault((organizacion, aplicacion), {})

    def value(self, clave, defecto=None, type=None):  # noqa: A002
        return self._datos.get(clave, defecto)

    def setValue(self, clave, valor) -> None:
        self._datos[clave] = valor


@pytest.fixture(autouse=True)
def _settings_aislados(monkeypatch):
    _SettingsFalso._ALMACEN.clear()
    monkeypatch.setattr(ventana_mod, "QSettings", _SettingsFalso)
    yield
    _SettingsFalso._ALMACEN.clear()


def test_se_construye_sin_lanzar():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    assert p.paso_actual() == "ordenar"


def test_navega_los_cinco_pasos_en_orden():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    vistos = [p.paso_actual()]
    for _ in range(len(ID_PASOS) - 1):
        p.siguiente()
        vistos.append(p.paso_actual())
    assert tuple(vistos) == ID_PASOS
    p.siguiente()  # en el ultimo paso, no se pasa de largo
    assert p.paso_actual() == ID_PASOS[-1]


def test_deshacer_no_baja_de_cero():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    p.deshacer()
    assert p.paso_actual() == ID_PASOS[0]


def test_botones_se_deshabilitan_en_los_extremos():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    assert not p.boton_deshacer.isEnabled()
    assert p.boton_siguiente.isEnabled()
    for _ in range(len(ID_PASOS) - 1):
        p.siguiente()
    assert p.boton_deshacer.isEnabled()
    assert not p.boton_siguiente.isEnabled()


def test_la_frase_del_paso_1_coincide_con_el_calculo_puro():
    app_qt()
    estado = dd.estado_demo()
    esperado = ejecutar_ordenar(estado)
    p = PantallaFacil(estado)
    assert p._frase.text() == esperado.frase


def test_paso_look_sin_biblioteca_no_muestra_selector():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    p.siguiente()
    p.siguiente()
    p.siguiente()
    assert p.paso_actual() == "look"
    assert not p._selector_presets.isVisible()


def test_paso_look_muestra_el_panel_del_tutor_con_frases_del_catalogo():
    """Día 8, tarea 2.6: el modo fácil sólo enseña `Frase.texto`, nunca la
    característica ni el umbral (eso es el modo avanzado)."""
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    p.show()
    for _ in range(3):
        p.siguiente()
    assert p.paso_actual() == "look"
    assert p._panel_tutor.isVisible()
    assert p._panel_tutor._etiquetas, "el clip de demo tiene que dar alguna frase del tutor"


def test_panel_del_tutor_nunca_empuja_los_botones_fuera_de_la_ventana(monkeypatch):
    """Día 8, aviso de Mario: "la imagen es la que cede" y los botones
    Deshacer/Siguiente SIEMPRE visibles, pase lo que pase con el contenido
    del tutor. Fabrica muchas frases largas (más de las que el catálogo
    real produciría nunca) y comprueba que, a la anchura Y ALTURA mínimas
    reales de la ventana, los botones siguen dentro del rectángulo visible
    — no que "quepan de casualidad" con las dos frases cortas de la demo."""
    import gui.pantalla_facil as pf
    from core.tutor import Frase

    frases_falsas = tuple(
        Frase(
            regla_id=f"falsa_{i}",
            texto=(
                f"Frase de prueba número {i}, deliberadamente larga para forzar que el "
                "panel del tutor necesite más espacio vertical del que cabría de sobra "
                "con las dos frases cortas de la demo real."
            ),
            caracteristica="característica de prueba",
            valor_medido="valor de prueba",
            umbral=None,
            validacion="descriptiva",
            cifras_ref="—",
        )
        for i in range(8)
    )
    monkeypatch.setattr(pf, "frases_de_clip", lambda estado, clip: frases_falsas)

    p = PantallaFacil(dd.estado_demo())
    p.show()
    minimo_ancho = p.anchura_minima() if hasattr(p, "anchura_minima") else 973
    for _ in range(3):
        p.siguiente()
    assert p.paso_actual() == "look"
    asentar()
    alto_minimo = p.minimumSizeHint().height()
    p.resize(minimo_ancho, alto_minimo)
    asentar()

    assert len(p._panel_tutor._etiquetas) == len(frases_falsas)
    # El panel tiene tope: no puede crecer sin límite aunque haya 8 frases largas.
    from gui.pantalla_facil import ALTO_MAXIMO_PANEL_TUTOR

    assert p._panel_tutor._area.height() <= ALTO_MAXIMO_PANEL_TUTOR
    # Y los botones siguen dentro de la ventana, a su propia altura mínima real.
    abajo_boton = p.boton_deshacer.geometry().bottom()
    assert abajo_boton <= p.height(), (
        f"el botón Deshacer queda en y={abajo_boton}, fuera de una ventana de "
        f"{p.height()}px de alto"
    )
    assert p.boton_deshacer.isVisible() and p.boton_siguiente.isVisible()


def test_panel_del_tutor_se_oculta_fuera_del_paso_look():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    p.show()
    for _ in range(3):
        p.siguiente()
    assert p._panel_tutor.isVisible()
    p.siguiente()  # pasa a "repasar"
    assert not p._panel_tutor.isVisible()


def test_paso_look_con_biblioteca_muestra_selector_y_permite_elegir(tmp_path):
    from core.contracts import LUT3D
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.io.cube import escribir_cube

    lut = LUT3D.identity(3)
    escribir_cube(lut, tmp_path / "Look Uno.cube")
    escribir_cube(lut, tmp_path / "Look Dos.cube")
    biblioteca = tuple(sembrar_desde_carpeta(tmp_path))

    app_qt()
    p = PantallaFacil(dd.estado_demo(), biblioteca=biblioteca)
    p.show()
    for _ in range(3):
        p.siguiente()
    assert p.paso_actual() == "look"
    assert p._selector_presets.isVisible()
    assert set(p._selector_presets._botones) == {b.id for b in biblioteca}

    otro = next(b for b in biblioteca if b.nombre == "Look Dos")
    p._elegir_preset(otro.id)
    assert p._preset_elegido_id == otro.id
    assert otro.nombre in p._frase.text()


def test_selector_se_oculta_fuera_del_paso_look(tmp_path):
    from core.contracts import LUT3D
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.io.cube import escribir_cube

    lut = LUT3D.identity(3)
    escribir_cube(lut, tmp_path / "Look Uno.cube")
    biblioteca = tuple(sembrar_desde_carpeta(tmp_path))

    app_qt()
    p = PantallaFacil(dd.estado_demo(), biblioteca=biblioteca)
    p.show()
    for _ in range(3):
        p.siguiente()
    assert p._selector_presets.isVisible()
    p.siguiente()  # pasa a "repasar"
    assert not p._selector_presets.isVisible()


def test_paso_repasar_muestra_la_lista_completa_no_solo_el_primero():
    """Día 7, tarea 3: si sólo se pintaba `candidatos[0]` no había orden que
    enseñar en pantalla, aunque la frase dijera "por orden". La lista tiene
    que traer TODOS los candidatos del cálculo puro, no sólo el primero."""
    app_qt()
    estado = dd.estado_demo()
    p = PantallaFacil(estado)
    p.show()
    for _ in range(4):
        p.siguiente()
    assert p.paso_actual() == "repasar"

    from gui.asistente_facil import ejecutar_ordenar, ejecutar_repasar

    esperado = ejecutar_repasar(estado, ejecutar_ordenar(estado))
    assert esperado.candidatos  # el caso de demo tiene de sobra
    assert p._lista_repaso.isVisible()
    assert len(p._lista_repaso._botones) == len(esperado.candidatos)


def test_boton_de_la_lista_recorta_el_texto_largo_con_puntos_suspensivos():
    """Día 7: capturada la anchura mínima real, el motivo de un candidato
    salía cortado a mitad de palabra sin ninguna marca de que faltaba texto.
    A un ancho estrecho el botón tiene que recortar con «…» y guardar el
    texto completo en el tooltip, nunca cortarlo a lo bruto."""
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    p.show()
    for _ in range(4):
        p.siguiente()
    assert p._lista_repaso._botones
    b = p._lista_repaso._botones[0]
    completo = b._texto_completo
    b.resize(60, b.sizeHint().height())
    asentar()
    assert b.text() != completo
    assert b.text().endswith("…")
    assert b.toolTip() == completo


def test_lista_repaso_se_oculta_fuera_del_paso_repasar():
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    p.show()
    for _ in range(4):
        p.siguiente()
    assert p._lista_repaso.isVisible()
    p.deshacer()  # vuelve a "look"
    assert not p._lista_repaso.isVisible()


def test_elegir_un_candidato_de_la_lista_cambia_lo_que_se_muestra():
    app_qt()
    estado = dd.estado_demo()
    p = PantallaFacil(estado)
    for _ in range(4):
        p.siguiente()

    from gui.asistente_facil import ejecutar_ordenar, ejecutar_repasar

    candidatos = ejecutar_repasar(estado, ejecutar_ordenar(estado)).candidatos
    assert len(candidatos) > 1
    otro = candidatos[1]

    p._elegir_repaso(otro.clip_id)
    assert p._repaso_elegido_id == otro.clip_id
    assert otro.nombre in p._pregunta.text()


def test_paso_ordenar_no_muestra_ni_un_numero_de_confianza():
    """Regla del encargo: ni ΔE, ni CDL, ni cobertura, ni confianza en pantalla."""
    app_qt()
    p = PantallaFacil(dd.estado_demo())
    for texto in (p._frase.text(), p._pregunta.text()):
        assert "ΔE" not in texto
        assert "confianza" not in texto.lower()


# ---------------------------------------------------------------------------
# El conmutador de VentanaPrincipal
# ---------------------------------------------------------------------------


def test_conmutador_cambia_de_pagina_y_oculta_la_navegacion():
    app_qt()
    v = VentanaPrincipal(dd.estado_demo())
    v.show()
    asentar()
    assert v.pila.currentWidget() is not v.p_facil
    v.boton_modo_facil.setChecked(True)
    asentar()
    assert v.pila.currentWidget() is v.p_facil
    assert all(not b.isVisible() for b in v.grupo.buttons())
    v.boton_modo_facil.setChecked(False)
    asentar()
    assert v.pila.currentWidget() is not v.p_facil
    assert all(b.isVisible() for b in v.grupo.buttons())
    v.close()


def test_ir_a_estando_en_modo_facil_desactiva_el_modo_y_navega_de_verdad():
    """Bug real, cazado regenerando `capturas/`: `ir_a(0)` con el modo fácil
    activo dejaba la pila en la pantalla 0 pero el conmutador seguía marcado
    y los botones de navegación seguían ocultos — un estado a medias."""
    app_qt()
    v = VentanaPrincipal(dd.estado_demo())
    v.show()
    asentar()
    v.boton_modo_facil.setChecked(True)
    asentar()
    v.ir_a(2)
    asentar()
    assert not v.boton_modo_facil.isChecked()
    assert v.pila.currentIndex() == 2
    assert all(b.isVisible() for b in v.grupo.buttons())
    v.close()


def test_el_modo_se_recuerda_entre_ventanas():
    app_qt()
    v1 = VentanaPrincipal(dd.estado_demo())
    v1.show()
    asentar()
    v1.boton_modo_facil.setChecked(True)
    asentar()
    assert _SettingsFalso("SIDEBFLMS", "COLOR").value(CLAVE_MODO_FACIL, False) is True
    v1.close()

    v2 = VentanaPrincipal(dd.estado_demo())
    v2.show()
    asentar()
    assert v2.boton_modo_facil.isChecked()
    assert v2.pila.currentWidget() is v2.p_facil
    v2.close()
