// Genera AppIcon.iconset (y, con iconutil, AppIcon.icns) del icono de SIDEBFLMS COLOR.
// Regla del diseño (sidebflms-design · reviews/2026-10-08-iconos/INFORME.md):
//   - desde 128 px: COLOR-maestro.svg (casete oficial blanco + nombre en contornos + distintivo);
//   - a 64 px o menos: COLOR-solo-casete.svg (sin nombre) con el contorno del casete engrosado:
//     9 unidades a 64 px, 16 a 32 px, 26 a 16 px.
// Los SVG llevan el nombre en CONTORNOS (ni <text> ni fuente): no hace falta Akira para generar nada.
// Uso: node genera_icono.mjs <carpeta de los SVG> <salida .iconset>
//   SUITE_PUPPETEER_FROM = carpeta con node_modules/puppeteer-core (por defecto, la primera de ~/.npm/_npx)
//   SUITE_CHROME         = ejecutable de Chrome (por defecto, el de /Applications)
import { createRequire } from "node:module";
import { readFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const [carpetaSvg, salida] = process.argv.slice(2);
if (!carpetaSvg || !salida) { console.error("uso: node genera_icono.mjs <carpeta SVG> <salida.iconset>"); process.exit(2); }

function buscarPuppeteer() {
  if (process.env.SUITE_PUPPETEER_FROM) return process.env.SUITE_PUPPETEER_FROM;
  const npx = join(homedir(), ".npm", "_npx");
  if (existsSync(npx)) for (const d of readdirSync(npx))
    if (existsSync(join(npx, d, "node_modules", "puppeteer-core"))) return join(npx, d) + "/";
  console.error("No encuentro puppeteer-core. Fija SUITE_PUPPETEER_FROM (carpeta que contenga node_modules/puppeteer-core)."); process.exit(3);
}
const puppeteer = createRequire(buscarPuppeteer())("puppeteer-core");
const chrome = process.env.SUITE_CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

// [nombre del archivo, píxeles]
const TAMANOS = [
  ["icon_16x16", 16], ["icon_16x16@2x", 32], ["icon_32x32", 32], ["icon_32x32@2x", 64],
  ["icon_128x128", 128], ["icon_128x128@2x", 256], ["icon_256x256", 256], ["icon_256x256@2x", 512],
  ["icon_512x512", 512], ["icon_512x512@2x", 1024],
];
const contorno = (px) => (px <= 16 ? 26 : px <= 32 ? 16 : 9);

mkdirSync(salida, { recursive: true });
const maestro = readFileSync(join(carpetaSvg, "COLOR-maestro.svg"), "utf8");
const solo = readFileSync(join(carpetaSvg, "COLOR-solo-casete.svg"), "utf8");
if (!/stroke-width="16"/.test(solo)) { console.error("COLOR-solo-casete.svg ya no trae el contorno de 16 que se sustituye por tamaño"); process.exit(4); }

const browser = await puppeteer.launch({ executablePath: chrome, headless: "new", args: ["--no-sandbox", "--hide-scrollbars"] });
try {
  const page = await browser.newPage();
  for (const [nombre, px] of TAMANOS) {
    const svg = px >= 128 ? maestro : solo.replace('stroke-width="16"', `stroke-width="${contorno(px)}"`);
    await page.setViewport({ width: px, height: px, deviceScaleFactor: 1 });
    await page.setContent(`<!doctype html><style>html,body{margin:0;background:transparent}svg{display:block;width:${px}px;height:${px}px}</style>${svg}`);
    await page.screenshot({ path: join(salida, nombre + ".png"), omitBackground: true, clip: { x: 0, y: 0, width: px, height: px } });
    console.log(nombre, px, px >= 128 ? "maestro" : `solo-casete (contorno ${contorno(px)})`);
  }
} finally { await browser.close(); }
