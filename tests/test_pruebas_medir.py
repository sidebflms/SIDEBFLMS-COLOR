"""Lo que aporta cada pieza de la medicion, medido y no supuesto.

Son las cifras de `pruebas/NOTAS.md` §2 y §3. Cada test IMPRIME su tabla (`-s`) y
comprueba solo lo que la decision necesita: que la pieza no empeora las cosas.

    .venv/bin/python -m pytest tests/test_pruebas_medir.py -s

§2 · el prefiltro de la estructura: ¿el fotograma correcto gana a sus vecinos?
§3 · medir a la mitad y el registro subpixel: ¿se acerca el T1 al del grado verdadero?
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import delta_e2000, from_working, to_working
from core.paths import have_ffmpeg
from pruebas import lectura, localizar, medir
from pruebas.sintetico import grado_sintetico, montaje_compartido

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(not have_ffmpeg(), reason="hace falta ffmpeg para fabricar y leer clips"),
]


@pytest.fixture(scope="module")
def montaje(tmp_path_factory):
    return montaje_compartido(tmp_path_factory.getbasetemp())


@pytest.fixture(scope="module")
def master_escaneado(montaje):
    return localizar.escanear_master(montaje.master, lectura.sondear(montaje.master))


def _tramos_largos(montaje):
    return [t for t in montaje.tramos if t.n >= localizar.FOTOGRAMAS_FIABLES]


def test_prefiltro_el_fotograma_correcto_gana_a_sus_vecinos(montaje, master_escaneado, monkeypatch):
    filas = []
    for sigma in (0.0, localizar.SIGMA_PREFILTRO):
        monkeypatch.setattr(localizar, "SIGMA_PREFILTRO", sigma)
        for t in _tramos_largos(montaje):
            j = t.n // 2 + 3  # lejos del fundido
            k_master = t.master_desde + j
            k_bruto = t.bruto_desde + j
            ruta = montaje.brutos[t.bruto]
            info = lectura.sondear(ruta)
            primero = max(k_bruto - 3, 0)
            fot = lectura.ventana(ruta, info, primero, 7, localizar.ANCHO_ESCANEO_BRUTO)
            ml = master_escaneado.luma_activa(k_master)
            nccs = {
                primero + i: localizar.buscar_geometria(
                    localizar.luma(fot[i]), ml, escala_min=0.5).ncc
                for i in range(fot.shape[0])
            }
            correcto = nccs[k_bruto]
            vecino = max(v for k, v in nccs.items() if k != k_bruto)
            filas.append((sigma, t.bruto, k_master, correcto, vecino))
    print("\n§2 prefiltro | bruto | fotograma master | encaje correcto | mejor vecino (+-3) | margen")
    for sigma, bruto, k, c, v in filas:
        print(f"   {sigma:.1f} | {bruto:15s} | {k:3d} | {c:.3f} | {v:.3f} | {c - v:+.3f}")
    con = [f for f in filas if f[0] > 0]
    assert con, (
        "no hay nada que comprobar: no hay ni una fila con prefiltro (¿`_tramos_largos` vacio o "
        "SIGMA_PREFILTRO a 0?), y el `all` de abajo pasaria solo"
    )
    assert all(c > v for _, _, _, c, v in con), "con prefiltro, un vecino gana al correcto"
    margen_sin = np.mean([c - v for s, _, _, c, v in filas if s == 0])
    margen_con = np.mean([c - v for _, _, _, c, v in con])
    print(f"   margen medio: sin prefiltro {margen_sin:+.4f} · con prefiltro {margen_con:+.4f}")


def test_sin_prefiltro_se_acepta_un_fotograma_equivocado(montaje, monkeypatch):
    """CENTINELA de por que existe `SIGMA_PREFILTRO`.

    Frente a los fotogramas vecinos el prefiltro NO separa mejor (test de arriba:
    el margen medio baja). Pero en la localizacion entera, sin el, una aparicion de
    la toma E sale aceptada con confianza alta en un fotograma que no es. Si algun
    dia este test deja de cumplirse, el motivo del prefiltro ha cambiado y hay que
    volver a medirlo.
    """
    def equivocadas(sigma: float) -> list[str]:
        monkeypatch.setattr(localizar, "SIGMA_PREFILTRO", sigma)
        em = localizar.escanear_master(montaje.master, lectura.sondear(montaje.master))
        y0, y1, x0, x1 = em.area_activa
        brutos = [
            localizar.escanear_bruto(n, r, lectura.sondear(r), aspecto_master=(y1 - y0) / (x1 - x0))
            for n, r in montaje.brutos.items()
        ]
        loc = localizar.localizar(em, brutos)
        mal = []
        for a in loc.apariciones:
            if not a.aceptada:
                continue
            for t in montaje.tramos:
                solape = min(a.master_hasta, t.master_desde + t.n) - max(a.master_desde,
                                                                          t.master_desde)
                if t.bruto == a.bruto and solape > 0:
                    desfase = (t.bruto_desde - t.master_desde) / 25.0
                    if abs(a.desfase_s - desfase) > 1.5 / 25.0:
                        mal.append(f"{a.bruto} [{a.master_desde},{a.master_hasta}) desfase "
                                   f"{a.desfase_s * 25:+.0f} fot, verdad {desfase * 25:+.0f}")
        return mal

    con = equivocadas(localizar.SIGMA_PREFILTRO)
    sin = equivocadas(0.0)
    print(f"\n§2 aceptadas en un fotograma equivocado: con prefiltro {con} · sin prefiltro {sin}")
    assert con == []
    assert sin, "sin prefiltro ya no se equivoca: el motivo del prefiltro ha cambiado, re-medir"


def _suelo(p: medir.Pareja) -> tuple[float, float, float]:
    """ΔE del GRADO VERDADERO aplicado al bruto ya encajado: lo mejor que se puede medir."""
    codigo = np.asarray(from_working(p.bruto, "rec709"), dtype=np.float32)
    verdadero = to_working(np.clip(grado_sintetico(codigo), 0, 1).astype(np.float32), "rec709")
    de = np.asarray(delta_e2000(verdadero.astype(np.float64), p.master.astype(np.float64)))
    lejos = ~medir.mascara_bordes(p.master)
    return float(de.mean()), float(de.max()), float(de[lejos].max())


def test_medir_a_la_mitad_y_con_registro_subpixel_se_acerca_al_grado_verdadero(montaje):
    from pruebas.localizar import Geometria

    configs = [("completo, sin subpixel", 1, False), ("completo, subpixel", 1, True),
               ("mitad, sin subpixel", 2, False), ("mitad, subpixel (el script)", 2, True)]
    filas = []
    for t in _tramos_largos(montaje):
        if t.bruto == "B_casi_fijo":
            continue  # sin reencuadre: no aporta a esta pregunta y tarda
        j = t.n // 2 + 3
        info_m = lectura.sondear(montaje.master)
        info_b = lectura.sondear(montaje.brutos[t.bruto])
        mu = lectura.fotograma_completo(montaje.master, info_m, t.master_desde + j)
        bu = lectura.fotograma_completo(montaje.brutos[t.bruto], info_b, t.bruto_desde + j)
        g = Geometria(t.escala, t.x, t.y, 1.0)
        for nombre, red, sub in configs:
            p = medir.preparar_pareja(t.bruto, bu, mu, (0, 1, 0, 1), g, espacio_bruto="rec709",
                                      espacio_master="rec709", ancho_analisis=960,
                                      reduccion_minima=red, subpixel=sub)
            _, m1 = medir.medir_t1(p)
            s_medio, s_max, s_max_lejos = _suelo(p)
            filas.append((t.bruto, nombre, p.bruto.shape[1], m1.de_medio_cubierto,
                          m1.de_max_cubierto, m1.de_max_cubierto_sin_bordes, s_medio, s_max,
                          s_max_lejos))
    print("\n§3 bruto | configuracion | ancho | T1 medio | T1 max | T1 max lejos de bordes"
          " | grado verdadero: medio | max | max lejos de bordes")
    for f in filas:
        print(f"   {f[0]:15s} | {f[1]:27s} | {f[2]:4d} | {f[3]:.3f} | {f[4]:.2f} | {f[5]:.2f}"
              f" | {f[6]:.3f} | {f[7]:.2f} | {f[8]:.2f}")
    por = {n: [f for f in filas if f[1] == n] for n, _, _ in configs}
    medio = {n: float(np.mean([f[3] for f in fs])) for n, fs in por.items()}
    print("   T1 medio, media de los planos: " + " · ".join(f"{n} {v:.3f}" for n, v in medio.items()))
    assert medio["mitad, subpixel (el script)"] <= medio["completo, sin subpixel"]
    for f in por["mitad, subpixel (el script)"]:
        assert f[3] <= f[6] + 0.25, f"{f[0]}: T1 medio {f[3]:.3f} lejos del suelo {f[6]:.3f}"
