"""REVISION OLA 1 - agente G sobre `core/color/` (agente A).

Estos tests NO estan escritos para confirmar que el modulo funciona. Estan
escritos para intentar romperlo. Los que quedan en ROJO son bugs encontrados y
no se arreglan aqui: el modulo no es mio.

Lo que se ataca, y por que:

* La afirmacion de `core/color/NOTAS.md` de que las SEIS curvas coinciden con
  `colour-science` con diferencia 0.0. El autor la comprueba sobre valores
  positivos; el contrato 1 dice que los negativos son legales y hay que
  preservarlos, asi que la comprobacion tiene que incluirlos.
* La politica de NaN "se propaga", en las CATORCE funciones publicas, no en dos.
* La promesa de dtype del docstring del modulo (float32 salvo float64).
* Los extremos de la ida y vuelta (-0.5 y 9.5 codificados).
* La discontinuidad de tono de 275 grados en dE2000.
* Imagen negra, imagen saturada, un canal entero a cero, formas degeneradas.
"""

from __future__ import annotations

import warnings

import colour
import numpy as np
import pytest

import core.color as C
from core.color.spaces import SPACES
from tests.media import generate as gen

CURVAS = tuple(n for n in SPACES if not SPACES[n].is_linear)

#: El juez independiente, espacio a espacio. Es la misma tabla que usa el autor
#: en `tests/test_color_transfer.py`; lo que cambia son LOS VALORES.
JUEZ = {
    "slog3_sgamut3cine": colour.models.log_encoding_SLog3,
    "vlog_vgamut": colour.models.log_encoding_VLog,
    "clog3_cinemagamut": colour.models.log_encoding_CanonLog3,
    "dlog_dgamut": colour.models.log_encoding_DJIDLog,
    "davinci_wg_intermediate": colour.models.oetf_DaVinciIntermediate,
    "rec709": colour.models.oetf_BT709,
    # RONDA 2: `srgb` es un espacio nuevo (lo pidio el agente B porque mapear
    # sRGB a Rec.709 daba +57% de error en las sombras). Entra al juez como los
    # demas: la EOTF inversa de sRGB, que es su OETF.
    "srgb": colour.models.eotf_inverse_sRGB,
}


# ---------------------------------------------------------------------------
# 1. El juez independiente, con MIS valores (negativos incluidos)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", sorted(JUEZ))
def test_curvas_coinciden_con_colour_science_tambien_en_negativos(espacio):
    """RONDA 2 — arreglado. Ahora coinciden en TODO el dominio, no solo en x>=0.

    En la ronda 1 esto estaba rojo para `rec709`: el modulo extendia la BT.709 a
    negativos por simetria impar (f(-x) = -f(x)) y `colour` prolonga el tramo
    lineal (4.5*x). En x = -0.05 eran 0.0385 de diferencia, ~39 codigos de 10
    bits. El test del autor barria `0.18 * 2**linspace(-6, 6)` mas 0.0, 0.18,
    0.9 y 1.0, o sea **todo positivo**, asi que no lo veia.

    A ha cambiado la extension a la de colour-science. **No exijo la tolerancia
    de 1e-10 que pedia antes: exijo CERO**, que es lo que el autor afirma en
    NOTAS.md y lo que mide este test sobre 4.000 muestras de -2.88 a +11.5
    (o sea de -4 paradas a +6 sobre el blanco).
    """
    x = np.concatenate(
        [
            np.linspace(-2.88, -1e-6, 2000),
            np.array([-0.5, -0.05, -0.018, -0.0031308, -1e-12, 0.0, 1e-12, 0.018, 0.18, 0.9, 1.0]),
            np.linspace(1e-6, 11.5, 2000),
        ]
    ).astype(np.float64)
    mio = C.log_encode(x, espacio)
    with np.errstate(invalid="ignore", over="ignore"):
        suyo = np.asarray(JUEZ[espacio](x), dtype=np.float64)
    diferencia = np.abs(mio - suyo)
    peor = float(np.nanmax(diferencia))
    donde = float(x[int(np.nanargmax(diferencia))])
    assert peor == 0.0, (
        f"{espacio}: maxima diferencia con colour-science = {peor:.4e} en x = {donde:g}. "
        f"NOTAS.md afirma 0.0e+00 en todo el dominio."
    )


