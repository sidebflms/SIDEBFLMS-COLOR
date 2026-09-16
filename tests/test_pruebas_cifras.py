"""El lector de `CIFRAS.md` y la estimacion de coste: nada copiado a mano, nada inventado.

`CIFRAS.md` cambia (hoy mismo entran filas de T5), asi que estos tests **no fijan
valores de ese archivo**: comprueban que lo que se lee esta escrito alli, y que
con una tabla a la que le falta una fila el informe dice «no disponible en
CIFRAS.md» en vez de fallar o de inventar.
"""

from __future__ import annotations

import math

import pytest

from pruebas import cifras_ref, coste
from pruebas.cifras_ref import NO_DISPONIBLE, buscar, leer_tablas, referencias_para_informe

TABLAS = """
# CIFRAS de juguete

### Los titulares
| Criterio | Cifra que decide | Límite | **Margen** | Montaje | Comando | Fecha |
|---|---|---|---|---|---|---|
| **T1** ingeniería inversa | **ΔE2000 máximo 2.5** | < 3.0 | **0.5** | uno | `cmd` | 01-01 |
| **T3** igualado | **ΔE2000 peor par 1.9** | < 2.0 | 0.1 | dos | `cmd` | 01-01 |

### Detrás
| Montaje | Valor | Cifra | Fecha |
|---|---|---|---|
| repo | 0.12 | T1 ΔE2000 medio, zona cubierta | 01-01 |
| repo | 17.6 → 0.66 | T3 antes → después | 01-01 |

| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| **Cobertura del cubo, un solo plano** | **165 de 35.937 = 0.46%** | repo, LUT 33³ | `c` | 01-01 |
"""


def test_lee_por_nombre_de_columna_aunque_cambie_el_orden():
    filas = leer_tablas(TABLAS)
    t1 = buscar(filas, ("t1",), ("maximo",))
    assert [r.numero for r in t1] == [2.5]
    assert t1[0].limite == "< 3.0"
    medio = buscar(filas, ("t1",), ("medio",))
    assert [r.numero for r in medio] == [0.12]  # columnas en otro orden en esa tabla
    cob = buscar(filas, ("cobertura",))
    assert cob[0].numero == pytest.approx(0.46)
    assert buscar(filas, ("t3",), ("antes",))[0].numero is None  # flecha: no elige


def test_una_fila_que_falta_sale_como_no_disponible(tmp_path, monkeypatch):
    sin_t1 = "\n".join(linea for linea in TABLAS.splitlines() if "T1" not in linea)
    ruta = tmp_path / "CIFRAS.md"
    ruta.write_text(sin_t1, encoding="utf-8")
    refs = referencias_para_informe(ruta)
    assert refs["t1_max"] == NO_DISPONIBLE
    assert refs["t1_medio"] == NO_DISPONIBLE
    assert refs["t5_max"] == NO_DISPONIBLE
    assert refs["cobertura"] != NO_DISPONIBLE

    # y llega tal cual al informe
    from pruebas.informe import componer
    from pruebas.localizar import Localizacion

    monkeypatch.setattr(cifras_ref, "RUTA_CIFRAS", ruta)
    texto, datos = componer(
        fecha="hoy", argumentos={}, master={}, brutos=[], ignorados=[],
        localizacion=Localizacion([], [], [], {}), fps_master=25.0, medidas_t1={},
        medidas_t5=[], errores_medida={}, ficheros={}, avisos=[], tiempos={},
    )
    fila_t1 = next(linea for linea in texto.splitlines() if "el peor plano" in linea)
    assert NO_DISPONIBLE in fila_t1
    assert datos["referencias_cifras_md"]["t1_max"] == NO_DISPONIBLE


def test_sin_fichero_todo_no_disponible(tmp_path):
    refs = referencias_para_informe(tmp_path / "no_esta.md")
    assert set(refs.values()) == {NO_DISPONIBLE}


