"""`gui.asistente_facil`: los cinco pasos del modo fácil, sin Qt.

Se prueba sobre `EstadoDemo` (el mismo material sintético que usa el modo
avanzado, ver `gui/datos_demo.py`): cero material real, cero invención — cada
paso lee resultados que ya calculó `core.matching`/`core.colormgmt` de verdad.
"""

from __future__ import annotations

from core.contracts import CDL, LUT3D, ClipRef, Confidence, GrupoAmbiguo, MatchResult
from core.resolve import FakeResolve
from core.reverse.confianza_destino import FeaturesDestino
from core.reverse.orden_repaso import CandidatoOrden, ClaseMaterial
from gui.asistente_facil import (
    PasoOrdenar,
    ejecutar_equilibrar,
    ejecutar_igualar,
    ejecutar_look,
    ejecutar_ordenar,
    ejecutar_repasar,
)
from gui.datos_demo import ClipDemo, EstadoDemo, estado_demo, estado_desconectado, estado_vacio

# ---------------------------------------------------------------------------
# Paso 1 — ordenar la casa
# ---------------------------------------------------------------------------


def test_ordenar_sin_metadata_de_camara_agrupa_todo_como_pendiente():
    """`estado_demo()` no pone metadata de cámara en sus `ClipRef` (son de
    demostración): la regla de "no se adivina" tiene que dejarlos todos en
    grupos pendientes, no resueltos con una suposición."""
    estado = estado_demo()
    paso = ejecutar_ordenar(estado)
    assert not paso.clips_resueltos
    total_pendientes = sum(len(g.clip_ids) for g in paso.grupos_pendientes)
    assert total_pendientes == len(estado.clips)
    assert not paso.hecho


def test_ordenar_con_metadata_completa_resuelve_solo():
    estado = estado_demo()
    clips_con_metadata = []
    for i, c in enumerate(estado.clips):
        ref = ClipRef(
            clip_id=c.ref.clip_id, name=c.ref.name, track=1, index=i + 1,
            start_frame=c.ref.start_frame, end_frame=c.ref.end_frame,
            camera_manufacturer="Sony", gamma_notes="S-Log3",
        )
        c.ref = ref
        clips_con_metadata.append(c)
    estado.clips = clips_con_metadata
    paso = ejecutar_ordenar(estado)
    assert len(paso.clips_resueltos) == len(estado.clips)
    assert not paso.grupos_pendientes
    assert "espacio de entrada correcto" in paso.frase


def test_ordenar_estado_vacio_no_lanza():
    paso = ejecutar_ordenar(estado_vacio())
    assert paso.clips_resueltos == ()
    assert paso.grupos_pendientes == ()


def test_ordenar_desconectado_no_lanza_y_no_pide_avisos_de_proyecto():
    """Sin conexión no se puede leer `project_info()`/`list_nodes()`; el paso
    tiene que degradar (sin avisos de doble conversión) en vez de reventar."""
    paso = ejecutar_ordenar(estado_desconectado())
    assert paso.avisos == ()


# ---------------------------------------------------------------------------
# Paso 2 — igualar
# ---------------------------------------------------------------------------


def test_igualar_usa_la_referencia_del_estado():
    estado = estado_demo()
    paso = ejecutar_igualar(estado)
    assert paso.referencia_id == estado.referencia_id
    assert len(paso.igualados) == len(estado.clips) - 1  # todos menos la referencia
    assert paso.referencia_nombre in paso.frase


def test_igualar_sin_clips_no_lanza():
    paso = ejecutar_igualar(estado_vacio())
    assert paso.igualados == ()
    assert "Todavía" in paso.frase


# ---------------------------------------------------------------------------
# Paso 3 — equilibrar
# ---------------------------------------------------------------------------


def test_equilibrar_no_reinventa_el_cdl():
    """Lee EXACTAMENTE el CDL que ya calculó `core.matching.emparejar`
    (a través de `ClipDemo.match`), no recalcula nada por su cuenta."""
    estado = estado_demo()
    clip = estado.clips[0]
    paso = ejecutar_equilibrar(clip)
    assert paso.clip_id == clip.clip_id
    assert isinstance(paso.frase, str) and paso.frase


