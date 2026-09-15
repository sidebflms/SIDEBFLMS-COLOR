"""Oklab, CIE L*a*b*, CIEDE2000 y el locus de piel.

El ΔE2000 se verifica contra los datos de referencia de Sharma, Wu y Dalal
(2005), que son el estandar para validar una implementacion de CIEDE2000, y
ademas contra `colour.difference.delta_E_CIE2000` sobre pares aleatorios y
sobre los tonos dificiles de 275 grados.
"""

from __future__ import annotations

import colour
import numpy as np
import pytest

from core.color import (
    SKIN_OKLAB_LIMITES,
    delta_e2000,
    delta_e2000_lab,
    delta_e2000_mean,
    lab_to_xyz,
    log_encode,
    oklab_to_rgb,
    rgb_to_lab,
    rgb_to_oklab,
    skin_mask_oklab,
    xyz_to_lab,
)
from core.contracts import WORKING_SPACE
from tests.media import generate as gen

ESPACIOS_PRUEBA = ("linear_rec709", "rec709", "slog3_sgamut3cine", WORKING_SPACE)


# ---------------------------------------------------------------------------
# Oklab
# ---------------------------------------------------------------------------


def test_oklab_del_blanco_es_uno():
    """Oklab esta normalizado para que el blanco D65 tenga L = 1 y croma 0.

    La tolerancia es 2e-4 y no mas fina porque las matrices que publica
    Ottosson estan redondeadas a diez decimales; el residuo de 1.2e-4 en b es
    suyo, no nuestro. Aflojarla mas si taparia un error de verdad.
    """
    lab = rgb_to_oklab(np.ones((1, 3)), "linear_rec709")[0]
    assert lab[0] == pytest.approx(1.0, abs=2e-4)
    assert abs(lab[1]) < 2e-4
    assert abs(lab[2]) < 2e-4


def test_oklab_del_negro_es_cero():
    lab = rgb_to_oklab(np.zeros((1, 3)), "linear_rec709")[0]
    assert np.allclose(lab, 0.0, atol=1e-12)


@pytest.mark.parametrize("espacio", ESPACIOS_PRUEBA)
def test_oklab_ida_y_vuelta(espacio):
    rng = np.random.default_rng(21)
    img = rng.uniform(0.02, 0.9, (300, 3))
    vuelta = oklab_to_rgb(rgb_to_oklab(img, espacio), espacio)
    assert np.allclose(vuelta, img, rtol=1e-9, atol=1e-11)


def test_oklab_aguanta_fuera_de_gamut():
    """Un color imposible da LMS negativos. Con `x ** (1/3)` saldria NaN.

    Esto es lo que pasa de verdad con material log y con especulares: hay
    pixeles fuera del gamut del espacio. Tienen que seguir siendo numeros.
    """
    img = np.array([[-0.3, 1.4, -0.05], [2.0, -1.0, 0.5]])
    lab = rgb_to_oklab(img, "linear_rec709")
    assert np.all(np.isfinite(lab))
    assert np.allclose(oklab_to_rgb(lab, "linear_rec709"), img, rtol=1e-9, atol=1e-11)


def test_oklab_es_el_mismo_color_se_mire_desde_donde_se_mire():
    """Oklab es absoluto: el mismo color da el mismo Oklab venga del espacio que venga.

    Es la propiedad que hace que `skin_mask_oklab` funcione igual con material
    de Sony, de Lumix o ya convertido al espacio de trabajo. Si esto falla, es
    que `convert` mete un sesgo.
    """
    from core.color import convert

    rng = np.random.default_rng(23)
    lineal = rng.uniform(0.01, 1.5, (200, 3))
    referencia = rgb_to_oklab(lineal, "linear_rec709")
    for espacio in ("slog3_sgamut3cine", "vlog_vgamut", "dlog_dgamut", WORKING_SPACE):
        codificado = convert(lineal, "linear_rec709", espacio)
        assert np.allclose(rgb_to_oklab(codificado, espacio), referencia, atol=1e-9), espacio


