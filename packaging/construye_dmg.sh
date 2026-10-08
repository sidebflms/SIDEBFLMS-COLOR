#!/bin/bash
# Construye el .dmg de instalacion de SIDEBFLMS COLOR con la ventana de la suite SIDEBFLMS.
#
# IMPORTANTE: COLOR todavia NO tiene empaquetado de .app (PyInstaller, py2app o lo que se elija): este
# script NO lo inventa. Recibe una .app YA CONSTRUIDA y solo hace la ventana del .dmg, llamando a
# suite_dmg.py con los datos de COLOR (--nombre "SIDEBFLMS COLOR" --corto COLOR --distintivo COLOR).
#
# Uso:
#   packaging/construye_dmg.sh RUTA/SIDEBFLMS\ COLOR.app [opciones]
#     --version X.Y.Z   (por defecto, la de pyproject.toml)
#     --icns ARCHIVO    (por defecto, packaging/AppIcon.icns; la .app deberia llevar ese mismo icono)
#     --salida CARPETA  (por defecto, ./dist)
#     --volumen NOMBRE  (nombre final del volumen; por defecto, "SIDEBFLMS COLOR")
#     --solo-fondo      (solo pinta el fondo de la ventana en --salida; no necesita la .app)
#
# Fuentes (ninguna se versiona si es de licencia propia):
#   - Montserrat (OFL): sale de gui/fuentes/ de este repo.
#   - Akira: SUITE_AKIRA_OTF=/ruta/al/.otf, o copiada a mano a gui/fuentes/ (esta en .gitignore). Se lee
#     para RASTERIZAR el fondo; el .dmg solo lleva la imagen, nunca la fuente.
#   - Hace falta Node + Google Chrome + puppeteer-core (SUITE_PUPPETEER_FROM, SUITE_CHROME si no estan en su sitio).
# Si Finder no contesta (permiso de Automatizacion), el .dmg es valido igualmente: se abre en lista y
# suite_dmg.py lo avisa por la salida de error.
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$AQUI/.." && pwd)"

VERSION="$(grep -m1 -E '^version *= *"' "$RAIZ/pyproject.toml" 2>/dev/null | sed -E 's/^version *= *"([^"]+)".*/\1/' || true)"
VERSION="${VERSION:-0.0.0}"
ICNS="$AQUI/AppIcon.icns"
SALIDA="$PWD/dist"
VOLUMEN=""
SOLO_FONDO=0
APP=""

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --icns) ICNS="$2"; shift 2 ;;
    --salida) SALIDA="$2"; shift 2 ;;
    --volumen) VOLUMEN="$2"; shift 2 ;;
    --solo-fondo) SOLO_FONDO=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    -*) echo "Opcion desconocida: $1" >&2; exit 2 ;;
    *) APP="$1"; shift ;;
  esac
done

PY="$(command -v python3)"
EXTRA=()
[ -n "$VOLUMEN" ] && EXTRA+=(--volumen "$VOLUMEN")

if [ "$SOLO_FONDO" = 1 ]; then
  exec "$PY" "$AQUI/suite_dmg.py" --app x.app --nombre "SIDEBFLMS COLOR" --corto COLOR --distintivo COLOR \
       --version "$VERSION" --icns "$ICNS" --salida "$SALIDA" --solo-fondo
fi

if [ -z "$APP" ]; then
  echo "Falta la .app ya construida. COLOR todavia no tiene empaquetado de .app: esto solo hace el .dmg." >&2
  echo "Uso: $0 RUTA/SIDEBFLMS\\ COLOR.app [--version X] [--icns F] [--salida DIR]" >&2
  exit 2
fi
[ -d "$APP" ] && [ "${APP%.app}" != "$APP" ] || { echo "No es una .app: $APP" >&2; exit 2; }
[ -f "$ICNS" ] || { echo "No existe el icono: $ICNS (genera packaging/AppIcon.icns con packaging/genera_icono.sh)" >&2; exit 2; }

exec "$PY" "$AQUI/suite_dmg.py" --app "$APP" --nombre "SIDEBFLMS COLOR" --corto COLOR --distintivo COLOR \
     --version "$VERSION" --icns "$ICNS" --salida "$SALIDA" "${EXTRA[@]+"${EXTRA[@]}"}"
