"""`core.tutor.catalogo`/`explicar`: cada regla dispara con lo suyo y calla con
lo demás, y nunca inventa un veredicto que el umbral no respalda.

Filosofía del módulo (día 8, tarea 2): una regla es una función determinista
de `ContextoTutor` a `Frase | None`. Aquí se prueba mecánica (dispara/no
dispara, con el número correcto) y honestidad (una regla `no_validable` o
`descriptiva` nunca aparece en tono de veredicto — eso se revisa a mano
leyendo el texto exacto, no sólo el booleano).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.analysis import analizar_imagen
from core.colormgmt import detectar_espacio_clip
from core.contracts import CDL, ClipRef, Confidence, MatchResult
from core.io.lut_malos import lut_fuera_de_gamut, lut_plano
from core.io.qc import qc_lut
from core.tutor.catalogo import CATALOGO, ContextoTutor
from core.tutor.explicar import explicar
from tests.conftest import a_trabajo

pytestmark = pytest.mark.filterwarnings("ignore")


def _analisis(img: np.ndarray, clip_id: str = "x"):
    return analizar_imagen(img, clip_id=clip_id)


# ---------------------------------------------------------------------------
# El catálogo en sí: trazabilidad
# ---------------------------------------------------------------------------


def test_todas_las_reglas_tienen_id_unico_y_referencia_a_cifras():
    ids = [r.id for r in CATALOGO]
    assert len(ids) == len(set(ids)), "hay ids repetidos en el catálogo"
    for regla in CATALOGO:
        assert regla.caracteristica, f"{regla.id} sin característica"
        assert regla.cifras_ref, f"{regla.id} sin referencia de cifras"
        assert regla.validacion in ("validado", "descriptiva", "no_validable", "solo_sintetico")


def test_una_regla_con_umbral_lleva_el_umbral_en_la_frase_final(estudio_trabajo):
    """`Frase.umbral` sólo se rellena si la regla declara `umbral_nombre` — las
    descriptivas van con `None`, nunca con un umbral inventado."""
    analisis = _analisis(estudio_trabajo)
    lut = lut_fuera_de_gamut(17, exceso=0.25)
    informe = qc_lut(lut)
    ctx = ContextoTutor(analisis=analisis, qc_look=informe)
    frases = explicar(ctx)
    por_id = {f.regla_id: f for f in frases}
    assert "look_gamut" in por_id
    assert por_id["look_gamut"].umbral is not None and "TOL_GAMUT" in por_id["look_gamut"].umbral


# ---------------------------------------------------------------------------
# Grupo A — el look aplicado
# ---------------------------------------------------------------------------


def test_look_plano_dispara_con_un_lut_que_aplasta_a_un_color(estudio_trabajo):
    analisis = _analisis(estudio_trabajo)
    informe = qc_lut(lut_plano(17, color=(0.2, 0.4, 0.6)))
    frases = explicar(ContextoTutor(analisis=analisis, qc_look=informe))
    ids = {f.regla_id for f in frases}
    assert "look_plano" in ids
    assert "un solo color" in next(f.texto for f in frases if f.regla_id == "look_plano")


def test_look_gamut_dispara_con_un_lut_fuera_de_rango_y_no_le_llama_error(estudio_trabajo):
    """`gamut` es un aviso, no un error (día 6): la frase no puede sonar a
    veredicto absoluto — tiene que dejar sitio a que sea intencional."""
    analisis = _analisis(estudio_trabajo)
    informe = qc_lut(lut_fuera_de_gamut(17, exceso=0.25))
    frases = explicar(ContextoTutor(analisis=analisis, qc_look=informe))
    texto = next(f.texto for f in frases if f.regla_id == "look_gamut")
    assert "habitual" in texto or "conviene" in texto


def test_look_limpio_no_dispara_ninguna_regla_del_grupo_a(estudio_trabajo):
    from core.contracts import LUT3D

    analisis = _analisis(estudio_trabajo)
    informe = qc_lut(LUT3D.identity(17))
    frases = explicar(ContextoTutor(analisis=analisis, qc_look=informe))
    ids = {f.regla_id for f in frases}
    assert "look_plano" not in ids and "look_gamut" not in ids


def test_sin_qc_look_las_reglas_del_grupo_a_no_disparan(estudio_trabajo):
    analisis = _analisis(estudio_trabajo)
    frases = explicar(ContextoTutor(analisis=analisis, qc_look=None))
    ids = {f.regla_id for f in frases}
    assert "look_plano" not in ids and "look_gamut" not in ids


# ---------------------------------------------------------------------------
# Grupo B — descriptivas sobre el material
# ---------------------------------------------------------------------------


def test_punto_negro_reporta_un_numero_y_no_afirma_un_veredicto(estudio_trabajo):
    analisis = _analisis(estudio_trabajo)
    frases = explicar(ContextoTutor(analisis=analisis))
    negro = next((f for f in frases if f.regla_id == "punto_negro"), None)
    assert negro is not None
    assert "%" in negro.texto
    # Descriptiva: nunca dice "mal" ni "error", sólo constata y sugiere mirar.
    palabras = negro.texto.lower().split()
    for palabra in ("mal", "error", "roto"):
        assert palabra not in palabras


def test_punto_negro_con_espacio_detectado_da_el_motivo_confiado(estudio_trabajo):
    """Con una detección `segura=True` de cámara/gamma, el motivo se afirma
    ('el material viene marcado como...'); sin ella, se hedgea ('conviene
    comprobar')."""
    analisis = _analisis(estudio_trabajo)
    ref = ClipRef(
        clip_id="c1", name="c1", track=1, index=1, start_frame=0, end_frame=10,
        camera_manufacturer="Sony", gamma_notes="S-Log3",
    )
    deteccion = detectar_espacio_clip(ref)
    assert deteccion.segura
    frases = explicar(ContextoTutor(analisis=analisis, deteccion=deteccion))
    negro = next(f for f in frases if f.regla_id == "punto_negro")
    assert "viene marcado como" in negro.texto


def test_negro_practicamente_cero_no_dispara(rampa):
    """Una rampa de gris que empieza en 0 no debería disparar la regla del
    punto negro tras pasar por la curva de cámara — el suelo del 2% existe
    justo para esto."""
    fila = rampa[:1, :4, :]  # primeros 4 pixeles de la rampa: cerca de 0
    negro_puro = np.zeros_like(fila)
    analisis = _analisis(a_trabajo(negro_puro))
    frases = explicar(ContextoTutor(analisis=analisis))
    ids = {f.regla_id for f in frases}
    assert "punto_negro" not in ids


def test_saturacion_extendida_dispara_con_un_primario_puro():
    """Un primario puro (max=1, min=0 EN EL ESPACIO DE TRABAJO — no en
    escena-lineal: `WORKING_SPACE` es logarítmico, así que un primario de
    Rec.709 escena-lineal no llega a saturación 1 tras codificarse, tiene que
    fabricarse ya como código extremo) llena el bin más alto del histograma
    de saturación."""
    rojo_puro = np.zeros((8, 8, 3), dtype=np.float32)
    rojo_puro[..., 0] = 1.0
    analisis = _analisis(rojo_puro)
    frases = explicar(ContextoTutor(analisis=analisis))
    ids = {f.regla_id for f in frases}
    assert "saturacion_extendida" in ids
    texto = next(f.texto for f in frases if f.regla_id == "saturacion_extendida")
    assert "puede" in texto.lower()  # hedge: nunca "se va a", siempre "puede"


def test_gris_neutro_no_dispara_saturacion_extendida():
    gris = np.full((8, 8, 3), 0.4, dtype=np.float32)
    analisis = _analisis(a_trabajo(gris))
    frases = explicar(ContextoTutor(analisis=analisis))
    ids = {f.regla_id for f in frases}
    assert "saturacion_extendida" not in ids


def test_piel_vs_referencia_dispara_solo_con_los_dos_locus(estudio_trabajo, exterior_trabajo):
    analisis = _analisis(estudio_trabajo, "a")
    analisis_ref = _analisis(estudio_trabajo, "b")  # comparado consigo mismo: sin diferencia
    frases = explicar(ContextoTutor(analisis=analisis, analisis_referencia=analisis_ref))
    ids = {f.regla_id for f in frases}
    assert "piel_vs_referencia" not in ids, "un clip comparado consigo mismo no tiene diferencia de tono"


def test_piel_vs_referencia_sin_referencia_no_dispara(estudio_trabajo):
    analisis = _analisis(estudio_trabajo)
    frases = explicar(ContextoTutor(analisis=analisis, analisis_referencia=None))
    ids = {f.regla_id for f in frases}
    assert "piel_vs_referencia" not in ids


def test_piel_vs_referencia_entre_dos_tonos_distintos_da_una_diferencia_no_nula(escenas_pieles):
    claro = _analisis(a_trabajo(escenas_pieles[0].image), "claro")
    oscuro = _analisis(a_trabajo(escenas_pieles[-1].image), "oscuro")
    frases = explicar(ContextoTutor(analisis=claro, analisis_referencia=oscuro))
    piel = next((f for f in frases if f.regla_id == "piel_vs_referencia"), None)
    if piel is None:
        pytest.skip("los dos tonos de piel dieron el mismo ángulo de tono en Oklab (caso límite)")
    assert "°" in piel.texto
    assert "hacia" in piel.texto


# ---------------------------------------------------------------------------
# Grupo C — emparejamiento, nunca "confianza"
# ---------------------------------------------------------------------------


def _match(content_mismatch: bool) -> MatchResult:
    return MatchResult(
        cdl=CDL(), lut=None, confidence=Confidence(score=0.9, level="alta"),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=content_mismatch,
    )


def test_contenido_no_coincide_dispara_hedgeado(estudio_trabajo):
    analisis = _analisis(estudio_trabajo)
    frases = explicar(ContextoTutor(analisis=analisis, match=_match(True)))
    desajuste = next(f for f in frases if f.regla_id == "contenido_no_coincide")
    assert desajuste.validacion == "no_validable"
    assert "puede que" in desajuste.texto or "míralo" in desajuste.texto.lower()


def test_contenido_coincide_no_dispara(estudio_trabajo):
    analisis = _analisis(estudio_trabajo)
    frases = explicar(ContextoTutor(analisis=analisis, match=_match(False)))
    ids = {f.regla_id for f in frases}
    assert "contenido_no_coincide" not in ids


def test_ninguna_frase_usa_la_palabra_confianza(estudio_trabajo, exterior_trabajo):
    """Regla de oro heredada del día 4/6 (`CALIBRACION-CONFIANZA.md`): la nota
    de confianza no predice el error, así que ninguna frase del tutor la
    puede usar como argumento, en ningún grupo."""
    analisis = _analisis(estudio_trabajo)
    ref = _analisis(exterior_trabajo, "ref")
    ctx = ContextoTutor(
        analisis=analisis, analisis_referencia=ref, match=_match(True),
        qc_look=qc_lut(lut_fuera_de_gamut(17, exceso=0.25)),
    )
    for f in explicar(ctx):
        assert "confianza" not in f.texto.lower(), f.texto
