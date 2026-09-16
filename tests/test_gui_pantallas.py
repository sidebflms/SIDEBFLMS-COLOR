"""Cada pantalla se construye contra `FakeResolve` y **los datos llegan**.

Aqui no hay ni un test de «se instancia el widget y no lanza», que no prueba
nada. Lo que se comprueba es que el numero que se ve en pantalla es el numero
que trae la dataclass del contrato:

* la lista de clips ensena los clips que hay en el puente, con su nombre y sus
  dos ΔE;
* la insignia que se pinta es la del `Confidence` de ese clip, y se comprueba
  **pintandola**: se renderiza la celda con el delegado y se compara pixel a
  pixel con la insignia dibujada a mano con el nivel y la puntuacion buenos;
* los diez numeros del CDL del panel de ingenieria inversa son los del
  `ReverseResult`, con sus cuatro decimales;
* y el plan de la pantalla de aplicar dice la version, el nodo y el `.cube` que
  de verdad se van a usar.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem  # noqa: E402

from core.contracts import NODE_BALANCE, NODE_LOOK, VERSION_NAME  # noqa: E402
from gui import identidad as idn  # noqa: E402
from gui.datos_demo import (  # noqa: E402
    ClipDemo,
    EstadoDemo,
    match_con_desajuste_y_confianza_alta,
)
from gui.pantalla_aplicar import construir_plan  # noqa: E402
from gui.pantalla_clips import (  # noqa: E402
    COL_ANTES,
    COL_CONFIANZA,
    COL_DESPUES,
    COL_INDICE,
    COL_NOMBRE,
    ROL_CLIP,
    FichaClip,
)
from gui.pantalla_comparar import PASO_FLECHA  # noqa: E402
from gui.pantalla_reverse import montaje_cobertura  # noqa: E402
from gui.widgets import INSIGNIA_ALTO, INSIGNIA_ANCHO, pintar_insignia_confianza  # noqa: E402
from tests.test_gui_apoyo import (  # noqa: E402
    app_qt,
    asentar,
    demo,
    es_monoespaciada,
    ventana,
)

pytestmark = pytest.mark.gui


# ---------------------------------------------------------------------------
# Pantalla 1 · clips y confianza
# ---------------------------------------------------------------------------


def test_la_tabla_ensena_los_clips_que_hay_en_el_puente():
    """Los del modelo son los del `FakeResolve`, en el mismo orden."""
    est = demo()
    v = ventana(est)
    try:
        modelo = v.p_clips.modelo
        del_puente = est.puente.list_clips()
        assert modelo.rowCount() == len(del_puente) == len(est.clips)
        for fila, ref in enumerate(del_puente):
            clip: ClipDemo = modelo.data(modelo.index(fila, 0), ROL_CLIP)
            assert clip.clip_id == ref.clip_id
            assert modelo.data(modelo.index(fila, COL_NOMBRE)) == ref.name
            assert modelo.data(modelo.index(fila, COL_INDICE)) == f"{ref.index:03d}"
    finally:
        v.close()


def test_los_dos_delta_e_de_cada_fila_son_los_del_matchresult():
    est = demo()
    v = ventana(est)
    try:
        modelo = v.p_clips.modelo
        assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
        for fila, clip in enumerate(est.clips):
            assert modelo.data(modelo.index(fila, COL_ANTES)).strip() == (
                f"{clip.match.delta_e_before:6.2f}".strip()
            )
            assert modelo.data(modelo.index(fila, COL_DESPUES)).strip() == (
                f"{clip.match.delta_e_after:6.2f}".strip()
            )
            fuente = modelo.data(modelo.index(fila, COL_ANTES), Qt.ItemDataRole.FontRole)
            assert es_monoespaciada(fuente), "un ΔE de la tabla no va en monoespaciada"
    finally:
        v.close()


def _pintar_celda(tabla, delegado, indice, ancho=160, alto=34) -> QImage:
    img = QImage(ancho, alto, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    op = QStyleOptionViewItem()
    op.initFrom(tabla)
    op.widget = tabla
    op.rect = QRect(0, 0, ancho, alto)
    op.state = QStyle.StateFlag.State_Enabled
    delegado.paint(p, op, indice)
    p.end()
    return img


def _insignia_a_mano(tabla, nivel: str, score: float, ancho=160, alto=34) -> QImage:
    """La misma celda, pero con la confianza puesta a mano. La referencia."""
    img = QImage(ancho, alto, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    op = QStyleOptionViewItem()
    op.initFrom(tabla)
    op.widget = tabla
    op.rect = QRect(0, 0, ancho, alto)
    op.state = QStyle.StateFlag.State_Enabled
    op.text = ""
    tabla.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, op, p, tabla)
    r = QRect(0, 0, ancho, alto)
    h = min(INSIGNIA_ALTO, r.height() - 6)
    caja = r.adjusted(6, (r.height() - h) // 2, 0, 0)
    caja.setWidth(min(INSIGNIA_ANCHO, r.width() - 12))
    caja.setHeight(h)
    pintar_insignia_confianza(p, caja, idn.FormaConfianza.de_nivel(nivel), score)
    p.end()
    return img


def test_la_insignia_que_se_pinta_es_la_confianza_de_ese_clip():
    """Se compara lo PINTADO, no el atributo.

    El delegado podria estar leyendo la confianza de otra fila, o redondeando
    la puntuacion, y un test que mirara `clip.match.confidence` no se enteraria.
    Aqui se renderiza la celda de verdad y se compara pixel a pixel con la
    insignia dibujada con el nivel y la puntuacion que trae el `Confidence`.
    """
    est = demo()
    v = ventana(est)
    try:
        tabla = v.p_clips.tabla
        delegado = tabla.itemDelegateForColumn(COL_CONFIANZA)
        assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
        for fila, clip in enumerate(est.clips):
            conf = clip.match.confidence
            indice = v.p_clips.modelo.index(fila, COL_CONFIANZA)
            pintada = _pintar_celda(tabla, delegado, indice)
            buena = _insignia_a_mano(tabla, conf.level, conf.score)
            assert pintada == buena, (
                f"fila {fila} ({clip.clip_id}): la insignia pintada no es la del "
                f"Confidence ({conf.level}, {conf.score:.4f})"
            )
    finally:
        v.close()


def test_una_insignia_con_la_confianza_equivocada_si_se_distingue():
    """Control negativo del test de arriba: si comparara mal, pasaria siempre."""
    est = demo()
    v = ventana(est)
    try:
        tabla = v.p_clips.tabla
        clip = est.clips[0]
        conf = clip.match.confidence
        buena = _insignia_a_mano(tabla, conf.level, conf.score)
        otra = _insignia_a_mano(tabla, "baja", 0.11)
        assert buena != otra
    finally:
        v.close()


def test_la_ficha_ensena_las_razones_tal_cual_vienen_del_nucleo():
    """`Confidence.reasons` viene en castellano y ordenado. No se reescribe."""
    est = demo()
    v = ventana(est)
    try:
        assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
        for fila, clip in enumerate(est.clips):
            v.p_clips.tabla.selectRow(fila)
            asentar(2)
            texto = v.p_clips.ficha.razones.text()
            assert clip.match.confidence.reasons, (
                f"no hay nada que comprobar: {clip.clip_id} no trae ni una razon de confianza"
            )
            for razon in clip.match.confidence.reasons:
                assert razon in texto, f"falta una razon del clip {clip.clip_id}: {razon!r}"
            assert v.p_clips.ficha._de_antes.text() == f"{clip.match.delta_e_before:.2f}"
            assert v.p_clips.ficha._de_despues.text() == f"{clip.match.delta_e_after:.2f}"
    finally:
        v.close()


def test_el_desajuste_se_ensena_aunque_la_confianza_salga_alta():
    """Lo exige `CONTRATOS.md` sobre `MatchResult.content_mismatch`.

    Por el camino normal no se puede llegar ahi (`puntuar_confianza` penaliza
    el desajuste), asi que el `MatchResult` se construye a mano. Es justo para
    lo que esta la dataclass del contrato.
    """
    app_qt()
    est = demo()
    clip = ClipDemo(
        ref=est.clips[0].ref,
        match=match_con_desajuste_y_confianza_alta(),
        original=None,
        razones_desajuste=("la composicion no se parece",),
    )
    ficha = FichaClip()
    ficha.show()
    asentar()
    try:
        ficha.mostrar(clip)
        asentar(2)
        assert clip.match.confidence.level == "alta"
        assert clip.match.content_mismatch is True
        assert ficha.bloque_desajuste.isVisible(), (
            "con confianza alta se ha escondido el aviso de desajuste"
        )
        assert "composicion" in ficha.texto_desajuste.text()
    finally:
        ficha.close()


def test_sin_clip_seleccionado_la_ficha_lo_dice_y_no_inventa_cifras():
    app_qt()
    ficha = FichaClip()
    ficha.show()
    asentar()
    try:
        ficha.mostrar(None)
        asentar(2)
        assert ficha._de_antes.text() == "—"
        assert ficha._de_despues.text() == "—"
        assert not ficha.insignia.isVisible()
        assert not ficha.bloque_desajuste.isVisible()
    finally:
        ficha.close()


# ---------------------------------------------------------------------------
# Pantalla 2 · antes / despues
# ---------------------------------------------------------------------------


def test_comparar_pinta_los_numeros_del_match_y_el_cdl_entero():
    est = demo()
    v = ventana(est)
    try:
        v.ir_a(1)
        comparar = v.p_comparar
        clip = comparar.clip_actual()
        assert clip is not None
        asentar(2)
        assert comparar._cifras["antes"].text() == f"{clip.match.delta_e_before:.2f}"
        assert comparar._cifras["despues"].text() == f"{clip.match.delta_e_after:.2f}"
        texto = comparar.texto_cdl.text()
        cdl = clip.match.cdl
        for v_ in cdl.slope:
            assert f"{v_:.4f}" in texto
        for v_ in cdl.offset:
            assert f"{v_:+.4f}" in texto
        for v_ in cdl.power:
            assert f"{v_:.4f}" in texto
        assert f"{cdl.saturation:.4f}" in texto
        assert es_monoespaciada(comparar.texto_cdl.font()), (
            "los diez numeros del CDL no van en monoespaciada"
        )
    finally:
        v.close()


def test_comparar_no_arranca_ensenando_la_referencia_contra_si_misma():
    est = demo()
    v = ventana(est)
    try:
        v.ir_a(1)
        asentar(2)
        clip = v.p_comparar.clip_actual()
        assert clip is not None
        assert clip.clip_id != est.referencia_id, (
            "la pantalla de comparar arranca comparando la referencia consigo misma"
        )
    finally:
        v.close()


def test_el_despues_es_el_cdl_del_contrato_aplicado_al_antes():
    """El «despues» no es una simulacion: es `CDL.apply()`, la formula del nodo 2."""
    est = demo()
    clip = next(c for c in est.clips if c.original is not None)
    esperado = clip.match.cdl.apply(clip.original)
    np.testing.assert_allclose(clip.despues(), esperado, rtol=0, atol=1e-6)


def test_la_cortinilla_se_mueve_con_el_teclado_y_se_lee_en_monoespaciada():
    est = demo()
    v = ventana(est)
    try:
        v.ir_a(1)
        asentar(2)
        visor = v.p_comparar.visor
        visor.set_posicion(0.5)
        asentar(1)
        assert v.p_comparar.pos_texto.text().strip() == "50.0 %"
        assert es_monoespaciada(v.p_comparar.pos_texto.font())
        visor.set_posicion(0.5 + PASO_FLECHA)
        asentar(1)
        assert abs(visor.posicion() - 0.52) < 1e-9
        visor.set_posicion(-5.0)
        assert visor.posicion() == 0.0
        visor.set_posicion(5.0)
        assert visor.posicion() == 1.0
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Pantalla 3 · aplicar
# ---------------------------------------------------------------------------


def test_el_plan_dice_la_version_el_nodo_y_el_cube_antes_de_escribir():
    est = demo()
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        aplicar = v.p_aplicar
        plan = aplicar.plan_actual()
        assert not plan.error_global
        assert len(plan.lineas) == len(est.clips)
        for linea, clip in zip(plan.lineas, est.clips, strict=True):
            assert linea.clip_id == clip.clip_id
            assert linea.n_nodos == len(est.puente.list_nodes(clip.clip_id))
            assert linea.version_actual == est.puente.current_version(clip.clip_id)
            assert VERSION_NAME in linea.accion_version
        html = aplicar.texto_plan.toHtml()
        assert VERSION_NAME in html
        assert est.look_rel in html
        assert f"nodo {NODE_BALANCE}" in html
        assert f"nodo {NODE_LOOK}" in html
        primero = est.clips[0].match.cdl
        assert f"{primero.slope[0]:.4f}" in html
        assert f"{primero.saturation:.4f}" in html
    finally:
        v.close()


def test_construir_plan_no_escribe_absolutamente_nada():
    """El plan es lo que se mira ANTES de decidir. No puede tocar el puente."""
    est = demo()
    antes = list(est.puente._grados_escritos)
    versiones = {c.clip_id: list(est.puente.version_names(c.clip_id)) for c in est.clips}
    construir_plan(est, [c.clip_id for c in est.clips])
    assert est.puente._grados_escritos == antes
    assert versiones, "no hay nada que comprobar: el estado de demostracion no trae clips"
    for clip_id, nombres in versiones.items():
        assert est.puente.version_names(clip_id) == nombres


def test_el_contador_del_plan_cuenta_los_que_de_verdad_se_pueden():
    est = demo()
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        plan = v.p_aplicar.plan_actual()
        assert v.p_aplicar.contador.text() == (
            f"{len(plan.aplicables)} de {len(v.p_aplicar.seleccionados())} clips"
        )
        v.p_aplicar._marcar_todos(False)
        asentar(2)
        assert v.p_aplicar.seleccionados() == []
        assert not v.p_aplicar.btn_lote.isEnabled()
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Pantalla 4 · ingenieria inversa
# ---------------------------------------------------------------------------


def test_los_numeros_del_cdl_del_panel_son_los_del_reverseresult():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        res = v.p_reverse.resultado()
        assert res is not None
        puesto = v.p_reverse.editor.cdl()
        # Los campos tienen cuatro decimales: se compara a esa resolucion, que
        # es la que el colorista ve y puede teclear.
        np.testing.assert_allclose(puesto.slope, res.cdl.slope, atol=5e-5)
        np.testing.assert_allclose(puesto.offset, res.cdl.offset, atol=5e-5)
        np.testing.assert_allclose(puesto.power, res.cdl.power, atol=5e-5)
        assert abs(puesto.saturation - res.cdl.saturation) < 5e-5
        assert not v.p_reverse.editor.editado(), (
            "el CDL recien recuperado sale marcado como «editado» sin que nadie lo toque"
        )
    finally:
        v.close()


def test_las_cifras_del_diagnostico_son_las_del_reverseresult():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        res = v.p_reverse.resultado()
        assert res is not None
        diag = res.diagnosis
        # Sin espacio antes del `%`: esta cifra va a 26 px y en monoespaciada el
        # espacio mide ahi 16 px, o sea que «62.6 %» se leia como dos cosas. Lo
        # que este test vigila no es el formato, es que el numero de la pantalla
        # sea el del `ReverseResult`, y eso sigue clavado al valor.
        assert v.p_reverse.cifra_repro.text() == f"{diag.lut_reproducible * 100:.1f}%"
        assert abs(v.p_reverse.barra_repro.valor() - diag.lut_reproducible) < 1e-6
        assert v.p_reverse._de_media.text() == f"{res.delta_e_mean:.2f}"
        assert v.p_reverse._de_p95.text() == f"{res.delta_e_p95:.2f}"
        assert v.p_reverse._de_max.text() == f"{res.delta_e_max:.2f}"
        celdas = int(res.coverage.covered_mask().sum())
        # [dia 4] Recuento en la cabecera del mapa; porcentaje, en el diagnostico.
        assert f"{celdas:,}".replace(",", ".") in v.p_reverse.celdas_cobertura.text()
        assert v.p_reverse.cifra_cobertura.text() == (
            f"{res.coverage.coverage_fraction() * 100:.2f}%"
        )
    finally:
        v.close()


def test_editar_un_numero_del_cdl_marca_editado_y_restaurar_lo_deshace():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        editor = v.p_reverse.editor
        original = editor.cdl()
        editor._campos["slope_r"].setValue(original.slope[0] + 0.25)
        asentar(1)
        assert editor.editado()
        assert v.p_reverse.marca_editado.isVisible()
        editor.restaurar()
        asentar(1)
        assert not editor.editado()
        assert not v.p_reverse.marca_editado.isVisible()
    finally:
        v.close()


def test_el_editor_de_cdl_no_deja_un_power_de_cero():
    """`power > 0` o el constructor del contrato lanza."""
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        editor = v.p_reverse.editor
        editor._campos["power_r"].setValue(0.0)
        asentar(1)
        assert editor.cdl().power[0] > 0.0
    finally:
        v.close()


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "VACIO ENCONTRADO EL 2026-09-16 (revisor de vacios, dia 4). La mitad «una celda medida "
        "no se pinta igual que una inventada» NUNCA ha comprobado nada: el montaje pinta solo "
        "el corte b=0 (cortes=1) y en el estado de demostracion ese corte tiene 0 celdas "
        "cubiertas. LUT 17^3: 52 cubiertas de 4.913; por corte b = 0,3,6,7,7,7,4,4,5,6,3,0,0,0,0,0,0. "
        "La otra mitad (tablero de 2 tonos en las inventadas) si se comprueba. Se reproduce con: "
        ".venv/bin/python -m pytest tests/test_gui_pantallas.py -k mapa_de_cobertura --runxfail. "
        "Cerrarlo = montar un corte que tenga celdas cubiertas (p. ej. b=3 o b=4) sin aflojar lo "
        "que se afirma; decide el dueño de la GUI."
    ),
)
def test_el_mapa_de_cobertura_distingue_lo_medido_de_lo_inventado():
    """Relleno contra tablero de ajedrez, y la diferencia es de TEXTURA.

    Se comprueba que una celda cubierta y una no cubierta salen de colores
    distintos, y que las no cubiertas alternan entre dos tonos de superficie
    (eso es el tablero), que es lo que se lee en blanco y negro.
    """
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        res = v.p_reverse.resultado()
        assert res is not None
        cob = res.coverage
        img = montaje_cobertura(cob, cortes=1, columnas=1)
        assert img.width() == cob.size and img.height() == cob.size
        mask = cob.covered_mask()
        n = cob.size
        # El montaje pinta el corte b=0 con el verde hacia arriba.
        corte = mask[:, :, 0].T[::-1]
        cubiertas = [(x, y) for y in range(n) for x in range(n) if corte[y, x]]
        libres = [(x, y) for y in range(n) for x in range(n) if not corte[y, x]]
        assert libres, "no hay ni una celda inventada: el caso no prueba nada"
        tonos_libres = {img.pixel(x, y) for x, y in libres}
        assert len(tonos_libres) == 2, "el tablero de ajedrez no alterna dos tonos"
        assert cubiertas, "no hay ni una celda medida en el corte: el caso no prueba nada"
        for x, y in cubiertas:
            assert img.pixel(x, y) not in tonos_libres, (
                "una celda medida se pinta igual que una inventada"
            )
    finally:
        v.close()


def test_cambiar_la_rejilla_recalcula_contra_ese_tamano():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        for indice, tam in enumerate((17, 33)):
            v.p_reverse.selector_tam.setCurrentIndex(indice)
            v.p_reverse.recalcular()
            asentar(2)
            res = v.p_reverse.resultado()
            assert res is not None
            assert res.lut.size == tam
            assert res.coverage.size == tam
    finally:
        v.close()


# ---------------------------------------------------------------------------
# La ventana que las cose
# ---------------------------------------------------------------------------


def test_elegir_un_clip_en_la_tabla_lo_selecciona_en_comparar():
    est = demo()
    v = ventana(est)
    try:
        v.p_clips.tabla.selectRow(2)
        asentar(2)
        assert v.p_comparar.clip_actual() is not None
        assert v.p_comparar.clip_actual().clip_id == est.clips[2].clip_id
    finally:
        v.close()


def test_el_pie_ensena_el_proyecto_del_puente_y_cuenta_los_clips():
    est = demo()
    v = ventana(est)
    try:
        info = est.puente.project_info()
        detalle = v.detalle_resolve.texto_completo()
        assert info.name in detalle
        assert info.timeline_name in detalle
        assert info.color_science in detalle
        assert v.cifra_clips.text() == f"{len(est.clips):d} clips"  # 7, plural
        assert es_monoespaciada(v.cifra_clips.font())
    finally:
        v.close()


def test_la_ventana_habla_siempre_con_el_resolve_falso():
    """El puente de una ventana es un `FakeResolve`, nunca un `LiveResolve`.

    Lo de «y ademas nadie ha importado `DaVinciResolveScript`» **no se
    comprueba mirando `sys.modules`**: eso es estado de todo el proceso, y en la
    suite entera hay tests de `core/resolve` que lo importan a proposito, asi
    que el resultado dependeria del orden en que pytest recoja los ficheros. La
    regla de import se comprueba donde se puede comprobar de verdad, leyendo el
    codigo de `gui/`, y esta en
    `tests/test_gui_regla_de_oro.py::test_la_gui_no_importa_el_puente_de_verdad`.
    """
    from core.resolve import FakeResolve

    v = ventana(demo())
    try:
        assert isinstance(v._estado.puente, FakeResolve)
        assert type(v._estado.puente).__name__ != "LiveResolve"
    finally:
        v.close()


def test_el_estado_demo_no_apunta_a_ningun_fichero_real():
    """Cero material real: ni un `file_path`, ni una ruta de `/Volumes`."""
    est: EstadoDemo = demo()
    assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
    for clip in est.clips:
        assert clip.ref.file_path is None
