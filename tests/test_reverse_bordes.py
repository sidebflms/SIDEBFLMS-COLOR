"""Los bordes de `core.reverse`: lo que llega cuando no llega lo que se esperaba.

De extremo a extremo ya prueba `tests/test_entregables.py` (T1 y T2). Aqui estan
los casos que **no** son el camino feliz y que, si revientan, revientan en casa
de Mario a las tres de la mañana:

* una pareja de **un solo fotograma**, y el caso degenerado de una imagen de 1 px;
* el coloreado **reencuadrado a vertical**;
* el coloreado **a otra resolucion**;
* original y coloreado que **no se corresponden**;
* zonas del cubo **sin una sola muestra** (que es casi todo: un plano cubre el
  0.46% de un cubo de 33³);
* **altas luces recortadas** en el coloreado;
* **NaN** y valores fuera de rango.

LA REGLA QUE SE COMPRUEBA EN TODOS
----------------------------------
`invertir_grado` **no lanza** por material raro: devuelve un `ReverseResult`
completo, con un LUT que se puede escribir, y **lo dice** en las notas y en la
confianza. Devolver un LUT basura con buena cara es el unico fallo de verdad
grave de este modulo, porque es el que nadie detecta hasta que el `.cube` esta
en el ordenador del cliente.

MATERIAL Y ESCRITURAS
---------------------
Todo el material sale de `tests/media/generate.py`. Lo unico que se escribe son
los clips de los dos tests marcados con `requiere_ffmpeg`, y va en el `tmp_path`
de pytest.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import to_working
from core.contracts import CDL, LUT3D, LUT_SIZE_DEFAULT
from core.io import qc_lut
from core.reverse import MUESTRAS_MINIMAS_CDL, alinear, invertir_grado
from tests.conftest import requiere_ffmpeg
from tests.media import generate as gen

CDL_CONOCIDO = CDL(
    slope=(1.06, 1.00, 0.94),
    offset=(0.012, 0.000, -0.008),
    power=(0.96, 1.00, 1.04),
    saturation=1.12,
)


def _lut_de_look(size: int = LUT_SIZE_DEFAULT) -> LUT3D:
    t = LUT3D.identity(size).table.astype(np.float64)
    r, g, b = t[..., 0], t[..., 1], t[..., 2]

    def curva(x: np.ndarray) -> np.ndarray:
        return np.clip(x + 0.12 * np.sin(np.pi * np.clip(x, 0, 1)) * (x - 0.5) * 2, 0, 1)

    return LUT3D(
        table=np.clip(
            np.stack([curva(r) * 1.02, curva(g), curva(b) * 0.98 + 0.03 * (1 - np.clip(b, 0, 1))],
                     -1),
            0, 1,
        ).astype(np.float32),
        title="look",
    )


def _coloreado(original: np.ndarray) -> np.ndarray:
    return _lut_de_look().apply(CDL_CONOCIDO.apply(original)).astype(np.float32)


@pytest.fixture(scope="module")
def pequeno() -> np.ndarray:
    """El retrato de estudio a 256x144, en espacio de trabajo.

    A tamano completo cada `invertir_grado` son 60 iteraciones de Jacobi sobre
    230.400 pixeles y este archivo tiene una docena de casos. A 256x144 se mide
    lo mismo (que no reviente y que lo diga) en una fraccion del tiempo. Las
    cifras de calidad, que si dependen del tamano, se miden en los entregables.
    """
    escena = gen.studio_scene(width=256, height=144, skin_tone_index=2).image
    return to_working(escena, "linear_rec709")


def _es_resultado_completo(res) -> None:
    """Todo `ReverseResult` tiene que traer esto, venga lo que venga."""
    assert res.cdl is not None
    assert res.lut is not None
    assert np.isfinite(res.lut.table).all(), "el LUT trae NaN o infinito"
    assert res.lut.table.shape == (res.lut.size,) * 3 + (3,)
    assert res.coverage is not None
    assert res.diagnosis is not None
    assert 0.0 <= res.confidence.score <= 1.0
    assert res.confidence.level in ("alta", "media", "baja")
    assert res.notes, "no dice ni una palabra de lo que ha hecho"
    informe = qc_lut(res.lut)
    assert not informe.hay_errores, f"el LUT no se puede ni escribir: {informe.resumen()}"


# ---------------------------------------------------------------------------
# Un solo fotograma
# ---------------------------------------------------------------------------


@requiere_ffmpeg
def test_un_clip_de_un_solo_fotograma_se_puede_invertir(pequeno, tmp_path):
    """Un plano de un fotograma es un plano. Sale de un clip de verdad, no de
    memoria, porque el camino que se prueba es el que usara la GUI."""
    from core.analysis import extraer_fotogramas
    from core.color import from_working

    original_lineal = from_working(pequeno, "linear_rec709")
    coloreado = _coloreado(pequeno)
    col_lineal = from_working(coloreado, "linear_rec709")

    ruta_a = gen.make_clip(tmp_path / "original.mov", [original_lineal], codec="prores")
    ruta_b = gen.make_clip(tmp_path / "coloreado.mov", [col_lineal], codec="prores")

    a = extraer_fotogramas(ruta_a, n_fotogramas=8)
    b = extraer_fotogramas(ruta_b, n_fotogramas=8)
    assert a.shape[0] == 1, f"el clip de un fotograma ha dado {a.shape[0]}"
    assert b.shape[0] == 1

    res = invertir_grado(a[0], b[0])
    _es_resultado_completo(res)
    print(
        f"\n[1-fotograma] dE medio={res.delta_e_mean:.3f} p95={res.delta_e_p95:.3f} "
        f"confianza={res.confidence.score:.3f}"
    )
    # Es material de 8/10 bits pasado por ProRes: no se le pide exactitud, se le
    # pide que el grado que salga se parezca al que entro.
    assert res.delta_e_mean < 3.0


def test_una_imagen_de_un_solo_pixel_no_revienta():
    """El caso degenerado de verdad. Con un pixel no hay CDL que ajustar (hacen
    falta `MUESTRAS_MINIMAS_CDL`), no hay desplazamiento que estimar y no hay
    cubo que rellenar. Tiene que salir la identidad y tiene que decirlo."""
    a = np.full((1, 1, 3), 0.18, dtype=np.float32)
    b = np.full((1, 1, 3), 0.36, dtype=np.float32)
    res = invertir_grado(a, b)
    _es_resultado_completo(res)
    texto = " ".join(res.notes).lower()
    print(f"\n[1-pixel] confianza={res.confidence.score:.3f} notas={len(res.notes)}")
    assert res.cdl.is_identity(tol=1e-9), (
        f"ajusta diez parametros con un pixel: {res.cdl}"
    )
    assert str(MUESTRAS_MINIMAS_CDL) in texto or "pixeles validos" in texto, (
        f"no explica por que no ajusta el CDL: {res.notes}"
    )
    assert res.confidence.level == "baja", "confianza no baja con un solo pixel"


def test_una_imagen_de_un_solo_color_hunde_la_confianza(pequeno):
    """Sin volumen de color no hay cubo que rellenar, y eso NO es un grado
    fiable aunque el ΔE salga perfecto. Es lo que mide el numero de condicion."""
    a = np.full((64, 64, 3), 0.18, dtype=np.float32)
    b = np.full((64, 64, 3), 0.30, dtype=np.float32)
    res = invertir_grado(a, b)
    _es_resultado_completo(res)
    print(f"\n[1-color] confianza={res.confidence.score:.3f} nivel={res.confidence.level}")
    assert res.confidence.level != "alta", (
        "dice confianza alta sobre un plano de un solo color"
    )


# ---------------------------------------------------------------------------
# Reencuadre y resolucion
# ---------------------------------------------------------------------------


def test_el_coloreado_reencuadrado_a_vertical_no_revienta_y_avisa(pequeno):
    """Alguien entrega el plano recortado a vertical para redes. No son el
    mismo encuadre y el emparejamiento pixel a pixel deja de valer.

    Lo que se exige NO es acertar el grado: es **no fingir que se ha acertado**.
    """
    coloreado = _coloreado(pequeno)
    h, w = coloreado.shape[:2]
    # Recorte central vertical 9:16 sobre el coloreado: misma escena, otro marco.
    ancho_v = max(int(h * 9 / 16), 8)
    x0 = (w - ancho_v) // 2
    vertical = np.ascontiguousarray(coloreado[:, x0 : x0 + ancho_v])
    assert vertical.shape[0] > vertical.shape[1], "el recorte no ha salido vertical"

    a, b, info = alinear(pequeno, vertical)
    assert a.shape == b.shape, "alinear deja las dos con formas distintas"
    assert info["escalado"], "no dice que ha tenido que reescalar"

    res = invertir_grado(pequeno, vertical)
    _es_resultado_completo(res)
    texto = " ".join(res.notes).lower()
    print(
        f"\n[vertical] dE medio={res.delta_e_mean:.3f} confianza={res.confidence.score:.3f} "
        f"nivel={res.confidence.level}"
    )
    assert "tamanos distintos" in texto or "reescalado" in texto, (
        f"no avisa del reencuadre: {res.notes}"
    )
    assert res.confidence.level != "alta", (
        "dice confianza alta sobre un plano reencuadrado a vertical"
    )


def test_el_coloreado_a_otra_resolucion_se_reescala_a_la_pequena(pequeno):
    """Mismo encuadre, otra resolucion: esto SI se puede resolver, y bien.

    Se reescala a la mas pequena a proposito (subir de resolucion inventa
    detalle, y el detalle inventado acaba dentro del LUT como si fuera medida),
    y eso hay que comprobarlo, no suponerlo.
    """
    from core.reverse import redimensionar

    coloreado = _coloreado(pequeno)
    h, w = coloreado.shape[:2]
    mitad = redimensionar(coloreado, h // 2, w // 2)

    a, b, info = alinear(pequeno, mitad)
    assert a.shape[:2] == (h // 2, w // 2), (
        f"ha reescalado a {a.shape[:2]} en vez de a la mas pequena {(h // 2, w // 2)}"
    )

    res = invertir_grado(pequeno, mitad)
    _es_resultado_completo(res)
    m = res.confidence.metrics
    print(
        f"\n[media-res] dE medio={res.delta_e_mean:.3f} cubierto="
        f"{m.get('de_medio_cubierto', float('nan')):.3f} confianza={res.confidence.score:.3f}"
    )
    # El remuestreo suaviza, asi que el residuo sube; pero el grado sigue ahi.
    assert res.delta_e_mean < 3.0, f"pierde el grado al reescalar: {res.delta_e_mean:.3f}"


# ---------------------------------------------------------------------------
# Dos planos que no son el mismo
# ---------------------------------------------------------------------------


def test_dos_planos_que_no_se_corresponden_fallan_limpio_y_lo_dicen(
    estudio_trabajo, exterior_trabajo
):
    """Un retrato de estudio contra un exterior. No hay grado que los una.

    Tiene que: no lanzar, devolver confianza baja, **decirlo en las notas con
    todas las letras**, y que el aviso llegue tambien a `confidence.reasons`,
    que es lo que la GUI pinta.
    """
    res = invertir_grado(estudio_trabajo, exterior_trabajo)
    _es_resultado_completo(res)
    texto = " ".join(res.notes).lower()
    razones = " ".join(res.confidence.reasons).lower()
    print(
        f"\n[planos-distintos] dE medio={res.delta_e_mean:.3f} "
        f"confianza={res.confidence.score:.3f} nivel={res.confidence.level}"
    )
    assert res.confidence.level == "baja", (
        f"confianza {res.confidence.level} sobre dos planos que no tienen nada que ver"
    )
    assert "no parecen la misma escena" in texto or "mismo encuadre" in texto, (
        f"no dice que no se correspondan: {res.notes}"
    )
    assert razones.strip(), "no da ni una razon en la confianza"
    assert res.delta_e_mean > 5.0, (
        f"un residuo de {res.delta_e_mean:.2f} dE2000 con dos escenas distintas es sospechoso: "
        f"o el LUT se ha inventado un grado o el test no mide lo que cree"
    )


def test_un_desencuadre_grande_no_se_corrige_y_se_avisa(pequeno):
    """Por encima de `MAX_DESPLAZAMIENTO_PX` no se desplaza nada: a esa
    distancia lo mas probable es que no sean el mismo plano, y mover 200 px una
    imagen para que «encaje» es como se fabrica un resultado bonito y falso."""
    from core.reverse import MAX_DESPLAZAMIENTO_PX

    coloreado = _coloreado(pequeno)
    corrido = np.roll(coloreado, MAX_DESPLAZAMIENTO_PX * 2 + 5, axis=1)
    _, _, info = alinear(pequeno, corrido)
    print(f"\n[desencuadre] detectado={info['desplazamiento_detectado']} corregido={info['corregido']}")
    if abs(info["desplazamiento_detectado"][1]) > MAX_DESPLAZAMIENTO_PX:
        assert not info["corregido"], "ha corregido un desplazamiento mayor que el maximo"
        assert any("no lo corrijo" in n.lower() for n in info["notas"]), info["notas"]


# ---------------------------------------------------------------------------
# El cubo casi vacio
# ---------------------------------------------------------------------------


def test_casi_todas_las_celdas_del_cubo_estan_inventadas(pequeno):
    """Un plano cubre una miseria del cubo, y el mapa de cobertura tiene que
    decir EXACTAMENTE cuales son las inventadas: las de `counts == 0`."""
    res = invertir_grado(pequeno, _coloreado(pequeno))
    cobertura = res.coverage
    n = cobertura.size
    sin_dato = np.asarray(cobertura.counts) == 0
    fraccion = float(sin_dato.sum()) / sin_dato.size
    print(
        f"\n[cubo-vacio] celdas sin UNA muestra: {int(sin_dato.sum())} de {n**3} "
        f"({fraccion * 100:.2f}%), fraccion cubierta={cobertura.coverage_fraction() * 100:.2f}%"
    )
    assert fraccion > 0.95, "este test deja de medir lo que dice si el plano cubriera el cubo"

    # Y aun asi el LUT esta entero, es finito y esta dentro de 0..1.
    assert np.isfinite(res.lut.table).all()
    assert res.lut.table.min() >= 0.0 and res.lut.table.max() <= 1.0

    # `covered_mask` es MAS estricta que "hay dato": es "hay dato suficiente".
    assert int(cobertura.covered_mask().sum()) <= int((~sin_dato).sum()), (
        "covered_mask marca mas celdas de las que han visto un pixel"
    )
    # Y la nota lo cuenta, con el numero.
    assert any("inventadas" in n.lower() for n in res.notes), res.notes


def test_un_plano_que_no_entra_en_el_cubo_da_LUT_identidad_y_lo_dice():
    """Todo el material por encima de 1.0 despues del CDL: ni un pixel cae
    dentro del dominio del LUT. El LUT tiene que salir identidad y decirlo, no
    salir inventado."""
    a = np.full((64, 64, 3), 40.0, dtype=np.float32)
    a += np.random.default_rng(7).normal(0, 0.5, a.shape).astype(np.float32)
    b = (a * 1.2).astype(np.float32)
    res = invertir_grado(a, b)
    _es_resultado_completo(res)
    texto = " ".join(res.notes).lower()
    print(f"\n[fuera-de-dominio] notas={res.notes[:3]}")
    assert "fuera" in texto or "sujeta al borde" in texto or "dominio" in texto, (
        f"no avisa de que el material se sale del dominio del LUT: {res.notes}"
    )


# ---------------------------------------------------------------------------
# Altas luces recortadas
# ---------------------------------------------------------------------------


def test_altas_luces_recortadas_en_el_coloreado(pequeno):
    """El coloreado llega con los blancos quemados (alguien lo entrego en 8 bits
    o lo revelo a saco). La informacion de arriba NO esta: el grado que salga es
    una media entre lo que pasaba y el tope.

    Lo que se exige es que **no se propague hacia abajo**: el grado tiene que
    seguir siendo bueno donde no hay recorte, y el modulo tiene que decir que
    arriba hay un problema.
    """
    ideal = _coloreado(pequeno)
    # El tope se saca de los propios datos (el percentil 85 del canal mas alto),
    # no de un numero a ojo: asi el test sigue quemando el 15% del plano aunque
    # alguien cambie la escena o el espacio de trabajo.
    tope = float(np.percentile(ideal.max(axis=2), 85))
    coloreado = np.clip(ideal, 0.0, tope).astype(np.float32)
    quemados = float((ideal.max(axis=2) > tope).mean())
    print(f"\n[recorte] tope={tope:.4f}")
    assert quemados > 0.05, f"el recorte apenas toca el {quemados * 100:.1f}% del plano"

    res = invertir_grado(pequeno, coloreado)
    _es_resultado_completo(res)

    # Donde NO hay recorte el grado tiene que seguir bien.
    luma_orig = ideal.max(axis=2)
    sanos = luma_orig <= tope * 0.9
    pred = res.lut.apply(res.cdl.apply(pequeno.astype(np.float64)))
    from core.color import delta_e2000

    de = np.asarray(delta_e2000(pred, coloreado.astype(np.float64)), dtype=np.float64)
    print(
        f"[recorte] quemado={quemados * 100:.1f}% dE medio global={res.delta_e_mean:.3f} "
        f"dE medio en la zona sana={float(de[sanos].mean()):.3f} "
        f"dE medio en la quemada={float(de[~sanos].mean()):.3f}"
    )
    assert float(de[sanos].mean()) < 2.0, (
        "el recorte de las altas luces contamina el grado en las zonas que no estan quemadas"
    )
    assert res.lut.table.max() <= 1.0


# ---------------------------------------------------------------------------
# NaN, infinitos y valores fuera de rango
# ---------------------------------------------------------------------------


def test_unos_pocos_NaN_se_descartan_y_se_cuentan(pequeno):
    """Los NaN se descartan (como en `core.matching`), no se propagan, y la
    fraccion descartada sale en las notas. Un grado con un NaN dentro no es un
    grado: lo que hay que mirar es que el LUT salga limpio."""
    coloreado = _coloreado(pequeno).copy()
    rng = np.random.default_rng(11)
    h, w = coloreado.shape[:2]
    filas = rng.integers(0, h, 200)
    cols = rng.integers(0, w, 200)
    coloreado[filas, cols, 0] = np.nan
    coloreado[filas[:50], cols[:50], 1] = np.inf

    res = invertir_grado(pequeno, coloreado)
    _es_resultado_completo(res)
    texto = " ".join(res.notes).lower()
    print(f"\n[NaN] dE medio={res.delta_e_mean:.3f} confianza={res.confidence.score:.3f}")
    assert "nan" in texto or "infinito" in texto, f"no cuenta los NaN descartados: {res.notes}"
    assert np.isfinite(res.delta_e_mean), "el ΔE medio sale NaN por unos pocos pixeles malos"
    assert np.isfinite(np.asarray(res.diagnosis.spatial_residual)).any(), (
        "el mapa de residuo espacial sale entero a NaN"
    )


def test_todo_NaN_devuelve_la_identidad_con_confianza_cero(pequeno):
    """Sin un solo pixel valido no hay grado que recuperar, y hay que decirlo
    asi en vez de devolver algo con buena cara."""
    coloreado = np.full_like(pequeno, np.nan)
    res = invertir_grado(pequeno, coloreado)
    _es_resultado_completo(res)
    print(f"\n[todo-NaN] confianza={res.confidence.score:.3f} nivel={res.confidence.level}")
    assert res.cdl.is_identity(tol=1e-9)
    assert np.abs(res.lut.table - LUT3D.identity(res.lut.size).table).max() < 1e-6, (
        "devuelve un LUT inventado con una pareja que es toda NaN"
    )
    assert res.confidence.score == pytest.approx(0.0, abs=1e-6)
    assert res.diagnosis.lut_reproducible == 0.0
    assert res.diagnosis.spatial_residual is None
    assert not np.isfinite(res.delta_e_mean), "se inventa un ΔE medio sin un solo pixel valido"


def test_valores_fuera_de_rango_se_conservan_y_no_rompen_el_grado(pequeno):
    """El contrato dice que los valores fuera de 0..1 son **legales**: el
    material log y el sobreexpuesto los tienen. No se pueden recortar por el
    camino, y tampoco pueden reventar el ajuste."""
    original = pequeno.copy()
    original[:8, :8] = -0.25  # negativos legales de un log
    original[-8:, -8:] = 6.0  # un especular que se sale
    coloreado = _coloreado(original)

    res = invertir_grado(original, coloreado)
    _es_resultado_completo(res)
    texto = " ".join(res.notes).lower()
    print(
        f"\n[fuera-de-rango] dE medio={res.delta_e_mean:.3f} "
        f"fuera_de_dominio={res.confidence.metrics.get('fraccion_fuera_de_dominio', float('nan')):.4f}"
    )
    assert "dominio" in texto, f"no avisa del material fuera del dominio del LUT: {res.notes}"
    assert np.isfinite(res.delta_e_mean)


def test_el_original_en_negro_absoluto_no_divide_por_cero(pequeno):
    """Un plano entero a cero. El campo de ganancia va en logaritmos, asi que
    este es el caso que lo rompe si el suelo del logaritmo no esta puesto."""
    a = np.zeros((64, 64, 3), dtype=np.float32)
    b = np.zeros((64, 64, 3), dtype=np.float32)
    res = invertir_grado(a, b)
    _es_resultado_completo(res)
    print(f"\n[negro] dE medio={res.delta_e_mean:.4f} notas={len(res.notes)}")
    assert res.diagnosis.spatial_residual is None or np.isfinite(
        np.asarray(res.diagnosis.spatial_residual)
    ).all()
    assert res.diagnosis.hotspots == (), (
        f"ve geometria en dos planos negros: {[h.label for h in res.diagnosis.hotspots]}"
    )


def test_el_mismo_plano_dos_veces_no_inventa_geometria(pequeno):
    """Original y coloreado identicos: cero grado, y por tanto cero hotspots.
    Si el detector espacial ve algo aqui, ve ruido."""
    res = invertir_grado(pequeno, pequeno.copy())
    _es_resultado_completo(res)
    print(
        f"\n[identidad] dE medio={res.delta_e_mean:.4f} "
        f"etiquetas={[h.label for h in res.diagnosis.hotspots]}"
    )
    assert res.cdl.is_identity(tol=1e-3), f"se inventa un CDL: {res.cdl}"
    assert res.diagnosis.hotspots == (), "ve geometria donde no hay ni grado"
