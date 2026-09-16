"""El test que caza tests que pasan sin comprobar nada.

QUÉ PROBLEMA RESUELVE
---------------------
Dos veces en este proyecto ha salido un verde que mentía:

- Día 2: `assert fuente.count("_exigir_version_propia") >= 5`. Pasaba aunque las
  cinco menciones fueran comentarios. No era una aserción floja: no era una aserción.
- Día 3: una cuarentena (`len(fallidos) <= len(conocidos)`) que, arreglado el fallo
  conocido, quedó en `0 <= 1` y dejó de vigilar nada.

La forma general es **una comprobación sobre una colección que puede venir vacía**:
`all([])` es `True`, `not any([])` es `True`, y un `for` que no itera no falla.

CÓMO FUNCIONA
-------------
Se recorre el **AST** de cada `.py` de `tests/` y se buscan tres formas, **solo
cuando la colección sale de algo que la puede dejar vacía en silencio** (ver
`_descubre`): mirar el disco (`glob`, `rglob`, `iterdir`, `listdir`, `os.walk`),
mirar el árbol de widgets (`findChildren`), un filtro (`[x for x in ... if ...]`),
o una función auxiliar del mismo módulo que devuelve una de esas.

1. `for x in FUENTE:` con un `assert` dentro.
2. `for x in FUENTE:` que acumula en una lista y luego `assert not lista`.
3. `malos = [x for x in FUENTE if ...]` y luego `assert not malos`; y
   `assert all(... for x in FUENTE)` / `assert not any(... for x in FUENTE)`.

Se da por **guardado** si antes (en la misma función) hay un `assert` que menciona
`FUENTE` o el nombre que la guarda (`assert ficheros`, `assert len(x) == 5`...), o
si antes del `assert not lista` se afirma algo de otro acumulador del mismo bucle
(el contador de «mirados»).

QUÉ **NO** CAZA (dicho para que nadie crea que caza más)
--------------------------------------------------------
- Colecciones que vienen de un fixture, de un atributo o de una llamada normal
  (`fake.list_nodes(clip)`, `pieles_trabajo`, `est.clips`). Probado: vigilarlas
  daba 52 avisos con la mayoría ruido (tuplas de tamaño fijo como `cdl.slope`,
  `not any(... in warnings)` donde vacío es lo correcto). Esas se revisan a mano.
- `.count()` sobre código fuente: eso es otro fallo (contar comentarios) y no se
  ve desde la forma del test.
- Un filtro `if ...: continue` dentro de un bucle que se salta todo.
- Tests `xfail(strict=True)`: ahí un vacío da XPASS, y `strict` lo pone rojo. Ojo, eso
  no los hace seguros: un `xfail` sin `raises=AssertionError` también cuenta como «fallo
  esperado» un `KeyError` de una columna renombrada.
- Una guarda que menciona la fuente pero no afirma que no esté vacía
  (`assert x.keys() == y.keys()` cuenta como guarda). Se prefiere no avisar.

Si se ensancha, primero se mide cuánto ruido da. Un detector que avisa de todo se
desactiva a la semana.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_TESTS = RAIZ / "tests"

#: Llamadas cuyo resultado sale de mirar algo que puede no estar ahí.
LLAMADAS_QUE_DESCUBREN = frozenset({"glob", "rglob", "iterdir", "listdir", "scandir", "findChildren"})
#: Envoltorios que no cambian si la colección está vacía.
ENVOLTORIOS = frozenset({"sorted", "list", "tuple", "set", "frozenset", "enumerate", "reversed", "iter"})
#: Formas de «esto está vacío».
_VACIO = r"not {n}|{n} == (\[\]|\{{\}}|set\(\)|\(\))|len\({n}\) == 0"

#: **Falsos positivos admitidos.** Clave `(ruta, funcion, fuente)`, valor: la razón
#: en una línea. Sin número de línea: no se rompe cuando alguien edita encima.
EXCEPCIONES: dict[tuple[str, str, str], str] = {
    ("tests/test_gui_titulares.py", "test_ningun_rotulo_de_delta_e_calla_que_estadistico_es",
     "v.findChildren(QLabel)"): "guardado de hecho: el `'ΔE medio' in rotulos` de despues exige QLabels en la ventana",
}

#: **Vacíos REALES que no se han podido arreglar en su día.** No son excepciones:
#: son hallazgos en ficheros que tenían dueño trabajando (día 4, 2026-09-16) y que
#: el revisor de vacíos no podía tocar. Cada uno lleva quién lo tiene que cerrar.
#: `test_los_pendientes_siguen_sin_arreglarse` falla en cuanto se arregla uno
#: (entrada muerta), y `test_barrido_del_repo_sin_pendientes` es un `xfail(strict=True)` que
#: deja el número a la vista en cada pasada.
PENDIENTES: dict[tuple[str, str, str], str] = {
    ("tests/test_gui_identidad.py", "test_ningun_setstylesheet_de_la_gui_pone_ff6a3d_de_fondo",
     "sorted(RAIZ_GUI.glob('*.py'))"): "dueño GUI: si gui/ se mueve, `not culpables` pasa sin leer nada",
    ("tests/test_gui_identidad.py", "test_no_hay_ningun_rojo_de_error_en_toda_la_gui",
     "sorted(RAIZ_GUI.glob('*.py'))"): "dueño GUI: igual",
    ("tests/test_gui_identidad.py", "test_todas_las_cifras_de_la_app_salen_en_monoespaciada",
     "v.findChildren(Cifra)"): "dueño GUI: sin ninguna Cifra visible, `not malas` pasa",
    ("tests/test_gui_identidad.py", "test_los_rotulos_van_en_mayusculas_y_con_el_tracking_de_la_identidad",
     "v.findChildren(Rotulo)"): "dueño GUI: sin ningun Rotulo visible, el bucle no afirma nada",
    ("tests/test_gui_pantallas.py", "test_el_mapa_de_cobertura_distingue_lo_medido_de_lo_inventado",
     "cubiertas"): "dueño GUI: se guarda `libres` pero no `cubiertas`",
    ("tests/test_gui_regla_de_oro.py", "test_ningun_modulo_de_la_gui_llama_a_una_escritura_cruda",
     "sorted(RAIZ_GUI.glob('*.py'))"): "dueño GUI: si gui/ se mueve, pasa sin leer nada",
    ("tests/test_gui_regla_de_oro.py", "test_la_gui_no_toca_la_via_de_escape_de_la_regla_de_oro",
     "sorted(RAIZ_GUI.glob('*.py'))"): "dueño GUI: igual",
    ("tests/test_gui_regla_de_oro.py", "test_la_gui_no_importa_el_puente_de_verdad",
     "sorted(RAIZ_GUI.glob('*.py'))"): "dueño GUI: igual",
    ("tests/test_gui_reverse.py", "test_la_gui_no_redefine_ningun_umbral_de_veredicto",
     "_modulos_gui()"): "dueño GUI: `_modulos_gui()` vacío deja `not culpables` en verde",
    ("tests/test_gui_reverse.py", "test_la_gui_no_construye_un_veredicto_positivo_de_lut_puro",
     "_modulos_gui()"): "dueño GUI: igual",
    ("tests/test_gui_reverse.py", "test_la_gui_no_reimplementa_confidence_level",
     "_modulos_gui()"): "dueño GUI: igual",
    ("tests/test_gui_titulares.py", "test_en_gui_no_hay_un_limite_de_criterio_escrito_a_mano",
     "sorted(RAIZ_GUI.glob('*.py'))"): "dueño GUI (fichero nuevo del dia 4): si gui/ se mueve, `not malos` pasa sin leer nada",
}


# ---------------------------------------------------------------------------
# El detector
# ---------------------------------------------------------------------------


def _nodos_propios(fn: ast.AST):
    """Los nodos de `fn` sin entrar en funciones, lambdas ni clases anidadas."""
    pila = list(fn.body)
    while pila:
        n = pila.pop()
        yield n
        for h in ast.iter_child_nodes(n):
            if not isinstance(h, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef):
                pila.append(h)


def _descubre(e: ast.expr, helpers: set[str], nombres: set[str]) -> bool:
    """¿La colección sale de algo que la puede dejar vacía en silencio?

    Solo se mira la expresión de arriba (quitando `sorted`, `enumerate`...): un
    filtro metido en un argumento no hace arriesgado lo que devuelve la llamada.
    """
    while isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id in ENVOLTORIOS and e.args:
        e = e.args[0]
    if isinstance(e, ast.Call):
        f = e.func
        if isinstance(f, ast.Attribute):
            if f.attr == "walk":  # os.walk si; ast.walk no
                return isinstance(f.value, ast.Name) and f.value.id == "os"
            return f.attr in LLAMADAS_QUE_DESCUBREN
        return isinstance(f, ast.Name) and (f.id in LLAMADAS_QUE_DESCUBREN or f.id in helpers)
    if isinstance(e, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
        return any(g.ifs or _descubre(g.iter, helpers, nombres) for g in e.generators)
    if isinstance(e, ast.Name):
        return e.id in nombres
    return False


def _helpers_que_descubren(arbol: ast.Module) -> set[str]:
    """Funciones del módulo que devuelven (o van soltando) una colección arriesgada."""
    helpers: set[str] = set()
    cambiado = True
    while cambiado:
        cambiado = False
        for fn in arbol.body:
            if not isinstance(fn, ast.FunctionDef) or fn.name in helpers:
                continue
            for n in _nodos_propios(fn):
                valor = None
                if isinstance(n, ast.Return):
                    valor = n.value
                elif isinstance(n, ast.For) and any(
                    isinstance(x, ast.Yield | ast.YieldFrom) for b in n.body for x in ast.walk(b)
                ):
                    valor = n.iter
                if valor is not None and _descubre(valor, helpers, set()):
                    helpers.add(fn.name)
                    cambiado = True
                    break
    return helpers


def _menciona(texto: str, buscados: set[str]) -> bool:
    return any(re.search(r"(?<![\w.])" + re.escape(b) + r"(?!\w)", texto) for b in buscados)


def _acumuladores(cuerpo: list[ast.stmt]) -> set[str]:
    fuera: set[str] = set()
    for b in cuerpo:
        for m in ast.walk(b):
            if (
                isinstance(m, ast.Call)
                and isinstance(m.func, ast.Attribute)
                and m.func.attr in ("append", "extend", "add", "update", "setdefault")
                and isinstance(m.func.value, ast.Name)
            ):
                fuera.add(m.func.value.id)
            elif isinstance(m, ast.AugAssign) and isinstance(m.target, ast.Name):
                fuera.add(m.target.id)
            elif (
                isinstance(m, ast.Assign)
                and isinstance(m.targets[0], ast.Subscript)
                and isinstance(m.targets[0].value, ast.Name)
            ):
                fuera.add(m.targets[0].value.id)
    return fuera


def _es_xfail_estricto(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Un `xfail(strict=True)` espera que el assert falle: si la coleccion viene vacia,
    el assert pasa, sale XPASS y `strict` lo pone rojo. Ahi el vacio no es silencioso."""
    return any(
        isinstance(d, ast.Call)
        and ast.unparse(d.func).endswith("xfail")
        and any(k.arg == "strict" and isinstance(k.value, ast.Constant) and k.value.value is True
                for k in d.keywords)
        for d in fn.decorator_list
    )


