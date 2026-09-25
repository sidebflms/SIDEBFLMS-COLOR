"""Las seis incognitas: que esten todas, que el valor de hoy sea el pesimista,
y que cambiarlas cambie de verdad el comportamiento de la app.

Si manana Mario cambia una constante y no pasa nada, es que la decision no
estaba aislada donde decia que estaba.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.contracts import NODE_LOOK
from core.resolve import FakeResolve, Incognitas, asegurar_version
from core.resolve.bridge import RutaLUTInvalida
from core.resolve.incognitas import (
    INCOGNITAS_CONSERVADORAS,
    LUT_DIR_DESCARGA,
    extensiones_lut_aceptadas,
    formatos_export_disponibles,
    lut_dir,
    still_sirve_para_medir,
)
from core.resolve.incognitas import (
    Incognitas as Inc,
)

RAIZ = Path(__file__).resolve().parent.parent


def test_los_valores_de_hoy_son_los_confirmados_o_los_conservadores():
    """Día 9 (continuación 5): el probe corrió contra Resolve real por primera
    vez. F0-1 y F0-6 salieron confirmados; F0-2/F0-3/F0-5 se intentaron y
    quedaron inconclusos (no "confirmados en falso") así que se quedan en su
    valor conservador de siempre — ver los comentarios de cada campo en
    `core/resolve/incognitas.py`."""
    i = INCOGNITAS_CONSERVADORAS
    assert i.export_drx_funciona is True  # F0-1, confirmado 2026-09-25
    assert i.still_lleva_grado is False  # F0-2, intentado, inconcluso
    assert i.setlut_acepta_dctl is False  # F0-3, sin .dctl con que probar
    assert i.instalacion == "descarga"  # F0-4, confirmado 2026-09-25
    assert i.requiere_open_page is True  # F0-5, intentado, inconcluso
    assert i.fusionscript_importable is True  # F0-6, confirmado 2026-09-25


def test_las_seis_estan_marcadas_en_el_codigo():
    """Cada `# TODO(F0-n)` tiene que existir, para poder encontrarlas manana."""
    fuentes = "\n".join(
        p.read_text(encoding="utf-8") for p in (RAIZ / "core" / "resolve").glob("*.py")
    )
    for n in range(1, 7):
        assert f"TODO(F0-{n})" in fuentes, f"falta la marca de la incognita F0-{n}"


def test_la_decision_de_cada_incognita_esta_en_un_solo_sitio():
    """Una marca por incognita como maximo en todo `core/` fuera de incognitas.py,
    y las de incognitas.py concentradas en su funcion."""
    ficheros = sorted((RAIZ / "core").rglob("*.py"))
    assert ficheros, f"no hay nada que comprobar: {RAIZ / 'core'} sin ningun .py"
    for p in ficheros:
        if p.name == "incognitas.py":
            continue
        texto = p.read_text(encoding="utf-8")
        for n in range(1, 7):
            assert len(re.findall(rf"TODO\(F0-{n}\)", texto)) <= 1, f"{p} repite F0-{n}"


def test_describir_da_seis_frases():
    frases = Incognitas().describir()
    assert len(frases) == 6
    assert all(f.startswith("F0-") for f in frases)


# --- F0-4: la carpeta de LUTs ---------------------------------------------


def test_carpeta_de_luts_descarga_directa():
    assert lut_dir(Inc(instalacion="descarga")) == LUT_DIR_DESCARGA


def test_carpeta_de_luts_del_mac_app_store():
    ruta = lut_dir(Inc(instalacion="mac_app_store"), home="/Users/quien/sea")
    assert ruta.startswith("/Users/quien/sea/Library/Containers/")
    assert "DaVinciResolveAppStore" in ruta
    assert ruta.endswith("/LUT")


def test_la_carpeta_de_luts_no_se_comprueba_contra_el_disco():
    """No se toca el sistema de ficheros: se devuelve la cadena y punto."""
    ruta = lut_dir(Inc(instalacion="mac_app_store"), home="/esto/no/existe/en/ningun/mac")
    assert ruta.startswith("/esto/no/existe/en/ningun/mac")


def test_las_dos_candidatas_son_distintas():
    a = lut_dir(Inc(instalacion="descarga"))
    b = lut_dir(Inc(instalacion="mac_app_store"), home="/Users/x")
    assert a != b


# --- F0-3: el .dctl --------------------------------------------------------


def test_extensiones_aceptadas_hoy_y_manana():
    assert extensiones_lut_aceptadas(Inc()) == (".cube",)
    assert extensiones_lut_aceptadas(Inc(setlut_acepta_dctl=True)) == (".cube", ".dctl")


def test_cambiar_f0_3_cambia_lo_que_traga_el_puente():
    estricto = FakeResolve(n_clips=1)
    asegurar_version(estricto, "clip001")
    with pytest.raises(RutaLUTInvalida):
        estricto.set_lut("clip001", NODE_LOOK, "x.dctl")
    permisivo = FakeResolve(n_clips=1, incognitas=Inc(setlut_acepta_dctl=True))
    asegurar_version(permisivo, "clip001")
    assert permisivo.set_lut("clip001", NODE_LOOK, "x.dctl") is True


# --- F0-1: el .drx ---------------------------------------------------------


def test_el_drx_se_ofrece_desde_que_se_confirmo():
    """F0-1 confirmado el 2026-09-25 contra Resolve real: el valor por
    defecto ya ofrece 'drx'. `export_drx_funciona=False` sigue existiendo
    para quien necesite ser conservador (otra build, otra máquina)."""
    assert "drx" in formatos_export_disponibles(Inc())
    assert "drx" not in formatos_export_disponibles(Inc(export_drx_funciona=False))
    assert "cube" not in formatos_export_disponibles(Inc())  # cube no es un still


# --- F0-2: el still ---------------------------------------------------------


def test_hoy_el_still_no_sirve_para_medir():
    assert still_sirve_para_medir(Inc()) is False
    assert still_sirve_para_medir(Inc(still_lleva_grado=True)) is True


# --- F0-5 y F0-6 -----------------------------------------------------------


def test_f0_5_por_defecto_llama_a_open_page():
    assert Inc().requiere_open_page is True


def test_f0_6_no_afecta_al_comportamiento_de_la_app():
    """La app no depende de este valor: es informativo hasta que haya LiveResolve."""
    a = FakeResolve(n_clips=1, incognitas=Inc(fusionscript_importable=True))
    b = FakeResolve(n_clips=1, incognitas=Inc(fusionscript_importable=False))
    assert a.project_info().lut_dir == b.project_info().lut_dir