def test_equilibrar_frase_cambia_segun_el_cdl():
    estado = estado_demo()
    frases = {ejecutar_equilibrar(c).frase for c in estado.clips}
    # con seis clips distintos del generador, no todas las frases son iguales
    assert len(frases) > 1


def test_equilibrar_frase_bien_formada_cuando_solo_corrige_balance():
    """Día 7, tarea 5: leído el paso 3 seguido se ve que con offset ~0 pero
    slope desviado la frase se quedaba en "En «X» corregido el balance de
    color." — sin el "he" conjugado, no es pasado concreto, es un fragmento
    sin verbo. El "he" tiene que estar delante SIEMPRE, salte lo que salte."""
    ref = ClipRef(clip_id="c1", name="Clip Balance", track=1, index=1, start_frame=0, end_frame=119)
    cdl = CDL(slope=(1.05, 0.98, 0.97), offset=(0.0, 0.0, 0.0), power=(1.0, 1.0, 1.0))
    match = MatchResult(
        cdl=cdl, lut=None, confidence=Confidence(score=0.5, level="media"),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=False,
    )
    clip = ClipDemo(ref=ref, match=match)
    paso = ejecutar_equilibrar(clip)
    assert abs(paso.exposicion_ev_aprox) <= 0.05
    assert paso.balance_desviacion > 0.01
    assert paso.frase == "En «Clip Balance» he corregido el balance de color."


# ---------------------------------------------------------------------------
# Paso 4 — look
# ---------------------------------------------------------------------------


def test_look_aplicado_a_todos_los_clips():
    estado = estado_demo()
    paso = ejecutar_look(estado)
    assert paso.look is estado.look
    assert set(paso.aplicado_a) == {c.clip_id for c in estado.clips}
    assert estado.look.title in paso.frase


def test_look_sin_clips_no_lanza():
    estado = estado_vacio()
    paso = ejecutar_look(estado)
    assert paso.aplicado_a == ()


def test_look_con_biblioteca_elige_el_primer_preset_por_defecto(tmp_path):
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.io.cube import escribir_cube

    lut = LUT3D.identity(3)
    escribir_cube(lut, tmp_path / "Mi Preset Real.cube")
    biblioteca = sembrar_desde_carpeta(tmp_path)
    assert biblioteca

    estado = estado_demo()
    paso = ejecutar_look(estado, biblioteca=biblioteca)
    assert paso.preset_elegido is not None
    assert paso.preset_elegido.nombre == "Mi Preset Real"
    assert "Mi Preset Real" in paso.frase
    assert paso.presets_disponibles == biblioteca


def test_look_con_biblioteca_respeta_el_id_elegido(tmp_path):
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.io.cube import escribir_cube

    lut = LUT3D.identity(3)
    escribir_cube(lut, tmp_path / "Look A.cube")
    escribir_cube(lut, tmp_path / "Look B.cube")
    biblioteca = sembrar_desde_carpeta(tmp_path)
    elegido = next(p for p in biblioteca if p.nombre == "Look B")

    estado = estado_demo()
    paso = ejecutar_look(estado, biblioteca=biblioteca, preset_elegido_id=elegido.id)
    assert paso.preset_elegido == elegido
    assert "Look B" in paso.frase


def test_look_con_el_cube_del_preset_borrado_no_lanza(tmp_path):
    """Bloque 3 del día 9 (caminos de error): el `.cube` de un preset puede
    desaparecer entre que se siembra la biblioteca y que el usuario lo elige
    — un disco que se desmonta, alguien que borra el archivo. Antes de este
    test, `ejecutar_look` llamaba a `leer_cube(preset_elegido.ruta_origen)`
    sin capturar `ErrorFormatoCube`: un preset con el fichero borrado tumbaba
    el paso entero con una traza de Python en vez de una frase en castellano.
    """
    from core.io.biblioteca import sembrar_desde_carpeta
    from core.io.cube import escribir_cube

    lut = LUT3D.identity(3)
    ruta = tmp_path / "Look que desaparece.cube"
    escribir_cube(lut, ruta)
    biblioteca = sembrar_desde_carpeta(tmp_path)
    assert biblioteca

    ruta.unlink()  # el disco se desmonta, o alguien lo borra, entre sembrar y elegir

    estado = estado_demo()
    paso = ejecutar_look(estado, biblioteca=biblioteca)
    assert paso.look is None
    assert paso.preset_elegido is not None
    assert "Look que desaparece" in paso.frase
    assert "ya no está disponible" in paso.frase
    # La biblioteca sigue completa: el usuario puede elegir OTRO preset sin
    # que el que ha desaparecido se lleve la lista entera por delante.
    assert paso.presets_disponibles == biblioteca