def _guardado(e: ast.expr, antes_de: int, asserts: list[tuple[int, str]], riesgo: set[str]) -> bool:
    """¿Hay, antes de `antes_de`, un assert que mencione la colección o el nombre que la guarda?"""
    buscados = {ast.unparse(e)} | {m.id for m in ast.walk(e) if isinstance(m, ast.Name) and m.id in riesgo}
    return any(linea < antes_de and _menciona(t, buscados) for linea, t in asserts)


def _linea_de_vacio(nombre: str, desde: int, asserts: list[tuple[int, str]]) -> int | None:
    """La línea del primer `assert not nombre` (o `nombre == []`...) después de `desde`."""
    patron = _VACIO.format(n=re.escape(nombre))
    return next((linea for linea, t in asserts if linea > desde and re.fullmatch(patron, t)), None)


def vacios_en(fuente: str, ruta: str = "<fragmento>") -> list[tuple[str, int, str, str, str]]:
    """`(ruta, linea, funcion, forma, fuente_de_la_coleccion)` por cada hallazgo."""
    arbol = ast.parse(fuente)
    helpers = _helpers_que_descubren(arbol)
    fuera: set[tuple[str, int, str, str, str]] = set()
    for fn in ast.walk(arbol):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) or fn.name in helpers:
            continue
        if _es_xfail_estricto(fn):
            continue
        propios = list(_nodos_propios(fn))
        riesgo: set[str] = set()
        for n in sorted(
            (x for x in propios if isinstance(x, ast.Assign)), key=lambda x: x.lineno
        ):
            if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and _descubre(n.value, helpers, riesgo):
                riesgo.add(n.targets[0].id)
        asserts = sorted((a.lineno, ast.unparse(a.test)) for a in propios if isinstance(a, ast.Assert))

        for n in propios:
            if isinstance(n, ast.Assert):
                t, llamada, forma = n.test, None, ""
                if (
                    isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)
                    and isinstance(t.operand, ast.Call) and isinstance(t.operand.func, ast.Name)
                    and t.operand.func.id == "any"
                ):
                    llamada, forma = t.operand, "assert not any"
                elif isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and t.func.id == "all":
                    llamada, forma = t, "assert all"
                if llamada is None or not llamada.args:
                    continue
                arg = llamada.args[0]
                it = arg.generators[0].iter if isinstance(arg, ast.GeneratorExp | ast.ListComp) else arg
                if _descubre(it, helpers, riesgo) and not _guardado(it, n.lineno, asserts, riesgo):
                    fuera.add((ruta, n.lineno, fn.name, forma, ast.unparse(it)))

            elif isinstance(n, ast.For | ast.AsyncFor):
                if not _descubre(n.iter, helpers, riesgo) or _guardado(n.iter, n.lineno, asserts, riesgo):
                    continue
                if any(isinstance(m, ast.Assert) for b in n.body for m in ast.walk(b)):
                    fuera.add((ruta, n.lineno, fn.name, "for con assert", ast.unparse(n.iter)))
                    continue
                acumula = _acumuladores(n.body)
                for v in acumula:
                    linea = _linea_de_vacio(v, n.lineno, asserts)
                    if linea is None:
                        continue
                    otros = acumula - {v}
                    vigilado = any(n.lineno < l2 < linea and _menciona(t2, otros) for l2, t2 in asserts)
                    if not vigilado:
                        fuera.add((ruta, n.lineno, fn.name, "for que acumula y se afirma vacio",
                                   ast.unparse(n.iter)))

            elif (
                isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                and isinstance(n.value, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp)
            ):
                origen = n.value.generators[0].iter
                if not _descubre(origen, helpers, riesgo):
                    continue
                linea = _linea_de_vacio(n.targets[0].id, n.lineno, asserts)
                if linea is not None and not _guardado(origen, linea, asserts, riesgo):
                    fuera.add((ruta, n.lineno, fn.name, "filtro que se afirma vacio", ast.unparse(origen)))
    return sorted(fuera, key=lambda h: h[1])


