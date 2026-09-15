"""Calibracion del umbral de la huella, con la huella DE VERDAD del agente B.

Este archivo es el unico de los mios que importa `core.analysis`, y a proposito:
calibrar `UMBRAL_HUELLA` contra una huella inventada no calibra nada. El modulo
`core/matching/**` sigue sin importarlo (hay un test que lo comprueba en
`test_matching_emparejar.py`).

LO QUE MIDE, Y POR QUE ESTA ESCRITO ASI
---------------------------------------
Dos listas de pares, y las dos tienen que salir bien a la vez:

* `PARES_COMPARABLES` — el mismo plano con otra exposicion, con otro grado, con
  otra camara, con otro tono de piel. **Ninguno** puede salir marcado.
* `PARES_DISTINTOS` — escenas que no tienen nada que ver. **Todos** tienen que
  salir marcados.

El umbral tiene que caer en el hueco entre los dos, y el test afirma el hueco,
no solo el umbral: si alguien cambia la huella o los rasgos y el hueco se
estrecha, esto se pone rojo **antes** de que empiecen a salir falsos positivos.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.analysis import huella_de_contenido, parecido_de_huellas
from core.color import convert
from core.contracts import CDL, LUT3D, WORKING_SPACE
from core.matching import desajuste_de_contenido, emparejar
from core.matching.contenido import UMBRAL_DESAJUSTE as UMBRAL_DESAJUSTE_RASGOS
from core.matching.contenido import UMBRAL_HUELLA
from tests.conftest import a_trabajo
from tests.media import generate as gen

# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

CDL_FUERTE = CDL(
    slope=(1.35, 0.92, 0.72), offset=(0.03, -0.02, 0.06), power=(0.85, 1.05, 1.25), saturation=1.45
)
CDL_EXTREMO = CDL(
    slope=(1.8, 0.65, 0.55), offset=(0.08, -0.05, 0.12), power=(0.62, 1.15, 1.45), saturation=1.9
)


def lut_de_look(size: int = 33, *, amp: float = 0.15, g: float = 1.25, b: float = 1.45) -> LUT3D:
    """LUT separable con curva en S en el rojo y gamma distinta en verde y azul.

    La S es monotona creciente mientras `amp < 1/(2*pi)`; un LUT no monotono no
    es un look, es un LUT roto.
    """
    t = np.linspace(0.0, 1.0, size)
    ese = np.clip(t - amp * np.sin(2 * np.pi * t), 0.0, 1.0)
    assert np.all(np.diff(ese) > 0), "la curva en S de este test tiene que ser monotona"
    r_, g_, b_ = np.meshgrid(ese, np.clip(t**g, 0, 1), np.clip(t**b, 0, 1), indexing="ij")
    return LUT3D(table=np.stack([r_, g_, b_], axis=-1).astype(np.float32), title="Look")


def _camara(base: np.ndarray, espacio: str, ev: float, ganancia) -> np.ndarray:
    lineal = base * (2.0**ev) * np.asarray(ganancia)
    codificada = convert(lineal.astype(np.float32), "linear_rec709", espacio)  # type: ignore[arg-type]
    return convert(codificada, espacio, WORKING_SPACE).astype(np.float64)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def escenas() -> dict[str, np.ndarray]:
    base = gen.studio_scene(skin_tone_index=2).image.astype(np.float64)
    est = a_trabajo(gen.studio_scene(skin_tone_index=2).image).astype(np.float64)
    look = lut_de_look()
    return {
        "estudio2": est,
        # El look del agente B: una S suave y gammas por canal, que es un look
        # de verdad y no una destruccion de la imagen.
        "estudio2 CDL+look real": lut_de_look(amp=0.12, g=1.06, b=1.15).apply(
            CDL_FUERTE.apply(est)
        ),
        "estudio2 -1EV": a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=-1.0).image),
        "estudio2 -2EV": a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=-2.0).image),
        "estudio2 +1.5EV": a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=1.5).image),
        "estudio2 CDL fuerte": CDL_FUERTE.apply(est),
        "estudio2 CDL extremo": CDL_EXTREMO.apply(est),
        "estudio2 LUT look": look.apply(est),
        "estudio2 CDL+LUT": look.apply(CDL_EXTREMO.apply(est)),
        "estudio0": a_trabajo(gen.studio_scene(skin_tone_index=0).image),
        "estudio5": a_trabajo(gen.studio_scene(skin_tone_index=5).image),
        "cam Canon": _camara(base, "clog3_cinemagamut", -0.7, (1.08, 1.00, 0.88)),
        "cam DJI": _camara(base, "dlog_dgamut", 0.9, (1.04, 0.98, 0.95)),
        "exterior": a_trabajo(gen.exterior_scene().image),
        "carta": a_trabajo(gen.colorchecker()),
        "rampa": a_trabajo(gen.ramp_gray()),
        "degradado": a_trabajo(gen.gradient()),
        "ruido": a_trabajo(gen.noise_field()),
    }


@pytest.fixture(scope="module")
def huellas(escenas) -> dict[str, np.ndarray]:
    return {k: huella_de_contenido(v.astype(np.float32)) for k, v in escenas.items()}


#: Pares que SI son comparables: el mismo plano de otra manera.
PARES_COMPARABLES = [
    ("estudio2", "estudio2"),
    ("estudio2", "estudio2 -1EV"),
    ("estudio2", "estudio2 -2EV"),
    ("estudio2", "estudio2 +1.5EV"),
    ("estudio2", "estudio2 CDL fuerte"),
    ("estudio2", "estudio2 CDL extremo"),
    ("estudio2", "estudio2 LUT look"),
    ("estudio2", "estudio2 CDL+LUT"),
    ("estudio2", "estudio2 CDL+look real"),
    ("estudio2 CDL extremo", "estudio2 CDL+LUT"),
    ("estudio2", "estudio0"),
    ("estudio2", "estudio5"),
    ("estudio0", "estudio5"),
    ("estudio2", "cam Canon"),
    ("estudio2", "cam DJI"),
    ("cam Canon", "cam DJI"),
]

#: Pares que NO son comparables: otra escena.
PARES_DISTINTOS = [
    ("estudio2", "exterior"),
    ("estudio5", "exterior"),
    ("estudio2 CDL+LUT", "exterior"),
    ("estudio2", "carta"),
    ("estudio2", "rampa"),
    ("estudio2", "degradado"),
    ("estudio2", "ruido"),
    ("exterior", "rampa"),
    ("exterior", "carta"),
    ("exterior", "degradado"),
    ("carta", "rampa"),
    ("degradado", "rampa"),
]


def _con_huellas(escenas, huellas, a, b):
    return desajuste_de_contenido(
        escenas[a].reshape(-1, 3),
        escenas[b].reshape(-1, 3),
        huellas=(huellas[a], huellas[b]),
    )


# ---------------------------------------------------------------------------
# La calibracion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("a,b", PARES_COMPARABLES)
def test_ningun_par_comparable_sale_marcado(a, b, escenas, huellas):
    hay, _, _ = _con_huellas(escenas, huellas, a, b)
    assert hay is False, f"{a} vs {b} sale marcado y es el mismo plano"


@pytest.mark.parametrize("a,b", PARES_DISTINTOS)
def test_todos_los_pares_distintos_salen_marcados(a, b, escenas, huellas):
    hay, _, razones = _con_huellas(escenas, huellas, a, b)
    assert hay is True, f"{a} vs {b} NO sale marcado y son escenas distintas"
    assert "no parecen comparables" in razones[0]


def test_el_umbral_cae_en_el_hueco_medido_y_el_hueco_es_grande(escenas, huellas):
    """La afirmacion de verdad: el umbral esta en un hueco ancho, no rozando.

    Cifras medidas con la huella del agente B (parecido, 1 = identicas):

        peor par COMPARABLE ....... 0.756   (piel 0 contra piel 5)
        --- UMBRAL_HUELLA = 0.50 (parecido minimo) ---
        mejor par NO comparable ... 0.219   (degradado contra rampa de gris)

    Margen: 0.256 por arriba y 0.281 por abajo. Para comparar, los rasgos de
    pixeles solos separan 0.612 de 0.753, o sea un hueco de 0.14 en vez de 0.54.
    """
    peor_comparable = min(
        parecido_de_huellas(huellas[a], huellas[b]) for a, b in PARES_COMPARABLES
    )
    mejor_distinto = max(parecido_de_huellas(huellas[a], huellas[b]) for a, b in PARES_DISTINTOS)
    parecido_minimo = 1.0 - UMBRAL_HUELLA

    assert mejor_distinto < parecido_minimo < peor_comparable
    assert peor_comparable > 0.70, f"peor par comparable {peor_comparable:.4f}"
    assert mejor_distinto < 0.30, f"mejor par no comparable {mejor_distinto:.4f}"
    assert peor_comparable - mejor_distinto > 0.40, "el hueco se ha estrechado: recalibra"
    # Y el umbral esta cerca del centro del hueco, no pegado a un dato.
    centro = 0.5 * (peor_comparable + mejor_distinto)
    assert abs(parecido_minimo - centro) < 0.10


def test_con_un_grado_NORMAL_los_rasgos_se_quedan_a_0_09_del_umbral(escenas, huellas):
    """El hallazgo que motivo esta ronda, dicho con precision.

    Con un grado **plausible** (CDL fuerte + un LUT de look de verdad: S suave y
    gammas por canal) los rasgos de pixeles NO dan un falso positivo hoy, pero se
    quedan a **0.088** del umbral. Ese margen es el problema: es medio pelo para
    una cosa que, si se equivoca, le dice a Mario que no puede igualar dos planos
    que si puede.

        rasgos de pixeles ... distancia 0.612  (umbral 0.70 -> margen 0.088)
        huella .............. parecido  0.997  (umbral 0.50 -> margen 0.497)
    """
    a, b = "estudio2", "estudio2 CDL+look real"
    hay, distancia, _ = desajuste_de_contenido(
        escenas[a].reshape(-1, 3), escenas[b].reshape(-1, 3)
    )
    parecido = parecido_de_huellas(huellas[a], huellas[b])

    assert hay is False, "hoy no hay falso positivo, pero mira el margen"
    assert 0.55 < distancia < UMBRAL_DESAJUSTE_RASGOS
    assert UMBRAL_DESAJUSTE_RASGOS - distancia < 0.15, "el margen de la via debil es fino"
    assert parecido > 0.99
    assert _con_huellas(escenas, huellas, a, b)[0] is False


def test_un_grado_que_destroza_la_imagen_si_tumba_a_los_rasgos(escenas, huellas):
    """Y aqui si se rompe la via debil, aunque el grado ya no sea razonable.

    Un CDL extremo con un LUT de gammas encima deja el rojo pegado a 1.0 y el
    verde y el azul por debajo de 0.09: la imagen esta destrozada, no gradada. Es
    un caso limite, no un grado que Mario vaya a hacer, pero marca el final del
    recorrido de los rasgos de pixeles:

        rasgos de pixeles ... distancia 2.10  (umbral 0.70 -> falso desajuste)
        huella .............. parecido  0.91  (bien: sigue siendo el mismo plano)

    Aviso para quien lea el numero: en este caso la confianza sale 0 de todas
    formas, y **con razon**, porque el grado se ha comido el rango y la
    extrapolacion es del 100%. Lo que arregla la huella es la BANDERA de
    contenido, no la nota.
    """
    a, b = "estudio2", "estudio2 CDL+LUT"
    sin_huella_hay, distancia, _ = desajuste_de_contenido(
        escenas[a].reshape(-1, 3), escenas[b].reshape(-1, 3)
    )
    con_huella_hay, _, _ = _con_huellas(escenas, huellas, a, b)

    assert distancia > 1.5, "el grado ya no descoloca a los rasgos; vuelve a medir"
    assert sin_huella_hay is True  # el falso positivo de la via debil, medido
    assert parecido_de_huellas(huellas[a], huellas[b]) > 0.85
    assert con_huella_hay is False  # con huella, bien


def test_la_huella_manda_sobre_los_rasgos_en_los_dos_sentidos(escenas):
    """Con huella, los rasgos de pixeles ya no levantan la bandera ellos solos,
    ni en un sentido ni en el otro."""
    est = escenas["estudio2"].reshape(-1, 3)
    ext = escenas["exterior"].reshape(-1, 3)
    igual = np.full(96, 1.0 / np.sqrt(96))
    opuesta_a = np.zeros(96)
    opuesta_a[0] = 1.0
    opuesta_b = np.zeros(96)
    opuesta_b[1] = 1.0

    # Dos escenas distintas pero con la misma huella -> no se marca.
    assert desajuste_de_contenido(est, ext, huellas=(igual, igual))[0] is False
    # El mismo plano pero con huellas ajenas -> se marca.
    assert desajuste_de_contenido(est, est, huellas=(opuesta_a, opuesta_b))[0] is True


def test_sin_huellas_se_cae_a_los_rasgos_y_se_nota(escenas):
    """`huellas=None` tiene que dar exactamente el camino de siempre."""
    a, b = escenas["estudio2"].reshape(-1, 3), escenas["exterior"].reshape(-1, 3)
    assert desajuste_de_contenido(a, b)[0] is True
    assert desajuste_de_contenido(a, b, huellas=(None, None))[0] is True
    assert desajuste_de_contenido(a, a)[0] is False


# ---------------------------------------------------------------------------
# Que llegue hasta `emparejar`
# ---------------------------------------------------------------------------


def test_emparejar_acepta_las_huellas_y_cambia_de_opinion(escenas, huellas):
    """Es el caso que le importa a Mario: un plano con un grado muy fuerte,
    igualado contra el mismo plano sin gradar."""
    o = escenas["estudio2 CDL+LUT"].reshape(-1, 3)
    r = escenas["estudio2"].reshape(-1, 3)
    sin = emparejar(o, r)
    con = emparejar(o, r, huellas=(huellas["estudio2 CDL+LUT"], huellas["estudio2"]))

    assert sin.content_mismatch is True  # falso positivo de la via debil
    assert con.content_mismatch is False  # con la huella, bien
    assert sin.confidence.metrics["desajuste"] == 1.0
    assert con.confidence.metrics["desajuste"] == 0.0
    assert "no parecen la misma escena" in sin.confidence.reasons[0]
    assert not any("no parecen la misma escena" in r for r in con.confidence.reasons)
    # OJO: en ESTE caso la nota sigue siendo 0 en los dos, y con razon: el grado
    # aplasta el rango y la extrapolacion es del 100%. Lo que arregla la huella
    # es la bandera de contenido, no la nota. Que la pena por desajuste se quite
    # y suba la nota se prueba en `test_la_pena_por_desajuste_se_levanta`.
    assert con.confidence.metrics["extrapolacion"] > 0.9


def test_emparejar_con_huellas_sigue_marcando_lo_que_hay_que_marcar(escenas, huellas):
    """La huella no puede servir para que no salte nunca nada."""
    m = emparejar(
        escenas["estudio2"].reshape(-1, 3),
        escenas["exterior"].reshape(-1, 3),
        huellas=(huellas["estudio2"], huellas["exterior"]),
    )
    assert m.content_mismatch is True
    assert m.confidence.level == "baja"


def test_las_cuatro_camaras_no_se_marcan_ni_con_huella_ni_sin_ella(escenas, huellas):
    for a, b in (("estudio2", "cam Canon"), ("estudio2", "cam DJI"), ("cam Canon", "cam DJI")):
        assert _con_huellas(escenas, huellas, a, b)[0] is False, (a, b)
        assert (
            desajuste_de_contenido(escenas[a].reshape(-1, 3), escenas[b].reshape(-1, 3))[0] is False
        ), (a, b)


def test_la_razon_de_la_huella_va_la_primera_y_se_entiende(escenas, huellas):
    _, _, razones = _con_huellas(escenas, huellas, "estudio2", "exterior")
    assert "no parecen comparables" in razones[0]
    assert any("se parecen un" in r and "composicion" in r for r in razones)


def test_la_pena_por_desajuste_se_levanta(escenas, huellas):
    """Con un grado normal (que no destroza el rango), quitar el falso desajuste
    tiene que subir la nota de verdad: la pena es multiplicativa (x0.35)."""
    from core.matching import puntuar_confianza

    con_bandera = puntuar_confianza(
        n_muestras=60000, solape=0.99, condicion=1e3, residuo_de=0.3, desajuste=True
    )
    sin_bandera = puntuar_confianza(
        n_muestras=60000, solape=0.99, condicion=1e3, residuo_de=0.3, desajuste=False
    )
    assert sin_bandera.score > con_bandera.score * 2.5
    assert sin_bandera.level == "alta"
    assert con_bandera.level == "baja"
