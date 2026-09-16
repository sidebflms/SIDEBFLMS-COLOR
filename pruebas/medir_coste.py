"""Medir cuanto cuesta cada paso de la primera prueba, sobre material SINTETICO.

    .venv/bin/python pruebas/medir_coste.py

Escribe `pruebas/coste_medido.json`, que es de donde salen las estimaciones de
tiempo y espacio del simulacro (`pruebas/coste.py`) y las cifras del instructivo.
No toca material real: fabrica sus clips en una carpeta temporal del sistema que
se borra sola al terminar.

QUE SE MIDE Y COMO SE EXTRAPOLA
-------------------------------
Cada coste se mide a dos tamanos cuando depende del tamano, y se ajusta una recta
`t = fijo + por_MPx * megapixeles`. Eso es lo que permite pasar de un clip de
640x360 a un 4K con una cuenta escrita en vez de con una suposicion. La recta es
de ProRes 4444 sintetico: un H.265 de camara decodifica a otra velocidad, y eso
el simulacro lo dice.

ESTE ARCHIVO ESCRIBE: los clips en la carpeta temporal y el JSON en `pruebas/`.
No lo importa `primera_real.py`.
"""

from __future__ import annotations

import datetime as _dt
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from core.color import to_working  # noqa: E402
from core.reverse import invertir_grado  # noqa: E402
from pruebas import lectura, localizar, medir  # noqa: E402
from pruebas.sintetico import _clip, escena, fabricar_montaje, grado_sintetico  # noqa: E402

SALIDA = Path(__file__).resolve().parent / "coste_medido.json"


def _recta(x1: float, t1: float, x2: float, t2: float) -> tuple[float, float]:
    pendiente = (t2 - t1) / (x2 - x1)
    return max(t1 - pendiente * x1, 0.0), max(pendiente, 0.0)


def _cronometrar(f, repeticiones: int = 1) -> float:
    t0 = time.perf_counter()
    for _ in range(repeticiones):
        f()
    return (time.perf_counter() - t0) / repeticiones


