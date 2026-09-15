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
    VersionIndeterminada,
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


# ---------------------------------------------------------------------------
# E-3: los dos puentes tienen que protegerse IGUAL
# ---------------------------------------------------------------------------


def _clase_del_ast(ruta: str, nombre: str):
    """Busca una clase leyendo el fichero. NO lo importa.

    `live.py` no se importa ni se instancia en ningun test: es el unico archivo
    que habla con Resolve y esta sin estrenar. Pero su `__init__` SI hay que
    vigilarlo, porque ahi estuvo el hallazgo E-3. Leer el AST da la misma
    respuesta sin ejecutar una sola linea suya.
    """
    import ast
    from pathlib import Path

    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.ClassDef) and n.name == nombre:
            return n
    raise AssertionError(f"no encuentro la clase {nombre} en {ruta}")


def _atributos_de_clase(cd) -> list[str]:
    import ast

    out: list[str] = []
    for n in cd.body:
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.append(n.target.id)
        elif isinstance(n, ast.Assign):
            out += [t.id for t in n.targets if isinstance(t, ast.Name)]
    return [a for a in out if not a.startswith("__")]


def _asignados_en_init(cd) -> set[str]:
    import ast

    for n in cd.body:
        if isinstance(n, ast.FunctionDef) and n.name == "__init__":
            return {
                t.attr
                for x in ast.walk(n)
                if isinstance(x, ast.Assign)
                for t in x.targets
                if isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"
            }
    return set()


RAIZ = __file__.rsplit("/tests/", 1)[0]


def test_los_dos_puentes_fijan_los_MISMOS_atributos_en_la_instancia():
    """Hallazgo E-3, y la red para el siguiente de su especie.

    `PELIGRO_escribir_fuera_de_la_version` es atributo de clase. `FakeResolve`
    lo reasignaba en la instancia y `LiveResolve` no, asi que envenenar la clase
    base (`BaseResolveBridge.PELIGRO_... = True` en cualquier sitio) apagaba la
    regla de oro EN EL PUENTE DE VERDAD y la dejaba puesta en el falso. Ningun
    test contra `FakeResolve` puede cazar eso: todo verde de noche y cero
    proteccion el dia que se conecte.

    Este test compara los dos `__init__` para que no vuelva a pasar con el
    proximo atributo que se anada.
    """
    base = _atributos_de_clase(_clase_del_ast(f"{RAIZ}/core/resolve/bridge.py", "BaseResolveBridge"))
    fake = _asignados_en_init(_clase_del_ast(f"{RAIZ}/core/resolve/fake.py", "FakeResolve"))
    live = _asignados_en_init(_clase_del_ast(f"{RAIZ}/core/resolve/live.py", "LiveResolve"))

    assert base, "BaseResolveBridge deberia declarar algun atributo de clase"
    asimetricos = [a for a in base if (a in fake) != (a in live)]
    assert asimetricos == [], (
        f"estos atributos los fija un puente y el otro no: {asimetricos}. "
        f"El que no lo fija se queda con el valor de la clase base, y envenenar la clase base "
        f"lo apaga solo a el. Fijalo en los dos __init__."
    )
    faltan = [a for a in base if a not in fake or a not in live]
    assert faltan == [], f"ningun puente fija {faltan} en la instancia"


def test_envenenar_la_clase_base_no_apaga_la_regla_en_el_falso():
    """La mitad que si se puede comprobar ejecutando."""
    from core.resolve.bridge import BaseResolveBridge

    original = BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version
    try:
        BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True
        fake = FakeResolve(n_clips=1)
        assert fake.PELIGRO_escribir_fuera_de_la_version is False
        with pytest.raises(EscrituraFueraDeVersion):
            fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    finally:
        BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = original


