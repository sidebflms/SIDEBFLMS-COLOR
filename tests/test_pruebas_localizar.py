"""Localizar brutos dentro de un master montado: sobre un montaje sintetico con verdad conocida.

El montaje (`pruebas/sintetico.py`) tiene lo que va a tener un master real:

- un plano **reencuadrado** al 75% (A) y otro al 60% (D);
- un bruto que aparece **dos veces** (D), una reencuadrada y otra entera;
- un bruto que **no aparece** (C, el descarte);
- un plano **muy corto**, de 5 fotogramas (B por segunda vez);
- un **fundido** encadenado de 6 fotogramas (D -> E);
- una **toma gemela** (E: el mismo decorado que A con cosas cambiadas);
- panoramicas y un objeto que se mueve por su cuenta en cada bruto;
- y **otro color**: el master lleva un CDL + LUT conocidos.

Lo que mas importa no es que encuentre mucho, sino que **no asigne nunca un
fotograma del master al bruto equivocado con confianza alta**. Eso tiene su
propio test, y dos mas con la trampa de la toma gemela: quitando la toma buena
de la lista de brutos, lo que era de ella no puede salir aceptado con la otra.
"""

from __future__ import annotations

import pytest

from core.paths import have_ffmpeg
from pruebas import lectura, localizar
from pruebas.sintetico import FUNDIDO, montaje_compartido

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(not have_ffmpeg(), reason="hace falta ffmpeg para fabricar y leer clips"),
]

FPS = 25


@pytest.fixture(scope="module")
def montaje(tmp_path_factory):
    return montaje_compartido(tmp_path_factory.getbasetemp())


@pytest.fixture(scope="module")
def escaneos(montaje):
    info_m = lectura.sondear(montaje.master)
    em = localizar.escanear_master(montaje.master, info_m)
    y0, y1, x0, x1 = em.area_activa
    aspecto = (y1 - y0) / (x1 - x0)
    brutos = {
        nombre: localizar.escanear_bruto(nombre, ruta, lectura.sondear(ruta), aspecto_master=aspecto)
        for nombre, ruta in montaje.brutos.items()
    }
    return em, brutos


@pytest.fixture(scope="module")
def loc(escaneos):
    em, brutos = escaneos
    return localizar.localizar(em, list(brutos.values()))


def _brutos_verdad(montaje, k: int) -> set[str]:
    """Brutos que de verdad estan en el fotograma k del master (dos en un fundido)."""
    return {t.bruto for t in montaje.tramos if t.master_desde <= k < t.master_desde + t.n}


def _imprime(loc) -> None:
    for i, a in enumerate(loc.apariciones, 1):
        g = a.geometria
        verif = [round(v, 3) for _, v in a.verificaciones]
        print(f"  #{i} {a.bruto:15s} [{a.master_desde:3d},{a.master_hasta:3d}) "
              f"desfase {a.desfase_s * FPS:+.1f} fot · escala {g.escala:.3f} x {g.x:.3f} y {g.y:.3f}"
              f" · encaje {g.ncc:.3f} verif {verif} · otro {a.alternativa} {a.ncc_alternativa:.3f}"
              f" cociente {a.margen:.2f} · {a.nivel} {a.confianza:.2f}")


def test_localiza_cada_plano_donde_esta(montaje, loc):
    _imprime(loc)
    fiables = [t for t in montaje.tramos if t.n >= localizar.FOTOGRAMAS_FIABLES]
    assert len(fiables) == 5
    for t in fiables:
        candidatas = [
            a for a in loc.apariciones
            if a.aceptada and a.bruto == t.bruto
            and min(a.master_hasta, t.master_desde + t.n) - max(a.master_desde, t.master_desde)
            > t.n // 2
        ]
        assert len(candidatas) == 1, f"{t}: {len(candidatas)} apariciones aceptadas"
        a = candidatas[0]
        desfase_verdad = t.bruto_desde - t.master_desde  # en fotogramas, mismo fps
        assert abs(a.desfase_s * FPS - desfase_verdad) <= 1.0, (t, a.desfase_s * FPS)
        assert a.geometria.escala == pytest.approx(t.escala, rel=0.03), t
        assert a.geometria.x == pytest.approx(t.x, abs=0.02), t
        assert a.geometria.y == pytest.approx(t.y, abs=0.02), t
        tolerancia = FUNDIDO  # los bordes con fundido se parten por la mitad
        assert abs(a.master_desde - t.master_desde) <= tolerancia, (t, a.master_desde)
        assert abs(a.master_hasta - (t.master_desde + t.n)) <= tolerancia, (t, a.master_hasta)
        assert a.bruto_medida - a.master_medida == desfase_verdad or abs(
            (a.bruto_medida - a.master_medida) - desfase_verdad
        ) <= 1


