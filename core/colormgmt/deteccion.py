"""Detector de camara y tabla de decision de espacio de entrada.

Las cuatro camaras del encargo, mas Rec.709 para material ya convertido. La
tabla (`REGLAS_DECISION`) es explicita a proposito: cada fila dice de que
fabricante viene, que texto de metadata la dispara y de donde sale el espacio
de color, para que nadie tenga que adivinar ni confiar en una intuicion.

QUE HACE CUANDO NO SABE (punto 3 del encargo)
-----------------------------------------------
Si la metadata no basta para decidir con seguridad, `detectar_espacio_clip`
devuelve `segura=False`. Puede llevar igualmente una MEJOR CONJETURA en
`space` (por ejemplo, "el fabricante es Sony pero no declara curva": la
conjetura es su log habitual), pero esa conjetura **no se aplica sola**: solo
sirve para redactar una pregunta mejor en `agrupar_ambiguos`. Los clips con
`segura=False` nunca deberian escribirse en Resolve sin que el usuario
conteste antes por su grupo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.color.spaces import SPACES
from core.contracts import ClipRef, ColorSpaceName, DeteccionEspacio, GrupoAmbiguo


@dataclass(frozen=True)
class ReglaDeteccion:
    """Una fila de la tabla de decision."""

    nombre: str  # legible, para razones y preguntas
    espacio: ColorSpaceName
    fabricante_contiene: tuple[str, ...]  # tokens (minusculas) que identifican al fabricante
    gamma_contiene: tuple[str, ...]  # tokens (minusculas) que identifican la curva
    fuente: str  # de donde sale el mapeo curva -> espacio


#: Las cuatro camaras del encargo. El espacio de cada una es el mismo nombre
#: que usa `core.color.spaces.SPACES`, y la fuente es la misma que alli: no se
#: duplica el dato, se cita el mismo origen.
REGLAS_DECISION: tuple[ReglaDeteccion, ...] = (
    ReglaDeteccion(
        nombre="Sony FX3 (S-Log3 / S-Gamut3.Cine)",
        espacio="slog3_sgamut3cine",
        fabricante_contiene=("sony",),
        gamma_contiene=("s-log3", "slog3"),
        fuente=SPACES["slog3_sgamut3cine"].fuente,
    ),
    ReglaDeteccion(
        nombre="Panasonic Lumix (V-Log / V-Gamut)",
        espacio="vlog_vgamut",
        fabricante_contiene=("panasonic", "lumix"),
        gamma_contiene=("v-log", "vlog"),
        fuente=SPACES["vlog_vgamut"].fuente,
    ),
    ReglaDeteccion(
        nombre="Canon (C-Log3 / Cinema Gamut)",
        espacio="clog3_cinemagamut",
        fabricante_contiene=("canon",),
        gamma_contiene=("c-log3", "canon log 3", "clog3"),
        fuente=SPACES["clog3_cinemagamut"].fuente,
    ),
    ReglaDeteccion(
        nombre="DJI (D-Log / D-Gamut)",
        espacio="dlog_dgamut",
        fabricante_contiene=("dji",),
        gamma_contiene=("d-log", "dlog"),
        fuente=SPACES["dlog_dgamut"].fuente,
    ),
)

#: Tokens que dicen "esto ya viene en Rec.709", sin curva log de por medio.
_REC709_TOKENS: tuple[str, ...] = ("rec.709", "rec709", "rec 709", "rec-709", "bt.709", "bt709")

__all__ = [
    "REGLAS_DECISION",
    "ReglaDeteccion",
    "detectar_espacio_clip",
    "detectar_espacios_timeline",
    "agrupar_ambiguos",
]


def _norm(texto: str | None) -> str:
    return texto.strip().lower() if texto else ""


def detectar_espacio_clip(ref: ClipRef) -> DeteccionEspacio:
    """Decide el espacio de entrada de UN clip a partir de su metadata.

    Nunca lanza: la falta de metadata es el caso normal, no un error.
    """
    fabricante = _norm(ref.camera_manufacturer) or _norm(ref.camera_type)
    texto_curva = " ".join(
        t for t in (_norm(ref.gamma_notes), _norm(ref.camera_notes), _norm(ref.input_color_space)) if t
    )

    coincidencias = [r for r in REGLAS_DECISION if any(tok in texto_curva for tok in r.gamma_contiene)]

    if len(coincidencias) > 1:
        nombres = ", ".join(r.nombre for r in coincidencias)
        return DeteccionEspacio(
            clip_id=ref.clip_id,
            space=None,
            segura=False,
            razon=f"la metadata menciona mas de una curva de camara a la vez ({nombres}); no se puede elegir sola.",
            regla=None,
        )

    if len(coincidencias) == 1:
        regla = coincidencias[0]
        if fabricante and not any(tok in fabricante for tok in regla.fabricante_contiene):
            return DeteccionEspacio(
                clip_id=ref.clip_id,
                space=regla.espacio,
                segura=False,
                razon=(
                    f"declara la curva de {regla.nombre}, pero el fabricante puesto es "
                    f"{ref.camera_manufacturer or ref.camera_type!r}, que no cuadra con esa curva. "
                    "Revisalo antes de aplicar."
                ),
                regla=regla.nombre,
            )
        return DeteccionEspacio(
            clip_id=ref.clip_id,
            space=regla.espacio,
            segura=True,
            razon=f"curva declarada de {regla.nombre} ({regla.fuente}).",
            regla=regla.nombre,
        )

    if texto_curva and any(tok in texto_curva for tok in _REC709_TOKENS):
        return DeteccionEspacio(
            clip_id=ref.clip_id,
            space="rec709",
            segura=True,
            razon="declarado como Rec.709: material que ya venia convertido.",
            regla="Rec.709 declarado",
        )

    if fabricante:
        for regla in REGLAS_DECISION:
            if any(tok in fabricante for tok in regla.fabricante_contiene):
                return DeteccionEspacio(
                    clip_id=ref.clip_id,
                    space=regla.espacio,
                    segura=False,
                    razon=(
                        f"el fabricante {regla.nombre.split(' ', 1)[0]} esta reconocido pero el clip "
                        "no declara curva: podria venir en su log habitual o ya convertido a Rec.709. "
                        "Hay que preguntar."
                    ),
                    regla=regla.nombre,
                )

    return DeteccionEspacio(
        clip_id=ref.clip_id,
        space=None,
        segura=False,
        razon="no hay metadatos de camara reconocibles (ni fabricante ni curva declarada).",
        regla=None,
    )


def detectar_espacios_timeline(clips: list[ClipRef]) -> list[DeteccionEspacio]:
    """`detectar_espacio_clip` sobre cada clip del timeline, en el mismo orden."""
    return [detectar_espacio_clip(c) for c in clips]


def _carpeta(ref: ClipRef) -> str | None:
    if not ref.file_path:
        return None
    carpeta = os.path.dirname(ref.file_path)
    return carpeta or None


def _prefijo_nombre(nombre: str) -> str:
    """El tramo alfabetico antes del primer digito: 'A001C002' -> 'A'.

    Es la heuristica mas simple que sirve para el nombrado tipico de camara
    (prefijo de carrete + numeros). Si el nombre no tiene ningun digito, se
    agrupa por el nombre entero.
    """
    i = 0
    while i < len(nombre) and not nombre[i].isdigit():
        i += 1
    return nombre[:i] if i > 0 else nombre


def _clave_agrupacion(ref: ClipRef) -> str:
    carpeta = _carpeta(ref)
    return carpeta if carpeta is not None else f"nombre:{_prefijo_nombre(ref.name)}"


def _pregunta_grupo(clip_ids: tuple[str, ...], hints: set[ColorSpaceName | None]) -> tuple[str, ColorSpaceName | None]:
    """Redacta la pregunta en castellano llano. Devuelve (pregunta, sugerencia)."""
    n = len(clip_ids)
    hints_validos = {h for h in hints if h is not None}
    if len(hints_validos) == 1:
        (espacio,) = hints_validos
        etiqueta = SPACES[espacio].label
        return (
            f"Estos {n} clips parecen ser {etiqueta}, ¿lo son?",
            espacio,
        )
    return (
        f"No he podido reconocer la camara de estos {n} clips. ¿De que camara son "
        "(Sony FX3, Panasonic Lumix, Canon, DJI, o ya convertidos a Rec.709)?",
        None,
    )


def agrupar_ambiguos(
    clips: list[ClipRef],
    detecciones: list[DeteccionEspacio] | None = None,
) -> list[GrupoAmbiguo]:
    """Agrupa los clips con deteccion insegura por carpeta o por patron de nombre.

    Un clip con `segura=True` no entra en ningun grupo: ya se puede aplicar
    solo. Los grupos salen ordenados por `grupo_id` para que el orden sea
    estable entre ejecuciones (los tests y la GUI lo dan por hecho).
    """
    dets = detecciones if detecciones is not None else detectar_espacios_timeline(clips)
    por_clip = {d.clip_id: d for d in dets}

    grupos: dict[str, list[ClipRef]] = {}
    for ref in clips:
        deteccion = por_clip.get(ref.clip_id)
        if deteccion is None or deteccion.segura:
            continue
        grupos.setdefault(_clave_agrupacion(ref), []).append(ref)

    resultado: list[GrupoAmbiguo] = []
    for clave in sorted(grupos):
        miembros = grupos[clave]
        clip_ids = tuple(m.clip_id for m in miembros)
        hints = {por_clip[cid].space for cid in clip_ids}
        pregunta, sugerencia = _pregunta_grupo(clip_ids, hints)
        resultado.append(
            GrupoAmbiguo(
                grupo_id=clave,
                clip_ids=clip_ids,
                pregunta=pregunta,
                sugerencia_espacio=sugerencia,
                frame_muestra_clip_id=clip_ids[0] if clip_ids else None,
            )
        )
    return resultado