def test_oklab_contra_colour():
    """colour trae Oklab. Misma definicion, otra implementacion."""
    rng = np.random.default_rng(27)
    lineal = rng.uniform(0.0, 1.0, (300, 3))
    xyz = colour.RGB_to_XYZ(lineal, colour.RGB_COLOURSPACES["ITU-R BT.709"], apply_cctf_decoding=False)
    suyo = colour.XYZ_to_Oklab(xyz)
    mio = rgb_to_oklab(lineal, "linear_rec709")
    assert np.allclose(mio, suyo, atol=1e-9)


# ---------------------------------------------------------------------------
# CIE L*a*b*
# ---------------------------------------------------------------------------


def test_lab_del_blanco_es_100_0_0():
    """Con blanco de referencia D65, el blanco tiene que dar L* = 100 clavado."""
    lab = rgb_to_lab(np.ones((1, 3)), "linear_rec709")[0]
    assert lab[0] == pytest.approx(100.0, abs=1e-10)
    assert abs(lab[1]) < 1e-10
    assert abs(lab[2]) < 1e-10


def test_lab_del_gris18_es_el_l_star_publicado():
    """Y = 0.18 da L* = 49.5 aproximadamente: el famoso "el 18% no es el 50%"."""
    lab = rgb_to_lab(np.full((1, 3), 0.18), "linear_rec709")[0]
    assert lab[0] == pytest.approx(49.496, abs=1e-3)


def test_lab_del_negro_exacto_es_cero_no_menos_dieciseis():
    """REGRESION (ronda 2, lo encontro el agente C). De los que vuelven.

    `_f_lab` extendia a negativos con `np.sign`, y `np.sign(0) == 0`, mientras
    que la rama lineal de la CIE vale 16/116 en el cero. Resultado: un negro
    EXACTO salia con L* = -16 en vez de L* = 0. Un salto de 16 unidades justo
    en el cero, y ΔE2000 entre dos negros indistinguibles daba 8.57.

    Un negro exacto no es un caso raro: sale de material recortado, de un fondo
    apagado y de cualquier `np.zeros` de prueba. Y ΔE2000 es la vara de medir de
    los cuatro tests entregables, asi que esto contaminaba medidas de otros
    modulos sin que se viera.
    """
    negro = np.zeros((1, 3))
    assert np.allclose(rgb_to_lab(negro, "linear_rec709"), 0.0, atol=1e-12)
    assert np.allclose(xyz_to_lab(np.zeros((1, 3))), 0.0, atol=1e-12)
    # Y no hay escalon: un negro exacto y un casi-negro son el mismo color.
    for epsilon in (1e-30, 1e-12, 1e-8):
        casi = np.full((1, 3), epsilon)
        assert float(delta_e2000(negro, casi, "linear_rec709")[0]) < 1e-3, epsilon
    assert float(delta_e2000(negro, np.full((1, 3), 1e-30), "linear_rec709")[0]) == 0.0


def test_no_hay_escalon_en_el_cero_en_ninguna_direccion():
    """Barre el cero por los dos lados, canal a canal.

    El bug original solo saltaba con el canal a cero EXACTO, asi que lo que hay
    que comprobar no es la diferencia entre muestras consecutivas (que crece
    sola al espaciar las muestras en escala logaritmica) sino que el valor EN el
    cero coincide con el limite por los dos lados.

    Se mide sobre los tres canales por separado, porque el material fuera de
    gamut llega con un solo canal negativo, no con los tres.

    La tolerancia de 1e-4 no es arbitraria: con el mayor epsilon del barrido
    (1e-9), la respuesta LEGITIMA de a* es 500 * kappa * 1e-9 / 116 / 0.9505 =
    4.3e-6, o sea que 1e-4 deja veinte veces de margen y sigue siendo cien mil
    veces mas pequena que el escalon de 16 unidades que producia el bug.
    """
    epsilons = 10.0 ** np.arange(-30.0, -8.0)
    for canal in range(3):
        cero = np.zeros((1, 3))
        en_cero = xyz_to_lab(cero)[0]
        for signo in (+1.0, -1.0):
            xyz = np.zeros((epsilons.size, 3))
            xyz[:, canal] = signo * epsilons
            lab = xyz_to_lab(xyz)
            assert np.all(np.isfinite(lab))
            salto = float(np.max(np.abs(lab - en_cero)))
            assert salto < 1e-4, f"canal {canal}, signo {signo:+.0f}: salto de {salto}"


