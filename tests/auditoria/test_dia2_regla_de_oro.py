"""AUDITORIA DIA 2 - Casos 1, 2 y 3: la regla de oro y su via de escape.

Los tres tests del revisor que el orquestador reescribio afirmaban cosas
contando texto: numero de lineas con `self.PELIGRO...`, numero de veces que
aparece la cadena `_exigir_version_propia` en el fuente. Contar texto es fragil
por los dos lados: un `==` se rompe con un comentario nuevo y un `>=` pasa
aunque las cinco apariciones esten en un docstring.

Aqui se afirma lo mismo **por AST y por comportamiento**, que es inmune a las
dos cosas:

* Caso 1: ninguna asignacion de la via de escape dentro de `core/` la enciende.
  No importa cuantas haya: importa que ninguna ponga `True` a pelo.
* Caso 2: cada una de las CINCO escrituras de grado, en LAS DOS
  implementaciones, llama de verdad a `_exigir_version_propia`. Por AST (que la
  llamada existe) y por comportamiento (que salta, tambien en `LiveResolve`,
  usando un doble de la API que NO es Resolve).
* Caso 3: envenenar la clase base no apaga la regla en ninguna de las dos, y
  ningun otro atributo de clase compartido tiene la asimetria de antes.

No se conecta a Resolve. No se importa `DaVinciResolveScript` ni
`fusionscript`: `LiveResolve.__init__` solo guarda el objeto que se le pasa.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

from core.contracts import CDL, NODE_BALANCE, NODE_LOOK
from core.resolve import EscrituraFueraDeVersion, FakeResolve
from core.resolve.bridge import BaseResolveBridge
from core.resolve.live import LiveResolve

RAIZ = Path(__file__).resolve().parents[2]
CORE = RAIZ / "core"

#: Las cinco escrituras de grado, las mismas que enumeraba el revisor.
ESCRITURAS_DE_GRADO = ("set_cdl", "set_lut", "set_node_enabled", "copy_grades", "reset_all_grades")

VIA_DE_ESCAPE = "PELIGRO_escribir_fuera_de_la_version"
REGLA = "_exigir_version_propia"


# ---------------------------------------------------------------------------
# Caso 1 - la via de escape: lo que importa no es cuantas veces se asigna,
#          sino que ninguna asignacion de `core/` la deje encendida.
# ---------------------------------------------------------------------------


def _asignaciones_de_la_via_de_escape():
    """Todas las asignaciones a la via de escape en `core/`, por AST.

    Devuelve `(fichero, linea, descripcion_del_valor, es_segura)`.
    Segura = pone `False` literal, o reenvia un parametro homonimo del mismo
    `__init__` cuyo valor por defecto es `False`.
    """
    fuera = []
    for py in sorted(CORE.rglob("*.py")):
        arbol = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        # De que funcion cuelga cada nodo, para poder mirar sus parametros.
        padre = {}
        for fn in ast.walk(arbol):
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                for hijo in ast.walk(fn):
                    padre.setdefault(hijo, fn)
        for nodo in ast.walk(arbol):
            objetivos = []
            if isinstance(nodo, ast.Assign):
                objetivos = nodo.targets
            elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
                objetivos = [nodo.target]
            else:
                continue
            toca = any(
                (isinstance(t, ast.Attribute) and t.attr == VIA_DE_ESCAPE)
                or (isinstance(t, ast.Name) and t.id == VIA_DE_ESCAPE)
                for t in objetivos
            )
            if not toca:
                continue
            valor = nodo.value
            if isinstance(valor, ast.Constant) and valor.value is False:
                desc, segura = "False literal", True
            elif isinstance(valor, ast.Name) and valor.id == VIA_DE_ESCAPE:
                fn = padre.get(nodo)
                defecto_falso = False
                if fn is not None:
                    args = fn.args
                    todos = args.posonlyargs + args.args + args.kwonlyargs
                    pos = args.defaults
                    kw = args.kw_defaults
                    emparejados = list(
                        zip(args.posonlyargs + args.args, [None] * 99, strict=False)
                    )
                    del emparejados
                    # posicionales: los defaults van alineados por la derecha
                    nombres_pos = [a.arg for a in args.posonlyargs + args.args]
                    for nombre, d in zip(nombres_pos[len(nombres_pos) - len(pos) :], pos, strict=True):
                        if nombre == VIA_DE_ESCAPE and isinstance(d, ast.Constant):
                            defecto_falso = d.value is False
                    for a, d in zip(args.kwonlyargs, kw, strict=True):
                        if a.arg == VIA_DE_ESCAPE and isinstance(d, ast.Constant):
                            defecto_falso = d.value is False
                    if VIA_DE_ESCAPE not in [a.arg for a in todos]:
                        defecto_falso = False
                desc = f"parametro homonimo (defecto False: {defecto_falso})"
                segura = defecto_falso
            else:
                desc, segura = f"valor {ast.dump(valor)[:60]}", False
            fuera.append((py.relative_to(RAIZ).as_posix(), nodo.lineno, desc, segura))
    return fuera


def test_AUD1_ninguna_asignacion_de_core_enciende_la_via_de_escape():
    """CASO 1. Lo que el revisor queria proteger, dicho sin contar lineas.

    El test original decia `len(usos) == 1` y el reescrito `== 2`. Los dos
    cuentan sitios; ninguno mira el VALOR. Un
    `self.PELIGRO_escribir_fuera_de_la_version = True` a pelo pasaria los dos
    si alguien borrase otra linea a cambio. Esto no.
    """
    asignaciones = _asignaciones_de_la_via_de_escape()
    for f, linea, desc, segura in asignaciones:
        print(f"[AUD1] {f}:{linea} -> {desc} {'OK' if segura else '<-- PELIGRO'}")
    assert asignaciones, "no encuentro ni una asignacion: el test se ha quedado ciego"
    malas = [a for a in asignaciones if not a[3]]
    assert not malas, f"hay asignaciones de core/ que pueden encender la via de escape: {malas}"


def test_AUD1_apagada_por_defecto_en_la_base_y_en_las_dos_implementaciones():
    """CASO 1. La propiedad de verdad: por defecto, apagada en todas partes."""
    assert BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version is False
    assert not callable(BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version)
    assert FakeResolve(n_clips=1).PELIGRO_escribir_fuera_de_la_version is False
    assert LiveResolve(object()).PELIGRO_escribir_fuera_de_la_version is False


def test_AUD1_hay_que_escribir_el_nombre_entero_en_las_dos_clases():
    """CASO 1. Un typo es un TypeError, no una proteccion apagada en silencio."""
    with pytest.raises(TypeError):
        FakeResolve(n_clips=1, PELIGRO=True)
    with pytest.raises(TypeError):
        LiveResolve(object(), PELIGRO=True)


# ---------------------------------------------------------------------------
# Caso 2 - que las cinco escrituras llaman DE VERDAD a la regla.
# ---------------------------------------------------------------------------


def _metodos_que_llaman_a_la_regla(clase) -> dict[str, bool]:
    """Por AST: ¿el cuerpo de cada escritura contiene `self._exigir_version_propia(...)`?

    Inmune al `==` (un comentario nuevo no lo rompe) y al `>=` (cinco menciones
    en un docstring no lo salvan): se miran llamadas, no texto.
    """
    fuente = inspect.getsource(sys.modules[clase.__module__])
    arbol = ast.parse(fuente)
    definicion = next(
        n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef) and n.name == clase.__name__
    )
    fuera = {}
    for metodo in ESCRITURAS_DE_GRADO:
        fn = next(
            (
                n
                for n in definicion.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == metodo
            ),
            None,
        )
        if fn is None:
            fuera[metodo] = False
            continue
        fuera[metodo] = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == REGLA
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "self"
            for n in ast.walk(fn)
        )
    return fuera


@pytest.mark.parametrize("clase", [FakeResolve, LiveResolve], ids=["FakeResolve", "LiveResolve"])
def test_AUD2_las_cinco_escrituras_llaman_a_la_regla_por_AST(clase):
    """CASO 2, forma fuerte. Ni `==` ni `>=`: llamadas reales en el AST."""
    mapa = _metodos_que_llaman_a_la_regla(clase)
    for metodo, llama in sorted(mapa.items()):
        print(f"[AUD2-AST] {clase.__name__}.{metodo}: {'llama' if llama else 'NO LLAMA'}")
    faltan = [m for m, ok in mapa.items() if not ok]
    assert not faltan, f"{clase.__name__} no llama a {REGLA} en: {faltan}"


def test_AUD2_el_conteo_de_texto_era_fragil_y_se_deja_demostrado():
    """CASO 2, la prueba de por que el test original se rompio.

    `live.py` menciona el nombre de la regla 6 veces: 5 llamadas y 1 en un
    docstring. O sea que el `==` del revisor no fallaba porque faltara una
    proteccion, y el `>=` del orquestador pasaria igual si de las 6 menciones
    solo 1 fuera una llamada. Las dos formas miden lo que no es.
    """
    texto_live = (CORE / "resolve" / "live.py").read_text(encoding="utf-8")
    texto_fake = (CORE / "resolve" / "fake.py").read_text(encoding="utf-8")
    menciones_live = texto_live.count(REGLA)
    llamadas_live = sum(_metodos_que_llaman_a_la_regla(LiveResolve).values())
    print(f"[AUD2-texto] live.py menciona {REGLA} {menciones_live} veces")
    print(f"[AUD2-texto] fake.py menciona {REGLA} {texto_fake.count(REGLA)} veces")
    print(f"[AUD2-texto] llamadas de verdad en LiveResolve: {llamadas_live} de 5")
    assert menciones_live > llamadas_live, (
        "hoy ya no hay menciones de sobra; si esto cambia, revisa la conclusion del caso 2"
    )


# --- el mismo caso 2, pero por comportamiento y tambien en LiveResolve -------


class _GrafoDoble:
    """Doble del grafo de nodos de Resolve. NO es Resolve: cuenta escrituras."""

    def __init__(self, registro: list[str], n_nodos: int = 3) -> None:
        self._registro = registro
        self._n = n_nodos

    def GetNumNodes(self):  # noqa: N802 - la API real se llama asi
        return self._n

    def SetNodeEnabled(self, idx, on):  # noqa: N802
        self._registro.append(f"SetNodeEnabled({idx},{on})")
        return True

    def ResetAllGrades(self):  # noqa: N802
        self._registro.append("ResetAllGrades")
        return True

    def GetLUT(self, idx):  # noqa: N802
        return ""

    def GetNodeLabel(self, idx):  # noqa: N802
        return f"nodo {idx}"


class _ClipDoble:
    """Doble de un TimelineItem. La version activa es la del USUARIO."""

    def __init__(self, registro: list[str], version: str = "Version 1") -> None:
        self._registro = registro
        self._version = version
        self._grafo = _GrafoDoble(registro)

    def GetNodeGraph(self, capa):  # noqa: N802
        return self._grafo

    def GetCurrentVersion(self):  # noqa: N802
        return self._version

    def SetCDL(self, payload):  # noqa: N802
        self._registro.append("SetCDL")
        return True

    def SetLUT(self, idx, ruta):  # noqa: N802
        self._registro.append(f"SetLUT({idx},{ruta})")
        return True

    def CopyGrades(self, destinos):  # noqa: N802
        self._registro.append("CopyGrades")
        return True


def _live_con_dobles(version="Version 1"):
    """`LiveResolve` con la cache de clips rellenada a mano.

    `LiveResolve.__init__` solo guarda el objeto que se le pasa; el modulo de
    scripting de Resolve solo se importa dentro de `conectar()`, que aqui no se
    llama. Asi que esto no roza Resolve.
    """
    registro: list[str] = []
    vivo = LiveResolve(object())
    vivo._cache = {
        "v1-001": _ClipDoble(registro, version),
        "v1-002": _ClipDoble(registro, version),
    }
    return vivo, registro


def _intentar(bridge, operacion, a="v1-001", b="v1-002"):
    return {
        "set_cdl": lambda: bridge.set_cdl(a, NODE_BALANCE, CDL(slope=(2.0, 2.0, 2.0))),
        "set_lut": lambda: bridge.set_lut(a, NODE_LOOK, "SIDEB/look.cube"),
        "set_node_enabled": lambda: bridge.set_node_enabled(a, 1, False),
        "copy_grades": lambda: bridge.copy_grades(a, [b]),
        "reset_all_grades": lambda: bridge.reset_all_grades(a),
    }[operacion]()


@pytest.mark.parametrize("operacion", ESCRITURAS_DE_GRADO)
def test_AUD2_en_LiveResolve_la_regla_salta_ANTES_de_tocar_la_api(operacion):
    """CASO 2, forma mas fuerte todavia: se ejecuta `LiveResolve` de verdad.

    Contra un doble de la API, no contra Resolve. Si la regla no estuviera,
    el doble registraria la escritura; con la regla, el registro queda vacio.
    """
    vivo, registro = _live_con_dobles(version="Version 1")
    with pytest.raises(EscrituraFueraDeVersion):
        _intentar(vivo, operacion)
    assert registro == [], (
        f"{operacion}: la regla ha saltado DESPUES de escribir en la API: {registro}"
    )


@pytest.mark.parametrize("operacion", ESCRITURAS_DE_GRADO)
def test_AUD2_en_LiveResolve_el_camino_bueno_SI_escribe(operacion):
    """Contrapeso obligatorio: dentro de una version nuestra, se escribe."""
    vivo, registro = _live_con_dobles(version="SIDEB COLOR")
    assert _intentar(vivo, operacion) is True
    assert registro, f"{operacion}: no ha llegado ninguna llamada a la API"
    print(f"[AUD2-vivo] {operacion} -> {registro}")


@pytest.mark.parametrize("version_rara", ["", None, "   ", 0])
def test_AUD2_una_version_que_no_se_sabe_tambien_bloquea_en_LiveResolve(version_rara):
    """La rama `VersionIndeterminada`, que es la que mas miedo da manana."""
    vivo, registro = _live_con_dobles(version=version_rara)
    with pytest.raises(EscrituraFueraDeVersion):
        _intentar(vivo, "set_cdl")
    assert registro == []


def test_AUD2_copy_grades_mira_TODOS_los_destinos_antes_de_copiar_en_LiveResolve():
    """Un solo destino en la version del usuario tiene que abortar la copia."""
    registro: list[str] = []
    vivo = LiveResolve(object())
    vivo._cache = {
        "v1-001": _ClipDoble(registro, "SIDEB COLOR"),
        "v1-002": _ClipDoble(registro, "SIDEB COLOR"),
        "v1-003": _ClipDoble(registro, "Version 1"),  # el del usuario
    }
    with pytest.raises(EscrituraFueraDeVersion):
        vivo.copy_grades("v1-001", ["v1-002", "v1-003"])
    assert registro == [], f"ha copiado algo antes de mirar el tercer destino: {registro}"


# ---------------------------------------------------------------------------
# Caso 3 - la asimetria entre FakeResolve y LiveResolve.
# ---------------------------------------------------------------------------


def test_AUD3_envenenar_la_clase_base_ya_no_apaga_la_regla_en_ninguna():
    """CASO 3. El HALLAZGO del revisor: ¿esta cerrado de verdad?"""
    original = BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version
    try:
        BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True
        falso = FakeResolve(n_clips=1)
        vivo, registro = _live_con_dobles(version="Version 1")
        print(f"[AUD3] con la base envenenada: Fake={falso.PELIGRO_escribir_fuera_de_la_version} "
              f"Live={vivo.PELIGRO_escribir_fuera_de_la_version}")
        assert falso.PELIGRO_escribir_fuera_de_la_version is False
        assert vivo.PELIGRO_escribir_fuera_de_la_version is False, (
            "LiveResolve sigue heredando la via de escape envenenada: el hallazgo E-3 NO esta "
            "cerrado"
        )
        # Y que no es solo el atributo: la escritura sigue bloqueada.
        with pytest.raises(EscrituraFueraDeVersion):
            vivo.set_cdl("v1-001", NODE_BALANCE, CDL())
        assert registro == []
    finally:
        BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = original
    assert FakeResolve(n_clips=1).PELIGRO_escribir_fuera_de_la_version is False
    assert LiveResolve(object()).PELIGRO_escribir_fuera_de_la_version is False


def test_AUD3_ningun_atributo_de_clase_compartido_se_queda_sin_blindar():
    """CASO 3, la parte de "donde hay uno suele haber dos".

    Cualquier atributo de datos declarado en `BaseResolveBridge` que una de las
    dos implementaciones re-asigne en la instancia y la otra no, es la misma
    trampa: se envenena la clase base y una de las dos se entera y la otra no.
    """
    de_clase = {
        n: v
        for n, v in vars(BaseResolveBridge).items()
        if not n.startswith("__") and not callable(v) and not isinstance(v, staticmethod)
    }
    # Tambien las que solo estan anotadas con valor (incognitas lo esta).
    anotadas = set(getattr(BaseResolveBridge, "__annotations__", {}))
    nombres = sorted(set(de_clase) | {a for a in anotadas if hasattr(BaseResolveBridge, a)})
    print(f"[AUD3] atributos de clase de BaseResolveBridge: {nombres}")
    assert nombres, "BaseResolveBridge ya no declara atributos de clase: revisa este test"

    falso = FakeResolve(n_clips=1)
    vivo = LiveResolve(object())
    asimetricos = []
    for nombre in nombres:
        en_fake = nombre in vars(falso)
        en_live = nombre in vars(vivo)
        print(f"[AUD3] {nombre}: instancia en Fake={en_fake} instancia en Live={en_live}")
        if en_fake != en_live:
            asimetricos.append(nombre)
    assert not asimetricos, (
        f"atributos de clase que una implementacion blinda y la otra no: {asimetricos}"
    )


def test_AUD3_las_dos_implementaciones_declaran_la_misma_via_de_escape_en_el_constructor():
    """Y que las dos la aceptan por constructor, con el mismo defecto."""
    for clase in (FakeResolve, LiveResolve):
        firma = inspect.signature(clase.__init__)
        assert VIA_DE_ESCAPE in firma.parameters, f"{clase.__name__} no la acepta por constructor"
        assert firma.parameters[VIA_DE_ESCAPE].default is False, clase.__name__
        print(f"[AUD3] {clase.__name__}.__init__ acepta {VIA_DE_ESCAPE} con defecto False")