def test_look_sin_biblioteca_usa_el_look_fijo_del_estado():
    """Sin biblioteca (el camino de siempre, `estado_demo()`), el
    comportamiento no cambia respecto al día 5."""
    estado = estado_demo()
    paso = ejecutar_look(estado)
    assert paso.preset_elegido is None
    assert paso.presets_disponibles == ()
    assert paso.look is estado.look


# ---------------------------------------------------------------------------
# Paso 5 — repasar
# ---------------------------------------------------------------------------


def test_repasar_incluye_el_clip_con_desajuste_de_contenido():
    """`estado_demo()` tiene un clip (el exterior) deliberadamente cruzado
    contra la referencia de estudio: `content_mismatch=True` de verdad."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    con_desajuste = [c for c in estado.clips if c.match.content_mismatch]
    assert con_desajuste  # el caso de uso existe en el estado de demo
    ids_repasar = {c.clip_id for c in paso.candidatos}
    assert all(c.clip_id in ids_repasar for c in con_desajuste)


def test_repasar_incluye_los_grupos_pendientes_del_paso_1():
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    pendientes_ordenar = {cid for g in paso_ordenar.grupos_pendientes for cid in g.clip_ids}
    ids_repasar = {c.clip_id for c in paso.candidatos}
    assert pendientes_ordenar <= ids_repasar


def test_repasar_no_usa_la_palabra_confianza_en_sus_motivos():
    """La regla del encargo: el paso 5 no se apoya en la nota de confianza sin
    calibrar. Comprobación textual barata pero honesta: ningún motivo debe
    mencionar una nota o porcentaje de confianza."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    for c in paso.candidatos:
        assert "confianza" not in c.motivo.lower()
        assert "%" not in c.motivo


def test_repasar_frase_no_promete_mas_de_lo_medido():
    """Día 7, tarea 3: precisión@5 = 0.40 frente a 0.25 de azar (CIFRAS.md
    §18) es una mejora sobre el azar, no una certificación. La frase no
    puede decir "son los peores" ni "tienen problemas" (eso afirmaría que se
    sabe cuáles son malos), sino algo del tipo "estos los miraría yo"."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    assert paso.candidatos  # el caso de demo tiene candidatos de sobra
    frase_min = paso.frase.lower()
    for prohibido in ("los peores", "tienen problemas", "están mal", "son malos"):
        assert prohibido not in frase_min, f"la frase promete de más: {paso.frase!r}"
    assert "miraría" in frase_min


def test_repasar_no_duplica_un_clip_con_dos_motivos():
    """El exterior de `estado_demo()` tiene desajuste de contenido Y (al no
    llevar metadata de cámara) también cae en un grupo pendiente del paso 1:
    tiene que aparecer UNA vez, con los dos motivos, no dos veces."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    ids = [c.clip_id for c in paso.candidatos]
    assert len(ids) == len(set(ids)), "hay un clip_id repetido en la lista de repaso"


def test_repasar_vacio_cuando_no_hay_nada_que_mirar():
    estado = estado_vacio()
    paso_ordenar = ejecutar_ordenar(estado)
    paso = ejecutar_repasar(estado, paso_ordenar)
    assert paso.candidatos == ()
    # NO "todo está medido": sólo se han comprobado dos señales concretas.
    assert "medido" not in paso.frase.lower()
    assert "todo" not in paso.frase.lower()