def test_l_estrella_es_creciente_y_continua_cruzando_el_cero():
    """La luminosidad tiene que crecer sin saltos al pasar de Y negativo a Y positivo.

    Es la comprobacion que habria cazado el bug de la ronda 2 de una sola vez:
    con `np.sign`, L* daba -16 exactamente en Y = 0 y 0 a los dos lados, o sea
    un pozo de 16 unidades de ancho cero.
    """
    y = np.linspace(-0.02, 0.02, 40001)
    xyz = np.zeros((y.size, 3))
    xyz[:, 1] = y
    ele = xyz_to_lab(xyz)[:, 0]
    assert np.all(np.diff(ele) > 0.0), "L* no es estrictamente creciente en Y"
    # Sin saltos: el mayor escalon entre muestras contiguas es minusculo.
    assert float(np.max(np.abs(np.diff(ele)))) < 0.5


def test_el_cero_negativo_se_comporta_como_el_cero():
    """Variante taimada del bug de la ronda 2: en coma flotante hay un `-0.0`.

    Sale solo de multiplicar cualquier cosa por cero con signo, y con el
    `np.sign` viejo habria caido en la rama de los negativos. Tiene que ser
    indistinguible del cero por todos lados.
    """
    cero = np.zeros((1, 3))
    menos_cero = np.full((1, 3), -0.0)
    assert np.allclose(xyz_to_lab(menos_cero), 0.0, atol=1e-15)
    assert np.allclose(rgb_to_lab(menos_cero, "linear_rec709"), 0.0, atol=1e-15)
    assert np.allclose(rgb_to_oklab(menos_cero, "linear_rec709"), 0.0, atol=1e-15)
    assert float(delta_e2000(cero, menos_cero, "linear_rec709")[0]) == 0.0


def test_croma_cero_no_es_una_discontinuidad_disfrazada():
    """El convenio de Sharma (h' = 0 cuando C' = 0) NO mete un escalon.

    Es el otro sitio del modulo donde un cero exacto cambia de rama, asi que
    entra en la misma revision que `_f_lab`. Se compara contra colour porque es
    quien manda en el convenio.
    """
    gris = np.array([[50.0, 0.0, 0.0]])
    for delta in (1e-14, 1e-10, 1e-6):
        casi = np.array([[50.0, delta, 0.0]])
        mio = float(np.ravel(delta_e2000_lab(gris, casi))[0])
        suyo = float(np.ravel(colour.difference.delta_E_CIE2000(gris, casi))[0])
        assert mio == pytest.approx(suyo, abs=1e-12)
        assert mio < 1e-5


def test_lab_ida_y_vuelta_del_negro_exacto():
    """L* = 0 tiene que volver a XYZ = 0 clavado, no a -0.0018."""
    assert np.allclose(lab_to_xyz(np.zeros((1, 3))), 0.0, atol=1e-18)


def test_lab_contra_colour():
    rng = np.random.default_rng(31)
    lineal = rng.uniform(0.0, 1.2, (400, 3))
    xyz = colour.RGB_to_XYZ(lineal, colour.RGB_COLOURSPACES["ITU-R BT.709"], apply_cctf_decoding=False)
    suyo = colour.XYZ_to_Lab(xyz, colour.RGB_COLOURSPACES["ITU-R BT.709"].whitepoint)
    mio = rgb_to_lab(lineal, "linear_rec709")
    assert np.allclose(mio, suyo, atol=1e-9)


