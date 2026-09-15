"""REVISION OLA 1 - agente G: el limite duro de la noche.

**Ningun modulo puede escribir fuera de la ruta que le pasan.** Es la convencion
7 de `CONTRATOS.md` ("cero escrituras en el sistema, en `~` o en `/Volumes`") y
es lo que hay que cazar hoy, no mañana con un disco de produccion delante.

Se comprueba de dos formas, porque una sola no basta:

1. **Estatica**: se leen los fuentes de `core/` y se comprueba que las unicas
   llamadas que escriben estan en la lista blanca de funciones que reciben la
   ruta por parametro, y que no hay literales `/Volumes`, `/tmp`, `~/` ni
   `Path.home()` en ningun camino de escritura.
2. **Dinamica**: se ejecuta TODO lo que `core/` sabe escribir contra un
   `tmp_path`, con una foto del repo entera antes y despues. Si aparece o
   desaparece un solo fichero del repo, salta.

Los modulos de los agentes B (`core/analysis/`) y C (`core/matching/`) se
excluyen a proposito: se estan escribiendo a la vez que esta revision y no son
mios. Que los revise quien les toque.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from core.contracts import CDL, LUT3D
from core.io import escribir_cdl, escribir_cdls, escribir_cube, guardar_sesion
from core.resolve import FakeResolve

RAIZ = Path(__file__).resolve().parents[2]

#: Lo que reviso yo esta noche. B y C van aparte.
MODULOS_REVISADOS = ("core/color", "core/io", "core/resolve", "probe")

#: Nombres que abren un fichero para escribir o fabrican carpetas. Se dejan
#: fuera `copy` y `replace`, que en este repo son `ndarray.copy()` y
#: `dataclasses.replace()` / `str.replace()` y no tocan el disco.
_ESCRITURAS = {
    "open",
    "mkdir",
    "makedirs",
    "write_text",
    "write_bytes",
    "touch",
    "unlink",
    "rmtree",
    "copyfile",
    "copytree",
    "mkdtemp",
    "mkstemp",
    "NamedTemporaryFile",
    "TemporaryDirectory",
    "savetxt",
    "savez",
}

#: Literales que no pueden aparecer NUNCA en `core/` dentro de una escritura.
_RUTAS_PROHIBIDAS = ("/Volumes", "/tmp", "/var/folders", "/Users/")


def _ficheros(paquete: str) -> list[Path]:
    return sorted((RAIZ / paquete).rglob("*.py"))


def _nombre_llamada(nodo: ast.Call) -> str:
    fn = nodo.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


# ---------------------------------------------------------------------------
# 1. Revision estatica
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("paquete", ["core/color", "core/io", "core/resolve"])
def test_ninguna_ruta_absoluta_del_sistema_aparece_en_core(paquete):
    """`/Volumes`, `/tmp`, `/Users/` y `/var/folders` no pintan nada en `core/`.

    Se admite una sola excepcion, declarada: las dos carpetas de LUT de Resolve
    en `incognitas.py` y `live.py`, que son cadenas que se ENSEÑAN y con las que
    se calculan rutas relativas. `core/` no escribe en ellas (hay un test
    dinamico mas abajo que lo comprueba de verdad).
    """
    permitidos = {"incognitas.py", "live.py"}
    culpables = {}
    for fichero in _ficheros(paquete):
        if fichero.name in permitidos:
            continue
        texto = fichero.read_text(encoding="utf-8")
        # Fuera comentarios y docstrings: solo interesa el codigo.
        arbol = ast.parse(texto)
        literales = [
            n.value
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        docs = {
            ast.get_docstring(n)
            for n in ast.walk(arbol)
            if isinstance(n, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
        malos = [
            s
            for s in literales
            if s not in docs and any(p in s for p in _RUTAS_PROHIBIDAS)
        ]
        if malos:
            culpables[fichero.name] = malos
    assert culpables == {}, culpables


@pytest.mark.parametrize("paquete", ["core/color", "core/io", "core/resolve"])
def test_las_escrituras_de_core_estan_todas_localizadas(paquete):
    """Inventario de escrituras. Si aparece una nueva, esta revision salta.

    No es que escribir este prohibido: es que tiene que estar en un sitio
    conocido, en una funcion que reciba la ruta por parametro. La lista es corta
    a proposito.
    """
    esperado = {
        "core/color": {},
        "core/io": {
            "bundle.py": {"mkdir", "open"},
            "cdl_xml.py": {"mkdir", "open"},
            "cube.py": {"mkdir", "open"},
        },
        "core/resolve": {"fake.py": {"open"}},
    }[paquete]

    encontrado: dict[str, set[str]] = {}
    for fichero in _ficheros(paquete):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        nombres = {
            _nombre_llamada(n) for n in ast.walk(arbol) if isinstance(n, ast.Call)
        } & _ESCRITURAS
        if nombres:
            encontrado[fichero.name] = nombres
    assert encontrado == esperado, (
        f"el inventario de escrituras de {paquete} ha cambiado: {encontrado}"
    )


def test_core_no_usa_tempfile_ni_Path_home_para_escribir():
    """`tempfile` y `Path.home()` son las dos formas faciles de saltarse la regla.

    `Path.home()` aparece una vez, en `incognitas.lut_dir()`, y solo para
    CONSTRUIR una cadena que se enseña. `tempfile` no aparece en `core/` en
    absoluto. Lo que si lo usa es `probe/api_probe.py`, que es una herramienta
    aparte que Mario ejecuta a mano y que pide permiso antes de escribir; queda
    dicho en el informe.
    """
    con_tempfile = []
    con_home = []
    for paquete in ("core/color", "core/io", "core/resolve"):
        for fichero in _ficheros(paquete):
            texto = fichero.read_text(encoding="utf-8")
            if "tempfile" in texto:
                con_tempfile.append(fichero.name)
            if "Path.home()" in texto or "expanduser" in texto:
                con_home.append(fichero.name)
    assert con_tempfile == []
    assert sorted(con_home) == ["incognitas.py", "live.py"]


# ---------------------------------------------------------------------------
# 2. Revision dinamica: foto del repo antes y despues
# ---------------------------------------------------------------------------


def _foto_del_repo() -> set[Path]:
    fuera = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
    return {
        p
        for p in RAIZ.rglob("*")
        if p.is_file() and not any(parte in fuera for parte in p.parts)
    }


def test_escribirlo_todo_en_tmp_path_no_toca_ni_un_fichero_del_repo(tmp_path):
    """Se ejecuta TODO lo que `core/` sabe escribir y se mira el repo entero.

    `.cube` (los tres tamaños, modo normal y exacto), `.cc`, `.ccc`, `.cdl`,
    `.sidebcolor` y los stills de `FakeResolve`. Si algo se escapa a la carpeta
    de trabajo, al repo, a `~` o a cualquier sitio, aqui se ve.
    """
    from core.contracts import ColorSession

    antes = _foto_del_repo()

    for n in (17, 33, 65):
        escribir_cube(LUT3D.identity(n), tmp_path / f"lut{n}.cube")
        escribir_cube(LUT3D.identity(n), tmp_path / f"exacto{n}.cube", decimales=None)
    escribir_cube(LUT3D.identity(2), tmp_path / "sub" / "x.cube", crear_directorios=True)

    cdl = CDL(slope=(1.1, 1.0, 0.9), offset=(0.0, 0.0, 0.0), power=(1.0, 1.0, 1.0))
    escribir_cdl(cdl, tmp_path / "uno.cc")
    escribir_cdls([("a", cdl), ("b", cdl)], tmp_path / "varios.ccc")
    escribir_cdls([("a", cdl)], tmp_path / "lista.cdl")

    sesion = ColorSession(
        project_name="REVISION",
        created_at="2026-09-15",
        app_version="0.1.0",
        reference_clip_id=None,
        look_lut=LUT3D.identity(17),
    )
    guardar_sesion(sesion, tmp_path / "s.sidebcolor")
    guardar_sesion(sesion, tmp_path / "otra" / "s.sidebcolor", crear_directorios=True)

    fake = FakeResolve(n_clips=1, home=str(tmp_path / "casa_falsa"))
    still = fake.grab_still()
    fake.export_stills([still], str(tmp_path), "still_", "png")

    despues = _foto_del_repo()
    assert despues == antes, (
        f"el repo ha cambiado. Nuevos: {sorted(p.name for p in despues - antes)}; "
        f"desaparecidos: {sorted(p.name for p in antes - despues)}"
    )
    assert not (tmp_path / "casa_falsa").exists(), "lut_dir() ha FABRICADO la carpeta de LUTs"


def test_el_lut_dir_del_sistema_se_calcula_pero_no_se_toca(tmp_path):
    """`lut_dir()` devuelve una ruta absoluta del sistema. No puede crearla.

    Es la que mas cerca esta de la linea roja: si `lut_dir()` hiciera `mkdir`,
    la app estaria fabricando carpetas en `/Library` sin permiso de nadie.
    """
    from core.resolve import Incognitas
    from core.resolve.incognitas import LUT_DIR_DESCARGA

    casa = tmp_path / "no_existo"
    devuelto = lut_dir_mas = None
    devuelto = __import__("core.resolve", fromlist=["lut_dir"]).lut_dir(Incognitas())
    lut_dir_mas = __import__("core.resolve", fromlist=["lut_dir"]).lut_dir(
        Incognitas(instalacion="mac_app_store"), home=str(casa)
    )
    assert devuelto == LUT_DIR_DESCARGA
    assert lut_dir_mas.startswith(str(casa))
    assert not casa.exists(), "lut_dir() ha creado la carpeta personal falsa"


def test_qc_y_lectura_no_escriben_absolutamente_nada(tmp_path):
    """Las funciones de LECTURA no pueden dejar rastro (ni un `.pyc` de datos).

    Suena obvio; se comprueba igual, porque un `np.load` mal hecho o un cache
    perezoso son formas reales de dejar ficheros por ahi.
    """
    from core.io import leer_cdl, leer_cube, qc_lut

    ruta_lut = escribir_cube(LUT3D.identity(17), tmp_path / "l.cube")
    ruta_cdl = escribir_cdl(CDL(), tmp_path / "c.cc")
    antes = sorted(p.name for p in tmp_path.rglob("*"))

    for _ in range(3):
        qc_lut(leer_cube(ruta_lut))
        leer_cdl(ruta_cdl)
        np.asarray(leer_cube(ruta_lut).table)

    assert sorted(p.name for p in tmp_path.rglob("*")) == antes