def test_con_el_cifras_md_de_verdad_lo_leido_esta_escrito_alli():
    """No se fija ningun valor: se comprueba que cada numero leido aparece en el archivo."""
    texto = cifras_ref.RUTA_CIFRAS.read_text(encoding="utf-8")
    refs = referencias_para_informe()
    assert refs["t1_max"] != NO_DISPONIBLE, "CIFRAS.md ya no tiene el maximo de T1"
    for clave, valor in refs.items():
        if valor == NO_DISPONIBLE:
            continue
        for r in valor:
            assert r.valor.split()[-1].strip("*") in texto.replace("**", ""), (clave, r)
            if r.numero is not None:
                assert f"{r.numero:g}" in texto or str(r.numero) in texto, (clave, r)
    for r in refs["t1_max"]:  # type: ignore[union-attr]
        assert r.numero is not None and math.isfinite(r.numero)


# ---------------------------------------------------------------------------
# Estimacion de coste
# ---------------------------------------------------------------------------


def test_sin_costes_medidos_dice_no_medido():
    e = coste.estimar(master=(1920, 1080, 1500), brutos=[(3840, 2160, 750, 30.0)] * 2,
                      ancho_analisis=960, paso=12, coste=None)
    assert e.segundos is None
    assert "no medido" in e.nota
    # el espacio si se sabe: es aritmetica, 6 bytes por pixel como mucho
    assert e.bytes_disco >= 2 * 6.0 * (3840 * 2160 + 1920 * 1080)


def test_la_cuenta_del_tiempo_es_la_escrita():
    c = {
        "decodificar_s_por_fotograma_mpx": 0.001, "escaneo_master_s_por_fotograma": 0.001,
        "escaneo_bruto_s_por_segundo": 0.01, "localizar_s_por_punto": 0.1,
        "afinar_s_por_plano_sin_leer": 0.0, "fotogramas_leidos_por_plano": 10,
        "lecturas_por_plano": 2, "extraer_s_por_fotograma_fijo": 0.05,
        "extraer_s_por_fotograma_mpx": 0.01, "invertir_s_por_mpx": 10.0,
        "t5_s_por_pareja_mpx": 1.0, "hoja_bytes_por_plano": 1000.0,
        "memoria_bytes_por_fotograma_master": 10.0, "memoria_bytes_por_segundo_bruto": 100.0,
    }
    e = coste.estimar(master=(1920, 1080, 1200), brutos=[(1920, 1080, 250, 10.0)] * 3,
                      ancho_analisis=960, paso=12, coste=c)
    mpx = 1920 * 1080 / 1e6
    mpx_a = 960 * 540 / 1e6
    assert e.desglose_s["escanear master"] == pytest.approx(1200 * (0.001 * mpx + 0.001))
    assert e.desglose_s["escanear brutos"] == pytest.approx(3 * (250 * 0.001 * mpx + 10 * 0.01))
    assert e.desglose_s["localizar"] == pytest.approx(100 * 0.1 + 3 * (10 * 0.001 * mpx + 2 * 0.05))
    assert e.desglose_s["T1 (sacar el grado)"] == pytest.approx(3 * 10.0 * mpx_a)
    assert e.desglose_s["T5 (aplicarlo a los demas)"] == pytest.approx(3 * 2 * 1.0 * mpx_a)
    assert e.memoria_bytes == pytest.approx(1200 * 10 + 3 * 10 * 100)


def test_el_json_de_costes_del_repo_tiene_todas_las_claves():
    c = coste.leer_coste()
    if c is None:
        pytest.skip("pruebas/coste_medido.json no generado (.venv/bin/python pruebas/medir_coste.py)")
    e = coste.estimar(master=(1920, 1080, 1500), brutos=[(3840, 2160, 750, 30.0)],
                      ancho_analisis=960, paso=12, coste=c)
    assert e.segundos is not None and e.segundos > 0
