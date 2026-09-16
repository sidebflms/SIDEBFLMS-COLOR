"""El script de la primera prueba, ejecutandose de verdad, sobre un origen de solo lectura.

LAS TRES CONDICIONES QUE SE DEMUESTRAN AQUI
-------------------------------------------
1. **Sin argumentos no hace nada**: sale con un mensaje claro y no escribe ni en
   `pruebas/trabajo/`.
2. **En simulacro no escribe nada**: ni el origen ni `pruebas/trabajo/` cambian.
3. **Ejecutandose de verdad, el origen queda identico byte a byte**: mismo listado,
   mismos tamanos, mismas fechas de modificacion (de ficheros y de carpetas) y el
   mismo contenido (sha256). El origen es una copia del montaje sintetico con
   `chmod` de solo lectura, asi que un intento de escribir ahi reventaria ademas.

La ejecucion de verdad escribe en `pruebas/trabajo/<fecha-hora>/`. El test
comprueba que aparece exactamente UNA carpeta nueva, la revisa y la borra.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from core.paths import have_ffmpeg
from pruebas import origen as origen_mod
from pruebas import primera_real
from pruebas.guarda import RAIZ_REPO, RAIZ_TRABAJO
from pruebas.sintetico import montaje_compartido

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(not have_ffmpeg(), reason="hace falta ffmpeg para fabricar y leer clips"),
]


def foto_arbol(raiz: Path) -> dict[str, tuple]:
    """Todo lo que puede cambiar en un arbol: listado, tamanos, mtimes y contenido."""
    salida: dict[str, tuple] = {}
    for carpeta, subcarpetas, ficheros in os.walk(raiz):
        c = Path(carpeta)
        st = c.stat()
        salida[str(c.relative_to(raiz)) + "/"] = ("carpeta", st.st_mtime_ns, sorted(subcarpetas),
                                                  sorted(ficheros))
        for f in ficheros:
            p = c / f
            st = p.lstat()
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            salida[str(p.relative_to(raiz))] = ("fichero", st.st_size, st.st_mtime_ns, h)
    return salida


def foto_trabajo() -> set[str]:
    if not RAIZ_TRABAJO.exists():
        return {"<no existe>"}
    return {str(p.relative_to(RAIZ_TRABAJO)) for p in RAIZ_TRABAJO.rglob("*")}


def _solo_lectura(raiz: Path, activar: bool) -> None:
    for carpeta, _, ficheros in os.walk(raiz):
        for f in ficheros:
            os.chmod(Path(carpeta) / f, 0o444 if activar else 0o644)
    for carpeta, _, _ in sorted(os.walk(raiz), key=lambda t: -len(t[0])):
        os.chmod(carpeta, 0o555 if activar else 0o755)


@pytest.fixture(scope="module")
def rodaje(tmp_path_factory):
    """Copia del montaje sintetico, en solo lectura: el "disco de produccion" del test."""
    m = montaje_compartido(tmp_path_factory.getbasetemp())
    raiz = tmp_path_factory.mktemp("rodaje_solo_lectura")
    shutil.copytree(m.master.parent, raiz / "MASTER")
    shutil.copytree(next(iter(m.brutos.values())).parent, raiz / "BRUTOS")
    _solo_lectura(raiz, True)
    yield {"raiz": raiz, "master": raiz / "MASTER" / m.master.name, "brutos": raiz / "BRUTOS"}
    _solo_lectura(raiz, False)


def _main(args: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    rc = primera_real.main(args, salida=out)
    return rc, out.getvalue()


def test_sin_argumentos_no_hace_nada_y_lo_dice():
    antes = foto_trabajo()
    rc, texto = _main([])
    print(texto)
    assert rc == primera_real.SALIDA_FALTAN_ARGUMENTOS
    assert "No hago nada" in texto and "--master" in texto and "--brutos" in texto
    assert foto_trabajo() == antes


def test_solo_con_master_dice_que_faltan_los_brutos(rodaje):
    antes = foto_trabajo()
    rc, texto = _main(["--master", str(rodaje["master"])])
    assert rc == primera_real.SALIDA_FALTAN_ARGUMENTOS
    assert "--brutos" in texto and "--master RUTA" not in texto
    assert foto_trabajo() == antes


def test_simulacro_no_escribe_ni_en_el_origen_ni_en_trabajo(rodaje):
    origen_antes = foto_arbol(rodaje["raiz"])
    trabajo_antes = foto_trabajo()
    rc, texto = _main(["--master", str(rodaje["master"]), "--brutos", str(rodaje["brutos"])])
    print(texto)
    assert rc == primera_real.SALIDA_OK
    assert "SIMULACRO" in texto
    assert "no se ha escrito nada" in texto
    assert "5 ficheros" in texto  # los cinco brutos listados
    assert "TIEMPO ESTIMADO" in texto and "espacio: como mucho" in texto
    assert foto_trabajo() == trabajo_antes
    assert foto_arbol(rodaje["raiz"]) == origen_antes


def test_ejecutando_de_verdad_el_origen_queda_identico_byte_a_byte(rodaje):
    origen_antes = foto_arbol(rodaje["raiz"])
    trabajo_antes = foto_trabajo()
    rc, texto = _main([
        "--master", str(rodaje["master"]), "--brutos", str(rodaje["brutos"]), "--ejecutar",
        "--ancho-analisis", "240",
    ])
    print(texto[-3000:])
    origen_despues = foto_arbol(rodaje["raiz"])
    nuevas = sorted({p.split("/")[0] for p in foto_trabajo() - trabajo_antes} - {"<no existe>"})
    carpeta = RAIZ_TRABAJO / nuevas[0] if len(nuevas) == 1 else None
    try:
        assert rc == primera_real.SALIDA_OK, texto
        # --- el origen, identico -------------------------------------------------
        ficheros = [k for k, v in origen_antes.items() if v[0] == "fichero"]
        carpetas = [k for k, v in origen_antes.items() if v[0] == "carpeta"]
        bytes_totales = sum(origen_antes[k][1] for k in ficheros)
        print(f"\nORIGEN: {len(ficheros)} ficheros ({bytes_totales} bytes) y {len(carpetas)} "
              f"carpetas; listado, tamanos, mtimes y sha256 comparados antes y despues")
        assert origen_despues.keys() == origen_antes.keys(), "el listado del origen ha cambiado"
        for k in origen_antes:
            assert origen_despues[k] == origen_antes[k], f"ha cambiado {k}"
        assert origen_despues == origen_antes
        print("ORIGEN: identico byte a byte")
        # --- una sola carpeta nueva, dentro de trabajo -----------------------------
        assert len(nuevas) == 1, nuevas
        assert carpeta is not None and carpeta.resolve().is_relative_to(RAIZ_TRABAJO.resolve())
        assert (carpeta / "informe.md").is_file()
        datos = json.loads((carpeta / "informe.json").read_text(encoding="utf-8"))
        aceptadas = [a for a in datos["localizacion"]["apariciones"] if a["aceptada"]]
        assert len(aceptadas) == 5
        assert datos["localizacion"]["no_encontrados"] == ["C_descarte.mov"]
        assert len(datos["t1"]) == 5 and len(datos["t5"]) == 5 * 4
        for m in datos["t1"].values():
            assert m["de_medio_cubierto"] < 1.0, m
            assert any("registro subpixel" in n for n in m["notas"]), m["notas"]
        md = (carpeta / "informe.md").read_text(encoding="utf-8")
        assert "T1 · ΔE2000 máximo" in md and "Cobertura del cubo" in md and "T5" in md
        pngs = list((carpeta / "fotogramas").glob("*.png"))
        assert len(pngs) == 10
    finally:
        if carpeta is not None and carpeta.resolve().is_relative_to(RAIZ_TRABAJO.resolve()):
            shutil.rmtree(carpeta)


def test_se_niega_si_la_carpeta_de_trabajo_queda_dentro_del_origen(rodaje, monkeypatch):
    def trampa(*_a, **_k):
        raise AssertionError("ha recorrido una carpeta que no debia")

    monkeypatch.setattr(origen_mod.os, "walk", trampa)
    antes = foto_trabajo()
    rc, texto = _main(["--master", str(rodaje["master"]), "--brutos", str(RAIZ_REPO),
                       "--ejecutar"])
    print(texto)
    assert rc == primera_real.SALIDA_RECHAZADO
    assert "NO SIGO" in texto
    assert foto_trabajo() == antes


def test_se_niega_si_el_master_esta_entre_los_brutos(rodaje):
    antes = foto_trabajo()
    rc, texto = _main(["--master", str(rodaje["master"]), "--brutos", str(rodaje["master"]),
                       "--ejecutar"])
    assert rc == primera_real.SALIDA_RECHAZADO
    assert "master" in texto
    assert foto_trabajo() == antes


def test_ayuda_funciona_desde_la_terminal():
    proc = subprocess.run(
        [sys.executable, str(RAIZ_REPO / "pruebas" / "primera_real.py"), "--help"],
        capture_output=True, text=True, timeout=120, cwd=str(RAIZ_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert "SIMULACRO" in proc.stdout and "--ejecutar" in proc.stdout
    assert "INVENTADAS" in proc.stdout


def test_el_origen_de_solo_lectura_es_de_verdad_de_solo_lectura(rodaje):
    """Sin esto, el test byte a byte seria menos fuerte de lo que dice."""
    assert not (stat.S_IMODE(os.stat(rodaje["brutos"]).st_mode) & 0o222)
    with pytest.raises(PermissionError):
        (rodaje["brutos"] / "intento.txt").write_text("x")
