"""Primera prueba de SIDEBFLMS COLOR con material real: medir, sin tocar el origen.

Lee un master coloreado y los brutos con los que se hizo, localiza cada bruto
dentro del master, saca el grado plano a plano y mide T1, T5 y la cobertura del
cubo. Escribe un informe en `pruebas/trabajo/<fecha-hora>/`.

GARANTIAS, EN EL CODIGO Y NO SOLO EN LA INTENCION
-------------------------------------------------
1. **Solo lectura sobre el origen.** Toda escritura pasa por `pruebas.guarda.Guarda`,
   que solo deja escribir dentro de `pruebas/trabajo/` y nunca dentro de una
   carpeta de origen ni de `/Volumes`. ffmpeg solo escribe en la memoria
   (`pruebas.lectura`). No se copian los brutos: se leen los fotogramas que se
   usan, directamente del origen.
2. **Rutas explicitas.** `--master` y `--brutos`. Sin ellas no hace nada. No
   busca material por el disco.
3. **Simulacro por defecto.** Sin `--ejecutar` solo dice que haria. No crea ni
   la carpeta de trabajo.
4. **No habla con DaVinci Resolve.** No lo importa.

Uso: ver `--help` y `pruebas/COMO-HACER-LA-PRIMERA-PRUEBA.md`.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import math
import sys
import time
import traceback
from pathlib import Path

if __package__ in (None, ""):  # ejecutado como `python pruebas/primera_real.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from core.color import SPACES  # noqa: E402
from pruebas import coste as _coste  # noqa: E402
from pruebas import lectura, localizar, medir  # noqa: E402
from pruebas.guarda import RAIZ_TRABAJO, EscrituraProhibida, Guarda  # noqa: E402
from pruebas.origen import OrigenRechazado, listar_brutos, validar_master  # noqa: E402

__all__ = ["main"]

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_FALTAN_ARGUMENTOS = 2
SALIDA_RECHAZADO = 3

_EJEMPLO = """\
ejemplos (las rutas son INVENTADAS, pon las tuyas):

  simulacro, no escribe nada:
    .venv/bin/python pruebas/primera_real.py \\
        --master "/Volumes/EJEMPLO_DISCO/TRABAJO_EJEMPLO/MASTER_EJEMPLO.mov" \\
        --brutos "/Volumes/EJEMPLO_DISCO/TRABAJO_EJEMPLO/BRUTOS_EJEMPLO"

  de verdad:
    .venv/bin/python pruebas/primera_real.py \\
        --master "/Volumes/EJEMPLO_DISCO/TRABAJO_EJEMPLO/MASTER_EJEMPLO.mov" \\
        --brutos "/Volumes/EJEMPLO_DISCO/TRABAJO_EJEMPLO/BRUTOS_EJEMPLO" \\
        --espacio-brutos slog3_sgamut3cine \\
        --ejecutar

