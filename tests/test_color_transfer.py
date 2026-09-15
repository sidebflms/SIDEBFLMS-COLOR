"""Curvas de transferencia: anclas del fabricante, juez independiente e ida y vuelta.

Tres niveles de verificacion, de mas fuerte a mas debil:

1. **Anclas publicadas.** Numeros que el fabricante imprime en su documento
   (18% de gris, 90% de blanco, punto de corte). Tolerancia apretada: si esto
   falla, la formula esta mal escrita, no es ruido numerico.
2. **Juez independiente.** `colour-science` implementa las mismas curvas por su
   cuenta. Nuestra implementacion es propia; colour solo juzga.
3. **Ida y vuelta.** `log_decode(log_encode(x)) == x` en todo el rango util,
   negativos y valores enormes incluidos.
"""

from __future__ import annotations

import colour
import numpy as np
import pytest

from core.color import SPACES, log_decode, log_encode
from core.color import transfer as T

ESPACIOS = tuple(SPACES)
CON_CURVA = tuple(n for n in SPACES if not SPACES[n].is_linear)
LINEALES = tuple(n for n in SPACES if SPACES[n].is_linear)

#: Juez independiente por espacio. Se pasan los valores por defecto de colour a
#: proposito: para las cinco curvas de camara, el defecto de colour es
#: exactamente nuestra convencion (escena-lineal con 0.18 = 18% de gris ->
#: code value normalizado).
JUEZ = {
    "slog3_sgamut3cine": colour.models.log_encoding_SLog3,
    "vlog_vgamut": colour.models.log_encoding_VLog,
    "clog3_cinemagamut": colour.models.log_encoding_CanonLog3,
    "dlog_dgamut": colour.models.log_encoding_DJIDLog,
    "davinci_wg_intermediate": colour.models.oetf_DaVinciIntermediate,
    "rec709": colour.models.oetf_BT709,
    "srgb": colour.models.eotf_inverse_sRGB,
}


# ---------------------------------------------------------------------------
# 1. Anclas publicadas por el fabricante
# ---------------------------------------------------------------------------


def test_slog3_gris18_es_420_entre_1023():
    """Sony publica el 18% de gris en el code value 420 de 10 bits. Exacto."""
    assert log_encode(np.float64(0.18), "slog3_sgamut3cine") == pytest.approx(
        420.0 / 1023.0, abs=1e-12
    )


def test_slog3_punto_de_corte_publicado():
    """El corte esta en 0.01125 y la rama lineal pasa por el code value 171.2103."""
    lin = log_encode(np.float64(0.01125 - 1e-9), "slog3_sgamut3cine")
    assert lin == pytest.approx(171.2102946929 / 1023.0, abs=1e-8)
    # Y la rama lineal pasa por el 95 en x = 0 (el "negro" de S-Log3).
    assert log_encode(np.float64(0.0), "slog3_sgamut3cine") == pytest.approx(
        95.0 / 1023.0, abs=1e-12
    )


def test_vlog_anclas_publicadas():
    """Panasonic: 0% de reflectancia -> 0.125, y cut1 = 0.01 cae justo en cut2 = 0.181."""
    assert log_encode(np.float64(0.0), "vlog_vgamut") == pytest.approx(0.125, abs=1e-12)
    justo_antes = log_encode(np.float64(0.01 - 1e-12), "vlog_vgamut")
    assert justo_antes == pytest.approx(0.181, abs=1e-10)


def test_vlog_tabla_ire_del_manual():
    """La tabla de Panasonic en IRE: 0% -> 7.3, 18% -> ~42, 90% -> ~61.

    El paso a IRE es el de rango legal de 10 bits: (CV - 64) / (940 - 64).
    """

    def ire(x: float) -> float:
        return float((log_encode(np.float64(x), "vlog_vgamut") * 1023.0 - 64.0) / 876.0 * 100.0)

    assert ire(0.0) == pytest.approx(7.3, abs=0.05)
    assert ire(0.18) == pytest.approx(42.0, abs=0.2)
    assert ire(0.90) == pytest.approx(61.0, abs=0.5)


def test_clog3_gris18_es_32_8_ire():
    """Canon publica el 18% de gris en 32.8 IRE de rango completo.

    Nuestra salida es code value de rango legal (ver `transfer.py`), asi que
    para comparar con el numero publicado hay que deshacer el rango legal:
    completo = (cv * 1023 - 64) / 876.
    """
    cv = log_encode(np.float64(0.18), "clog3_cinemagamut")
    completo = (cv * 1023.0 - 64.0) / 876.0
    assert completo * 100.0 == pytest.approx(32.8, abs=0.02)


