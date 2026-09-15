"""Extraccion de fotogramas: reparto, precision, imagenes sueltas y averias.

Todo el material sale de `tests/media/generate.py` y se escribe en `tmp_path`.
Aqui no se abre ni un fichero de Mario, ni un disco externo, ni /Volumes.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.analysis import (
    ErrorAnalisis,
    ErrorFFmpeg,
    FicheroNoEncontrado,
    FormatoNoSoportado,
    HerramientaNoDisponible,
    analizar_clip,
    extraer_fotogramas,
    sondear,
)
from core.analysis import frames as fr
from core.contracts import WORKING_SPACE
from core.paths import ExecutableNotFound
from tests.conftest import requiere_ffmpeg
from tests.media import generate as gen

pytestmark = requiere_ffmpeg


# ---------------------------------------------------------------------------
# Material de prueba
# ---------------------------------------------------------------------------


def _fotograma_plano(valor: float, lado: int = 32) -> np.ndarray:
    """Gris plano escena-lineal. Sirve de 'numero de fotograma' legible."""
    return np.full((lado, lado, 3), valor, dtype=np.float32)


#: Valor lineal del fotograma i de los clips de escalera de este archivo.
def _valor(i: int) -> float:
    return 0.02 + 0.03 * i


def _clip_escalera(carpeta, n: int, *, fps: int = 25, codec: str = "prores"):
    """Clip de `n` fotogramas, cada uno de un gris distinto y creciente."""
    fotogramas = [_fotograma_plano(_valor(i)) for i in range(n)]
    return gen.make_clip(carpeta / f"escalera{n}.mov", fotogramas, fps=fps, codec=codec)


def _lineal_de(fotograma_trabajo: np.ndarray) -> float:
    """Del fotograma ya en espacio de trabajo, de vuelta al valor escena-lineal.

    OJO con el camino: `generate.make_clip` codifica con la curva **sRGB**, y el
    modulo decodifica el clip como **Rec.709** (que es lo que asume por defecto y
    lo que trae etiquetado el material de camara de verdad). Las dos curvas NO son
    la misma, asi que para volver al lineal de origen hay que deshacer la de sRGB,
    no la de Rec.709. La diferencia esta medida en `test_la_curva_srgb_del_generador_no_es_la_de_rec709`.
    """
    from core.color import from_working

    codificado = np.asarray(from_working(fotograma_trabajo, "rec709"), dtype=np.float64)
    return float(gen.srgb_eotf(codificado).mean())


def _indice_de(fotograma_trabajo: np.ndarray) -> int:
    """Del fotograma ya en espacio de trabajo, de vuelta al indice de la escalera."""
    return int(round((_lineal_de(fotograma_trabajo) - 0.02) / 0.03))


# ---------------------------------------------------------------------------
# Reparto por el clip
# ---------------------------------------------------------------------------


def test_los_fotogramas_se_reparten_por_todo_el_clip(salida):
    """Lo que de verdad importa: NO se cogen los k primeros."""
    clip = _clip_escalera(salida, 20)
    fotogramas = extraer_fotogramas(clip, n_fotogramas=5)
    indices = [_indice_de(f) for f in fotogramas]
    assert indices == [0, 5, 10, 14, 19], indices
    # Si se cogieran del principio, el ultimo indice seria 4 y no 19.
    assert indices[-1] >= 19


def test_pedir_todos_los_fotogramas_los_da_todos_y_en_orden(salida):
    clip = _clip_escalera(salida, 10)
    fotogramas = extraer_fotogramas(clip, n_fotogramas=10)
    assert [_indice_de(f) for f in fotogramas] == list(range(10))


def test_el_ultimo_fotograma_del_clip_es_alcanzable(salida):
    """Regresion: pedir el CENTRO del ultimo fotograma devolvia cero bytes.

    ffmpeg con `-ss` antes de `-i` entrega el primer fotograma con pts >= ss, asi
    que pedir el centro del ultimo se plantaba detras del final del fichero.
    """
    clip = _clip_escalera(salida, 6)
    fotogramas = extraer_fotogramas(clip, n_fotogramas=6)
    assert len(fotogramas) == 6
    assert _indice_de(fotogramas[-1]) == 5


def test_forma_tipo_y_espacio(salida):
    from core.color import convert

    clip = _clip_escalera(salida, 8)
    fotogramas = extraer_fotogramas(clip, n_fotogramas=3)
    assert fotogramas.shape == (3, 32, 32, 3)
    assert fotogramas.dtype == np.float32

    # Lo que sale NO es el valor crudo del fichero: es el valor ya llevado al
    # espacio de trabajo por el camino completo (curva de origen -> primarios ->
    # curva de DaVinci Intermediate).
    gris = extraer_fotogramas(
        gen.make_clip(salida / "gris.mov", [_fotograma_plano(0.18)] * 3, fps=25),
        n_fotogramas=1,
    )
    crudo = float(gen.srgb_oetf(np.array(0.18)))
    esperado = float(convert(np.full((1, 1, 3), crudo, np.float32), "rec709", WORKING_SPACE).mean())
    assert gris[0].mean() == pytest.approx(esperado, abs=2e-3)
    assert abs(gris[0].mean() - crudo) > 0.05, "esto sigue siendo el valor del fichero"


def test_la_curva_srgb_del_generador_no_es_la_de_rec709(salida):
    """Limite real, medido y escrito: el generador codifica en sRGB y nosotros
    decodificamos en Rec.709 porque es lo que asume el modulo. Las dos curvas se
    separan en las sombras, y aqui queda el numero en vez de esconderlo.

    No afecta al material de camara (que viene etiquetado bt709 y se decodifica
    con la curva correcta), pero si a cualquiera que compare estos clips
    sinteticos contra el `Scene.image` original.
    """
    from core.color import from_working

    clip = gen.make_clip(salida / "sombra.mov", [_fotograma_plano(0.045)] * 3, fps=25)
    f = extraer_fotogramas(clip, n_fotogramas=1)[0]
    codificado = float(np.asarray(from_working(f, "rec709")).mean())
    como_srgb = float(gen.srgb_eotf(np.array(codificado)))
    como_709 = float(np.asarray(from_working(f, "linear_rec709")).mean())
    assert como_srgb == pytest.approx(0.045, abs=1e-3)
    # El mismo valor leido con la curva equivocada se va un 55% arriba.
    assert como_709 / como_srgb == pytest.approx(1.567, rel=0.05)


# ---------------------------------------------------------------------------
# Precision: 16 bits, no 8
# ---------------------------------------------------------------------------


def test_la_tuberia_es_de_16_bits_y_no_de_8(salida):
    """Una rampa de 512 pasos tiene que salir con mas de 256 niveles distintos.

    Si alguien cambiara el `rgb48le` por un PNG de 8 bits, este test cae al
    instante: por ancho de banda, en 8 bits no caben mas de 256 niveles.
    """
    rampa = gen.ramp_gray(width=512, height=64)
    clip = gen.make_clip(salida / "rampa.mov", [rampa] * 3, fps=25)
    fotograma = extraer_fotogramas(clip, n_fotogramas=1)[0]
    niveles = np.unique(np.round(fotograma[..., 0].astype(np.float64), 6)).size
    # El techo real no es 65.536: `make_clip` escribe ProRes 4444 en yuv444p10le,
    # o sea 10 bits (1.024 niveles), y una rampa de 12 pasos de luz amontona la
    # mitad de sus 512 columnas en las sombras. 350 niveles medidos: imposible en
    # 8 bits, coherente con 10.
    assert niveles > 300, f"solo {niveles} niveles distintos: esto huele a 8 bits"


def test_ida_y_vuelta_por_el_clip_conserva_el_valor(salida):
    """ProRes 4444 + 16 bits: el gris que entra es el que sale, dentro de 1e-3."""
    valores = [0.045, 0.18, 0.55]
    clip = gen.make_clip(
        salida / "grises.mov", [_fotograma_plano(v) for v in valores], fps=25
    )
    fotogramas = extraer_fotogramas(clip, n_fotogramas=3)
    for esperado, f in zip(valores, fotogramas, strict=True):
        assert _lineal_de(f) == pytest.approx(esperado, abs=1e-3)


# ---------------------------------------------------------------------------
# Casos frontera del propio fichero
# ---------------------------------------------------------------------------


def test_clip_de_un_solo_fotograma(salida):
    clip = gen.make_clip(salida / "uno.mov", [_fotograma_plano(0.2)], fps=25)
    fotogramas = extraer_fotogramas(clip, n_fotogramas=12)
    assert fotogramas.shape[0] == 1
    analisis = analizar_clip(clip, n_fotogramas=12)
    assert analisis.sampled_frames == 1
    assert any("un solo fotograma" in a for a in analisis.warnings)


def test_clip_con_menos_fotogramas_de_los_que_se_piden(salida):
    clip = _clip_escalera(salida, 4)
    analisis = analizar_clip(clip, n_fotogramas=12)
    assert analisis.sampled_frames == 4
    assert analisis.frame_count == 4
    assert any("solo tiene 4 fotogramas" in a for a in analisis.warnings)


def test_clip_truncado_a_mitad_no_revienta(salida):
    """Se corta el fichero por la mitad. Lo que NO puede pasar es un traceback."""
    clip = _clip_escalera(salida, 40)
    crudo = clip.read_bytes()
    roto = salida / "truncado.mov"
    roto.write_bytes(crudo[: len(crudo) // 2])
    try:
        analisis = analizar_clip(roto, n_fotogramas=6)
    except ErrorAnalisis as e:
        assert str(e), "el error tiene que traer mensaje"
        assert "truncado" in str(e) or "decodificar" in str(e)
    else:
        assert analisis.sampled_frames >= 1
        assert analisis.stats.n_samples > 0


def test_fichero_que_no_existe(salida):
    with pytest.raises(FicheroNoEncontrado) as e:
        extraer_fotogramas(salida / "no_existe.mov")
    assert "No existe" in str(e.value)


def test_una_carpeta_no_es_un_clip(salida):
    with pytest.raises(FicheroNoEncontrado) as e:
        extraer_fotogramas(salida)
    assert "carpeta" in str(e.value)


def test_fichero_vacio(salida):
    vacio = salida / "vacio.mov"
    vacio.write_bytes(b"")
    with pytest.raises(FormatoNoSoportado) as e:
        extraer_fotogramas(vacio)
    assert "vacio" in str(e.value)


def test_lo_que_no_es_un_video(salida):
    texto = salida / "notas.mov"
    texto.write_text("esto no es un clip, es una nota de produccion\n")
    with pytest.raises(FormatoNoSoportado) as e:
        extraer_fotogramas(texto)
    assert "notas.mov" in str(e.value)


def test_un_png_que_no_es_un_png(salida):
    falso = salida / "falso.png"
    falso.write_bytes(b"PNG de mentira")
    with pytest.raises(FormatoNoSoportado) as e:
        extraer_fotogramas(falso)
    assert "No he podido abrir" in str(e.value)


def test_sin_ffmpeg_el_error_lo_dice_en_castellano(salida, monkeypatch):
    clip = _clip_escalera(salida, 3)

    def sin_binario() -> str:
        raise ExecutableNotFound("No encuentro 'ffprobe'. Instalalo (brew install ffprobe).")

    monkeypatch.setattr(fr, "_ffprobe", sin_binario)
    with pytest.raises(HerramientaNoDisponible) as e:
        extraer_fotogramas(clip)
    assert "No encuentro" in str(e.value)
    assert isinstance(e.value, ErrorAnalisis)


def test_si_ffmpeg_no_decodifica_nada_se_dice_claro(salida, monkeypatch):
    clip = _clip_escalera(salida, 5)
    monkeypatch.setattr(fr, "_decodificar_uno", lambda *a, **k: None)
    with pytest.raises(ErrorFFmpeg) as e:
        extraer_fotogramas(clip, n_fotogramas=3)
    assert "ni un fotograma" in str(e.value)


# ---------------------------------------------------------------------------
# Imagenes sueltas
# ---------------------------------------------------------------------------


def test_png_de_16_bits_como_referencia(salida, escena_estudio):
    ruta = gen.write_png16(salida / "ref.png", escena_estudio.image)
    fotogramas = extraer_fotogramas(ruta, n_fotogramas=12)
    assert fotogramas.shape == (1, 360, 640, 3)
    assert fotogramas.dtype == np.float32
    info = sondear(ruta)
    assert info.es_imagen and info.n_fotogramas == 1


def test_exr_conserva_los_valores_fuera_de_rango(salida, escena_exterior):
    """El sol de `exterior_scene` esta a 9.0. Un rgb48le lo recortaria a 1.0."""
    cv2 = pytest.importorskip("cv2")
    assert cv2 is not None
    try:
        ruta = gen.write_exr(salida / "sol.exr", escena_exterior.image)
    except RuntimeError as e:  # OpenCV sin soporte OpenEXR
        pytest.skip(f"sin soporte EXR en este OpenCV: {e}")
    crudo = fr._leer_imagen(ruta)
    assert crudo.max() > 5.0, "el EXR ha vuelto recortado; se ha perdido el sol"
    fotogramas = extraer_fotogramas(ruta)
    assert fotogramas.shape[0] == 1


def test_el_exr_se_asume_lineal_y_el_png_codificado(salida, escena_estudio):
    png = gen.write_png16(salida / "e.png", escena_estudio.image)
    assert sondear(png).space_deducido == "rec709"
    try:
        exr = gen.write_exr(salida / "e.exr", escena_estudio.image)
    except RuntimeError as e:
        pytest.skip(f"sin soporte EXR: {e}")
    assert sondear(exr).space_deducido == "linear_rec709"


# ---------------------------------------------------------------------------
# Metadatos y espacio de origen
# ---------------------------------------------------------------------------


def test_sondear_da_resolucion_duracion_y_fotogramas(salida):
    clip = _clip_escalera(salida, 15, fps=25)
    info = sondear(clip)
    assert (info.ancho, info.alto) == (32, 32)
    assert info.n_fotogramas == 15
    assert info.fps == pytest.approx(25.0)
    assert info.duracion == pytest.approx(15 / 25, abs=0.05)
    assert not info.es_imagen


def test_si_no_se_sabe_el_espacio_se_avisa(salida):
    clip = _clip_escalera(salida, 4)
    analisis = analizar_clip(clip, n_fotogramas=2)
    assert analisis.source_space == fr.ESPACIO_ASUMIDO_VIDEO
    assert any("Asumo rec709" in a for a in analisis.warnings)


def test_el_espacio_que_se_pasa_a_mano_manda(salida):
    clip = _clip_escalera(salida, 4)
    analisis = analizar_clip(clip, n_fotogramas=2, space="slog3_sgamut3cine")
    assert analisis.source_space == "slog3_sgamut3cine"
    assert not any("Asumo" in a for a in analisis.warnings)
    # Y cambia de verdad los numeros: no es un campo decorativo.
    otro = analizar_clip(clip, n_fotogramas=2, space="rec709")
    assert not np.allclose(analisis.stats.mean, otro.stats.mean)


def test_si_el_fichero_trae_metadatos_de_color_se_usan(salida):
    """Un clip etiquetado bt709 se deduce solo, sin avisar de que se asume nada.

    El material de camara de verdad viene etiquetado; el que fabrica
    `generate.make_clip` no, por eso hay que ponerle la etiqueta a mano aqui.
    """
    import subprocess

    from core.paths import ffmpeg as ruta_ffmpeg

    crudo = _clip_escalera(salida, 4)
    etiquetado = salida / "bt709.mov"
    proc = subprocess.run(
        [ruta_ffmpeg(), "-v", "error", "-y", "-i", str(crudo), "-c", "copy",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         str(etiquetado)],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip("este ffmpeg no sabe reetiquetar el color del fichero")
    assert sondear(etiquetado).space_deducido == "rec709"
    analisis = analizar_clip(etiquetado, n_fotogramas=2)
    assert analisis.source_space == "rec709"
    assert not any("Asumo" in a for a in analisis.warnings)
    assert any("deducido de los metadatos" in a for a in analisis.warnings)


def test_n_fotogramas_tiene_que_ser_positivo(salida):
    clip = _clip_escalera(salida, 3)
    with pytest.raises(ValueError):
        extraer_fotogramas(clip, n_fotogramas=0)


# ---------------------------------------------------------------------------
# ClipAnalysis completo
# ---------------------------------------------------------------------------


def test_analizar_clip_rellena_el_contrato(salida, escena_estudio):
    clip = gen.make_clip(
        salida / "estudio.mov",
        [escena_estudio.image, escena_estudio.image * 1.02, escena_estudio.image * 0.98],
        fps=25,
    )
    a = analizar_clip(clip, n_fotogramas=3, guardar_pixeles=True, max_pixeles=1000)
    assert a.clip_id == "estudio"
    assert a.path == str(clip)
    assert (a.width, a.height) == (640, 360)
    assert a.frame_count == 3 and a.sampled_frames == 3
    assert a.fingerprint.shape == (96,)
    assert a.pixels is not None and a.pixels.shape == (1000, 3)
    assert a.pixels.dtype == np.float32
    assert a.stats.n_samples == 3 * 640 * 360
    assert a.source_space == "rec709", "sin metadatos de color se asume rec709"


def test_clip_id_por_defecto_y_a_mano(salida):
    clip = _clip_escalera(salida, 3)
    assert analizar_clip(clip, n_fotogramas=1).clip_id == "escalera3"
    assert analizar_clip(clip, n_fotogramas=1, clip_id="A003_C012").clip_id == "A003_C012"


def test_dos_analisis_del_mismo_clip_dan_lo_mismo(salida):
    clip = _clip_escalera(salida, 6)
    a = analizar_clip(clip, n_fotogramas=3, guardar_pixeles=True, max_pixeles=500)
    b = analizar_clip(clip, n_fotogramas=3, guardar_pixeles=True, max_pixeles=500)
    assert np.array_equal(a.fingerprint, b.fingerprint)
    assert np.array_equal(a.pixels, b.pixels)
    assert np.allclose(a.stats.mean, b.stats.mean)


@pytest.mark.lento
def test_h264_con_perdida_tambien_se_lee(salida, escena_estudio):
    """El camino con perdida tiene que funcionar, aunque los numeros bailen."""
    clip = gen.make_clip(
        salida / "h264.mp4", [escena_estudio.image] * 4, fps=25, codec="h264"
    )
    a = analizar_clip(clip, n_fotogramas=2)
    assert a.sampled_frames == 2
    assert a.stats.skin_locus is not None, "con h264 se sigue viendo la piel"