@pytest.mark.parametrize("espacio", sorted(JUEZ))
def test_el_cambio_de_los_negativos_no_ha_roto_la_ida_y_vuelta(espacio):
    """Lo que habia que vigilar al cambiar la extension: que siga siendo invertible.

    Cambiar como se extiende una curva a negativos es facil que rompa la ida y
    vuelta, porque el umbral del decodificador tiene que moverse con ella. Se
    comprueba en los dos lados del corte y bien lejos, en los siete espacios.
    """
    valores = np.array([[-2.88, -1.0, -0.5], [-0.05, -0.018, 0.0], [0.018, 1.0, 9.5]])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        vuelta = C.log_encode(C.log_decode(valores, espacio), espacio)
    assert np.isfinite(vuelta).all()
    assert float(np.max(np.abs(vuelta - valores))) < 1e-9


# ---------------------------------------------------------------------------
# 2. NaN en las CATORCE funciones publicas, no en dos
# ---------------------------------------------------------------------------


def _funciones_publicas_con_array():
    """Las catorce entradas de `core.color.__all__` que reciben un array."""
    nan3 = np.array([[np.nan, 0.5, 0.5]], dtype=np.float64)
    imagen = np.full((2, 2, 3), np.nan, dtype=np.float32)
    lab = np.array([[50.0, 0.0, 0.0]], dtype=np.float64)
    return {
        "convert": lambda: C.convert(nan3, "rec709", "slog3_sgamut3cine"),
        "to_working": lambda: C.to_working(nan3, "linear_rec709"),
        "from_working": lambda: C.from_working(nan3, "rec709"),
        "log_encode": lambda: C.log_encode(nan3, "vlog_vgamut"),
        "log_decode": lambda: C.log_decode(nan3, "vlog_vgamut"),
        "rgb_to_oklab": lambda: C.rgb_to_oklab(nan3),
        "oklab_to_rgb": lambda: C.oklab_to_rgb(nan3),
        "rgb_to_lab": lambda: C.rgb_to_lab(nan3),
        "xyz_to_lab": lambda: C.xyz_to_lab(nan3),
        "lab_to_xyz": lambda: C.lab_to_xyz(nan3),
        "delta_e2000": lambda: C.delta_e2000(nan3, nan3),
        "delta_e2000_lab": lambda: C.delta_e2000_lab(nan3, lab),
        "delta_e2000_mean": lambda: np.array([C.delta_e2000_mean(nan3, nan3)]),
        "skin_mask_oklab": lambda: C.skin_mask_oklab(imagen),
    }


