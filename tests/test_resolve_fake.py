"""`FakeResolve` tiene que mentir bien.

Si el falso es permisivo, esta noche la app parece que funciona y manana, con
Resolve delante, se cae. Asi que aqui se le exige lo mismo que va a exigir la
API real: indices 1-based, rutas de LUT relativas, y nada de leer un CDL.
"""

from __future__ import annotations

import os

import pytest

from core.contracts import (
    CDL,
    NODE_BALANCE,
    NODE_LOOK,
    VERSION_NAME,
    ClipRef,
    ResolveBridge,
    ResolveError,
    StillRef,
)
from core.resolve import FakeResolve, Incognitas, asegurar_version
from core.resolve.bridge import (
    ClipNoEncontrado,
    GrupoNoEncontrado,
    NodoInvalido,
    ResolveNoConectado,
    RutaLUTInvalida,
    TimelineNoAbierto,
    VersionInvalida,
)
from core.resolve.fake import ALBUM_INICIAL, OPERACIONES, VERSION_INICIAL

LUT_OK = "SIDEB/look.cube"


@pytest.fixture
def fake() -> FakeResolve:
    return FakeResolve(n_clips=3)


@pytest.fixture
def listo() -> FakeResolve:
    """Un fake con la version `SIDEB COLOR` ya activa en todos sus clips.

    Desde la revision de la ronda 1 el puente se niega a escribir grado fuera de
    una version de la app, asi que para probar `set_cdl` y compania a pelo hay
    que estar en la nuestra. Es a proposito: ver R-0 en NOTAS.md.
    """
    f = FakeResolve(n_clips=3)
    for clip in f.list_clips():
        asegurar_version(f, clip.clip_id)
    f._llamadas.clear()
    return f