def _ficheros_de_tests() -> list[Path]:
    return sorted(
        p for p in CARPETA_TESTS.rglob("*.py")
        if "__pycache__" not in p.parts and p.parent.name != "media"
    )


def _barrido() -> list[tuple[str, int, str, str, str]]:
    fuera = []
    for p in _ficheros_de_tests():
        fuera.extend(vacios_en(p.read_text(encoding="utf-8"), str(p.relative_to(RAIZ))))
    return fuera


def _clave(h: tuple[str, int, str, str, str]) -> tuple[str, str, str]:
    return (h[0], h[2], h[4])


# ---------------------------------------------------------------------------
# CONTROL NEGATIVO: fragmentos plantados que TIENE que cazar
# ---------------------------------------------------------------------------

PLANTADOS: dict[str, str] = {
    "for con assert sobre un glob": """
        def test_x():
            for p in sorted(RAIZ.glob("*.py")):
                assert "import resolve" not in p.read_text()
    """,
    "for que acumula sobre un rglob y afirma vacio": """
        def test_x():
            culpables = []
            for p in (RAIZ / "core").rglob("*.py"):
                if "tempfile" in p.read_text():
                    culpables.append(p.name)
            assert not culpables, culpables
    """,
    "helper que suelta un glob": """
        def _modulos():
            for p in sorted(RAIZ.glob("*.py")):
                yield p
        def test_x():
            malos = []
            for p in _modulos():
                malos.append(p)
            assert malos == []
    """,
    "filtro que se afirma vacio (el de la cuarentena)": """
        def test_x(filas):
            sel = [f for f in filas if f["A"] == "A2 interior calido"]
            malos = {f["B"]: f["max"] for f in sel if not f["max"] < 3.0}
            assert not malos, malos
    """,
    "assert all sobre findChildren": """
        def test_x(v):
            assert all(es_mono(lab.font()) for lab in v.findChildren(Cifra))
    """,
    "assert not any sobre un nombre filtrado": """
        def test_x(fallidos_posibles):
            vivos = [w for w in fallidos_posibles if w.vivo]
            assert not any(not mide_mono(w) for w in vivos)
    """,
    "guarda DESPUES del assert no vale": """
        def test_x():
            ficheros = sorted(RAIZ.glob("*.py"))
            for p in ficheros:
                assert p.stat().st_size < 10_000
            assert ficheros
    """,
}


