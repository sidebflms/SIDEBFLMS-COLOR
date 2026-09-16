"""Verificador de doble conversion: la otra mitad de "ordenar la casa".

La doble conversion no da ningun error: el proyecto ya convierte el color de
entrada (gestion de color automatica) y ADEMAS hay un LUT de conversion
puesto a mano en el nodo de normalizacion. El resultado sale con mas
contraste y saturacion de la cuenta, y a simple vista solo parece "un grado
raro". Es el fallo silencioso mas comun con material mezclado (ver el
encargo del dia 5).

SIN VERIFICAR CONTRA RESOLVE REAL. Las tres heuristicas de aqui (que texto de
`color_science` cuenta como "gestion automatica", que nombre de LUT "parece"
una conversion de entrada, que `timeline_color_space` es el esperado) son la
mejor lectura disponible hasta que el probe confirme F0-8. Estan aisladas en
este modulo para que cambiarlas, cuando lleguen los datos reales, sea tocar
solo aqui.
"""

from __future__ import annotations

from core.contracts import (
    NODE_NORMALIZACION,
    AvisoGestionColor,
    ClipRef,
    DeteccionEspacio,
    NodeInfo,
    ProjectInfo,
)

__all__ = ["verificar_proyecto"]

#: Tokens (minusculas) que, en `ProjectInfo.color_science`, indican que
#: Resolve ya convierte el color de entrada por su cuenta. SIN VERIFICAR.
_TOKENS_GESTION_AUTOMATICA: tuple[str, ...] = ("color managed", "managed")

#: Tokens que, en el nombre de un LUT, sugieren que es una conversion de
#: espacio de entrada (y no un look). SIN VERIFICAR: es una lectura de
#: convenciones de nombrado habituales, no una lista cerrada.
_TOKENS_LUT_CONVERSION: tuple[str, ...] = (
    "log3",
    "vlog",
    "clog",
    "dlog",
    "slog",
    "to rec709",
    "to rec.709",
    "cst",
    "input",
)

#: Tokens que, en `ProjectInfo.timeline_color_space`, indican el espacio de
#: trabajo ancho que espera un proyecto con gestion de color activada.
_TOKENS_ESPACIO_TRABAJO_ESPERADO: tuple[str, ...] = ("wide gamut", "davinci wg", "intermediate")

#: Marcador que deteccion.py escribe en `DeteccionEspacio.razon` cuando la
#: curva declarada contradice el fabricante declarado. Frágil a proposito de
#: forma controlada: los dos modulos son hermanos y se prueban juntos
#: (`tests/test_colormgmt_verificacion.py::test_contradiccion_...`).
_MARCADOR_CONTRADICCION = "no cuadra"


def _es_gestion_automatica(color_science: str) -> bool:
    texto = color_science.lower()
    return any(tok in texto for tok in _TOKENS_GESTION_AUTOMATICA)


def _parece_lut_conversion(lut_path: str) -> bool:
    texto = lut_path.lower()
    return any(tok in texto for tok in _TOKENS_LUT_CONVERSION)


def verificar_proyecto(
    project: ProjectInfo,
    clips: list[ClipRef],
    nodos_por_clip: dict[str, list[NodeInfo]],
    detecciones: list[DeteccionEspacio] | None = None,
) -> list[AvisoGestionColor]:
    """Recorre el proyecto y devuelve los avisos de gestion de color.

    `nodos_por_clip` es `{clip_id: list_nodes(clip_id)}`: se pasa ya calculado
    porque pedirlo aqui exigiria un `ResolveBridge`, y este modulo es puro.
    """
    avisos: list[AvisoGestionColor] = []
    gestion_automatica = _es_gestion_automatica(project.color_science)

    if gestion_automatica:
        for ref in clips:
            nodos = nodos_por_clip.get(ref.clip_id, [])
            normalizacion = next((n for n in nodos if n.index == NODE_NORMALIZACION), None)
            if normalizacion is None or not normalizacion.lut_path:
                continue
            if _parece_lut_conversion(normalizacion.lut_path):
                avisos.append(
                    AvisoGestionColor(
                        clip_id=ref.clip_id,
                        tipo="doble_conversion",
                        mensaje=(
                            f"«{ref.name}»: el proyecto ya convierte el color de entrada "
                            f"({project.color_science}) y ademas tiene el LUT "
                            f"«{normalizacion.lut_path}» puesto en el nodo de normalizacion. "
                            "Esto convierte el color dos veces: quita el LUT o desactiva la "
                            "gestion automatica para este clip."
                        ),
                        severidad="grave",
                    )
                )
    else:
        avisos.append(
            AvisoGestionColor(
                clip_id=None,
                tipo="espacio_trabajo_inesperado",
                mensaje=(
                    f"El proyecto no tiene gestion de color automatica activada "
                    f"({project.color_science}); la conversion de entrada hay que hacerla "
                    "a mano, LUT por clip."
                ),
                severidad="aviso",
            )
        )

    if gestion_automatica and not any(
        tok in project.timeline_color_space.lower() for tok in _TOKENS_ESPACIO_TRABAJO_ESPERADO
    ):
        avisos.append(
            AvisoGestionColor(
                clip_id=None,
                tipo="espacio_trabajo_inesperado",
                mensaje=(
                    f"El espacio de trabajo de la timeline es «{project.timeline_color_space}», "
                    "que no es el amplio que suele acompañar a la gestion de color automatica. "
                    "Revisa Project Settings > Color Management."
                ),
                severidad="aviso",
            )
        )

    if detecciones is not None:
        for d in detecciones:
            if not d.segura and _MARCADOR_CONTRADICCION in d.razon:
                avisos.append(
                    AvisoGestionColor(
                        clip_id=d.clip_id,
                        tipo="curva_no_cuadra",
                        mensaje=d.razon,
                        severidad="aviso",
                    )
                )

    return avisos
