"""`core.io.drx_protobuf`: el decodificador de wire format, sobre mensajes
fabricados a mano (bytes exactos, no un `.drx` real — eso es
`tests/test_io_drx.py`).
"""

from __future__ import annotations

import pytest

from core.io.drx_protobuf import ErrorProtobuf, campos, hojas_bytes, leer_varint, parsear_mensaje


def _tag(numero: int, wire_type: int) -> bytes:
    return _varint((numero << 3) | wire_type)


def _varint(v: int) -> bytes:
    out = bytearray()
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _campo_varint(numero: int, valor: int) -> bytes:
    return _tag(numero, 0) + _varint(valor)


def _campo_bytes(numero: int, datos: bytes) -> bytes:
    return _tag(numero, 2) + _varint(len(datos)) + datos


# ---------------------------------------------------------------------------
# leer_varint
# ---------------------------------------------------------------------------


def test_leer_varint_un_byte():
    assert leer_varint(bytes([5]), 0) == (5, 1)


def test_leer_varint_multibyte():
    # 300 = 0b1_0010_1100 -> codificado en 2 bytes: 0xAC 0x02
    assert leer_varint(bytes([0xAC, 0x02]), 0) == (300, 2)


def test_leer_varint_sin_terminar_lanza():
    with pytest.raises(ErrorProtobuf):
        leer_varint(bytes([0x80, 0x80]), 0)


# ---------------------------------------------------------------------------
# parsear_mensaje / campos
# ---------------------------------------------------------------------------


def test_mensaje_con_un_varint():
    msg = parsear_mensaje(_campo_varint(1, 42))
    assert len(msg) == 1
    assert msg[0].numero == 1
    assert msg[0].wire_type == 0
    assert msg[0].valor == 42


def test_mensaje_con_campos_repetidos():
    datos = _campo_varint(7, 1) + _campo_varint(7, 2) + _campo_varint(7, 3)
    msg = parsear_mensaje(datos)
    repetidos = campos(msg, 7)
    assert [c.valor for c in repetidos] == [1, 2, 3]


def test_bytes_no_protobuf_se_quedan_como_bytes_crudos():
    """Un campo bytes cuyo contenido NO es protobuf valido (p.ej. texto con un
    byte con el bit alto que rompe el varint de longitud) se queda como bytes,
    no lanza ni finge un submensaje."""
    texto = b"SIDEBFLMS/mi_look.cube"
    msg = parsear_mensaje(_campo_bytes(5, texto))
    assert msg[0].valor == texto
    assert not msg[0].es_submensaje


def test_bytes_que_SI_son_protobuf_valido_se_parsean_recursivamente():
    interior = _campo_varint(1, 99)
    msg = parsear_mensaje(_campo_bytes(2, interior))
    assert msg[0].es_submensaje
    sub = msg[0].valor
    assert campos(sub, 1)[0].valor == 99


def test_mensaje_raiz_mal_formado_lanza():
    """A diferencia de un submensaje (que se degrada a bytes en silencio), el
    mensaje de nivel superior SI lanza: si esto no es protobuf, hay que
    decirlo, no devolver una lista vacia como si no hubiera nada."""
    with pytest.raises(ErrorProtobuf):
        parsear_mensaje(b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff")


def test_wire_type_desconocido_lanza():
    # wire_type 3 (start group), no soportado
    tag = _varint((1 << 3) | 3)
    with pytest.raises(ErrorProtobuf):
        parsear_mensaje(tag)


# ---------------------------------------------------------------------------
# hojas_bytes
# ---------------------------------------------------------------------------


def test_hojas_bytes_encuentra_texto_en_cualquier_profundidad():
    ruta_lut = b"SIDEBFLMS/mi_look.cube"
    nivel3 = _campo_bytes(1, ruta_lut)
    nivel2 = _campo_bytes(9, nivel3)
    nivel1 = _campo_varint(1, 5) + _campo_bytes(9, nivel2)
    msg = parsear_mensaje(nivel1)
    hojas = hojas_bytes(msg)
    assert ruta_lut in hojas


def test_hojas_bytes_vacio_sin_hojas():
    msg = parsear_mensaje(_campo_varint(1, 1) + _campo_varint(2, 2))
    assert hojas_bytes(msg) == ()
