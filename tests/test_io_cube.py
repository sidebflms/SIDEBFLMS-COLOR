"""`.cube`: ida y vuelta, y sobre todo LOS EJES.

Si en este fichero hay un test que importa más que los demás es
`test_ida_y_vuelta_un_lut_que_solo_toca_el_rojo`. Todo lo demás es higiene.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from core.contracts import LUT3D, LUT_SIZES_SOPORTADOS
from core.io import (
    LUT_SIZE_MAX_LECTURA,
    ErrorFormatoCube,
    cube_a_texto,
    cube_desde_texto,
    escribir_cube,
    leer_cube,
    lut_solo_rojo,
    orden_fichero_desde_tabla,
    tabla_desde_orden_fichero,
)

es_root = os.geteuid() == 0


# ---------------------------------------------------------------------------
# LOS EJES (convención 4). Lo demás puede fallar; esto no.
# ---------------------------------------------------------------------------


def test_ida_y_vuelta_un_lut_que_solo_toca_el_rojo(tmp_path):
    """EL test del módulo.

    Se fabrica un LUT que sólo altera el rojo (lo baja a la mitad) y deja el
    verde y el azul intactos. Se escribe, se lee, y tiene que seguir alterando
    el ROJO. Si alguien se equivoca con `transpose(2, 1, 0, 3)` en cualquiera de
    los dos lados, el LUT vuelve tocando el azul y aquí se ve.
    """
    original = lut_solo_rojo(17, ganancia=0.5)
    vuelto = leer_cube(escribir_cube(original, tmp_path / "solo_rojo.cube"))

    assert np.array_equal(original.table, vuelto.table)

    # Y ahora la prueba de verdad, aplicándolo a un color: el rojo puro baja a
    # la mitad, el azul puro no se entera.
    rojo = vuelto.apply(np.array([[1.0, 0.0, 0.0]]))[0]
    azul = vuelto.apply(np.array([[0.0, 0.0, 1.0]]))[0]
    assert rojo == pytest.approx([0.5, 0.0, 0.0], abs=1e-6)
    assert azul == pytest.approx([0.0, 0.0, 1.0], abs=1e-6)


def test_en_el_fichero_el_rojo_es_el_que_varia_mas_rapido(tmp_path):
    """La otra mitad de la convención 4, mirada en el texto del fichero."""
    lut = LUT3D.identity(3)
    ruta = escribir_cube(lut, tmp_path / "ident3.cube", decimales=3)
    datos = [
        [float(x) for x in linea.split()]
        for linea in ruta.read_text().splitlines()
        if linea and not linea[0].isalpha()
    ]
    # Las tres primeras líneas recorren el ROJO con verde y azul a cero.
    assert datos[0] == [0.0, 0.0, 0.0]
    assert datos[1] == [0.5, 0.0, 0.0]
    assert datos[2] == [1.0, 0.0, 0.0]
    # La cuarta ya sube el verde, y hay que llegar a la novena para el azul.
    assert datos[3] == [0.0, 0.5, 0.0]
    assert datos[9] == [0.0, 0.0, 0.5]


def test_la_permutacion_de_ejes_es_involutiva():
    """`transpose(2,1,0,3)` aplicada dos veces es la identidad. Si algún día
    alguien la cambia por `(1,2,0,3)` o similar, esto se cae."""
    tabla = np.arange(4 * 4 * 4 * 3, dtype=np.float32).reshape(4, 4, 4, 3)
    vuelta = tabla_desde_orden_fichero(orden_fichero_desde_tabla(tabla), 4)
    assert np.array_equal(tabla, vuelta)


def test_un_cube_leido_con_los_ejes_cambiados_se_notaria():
    """Comprobación de que el test de arriba no es tautológico: si el lector
    usara `reshape` a secas (sin transponer), el LUT saldría distinto."""
    lut = lut_solo_rojo(5, ganancia=0.5)
    plano = orden_fichero_desde_tabla(lut.table)
    mal = plano.reshape(5, 5, 5, 3)  # el error clásico
    assert not np.array_equal(mal, lut.table)


# ---------------------------------------------------------------------------
# Ida y vuelta normal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [2, *LUT_SIZES_SOPORTADOS])
def test_ida_y_vuelta_identidad(tmp_path, size):
    lut = LUT3D.identity(size)
    vuelto = leer_cube(escribir_cube(lut, tmp_path / f"ident{size}.cube"))
    assert vuelto.size == size
    assert np.abs(vuelto.table - lut.table).max() < 1e-6


def test_ida_y_vuelta_exacta_en_modo_exacto(tmp_path, rng):
    """Con `decimales=None` la tabla vuelve bit a bit, incluso con valores
    minúsculos donde 9 decimales no llegarían."""
    tabla = rng.random((9, 9, 9, 3)).astype(np.float32)
    tabla[0, 0, 0] = [1e-7, 1e-12, 0.0]
    tabla[1, 2, 3] = [12.3456789, -0.5, 1.0000001]
    lut = LUT3D(table=tabla)
    vuelto = leer_cube(escribir_cube(lut, tmp_path / "exacto.cube", decimales=None))
    assert np.array_equal(vuelto.table, tabla)


def test_se_conservan_titulo_y_dominio(tmp_path):
    lut = LUT3D(
        table=LUT3D.identity(4).table,
        domain_min=(-0.1, -0.2, -0.3),
        domain_max=(1.5, 2.0, 1.25),
        title="Un look de Mario",
    )
    vuelto = leer_cube(escribir_cube(lut, tmp_path / "t.cube"))
    assert vuelto.title == "Un look de Mario"
    assert vuelto.domain_min == pytest.approx((-0.1, -0.2, -0.3))
    assert vuelto.domain_max == pytest.approx((1.5, 2.0, 1.25))


def test_el_fichero_es_como_lo_quiere_resolve(tmp_path):
    ruta = escribir_cube(LUT3D.identity(4), tmp_path / "r.cube")
    crudo = ruta.read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "no puede llevar BOM"
    assert b"\r" not in crudo, "saltos de línea Unix, no CRLF"
    crudo.decode("ascii")  # tiene que ser ASCII puro
    texto = crudo.decode("ascii")
    pos_size = texto.index("LUT_3D_SIZE")
    pos_datos = texto.index("\n0.000000 0.000000 0.000000")
    assert pos_size < pos_datos, "LUT_3D_SIZE tiene que ir ANTES de los datos"
    assert texto.endswith("\n")


def test_seis_decimales_por_defecto(tmp_path):
    ruta = escribir_cube(LUT3D.identity(3), tmp_path / "d.cube")
    fila = next(x for x in ruta.read_text().splitlines() if x.startswith("0.5"))
    assert fila.split()[0] == "0.500000"


# ---------------------------------------------------------------------------
# Ficheros escritos a mano, con todas las manías del formato
# ---------------------------------------------------------------------------


def _escribe(tmp_path, nombre, texto, *, encoding="utf-8"):
    ruta = tmp_path / nombre
    ruta.write_bytes(texto.encode(encoding) if isinstance(texto, str) else texto)
    return ruta


CUBE_RARO = """\
# Un LUT de tamaño 2 escrito por alguien con mal gusto
   \t
