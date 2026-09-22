"""Parser protobuf "raw", sin `.proto`.

Blackmagic no publica el esquema del blob binario que vive dentro de un
`<Body>` de `.drx` (ver `core/io/FORMATO-DRX.md`). Lo que SÍ se puede hacer
sin el `.proto` es decodificar el *wire format* de Protocol Buffers, que es
público y estable: cada campo es un `(numero_de_campo << 3 | wire_type)`
como varint, seguido del valor según `wire_type`. Es exactamente lo que hace
`protoc --decode_raw`, y este módulo es una reimplementación mínima de eso en
Python puro, sin depender de `protoc` ni de la librería `protobuf`.

LA HEURÍSTICA DE "¿ES UN SUBMENSAJE?"
--------------------------------------
El wire format NO distingue "bytes crudos" de "un submensaje anidado": los
dos son `wire_type == 2` (length-delimited). Igual que `protoc --decode_raw`,
este módulo intenta parsear CADA campo length-delimited como un submensaje
recursivo, y sólo si eso falla (un tag con `wire_type` desconocido, o los
bytes no se consumen exactamente) lo deja como bytes/texto crudo
(`ValorCrudo`). Es una heurística, no una certeza: unos bytes que por
casualidad parecen un submensaje válido se interpretarán como tal aunque en
realidad fueran datos opacos (una imagen, un blob cifrado). Para lo que se
usa aquí — encontrar nodos y rutas de LUT — el coste de ese error es bajo: un
"submensaje" espurio simplemente no contendrá ningún string reconocible.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Campo", "ErrorProtobuf", "leer_varint", "parsear_mensaje", "campos", "hojas_bytes"]


class ErrorProtobuf(ValueError):
    """El wire format no es válido: un tag con wire_type fuera de {0,1,2,5}."""


#: `_intentar_submensaje` es recursivo (cada campo length-delimited que
#: parece un submensaje se parsea llamándose a sí mismo). Un `.drx` hostil
#: puede tener bytes que "parecen" cientos de submensajes anidados sin serlo
#: de verdad (la heurística de arriba lo admite: "un 'submensaje' espurio...
#: no contendrá ningún string reconocible", pero SÍ puede reventar la pila
#: de Python antes de llegar a esa conclusión). Un grafo de color real no
#: pasa de unos pocos niveles (nodo -> parámetros -> valores); 40 es generoso
#: de sobra y muy por debajo del límite de recursión de Python.
_PROFUNDIDAD_MAXIMA_SUBMENSAJE = 40


@dataclass(frozen=True)
class Campo:
    """Un campo del wire format. `valor` es `int` (varint/64bit/32bit como
    entero crudo), `bytes` (length-delimited que no parseó como submensaje) o
    `tuple[Campo, ...]` (length-delimited que sí parseó como submensaje)."""

    numero: int
    wire_type: int
    valor: int | bytes | tuple[Campo, ...]

    @property
    def es_submensaje(self) -> bool:
        return isinstance(self.valor, tuple)


def leer_varint(b: bytes, i: int) -> tuple[int, int]:
    """`(valor, siguiente_indice)`. Lanza `ErrorProtobuf` si se sale del buffer
    o el varint no termina en 10 bytes (el máximo de un varint de 64 bits)."""
    resultado = 0
    despl = 0
    inicio = i
    while True:
        if i >= len(b):
            raise ErrorProtobuf(f"varint sin terminar en el offset {inicio}")
        if i - inicio > 9:
            raise ErrorProtobuf(f"varint demasiado largo en el offset {inicio}")
        byte = b[i]
        resultado |= (byte & 0x7F) << despl
        i += 1
        if not (byte & 0x80):
            return resultado, i
        despl += 7


def _parsear_campos(b: bytes, profundidad: int = 0) -> tuple[Campo, ...]:
    """Parsea `b` entero como una secuencia de campos. Lanza `ErrorProtobuf`
    si algo no cuadra — es la señal que usa `_intentar_submensaje` para saber
    que estos bytes NO eran un submensaje."""
    i = 0
    n = len(b)
    out: list[Campo] = []
    while i < n:
        tag, i = leer_varint(b, i)
        numero, wire_type = tag >> 3, tag & 0x7
        if numero == 0:
            raise ErrorProtobuf("numero de campo 0: invalido")
        if wire_type == 0:
            valor, i = leer_varint(b, i)
        elif wire_type == 1:
            if i + 8 > n:
                raise ErrorProtobuf("64bit truncado")
            valor = int.from_bytes(b[i : i + 8], "little")
            i += 8
        elif wire_type == 2:
            longitud, i = leer_varint(b, i)
            if i + longitud > n:
                raise ErrorProtobuf("length-delimited truncado")
            crudo = b[i : i + longitud]
            i += longitud
            sub = _intentar_submensaje(crudo, profundidad + 1)
            valor = sub if sub is not None else crudo
        elif wire_type == 5:
            if i + 4 > n:
                raise ErrorProtobuf("32bit truncado")
            valor = int.from_bytes(b[i : i + 4], "little")
            i += 4
        else:
            raise ErrorProtobuf(f"wire_type {wire_type} no soportado (campo {numero})")
        out.append(Campo(numero=numero, wire_type=wire_type, valor=valor))
    return tuple(out)


def _intentar_submensaje(b: bytes, profundidad: int = 0) -> tuple[Campo, ...] | None:
    if not b:
        return None
    if profundidad > _PROFUNDIDAD_MAXIMA_SUBMENSAJE:
        # Ni ErrorProtobuf ni RecursionError: esto no es "el wire format esta
        # mal" (podria seguir siendolo formalmente cientos de niveles mas
        # adentro), es "dejo de intentar interpretar esto como un submensaje
        # anidado" — se degrada a bytes crudos, exactamente como cualquier
        # otro intento de submensaje que no cuaja.
        return None
    try:
        return _parsear_campos(b, profundidad)
    except ErrorProtobuf:
        return None


def parsear_mensaje(b: bytes) -> tuple[Campo, ...]:
    """Punto de entrada: parsea el mensaje de nivel superior. A diferencia de
    los submensajes (que se degradan a bytes crudos en silencio si no
    parsean), el de nivel superior SÍ lanza `ErrorProtobuf` — si esto falla,
    `b` no es protobuf en absoluto y hay que decirlo, no fingir un resultado
    vacío."""
    return _parsear_campos(b)


def campos(msg: tuple[Campo, ...], numero: int) -> tuple[Campo, ...]:
    """Todos los campos de `msg` con ese número (protobuf permite repetidos:
    así es como se representa una lista, p.ej. una lista de nodos)."""
    return tuple(c for c in msg if c.numero == numero)


def hojas_bytes(msg: tuple[Campo, ...]) -> tuple[bytes, ...]:
    """Recorre `msg` recursivamente y devuelve TODOS los `bytes` crudos de
    sus hojas (campos length-delimited que no parsearon como submensaje).

    No hace falta conocer la ruta exacta de campos para buscar algo: esto
    aplana el árbol entero, así que un cambio de estructura entre builds de
    Resolve (un campo que se mueve un nivel) no rompe la búsqueda de texto.
    """
    out: list[bytes] = []
    for c in msg:
        if isinstance(c.valor, tuple):
            out.extend(hojas_bytes(c.valor))
        elif isinstance(c.valor, bytes):
            out.append(c.valor)
    return tuple(out)