def test_lab_ida_y_vuelta_por_xyz():
    rng = np.random.default_rng(33)
    xyz = rng.uniform(0.0, 1.1, (300, 3))
    assert np.allclose(lab_to_xyz(xyz_to_lab(xyz)), xyz, rtol=1e-9, atol=1e-12)


def test_lab_contra_colour_en_el_cero_y_en_negativos():
    """El mismo juez, pero donde duele. Mismo criterio que en A-1.

    La CIE define su f() solo para t >= 0. Nosotros prolongamos la rama LINEAL a
    los negativos, que es lo que hace colour-science, en vez de espejar. Asi la
    comparacion con el juez independiente vale en todo el dominio y no solo en
    la mitad positiva.
    """
    xyz = np.array(
        [
            [0.0, 0.0, 0.0],
            [-0.2, 0.3, -0.01],
            [0.5, -0.1, 0.9],
            [-1.0, -1.0, -1.0],
            [1e-30, 0.0, -1e-30],
        ]
    )
    suyo = colour.XYZ_to_Lab(xyz, colour.RGB_COLOURSPACES["ITU-R BT.709"].whitepoint)
    assert np.allclose(xyz_to_lab(xyz), suyo, rtol=1e-12, atol=1e-10)


def test_lab_aguanta_xyz_negativo():
    """Fuera de gamut hay XYZ negativos. La f() de la CIE no los define; aqui se
    prolonga la rama lineal, que ya es monotona e invertible en los negativos."""
    xyz = np.array([[-0.2, 0.3, -0.01], [0.5, -0.1, 0.9]])
    lab = xyz_to_lab(xyz)
    assert np.all(np.isfinite(lab))
    assert np.allclose(lab_to_xyz(lab), xyz, rtol=1e-9, atol=1e-12)


# ---------------------------------------------------------------------------
# CIEDE2000: datos de referencia de Sharma, Wu y Dalal (2005)
# ---------------------------------------------------------------------------

#: Pares del conjunto de datos suplementario de Sharma, Wu y Dalal (2005),
#: "The CIEDE2000 Color-Difference Formula: Implementation Notes,
#: Supplementary Test Data, and Mathematical Observations".
#: Estan elegidos los que rompen implementaciones ingenuas: tonos a caballo de
#: 0/360 grados, croma cero, y el entorno de 275 grados.
SHARMA: tuple[tuple[tuple[float, float, float], tuple[float, float, float], float], ...] = (
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
)


@pytest.mark.parametrize("lab1,lab2,esperado", SHARMA)
def test_delta_e2000_contra_sharma(lab1, lab2, esperado):
    """Los valores publicados de Sharma tienen cuatro decimales: tolerancia 5e-5.

    Es la tolerancia que impone el dato, no una elegida para que pase. Si esto
    falla por 0.01, la implementacion esta mal en alguno de los tres sitios
    raros (croma cero, media de tonos, el pico de 275 grados).
    """
    mio = float(delta_e2000_lab(np.array(lab1), np.array(lab2)))
    assert mio == pytest.approx(esperado, abs=5e-5)


def test_delta_e2000_contra_colour_sobre_pares_aleatorios():
    """3000 pares al azar por todo el volumen de Lab, contra colour-science."""
    rng = np.random.default_rng(41)
    a = np.column_stack(
        [rng.uniform(0, 100, 3000), rng.uniform(-128, 128, 3000), rng.uniform(-128, 128, 3000)]
    )
    b = np.column_stack(
        [rng.uniform(0, 100, 3000), rng.uniform(-128, 128, 3000), rng.uniform(-128, 128, 3000)]
    )
    mio = delta_e2000_lab(a, b)
    suyo = colour.difference.delta_E_CIE2000(a, b)
    assert np.max(np.abs(mio - suyo)) < 1e-10


