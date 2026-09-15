"""La secuencia segura: version primero, y el grado de Mario intacto.

Esto es lo que de verdad hay que probar. Un `SetCDL` suelto es una linea; lo
dificil es garantizar que esa linea nunca cae encima del trabajo de alguien.
"""

from __future__ import annotations

import pytest

from core.contracts import (
    CDL,
    NODE_BALANCE,
    NODE_LOOK,
    NODE_NORMALIZACION,
    VERSION_NAME,
    ResolveError,
)
from core.resolve import (
    FakeResolve,
    Incognitas,
    aplicar_grado_seguro,
    asegurar_version,
    resumen_nodos,
    verificar_estructura_nodos,
)
from core.resolve.bridge import NodoInvalido, RutaLUTInvalida, VersionInvalida
from core.resolve.fake import VERSION_INICIAL

LUT_OK = "SIDEB/look.cube"
CDL_PRUEBA = CDL(slope=(1.05, 1.0, 0.95), offset=(0.0, 0.0, 0.01), saturation=1.1)


@pytest.fixture
def fake() -> FakeResolve:
    return FakeResolve(n_clips=2)


# ---------------------------------------------------------------------------
# El orden
# ---------------------------------------------------------------------------


def test_la_version_se_crea_antes_de_escribir_nada(fake):
    aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA, lut_rel_path=LUT_OK)
    llamadas = fake._llamadas
    assert llamadas.index("add_version") < llamadas.index("set_cdl")
    assert llamadas.index("add_version") < llamadas.index("set_lut")


def test_escribe_el_cdl_en_el_2_y_el_lut_en_el_3(fake):
    res = aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA, lut_rel_path=LUT_OK)
    assert res.ok and res.cdl_escrito and res.lut_escrito
    assert res.version == VERSION_NAME
    assert fake._cdl_escrito("clip001", NODE_BALANCE) == CDL_PRUEBA
    assert fake.get_lut("clip001", NODE_LOOK) == LUT_OK
    # Y en ningun otro nodo.
    assert fake._cdl_escrito("clip001", NODE_NORMALIZACION) is None
    assert fake._cdl_escrito("clip001", NODE_LOOK) is None
    assert fake._lut_escrito("clip001", NODE_BALANCE) is None


def test_el_grado_original_queda_intacto_en_su_version(fake):
    """Lo que Mario tenia hecho sigue donde estaba."""
    original = CDL(slope=(0.4, 0.4, 0.4), saturation=0.2)
    fake.set_cdl("clip001", NODE_BALANCE, original)
    fake.set_lut("clip001", NODE_LOOK, "DELCLIENTE/suyo.cube")

    aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA, lut_rel_path=LUT_OK)

    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_INICIAL) == original
    assert fake._lut_escrito("clip001", NODE_LOOK, VERSION_INICIAL) == "DELCLIENTE/suyo.cube"
    fake.load_version("clip001", VERSION_INICIAL)
    assert fake.get_lut("clip001", NODE_LOOK) == "DELCLIENTE/suyo.cube"


def test_pasar_dos_veces_no_crea_dos_versiones(fake):
    aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    aplicar_grado_seguro(fake, "clip001", cdl=CDL(saturation=0.9))
    assert fake.version_names("clip001") == [VERSION_INICIAL, VERSION_NAME]
    assert fake._cdl_escrito("clip001", NODE_BALANCE).saturation == 0.9


def test_sin_cdl_ni_lut_deja_el_clip_preparado_y_no_escribe(fake):
    res = aplicar_grado_seguro(fake, "clip001")
    assert res.ok is False
    assert fake.current_version("clip001") == VERSION_NAME
    assert fake._grados_escritos == []


def test_asegurar_version_es_idempotente(fake):
    assert asegurar_version(fake, "clip001") == VERSION_NAME
    assert asegurar_version(fake, "clip001") == VERSION_NAME
    assert fake.version_names("clip001").count(VERSION_NAME) == 1


def test_asegurar_version_vuelve_a_la_nuestra_si_estaba_en_otra(fake):
    asegurar_version(fake, "clip001")
    fake.load_version("clip001", VERSION_INICIAL)
    assert asegurar_version(fake, "clip001") == VERSION_NAME
    assert fake.current_version("clip001") == VERSION_NAME


# ---------------------------------------------------------------------------
# La pagina de color (F0-5)
# ---------------------------------------------------------------------------


def test_abre_la_pagina_de_color_porque_hoy_asumimos_que_hace_falta(fake):
    aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert fake.pagina_actual == "color"
    assert "open_page" in fake._llamadas


def test_si_manana_no_hiciera_falta_no_se_llama():
    inc = Incognitas(requiere_open_page=False)
    fake = FakeResolve(n_clips=1, incognitas=inc)
    aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA, incognitas=inc)
    assert "open_page" not in fake._llamadas
    assert fake.pagina_actual == "edit"


# ---------------------------------------------------------------------------
# Los tres nodos
# ---------------------------------------------------------------------------


def test_un_clip_con_un_solo_nodo_no_se_toca():
    fake = FakeResolve(n_clips=1, nodos_por_clip=1)
    with pytest.raises(NodoInvalido) as exc:
        aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert "no sabe crear nodos" in str(exc.value).lower()
    assert fake._grados_escritos == []