def test_live_resolve_acepta_la_via_de_escape_por_el_constructor():
    """Leido del AST: `LiveResolve.__init__` tiene el parametro y lo asigna."""
    cd = _clase_del_ast(f"{RAIZ}/core/resolve/live.py", "LiveResolve")
    import ast

    init = next(n for n in cd.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    nombres = [a.arg for a in init.args.args]
    assert "PELIGRO_escribir_fuera_de_la_version" in nombres
    assert "PELIGRO_escribir_fuera_de_la_version" in _asignados_en_init(cd)


# ---------------------------------------------------------------------------
# E-3 (segunda parte): cuando NO se sabe en que version estamos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("respuesta", ["", "   ", None, 0, {}, [], 7])
def test_si_no_se_sabe_la_version_no_se_escribe(respuesta):
    """Bloquea, no avisa. El razonamiento esta en NOTAS.md 2.5.

    Las dos salidas no cuestan lo mismo: bloquear de mas cuesta una mañana y no
    rompe nada; escribir de mas cuesta el trabajo de alguien y no hay deshacer.
    """
    fake = FakeResolve(n_clips=1)
    with pytest.raises(VersionIndeterminada):
        fake._exigir_version_propia("clip001", respuesta, "set_cdl")


def test_el_mensaje_de_version_indeterminada_culpa_a_la_api_no_al_usuario():
    fake = FakeResolve(n_clips=1)
    with pytest.raises(VersionIndeterminada) as exc:
        fake._exigir_version_propia("clip001", "", "set_cdl")
    mensaje = str(exc.value)
    assert "GetCurrentVersion" in mensaje
    assert "V-0" in mensaje  # la pregunta del probe que lo diagnostica
    assert "api_probe" in mensaje
    assert "PELIGRO_escribir_fuera_de_la_version" in mensaje


def test_version_indeterminada_es_un_caso_de_escritura_fuera_de_version():
    """Quien ya capturaba `EscrituraFueraDeVersion` sigue capturando esta, y la
    GUI, que solo captura `ResolveError`, tambien."""
    assert issubclass(VersionIndeterminada, EscrituraFueraDeVersion)
    assert issubclass(VersionIndeterminada, ResolveError)


def test_los_dos_casos_se_distinguen():
    """Saber que estas en la version del usuario y no saber donde estas son dos
    cosas distintas, y el que lea el error tiene que poder notarlo."""
    fake = FakeResolve(n_clips=1)
    with pytest.raises(EscrituraFueraDeVersion) as sabido:
        fake._exigir_version_propia("clip001", "Version 1", "set_cdl")
    assert not isinstance(sabido.value, VersionIndeterminada)
    assert "Version 1" in str(sabido.value)

    with pytest.raises(VersionIndeterminada) as ignorado:
        fake._exigir_version_propia("clip001", "", "set_cdl")
    assert "no he podido saber" in str(ignorado.value)


def test_un_puente_que_no_sabe_la_version_no_escribe_nada():
    """Reproduce la forma de `LiveResolve` (que pregunta con `current_version()`)
    sin importar `live.py` ni tocar Resolve."""
    from core.resolve.bridge import BaseResolveBridge

    class PuenteMudo(BaseResolveBridge):
        """Resolve que no sabe decir en que version esta. Es el caso que nos da
        miedo: `GetCurrentVersion()` contestando cualquier cosa."""

        def __init__(self, respuesta):
            self.respuesta = respuesta
            self.escrituras = []

        def current_version(self, clip_id):
            return self.respuesta

        def set_cdl(self, clip_id, node_index, cdl):
            self._exigir_version_propia(clip_id, self.current_version(clip_id), "set_cdl")
            self.escrituras.append((clip_id, node_index))
            return True

    mudo = PuenteMudo("")
    with pytest.raises(VersionIndeterminada):
        mudo.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert mudo.escrituras == []

    # Y con la via de escape, escribe: el que decide es quien la abre.
    mudo.PELIGRO_escribir_fuera_de_la_version = True
    assert mudo.set_cdl("clip001", NODE_BALANCE, GRADO) is True
    assert mudo.escrituras == [("clip001", NODE_BALANCE)]


# ---------------------------------------------------------------------------
# B: las CUATRO respuestas raras de GetCurrentVersion()
# ---------------------------------------------------------------------------
#
# Esto es el riesgo que nos creamos al cerrar R-0: la regla de oro llama a
# `GetCurrentVersion()` antes de CADA escritura y nadie ha visto esa llamada
# contestar contra Resolve de verdad. Si se porta raro, la app no escribe en
# ningun sitio, y eso la deja inservible hasta que alguien lo mire.
#
# Aqui se prueba lo unico que se puede probar sin Resolve: que las cuatro formas
# plausibles de portarse mal acaban en "no puedo garantizar la version de
# seguridad, no escribo", y que NI UNA acaba en una escritura.


#: Las cuatro, cada una con la linea que la monta en `FakeResolve`. El mecanismo
#: es el de siempre (`devolver_en` / `fallar_en`), no uno inventado para esto.
RESPUESTAS_RARAS = {
    "cadena vacia": lambda f: f.devolver_en("current_version", ""),
    "solo espacios": lambda f: f.devolver_en("current_version", "   "),
    "None": lambda f: f.devolver_en("current_version", None),
    "dict sin las claves": lambda f: f.devolver_en(
        "current_version", {"version": 2, "tipo": "local"}
    ),
    "dict vacio": lambda f: f.devolver_en("current_version", {}),
    "dict con versionName vacio": lambda f: f.devolver_en(
        "current_version", {"versionName": ""}
    ),
    "un numero": lambda f: f.devolver_en("current_version", 7),
    "lanza": lambda f: f.fallar_en("current_version", "GetCurrentVersion se ha caido"),
}

#: Las cinco escrituras de grado, cada una lanzada a pelo sobre el puente.
ESCRITURAS = {
    "set_cdl": lambda f: f.set_cdl("clip001", NODE_BALANCE, GRADO),
    "set_lut": lambda f: f.set_lut("clip001", NODE_LOOK, LUT_OK),
    "set_node_enabled": lambda f: f.set_node_enabled("clip001", NODE_NORMALIZACION, False),
    "copy_grades": lambda f: f.copy_grades("clip001", ["clip002"]),
    "reset_all_grades": lambda f: f.reset_all_grades("clip001"),
}


def _fake_ya_en_nuestra_version() -> FakeResolve:
    """Un falso con la version `SIDEB COLOR` ya activa en los dos clips.

    El punto de partida tiene que ser el caso BUENO: si se partiera de la
    version del usuario, bloquear seria lo esperado y el test no probaria nada.
    Aqui todo esta bien y lo unico que falla es la respuesta de la API.
    """
    fake = FakeResolve(n_clips=2)
    for clip in ("clip001", "clip002"):
        asegurar_version(fake, clip)
    assert fake.current_version("clip001") == VERSION_NAME
    fake._grados_escritos.clear()
    return fake


@pytest.mark.parametrize("rara", sorted(RESPUESTAS_RARAS))
@pytest.mark.parametrize("operacion", sorted(ESCRITURAS))
def test_si_GetCurrentVersion_se_porta_raro_no_se_escribe_NADA(rara, operacion):
    """Las cuatro respuestas raras x las cinco escrituras. Ninguna escribe.

    Y se comprueba que no escribe de verdad, no solo que lanza: se mira
    `_grados_escritos` (los CDL que han entrado) y el LUT del nodo 3.
    """
    fake = _fake_ya_en_nuestra_version()
    RESPUESTAS_RARAS[rara](fake)

    with pytest.raises(VersionIndeterminada):
        ESCRITURAS[operacion](fake)

    assert fake._grados_escritos == []
    for clip in ("clip001", "clip002"):
        assert fake._lut_escrito(clip, NODE_LOOK, VERSION_NAME) is None


@pytest.mark.parametrize("rara", sorted(RESPUESTAS_RARAS))
def test_el_camino_bueno_tambien_se_para(rara):
    """`aplicar_grado_seguro` no tiene una puerta de atras: se para igual."""
    fake = _fake_ya_en_nuestra_version()
    RESPUESTAS_RARAS[rara](fake)
    with pytest.raises(ResolveError):  # VersionIndeterminada, o el fallo al asegurar
        aplicar_grado_seguro(fake, "clip001", cdl=GRADO, lut_rel_path=LUT_OK)
    assert fake._grados_escritos == []


@pytest.mark.parametrize("rara", sorted(RESPUESTAS_RARAS))
def test_copiar_a_varios_clips_no_copia_a_ninguno(rara):
    """El caso peor: `CopyGrades` reemplaza el arbol de nodos ENTERO del
    destino. Si no se sabe donde esta ninguno, no se copia a ninguno."""
    fake = _fake_ya_en_nuestra_version()
    RESPUESTAS_RARAS[rara](fake)
    with pytest.raises(ResolveError):
        copiar_grado_seguro(fake, "clip001", ["clip002"])
    assert fake._grados_escritos == []


def test_un_diccionario_CON_el_nombre_si_se_entiende_y_se_escribe():
    """Contrapeso obligatorio: bloquear siempre seria facil y seria inutil.

    Si manana resulta que `GetCurrentVersion()` devuelve un diccionario con
    `versionName` —que es la forma en que la API contesta en otros sitios—, la
    app tiene que FUNCIONAR, no bloquear. Lo que bloquea es no encontrar el
    nombre, no que venga envuelto.
    """
    fake = _fake_ya_en_nuestra_version()
    fake.devolver_en("current_version", {"versionName": VERSION_NAME, "versionType": 0})
    assert fake.set_cdl("clip001", NODE_BALANCE, GRADO) is True
    assert len(fake._grados_escritos) == 1


def test_un_diccionario_con_el_nombre_del_USUARIO_bloquea_como_debe():
    """Y el otro contrapeso: entender el diccionario no puede ablandar la regla.

    Si el diccionario dice que estamos en `Version 1`, eso es saber que estamos
    en la version del usuario, no es no saber nada: tiene que salir
    `EscrituraFueraDeVersion` y NO `VersionIndeterminada`, porque el mensaje y
    la salida son distintos.
    """
    fake = _fake_ya_en_nuestra_version()
    fake.devolver_en("current_version", {"versionName": VERSION_INICIAL})
    with pytest.raises(EscrituraFueraDeVersion) as exc:
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert not isinstance(exc.value, VersionIndeterminada)
    assert VERSION_INICIAL in str(exc.value)


@pytest.mark.parametrize("rara", sorted(RESPUESTAS_RARAS))
def test_el_mensaje_dice_QUE_devolvio_la_api_y_QUE_ejecutar(rara):
    """El mensaje lo va a leer Mario con Resolve abierto y sin saber por que.

    Tiene que hacer tres cosas: decir que contesto la API en crudo, decir que el
    sospechoso es la API y no el, y decir el comando exacto que lo diagnostica.
    """
    fake = _fake_ya_en_nuestra_version()
    RESPUESTAS_RARAS[rara](fake)
    with pytest.raises(VersionIndeterminada) as exc:
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    mensaje = str(exc.value)

    assert "GetCurrentVersion()" in mensaje  # que llamada es
    assert "NO ES CULPA TUYA" in mensaje  # de quien es la culpa
    assert "probe/api_probe.py" in mensaje  # que ejecutar
    assert "V-0" in mensaje  # que mirar dentro del informe
    assert "PELIGRO_escribir_fuera_de_la_version" in mensaje  # como salir del paso
    assert "no tiene deshacer" in mensaje  # por que no se arriesga


def test_el_mensaje_distingue_devolver_de_reventar():
    """Un `None` y una excepcion son dos averias distintas y se diagnostican
    distinto: el texto no puede decir lo mismo en los dos casos."""
    devuelto = _fake_ya_en_nuestra_version()
    devuelto.devolver_en("current_version", None)
    with pytest.raises(VersionIndeterminada) as a:
        devuelto.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert "ha devuelto None (tipo NoneType)" in str(a.value)

    revienta = _fake_ya_en_nuestra_version()
    revienta.fallar_en("current_version", "el socket se ha cerrado")
    with pytest.raises(VersionIndeterminada) as b:
        revienta.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert "no ha contestado: ha lanzado" in str(b.value)
    assert "el socket se ha cerrado" in str(b.value)


def test_el_mensaje_de_un_diccionario_dice_QUE_CLAVES_traia():
    """Si contesta un diccionario, lo unico que hace falta para arreglarlo es
    saber por que clave viene el nombre. El mensaje tiene que darlas."""
    fake = _fake_ya_en_nuestra_version()
    fake.devolver_en("current_version", {"nombreVersion": "SIDEB COLOR", "tipo": 0})
    with pytest.raises(VersionIndeterminada) as exc:
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    mensaje = str(exc.value)
    assert "'nombreVersion'" in mensaje and "'tipo'" in mensaje
    assert "versionName" in mensaje  # las que SI busca
    print(f"[B dict] {mensaje.splitlines()[1]}")


def test_la_via_de_escape_sigue_siendo_la_unica_forma_de_escribir_a_ciegas():
    """Que bloquee siempre no puede dejar la app tapiada: con la via de escape
    abierta se escribe, y el que la abre sabe lo que hace."""
    fake = _fake_ya_en_nuestra_version()
    fake.devolver_en("current_version", None)
    fake.PELIGRO_escribir_fuera_de_la_version = True
    assert fake.set_cdl("clip001", NODE_BALANCE, GRADO) is True


def test_una_respuesta_rara_de_UNA_vez_no_deja_el_puente_tonto_para_siempre():
    """`veces=1` se consume al contestar, no al registrar la llamada.

    Si `_guardia` y `_respuesta_simulada` consumieran los dos, la respuesta rara
    se gastaria antes de llegar a contestar y este test no vería nunca el fallo.
    """
    fake = _fake_ya_en_nuestra_version()
    fake.devolver_en("current_version", None, veces=1)
    with pytest.raises(VersionIndeterminada):
        fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert fake.set_cdl("clip001", NODE_BALANCE, GRADO) is True


def test_el_falso_pregunta_la_version_en_cada_escritura_como_hara_el_de_verdad():
    """`FakeResolve` no puede atajar mirando su estado interno.

    Si el falso comprobara la version leyendo su propio diccionario en vez de
    pasar por `current_version()`, estaria probando algo que `LiveResolve` no
    hace, y las respuestas raras de arriba no se podrian simular siquiera. Se
    comprueba contando llamadas.
    """
    fake = _fake_ya_en_nuestra_version()
    fake._llamadas.clear()
    fake.set_cdl("clip001", NODE_BALANCE, GRADO)
    assert "current_version" in fake._llamadas, (
        "set_cdl no ha preguntado la version: la regla de oro estaria mirando el estado "
        "interno del falso y no lo que contesta la API"
    )


# ---------------------------------------------------------------------------
# C1: la excepcion de la regla de oro, escrita donde se puede encontrar
# ---------------------------------------------------------------------------


def test_el_hueco_de_set_group_post_clip_lut_esta_ESCRITO_en_los_dos_puentes():
    """Hallazgo 4 del auditor. No es un bug: es que no estaba dicho.

    `set_group_post_clip_lut` no pasa por la regla de oro y no puede pasar (un
    grafo post-clip de grupo no tiene versiones). Eso convierte la frase que se
    repite por todo el repo —«el puente se niega en redondo a escribir grado
    fuera de la version»— en algo con una excepcion silenciosa. Este test exige
    que la excepcion este dicha en el docstring del metodo, en las DOS
    implementaciones, para que nadie se la encuentre de golpe.
    """
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "core" / "resolve"
    for fichero, clase in (("fake.py", "FakeResolve"), ("live.py", "LiveResolve")):
        arbol = ast.parse((raiz / fichero).read_text(encoding="utf-8"))
        definicion = next(
            n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef) and n.name == clase
        )
        metodo = next(
            n
            for n in definicion.body
            if isinstance(n, ast.FunctionDef) and n.name == "set_group_post_clip_lut"
        )
        doc = ast.get_docstring(metodo) or ""
        assert "FUERA DE LA REGLA DE ORO" in doc, f"{fichero}: sin avisar del hueco"
        assert "no tiene versiones" in doc or "no tienen versiones" in doc, fichero
        assert "sin deshacer" in doc, f"{fichero}: no dice lo que cuesta"
        assert "NOTAS.md" in doc, f"{fichero}: no manda a donde esta explicado"


def test_el_hueco_tambien_esta_en_NOTAS_y_en_el_docstring_de_bridge():
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "core" / "resolve"
    notas = (raiz / "NOTAS.md").read_text(encoding="utf-8")
    assert "set_group_post_clip_lut" in notas
    assert "2.8" in notas
    import core.resolve.bridge as bridge

    assert "set_group_post_clip_lut" in (bridge.__doc__ or "")
