"""La regla de oro, vista desde la interfaz.

**Nada se escribe fuera de la version `SIDEB COLOR`.** Eso ya lo impone
`core/resolve/bridge.py` con un `if`, y tiene sus propios tests. Lo que se
comprueba aqui es lo otro: que **la GUI pasa por ahi**, que no hay ningun
camino en `gui/` que llame a las escrituras a pelo, y que despues de darle al
boton el grado del usuario sigue donde estaba, intacto.

Se mira de cuatro formas, porque con una sola no basta:

1. **Espiando `aplicar_grado_seguro`**: se sustituye por un doble que anota y
   delega. Si la pantalla escribiera por otro lado, el doble no se enteraria y
   el test lo diria.
2. **Mirando donde quedaron las escrituras**: `FakeResolve` guarda cada CDL
   escrito con la version en la que cayo (`_grados_escritos`). Todas tienen que
   estar en `SIDEB COLOR`.
3. **Mirando la version del usuario**: los nodos de `Version 1` tienen que
   seguir sin CDL y sin LUT despues de aplicar a los siete clips.
4. **Leyendo el codigo**: ningun modulo de `gui/` puede llamar a `set_cdl`,
   `set_lut`, `set_node_enabled`, `copy_grades` ni `reset_all_grades`, ni tocar
   la via de escape `PELIGRO_escribir_fuera_de_la_version`.

Los estados de estos tests se construyen **enteros cada vez**, sin cache: un
test que viera las escrituras del anterior no probaria nada.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from core.contracts import NODE_BALANCE, NODE_LOOK, VERSION_NAME  # noqa: E402
from core.resolve import EscrituraFueraDeVersion, es_version_nuestra  # noqa: E402
from core.resolve.fake import VERSION_INICIAL  # noqa: E402
from gui import datos_demo as dd  # noqa: E402
from gui import pantalla_aplicar as pa  # noqa: E402
from tests.test_gui_apoyo import asentar, ventana  # noqa: E402

pytestmark = pytest.mark.gui

RAIZ_GUI = Path(__file__).resolve().parent.parent / "gui"

#: Los metodos del puente que escriben color. La GUI no llama a ninguno.
ESCRITURAS_CRUDAS = (
    "set_cdl",
    "set_lut",
    "set_node_enabled",
    "copy_grades",
    "reset_all_grades",
)


# ---------------------------------------------------------------------------
# 1 · la pantalla pasa por aplicar_grado_seguro
# ---------------------------------------------------------------------------


def test_aplicar_al_lote_pasa_por_aplicar_grado_seguro(monkeypatch):
    est = dd.estado_demo()
    visto: list[tuple[str, dict]] = []
    real = pa.aplicar_grado_seguro

    def espia(bridge, clip_id, **kw):
        visto.append((clip_id, kw))
        return real(bridge, clip_id, **kw)

    monkeypatch.setattr(pa, "aplicar_grado_seguro", espia)
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        v.p_aplicar._aplicar_lote()
        asentar(2)
    finally:
        v.close()

    assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
    assert [c for c, _ in visto] == [c.clip_id for c in est.clips], (
        "algun clip se ha escrito sin pasar por aplicar_grado_seguro"
    )
    for (clip_id, kw), clip in zip(visto, est.clips, strict=True):
        assert kw["cdl"] is clip.match.cdl, f"{clip_id}: se ha escrito otro CDL"
        assert kw["lut_rel_path"] == est.look_rel


def test_aplicar_a_un_solo_clip_tambien_pasa_por_ahi(monkeypatch):
    est = dd.estado_demo()
    visto: list[str] = []
    real = pa.aplicar_grado_seguro

    def espia(bridge, clip_id, **kw):
        visto.append(clip_id)
        return real(bridge, clip_id, **kw)

    monkeypatch.setattr(pa, "aplicar_grado_seguro", espia)
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        v.p_aplicar.lista.setCurrentRow(2)
        asentar(2)
        v.p_aplicar._aplicar_uno()
        asentar(2)
    finally:
        v.close()
    assert visto == [est.clips[2].clip_id]


# ---------------------------------------------------------------------------
# 2 y 3 · donde quedaron las escrituras
# ---------------------------------------------------------------------------


def test_todas_las_escrituras_caen_en_la_version_de_la_app():
    est = dd.estado_demo()
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        v.p_aplicar._aplicar_lote()
        asentar(2)
    finally:
        v.close()

    escritos = est.puente._grados_escritos
    assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
    assert len(escritos) == len(est.clips), "no se ha escrito en todos los clips"
    for g in escritos:
        assert g.version == VERSION_NAME, (
            f"se ha escrito un CDL en la version {g.version!r}, que no es de la app"
        )
        assert es_version_nuestra(g.version)
        assert g.node_index == NODE_BALANCE


def test_la_version_del_usuario_sigue_intacta_despues_de_aplicar():
    """El grado de Mario se queda en `Version 1`, sin CDL y sin LUT."""
    est = dd.estado_demo()
    assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
    for clip in est.clips:
        assert est.puente.current_version(clip.clip_id) == VERSION_INICIAL

    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        v.p_aplicar._aplicar_lote()
        asentar(2)
    finally:
        v.close()

    for clip in est.clips:
        for nodo in (NODE_BALANCE, NODE_LOOK):
            assert est.puente._cdl_escrito(clip.clip_id, nodo, version=VERSION_INICIAL) is None, (
                f"{clip.clip_id}: hay un CDL en el nodo {nodo} de la version del usuario"
            )
            assert est.puente._lut_escrito(clip.clip_id, nodo, version=VERSION_INICIAL) is None, (
                f"{clip.clip_id}: hay un LUT en el nodo {nodo} de la version del usuario"
            )
        assert VERSION_NAME in est.puente.version_names(clip.clip_id)


def test_la_version_se_crea_antes_de_la_primera_escritura():
    """El orden importa: `AddVersion` primero, `SetCDL` despues. Siempre."""
    est = dd.estado_demo()
    est.puente._llamadas.clear()
    pa.aplicar(est, [est.clips[0].clip_id])
    llamadas = est.puente._llamadas
    assert "set_cdl" in llamadas
    assert "add_version" in llamadas
    assert llamadas.index("add_version") < llamadas.index("set_cdl"), (
        "se ha escrito el CDL antes de crear la version: eso es escribir encima "
        "del grado del usuario"
    )


def test_aplicar_dos_veces_no_crea_una_segunda_version():
    """Idempotente: nada de `SIDEB COLOR 2`, `SIDEB COLOR 3`..."""
    est = dd.estado_demo()
    ids = [c.clip_id for c in est.clips]
    assert ids, "no hay nada que comprobar: el estado de demostracion no trae clips"
    pa.aplicar(est, ids)
    pa.aplicar(est, ids)
    for clip_id in ids:
        nombres = est.puente.version_names(clip_id)
        nuestras = [n for n in nombres if es_version_nuestra(n)]
        assert nuestras == [VERSION_NAME], f"{clip_id} ha acabado con {nombres}"


def test_el_puente_corta_una_escritura_a_pelo():
    """Comprobacion de que la red de debajo existe de verdad.

    Si esto dejara de lanzar, los tests de arriba seguirian pasando y la regla
    de oro no estaria protegida por nada.
    """
    est = dd.estado_demo()
    clip_id = est.clips[0].clip_id
    assert est.puente.current_version(clip_id) == VERSION_INICIAL
    with pytest.raises(EscrituraFueraDeVersion):
        est.puente.set_cdl(clip_id, NODE_BALANCE, est.clips[0].match.cdl)


def test_el_resultado_que_se_ensena_dice_en_que_version_se_escribio():
    est = dd.estado_demo()
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        v.p_aplicar._aplicar_lote()
        asentar(2)
        texto = v.p_aplicar.texto_resultado.toPlainText()
        assert VERSION_NAME in texto
        assert f"nodo {NODE_BALANCE}" in texto
        assert f"nodo {NODE_LOOK}" in texto
        assert est.look_rel in texto
    finally:
        v.close()


# ---------------------------------------------------------------------------
# 4 · lo que dice el codigo
# ---------------------------------------------------------------------------


def _llamadas_de(archivo: Path) -> list[tuple[int, str]]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    salida = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            salida.append((nodo.lineno, nodo.func.attr))
    return salida


def test_ningun_modulo_de_la_gui_llama_a_una_escritura_cruda():
    """Se lee el arbol de sintaxis: un docstring que NOMBRE `set_cdl` para
    explicar que no se usa no puede hacer fallar el test, y una llamada
    escondida dentro de una expresion si tiene que salir."""
    culpables: list[str] = []
    assert sorted(RAIZ_GUI.glob("*.py")), (
        f"no hay nada que comprobar: {RAIZ_GUI} no tiene ningun .py (carpeta movida o renombrada)"
    )
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        for linea, metodo in _llamadas_de(archivo):
            if metodo in ESCRITURAS_CRUDAS:
                culpables.append(f"{archivo.name}:{linea}: llama a {metodo}()")
    assert not culpables, (
        "la GUI escribe color sin pasar por aplicar_grado_seguro / copiar_grado_seguro:\n"
        + "\n".join(culpables)
    )


def test_la_gui_no_toca_la_via_de_escape_de_la_regla_de_oro():
    """`PELIGRO_escribir_fuera_de_la_version` es para los tests y para el probe.

    Se llama asi de feo a proposito. Si aparece en `gui/`, el diseno esta mal.
    """
    culpables: list[str] = []
    assert sorted(RAIZ_GUI.glob("*.py")), (
        f"no hay nada que comprobar: {RAIZ_GUI} no tiene ningun .py (carpeta movida o renombrada)"
    )
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        texto = archivo.read_text(encoding="utf-8")
        if "PELIGRO_escribir_fuera_de_la_version" in texto:
            culpables.append(archivo.name)
    assert not culpables, (
        "la GUI usa la via de escape de la regla de oro: " + ", ".join(culpables)
    )


def test_la_gui_no_importa_el_puente_de_verdad():
    """`LiveResolve`, `DaVinciResolveScript` y `fusionscript`, ni mencionados."""
    prohibidos = ("DaVinciResolveScript", "fusionscript", "core.resolve.live", "LiveResolve")
    culpables: list[str] = []
    assert sorted(RAIZ_GUI.glob("*.py")), (
        f"no hay nada que comprobar: {RAIZ_GUI} no tiene ningun .py (carpeta movida o renombrada)"
    )
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if any(p in alias.name for p in prohibidos):
                        culpables.append(f"{archivo.name}:{nodo.lineno}: import {alias.name}")
            elif isinstance(nodo, ast.ImportFrom):
                origen = nodo.module or ""
                nombres = [a.name for a in nodo.names]
                if any(p in origen for p in prohibidos) or any(
                    p in n for p in prohibidos for n in nombres
                ):
                    culpables.append(f"{archivo.name}:{nodo.lineno}: from {origen}")
    assert not culpables, "la GUI importa el puente de verdad:\n" + "\n".join(culpables)


def test_hoy_la_gui_no_tiene_ningun_camino_de_copiar_grados():
    """Dejado por escrito a proposito, no es un olvido.

    `copiar_grado_seguro` existe en el puente y es el unico camino seguro para
    `CopyGrades`, pero **la interfaz no copia grados de un clip a otro**: cada
    clip lleva su propio CDL, calculado contra la referencia. El dia que haya un
    boton de «copiar a los demas», tiene que salir por ahi, y este test se
    convierte en el que lo comprueba.
    """
    assert sorted(RAIZ_GUI.glob("*.py")), (
        f"no hay nada que comprobar: {RAIZ_GUI} no tiene ningun .py (carpeta movida o renombrada)"
    )
    llamadas = {
        metodo
        for archivo in RAIZ_GUI.glob("*.py")
        for _, metodo in _llamadas_de(archivo)
    }
    assert "copy_grades" not in llamadas
    assert "copiar_grado_seguro" not in llamadas, (
        "ya hay un camino de copia en la GUI: cambia este test por uno que "
        "compruebe que pasa por copiar_grado_seguro y que no pisa la version del usuario"
    )
