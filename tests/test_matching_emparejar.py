"""Tests del emparejamiento completo (`emparejar` / `emparejar_analisis`)."""

from __future__ import annotations

import numpy as np
import pytest

from core.color import delta_e2000_mean
from core.contracts import (
    CDL,
    FINGERPRINT_LEN,
    LUT3D,
    LUT_SIZE_DEFAULT,
    LUT_SIZES_SOPORTADOS,
    PERCENTILE_LEVELS,
    SAT_BINS,
    ClipAnalysis,
    ColorStats,
    MatchResult,
)
from core.matching import (
    emparejar,
    emparejar_analisis,
    fraccion_extrapolada,
    solape_de_distribuciones,
)

GRADO = CDL(
    slope=(1.35, 0.85, 1.18), offset=(-0.06, 0.04, -0.09), power=(0.78, 1.22, 0.95), saturation=1.25
)


def pix(img) -> np.ndarray:
    return np.asarray(img, dtype=np.float64).reshape(-1, 3)


# ---------------------------------------------------------------------------
# Lo basico
# ---------------------------------------------------------------------------


def test_devuelve_un_matchresult_completo(estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar(GRADO.apply(px), px)
    assert isinstance(m, MatchResult)
    assert isinstance(m.cdl, CDL)
    assert m.lut is None
    assert np.isfinite(m.delta_e_before) and np.isfinite(m.delta_e_after)
    assert 0.0 <= m.confidence.score <= 1.0
    assert isinstance(m.content_mismatch, bool)
    assert all(isinstance(n, str) for n in m.notes)


def test_deshace_un_grado_conocido(estudio_trabajo):
    """El caso central: un plano con un grado encima vuelve al plano de al lado."""
    px = pix(estudio_trabajo)
    m = emparejar(GRADO.apply(px), px)
    assert m.delta_e_before > 5.0
    assert m.delta_e_after < 1.0
    assert m.content_mismatch is False
    assert m.confidence.level == "alta"
    # Y ademas el resultado se parece de verdad al original, pixel a pixel.
    assert delta_e2000_mean(m.cdl.apply(GRADO.apply(px)), px) < 2.0


def test_cuanto_se_pierde_por_no_tener_parejas_de_pixeles(estudio_trabajo):
    """El limite real del metodo, medido y escrito, para que nadie se confunda.

    `delta_e_after` mide la distancia al TRANSPORTE, no a la verdad. Y el
    transporte es afin, o sea que el techo de todo esto lo pone el propio MKL,
    no el ajuste a CDL. Cadena medida sobre el retrato de estudio con el grado
    `GRADO` encima (ΔE2000 medio contra el plano original):

        sin corregir ................................ 32.73
        con el transporte MKL ideal .................  1.66   <- el techo
        con el CDL que sale de `emparejar` ..........  1.72
        con el CDL + el LUT de residuo ..............  1.65
        con un CDL ajustado sobre PAREJAS de pixeles.  0.12

    O sea: el CDL solo pierde 0.06 respecto al transporte, y el LUT recupera
    esos 0.06. Los 1.65 que quedan son del modelo afin, y para bajarlos hay que
    tener las parejas (que es lo que hace el agente F con ingenieria inversa),
    no ajustar mejor el CDL.
    """
    from core.matching import ajustar_cdl, aplicar_mkl, transporte_mkl

    px = pix(estudio_trabajo)
    graduado = GRADO.apply(px)
    a, b = transporte_mkl(graduado, px)
    techo = delta_e2000_mean(aplicar_mkl(graduado, a, b), px)
    con_cdl = delta_e2000_mean(emparejar(graduado, px).cdl.apply(graduado), px)
    con_parejas = delta_e2000_mean(ajustar_cdl(graduado, px).apply(graduado), px)

    assert delta_e2000_mean(graduado, px) > 25.0
    assert 1.0 < techo < 2.5
    assert con_cdl < techo * 1.2
    assert con_parejas < techo / 5.0


def test_emparejar_un_plano_consigo_mismo_da_la_identidad(estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar(px, px)
    assert m.cdl.is_identity(tol=1e-6), m.cdl
    assert m.delta_e_before == pytest.approx(0.0, abs=1e-9)
    assert m.delta_e_after == pytest.approx(0.0, abs=1e-9)
    assert m.confidence.level == "alta"
    assert m.content_mismatch is False


def test_es_determinista(estudio_trabajo, exterior_trabajo):
    a, b = pix(estudio_trabajo), pix(exterior_trabajo)
    m1, m2 = emparejar(a, b), emparejar(a, b)
    assert m1.cdl == m2.cdl
    assert m1.delta_e_after == m2.delta_e_after
    assert m1.confidence.score == m2.confidence.score


def test_las_dos_listas_pueden_medir_distinto(estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar(GRADO.apply(px)[::5], px[::3])
    assert m.delta_e_after < 1.0
    assert m.confidence.level in ("alta", "media")


def test_acepta_imagenes_y_listas_indistintamente(estudio_trabajo):
    img = estudio_trabajo.astype(np.float64)
    m1 = emparejar(GRADO.apply(img), img)
    m2 = emparejar(GRADO.apply(img).reshape(-1, 3), img.reshape(-1, 3))
    assert m1.cdl == m2.cdl


def test_los_seis_tonos_de_piel_se_igualan_igual_de_bien(pieles_trabajo):
    """El emparejamiento no puede funcionar solo con pieles claras."""
    for i, piel in enumerate(pieles_trabajo):
        px = pix(piel)
        m = emparejar(GRADO.apply(px), px)
        assert m.delta_e_before > 5.0, i
        assert m.delta_e_after < 1.5, i
        assert m.content_mismatch is False, i
        assert m.confidence.level == "alta", (i, m.confidence.reasons)
        assert delta_e2000_mean(m.cdl.apply(GRADO.apply(px)), px) < 2.5, i


# ---------------------------------------------------------------------------
# Desajuste de contenido: que llegue al MatchResult
# ---------------------------------------------------------------------------


def test_estudio_contra_exterior_sale_marcado_aunque_el_numero_sea_bonito(
    estudio_trabajo, exterior_trabajo
):
    """Es lo que evita que la app 'iguale' dos planos que no tienen que ver."""
    m = emparejar(pix(estudio_trabajo), pix(exterior_trabajo))
    assert m.content_mismatch is True
    # El ΔE baja igual: por eso hace falta la bandera.
    assert m.delta_e_after < m.delta_e_before
    assert m.confidence.level == "baja"
    assert any("no parecen" in n for n in m.notes)
    assert "no parecen la misma escena" in m.confidence.reasons[0]


# ---------------------------------------------------------------------------
# LUT de residuo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tam", LUT_SIZES_SOPORTADOS)
def test_con_lut_devuelve_un_lut_del_tamano_pedido(tam, estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar(GRADO.apply(px), px, con_lut=True, tam_lut=tam)
    assert isinstance(m.lut, LUT3D)
    assert m.lut.size == tam


def test_el_lut_por_defecto_es_de_33(estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar(GRADO.apply(px), px, con_lut=True)
    assert m.lut.size == LUT_SIZE_DEFAULT


def test_el_lut_va_detras_del_cdl_y_no_lo_estropea(estudio_trabajo):
    """El LUT es el RESIDUO: se aplica despues del CDL. Aplicar los dos tiene
    que dejar el resultado al menos tan cerca como el CDL solo."""
    px = pix(estudio_trabajo)
    con = emparejar(GRADO.apply(px), px, con_lut=True)
    sin = emparejar(GRADO.apply(px), px, con_lut=False)
    assert con.delta_e_after <= sin.delta_e_after + 1e-9


def test_el_lut_de_un_emparejamiento_identidad_es_casi_la_identidad(estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar(px, px, con_lut=True)
    identidad = LUT3D.identity(m.lut.size)
    dentro = np.linspace(0.05, 0.95, 40)
    rejilla = np.stack(np.meshgrid(dentro, dentro, dentro, indexing="ij"), axis=-1).reshape(-1, 3)
    np.testing.assert_allclose(m.lut.apply(rejilla), identidad.apply(rejilla), atol=1e-5)


# ---------------------------------------------------------------------------
# Metricas sueltas
# ---------------------------------------------------------------------------


def test_extrapolacion_es_cero_contra_uno_mismo(estudio_trabajo):
    px = pix(estudio_trabajo)
    assert fraccion_extrapolada(px, px) == 0.0


def test_extrapolacion_cuenta_lo_que_se_sale():
    origen = np.zeros((100, 3))
    referencia = np.concatenate([np.zeros((50, 3)), np.ones((50, 3))])
    assert fraccion_extrapolada(origen, referencia) == pytest.approx(0.5)


def test_solape_de_un_plano_consigo_mismo_es_uno(estudio_trabajo):
    px = pix(estudio_trabajo)
    assert solape_de_distribuciones(px, px) == pytest.approx(1.0, abs=1e-9)


def test_solape_de_dos_nubes_ajenas_es_pequeno():
    a = np.zeros((5000, 3))
    b = np.ones((5000, 3))
    assert solape_de_distribuciones(a, b) < 0.1


def test_el_solape_se_mide_despues_del_transporte_y_por_eso_sirve(estudio_trabajo):
    """Un grado fuerte deja el solape EN CRUDO en casi cero, y ese es el caso
    normal del programa. Despues del transporte tiene que volver a ~1."""
    px = pix(estudio_trabajo)
    graduado = GRADO.apply(px)
    assert solape_de_distribuciones(graduado, px) < 0.2
    m = emparejar(graduado, px)
    assert m.confidence.metrics["solape"] > 0.9


# ---------------------------------------------------------------------------
# emparejar_analisis
# ---------------------------------------------------------------------------


def _stats_de(px: np.ndarray) -> ColorStats:
    """`ColorStats` a mano: el agente B esta escribiendo `core.analysis` a la vez
    que yo, asi que aqui no se importa nada suyo."""
    px = np.asarray(px, dtype=np.float64).reshape(-1, 3)
    croma = px.max(axis=1) - px.min(axis=1)
    hist, _ = np.histogram(croma, bins=SAT_BINS, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    hist /= max(hist.sum(), 1.0)
    perc = np.percentile(px, PERCENTILE_LEVELS, axis=0)
    return ColorStats(
        mean=px.mean(axis=0),
        std=px.std(axis=0),
        cov=np.cov(px, rowvar=False, ddof=1),
        percentiles=perc,
        black_point=perc[1],
        white_point=perc[-2],
        saturation_hist=hist,
        skin_locus=None,
        skin_fraction=0.0,
        n_samples=px.shape[0],
    )


def _analisis(px: np.ndarray, *, con_pixeles: bool = True, clip_id: str = "x") -> ClipAnalysis:
    px = np.asarray(px, dtype=np.float64).reshape(-1, 3)
    huella = np.full(FINGERPRINT_LEN, 1.0 / np.sqrt(FINGERPRINT_LEN), dtype=np.float32)
    return ClipAnalysis(
        clip_id=clip_id,
        path=f"/no/existe/{clip_id}.mov",
        stats=_stats_de(px),
        fingerprint=huella,
        width=640,
        height=360,
        frame_count=0,
        sampled_frames=1,
        source_space=None,
        pixels=px if con_pixeles else None,
    )


def test_emparejar_analisis_con_pixeles_da_lo_mismo_que_emparejar(estudio_trabajo):
    px = pix(estudio_trabajo)
    directo = emparejar(GRADO.apply(px), px)
    por_analisis = emparejar_analisis(_analisis(GRADO.apply(px), clip_id="a"), _analisis(px))
    assert por_analisis.cdl == directo.cdl


def test_emparejar_analisis_sin_pixeles_se_apoya_en_la_estadistica(estudio_trabajo):
    """Sin pixeles el CDL sale del modelo gaussiano, no del plano. Tiene que
    decirlo en las notas y seguir siendo util."""
    px = pix(estudio_trabajo)
    m = emparejar_analisis(
        _analisis(GRADO.apply(px), con_pixeles=False, clip_id="a"),
        _analisis(px, con_pixeles=False, clip_id="b"),
    )
    assert any("nube gaussiana" in n for n in m.notes)
    # Sobre los pixeles DE VERDAD, el CDL que sale del modelo sigue acercando.
    antes = delta_e2000_mean(GRADO.apply(px), px)
    despues = delta_e2000_mean(m.cdl.apply(GRADO.apply(px)), px)
    assert despues < antes / 3.0


def test_emparejar_analisis_usa_el_n_samples_de_verdad(estudio_trabajo):
    px = pix(estudio_trabajo)
    m = emparejar_analisis(
        _analisis(GRADO.apply(px), con_pixeles=False, clip_id="a"),
        _analisis(px, con_pixeles=False, clip_id="b"),
    )
    assert m.confidence.metrics["n_muestras"] == px.shape[0]


def test_emparejar_analisis_no_importa_core_analysis():
    """El contrato es lo unico que cruza la frontera: si `core.matching` empieza
    a importar `core.analysis`, los dos modulos dejan de poder escribirse a la
    vez."""
    import pathlib
    import sys

    assert sys is not None  # solo para que quede claro que no se importa nada de B
    carpeta = pathlib.Path(__file__).resolve().parents[1] / "core" / "matching"
    for archivo in sorted(carpeta.glob("*.py")):
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            pelada = linea.strip()
            if pelada.startswith(("import ", "from ")):
                assert "core.analysis" not in pelada, f"{archivo.name}:{numero}"