El informe queda en pruebas/trabajo/<fecha-hora>/informe.md. Instrucciones
completas: pruebas/COMO-HACER-LA-PRIMERA-PRUEBA.md
"""


def _parser() -> argparse.ArgumentParser:
    espacios = ["auto", *SPACES.keys()]
    p = argparse.ArgumentParser(
        prog="primera_real.py",
        description=(
            "Primera prueba con material real. Localiza cada bruto dentro del master "
            "coloreado, saca el grado y mide T1 (el grado sobre su propio plano), T5 (el "
            "grado de un plano aplicado a los demas) y la cobertura del cubo. SOLO LEE el "
            "origen; escribe unicamente en pruebas/trabajo/. SIN --ejecutar ES UN SIMULACRO: "
            "dice que haria y no escribe nada. No se conecta a DaVinci Resolve."
        ),
        epilog=_EJEMPLO,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p.add_argument("-h", "--help", action="help", help="muestra esta ayuda y sale")
    p.add_argument("--master", metavar="RUTA",
                   help="el master coloreado: UN fichero de video (ProRes, DNxHR, H.264/H.265)")
    p.add_argument("--brutos", metavar="RUTA", nargs="+",
                   help="los brutos: ficheros o carpetas. Una carpeta se recorre entera, "
                        "sin salir de ella")
    p.add_argument("--ejecutar", action="store_true",
                   help="hacerlo de verdad. Sin esto, solo simulacro")
    p.add_argument("--espacio-master", default="auto", choices=espacios, metavar="ESPACIO",
                   help="espacio de color del master (por defecto: lo que digan los metadatos, "
                        "o rec709). Opciones: " + ", ".join(espacios))
    p.add_argument("--espacio-brutos", default="auto", choices=espacios, metavar="ESPACIO",
                   help="espacio de color de TODOS los brutos. Si son log, dilo aqui "
                        "(p. ej. slog3_sgamut3cine): los metadatos casi nunca lo dicen")
    p.add_argument("--ancho-analisis", type=int, default=960, metavar="PX",
                   help="ancho al que se mide el grado (por defecto 960)")
    p.add_argument("--paso", type=int, default=localizar.PASO_MASTER, metavar="FOTOGRAMAS",
                   help=f"cada cuantos fotogramas del master se busca (por defecto "
                        f"{localizar.PASO_MASTER})")
    p.add_argument("--escala-minima", type=float, default=localizar.ESCALA_MINIMA,
                   metavar="FRACCION",
                   help=f"reencuadre mas cerrado que se busca, como fraccion del ancho del "
                        f"bruto (por defecto {localizar.ESCALA_MINIMA})")
    return p


def _mb(b: float) -> str:
    if b >= 1e9:
        return f"{b / 1e9:.1f} GB"
    return f"{b / 1e6:.0f} MB"


def _duracion(s: float) -> str:
    if s < 90:
        return f"{s:.0f} s"
    if s < 5400:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"


def _espacio(pedido: str, info: lectura.InfoMedio, avisos: list[str], quien: str) -> str:
    if pedido != "auto":
        return pedido
    if info.space_deducido:
        return str(info.space_deducido)
    avisos.append(
        f"{quien}: el fichero no dice su espacio de color; asumo rec709. Si es log, "
        f"repite con --espacio-{'master' if quien == 'master' else 'brutos'}."
    )
    return "rec709"


def _png16(img_u16: np.ndarray) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".png", np.ascontiguousarray(img_u16[..., ::-1]))
    if not ok:
        raise RuntimeError("no he podido codificar el PNG")
    return buf.tobytes()


def _png8(img01: np.ndarray) -> bytes:
    import cv2

    arr = np.clip(np.round(np.asarray(img01) * 255.0), 0, 255).astype(np.uint8)
    if arr.ndim == 3:
        arr = arr[..., ::-1]
    ok, buf = cv2.imencode(".png", np.ascontiguousarray(arr))
    if not ok:
        raise RuntimeError("no he podido codificar el PNG")
    return buf.tobytes()


def _hoja(bruto_trozo: np.ndarray, master: np.ndarray, ancho: int = 320) -> np.ndarray:
    import cv2

    h = max(int(round(ancho * master.shape[0] / master.shape[1])), 2)
    a = cv2.resize(np.ascontiguousarray(bruto_trozo, np.float32), (ancho, h),
                   interpolation=cv2.INTER_AREA)
    b = cv2.resize(np.ascontiguousarray(master, np.float32), (ancho, h),
                   interpolation=cv2.INTER_AREA)
    sep = np.ones((h, 4, 3), np.float32)
    return np.concatenate([a, sep, b], axis=1)


def _carpeta_nueva(guarda: Guarda) -> Path:
    base = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for k in range(100):
        nombre = base if k == 0 else f"{base}_{k + 1}"
        destino = RAIZ_TRABAJO / nombre
        if not destino.exists():
            return guarda.crear_carpeta(destino)
    raise EscrituraProhibida("no encuentro un nombre libre para la carpeta de trabajo")


def main(argv: list[str] | None = None, *, salida=None) -> int:
    out = salida or sys.stdout

    def say(texto: str = "") -> None:
        print(texto, file=out, flush=True)

    args = _parser().parse_args(argv)

    faltan = []
    if not args.master:
        faltan.append("--master RUTA   (el master coloreado, un fichero)")
    if not args.brutos:
        faltan.append("--brutos RUTA [RUTA ...]   (los brutos: ficheros o carpetas)")
    if faltan:
        say("No hago nada: faltan rutas. Este script no busca material por su cuenta.")
        say("")
        say("Me falta:")
        for f in faltan:
            say(f"  {f}")
        say("")
        say("Ayuda completa: .venv/bin/python pruebas/primera_real.py --help")
        return SALIDA_FALTAN_ARGUMENTOS

    # --- origen: validar, listar, proteger ---------------------------------
    try:
        ruta_master = validar_master(args.master)
        # La guarda se construye ANTES de recorrer ninguna carpeta: si la carpeta de
        # trabajo cae dentro de un origen (p. ej. alguien pasa el repo como brutos),
        # se para aqui sin haber listado nada.
        Guarda([ruta_master, *[Path(b) for b in args.brutos]])
        listado = listar_brutos(args.brutos)
        guarda = Guarda([ruta_master, *[Path(b) for b in args.brutos], *listado.ficheros])
    except (OrigenRechazado, EscrituraProhibida) as e:
        say(f"NO SIGO: {e}")
        return SALIDA_RECHAZADO
    if any(f.resolve() == ruta_master.resolve() for f in listado.ficheros):
        say("NO SIGO: el master esta tambien entre los brutos. Pasa el master aparte.")
        return SALIDA_RECHAZADO
    if not listado.ficheros:
        say("NO SIGO: en las rutas de --brutos no hay ningun video que se pueda leer.")
        for r, m in listado.ignorados:
            say(f"  - {r}: {m}")
        return SALIDA_RECHAZADO

    avisos: list[str] = []
    ignorados = list(listado.ignorados)
    try:
        info_m = lectura.sondear(ruta_master)
    except Exception as e:  # noqa: BLE001 - cualquier fallo de ffprobe se cuenta igual
        say(f"NO SIGO: no puedo leer el master {ruta_master.name}: {e}")
        return SALIDA_RECHAZADO
    if info_m.es_imagen:
        say("NO SIGO: el master es una imagen fija; tiene que ser el video entregado.")
        return SALIDA_RECHAZADO
    esp_m = _espacio(args.espacio_master, info_m, avisos, "master")

    brutos: list[tuple[str, Path, lectura.InfoMedio, str]] = []
    nombres_usados: set[str] = set()
    for f in listado.ficheros:
        try:
            info = lectura.sondear(f)
        except Exception as e:  # noqa: BLE001
            ignorados.append((str(f), f"ffmpeg no lo lee: {e}"))
            continue
        if info.es_imagen:
            ignorados.append((str(f), "es una imagen fija, no un clip"))
            continue
        nombre = f.name
        k = 2
        while nombre in nombres_usados:
            nombre = f"{f.name} ({k})"
            k += 1
        nombres_usados.add(nombre)
        brutos.append((nombre, f, info, _espacio(args.espacio_brutos, info, avisos, nombre)))
    if not brutos:
        say("NO SIGO: ningun bruto se ha podido leer.")
        for r, m in ignorados:
            say(f"  - {r}: {m}")
        return SALIDA_RECHAZADO

    # --- plan --------------------------------------------------------------
    est = _coste.estimar(
        master=(info_m.ancho, info_m.alto, info_m.n_fotogramas),
        brutos=[(i.ancho, i.alto, i.n_fotogramas, i.duracion) for _, _, i, _ in brutos],
        ancho_analisis=args.ancho_analisis,
        paso=args.paso,
        coste=_coste.leer_coste(),
    )
    say("=" * 72)
    say("PRIMERA PRUEBA CON MATERIAL REAL — " + ("EJECUCION" if args.ejecutar else "SIMULACRO"))
    say("=" * 72)
    say("")
    say("LEERIA (solo lectura, nada se copia):")
    say(f"  master: {ruta_master}")
    say(f"          {info_m.ancho}x{info_m.alto}, {info_m.fps:.3f} fps, {info_m.n_fotogramas} "
        f"fotogramas ({info_m.duracion:.1f} s), {info_m.codec}, espacio {esp_m}")
    say(f"  brutos: {len(brutos)} ficheros")
    for nombre, _f, i, esp in brutos:
        say(f"    - {nombre}: {i.ancho}x{i.alto}, {i.fps:.3f} fps, {i.duracion:.1f} s, "
            f"{i.codec}, espacio {esp}")
    if ignorados:
        say(f"  no se leerian ({len(ignorados)}):")
        for r, m in ignorados:
            say(f"    - {r}: {m}")
    say("")
    say("CARPETAS PROTEGIDAS (ahi no se escribe nunca):")
    for p in guarda.protegidas:
        say(f"  {p}")
    say("")
    say("ESCRIBIRIA solo en:")
    say(f"  {RAIZ_TRABAJO}/<fecha-hora>/")
    say(f"  - hasta {est.fotogramas_a_disco} fotogramas en PNG de 16 bits (uno del bruto y uno "
        f"del master por plano; {est.planos} planos si cada bruto sale una vez)")
    say("  - una hoja de contacto por plano, informe.md e informe.json")
    say(f"  - espacio: como mucho {_mb(est.bytes_disco)} en el disco del ordenador")
    say("")
    say("TIEMPO ESTIMADO:")
    if est.segundos is None:
        say(f"  {est.nota}")
    else:
        say(f"  unos {_duracion(est.segundos)} en total")
        for k, v in est.desglose_s.items():
            say(f"    - {k}: {_duracion(v)}")
        if est.memoria_bytes is not None:
            say(f"  memoria del escaneo: unos {_mb(est.memoria_bytes)} de RAM")
        say(f"  ({est.nota})")
    say("")
    for a in avisos:
        say(f"AVISO: {a}")
    if avisos:
        say("")
    if not args.ejecutar:
        say("SIMULACRO: no se ha escrito nada, ni la carpeta de trabajo.")
        say("Para hacerlo de verdad, repite el mismo comando anadiendo --ejecutar")
        return SALIDA_OK

    # --- ejecucion ------------------------------------------------------------
    try:
        carpeta = _carpeta_nueva(guarda)
    except EscrituraProhibida as e:
        say(f"NO SIGO: {e}")
        return SALIDA_RECHAZADO
    say(f"Carpeta de trabajo: {carpeta}")
    tiempos: dict[str, float] = {}
    try:
        return _ejecutar(args, guarda, carpeta, ruta_master, info_m, esp_m, brutos,
                         ignorados, avisos, tiempos, say)
    except EscrituraProhibida as e:
        say(f"PARADO POR LA GUARDA: {e}")
        return SALIDA_RECHAZADO
    except Exception:  # noqa: BLE001 - se guarda el error y se sale limpio
        detalle = traceback.format_exc()
        say("ERROR durante la prueba. Detalle guardado en error.txt:")
        say(detalle)
        with contextlib.suppress(Exception):
            guarda.escribir_texto(carpeta / "error.txt", detalle)
        return SALIDA_ERROR


def _ejecutar(args, guarda, carpeta, ruta_master, info_m, esp_m, brutos, ignorados, avisos,
              tiempos, say) -> int:
    from pruebas.informe import componer

    t0 = time.perf_counter()
    say("1/5 Escaneando el master...")
    em = localizar.escanear_master(ruta_master, info_m, progreso=say)
    tiempos["escanear master"] = time.perf_counter() - t0
    y0, y1, x0, x1 = em.area_activa
    alto_escaneo, ancho_escaneo = em.lumas.shape[1:]
    if (y0, y1, x0, x1) != (0, alto_escaneo, 0, ancho_escaneo):
        avisos.append(
            f"el master tiene bandas negras; se mide solo la imagen activa "
            f"(filas {y0}-{y1} y columnas {x0}-{x1} de {alto_escaneo}x{ancho_escaneo} de escaneo)"
        )
    aspecto = (y1 - y0) / max(x1 - x0, 1)

    t0 = time.perf_counter()
    say("2/5 Escaneando los brutos...")
    escaneos = []
    for nombre, f, info, _ in brutos:
        say(f"  {nombre}")
        try:
            escaneos.append(localizar.escanear_bruto(nombre, f, info, aspecto_master=aspecto))
        except Exception as e:  # noqa: BLE001
            ignorados.append((str(f), f"no se ha podido escanear: {e}"))
    tiempos["escanear brutos"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    say("3/5 Localizando cada bruto dentro del master...")
    loc = localizar.localizar(em, escaneos, paso=args.paso, escala_minima=args.escala_minima,
                              progreso=say)
    tiempos["localizar"] = time.perf_counter() - t0
    say(f"  {sum(a.aceptada for a in loc.apariciones)} planos con confianza alta, "
        f"{sum(not a.aceptada for a in loc.apariciones)} descartados")

    t0 = time.perf_counter()
    say("4/5 Extrayendo fotogramas y midiendo T1...")
    por_nombre = {n: (f, i, e) for n, f, i, e in brutos}
    area_rel = (y0 / alto_escaneo, y1 / alto_escaneo, x0 / ancho_escaneo, x1 / ancho_escaneo)
    guarda.crear_carpeta(carpeta / "fotogramas")
    guarda.crear_carpeta(carpeta / "hojas")
    parejas: dict[int, medir.Pareja] = {}
    resultados = {}
    medidas_t1: dict[int, medir.MedidaT1] = {}
    errores: dict[int, str] = {}
    ficheros: dict[int, dict[str, str]] = {}
    for i, a in enumerate(loc.apariciones, start=1):
        if not a.aceptada:
            # hoja de contacto a resolucion de escaneo, para ver por que se descarto
            e = next(x for x in escaneos if x.nombre == a.bruto)
            ml = em.luma_activa(a.master_medida)
            ib = min(int(round(a.bruto_medida / max(e.info.fps, 1e-6) * e.muestreo)), e.n - 1)
            bl = e.luma(ib)
            g = a.geometria
            bh, bw = bl.shape
            cw = max(int(round(g.escala * bw)), 2)
            ch = max(int(round(cw * ml.shape[0] / ml.shape[1])), 2)
            cx, cy = int(round(g.x * bw)), int(round(g.y * bh))
            trozo = bl[cy : cy + ch, cx : cx + cw]
            if trozo.size:
                hoja = _hoja(np.repeat(trozo[..., None], 3, 2), np.repeat(ml[..., None], 3, 2))
                nombre_hoja = f"hojas/{i:03d}_DESCARTADA_{_seguro(a.bruto)}.png"
                guarda.escribir_bytes(carpeta / nombre_hoja, _png8(hoja))
                ficheros[i] = {"hoja": nombre_hoja}
            continue
        f, info, esp_b = por_nombre[a.bruto]
        try:
            say(f"  #{i} {a.bruto}: master {a.master_medida} <- bruto {a.bruto_medida}")
            m_u16 = lectura.fotograma_completo(ruta_master, info_m, a.master_medida)
            b_u16 = lectura.fotograma_completo(f, info, a.bruto_medida)
            n_m = f"fotogramas/{i:03d}_master_f{a.master_medida:07d}.png"
            n_b = f"fotogramas/{i:03d}_bruto_{_seguro(a.bruto)}_f{a.bruto_medida:07d}.png"
            guarda.escribir_bytes(carpeta / n_m, _png16(m_u16))
            guarda.escribir_bytes(carpeta / n_b, _png16(b_u16))
            p = medir.preparar_pareja(
                f"#{i} {a.bruto}", b_u16, m_u16, area_rel, a.geometria,
                espacio_bruto=esp_b, espacio_master=esp_m, ancho_analisis=args.ancho_analisis,
            )
            cx, cy, cw, ch = p.recorte_px
            trozo = b_u16[cy : cy + ch, cx : cx + cw].astype(np.float32) / 65535.0
            mh, mw = m_u16.shape[:2]
            activa = m_u16[int(round(area_rel[0] * mh)) : int(round(area_rel[1] * mh)),
                           int(round(area_rel[2] * mw)) : int(round(area_rel[3] * mw))]
            n_h = f"hojas/{i:03d}_{_seguro(a.bruto)}.png"
            guarda.escribir_bytes(
                carpeta / n_h, _png8(_hoja(trozo, activa.astype(np.float32) / 65535.0))
            )
            ficheros[i] = {"master": n_m, "bruto": n_b, "hoja": n_h}
            r, m1 = medir.medir_t1(p)
            parejas[i], resultados[i], medidas_t1[i] = p, r, m1
            say(f"     T1 max {m1.de_max_cubierto:.2f} · medio {m1.de_medio_cubierto:.2f} · "
                f"cobertura {m1.fraccion_cubierta * 100:.2f}%")
        except EscrituraProhibida:
            raise
        except Exception as e:  # noqa: BLE001
            errores[i] = f"{type(e).__name__}: {e}"
            say(f"     no se pudo medir: {errores[i]}")
    tiempos["extraer y T1"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    say("5/5 T5: el grado de cada plano aplicado a los demas...")
    medidas_t5: list[medir.MedidaT5] = []
    for i, r in resultados.items():
        for j, p in parejas.items():
            if i == j:
                continue
            m5 = medir.medir_t5(f"#{i} {loc.apariciones[i - 1].bruto}", r, p)
            medidas_t5.append(m5)
    tiempos["T5"] = time.perf_counter() - t0

    texto, datos = componer(
        fecha=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        argumentos={k: v for k, v in vars(args).items()},
        master={"ruta": str(ruta_master), "ancho": info_m.ancho, "alto": info_m.alto,
                "fps": info_m.fps, "fotogramas": info_m.n_fotogramas, "codec": info_m.codec,
                "espacio": esp_m},
        brutos=[{"nombre": n, "ruta": str(f), "ancho": i.ancho, "alto": i.alto, "fps": i.fps,
                 "fotogramas": i.n_fotogramas, "codec": i.codec, "espacio": e}
                for n, f, i, e in brutos],
        ignorados=ignorados,
        localizacion=loc,
        fps_master=info_m.fps or 25.0,
        medidas_t1=medidas_t1,
        medidas_t5=medidas_t5,
        errores_medida=errores,
        ficheros=ficheros,
        avisos=avisos,
        tiempos=tiempos,
    )
    guarda.escribir_texto(carpeta / "informe.md", texto)
    guarda.escribir_texto(
        carpeta / "informe.json",
        json.dumps(_sin_nan(datos), ensure_ascii=False, indent=2, default=_json_default,
                   allow_nan=False),
    )
    say("")
    say(f"Hecho. Informe: {carpeta / 'informe.md'}")
    return SALIDA_OK


def _seguro(nombre: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in nombre)[:60]


def _sin_nan(o):
    """NaN e infinitos a None: el JSON estandar no los admite."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): _sin_nan(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_sin_nan(v) for v in o]
    if isinstance(o, np.generic):
        return _sin_nan(o.item())
    return o


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, Path):
        return str(o)
    return str(o)


if __name__ == "__main__":
    sys.exit(main())
