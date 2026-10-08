#!/usr/bin/env python3
"""suite_dmg.py -- UNA herramienta para hacer el .dmg de instalación de TODAS las apps de macOS de SIDEBFLMS
(DIT, AutoEDIT, COLOR, Downloader, COMPRESSOR) con la misma ventana de la suite.

COPIA de `sidebflms-design` -> reviews/2026-10-08-dmg/ (prototipo de la suite), adaptada a este repo, que es PUBLICO:
  - NO hay ninguna ruta de un equipo concreto: Akira se busca en SUITE_AKIRA_OTF o en `gui/fuentes/` (carpeta fuera del
    control de versiones para los .otf: ver .gitignore) y NUNCA se copia ni se versiona; Montserrat (OFL) sale de
    `gui/fuentes/` (SUITE_MONTSERRAT la sustituye); puppeteer-core se busca en SUITE_PUPPETEER_FROM o en ~/.npm/_npx.
  - Si falta una fuente, el error lo dice con la variable a fijar. El fondo lleva las letras RASTERIZADAS (PNG).

Python 3.9+, solo biblioteca estándar. Para pintar el fondo llama a Node + Chrome headless (puppeteer-core)
a través de `suite_dmg_fondo.mjs` (no hace falta PySide6 en el entorno de cada app).

USO COMO BIBLIOTECA
    from suite_dmg import construir_dmg
    r = construir_dmg(app="dist/SIDEBFLMS DIT.app", nombre="SIDEBFLMS DIT", corto="DIT", version="2.3.0",
                      icns="packaging/AppIcon.icns", salida="~/Downloads", distintivo="DIT")
    print(r.dmg, r.ventana_colocada)

USO COMO COMANDO
    python3 suite_dmg.py --app X.app --nombre "SIDEBFLMS DIT" --corto DIT --version 2.3.0 \
        --icns AppIcon.icns --salida carpeta --distintivo DIT [--extra "LEEME.txt" ...] [--solo-fondo]

LAS TRAMPAS (todas comprobadas por DIT/AutoEdit y aquí):
 1. Finder recuerda el tamaño de ventana por el NOMBRE del volumen -> se monta con nombre temporal único y se
    renombra al final (diskutil rename por nodo de dispositivo) con la ventana ya cerrada.
 2. Fondo = DOS PNG, background.png 660x400 y background@2x.png 1320x800, sin metadata de escala. Finder elige
    el @2x solo en Retina. Los puntos de la ventana = píxeles del 1x.
 3. El marco superior de la ventana de Finder se come 28 pt (macOS<=15) o 68 pt (macOS 26) del area de bounds: aqui
    los bounds suman TITLEBAR a la altura para que el area de contenido sea el tamaño del fondo (medido, ver INFORME).
 4. AppleScript exige permiso de automatizacion de Finder; si nadie contesta caduca. Se pone `with timeout of 60`
    y un timeout de subprocess; si falla, el .dmg sigue siendo valido (se abre en lista) y se devuelve
    ventana_colocada=False con el motivo -- nunca se calla.
 5. Tras close/open Finder a veces recoloca los iconos en su rejilla: se re-verifican las posiciones y se
    re-piden una vez (como construye_dmg.sh de AutoEdit).
 6. .VolumeIcon.icns se pone DESPUES de la ventana de Finder (si no, se pierde) + SetFile -a C.
 7. Nunca expulsar por nombre/puerto: el desmontaje es por nodo de dispositivo (/dev/diskN) del volumen PROPIO.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

AQUI = Path(__file__).resolve().parent

# La plantilla clasica (la misma que ya exportan DIT y AutoEdit: coinciden con la receta por defecto de create-dmg).
WINDOW_WIDTH = 660
WINDOW_HEIGHT = 400
ICON_SIZE = 100
APP_ICON_CENTER = (180, 190)
APPLICATIONS_ICON_CENTER = (480, 190)
def _barra_finder() -> int:
    """Alto del marco superior de la ventana de Finder (titulo + barra), que se resta del area de bounds.
    MEDIDO (capturando la ventana real): 28 pt en macOS <= 15; 68 pt en macOS 26 (Tahoe), aunque la barra de herramientas
    este oculta (segunda fila con el nombre del volumen); **32 pt en macOS 27.0** (una sola fila de titulo: con 68 la
    ventana salia 36 pt mas alta y quedaba una franja blanca debajo del fondo).
    Se puede forzar con SUITE_DMG_BARRA. El fondo es de 400 de alto: si la ventana abre en un macOS con menos marco
    que el de construccion se recorta abajo (por eso lo esencial esta por encima de y=350)."""
    if os.environ.get("SUITE_DMG_BARRA"):
        return int(os.environ["SUITE_DMG_BARRA"])
    import platform
    mayor = int((platform.mac_ver()[0] or "0").split(".")[0] or 0)
    if mayor >= 27:
        return 32
    return 68 if mayor == 26 else 28


TITLEBAR = _barra_finder()
EXTRAS_HEIGHT = 542      # con archivos extra (notas, aviso de cuarentena) la ventana crece
EXTRAS_Y = 425

REPO = AQUI.parent                      # packaging/ vive en la raiz del repo
CARPETA_FUENTES = REPO / "gui" / "fuentes"


def _buscar_akira() -> str:
    """SUITE_AKIRA_OTF, o un .otf de Akira dentro de gui/fuentes/ (donde Mario lo copia a mano; no se versiona)."""
    if os.environ.get("SUITE_AKIRA_OTF"):
        return os.environ["SUITE_AKIRA_OTF"]
    if CARPETA_FUENTES.is_dir():
        for f in sorted(CARPETA_FUENTES.glob("*.otf")):
            if "akira" in f.name.lower() or "tipografia" in f.name.lower():
                return str(f)
    return ""


def _buscar_montserrat() -> str:
    """SUITE_MONTSERRAT (archivo variable o carpeta con los TTF estaticos), o gui/fuentes/ de este repo (OFL)."""
    return os.environ.get("SUITE_MONTSERRAT") or str(CARPETA_FUENTES)


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


@dataclass
class Resultado:
    dmg: Path
    fondo_1x: Path
    fondo_2x: Path
    ventana_colocada: bool = False
    aviso: str = ""
    icono_volumen: bool = False
    comprobaciones: List[str] = field(default_factory=list)


def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def _distintivo(distintivo: str) -> str:
    """`distintivo` = clave (DIT, AUTOEDIT, COLOR, DOWNLOADER, COMPRESSOR, ...) de distintivos.json, o un fragmento SVG."""
    if distintivo.lstrip().startswith("<"):
        return distintivo
    datos = json.loads((AQUI / "distintivos.json").read_text())
    return datos[distintivo.upper()]


def dimensiones(extras: bool):
    return (WINDOW_WIDTH, EXTRAS_HEIGHT if extras else WINDOW_HEIGHT)


def generar_fondo(destino: Path, nombre: str, corto: str, version: str, distintivo: str,
                  frase: Optional[str] = None, extras: int = 0, etiqueta_app: Optional[str] = None,
                  etiquetas_extras: Optional[List[str]] = None) -> Path:
    """Escribe destino/background.png y destino/background@2x.png. Devuelve la ruta del 1x."""
    akira = _buscar_akira()
    montserrat = _buscar_montserrat()
    for etiqueta, ruta, variable in (("Akira", akira, "SUITE_AKIRA_OTF"), ("Montserrat", montserrat, "SUITE_MONTSERRAT")):
        if not ruta or not Path(ruta).exists():
            raise FileNotFoundError(
                f"Falta la fuente {etiqueta} ({ruta or 'sin ruta'}): fija {variable} o, para Akira, copia el .otf a "
                f"gui/fuentes/ (no se versiona)")
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    w, h = dimensiones(bool(extras))
    extras_pos = []
    if extras:
        xs = {1: [APP_ICON_CENTER[0]], 2: [APP_ICON_CENTER[0], APPLICATIONS_ICON_CENTER[0]]}.get(extras)
        xs = xs or [int(60 + i * (w - 120) / (extras - 1)) for i in range(extras)]
        extras_pos = [{"x": x, "y": EXTRAS_Y, "label": (etiquetas_extras or ["archivo"] * extras)[i]} for i, x in enumerate(xs)]
    cfg = {
        "appName": corto, "appLabel": etiqueta_app or nombre, "version": version, "badge": _distintivo(distintivo),
        "mark": str(AQUI / "casete-oficial-blanco.svg"), "akira": akira, "montserrat": montserrat,
        "out": str(destino), "width": w, "height": h, "appCenter": APP_ICON_CENTER,
        "appsCenter": APPLICATIONS_ICON_CENTER, "iconSize": ICON_SIZE,
        "frase": frase or f"Arrastra {nombre} a Aplicaciones", "extras": extras_pos,
        "puppeteerFrom": os.environ.get("SUITE_PUPPETEER_FROM", ""),
        "chrome": os.environ.get("SUITE_CHROME", CHROME),
    }
    destino.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([node, str(AQUI / "suite_dmg_fondo.mjs"), json.dumps(cfg)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("no se pudo pintar el fondo:\n" + r.stderr[-1500:])
    return destino / "background.png"


def _applescript(volumen: str, app_nombre: str, extras: List[str], w: int, h: int, fondo: str = "background.png") -> str:
    bx, by = 400, 120
    ax, ay = APP_ICON_CENTER
    px, py = APPLICATIONS_ICON_CENTER
    pos = [(app_nombre + ".app", ax, ay), ("Aplicaciones", px, py)]
    if extras:
        xs = {1: [ax], 2: [ax, px]}.get(len(extras)) or [int(60 + i * (w - 120) / (len(extras) - 1)) for i in range(len(extras))]
        pos += [(n, x, EXTRAS_Y) for n, x in zip(extras, xs)]
    lista = ", ".join('{"%s", %d, %d}' % (n.replace('"', '\\"'), x, y) for n, x, y in pos)
    return f'''
on run
  set posiciones to {{{lista}}}
  with timeout of 60 seconds
    tell application "Finder"
      tell disk "{volumen}"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {{{bx}, {by}, {bx + w}, {by + h + TITLEBAR}}}
        set opciones to the icon view options of container window
        set arrangement of opciones to not arranged
        set icon size of opciones to {ICON_SIZE}
        set text size of opciones to 12
        set label position of opciones to bottom
        set background picture of opciones to file ".background:{fondo}"
        repeat with p in posiciones
          set position of item (item 1 of p) to {{item 2 of p, item 3 of p}}
        end repeat
        close
        open
        update without registering applications
        delay 2
        set opciones to the icon view options of container window
        set arrangement of opciones to not arranged
        repeat with intento from 1 to 2
          set descuadrado to false
          repeat with p in posiciones
            set pos to position of item (item 1 of p)
            if (item 1 of pos) is not (item 2 of p) or (item 2 of pos) is not (item 3 of p) then
              set descuadrado to true
              set position of item (item 1 of p) to {{item 2 of p, item 3 of p}}
            end if
          end repeat
          if not descuadrado then exit repeat
          update without registering applications
          delay 1
        end repeat
        close
      end tell
    end tell
  end timeout
end run
'''


def construir_dmg(app, nombre: str, corto: str, version: str, icns, salida, distintivo: str,
                  extras: Optional[List] = None, nombre_dmg: Optional[str] = None,
                  volumen: Optional[str] = None, frase: Optional[str] = None,
                  conservar_fondo: Optional[Path] = None) -> Resultado:
    """Construye `<salida>/<nombre_dmg or "nombre version">.dmg`. `extras` = archivos opcionales (notas, aviso de
    cuarentena...) que viajan dentro en una segunda fila. `volumen` = nombre final del volumen (por defecto `nombre`)."""
    app, icns, salida = Path(app).expanduser(), Path(icns).expanduser(), Path(salida).expanduser()
    extras = [Path(e).expanduser() for e in (extras or [])]
    if not app.is_dir() or app.suffix != ".app":
        raise FileNotFoundError(f"No es una .app: {app}")
    if not icns.is_file():
        raise FileNotFoundError(f"No existe el icono: {icns}")
    volumen = volumen or nombre
    dmg_final = salida / ((nombre_dmg or f"{nombre} {version}") + ".dmg")
    salida.mkdir(parents=True, exist_ok=True)
    w, h = dimensiones(bool(extras))

    tmp = Path(tempfile.mkdtemp(prefix="suite_dmg_"))
    escenario = tmp / "escenario"
    crudo = tmp / "crudo.dmg"
    nodo = None
    try:
        escenario.mkdir()
        _run(["ditto", str(app), str(escenario / app.name)])
        (escenario / "Aplicaciones").symlink_to("/Applications")
        for e in extras:
            shutil.copy2(e, escenario / e.name)
        shutil.copy2(icns, escenario / ".VolumeIcon.icns")
        fondo = generar_fondo(escenario / ".background", nombre, corto, version, distintivo, frase, len(extras), app.stem, [e.name for e in extras])
        # 2x de verdad: Finder NO escoge solo el background@2x.png (medido en macOS 26: se ve el 1x ampliado y borroso).
        # Lo que si funciona es un TIFF multi-representacion (el truco de create-dmg/dmgbuild): 1x + 2x en un archivo.
        fondo_finder = "background.png"
        t = subprocess.run(["tiffutil", "-cathidpicheck", str(fondo), str(fondo.with_name("background@2x.png")),
                            "-out", str(fondo.with_name("background.tiff"))], capture_output=True, text=True)
        if t.returncode == 0:
            fondo_finder = "background.tiff"
        if conservar_fondo:
            conservar_fondo = Path(conservar_fondo)
            conservar_fondo.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fondo, conservar_fondo / "background.png")
            shutil.copy2(fondo.with_name("background@2x.png"), conservar_fondo / "background@2x.png")

        temporal = f"{volumen} staging {uuid.uuid4().hex[:8]}"        # trampa 1: nombre que Finder nunca vio
        megas = int(sum(f.stat().st_size for f in escenario.rglob("*") if f.is_file()) / 1e6) + 60
        _run(["hdiutil", "create", "-volname", temporal, "-srcfolder", str(escenario), "-fs", "HFS+",
              "-format", "UDRW", "-size", f"{megas}m", "-ov", str(crudo)])
        info = plistlib.loads(subprocess.run(["hdiutil", "attach", "-readwrite", "-noverify", "-noautoopen", "-plist", str(crudo)],
                                             check=True, capture_output=True).stdout)
        ent = next(e for e in info["system-entities"] if e.get("mount-point"))
        nodo, punto = ent["dev-entry"], ent["mount-point"]

        colocada, aviso = False, ""
        try:
            r = subprocess.run(["osascript", "-e", _applescript(temporal, app.stem, [e.name for e in extras], w, h, fondo_finder)],
                               capture_output=True, text=True, timeout=90)
            if r.returncode == 0:
                colocada = True
            else:
                aviso = ("Finder no contesto (falta el permiso de Automatizacion del Finder para este Terminal/app, o caduco "
                         "el evento). El .dmg es valido igual; se abrira en lista. Ajustes > Privacidad y seguridad > "
                         "Automatizacion. Detalle: " + r.stderr.strip()[:300])
        except subprocess.TimeoutExpired:
            aviso = "Finder no contesto en 90 s (permiso de automatizacion sin conceder). El .dmg es valido; se abrira en lista."

        subprocess.run(["sync"])
        _run(["diskutil", "rename", nodo, volumen])                    # ventana ya cerrada: nombre definitivo
        punto = plistlib.loads(subprocess.run(["diskutil", "info", "-plist", nodo], capture_output=True).stdout).get("MountPoint")
        # trampa 6: el icono del volumen, DESPUES de Finder
        icono = False
        if isinstance(punto, str):
            shutil.copy2(icns, Path(punto) / ".VolumeIcon.icns")
            subprocess.run(["SetFile", "-a", "C", punto], capture_output=True)
            icono = (Path(punto) / ".VolumeIcon.icns").exists()
        subprocess.run(["sync"])
        _run(["hdiutil", "detach", nodo])                              # trampa 7: por nodo
        nodo = None

        if dmg_final.exists():
            dmg_final.unlink()
        _run(["hdiutil", "convert", str(crudo), "-format", "UDZO", "-imagekey", "zlib-level=9", "-o", str(dmg_final)])
        res = Resultado(dmg_final, fondo, fondo.with_name("background@2x.png"), colocada, aviso, icono)
        res.comprobaciones = comprobar(dmg_final, app.name, [e.name for e in extras])
        return res
    finally:
        if nodo:
            subprocess.run(["hdiutil", "detach", nodo, "-force"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def comprobar(dmg: Path, app_nombre: str, extras: List[str]) -> List[str]:
    """Monta una copia de SOLO LECTURA en un punto de montaje propio, mira el contenido y desmonta ese punto."""
    mp = Path(tempfile.mkdtemp(prefix="suite_dmg_mp_"))
    out = []
    try:
        _run(["hdiutil", "attach", "-readonly", "-nobrowse", "-noverify", "-mountpoint", str(mp), str(dmg)])
        def c(desc, ok): out.append(("OK    " if ok else "FALLA ") + desc)
        c("la aplicacion esta dentro", (mp / app_nombre).is_dir())
        c("enlace Aplicaciones -> /Applications", (mp / "Aplicaciones").is_symlink() and os.readlink(mp / "Aplicaciones") == "/Applications")
        c("fondo 1x y 2x en .background (y TIFF retina)", (mp / ".background/background.png").exists() and (mp / ".background/background@2x.png").exists() and (mp / ".background/background.tiff").exists())
        ds = (mp / ".DS_Store")
        datos = ds.read_bytes().replace(b"\x00", b"") if ds.exists() else b""
        c(".DS_Store con la disposicion (fondo y bounds)", b"background.tiff" in datos or b"background.png" in datos)
        for e in extras:
            c(f"extra {e}", (mp / e).exists())
        c("icono del volumen", (mp / ".VolumeIcon.icns").exists())
    finally:
        subprocess.run(["hdiutil", "detach", str(mp)], capture_output=True)
        try: mp.rmdir()
        except OSError: pass
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="DMG de instalacion con la ventana de la suite SIDEBFLMS")
    p.add_argument("--app", required=True); p.add_argument("--nombre", required=True)
    p.add_argument("--corto", required=True, help="nombre en Akira, solo ASCII (DIT, AUTOEDIT, COLOR...)")
    p.add_argument("--version", required=True); p.add_argument("--icns", required=True)
    p.add_argument("--salida", required=True); p.add_argument("--distintivo", required=True)
    p.add_argument("--extra", action="append", default=[]); p.add_argument("--volumen")
    p.add_argument("--nombre-dmg"); p.add_argument("--solo-fondo", action="store_true")
    a = p.parse_args(argv)
    if a.solo_fondo:
        print(generar_fondo(Path(a.salida), a.nombre, a.corto, a.version, a.distintivo, None, len(a.extra)))
        return 0
    r = construir_dmg(a.app, a.nombre, a.corto, a.version, a.icns, a.salida, a.distintivo, a.extra,
                      a.nombre_dmg, a.volumen)
    print("dmg:", r.dmg)
    for l in r.comprobaciones: print("  ", l)
    print("ventana colocada:", r.ventana_colocada)
    if r.aviso: print("AVISO:", r.aviso, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
