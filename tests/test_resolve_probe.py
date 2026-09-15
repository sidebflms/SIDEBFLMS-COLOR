"""El probe se prueba hasta donde se puede sin Resolve delante.

Lo que SI se puede comprobar esta noche, y es casi todo lo que puede salir mal
manana a las nueve de la manana:

* que compila y que `--help` funciona;
* que **no importa Resolve al cargarse** (el import esta dentro de una funcion);
* que usa solo la biblioteca estandar y no importa `core`, porque Mario lo va a
  ejecutar con el `python3` del sistema, sin el entorno virtual;
* que el trozo mas delicado, el que mide el brillo de un still exportado, esta
  bien escrito (ahi es donde se responde la incognita F0-2).

Lo que NO se prueba aqui, y hay que decirlo: nada que hable con Resolve. Este
test nunca conecta.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PROBE = RAIZ / "probe" / "api_probe.py"

#: Modulos que trae Python de serie y que el probe puede usar.
STDLIB_PERMITIDA = {
    "argparse",
    "contextlib",
    "datetime",
    "json",
    "os",
    "platform",
    "sys",
    "tempfile",
    "__future__",
}


@pytest.fixture(scope="module")
def arbol() -> ast.Module:
    return ast.parse(PROBE.read_text(encoding="utf-8"))


def test_el_probe_existe_y_compila():
    assert PROBE.is_file()
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(PROBE)], check=True, capture_output=True
    )


def test_solo_biblioteca_estandar(arbol):
    """Mario lo ejecuta con su python3 del sistema, que no tiene numpy."""
    importados = set()
    for nodo in arbol.body:  # solo el nivel superior
        if isinstance(nodo, ast.Import):
            importados.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])
    de_mas = importados - STDLIB_PERMITIDA
    assert not de_mas, f"el probe importa cosas que no son de la stdlib: {de_mas}"


def test_no_importa_core_ni_numpy():
    texto = PROBE.read_text(encoding="utf-8")
    assert "import numpy" not in texto
    assert "from core" not in texto
    assert "import core" not in texto


def test_el_import_de_resolve_esta_dentro_de_una_funcion(arbol):
    """Cargar el modulo no puede intentar hablar con Resolve."""
    al_nivel_superior = [
        a.name
        for nodo in arbol.body
        if isinstance(nodo, ast.Import)
        for a in nodo.names
    ]
    assert "DaVinciResolveScript" not in al_nivel_superior
    assert "fusionscript" not in al_nivel_superior

    dentro = [
        n
        for n in ast.walk(arbol)
        if isinstance(n, ast.Import)
        and any(a.name == "DaVinciResolveScript" for a in n.names)
    ]
    assert len(dentro) == 1, "el import de Resolve tiene que estar en un solo sitio"


def test_importar_el_probe_no_carga_resolve():
    """Se importa en un proceso aparte para no ensuciar la sesion de pytest."""
    codigo = (
        "import sys;"
        f"sys.path.insert(0, {str(RAIZ)!r});"
        "import probe.api_probe as p;"
        "print('DaVinciResolveScript' in sys.modules, 'fusionscript' in sys.modules)"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    )
    assert salida.stdout.strip() == "False False"


def test_help(arbol):
    r = subprocess.run(
        [sys.executable, str(PROBE), "--help"], capture_output=True, text=True, check=True
    )
    for bandera in ("--solo-diagnostico", "--no-escribir", "--informe", "--clip", "--dctl"):
        assert bandera in r.stdout


# ---------------------------------------------------------------------------
# La regla de arquitectura: abrir la app no roza Resolve
# ---------------------------------------------------------------------------


def test_importar_core_resolve_no_carga_resolve():
    """Convencion 6 de CONTRATOS: `core/` no importa DaVinciResolveScript.

    Se comprueba en un proceso limpio: si algun dia alguien mete el import
    arriba del todo de `live.py` y lo engancha al `__init__`, esto lo pilla.
    """
    codigo = (
        "import sys;"
        f"sys.path.insert(0, {str(RAIZ)!r});"
        "import core.resolve as r;"
        "print('DaVinciResolveScript' in sys.modules,"
        " 'fusionscript' in sys.modules,"
        " 'core.resolve.live' in sys.modules,"
        " 'PySide6' in sys.modules)"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    )
    assert salida.stdout.strip() == "False False False False"


def test_el_unico_archivo_de_core_que_importa_resolve_es_live():
    """Se mira el arbol de sintaxis, no el texto: en los docstrings el nombre
    aparece a menudo, y decir 'aqui no se importa' no puede hacer fallar esto."""
    for p in (RAIZ / "core").rglob("*.py"):
        importa = any(
            isinstance(n, ast.Import)
            and any(a.name in ("DaVinciResolveScript", "fusionscript") for a in n.names)
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        )
        assert importa == (p.name == "live.py"), p


def test_live_importa_resolve_dentro_de_una_funcion():
    """Existe, pero no se ejecuta hoy: solo se mira su codigo."""
    live = RAIZ / "core" / "resolve" / "live.py"
    arbol_live = ast.parse(live.read_text(encoding="utf-8"))
    al_nivel_superior = [
        a.name for n in arbol_live.body if isinstance(n, ast.Import) for a in n.names
    ]
    assert "DaVinciResolveScript" not in al_nivel_superior
    assert "NO SE HA EJECUTADO NUNCA" in (ast.get_docstring(arbol_live) or "")


def test_las_instrucciones_de_uso_estan_en_la_cabecera():
    """Quien lo ejecuta se acaba de levantar: tiene que saber que hace antes de
    ejecutarlo."""
    cabecera = ast.get_docstring(ast.parse(PROBE.read_text(encoding="utf-8")))
    assert cabecera is not None
    for trozo in ("Studio", "--solo-diagnostico", "QUE VA A TOCAR", "SIDEB COLOR PROBE"):
        assert trozo in cabecera


def test_pregunta_antes_de_escribir():
    """El `input()` tiene que estar, y el camino de escritura tiene que pasar
    por el. Si esto se rompe, el probe podria tocar un proyecto sin avisar."""
    texto = PROBE.read_text(encoding="utf-8")
    assert "input(" in texto
    assert "preguntar_permiso" in texto
    assert "if not (args.si or preguntar_permiso(" in texto


# ---------------------------------------------------------------------------
# El medidor de stills (con el que se responde F0-2)
# ---------------------------------------------------------------------------


def cargar_funcion(nombre):
    """Carga una funcion suelta del probe sin importarlo como paquete."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("api_probe_bajo_test", PROBE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return getattr(modulo, nombre)


