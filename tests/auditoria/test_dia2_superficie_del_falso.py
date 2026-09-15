"""AUDITORIA DIA 2, segunda vuelta - DECISION 1: ¿entra `devolver_en` en la lista?

El test `test_los_metodos_publicos_de_mas_de_fakeresolve_son_solo_de_simulacion`
existe para impedir que `FakeResolve` ofrezca **capacidades que la API real no
tiene**. El caso que lo motivo fue `GetCDL`: si el falso dejara leer el grado,
alguien escribiria esta noche codigo que lo lee y manana no funcionaria.

La pregunta no es si `devolver_en` es comodo. Es si abre una puerta para que
codigo de PRODUCCION lea o haga algo que Resolve no da. Se comprueba aqui, y se
comprueba tambien la trampa contraria, que es la que de verdad me preocupaba:
que el falso pueda quedarse en un estado en el que **se miente a si mismo** —la
regla de oro mirando una version simulada y la escritura cayendo en otra.
"""

from __future__ import annotations

import inspect

import pytest

from core.contracts import CDL, NODE_BALANCE, NODE_LOOK, VERSION_NAME, ResolveBridge
from core.resolve import (
    EscrituraFueraDeVersion,
    FakeResolve,
    asegurar_version,
)

ESCRITURAS_DE_GRADO = ("set_cdl", "set_lut", "set_node_enabled", "copy_grades", "reset_all_grades")


def _publicos_de_mas() -> list[str]:
    protocolo = {m for m in dir(ResolveBridge) if not m.startswith("_")}
    publicos = {
        m
        for m in dir(FakeResolve)
        if not m.startswith("_") and callable(getattr(FakeResolve, m, None))
    }
    return sorted(publicos - protocolo)


def test_D1_cual_es_hoy_la_superficie_de_mas_del_falso():
    """Deja por escrito la lista de hoy, para poder razonar sobre ella."""
    de_mas = _publicos_de_mas()
    for m in de_mas:
        doc = (inspect.getdoc(getattr(FakeResolve, m)) or "").splitlines()
        print(f"[D1] {m}: {doc[0] if doc else '(sin docstring)'}")
    assert "devolver_en" in de_mas, "el metodo nuevo ya no esta: rehaz esta decision"


def test_D1_devolver_en_no_deja_LEER_nada_que_Resolve_no_de():
    """La prueba de fondo: ¿es una fuga de informacion como lo era GetCDL?

    `devolver_en` no DEVUELVE nada: es un setter de la simulacion. Lo unico que
    hace es cambiar lo que contestan metodos que YA estan en el Protocol. No
    anade ni una via de lectura.
    """
    firma = inspect.signature(FakeResolve.devolver_en)
    assert list(firma.parameters) == ["self", "operacion", "valor", "veces"]
    assert firma.return_annotation in (None, "None"), firma.return_annotation
    fake = FakeResolve(n_clips=1)
    assert fake.devolver_en("current_version", "lo que sea") is None

    # Y no se puede usar para inventar operaciones que el Protocol no tenga.
    with pytest.raises(ValueError):
        fake.devolver_en("get_cdl", CDL())
    with pytest.raises(ValueError):
        fake.devolver_en("GetCDL", CDL())
    assert not hasattr(fake, "get_cdl")


def test_D1_devolver_en_solo_admite_las_24_operaciones_del_protocol():
    """No es una puerta trasera: la lista de operaciones validas es cerrada."""
    from core.resolve.fake import OPERACIONES

    protocolo = {m for m in dir(ResolveBridge) if not m.startswith("_")}
    assert set(OPERACIONES) == protocolo, (
        f"la lista de operaciones simulables ya no es la del Protocol: "
        f"de mas={set(OPERACIONES) - protocolo} de menos={protocolo - set(OPERACIONES)}"
    )
    print(f"[D1] operaciones simulables = {len(OPERACIONES)}, y son exactamente las del Protocol")


def test_D1_lo_simulado_NO_deja_rastro_en_el_estado_real_del_falso():
    """Una respuesta simulada es una mentira de la API, no un cambio de estado.

    Si `devolver_en("current_version", X)` cambiara de verdad la version activa
    del clip, seria otra cosa: seria una forma de mover el estado por la puerta
    de atras. No lo hace.
    """
    fake = FakeResolve(n_clips=1)
    asegurar_version(fake, "clip001")
    assert fake.current_version("clip001") == VERSION_NAME
    fake.devolver_en("current_version", "Version 1", veces=1)
    assert fake.current_version("clip001") == "Version 1"  # la mentira
    assert fake.current_version("clip001") == VERSION_NAME  # y se acabo
    assert fake.version_names("clip001") == ["Version 1", VERSION_NAME] or VERSION_NAME in (
        fake.version_names("clip001")
    )
    print(f"[D1] versiones reales tras la mentira: {fake.version_names('clip001')}")