@pytest.mark.parametrize("nombre", sorted(PLANTADOS))
def test_CONTROL_NEGATIVO_caza_cada_forma_plantada(nombre):
    hallazgos = vacios_en(textwrap.dedent(PLANTADOS[nombre]), f"plantado: {nombre}")
    print(f"\n[CONTROL-] {nombre}: {hallazgos}")
    assert len(hallazgos) == 1, f"el detector no ha visto el vacio plantado «{nombre}»: {hallazgos}"


# ---------------------------------------------------------------------------
# CONTROL POSITIVO: fragmentos correctos (o ruido conocido) que NO debe cazar
# ---------------------------------------------------------------------------

LIMPIOS: dict[str, str] = {
    "glob con guarda antes": """
        def test_x():
            ficheros = sorted(RAIZ.glob("*.py"))
            assert ficheros, "no hay nada que comprobar"
            for p in ficheros:
                assert "resolve" not in p.read_text()
    """,
    "guarda escrita sobre la misma llamada": """
        def test_x(paquete):
            assert _ficheros(paquete)
            culpables = {}
            for f in _ficheros(paquete):
                culpables[f.name] = 1
            assert culpables == {}
        def _ficheros(paquete):
            return sorted((RAIZ / paquete).rglob("*.py"))
    """,
    "contador de mirados afirmado antes del vacio": """
        def test_x(v):
            mirados, fallos = 0, []
            for w in v.findChildren(QWidget):
                mirados += 1
                if w.mal:
                    fallos.append(w)
            assert mirados > 50
            assert not fallos
    """,
    "filtro guardado con len": """
        def test_x(montaje):
            fiables = [t for t in montaje.tramos if t.n >= 25]
            assert len(fiables) == 5
            for t in fiables:
                assert t.ok
    """,
    "filtro guardado antes del vacio aunque despues de la asignacion": """
        def test_x(v):
            marcadas = [lab for lab in v.findChildren(QLabel) if "cifra" in lab.objectName()]
            malas = [lab for lab in marcadas if not mono(lab)]
            assert marcadas
            assert not malas
    """,
    "ast.walk no es mirar el disco": """
        def test_x(arbol):
            for nodo in ast.walk(arbol):
                assert not isinstance(nodo, ast.Global)
    """,
    "tuplas literales y rangos": """
        CASOS = ("a", "b")
        def test_x():
            for caso in CASOS:
                for i in range(3):
                    assert caso * i is not None
            assert all(x > 0 for x in (1, 2, 3))
    """,
    "ausencias donde vacio es lo correcto (no se vigila)": """
        def test_x(analisis):
            assert not any("Asumo" in a for a in analisis.warnings)
    """,
    "xfail estricto: el vacio sale como XPASS y es rojo": """
        @pytest.mark.xfail(strict=True, reason="12 de 12 por encima de 3.0")
        def test_x(filas):
            sel = [f for f in filas if f["A"] == "A2"]
            malos = [f for f in sel if f["max"] >= 3.0]
            assert not malos
    """,
    "un filtro que no sale de nada arriesgado y se afirma no vacio": """
        def test_x(informe):
            problemas = [p for p in informe.problemas if p.codigo == "gamut"]
            assert problemas
            assert all(p.gravedad == "aviso" for p in problemas)
    """,
}


