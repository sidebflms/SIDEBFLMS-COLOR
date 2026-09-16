"""Que se lee: solo lo que se pide por argumento, sin salir de las carpetas dadas.

Nada de estos tests toca discos reales: todo en `tmp_path`. Donde hay que
comprobar que se NIEGA a recorrer `/`, `/Volumes` o la carpeta personal, se
sustituye `os.walk` por una trampa que falla si se llama: asi se demuestra que se
niega ANTES de listar nada, sin listar nada.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pruebas import origen
from pruebas.origen import OrigenRechazado, listar_brutos, validar_master


def _video(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"no es un video de verdad; aqui solo se listan nombres")
    return ruta


def test_recorre_la_carpeta_dada_y_sus_subcarpetas(tmp_path):
    raiz = tmp_path / "BRUTOS"
    a = _video(raiz / "A001.MOV")
    b = _video(raiz / "tarjeta2" / "C0002.mp4")
    _video(raiz / "notas.txt")
    _video(raiz / "._A001.MOV")  # basura de macOS en exFAT
    listado = listar_brutos([raiz])
    assert sorted(p.name for p in listado.ficheros) == sorted([a.name, b.name])


def test_no_sigue_enlaces_que_salen_de_la_carpeta(tmp_path):
    raiz = tmp_path / "BRUTOS"
    dentro = _video(raiz / "A001.mov")
    fuera = _video(tmp_path / "OTRO_DISCO" / "secreto.mov")
    os.symlink(fuera, raiz / "enlace_fuera.mov")
    os.symlink(dentro, raiz / "enlace_dentro.mov")
    os.symlink(tmp_path / "OTRO_DISCO", raiz / "carpeta_enlazada")
    listado = listar_brutos([raiz])
    resueltos = {p.resolve() for p in listado.ficheros}
    assert fuera.resolve() not in resueltos
    assert dentro.resolve() in resueltos
    assert len(listado.ficheros) == 1  # el enlace de dentro es el mismo fichero
    motivos = " ".join(m for _, m in listado.ignorados)
    assert "sale de la carpeta" in motivos


def test_los_raw_se_listan_como_no_legibles(tmp_path):
    raiz = tmp_path / "BRUTOS"
    _video(raiz / "A001.braw")
    _video(raiz / "B001.R3D")
    listado = listar_brutos([raiz])
    assert listado.ficheros == []
    assert len(listado.ignorados) == 2
    assert all("RAW" in m for _, m in listado.ignorados)


def test_ficheros_sueltos_y_rutas_que_no_existen(tmp_path):
    a = _video(tmp_path / "suelto.mov")
    listado = listar_brutos([a, tmp_path / "no_existe.mov"])
    assert listado.ficheros == [a]
    assert listado.ignorados == [(str(tmp_path / "no_existe.mov"), "no existe")]


def test_la_lista_de_raices_prohibidas_incluye_volumes_raiz_y_home():
    assert Path("/Volumes") in origen._RAICES_PROHIBIDAS
    assert Path("/") in origen._RAICES_PROHIBIDAS
    assert Path.home() in origen._RAICES_PROHIBIDAS


def test_se_niega_a_recorrer_una_raiz_prohibida_sin_listarla(tmp_path, monkeypatch):
    """Con una carpeta sustituta en tmp_path: este test no toca el /Volumes real."""
    sustituta = tmp_path / "Volumes_de_mentira"
    _video(sustituta / "DISCO" / "A001.mov")

    def trampa(*_a, **_k):
        raise AssertionError("se ha intentado listar una carpeta prohibida")

    monkeypatch.setattr(origen, "_RAICES_PROHIBIDAS", (sustituta,))
    monkeypatch.setattr(origen.os, "walk", trampa)
    with pytest.raises(OrigenRechazado, match="demasiado general"):
        listar_brutos([sustituta])


def test_tope_de_ficheros_por_carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(origen, "MAX_FICHEROS_POR_CARPETA", 3)
    for k in range(4):
        _video(tmp_path / "B" / f"c{k}.mov")
    with pytest.raises(OrigenRechazado, match="disco entero"):
        listar_brutos([tmp_path / "B"])


def test_master_tiene_que_ser_un_fichero(tmp_path):
    with pytest.raises(OrigenRechazado, match="no existe"):
        validar_master(tmp_path / "nada.mov")
    (tmp_path / "carpeta").mkdir()
    with pytest.raises(OrigenRechazado, match="UN fichero"):
        validar_master(tmp_path / "carpeta")
    with pytest.raises(OrigenRechazado, match="RAW"):
        validar_master(_video(tmp_path / "m.braw"))
    assert validar_master(_video(tmp_path / "m.mov")).name == "m.mov"