# ---------------------------------------------------------------------------
# Paso 5 — el ORDEN (día 6): triaje, no certificación.
#
# `ejecutar_repasar` sigue decidiendo QUIÉN entra en la lista exactamente
# igual que el día 5 (los tests de arriba no cambian). Lo que se prueba aquí
# es el ORDEN: por defecto, el "orden simple declarado" (más motivos
# primero); y, cuando se le pasan señales de `core.reverse.orden_repaso`
# (que hoy no existen en `gui.datos_demo`: ver el docstring de
# `ejecutar_repasar`), el orden calibrado por clase de material.
# ---------------------------------------------------------------------------


def _clip_minimo(clip_id: str, *, content_mismatch: bool, metadata_resuelta: bool) -> ClipDemo:
    """Un `ClipDemo` barato (sin imagen ni generador de escenas) para probar
    sólo el ORDEN de `ejecutar_repasar`, sin pagar el coste de `estado_demo()`."""
    ref = ClipRef(
        clip_id=clip_id, name=clip_id, track=1, index=1, start_frame=0, end_frame=119,
        camera_manufacturer="Sony" if metadata_resuelta else None,
        gamma_notes="S-Log3" if metadata_resuelta else None,
    )
    match = MatchResult(
        cdl=CDL(), lut=None, confidence=Confidence(score=0.5, level="media"),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=content_mismatch,
    )
    return ClipDemo(ref=ref, match=match)


def _estado_minimo(clips: list[ClipDemo]) -> EstadoDemo:
    return EstadoDemo(clips=clips, puente=FakeResolve(clips=[c.ref for c in clips]))


def _paso_ordenar_con_grupo(clip_ids_pendientes: tuple[str, ...]) -> PasoOrdenar:
    grupo = GrupoAmbiguo(
        grupo_id="g1", clip_ids=clip_ids_pendientes,
        pregunta="¿de qué cámara son estos clips?", sugerencia_espacio=None,
        frame_muestra_clip_id=None,
    )
    return PasoOrdenar(clips_resueltos=(), grupos_pendientes=(grupo,) if clip_ids_pendientes else (),
                        avisos=(), frase="")


def test_repasar_orden_simple_declarado_pone_primero_al_de_mas_motivos():
    """Sin señal calibrada (el caso de hoy): el orden no es el de aparición,
    es el de NÚMERO DE MOTIVOS, descendente. `a` tiene metadata resuelta (un
    solo motivo: desajuste de contenido) y aparece primero en el timeline;
    `b` no tiene metadata (dos motivos: desajuste Y grupo pendiente) y
    aparece después. El orden de aparición pondría a `a` primero (se detecta
    antes); el orden declarado tiene que poner a `b` primero, porque tiene
    más pegas."""
    a = _clip_minimo("a", content_mismatch=True, metadata_resuelta=True)
    b = _clip_minimo("b", content_mismatch=True, metadata_resuelta=False)
    estado = _estado_minimo([a, b])
    paso_ordenar = _paso_ordenar_con_grupo(("b",))

    paso = ejecutar_repasar(estado, paso_ordenar)

    assert [c.clip_id for c in paso.candidatos] == ["b", "a"]
    assert len(next(c for c in paso.candidatos if c.clip_id == "b").motivo.split("; y ")) == 2
    assert len(next(c for c in paso.candidatos if c.clip_id == "a").motivo.split("; y ")) == 1


def test_repasar_a_igualdad_de_motivos_respeta_el_orden_de_deteccion():
    a = _clip_minimo("a", content_mismatch=True, metadata_resuelta=True)
    b = _clip_minimo("b", content_mismatch=True, metadata_resuelta=True)
    estado = _estado_minimo([a, b])
    paso_ordenar = _paso_ordenar_con_grupo(())

    paso = ejecutar_repasar(estado, paso_ordenar)

    assert [c.clip_id for c in paso.candidatos] == ["a", "b"]


def _candidato(clip_id: str, cobertura: float) -> CandidatoOrden:
    features = FeaturesDestino(
        cobertura_destino=cobertura, muestras_p10_zona=100.0, muestras_mediana_zona=100.0,
        variance_zona=0.0, planos_acumulados=1, n_pixeles_destino=1000,
    )
    return CandidatoOrden(id=clip_id, features=features,
                           clase=ClaseMaterial(tam_rejilla=33, compresion=False, recorte=False))


