"""`core.looks.generador`: cada parámetro en su sitio, con casos calculados a
mano — no es una calibración de "este es el look correcto" (ver
`SUPUESTOS.md` fila I2, ninguno de los presets está validado por un
colorista todavía).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.io import clasificar_lut, escribir_cube, leer_cube, qc_lut
from core.io.biblioteca import sembrar_desde_carpeta
from core.looks import PRESETS, ParametrosLook, VentanaSecundaria, generar_look, sembrar_generados
from core.reverse.relleno import rejilla_de_entradas

N = 9  # rejilla pequeña: estos tests miran la mecánica, no el aspecto final


def test_parametros_por_defecto_dan_la_identidad():
    lut = generar_look(ParametrosLook(), n=N)
    np.testing.assert_array_equal(lut.table, rejilla_de_entradas(N).astype(np.float32))


def test_es_determinista():
    parametros = PRESETS["teal_naranja_clasico"]
    a = generar_look(parametros, n=N)
    b = generar_look(parametros, n=N)
    np.testing.assert_array_equal(a.table, b.table)


def test_solo_contraste_no_toca_el_pivote():
    """El pivote es, por definición, el punto que la curva no mueve."""
    n = 33
    idx = 13  # el pivote se elige EXACTO sobre un punto de la rejilla (13/32)
    pivote = idx / (n - 1)
    parametros = ParametrosLook(pivote_contraste=pivote, fuerza_contraste=0.3)
    lut = generar_look(parametros, n=n)
    entradas = rejilla_de_entradas(n)
    np.testing.assert_allclose(
        lut.table[idx, idx, idx], entradas[idx, idx, idx], atol=1e-6
    )


def test_tinte_de_sombras_no_toca_las_luces():
    # El empuje es proporcional al margen disponible hacia el límite del
    # canal (0 o 1, según el signo) -- ver _empuje_por_zona. Con una celda
    # muy oscura (luma 0.0625) el canal que se empuja hacia abajo (azul) ya
    # casi no tiene margen: se elige una celda con luma media (0.25) dentro
    # de la zona para que ambos empujes, el que sube y el que baja, tengan
    # margen real que medir.
    sombras = (0.1, 0.0, -0.1)
    parametros = ParametrosLook(tinte_sombras=sombras, zona_sombras=(0.0, 0.6))
    lut = generar_look(parametros, n=17)
    entradas = rejilla_de_entradas(17)

    celda_sombra_con_margen = (4, 4, 4)  # luma = 4/16 = 0.25, dentro de la zona
    dif_sombra = lut.table[celda_sombra_con_margen] - entradas[celda_sombra_con_margen]
    assert dif_sombra[0] > 0.01
    assert dif_sombra[2] < -0.01

    # Celda claramente en luces: no la toca la zona de sombras (0.0..0.6).
    np.testing.assert_allclose(lut.table[-1, -1, -1], entradas[-1, -1, -1], atol=1e-4)


def test_tinte_de_luces_no_toca_las_sombras():
    # El empuje es proporcional al margen hacia 1.0 (ver _empuje_por_zona):
    # ni la celda mas clara de todas (margen cero, el empuje se recortaria a
    # 0 sin decir nada) ni una celda justo encima de la zona (poco margen)
    # sirven para medir el empuje -- se usa una celda de luma media con
    # margen real.
    luces = (0.0, 0.1, 0.0)
    parametros = ParametrosLook(tinte_luces=luces, zona_luces=(0.2, 0.4))
    lut = generar_look(parametros, n=17)
    entradas = rejilla_de_entradas(17)

    celda_clara_con_margen = (8, 8, 8)  # luma = 8/16 = 0.5, por encima de la zona, con margen
    dif_luz = lut.table[celda_clara_con_margen] - entradas[celda_clara_con_margen]
    assert dif_luz[1] > 0.04

    np.testing.assert_allclose(lut.table[0, 0, 0], entradas[0, 0, 0], atol=1e-4)


def test_compresion_de_croma_alta_no_toca_los_neutros():
    """Un gris no tiene croma que comprimir: nada que restar de él."""
    parametros = ParametrosLook(compresion_croma_alta=0.5, zona_croma_alta=(0.0, 0.3))
    lut = generar_look(parametros, n=9)
    entradas = rejilla_de_entradas(9)
    for i in range(9):
        np.testing.assert_allclose(lut.table[i, i, i], entradas[i, i, i], atol=1e-5)


def test_compresion_de_croma_alta_reduce_la_distancia_a_la_luma():
    parametros_sin = ParametrosLook()
    parametros_con = ParametrosLook(compresion_croma_alta=0.8, zona_croma_alta=(0.0, 1.0))
    sin = generar_look(parametros_sin, n=9).table
    con = generar_look(parametros_con, n=9).table
    luma = np.array([0.2126, 0.7152, 0.0722])
    d_sin = np.linalg.norm(sin - (sin @ luma)[..., None], axis=-1)
    d_con = np.linalg.norm(con - (con @ luma)[..., None], axis=-1)
    # En las celdas con croma de verdad, la version comprimida esta mas cerca
    # de su propia luma.
    con_croma = d_sin > 0.05
    assert con_croma.any(), "no hay ninguna celda con croma en esta rejilla tan pequeña"
    assert (d_con[con_croma] <= d_sin[con_croma] + 1e-6).all()


def test_una_secundaria_solo_toca_su_ventana_de_matiz():
    """Naranjas (centro 45°) con saturacion +1 no debería mover los azules
    (centro -60°, la ventana contraria en el plano oponente)."""
    naranjas = VentanaSecundaria(
        nombre="naranjas", centro_grados=45.0, ancho_grados=20.0, desplazamiento_saturacion=1.0
    )
    parametros = ParametrosLook(secundarias=(naranjas,))
    lut = generar_look(parametros, n=17)
    entradas = rejilla_de_entradas(17)

    # Una celda azulada de verdad (poco rojo/verde, mucho azul) esta lejos de
    # los 45 grados de la ventana de naranjas.
    azul_idx = (2, 2, 14)
    np.testing.assert_allclose(lut.table[azul_idx], entradas[azul_idx], atol=1e-4)


def test_una_ventana_secundaria_sin_efecto_es_un_no_op():
    ventana_vacia = VentanaSecundaria(nombre="nada", centro_grados=0.0, ancho_grados=30.0)
    lut = generar_look(ParametrosLook(secundarias=(ventana_vacia,)), n=N)
    np.testing.assert_array_equal(lut.table, rejilla_de_entradas(N).astype(np.float32))


@pytest.mark.parametrize("clave", sorted(PRESETS))
def test_cada_preset_es_un_lut3d_valido(clave):
    lut = generar_look(PRESETS[clave], n=17)
    assert lut.size == 17
    assert np.isfinite(lut.table).all()
    assert lut.table.min() >= 0.0 and lut.table.max() <= 1.0


@pytest.mark.parametrize("clave", sorted(PRESETS))
def test_cada_preset_clasifica_como_look_no_como_conversion(clave):
    """Si un preset saliera clasificado "conversion", es que sus parametros
    son tan suaves que no tiñen el gris neutro — no séria un look de verdad."""
    lut = generar_look(PRESETS[clave], n=17)
    assert clasificar_lut(lut) == "look", f"{clave} no tiñe el neutro lo suficiente para ser un look"


@pytest.mark.parametrize("clave", sorted(PRESETS))
def test_cada_preset_pasa_el_qc_sin_errores(clave):
    """Avisos (banding, gamut) son aceptables en un look — errores (no
    monotono, no finito) no: un preset roto no debería llegar a la biblioteca."""
    lut = generar_look(PRESETS[clave], n=17)
    informe = qc_lut(lut, clasificacion="look")
    assert not informe.hay_errores, informe.resumen()


@pytest.mark.parametrize("clave", sorted(PRESETS))
def test_cada_preset_sobrevive_a_escribir_y_releer_un_cube(clave, tmp_path):
    """El generador tiene que producir algo que de verdad se pueda meter en
    la biblioteca por el camino ya existente — no un objeto que solo vive en
    memoria."""
    lut = generar_look(PRESETS[clave], n=17)
    ruta = escribir_cube(lut, tmp_path / f"{clave}.cube")
    releido = leer_cube(ruta)
    np.testing.assert_allclose(releido.table, lut.table, atol=1e-5)


def test_sembrar_generados_escribe_un_cube_por_preset(tmp_path):
    rutas = sembrar_generados(tmp_path, n=9)
    assert len(rutas) == len(PRESETS)
    assert {r.name for r in rutas} == {f"{clave}.cube" for clave in PRESETS}
    for ruta in rutas:
        assert ruta.is_file()


def test_sembrar_generados_es_determinista_en_el_orden(tmp_path):
    d1, d2 = tmp_path / "a", tmp_path / "b"
    r1 = sembrar_generados(d1, n=5)
    r2 = sembrar_generados(d2, n=5)
    assert [r.name for r in r1] == [r.name for r in r2]


def test_lo_sembrado_lo_recoge_sembrar_desde_carpeta_de_verdad(tmp_path):
    """El punto entero de `sembrar_generados`: que lo generado entre en la
    biblioteca de la app por el camino que ya existe, sin cableado especial."""
    sembrar_generados(tmp_path, n=9)
    biblioteca = sembrar_desde_carpeta(tmp_path)
    assert {p.nombre for p in biblioteca} == set(PRESETS)
    assert all(p.clasificacion == "look" for p in biblioteca)