def test_si_la_version_nueva_empieza_en_blanco_se_para_antes_de_escribir():
    fake = FakeResolve(n_clips=1, version_hereda_grafo=False)
    with pytest.raises(NodoInvalido):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert fake._grados_escritos == []
    # La version se ha creado, pero no se ha escrito nada en ella.
    assert VERSION_NAME in fake.version_names("clip001")


def test_aviso_si_el_nodo_de_normalizacion_esta_apagado(fake):
    fake.set_node_enabled("clip001", NODE_NORMALIZACION, False)
    res = aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert any("desactivado" in a for a in res.avisos)
    assert res.cdl_escrito is True  # avisar no es impedir


def test_aviso_si_hay_mas_de_tres_nodos():
    fake = FakeResolve(n_clips=1, nodos_por_clip=5)
    res = aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert any("5 nodos" in a for a in res.avisos)


def test_aviso_si_nadie_normaliza():
    """Proyecto sin gestion de color y nodo 1 vacio: no normaliza nadie."""
    fake = FakeResolve(n_clips=1, color_science="DaVinci YRGB")
    res = aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert any("normalizando" in a for a in res.avisos)

    gestionado = FakeResolve(n_clips=1)
    assert verificar_estructura_nodos(gestionado, "clip001") == ()


def test_aviso_si_el_cdl_es_la_identidad(fake):
    res = aplicar_grado_seguro(fake, "clip001", cdl=CDL())
    assert any("identidad" in a for a in res.avisos)


# ---------------------------------------------------------------------------
# Caminos de error
# ---------------------------------------------------------------------------


def test_lut_absoluto_se_corta_antes_de_crear_la_version(fake):
    with pytest.raises(RutaLUTInvalida):
        aplicar_grado_seguro(fake, "clip001", lut_rel_path="/Users/mario/luts/look.cube")
    assert fake._llamadas == []  # no se ha llegado ni a preguntar
    assert fake.version_names("clip001") == [VERSION_INICIAL]


def test_si_resolve_dice_que_no_a_la_version_no_se_escribe(fake):
    fake.devolver_false_en("add_version")
    with pytest.raises(VersionInvalida):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    assert fake._grados_escritos == []


def test_si_resolve_dice_que_no_al_cdl_sale_un_resolve_error(fake):
    fake.devolver_false_en("set_cdl")
    with pytest.raises(ResolveError, match="CDL"):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)


def test_si_resolve_dice_que_no_al_lut_el_mensaje_explica_que_mirar(fake):
    fake.devolver_false_en("set_lut")
    with pytest.raises(ResolveError) as exc:
        aplicar_grado_seguro(fake, "clip001", lut_rel_path=LUT_OK)
    assert "RefreshLUTList" in str(exc.value)


def test_una_averia_a_media_escritura_sale_como_resolve_error(fake):
    """La GUI captura solo ResolveError; nada se le puede escapar."""
    fake.fallar_en("set_lut", "se ha cerrado Resolve")
    with pytest.raises(ResolveError):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA, lut_rel_path=LUT_OK)
    # El CDL si llego a escribirse: la escritura no es atomica y hay que saberlo.
    assert fake._cdl_escrito("clip001", NODE_BALANCE) == CDL_PRUEBA


def test_si_el_lut_no_cuaja_de_verdad_se_avisa(fake):
    """Un `SetLUT` que dice True y no hace nada es el fallo mas feo posible.
    Por eso se relee con `GetLUT`."""

    class MentirosoConElLut(FakeResolve):
        def set_lut(self, clip_id, node_index, lut_rel_path):
            self._validar_lut(lut_rel_path)
            return True  # dice que si y no escribe nada

    mentiroso = MentirosoConElLut(n_clips=1)
    res = aplicar_grado_seguro(mentiroso, "clip001", lut_rel_path=LUT_OK)
    assert res.lut_escrito is True
    assert any("GetLUT" in a for a in res.avisos)


def test_clip_que_no_existe(fake):
    with pytest.raises(ResolveError):
        aplicar_grado_seguro(fake, "clipXXX", cdl=CDL_PRUEBA)


def test_timeline_sin_abrir():
    fake = FakeResolve(n_clips=1, timeline_abierto=False)
    with pytest.raises(ResolveError):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)


def test_resolve_cerrado_a_media_faena(fake):
    aplicar_grado_seguro(fake, "clip001", cdl=CDL_PRUEBA)
    fake.desconectar()
    with pytest.raises(ResolveError):
        aplicar_grado_seguro(fake, "clip002", cdl=CDL_PRUEBA)


def test_todos_los_errores_del_puente_son_resolve_error():
    """La GUI hace `except ResolveError`. Si algo no hereda de ahi, se cuela."""
    from core.resolve import bridge as b

    for nombre in (
        "ResolveNoConectado",
        "TimelineNoAbierto",
        "ClipNoEncontrado",
        "GrupoNoEncontrado",
        "NodoInvalido",
        "RutaLUTInvalida",
        "VersionInvalida",
        "OperacionNoDisponible",
    ):
        assert issubclass(getattr(b, nombre), ResolveError), nombre


# ---------------------------------------------------------------------------
# Presentacion
# ---------------------------------------------------------------------------


def test_resumen_de_nodos_legible(fake):
    aplicar_grado_seguro(fake, "clip001", lut_rel_path=LUT_OK)
    fake.set_node_enabled("clip001", 1, False)
    texto = resumen_nodos(fake.list_nodes("clip001"))
    assert "OFF" in texto
    assert LUT_OK in texto
    assert len(texto.splitlines()) == 3
    assert resumen_nodos([]) == "(sin nodos)"
