"""El lector de `CIFRAS.md` y la estimacion de coste: nada copiado a mano, nada inventado.

`CIFRAS.md` cambia (hoy entraron las filas de T5), asi que estos tests **no fijan
valores de ese archivo**: comprueban que lo que se lee esta escrito alli; que el
titular de T1 sale **solo** de la tabla de titulares aunque otra seccion tenga una
fila «T1 ... maximo» (la trampa real fue «T1 A->A maximo en escena rica (A5)»); y
que con una tabla a la que le falta una fila el informe dice «no disponible en
CIFRAS.md» en vez de fallar o de inventar.
"""

from __future__ import annotations

import math
import re

import pytest

from pruebas import cifras_ref, coste
from pruebas.cifras_ref import NO_DISPONIBLE, buscar, leer_tablas, referencias_para_informe

TABLAS = """
# CIFRAS de juguete

## 1 · Las cifras de titular

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

### La cifra que faltaba en la tabla de titulares
| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| **Cobertura del cubo, un solo plano** | **165 de 35.937 = 0.46%** | repo, LUT 33³ | `c` | 01-01 |

## 3 · Ingeniería inversa
| Cifra | Valor | Montaje | Comando | Fecha |
|---|---|---|---|---|
| T1 máximo de una trampa en otra sección | 99.9 | trampa | `c` | 01-01 |
| Cobertura de otra cosa | 50% | trampa | `c` | 01-01 |

## 8 · T5 — el LUT de un plano en otro
| Cifra | Valor | Montaje | Línea de la salida | Fecha |
|---|---|---|---|---|
| **T5 máximo en B, plano normal** | **3.5 – 5.9; 0 de 12 bajo 3.0** ✔ | A2 | `[T5 AB]` | 01-01 |
| T5 medio en B, plano normal | 0.33 – 1.68 | ídem | ídem | 01-01 |
| T5 corte de cobertura para máximo < 3.0 | no existe | ídem | ídem | 01-01 |
| **T1 A→A máximo en escena rica (A5)** | **4.00095 / 3.85405 — NO cumple < 3.0** ✔ | A5 | `[T5 ref]` | 01-01 |
"""


def _consulta(clave: str) -> cifras_ref.Consulta:
    return next(c for c in cifras_ref.CONSULTAS if c.clave == clave)


def test_cada_cifra_sale_solo_de_su_sitio():
    filas = leer_tablas(TABLAS)
    t1 = buscar(filas, _consulta("t1_max"))
    assert [(r.etiqueta, r.numero, r.limite) for r in t1] == [("T1 ingeniería inversa", 2.5, "< 3.0")]
    medio = buscar(filas, _consulta("t1_medio"))
    assert [r.numero for r in medio] == [0.12]  # columnas en otro orden en esa tabla
    cob = buscar(filas, _consulta("cobertura"))
    assert [r.numero for r in cob] == [pytest.approx(0.46)]
    t5 = buscar(filas, _consulta("t5_max"))
    assert [r.etiqueta for r in t5] == ["T5 máximo en B, plano normal"]
    assert t5[0].numero is None  # un rango: no se elige un numero, se da el texto
    assert [r.etiqueta for r in buscar(filas, _consulta("t5_medio"))] == [
        "T5 medio en B, plano normal"
    ]


def test_las_filas_trampa_de_otras_secciones_no_entran():
    """«T1 ... máximo» fuera de la tabla de titulares NO es el titular de T1."""
    refs = {c.clave: buscar(leer_tablas(TABLAS), c) for c in cifras_ref.CONSULTAS}
    todas = [r for rs in refs.values() for r in rs]
    etiquetas = " ".join(r.etiqueta for r in todas)
    assert "A5" not in etiquetas
    assert "trampa" not in etiquetas
    assert "otra cosa" not in etiquetas
    assert "corte de cobertura" not in etiquetas
    assert all(r.numero != 99.9 for r in todas)


def test_sin_tabla_de_titulares_el_maximo_de_t1_no_se_busca_en_otra_parte(tmp_path):
    """Quitando la tabla de titulares, la fila trampa de T1 sigue sin entrar: no disponible."""
    sin_titulares = "\n".join(
        linea for linea in TABLAS.splitlines()
        if "Criterio" not in linea and "ingeniería inversa" not in linea and "igualado" not in linea
    )
    ruta = tmp_path / "CIFRAS.md"
    ruta.write_text(sin_titulares, encoding="utf-8")
    refs = referencias_para_informe(ruta)
    assert refs["t1_max"] == NO_DISPONIBLE


def test_una_fila_que_falta_sale_como_no_disponible(tmp_path, monkeypatch):
    sin_t1 = "\n".join(linea for linea in TABLAS.splitlines() if "T1" not in linea)
    ruta = tmp_path / "CIFRAS.md"
    ruta.write_text(sin_t1, encoding="utf-8")
    refs = referencias_para_informe(ruta)
    assert refs["t1_max"] == NO_DISPONIBLE
    assert refs["t1_medio"] == NO_DISPONIBLE
    assert refs["cobertura"] != NO_DISPONIBLE
    assert refs["t5_max"] != NO_DISPONIBLE

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
    """No se fija ningun valor: lo leido esta escrito alli, y el T1 sale de los titulares."""
    texto = cifras_ref.RUTA_CIFRAS.read_text(encoding="utf-8")
    limpio = re.sub(r"\s+", " ", texto.replace("**", "").replace("`", ""))
    filas = leer_tablas(texto)
    titulares = {cifras_ref._limpia(f["criterio"]) for f in filas if f.get("_titulares")}
    refs = referencias_para_informe()
    assert refs["t1_max"] != NO_DISPONIBLE, "CIFRAS.md ya no tiene el maximo de T1 en titulares"
    for r in refs["t1_max"]:  # type: ignore[union-attr]
        assert r.etiqueta in titulares, r
        assert r.numero is not None and math.isfinite(r.numero), r
    for clave, valor in refs.items():
        if valor == NO_DISPONIBLE:
            continue
        for r in valor:
            assert r.etiqueta in limpio and r.valor in limpio, (clave, r)
            if r.numero is not None:
                assert f"{r.numero:g}" in texto, (clave, r)


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
