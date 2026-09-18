"""La única capa del tutor que puede tocar la red, y sólo para prosa.

Tarea 2.5 del día 8: "Claude, cuando hay red, sólo reescribe la explicación
con mejor prosa y propone direcciones creativas. Sin red no se pierde
ninguna función de color ni ninguna explicación: se pierde el estilo."

Por qué vive en `gui/` y no en `core/tutor/`
------------------------------------------------
`core/tutor` no importa nada de `gui`, no abre sockets, no depende de que
haya red — es el motor de reglas completo, y `core/` en este proyecto nunca
depende de nada externo. Esta capa SÍ puede llamar a la red, así que no
puede vivir en `core/`: es presentación, no decisión. Nunca cambia si una
regla dispara ni qué número usa — sólo puede tocar el `texto`/`titulo` que
ya escribió el motor.

QUÉ HAY HOY, Y QUÉ NO
------------------------
Hoy no hay ningún servicio de reescritura conectado: no hay infraestructura
de API externa en este proyecto (ni clave, ni facturación, ni endpoint).
`reescribir_frases`/`reescribir_lecciones` son el punto de enganche para el
día que lo haya — y hoy, CON o SIN red, devuelven la entrada intacta. Eso no
es un hueco a medio hacer: es la prueba en código de la regla de la tarea
2.5. `hay_red()` existe y se usa igual, para que el día que se conecte un
reescritor de verdad, el camino de "sin red no toques nada" ya esté probado
y no haya que construirlo con prisa.
"""

from __future__ import annotations

import socket

from core.tutor import Frase, Leccion

__all__ = ["hay_red", "reescribir_frases", "reescribir_lecciones"]

#: Un servidor DNS público, sólo para el intento de conexión — no se le pide
#: nada, no se lee la respuesta. `1.1.1.1`/`8.8.8.8` son los dos de siempre;
#: se usa `8.8.8.8` porque es el que ya aparece en foros de macOS para
#: comprobar conectividad sin depender de que un dominio concreto responda.
_HOST_SONDA = "8.8.8.8"
_PUERTO_SONDA = 53
_TIMEOUT_SONDA_S = 0.5


def hay_red(host: str = _HOST_SONDA, puerto: int = _PUERTO_SONDA, timeout: float = _TIMEOUT_SONDA_S) -> bool:
    """Un intento de conexión TCP corto. Cualquier fallo —sin red, DNS roto,
    firewall, modo avión, cortafuegos corporativo— cuenta como "no hay red":
    nunca se deja que una excepción de conectividad se cuele hasta la GUI."""
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            return True
    except OSError:
        return False


def reescribir_frases(frases: tuple[Frase, ...], *, disponible: bool | None = None) -> tuple[Frase, ...]:
    """Con red Y un reescritor configurado, cambiaría `Frase.texto` por una
    versión con mejor prosa — nunca `caracteristica`/`valor_medido`/
    `umbral`/`validacion`: esos son el motor, no el estilo.

    `disponible` se puede forzar (para probar los dos caminos sin depender
    de la red real del equipo que ejecute los tests); si no se pasa, se mide
    con `hay_red()`. Hoy, en los dos casos, se devuelve la entrada tal cual:
    no hay ningún reescritor conectado todavía.
    """
    if disponible is None:
        disponible = hay_red()
    if not disponible:
        return frases
    return frases


def reescribir_lecciones(lecciones: tuple[Leccion, ...], *, disponible: bool | None = None) -> tuple[Leccion, ...]:
    """Igual que `reescribir_frases`, para las lecciones de `core.tutor.ensenar`."""
    if disponible is None:
        disponible = hay_red()
    if not disponible:
        return lecciones
    return lecciones