def test_delta_e2000_en_los_tonos_dificiles_de_275_grados():
    """El termino de rotacion RT tiene su pico en h = 275 grados.

    Es donde el ΔE2000 tiene sus discontinuidades famosas y donde mas de una
    implementacion se desvia. Aqui se barre ese entorno a proposito.
    """
    tonos = np.radians(np.linspace(255.0, 295.0, 801))
    croma = 50.0
    a = np.column_stack(
        [np.full(tonos.size, 50.0), croma * np.cos(tonos), croma * np.sin(tonos)]
    )
    b = a + np.array([0.0, 1.0, 1.0])
    mio = delta_e2000_lab(a, b)
    suyo = colour.difference.delta_E_CIE2000(a, b)
    assert np.max(np.abs(mio - suyo)) < 1e-10


def test_delta_e2000_con_croma_cero():
    """Dos grises: el tono no existe y hay que forzarlo a 0, no dividir por cero."""
    a = np.array([[50.0, 0.0, 0.0]])
    b = np.array([[60.0, 0.0, 0.0]])
    mio = delta_e2000_lab(a, b)
    assert np.all(np.isfinite(mio))
    assert mio == pytest.approx(colour.difference.delta_E_CIE2000(a, b), abs=1e-12)


def test_delta_e2000_de_un_color_consigo_mismo_es_cero():
    rng = np.random.default_rng(43)
    a = rng.uniform(-100, 100, (500, 3))
    a[:, 0] = rng.uniform(0, 100, 500)
    assert np.allclose(delta_e2000_lab(a, a), 0.0, atol=1e-12)


def test_delta_e2000_con_croma_gigante_no_desborda():
    """C^7 con C = 1e5 desbordaria si se calculara literalmente. Aqui no.

    Viene a cuento: el especular de `studio_scene` llega a 2.4 y el sol de
    `exterior_scene` a 9.0; en log y fuera de gamut salen cromas enormes.
    """
    a = np.array([[50.0, 1e5, -1e5]])
    b = np.array([[50.0, 0.0, 0.0]])
    assert np.all(np.isfinite(delta_e2000_lab(a, b)))


def test_delta_e2000_sobre_imagenes_quita_el_eje_de_canal():
    img = np.full((7, 5, 3), 0.4)
    assert delta_e2000(img, img, "linear_rec709").shape == (7, 5)


def test_delta_e2000_detecta_un_desplazamiento_real():
    """Subir una parada entera tiene que dar un ΔE claramente por encima de 1."""
    a = gen.studio_scene(skin_tone_index=2).image
    b = a * 2.0
    assert delta_e2000_mean(a, b, "linear_rec709") > 10.0


def test_delta_e2000_mean_devuelve_un_float():
    img = np.full((4, 4, 3), 0.3)
    v = delta_e2000_mean(img, img, "linear_rec709")
    assert isinstance(v, float)
    assert v == pytest.approx(0.0, abs=1e-12)


def test_delta_e2000_con_formas_incompatibles_lanza():
    with pytest.raises(ValueError, match="incompatibles"):
        delta_e2000_lab(np.zeros((4, 3)), np.zeros((7, 3)))


# ---------------------------------------------------------------------------
# Locus de piel
# ---------------------------------------------------------------------------

#: Precision y exhaustividad MEDIDAS contra la verdad de `studio_scene`, tono a
#: tono. No son objetivos: son lo que da hoy. Estan aqui como cota inferior
#: para que una "mejora" futura que empeore las pieles oscuras salte.
#: Los numeros de verdad, con su explicacion, estan en core/color/NOTAS.md.
PIEL_ESPERADO = {
    0: (0.75, 0.95),
    1: (0.65, 0.99),
    2: (0.64, 0.99),
    3: (0.65, 0.99),
    4: (0.70, 0.98),
    5: (0.80, 0.88),
}