@pytest.mark.parametrize("nombre", sorted(LIMPIOS))
def test_CONTROL_POSITIVO_no_caza_lo_que_esta_bien(nombre):
    hallazgos = vacios_en(textwrap.dedent(LIMPIOS[nombre]), f"limpio: {nombre}")
    assert hallazgos == [], f"falso positivo en «{nombre}»: {hallazgos}"


# ---------------------------------------------------------------------------
# El barrido del repo
# ---------------------------------------------------------------------------


def test_el_barrido_mira_ficheros_de_verdad():
    """El detector de vacíos no puede estar él mismo vacío."""
    ficheros = _ficheros_de_tests()
    print(f"\n[SIN-VACIO] ficheros de tests mirados: {len(ficheros)}")
    assert len(ficheros) > 30, f"solo {len(ficheros)} ficheros: ¿se ha movido tests/?"
    assert Path(__file__).resolve() in ficheros


def test_ningun_test_comprueba_una_coleccion_que_puede_venir_vacia_sin_guarda():
    hallazgos = _barrido()
    nuevos = [h for h in hallazgos if _clave(h) not in EXCEPCIONES and _clave(h) not in PENDIENTES]
    print(f"\n[SIN-VACIO] hallazgos: {len(hallazgos)} "
          f"(pendientes conocidos: {len(PENDIENTES)}, excepciones: {len(EXCEPCIONES)})")
    for h in hallazgos:
        marca = "PENDIENTE" if _clave(h) in PENDIENTES else "EXCEPCION" if _clave(h) in EXCEPCIONES else "NUEVO"
        print(f"[SIN-VACIO]   {marca:<9} {h[0]}:{h[1]} {h[2]} [{h[3]}] {h[4]}")
    assert not nuevos, (
        "test que puede pasar sin comprobar nada: la coleccion puede venir vacia y no se "
        "comprueba antes. Pon delante `assert coleccion, \"no hay nada que comprobar: <por que "
        "podria estar vacia>\"`. Si de verdad es un falso positivo, a EXCEPCIONES con su razon.\n"
        + "\n".join(f"  - {h[0]}:{h[1]} {h[2]} [{h[3]}] {h[4]}" for h in nuevos)
    )


