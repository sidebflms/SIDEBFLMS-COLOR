"""Remuestrear un LUT a otro tamaño: la opción de exportar a 65³.

LO QUE ESTE FICHERO TIENE QUE DEMOSTRAR, y es una sola cosa: que subir de 33 a
65 **no añade información**. Si un día alguien "mejora" `remuestrear_lut` y el
resultado deja de ser el mismo LUT, estos tests se ponen rojos y hay que mirar
por qué, porque el argumento entero para exportar a 65 se apoya en que el color
que sale es idéntico.

Lo secundario, pero también aquí: que 33 sigue siendo el tamaño por defecto y
que nadie acaba en un 65 sin haberlo pedido.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import CDL, LUT3D, LUT_SIZE_DEFAULT, LUT_SIZES_SOPORTADOS
from core.io import (
    CODIGO_BANDING,
    TAMANO_ENTREGA_FINAL,
    ErrorFormatoCube,
    escribir_cube,
    explicacion_remuestreo,
    leer_cube,
    qc_lut,
    rejilla_del_dominio,
    remuestrear_lut,
)


#: Un puñado de LUT que son los que Mario va a exportar de verdad: un balance
#: de CDL, una curva de contraste, la gamma de salida y la identidad.
def _lut_de_cdl(cdl: CDL, n: int = LUT_SIZE_DEFAULT) -> LUT3D:
    rejilla = rejilla_del_dominio(LUT3D.identity(n), n)
    return LUT3D(table=np.asarray(cdl.apply(rejilla), dtype=np.float32), title="balance")


def _lut_de_funcion(fn, n: int = LUT_SIZE_DEFAULT, titulo: str = "prueba") -> LUT3D:
    rejilla = rejilla_del_dominio(LUT3D.identity(n), n)
    return LUT3D(table=np.asarray(fn(rejilla), dtype=np.float32), title=titulo)


def _luts_de_verdad() -> dict[str, LUT3D]:
    return {
        "identidad": LUT3D.identity(LUT_SIZE_DEFAULT),
        "curva_en_s": _lut_de_funcion(lambda x: np.clip(x * x * (3 - 2 * x), 0, 1), titulo="s"),
        "gamma_de_salida": _lut_de_funcion(
            lambda x: np.clip(x, 0, None) ** (1 / 2.2), titulo="rec709"
        ),
        "cdl_realista": _lut_de_cdl(
            CDL(
                slope=(1.05, 0.98, 0.92),
                offset=(0.01, 0.0, -0.005),
                power=(0.95, 1.0, 1.08),
                saturation=0.9,
            )
        ),
    }


@pytest.fixture
def colores() -> np.ndarray:
    """200.000 colores repartidos por todo el cubo. Semilla fija a propósito."""
    return np.random.default_rng(7).random((200_000, 3))


# ---------------------------------------------------------------------------
# Lo importante: subir de tamaño NO añade información
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", sorted(_luts_de_verdad()))
def test_un_lut_de_33_remuestreado_a_65_da_practicamente_lo_mismo(nombre, colores):
    """La cifra medida, y por qué es tan pequeña.

    Con 65 = 2·33 − 1, los puntos de la rejilla de 65 caen exactamente sobre los
    de la de 33 y sobre sus puntos medios, y la interpolación trilineal de una
    interpolación trilineal dentro de la misma celda es la misma función. O sea
    que no es "casi igual": es igual, y lo único que separa a los dos es el
    redondeo de guardar la tabla en float32.

    Medido sobre 200.000 colores (peor caso de los cuatro LUT, el del CDL):
    **5,7e-08**, o sea 0,0000146 de un nivel de 255. La tolerancia de aquí es
    1e-6, que deja margen de sobra para el float32 y sigue siendo 30 veces más
    fina que una milésima de nivel de 8 bits: si alguien rompe el remuestreo, no
    va a fallar por 1e-6, va a fallar por mucho.
    """
    l33 = _luts_de_verdad()[nombre]
    l65 = remuestrear_lut(l33, TAMANO_ENTREGA_FINAL)
    assert l65.size == 65

    peor = float(np.abs(np.asarray(l33.apply(colores)) - np.asarray(l65.apply(colores))).max())
    print(f"[65] {nombre}: peor diferencia {peor:.3e} ({peor * 255:.7f} de 255)")
    assert peor < 1e-6, f"{nombre}: remuestrear a 65 ha cambiado el LUT en {peor}"


def test_la_cifra_que_esta_escrita_en_las_notas_es_la_que_sale(colores):
    """Contrapeso del test de arriba: fija el ORDEN DE MAGNITUD, no sólo un tope.

    `core/io/remuestreo.py` dice en su docstring que el peor caso son 5,7e-08.
    Si un día el remuestreo empezara a desviarse 1e-7 seguiría pasando el test
    anterior (que tolera 1e-6) y la cifra escrita sería mentira. Esto lo caza.
    """
    l33 = _luts_de_verdad()["cdl_realista"]
    l65 = remuestrear_lut(l33, 65)
    peor = float(np.abs(np.asarray(l33.apply(colores)) - np.asarray(l65.apply(colores))).max())
    print(f"[cifra] peor diferencia medida: {peor:.4e}")
    assert peor < 1e-7, (
        f"las NOTAS dicen 5,7e-08 y ahora salen {peor:.3e}; actualiza la cifra o mira qué ha "
        f"cambiado, pero no dejes escrito un número que no es"
    )


def test_el_lut_de_65_pasa_el_qc_igual_de_limpio_que_el_de_33():
    """Remuestrear no puede inventarse problemas de calidad.

    Cada LUT tiene que salir del QC con los mismos códigos que tenía: la gamma
    de salida sigue avisando de banding en sombras (y está bien que avise), y la
    identidad y la curva en S siguen saliendo limpias.
    """
    for nombre, l33 in sorted(_luts_de_verdad().items()):
        informe33 = qc_lut(l33)
        informe65 = qc_lut(remuestrear_lut(l33, 65))
        print(f"[qc] {nombre}: 33 -> {informe33.resumen()} | 65 -> {informe65.resumen()}")
        assert informe65.codigos() == informe33.codigos(), nombre
        assert informe65.hay_errores == informe33.hay_errores, nombre


def test_el_lut_de_65_se_escribe_y_se_vuelve_a_leer_igual(tmp_path):
    """La ida y vuelta completa: remuestrear, escribir el .cube, leerlo."""
    l33 = _luts_de_verdad()["cdl_realista"]
    l65 = remuestrear_lut(l33, 65)
    ruta = escribir_cube(l65, tmp_path / "entrega_65.cube")
    leido = leer_cube(ruta)
    assert leido.size == 65
    # Con 6 decimales la ida y vuelta no es exacta (está documentado en
    # core/io/NOTAS.md, punto 6): se comprueba con la tolerancia del formato.
    assert np.allclose(leido.table, l65.table, atol=1e-6)
    assert qc_lut(leido).hay_errores is False


def test_un_cube_de_65_pesa_ocho_veces_mas_y_eso_es_lo_UNICO_que_se_gana(tmp_path):
    """El precio, medido. Es el argumento para no hacerlo por defecto."""
    l33 = _luts_de_verdad()["cdl_realista"]
    ruta33 = escribir_cube(l33, tmp_path / "33.cube")
    ruta65 = escribir_cube(remuestrear_lut(l33, 65), tmp_path / "65.cube")
    bytes33, bytes65 = ruta33.stat().st_size, ruta65.stat().st_size
    print(f"[peso] 33 -> {bytes33 / 1024:.0f} KB | 65 -> {bytes65 / 1024 / 1024:.1f} MB")
    assert bytes65 > 7 * bytes33  # 65**3 / 33**3 = 7,6


# ---------------------------------------------------------------------------
# Que nadie acabe en 65 sin pedirlo
# ---------------------------------------------------------------------------


def test_el_tamano_por_defecto_del_proyecto_sigue_siendo_33():
    """Mario lo confirmó: 33 es el estándar de facto y no se toca.

    Si esto se pone rojo es que alguien ha cambiado `LUT_SIZE_DEFAULT`, que
    además está en `core/contracts.py` y no es de este agente.
    """
    assert LUT_SIZE_DEFAULT == 33
    assert TAMANO_ENTREGA_FINAL == 65
    assert TAMANO_ENTREGA_FINAL in LUT_SIZES_SOPORTADOS


def test_remuestrear_no_pasa_solo_hay_que_escribirlo(tmp_path):
    """No hay ningún camino en `core/io` que remuestree por su cuenta.

    O sea: escribir un `.cube` deja el tamaño que tenga el LUT, punto. Es lo que
    hace que exportar a 65 sea una decisión y no un efecto secundario.
    """
    l33 = _luts_de_verdad()["cdl_realista"]
    assert leer_cube(escribir_cube(l33, tmp_path / "x.cube")).size == 33

    import inspect

    from core.io import cube

    firma = inspect.signature(cube.escribir_cube)
    assert "tamano" not in firma.parameters and "remuestrear" not in firma.parameters, (
        "si `escribir_cube` acepta un tamaño, remuestrear deja de verse en la línea que lo "
        "pide y alguien exportará a 65 creyendo que ha ganado precisión"
    )


# ---------------------------------------------------------------------------
# Bajar SÍ pierde, y hay que poder decirlo
# ---------------------------------------------------------------------------


def test_bajar_de_33_a_17_si_pierde_y_la_explicacion_lo_dice(colores):
    """El contrapeso honesto: no todo remuestreo es gratis.

    Medido sobre la gamma de salida, bajar de 33 a 17 llega a 0,065, o sea 16,6
    niveles de 255. Ese número está escrito en `explicacion_remuestreo` y en el
    docstring del módulo, y este test lo mide de verdad.
    """
    l33 = _luts_de_verdad()["gamma_de_salida"]
    l17 = remuestrear_lut(l33, 17)
    peor = float(np.abs(np.asarray(l33.apply(colores)) - np.asarray(l17.apply(colores))).max())
    print(f"[17] gamma_de_salida: peor diferencia {peor:.4f} ({peor * 255:.1f} de 255)")
    assert peor > 0.05, "bajar de 33 a 17 tendría que perder de forma medible, y no pierde"
    assert "SÍ pierde" in explicacion_remuestreo(33, 17)
    assert "16" in explicacion_remuestreo(33, 17)


def test_la_explicacion_de_subir_dice_que_no_gana_precision():
    """Es la frase que va a leer Mario al lado del botón. Que no mienta."""
    texto = explicacion_remuestreo(33, 65)
    print(f"[texto] {texto}")
    assert "no gana precisión" in texto
    assert "el mismo LUT" in texto
    assert "8 veces" in texto  # 65**3 / 33**3 = 7,6 -> "8"


def test_remuestrear_al_mismo_tamano_no_es_un_error():
    l33 = _luts_de_verdad()["curva_en_s"]
    igual = remuestrear_lut(l33, 33)
    assert igual is not l33
    assert np.allclose(igual.table, l33.table, atol=1e-7)
    assert "nada que remuestrear" in explicacion_remuestreo(33, 33)


# ---------------------------------------------------------------------------
# Bordes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tamano", [0, 1, -5, 130, 4096])
def test_un_tamano_absurdo_se_rechaza_con_un_mensaje_en_castellano(tamano):
    with pytest.raises(ErrorFormatoCube) as exc:
        remuestrear_lut(LUT3D.identity(17), tamano)
    assert "tamaño de rejilla" in str(exc.value)


@pytest.mark.parametrize("tamano", [33.0, "65", True, None])
def test_un_tamano_que_no_es_entero_se_rechaza_en_vez_de_convertirse(tamano):
    """Igual que con los índices de nodo: aquí no se adivina.

    `int(64.9)` es 64, y un 64 silencioso donde se quería un 65 es el tipo de
    cosa que no se ve hasta que la casa de post dice que el LUT no es el que
    pidieron.
    """
    with pytest.raises(ErrorFormatoCube):
        remuestrear_lut(LUT3D.identity(17), tamano)


def test_se_respeta_el_dominio_del_lut_de_partida(colores):
    """Un LUT de dominio ancho (material log) no puede salir recortado.

    Si `rejilla_del_dominio` usara 0..1 siempre, remuestrear este LUT le
    cortaría los extremos sin decir nada, y eso es justo la clase de pérdida
    silenciosa que no puede pasar.
    """
    dmin, dmax = (-0.07, -0.07, -0.07), (1.09, 1.09, 1.09)
    base = LUT3D.identity(33)
    l33 = LUT3D(table=base.table * 0.9 + 0.05, domain_min=dmin, domain_max=dmax, title="log")
    l65 = remuestrear_lut(l33, 65)
    assert l65.domain_min == dmin and l65.domain_max == dmax

    # Y se comprueba sobre colores que se salen de 0..1, que es donde se notaría.
    fuera = colores * 1.16 - 0.07
    peor = float(np.abs(np.asarray(l33.apply(fuera)) - np.asarray(l65.apply(fuera))).max())
    print(f"[dominio] peor diferencia fuera de 0..1: {peor:.3e}")
    assert peor < 1e-6


def test_el_titulo_se_conserva_y_se_puede_cambiar():
    l33 = LUT3D.identity(33)
    l33 = LUT3D(table=l33.table, title="Look de la boda")
    assert remuestrear_lut(l33, 65).title == "Look de la boda"
    assert remuestrear_lut(l33, 65, titulo="Look de la boda (65)").title == "Look de la boda (65)"


def test_el_banding_de_la_gamma_sigue_avisando_despues_de_remuestrear():
    """Subir a 65 NO calla el aviso de sombras, y eso es correcto.

    Está medido en `core/io/NOTAS.md`: con 65 puntos el LUT sigue desviándose
    11/255 de la curva que dice representar. Si remuestrear callara el aviso,
    estaríamos escondiendo el defecto en vez de arreglarlo.
    """
    l65 = remuestrear_lut(_luts_de_verdad()["gamma_de_salida"], 65)
    informe = qc_lut(l65)
    avisos = informe.por_codigo(CODIGO_BANDING)
    assert avisos, "el aviso de banding ha desaparecido al remuestrear a 65"
    assert all(p.gravedad == "aviso" for p in avisos)
    assert informe.hay_errores is False
