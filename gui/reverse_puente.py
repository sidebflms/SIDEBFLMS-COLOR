"""El panel de ingenieria inversa habla con `core.reverse` **si existe**.

El modulo lo esta escribiendo el agente F en paralelo. Asi que:

1. El import va protegido. Si `core.reverse` no esta, la GUI **no revienta**:
   el panel se dibuja igual y dice «modulo no disponible», con el motivo.
2. Lo que se dibuja sale siempre de `core.contracts.ReverseResult`, que esta
   congelado. O sea que el dia que F aterrice, el panel no cambia una linea:
   solo cambia quien rellena la dataclass.
3. Mientras no este, hay un **sustituto** que hace de verdad una inversion
   pequena y honesta (`_invertir_sustituto`). No devuelve numeros inventados:
   bina los pixeles del par original/coloreado en el cubo, mide el residuo y
   cuenta las celdas que se han quedado sin datos. La cobertura que sale es la
   cobertura que hay, que con una sola imagen es baja de verdad.

COMO SE SABE CUAL DE LOS DOS CONTESTO
--------------------------------------
`invertir()` devuelve `(ReverseResult, origen)` donde `origen` es
`ORIGEN_CORE` o `ORIGEN_SUSTITUTO`, y la pantalla lo pone por escrito. Una
captura con el sustituto no se puede confundir con una captura del modulo bueno.
"""

from __future__ import annotations

import numpy as np

from core.color import delta_e2000
from core.contracts import (
    CDL,
    LUT3D,
    WORKING_SPACE,
    CoverageMap,
    Hotspot,
    ReverseDiagnosis,
    ReverseResult,
)
from core.matching import ajustar_cdl, puntuar_confianza

ORIGEN_CORE = "core.reverse"
ORIGEN_SUSTITUTO = "sustituto de la GUI"

# --- el import protegido ---------------------------------------------------

try:  # pragma: no cover - depende de si el agente F ha aterrizado
    from core.reverse import invertir_grado as _invertir_grado_core

    DISPONIBLE = True
    MOTIVO = ""
except ImportError as exc:  # pragma: no cover
    _invertir_grado_core = None
    DISPONIBLE = False
    MOTIVO = f"core.reverse todavia no esta en el repo ({exc})"
except Exception as exc:  # pragma: no cover - F puede dejarlo a medias
    _invertir_grado_core = None
    DISPONIBLE = False
    MOTIVO = f"core.reverse esta pero no se puede importar: {exc!r}"


# ---------------------------------------------------------------------------
# El sustituto
# ---------------------------------------------------------------------------

#: Rejilla que usa el panel por defecto. 17 y no 33 (que es el defecto del
#: contrato) por un motivo de pantalla, no de calidad: con un solo par de
#: imagenes, un cubo de 33 se queda con el 0,24% de las celdas medidas y el mapa
#: de cobertura sale practicamente en negro. Con 17 sube al 0,77% y al menos se
#: ve la forma de la nube de color. **Los dos numeros son la misma verdad: la
#: cobertura de un solo fotograma es casi nula.** El selector de la pantalla deja
#: pedir 33 y 65 para verlo.
TAM_REJILLA_PANEL = 17


def _binar(original: np.ndarray, coloreado: np.ndarray, tam: int, min_muestras: int):
    """Cuenta cuantas muestras caen en cada celda y que color medio sale."""
    o = np.asarray(original, dtype=np.float64).reshape(-1, 3)
    c = np.asarray(coloreado, dtype=np.float64).reshape(-1, 3)
    finitos = np.isfinite(o).all(axis=1) & np.isfinite(c).all(axis=1)
    o, c = o[finitos], c[finitos]

    idx = np.clip(np.round(np.clip(o, 0.0, 1.0) * (tam - 1)).astype(np.int64), 0, tam - 1)
    plano = (idx[:, 0] * tam + idx[:, 1]) * tam + idx[:, 2]
    n_celdas = tam**3

    counts = np.bincount(plano, minlength=n_celdas).astype(np.int32)
    suma = np.stack([np.bincount(plano, weights=c[:, k], minlength=n_celdas) for k in range(3)], -1)
    suma2 = np.stack(
        [np.bincount(plano, weights=c[:, k] ** 2, minlength=n_celdas) for k in range(3)], -1
    )
    con = counts > 0
    media = np.zeros_like(suma)
    media[con] = suma[con] / counts[con, None]
    var = np.zeros(n_celdas, dtype=np.float64)
    var[con] = np.maximum(
        (suma2[con] / counts[con, None] - media[con] ** 2).mean(axis=1), 0.0
    )
    forma = (tam, tam, tam)
    return (
        counts.reshape(forma),
        media.reshape((*forma, 3)),
        var.reshape(forma).astype(np.float32),
        min_muestras,
    )


