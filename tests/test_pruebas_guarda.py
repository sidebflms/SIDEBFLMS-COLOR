"""La guarda de escritura de la primera prueba real, y que nadie se la salta.

Dos cosas distintas se prueban aqui:

1. **Que la guarda dice que no** donde tiene que decir que no: fuera de
   `pruebas/trabajo/`, dentro de un origen, por un enlace simbolico, con `..`,
   en `/Volumes`, sobreescribiendo.
2. **Que ningun modulo del script escribe sin pasar por ella.** Un recorrido del
   AST de los modulos que importa `primera_real.py` busca cualquier forma de
   escribir en disco (`open` en escritura, `write_text`, `mkdir`, `shutil`,
   `cv2.imwrite`, `np.save`...) fuera de `pruebas/guarda.py`. Con control
   negativo: se le da un trozo de codigo que escribe y tiene que cazarlo.

Los tests que tienen que crear algo en `pruebas/trabajo/` lo hacen en una
subcarpeta con nombre propio y la borran al terminar.
"""

from __future__ import annotations

import ast
import os
import shutil
import textwrap
import uuid
from pathlib import Path

import pytest

from pruebas import guarda as G
from pruebas.guarda import RAIZ_TRABAJO, EscrituraProhibida, Guarda

PRUEBAS = Path(G.__file__).resolve().parent


@pytest.fixture
def sub_trabajo():
    """Subcarpeta propia dentro de pruebas/trabajo, que se borra al terminar."""
    nombre = f"_test_guarda_{uuid.uuid4().hex[:8]}"
    ruta = RAIZ_TRABAJO / nombre
    yield ruta
    if ruta.exists() or ruta.is_symlink():
        assert ruta.resolve().is_relative_to(RAIZ_TRABAJO.resolve()) or ruta.is_symlink()
        if ruta.is_symlink():
            ruta.unlink()
        else:
            shutil.rmtree(ruta)


def test_escribe_dentro_de_trabajo_y_nunca_sobreescribe(tmp_path, sub_trabajo):
    g = Guarda([tmp_path / "origen"])
    g.crear_carpeta(sub_trabajo)
    f = g.escribir_texto(sub_trabajo / "a.txt", "hola")
    assert f.read_text() == "hola"
    with pytest.raises(FileExistsError):
        g.escribir_texto(sub_trabajo / "a.txt", "otra vez")
    assert f.read_text() == "hola"


def test_rechaza_fuera_de_trabajo(tmp_path):
    g = Guarda([tmp_path / "origen"])
    destino = tmp_path / "fuera.txt"
    with pytest.raises(EscrituraProhibida):
        g.escribir_texto(destino, "x")
    with pytest.raises(EscrituraProhibida):
        g.crear_carpeta(tmp_path / "carpeta_fuera")
    assert not destino.exists()
    assert not (tmp_path / "carpeta_fuera").exists()


def test_rechaza_la_raiz_del_repo_y_la_propia_raiz_de_trabajo(tmp_path):
    g = Guarda([tmp_path / "origen"])
    for destino in (G.RAIZ_REPO / "no_deberia.txt", RAIZ_TRABAJO, RAIZ_TRABAJO.parent / "x.txt"):
        with pytest.raises(EscrituraProhibida):
            g.comprobar(destino)


def test_rechaza_puntos_puntos_que_salen(tmp_path):
    g = Guarda([tmp_path / "origen"])
    truco = RAIZ_TRABAJO / "a" / ".." / ".." / ".." / "CIFRAS_falso.md"
    with pytest.raises(EscrituraProhibida):
        g.comprobar(truco)


def test_rechaza_discos_externos(tmp_path, monkeypatch):
    """Con un /Volumes sustituto: este test no resuelve ni una ruta del /Volumes real."""
    assert Path("/Volumes") == G._VOLUMES
    falso = tmp_path / "Volumes"
    (falso / "DISCO_EJEMPLO").mkdir(parents=True)
    monkeypatch.setattr(G, "_VOLUMES", falso)
    g = Guarda([tmp_path / "origen"])
    with pytest.raises(EscrituraProhibida):
        g.comprobar(falso / "DISCO_EJEMPLO" / "x.txt")
    # y un enlace dentro de trabajo que apunte a un disco externo tampoco
    enlace = RAIZ_TRABAJO / f"_test_volumes_{os.getpid()}"
    RAIZ_TRABAJO.mkdir(parents=True, exist_ok=True)
    os.symlink(falso / "DISCO_EJEMPLO", enlace)
    try:
        with pytest.raises(EscrituraProhibida):
            g.escribir_texto(enlace / "x.txt", "x")
        assert list((falso / "DISCO_EJEMPLO").iterdir()) == []
    finally:
        enlace.unlink()