def test_los_pendientes_siguen_sin_arreglarse():
    """Una entrada de PENDIENTES o EXCEPCIONES que ya no sale es una entrada muerta."""
    vistos = {_clave(h) for h in _barrido()}
    muertas = sorted((set(PENDIENTES) | set(EXCEPCIONES)) - vistos)
    assert not muertas, f"ya no salen, quitalas de la lista: {muertas}"


def test_la_lista_de_excepciones_sigue_siendo_corta():
    assert len(EXCEPCIONES) <= 15, (
        f"{len(EXCEPCIONES)} excepciones. Si hace falta tanta lista, el detector da ruido "
        "y hay que afinar la regla, no ampliar la lista."
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "12 vacios reales encontrados el 2026-09-16 en tests/test_gui_identidad.py (4), "
        "test_gui_regla_de_oro.py (3), test_gui_reverse.py (3), test_gui_pantallas.py (1) y "
        "test_gui_titulares.py (1), "
        "ficheros con dueño trabajando ese dia; "
        "falta poner la guarda `assert coleccion` delante. Se reproduce con: "
        ".venv/bin/python -m pytest tests/test_sin_vacio.py -s -k barrido_del_repo_sin_pendientes. "
        "Se cierra vaciando PENDIENTES; entonces este xfail pasa a XPASS y hay que quitarlo."
    ),
)
def test_barrido_del_repo_sin_pendientes():
    assert not PENDIENTES, f"{len(PENDIENTES)} vacios reales pendientes de guarda: {sorted(PENDIENTES)}"
