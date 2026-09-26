"""`PantallaFacil.btn_usar_al_aplicar` (día 9, continuación 12): el punto 2
de la lista de Mario — el preset elegido en el selector de modo fácil, hasta
ahora, sólo cambiaba la vista previa; `PantallaAplicar` seguía escribiendo
el look fijo de siempre porque nada los conectaba.

**Por qué un botón, no algo automático al navegar los pasos**: `FakeResolve`
con la instalación por defecto ("descarga") devuelve la carpeta de LUTs REAL
del sistema — escribir en cada navegación al paso "look" (como hacen
decenas de tests existentes con `dd.estado_demo()` sin sandbox) habría
escrito ahí en cada pasada de la suite. Por eso el despliegue real sólo
ocurre al pulsar `btn_usar_al_aplicar`, y **todos** los `FakeResolve` de
aquí se construyen sandboxed (`incognitas=Incognitas(instalacion=
"mac_app_store")` + `home=tmp_path`), igual que en
`test_gui_perfiles_trabajo.py` / `test_gui_despliegue_presets.py`.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

from core.contracts import LUT3D  # noqa: E402
from core.io.biblioteca import sembrar_desde_carpeta  # noqa: E402
from core.io.cube import escribir_cube  # noqa: E402
from core.resolve import FakeResolve  # noqa: E402
from core.resolve.incognitas import Incognitas, lut_dir  # noqa: E402
from gui import datos_demo as dd  # noqa: E402
from gui.pantalla_facil import PantallaFacil  # noqa: E402
from tests.test_gui_apoyo import app_qt  # noqa: E402


def _estado_con_biblioteca_sandbox(tmp_path: Path):
    carpeta_luts = tmp_path / "luts_origen"
    carpeta_luts.mkdir()
    lut = LUT3D.identity(3)
    escribir_cube(lut, carpeta_luts / "Look Uno.cube")
    escribir_cube(lut, carpeta_luts / "Look Dos.cube")
    biblioteca = tuple(sembrar_desde_carpeta(carpeta_luts))

    estado = dd.estado_demo()
    incognitas = Incognitas(instalacion="mac_app_store")
    refs = [c.ref for c in estado.clips]
    estado.puente = FakeResolve(
        clips=refs, incognitas=incognitas, home=str(tmp_path / "resolve_home"),
        project_name="SIDEB · DEMO", timeline_name="TL 01 MONTAJE",
    )
    return estado, biblioteca


def _lut_dir_de_prueba(tmp_path: Path) -> Path:
    return Path(lut_dir(Incognitas(instalacion="mac_app_store"), home=str(tmp_path / "resolve_home")))


def test_boton_oculto_fuera_del_paso_look(tmp_path):
    app_qt()
    estado, biblioteca = _estado_con_biblioteca_sandbox(tmp_path)
    p = PantallaFacil(estado, biblioteca=biblioteca)
    assert not p.btn_usar_al_aplicar.isVisible()


def test_boton_visible_y_habilitado_en_el_paso_look_con_preset(tmp_path):
    app_qt()
    estado, biblioteca = _estado_con_biblioteca_sandbox(tmp_path)
    p = PantallaFacil(estado, biblioteca=biblioteca)
    p.show()
    for _ in range(3):
        p.siguiente()
    assert p.paso_actual() == "look"
    assert p.btn_usar_al_aplicar.isVisible()
    assert p.btn_usar_al_aplicar.isEnabled()


def test_sin_biblioteca_el_boton_no_se_habilita():
    app_qt()
    p = PantallaFacil(dd.estado_demo())  # sin biblioteca: estado.look de siempre
    p.show()
    for _ in range(3):
        p.siguiente()
    assert p.paso_actual() == "look"
    assert not p.btn_usar_al_aplicar.isEnabled()


def test_pulsar_el_boton_no_escribe_nada_fuera_del_sandbox(tmp_path):
    """La comprobación que de verdad importa: el `.cube` cae DENTRO de
    `tmp_path`, nunca en la carpeta real del sistema."""
    app_qt()
    estado, biblioteca = _estado_con_biblioteca_sandbox(tmp_path)
    p = PantallaFacil(estado, biblioteca=biblioteca)
    p.show()
    for _ in range(3):
        p.siguiente()

    p.btn_usar_al_aplicar.click()

    lut_dir_prueba = _lut_dir_de_prueba(tmp_path)
    ruta_absoluta = lut_dir_prueba / estado.look_rel
    assert ruta_absoluta.is_file()
    assert ruta_absoluta.is_relative_to(tmp_path)  # nunca fuera del sandbox


def test_pulsar_el_boton_deja_look_rel_apuntando_al_preset_elegido(tmp_path):
    app_qt()
    estado, biblioteca = _estado_con_biblioteca_sandbox(tmp_path)
    p = PantallaFacil(estado, biblioteca=biblioteca)
    p.show()
    for _ in range(3):
        p.siguiente()

    otro = next(b for b in biblioteca if b.nombre == "Look Dos")
    p._elegir_preset(otro.id)
    p.btn_usar_al_aplicar.click()

    assert otro.id.split("-")[0] in estado.look_rel or "look-dos" in estado.look_rel
    assert "Listo" in p._frase.text()


def test_elegir_otro_preset_sin_pulsar_boton_no_cambia_look_rel(tmp_path):
    """El punto entero de que sea un botón aparte: la vista previa cambia
    sola al elegir, pero `look_rel` (lo que de verdad se aplicaría) no se
    toca hasta que Mario lo confirme."""
    app_qt()
    estado, biblioteca = _estado_con_biblioteca_sandbox(tmp_path)
    look_rel_inicial = estado.look_rel
    p = PantallaFacil(estado, biblioteca=biblioteca)
    p.show()
    for _ in range(3):
        p.siguiente()

    otro = next(b for b in biblioteca if b.nombre == "Look Dos")
    p._elegir_preset(otro.id)

    assert estado.look_rel == look_rel_inicial