def test_rechaza_un_enlace_simbolico_de_trabajo_que_apunta_a_otro_sitio(tmp_path, sub_trabajo):
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    sub_trabajo.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(afuera, sub_trabajo)  # pruebas/trabajo/_test_xxx -> tmp_path/afuera
    g = Guarda([tmp_path / "origen"])
    with pytest.raises(EscrituraProhibida):
        g.escribir_texto(sub_trabajo / "a.txt", "x")
    assert list(afuera.iterdir()) == []


def test_rechaza_escribir_dentro_de_un_origen_que_cuelga_de_trabajo(sub_trabajo, tmp_path):
    g0 = Guarda([tmp_path / "o"])
    g0.crear_carpeta(sub_trabajo / "origen_raro")
    (sub_trabajo / "origen_raro" / "master.mov").write_bytes(b"x")
    # Un origen dentro de la carpeta de trabajo: la guarda no se construye.
    with pytest.raises(EscrituraProhibida):
        Guarda([sub_trabajo / "origen_raro" / "master.mov"])


@pytest.mark.parametrize("origen", ["repo", "pruebas", "trabajo"])
def test_no_se_construye_si_trabajo_queda_dentro_de_un_origen(origen):
    ruta = {"repo": G.RAIZ_REPO, "pruebas": G.RAIZ_REPO / "pruebas", "trabajo": RAIZ_TRABAJO}[origen]
    with pytest.raises(EscrituraProhibida):
        Guarda([ruta])


def test_un_fichero_de_origen_protege_su_carpeta(tmp_path):
    carpeta = tmp_path / "rodaje"
    carpeta.mkdir()
    master = carpeta / "master.mov"
    master.write_bytes(b"x")
    g = Guarda([master])
    assert carpeta.resolve() in g.protegidas
    with pytest.raises(EscrituraProhibida):
        g.comprobar(carpeta / "master_informe.md")


def test_no_acepta_otra_raiz_de_trabajo(tmp_path):
    with pytest.raises(EscrituraProhibida):
        Guarda([tmp_path / "o"], raiz_trabajo=tmp_path / "trabajo")


# ---------------------------------------------------------------------------
# Nadie escribe sin la guarda
# ---------------------------------------------------------------------------

#: Los modulos que usa `primera_real.py`. `guarda.py` es el unico que puede escribir.
MODULOS_DEL_SCRIPT = (
    "primera_real.py", "origen.py", "lectura.py", "localizar.py", "medir.py",
    "informe.py", "cifras_ref.py", "coste.py",
)

#: Metodos que solo sirven para escribir, llamados sobre lo que sea.
_METODOS_QUE_ESCRIBEN = {
    "write_text", "write_bytes", "mkdir", "makedirs", "touch", "rename", "unlink", "rmdir",
    "rmtree", "symlink_to", "hardlink_to", "chmod", "imwrite", "savez", "savez_compressed",
    "tofile", "copyfile", "copytree", "copy2", "symlink",
}

#: Nombres ambiguos (`"a".replace`, `arr.copy()`) que solo escriben llamados sobre
#: estos modulos.
_AMBIGUOS_POR_MODULO = {
    ("os", "replace"), ("os", "remove"), ("os", "link"), ("os", "truncate"),
    ("shutil", "copy"), ("shutil", "move"), ("np", "save"), ("numpy", "save"),
    ("json", "dump"), ("pickle", "dump"), ("cv2", "imwrite"),
}


def _modo(nodo: ast.Call, posicion: int) -> object:
    """El modo de un `open`: "r" si no se da, la cadena si es literal, None si no se sabe."""
    expr = nodo.args[posicion] if len(nodo.args) > posicion else None
    for kw in nodo.keywords:
        if kw.arg == "mode":
            expr = kw.value
    if expr is None:
        return "r"
    return expr.value if isinstance(expr, ast.Constant) else None


