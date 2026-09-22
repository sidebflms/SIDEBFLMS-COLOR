"""QC de LUT.

EL TEST QUE MANDA es `test_la_identidad_pasa_limpia`. Un QC que se inventa
avisos sobre un LUT identidad no sirve para nada: la GUI se llenaría de ruido y
Mario dejaría de mirarlos en dos días. Si tocas un umbral en `core/io/qc.py` y
este test se pone rojo, el umbral está mal, no el test.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import CDL, LUT3D
from core.io import (
    CODIGO_BANDING,
    CODIGO_CANALES_INVERTIDOS,
    CODIGO_GAMUT,
    CODIGO_LUT_PLANO,
    CODIGO_NO_FINITO,
    CODIGO_NO_MONOTONIA,
    MAX_PROBLEMAS_POR_CODIGO,
    catalogo_luts_malos,
    lut_con_banding,
    lut_con_nan,
    lut_desde_curvas,
    lut_fuera_de_gamut,
    lut_no_monotono,
    lut_plano,
    lut_solo_rojo,
    qc_lut,
)


def _lut_de_funcion(n: int, fn) -> LUT3D:
    """Aplica `fn` a la rejilla identidad y recorta a 0..1. Es la forma en que
    el agente F va a fabricar LUT de verdad, así que es lo que hay que probar."""
    ident = np.asarray(LUT3D.identity(n).table, dtype=np.float64)
    return LUT3D(table=np.clip(fn(ident), 0.0, 1.0).astype(np.float32))


# ---------------------------------------------------------------------------
# Falsos positivos: lo que NO puede avisar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [2, 17, 33, 65])
def test_la_identidad_pasa_limpia(size):
    """EL test del módulo. Ni un aviso, de ningún tipo, en ningún tamaño."""
    informe = qc_lut(LUT3D.identity(size))
    assert informe.problemas == (), informe.resumen()
    assert informe.ok
    assert not informe.hay_errores
    assert informe.resumen().endswith("limpio.")


def test_un_lut_que_solo_toca_el_rojo_pasa_limpio():
    assert qc_lut(lut_solo_rojo(33, ganancia=0.5)).ok


@pytest.mark.parametrize("size", [17, 33, 65])
def test_una_curva_en_s_de_contraste_pasa_limpia(size):
    """Lo que hace un colorista todos los días: subir contraste con una S."""
    assert qc_lut(_lut_de_funcion(size, lambda x: x * x * (3 - 2 * x))).ok


@pytest.mark.parametrize("size", [17, 33, 65])
def test_un_cdl_realista_convertido_a_lut_pasa_limpio(size):
    cdl = CDL(
        slope=(1.05, 0.98, 0.93),
        offset=(0.01, 0.0, -0.005),
        power=(0.95, 1.0, 1.08),
        saturation=1.15,
    )
    assert qc_lut(_lut_de_funcion(size, cdl.apply)).ok


def test_un_lut_que_desatura_no_cuenta_como_ejes_cambiados():
    """Un LUT monocromo mueve los tres canales de salida con los tres de
    entrada por igual. El detector de ejes invertidos NO puede confundirlo con
    un rojo y un azul cambiados de sitio."""
    luma = np.array([0.2126, 0.7152, 0.0722])
    lut = _lut_de_funcion(33, lambda x: np.repeat((x @ luma)[..., None], 3, axis=-1))
    assert CODIGO_CANALES_INVERTIDOS not in qc_lut(lut).codigos()


# ---------------------------------------------------------------------------
# Verdaderos positivos: cada LUT roto saca SU código y sólo el suyo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", sorted(catalogo_luts_malos(5)))
def test_cada_lut_malo_saca_su_codigo_y_solo_el_suyo(codigo):
    """Los generadores de `core/io/lut_malos.py` están calibrados para romper
    UNA cosa. Si este test empieza a fallar es que alguien ha cambiado un
    parámetro por defecto y el LUT ya no prueba lo que dice probar."""
    lut = catalogo_luts_malos(17)[codigo]
    informe = qc_lut(lut)
    assert informe.codigos() == (codigo,), informe.resumen()
    assert not informe.ok


def test_la_no_monotonia_dice_que_celda_y_que_eje():
    p = qc_lut(lut_no_monotono(17, eje=1)).por_codigo(CODIGO_NO_MONOTONIA)[0]
    assert p.gravedad == "error"
    assert p.eje == 1 and p.canal == 1
    assert p.celda is not None and p.celda[1] == 7  # la celda de antes del hundimiento
    assert p.valor < 0
    assert "verde" in p.mensaje and "BAJA" in p.mensaje


def test_la_no_monotonia_se_caza_en_los_tres_ejes():
    for eje in (0, 1, 2):
        problemas = qc_lut(lut_no_monotono(17, eje=eje)).por_codigo(CODIGO_NO_MONOTONIA)
        assert problemas and all(p.eje == eje for p in problemas)


def test_el_banding_dice_donde_esta_el_escalon():
    p = qc_lut(lut_con_banding(17, eje=2, salto=0.3)).por_codigo(CODIGO_BANDING)[0]
    assert p.gravedad == "aviso"
    assert p.eje == 2 and p.canal == 2
    # El escalón está entre la celda 7 y la 8 (`lut_con_banding` suma el salto
    # a partir de `size // 2`), así que las dos son culpables y se avisa de las
    # dos; la primera que sale es la 7.
    assert p.celda is not None and p.celda[2] == 7
    celdas = {q.celda[2] for q in qc_lut(lut_con_banding(17, eje=2)).por_codigo(CODIGO_BANDING)}
    assert celdas == {7, 8}
    assert "banda" in p.mensaje


def test_un_escalon_pequeno_no_se_marca_como_banding():
    """El umbral tiene dos patas y la absoluta es la que evita el ruido: un
    escalón de 0.005 (algo más de 1/255) no se ve y no se avisa."""
    assert CODIGO_BANDING not in qc_lut(lut_con_banding(17, salto=0.005)).codigos()


def test_el_gamut_dice_por_que_lado_se_sale():
    informe = qc_lut(lut_fuera_de_gamut(17, exceso=0.25))
    problemas = informe.por_codigo(CODIGO_GAMUT)
    assert problemas
    assert all(p.gravedad == "aviso" for p in problemas)
    assert informe.metricas["minimo"] == pytest.approx(-0.25, abs=1e-5)
    assert informe.metricas["maximo"] == pytest.approx(1.25, abs=1e-5)
    assert any("por debajo de 0" in p.mensaje for p in problemas)
    assert not informe.hay_errores, "salirse de gamut es un aviso, no un error"


def test_un_nan_aislado_no_apaga_el_banding_real_del_resto_del_canal():
    """Bug real encontrado en revisión: `escala` se calculaba con `np.median`
    (no `np.nanmedian`) sobre el canal/eje ENTERO — un solo NaN en ese canal
    contaminaba `escala` a NaN, y de ahí `limite` también a NaN. Como
    `abs_d2 > NaN` es SIEMPRE False, el banding real en el RESTO del mismo
    canal (no sólo cerca del NaN) quedaba callado en silencio."""
    tabla = np.array(lut_con_banding(17, eje=2, salto=0.3).table, dtype=np.float32, copy=True)
    # El escalón de `lut_con_banding` está en las celdas 7/8 del eje 2; se
    # envenena una celda lejos de ahí, en el mismo canal (2), para que el
    # NaN no borre el propio escalón (eso ya lo cubre `test_el_nan_es_un_error`)
    # sino que sólo contamine el cálculo de escala del canal entero.
    tabla[1, 1, 1, 2] = np.nan
    informe = qc_lut(LUT3D(table=tabla, title="Banding + NaN aislado"))
    assert CODIGO_NO_FINITO in informe.codigos()
    assert CODIGO_BANDING in informe.codigos(), (
        "un NaN aislado en el canal ha apagado la deteccion de banding del resto del canal"
    )
    celdas_banding = {p.celda[2] for p in informe.por_codigo(CODIGO_BANDING)}
    assert celdas_banding == {7, 8}


def test_el_nan_es_un_error_y_dice_la_celda():
    p = qc_lut(lut_con_nan(17, celda=(3, 4, 5), canal=1)).por_codigo(CODIGO_NO_FINITO)[0]
    assert p.gravedad == "error"
    assert p.celda == (3, 4, 5) and p.canal == 1
    assert np.isnan(p.valor)


def test_el_lut_plano_es_un_error():
    informe = qc_lut(lut_plano(17, color=(0.2, 0.4, 0.6)))
    assert informe.hay_errores
    p = informe.por_codigo(CODIGO_LUT_PLANO)[0]
    assert "0.2" in p.mensaje and "aplasta" in p.mensaje


def test_los_ejes_cambiados_se_detectan():
    """El desastre que este módulo entero existe para evitar."""
    from core.io import lut_canales_invertidos

    problemas = qc_lut(lut_canales_invertidos(17)).por_codigo(CODIGO_CANALES_INVERTIDOS)
    ejes = {p.eje for p in problemas}
    assert ejes == {0, 2}, "el rojo apunta al azul y el azul al rojo"
    assert all("ejes cambiados" in p.mensaje for p in problemas)


# ---------------------------------------------------------------------------
# Límites conocidos, escritos a propósito
# ---------------------------------------------------------------------------


def test_una_gamma_fuerte_cerca_del_negro_se_marca_como_banding():
    """LÍMITE REAL, no bug. Este test documenta una decisión discutible.

    Una curva t**0.45 en una rejilla uniforme no se puede representar bien cerca
    del negro: medido sobre una rampa, un LUT de 65 puntos se desvía 11/255 de
    la curva real en los primeros pasos, y deja un quiebro de pendiente. El QC lo
    marca, y lo marca también con 65 puntos, así que "sube la resolución" no es
    el remedio: el remedio es no meter esa curva en un LUT 3D.

    Es un detector del lado sensible. Mario puede querer subir
    `UMBRAL_BANDING` o `SALTO_MINIMO_BANDING` si esto le molesta; está en
    `core/io/NOTAS.md`.
    """
    for size in (17, 33, 65):
        informe = qc_lut(_lut_de_funcion(size, lambda x: x**0.45))
        assert CODIGO_BANDING in informe.codigos(), f"tamaño {size}"
    # La gamma contraria (2.2) es suave donde importa y NO se marca.
    assert qc_lut(_lut_de_funcion(33, lambda x: x**2.2)).ok


def test_con_tamano_2_no_hay_segunda_derivada_y_no_se_busca_banding():
    """Caso frontera: el LUT legal más pequeño. No puede reventar ni avisar."""
    informe = qc_lut(LUT3D.identity(2))
    assert informe.ok
    assert informe.metricas["celdas_con_banding"] == 0.0


def test_no_se_listan_mas_problemas_de_la_cuenta_pero_si_se_cuentan():
    """Un LUT entero de NaN no puede devolver 14.739 problemas a la GUI."""
    tabla = np.full((17, 17, 17, 3), np.nan, dtype=np.float32)
    informe = qc_lut(LUT3D(table=tabla))
    listados = informe.por_codigo(CODIGO_NO_FINITO)
    assert len(listados) == MAX_PROBLEMAS_POR_CODIGO
    assert informe.metricas["no_finitos"] == 17**3 * 3


def test_el_resumen_es_una_linea_en_castellano():
    resumen = qc_lut(lut_no_monotono(17)).resumen()
    assert resumen.startswith("LUT de 17:")
    assert CODIGO_NO_MONOTONIA in resumen


def test_un_lut_con_mezcla_de_canales_fuerte_pero_sano_pasa_limpio():
    """Un tinte de verdad mezcla canales. Eso NO es un defecto."""
    n = 33
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    lut = lut_desde_curvas(t * 0.9 + 0.05, t, t * 0.8 + 0.1)
    assert qc_lut(lut).ok


# ---------------------------------------------------------------------------
# El recuento del banding (D-1 de la revisión de la ola 1)
# ---------------------------------------------------------------------------


def _lut_separable(n: int, f) -> LUT3D:
    x = np.linspace(0.0, 1.0, n)
    r, g, b = np.meshgrid(x, x, x, indexing="ij")
    return LUT3D(table=np.stack([f(r), f(g), f(b)], -1).astype(np.float32))


def test_un_escalon_es_un_escalon_y_no_doce_mil_celdas():
    """D-1. Un escalón vive en una POSICIÓN de la rejilla, pero aparece en las
    n*n líneas paralelas a ese eje. Contando celdas, un solo defecto sale como
    12.675 y la GUI le dice a Mario que el LUT está roto.

    La métrica en bruto sigue ahí (alguien la querrá), pero la que se enseña es
    el número de escalones."""
    n = 65
    lut = _lut_separable(n, lambda t: np.power(np.maximum(t, 0.0), 1.0 / 2.2))
    informe = qc_lut(lut)

    assert informe.metricas["celdas_con_banding"] == 3 * n * n  # el dato crudo
    assert informe.metricas["escalones_de_banding"] == 3  # la verdad: uno por eje
    assert len(informe.por_codigo(CODIGO_BANDING)) == 3

    p = informe.por_codigo(CODIGO_BANDING)[0]
    assert p.repeticiones == n * n
    assert "UN escalón" in p.mensaje and "líneas paralelas" in p.mensaje
    assert "pegado al negro" in p.mensaje


def test_el_resumen_habla_de_escalones_no_de_celdas():
    """Es la frase que acaba en la barra de estado. Tiene que ser verdad."""
    lut = _lut_separable(65, lambda t: np.power(np.maximum(t, 0.0), 1.0 / 2.2))
    resumen = qc_lut(lut).resumen()
    assert resumen == "LUT de 65: banding (3 escalones)."
    assert "12675" not in resumen


def test_el_resumen_usa_el_total_real_y_no_la_lista_recortada():
    """La lista de problemas está recortada a 20; el resumen NO puede decir 20
    cuando hay 14.739."""
    tabla = np.full((17, 17, 17, 3), np.nan, dtype=np.float32)
    resumen = qc_lut(LUT3D(table=tabla)).resumen()
    assert f"{17**3 * 3}" in resumen
    assert "(20 " not in resumen


def test_dos_escalones_en_el_mismo_eje_se_cuentan_como_dos():
    """Agrupar no puede tragarse escalones distintos: `lut_con_banding` deja la
    discontinuidad repartida entre dos posiciones contiguas y las dos salen."""
    informe = qc_lut(lut_con_banding(17, eje=0, salto=0.3))
    problemas = informe.por_codigo(CODIGO_BANDING)
    assert informe.metricas["escalones_de_banding"] == len(problemas) == 2
    assert {p.celda[0] for p in problemas} == {7, 8}
    assert all(p.repeticiones == 17 * 17 for p in problemas)


def test_un_escalon_en_una_sola_celda_no_se_agrupa_de_mas():
    """Contrapeso: si el defecto está en UNA celda (no separable), repeticiones
    tiene que ser 1 y no se puede inventar un grupo grande."""
    tabla = np.asarray(LUT3D.identity(17).table).copy()
    tabla[8, 3, 4, 0] += 0.5
    informe = qc_lut(LUT3D(table=tabla))
    problemas = informe.por_codigo(CODIGO_BANDING)
    assert problemas
    assert all(p.repeticiones == 1 for p in problemas)
    assert informe.metricas["celdas_con_banding"] == informe.metricas["escalones_de_banding"]


# ---------------------------------------------------------------------------
# El aviso de banding AVISA, no bloquea, y el mensaje dice por qué (A2)
# ---------------------------------------------------------------------------


def _gamma_de_salida(size: int) -> LUT3D:
    """El LUT más común que existe: la conversión a Rec.709 metida en un cubo."""
    return _lut_de_funcion(size, lambda x: x ** (1 / 2.2))


@pytest.mark.parametrize("size", [17, 33, 65])
def test_el_banding_en_sombras_se_explica_como_ESPERABLE_en_un_lut_de_salida(size):
    """Mario lo aclaró con estas palabras: si el LUT incluye la conversión a
    Rec.709, los escalones en sombras son esperables y no son un defecto.

    El detector no cambia —sigue avisando, y hace bien: está medido que el LUT
    se desvía 11/255 de la curva que dice representar incluso con 65 puntos—.
    Lo que cambia es que el mensaje ya no manda a arreglar algo que no está roto.
    """
    problemas = qc_lut(_gamma_de_salida(size)).por_codigo(CODIGO_BANDING)
    assert problemas, f"tamaño {size}: la gamma de salida tiene que seguir avisando"
    for p in problemas:
        assert "Rec.709" in p.mensaje
        assert "ESPERABLES y no son un defecto" in p.mensaje
        assert "aviso, no un error" in p.mensaje
    print(f"[A2 {size}] {problemas[0].mensaje}")


@pytest.mark.parametrize("size", [17, 33, 65])
def test_el_aviso_de_banding_es_de_gravedad_aviso_y_no_bloquea_nada(size, tmp_path):
    """Las tres formas de "no bloquea", porque decirlo en el texto no basta.

    1. `gravedad` es "aviso" en todos los problemas de banding;
    2. `hay_errores` sigue siendo False, que es lo que mira la GUI;
    3. el `.cube` se escribe y se vuelve a leer sin que nadie proteste.
    """
    lut = _gamma_de_salida(size)
    informe = qc_lut(lut)
    assert informe.codigos() == (CODIGO_BANDING,), informe.resumen()
    assert all(p.gravedad == "aviso" for p in informe.por_codigo(CODIGO_BANDING))
    assert informe.hay_errores is False

    from core.io import escribir_cube, leer_cube

    ruta = escribir_cube(lut, tmp_path / f"rec709_{size}.cube")
    assert leer_cube(ruta).size == size


def test_un_escalon_en_los_medios_NO_se_explica_como_normal():
    """El contrapeso, y es lo que hace que el aviso siga sirviendo de algo.

    Si el mensaje dijera "esto es normal" en todos los casos, quien lo lea deja
    de mirarlos. Un escalón en mitad del rango no es el achatamiento de una
    gamma de salida y el texto tiene que decir lo contrario que el de sombras.
    """
    problemas = qc_lut(lut_con_banding(17, eje=2, salto=0.3)).por_codigo(CODIGO_BANDING)
    assert problemas
    for p in problemas:
        assert "no está pegado al negro" in p.mensaje
        assert "Merece un vistazo" in p.mensaje
        assert "Rec.709" not in p.mensaje
        assert p.gravedad == "aviso"  # sigue sin bloquear: es un aviso, no un error
    print(f"[A2 medios] {problemas[0].mensaje}")


def test_el_mensaje_no_dice_que_haya_miles_de_bandas_cuando_hay_una():
    """Lo de D-1, pero mirando el texto y no las métricas: el aviso tiene que
    decir que es UN escalón repetido, no 1.089 defectos."""
    p = qc_lut(_gamma_de_salida(33)).por_codigo(CODIGO_BANDING)[0]
    assert "Es UN escalón, no 1089" in p.mensaje
    assert p.repeticiones == 33 * 33


def test_donde_esta_la_frontera_entre_sombras_y_medios():
    """`UMBRAL_SOMBRAS` decide la REDACCIÓN, no la detección.

    Un escalón deja dos quiebros de pendiente, uno a cada lado, así que este LUT
    de 33 da dos avisos: uno en la celda 4 (nivel de entrada 4/32 = 0,125, justo
    dentro de sombras) y otro en la 5 (5/32 = 0,156, ya fuera). O sea que la
    frontera se prueba con un solo LUT y con los dos textos a la vez.
    """
    from core.io import UMBRAL_SOMBRAS

    assert UMBRAL_SOMBRAS == 0.125
    tabla = np.asarray(LUT3D.identity(33).table, dtype=np.float64).copy()
    tabla[5:, :, :, 0] += 0.3
    informe = qc_lut(LUT3D(table=np.clip(tabla, 0, 1.3).astype(np.float32)))

    por_celda = {
        p.celda[0]: ("Rec.709" in p.mensaje)
        for p in informe.por_codigo(CODIGO_BANDING)
        if p.eje == 0
    }
    print(f"[frontera] celda -> se explica como sombras: {por_celda}")
    assert por_celda == {4: True, 5: False}


def test_cambiar_el_umbral_de_sombras_no_cambia_lo_que_se_detecta():
    """Que sea sólo de redacción no es una promesa: se comprueba.

    `UMBRAL_SOMBRAS` no es un parámetro de `qc_lut`, así que si alguien lo
    convirtiera en uno de detección este test se enteraría: el número de
    escalones de la gamma de salida es el mismo que estaba medido antes de
    tocar el mensaje (3, uno por eje, en 17, 33 y 65).
    """
    for size in (17, 33, 65):
        informe = qc_lut(_gamma_de_salida(size))
        assert informe.metricas["escalones_de_banding"] == 3.0, size
        assert informe.metricas["celdas_con_banding"] == 3.0 * size * size, size


# ---------------------------------------------------------------------------
# `clasificacion=` (día 7): monotonía por clase. Sólo mecánica — el VALOR de
# `TOL_MONOTONIA_LOOK` se calibra aparte contra material real, ver
# `CIFRAS.md` y `BITACORA.md` del día 7.
# ---------------------------------------------------------------------------


def test_sin_clasificacion_el_comportamiento_no_cambia():
    """`clasificacion=None` (el valor por defecto) tiene que dar EXACTAMENTE
    lo mismo que antes de que existiera el parámetro: nadie que ya llamaba a
    `qc_lut(lut)` puede ver cambiar el resultado por esto."""
    roto = lut_no_monotono(17, caida=0.02)
    con_none = qc_lut(roto, clasificacion=None)
    sin_parametro = qc_lut(roto)
    assert con_none.problemas == sin_parametro.problemas
    assert CODIGO_NO_MONOTONIA in con_none.codigos()


def test_clasificacion_conversion_es_igual_de_estricta_que_sin_clasificacion():
    roto = lut_no_monotono(17, caida=0.02)
    con_conversion = qc_lut(roto, clasificacion="conversion")
    sin_parametro = qc_lut(roto)
    assert con_conversion.problemas == sin_parametro.problemas


def test_clasificacion_look_usa_una_tolerancia_distinta_y_parametrizable():
    """No se fija el valor calibrado de TOL_MONOTONIA_LOOK aquí — sólo que el
    parámetro `tol_monotonia_look` de `qc_lut` es el que de verdad decide,
    para un LUT clasificado como "look". Con una tolerancia mayor que la
    caída real, el defecto deja de marcarse; con una menor, sigue marcado."""
    roto = lut_no_monotono(17, caida=0.02)
    informe_laxo = qc_lut(roto, clasificacion="look", tol_monotonia_look=0.05)
    assert CODIGO_NO_MONOTONIA not in informe_laxo.codigos()

    informe_estricto = qc_lut(roto, clasificacion="look", tol_monotonia_look=0.005)
    assert CODIGO_NO_MONOTONIA in informe_estricto.codigos()


def test_clasificacion_look_no_toca_los_demas_detectores():
    """El parámetro sólo mueve la tolerancia de monotonía: un LUT con banding
    o gamut fuera de rango los sigue disparando igual, esté clasificado como
    sea."""
    con_banding = lut_con_banding(17)
    informe_conversion = qc_lut(con_banding, clasificacion="conversion")
    informe_look = qc_lut(con_banding, clasificacion="look")
    assert CODIGO_BANDING in informe_conversion.codigos()
    assert CODIGO_BANDING in informe_look.codigos()


# ---------------------------------------------------------------------------
# Segunda ronda de tests de mecánica, escrita por el agente que calibró el
# valor real de `TOL_MONOTONIA_LOOK` (día 7) — cobertura independiente del
# mismo mecanismo, no duplicado: usa `lut_no_monotono(eje=...)` explícito y
# comprueba además que `clasificacion` no se cuela en el aviso de banding
# cuando los dos defectos conviven en el mismo LUT, en canales distintos.
#
# Las cifras de aquí (0.03 de caída, tol_monotonia=0.02, tol_monotonia_look=
# 0.05/0.005) son ejemplos ARBITRARIOS elegidos sólo para que el mecanismo se
# vea con margen a los dos lados: no son el valor real calibrado. Ese vive en
# `core.umbrales.TOL_MONOTONIA_LOOK`, medido contra material real y explicado
# en `tests/test_io_qc_reales.py` y `CIFRAS.md` §19.
# ---------------------------------------------------------------------------


def test_sin_clasificacion_o_conversion_se_comporta_igual_que_antes():
    """`clasificacion=None` (el valor por defecto, el de siempre) y
    `clasificacion="conversion"` usan `tol_monotonia`, ni un poco de
    `tol_monotonia_look`. Los tres informes -sin pasar `clasificacion`,
    pasando `None` a propósito y pasando "conversion"- salen IDÉNTICOS."""
    lut = lut_no_monotono(17, eje=0, caida=0.03)
    sin_clasificar = qc_lut(lut, tol_monotonia=0.02)
    con_none = qc_lut(lut, clasificacion=None, tol_monotonia=0.02)
    con_conversion = qc_lut(lut, clasificacion="conversion", tol_monotonia=0.02)
    assert CODIGO_NO_MONOTONIA in sin_clasificar.codigos()
    assert sin_clasificar.problemas == con_none.problemas
    assert sin_clasificar.problemas == con_conversion.problemas


def test_clasificacion_look_usa_tol_monotonia_look_y_no_tol_monotonia():
    """El mismo LUT (una caída de 0.03) sólo con `clasificacion="look"`:
    con `tol_monotonia_look=0.05` (más ancho que la caída) NO se caza, y con
    `tol_monotonia_look=0.005` (más estrecho) SÍ. `tol_monotonia=0.02` viaja
    en las dos llamadas y no cambia nada: en la rama "look" no se usa."""
    lut = lut_no_monotono(17, eje=0, caida=0.03)
    relajado = qc_lut(lut, clasificacion="look", tol_monotonia=0.02, tol_monotonia_look=0.05)
    estricto = qc_lut(lut, clasificacion="look", tol_monotonia=0.02, tol_monotonia_look=0.005)
    assert CODIGO_NO_MONOTONIA not in relajado.codigos(), relajado.resumen()
    assert CODIGO_NO_MONOTONIA in estricto.codigos()


def test_clasificacion_solo_toca_monotonia_y_ningun_otro_detector():
    """Un LUT con banding Y una caída de monotonía a la vez (en canales
    distintos, para que no se pisen): cambiar `clasificacion` no mueve ni una
    coma del aviso de banding, sólo decide si aparece `no_monotonia`."""
    tabla = np.asarray(lut_con_banding(17, eje=1, salto=0.3).table, dtype=np.float64).copy()
    # Hundimiento de 0.03 en el canal rojo (eje 0), que `lut_con_banding` deja
    # intacto porque su escalón vive en el eje 1 (verde): los dos defectos no
    # se pisan.
    tabla[8:, :, :, 0] = np.minimum(tabla[8:, :, :, 0], tabla[7, :, :, 0] - 0.03)
    lut = LUT3D(table=np.clip(tabla, 0.0, 1.0).astype(np.float32))

    estricto = qc_lut(lut, tol_monotonia=0.02)
    relajado = qc_lut(lut, clasificacion="look", tol_monotonia=0.02, tol_monotonia_look=0.05)

    assert estricto.por_codigo(CODIGO_BANDING) == relajado.por_codigo(CODIGO_BANDING)
    assert CODIGO_NO_MONOTONIA in estricto.codigos()
    assert CODIGO_NO_MONOTONIA not in relajado.codigos()
