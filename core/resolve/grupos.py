"""Grupos de color de Resolve: SÓLO LECTURA (día 9, continuación 15, punto 5).

La app no escribe nunca en un grupo: `set_group_post_clip_lut` es la única
escritura que queda fuera de la regla de oro (un grupo no tiene versiones, no
hay nada que restaurar) y a propósito no se ha cableado en ninguna pantalla.
Lo que sí hace falta saber ANTES de aplicar: si un clip está en un grupo, y
si ese grupo trae su propio LUT en el post-clip, porque entonces se suma por
encima del look de la app y el resultado en pantalla no es el que la app
calculó, sin que nada en el grado del clip lo delate.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts import ResolveBridge, ResolveError

__all__ = ["InfoGrupo", "info_grupo_de_clip"]


@dataclass(frozen=True)
class InfoGrupo:
    nombre: str
    #: LUT del nodo 1 del post-clip del grupo, o `None` si no trae ninguno.
    look_rel: str | None

    def aviso(self) -> str:
        if self.look_rel:
            return (
                f"el clip está en el grupo de color «{self.nombre}», que trae su propio "
                f"LUT ({self.look_rel}) en el post-clip: se suma POR ENCIMA del look de "
                "la app, y el resultado en pantalla no será el que se calculó."
            )
        return (
            f"el clip está en el grupo de color «{self.nombre}»: si ese grupo tiene "
            "ajustes de grupo, se suman a los de la app."
        )


def info_grupo_de_clip(puente: ResolveBridge, clip_id: str) -> InfoGrupo | None:
    """`None` si el clip no está en ningún grupo, o si el puente no sabe de
    grupos (los dos métodos son extras fuera del Protocol) o falla al mirar:
    un aviso opcional nunca puede tumbar el plan."""
    de_clip = getattr(puente, "clip_color_group", None)
    look_de_grupo = getattr(puente, "group_post_clip_lut", None)
    if not callable(de_clip) or not callable(look_de_grupo):
        return None
    try:
        nombre = de_clip(clip_id)
        if nombre is None:
            return None
        return InfoGrupo(nombre=nombre, look_rel=look_de_grupo(nombre))
    except ResolveError:
        return None
