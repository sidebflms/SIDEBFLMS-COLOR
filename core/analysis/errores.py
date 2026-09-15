"""Errores de `core.analysis`. Todos hablan castellano y todos heredan de
`ErrorAnalisis`, que es lo unico que la GUI tiene que capturar.

La regla: **ningun fallo previsible sale como traceback**. Un fichero que no
existe, un .txt que no es un video, ffmpeg sin instalar o un clip truncado a
mitad son cosas que pasan todos los dias en un rodaje; el usuario tiene que leer
una frase, no una pila de llamadas de Python.
"""

from __future__ import annotations


class ErrorAnalisis(RuntimeError):
    """Cualquier fallo analizando material. La GUI captura solo esto."""


class FicheroNoEncontrado(ErrorAnalisis):
    """La ruta no existe, o existe y no es un fichero."""


class FormatoNoSoportado(ErrorAnalisis):
    """El fichero existe pero no es video ni imagen que sepamos abrir."""


class ErrorFFmpeg(ErrorAnalisis):
    """ffmpeg o ffprobe han devuelto error, o el fichero esta truncado."""


class HerramientaNoDisponible(ErrorAnalisis):
    """No hay ffmpeg/ffprobe en esta maquina."""


__all__ = [
    "ErrorAnalisis",
    "ErrorFFmpeg",
    "FicheroNoEncontrado",
    "FormatoNoSoportado",
    "HerramientaNoDisponible",
]
