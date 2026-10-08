#!/bin/bash
# Regenera packaging/AppIcon.iconset y packaging/AppIcon.icns desde packaging/icono/*.svg.
# (>=128 px: COLOR-maestro.svg; <=64 px: COLOR-solo-casete.svg con el contorno engrosado; ver genera_icono.mjs.)
# Los SVG llevan el nombre en contornos: no hace falta Akira. Necesita Node + Chrome + puppeteer-core.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$AQUI/AppIcon.iconset"
node "$AQUI/genera_icono.mjs" "$AQUI/icono" "$AQUI/AppIcon.iconset"
iconutil -c icns "$AQUI/AppIcon.iconset" -o "$AQUI/AppIcon.icns"
echo "OK: $AQUI/AppIcon.icns"
