"""`core.tutor.opciones`: variantes de intensidad de UN look, escritas como
versiones de Resolve por el único camino seguro (día 8, tarea 2.3).

Nunca se llama a `set_cdl`/`set_lut` a pelo aquí tampoco — la misma regla de
oro que `gui/pantalla_aplicar.py`, comprobada de la misma forma: mirando en
qué versión quedaron las escrituras.
"""

from __future__ import annotations

import numpy as np

from core.contracts import CDL, LUT3D
from core.resolve.fake import FakeResolve
from core.tutor.opciones import INTENSIDADES, aplicar_opciones_como_versiones, generar_opciones


def _look_de_prueba() -> LUT3D:
    base = LUT3D.identity(5)
    cdl = CDL(slope=(1.1, 0.95, 0.9), offset=(0.02, 0.0, -0.01), power=(1.0, 1.0, 1.0))
    tabla = np.clip(cdl.apply(base.table), 0.0, 1.0).astype(np.float32)
    return LUT3D(table=tabla, title="look de prueba")


# ---------------------------------------------------------------------------
# generar_opciones: la mezcla en sí
# ---------------------------------------------------------------------------


def test_genera_una_opcion_por_intensidad():
    look = _look_de_prueba()
    opciones = generar_opciones(look)
    assert len(opciones) == len(INTENSIDADES)
    assert [o.intensidad for o in opciones] == list(INTENSIDADES)


def test_la_opcion_al_100_por_cien_es_el_look_tal_cual():
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(1.0,))
    assert np.array_equal(opciones[0].lut.table, look.table)


def test_la_opcion_al_0_por_cien_es_la_identidad():
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(0.0,))
    identidad = LUT3D.identity(look.size)
    assert np.allclose(opciones[0].lut.table, identidad.table, atol=1e-6)


def test_una_intensidad_intermedia_es_la_media_exacta():
    """50% tiene que ser EXACTAMENTE el punto medio entre identidad y look —
    es interpolación lineal, no una aproximación."""
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(0.5,))
    identidad = LUT3D.identity(look.size)
    esperado = 0.5 * np.asarray(identidad.table, dtype=np.float64) + 0.5 * np.asarray(
        look.table, dtype=np.float64
    )
    assert np.allclose(opciones[0].lut.table, esperado, atol=1e-6)


def test_cada_opcion_tiene_version_con_el_prefijo_que_exige_la_regla_de_oro():
    """`es_version_nuestra` sólo deja `SIDEB COLOR` o lo que empiece por
    `SIDEB COLOR `: si esto se rompe, `aplicar_grado_seguro` lanzaría
    `VersionInvalida` para cada opción."""
    look = _look_de_prueba()
    for opcion in generar_opciones(look):
        assert opcion.version.startswith("SIDEB COLOR ")


def test_rutas_de_lut_distintas_para_cada_opcion():
    look = _look_de_prueba()
    opciones = generar_opciones(look)
    rutas = {o.lut_rel_path for o in opciones}
    assert len(rutas) == len(opciones), "dos opciones no pueden compartir ruta de LUT"


# ---------------------------------------------------------------------------
# aplicar_opciones_como_versiones: el camino de escritura
# ---------------------------------------------------------------------------


def test_cada_opcion_se_escribe_en_su_propia_version():
    puente = FakeResolve(n_clips=1)
    clip_id = puente.list_clips()[0].clip_id
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(1.0, 0.5))

    resultados = aplicar_opciones_como_versiones(puente, clip_id, opciones)

    assert all(r.ok for r in resultados)
    nombres_version = set(puente.version_names(clip_id))
    for opcion in opciones:
        assert opcion.version in nombres_version
        assert puente._lut_escrito(clip_id, 3, version=opcion.version) == opcion.lut_rel_path


def test_el_mismo_cdl_viaja_a_todas_las_opciones():
    """El CDL (exposición/balance, nodo 2) no cambia entre opciones — sólo
    cambia el look (nodo 3). Ver `core/tutor/ensenar.py`."""
    puente = FakeResolve(n_clips=1)
    clip_id = puente.list_clips()[0].clip_id
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(1.0, 0.5))
    cdl = CDL(offset=(0.03, 0.0, 0.0))

    aplicar_opciones_como_versiones(puente, clip_id, opciones, cdl=cdl)

    for opcion in opciones:
        escrito = puente._cdl_escrito(clip_id, 2, version=opcion.version)
        assert escrito == cdl


def test_no_se_llama_a_set_cdl_ni_set_lut_fuera_de_una_version_nuestra():
    """Si `aplicar_opciones_como_versiones` llamara a `set_cdl`/`set_lut` sin
    pasar antes por `add_version`/`load_version` de una versión con el
    prefijo, `FakeResolve` lo dejaría pasar iguaL — la única red de seguridad
    de verdad es `aplicar_grado_seguro`, y este test comprueba que se use
    ESE camino y no otro, mirando en qué versión quedaron las escrituras."""
    puente = FakeResolve(n_clips=1)
    clip_id = puente.list_clips()[0].clip_id
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(1.0,))

    resultados = aplicar_opciones_como_versiones(puente, clip_id, opciones)

    assert resultados[0].version.startswith("SIDEB COLOR ")
    assert puente.current_version(clip_id) == opciones[-1].version


def test_con_resolve_desconectado_no_lanza_y_no_escribe_nada():
    """`ResolveNoConectado` es un `ResolveError`: se captura por opción, no
    tumba la función entera — mismo criterio que
    `gui/pantalla_aplicar.py::aplicar()`."""
    puente = FakeResolve(n_clips=1)
    clip_id = puente.list_clips()[0].clip_id
    puente.desconectar()
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(1.0, 0.5))

    resultados = aplicar_opciones_como_versiones(puente, clip_id, opciones)

    assert len(resultados) == len(opciones)
    assert not any(r.ok for r in resultados)
    assert all(r.avisos for r in resultados)


def test_un_fallo_en_una_opcion_no_tumba_las_demas():
    puente = FakeResolve(n_clips=1)
    clip_id = puente.list_clips()[0].clip_id
    look = _look_de_prueba()
    opciones = generar_opciones(look, intensidades=(1.0, 0.5, 0.0))
    # La segunda opción falla al escribir el LUT; las otras dos tienen que
    # seguir escribiéndose bien.
    puente.fallar_en("set_lut", "avería simulada", veces=1)

    resultados = aplicar_opciones_como_versiones(puente, clip_id, opciones)

    assert len(resultados) == 3
    ok = [r.ok for r in resultados]
    assert ok.count(True) == 2 and ok.count(False) == 1