def test_clog3_injertos_en_mas_menos_0_014():
    """Las ramas de Canon se injertan en +/-0.014 de la entrada de la formula.

    La entrada de la formula es reflectancia/0.9, asi que en escena-lineal los
    injertos caen en +/-0.0126. Los valores codificados de esos dos puntos son
    los que Canon publica: 0.097465473 y 0.15277891.
    """
    assert log_encode(np.float64(0.014 * 0.9), "clog3_cinemagamut") == pytest.approx(
        0.15277891, abs=1e-8
    )
    assert log_encode(np.float64(-0.014 * 0.9), "clog3_cinemagamut") == pytest.approx(
        0.097465473, abs=1e-8
    )


def test_dlog_negro_publicado():
    """DJI: la rama lineal es 6.025x + 0.0929, o sea que x = 0 da 0.0929 exacto."""
    assert log_encode(np.float64(0.0), "dlog_dgamut") == pytest.approx(0.0929, abs=1e-12)


def test_davinci_intermediate_gris18_es_0_336():
    """Blackmagic publica el 18% de gris de DaVinci Intermediate en 0.336."""
    assert log_encode(np.float64(0.18), "davinci_wg_intermediate") == pytest.approx(
        0.336, abs=5e-5
    )


def test_davinci_intermediate_corte_lineal_coincide_con_corte_log():
    """LIN_CUT * M tiene que dar LOG_CUT: es como Blackmagic define la curva.

    La tolerancia es 1e-7 y no es un apano para que pase: Blackmagic publica
    LIN_CUT y LOG_CUT redondeados a ocho decimales, y ese redondeo de LIN_CUT
    multiplicado por M = 10.44 ya vale +/-5.2e-8 el solo. Pedir mas seria pedir
    mas precision de la que tiene el documento. Lo que este test comprueba de
    verdad es que las dos constantes publicadas son coherentes entre si hasta
    donde estan impresas; la diferencia real medida es 2.1e-8.
    """
    assert pytest.approx(T._DI_LOG_CUT, abs=1e-7) == T._DI_LIN_CUT * T._DI_M


def test_srgb_anclas_publicadas():
    """IEC 61966-2-1: 1.0 -> 1.0, corte en 0.0031308, y el 18% de gris en 0.4614.

    El 0.4614 es el famoso "el 18% de gris es el 118 de 255" en sRGB de 8 bits
    (0.46136 * 255 = 117.6).
    """
    assert log_encode(np.float64(0.0), "srgb") == pytest.approx(0.0, abs=1e-15)
    assert log_encode(np.float64(1.0), "srgb") == pytest.approx(1.0, abs=1e-12)
    assert log_encode(np.float64(0.18), "srgb") == pytest.approx(0.46136, abs=1e-5)
    assert log_encode(np.float64(0.0031308), "srgb") == pytest.approx(0.04045, abs=1e-6)
    # El tramo lineal tiene pendiente 12.92, no 4.5 como el de Rec.709.
    assert log_encode(np.float64(0.001), "srgb") == pytest.approx(0.01292, abs=1e-15)


def test_bt709_anclas_publicadas():
    """BT.709: pendiente 4.5 cerca del negro, y 1.0 -> 1.0 exacto."""
    assert log_encode(np.float64(0.001), "rec709") == pytest.approx(0.0045, abs=1e-12)
    assert log_encode(np.float64(1.0), "rec709") == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 2. Juez independiente: colour-science
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", sorted(JUEZ))
def test_coincide_con_colour_science(espacio):
    """Nuestra curva contra la de colour-science, NEGATIVOS INCLUIDOS.

    Tolerancia 1e-10 absoluta: no es "parecido", es la misma formula. Si esto
    se afloja alguna vez, lo que hay debajo es un error de constante.

    Los negativos estan aqui desde la ronda 1 de revision. Antes el barrido era
    solo positivo, y con eso la afirmacion de NOTAS.md ("diferencia maxima 0.0")
    solo valia en medio dominio: `rec709` extendia por simetria impar y colour
    prolonga el tramo lineal, lo que daba 11.3 de diferencia en x = -2.88. Ver
    NOTAS.md seccion 9 para por que se cambio la curva y no la afirmacion.
    """
    x = np.concatenate(
        [
            np.array([0.0, 0.18, 0.9, 1.0, -0.5, -0.05, -0.018, -1e-6, 1e-6]),
            0.18 * 2.0 ** np.linspace(-6.0, 6.0, 200),
            -0.18 * 2.0 ** np.linspace(-6.0, 4.0, 100),  # 10 paradas en negativo
        ]
    ).astype(np.float64)
    mio = log_encode(x, espacio)
    with np.errstate(invalid="ignore"):
        # colour evalua las tres ramas de Canon a la vez con `np.select` y la
        # rama de negativos suelta un NaN (descartado despues) para x grande.
        # Es ruido suyo, no nuestro.
        suyo = np.asarray(JUEZ[espacio](x), dtype=np.float64)
    assert np.max(np.abs(mio - suyo)) < 1e-10