def escrituras_en(codigo: str) -> list[str]:
    """Llamadas del codigo que pueden escribir en disco."""
    hallazgos: list[str] = []
    for nodo in ast.walk(ast.parse(codigo)):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        if isinstance(f, ast.Name) and f.id == "open":
            modo = _modo(nodo, 1)
            if modo is None or any(c in str(modo) for c in "wax+"):
                hallazgos.append(f"linea {nodo.lineno}: open(..., {modo!r})")
        elif isinstance(f, ast.Attribute) and f.attr == "open":
            modo = _modo(nodo, 0)
            if modo is None or any(c in str(modo) for c in "wax+"):
                hallazgos.append(f"linea {nodo.lineno}: .open({modo!r})")
        elif isinstance(f, ast.Attribute) and f.attr in _METODOS_QUE_ESCRIBEN:
            hallazgos.append(f"linea {nodo.lineno}: .{f.attr}(...)")
        elif (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and (f.value.id, f.attr) in _AMBIGUOS_POR_MODULO
        ):
            hallazgos.append(f"linea {nodo.lineno}: {f.value.id}.{f.attr}(...)")
    return hallazgos


def test_el_detector_de_escrituras_caza_lo_que_tiene_que_cazar():
    """Control negativo: si esto no caza, el test de abajo pasaria en vacio."""
    trampa = textwrap.dedent("""
        from pathlib import Path
        import cv2, shutil, numpy as np
        open("x", "w")
        open("x", mode="ab")
        Path("x").write_text("hola")
        Path("d").mkdir()
        cv2.imwrite("a.png", img)
        shutil.copy("a", "b")
        np.save("a.npy", arr)
        Path("x").open("w")
    """)
    assert len(escrituras_en(trampa)) == 8
    inocente = "open('x')\nopen('x', 'rb')\nPath('x').read_text()\n'a'.replace('a', 'b')\narr.copy()\n"
    assert escrituras_en(inocente) == []


@pytest.mark.parametrize("modulo", MODULOS_DEL_SCRIPT)
def test_ningun_modulo_del_script_escribe_sin_la_guarda(modulo):
    hallazgos = escrituras_en((PRUEBAS / modulo).read_text(encoding="utf-8"))
    assert hallazgos == [], f"{modulo} escribe sin pasar por la guarda: {hallazgos}"


def test_primera_real_no_importa_lo_que_si_escribe():
    """`sintetico.py` y `medir_coste.py` escriben (material sintetico); el script no los usa."""
    for modulo in MODULOS_DEL_SCRIPT:
        arbol = ast.parse((PRUEBAS / modulo).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            nombres: list[str] = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                base = nodo.module or ""
                nombres = [base, *[f"{base}.{a.name}" for a in nodo.names]]
            for n in nombres:
                assert "sintetico" not in n and "medir_coste" not in n, (modulo, n)
                assert not n.startswith("tests"), (modulo, n)
                assert "DaVinciResolveScript" not in n and "core.resolve" not in n, (modulo, n)


def test_subprocess_solo_en_lectura():
    for modulo in MODULOS_DEL_SCRIPT:
        texto = (PRUEBAS / modulo).read_text(encoding="utf-8")
        if modulo == "lectura.py":
            continue
        assert "subprocess" not in texto, f"{modulo} lanza procesos fuera de lectura.py"


def test_lectura_se_niega_a_lanzar_un_ffmpeg_que_escriba():
    from pruebas import lectura

    for orden in (
        ["-i", "a.mov", "salida.mov"],
        ["-i", "a.mov", "-y", "pipe:1"],
        ["-i", "a.mov", "b.mov", "pipe:1"] + ["pipe:2"],
        ["-report", "-i", "a.mov", "pipe:1"],
    ):
        with pytest.raises(lectura.ErrorLectura):
            lectura._orden(orden)
    cmd, entorno = lectura._orden(["-i", "a.mov", "-f", "rawvideo", "pipe:1"])
    assert cmd[-1] == "pipe:1"
    assert "FFREPORT" not in entorno