TITLE "Raro pero legal"

LUT_3D_SIZE\t2
DOMAIN_MIN 0 0 0
DOMAIN_MAX 1 1 1

0,0,0        # comentario al final de la línea
1 0 0
0 1 0
1 1 0
0;0;1
1 0 1
0 1 1
1 1 1
"""


def test_lee_un_cube_con_separadores_y_comentarios_raros(tmp_path):
    lut = leer_cube(_escribe(tmp_path, "raro.cube", CUBE_RARO))
    assert lut.size == 2
    assert lut.title == "Raro pero legal"
    assert np.array_equal(lut.table, LUT3D.identity(2).table)


def test_lee_un_cube_con_crlf_y_con_bom(tmp_path):
    texto = CUBE_RARO.replace("\n", "\r\n")
    ruta = _escribe(tmp_path, "crlf.cube", texto, encoding="utf-8-sig")
    assert leer_cube(ruta).size == 2


def test_lut_3d_input_range_se_traduce_a_dominio(tmp_path):
    texto = "LUT_3D_SIZE 2\nLUT_3D_INPUT_RANGE -0.5 2.0\n" + "0 0 0\n" * 8
    lut = leer_cube(_escribe(tmp_path, "rango.cube", texto))
    assert lut.domain_min == pytest.approx((-0.5, -0.5, -0.5))
    assert lut.domain_max == pytest.approx((2.0, 2.0, 2.0))


def test_lut_1d_se_convierte_a_3d_y_actua_por_canal(tmp_path):
    """Decisión documentada en NOTAS.md: un LUT 1D NO es un error, se convierte.

    La curva del rojo baja a la mitad, las otras dos son la identidad: el cubo
    resultante tiene que hacer exactamente eso.
    """
    n = 33
    t = np.linspace(0.0, 1.0, n)
    lineas = "".join(f"{r * 0.5} {g} {b}\n" for r, g, b in zip(t, t, t, strict=True))
    ruta = _escribe(tmp_path, "curva.cube", f"LUT_1D_SIZE {n}\n{lineas}")
    lut = leer_cube(ruta, tamano_3d_desde_1d=33)
    assert lut.size == 33
    salida = lut.apply(np.array([[1.0, 1.0, 1.0], [0.6, 0.6, 0.6]]))
    assert salida[0] == pytest.approx([0.5, 1.0, 1.0], abs=1e-5)
    assert salida[1] == pytest.approx([0.3, 0.6, 0.6], abs=1e-5)


# ---------------------------------------------------------------------------
# Ficheros hostiles: cada uno tiene que dar un error LEGIBLE en castellano
# ---------------------------------------------------------------------------


def _mensaje(excinfo) -> str:
    texto = str(excinfo.value)
    # Un error de este módulo no puede ser un error crudo de Python.
    assert "invalid literal" not in texto
    assert "Traceback" not in texto
    return texto


def test_fichero_vacio(tmp_path):
    ruta = tmp_path / "vacio.cube"
    ruta.write_bytes(b"")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "vacío" in _mensaje(e)


def test_fichero_binario(tmp_path):
    ruta = tmp_path / "bin.cube"
    ruta.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "binario" in _mensaje(e)


def test_fichero_que_no_existe(tmp_path):
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(tmp_path / "ni_idea.cube")
    assert "no existe" in _mensaje(e)


def test_una_carpeta_no_es_un_cube(tmp_path):
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(tmp_path)
    assert "carpeta" in _mensaje(e)


@pytest.mark.skipif(es_root, reason="root lee cualquier cosa, el test no probaría nada")
def test_fichero_sin_permiso_de_lectura(tmp_path):
    ruta = _escribe(tmp_path, "cerrado.cube", "LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    ruta.chmod(0o000)
    try:
        with pytest.raises(ErrorFormatoCube) as e:
            leer_cube(ruta)
        assert "permiso" in _mensaje(e)
    finally:
        ruta.chmod(0o644)


def test_tamano_declarado_que_no_cuadra_faltan_lineas(tmp_path):
    ruta = _escribe(tmp_path, "corto.cube", "LUT_3D_SIZE 3\n" + "0 0 0\n" * 10)
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    msg = _mensaje(e)
    assert "27" in msg and "10" in msg


def test_tamano_declarado_que_no_cuadra_sobran_lineas(tmp_path):
    ruta = _escribe(tmp_path, "largo.cube", "LUT_3D_SIZE 2\n" + "0 0 0\n" * 20)
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "no cuadra" in _mensaje(e)


def test_valor_que_no_es_un_numero(tmp_path):
    ruta = _escribe(tmp_path, "letras.cube", "LUT_3D_SIZE 2\n" + "0 0 0\n" * 7 + "a b c\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    msg = _mensaje(e)
    assert "línea 9" in msg and "'a'" in msg


def test_nan_en_el_fichero(tmp_path):
    ruta = _escribe(tmp_path, "nan.cube", "LUT_3D_SIZE 2\n" + "0 0 0\n" * 7 + "nan 0 0\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "finito" in _mensaje(e)


def test_tamano_declarado_no_numerico(tmp_path):
    ruta = _escribe(tmp_path, "malsize.cube", "LUT_3D_SIZE treinta y tres\n0 0 0\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    msg = _mensaje(e)
    assert "entero" in msg and "treinta" in msg


@pytest.mark.parametrize("size", [0, 1, -5])
def test_tamano_demasiado_pequeno(tmp_path, size):
    ruta = _escribe(tmp_path, "peq.cube", f"LUT_3D_SIZE {size}\n0 0 0\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "entre 2 y" in _mensaje(e)


def test_tamano_gigantesco_no_reserva_memoria(tmp_path):
    """`LUT_3D_SIZE 4096` son 824 GB. El fichero pesa 40 bytes y tiene que
    fallar en microsegundos, no comerse la máquina."""
    ruta = _escribe(tmp_path, "bomba.cube", "LUT_3D_SIZE 4096\n0 0 0\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    msg = _mensaje(e)
    assert str(LUT_SIZE_MAX_LECTURA) in msg and "4096" in msg


def test_sin_palabra_clave_de_tamano(tmp_path):
    ruta = _escribe(tmp_path, "sin.cube", "0 0 0\n1 1 1\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "LUT_3D_SIZE" in _mensaje(e)


def test_palabra_clave_desconocida(tmp_path):
    ruta = _escribe(tmp_path, "rara.cube", "LUT_3D_SIZE 2\nLUT_CUATRIDIMENSIONAL 7\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "LUT_CUATRIDIMENSIONAL" in _mensaje(e)


def test_1d_y_3d_a_la_vez(tmp_path):
    ruta = _escribe(tmp_path, "ambos.cube", "LUT_3D_SIZE 2\nLUT_1D_SIZE 8\n" + "0 0 0\n" * 8)
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "a la vez" in _mensaje(e)


def test_dominio_invertido(tmp_path):
    texto = "LUT_3D_SIZE 2\nDOMAIN_MIN 1 1 1\nDOMAIN_MAX 0 0 0\n" + "0 0 0\n" * 8
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(_escribe(tmp_path, "dom.cube", texto))
    assert "dominio" in _mensaje(e)


def test_linea_de_datos_con_dos_numeros(tmp_path):
    ruta = _escribe(tmp_path, "dos.cube", "LUT_3D_SIZE 2\n" + "0 0 0\n" * 7 + "0 0\n")
    with pytest.raises(ErrorFormatoCube) as e:
        leer_cube(ruta)
    assert "3 números" in _mensaje(e)


# ---------------------------------------------------------------------------
# Escritura: casos frontera
# ---------------------------------------------------------------------------


def test_no_escribe_un_lut_con_nan(tmp_path):
    from core.io import lut_con_nan

    with pytest.raises(ErrorFormatoCube) as e:
        escribir_cube(lut_con_nan(5), tmp_path / "nan.cube")
    assert "no finitos" in _mensaje(e)
    assert not (tmp_path / "nan.cube").exists(), "no puede dejar un fichero a medias"


def test_directorio_que_no_existe_lanza_y_no_lo_crea(tmp_path):
    destino = tmp_path / "ni" / "de" / "broma" / "x.cube"
    with pytest.raises(ErrorFormatoCube) as e:
        escribir_cube(LUT3D.identity(2), destino)
    assert "no existe" in _mensaje(e)
    assert not destino.parent.exists()


def test_directorio_que_no_existe_se_crea_si_se_pide(tmp_path):
    destino = tmp_path / "si" / "por" / "favor" / "x.cube"
    escribir_cube(LUT3D.identity(2), destino, crear_directorios=True)
    assert destino.is_file()


def test_decimales_fuera_de_rango(tmp_path):
    with pytest.raises(ErrorFormatoCube):
        cube_a_texto(LUT3D.identity(2), decimales=99)


def test_el_titulo_no_puede_romper_el_fichero():
    lut = LUT3D(table=LUT3D.identity(2).table, title='mal"uso\ncon salto')
    linea = cube_a_texto(lut).splitlines()[0]
    assert linea.count('"') == 2, "el título tiene que quedar entre exactamente 2 comillas"


def test_cube_desde_texto_no_toca_el_disco():
    """La versión en memoria (la que usa el bundle) da el mismo resultado."""
    lut = LUT3D.identity(4)
    texto = cube_a_texto(lut, decimales=None)
    assert np.array_equal(cube_desde_texto(texto).table, lut.table)


def test_con_seis_decimales_la_ida_y_vuelta_NO_es_exacta():
    """Documenta el límite real: 1/3 no cabe en 6 decimales.

    No es un bug, es el formato que espera Resolve. Por eso el bundle usa
    `decimales=None` y por eso `escribir_cube` lo ofrece.
    """
    lut = LUT3D.identity(4)
    vuelto = cube_desde_texto(cube_a_texto(lut, decimales=6))
    assert not np.array_equal(vuelto.table, lut.table)
    assert np.abs(vuelto.table - lut.table).max() < 1e-6


@pytest.mark.lento
def test_un_lut_de_65_va_y_viene(tmp_path):
    lut = LUT3D.identity(65)
    vuelto = leer_cube(escribir_cube(lut, tmp_path / "g65.cube"))
    assert vuelto.size == 65
    assert np.abs(vuelto.table - lut.table).max() < 1e-6
