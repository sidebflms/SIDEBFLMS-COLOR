"""LOS CUATRO TESTS QUE DECIDEN SI LA NOCHE HA SERVIDO.

Son los T1-T4 de la seccion 6 del encargo. Propiedad del orquestador, escritos
**sin mirar** los tests de los agentes y sin llamar a las funciones que ellos
escribieron para probarse a si mismos (`igualar_camaras`, `catalogo_luts_malos`
como unica fuente...). El montaje se fabrica aqui, desde el generador.

Si estos cuatro fallan, la noche no ha servido, por muy bonito que este el
codigo y por muchos miles de tests que haya en verde.

LOS CRITERIOS NO SE TOCAN. Estan copiados literalmente del encargo:

  T1  dE2000 medio < 1.0 y maximo < 3.0 en la zona con cobertura,
      y el mapa de cobertura marca como inventadas EXACTAMENTE las celdas
      sin muestras.
  T2  con vineta y ventana encima, el diagnostico NO puede decir que es
      100% LUT, y tiene que senalar la zona.
  T3  dE2000 medio entre camaras < 2.0 despues, partiendo de > 8.0 antes.
  T4  el QC caza los tres LUT malos, cada uno por su nombre, y la identidad
      pasa limpia.

Si alguno no llega, se queda rojo y se dice en BITACORA.md con el numero
exacto. Un rojo honesto es un resultado util; un verde conseguido aflojando
un umbral es una mentira que se descubre el lunes delante de un cliente.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import convert, delta_e2000_mean
from core.contracts import CDL, LUT3D, LUT_SIZE_DEFAULT, WORKING_SPACE
from core.io import (
    CODIGO_BANDING,
    CODIGO_GAMUT,
    CODIGO_NO_MONOTONIA,
    escribir_cube,
    leer_cube,
    qc_lut,
)
from core.matching import emparejar
from tests.conftest import a_trabajo
from tests.media import generate as gen

# Las cifras que salgan se imprimen para poder copiarlas a la bitacora tal cual.
pytestmark = pytest.mark.entregable


def _informe(nombre: str, **cifras: float) -> None:
    linea = "  ".join(f"{k}={v:.4f}" for k, v in cifras.items())
    print(f"\n[{nombre}] {linea}")


# ---------------------------------------------------------------------------
# T3 - Igualado de cuatro camaras
# ---------------------------------------------------------------------------

#: Las cuatro camaras de SIDEBFLMS, con su espacio de captura real.
CAMARAS: tuple[tuple[str, str], ...] = (
    ("FX3", "slog3_sgamut3cine"),
    ("Canon", "clog3_cinemagamut"),
    ("Lumix", "vlog_vgamut"),
    ("DJI", "dlog_dgamut"),
)

#: Desviacion de balance y exposicion plausible de rodaje: cada camara llega con
#: su temperatura y su diafragma algo distintos, que es lo que pasa de verdad.
DESVIACIONES: tuple[CDL, ...] = (
    CDL(slope=(1.00, 1.00, 1.00), offset=(0.000, 0.000, 0.000)),
    CDL(slope=(1.08, 0.99, 0.93), offset=(0.006, 0.000, -0.004)),
    CDL(slope=(0.94, 1.01, 1.09), offset=(-0.005, 0.002, 0.007)),
    CDL(slope=(1.12, 1.04, 0.90), offset=(0.010, 0.003, -0.008)),
)


def _fabricar_camaras(escena_lineal: np.ndarray) -> list[np.ndarray]:
    """Un mismo plano, tal y como lo habria grabado cada una de las cuatro.

    Se pasa de escena-lineal al espacio de captura de cada camara con
    `core.color.convert` (primarios + curva de verdad, no a ojo), se le suma su
    desviacion de balance, y se devuelve al espacio de trabajo, que es donde
    opera el emparejador. El resultado son cuatro versiones del mismo plano que
    NO coinciden, igual que en una mesa de montaje.
    """
    salida = []
    for (_, espacio), desvio in zip(CAMARAS, DESVIACIONES, strict=True):
        captado = convert(escena_lineal, "linear_rec709", espacio)
        captado = desvio.apply(captado)
        salida.append(convert(captado, espacio, WORKING_SPACE).astype(np.float32))
    return salida


def _de_medio_entre_pares(imagenes: list[np.ndarray]) -> float:
    """dE2000 medio de todos los pares, sin repetir."""
    valores = [
        delta_e2000_mean(imagenes[i], imagenes[j])
        for i in range(len(imagenes))
        for j in range(i + 1, len(imagenes))
    ]
    return float(np.mean(valores))


def test_T3_igualado_de_cuatro_camaras(escena_estudio):
    """Las cuatro camaras tienen que volver al espacio de la referencia."""
    camaras = _fabricar_camaras(escena_estudio.image)
    antes = _de_medio_entre_pares(camaras)

    referencia = camaras[0]  # la FX3 manda
    igualadas = [referencia]
    for imagen in camaras[1:]:
        match = emparejar(imagen.reshape(-1, 3), referencia.reshape(-1, 3))
        igualadas.append(match.cdl.apply(imagen).astype(np.float32))
    despues = _de_medio_entre_pares(igualadas)

    _informe("T3", antes=antes, despues=despues, mejora=antes / max(despues, 1e-9))

    assert antes > 8.0, f"el montaje no parte de suficiente desajuste: {antes:.3f}"
    assert despues < 2.0, f"no llega al criterio: {despues:.3f}"


def test_T3_ningun_par_suelto_se_esconde_detras_de_la_media(escena_estudio):
    """Una media de 0.3 con un par a 5 seria una media que miente."""
    camaras = _fabricar_camaras(escena_estudio.image)
    referencia = camaras[0]
    igualadas = [referencia] + [
        emparejar(im.reshape(-1, 3), referencia.reshape(-1, 3)).cdl.apply(im).astype(np.float32)
        for im in camaras[1:]
    ]
    peor = max(
        delta_e2000_mean(igualadas[i], igualadas[j])
        for i in range(4)
        for j in range(i + 1, 4)
    )
    _informe("T3-peor-par", peor=peor)
    assert peor < 2.0, f"el peor par se queda en {peor:.3f}"


def test_T3_tambien_con_piel_oscura(escenas_pieles):
    """Si solo funciona con pieles claras, no funciona."""
    escena = escenas_pieles[5]
    camaras = _fabricar_camaras(escena.image)
    antes = _de_medio_entre_pares(camaras)
    referencia = camaras[0]
    igualadas = [referencia] + [
        emparejar(im.reshape(-1, 3), referencia.reshape(-1, 3)).cdl.apply(im).astype(np.float32)
        for im in camaras[1:]
    ]
    despues = _de_medio_entre_pares(igualadas)
    _informe("T3-piel-oscura", antes=antes, despues=despues)
    assert antes > 8.0
    assert despues < 2.0, f"con piel oscura se queda en {despues:.3f}"


# ---------------------------------------------------------------------------
# T4 - QC de LUT
# ---------------------------------------------------------------------------


def _lut_desde_funcion(fn, size: int = 33) -> LUT3D:
    """Construye un LUT aplicando `fn` a la rejilla. Fabricado aqui a proposito:
    no uso los generadores de `core.io.lut_malos` como unica fuente, porque
    entonces estaria probando que el QC caza los LUT que el mismo autor diseno
    para que los cazara."""
    identidad = LUT3D.identity(size)
    return LUT3D(table=fn(identidad.table.astype(np.float64)).astype(np.float32))


def test_T4_la_identidad_pasa_limpia():
    """El test mas importante del QC: si da falsos positivos sobre la
    identidad, es inutil y nadie se va a fiar de el."""
    for size in (17, 33, 65):
        informe = qc_lut(LUT3D.identity(size))
        _informe(f"T4-identidad-{size}", avisos=len(informe.problemas))
        assert informe.ok, f"la identidad de {size} saca avisos: {informe.resumen()}"


def test_T4_caza_un_lut_no_monotono():
    """Subir la entrada y que baje la salida."""

    def romper(t):
        t = t.copy()
        t[10, :, :, 0] = t[9, :, :, 0] - 0.02  # el rojo retrocede en un escalon
        return t

    informe = qc_lut(_lut_desde_funcion(romper))
    codigos = informe.codigos()
    _informe("T4-no-monotono", avisos=len(informe.problemas))
    assert CODIGO_NO_MONOTONIA in codigos, f"no lo caza: {informe.resumen()}"
    assert any(p.celda is not None for p in informe.por_codigo(CODIGO_NO_MONOTONIA)), (
        "lo caza pero no dice donde, y la GUI tiene que ensenarlo"
    )


def test_T4_caza_un_escalon_que_provoca_banding():
    """Un salto brusco entre celdas contiguas: en la imagen se vera como una
    banda."""

    def romper(t):
        t = t.copy()
        t[16:, :, :, :] += 0.30  # medio cubo salta de golpe
        return t

    informe = qc_lut(_lut_desde_funcion(romper))
    _informe("T4-banding", avisos=len(informe.problemas))
    assert CODIGO_BANDING in informe.codigos(), f"no lo caza: {informe.resumen()}"


def test_T4_caza_la_excursion_de_gamut():
    """Valores de salida fuera de lo representable."""
    informe = qc_lut(_lut_desde_funcion(lambda t: t * 1.4 - 0.2))
    _informe("T4-gamut", avisos=len(informe.problemas))
    assert CODIGO_GAMUT in informe.codigos(), f"no lo caza: {informe.resumen()}"


def test_T4_los_tres_a_la_vez_y_cada_uno_con_su_nombre():
    """El criterio del encargo, tal cual: el QC tiene que cazar los tres."""
    def no_monotono(t):
        # OJO: el retroceso tiene que ser MAYOR que el paso de rejilla (1/32 con
        # tamano 33) o no invierte nada. Restar 0.02 a la celda 10 la deja en
        # 0.2925, todavia por encima de la 9 (0.28125): eso NO es un LUT no
        # monotono, y aqui me equivoque la primera vez. Se copia el valor de la
        # celda anterior y se le resta, que es lo unico que garantiza inversion.
        t = t.copy()
        t[10, :, :, 0] = t[9, :, :, 0] - 0.02
        return t

    def con_banding(t):
        t = t.copy()
        t[16:, :, :, :] += 0.30
        return t

    cazados = set()
    for fn in (no_monotono, con_banding, lambda t: t * 1.4 - 0.2):
        cazados |= set(qc_lut(_lut_desde_funcion(fn)).codigos())
    faltan = {CODIGO_NO_MONOTONIA, CODIGO_BANDING, CODIGO_GAMUT} - cazados
    _informe("T4-los-tres", cazados=len(cazados))
    assert not faltan, f"el QC no caza: {faltan}"


def test_T4_un_lut_malo_sigue_siendo_malo_despues_de_pasar_por_el_fichero(salida):
    """El QC y el .cube tienen que estar de acuerdo. Si escribir y releer
    'arregla' un LUT roto, uno de los dos miente."""
    malo = _lut_desde_funcion(lambda t: t * 1.4 - 0.2)
    ruta = escribir_cube(malo, salida / "malo.cube")
    releido = leer_cube(ruta)
    assert CODIGO_GAMUT in qc_lut(releido).codigos()


def test_T4_el_canario_de_los_ejes(salida):
    """Un LUT que solo toca el ROJO tiene que seguir tocando solo el rojo
    despues de escribirlo y releerlo. Es lo que caza que se crucen los ejes al
    pasar por el fichero, que es el fallo del que nadie se entera hasta que ve
    una imagen azul donde deberia ser roja."""
    solo_rojo = _lut_desde_funcion(lambda t: np.stack([t[..., 0] * 0.5, t[..., 1], t[..., 2]], -1))
    releido = leer_cube(escribir_cube(solo_rojo, salida / "rojo.cube"))
    prueba = np.array([[0.8, 0.8, 0.8]])
    fuera = releido.apply(prueba)[0]
    assert fuera[0] == pytest.approx(0.4, abs=1e-3), f"el rojo no es el rojo: {fuera}"
    assert fuera[1] == pytest.approx(0.8, abs=1e-3)
    assert fuera[2] == pytest.approx(0.8, abs=1e-3)


# ---------------------------------------------------------------------------
# Verificaciones de apoyo que el encargo pide junto a los cuatro
# ---------------------------------------------------------------------------


def test_el_detector_de_desajuste_caza_dos_escenas_incompatibles(
    escena_estudio, escena_exterior
):
    """Un retrato de estudio contra un exterior al sol no son comparables,
    aunque el emparejamiento produzca un numero bonito."""
    from core.analysis import huella_de_contenido

    a = a_trabajo(escena_estudio.image)
    b = a_trabajo(escena_exterior.image)
    match = emparejar(
        a.reshape(-1, 3),
        b.reshape(-1, 3),
        huellas=(huella_de_contenido(a), huella_de_contenido(b)),
    )
    assert match.content_mismatch, "no marca dos escenas que no tienen nada que ver"


def test_el_detector_NO_marca_la_misma_escena_con_otra_exposicion():
    """Lo contrario es igual de importante: decirle a Mario que no puede igualar
    dos planos que si puede igualar es como se pierde la confianza en la app."""
    from core.analysis import huella_de_contenido

    a = a_trabajo(gen.studio_scene(skin_tone_index=2).image)
    b = a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=-1.0).image)
    match = emparejar(
        a.reshape(-1, 3),
        b.reshape(-1, 3),
        huellas=(huella_de_contenido(a), huella_de_contenido(b)),
    )
    assert not match.content_mismatch, "marca desajuste sobre la misma escena a -1 EV"


def test_las_curvas_de_camara_van_contra_valores_publicados():
    """Verificacion independiente contra colour-science, que es una
    implementacion distinta de las mismas normas."""
    import colour

    x = np.linspace(0.0, 1.0, 501)
    pares = (
        ("slog3_sgamut3cine", colour.models.log_encoding_SLog3),
        ("vlog_vgamut", colour.models.log_encoding_VLog),
        ("clog3_cinemagamut", colour.models.log_encoding_CanonLog3),
        ("dlog_dgamut", colour.models.log_encoding_DJIDLog),
    )
    from core.color import log_encode

    for espacio, referencia in pares:
        mio = log_encode(x, espacio)
        suyo = np.asarray(referencia(x), dtype=np.float64)
        error = float(np.abs(mio - suyo).max())
        _informe(f"curva-{espacio}", error_max=error)
        assert error < 1e-9, f"{espacio} se desvia {error:.2e} de colour-science"


@pytest.mark.parametrize("tam", [17, LUT_SIZE_DEFAULT, 65])
def test_un_cube_sobrevive_a_la_ida_y_vuelta(salida, tam, rng):
    """Lo mas basico y lo mas facil de romper sin enterarse."""
    tabla = np.clip(LUT3D.identity(tam).table.astype(np.float64) ** 1.2, 0, 1)
    lut = LUT3D(table=tabla.astype(np.float32), title="ida y vuelta")
    releido = leer_cube(escribir_cube(lut, salida / f"t{tam}.cube"))
    assert releido.size == tam
    assert np.abs(releido.table - lut.table).max() < 1e-5