def escribir_ppm(ruta: Path, valor: int, ancho: int = 64, alto: int = 64) -> None:
    cuerpo = bytes([valor]) * (ancho * alto * 3)
    ruta.write_bytes(f"P6\n{ancho} {alto}\n255\n".encode("ascii") + cuerpo)


def test_medir_ppm_negro_y_blanco(tmp_path):
    leer = cargar_funcion("leer_ppm_medio")
    negro, blanco = tmp_path / "n.ppm", tmp_path / "b.ppm"
    escribir_ppm(negro, 0)
    escribir_ppm(blanco, 255)
    assert leer(str(negro)) == pytest.approx(0.0)
    assert leer(str(blanco)) == pytest.approx(1.0)


def test_medir_ppm_gris_medio(tmp_path):
    leer = cargar_funcion("leer_ppm_medio")
    gris = tmp_path / "g.ppm"
    escribir_ppm(gris, 128)
    assert leer(str(gris)) == pytest.approx(128 / 255, abs=0.01)


def test_medir_ppm_con_comentarios_en_la_cabecera(tmp_path):
    """Algunos escritores de PPM meten un comentario. No puede despistar."""
    leer = cargar_funcion("leer_ppm_medio")
    ruta = tmp_path / "c.ppm"
    ruta.write_bytes(b"P6\n# hecho por quien sea\n8 8\n255\n" + bytes([255]) * 8 * 8 * 3)
    assert leer(str(ruta)) == pytest.approx(1.0)


def test_medir_ppm_de_16_bits(tmp_path):
    leer = cargar_funcion("leer_ppm_medio")
    ruta = tmp_path / "16.ppm"
    ruta.write_bytes(b"P6\n8 8\n65535\n" + b"\xff\xff" * 8 * 8 * 3)
    assert leer(str(ruta)) == pytest.approx(1.0, abs=0.01)


def test_medir_algo_que_no_es_un_ppm(tmp_path):
    leer = cargar_funcion("leer_ppm_medio")
    ruta = tmp_path / "x.png"
    ruta.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert leer(str(ruta)) is None
    assert leer(str(tmp_path / "no_existe.ppm")) is None


def test_distingue_un_still_graduado_de_uno_limpio(tmp_path):
    """Es exactamente la comparacion con la que el probe responde F0-2."""
    leer = cargar_funcion("leer_ppm_medio")
    con_grado, sin_grado = tmp_path / "con.ppm", tmp_path / "sin.ppm"
    escribir_ppm(con_grado, 10)  # slope 0.05: casi negro
    escribir_ppm(sin_grado, 180)  # el nodo apagado
    assert leer(str(con_grado)) < leer(str(sin_grado)) * 0.5


# ---------------------------------------------------------------------------
# El informe
# ---------------------------------------------------------------------------


def test_el_informe_se_escribe_en_json_y_en_texto(tmp_path):
    import json

    Informe = cargar_funcion("Informe")
    inf = Informe()
    inf.responder("F0-1", "¿va el drx?", False, "no ha escrito nada", "no se ofrece")
    inf.aviso("mira esto")
    destino = tmp_path / "sub" / "informe.json"
    ruta_json, ruta_txt = inf.escribir(str(destino))
    datos = json.loads(Path(ruta_json).read_text(encoding="utf-8"))
    assert datos["preguntas"]["F0-1"]["respuesta"] is False
    texto = Path(ruta_txt).read_text(encoding="utf-8")
    assert "¿va el drx?" in texto
    assert "mira esto" in texto


