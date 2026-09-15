"""El test que impide que los umbrales se vuelvan a desordenar.

QUÉ PROBLEMA RESUELVE
---------------------
El día 2 se encontró que `gui/reverse_puente.py` tenía su propia definición, más
floja, de «esto es un LUT puro» (`reproducible > 0.92`, frente al 0.95 **y**
percentil 95 por debajo de 1.0 ΔE2000 del núcleo). No fue un bug suelto: fue la
demostración de que un criterio de decisión se puede escribir dos veces y que
nadie se entera. `core/umbrales.py` lo centraliza; este archivo es lo que impide
que se descoloque otra vez en dos semanas.

CÓMO FUNCIONA
-------------
Se recorre el **AST** de cada `.py` de los paquetes vigilados buscando
**comparaciones de orden** (`<`, `>`, `<=`, `>=`) contra un **literal numérico
no trivial**. Eso caza `if reproducible > 0.92` y no caza `if len(x) > 0`.

Por qué el AST y no un `grep`: un `grep` de `0.92` encuentra el número dentro de
un comentario, dentro de una cadena de texto y dentro de una lista de constantes
medidas, y no encuentra `if reproducible>0.92` sin espacios. El AST ve la
estructura, así que ve exactamente lo que se quiere ver: un número tomando una
decisión.

QUÉ **NO** CAZA (dicho aquí para que nadie crea que caza más de lo que caza)
---------------------------------------------------------------------------
- `if x > UMBRAL * 0.9`: el lado derecho es una operación, no un literal. Un
  umbral derivado de otro pasa. Se ha dejado así a propósito: `contenido.py`
  tiene un `UMBRAL_HUELLA * 0.5` legítimo y escribir el 0.25 a pelo sería peor.
- `np.percentile(residuo, 95)`: un literal como **argumento** no es una
  comparación. Un umbral escondido en una llamada pasa.
- `d = {"corte": 0.92}` y `UMBRAL = 0.92` fuera de `core/umbrales.py`: no son
  comparaciones. Eso lo cubre el otro test de este archivo,
  `test_ningun_umbral_centralizado_se_redefine_fuera_de_core_umbrales`.
- `==` y `!=`: no son comparaciones de orden. Un `if size == 33` pasa.
- Igualdades y umbrales dentro de `gui/`: **hoy no**, ver `PAQUETES`.

CÓMO SE AÑADE `gui/`
--------------------
Una línea: añadir `"gui"` a `PAQUETES`. La migración de `gui/` viene después de
esto, y cuando llegue, esto es todo lo que hay que tocar aquí.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from core import umbrales

RAIZ = Path(__file__).resolve().parent.parent

#: Los paquetes que se vigilan. **Añadir `gui/` es añadir una cadena a esta
#: tupla**, y nada más: la migración de la GUI viene después de que exista
#: `core/umbrales.py`, que es lo que este día entrega.
PAQUETES: tuple[str, ...] = ("core",)

#: El archivo donde un umbral SÍ puede ser un literal, porque es el único sitio
#: donde se escribe un umbral.
CASA_DE_LOS_UMBRALES = Path("core/umbrales.py")

#: Números que no son un umbral por sí solos: `> 0` es «hay algo», `>= 1` es «no
#: está vacío», `< 2` es «no hay pareja», `0.5` es «la mitad». Si uno de estos
#: llegara a ser un criterio de verdad, tendría que llevar nombre igual, pero
#: dejarlos fuera es lo que separa un test que sirve de uno que da la lata con
#: cada índice del código.
TRIVIALES: frozenset[float] = frozenset({0, 1, -1, 2, -2, 0.5, -0.5, 3, 100})

#: Por debajo de esta magnitud un literal no puede ser un criterio de decisión
#: de esta aplicación: es epsilon de máquina. Ningún ΔE2000, ninguna fracción y
#: ningún recuento de píxeles vive en 1e-9. Es una **regla**, no una excepción,
#: y por eso no está en la lista de abajo: evita que la lista se llene de
#: `1e-12` y deje de leerse. Ojo con dónde está el corte: `1e-6` y `1e-5` SÍ se
#: cazan, porque `UMBRAL_RECORRIDO_LUT_PLANO` y `TOL_MONOTONIA` valen eso.
SUELO_DE_EPSILON = 1e-8

#: **La lista de excepciones. Si crece sin freno, este test dejó de servir.**
#: Clave `(ruta relativa, valor)`, valor: la razón, en una línea. No lleva
#: número de línea a propósito: un umbral nuevo en el mismo archivo con el mismo
#: valor exacto es tan improbable que no compensa la fragilidad de reindexar
#: esta tabla cada vez que alguien añade una función.
EXCEPCIONES: dict[tuple[str, float], str] = {
    ("core/color/perceptual.py", 180.0): "grados del circulo de tono: geometria de la formula ΔE2000, no un umbral",
    ("core/color/perceptual.py", 360.0): "la vuelta completa del circulo de tono, por lo mismo",
    ("core/io/cube.py", 65536.0): "tope de lado de un HALD: limite del formato, no un criterio de calidad",
    ("core/io/cube.py", 12.0): "decimales maximos al escribir un .cube: limite del formato",
    ("core/matching/cdl_fit.py", 1e-06): "guarda de division: |saturacion| practicamente cero antes de dividir",
    ("core/reverse/alineado.py", 8.0): "minimo de muestras para que np.gradient tenga algo que derivar",
    ("core/reverse/alineado.py", 16.0): "lado minimo en px para que la ventana de Hann y la FFT tengan sentido",
    ("core/reverse/diagnostico.py", 16.0): "minimo de puntos finitos para ajustar un plano o una parabola",
    ("core/reverse/invertir.py", 4.0): "minimo de puntos para una covarianza 3x3: por debajo es singular",
    ("core/reverse/relleno.py", 8.0): "minimo de filas para unos minimos cuadrados de la base afin",
}


# ---------------------------------------------------------------------------
# El detector
# ---------------------------------------------------------------------------


class _Hallazgo:
    __slots__ = ("linea", "ruta", "texto", "valor")

    def __init__(self, ruta: str, linea: int, valor: float, texto: str) -> None:
        self.ruta = ruta
        self.linea = linea
        self.valor = valor
        self.texto = texto

    def __repr__(self) -> str:  # pragma: no cover - solo sale en el mensaje de fallo
        return f"{self.ruta}:{self.linea}: compara contra {self.valor!r} -> {self.texto}"


class _Buscador(ast.NodeVisitor):
    """Comparaciones de orden contra un literal numerico no trivial."""

    def __init__(self, ruta: str, fuente: str) -> None:
        self.ruta = ruta
        self.lineas = fuente.splitlines()
        self.hallazgos: list[_Hallazgo] = []

    def visit_Compare(self, nodo: ast.Compare) -> None:  # noqa: N802 - lo manda ast
        for op, derecha in zip(nodo.ops, nodo.comparators, strict=True):
            if not isinstance(op, (ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
                continue
            for lado in (nodo.left, derecha):
                valor = _literal_numerico(lado)
                if valor is None or _es_trivial(valor):
                    continue
                texto = self.lineas[lado.lineno - 1].strip() if lado.lineno <= len(self.lineas) else ""
                self.hallazgos.append(_Hallazgo(self.ruta, lado.lineno, valor, texto))
        self.generic_visit(nodo)


def _literal_numerico(nodo: ast.AST) -> float | None:
    """El valor si el nodo es un numero literal (`True`/`False` no cuentan)."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
        if isinstance(nodo.value, bool):
            return None
        return float(nodo.value)
    return None


