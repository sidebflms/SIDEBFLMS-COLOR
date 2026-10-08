"""Icono y ventana del .dmg de SIDEBFLMS COLOR (`packaging/`).

COLOR todavía NO tiene empaquetado de `.app`: aquí solo hay (1) el icono (`AppIcon.iconset` /
`AppIcon.icns`, generados de `packaging/icono/*.svg`) y (2) la herramienta que hace la ventana del
`.dmg` de la suite (`suite_dmg.py`, copia adaptada de `sidebflms-design`) con su lanzador
`construye_dmg.sh`. Estos tests no montan ningún `.dmg` ni usan Chrome/Finder: miran los archivos.

El repo es PÚBLICO: ningún `.otf` de Akira (ni nada que lo parezca) puede estar en `packaging/`.
"""

from __future__ import annotations

import importlib.util
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PAQ = RAIZ / "packaging"

#: nombre del archivo del iconset -> lado en píxeles
TAMANOS = {
    "icon_16x16": 16, "icon_16x16@2x": 32, "icon_32x32": 32, "icon_32x32@2x": 64,
    "icon_128x128": 128, "icon_128x128@2x": 256, "icon_256x256": 256, "icon_256x256@2x": 512,
    "icon_512x512": 512, "icon_512x512@2x": 1024,
}


