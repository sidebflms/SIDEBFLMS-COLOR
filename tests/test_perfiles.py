"""`core.perfiles`: perfiles de trabajo reutilizables (día 9, continuación
10) — un ajuste de cámara conocido + un look compartido, horneados juntos en
un solo LUT por cámara.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import CDL, LUT3D, ClipRef
from core.perfiles import PerfilCamara, PerfilTrabajo, camara_para_clip, lut_para_camara
from core.reverse.relleno import rejilla_de_entradas


def _ref(manufacturer: str | None, tipo: str | None = None) -> ClipRef:
    return ClipRef(
        clip_id="c1",
        name="clip",
        track=1,
        index=1,
        start_frame=0,
        end_frame=99,
        camera_manufacturer=manufacturer,
        camera_type=tipo,
    )


# ---------------------------------------------------------------------------
# camara_para_clip
# ---------------------------------------------------------------------------


def test_reconoce_por_fabricante():
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro"),))
    assert camara_para_clip(perfil, _ref("GoPro")) is not None
    assert camara_para_clip(perfil, _ref("Sony")) is None


def test_reconoce_por_fabricante_y_tipo():
    perfil = PerfilTrabajo(
        nombre="Fabrik",
        camaras=(PerfilCamara(fabricante_contiene="sony", tipo_contiene="fx3"),),
    )
    assert camara_para_clip(perfil, _ref("Sony", "ILME-FX3")) is not None
    assert camara_para_clip(perfil, _ref("Sony", "A7S3")) is None


def test_sin_metadata_no_reconoce_nada():
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro"),))
    assert camara_para_clip(perfil, _ref(None)) is None


def test_se_queda_con_la_primera_que_coincide_en_orden():
    especifica = PerfilCamara(fabricante_contiene="gopro", tipo_contiene="hero12", nombre_legible="GoPro 12")
    generica = PerfilCamara(fabricante_contiene="gopro", nombre_legible="GoPro (otro modelo)")
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(especifica, generica))
    encontrada = camara_para_clip(perfil, _ref("GoPro", "HERO12 Black"))
    assert encontrada is especifica


# ---------------------------------------------------------------------------
# lut_para_camara
# ---------------------------------------------------------------------------


def test_sin_camara_ni_look_no_hay_nada_que_escribir():
    perfil = PerfilTrabajo(nombre="Fabrik")
    assert lut_para_camara(perfil, None, n=5) is None


def test_camara_sin_ajuste_y_sin_look_no_hay_nada_que_escribir():
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro"),))
    camara = camara_para_clip(perfil, _ref("GoPro"))
    assert lut_para_camara(perfil, camara, n=5) is None


def test_solo_ajuste_de_camara_sin_look_hornea_el_cdl():
    cdl = CDL(slope=(1.1, 1.0, 0.9), offset=(0.02, 0.0, -0.01), power=(1.0, 1.0, 1.0))
    camara = PerfilCamara(fabricante_contiene="gopro", cdl_base=cdl)
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(camara,))
    lut = lut_para_camara(perfil, camara, n=9)
    assert lut is not None
    entradas = rejilla_de_entradas(9)
    esperado = np.clip(cdl.apply(entradas), 0.0, 1.0).astype(np.float32)
    np.testing.assert_allclose(lut.table, esperado)


def test_solo_look_sin_camara_es_el_look_tal_cual():
    look = LUT3D.identity(9)
    perfil = PerfilTrabajo(nombre="Fabrik", look=look)
    lut = lut_para_camara(perfil, None, n=9)
    assert lut is not None
    np.testing.assert_allclose(lut.table, look.table)


def test_camara_y_look_se_componen_en_orden_camara_luego_look():
    cdl = CDL(slope=(1.2, 1.0, 0.8), offset=(0.03, 0.0, -0.02), power=(1.0, 1.0, 1.0))
    camara = PerfilCamara(fabricante_contiene="gopro", cdl_base=cdl)
    # Un "look" que no es la identidad, para que el orden de composicion importe.
    look_cdl = CDL(saturation=1.3)
    look = LUT3D(table=np.clip(look_cdl.apply(rejilla_de_entradas(9)), 0, 1).astype(np.float32))
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(camara,), look=look)

    lut = lut_para_camara(perfil, camara, n=9)
    entradas = rejilla_de_entradas(9)
    con_camara = np.clip(cdl.apply(entradas), 0.0, 1.0).astype(np.float32)
    esperado = np.clip(look.apply(con_camara), 0.0, 1.0).astype(np.float32)
    np.testing.assert_allclose(lut.table, esperado)

    # Y el orden importa de verdad: aplicar el look ANTES que la camara da otra cosa.
    al_reves = np.clip(camara.cdl_base.apply(look.apply(entradas)), 0.0, 1.0).astype(np.float32)
    assert not np.allclose(lut.table, al_reves)


@pytest.mark.parametrize("n", [5, 9, 17])
def test_el_tamano_de_rejilla_se_respeta(n):
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="x", cdl_base=CDL(saturation=1.1)),))
    camara = perfil.camaras[0]
    lut = lut_para_camara(perfil, camara, n=n)
    assert lut.size == n
