"""Ningún botón, casilla ni combo se queda cortado a 1024 ni a 973 px.

Cierra el hallazgo de la auditoría de diseño del 2026-10-06 (veredicto
«Mejorable»): en la pantalla Aplicar había tres controles con menos ancho del
que necesitan, a 1024 y a 973 px (tres a cada anchura):

* «Copiar la estructura de nodos al resto marcado»: 210 px de 304;
* «Aplicar perfil a todo el lote»: 102 px de 182;
* el combo «(sin carpeta de perfiles configurada)»: 210 px de 298.

Se arreglaron con textos cortos (el largo va al tooltip) y, en el combo, con
`AdjustToMinimumContentsLengthWithIcon`. Este test mira las cinco pantallas, en
varios estados, con el detector `controles_cortados()` de `test_gui_apoyo.py`
(que tiene sus propios tests: un detector que no detecta pasa siempre).
"""

from __future__ import annotations

import pytest

from tests.test_gui_apoyo import (
    ANCHURA_MINIMA,
    app_qt,
    confianza_baja,
    controles_cortados,
    demo,
    desconectado,
    redimensionar,
    vacio,
    ventana,
)

pytestmark = pytest.mark.gui

ANCHURAS = (1024, ANCHURA_MINIMA)
PANTALLAS = ("clips", "comparar", "aplicar", "reverse", "facil")


@pytest.mark.parametrize("ancho", ANCHURAS)
@pytest.mark.parametrize(
    "nombre,estado",
    [("demo", demo), ("vacio", vacio), ("confianza baja", confianza_baja), ("desconectado", desconectado)],
)
def test_ningun_control_se_corta(ancho, nombre, estado):
    app_qt()
    v = ventana(estado())
    try:
        redimensionar(v, ancho, 900)
        for indice, pantalla in enumerate(PANTALLAS):
            v.ir_a(indice)
            redimensionar(v, ancho, 900)
            cortados = controles_cortados(v)
            assert not cortados, f"{nombre} · {pantalla} · {ancho} px: {cortados}"
    finally:
        v.close()


@pytest.mark.parametrize("ancho", ANCHURAS)
def test_el_combo_de_perfiles_con_perfiles_guardados_tampoco_se_corta(ancho, tmp_path):
    """El mensaje de «sin perfiles» no es el único texto posible del combo: con
    perfiles, lo que se ve es el nombre del perfil (los que dé Mario)."""
    from core.io.perfiles import guardar_perfil
    from core.perfiles import PerfilTrabajo
    from gui.ventana import VentanaPrincipal

    carpeta = tmp_path / "perfiles"
    guardar_perfil(PerfilTrabajo(nombre="Fabrik"), carpeta / "fabrik", crear_directorios=True)
    app_qt()
    v = VentanaPrincipal(demo(), perfiles_carpeta=str(carpeta))
    v.resize(ancho, 900)
    v.show()
    try:
        v.ir_a(2)
        redimensionar(v, ancho, 900)
        assert not controles_cortados(v)
    finally:
        v.close()
