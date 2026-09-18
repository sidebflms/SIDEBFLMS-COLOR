"""`explicar()`: recorre `catalogo.CATALOGO` y junta lo que dispara sobre un clip.

Puro, determinista, sin Resolve y sin red — el motor de reglas completo del
tutor (día 8, tarea 2.5: "sin conexión no se pierde ninguna función de color
ni ninguna explicación"). Lo único que la red puede añadir, en otra capa
completamente aparte (`gui.tutor_estilo`), es reescribir la PROSA de estas
frases — nunca decidir si una regla dispara ni con qué número.
"""

from __future__ import annotations

from core.tutor.catalogo import CATALOGO, ContextoTutor, Frase

__all__ = ["explicar"]


def explicar(contexto: ContextoTutor) -> tuple[Frase, ...]:
    """Todas las reglas del catálogo que tienen algo que decir sobre este clip,
    en el orden del catálogo (que es, a su vez, el orden de los grupos: primero
    el look aplicado, luego el material, luego el emparejamiento).

    Nunca lanza: una regla que no puede evaluarse (falta un dato en el
    contexto) simplemente no dispara — ver el `None` temprano de cada regla en
    `catalogo.py`.
    """
    frases: list[Frase] = []
    for regla in CATALOGO:
        resultado = regla.evaluar(contexto)
        if resultado is None:
            continue
        umbral = None
        if regla.umbral_nombre is not None:
            umbral = f"{regla.umbral_nombre} = {regla.umbral_valor}"
        frases.append(
            Frase(
                regla_id=regla.id,
                texto=resultado.texto,
                caracteristica=regla.caracteristica,
                valor_medido=resultado.valor_medido,
                umbral=umbral,
                validacion=regla.validacion,
                cifras_ref=regla.cifras_ref,
            )
        )
    return tuple(frases)
