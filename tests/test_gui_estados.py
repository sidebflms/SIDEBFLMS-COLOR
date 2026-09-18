"""Estados vacios y de error: que se dibujen, y que digan la verdad.

Un caso frontera por fichero, los mismos que hay capturados:

* cero clips, un clip, doscientos clips;
* Resolve «desconectado»;
* una averia simulada de `FakeResolve` (sabe fingirlas) a media escritura;
* un LUT que no pasa el QC;
* un clip sin fotograma en memoria;
* un `ReverseResult` con cobertura casi nula (rejilla de 65³ con un fotograma).

Lo que se comprueba no es «no lanza», sino que la pantalla **dice lo que pasa**:
que el boton se apaga, que el motivo se lee, que un fallo de un clip no tumba
el lote y se cuenta.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from core.contracts import VERSION_NAME  # noqa: E402
from gui import datos_demo as dd  # noqa: E402
from gui.pantalla_aplicar import aplicar, construir_plan  # noqa: E402
from tests.test_gui_apoyo import (  # noqa: E402
    asentar,
    confianza_baja,
    desconectado,
    lut_malo,
    muchos,
    un_clip,
    vacio,
    ventana,
)

pytestmark = pytest.mark.gui


# ---------------------------------------------------------------------------
# Cuantos clips hay
# ---------------------------------------------------------------------------


def test_cero_clips_lo_dice_en_vez_de_quedarse_en_blanco():
    est = vacio()
    v = ventana(est)
    try:
        assert est.clips == []
        assert v.p_clips.vacio.isVisible()
        assert not v.p_clips.division.isVisible()
        assert v.p_clips.modelo.rowCount() == 0
        assert v.p_clips.clip_actual() is None
        assert v.cifra_clips.text() == "0 clips"
        # Y comparar tampoco puede comparar nada, pero lo dice.
        v.ir_a(1)
        asentar(2)
        assert not v.p_comparar.selector.isEnabled()
        assert v.p_comparar.clip_actual() is None
        # Y el plan de aplicar no tiene lineas ni deja aplicar.
        v.ir_a(2)
        asentar(2)
        assert v.p_aplicar.plan_actual().lineas == []
        assert not v.p_aplicar.btn_lote.isEnabled()
    finally:
        v.close()


def test_un_solo_clip_se_ensena_y_se_selecciona():
    est = un_clip()
    v = ventana(est)
    try:
        assert v.p_clips.modelo.rowCount() == 1
        assert v.p_clips.division.isVisible()
        assert not v.p_clips.vacio.isVisible()
        assert v.p_clips.clip_actual().clip_id == est.clips[0].clip_id
        assert v.cifra_clips.text() == "1 clip", "con un solo clip el pie dice «1 clips»"
    finally:
        v.close()


def test_doscientos_clips_entran_en_la_tabla_sin_crear_doscientas_filas():
    """Un modelo de verdad: con 200 clips no hay 1.200 celdas instanciadas."""
    est = muchos()
    v = ventana(est)
    try:
        assert len(est.clips) == 200
        assert v.p_clips.modelo.rowCount() == 200
        assert v.cifra_clips.text() == "200 clips"
        assert v.p_aplicar.lista.count() == 200
        # Y el resumen cuenta bien las tres notas.
        niveles = [c.match.confidence.level for c in est.clips]
        assert sum(1 for n in niveles if n == "alta") + sum(
            1 for n in niveles if n == "media"
        ) + sum(1 for n in niveles if n == "baja") == 200
    finally:
        v.close()


def test_un_clip_sin_fotograma_en_memoria_se_dice_y_no_revienta():
    est = muchos()
    v = ventana(est)
    try:
        v.ir_a(1)
        sin_imagen = next(c for c in est.clips if c.original is None)
        v.p_comparar.seleccionar(sin_imagen.clip_id)
        asentar(2)
        antes, despues = v.p_comparar._imagenes(sin_imagen)
        assert antes is None and despues is None
        assert sin_imagen.despues() is None
        # Los numeros del emparejamiento SI son suyos, aunque no haya imagen.
        assert v.p_comparar._cifras["antes"].text() == (
            f"{sin_imagen.match.delta_e_before:.2f}"
        )
    finally:
        v.close()


def test_confianza_baja_en_todos_se_pinta_con_la_forma_de_baja():
    est = confianza_baja()
    v = ventana(est)
    try:
        from gui import identidad as idn

        niveles = {c.match.confidence.level for c in est.clips}
        assert niveles == {"baja"}, f"el estado de confianza baja trae {niveles}"
        forma = idn.FormaConfianza.de_nivel("baja")
        assert forma.discontinuo is True
        assert forma.relleno is None
        assert forma.escalones == 1
        assert v.p_clips.ficha.insignia.isVisible()
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Resolve caido
# ---------------------------------------------------------------------------


def test_resolve_desconectado_apaga_el_boton_y_explica_por_que():
    est = desconectado()
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        plan = v.p_aplicar.plan_actual()
        assert plan.error_global, "sin conexion el plan tiene que traer el motivo"
        assert "Resolve" in plan.error_global
        assert plan.lineas == []
        assert not v.p_aplicar.btn_lote.isEnabled()
        assert not v.p_aplicar.btn_uno.isEnabled()
        assert "desconectado" in v.p_aplicar.rotulo_banda.texto_completo()
        assert plan.error_global in v.p_aplicar.texto_plan.toPlainText()
        # Y el pie de la ventana lo dice tambien.
        assert "desconectado" in v.estado_resolve.texto_completo()
        assert "no se escribe nada" in v.detalle_resolve.texto_completo()
    finally:
        v.close()


def test_aplicar_con_resolve_caido_no_escribe_nada():
    est = desconectado()
    est.puente._grados_escritos.clear()
    resultados = aplicar(est, [c.clip_id for c in est.clips])
    assert est.puente._grados_escritos == []
    assert resultados, "sin conexion tiene que haber resultados que digan que no se ha podido"
    assert all(not r.ok for r in resultados)


def test_volver_a_conectar_reactiva_el_boton():
    est = desconectado()
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        assert not v.p_aplicar.btn_lote.isEnabled()
        est.puente.conectar()
        v.p_aplicar.refrescar_plan()
        asentar(2)
        assert v.p_aplicar.btn_lote.isEnabled()
        assert "conectado" in v.p_aplicar.rotulo_banda.texto_completo()
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Averias simuladas
# ---------------------------------------------------------------------------


def test_una_averia_en_set_lut_no_tumba_el_lote_y_se_cuenta():
    """`FakeResolve.fallar_en` finge la averia; el lote tiene que seguir."""
    est = dd.estado_demo()
    est.puente.fallar_en("set_lut", "no se encuentra el .cube en la carpeta de LUTs")
    v = ventana(est)
    try:
        v.ir_a(2)
        asentar(2)
        v.p_aplicar._aplicar_lote()
        asentar(2)
        texto = v.p_aplicar.texto_resultado.toPlainText()
        assert "no se encuentra el .cube" in texto
        # Todos los clips se han intentado: el fallo del primero no para el resto.
        assert est.clips, "no hay nada que comprobar: el estado de demostracion no trae clips"
        for clip in est.clips:
            assert clip.clip_id in texto
        assert f"{len(est.clips)}" in texto
    finally:
        v.close()


def test_una_averia_de_una_sola_vez_se_cura_y_el_resto_se_escribe():
    est = dd.estado_demo()
    est.puente.fallar_en("set_cdl", "disco lleno", veces=1)
    resultados = aplicar(est, [c.clip_id for c in est.clips])
    fallidos = [r for r in resultados if not r.ok]
    buenos = [r for r in resultados if r.ok]
    assert len(fallidos) == 1
    assert "disco lleno" in fallidos[0].mensaje
    assert len(buenos) == len(est.clips) - 1
    assert buenos, "no hay nada que comprobar: con un solo clip no queda ninguno que se escriba bien"
    for r in buenos:
        assert r.version == VERSION_NAME


def test_un_clip_que_desaparece_de_la_timeline_no_tumba_el_lote():
    """Bloque 3 del día 9 (caminos de error): la timeline cambia entre que se
    analiza y que se aplica — alguien borra un plano del timeline de Resolve
    después de que esta app ya calculó su CDL. `FakeResolve.set_cdl` levanta
    `ClipNoEncontrado` (subclase de `ResolveError`) para ese clip_id; como
    `aplicar()` sólo captura `ResolveError` por clip, el resto del lote tiene
    que escribirse igual — no es un bug nuevo, es la garantía que ya da
    `aplicar_grado_seguro`, fijada aquí con el escenario concreto que pidió
    Mario."""
    est = dd.estado_demo()
    assert len(est.clips) >= 2, "hacen falta al menos dos clips para ver que el resto sobrevive"
    desaparecido = est.clips[0].clip_id
    del est.puente._clips[desaparecido]  # el plano ya no existe en Resolve

    resultados = aplicar(est, [c.clip_id for c in est.clips])
    por_id = {r.clip_id: r for r in resultados}

    assert not por_id[desaparecido].ok
    assert "no existe el clip" in por_id[desaparecido].mensaje

    resto = [c.clip_id for c in est.clips if c.clip_id != desaparecido]
    assert resto, "no hay nada que comprobar: hacen falta al menos dos clips para ver que el resto sobrevive"
    for clip_id in resto:
        assert por_id[clip_id].ok, (
            f"{clip_id}: el clip desaparecido no debería tumbar al resto del lote"
        )


def test_un_clip_sin_los_tres_nodos_sale_como_no_se_puede():
    """La API de Resolve no sabe crear nodos, asi que esto no lo arregla la app."""
    est = dd.estado_demo()
    flaco = dd._puente(est.clips, nodos=1)
    est.puente = flaco
    plan = construir_plan(est, [c.clip_id for c in est.clips])
    assert plan.aplicables == []
    assert plan.bloqueados
    for linea in plan.bloqueados:
        assert "nodo" in linea.motivo.lower()
        assert not linea.puede


def test_si_el_puente_no_puede_ni_decir_la_version_el_plan_lo_dice():
    est = dd.estado_demo()
    est.puente.fallar_en("current_version", "no se puede leer la version activa")
    plan = construir_plan(est, [est.clips[0].clip_id])
    assert plan.lineas
    assert not plan.lineas[0].puede
    assert "version" in plan.lineas[0].motivo


# ---------------------------------------------------------------------------
# Un LUT que no pasa el QC
# ---------------------------------------------------------------------------


def test_un_look_que_no_pasa_el_qc_se_avisa_antes_de_escribirlo():
    est = lut_malo()
    v = ventana(est)
    try:
        assert est.informe_lut is not None
        assert not est.informe_lut.ok, "el estado de LUT malo trae un LUT que si pasa el QC"
        v.ir_a(2)
        asentar(2)
        texto_look = v.p_aplicar.texto_look.text()
        assert "QC" in texto_look
        assert est.informe_lut.problemas
        assert est.informe_lut.problemas[0].mensaje in texto_look
        assert "Se puede escribir igualmente" in texto_look
        # Y el aviso va en naranja de MARCA, no en rojo.
        from gui import identidad as idn

        assert idn.BRAND_400 in v.p_aplicar.texto_look.styleSheet()
        assert est.informe_lut.resumen() in v.p_aplicar.texto_plan.toPlainText()
    finally:
        v.close()


def test_un_look_que_pasa_el_qc_no_pinta_ningun_aviso():
    est = dd.estado_demo()
    v = ventana(est)
    try:
        assert est.informe_lut is not None and est.informe_lut.ok
        v.ir_a(2)
        asentar(2)
        assert v.p_aplicar.texto_look.styleSheet().count("#") <= 1
        assert "Se puede escribir igualmente" not in v.p_aplicar.texto_look.text()
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Cobertura casi nula
# ---------------------------------------------------------------------------


def test_con_rejilla_de_65_la_cobertura_es_casi_nula_y_se_dice():
    """Un fotograma en un cubo de 65³: el 99,9% del LUT es invento, y se ve."""
    v = ventana(dd.estado_demo())
    try:
        v.ir_a(3)
        asentar(2)
        v.p_reverse.selector_tam.setCurrentIndex(2)  # 65³
        v.p_reverse.recalcular()
        asentar(2)
        res = v.p_reverse.resultado()
        assert res is not None
        assert res.coverage.size == 65
        fraccion = res.coverage.coverage_fraction()
        assert fraccion < 0.01, f"la cobertura de 65³ ha salido {fraccion:.4f}"
        # [dia 4] El porcentaje subio al diagnostico, a tamano de titular y sin
        # espacio antes del `%` (como el de reproducible); el recuento de celdas
        # se queda en la cabecera del mapa, en `celdas_cobertura`.
        assert v.p_reverse.cifra_cobertura.text() == f"{fraccion * 100:.2f}%"
        assert f"{65 ** 3:,}".replace(",", ".") in v.p_reverse.celdas_cobertura.text()
        assert abs(v.p_reverse.barra_repro.valor() - res.diagnosis.lut_reproducible) < 1e-6
    finally:
        v.close()


def test_el_mismo_grado_sin_vineta_cambia_el_diagnostico():
    """Con vineta hay algo que depende de DONDE esta el pixel; sin ella, no."""
    con = dd.par_ingenieria_inversa(con_vineta=True)
    sin = dd.par_ingenieria_inversa(con_vineta=False)
    v_con = ventana(dd.estado_demo(), par=con)
    try:
        v_con.ir_a(3)
        asentar(2)
        r_con = v_con.p_reverse.resultado()
    finally:
        v_con.close()
    v_sin = ventana(dd.estado_demo(), par=sin)
    try:
        v_sin.ir_a(3)
        asentar(2)
        r_sin = v_sin.p_reverse.resultado()
    finally:
        v_sin.close()
    assert r_con is not None and r_sin is not None
    assert r_sin.delta_e_mean < r_con.delta_e_mean, (
        "quitar la vineta tendria que dejar menos residuo, y no lo hace: "
        f"{r_sin.delta_e_mean:.3f} contra {r_con.delta_e_mean:.3f}"
    )