def main() -> int:
    r: dict = {
        "fecha": _dt.date.today().isoformat(),
        "comando": ".venv/bin/python pruebas/medir_coste.py",
        "maquina": {"sistema": platform.platform(), "procesador": platform.processor(),
                    "python": platform.python_version()},
        "material": "sintetico: ProRes 4444 10 bits de pruebas/sintetico.py",
    }
    with tempfile.TemporaryDirectory(prefix="sidebcolor_coste_") as tmp:
        tmp = Path(tmp)
        n = 40
        tamanos = [(640, 360), (1920, 1080)]
        clips = {}
        for w, h in tamanos:
            base = escena(7, w, h)
            fot = [np.roll(base, k * 3, axis=1) for k in range(n)]
            clips[(w, h)] = _clip(tmp / f"c_{w}.mov", fot)
            print(f"clip {w}x{h} listo", flush=True)

        # 1. decodificar a resolucion de escaneo (todo el clip, sin procesar)
        tiempos = {}
        for (w, h), ruta in clips.items():
            info = lectura.sondear(ruta)
            t = _cronometrar(lambda ruta=ruta, info=info: sum(
                1 for _ in lectura.recorrer(ruta, info, localizar.ANCHO_ESCANEO_BRUTO)), 2)
            tiempos[(w, h)] = t / n
        mpx = [w * h / 1e6 for w, h in tamanos]
        fijo, por_mpx = _recta(mpx[0], tiempos[tamanos[0]], mpx[1], tiempos[tamanos[1]])
        r["decodificar_s_por_fotograma_mpx"] = por_mpx
        r["decodificar_s_por_fotograma_fijo"] = fijo
        r["decodificar_medido_s_por_fotograma"] = {f"{w}x{h}": tiempos[(w, h)] for w, h in tamanos}

        # 2. extraer un fotograma completo (proceso de ffmpeg + busqueda + decodificado)
        ext = {}
        for (w, h), ruta in clips.items():
            info = lectura.sondear(ruta)
            ext[(w, h)] = _cronometrar(
                lambda ruta=ruta, info=info: [lectura.fotograma_completo(ruta, info, k)
                                              for k in (5, 20, 35)], 1) / 3
        fijo, por_mpx = _recta(mpx[0], ext[tamanos[0]], mpx[1], ext[tamanos[1]])
        r["extraer_s_por_fotograma_fijo"] = fijo
        r["extraer_s_por_fotograma_mpx"] = por_mpx
        r["extraer_medido_s_por_fotograma"] = {f"{w}x{h}": ext[(w, h)] for w, h in tamanos}

        # 3. PNG de 16 bits: bytes por pixel, liso y con grano fuerte
        info = lectura.sondear(clips[(1920, 1080)])
        u16 = lectura.fotograma_completo(clips[(1920, 1080)], info, 10)
        liso = len(cv2.imencode(".png", u16[..., ::-1])[1].tobytes()) / (1920 * 1080)
        rng = np.random.default_rng(1)
        grano = np.clip(u16.astype(np.float64) + rng.normal(0, 800, u16.shape), 0, 65535)
        grano = grano.astype(np.uint16)
        con_grano = len(cv2.imencode(".png", grano[..., ::-1])[1].tobytes()) / (1920 * 1080)
        r["png16_bytes_por_pixel_sintetico_liso"] = liso
        r["png16_bytes_por_pixel_con_grano_fuerte"] = con_grano
        r["png16_bytes_por_pixel_maximo_aritmetico"] = 6.0

        # 4. el montaje: escaneos, localizacion y hojas
        print("fabricando montaje...", flush=True)
        m = fabricar_montaje(tmp / "montaje")
        info_m = lectura.sondear(m.master)
        fot_m = list(lectura.recorrer(m.master, info_m, localizar.ANCHO_ESCANEO_MASTER))
        t = _cronometrar(lambda: localizar.escanear_master(m.master, info_m, fotogramas=fot_m), 3)
        r["escaneo_master_s_por_fotograma"] = t / len(fot_m)
        em = localizar.escanear_master(m.master, info_m, fotogramas=fot_m)
        aspecto = em.lumas.shape[1] / em.lumas.shape[2]

        escaneos = []
        t_bruto = 0.0
        segundos = 0.0
        for nombre, ruta in m.brutos.items():
            info = lectura.sondear(ruta)
            fot = list(lectura.recorrer(ruta, info, localizar.ANCHO_ESCANEO_BRUTO,
                                        fps=localizar.MUESTREO_BRUTOS))
            t0 = time.perf_counter()
            escaneos.append(localizar.escanear_bruto(nombre, ruta, info, aspecto_master=aspecto,
                                                     fotogramas=fot))
            t_bruto += time.perf_counter() - t0
            segundos += info.duracion
        r["escaneo_bruto_s_por_segundo"] = t_bruto / segundos

        leidos = {"fotogramas": 0, "lecturas": 0, "segundos": 0.0}

        def leer(b, primero, cuantos):
            t0 = time.perf_counter()
            out = lectura.ventana(b.ruta, b.info, primero, cuantos, localizar.ANCHO_ESCANEO_BRUTO)
            leidos["segundos"] += time.perf_counter() - t0
            leidos["fotogramas"] += int(out.shape[0])
            leidos["lecturas"] += 1
            return out

        t0 = time.perf_counter()
        loc = localizar.localizar(em, escaneos, leer_ventana=leer)
        t_loc = time.perf_counter() - t0 - leidos["segundos"]
        planos = len(loc.apariciones)
        puntos = loc.parametros["puntos_de_busqueda"]
        # Todo el tiempo de localizar (sin contar lo que tarda ffmpeg en leer) se
        # atribuye por punto de busqueda. En el montaje hay 6 planos en 14 puntos; un
        # master con planos de mas de ~28 fotogramas de media (con paso 12) tiene menos
        # planos por punto, y entonces el coste de afinar y verificar cada plano queda
        # repartido de mas: la estimacion peca por arriba. Con planos mas cortos que
        # eso, peca por abajo.
        r["localizar_s_por_punto"] = t_loc / max(puntos, 1)
        r["afinar_s_por_plano_sin_leer"] = 0.0
        r["fotogramas_leidos_por_plano"] = leidos["fotogramas"] / max(planos, 1)
        r["lecturas_por_plano"] = leidos["lecturas"] / max(planos, 1)
        r["montaje_medido"] = {"puntos": puntos, "planos": planos,
                               "localizar_total_s_sin_leer": t_loc,
                               "lecturas_s": leidos["segundos"],
                               "lecturas": leidos["lecturas"],
                               "fotogramas_leidos": leidos["fotogramas"]}

        # 5. T1 (invertir) y T5 por megapixel de analisis
        base = escena(11, 960, 540)
        gr = np.clip(grado_sintetico(base), 0, 1).astype(np.float32)
        inv = {}
        for w in (480, 960):
            h = w * 9 // 16
            a = to_working(cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA), "rec709")
            b = to_working(cv2.resize(gr, (w, h), interpolation=cv2.INTER_AREA), "rec709")
            inv[w] = (_cronometrar(lambda a=a, b=b: invertir_grado(a, b), 1), w * h / 1e6, a, b)
        r["invertir_s_por_mpx"] = inv[960][0] / inv[960][1]
        r["invertir_medido_s"] = {"480x270": inv[480][0], "960x540": inv[960][0]}
        a, b = inv[960][2], inv[960][3]
        res = invertir_grado(a, b)
        par = medir.Pareja("x", a, b, (0, 0, 960, 540), 1.0)
        t5 = _cronometrar(lambda: medir.medir_t5("x", res, par), 3)
        r["t5_s_por_pareja_mpx"] = t5 / inv[960][1]

        # 6. hoja de contacto y memoria
        hoja = np.concatenate([base[:180, :320], np.ones((180, 4, 3), np.float32),
                               gr[:180, :320]], axis=1)
        r["hoja_bytes_por_plano"] = float(len(cv2.imencode(
            ".png", (hoja[..., ::-1] * 255).astype(np.uint8))[1].tobytes()))
        alto_m = localizar.ANCHO_ESCANEO_MASTER * 9 // 16
        r["memoria_bytes_por_fotograma_master"] = float(
            localizar.ANCHO_ESCANEO_MASTER * alto_m + 96 * 4 + 16)
        alto_b = localizar.ANCHO_ESCANEO_BRUTO * 9 // 16
        filas_banco = localizar.MUESTREO_BANCO
        recortes = len(localizar.recortes_del_banco(9 / 16, 9 / 16))
        r["memoria_bytes_por_segundo_bruto"] = float(
            localizar.MUESTREO_BRUTOS * localizar.ANCHO_ESCANEO_BRUTO * alto_b
            + filas_banco * recortes * 96 * 4)

    SALIDA.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print(f"\nEscrito {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
