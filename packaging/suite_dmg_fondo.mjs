// Fondo de la ventana de instalación del .dmg · diseño de la suite SIDEBFLMS.
// Uso: node suite_dmg_fondo.mjs '<json>'   (lo llama suite_dmg.py; también se puede lanzar a mano)
// json: { appName, version, badge, mark, akira, montserrat, out, width, height, appCenter, appsCenter,
//         iconSize, frase, extras:[{x,y}], puppeteerFrom, chrome }
// Escribe out/background.png (1x) y out/background@2x.png (2x), sin metadata de escala (Finder la ignora).
// La fuente Akira SOLO se lee de la ruta que se le pasa para rasterizar el texto: no se copia a ningún sitio.
import { createRequire } from "node:module";
import { readFileSync, mkdirSync, existsSync, readdirSync, statSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { homedir } from "node:os";
import { join } from "node:path";

const cfg = JSON.parse(process.argv[2]);
function buscarPuppeteer() {
  if (cfg.puppeteerFrom) return cfg.puppeteerFrom;
  const npx = join(homedir(), ".npm", "_npx");
  if (existsSync(npx)) for (const d of readdirSync(npx))
    if (existsSync(join(npx, d, "node_modules", "puppeteer-core"))) return join(npx, d) + "/";
  console.error("No encuentro puppeteer-core: fija SUITE_PUPPETEER_FROM (carpeta con node_modules/puppeteer-core)."); process.exit(3);
}
const require = createRequire(buscarPuppeteer());
const puppeteer = require("puppeteer-core");

// Montserrat: un archivo variable (peso 100-900) o una CARPETA con los TTF estaticos del repo (400-800).
function carasMontserrat(ruta) {
  if (!statSync(ruta).isDirectory())
    return `@font-face{font-family:MontX;src:url("${pathToFileURL(ruta).href}");font-weight:100 900}`;
  const pesos = { Regular: 400, Medium: 500, SemiBold: 600, Bold: 700, ExtraBold: 800 };
  return Object.entries(pesos).map(([n, p]) =>
    `@font-face{font-family:MontX;src:url("${pathToFileURL(join(ruta, `Montserrat-${n}.ttf`)).href}");font-weight:${p}}`).join("\n");
}

const W = cfg.width, H = cfg.height;
const [ax, ay] = cfg.appCenter, [bx, by] = cfg.appsCenter;
const half = cfg.iconSize / 2;
const markSvg = readFileSync(cfg.mark, "utf8");
const markInner = markSvg.replace(/^[\s\S]*?<g>/, "").replace(/<\/g>[\s\S]*$/, "");
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

const hasExtras = (cfg.extras || []).length > 0;
const extraY = hasExtras ? cfg.extras[0].y : 0;

const html = `<!doctype html><meta charset="utf-8"><style>
@font-face{font-family:AkiraX;src:url("${pathToFileURL(cfg.akira).href}")}
${carasMontserrat(cfg.montserrat)}
html,body{margin:0;background:#1e1e1e}
svg{display:block}
.akira{font-family:AkiraX;fill:#f2ece4}
.sans{font-family:MontX}
.frase{font:600 16px MontX;fill:#f2ece4}
.sub{font:500 12px MontX;fill:#938e89}
.mini{font:500 11px MontX;fill:#938e89}
</style>
<svg id="s" xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<defs>
 <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#232323"/><stop offset=".6" stop-color="#1e1e1e"/><stop offset="1" stop-color="#191919"/></linearGradient>
 <radialGradient id="glow" gradientUnits="userSpaceOnUse" cx="${W * 0.06}" cy="${H * 0.02}" r="${W * 0.72}" gradientTransform="translate(${W * 0.06} ${H * 0.02}) scale(1 .78) translate(${-W * 0.06} ${-H * 0.02})">
  <stop offset="0" stop-color="#E8451D" stop-opacity=".44"/><stop offset=".45" stop-color="#E8451D" stop-opacity=".09"/><stop offset="1" stop-color="#E8451D" stop-opacity="0"/></radialGradient>
 <linearGradient id="arrow" gradientUnits="userSpaceOnUse" x1="${ax + half + 18}" y1="0" x2="${bx - half - 18}" y2="0">
  <stop offset="0" stop-color="#f2ece4" stop-opacity=".18"/><stop offset=".55" stop-color="#e8451d" stop-opacity=".85"/><stop offset="1" stop-color="#ff6a3d"/></linearGradient>
 <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".30"/><stop offset=".3" stop-color="#fff" stop-opacity=".07"/><stop offset=".62" stop-color="#fff" stop-opacity=".04"/><stop offset="1" stop-color="#E8451D" stop-opacity=".7"/></linearGradient>
 <linearGradient id="badgeEdge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".3" stop-color="#fff" stop-opacity=".10"/><stop offset=".62" stop-color="#fff" stop-opacity=".05"/><stop offset="1" stop-color="#E8451D" stop-opacity=".95"/></linearGradient>
 <filter id="soft"><feGaussianBlur stdDeviation="3"/></filter>
</defs>
<rect width="${W}" height="${H}" fill="url(#bg)"/>
<rect width="${W}" height="${H}" fill="url(#glow)"/>
<g id="contornos" fill="none" stroke="#f2ece4" stroke-opacity=".055" stroke-width="1"></g>
<!-- sello: el casete oficial blanco, pequeño, esquina superior izquierda -->
<g transform="translate(30 26) scale(${60 / 650})"><g transform="translate(-30 -35)" opacity=".96">${markInner}</g></g>
<!-- nombre -->
<text x="104" y="40" class="akira" style="font-size:10px;letter-spacing:.14em;fill:#ff6a3d">SIDEBFLMS</text>
<text id="nombre" x="104" y="72" class="akira" style="font-size:${cfg.nameSize || 32}px">${esc(cfg.appName)}</text>
<text x="105" y="94" class="sub">${esc(cfg.version ? "Versión " + cfg.version : "")}</text>
<!-- distintivo de la app (el mismo del icono), cristal arriba a la derecha -->
<g transform="translate(${W - 62} 54) scale(${0.36}) translate(-824 -248)">${cfg.badge}</g>
<!-- flecha: del icono de la app hacia Aplicaciones -->
<g>
 <line x1="${ax + half + 18}" y1="${ay}" x2="${bx - half - 22}" y2="${by}" stroke="#e8451d" stroke-opacity=".5" stroke-width="7" stroke-linecap="round" filter="url(#soft)"/>
 <line x1="${ax + half + 18}" y1="${ay}" x2="${bx - half - 22}" y2="${by}" stroke="url(#arrow)" stroke-width="3.5" stroke-linecap="round"/>
 <path d="M${bx - half - 36} ${by - 13} L${bx - half - 17} ${by} L${bx - half - 36} ${by + 13}" fill="none" stroke="#ff6a3d" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
</g>
<!-- peanas claras bajo las etiquetas: Finder pinta SIEMPRE en negro el nombre de los iconos cuando hay imagen de fondo -->
${[[ax, cfg.appLabel], [bx, "Aplicaciones"], ...(cfg.extras || []).map((e) => [e.x, e.label, e.y])].map(([x, t, y]) => {
  const w = Math.min(210, Math.max(86, t.length * 7.3 + 30)); const yy = (y ?? ay) + half + 6;
  return `<rect x="${x - w / 2}" y="${yy}" width="${w}" height="21" rx="10.5" fill="#f2ece4" fill-opacity=".93"/>`; }).join("")}
<!-- frase -->
<text x="${W / 2}" y="${ay + half + 78}" text-anchor="middle" class="frase">${esc(cfg.frase)}</text>
${hasExtras ? `<line x1="40" y1="${extraY - 62}" x2="${W - 40}" y2="${extraY - 62}" stroke="#fff" stroke-opacity=".07"/>` : ""}
${hasExtras ? "" : `<text x="${W - 30}" y="${H - 34}" text-anchor="end" class="mini">sidebflms.com</text>`}
<!-- filo fino, dentro del marco -->
<rect x="8.5" y="8.5" width="${W - 17}" height="${H - 17}" rx="18" fill="none" stroke="url(#edge)" stroke-width="1"/>
</svg>
<script>
// Curvas de nivel: campo suave (suma de senos) + marching squares. Misma idea que el fondo de la web.
(function(){
 const W=${W},H=${H},step=6,nx=Math.ceil(W/step)+1,ny=Math.ceil(H/step)+1;
 const f=(x,y)=>Math.sin(x*.011+1.3)*.9+Math.sin(y*.016-.4)*.7+Math.sin((x+y)*.0075+2.1)*.8+Math.sin(Math.hypot(x-60,y-20)*.012)*1.1;
 const g=[];for(let j=0;j<ny;j++){g[j]=[];for(let i=0;i<nx;i++)g[j][i]=f(i*step,j*step);}
 let d="";
 for(let L=-3.2;L<=3.2;L+=.42){
  const P=(x0,y0,v0,x1,y1,v1)=>{const t=(L-v0)/(v1-v0);return [x0+(x1-x0)*t,y0+(y1-y0)*t];};
  for(let j=0;j<ny-1;j++)for(let i=0;i<nx-1;i++){
   const x=i*step,y=j*step,a=g[j][i],b=g[j][i+1],c=g[j+1][i+1],e=g[j+1][i];
   const k=(a>L?8:0)|(b>L?4:0)|(c>L?2:0)|(e>L?1:0);if(k===0||k===15)continue;
   const T=()=>P(x,y,a,x+step,y,b),R=()=>P(x+step,y,b,x+step,y+step,c),B=()=>P(x,y+step,e,x+step,y+step,c),Le=()=>P(x,y,a,x,y+step,e);
   const seg=(p,q)=>{d+="M"+p[0].toFixed(1)+" "+p[1].toFixed(1)+"L"+q[0].toFixed(1)+" "+q[1].toFixed(1);};
   switch(k){case 1:case 14:seg(Le(),B());break;case 2:case 13:seg(B(),R());break;case 3:case 12:seg(Le(),R());break;
    case 4:case 11:seg(T(),R());break;case 5:seg(T(),Le());seg(B(),R());break;case 6:case 9:seg(T(),B());break;
    case 7:case 8:seg(T(),Le());break;case 10:seg(T(),R());seg(Le(),B());break;}
  }
 }
 const p=document.createElementNS("http://www.w3.org/2000/svg","path");p.setAttribute("d",d);p.setAttribute("stroke-linecap","round");
 document.getElementById("contornos").appendChild(p);
})();
</script>`;

mkdirSync(cfg.out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: cfg.chrome || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true, args: ["--allow-file-access-from-files"],
});
try {
  for (const scale of [1, 2]) {
    const page = await browser.newPage();
    await page.setViewport({ width: W, height: H, deviceScaleFactor: scale });
    // file:// para que las @font-face de ruta local carguen
    const tmp = cfg.out + "/_fondo.html";
    (await import("node:fs")).writeFileSync(tmp, html);
    await page.goto(pathToFileURL(tmp).href, { waitUntil: "load" });
    // con TTF estaticos cada peso es una cara distinta y se carga al usarla: se piden todas antes de comprobar
    await page.evaluate(() => Promise.all(["12px AkiraX", "400 12px MontX", "500 12px MontX", "600 12px MontX", "700 12px MontX", "800 12px MontX"].map((f) => document.fonts.load(f))));
    await page.evaluate(() => document.fonts.ready);
    const ok = await page.evaluate(() => document.fonts.check("12px AkiraX") && document.fonts.check("12px MontX"));
    if (!ok) throw new Error("no cargaron las fuentes (Akira/Montserrat)");
    const file = cfg.out + (scale === 1 ? "/background.png" : "/background@2x.png");
    await page.screenshot({ path: file, type: "png", clip: { x: 0, y: 0, width: W, height: H }, omitBackground: false });
    await page.close();
  }
  (await import("node:fs")).unlinkSync(cfg.out + "/_fondo.html");
} finally { await browser.close(); }