def _es_trivial(valor: float) -> bool:
    return valor in TRIVIALES or abs(valor) < SUELO_DE_EPSILON


def buscar_literales(fuente: str, ruta: str = "<memoria>") -> list[_Hallazgo]:
    """El detector, aislado, para poder pasarle un fragmento a mano.

    Existe separado del recorrido de ficheros **justo para el control negativo**:
    sin poder darle un fragmento con un literal puesto a proposito no hay forma
    de saber si el barrido encuentra algo o si siempre dice que si.
    """
    buscador = _Buscador(ruta, fuente)
    buscador.visit(ast.parse(fuente))
    return buscador.hallazgos


def _ficheros_vigilados() -> list[Path]:
    ficheros: list[Path] = []
    for paquete in PAQUETES:
        ficheros.extend(sorted((RAIZ / paquete).rglob("*.py")))
    return ficheros


def _barrido() -> list[_Hallazgo]:
    fuera: list[_Hallazgo] = []
    for fichero in _ficheros_vigilados():
        rel = fichero.relative_to(RAIZ)
        if rel == CASA_DE_LOS_UMBRALES:
            continue
        fuera.extend(buscar_literales(fichero.read_text(encoding="utf-8"), str(rel)))
    return fuera


# ---------------------------------------------------------------------------
# CONTROL NEGATIVO
# Sin esto no se sabe si el barrido encuentra algo o si siempre dice que si.
# ---------------------------------------------------------------------------


FRAGMENTO_CON_UMBRAL = textwrap.dedent(
    """
    def es_un_lut_puro(reproducible, residuo_p95, hotspots):
        # Exactamente el bug del dia 2: un criterio mas flojo, escrito aparte.
        return reproducible > 0.92 and not hotspots
    """
)

