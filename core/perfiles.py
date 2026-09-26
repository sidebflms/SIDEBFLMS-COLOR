"""Perfiles de trabajo reutilizables (día 9, continuación 10).

Mario pidió un "botón" que, para un tipo de trabajo recurrente (p.ej.
"Fabrik": grabado con varias cámaras conocidas, siempre el mismo tipo de
sitio y de luz), ajuste la timeline entera de una vez — sin ir cámara por
cámara, clip por clip.

QUÉ ES UN PERFIL, EN UNA FRASE
--------------------------------
Un nombre + un ajuste de partida CONOCIDO por cámara (de la experiencia de
quien monta, no calculado) + un look compartido para ese tipo de trabajo.
El ajuste "de hoy" (comparar cada clip contra una referencia de ESE día,
`core.matching.emparejar_analisis`) sigue siendo aparte — se sigue
calculando igual que siempre, esto no lo sustituye.

POR QUÉ EL AJUSTE DE CÁMARA Y EL LOOK VIVEN JUNTOS, HORNEADOS EN UN LUT
--------------------------------------------------------------------------
Resolve sólo da dos sitios por clip donde este proyecto escribe: el nodo de
balance (un CDL) y el nodo de look (un LUT). El ajuste "de hoy" usa el CDL —
es lo que ya hacía la app. El ajuste conocido de cada cámara NO puede ir
también en ese mismo CDL: un CDL con `power` ajustado (lo habitual, ver
`core/matching/cdl_fit.py` — "power" es "lo importante") no se puede
COMPONER con otro CDL y seguir siendo un único CDL — componer dos curvas con
exponente no da, en general, otra curva con exponente. Un LUT SÍ compone sin
este problema (aplicar una tabla y luego otra es, siempre, otra tabla), así
que el ajuste de cámara se hornea DENTRO del LUT de look, una vez por
cámara — invisible para quien usa la app, es sólo dónde vive el número.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.contracts import CDL, LUT3D, ClipRef
from core.reverse.relleno import rejilla_de_entradas
from core.umbrales import LUT_SIZE_DEFAULT

__all__ = ["PerfilCamara", "PerfilTrabajo", "camara_para_clip", "lut_para_camara"]


def _norm(texto: str | None) -> str:
    return texto.strip().lower() if texto else ""


@dataclass(frozen=True)
class PerfilCamara:
    """Ajuste de partida conocido para una cámara, dentro de un `PerfilTrabajo`.

    Se identifica por SUBCADENA (como `core.colormgmt.deteccion.ReglaDeteccion`,
    mismo criterio): `fabricante_contiene` se busca dentro de
    `ClipRef.camera_manufacturer` en minúsculas, `tipo_contiene` (opcional)
    dentro de `camera_type`. No hace falta acertar el nombre exacto que use
    Resolve, sólo un trozo reconocible ("gopro", "sony", "fx3"...).
    """

    fabricante_contiene: str
    tipo_contiene: str = ""
    nombre_legible: str = ""
    cdl_base: CDL = field(default_factory=CDL)

    def coincide(self, ref: ClipRef) -> bool:
        if self.fabricante_contiene and self.fabricante_contiene not in _norm(ref.camera_manufacturer):
            return False
        return not (self.tipo_contiene and self.tipo_contiene not in _norm(ref.camera_type))


@dataclass(frozen=True)
class PerfilTrabajo:
    """Un perfil reutilizable de trabajo (p.ej. "Fabrik").

    `camaras` se recorre EN ORDEN y se queda con la primera que coincide —
    igual que `core.colormgmt.deteccion.REGLAS_DECISION` — así que una regla
    más específica ("fabricante_contiene='gopro', tipo_contiene='hero12'")
    puede ir antes que una más genérica ("fabricante_contiene='gopro'") sin
    que se estorben.
    """

    nombre: str
    camaras: tuple[PerfilCamara, ...] = ()
    #: El look compartido de este trabajo. `None` = ninguno (sólo el ajuste
    #: de cámara, si lo hay, acaba en el LUT de look).
    look: LUT3D | None = None


def camara_para_clip(perfil: PerfilTrabajo, ref: ClipRef) -> PerfilCamara | None:
    """La primera `PerfilCamara` de `perfil` que reconoce este clip, o
    `None` si ninguna coincide (cámara no contemplada en este perfil)."""
    for camara in perfil.camaras:
        if camara.coincide(ref):
            return camara
    return None


def lut_para_camara(
    perfil: PerfilTrabajo, camara: PerfilCamara | None, *, n: int = LUT_SIZE_DEFAULT
) -> LUT3D | None:
    """El LUT que le corresponde al nodo de look para una cámara concreta de
    este perfil: el look compartido, con el ajuste de partida de esa cámara
    horneado delante (si la tiene).

    `None` si no hay nada que escribir (ni ajuste de cámara real ni look
    compartido) — mismo criterio que el resto de la app: no escribir un LUT
    identidad de mentira donde no hace falta ninguno.
    """
    cdl = camara.cdl_base if camara is not None else CDL()
    if cdl.is_identity() and perfil.look is None:
        return None
    entradas = rejilla_de_entradas(n)
    con_cdl = np.clip(cdl.apply(entradas), 0.0, 1.0).astype(np.float32)
    if perfil.look is None:
        titulo = f"{perfil.nombre} — {camara.nombre_legible or 'cámara'}" if camara else perfil.nombre
        return LUT3D(table=con_cdl, title=titulo)
    salida = perfil.look.apply(con_cdl)
    tabla = np.clip(salida, 0.0, 1.0).astype(np.float32)
    titulo = f"{perfil.nombre} — {camara.nombre_legible or 'cámara'}" if camara else perfil.nombre
    return LUT3D(table=tabla, title=titulo)