@pytest.mark.parametrize("nombre", sorted(_funciones_publicas_con_array()))
def test_el_nan_se_propaga_en_todas_las_publicas_no_solo_en_dos(nombre):
    """El autor dice que el NaN se propaga. Se comprueba una por una.

    La unica excepcion admitida es `skin_mask_oklab`, que devuelve bool: ahi un
    NaN tiene que salir False (no es piel), nunca True.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        salida = np.asarray(_funciones_publicas_con_array()[nombre]())
    if nombre == "skin_mask_oklab":
        assert salida.dtype == np.bool_
        assert not salida.any(), "un pixel NaN se ha marcado como piel"
        return
    assert np.isnan(salida).any(), f"{nombre} se ha comido el NaN en vez de propagarlo"


@pytest.mark.parametrize("canal", [0, 1, 2])
def test_un_nan_en_cualquier_canal_del_lab_ensucia_el_delta_e(canal):
    """No vale con que el NaN llegue por L*: a* y b* tienen que propagarlo igual.

    Es el camino que mas facil se rompe: `np.where` con una condicion que es
    False para NaN puede barrer el NaN sin que nadie se entere.
    """
    a = np.array([[50.0, 10.0, 10.0]])
    a[0, canal] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        assert np.isnan(C.delta_e2000_lab(a, np.array([[50.0, 0.0, 0.0]]))).all()


# ---------------------------------------------------------------------------
# 3. La promesa de dtype
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entrada", [np.uint8, np.int32, np.int64, np.uint16])
def test_convert_devuelve_el_MISMO_dtype_coincidan_o_no_los_espacios(entrada):
    """RONDA 2 — arreglado. El dtype ya no depende de si los espacios coinciden.

    En la ronda 1, `convert(x, X, X)` cortaba por lo sano con `arr.copy()` y
    devolvia el dtype de ENTRADA: una imagen uint8 (lo que le llega a la GUI de
    un PNG) salia uint8 por la rama de identidad y float32 por la otra. El que
    llamaba no podia saber que le iban a devolver sin mirar antes si los dos
    espacios eran el mismo, y un uint8 cruzando una frontera entre modulos es
    justo lo que prohibe el contrato 1.
    """
    x = np.zeros((2, 2, 3), dtype=entrada)
    assert C.convert(x, "rec709", "rec709").dtype == np.float32
    assert C.convert(x, "rec709", "linear_rec709").dtype == np.float32


@pytest.mark.parametrize("entrada", [bool, np.complex128])
def test_convert_valida_el_tipo_por_LAS_DOS_ramas(entrada):
    """RONDA 2 — arbitrado en mi contra, y el orquestador tiene razon.

    En la ronda 1 escribi dos tests que se contradecian: uno exigia float32 para
    un uint8 (correcto, es el contrato) y el otro daba por buena la conducta de
    devolver `bool` para un bool, que no era un requisito sino la fotografia de
    un defecto. Lo coherente es que `convert` valide el tipo por las dos ramas,
    y asi lo ha dejado A.
    """
    x = np.zeros((2, 2, 3), dtype=entrada)
    with pytest.raises(TypeError, match="(?i)numerico"):
        C.convert(x, "rec709", "linear_rec709")
    with pytest.raises(TypeError, match="(?i)numerico"):
        C.convert(x, "rec709", "rec709")


def test_convert_identidad_es_exacta_bit_a_bit_incluso_con_nan_e_infinitos():
    """Lo que el autor SI cumple: la identidad es una copia bit a bit."""
    x = np.array([[np.nan, np.inf, -np.inf], [0.18, -0.5, 9.5]], dtype=np.float32)
    assert C.convert(x, "slog3_sgamut3cine", "slog3_sgamut3cine").tobytes() == x.tobytes()


# ---------------------------------------------------------------------------
# 4. Los extremos de la ida y vuelta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("codificado", [-0.5, -0.1, 0.0, 3.0, 9.5, 20.0, 60.0])
@pytest.mark.parametrize("espacio", sorted(CURVAS))
def test_ida_y_vuelta_de_valores_codificados_absurdos(espacio, codificado):
    """Un -0.5 y un 9.5 codificados tienen que volver como entraron.

    El 9.5 en S-Log3 son 8.4e39 de escena-lineal, que NO cabe en float32: si
    algun paso intermedio bajara la precision, esto saldria infinito o NaN. Es
    justo el bug que el autor dice haber arreglado con `encode_raw`/`decode_raw`.
    """
    v = np.array([[codificado] * 3], dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        vuelta = C.log_encode(C.log_decode(v, espacio), espacio)
    assert np.isfinite(vuelta).all(), f"{espacio} devuelve no-finitos con {codificado}"
    assert float(np.max(np.abs(vuelta - v))) < 1e-9


#: Las curvas de LEY DE POTENCIA. Su techo esta muchisimo mas arriba que el de
#: las logaritmicas, asi que van por separado. `srgb` es nueva de la ronda 2.
CURVAS_DE_POTENCIA = ("rec709", "srgb")
CURVAS_LOGARITMICAS = tuple(sorted(set(CURVAS) - set(CURVAS_DE_POTENCIA)))


@pytest.mark.parametrize("espacio", CURVAS_LOGARITMICAS)
def test_un_codificado_de_200_desborda_a_infinito_en_las_logaritmicas(espacio):
    """Documenta donde se acaba el rango util de las cinco curvas log.

    No es un caso plausible (200 codificado no sale de ninguna camara) pero deja
    escrito donde esta el techo y que la salida es `inf`, no una excepcion.
    Ademas suelta un `RuntimeWarning` de desbordamiento que NO esta silenciado,
    a diferencia de lo que hace `_frac_c7` en `perceptual.py`.

    RONDA 2: la premisa vale para las curvas con un `10**algo` dentro, no para
    una ley de potencia. Antes bastaba con excluir `rec709`; con la llegada de
    `srgb` hay dos, asi que ahora se dicen por su nombre en
    `CURVAS_DE_POTENCIA`. Mi `parametrize` recorria `SPACES` y por eso se puso
    rojo solo al aparecer un espacio nuevo: es el precio (barato) de recorrer la
    tabla en vez de listar a mano.
    """
    v = np.array([[200.0] * 3], dtype=np.float64)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        lineal = C.log_decode(v, espacio)
    assert not np.isfinite(lineal).all()
    assert any("overflow" in str(a.message) for a in avisos)


@pytest.mark.parametrize("espacio", CURVAS_DE_POTENCIA)
def test_las_curvas_de_potencia_aguantan_muchisimo_mas_antes_de_desbordar(espacio):
    """El otro techo, medido: `rec709` y `srgb` no desbordan hasta ~1e200.

    Un codificado de 200 les da 1.05e5 y 2.93e5 respectivamente, finitos y
    perfectamente utilizables. El desbordamiento llega cuando el exponente
    (1/0.45 y 2.4) lleva el resultado por encima del maximo del float64, que es
    entre 1e100 y 1e200 de entrada. Dicho de otra forma: por este lado no se
    rompe nada nunca.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        finitos = C.log_decode(np.array([[200.0, 1e10, 1e100]]), espacio)
        desbordados = C.log_decode(np.array([[1e200, 1e300, 1e308]]), espacio)
    assert np.isfinite(finitos).all(), f"{espacio} desborda antes de tiempo: {finitos}"
    assert not np.isfinite(desbordados).any()


