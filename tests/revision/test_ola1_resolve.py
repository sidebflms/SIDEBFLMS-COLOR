"""REVISION OLA 1 - agente G sobre `core/resolve/` y `probe/` (agente E).

NO se conecta a Resolve. No se importa `DaVinciResolveScript` ni `fusionscript`
desde aqui: el probe se ejecuta como subproceso y solo con `--help` y
`--solo-diagnostico`.

Lo que se ataca:

* Indices de nodo 0, negativos, fuera de rango y **no enteros**.
* Rutas de LUT absolutas, con `~`, con `..`, sin extension y con extension mala.
* Nombres de version vacios y duplicados; clips que no existen.
* **La regla de oro**: ¿se puede escribir un grado sin pasar por `AddVersion`?
* ¿`FakeResolve` deja leer el CDL por algun sitio publico? (seria una trampa que
  se descubre mañana con Resolve delante).
* Las seis incognitas: que la marca `# TODO(F0-n)` existe y que el codigo
  funciona con LAS DOS respuestas posibles de cada una, no solo con la
  conservadora.
* Que `--solo-diagnostico` hace lo que dice su propia ayuda.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from core.contracts import (
    CDL,
    NODE_BALANCE,
    NODE_LOOK,
    VERSION_NAME,
    ResolveBridge,
    ResolveError,
)
from core.resolve import (
    EscrituraFueraDeVersion,
    FakeResolve,
    Incognitas,
    NodoInvalido,
    RutaLUTInvalida,
    VersionInvalida,
    aplicar_grado_seguro,
    asegurar_version,
    extensiones_lut_aceptadas,
    formatos_export_disponibles,
    lut_dir,
    still_sirve_para_medir,
    validar_indice_nodo,
    validar_nombre_version,
    validar_ruta_lut_relativa,
)
from core.resolve.bridge import BaseResolveBridge
from core.resolve.fake import VERSION_INICIAL

RAIZ = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Indices de nodo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("indice", [0, -1, -100, 4, 99, 10**20, None, "hola", 2.5j])
def test_un_indice_de_nodo_imposible_lanza_NodoInvalido(indice):
    """La API es 1-based y el 0 no existe. Fuera de rango tampoco."""
    with pytest.raises(NodoInvalido):
        validar_indice_nodo(indice, 3)


@pytest.mark.parametrize(
    "indice",
    [3.0 - 1e-10, 2.9, 2.0, 3.0, "2", "3", True, False, None, 2.5j, b"2"],
)
def test_un_indice_de_nodo_que_no_sea_un_entero_de_verdad_se_rechaza(indice):
    """RONDA 2 — arreglado. Antes se truncaba en silencio; ahora lanza.

    En la ronda 1 `validar_indice_nodo` hacia `int(node_index)`, que se tragaba
    un float, una cadena y un booleano, y con un float **truncaba**: un indice
    calculado que valiera 2,9999999999 —que para cualquiera es el nodo 3— se
    convertia en el 2 sin decir ni mu.

    E lo ha cerrado del todo: sólo `int`, y además echa fuera el `bool`, que
    para Python es un entero y aquí sería un fallo de tipos. Ojo a los casos
    `2.0` y `3.0`: un float que "parece" un entero **también** se rechaza, y es
    lo correcto — quien tenga un decimal que decida él si es el 2 o el 3 y lo
    redondee donde se pueda ver.

    (Mi test de la ronda 1 se contradecía consigo mismo: afirmaba el valor
    truncado *y* que la misma llamada lanzara. Era rojo con el bug y sin él.
    Arbitrado por el orquestador a favor de E, y con razón.)
    """
    with pytest.raises(NodoInvalido, match="(?i)tiene que ser un entero"):
        validar_indice_nodo(indice, 3)


def test_un_indice_decimal_no_llega_a_escribir_nada():
    """RONDA 2 — arreglado. El decimal muere en la validación, no en el nodo.

    Antes, pedir el nodo `3 - 1e-10` dejaba el CDL en el nodo 2 y `set_cdl`
    devolvía True. Ahora ni se escribe ni se devuelve nada: lanza.
    """
    fake = FakeResolve(n_clips=1)
    asegurar_version(fake, "clip001")
    with pytest.raises(NodoInvalido):
        fake.set_cdl("clip001", 3.0 - 1e-10, CDL(slope=(2.0, 2.0, 2.0)))
    assert fake._cdl_escrito("clip001", 2) is None
    assert fake._cdl_escrito("clip001", 3) is None
    assert fake._grados_escritos == []


# ---------------------------------------------------------------------------
# 2. Rutas de LUT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta",
    [
        "/Library/Application Support/x.cube",
        "/Volumes/DISCO_DEL_CLIENTE/look.cube",
        "//Volumes/DISCO/look.cube",
        "~/look.cube",
        "~mario/look.cube",
        "../look.cube",
        "SIDEB/../../look.cube",
        "SIDEB\\..\\..\\look.cube",
        "look.dctl",
        "look.3dl",
        "look",
        "",
        "   ",
    ],
)
def test_una_ruta_de_lut_hostil_lanza_RutaLUTInvalida(ruta):
    """Resolve se traga una ruta absoluta y luego deja el nodo SIN LUT, callado.

    Es el peor fallo posible, asi que aqui se corta antes. Trece formas de
    equivocarse, todas tienen que morir.
    """
    with pytest.raises(RutaLUTInvalida):
        validar_ruta_lut_relativa(ruta)


def test_una_ruta_absoluta_de_windows_se_cuela_por_la_rendija():
    """HUECO (menor): `C:\\luts\\look.cube` pasa la validacion.

    `os.path.isabs` en macOS solo mira si empieza por `/`, asi que una ruta
    absoluta con letra de unidad no le parece absoluta. En macOS eso no llega a
    ningun sitio malo (seria un nombre de fichero raro) pero el modulo presume
    de cortar las absolutas, y esta no la corta.

    Verde a proposito: documenta el hueco sin romper la suite por algo que hoy
    no es explotable en esta plataforma.
    """
    assert validar_ruta_lut_relativa("C:\\luts\\look.cube") == "C:\\luts\\look.cube"


def test_una_ruta_relativa_legitima_pasa():
    assert validar_ruta_lut_relativa("SIDEB/look.cube") == "SIDEB/look.cube"
    assert validar_ruta_lut_relativa("  SIDEB/look.cube  ") == "SIDEB/look.cube"
    assert validar_ruta_lut_relativa("look.CUBE") == "look.CUBE"


# ---------------------------------------------------------------------------
# 3. Versiones y clips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["", "   ", "\t\n", None, 5, b"SIDEB"])
def test_una_version_sin_nombre_no_se_crea(nombre):
    """Sin nombre no hay `LoadVersionByName` que valga: no se puede recuperar."""
    with pytest.raises(VersionInvalida):
        validar_nombre_version(nombre)


def test_una_version_duplicada_contesta_False_y_no_es_una_averia():
    """Resolve no duplica nombres: contesta que no. Eso es una respuesta."""
    fake = FakeResolve(n_clips=1)
    assert fake.add_version("clip001", "MIA") is True
    assert fake.add_version("clip001", "MIA") is False
    assert fake.version_names("clip001") == [VERSION_INICIAL, "MIA"]


def test_pasar_la_app_dos_veces_no_deja_SIDEB_COLOR_2():
    """`asegurar_version` es idempotente. Si no lo fuera, se llenaria el clip."""
    fake = FakeResolve(n_clips=1)
    for _ in range(5):
        resultado = aplicar_grado_seguro(fake, "clip001", cdl=CDL(), lut_rel_path="SIDEB/l.cube")
        assert resultado.version == VERSION_NAME
    assert fake.version_names("clip001") == [VERSION_INICIAL, VERSION_NAME]


def test_un_clip_que_no_existe_se_dice_con_nombres_y_apellidos():
    fake = FakeResolve(n_clips=2)
    with pytest.raises(ResolveError, match="clip999"):
        aplicar_grado_seguro(fake, "clip999", cdl=CDL())


def test_sin_los_tres_nodos_no_se_escribe_NADA():
    """La API no sabe crear nodos. Con menos de tres hay que parar, no escribir.

    Se comprueba lo importante: que despues de la excepcion **no ha quedado un
    CDL a medias** en ningun nodo de ninguna version.
    """
    fake = FakeResolve(n_clips=1, nodos_por_clip=1)
    with pytest.raises(NodoInvalido, match="(?i)no sabe crear nodos"):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL(slope=(2.0, 2.0, 2.0)))
    assert fake._grados_escritos == []


def test_la_septima_incognita_con_la_respuesta_mala_para_la_app_en_seco():
    """Si `AddVersion` deja la version en blanco, la app no puede escribir.

    Es la incognita que no esta numerada. Con `version_hereda_grafo=False` la
    version nueva tiene un solo nodo y hay que parar y avisar, no escribir a
    ciegas en un nodo que no existe.
    """
    fake = FakeResolve(n_clips=1, version_hereda_grafo=False)
    with pytest.raises(NodoInvalido):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL())
    assert fake._grados_escritos == []
    # Pero la version SI se ha creado, y el grado original sigue en la suya.
    assert VERSION_NAME in fake.version_names("clip001")


def test_una_ruta_de_lut_mala_se_rechaza_ANTES_de_tocar_nada():
    """La validacion va antes de `OpenPage` y antes de `AddVersion`.

    Si fuera al reves, una ruta mal tecleada dejaria el clip con una version
    nueva creada para nada.
    """
    fake = FakeResolve(n_clips=1)
    with pytest.raises(RutaLUTInvalida):
        aplicar_grado_seguro(fake, "clip001", cdl=CDL(), lut_rel_path="/absoluta/x.cube")
    assert fake._llamadas == [], f"ha llamado a {fake._llamadas} antes de validar"
    assert fake.version_names("clip001") == [VERSION_INICIAL]


# ---------------------------------------------------------------------------
# 4. LA REGLA DE ORO: el agujero
# ---------------------------------------------------------------------------


#: Las CINCO operaciones del puente que escriben grado. Las cinco tienen que
#: pasar por la regla de oro, no sólo las dos obvias.
ESCRITURAS_DE_GRADO = ("set_cdl", "set_lut", "set_node_enabled", "copy_grades", "reset_all_grades")


def _intentar_escritura(bridge, operacion: str):
    return {
        "set_cdl": lambda: bridge.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0))),
        "set_lut": lambda: bridge.set_lut("clip001", NODE_LOOK, "SIDEB/look.cube"),
        "set_node_enabled": lambda: bridge.set_node_enabled("clip001", 1, False),
        "copy_grades": lambda: bridge.copy_grades("clip001", ["clip002"]),
        "reset_all_grades": lambda: bridge.reset_all_grades("clip001"),
    }[operacion]()


@pytest.mark.parametrize("operacion", ESCRITURAS_DE_GRADO)
def test_la_regla_de_oro_corta_las_cinco_escrituras_de_grado(operacion):
    """RONDA 2 — el agujero está CERRADO. Este test antes afirmaba lo contrario.

    En la ronda 1 se podía llamar a `set_cdl` / `set_lut` / `copy_grades`
    directamente sobre el puente y escribir encima de la versión del usuario:
    la regla de oro vivía sólo dentro de `aplicar_grado_seguro`, que nadie
    estaba obligado a llamar.

    Ahora vive en `BaseResolveBridge._exigir_version_propia()` y es un `if`. Se
    comprueban **las cinco** escrituras, no las dos que encontré primero:
    `set_node_enabled` y `reset_all_grades` también modifican el grado del
    usuario y también están cubiertas.
    """
    fake = FakeResolve(n_clips=2)
    assert fake.current_version("clip001") == VERSION_INICIAL

    with pytest.raises(EscrituraFueraDeVersion, match="(?i)no se toca"):
        _intentar_escritura(fake, operacion)

    # Y no ha escrito nada a medias por el camino.
    assert fake._grados_escritos == []
    assert fake.version_names("clip001") == [VERSION_INICIAL]
    for clip in ("clip001", "clip002"):
        for nodo in fake.list_nodes(clip):
            assert nodo.lut_path is None
            assert nodo.enabled is True


@pytest.mark.parametrize("operacion", ESCRITURAS_DE_GRADO)
def test_las_cinco_escrituras_SI_funcionan_dentro_de_la_version_de_la_app(operacion):
    """Contrapeso obligatorio: la regla de oro no puede haber roto el camino bueno.

    Una protección que además impide trabajar no es una protección, es un bug.
    """
    fake = FakeResolve(n_clips=2)
    asegurar_version(fake, "clip001")
    asegurar_version(fake, "clip002")
    assert _intentar_escritura(fake, operacion) is True


def test_copy_grades_comprueba_TODOS_los_destinos_antes_de_tocar_ninguno():
    """La segunda puerta del agujero, cerrada y además de forma atómica.

    `copy_grades` **reemplaza el árbol de nodos entero** del destino. Si se
    copia a varios clips y uno de ellos está en la versión del usuario, no vale
    con parar a la mitad: los que ya se hubieran copiado quedarían pisados.

    Verifico que comprueba los destinos **todos por delante**: el clip que sí
    estaba en `SIDEB COLOR` conserva intacto lo que tenía.
    """
    fake = FakeResolve(n_clips=3)
    asegurar_version(fake, "clip001")
    asegurar_version(fake, "clip002")  # clip003 se queda en la del usuario
    fake.set_lut("clip001", NODE_LOOK, "ORIGEN/x.cube")
    fake.set_lut("clip002", NODE_LOOK, "DESTINO/suyo.cube")

    with pytest.raises(EscrituraFueraDeVersion, match="clip003"):
        fake.copy_grades("clip001", ["clip002", "clip003"])

    assert fake._lut_escrito("clip002", NODE_LOOK, VERSION_NAME) == "DESTINO/suyo.cube"


def test_la_via_de_escape_existe_hay_que_nombrarla_y_no_se_activa_de_pasada():
    """La vía de escape tiene que existir (los tests la necesitan) y verse venir.

    Tres propiedades que compruebo:

    1. está apagada por defecto;
    2. es un **atributo**, no un método, así que no se puede llamar de pasada
       desde otro módulo ni encadenar en una expresión;
    3. hay que escribir su nombre entero, que es feo a propósito y se encuentra
       con `grep` en dos segundos. Un typo en el constructor es `TypeError`, no
       una protección apagada en silencio.
    """
    assert BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version is False
    assert not callable(BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version)

    with pytest.raises(TypeError):
        FakeResolve(n_clips=1, PELIGRO=True)  # un typo no la activa

    # Por constructor y por atributo: las dos formas exigen el nombre completo.
    por_constructor = FakeResolve(n_clips=1, PELIGRO_escribir_fuera_de_la_version=True)
    assert por_constructor.set_cdl("clip001", NODE_BALANCE, CDL()) is True

    por_atributo = FakeResolve(n_clips=1)
    por_atributo.PELIGRO_escribir_fuera_de_la_version = True
    assert por_atributo.set_cdl("clip001", NODE_BALANCE, CDL()) is True

    # Y dentro de `core/` se asigna en los DOS puentes, no en uno.
    # (Arbitrado por el orquestador tras el arreglo de E-3: antes este test
    # exigia exactamente 1 sitio, y ese 1 era justo el bug — solo el falso se
    # blindaba. Ahora tienen que ser 2, uno por implementacion; si alguien anade
    # un tercer puente y se le olvida, esto salta.)
    usos = [
        f"{p}:{i}"
        for p in (RAIZ / "core").rglob("*.py")
        for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "PELIGRO_escribir_fuera_de_la_version" in linea
        and "=" in linea
        and linea.strip().startswith("self.PELIGRO")
    ]
    assert len(usos) == 2, (
        f"la via de escape tiene que asignarse en la instancia de LOS DOS puentes "
        f"(fake.py y live.py), y se asigna en {len(usos)}: {usos}"
    )


def test_la_regla_de_oro_vive_en_la_clase_base_asi_que_LiveResolve_la_hereda():
    """Lo que de verdad importa: que no sea una red que sólo exista en pruebas.

    Si `_exigir_version_propia` estuviera sólo en `FakeResolve`, mañana con
    Resolve delante no protegería nada y no nos enteraríamos hasta pisarle el
    grado a alguien. Se comprueba **leyendo el fuente**, sin importar Resolve:
    `LiveResolve` hereda de `BaseResolveBridge` y llama a la regla las mismas
    cinco veces que `FakeResolve`.
    """
    fuente_live = (RAIZ / "core" / "resolve" / "live.py").read_text(encoding="utf-8")
    fuente_fake = (RAIZ / "core" / "resolve" / "fake.py").read_text(encoding="utf-8")

    arbol = ast.parse(fuente_live)
    clases = {
        n.name: [b.id for b in n.bases if isinstance(b, ast.Name)]
        for n in ast.walk(arbol)
        if isinstance(n, ast.ClassDef)
    }
    assert "BaseResolveBridge" in clases.get("LiveResolve", []), clases

    # >= y no ==: contar un nombre en el texto fuente cuenta tambien las veces
    # que sale en un comentario o en un docstring, y E documento el porque del
    # arreglo E-3 justo ahi. Lo que se quiere afirmar es que NO FALTA ninguna
    # escritura sin comprobar, no que nadie pueda escribir el nombre en prosa.
    assert fuente_live.count("_exigir_version_propia") >= len(ESCRITURAS_DE_GRADO)
    assert fuente_fake.count("_exigir_version_propia") >= len(ESCRITURAS_DE_GRADO)


def test_envenenar_la_clase_base_ya_NO_apaga_la_regla_en_ninguno_de_los_dos():
    """Fue el hallazgo E-3 de la ronda 2, y esta cerrado.

    `PELIGRO_escribir_fuera_de_la_version` es un atributo de clase.
    `FakeResolve.__init__` lo reasignaba en la instancia y `LiveResolve.__init__`
    no, asi que una linea suelta en cualquier sitio del proyecto apagaba la
    regla de oro **en el puente de verdad** y la dejaba puesta en el falso: todo
    verde esta noche y ni una proteccion el dia que hable con Resolve.

    Es la asimetria que ningun test contra `FakeResolve` puede cazar, y por eso
    este test entra por la clase base a envenenarla.

    (Test reescrito por el orquestador con el agente G ya caido por limite de
    API. El anterior afirmaba el bug; este afirma el arreglo.)
    """
    import core.resolve.live as live

    original = BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version
    try:
        BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True
        falso = FakeResolve(n_clips=1)
        vivo = live.LiveResolve(object())  # no toca Resolve: solo guarda el objeto
        assert falso.PELIGRO_escribir_fuera_de_la_version is False, "el falso se blinda solo"
        assert vivo.PELIGRO_escribir_fuera_de_la_version is False, (
            "LiveResolve vuelve a heredar la via de escape de la clase base: E-3 ha vuelto"
        )
    finally:
        BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = original

    # Y que la limpieza ha funcionado, no vaya a contaminar a los demas tests.
    assert FakeResolve(n_clips=1).PELIGRO_escribir_fuera_de_la_version is False


def test_aplicar_grado_seguro_SI_hace_las_cosas_en_orden():
    """Contrapeso: el camino bueno escribe en `SIDEB COLOR` y deja intacta la otra."""
    fake = FakeResolve(n_clips=1)
    aplicar_grado_seguro(fake, "clip001", cdl=CDL(slope=(2.0, 2.0, 2.0)), lut_rel_path="S/l.cube")

    assert fake.current_version("clip001") == VERSION_NAME
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_NAME) is not None
    assert fake._cdl_escrito("clip001", NODE_BALANCE, VERSION_INICIAL) is None
    assert fake._lut_escrito("clip001", NODE_LOOK, VERSION_INICIAL) is None

    # Y el orden: nada de escritura antes de add_version.
    llamadas = fake._llamadas
    primera_escritura = min(llamadas.index("set_cdl"), llamadas.index("set_lut"))
    assert llamadas.index("add_version") < primera_escritura


# ---------------------------------------------------------------------------
# 5. ¿Filtra `FakeResolve` algo que la API real no tiene?
# ---------------------------------------------------------------------------


def test_fakeresolve_no_ofrece_ninguna_forma_PUBLICA_de_leer_el_cdl():
    """`GetCDL` no existe en Resolve. Si el falso lo ofreciera, seria una trampa.

    Se comprueba que ningun metodo publico (sin guion bajo) devuelve un `CDL`, y
    que los dos que si lo hacen (`_cdl_escrito`, `_grados_escritos`) empiezan por
    guion bajo, o sea que son para los tests y se ven a la legua.
    """
    publicos = [
        m
        for m in dir(FakeResolve)
        if not m.startswith("_") and callable(getattr(FakeResolve, m, None))
    ]
    sospechosos = [m for m in publicos if "cdl" in m.lower() or "grado" in m.lower()]
    assert sospechosos == ["set_cdl"], f"metodos publicos que huelen a leer grado: {sospechosos}"

    fake = FakeResolve(n_clips=1)
    # RONDA 2: el montaje necesita la version de la app. Antes bastaba un
    # `set_cdl` crudo; ahora eso lanza `EscrituraFueraDeVersion`, que es el
    # arreglo funcionando. El asunto de fondo del test no cambia.
    asegurar_version(fake, "clip001")
    fake.set_cdl("clip001", NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0)))
    # Y lo que si es publico (list_nodes) no lleva el CDL dentro:
    for nodo in fake.list_nodes("clip001"):
        assert not hasattr(nodo, "cdl")
    assert not hasattr(fake, "get_cdl")


def test_los_metodos_publicos_de_mas_de_fakeresolve_son_solo_de_simulacion():
    """Lo que `FakeResolve` tiene de mas que el Protocol tiene que ser inofensivo.

    Son la maquinaria de fingir averias (`fallar_en`...) y dos que si existen en
    la API real (`SetCurrentStillAlbum`, y leer el grafo post-clip de un grupo).
    Ninguno permite hacer con el falso algo que mañana no se pueda hacer.
    """
    protocolo = {m for m in dir(ResolveBridge) if not m.startswith("_")}
    publicos = {
        m
        for m in dir(FakeResolve)
        if not m.startswith("_") and callable(getattr(FakeResolve, m, None))
    }
    assert sorted(publicos - protocolo) == [
        "conectar",
        "dejar_de_fallar",
        "desconectar",
        # `devolver_en(operacion, valor)` lo anadio el dia 2 para simular las
        # cuatro respuestas raras de GetCurrentVersion(). Entra en la lista por
        # decision del AUDITOR INDEPENDIENTE, no del orquestador, y con
        # evidencia: solo admite las 24 operaciones del Protocol (pedirle
        # "get_cdl" lanza ValueError), devuelve None -- es un setter de la
        # simulacion, no una fuga de lectura -- y no mueve el estado real. Ver
        # AUDITORIA-DIA2.md, decision 1.
        "devolver_en",
        "devolver_false_en",
        "fallar_en",
        "nodos_post_clip",
        "set_current_still_album",
    ]


def test_el_look_de_un_grupo_es_el_nodo_1_del_post_clip_no_el_3():
    """La trampa de la constante `NODE_LOOK = 3` fuera de su sitio."""
    fake = FakeResolve(n_clips=1)
    fake.add_color_group("MI GRUPO")
    with pytest.raises(NodoInvalido):
        fake.set_group_post_clip_lut("MI GRUPO", NODE_LOOK, "S/l.cube")
    assert fake.set_group_post_clip_lut("MI GRUPO", 1, "S/l.cube") is True


# ---------------------------------------------------------------------------
# 6. Las seis incognitas, con LAS DOS respuestas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_la_marca_TODO_de_cada_incognita_existe_de_verdad(n):
    """Mañana hay que encontrarlas. Se busca en el codigo fuente, no en el docstring."""
    fuentes = "\n".join(
        p.read_text(encoding="utf-8") for p in (RAIZ / "core").rglob("*.py")
    )
    assert f"TODO(F0-{n})" in fuentes


def test_las_marcas_TODO_no_se_han_multiplicado_por_el_codigo():
    """Cambiar una incognita mañana tiene que ser tocar UN sitio.

    NOTAS.md promete que fuera de `incognitas.py` hay exactamente dos marcas.
    Si esto crece, mañana se cambia una constante y la app sigue asumiendo lo
    contrario en otro archivo.
    """
    fuera = {}
    for p in (RAIZ / "core").rglob("*.py"):
        if p.name == "incognitas.py":
            continue
        cuantas = p.read_text(encoding="utf-8").count("TODO(F0-")
        if cuantas:
            fuera[p.name] = cuantas
    assert fuera == {"bridge.py": 1, "fake.py": 1}, fuera


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("export_drx_funciona", False),
        ("export_drx_funciona", True),
        ("still_lleva_grado", False),
        ("still_lleva_grado", True),
        ("setlut_acepta_dctl", False),
        ("setlut_acepta_dctl", True),
        ("instalacion", "descarga"),
        ("instalacion", "mac_app_store"),
        ("requiere_open_page", True),
        ("requiere_open_page", False),
        ("fusionscript_importable", None),
        ("fusionscript_importable", True),
        ("fusionscript_importable", False),
    ],
)
def test_la_app_funciona_con_las_DOS_respuestas_de_cada_incognita(campo, valor, tmp_path):
    """No basta con que funcione con la respuesta conservadora.

    Mañana Mario contesta el probe y cambia las constantes. Si alguna rama solo
    esta escrita para el valor de hoy, se descubre delante del cliente.
    """
    incognitas = Incognitas(**{campo: valor})
    fake = FakeResolve(n_clips=1, incognitas=incognitas, home=str(tmp_path))
    resultado = aplicar_grado_seguro(
        fake, "clip001", cdl=CDL(), lut_rel_path="SIDEB/l.cube", incognitas=incognitas
    )
    assert resultado.ok
    assert len(resultado.avisos) >= 0
    assert isinstance(lut_dir(incognitas, home=str(tmp_path)), str)
    assert isinstance(still_sirve_para_medir(incognitas), bool)
    assert ".cube" in extensiones_lut_aceptadas(incognitas)
    assert len(formatos_export_disponibles(incognitas)) >= 8
    assert incognitas.describir()


def test_cada_incognita_cambia_algo_observable(tmp_path):
    """Si cambiar una constante no cambia nada, la incognita esta muerta."""
    base = Incognitas()
    assert "drx" not in formatos_export_disponibles(base)
    assert "drx" in formatos_export_disponibles(Incognitas(export_drx_funciona=True))

    assert extensiones_lut_aceptadas(base) == (".cube",)
    assert ".dctl" in extensiones_lut_aceptadas(Incognitas(setlut_acepta_dctl=True))

    assert still_sirve_para_medir(base) is False
    assert still_sirve_para_medir(Incognitas(still_lleva_grado=True)) is True

    assert lut_dir(base).startswith("/Library/")
    assert lut_dir(Incognitas(instalacion="mac_app_store"), home=str(tmp_path)).startswith(
        str(tmp_path)
    )

    # F0-5: con requiere_open_page=False NO se cambia de pagina.
    for requiere, pagina in ((True, "color"), (False, "edit")):
        inc = Incognitas(requiere_open_page=requiere)
        fake = FakeResolve(n_clips=1, incognitas=inc)
        aplicar_grado_seguro(fake, "clip001", cdl=CDL(), incognitas=inc)
        assert fake.pagina_actual == pagina


def test_el_drx_devuelve_lista_vacia_mientras_F0_1_diga_que_no(tmp_path):
    """Y con la respuesta buena, escribe. Las dos ramas, ejercitadas."""
    for funciona, esperados in ((False, 0), (True, 1)):
        inc = Incognitas(export_drx_funciona=funciona)
        fake = FakeResolve(n_clips=1, incognitas=inc)
        still = fake.grab_still()
        salida = tmp_path / f"drx_{funciona}"
        salida.mkdir()
        escritos = fake.export_stills([still], str(salida), "probe_", "drx")
        assert len(escritos) == esperados
        assert len(list(salida.iterdir())) == esperados


def test_export_stills_no_se_sale_del_directorio_que_le_dan(tmp_path):
    """`FakeResolve` escribe ficheros DE VERDAD. Que sean solo donde le dicen."""
    fake = FakeResolve(n_clips=1)
    still = fake.grab_still()
    salida = tmp_path / "salida"
    salida.mkdir()
    for prefijo in ("../fuera_", "a/b_", "..\\fuera_", "/absoluto_"):
        with pytest.raises(ResolveError, match="(?i)separadores"):
            fake.export_stills([still], str(salida), prefijo, "png")
    with pytest.raises(ResolveError, match="(?i)no existe"):
        fake.export_stills([still], str(tmp_path / "no_existe"), "p_", "png")

    escritos = fake.export_stills([still], str(salida), "bien_", "png")
    assert [Path(p).parent for p in escritos] == [salida]
    assert list(tmp_path.iterdir()) == [salida]


# ---------------------------------------------------------------------------
# 7. El probe, sin tocar Resolve
# ---------------------------------------------------------------------------


def _correr_probe(argumentos: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(RAIZ / "probe" / "api_probe.py"), *argumentos],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_el_probe_arranca_y_su_ayuda_no_escribe_nada(tmp_path):
    proceso = _correr_probe(["--help"], tmp_path)
    assert proceso.returncode == 0
    assert "--solo-diagnostico" in proceso.stdout
    assert list(tmp_path.iterdir()) == []


def test_solo_diagnostico_DICE_que_no_escribe_nada_y_escribe_dos_ficheros(tmp_path):
    """BUG: la ayuda de `--solo-diagnostico` dice "no escribe nada". Miente.

    `main()` termina siempre por `terminar()`, que llama a `Informe.escribir()`
    con el valor por defecto de `--informe`, o sea `informe_probe_resolve.json`
    EN LA CARPETA DESDE LA QUE SE EJECUTA. Se escriben dos ficheros (el .json y
    el .txt de al lado) y ademas se hace `os.makedirs` de su carpeta.

    Consecuencia practica: si Mario lo ejecuta desde el repo (que es lo natural,
    porque el script esta ahi), le deja dos ficheros sueltos dentro del repo.

    ROJO a proposito. El arreglo es una linea: o no escribir con
    `--solo-diagnostico`, o cambiar el texto de la ayuda.
    """
    proceso = _correr_probe(["--solo-diagnostico"], tmp_path)
    assert proceso.returncode in (0, 1), proceso.stderr[-500:]
    escritos = sorted(p.name for p in tmp_path.iterdir())
    assert escritos == [], (
        f"--solo-diagnostico dice en su ayuda que no escribe nada, y ha escrito {escritos}"
    )


def test_solo_diagnostico_no_intenta_conectarse_a_resolve(tmp_path):
    """Lo que SI cumple: para antes de conectar. Solo mira el entorno.

    (Ojo: si que IMPORTA el modulo de scripting, que es lo que le hace falta
    para contestar F0-6. Eso es por diseño y esta documentado en la ayuda.)
    """
    proceso = _correr_probe(["--solo-diagnostico", "--informe", str(tmp_path / "inf.json")], tmp_path)
    salida = proceso.stdout
    assert "PARO AQUI (--solo-diagnostico)" in salida
    assert "F0-6" in salida
    # No ha llegado a preguntar nada que necesite escribir en el proyecto.
    for marca in ("F0-1", "F0-2", "F0-3", "F0-5"):
        assert f"  {marca}   " not in salida


def test_importar_core_resolve_no_carga_el_modulo_de_scripting_de_resolve():
    """Contrato 6, comprobado en un proceso limpio.

    Si algun dia alguien engancha `live.py` al `__init__`, abrir la app sin
    Resolve instalado empezaria a fallar. Se repite aqui aunque el autor ya lo
    tenga: es la clase de test que se borra "por duplicado" y luego se echa de
    menos.
    """
    codigo = (
        "import sys; import core.resolve; "
        "malos=[m for m in sys.modules if 'DaVinciResolveScript' in m or 'fusionscript' in m "
        "or m.startswith('PySide6')]; "
        "print(malos)"
    )
    proceso = subprocess.run(  # noqa: S603
        [sys.executable, "-c", codigo],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert proceso.stdout.strip() == "[]", proceso.stdout
