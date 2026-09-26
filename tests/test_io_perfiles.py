"""`core.io.perfiles`: guardar y cargar un `PerfilTrabajo` por nombre (día 9,
continuación 10) — una carpeta con `perfil.json` + `look.cube` opcional.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.contracts import CDL, LUT3D
from core.io.errores import ErrorPerfil
from core.io.perfiles import borrar_perfil, cargar_perfil, guardar_perfil, listar_perfiles
from core.perfiles import PerfilCamara, PerfilTrabajo


def _perfil_de_prueba(*, con_look: bool = True) -> PerfilTrabajo:
    camaras = (
        PerfilCamara(
            fabricante_contiene="gopro",
            tipo_contiene="hero12",
            nombre_legible="GoPro Hero 12",
            cdl_base=CDL(slope=(1.05, 1.0, 0.95), offset=(0.01, 0.0, -0.005), saturation=1.1),
        ),
        PerfilCamara(fabricante_contiene="dji", nombre_legible="Dron DJI"),
    )
    look = LUT3D.identity(9) if con_look else None
    return PerfilTrabajo(nombre="Fabrik", camaras=camaras, look=look)


def test_guardar_y_cargar_da_lo_mismo(tmp_path: Path):
    original = _perfil_de_prueba()
    guardar_perfil(original, tmp_path / "fabrik", crear_directorios=True)

    releido = cargar_perfil(tmp_path / "fabrik")

    assert releido.nombre == "Fabrik"
    assert len(releido.camaras) == 2
    c1, c2 = releido.camaras
    assert c1.fabricante_contiene == "gopro"
    assert c1.tipo_contiene == "hero12"
    assert c1.nombre_legible == "GoPro Hero 12"
    assert c1.cdl_base == original.camaras[0].cdl_base
    assert c2.fabricante_contiene == "dji"
    assert releido.look is not None
    np.testing.assert_allclose(releido.look.table, original.look.table)


def test_sin_look_no_escribe_ni_lee_ningun_cube(tmp_path: Path):
    perfil = _perfil_de_prueba(con_look=False)
    guardar_perfil(perfil, tmp_path / "sin-look", crear_directorios=True)

    assert not (tmp_path / "sin-look" / "look.cube").exists()
    releido = cargar_perfil(tmp_path / "sin-look")
    assert releido.look is None


def test_guardar_sin_crear_directorios_lanza_si_no_existe(tmp_path: Path):
    with pytest.raises(ErrorPerfil):
        guardar_perfil(_perfil_de_prueba(), tmp_path / "no-existe")


def test_guardar_dos_veces_sin_look_borra_el_cube_de_la_vez_anterior(tmp_path: Path):
    carpeta = tmp_path / "fabrik"
    guardar_perfil(_perfil_de_prueba(con_look=True), carpeta, crear_directorios=True)
    assert (carpeta / "look.cube").exists()

    guardar_perfil(_perfil_de_prueba(con_look=False), carpeta)
    assert not (carpeta / "look.cube").exists()
    assert cargar_perfil(carpeta).look is None


def test_cargar_una_carpeta_sin_perfil_json_lanza():
    with pytest.raises(ErrorPerfil):
        cargar_perfil("/no/existe/de/verdad")


def test_cargar_json_corrupto_lanza(tmp_path: Path):
    carpeta = tmp_path / "roto"
    carpeta.mkdir()
    (carpeta / "perfil.json").write_text("esto no es json {{{", encoding="utf-8")
    with pytest.raises(ErrorPerfil):
        cargar_perfil(carpeta)


def test_listar_perfiles_encuentra_solo_carpetas_con_perfil_json(tmp_path: Path):
    guardar_perfil(_perfil_de_prueba(), tmp_path / "fabrik", crear_directorios=True)
    guardar_perfil(PerfilTrabajo(nombre="Boda"), tmp_path / "boda", crear_directorios=True)
    (tmp_path / "carpeta-vacia").mkdir()

    assert listar_perfiles(tmp_path) == ["boda", "fabrik"]


def test_listar_perfiles_carpeta_inexistente_da_lista_vacia(tmp_path: Path):
    assert listar_perfiles(tmp_path / "no-existe") == []


def test_borrar_perfil_quita_la_carpeta_entera(tmp_path: Path):
    carpeta = tmp_path / "fabrik"
    guardar_perfil(_perfil_de_prueba(), carpeta, crear_directorios=True)

    borrar_perfil(carpeta)

    assert not carpeta.exists()
    assert listar_perfiles(tmp_path) == []


def test_borrar_perfil_se_niega_si_no_es_una_carpeta_de_perfil(tmp_path: Path):
    carpeta_ajena = tmp_path / "no-es-un-perfil"
    carpeta_ajena.mkdir()
    (carpeta_ajena / "algo.txt").write_text("no me borres", encoding="utf-8")

    with pytest.raises(ErrorPerfil):
        borrar_perfil(carpeta_ajena)

    assert carpeta_ajena.is_dir()  # sigue ahi, no se ha tocado
