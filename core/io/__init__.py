"""`core.io` — todo lo que entra y sale a disco en SIDEBFLMS COLOR.

Cinco cosas:

1. **`.cube`** (`cube.py`) — leer y escribir LUT 3D de 17/33/65 (y cualquier
   tamaño entre 2 y 129 al leer). Aquí vive la convención 4: el eje 0 de
   `LUT3D.table` es el ROJO, pero en el fichero el rojo es el que varía más
   rápido.
2. **HALD CLUT** (`hald.py`) — el LUT como imagen, ida y vuelta exacta.
3. **QC de LUT** (`qc.py`) — `qc_lut()` dice qué le pasa a un LUT y **dónde**.
   Un LUT identidad pasa limpio; eso no se negocia.
   Y `remuestreo.py`, que escribe el mismo LUT sobre otra rejilla: es por donde
   se exporta a 65 para una entrega final. **Nunca por defecto, y no añade
   información**: el tamaño de la app sigue siendo 33.
4. **ASC CDL** (`cdl_xml.py`) — `.cc`, `.ccc` y `.cdl`, leer y escribir.
5. **`.sidebcolor`** (`bundle.py`) — la sesión entera en un zip.

Y `lut_malos.py`, que fabrica LUT rotos a propósito para probar el QC.

**Todos los errores heredan de `ErrorIO`** y hablan castellano. La GUI captura
`ErrorIO` y enseña el mensaje tal cual.

Nada de aquí escribe fuera de la ruta que le pasen (convención 7 de CONTRATOS).
Es más: si la carpeta de destino no existe, se lanza en vez de crearla, salvo
que se pida `crear_directorios=True` explícitamente.
"""

from __future__ import annotations

from .bundle import (
    DECIMALES_LUT_BUNDLE,
    EXTENSION_BUNDLE,
    FORMATO_VERSION,
    MAX_DESCOMPRIMIDO,
    MAX_ENTRADAS,
    abrir_sesion,
    guardar_sesion,
)
from .cdl_xml import (
    EXTENSIONES_CDL,
    MAX_BYTES_CDL,
    cdl_a_xml,
    escribir_cdl,
    escribir_cdls,
    leer_cdl,
    leer_cdls,
)
from .cube import (
    LUT_SIZE_MAX_LECTURA,
    LUT_SIZE_MIN,
    MAX_BYTES_CUBE,
    cube_a_texto,
    cube_desde_texto,
    escribir_cube,
    leer_cube,
    orden_fichero_desde_tabla,
    tabla_desde_orden_fichero,
)
from .errores import (
    ErrorBundle,
    ErrorFormatoCDL,
    ErrorFormatoCube,
    ErrorFormatoHald,
    ErrorIO,
)
from .hald import hald_image, lado_hald, lut_from_hald
from .lut_malos import (
    catalogo_luts_malos,
    lut_canales_invertidos,
    lut_con_banding,
    lut_con_nan,
    lut_desde_curvas,
    lut_fuera_de_gamut,
    lut_no_monotono,
    lut_plano,
    lut_solo_rojo,
)
from .qc import (
    CODIGO_BANDING,
    CODIGO_CANALES_INVERTIDOS,
    CODIGO_GAMUT,
    CODIGO_LUT_PLANO,
    CODIGO_NO_FINITO,
    CODIGO_NO_MONOTONIA,
    EXPLICACION_MEDIOS,
    EXPLICACION_SOMBRAS,
    MAX_PROBLEMAS_POR_CODIGO,
    SALTO_MINIMO_BANDING,
    UMBRAL_BANDING,
    UMBRAL_CHROMA_CONVERSION,
    UMBRAL_SOMBRAS,
    LUTQualityReport,
    ProblemaQC,
    clasificar_lut,
    qc_lut,
)
from .remuestreo import (
    TAMANO_ENTREGA_FINAL,
    explicacion_remuestreo,
    rejilla_del_dominio,
    remuestrear_lut,
)

__all__ = [
    # errores
    "ErrorIO",
    "ErrorFormatoCube",
    "ErrorFormatoHald",
    "ErrorFormatoCDL",
    "ErrorBundle",
    # .cube
    "leer_cube",
    "escribir_cube",
    "cube_desde_texto",
    "cube_a_texto",
    "orden_fichero_desde_tabla",
    "tabla_desde_orden_fichero",
    "LUT_SIZE_MIN",
    "LUT_SIZE_MAX_LECTURA",
    "MAX_BYTES_CUBE",
    # HALD
    "hald_image",
    "lut_from_hald",
    "lado_hald",
    # QC
    "qc_lut",
    "clasificar_lut",
    "UMBRAL_CHROMA_CONVERSION",
    "LUTQualityReport",
    "ProblemaQC",
    "CODIGO_NO_FINITO",
    "CODIGO_LUT_PLANO",
    "CODIGO_NO_MONOTONIA",
    "CODIGO_BANDING",
    "CODIGO_GAMUT",
    "CODIGO_CANALES_INVERTIDOS",
    "UMBRAL_BANDING",
    "SALTO_MINIMO_BANDING",
    "UMBRAL_SOMBRAS",
    "EXPLICACION_SOMBRAS",
    "EXPLICACION_MEDIOS",
    "MAX_PROBLEMAS_POR_CODIGO",
    # remuestreo (exportar a 65 para una entrega final; NUNCA por defecto)
    "remuestrear_lut",
    "explicacion_remuestreo",
    "rejilla_del_dominio",
    "TAMANO_ENTREGA_FINAL",
    # LUT malos (para probar el QC y para el test entregable T4)
    "catalogo_luts_malos",
    "lut_desde_curvas",
    "lut_solo_rojo",
    "lut_no_monotono",
    "lut_con_banding",
    "lut_fuera_de_gamut",
    "lut_plano",
    "lut_con_nan",
    "lut_canales_invertidos",
    # ASC CDL
    "leer_cdl",
    "leer_cdls",
    "escribir_cdl",
    "escribir_cdls",
    "cdl_a_xml",
    "EXTENSIONES_CDL",
    "MAX_BYTES_CDL",
    # bundle
    "guardar_sesion",
    "abrir_sesion",
    "EXTENSION_BUNDLE",
    "FORMATO_VERSION",
    "MAX_DESCOMPRIMIDO",
    "MAX_ENTRADAS",
    "DECIMALES_LUT_BUNDLE",
]