def test_repasar_usa_el_orden_calibrado_cuando_hay_senales_de_reverse():
    """`a` aparece primero en el timeline pero su cobertura es mucho mejor que
    la de `b`: el orden calibrado tiene que poner a `b` primero (peor), al
    reves del orden de deteccion, cuando se le pasan las senales."""
    a = _clip_minimo("a", content_mismatch=True, metadata_resuelta=True)
    b = _clip_minimo("b", content_mismatch=True, metadata_resuelta=True)
    estado = _estado_minimo([a, b])
    paso_ordenar = _paso_ordenar_con_grupo(())
    candidatos_orden = {"a": _candidato("a", cobertura=0.99), "b": _candidato("b", cobertura=0.10)}

    paso = ejecutar_repasar(estado, paso_ordenar, candidatos_orden=candidatos_orden)

    assert [c.clip_id for c in paso.candidatos] == ["b", "a"]


def test_repasar_clips_sin_senal_calibrada_van_detras_de_los_que_si_la_tienen():
    """`b` no tiene ningun motivo declarado extra (un solo motivo, igual que
    `a`), pero SI tiene senal calibrada; `c` tiene dos motivos pero ninguna
    senal calibrada. La senal medida manda sobre el conteo de motivos: `b`
    va antes que `c`, aunque `c` "parezca" mas urgente por tener mas pegas
    declaradas."""
    a = _clip_minimo("a", content_mismatch=True, metadata_resuelta=True)
    b = _clip_minimo("b", content_mismatch=True, metadata_resuelta=True)
    c = _clip_minimo("c", content_mismatch=True, metadata_resuelta=False)
    estado = _estado_minimo([a, b, c])
    paso_ordenar = _paso_ordenar_con_grupo(("c",))
    candidatos_orden = {"a": _candidato("a", cobertura=0.99), "b": _candidato("b", cobertura=0.10)}

    paso = ejecutar_repasar(estado, paso_ordenar, candidatos_orden=candidatos_orden)

    ids = [c.clip_id for c in paso.candidatos]
    assert ids.index("b") < ids.index("c")  # con dato calibrado, antes que cualquiera sin dato
    assert ids.index("a") < ids.index("c")
    assert ids == ["b", "a", "c"]


def test_repasar_orden_por_defecto_no_cambia_el_caso_de_demostracion():
    """`candidatos_orden=None` (el valor por defecto, y lo que usa hoy toda la
    GUI) tiene que dar exactamente lo mismo que no pasar el parametro: no es
    una migracion silenciosa de comportamiento para quien ya llama a esta
    funcion sin el parametro nuevo."""
    estado = estado_demo()
    paso_ordenar = ejecutar_ordenar(estado)
    con_valor_explicito = ejecutar_repasar(estado, paso_ordenar, candidatos_orden=None)
    con_valor_por_defecto = ejecutar_repasar(estado, paso_ordenar)
    assert con_valor_explicito == con_valor_por_defecto


def test_repasar_orden_calibrado_tampoco_menciona_confianza_ni_numeros():
    """La misma salvaguarda que el resto del paso 5, pero ejercitando el
    camino CALIBRADO (con `candidatos_orden`), no sólo el simple."""
    a = _clip_minimo("a", content_mismatch=True, metadata_resuelta=True)
    b = _clip_minimo("b", content_mismatch=True, metadata_resuelta=True)
    estado = _estado_minimo([a, b])
    paso_ordenar = _paso_ordenar_con_grupo(())
    candidatos_orden = {"a": _candidato("a", cobertura=0.99), "b": _candidato("b", cobertura=0.10)}

    paso = ejecutar_repasar(estado, paso_ordenar, candidatos_orden=candidatos_orden)

    for c in paso.candidatos:
        assert "confianza" not in c.motivo.lower()
        assert "%" not in c.motivo
    assert "confianza" not in paso.frase.lower()