# ---------------------------------------------------------------------------
# V-0: la comprobacion mas importante del probe, probada sin Resolve
# ---------------------------------------------------------------------------


class ClipFalso:
    """Un timelineItem de mentira. Solo hace falta que sepa estas dos cosas.

    Esto NO es hablar con Resolve: es comprobar que el probe interpreta bien lo
    que Resolve le conteste, sea lo que sea.
    """

    def __init__(self, nombre, version, revienta=False):
        self._nombre = nombre
        self._version = version
        self._revienta = revienta

    def GetName(self):  # noqa: N802 - la API de Resolve se llama asi
        return self._nombre

    def GetCurrentVersion(self):  # noqa: N802
        if self._revienta:
            raise RuntimeError("Resolve dice que no")
        return self._version


def _preguntar_v0(items):
    pregunta = cargar_funcion("pregunta_v0_version_actual")
    Informe = cargar_funcion("Informe")
    inf = Informe()
    pregunta(inf, items)
    return inf


def test_v0_con_resolve_portandose_bien():
    inf = _preguntar_v0(
        [
            ClipFalso("A001_C001", {"versionName": "Version 1", "versionType": 0}),
            ClipFalso("A001_C002", {"versionName": "SIDEB COLOR", "versionType": 0}),
        ]
    )
    v0 = inf.datos["preguntas"]["V-0"]
    assert v0["respuesta"] is True
    assert "2 de 2" in v0["detalle"]


@pytest.mark.parametrize(
    "version",
    [
        {"versionName": ""},  # nombre vacio
        {"versionType": 0},  # el diccionario sin la clave
        None,  # nada
        "",  # cadena vacia
        {},  # diccionario vacio
    ],
)
def test_v0_caza_a_resolve_portandose_raro(version):
    """Si Resolve contesta cualquiera de estas, la app NO podria escribir."""
    inf = _preguntar_v0([ClipFalso("A001_C001", version)])
    v0 = inf.datos["preguntas"]["V-0"]
    assert v0["respuesta"] is False
    assert "NEGARIA" in v0["consecuencia_para_la_app"]
    assert "VersionIndeterminada" in v0["consecuencia_para_la_app"]


def test_v0_sobrevive_a_que_la_llamada_reviente():
    inf = _preguntar_v0([ClipFalso("A001_C001", None, revienta=True)])
    assert inf.datos["preguntas"]["V-0"]["respuesta"] is False
    assert any("GetCurrentVersion" in e for e in inf.datos["errores"])


def test_v0_avisa_aunque_solo_falle_un_clip():
    """Un solo clip mudo ya deja a la app sin poder graduar ese clip."""
    inf = _preguntar_v0(
        [
            ClipFalso("bueno", {"versionName": "Version 1"}),
            ClipFalso("mudo", {"versionName": ""}),
        ]
    )
    v0 = inf.datos["preguntas"]["V-0"]
    assert v0["respuesta"] is False
    assert "1 de 2" in v0["detalle"]


def test_v0_apunta_lo_que_vio_en_crudo_para_poder_diagnosticarlo():
    """En el informe tiene que quedar el valor tal cual, no interpretado."""
    inf = _preguntar_v0([ClipFalso("A001_C001", {"versionName": "Version 1"})])
    filas = inf.datos["resolve"]["get_current_version"]
    assert len(filas) == 1
    assert "versionName" in filas[0]["crudo"]
    assert filas[0]["tipo"] == "dict"
    assert filas[0]["usable"] is True


def test_v0_es_de_solo_lectura():
    """No llama a nada que escriba. Si algun dia lo hiciera, este clip lo dice."""

    class ClipQueSeQueja(ClipFalso):
        def __getattr__(self, nombre):
            raise AssertionError(f"V-0 tiene que ser de solo lectura y ha llamado a {nombre}")

    inf = _preguntar_v0([ClipQueSeQueja("A001_C001", {"versionName": "Version 1"})])
    assert inf.datos["preguntas"]["V-0"]["respuesta"] is True


def test_el_probe_hace_la_v0_antes_que_las_seis_incognitas(arbol):
    """Orden DENTRO de `main()`: la V-0 se hace nada mas tener contexto, y como
    es de solo lectura, antes de pedir permiso para escribir nada."""
    main = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    llamadas = sorted(
        (n.lineno, n.func.id)
        for n in ast.walk(main)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    )
    orden = [nombre for _, nombre in llamadas]
    assert "pregunta_v0_version_actual" in orden
    assert orden.index("pregunta_v0_version_actual") < orden.index("preguntar_permiso")
    for incognita in ("pregunta_f0_5", "pregunta_f0_3", "preguntas_stills"):
        assert orden.index("pregunta_v0_version_actual") < orden.index(incognita)
    assert "V-0" in ast.get_docstring(arbol)