FRAGMENTO_LIMPIO = textwrap.dedent(
    """
    from core.umbrales import UMBRAL_REPRODUCIBLE_PURO, UMBRAL_DE_PURO

    def es_un_lut_puro(reproducible, residuo_p95, hotspots):
        if len(hotspots) > 0:
            return False
        if reproducible < 0:
            return False
        for i in range(2):
            _ = i
        return reproducible >= UMBRAL_REPRODUCIBLE_PURO and residuo_p95 <= UMBRAL_DE_PURO
    """
)


def test_CONTROL_NEGATIVO_el_detector_caza_el_umbral_del_dia_2(capsys):
    """Se le mete a proposito el literal de `gui/reverse_puente.py` y tiene que verlo."""
    hallazgos = buscar_literales(FRAGMENTO_CON_UMBRAL, "fragmento_plantado.py")
    with capsys.disabled():
        for h in hallazgos:
            print(f"[CONTROL-] {h!r}")
    assert len(hallazgos) == 1, f"el detector no vio el umbral plantado: {hallazgos}"
    assert hallazgos[0].valor == pytest.approx(0.92)
    assert "0.92" in hallazgos[0].texto


@pytest.mark.parametrize(
    "fragmento",
    [
        "x = 1\nif len(datos) > 0:\n    pass\n",
        "if indice >= 2:\n    pass\n",
        "if fraccion > 0.5:\n    pass\n",
        "if peso < 1e-12:\n    pass\n",
        "if nombre == 33:\n    pass\n",
        "if valor > UMBRAL_REPRODUCIBLE_PURO:\n    pass\n",
    ],
)
def test_CONTROL_NEGATIVO_el_detector_no_da_la_lata_con_lo_que_no_es_un_umbral(fragmento):
    """Un test que dijera que si a todo seria peor que no tenerlo."""
    assert buscar_literales(fragmento, "fragmento_inocente.py") == []


def test_CONTROL_NEGATIVO_un_fragmento_bien_escrito_pasa_entero(capsys):
    hallazgos = buscar_literales(FRAGMENTO_LIMPIO, "fragmento_bueno.py")
    with capsys.disabled():
        print(f"[CONTROL+] fragmento bien escrito -> {len(hallazgos)} hallazgos")
    assert hallazgos == []


# ---------------------------------------------------------------------------
# El barrido de verdad
# ---------------------------------------------------------------------------


def test_ningun_umbral_suelto_en_los_paquetes_vigilados(capsys):
    """Ni un literal de umbral fuera de `core/umbrales.py`, salvo la lista de arriba."""
    sin_excusa = [h for h in _barrido() if (h.ruta, h.valor) not in EXCEPCIONES]
    with capsys.disabled():
        print(f"[BARRIDO] paquetes vigilados: {PAQUETES}")
        print(f"[BARRIDO] ficheros mirados: {len(_ficheros_vigilados())}")
        print(f"[BARRIDO] excepciones declaradas: {len(EXCEPCIONES)}")
        print(f"[BARRIDO] literales de umbral sin excusa: {len(sin_excusa)}")
    assert not sin_excusa, (
        "hay un umbral escrito como numero suelto fuera de core/umbrales.py.\n"
        "Si es un criterio de decision, llevatelo alli con su unidad y su porque.\n"
        "Si de verdad no lo es, anadelo a EXCEPCIONES con la razon en una linea.\n"
        + "\n".join(f"  - {h!r}" for h in sin_excusa)
    )


def test_la_lista_de_excepciones_no_tiene_entradas_muertas(capsys):
    """Una excepción que ya no corresponde a nada es la forma en que esta lista
    crece hasta dejar de leerse. Si el código la quitó, la lista se queda corta."""
    vistos = {(h.ruta, h.valor) for h in _barrido()}
    muertas = sorted(set(EXCEPCIONES) - vistos)
    with capsys.disabled():
        for clave, razon in sorted(EXCEPCIONES.items()):
            print(f"[EXCEPCION] {clave[0]} {clave[1]!r}: {razon}")
    assert not muertas, f"excepciones que ya no hacen falta, quitalas: {muertas}"


def test_la_lista_de_excepciones_sigue_siendo_corta():
    """Un numero, no una opinion. Si esto se pone rojo no es que haga falta
    subirlo: es que alguien esta metiendo umbrales sueltos en `core/`."""
    assert len(EXCEPCIONES) <= 15, (
        f"{len(EXCEPCIONES)} excepciones. Esta lista existe para leerse entera de un "
        "vistazo; si no se puede, el test ya no protege nada."
    )


