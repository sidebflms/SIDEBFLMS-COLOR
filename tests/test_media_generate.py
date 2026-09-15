"""El generador de material es el suelo de todo. Si miente, mienten los 4 tests
entregables de la seccion 6."""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import requiere_ffmpeg
from tests.media import generate as gen


def test_es_reproducible():
    a = gen.studio_scene(skin_tone_index=3).image
    b = gen.studio_scene(skin_tone_index=3).image
    assert np.array_equal(a, b)


def test_ruido_es_reproducible():
    assert np.array_equal(gen.noise_field(), gen.noise_field())


def test_formato_de_salida(escena_estudio):
    img = escena_estudio.image
    assert img.dtype == np.float32
    assert img.ndim == 3 and img.shape[2] == 3
    assert img.min() >= 0.0


def test_la_escena_tiene_especular_fuera_de_rango(escena_estudio):
    """Si todo cupiera en 0..1 no estariamos probando nada."""
    assert escena_estudio.image.max() > 1.2


def test_la_escena_tiene_negros_con_detalle(escena_estudio):
    oscuros = escena_estudio.image[escena_estudio.image < 0.02]
    assert oscuros.size > 0
    assert oscuros.std() > 0.0


def test_la_mascara_de_piel_cubre_area_suficiente(escenas_pieles):
    for escena in escenas_pieles:
        fraccion = escena.skin_mask.mean()
        assert 0.03 < fraccion < 0.45, f"{escena.name}: piel al {fraccion:.1%}"


def test_los_seis_tonos_de_piel_son_distinguibles(escenas_pieles):
    medias = [e.image[e.skin_mask].mean(axis=0) for e in escenas_pieles]
    for i, (a, b) in enumerate(zip(medias, medias[1:])):  # noqa: B905  longitudes distintas a proposito
        assert np.linalg.norm(a - b) > 0.05, f"los tonos {i} y {i + 1} se parecen demasiado"


def test_estudio_y_exterior_son_incompatibles(escena_estudio, escena_exterior):
    """Son la pareja del detector de desajuste de contenido: si sus estadisticas
    se parecieran, el test de desajuste no probaria nada."""
    a = escena_estudio.image.reshape(-1, 3).mean(axis=0)
    b = escena_exterior.image.reshape(-1, 3).mean(axis=0)
    assert np.linalg.norm(a - b) > 0.1


def test_carta_tiene_24_colores_distintos(carta):
    colores = {tuple(np.round(c, 5)) for c in carta.reshape(-1, 3)}
    assert len(colores) >= 25  # 24 parches + el fondo


def test_rampa_es_monotona(rampa):
    fila = rampa[rampa.shape[0] // 2, :, 0]
    assert np.all(np.diff(fila) > 0)


def test_hald_cubre_el_cubo_entero():
    img = gen.hald(17)
    entradas = img.reshape(-1, 3)[: 17**3]
    assert np.isclose(entradas.min(), 0.0) and np.isclose(entradas.max(), 1.0)
    assert len({tuple(np.round(e, 6)) for e in entradas}) == 17**3


def test_vineta_oscurece_las_esquinas(escena_estudio):
    out = gen.apply_vignette(escena_estudio.image, strength=0.5)
    h, w = out.shape[:2]
    assert out[2, 2].mean() < escena_estudio.image[2, 2].mean()
    # El centro no se toca. No es identidad exacta porque con lado par el pixel
    # central no cae en el centro geometrico: la ganancia ahi es 0.9999998, no 1.
    assert out[h // 2, w // 2] == pytest.approx(escena_estudio.image[h // 2, w // 2], rel=1e-5)


def test_ventana_solo_toca_su_zona(escena_estudio):
    img = escena_estudio.image
    out = gen.apply_window(img, box=(400, 40, 120, 90), gain=1.5, feather=8)
    assert out[80, 450].mean() > img[80, 450].mean() * 1.2
    assert np.allclose(out[300, 20], img[300, 20], atol=1e-4)


def test_ida_y_vuelta_srgb(rng):
    x = rng.random((100, 3))
    assert np.abs(gen.srgb_eotf(gen.srgb_oetf(x)) - x).max() < 1e-6


@requiere_ffmpeg
def test_escribe_un_clip_legible(salida, escena_estudio):
    import cv2

    ruta = gen.make_clip(salida / "c.mov", [escena_estudio.image] * 3, codec="prores")
    assert ruta.is_file() and ruta.stat().st_size > 1000
    cap = cv2.VideoCapture(str(ruta))
    ok, frame = cap.read()
    cap.release()
    assert ok and frame.shape[:2] == escena_estudio.image.shape[:2]


def test_solo_escribe_donde_le_dicen(salida, escena_estudio):
    antes = set(salida.iterdir())
    gen.write_png16(salida / "x.png", escena_estudio.image)
    nuevos = set(salida.iterdir()) - antes
    assert {p.name for p in nuevos} == {"x.png"}