# ---------------------------------------------------------------------------
# 5. dE2000 en la discontinuidad famosa y en los casos degenerados
# ---------------------------------------------------------------------------


def test_delta_e2000_en_la_discontinuidad_de_tono_de_275_grados():
    """801 muestras barriendo h = 255..295, que es donde RT tiene su pico.

    Se compara contra `colour.difference.delta_E_CIE2000`, no contra los numeros
    del autor. Es el sitio donde mas implementaciones se desvian.
    """
    h = np.linspace(255.0, 295.0, 801)
    croma = 40.0
    lab1 = np.stack(
        [np.full_like(h, 50.0), croma * np.cos(np.radians(h)), croma * np.sin(np.radians(h))], -1
    )
    lab2 = np.stack(
        [
            np.full_like(h, 51.0),
            (croma + 2.0) * np.cos(np.radians(h + 3.0)),
            (croma + 2.0) * np.sin(np.radians(h + 3.0)),
        ],
        -1,
    )
    peor = float(np.max(np.abs(C.delta_e2000_lab(lab1, lab2) - colour.difference.delta_E_CIE2000(lab1, lab2))))
    assert peor < 1e-10, f"diferencia maxima con colour en el entorno de 275 grados: {peor:.3e}"


@pytest.mark.parametrize(
    ("nombre", "a", "b"),
    [
        ("croma cero en los dos (dos grises)", [50.0, 0.0, 0.0], [70.0, 0.0, 0.0]),
        ("croma cero en uno solo", [50.0, 0.0, 0.0], [50.0, 20.0, 0.0]),
        ("tonos a caballo de 0/360", [50.0, 20.0, 0.5], [50.0, 20.0, -0.5]),
        ("croma que desborda el float64", [50.0, 1e5, 1e5], [50.0, -1e5, 1e5]),
        ("L* negativa (fuera de gamut)", [-30.0, 5.0, 5.0], [50.0, 0.0, 0.0]),
        ("el cero absoluto", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]),
    ],
)
def test_delta_e2000_en_los_casos_donde_fallan_las_implementaciones_ingenuas(nombre, a, b):
    """Los seis sitios donde un dE2000 mal escrito se cae. Juez: colour."""
    va = np.array([a])
    vb = np.array([b])
    mio = float(C.delta_e2000_lab(va, vb)[0])
    suyo = float(np.asarray(colour.difference.delta_E_CIE2000(va, vb)).ravel()[0])
    assert np.isfinite(mio), f"{nombre}: ha salido {mio}"
    assert abs(mio - suyo) < 1e-9, f"{nombre}: mio={mio!r} colour={suyo!r}"


def test_delta_e2000_mean_de_una_imagen_vacia_da_nan_con_aviso():
    """Un clip de CERO fotogramas llega aqui como un array vacio.

    No lanza: devuelve NaN y suelta "Mean of empty slice". Queda documentado
    porque quien llame (el agente C) va a recibir un NaN que no viene de ningun
    pixel roto, sino de no haber pixeles.
    """
    vacio = np.zeros((0, 3), dtype=np.float32)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        resultado = C.delta_e2000_mean(vacio, vacio)
    assert np.isnan(resultado)
    assert any("empty slice" in str(a.message) for a in avisos)