def _cargar_suite_dmg():
    spec = importlib.util.spec_from_file_location("suite_dmg_de_color", PAQ / "suite_dmg.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # las dataclasses de suite_dmg.py lo necesitan
    spec.loader.exec_module(modulo)
    return modulo


def _dimensiones_png(ruta: Path) -> tuple[int, int]:
    datos = ruta.read_bytes()
    assert datos[:8] == b"\x89PNG\r\n\x1a\n", f"{ruta.name} no es un PNG"
    return struct.unpack(">II", datos[16:24])


def test_estan_los_archivos_de_empaquetado():
    for nombre in (
        "suite_dmg.py", "suite_dmg_fondo.mjs", "distintivos.json", "casete-oficial-blanco.svg",
        "construye_dmg.sh", "genera_icono.sh", "genera_icono.mjs", "AppIcon.icns",
        "icono/COLOR-maestro.svg", "icono/COLOR-solo-casete.svg",
    ):
        assert (PAQ / nombre).is_file(), f"falta packaging/{nombre}"


def test_el_iconset_trae_los_diez_tamanos_con_su_tamano_real():
    archivos = {p.stem: p for p in (PAQ / "AppIcon.iconset").glob("*.png")}
    assert set(archivos) == set(TAMANOS), "el iconset no tiene exactamente los diez tamaños de macOS"
    for nombre, lado in TAMANOS.items():
        assert _dimensiones_png(archivos[nombre]) == (lado, lado), nombre


def test_el_icns_es_un_icns_y_no_es_el_del_piloto_de_otra_app():
    datos = (PAQ / "AppIcon.icns").read_bytes()
    assert datos[:4] == b"icns"
    assert struct.unpack(">I", datos[4:8])[0] == len(datos), "la longitud de la cabecera no coincide"
    assert len(datos) > 200_000, "un .icns con 1024 px pesa cientos de KB"


@pytest.mark.parametrize("svg", ["COLOR-maestro.svg", "COLOR-solo-casete.svg"])
def test_los_svg_del_icono_llevan_el_nombre_en_contornos_sin_fuente(svg):
    """Licencia: el nombre en Akira va como trazados; no hay <text> ni @font-face ni fuente incrustada."""
    texto = (PAQ / "icono" / svg).read_text(encoding="utf-8")
    assert "<svg" in texto
    for prohibido in ("<text", "@font-face", "font-family", "base64", ".otf", ".ttf"):
        assert prohibido not in texto, f"{svg} contiene {prohibido!r}"


def test_no_hay_ninguna_fuente_de_akira_en_packaging():
    paquetes = [p for p in PAQ.rglob("*") if p.is_file()]
    assert paquetes, "no hay nada que comprobar: packaging/ trae archivos"
    for p in paquetes:
        assert p.suffix.lower() not in (".otf", ".woff", ".woff2"), f"fuente en el repo público: {p}"
        assert "akira" not in p.name.lower() and "tipografia" not in p.name.lower(), p


def test_las_herramientas_no_llevan_rutas_de_ningun_equipo():
    for nombre in ("suite_dmg.py", "suite_dmg_fondo.mjs", "construye_dmg.sh", "genera_icono.mjs", "genera_icono.sh"):
        texto = (PAQ / nombre).read_text(encoding="utf-8")
        assert not re.search(r"/Users/[A-Za-z0-9_.-]+/", texto), f"{nombre} lleva una ruta de usuario"


def test_la_clave_color_esta_en_los_distintivos():
    import json

    distintivos = json.loads((PAQ / "distintivos.json").read_text(encoding="utf-8"))
    assert "COLOR" in distintivos and "<path" in distintivos["COLOR"]


def test_el_alto_del_marco_de_finder_segun_el_macos(monkeypatch):
    """Medido capturando la ventana real: 28 pt (<=15), 68 pt (26), 32 pt (27). Fuerza SUITE_DMG_BARRA."""
    import platform

    sd = _cargar_suite_dmg()
    monkeypatch.delenv("SUITE_DMG_BARRA", raising=False)
    esperado = {"14.5": 28, "15.6": 28, "26.0": 68, "26.5": 68, "27.0": 32, "27.1": 32}
    for version, barra in esperado.items():
        monkeypatch.setattr(platform, "mac_ver", lambda v=version: (v, ("", "", ""), ""))
        assert sd._barra_finder() == barra, version
    monkeypatch.setenv("SUITE_DMG_BARRA", "50")
    assert sd._barra_finder() == 50


def test_akira_solo_se_busca_en_variable_de_entorno_o_en_gui_fuentes(monkeypatch, tmp_path):
    sd = _cargar_suite_dmg()
    monkeypatch.setenv("SUITE_AKIRA_OTF", str(tmp_path / "x.otf"))
    assert sd._buscar_akira() == str(tmp_path / "x.otf")
    monkeypatch.delenv("SUITE_AKIRA_OTF")
    monkeypatch.setattr(sd, "CARPETA_FUENTES", tmp_path)
    assert sd._buscar_akira() == ""
    (tmp_path / "SIDEBFLMS TIPOGRAFIA (c SIDEBFLMS).otf").write_bytes(b"")
    assert sd._buscar_akira().endswith("(c SIDEBFLMS).otf")
    monkeypatch.delenv("SUITE_MONTSERRAT", raising=False)
    assert Path(sd._buscar_montserrat()) == tmp_path


@pytest.mark.skipif(os.name != "posix", reason="script de bash")
def test_construye_dmg_tiene_sintaxis_valida_y_se_niega_sin_app(tmp_path):
    script = PAQ / "construye_dmg.sh"
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    sin_app = subprocess.run(["bash", str(script)], capture_output=True, text=True, cwd=tmp_path)
    assert sin_app.returncode == 2
    assert "todavia no tiene empaquetado" in sin_app.stderr
    no_app = subprocess.run(["bash", str(script), str(tmp_path)], capture_output=True, text=True, cwd=tmp_path)
    assert no_app.returncode == 2 and "No es una .app" in no_app.stderr
    falso = tmp_path / "Falsa.app"
    falso.mkdir()
    sin_icono = subprocess.run(
        ["bash", str(script), str(falso), "--icns", str(tmp_path / "no-existe.icns")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert sin_icono.returncode == 2 and "No existe el icono" in sin_icono.stderr


def test_construye_dmg_llama_a_suite_dmg_con_los_datos_de_color():
    texto = (PAQ / "construye_dmg.sh").read_text(encoding="utf-8")
    assert '--nombre "SIDEBFLMS COLOR"' in texto
    assert "--corto COLOR" in texto and "--distintivo COLOR" in texto
    assert "suite_dmg.py" in texto
