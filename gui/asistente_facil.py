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

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from core.colormgmt import agrupar_ambiguos, detectar_espacios_timeline, verificar_proyecto
from core.contracts import LUT3D, AvisoGestionColor, GrupoAmbiguo
from core.io.biblioteca import Preset
from core.reverse.orden_repaso import CandidatoOrden, orden_de_repaso
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
    #: La biblioteca de presets disponible (día 6, tarea 4), para que la
    #: pantalla pueda enseñar "elige entre estos" con nombre legible y
    #: miniatura — nunca con el nombre de archivo. Vacío si no hay biblioteca
    #: sembrada (p.ej. sin `tests/luts_reales/`, o en el estado de demo).
    presets_disponibles: tuple[Preset, ...] = ()
    #: Cuál de `presets_disponibles` es el que está aplicado ahora mismo.
    #: `None` cuando `look` viene de `estado.look` directamente (sin pasar
    #: por la biblioteca) o cuando no hay ninguno elegido todavía.
    preset_elegido: Preset | None = None


def ejecutar_look(
    estado: EstadoDemo,
    *,
    biblioteca: tuple[Preset, ...] = (),
    preset_elegido_id: str | None = None,
) -> PasoLook:
    """Aplica un look. Si hay `biblioteca` (día 6: sembrada desde los LUTs
    reales de Mario), elige de ahí — el primero por defecto, o el que diga
    `preset_elegido_id`; si no, cae al `estado.look` fijo de siempre (el
    camino que usa `estado_demo()`, sin biblioteca).
    """
    preset_elegido: Preset | None = None
    look = estado.look
    if biblioteca:
        preset_elegido = next((p for p in biblioteca if p.id == preset_elegido_id), biblioteca[0])
        from core.io.cube import leer_cube

        look = leer_cube(preset_elegido.ruta_origen)

    if look is None:
        return PasoLook(look=None, aplicado_a=(), frase="Todavía no hay ningún look elegido.")

    nombre = preset_elegido.nombre if preset_elegido is not None else (look.title or "look")
    clip_ids = tuple(c.clip_id for c in estado.clips)
    frase = (
        f"He aplicado el look «{nombre}» a los {len(clip_ids)} clips."
        if clip_ids
        else f"El look «{nombre}» está listo; todavía no hay clips a los que aplicarlo."
    )
    return PasoLook(
        look=look,
        aplicado_a=clip_ids,
        frase=frase,
        presets_disponibles=biblioteca,
        preset_elegido=preset_elegido,
    )


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
    QUIÉN entra en la lista sigue decidido por dos señales que SÍ están
    medidas y validadas: el desajuste de contenido (§3.3 de ese mismo
    informe: predice bien "misma escena o no") y los grupos de gestión de
    color que el paso 1 dejó sin resolver.

    El ORDEN (día 6) es harina de otro costal: no certifica nada, sólo
    prioriza. Ver `ejecutar_repasar` y `core.reverse.orden_repaso`.
    """

    candidatos: tuple[ClipParaRevisar, ...]
    frase: str


def ejecutar_repasar(
    estado: EstadoDemo,
    paso_ordenar: PasoOrdenar,
    *,
    candidatos_orden: Mapping[str, CandidatoOrden] | None = None,
) -> PasoRepasar:
    """Decide QUIÉN entra en la lista (sin cambios: día 5) y en qué ORDEN
    enseñarla (día 6).

    `candidatos_orden` es opcional y por clip: `core.reverse.orden_repaso`
    necesita `FeaturesDestino` (cobertura del cubo contra el plano de destino
    de ESE clip), que sólo existen cuando el look se extrajo por ingeniería
    inversa (`core.reverse.invertir_grado`/`_lote`) con su `CoverageMap` a
    mano. Hoy el modo fácil (`gui.datos_demo`) NO pasa por ahí — el paso 4
    aplica un look ya horneado (`look_de_demostracion`/la biblioteca de
    presets), sin extracción ni cobertura — así que en la práctica este
    diccionario llega vacío y el paso cae al orden simple de abajo. Es la
    misma regla que el resto del módulo: **sólo se automatiza lo que está
    medido**, y para lo que no lo está, se declara así en vez de fingir.

    Para los clips CON dato (`clip_id` en `candidatos_orden`), el orden que
    decide `core.reverse.orden_repaso.orden_de_repaso` (calibrado por clase
    de material; medido en `tests/calibracion_destino/ordenar.py`,
    `CIFRAS.md` §18: precisión@5 0.40 y precisión@10 0.62-0.63, mejor que el
    mismo cálculo sin normalizar por clase y que un orden al azar) va
    PRIMERO, de peor a mejor. Los que no tengan dato van detrás, con el
    **orden simple y declarado** (no una fórmula compuesta, tal y como pide
    el encargo cuando no hay señal calibrada que usar): más motivos de
    revisión primero, y a igualdad de motivos, el orden en que se
    detectaron. Nunca se muestra ningún número de ninguno de los dos: sólo
    cambia en qué posición sale cada `ClipParaRevisar`.
    """
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

    orden = _ordenar_para_repaso(orden, motivos_por_clip, candidatos_orden or {})

    candidatos = tuple(
        ClipParaRevisar(clip_id=cid, nombre=estado.por_id(cid).nombre, motivo="; y ".join(motivos_por_clip[cid]))
        for cid in orden
    )

    if not candidatos:
        frase = "No hay nada que te haga falta revisar a mano: todo lo demás está medido."
    else:
        frase = f"Hay {len(candidatos)} clip{'s' if len(candidatos) != 1 else ''} que conviene que mires tú."
    return PasoRepasar(candidatos=candidatos, frase=frase)


def _ordenar_para_repaso(
    clip_ids: list[str],
    motivos_por_clip: dict[str, list[str]],
    candidatos_orden: Mapping[str, CandidatoOrden],
) -> list[str]:
    """El orden final de la lista de repaso: primero los clips con señal
    calibrada (`orden_de_repaso`, de peor a mejor), después el resto con el
    orden simple declarado (más motivos primero; a igualdad, el orden en que
    `ejecutar_repasar` los fue detectando — `sorted` es estable, así que ese
    empate no se reordena al azar)."""
    con_dato = [cid for cid in clip_ids if cid in candidatos_orden]
    sin_dato = [cid for cid in clip_ids if cid not in candidatos_orden]
    calibrado = orden_de_repaso([candidatos_orden[cid] for cid in con_dato])
    simple = sorted(sin_dato, key=lambda cid: -len(motivos_por_clip[cid]))
    return calibrado + simple
