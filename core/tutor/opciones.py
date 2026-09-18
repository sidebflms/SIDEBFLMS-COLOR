"""Tarea 2.3 del día 8: 3-4 variantes de un look, para comparar a pantalla
completa con el selector de versiones de Resolve en vez de en una miniatura.

QUÉ VARÍA ENTRE LAS OPCIONES, Y QUÉ NO
-----------------------------------------
Las variantes son del MISMO look, mezclado a distinta intensidad — nunca
looks distintos inventados de la nada. La mezcla es interpolación lineal
celda a celda entre la rejilla identidad y la rejilla del look elegido: la
misma técnica que "intensidad de LUT" en cualquier NLE, no una idea nueva. Es
un cálculo, no una decisión artística que este módulo no tiene forma de
justificar.

EL SUPUESTO QUE ESTO ARRASTRA (`SUPUESTOS.md`, fila G)
----------------------------------------------------------
Meter cada variante como una versión de Resolve separada depende de
`AddVersion()`, que **no está verificado** (`SUPUESTOS.md` fila A9 — la
séptima incógnita: si `AddVersion` no hereda el árbol de nodos, la app no
puede escribir nada en absoluto). Por eso este módulo se construye tras la
interfaz (`ResolveBridge`) y se prueba con `FakeResolve`: funciona igual hoy
que el día que haya Resolve real delante, porque nunca llama a nada por
debajo de la interfaz — la única función que escribe es
`core.resolve.bridge.aplicar_grado_seguro`, el mismo camino único que usa el
modo avanzado (`gui/pantalla_aplicar.py`) para aplicar de verdad.

NINGÚN MÉTODO NUEVO DE LA API
--------------------------------
Sólo se usan `aplicar_grado_seguro`/`add_version`/`load_version`, que ya
están en la lista verificada de `CONTRATOS.md`. No hay ningún "mezclador de
nodos" ni "opacidad de nodo" inventado: si Resolve tuviera un control de
mezcla de nodo expuesto en la API, sería otra función; hoy no consta que lo
tenga, así que la mezcla se hornea en la rejilla del LUT antes de escribirlo,
no se pide a Resolve que la haga.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.contracts import CDL, LUT3D, ResolveBridge, ResolveError
from core.resolve.bridge import ResultadoAplicacion, aplicar_grado_seguro
from core.resolve.incognitas import INCOGNITAS_CONSERVADORAS, Incognitas

__all__ = ["INTENSIDADES", "OpcionLook", "aplicar_opciones_como_versiones", "generar_opciones"]

#: Intensidades de mezcla, de más a menos look. 100% (el look tal cual) tiene
#: que estar siempre — es lo que ya se aplicaría sin esta función. Las otras
#: dos son puntos intermedios razonables para "auditar" cuánto look hace
#: falta, no una cifra medida: no hay umbral de "la intensidad correcta es
#: X%", así que se deja como parámetro y estos son sólo los valores por
#: defecto (ver `SUPUESTOS.md`, fila G).
INTENSIDADES: tuple[float, ...] = (1.0, 0.66, 0.33)


@dataclass(frozen=True)
class OpcionLook:
    """Una variante lista para escribirse como versión de Resolve."""

    nombre: str  # legible, para la GUI: "Opción 1: 100% del look"
    version: str  # nombre de versión de Resolve, ya con el prefijo SIDEB COLOR
    intensidad: float  # 0..1
    lut: LUT3D  # la rejilla YA mezclada, lista para render local
    lut_rel_path: str  # convención informativa, igual que EstadoDemo.look_rel
    descripcion: str  # una frase de qué es esta variante


def _mezclar(look: LUT3D, intensidad: float) -> LUT3D:
    if intensidad >= 1.0:
        return look
    identidad = LUT3D.identity(look.size)
    tabla_look = np.asarray(look.table, dtype=np.float64)
    tabla_identidad = np.asarray(identidad.table, dtype=np.float64)
    mezcla = (1.0 - intensidad) * tabla_identidad + intensidad * tabla_look
    titulo_base = look.title or "look"
    return LUT3D(table=mezcla.astype(np.float32), title=f"{titulo_base} {intensidad * 100:.0f}%")


def generar_opciones(
    look: LUT3D,
    *,
    look_rel_base: str = "SIDEB/SIDEB COLOR look.cube",
    version_base: str = "SIDEB COLOR — Opción",
    intensidades: tuple[float, ...] = INTENSIDADES,
) -> tuple[OpcionLook, ...]:
    """3-4 variantes DEL MISMO look, mezclado a distinta intensidad.

    `intensidades` va de 1.0 (100%, el look tal cual) hacia 0.0 (el material
    sin gradar). No se valida que sea monótona ni que 1.0 esté incluida —
    quien llama decide; el valor por defecto (`INTENSIDADES`) sí cumple las
    dos cosas.
    """
    base, _, ext = look_rel_base.rpartition(".")
    if not base:
        base, ext = look_rel_base, "cube"
    opciones = []
    for i, intensidad in enumerate(intensidades, start=1):
        variante = _mezclar(look, intensidad)
        porcentaje = round(intensidad * 100)
        if intensidad >= 1.0:
            descripcion = "El look tal cual está en la biblioteca, sin mezclar."
        elif intensidad <= 0.0:
            descripcion = "El material sin ningún look aplicado — el punto de partida."
        else:
            descripcion = f"El {porcentaje}% del look, mezclado hacia el material sin gradar."
        opciones.append(
            OpcionLook(
                nombre=f"Opción {i}: {porcentaje}% del look",
                version=f"{version_base} {i} ({porcentaje}%)",
                intensidad=intensidad,
                lut=variante,
                lut_rel_path=f"{base} — {porcentaje}%.{ext}",
                descripcion=descripcion,
            )
        )
    return tuple(opciones)


def aplicar_opciones_como_versiones(
    bridge: ResolveBridge,
    clip_id: str,
    opciones: tuple[OpcionLook, ...],
    *,
    cdl: CDL | None = None,
    incognitas: Incognitas = INCOGNITAS_CONSERVADORAS,
) -> list[ResultadoAplicacion]:
    """Escribe cada opción como su propia versión de Resolve.

    El ÚNICO camino: `aplicar_grado_seguro`, el mismo que usa
    `gui/pantalla_aplicar.py` para aplicar de verdad — nunca `set_cdl`/
    `set_lut` a pelo. `cdl` es el mismo para todas las opciones a propósito:
    lo que cambia entre variantes es sólo el look (nodo 3), no la
    exposición/balance del clip (nodo 2) — ver `core/tutor/ensenar.py`, "por
    qué la exposición nunca va dentro de un look".

    Un fallo en una opción no tumba las demás — mismo criterio que
    `gui/pantalla_aplicar.py::aplicar()`: se captura sólo `ResolveError` (si
    sale otra cosa es un bug de la app y tiene que verse, no taparse), y esa
    opción queda con `ok=False` y el motivo en `avisos`.
    """
    resultados = []
    for opcion in opciones:
        try:
            resultados.append(
                aplicar_grado_seguro(
                    bridge,
                    clip_id,
                    cdl=cdl,
                    lut_rel_path=opcion.lut_rel_path,
                    version=opcion.version,
                    incognitas=incognitas,
                )
            )
        except ResolveError as exc:
            resultados.append(
                ResultadoAplicacion(
                    clip_id=clip_id,
                    version=opcion.version,
                    cdl_escrito=False,
                    lut_escrito=False,
                    avisos=(str(exc),),
                )
            )
    return resultados