def test_colour_no_trae_davinci_como_log_encoding():
    """Aviso para el revisor: DaVinci Intermediate no esta como `log_encoding_*`.

    colour la publica como `oetf_DaVinciIntermediate` / `oetf_inverse_...`. Es
    la misma curva; el encargo la nombraba `log_encoding_DaVinciIntermediate` y
    ese nombre NO existe. Este test esta para que nadie pierda media hora
    buscandolo.
    """
    assert not hasattr(colour.models, "log_encoding_DaVinciIntermediate")
    assert hasattr(colour.models, "oetf_DaVinciIntermediate")


# ---------------------------------------------------------------------------
# 3. Ida y vuelta
# ---------------------------------------------------------------------------

#: Rango de prueba: de -0.2 (los negativos que trae el log) a 20.0 (el sol de
#: `exterior_scene`, que llega a 9.0, con margen de sobra).
_RANGO = np.concatenate(
    [
        np.linspace(-0.2, 0.0, 2001, endpoint=False),
        np.linspace(0.0, 0.05, 5001),
        np.linspace(0.05, 20.0, 20001),
    ]
)


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_ida_y_vuelta_en_todo_el_rango(espacio):
    """`log_decode(log_encode(x)) == x` con error de maquina.

    Se excluye una ventana minuscula alrededor del punto de corte de V-Log y de
    DaVinci Intermediate, donde la curva PUBLICADA es no monotona y por tanto
    no invertible. Ver `test_ventana_no_invertible_*`: el limite esta medido y
    afirmado ahi, no escondido aqui.
    """
    x = _RANGO[~_en_ventana_mala(_RANGO, espacio)]
    z = log_decode(log_encode(x, espacio), espacio)
    error = np.abs(z - x) / np.maximum(np.abs(x), 1e-6)
    assert np.max(error) < 1e-9


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_ida_y_vuelta_con_valores_enormes(espacio):
    """Un especular a 9.0 y un cielo a 100 tienen que sobrevivir la vuelta."""
    x = np.array([2.4, 9.0, 40.0, 100.0, 1000.0])
    z = log_decode(log_encode(x, espacio), espacio)
    assert np.allclose(z, x, rtol=1e-9)


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_ida_y_vuelta_con_negativos(espacio):
    """El material log trae negativos de verdad. No se recortan."""
    x = np.array([-0.5, -0.2, -0.05, -0.01, -1e-6])
    y = log_encode(x, espacio)
    assert np.all(np.isfinite(y))
    z = log_decode(y, espacio)
    assert np.allclose(z, x, rtol=1e-9, atol=1e-12)


def test_los_negativos_de_rec709_y_srgb_prolongan_el_tramo_lineal():
    """Decision de la ronda 1: extension lineal, no simetria impar.

    Las dos normas definen su curva solo en 0..1. Se extiende prolongando el
    tramo lineal (4.5x en Rec.709, 12.92x en sRGB), que es lo que hace
    colour-science. La alternativa que habia antes (simetria impar) tambien es
    monotona e invertible y cumple el contrato 1 igual de bien; lo que decidio
    fue poder verificar la curva entera contra una implementacion independiente
    en vez de solo la mitad positiva. Ver NOTAS.md seccion 9.
    """
    x = np.array([-0.5, -0.18, -0.05, -0.018, -0.001])
    assert np.allclose(log_encode(x, "rec709"), 4.5 * x, atol=1e-15)
    assert np.allclose(log_encode(x, "srgb"), 12.92 * x, atol=1e-15)
    # Y siguen invirtiendo exacto, que es lo que pide el contrato 1.
    assert np.allclose(log_decode(log_encode(x, "rec709"), "rec709"), x, atol=1e-15)
    assert np.allclose(log_decode(log_encode(x, "srgb"), "srgb"), x, atol=1e-15)