# ---------------------------------------------------------------------------
# La trampa de verdad: ¿puede el falso mentirse A SI MISMO?
# ---------------------------------------------------------------------------


def test_D1_RIESGO_mentir_que_SI_es_nuestra_deja_escribir_en_la_version_del_usuario():
    """El riesgo real de `devolver_en`, y no es una fuga de lectura.

    La regla de oro del falso mira `_version_activa_o_rota()`, que pasa por
    `current_version()` y por tanto **es simulable**. Pero la escritura cae en
    `self._version_actual(clip)`, que es el diccionario interno y **no lo es**.

    O sea que `devolver_en("current_version", "SIDEB COLOR")` con el clip
    parado en la version del usuario hace pasar la guardia y escribe en la del
    usuario. Es coherente (el falso simula una API que miente y la app se la
    cree, que es lo que pasaria de verdad), pero conviene que este escrito:
    quien use `devolver_en` para hacer pasar una guardia esta montando un
    escenario en el que el grado acaba donde no se espera.
    """
    fake = FakeResolve(n_clips=1)
    # El clip esta en la version del usuario. Sin mentir, la regla corta.
    del_usuario = fake.current_version("clip001")
    assert del_usuario == "Version 1", del_usuario
    with pytest.raises(EscrituraFueraDeVersion):
        fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0)))

    # Ahora el falso miente y dice que esta en la nuestra.
    fake.devolver_en("current_version", VERSION_NAME)
    assert fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0))) is True

    escritos = fake._grados_escritos
    destino = escritos[-1].version
    print(f"[D1-riesgo] la guardia vio {VERSION_NAME!r} y el grado ha caido en {destino!r}")
    assert destino == del_usuario, (
        "si esto cambia, es que el falso ya escribe donde dice la mentira y no donde esta "
        "de verdad; entonces la mentira mueve el estado y eso SI seria una puerta trasera"
    )


def test_D1_pero_el_rastro_NO_miente_el_grado_queda_fichado_en_su_version_real():
    """Lo que salva la situacion anterior: el registro no se traga la mentira.

    `_grados_escritos` anota la version REAL. O sea que un test que se enganase
    a si mismo con `devolver_en` y luego comprobara donde cayo el grado, lo
    veria. La mentira no contamina la contabilidad.
    """
    from core.contracts import ResolveError

    fake = FakeResolve(n_clips=1)
    fake.devolver_en("current_version", VERSION_NAME)
    fake.set_lut("clip001", NODE_LOOK, "SIDEB/look.cube")

    # Ni siquiera existe la version de la app: la mentira no la ha creado.
    with pytest.raises(ResolveError, match="no tiene la version"):
        fake._lut_escrito("clip001", NODE_LOOK, VERSION_NAME)
    assert fake._lut_escrito("clip001", NODE_LOOK, "Version 1") == "SIDEB/look.cube"
    print("[D1-rastro] el LUT esta fichado en 'Version 1', que es donde cayo de verdad;")
    print("[D1-rastro] preguntar por la version de la app LANZA, no contesta que si.")


@pytest.mark.parametrize("operacion", ESCRITURAS_DE_GRADO)
def test_D1_sin_mentir_las_cinco_escrituras_siguen_cortadas(operacion):
    """Contrapeso: que anadir `devolver_en` no ha aflojado la regla de oro."""
    fake = FakeResolve(n_clips=2)
    accion = {
        "set_cdl": lambda: fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0))),
        "set_lut": lambda: fake.set_lut("clip001", NODE_LOOK, "SIDEB/look.cube"),
        "set_node_enabled": lambda: fake.set_node_enabled("clip001", 1, False),
        "copy_grades": lambda: fake.copy_grades("clip001", ["clip002"]),
        "reset_all_grades": lambda: fake.reset_all_grades("clip001"),
    }[operacion]
    with pytest.raises(EscrituraFueraDeVersion):
        accion()


def test_D1_la_lista_del_test_de_revision_con_devolver_en_dentro():
    """Mi veredicto, escrito como test: la lista correcta a dia de hoy.

    Si manana aparece un metodo publico de mas que NO sea maquinaria de simular
    ni exista en la API real, este test salta y hay que volver a pensarlo. Es
    el mismo servicio que daba el del revisor, con el metodo nuevo dentro.
    """
    esperada = [
        "conectar",
        "dejar_de_fallar",
        "desconectar",
        "devolver_en",
        "devolver_false_en",
        "fallar_en",
        "nodos_post_clip",
        "set_current_still_album",
    ]
    assert _publicos_de_mas() == esperada, (
        f"la superficie de mas de FakeResolve ha cambiado: {_publicos_de_mas()}. "
        f"Antes de ampliar la lista, comprueba que el metodo nuevo no deja LEER nada que "
        f"Resolve no de (fue el caso de GetCDL)."
    )


