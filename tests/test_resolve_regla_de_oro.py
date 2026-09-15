"""La regla de oro ya no es una convencion: es un `if`. Y los indices, enteros.

Esto sale de la revision de la ronda 1 (agente G), hallazgos R-0 y E-1.

R-0 decia, con razon, que «nada destructivo» se cumplia solo si el que llamaba
se acordaba de usar `aplicar_grado_seguro()`. Cualquiera con el puente a mano
podia llamar a `set_cdl` y escribir encima del grado del usuario. Ya no.

E-1 decia que `validar_indice_nodo` se tragaba un float y lo **truncaba**, asi
que pedir el nodo 3 con un 2,9999999999 escribia en el 2 sin avisar. Ya no.
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
    EscrituraFueraDeVersion,
    FakeResolve,
    aplicar_grado_seguro,
    asegurar_version,
    copiar_grado_seguro,
    es_version_nuestra,
    validar_indice_nodo,
)
from core.resolve.bridge import NodoInvalido, VersionInvalida
from core.resolve.fake import VERSION_INICIAL

LUT_OK = "SIDEB/look.cube"
GRADO = CDL(slope=(2.0, 2.0, 2.0))


# ---------------------------------------------------------------------------
# R-0: las cinco puertas por las que se podia escribir encima del usuario
# ---------------------------------------------------------------------------


def test_set_cdl_se_niega_a_escribir_en_la_version_del_usuario():
    fake = FakeResolve(n_clips=1)
    assert fake.current_version("clip001") == VERSION_INICIAL
    with pytest.raises(EscrituraFueraDeVersion):
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert fake._grados_escritos == []
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_INICIAL) is None


def test_set_lut_se_niega_a_escribir_en_la_version_del_usuario():
    fake = FakeResolve(n_clips=1)
    with pytest.raises(EscrituraFueraDeVersion):
        fake.set_lut("clip001", NODE_LOOK, LUT_OK)
    assert fake._lut_escrito("clip001", NODE_LOOK, VERSION_INICIAL) is None


def test_set_node_enabled_se_niega_a_tocar_la_version_del_usuario():
    """Apagar un nodo cambia la imagen: es escribir, aunque no lleve numeros."""
    fake = FakeResolve(n_clips=1)
    with pytest.raises(EscrituraFueraDeVersion):
        fake.set_node_enabled("clip001", NODE_NORMALIZACION, False)
    assert fake.list_nodes("clip001")[0].enabled is True


def test_reset_all_grades_se_niega_a_tocar_la_version_del_usuario():
    fake = FakeResolve(n_clips=1)
    fake.PELIGRO_escribir_fuera_de_la_version = True
    fake.set_lut("clip001", NODE_LOOK, "DEL_USUARIO/suyo.cube")
    fake.PELIGRO_escribir_fuera_de_la_version = False

    with pytest.raises(EscrituraFueraDeVersion):
        fake.reset_all_grades("clip001")
    assert fake._lut_escrito("clip001", NODE_LOOK, VERSION_INICIAL) == "DEL_USUARIO/suyo.cube"


def test_copy_grades_no_pisa_el_grado_del_destino():
    """Era la peor de las cinco: `CopyGrades` reemplaza el arbol entero."""
    fake = FakeResolve(n_clips=2)
    fake.PELIGRO_escribir_fuera_de_la_version = True
    fake.set_lut("clip002", NODE_LOOK, "DEL_USUARIO/suyo.cube")
    fake.PELIGRO_escribir_fuera_de_la_version = False
    asegurar_version(fake, "clip001")
    fake.set_cdl("clip001", NODE_BALANCE, GRADO)

    with pytest.raises(EscrituraFueraDeVersion):
        fake.copy_grades("clip001", ["clip002"])
    assert fake._lut_escrito("clip002", NODE_LOOK, VERSION_INICIAL) == "DEL_USUARIO/suyo.cube"


def test_copy_grades_comprueba_TODOS_los_destinos_antes_de_copiar_a_ninguno():
    """Si el tercero esta en la version del usuario, no se copia ni al primero."""
    fake = FakeResolve(n_clips=4)
    for cid in ("clip001", "clip002", "clip003"):
        asegurar_version(fake, cid)
    # clip004 se queda en la del usuario.
    fake.set_cdl("clip001", NODE_BALANCE, GRADO)

    with pytest.raises(EscrituraFueraDeVersion, match="clip004"):
        fake.copy_grades("clip001", ["clip002", "clip003", "clip004"])
    assert fake._cdl_escrito("clip002", NODE_BALANCE) is None
    assert fake._cdl_escrito("clip003", NODE_BALANCE) is None


def test_el_mensaje_de_error_dice_que_hacer():
    """Lo va a leer el agente H, que no ha leido mis NOTAS. Que se entienda."""
    fake = FakeResolve(n_clips=1)
    with pytest.raises(EscrituraFueraDeVersion) as exc:
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    mensaje = str(exc.value)
    assert "aplicar_grado_seguro" in mensaje
    assert VERSION_NAME in mensaje
    assert "PELIGRO_escribir_fuera_de_la_version" in mensaje


def test_la_gui_solo_tiene_que_capturar_resolve_error():
    assert issubclass(EscrituraFueraDeVersion, ResolveError)


# ---------------------------------------------------------------------------
# R-0: y por el camino bueno, todo sigue funcionando
# ---------------------------------------------------------------------------


def test_por_el_camino_bueno_no_se_entera_nadie():
    fake = FakeResolve(n_clips=1)
    res = aplicar_grado_seguro(fake, "clip001", cdl=GRADO, lut_rel_path=LUT_OK)
    assert res.ok
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_NAME) == GRADO
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_INICIAL) is None


def test_despues_de_asegurar_version_se_puede_escribir_a_pelo():
    """El puente no obliga a usar `aplicar_grado_seguro`; obliga a estar en la
    version buena. Quien quiera escribir a mano, que cree la version."""
    fake = FakeResolve(n_clips=1)
    asegurar_version(fake, "clip001")
    assert fake.set_cdl("clip001", NODE_BALANCE, GRADO) is True
    assert fake.set_lut("clip001", NODE_LOOK, LUT_OK) is True


def test_volver_a_la_version_del_usuario_vuelve_a_cerrar_la_puerta():
    fake = FakeResolve(n_clips=1)
    asegurar_version(fake, "clip001")
    assert fake.set_cdl("clip001", NODE_BALANCE, GRADO) is True
    fake.load_version("clip001", VERSION_INICIAL)
    with pytest.raises(EscrituraFueraDeVersion):
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)


# ---------------------------------------------------------------------------
# R-0: que cuenta como "version nuestra"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "es_nuestra"),
    [
        (VERSION_NAME, True),
        ("SIDEB COLOR PROBE", True),  # la que crea el probe
        ("SIDEB COLOR 2", True),
        ("Version 1", False),
        ("Cliente", False),
        ("sideb color", False),  # las mayusculas importan
        ("SIDEB COLORADO", False),  # no vale con que empiece por las letras
        ("", False),
    ],
)
def test_que_version_es_nuestra(nombre, es_nuestra):
    assert es_version_nuestra(nombre) is es_nuestra


def test_aplicar_grado_seguro_no_escribe_en_una_version_ajena():
    """Ni aunque se la pidan por su nombre."""
    fake = FakeResolve(n_clips=1)
    with pytest.raises(VersionInvalida, match="solo escribe en versiones suyas"):
        aplicar_grado_seguro(fake, "clip001", cdl=GRADO, version="Cliente")
    assert fake.version_names("clip001") == [VERSION_INICIAL]


def test_la_version_del_probe_vale_para_escribir():
    fake = FakeResolve(n_clips=1)
    res = aplicar_grado_seguro(fake, "clip001", cdl=GRADO, version="SIDEB COLOR PROBE")
    assert res.version == "SIDEB COLOR PROBE"


# ---------------------------------------------------------------------------
# R-0: la via de escape
# ---------------------------------------------------------------------------


def test_la_via_de_escape_existe_y_se_llama_feo():
    """Tiene que cantar en una revision y encontrarse con grep. Si alguien la
    renombra a algo mono, este test se entera."""
    assert hasattr(FakeResolve, "PELIGRO_escribir_fuera_de_la_version")
    assert FakeResolve.PELIGRO_escribir_fuera_de_la_version is False
    assert "PELIGRO" in "PELIGRO_escribir_fuera_de_la_version"


def test_la_via_de_escape_se_puede_pedir_al_construir():
    fake = FakeResolve(n_clips=1, PELIGRO_escribir_fuera_de_la_version=True)
    assert fake.set_cdl("clip001", NODE_BALANCE, GRADO) is True
    assert fake.current_version("clip001") == VERSION_INICIAL


def test_la_via_de_escape_no_es_un_metodo_publico():
    """Si fuera un metodo, se podria llamar de pasada desde cualquier sitio.
    Siendo un atributo, queda escrito en la linea donde se pone."""
    assert not callable(FakeResolve.PELIGRO_escribir_fuera_de_la_version)


def test_cada_puente_tiene_su_propia_via_de_escape():
    """Abrirla en uno no la abre en los demas."""
    abierto = FakeResolve(n_clips=1, PELIGRO_escribir_fuera_de_la_version=True)
    cerrado = FakeResolve(n_clips=1)
    assert abierto.set_cdl("clip001", NODE_BALANCE, GRADO) is True
    with pytest.raises(EscrituraFueraDeVersion):
        cerrado.set_cdl("clip001", NODE_BALANCE, GRADO)


# ---------------------------------------------------------------------------
# R-0: copiar grado sin destrozar nada
# ---------------------------------------------------------------------------


def test_copiar_grado_seguro_le_crea_la_version_a_cada_destino():
    fake = FakeResolve(n_clips=3)
    aplicar_grado_seguro(fake, "clip001", cdl=GRADO, lut_rel_path=LUT_OK)
    fake.PELIGRO_escribir_fuera_de_la_version = True
    fake.set_lut("clip002", NODE_LOOK, "DEL_USUARIO/suyo.cube")
    fake.PELIGRO_escribir_fuera_de_la_version = False

    res = copiar_grado_seguro(fake, "clip001", ["clip002", "clip003"])
    assert res.ok
    for cid in ("clip002", "clip003"):
        assert fake.current_version(cid) == VERSION_NAME
        assert fake.get_lut(cid, NODE_LOOK) == LUT_OK
    # Y lo que tenia el usuario en clip002 sigue en su version, intacto.
    assert fake._lut_escrito("clip002", NODE_LOOK, VERSION_INICIAL) == "DEL_USUARIO/suyo.cube"


def test_copiar_grado_seguro_sin_destinos_no_hace_nada():
    fake = FakeResolve(n_clips=2)
    res = copiar_grado_seguro(fake, "clip001", [])
    assert res.ok is False
    assert any("ningun clip de destino" in a for a in res.avisos)
    assert fake.version_names("clip002") == [VERSION_INICIAL]


def test_copiar_grado_seguro_avisa_si_el_origen_es_del_usuario():
    """Copiar DESDE la version del usuario es legitimo (no la modifica), pero
    conviene decirlo: se esta repartiendo el grado de Mario, no el de la app."""
    fake = FakeResolve(n_clips=2)
    res = copiar_grado_seguro(fake, "clip001", ["clip002"])
    assert any("no es de la app" in a for a in res.avisos)


def test_copiar_grado_seguro_a_un_clip_que_no_existe():
    fake = FakeResolve(n_clips=2)
    with pytest.raises(ResolveError):
        copiar_grado_seguro(fake, "clip001", ["fantasma"])


# ---------------------------------------------------------------------------
# E-1: los indices de nodo son enteros, y no se trunca nada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("indice", [3.0 - 1e-10, 2.9999999999, 2.5, 3.0, 1.0])
def test_un_indice_decimal_se_rechaza_en_vez_de_truncarse(indice):
    """`int(2.9999999999)` es 2. Quien pidiera el nodo 3 acabaria en el 2 y
    nadie se enteraria. Se rechaza: que redondee quien sepa lo que quiere."""
    with pytest.raises(NodoInvalido):
        validar_indice_nodo(indice, 3)


@pytest.mark.parametrize("indice", ["2", "hola", None, 2.5j, b"2", [2]])
def test_un_indice_que_no_es_un_entero_se_rechaza(indice):
    with pytest.raises(NodoInvalido):
        validar_indice_nodo(indice, 3)


def test_un_booleano_no_es_un_indice_de_nodo():
    """`True` es un `int` para Python y vale 1. Aqui no: es un bug de tipos."""
    with pytest.raises(NodoInvalido):
        validar_indice_nodo(True, 3)
    with pytest.raises(NodoInvalido):
        validar_indice_nodo(False, 3)


def test_el_mensaje_del_indice_explica_por_que_no_se_convierte():
    with pytest.raises(NodoInvalido) as exc:
        validar_indice_nodo(2.9999999999, 3)
    assert "round()" in str(exc.value)


def test_un_indice_decimal_no_llega_a_escribir_nada():
    """La consecuencia, hasta el final: el CDL no acaba en el nodo equivocado."""
    fake = FakeResolve(n_clips=1)
    asegurar_version(fake, "clip001")
    with pytest.raises(NodoInvalido):
        fake.set_cdl("clip001", 3.0 - 1e-10, GRADO)
    assert fake._cdl_escrito("clip001", 2) is None
    assert fake._cdl_escrito("clip001", 3) is None
    assert fake._grados_escritos == []


def test_los_enteros_de_toda_la_vida_siguen_valiendo():
    assert validar_indice_nodo(1, 3) == 1
    assert validar_indice_nodo(3, 3) == 3
    assert validar_indice_nodo(3) == 3  # sin limite superior
