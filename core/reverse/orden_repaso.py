"""Orden de repaso para el paso 5 del modo fácil: TRIAJE, no CERTIFICACIÓN.

POR QUÉ EXISTE (día 6)
-----------------------
`confianza_destino.py` (día 5) midió que `cobertura_destino` y
`muestras_p10_zona` predicen el ΔE2000 real de un LUT aplicado a un plano de
destino, con AUC 0.726-0.966 DENTRO de cada una de 8 "clases de material"
(rejilla del cubo × compresión × recorte de altas luces) — pero el umbral de
"cobertura buena" cambia mucho de una clase a otra (0.994 en 17³ comprimido,
0.975 en 33³ sin comprimir con recorte: `CALIBRACION-CONFIANZA-DESTINO.md`
§5). Ninguna combinación cruza el 95% que hacía falta para CERTIFICAR («alta
= me lo llevo sin mirar»), así que ese informe no conecta nada a una etiqueta
alta/media/baja.

El día 6 Mario decidió que el modo fácil no necesita certificar, necesita
TRIAR: ordenar una lista de candidatos de peor a mejor para que el paso 5
("repasar") enseñe «estos son los que yo miraría, por este orden» — sin
mostrar nunca un número. Es un problema de RANKING, no de calibración, y el
listón es mucho más bajo: mejor que un orden al azar, no 95% de aciertos.

EL HALLAZGO QUE APROVECHA ESTE MÓDULO: LA CLASE CAMBIA LA ESCALA
--------------------------------------------------------------------
`CALIBRACION-CONFIANZA-DESTINO.md` §3.2/§5 midió que la clase de material no
es ruido que promediar: CAMBIA LA ESCALA de las demás señales. Un
`cobertura_destino` de 0.99 es normal en 17³ comprimido (media medida 0.86) y
malo en 33³ sin comprimir con recorte (media medida 0.65). Por eso este
módulo NO compara `cobertura_destino`/`muestras_p10_zona`/`planos_acumulados`
crudos entre candidatos de clases distintas: los convierte a un z-score
DENTRO de su propia clase antes de comparar.

Medido en `tests/calibracion_destino/ordenar.py` sobre las mismas 1.700 filas
"fuera de plano" del día 5 (lotes simulados de 20 candidatos, 20
particiones): el orden calibrado por clase saca **precisión@5 = 0.40 y
precisión@10 = 0.62-0.63**, frente a **0.25 / 0.50 de un orden al azar** y
**0.373 / 0.609 del mismo cálculo SIN normalizar por clase** ("ingenuo"). La
comparación pareada sobre los mismos lotes confirma que no es ruido de
agregado: el orden calibrado gana en más lotes de los que pierde (451 contra
267 en precisión@5, empatando el resto). Ver `CIFRAS.md` §17 y el comando
exacto ahí anotado. **No llega a ser un orden perfecto — sigue siendo mejor
que las señales crudas sin ajustar, que es el listón que pedía el encargo.**

QUÉ CLASE SE CONOCE DE VERDAD EN PRODUCCIÓN
-----------------------------------------------
El tamaño de rejilla del cubo SÍ se conoce siempre: es una constante de
configuración (17 para el panel, 33 para el `.cube` final), no algo que haya
que medir. La compresión y el recorte de altas luces NO se conocen sobre un
clip real de Mario hoy: `core.contracts.ClipRef` no lleva códec ni ninguna
marca de si se recortaron altas luces. Por eso `ClaseMaterial.compresion` y
`.recorte` son `bool | None`: `None` ("desconocida") usa una calibración
marginada por `tam_rejilla` (mezclando las cuatro combinaciones de
compresión/recorte que caben en esa rejilla) en vez de fingir que se sabe
algo que no se sabe. La medición de arriba lo confirma como razonable: la
variante "desconocida" (sólo rejilla) rindió tan bien como la "informada"
(compresión y recorte exactos, sólo posible dentro del arnés de calibración)
— **precisión@5 = 0.40 en las dos**, precisión@10 ligeramente mejor en la
desconocida (0.629 contra 0.623). No hace falta saber compresión/recorte para
que esto funcione.

Si en algún momento el códec del archivo llega a estar disponible en
`ClipRef` (hoy NO lo está — no se inventa un campo que no existe en el
contrato, ver el informe final del encargo), se podría afinar la clase
"compresión" con eso. Es una decisión de producto, no de este módulo.

`variance_zona` SE EXCLUYE A PROPÓSITO
------------------------------------------
`CALIBRACION-CONFIANZA-DESTINO.md` §3.2/§6.1: su signo se invierte dentro de
la clase de material comprimido incluso DESPUÉS de separar por clase — no es
un problema que la normalización por clase arregle, es un problema
estructural de cómo `CoverageMap.variance` trata las celdas con menos de 2
muestras (pone `variance = 0`, que se lee como "zona limpia" cuando en
realidad es "no hay datos"). Meterla en la puntuación empeoraría el orden
justo en el material más difícil (comprimido), que es exactamente donde el
triaje más falta hace.

NUNCA UN NÚMERO EN PANTALLA
-------------------------------
`orden_de_repaso()` devuelve una lista de identificadores, de peor a mejor:
nunca una lista de notas. La función que sí calcula un número interno
(`_puntuacion_interna`) es privada a propósito y no forma parte de la API de
este módulo. Ver `gui/asistente_facil.py::ejecutar_repasar`, que es quien la
usa para decidir el ORDEN de una lista cuyo contenido (qué clips entran) lo
decide otra cosa.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from core.reverse.confianza_destino import FeaturesDestino

__all__ = ["ClaseMaterial", "CandidatoOrden", "orden_de_repaso"]

#: Unidad: adimensional (guarda de división). Ninguna clase con desviación 0
#: (p.ej. `planos_acumulados` constante dentro de una clase que sólo vio
#: extracciones de un solo fotograma) puede dividir por 0; con la diferencia
#: también en 0 en ese caso, el z-score sale 0 sin inventar una escala.
_DESV_MINIMA = 1e-6


@dataclass(frozen=True)
class ClaseMaterial:
    """La clase de material de un candidato, tal y como se conoce (o no) en
    producción. Ver el docstring del módulo: `tam_rejilla` siempre se sabe,
    `compresion`/`recorte` casi nunca (quedan en `None`, "desconocida")."""

    #: Unidad: lado del cubo del LUT (17 o 33 en este repo). Constante de
    #: configuración, no medida por clip.
    tam_rejilla: int
    #: `True`/`False` si se sabe, `None` si no (el caso normal en producción).
    compresion: bool | None = None
    #: `True`/`False` si se sabe, `None` si no (el caso normal en producción).
    recorte: bool | None = None


@dataclass(frozen=True)
class CandidatoOrden:
    """Un candidato a ordenar: su identificador, sus señales de destino
    (`calcular_features_destino`, sin tocar) y su clase de material."""

    id: str
    features: FeaturesDestino
    clase: ClaseMaterial


@dataclass(frozen=True)
class _EstadisticasClase:
    """Media y desviación, DENTRO de una clase, de las tres señales que entran
    en la puntuación. Calibradas una vez sobre datos de verdad conocida, no en
    cada arranque: ver la cabecera de `_ESTADISTICAS_POR_CLASE`."""

    media_cobertura: float
    desv_cobertura: float
    media_log_muestras: float
    desv_log_muestras: float
    media_log_planos: float
    desv_log_planos: float


#: Estadísticas de calibración por clase: `(tam_rejilla, compresion, recorte)`
#: -> `(media_cobertura, desv_cobertura, media_log_muestras, desv_log_muestras,
#: media_log_planos, desv_log_planos)`. `compresion`/`recorte` en `None` es la
#: clase "desconocida", marginada dentro de esa `tam_rejilla` (mezcla las
#: cuatro combinaciones de compresión/recorte que caben ahí). `(0, None, None)`
#: es el colchón final, marginado de todo, para una `tam_rejilla` que nunca
#: apareció en la calibración.
#:
#: MEDIDO, no inventado: 1.700 filas "fuera de plano" de
#: `tests/calibracion_destino/datos/` (el mismo material sintético del día 5:
#: `simple_000_120.csv` + `lote_000_100.csv`). Reproducir con
#:
#:     .venv/bin/python -m tests.calibracion_destino.ordenar | grep "CALD orden estadisticas"
#:
#: Fecha: 17-09. Si se vuelve a medir (más material, otro generador) hay que
#: pegar los números nuevos aquí a mano: no se calculan en tiempo de
#: ejecución para que arrancar la GUI no dependa de tener los CSV de
#: calibración en el disco.
_ESTADISTICAS_POR_CLASE: dict[tuple[int, bool | None, bool | None], tuple[
    float, float, float, float, float, float
]] = {
    (0, None, None): (0.766977, 0.265599, 2.443335, 2.889287, 0.910871, 0.441134),  # n=1700
    (17, False, False): (0.847361, 0.187763, 3.010808, 2.744712, 0.693147, 0.000000),  # n=150
    (17, False, True): (0.781323, 0.240617, 2.575666, 2.994203, 0.693147, 0.000000),  # n=150
    (17, True, False): (0.863751, 0.168499, 3.184900, 2.749360, 0.693147, 0.000000),  # n=150
    (17, True, True): (0.805983, 0.219254, 2.789541, 2.980816, 0.693147, 0.000000),  # n=150
    (17, None, None): (0.824604, 0.208498, 2.890229, 2.878949, 0.693147, 0.000000),  # n=600
    (33, False, False): (0.750394, 0.284358, 2.438797, 3.016080, 1.155810, 0.547905),  # n=400
    (33, False, True): (0.650154, 0.302604, 1.256145, 2.194005, 0.693147, 0.000000),  # n=150
    (33, True, False): (0.769877, 0.273091, 2.596922, 2.992606, 1.155810, 0.547905),  # n=400
    (33, True, True): (0.689777, 0.293053, 1.445486, 2.288365, 0.693147, 0.000000),  # n=150
    (33, None, None): (0.735544, 0.287244, 2.199575, 2.865685, 1.029629, 0.510671),  # n=1100
}


def _estadisticas_de(clave: tuple[int, bool | None, bool | None]) -> _EstadisticasClase:
    return _EstadisticasClase(*_ESTADISTICAS_POR_CLASE[clave])


def _clave_calibrada(clase: ClaseMaterial) -> tuple[int, bool | None, bool | None]:
    """La clave de `_ESTADISTICAS_POR_CLASE` que le toca a `clase`, con
    colchones si la combinación exacta no se midió: primero la clase
    "desconocida" de su misma rejilla, luego la global. Ninguna rejilla nueva
    puede reventar esto, sólo perder precisión (que ya es lo que pasa cuando
    se declara la clase como desconocida)."""
    if clase.compresion is not None and clase.recorte is not None:
        exacta = (clase.tam_rejilla, clase.compresion, clase.recorte)
        if exacta in _ESTADISTICAS_POR_CLASE:
            return exacta
    marginada = (clase.tam_rejilla, None, None)
    if marginada in _ESTADISTICAS_POR_CLASE:
        return marginada
    return (0, None, None)


def _z(valor: float, media: float, desv: float) -> float:
    return (float(valor) - media) / max(desv, _DESV_MINIMA)


def _puntuacion_interna(features: FeaturesDestino, clase: ClaseMaterial) -> float:
    """Media de tres z-scores DENTRO de la clase del candidato. Más alto =
    más fiable (el candidato necesita MENOS repaso). Privada: ver el
    docstring del módulo, este número no sale de aquí hacia ninguna pantalla.

    `cobertura_destino` entra tal cual (ya es 0..1 y monótona: más cobertura,
    menos error, medido en las 8 clases sin una sola inversión). `muestras_
    p10_zona` y `planos_acumulados` entran en `log1p`, igual que hace la
    rampa de `n_muestras` en `core.matching.confianza` (log10, aquí log1p
    natural por comodidad con `np.log1p(0) == 0`): las dos tienen un rango
    que va de 0 a varios miles/varias unidades y la escala lineal las
    dejaría dominadas por los valores grandes.
    """
    e = _estadisticas_de(_clave_calibrada(clase))
    z_cobertura = _z(features.cobertura_destino, e.media_cobertura, e.desv_cobertura)
    z_muestras = _z(np.log1p(features.muestras_p10_zona), e.media_log_muestras, e.desv_log_muestras)
    z_planos = _z(np.log1p(features.planos_acumulados), e.media_log_planos, e.desv_log_planos)
    return float(np.mean([z_cobertura, z_muestras, z_planos]))


def orden_de_repaso(candidatos: Sequence[CandidatoOrden]) -> list[str]:
    """Los `id` de `candidatos`, de PEOR a MEJOR: el primero es el que más
    conviene mirar.

    No decide QUIÉN entra en la lista de repaso (eso lo sigue decidiendo
    `ejecutar_repasar` con sus dos señales binarias, `content_mismatch` y los
    grupos pendientes del paso 1): sólo el orden de lo que ya está en ella.
    Con menos de 2 candidatos no hay nada que ordenar y se devuelve tal cual,
    en el mismo orden de entrada (evita un `sorted` sobre una lista de 0 o 1
    que no cambiaría nada pero costaría una lectura extra).
    """
    if len(candidatos) < 2:
        return [c.id for c in candidatos]
    orden = sorted(candidatos, key=lambda c: _puntuacion_interna(c.features, c.clase))
    return [c.id for c in orden]