@pytest.mark.parametrize("tono", sorted(PIEL_ESPERADO))
def test_skin_mask_funciona_con_los_seis_tonos(tono):
    """Los SEIS tonos, no solo los claros. Este es el test que importa.

    La exhaustividad baja del 100% al 90% en el tono mas oscuro: esta medido,
    esta en NOTAS.md y no se esconde. La precision se queda en 0.64-0.85 porque
    la mascara marca tambien el borde difuminado de la cara, que la verdad de
    `studio_scene` excluye (exige alpha > 0.55). Contra una verdad mas laxa
    (alpha > 0.2) la precision es ~0.95 en los seis.
    """
    escena = gen.studio_scene(skin_tone_index=tono)
    mascara = skin_mask_oklab(escena.image, "linear_rec709")
    verdad = escena.skin_mask
    aciertos = int((mascara & verdad).sum())
    precision = aciertos / max(int(mascara.sum()), 1)
    exhaustividad = aciertos / int(verdad.sum())
    min_p, min_r = PIEL_ESPERADO[tono]
    assert precision >= min_p, f"precision {precision:.3f} < {min_p}"
    assert exhaustividad >= min_r, f"exhaustividad {exhaustividad:.3f} < {min_r}"


def test_skin_mask_no_es_peor_en_las_pieles_oscuras_de_lo_que_decimos():
    """La pregunta de Mario: cuanto peor va con piel oscura. Respuesta medida.

    El umbral de croma es RELATIVO a L (C/L) justo por esto: con un umbral de
    croma absoluto, los tonos 4 y 5 se perderian enteros. Aun asi el tono 5
    pierde un 10% de la piel en las zonas mas en sombra.
    """
    exhaustividades = []
    for i in range(6):
        escena = gen.studio_scene(skin_tone_index=i)
        m = skin_mask_oklab(escena.image, "linear_rec709")
        exhaustividades.append(float((m & escena.skin_mask).sum() / escena.skin_mask.sum()))
    assert min(exhaustividades) > 0.85
    # El peor es el mas oscuro, y la caida respecto al mejor es menor de 0.15.
    assert exhaustividades.index(min(exhaustividades)) == 5
    assert max(exhaustividades) - min(exhaustividades) < 0.15


def test_skin_mask_no_ve_piel_donde_no_la_hay():
    """Rampa de gris: cero. Exterior sin gente: casi cero (el camino es terroso)."""
    assert skin_mask_oklab(gen.ramp_gray(), "linear_rec709").sum() == 0
    exterior = gen.exterior_scene()
    assert skin_mask_oklab(exterior.image, "linear_rec709").mean() < 0.03


def test_skin_mask_da_lo_mismo_desde_cualquier_espacio():
    """La mascara es una propiedad del COLOR, no de la codificacion.

    Si esto falla, o `convert` sesga o la mascara depende de la curva, y en los
    dos casos el emparejamiento de piel del agente C se va al garete.
    """
    escena = gen.studio_scene(skin_tone_index=4)
    desde_lineal = skin_mask_oklab(escena.image, "linear_rec709")
    for espacio in ("slog3_sgamut3cine", "vlog_vgamut", WORKING_SPACE):
        from core.color import convert

        codificado = convert(log_encode(escena.image, "linear_rec709"), "linear_rec709", espacio)
        otra = skin_mask_oklab(codificado, espacio)
        coincidencia = float((otra == desde_lineal).mean())
        assert coincidencia > 0.999, f"{espacio}: {coincidencia:.4f}"


def test_skin_mask_devuelve_bool_con_la_forma_de_la_imagen():
    escena = gen.studio_scene(skin_tone_index=2)
    m = skin_mask_oklab(escena.image, "linear_rec709")
    assert m.dtype == np.bool_
    assert m.shape == escena.image.shape[:2]


def test_skin_mask_rechaza_una_lista_de_pixeles():
    """Devuelve (alto, ancho): una lista (N, 3) no tiene esa forma. Mejor lanzar."""
    with pytest.raises(ValueError, match=r"\(alto, ancho, 3\)"):
        skin_mask_oklab(np.full((10, 3), 0.4), "linear_rec709")


def test_los_limites_del_locus_estan_documentados():
    """Si alguien toca los umbrales, que sepa que hay numeros medidos detras."""
    assert set(SKIN_OKLAB_LIMITES) == {
        "tono_min",
        "tono_max",
        "croma_rel_min",
        "croma_rel_max",
        "croma_abs_min",
        "l_min",
        "l_max",
    }
