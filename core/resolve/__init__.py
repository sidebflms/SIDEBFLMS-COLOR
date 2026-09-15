"""Puente con DaVinci Resolve.

**Importar este paquete NO toca Resolve.** Aqui no se importa
`DaVinciResolveScript`, ni `fusionscript`, ni se busca ningun socket. Lo unico
que habla con Resolve de verdad es `core.resolve.live.LiveResolve`, que hay que
importar a mano y a conciencia:

    from core.resolve.live import LiveResolve   # <- solo si el probe dice que si

Mientras tanto, todo el mundo usa `FakeResolve`, que es contra lo que se prueba
la app entera.

    from core.resolve import FakeResolve, aplicar_grado_seguro

    r = FakeResolve(n_clips=4)
    for clip in r.list_clips():
        resultado = aplicar_grado_seguro(r, clip.clip_id, cdl=mi_cdl,
                                         lut_rel_path="SIDEB/look.cube")
"""

from __future__ import annotations

from core.resolve.bridge import (
    BaseResolveBridge,
    ClipNoEncontrado,
    EscrituraFueraDeVersion,
    GrupoNoEncontrado,
    NodoInvalido,
    OperacionNoDisponible,
    ResolveNoConectado,
    ResultadoAplicacion,
    RutaLUTInvalida,
    TimelineNoAbierto,
    VersionInvalida,
    aplicar_grado_seguro,
    asegurar_pagina_color,
    asegurar_version,
    copiar_grado_seguro,
    es_version_nuestra,
    resumen_nodos,
    validar_indice_nodo,
    validar_nombre_version,
    validar_ruta_lut_relativa,
    verificar_estructura_nodos,
)
from core.resolve.fake import FakeResolve, GradoEscrito
from core.resolve.incognitas import (
    INCOGNITAS_CONSERVADORAS,
    Incognitas,
    extensiones_lut_aceptadas,
    formatos_export_disponibles,
    lut_dir,
    still_sirve_para_medir,
)

__all__ = [
    "INCOGNITAS_CONSERVADORAS",
    "BaseResolveBridge",
    "ClipNoEncontrado",
    "EscrituraFueraDeVersion",
    "FakeResolve",
    "GradoEscrito",
    "GrupoNoEncontrado",
    "Incognitas",
    "NodoInvalido",
    "OperacionNoDisponible",
    "ResolveNoConectado",
    "ResultadoAplicacion",
    "RutaLUTInvalida",
    "TimelineNoAbierto",
    "VersionInvalida",
    "aplicar_grado_seguro",
    "asegurar_pagina_color",
    "asegurar_version",
    "copiar_grado_seguro",
    "es_version_nuestra",
    "extensiones_lut_aceptadas",
    "formatos_export_disponibles",
    "lut_dir",
    "resumen_nodos",
    "still_sirve_para_medir",
    "validar_indice_nodo",
    "validar_nombre_version",
    "validar_ruta_lut_relativa",
    "verificar_estructura_nodos",
]