def test_ninguna_aparicion_aceptada_asigna_un_fotograma_al_bruto_equivocado(montaje, loc):
    assert any(a.aceptada for a in loc.apariciones), (
        "no hay nada que comprobar: ninguna aparicion aceptada, y el bucle de abajo se las salta todas"
    )
    for a in loc.apariciones:
        if not a.aceptada:
            continue
        for k in range(a.master_desde, a.master_hasta):
            assert a.bruto in _brutos_verdad(montaje, k), (a.bruto, k, _brutos_verdad(montaje, k))


def test_el_bruto_que_no_aparece_sale_como_no_encontrado(montaje, loc):
    assert loc.no_encontrados == list(montaje.no_aparecen)
    assert not any(a.aceptada and a.bruto == "C_descarte" for a in loc.apariciones)


def test_el_plano_muy_corto_no_se_acepta_y_se_dice_por_que(montaje, loc):
    corto = next(t for t in montaje.tramos if t.n < localizar.FOTOGRAMAS_FIABLES)
    en_el_corto = [
        a for a in loc.apariciones
        if a.master_desde < corto.master_desde + corto.n and a.master_hasta > corto.master_desde
    ]
    assert en_el_corto, "el plano corto ni siquiera se ha intentado localizar"
    for a in en_el_corto:
        assert not a.aceptada
        assert any("corto" in r for r in a.razones), a.razones
    assert any(d <= corto.master_desde < h for d, h, _ in loc.tramos_sin_bruto)


@pytest.mark.parametrize("quitar", ["E_gemela_de_A", "A_pan_derecha"])
def test_toma_gemela_sin_la_toma_buena_no_se_acepta_la_otra(montaje, escaneos, quitar):
    """Si en la carpeta solo esta la otra toma, lo de la buena NO puede salir aceptado."""
    em, brutos = escaneos
    resto = [b for n, b in brutos.items() if n != quitar]
    loc2 = localizar.localizar(em, resto)
    print(f"\n  sin {quitar}:")
    _imprime(loc2)
    tramos_quitados = [t for t in montaje.tramos if t.bruto == quitar]
    assert tramos_quitados, (
        f"no hay nada que comprobar: ningun tramo del montaje es de {quitar!r} (¿renombrado en el "
        "parametrize o en el montaje?), y el bucle de abajo no miraria nada"
    )
    for t in tramos_quitados:
        for a in loc2.apariciones:
            if not a.aceptada:
                continue
            # los fotogramas de un fundido llevan tambien el plano anterior: se excluyen
            solo_quitado = [
                k for k in range(t.master_desde, t.master_desde + t.n)
                if _brutos_verdad(montaje, k) == {quitar}
            ]
            assert solo_quitado, (
                f"no hay nada que comprobar: el tramo de {quitar!r} en [{t.master_desde}, "
                f"{t.master_desde + t.n}) no tiene ni un fotograma solo suyo (todo fundido)"
            )
            pisados = [k for k in solo_quitado if a.master_desde <= k < a.master_hasta]
            assert not pisados, f"{a.bruto} aceptado sobre fotogramas de {quitar}: {pisados[:5]}"
    assert quitar not in loc2.no_encontrados  # no esta en la lista: ni se busca


def test_la_geometria_ignora_el_color(montaje):
    """Mismo recorte, con y sin grado: la busqueda da la misma geometria."""
    import cv2
    import numpy as np

    from pruebas.sintetico import grado_sintetico

    info = lectura.sondear(montaje.brutos["D_pan_abajo"])
    f = lectura.ventana(montaje.brutos["D_pan_abajo"], info, 10, 1, None)[0]
    h, w = f.shape[:2]
    recorte = f[int(0.35 * h) : int(0.35 * h) + int(0.6 * w * 9 / 16),
                int(0.3 * w) : int(0.3 * w) + int(0.6 * w)]
    maestro = cv2.resize(recorte, (128, 72), interpolation=cv2.INTER_AREA)
    bruto = localizar.luma(cv2.resize(f, (256, 144), interpolation=cv2.INTER_AREA))
    sin = localizar.buscar_geometria(bruto, localizar.luma(maestro), escala_min=0.5)
    con = localizar.buscar_geometria(
        bruto, localizar.luma(np.clip(grado_sintetico(maestro), 0, 1)), escala_min=0.5
    )
    print(f"\n  sin grado {sin}\n  con grado {con}")
    assert con.escala == pytest.approx(sin.escala, rel=0.02)
    assert con.x == pytest.approx(sin.x, abs=0.01)
    assert con.y == pytest.approx(sin.y, abs=0.01)
    assert con.ncc > 0.9
