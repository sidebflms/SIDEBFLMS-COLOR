"""`core.analysis` — de un fichero de video a `ColorStats` y a una huella.

Lo que hace este modulo, en una frase: **mirar un plano y resumirlo en numeros
con los que se pueda decidir**. El agente C empareja con esos numeros y el F los
usa de referencia, asi que si aqui hay un sesgo, lo hay en toda la app.

LA API PUBLICA, QUE ES CONTRA LO QUE ESCRIBE TODO EL MUNDO
----------------------------------------------------------
- `extraer_fotogramas(ruta, n_fotogramas=12, space=None)` -> (k, alto, ancho, 3)
  float32 en `WORKING_SPACE`, repartidos a lo largo del clip.
- `analizar_clip(ruta, ...)` -> `ClipAnalysis` de un fichero.
- `analizar_imagen(img, clip_id=..., ...)` -> `ClipAnalysis` de algo que ya esta
  en memoria.
- `estadisticas(datos, space=...)` -> `ColorStats`, con (alto, ancho, 3) o (N, 3).
- `huella_de_contenido(img)` -> (96,) float32 de norma 1.
- `parecido_de_huellas(a, b)` -> 0..1.

Todos los fallos previsibles salen como `ErrorAnalisis` (o una hija) con un
mensaje en castellano: fichero que no existe, fichero que no es un video, clip
truncado, ffmpeg que no esta instalado.

Las decisiones (que percentiles, que es "saturacion", que pasa con la covarianza
degenerada, de que estan hechos los 96 numeros) estan en `NOTAS.md`, con los
numeros medidos.
"""

from __future__ import annotations

from .errores import (
    ErrorAnalisis,
    ErrorFFmpeg,
    FicheroNoEncontrado,
    FormatoNoSoportado,
    HerramientaNoDisponible,
)
from .fingerprint import (
    BINS_ORIENTACION,
    PESOS,
    REJILLA_DETALLE,
    REJILLA_LUMA,
    huella_de_contenido,
    parecido_de_huellas,
)
from .frames import (
    ESPACIO_ASUMIDO_LINEAL,
    ESPACIO_ASUMIDO_VIDEO,
    N_FOTOGRAMAS_POR_DEFECTO,
    InfoMedio,
    extraer_fotogramas,
    sondear,
)
from .lote import ResultadoLoteAnalisis, analizar_lote
from .stats import (
    FRACCION_PIEL_MINIMA,
    MAX_PIXELES_POR_DEFECTO,
    PERCENTIL_BLANCO,
    PERCENTIL_NEGRO,
    PIXELES_PIEL_MINIMOS,
    analizar_clip,
    analizar_imagen,
    estadisticas,
    saturacion_hsv,
)

__all__ = [
    # API principal
    "extraer_fotogramas",
    "analizar_clip",
    "analizar_imagen",
    "analizar_lote",
    "ResultadoLoteAnalisis",
    "estadisticas",
    "huella_de_contenido",
    "parecido_de_huellas",
    # utilidades
    "sondear",
    "saturacion_hsv",
    "InfoMedio",
    # errores
    "ErrorAnalisis",
    "ErrorFFmpeg",
    "FicheroNoEncontrado",
    "FormatoNoSoportado",
    "HerramientaNoDisponible",
    # constantes documentadas
    "BINS_ORIENTACION",
    "ESPACIO_ASUMIDO_LINEAL",
    "ESPACIO_ASUMIDO_VIDEO",
    "FRACCION_PIEL_MINIMA",
    "MAX_PIXELES_POR_DEFECTO",
    "N_FOTOGRAMAS_POR_DEFECTO",
    "PERCENTIL_BLANCO",
    "PERCENTIL_NEGRO",
    "PESOS",
    "PIXELES_PIEL_MINIMOS",
    "REJILLA_DETALLE",
    "REJILLA_LUMA",
]