def test_D1_ninguno_de_los_de_mas_devuelve_un_CDL_ni_un_grado():
    """La prueba que de verdad protege contra la fuga del CDL, por firma.

    El test del revisor filtraba por NOMBRE ('cdl' o 'grado' en el nombre del
    metodo). Un `devolver_en` no lleva ninguna de las dos palabras, asi que ese
    filtro no lo habria visto nunca. Aqui se mira lo que de verdad importa:
    que ninguno de los publicos de mas devuelva un CDL, ni acepte que se le
    pida uno de vuelta.
    """
    fake = FakeResolve(n_clips=1)
    asegurar_version(fake, "clip001")
    fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(3.0, 3.0, 3.0)))
    for nombre in _publicos_de_mas():
        metodo = getattr(FakeResolve, nombre)
        anotacion = inspect.signature(metodo).return_annotation
        print(f"[D1-firma] {nombre} -> {anotacion}")
        assert "CDL" not in str(anotacion), f"{nombre} devuelve un CDL"
    # Y el unico camino a un CDL escrito sigue siendo de guion bajo.
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_NAME) is not None
    assert not any(n.startswith("cdl") or n.endswith("cdl") for n in _publicos_de_mas())


# ---------------------------------------------------------------------------
# «Si eso se rompio, se rompio la red entera»: la invariante del falso.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version_activa", ["Version 1", VERSION_NAME, "SIDEB COLOR PROBE"])
def test_D1_INVARIANTE_sin_mentir_la_guardia_y_la_escritura_miran_LO_MISMO(version_activa):
    """La comprobacion de fondo del cambio de anoche en `FakeResolve`.

    Las cinco escrituras preguntan ahora por `current_version()` (simulable) y
    escriben en `_version_actual(clip)` (el diccionario interno). Mientras nadie
    mienta, los dos tienen que decir lo mismo **siempre**. Si alguna vez
    divergen sin que nadie haya llamado a `devolver_en`, el falso estaria
    comprobando una cosa y escribiendo en otra, y entonces si se habria roto la
    red contra la que se prueba todo lo demas.
    """
    fake = FakeResolve(n_clips=1)
    if version_activa != "Version 1":
        asegurar_version(fake, "clip001", version_activa)

    guardia = fake._version_activa_o_rota("clip001")
    interna = fake._version_actual(fake._clip("clip001")).nombre
    publica = fake.current_version("clip001")
    print(f"[D1-inv] guardia={guardia!r} interna={interna!r} publica={publica!r}")
    assert guardia == interna == publica == version_activa


def test_D1_INVARIANTE_tras_cada_operacion_de_version_siguen_cuadrando():
    """La misma invariante, pero despues de mover las versiones de un lado a otro."""
    fake = FakeResolve(n_clips=1)
    pasos = [
        ("inicio", lambda: None),
        ("add_version", lambda: fake.add_version("clip001", VERSION_NAME)),
        ("load_version a la del usuario", lambda: fake.load_version("clip001", "Version 1")),
        ("load_version a la nuestra", lambda: fake.load_version("clip001", VERSION_NAME)),
        ("add_version PROBE", lambda: fake.add_version("clip001", "SIDEB COLOR PROBE")),
        ("asegurar_version", lambda: asegurar_version(fake, "clip001")),
    ]
    for nombre, accion in pasos:
        accion()
        guardia = fake._version_activa_o_rota("clip001")
        interna = fake._version_actual(fake._clip("clip001")).nombre
        print(f"[D1-inv] tras {nombre:<28} guardia={guardia!r} interna={interna!r}")
        assert guardia == interna, f"divergen tras {nombre}"


@pytest.mark.parametrize("operacion", ESCRITURAS_DE_GRADO)
def test_D1_si_la_API_REVIENTA_al_preguntar_la_version_no_se_escribe_nada(operacion):
    """La cuarta forma de portarse mal: que `GetCurrentVersion()` lance.

    Es la que mas me interesa auditar porque el falso la simula con
    `fallar_en`, no con `devolver_en`, o sea que va por otro camino del codigo.
    """
    fake = FakeResolve(n_clips=2)
    asegurar_version(fake, "clip001")
    asegurar_version(fake, "clip002")
    fake.fallar_en("current_version", "la API ha reventado")
    accion = {
        "set_cdl": lambda: fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0))),
        "set_lut": lambda: fake.set_lut("clip001", NODE_LOOK, "SIDEB/look.cube"),
        "set_node_enabled": lambda: fake.set_node_enabled("clip001", 1, False),
        "copy_grades": lambda: fake.copy_grades("clip001", ["clip002"]),
        "reset_all_grades": lambda: fake.reset_all_grades("clip001"),
    }[operacion]
    with pytest.raises(EscrituraFueraDeVersion):
        accion()
    assert fake._grados_escritos == [], "ha quedado grado escrito pese a no saber la version"
    assert fake._lut_escrito("clip001", NODE_LOOK, VERSION_NAME) is None
