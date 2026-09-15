"""Detector de desajuste de contenido: "estas dos escenas no son comparables".

PARA QUE SIRVE
--------------
El emparejamiento SIEMPRE devuelve un numero. Si le das un retrato de estudio y
un exterior a pleno sol, te va a calcular una correccion que iguala las dos
medias y las dos covarianzas, el ΔE va a bajar y va a parecer que ha funcionado.
Y no ha funcionado: lo que ha hecho es teñir el retrato de verde porque el otro
plano tiene un prado. Esto es lo que evita que Mario se lo crea.

QUIEN DECIDE: LA HUELLA, SI LA HAY
----------------------------------
Hay **dos instrumentos** para responder a la misma pregunta, y no son igual de
buenos. Medidos sobre el material del generador (tabla completa en NOTAS.md §4):

| | peor par COMPARABLE | mejor par NO comparable | hueco |
|---|---|---|---|
| huella de `ClipAnalysis` (parecido) | 0.756 | 0.219 | **0.54** |
| rasgos de pixeles (distancia) | 0.612 | 0.753 | 0.14 |

O sea que **la huella separa cuatro veces mejor**. Y sobre todo: a la huella no
la mueve un grado, porque esta hecha de RANGOS y un grado es una funcion
monotona. Medido sobre el MISMO plano con grados encima (la primera columna es
la distancia de rasgos, con el umbral en 0.70):

| grado encima del mismo plano | rasgos | huella |
|---|---|---|
| CDL fuerte | 0.511 | 0.9988 |
| CDL fuerte + LUT de look | **0.612** | 0.9967 |
| CDL extremo | 0.564 | 0.9982 |
| CDL extremo + LUT (la imagen ya esta destrozada) | **2.097** | 0.9100 |

Los rasgos de pixeles se acercan al umbral con un grado normal (0.612 contra
0.70: **0.088 de margen**) y lo revientan cuando el grado aplasta la imagen. La
huella no se entera de ninguno de los cuatro.

Por eso la regla es:

* **si las dos entradas traen `fingerprint`, la huella decide y punto.** Los
  rasgos de pixeles se siguen midiendo y se cuentan en `razones`, pero no
  levantan la bandera: meter un instrumento peor en un OR junto a uno mejor solo
  añade falsos positivos.
* **si no hay huella** (`emparejar` con listas de pixeles sueltas), se cae a los
  rasgos de pixeles, que es una via mas debil y esta dicho en NOTAS.md §4 con el
  numero exacto. Para material gradado fuerte hay que pasar huellas: tanto
  `emparejar` como `emparejar_analisis` las aceptan.

LOS RASGOS DE PIXELES: INVARIANTES A LA EXPOSICION Y AL BALANCE
---------------------------------------------------------------
El detector tiene que separar dos cosas que de lejos se parecen mucho:

* "el mismo plano con otra exposicion o otro balance"  -> eso SI se iguala, es
  literalmente para lo que existe la app;
* "otra escena distinta"                               -> eso hay que marcarlo.

Asi que los dos rasgos estan elegidos para NO moverse cuando cambia la
exposicion o el balance. En el espacio de trabajo (que es logaritmico) un cambio
de exposicion es aproximadamente un desplazamiento comun y un cambio de balance
un desplazamiento distinto por canal. Por tanto:

1. **`perfil`** — el perfil de percentiles de la luma **normalizado**: se le
   resta la mediana y se divide por el recorrido p5..p95. Eso quita el
   desplazamiento (exposicion) y la escala (contraste); lo que queda es la FORMA
   del histograma. Un retrato tiene la masa en los medios; un exterior con cielo
   quemado tiene dos jorobas y una cola larga arriba.

2. **`croma`** — histograma 2D de la cromaticidad `(R-G, B-G)` **centrada en su
   propia media y dividida por su propia dispersion**, comparado con la
   distancia de Hellinger. Centrar mata el balance de blancos (que es justo lo
   que queremos poder corregir) y normalizar mata la ganancia global; lo que
   queda es *como estan repartidos los colores de la escena unos respecto de
   otros*. Es el rasgo que de verdad separa un retrato (piel + fondo neutro,
   todo en una franja) de un exterior (cielo azul por un lado, prado verde por
   otro).

La distancia es la suma de las dos y se compara con `UMBRAL_DESAJUSTE`. Los
numeros medidos con el material del generador estan en `core/matching/NOTAS.md`;
en resumen: el mismo plano a otra exposicion da 0.27-0.31, dos tonos de piel
distintos en el mismo decorado 0.37-0.59, y estudio contra exterior 1.07-1.20.
El umbral esta en 0.70, en mitad del hueco.

Descarte meter tambien las correlaciones entre canales y la dispersion cromatica
absoluta: las medi y **no separaban** (estudio contra exterior daba 0.02 de
diferencia de correlacion, menos que dos tonos de piel distintos). Estaban de
adorno y las quite.

MEDIR LA DISTANCIA **DESPUES** DEL TRANSPORTE: PROBADO Y DESCARTADO
-------------------------------------------------------------------
Era mi propia propuesta para arreglar el falso positivo del grado fuerte, y la
medi antes de escribirla. **No funciona**: arregla una punta y rompe la otra.

| par | distancia antes | despues del transporte |
|---|---|---|
| mismo plano + CDL fuerte | 0.511 | **0.070** ✔ arregla |
| mismo plano + CDL extremo + LUT | 2.097 | **1.927** ✘ sigue roto |
| piel 0 vs piel 5 (mismo decorado) | 0.588 | **0.673** ✘ empeora |
| retrato vs campo de ruido (¡distintos!) | 0.753 | **0.421** ✘ empeora |

El hueco **se invierte**: despues del transporte el peor par comparable (0.673)
queda POR ENCIMA del mejor par no comparable (0.421), asi que no existe ningun
umbral que los separe. Tiene sentido: el transporte iguala media y covarianza por
construccion, o sea que borra justo la parte de la diferencia que SI distinguia
dos escenas, y deja solo la parte de orden superior, que es ruido para esto.
La tabla completa esta en NOTAS.md §4. El arreglo bueno era la huella.

SI SOLO HAY UN `ColorStats` Y NO HAY PIXELES
--------------------------------------------
El histograma 2D de croma necesita pixeles. Con solo `ColorStats` se usa en su
lugar el `saturation_hist` que trae el contrato, tambien con Hellinger. Es del
mismo orden de magnitud, pero **no esta calibrado con el mismo material**:
cuando escribi esto el agente B estaba definiendo a la vez como calcula la
saturacion. Si hay pixeles se usan los pixeles, que es el camino medido.

LA HUELLA: COMO SE COMPARA Y DONDE ESTA EL UMBRAL
--------------------------------------------------
`d_huella = 1 - coseno`, con el coseno **recortado por abajo a cero**, igual que
hace `parecido_de_huellas` del agente B. Se recorta y no se reescala para que el
umbral signifique "se parecen tanto por ciento" y no "tanto por ciento por encima
de lo que se parecerian dos planos al azar": los tres bloques de la huella van
centrados en cero, asi que dos planos sin relacion dan coseno alrededor de 0 y a
veces negativo, que para esto es lo mismo.

`UMBRAL_HUELLA = 0.50` (o sea: se exige un parecido de **al menos 0.50**). Sale
del punto medio del hueco MEDIDO, no de una intuicion: el peor par comparable da
parecido 0.756 y el mejor par no comparable 0.219, asi que 0.50 deja 0.256 de
margen por un lado y 0.281 por el otro. La tabla entera esta en NOTAS.md §4.

QUE ACEPTA
----------
`desajuste_de_contenido(a, b, *, huellas=None)` acepta, en cualquier combinacion:

* un `ClipAnalysis` (usa `.pixels` si los trae, y si no `.stats`; y `.fingerprint`);
* un `ColorStats` suelto;
* una lista de pixeles `(N, 3)` o una imagen `(alto, ancho, 3)`.

`huellas=(a, b)` es la forma de pasar dos huellas cuando las entradas son
pixeles sueltos y no `ClipAnalysis`. Manda sobre lo que traigan las entradas.

No importa `core.analysis`: lee los campos del contrato y nada mas.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from core.contracts import LUMA_REC709, PERCENTILE_LEVELS

__all__ = [
    "ALFA_SUAVIZADO",
    "BINS_CROMA",
    "PESO_CROMA",
    "PESO_PERFIL",
    "RANGO_CROMA",
    "UMBRAL_DESAJUSTE",
    "UMBRAL_HUELLA",
    "desajuste_de_contenido",
    "distancia_hellinger",
    "rasgos_de_contenido",
]

#: Rejilla del histograma 2D de cromaticidad centrada y normalizada.
BINS_CROMA: int = 12
RANGO_CROMA: float = 3.0

#: Suavizado de Laplace del histograma, en cuentas por celda. Con una imagen
#: entera es despreciable; con cien pixeles aplasta el histograma contra el
#: uniforme, que es el lado seguro: con poca muestra el detector prefiere NO
#: marcar desajuste y dejar que sea la confianza quien avise de que hay poco.
ALFA_SUAVIZADO: float = 0.5

PESO_PERFIL: float = 1.0
PESO_CROMA: float = 1.0

#: Por encima de esto, las dos escenas no se consideran comparables **cuando no
#: hay huella**. Calibrado: ver NOTAS.md §4. Es la via debil: el hueco medido es
#: de solo 0.14 (de 0.612 a 0.753) y un grado muy agresivo lo cruza.
UMBRAL_DESAJUSTE: float = 0.70

#: Maxima distancia de huella tolerada, con `distancia = 1 - parecido`. O sea:
#: se exige un parecido de al menos 0.50. Punto medio del hueco MEDIDO con la
#: huella del agente B: peor par comparable 0.756, mejor par no comparable 0.219.
#: Ver NOTAS.md §4 para la tabla completa.
UMBRAL_HUELLA: float = 0.50

_I_P5 = PERCENTILE_LEVELS.index(5.0)
_I_P50 = PERCENTILE_LEVELS.index(50.0)
_I_P95 = PERCENTILE_LEVELS.index(95.0)


def distancia_hellinger(p: np.ndarray, q: np.ndarray) -> float:
    """Distancia de Hellinger entre dos histogramas normalizados. 0..1."""
    a = np.asarray(p, dtype=np.float64).reshape(-1)
    b = np.asarray(q, dtype=np.float64).reshape(-1)
    if a.shape != b.shape or a.size == 0:
        raise ValueError(f"histogramas incompatibles: {a.shape} y {b.shape}")
    sa, sb = a.sum(), b.sum()
    if sa <= 0 or sb <= 0:
        return 0.0
    coef = float(np.sum(np.sqrt((a / sa) * (b / sb))))
    return float(np.sqrt(max(0.0, 1.0 - min(coef, 1.0))))


def _perfil_normalizado(perc: np.ndarray) -> np.ndarray:
    """Percentiles -> forma del histograma, sin exposicion ni contraste."""
    p = np.asarray(perc, dtype=np.float64).reshape(-1)
    recorrido = float(p[_I_P95] - p[_I_P5])
    if not np.isfinite(recorrido) or abs(recorrido) < 1e-12:
        return np.zeros_like(p)
    return (p - p[_I_P50]) / recorrido


def _histograma_croma(px: np.ndarray) -> np.ndarray:
    """Histograma 2D de (R-G, B-G) centrado en su media y normalizado."""
    c = np.stack([px[:, 0] - px[:, 1], px[:, 2] - px[:, 1]], axis=1)
    c = c - c.mean(axis=0)
    escala = float(np.sqrt(np.mean(np.sum(c**2, axis=1))))
    if escala > 1e-12:
        c = c / escala
    borde = [[-RANGO_CROMA, RANGO_CROMA], [-RANGO_CROMA, RANGO_CROMA]]
    c = np.clip(c, -RANGO_CROMA, RANGO_CROMA)
    h, _, _ = np.histogram2d(c[:, 0], c[:, 1], bins=BINS_CROMA, range=borde)
    h = h + ALFA_SUAVIZADO
    return (h / h.sum()).reshape(-1)


def rasgos_de_contenido(x: Any, *, preferir: str = "auto") -> dict[str, Any]:
    """Extrae de lo que sea que le den los rasgos comparables.

    `preferir` vale "auto" (pixeles si los hay, si no `ColorStats`), "pixeles" o
    "stats"; los dos ultimos lanzan si esa via no esta disponible.

    Devuelve `perfil` (len(PERCENTILE_LEVELS),), `croma` (histograma
    normalizado), `de_pixeles` (bool: si el croma sale de pixeles o de
    `saturation_hist`), `huella` ((96,) o None) y `n` (muestras, 0 si no se sabe).
    """
    if preferir not in ("auto", "pixeles", "stats"):
        raise ValueError(f"rasgos_de_contenido: 'preferir' no puede ser {preferir!r}")

    huella = getattr(x, "fingerprint", None)
    if huella is not None:
        huella = np.asarray(huella, dtype=np.float64).reshape(-1)

    stats = getattr(x, "stats", None)  # ClipAnalysis
    if stats is None and hasattr(x, "cov") and hasattr(x, "percentiles"):
        stats = x  # ColorStats suelto

    pixeles = getattr(x, "pixels", None)
    if stats is None and pixeles is None:
        pixeles = x
    if preferir == "stats":
        if stats is None:
            raise TypeError("rasgos_de_contenido: me has pedido stats y no hay ColorStats")
        pixeles = None
    if preferir == "pixeles" and (pixeles is None or not np.size(pixeles)):
        raise TypeError("rasgos_de_contenido: me has pedido pixeles y no hay pixeles")

    if pixeles is not None and np.size(pixeles):
        try:
            px = np.asarray(pixeles, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "desajuste_de_contenido: no se que es esto. Acepto ClipAnalysis, "
                f"ColorStats, (N, 3) o (alto, ancho, 3); llego {type(pixeles).__name__}"
            ) from exc
        if px.ndim == 0 or px.shape[-1] != 3:
            raise TypeError(
                "desajuste_de_contenido: no se que es esto. Acepto ClipAnalysis, "
                f"ColorStats, (N, 3) o (alto, ancho, 3); llego {np.shape(pixeles)}"
            )
        px = px.reshape(-1, 3)
        px = px[np.isfinite(px).all(axis=1)]
        if px.shape[0] >= 2:
            return {
                "perfil": _perfil_normalizado(np.percentile(px @ LUMA_REC709, PERCENTILE_LEVELS)),
                "croma": _histograma_croma(px),
                "de_pixeles": True,
                "huella": huella,
                "n": int(px.shape[0]),
            }
        if stats is None:
            # Un pixel (o ninguno) no tiene forma ni reparto de croma.
            return {
                "perfil": np.zeros(len(PERCENTILE_LEVELS)),
                "croma": np.full(BINS_CROMA * BINS_CROMA, 1.0 / (BINS_CROMA * BINS_CROMA)),
                "de_pixeles": True,
                "huella": huella,
                "n": int(px.shape[0]),
            }

    if stats is None:
        raise TypeError("desajuste_de_contenido: no encuentro ni stats ni pixeles utilizables")

    # Camino ColorStats: la luma se aproxima ponderando los percentiles por
    # canal con los pesos Rec.709. No es identico a sacar el percentil de la
    # luma (el percentil no es lineal), pero para comparar FORMAS entre dos
    # planos sirve y evita pedirle otro campo al contrato.
    perc = np.asarray(stats.percentiles, dtype=np.float64).reshape(len(PERCENTILE_LEVELS), 3)
    sat = np.asarray(stats.saturation_hist, dtype=np.float64).reshape(-1)
    sat = np.clip(sat, 0.0, None)
    if sat.sum() <= 0:
        sat = np.full_like(sat, 1.0 / max(sat.size, 1))
    return {
        "perfil": _perfil_normalizado(perc @ LUMA_REC709),
        "croma": sat,
        "de_pixeles": False,
        "huella": huella,
        "n": int(getattr(stats, "n_samples", 0) or 0),
    }


def desajuste_de_contenido(
    a: Any, b: Any, *, huellas: tuple[Any, Any] | None = None
) -> tuple[bool, float, tuple[str, ...]]:
    """Dice si dos planos son comparables.

    Devuelve `(hay_desajuste, distancia, razones)`. `razones` va en castellano y
    ordenada por importancia, lista para enseñarla tal cual.

    **Quien decide**: si hay huella en los dos lados, decide la huella
    (`UMBRAL_HUELLA`); si no, deciden los rasgos de pixeles
    (`UMBRAL_DESAJUSTE`), que es la via debil. El porque, con los numeros
    medidos, esta en el docstring del modulo.

    `distancia` es **siempre** la de los rasgos de pixeles, decida ella o no,
    porque es una magnitud continua y sirve para ordenar candidatos a referencia.
    Si quieres la de la huella, esta en las razones.

    `huellas=(a, b)` permite pasar las dos huellas cuando las entradas son
    pixeles sueltos. Manda sobre lo que traigan las entradas.
    """
    ra = rasgos_de_contenido(a)
    rb = rasgos_de_contenido(b)
    if huellas is not None:
        ha_ext, hb_ext = huellas
        ra["huella"] = None if ha_ext is None else np.asarray(ha_ext, dtype=np.float64).reshape(-1)
        rb["huella"] = None if hb_ext is None else np.asarray(hb_ext, dtype=np.float64).reshape(-1)
    if ra["de_pixeles"] != rb["de_pixeles"]:
        # Uno trae pixeles y el otro solo ColorStats. Los dos histogramas de
        # croma no son el mismo y compararlos no significa nada, asi que se
        # baja a la via comun (stats) si los dos pueden. Si no pueden, se dice.
        try:
            ra = rasgos_de_contenido(a, preferir="stats")
            rb = rasgos_de_contenido(b, preferir="stats")
        except TypeError as exc:
            raise ValueError(
                "desajuste_de_contenido: uno de los dos trae pixeles y el otro "
                "solo ColorStats, y no hay forma comun de compararlos. Pasame "
                "los dos igual."
            ) from exc

    d_perfil = float(np.mean(np.abs(ra["perfil"] - rb["perfil"])))
    d_croma = distancia_hellinger(ra["croma"], rb["croma"])
    distancia = PESO_PERFIL * d_perfil + PESO_CROMA * d_croma

    parecido = _parecido_de_huellas(ra["huella"], rb["huella"])

    # Si hay huella, decide la huella; si no, deciden los rasgos de pixeles, que
    # es la via debil. Ver el docstring del modulo: la huella separa cuatro veces
    # mejor y no la mueve un grado, asi que meter los rasgos de pixeles en un OR
    # a su lado solo añadiria falsos positivos.
    hay = (
        distancia > UMBRAL_DESAJUSTE if parecido is None else (1.0 - parecido) > UMBRAL_HUELLA
    )

    razones: list[tuple[float, str]] = []
    if parecido is not None and (1.0 - parecido) > UMBRAL_HUELLA * 0.5:
        razones.append(
            (
                10.0 + (1.0 - parecido),  # la huella manda, va siempre la primera
                f"Los dos planos no tienen la misma pinta: se parecen un "
                f"{parecido:.0%} en composicion, encuadre y reparto del detalle.",
            )
        )
    if d_croma > 0.35:
        razones.append(
            (
                d_croma,
                "Los colores de las dos escenas no estan repartidos igual "
                f"(diferencia {d_croma:.2f})"
                + (
                    ": puede ser solo que uno lleve un grado fuerte encima."
                    if parecido is not None
                    else ": no es que tengan otra luz, es que hay cosas distintas "
                    "delante de la camara."
                ),
            )
        )
    if d_perfil > 0.12:
        razones.append(
            (
                d_perfil,
                "El reparto de luces y sombras es distinto: los dos histogramas "
                f"tienen otra forma (diferencia {d_perfil:.2f}).",
            )
        )
    razones.sort(key=lambda par: -par[0])
    texto = [t for _, t in razones]
    if hay:
        texto.insert(
            0,
            "Estas dos escenas no parecen comparables: el igualado va a dar un "
            "numero bueno de todas formas, no te fies de el.",
        )
    elif not texto:
        texto.append("Las dos escenas tienen contenido parecido; se pueden comparar.")
    return hay, distancia, tuple(texto)


def _parecido_de_huellas(ha: Any, hb: Any) -> float | None:
    """Coseno entre dos huellas, recortado a 0..1. `None` si no hay dos huellas.

    Recortado por abajo y no reescalado, igual que `parecido_de_huellas` del
    agente B: los tres bloques de la huella van centrados en cero, asi que dos
    planos sin relacion dan coseno alrededor de 0 y a veces negativo, y para esto
    las dos cosas significan lo mismo.
    """
    if ha is None or hb is None:
        return None
    ha = np.asarray(ha, dtype=np.float64).reshape(-1)
    hb = np.asarray(hb, dtype=np.float64).reshape(-1)
    if ha.shape != hb.shape or ha.size == 0:
        return None
    na, nb = float(np.linalg.norm(ha)), float(np.linalg.norm(hb))
    if not (np.isfinite(na) and np.isfinite(nb)) or na <= 0.0 or nb <= 0.0:
        return None
    return float(np.clip(np.dot(ha, hb) / (na * nb), 0.0, 1.0))