def _puntos_calientes(residuo: np.ndarray, *, bloques: int = 6, cuantos: int = 3) -> tuple[Hotspot, ...]:
    """Las zonas donde el residuo es mayor, por bloques. Sin refinar de mas.

    Etiquetar la zona («vineta», «zona local», «degradado») necesita mirar la
    geometria del residuo; aqui se hace lo minimo honesto: si el bloque esta en
    un borde se dice «vineta», si esta dentro «zona local». El modulo del agente
    F lo hara mejor, y cuando llegue esto no se usa.
    """
    h, w = residuo.shape
    bh, bw = max(1, h // bloques), max(1, w // bloques)
    encontrados: list[tuple[float, Hotspot]] = []
    medio = float(np.nanmean(residuo))
    for j in range(bloques):
        for i in range(bloques):
            y, x = j * bh, i * bw
            trozo = residuo[y : y + bh, x : x + bw]
            if trozo.size == 0:
                continue
            m = float(np.nanmean(trozo))
            borde = i in (0, bloques - 1) or j in (0, bloques - 1)
            encontrados.append(
                (m, Hotspot(x=x, y=y, w=trozo.shape[1], h=trozo.shape[0], magnitude=m,
                            label="vineta" if borde else "zona local"))
            )
    encontrados.sort(key=lambda t: t[0], reverse=True)
    return tuple(h for m, h in encontrados[:cuantos] if m > medio * 1.15)


def _invertir_sustituto(
    original: np.ndarray,
    coloreado: np.ndarray,
    *,
    tam_lut: int = TAM_REJILLA_PANEL,
    min_muestras: int = 4,
) -> ReverseResult:
    """Inversion pequena pero de verdad. Ver el docstring del modulo."""
    o = np.asarray(original, dtype=np.float32)
    c = np.asarray(coloreado, dtype=np.float32)
    if o.shape != c.shape or o.ndim != 3 or o.shape[2] != 3:
        raise ValueError(f"el par tiene que ser (alto, ancho, 3) y del mismo tamano: {o.shape} vs {c.shape}")

    px_o, px_c = o.reshape(-1, 3), c.reshape(-1, 3)
    cdl = ajustar_cdl(px_o, px_c)

    counts, media, var, min_m = _binar(o, c, tam_lut, min_muestras)
    cubiertas = counts >= min_m

    # Las celdas SIN datos no se dejan en identidad: se rellenan con lo que
    # diga el CDL ajustado, que es la mejor conjetura que hay. Eso es lo que
    # significa «inventada» en el mapa de cobertura: el valor esta, pero no lo
    # ha medido nadie.
    rejilla = LUT3D.identity(tam_lut).table
    tabla = cdl.apply(rejilla).astype(np.float32)
    tabla[cubiertas] = media[cubiertas].astype(np.float32)
    lut = LUT3D(table=np.clip(tabla, -1.0, 4.0), title="grado recuperado")

    reconstruido = lut.apply(o).astype(np.float32)
    de_antes = delta_e2000(o, c, WORKING_SPACE)
    de_despues = delta_e2000(reconstruido, c, WORKING_SPACE)
    de_despues = np.nan_to_num(np.asarray(de_despues, dtype=np.float64), nan=0.0)
    de_antes = np.nan_to_num(np.asarray(de_antes, dtype=np.float64), nan=0.0)

    medio_antes = float(de_antes.mean()) or 1e-9
    reproducible = float(np.clip(1.0 - de_despues.mean() / medio_antes, 0.0, 1.0))
    cobertura = CoverageMap(counts=counts, variance=var, min_samples=min_m)

    residuo = de_despues.astype(np.float32)
    pico = float(residuo.max()) or 1e-9
    puntos = _puntos_calientes(residuo)
    puro = reproducible > 0.92 and not puntos

    notas_diag: list[str] = []
    if not puro:
        notas_diag.append(
            "Queda residuo que depende de DONDE esta el pixel, no de su color: eso no cabe "
            "en un .cube. Mira el mapa de residuo."
        )
    if cobertura.coverage_fraction() < 0.10:
        notas_diag.append(
            f"Solo el {cobertura.coverage_fraction() * 100:.1f}% del cubo tiene datos reales: "
            f"el resto del LUT es la conjetura del CDL, no una medida."
        )

    confianza = puntuar_confianza(
        n_muestras=float(px_o.shape[0]),
        residuo_de=float(de_despues.mean()),
        extrapolacion=float(1.0 - cobertura.coverage_fraction()),
    )

    return ReverseResult(
        cdl=cdl,
        lut=lut,
        coverage=cobertura,
        diagnosis=ReverseDiagnosis(
            lut_reproducible=reproducible,
            is_pure_lut=puro,
            spatial_residual=(residuo / pico).astype(np.float32),
            hotspots=puntos,
            notes=tuple(notas_diag),
        ),
        delta_e_mean=float(de_despues.mean()),
        delta_e_p95=float(np.percentile(de_despues, 95)),
        delta_e_max=float(de_despues.max()),
        confidence=confianza,
        notes=(
            "Calculado por el sustituto de la GUI, no por core.reverse.",
            f"Rejilla de {tam_lut}; el modulo bueno usara la que le pidan.",
        ),
    )


# ---------------------------------------------------------------------------
# El unico punto de entrada que usa la pantalla
# ---------------------------------------------------------------------------


def invertir(
    original: np.ndarray,
    coloreado: np.ndarray,
    *,
    tam_lut: int = TAM_REJILLA_PANEL,
    min_muestras: int = 4,
) -> tuple[ReverseResult, str]:
    """Devuelve `(resultado, origen)`. `origen` dice quien lo ha calculado.

    Si `core.reverse` esta, se llama con la firma acordada
    `invertir_grado(original, coloreado, *, tam_lut, space, min_muestras)`. Si
    esta pero se atraganta, se cae al sustituto y se dice en el origen: una
    pantalla en blanco no ayuda a nadie a las tres de la manana.
    """
    if DISPONIBLE and _invertir_grado_core is not None:
        try:
            resultado = _invertir_grado_core(
                original,
                coloreado,
                tam_lut=tam_lut,
                space=WORKING_SPACE,
                min_muestras=min_muestras,
            )
            return resultado, ORIGEN_CORE
        except Exception as exc:  # pragma: no cover
            fallo = f"{ORIGEN_SUSTITUTO} (core.reverse fallo: {exc!r})"
            return _invertir_sustituto(original, coloreado, tam_lut=tam_lut,
                                       min_muestras=min_muestras), fallo
    return (
        _invertir_sustituto(original, coloreado, tam_lut=tam_lut, min_muestras=min_muestras),
        ORIGEN_SUSTITUTO,
    )


def cdl_a_numeros(cdl: CDL) -> list[tuple[str, float]]:
    """Los diez numeros del CDL con su nombre, en el orden del estandar ASC."""
    return [
        ("slope R", cdl.slope[0]), ("slope G", cdl.slope[1]), ("slope B", cdl.slope[2]),
        ("offset R", cdl.offset[0]), ("offset G", cdl.offset[1]), ("offset B", cdl.offset[2]),
        ("power R", cdl.power[0]), ("power G", cdl.power[1]), ("power B", cdl.power[2]),
        ("sat", cdl.saturation),
    ]


__all__ = [
    "DISPONIBLE",
    "MOTIVO",
    "ORIGEN_CORE",
    "ORIGEN_SUSTITUTO",
    "TAM_REJILLA_PANEL",
    "cdl_a_numeros",
    "invertir",
]