# ---------------------------------------------------------------------------
# La otra mitad: que nadie REDEFINA un umbral centralizado
# (el barrido de comparaciones no ve un `UMBRAL_X = 0.92` suelto)
# ---------------------------------------------------------------------------


def test_ningun_umbral_centralizado_se_redefine_fuera_de_core_umbrales(capsys):
    """Esto es literalmente el bug de `gui/reverse_puente.py`, visto por el otro lado.

    Un modulo puede **reexportar** un umbral (`from core.umbrales import X`), que
    es lo que hacen hoy `reverse.diagnostico`, `io.qc`, `matching.confianza` y
    compania para no romper a quien los importe. Lo que no puede es volver a
    ponerle un valor.
    """
    centralizados = set(umbrales.__all__)
    reasignados: list[str] = []
    for fichero in _ficheros_vigilados():
        rel = fichero.relative_to(RAIZ)
        if rel == CASA_DE_LOS_UMBRALES:
            continue
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            objetivos: list[ast.expr] = []
            if isinstance(nodo, ast.Assign):
                objetivos = list(nodo.targets)
            elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
                objetivos = [nodo.target]
            for destino in objetivos:
                if isinstance(destino, ast.Name) and destino.id in centralizados:
                    reasignados.append(f"{rel}:{destino.lineno}: {destino.id}")
    with capsys.disabled():
        print(f"[REDEFINICION] umbrales centralizados: {len(centralizados)}")
        print(f"[REDEFINICION] redefinidos fuera de core/umbrales.py: {len(reasignados)}")
    assert not reasignados, (
        "un umbral de `core.umbrales` esta escrito otra vez fuera de su casa. Eso es "
        "exactamente el bug de gui/reverse_puente.py: dos definiciones del mismo "
        "criterio y nadie garantiza que coincidan.\n" + "\n".join(reasignados)
    )


def test_core_umbrales_no_importa_nada_de_core(capsys):
    """Si lo hiciera, `core/contracts.py` no podria importarlo: habria ciclo."""
    arbol = ast.parse((RAIZ / CASA_DE_LOS_UMBRALES).read_text(encoding="utf-8"))
    importados: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:  # un import relativo dentro de core/ es un import de core/
                importados.append("." * nodo.level + (nodo.module or ""))
            elif nodo.module:
                importados.append(nodo.module)
    with capsys.disabled():
        print(f"[CICLOS] core/umbrales.py importa: {importados or 'nada'}")
    malos = [m for m in importados if m == "core" or m.startswith(("core.", "."))]
    assert not malos, f"core/umbrales.py no puede importar nada de core/: {malos}"


def test_cada_umbral_centralizado_lleva_unidad_escrita(capsys):
    """La unidad es parte del numero.

    Un `1.0` que es ΔE2000 y un `0.95` que es una fraccion no son la misma clase
    de numero, y confundirlos es exactamente como aparecio un criterio mas flojo
    en otro modulo. Se comprueba que cada constante lleva encima un comentario
    `#:` que dice **Unidad:**, o que hereda el valor de otra que la lleva.
    """
    fuente = (RAIZ / CASA_DE_LOS_UMBRALES).read_text(encoding="utf-8")
    lineas = fuente.splitlines()
    arbol = ast.parse(fuente)
    sin_unidad: list[str] = []
    for nodo in arbol.body:
        nombre = None
        if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            nombre = nodo.target.id
        elif isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(
            nodo.targets[0], ast.Name
        ):
            nombre = nodo.targets[0].id
        if nombre is None or nombre.startswith("_") or nombre == "__all__":
            continue
        # El bloque de comentarios `#:` que va justo encima.
        bloque: list[str] = []
        i = nodo.lineno - 2
        while i >= 0 and lineas[i].lstrip().startswith("#"):
            bloque.append(lineas[i])
            i -= 1
        if not any("Unidad:" in linea for linea in bloque):
            sin_unidad.append(nombre)
    with capsys.disabled():
        print(f"[UNIDADES] constantes publicas en core/umbrales.py: {len(umbrales.__all__)}")
        print(f"[UNIDADES] sin unidad escrita: {sin_unidad or 'ninguna'}")
    assert not sin_unidad, f"estas constantes no dicen en que unidad estan: {sin_unidad}"


def test_todo_lo_publico_esta_en_all():
    """Para que `__all__` no se quede atras y alguien crea que un umbral no existe."""
    declarado = set(umbrales.__all__)
    real = {
        n
        for n in vars(umbrales)
        if not n.startswith("_") and isinstance(vars(umbrales)[n], (int, float, dict))
    }
    assert real == declarado, f"descuadre entre __all__ y el modulo: {real ^ declarado}"