# ---------------------------------------------------------------------------
# 6. Imagenes extremas de verdad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "imagen"),
    [
        ("negra entera", np.zeros((8, 8, 3), dtype=np.float32)),
        ("blanca entera", np.ones((8, 8, 3), dtype=np.float32)),
        ("rojo saturado puro", np.tile(np.array([1.0, 0.0, 0.0], np.float32), (8, 8, 1))),
        (
            "canal verde entero a cero",
            np.stack(
                [np.ones((8, 8)), np.zeros((8, 8)), np.ones((8, 8))], -1
            ).astype(np.float32),
        ),
        ("toda negativa", np.full((8, 8, 3), -0.5, dtype=np.float32)),
        ("un solo pixel", np.zeros((1, 1, 3), dtype=np.float32)),
    ],
)
def test_una_imagen_extrema_atraviesa_el_modulo_entero_sin_nan(nombre, imagen):
    """Negro absoluto, blanco absoluto, saturacion total, un canal a cero.

    Pasa por `to_working` -> `from_working` -> Oklab -> Lab -> mascara de piel
    -> dE2000 medio. Nada puede salir NaN ni infinito, y la vuelta tiene que
    caer dentro del error de float32.
    """
    trabajo = C.to_working(imagen, "linear_rec709")
    vuelta = C.from_working(trabajo, "linear_rec709")
    assert np.isfinite(trabajo).all(), f"{nombre}: el espacio de trabajo tiene no-finitos"
    assert float(np.max(np.abs(vuelta - imagen))) < 1e-6
    assert np.isfinite(C.rgb_to_oklab(trabajo)).all()
    assert np.isfinite(C.rgb_to_lab(trabajo)).all()
    assert C.skin_mask_oklab(trabajo).dtype == np.bool_
    assert C.delta_e2000_mean(trabajo, trabajo) == pytest.approx(0.0, abs=1e-9)


def test_la_mascara_de_piel_se_traga_el_camino_de_tierra_del_exterior():
    """El autor lo dice en NOTAS.md; aqui esta el numero, medido por mi.

    No es un bug (es un detector de COLOR, no de caras) pero el numero tiene que
    estar en el informe y tiene que estar atado, porque si algun dia sube, el
    agente C empezara a sacar el "color medio de la piel" de un camino.
    """
    exterior = C.to_working(gen.exterior_scene().image, "linear_rec709")
    rampa = C.to_working(gen.ramp_gray(), "linear_rec709")
    carta = C.to_working(gen.colorchecker(), "linear_rec709")
    assert C.skin_mask_oklab(rampa).mean() == 0.0
    assert C.skin_mask_oklab(exterior).mean() == pytest.approx(0.0175, abs=0.002)
    assert C.skin_mask_oklab(carta).mean() == pytest.approx(0.157, abs=0.005)


@pytest.mark.parametrize("tono", range(6))
def test_la_mascara_de_piel_pierde_un_10_por_ciento_de_la_piel_mas_oscura(tono):
    """Reproduce la tabla de NOTAS.md tono a tono, sin fiarme de la del autor.

    El limite de abajo es lo que el informe afirma: **la exhaustividad del tono
    5 (el mas oscuro) es 0,90**, y la del 0 es 0,967. Los tonos claros llegan
    a 1,000. Eso es un sesgo medido, no una impresion.
    """
    escena = gen.studio_scene(skin_tone_index=tono)
    marcada = C.skin_mask_oklab(C.to_working(escena.image, "linear_rec709"))
    verdad = escena.skin_mask
    exhaustividad = float((marcada & verdad).sum()) / float(verdad.sum())
    precision = float((marcada & verdad).sum()) / float(marcada.sum())
    esperadas = {0: 0.967, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.992, 5: 0.900}
    assert exhaustividad == pytest.approx(esperadas[tono], abs=0.01)
    assert precision > 0.65


# ---------------------------------------------------------------------------
# 7. Formas degeneradas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("forma", "lanza"),
    [((3,), False), ((0, 3), False), ((1, 1, 3), False), ((2,), True), ((4, 4), True), ((3, 0), True)],
)
def test_formas_degeneradas_de_convert(forma, lanza):
    """Un array vacio es legal; uno que no acaba en 3 tiene que lanzar."""
    entrada = np.zeros(forma, dtype=np.float32)
    if lanza:
        with pytest.raises(ValueError, match=r"esperaba \(\.\.\., 3\)"):
            C.convert(entrada, "rec709", "vlog_vgamut")
    else:
        assert C.convert(entrada, "rec709", "vlog_vgamut").shape == forma


def test_un_espacio_inventado_lanza_en_las_cuatro_puertas():
    """`aces` no existe. Las cuatro puertas de entrada tienen que decirlo igual."""
    pixel = np.zeros((1, 3), dtype=np.float32)
    for llamada in (
        lambda: C.convert(pixel, "rec709", "aces"),
        lambda: C.convert(pixel, "aces", "rec709"),
        lambda: C.log_encode(pixel, "aces"),
        lambda: C.log_decode(pixel, "aces"),
    ):
        with pytest.raises(ValueError, match="espacio desconocido"):
            llamada()
