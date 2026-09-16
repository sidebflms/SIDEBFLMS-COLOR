"""El asistente de 5 pasos del modo fácil, sin Qt.

QUÉ ES EL MODO FÁCIL (día 5, tarea 3)
---------------------------------------
No es una version simplificada del modo avanzado: es OTRO camino sobre el
mismo motor, para alguien que sabe aplicar un LUT y poco más. Cinco pasos, en
este orden: 1 ordenar la casa (gestión de color), 2 igualar (todas las
cámaras al mismo sitio), 3 equilibrar (exposición y balance por clip), 4
look, 5 repasar (la lista corta que necesita ojo humano). Nada de ΔE, CDL ni
cobertura en pantalla: una frase en castellano de qué se hizo, antes/después
grande, y deshacer.

LA REGLA QUE HACE HONESTO EL MODO FÁCIL
-----------------------------------------
**Sólo se automatiza lo que está medido.** Por eso este módulo separa, para
cada paso, `resultado` (lo que se HIZO, con números reales detrás) de
`pendiente_preguntar` (lo que NO se pudo decidir solo y necesita que alguien
conteste). Un paso con `pendiente_preguntar` no se ejecuta él solo sobre esos
clips: se limita a agruparlos y redactar la pregunta.

Esta es la razón concreta por la que el paso 5 (repasar) NO usa la confianza
de `core.reverse`/`core.matching` para decidir qué enseñar: el día 4 se
diagnosticó que esa nota no predice el error real
(`CALIBRACION-CONFIANZA.md`), así que usarla aquí sería mentir con un número
que parece objetivo. En su lugar, el paso 5 lista lo que SÍ está medido y
validado: el desajuste de contenido (`content_mismatch`, que el día 4
confirmó que sí distingue "misma escena" de "escena distinta") y los grupos
ambiguos que el paso 1 no pudo resolver solo.

CÓMO SE CONECTA CON EL MODO AVANZADO
--------------------------------------
Mismo motor: cada paso llama a las mismas funciones de `core` que usa el modo
avanzado (`core.colormgmt`, `core.matching.emparejar`). No hay un camino de
cálculo "para el modo fácil" y otro "para el modo avanzado" — sólo cambia
cómo se presenta y qué se pregunta.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.colormgmt import agrupar_ambiguos, detectar_espacios_timeline, verificar_proyecto
from core.contracts import LUT3D, AvisoGestionColor, GrupoAmbiguo
from gui.datos_demo import ClipDemo, EstadoDemo

__all__ = [
    "ID_PASOS",
    "TITULOS_PASO",
    "PasoOrdenar",
    "PasoIgualar",
    "PasoEquilibrar",
    "PasoLook",
    "PasoRepasar",
    "ClipParaRevisar",
    "ejecutar_ordenar",
    "ejecutar_igualar",
    "ejecutar_equilibrar",
    "ejecutar_look",
    "ejecutar_repasar",
]

#: Los cinco pasos, en el orden que manda el encargo. No se reordenan: cada
#: uno depende de que el anterior haya dejado el material en un estado dado
#: (igualar necesita saber en qué espacio está cada clip; equilibrar necesita
#: los clips ya igualados).
ID_PASOS: tuple[str, ...] = ("ordenar", "igualar", "equilibrar", "look", "repasar")

TITULOS_PASO: dict[str, str] = {
    "ordenar": "Ordenar la casa",
    "igualar": "Igualar",
    "equilibrar": "Equilibrar",
    "look": "Look",
    "repasar": "Repasar",
}


# ---------------------------------------------------------------------------
# Paso 1 — ordenar la casa
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PasoOrdenar:
    """Resultado de revisar la gestión de color del proyecto."""

    clips_resueltos: tuple[str, ...]  # clip_id de los que se pudieron fijar solos
    grupos_pendientes: tuple[GrupoAmbiguo, ...]  # los que hay que preguntar
    avisos: tuple[AvisoGestionColor, ...]
    frase: str

    @property
    def hecho(self) -> bool:
        return not self.grupos_pendientes and not any(a.severidad == "grave" for a in self.avisos)


def _frase_ordenar(n_resueltos: int, n_pendientes: int, n_avisos_graves: int) -> str:
    if n_resueltos and not n_pendientes and not n_avisos_graves:
        return f"He revisado la gestión de color: los {n_resueltos} clips ya tienen su espacio de entrada correcto."
    partes = []
    if n_resueltos:
        partes.append(f"{n_resueltos} clips llevan ya el espacio de entrada correcto")
    if n_pendientes:
        partes.append(f"{n_pendientes} necesitan que confirmes de qué cámara son")
    if n_avisos_graves:
        partes.append(f"{n_avisos_graves} tienen la conversión de color duplicada: hay que arreglarlo antes de seguir")
    if not partes:
        return "No hay clips que revisar todavía."
    return "He revisado la gestión de color: " + "; ".join(partes) + "."


def ejecutar_ordenar(estado: EstadoDemo) -> PasoOrdenar:
    """Detecta el espacio de cada clip y agrupa lo que no se puede decidir solo.

    Puro diagnóstico: no escribe nada en Resolve (eso depende de F0-7 del
    probe, ver `core/colormgmt/NOTAS.md`). Lo que sí hace de verdad es la
    detección y la agrupación, con `core.colormgmt`.
    """
    refs = [c.ref for c in estado.clips]
    detecciones = detectar_espacios_timeline(refs)
    grupos = tuple(agrupar_ambiguos(refs, detecciones))
    resueltos = tuple(d.clip_id for d in detecciones if d.segura)

    nodos_por_clip = {
        c.clip_id: estado.puente.list_nodes(c.clip_id) if estado.puente.is_connected() else []
        for c in estado.clips
    }
    avisos = ()
    if estado.puente.is_connected():
        avisos = tuple(
            verificar_proyecto(estado.puente.project_info(), refs, nodos_por_clip, detecciones)
        )

    n_graves = sum(1 for a in avisos if a.severidad == "grave")
    frase = _frase_ordenar(len(resueltos), sum(len(g.clip_ids) for g in grupos), n_graves)
    return PasoOrdenar(clips_resueltos=resueltos, grupos_pendientes=grupos, avisos=avisos, frase=frase)


# ---------------------------------------------------------------------------
# Paso 2 — igualar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PasoIgualar:
    referencia_id: str | None
    referencia_nombre: str
    igualados: tuple[str, ...]  # clip_id
    frase: str


def ejecutar_igualar(estado: EstadoDemo) -> PasoIgualar:
    """Todas las cámaras al mismo sitio: el CDL que ya calcula `core.matching`.

    No recalcula nada — `EstadoDemo.clips[i].match` ya sale de
    `core.matching.emparejar` (ver `gui/datos_demo.py`). Este paso sólo
    decide QUÉ enseñar de ese resultado y en qué orden, que es la parte que
    le toca al modo fácil.
    """
    ref = estado.por_id(estado.referencia_id) if estado.referencia_id else None
    nombre_ref = ref.nombre if ref else "(sin referencia)"
    igualados = tuple(c.clip_id for c in estado.clips if c.clip_id != estado.referencia_id)
    if not igualados:
        frase = "Todavía no hay clips que igualar."
    else:
        frase = (
            f"He igualado {len(igualados)} clip"
            f"{'s' if len(igualados) != 1 else ''} tomando como referencia «{nombre_ref}»."
        )
    return PasoIgualar(
        referencia_id=estado.referencia_id, referencia_nombre=nombre_ref, igualados=igualados, frase=frase
    )


# ---------------------------------------------------------------------------
# Paso 3 — equilibrar (exposición y balance)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PasoEquilibrar:
    """La componente de exposición/balance del MISMO CDL del paso 2.

    No hay, hoy, una función separada en `core` que ajuste "sólo exposición"
    sin referencia — inventar una sería automatizar algo no medido. Así que
    este paso no ejecuta una segunda pasada: lee el mismo `MatchResult.cdl`
    que dejó `ejecutar_igualar` y explica, en su propio lenguaje, la parte
    que le corresponde (offset = exposición, slope = balance de color).
    """

    clip_id: str
    exposicion_ev_aprox: float  # log2 del offset medio, sólo para la frase
    balance_desviacion: float  # cuánto se separa el slope de (1,1,1)
    frase: str


def _frase_equilibrar(nombre: str, ev: float, balance: float) -> str:
    partes = []
    if abs(ev) > 0.05:
        direccion = "subido" if ev > 0 else "bajado"
        partes.append(f"he {direccion} la exposición")
    if balance > 0.01:
        partes.append("corregido el balance de color")
    if not partes:
        return f"«{nombre}» ya estaba equilibrado: no ha hecho falta tocar nada."
    return f"En «{nombre}» " + " y ".join(partes) + "."


def ejecutar_equilibrar(clip: ClipDemo) -> PasoEquilibrar:
    cdl = clip.match.cdl
    offset_medio = float(np.mean(cdl.offset))
    # Un offset en espacio de trabajo logarítmico no es EVs de verdad; es una
    # aproximación SOLO para la frase, no un número que se publique como cifra.
    ev_aprox = float(np.sign(offset_medio) * np.log2(1.0 + abs(offset_medio) * 8.0))
    balance = float(np.std(cdl.slope))
    return PasoEquilibrar(
        clip_id=clip.clip_id,
        exposicion_ev_aprox=ev_aprox,
        balance_desviacion=balance,
        frase=_frase_equilibrar(clip.nombre, ev_aprox, balance),
    )


# ---------------------------------------------------------------------------
# Paso 4 — look
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PasoLook:
    look: LUT3D | None
    aplicado_a: tuple[str, ...]
    frase: str


def ejecutar_look(estado: EstadoDemo) -> PasoLook:
    if estado.look is None:
        return PasoLook(look=None, aplicado_a=(), frase="Todavía no hay ningún look elegido.")
    nombre = estado.look.title or "look"
    clip_ids = tuple(c.clip_id for c in estado.clips)
    frase = (
        f"He aplicado el look «{nombre}» a los {len(clip_ids)} clips."
        if clip_ids
        else f"El look «{nombre}» está listo; todavía no hay clips a los que aplicarlo."
    )
    return PasoLook(look=estado.look, aplicado_a=clip_ids, frase=frase)


# ---------------------------------------------------------------------------
# Paso 5 — repasar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClipParaRevisar:
    clip_id: str
    nombre: str
    motivo: str  # en castellano llano, nunca un número crudo


@dataclass(frozen=True)
class PasoRepasar:
    """La lista corta que necesita ojo humano.

    Deliberadamente NO usa la confianza de `core.matching`/`core.reverse`:
    el día 4 midió que esa nota no predice el error (`CALIBRACION-CONFIANZA.md`).
    Usa dos señales que SÍ están medidas y validadas: el desajuste de
    contenido (§3.3 de ese mismo informe: predice bien "misma escena o no") y
    los grupos de gestión de color que el paso 1 dejó sin resolver.
    """

    candidatos: tuple[ClipParaRevisar, ...]
    frase: str


def ejecutar_repasar(estado: EstadoDemo, paso_ordenar: PasoOrdenar) -> PasoRepasar:
    # Un mismo clip puede caer en las dos señales a la vez (desajuste de
    # contenido Y falta de metadata de cámara): se cuenta una sola vez, con
    # los dos motivos juntos, para que "8 clips" no salga cuando en realidad
    # son 7 y uno tiene dos pegas.
    motivos_por_clip: dict[str, list[str]] = {}
    orden: list[str] = []

    def _anadir(clip_id: str, motivo: str) -> None:
        if clip_id not in motivos_por_clip:
            motivos_por_clip[clip_id] = []
            orden.append(clip_id)
        if motivo not in motivos_por_clip[clip_id]:
            motivos_por_clip[clip_id].append(motivo)

    for clip in estado.clips:
        if clip.match.content_mismatch:
            _anadir(clip.clip_id, "no se parece a la referencia; míralo antes de dar el trabajo por bueno")
    for grupo in paso_ordenar.grupos_pendientes:
        for clip_id in grupo.clip_ids:
            if estado.por_id(clip_id) is not None:
                _anadir(clip_id, "falta confirmar de qué cámara es")

    candidatos = tuple(
        ClipParaRevisar(clip_id=cid, nombre=estado.por_id(cid).nombre, motivo="; y ".join(motivos_por_clip[cid]))
        for cid in orden
    )

    if not candidatos:
        frase = "No hay nada que te haga falta revisar a mano: todo lo demás está medido."
    else:
        frase = f"Hay {len(candidatos)} clip{'s' if len(candidatos) != 1 else ''} que conviene que mires tú."
    return PasoRepasar(candidatos=candidatos, frase=frase)