def como_el_usuario(fake: FakeResolve):
    """Contexto para montar 'el grado que Mario ya tenia' en su propia version.

    Es el unico uso legitimo de la via de escape dentro de los tests, y por eso
    se hace por aqui y no poniendo el atributo a mano en veinte sitios.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        fake.PELIGRO_escribir_fuera_de_la_version = True
        try:
            yield fake
        finally:
            fake.PELIGRO_escribir_fuera_de_la_version = False

    return _ctx()


# ---------------------------------------------------------------------------
# El contrato
# ---------------------------------------------------------------------------


def test_cumple_el_protocol(fake):
    assert isinstance(fake, ResolveBridge)


def test_operaciones_cuadran_con_el_protocol():
    """Si el orquestador anade un metodo al Protocol, esta lista se entera."""
    del_protocol = {m for m in dir(ResolveBridge) if not m.startswith("_")}
    assert set(OPERACIONES) == del_protocol


def test_no_existe_get_cdl_en_ningun_sitio(fake):
    """La API real no sabe leer el grado. Si el falso lo ofreciera, alguien
    escribiria codigo que manana no funciona."""
    assert not hasattr(fake, "get_cdl")
    assert "get_cdl" not in dir(ResolveBridge)
    publicos = [m for m in dir(fake) if not m.startswith("_")]
    assert not any("cdl" in m and m.startswith("get") for m in publicos)


def test_los_grados_escritos_solo_se_ven_por_el_atributo_de_tests(fake):
    fake.add_version("clip001", VERSION_NAME)
    fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0)))
    assert len(fake._grados_escritos) == 1
    escrito = fake._grados_escritos[0]
    assert escrito.clip_id == "clip001"
    assert escrito.version == VERSION_NAME
    assert escrito.node_index == NODE_BALANCE
    assert escrito.cdl.slope == (2.0, 2.0, 2.0)


# ---------------------------------------------------------------------------
# Timeline y clips
# ---------------------------------------------------------------------------


def test_timeline_de_n_clips():
    fake = FakeResolve(n_clips=5)
    clips = fake.list_clips()
    assert len(clips) == 5
    assert [c.index for c in clips] == [1, 2, 3, 4, 5]
    assert len({c.clip_id for c in clips}) == 5


def test_timeline_vacio_es_legal_y_devuelve_lista_vacia():
    assert FakeResolve(n_clips=0).list_clips() == []


def test_timeline_sin_abrir():
    fake = FakeResolve(n_clips=2, timeline_abierto=False)
    with pytest.raises(TimelineNoAbierto):
        fake.list_clips()
    assert fake.project_info().timeline_name == ""


def test_sin_conexion_no_se_puede_ni_preguntar(fake):
    fake.desconectar()
    assert fake.is_connected() is False
    with pytest.raises(ResolveNoConectado):
        fake.project_info()
    with pytest.raises(ResolveNoConectado):
        fake.list_clips()
    fake.conectar()
    assert fake.is_connected() is True


def test_clip_que_no_existe(fake):
    with pytest.raises(ClipNoEncontrado) as exc:
        fake.list_nodes("clipXXX")
    assert "clipXXX" in str(exc.value)


def test_clips_a_medida():
    ref = ClipRef(
        clip_id="mio", name="TOMA 7", track=2, index=1, start_frame=0, end_frame=99
    )
    fake = FakeResolve(clips=[ref])
    assert fake.list_clips() == [ref]


def test_paginas(fake):
    assert fake.open_page("color") is True
    assert fake.pagina_actual == "color"
    with pytest.raises(ResolveError):
        fake.open_page("colour")


def test_project_info_lleva_la_carpeta_de_luts(fake):
    info = fake.project_info()
    assert info.is_studio is True
    assert info.lut_dir.endswith("/LUT")


# ---------------------------------------------------------------------------
# Nodos
# ---------------------------------------------------------------------------


def test_los_nodos_son_1_based(fake):
    nodos = fake.list_nodes("clip001")
    assert [n.index for n in nodos] == [1, 2, 3]
    assert all(n.enabled for n in nodos)
    assert all(n.lut_path is None for n in nodos)


@pytest.mark.parametrize("indice", [0, -1, -100])
def test_indice_de_nodo_cero_o_negativo(fake, indice):
    with pytest.raises(NodoInvalido):
        fake.set_cdl("clip001", indice, CDL())
    with pytest.raises(NodoInvalido):
        fake.set_lut("clip001", indice, LUT_OK)
    with pytest.raises(NodoInvalido):
        fake.get_lut("clip001", indice)


def test_indice_de_nodo_por_encima_del_numero_de_nodos(fake):
    with pytest.raises(NodoInvalido) as exc:
        fake.set_cdl("clip001", 4, CDL())
    assert "3 nodos" in str(exc.value)


def test_activar_y_desactivar_un_nodo(listo):
    assert listo.set_node_enabled("clip001", 1, False) is True
    assert listo.list_nodes("clip001")[0].enabled is False


def test_los_nodos_no_traen_etiqueta_porque_la_api_no_deja_ponerla(fake):
    """`GetNodeLabel` existe, pero `SetNodeLabel` no. La app no puede etiquetar."""
    assert all(n.label == "" for n in fake.list_nodes("clip001"))
    con_etiquetas = FakeResolve(n_clips=1, etiquetas=("Normalizacion", "Balance", "Look"))
    assert [n.label for n in con_etiquetas.list_nodes("clip001")] == [
        "Normalizacion",
        "Balance",
        "Look",
    ]


# ---------------------------------------------------------------------------
# Versiones
# ---------------------------------------------------------------------------


def test_version_inicial(fake):
    assert fake.version_names("clip001") == [VERSION_INICIAL]
    assert fake.current_version("clip001") == VERSION_INICIAL


def test_crear_version_la_deja_seleccionada(fake):
    assert fake.add_version("clip001", VERSION_NAME) is True
    assert fake.current_version("clip001") == VERSION_NAME
    assert fake.version_names("clip001") == [VERSION_INICIAL, VERSION_NAME]


def test_version_duplicada_devuelve_false_y_no_toca_nada(fake):
    fake.add_version("clip001", VERSION_NAME)
    fake.set_cdl("clip001", NODE_BALANCE, CDL(saturation=0.5))
    assert fake.add_version("clip001", VERSION_NAME) is False
    assert fake.version_names("clip001") == [VERSION_INICIAL, VERSION_NAME]
    assert fake._cdl_escrito("clip001", NODE_BALANCE).saturation == 0.5


def test_version_con_nombre_vacio(fake):
    for nombre in ("", "   ", "\n"):
        with pytest.raises(VersionInvalida):
            fake.add_version("clip001", nombre)
    assert fake.version_names("clip001") == [VERSION_INICIAL]


def test_cargar_una_version_que_no_existe_devuelve_false(fake):
    assert fake.load_version("clip001", "LA QUE SEA") is False
    assert fake.current_version("clip001") == VERSION_INICIAL


def test_el_grado_va_a_la_version_activa_y_la_otra_no_se_entera(fake):
    with como_el_usuario(fake):
        fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(0.5, 0.5, 0.5)))
    fake.add_version("clip001", VERSION_NAME)
    fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(3.0, 3.0, 3.0)))
    fake.set_lut("clip001", NODE_LOOK, LUT_OK)

    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_NAME).slope == (3.0, 3.0, 3.0)
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_INICIAL).slope == (0.5, 0.5, 0.5)
    assert fake._lut_escrito("clip001", NODE_LOOK, VERSION_INICIAL) is None

    fake.load_version("clip001", VERSION_INICIAL)
    assert fake.get_lut("clip001", NODE_LOOK) is None


def test_version_nueva_puede_no_heredar_el_grafo():
    """La septima incognita: si AddVersion deja el grafo en blanco, la app se
    queda sin nodo 2 y sin nodo 3, y la API NO sabe crear nodos."""
    fake = FakeResolve(n_clips=1, version_hereda_grafo=False)
    fake.add_version("clip001", VERSION_NAME)
    assert len(fake.list_nodes("clip001")) == 1
    with pytest.raises(NodoInvalido):
        fake.set_cdl("clip001", NODE_BALANCE, CDL())


# ---------------------------------------------------------------------------
# Rutas de LUT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta",
    [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/x.cube",
        "~/luts/x.cube",
        "../fuera.cube",
        "SIDEB/../../fuera.cube",
        "",
        "   ",
    ],
)
def test_ruta_de_lut_que_resolve_no_aceptaria(fake, ruta):
    with pytest.raises(RutaLUTInvalida):
        fake.set_lut("clip001", NODE_LOOK, ruta)


def test_ruta_de_lut_relativa_correcta(listo):
    assert listo.set_lut("clip001", NODE_LOOK, "SIDEB/look 01.cube") is True
    assert listo.get_lut("clip001", NODE_LOOK) == "SIDEB/look 01.cube"


def test_el_dctl_no_entra_hoy(fake):
    with pytest.raises(RutaLUTInvalida) as exc:
        fake.set_lut("clip001", NODE_LOOK, "SIDEB/look.dctl")
    assert "F0-3" in str(exc.value)


def test_el_dctl_entraria_si_la_incognita_f0_3_saliera_que_si():
    fake = FakeResolve(n_clips=1, incognitas=Incognitas(setlut_acepta_dctl=True))
    asegurar_version(fake, "clip001")
    assert fake.set_lut("clip001", NODE_LOOK, "SIDEB/look.dctl") is True


def test_extension_desconocida(fake):
    with pytest.raises(RutaLUTInvalida):
        fake.set_lut("clip001", NODE_LOOK, "SIDEB/look.3dl")


# ---------------------------------------------------------------------------
# Copiar y resetear
# ---------------------------------------------------------------------------


def test_copiar_grado_a_varios_clips(listo):
    listo.set_cdl("clip001", NODE_BALANCE, CDL(saturation=0.25))
    listo.set_lut("clip001", NODE_LOOK, LUT_OK)
    assert listo.copy_grades("clip001", ["clip002", "clip003"]) is True
    for cid in ("clip002", "clip003"):
        assert listo.get_lut(cid, NODE_LOOK) == LUT_OK
        assert listo._cdl_escrito(cid, NODE_BALANCE).saturation == 0.25


def test_copiar_grado_a_una_lista_vacia_no_es_un_error_pero_devuelve_false(listo):
    assert listo.copy_grades("clip001", []) is False


def test_copiar_grado_a_un_clip_que_no_existe(listo):
    with pytest.raises(ClipNoEncontrado):
        listo.copy_grades("clip001", ["clip002", "fantasma"])


def test_resetear_deja_el_clip_limpio(listo):
    listo.set_cdl("clip001", NODE_BALANCE, CDL(saturation=0.0))
    listo.set_lut("clip001", NODE_LOOK, LUT_OK)
    listo.set_node_enabled("clip001", 1, False)
    assert listo.reset_all_grades("clip001") is True
    assert listo.get_lut("clip001", NODE_LOOK) is None
    assert listo._cdl_escrito("clip001", NODE_BALANCE) is None
    assert listo.list_nodes("clip001")[0].enabled is True


def test_refrescar_la_lista_de_luts(fake):
    assert fake.lut_list_refrescada is False
    assert fake.refresh_lut_list() is True
    assert fake.lut_list_refrescada is True


# ---------------------------------------------------------------------------
# Grupos de color
# ---------------------------------------------------------------------------


def test_grupos_de_color(fake):
    assert fake.color_groups() == []
    assert fake.add_color_group("SIDEB") is True
    assert fake.color_groups() == ["SIDEB"]
    assert fake.add_color_group("SIDEB") is False
    assert fake.delete_color_group("SIDEB") is True
    assert fake.delete_color_group("SIDEB") is False


def test_grupo_sin_nombre(fake):
    with pytest.raises(ResolveError):
        fake.add_color_group("  ")


def test_el_look_de_un_grupo_es_el_nodo_1_del_post_clip_no_el_3(fake):
    """El grafo post-clip de un grupo empieza con UN nodo. Si el look va por
    grupo, ahi el indice es 1, no NODE_LOOK."""
    fake.add_color_group("SIDEB")
    assert fake.set_group_post_clip_lut("SIDEB", 1, LUT_OK) is True
    assert fake.nodos_post_clip("SIDEB")[0].lut_path == LUT_OK
    with pytest.raises(NodoInvalido):
        fake.set_group_post_clip_lut("SIDEB", NODE_LOOK, LUT_OK)


def test_grupo_que_no_existe(fake):
    with pytest.raises(GrupoNoEncontrado):
        fake.set_group_post_clip_lut("NO EXISTE", 1, LUT_OK)


# ---------------------------------------------------------------------------
# Galeria y stills
# ---------------------------------------------------------------------------


def test_albumes_y_stills(fake):
    assert fake.gallery_albums() == [ALBUM_INICIAL]
    assert fake.create_powergrade_album("SIDEB PG") is True
    assert fake.create_powergrade_album("SIDEB PG") is False
    still = fake.grab_still()
    assert still.album == ALBUM_INICIAL
    assert fake.set_current_still_album("SIDEB PG") is True
    assert fake.grab_still().album == "SIDEB PG"
    assert fake.set_current_still_album("NO EXISTE") is False


def test_grab_still_necesita_timeline():
    fake = FakeResolve(n_clips=1, timeline_abierto=False)
    with pytest.raises(TimelineNoAbierto):
        fake.grab_still()


def test_export_stills_escribe_solo_en_el_directorio_que_le_dan(fake, salida):
    stills = [fake.grab_still(), fake.grab_still()]
    escritos = fake.export_stills(stills, str(salida), "prueba", "png")
    assert len(escritos) == 2
    for ruta in escritos:
        assert os.path.dirname(ruta) == str(salida)
        assert os.path.isfile(ruta)
    assert sorted(os.listdir(salida)) == ["prueba001.png", "prueba002.png"]


def test_export_stills_con_cosas_mal(fake, salida):
    still = fake.grab_still()
    with pytest.raises(ResolveError):
        fake.export_stills([still], str(salida), "prueba", "exr")  # formato inexistente
    with pytest.raises(ResolveError):
        fake.export_stills([still], str(salida / "no_existe"), "prueba", "png")
    with pytest.raises(ResolveError):
        fake.export_stills([still], str(salida), "../fuera", "png")
    with pytest.raises(ResolveError):
        fake.export_stills([still], str(salida), "", "png")
    with pytest.raises(ResolveError):
        fake.export_stills(
            [StillRef(still_id="inventado", album=ALBUM_INICIAL)], str(salida), "p", "png"
        )
    assert fake.export_stills([], str(salida), "prueba", "png") == []
    assert os.listdir(salida) == []


def test_el_drx_hoy_no_exporta_nada(fake, salida):
    """Incognita F0-1: mientras no se verifique, se asume que no funciona."""
    still = fake.grab_still()
    assert fake.export_stills([still], str(salida), "pg", "drx") == []
    assert os.listdir(salida) == []
    assert any("F0-1" in a for a in fake._avisos)


def test_el_drx_exportaria_si_la_incognita_f0_1_saliera_que_si(salida):
    fake = FakeResolve(n_clips=1, incognitas=Incognitas(export_drx_funciona=True))
    still = fake.grab_still()
    escritos = fake.export_stills([still], str(salida), "pg", "drx")
    assert len(escritos) == 1
    assert escritos[0].endswith(".drx")


# ---------------------------------------------------------------------------
# Averias simuladas
# ---------------------------------------------------------------------------


def test_fallar_en_lanza_resolve_error(listo):
    listo.fallar_en("set_lut", "el disco esta lleno")
    with pytest.raises(ResolveError) as exc:
        listo.set_lut("clip001", NODE_LOOK, LUT_OK)
    assert "disco" in str(exc.value)
    listo.dejar_de_fallar("set_lut")
    assert listo.set_lut("clip001", NODE_LOOK, LUT_OK) is True


def test_fallar_solo_unas_veces(listo):
    listo.fallar_en("set_cdl", veces=1)
    with pytest.raises(ResolveError):
        listo.set_cdl("clip001", NODE_BALANCE, CDL())
    assert listo.set_cdl("clip001", NODE_BALANCE, CDL()) is True


def test_devolver_false_sin_excepcion(fake):
    fake.devolver_false_en("add_version")
    assert fake.add_version("clip001", VERSION_NAME) is False
    assert fake.version_names("clip001") == [VERSION_INICIAL]


def test_no_se_puede_fingir_un_false_donde_no_hay_bool(fake):
    with pytest.raises(ValueError, match="no devuelve bool"):
        fake.devolver_false_en("list_clips")


def test_nombre_de_operacion_mal_escrito(fake):
    with pytest.raises(ValueError, match="no es una operacion"):
        fake.fallar_en("set_lut_look")


def test_dejar_de_fallar_del_todo(listo):
    listo.fallar_en("set_lut")
    listo.fallar_en("set_cdl")
    listo.dejar_de_fallar()
    assert listo.set_cdl("clip001", NODE_BALANCE, CDL()) is True
    assert listo.set_lut("clip001", NODE_LOOK, LUT_OK) is True