def _en_ventana_mala(x: np.ndarray, espacio: str) -> np.ndarray:
    """Ventana (medida, no estimada) donde la curva publicada no es invertible."""
    ventanas = {
        "vlog_vgamut": (0.009999_9, 0.010000_1),
        "davinci_wg_intermediate": (0.00262408_9, 0.00262409_1),
    }
    if espacio not in ventanas:
        return np.zeros(x.shape, dtype=bool)
    lo, hi = ventanas[espacio]
    return (x > lo) & (x < hi)


def test_ventana_no_invertible_de_vlog_esta_acotada():
    """LIMITE REAL, no bug: V-Log publicada no es monotona en su punto de corte.

    La rama logaritmica en x = 0.01 vale 0.18099969 y la lineal justo por debajo
    llega a 0.181: hay un saltito hacia atras. Como la funcion no es inyectiva
    ahi, NINGUN decodificador puede invertirla en esa franja. Lo que si se puede
    es acotarla y no mentir sobre ella: mide 5.6e-8 de ancho en x, o sea 8e-6
    paradas de luz. No se toca la formula para "arreglarlo": cambiarla seria
    dejar de leer lo que graba una Lumix.
    """
    x = 0.01 * (1.0 + np.linspace(-2e-5, 2e-5, 40001))
    err = np.abs(log_decode(log_encode(x, "vlog_vgamut"), "vlog_vgamut") - x)
    malos = err > 1e-12
    assert malos.any(), "si esto deja de fallar, alguien ha cambiado la curva de Panasonic"
    assert np.ptp(x[malos]) < 1e-7
    assert err.max() < 1e-7


def test_ventana_no_invertible_de_davinci_esta_acotada():
    """Lo mismo en DaVinci Intermediate, pero tres ordenes de magnitud mas fina."""
    x = 0.00262409 * (1.0 + np.linspace(-2e-6, 2e-6, 40001))
    err = np.abs(
        log_decode(log_encode(x, "davinci_wg_intermediate"), "davinci_wg_intermediate") - x
    )
    assert err.max() < 1e-10


@pytest.mark.parametrize("espacio", ("slog3_sgamut3cine", "clog3_cinemagamut", "dlog_dgamut"))
def test_estas_curvas_si_son_exactas_en_el_corte(espacio):
    """Sony, Canon y DJI si invierten exacto en el corte. Que conste en acta."""
    cortes = {"slog3_sgamut3cine": 0.01125, "clog3_cinemagamut": 0.0126, "dlog_dgamut": 0.0078}
    c = cortes[espacio]
    x = c * (1.0 + np.linspace(-1e-4, 1e-4, 20001))
    err = np.abs(log_decode(log_encode(x, espacio), espacio) - x)
    assert err.max() < 1e-14


# ---------------------------------------------------------------------------
# Monotonia, forma y espacios lineales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_la_curva_es_creciente(espacio):
    """Una curva de transferencia que baje en algun sitio invierte el contraste.

    Se salta la ventana no invertible ya documentada.
    """
    x = _RANGO[~_en_ventana_mala(_RANGO, espacio)]
    y = log_encode(x, espacio)
    assert np.all(np.diff(y) > -1e-12)


@pytest.mark.parametrize("espacio", LINEALES)
def test_los_espacios_lineales_no_tocan_nada(espacio):
    x = np.array([[-0.3, 0.18, 9.0]], dtype=np.float64)
    assert np.array_equal(log_encode(x, espacio), x)
    assert np.array_equal(log_decode(x, espacio), x)


@pytest.mark.parametrize("espacio", LINEALES)
def test_los_espacios_lineales_devuelven_copia(espacio):
    """Si devolvieran el mismo array, tocar la salida tocaria la entrada de otro."""
    x = np.array([0.18, 0.5, 1.0])
    y = log_encode(x, espacio)
    y[0] = -99.0
    assert x[0] == 0.18


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_conserva_la_forma(espacio):
    for forma in [(), (3,), (1, 3), (4, 5, 3), (2, 3, 4, 3)]:
        x = np.full(forma, 0.18)
        assert log_encode(x, espacio).shape == forma


def test_espacio_desconocido_lanza():
    with pytest.raises(ValueError, match="espacio desconocido"):
        log_encode(np.array([0.18]), "arri_logc4")  # type: ignore[arg-type]


def test_dtype_float32_entra_float32_sale():
    x = np.full((4, 4, 3), 0.18, dtype=np.float32)
    assert log_encode(x, "slog3_sgamut3cine").dtype == np.float32


def test_dtype_float64_se_respeta():
    x = np.full((4, 4, 3), 0.18, dtype=np.float64)
    assert log_encode(x, "slog3_sgamut3cine").dtype == np.float64
