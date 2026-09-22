"""El panel de ingenieria inversa habla con `core.reverse` **si existe**.

1. El import va protegido. Si `core.reverse` no esta, la GUI **no revienta**:
   el panel se dibuja igual y dice «modulo no disponible», con el motivo.
2. Lo que se dibuja sale siempre de `core.contracts.ReverseResult`, que esta
   congelado. O sea que quien rellena la dataclass puede cambiar sin que el
   panel cambie una linea.
3. Si no esta, hay un **sustituto** que hace una inversion pequena y honesta
   (`_invertir_sustituto`). No devuelve numeros inventados: bina los pixeles
   del par original/coloreado en el cubo, mide el residuo y cuenta las celdas
   que se han quedado sin datos. La cobertura que sale es la cobertura que
   hay, que con una sola imagen es baja de verdad.

LA GUI NO DA VEREDICTOS. NUNCA.
-------------------------------
**El sustituto no decide si un grado «es un LUT puro».** Ese veredicto es de
`core.reverse`, que lo toma con dos condiciones a la vez
(`UMBRAL_REPRODUCIBLE_PURO` sobre la fraccion reproducible **y**
`UMBRAL_DE_PURO` sobre el percentil 95 del residuo), y con dos condiciones a
la vez a proposito: una media buena esconde un p95 malo.

Aqui habia una segunda definicion, `reproducible > 0.92 and not puntos`, que
era **mas floja que la del nucleo y se saltaba el p95**. Tres cosas estaban
mal:

* incumple `CONTRATOS.md` («no redefinas umbrales en tu modulo»: el sitio
  donde un numero se convierte en un veredicto tiene que ser uno solo);
* no miraba el percentil 95, que es justo la mitad que el nucleo pide;
* y no era codigo muerto: `invertir()` se cae al sustituto ante **cualquier**
  excepcion de `core.reverse`, asi que un fallo del nucleo degradaba en
  silencio al criterio permisivo y la pantalla llegaba a escribir «Es un LUT
  puro: todo el grado cabe en el .cube».

Esa frase es la mas peligrosa que puede decir esta app: mandar a Mario a
llevarse un `.cube` que no reproduce el grado y a enterarse delante de un
cliente. Equivocarse hacia «no es un LUT puro» solo le hace trabajar de mas.
Asi que el sustituto pone `is_pure_lut=False` **siempre**, lo dice en las
notas, y la pantalla, cuando el veredicto no viene del nucleo, escribe **que
no se ha podido decidir** en vez de decidirlo ella.

COMO SE SABE CUAL DE LOS DOS CONTESTO
--------------------------------------
`invertir()` devuelve una `Inversion`, que ademas del `ReverseResult` trae
`del_nucleo` (¿lo ha calculado `core.reverse`?) y `fallo` (por que no, si no).
La pantalla lo pone por escrito **y ensena un aviso**: caerse a un sustituto
esta bien para poder trabajar; caerse en silencio, no. Una captura con el
sustituto no se puede confundir con una captura del modulo bueno.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.color import delta_e2000
from core.contracts import (
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

#: Lo que la pantalla escribe cuando el veredicto NO lo ha dado `core.reverse`.
#: No es «no es un LUT puro» (eso seria decidirlo) ni «es un LUT puro» (eso
#: seria decidirlo y ademas hacia el lado grave): es «no lo se».
SIN_VEREDICTO = (
    "No se ha podido decidir si es un LUT puro: ese veredicto lo da "
    "core.reverse y aquí no ha contestado."
)


@dataclass(frozen=True)
class Inversion:
    """Lo que devuelve `invertir()`: el resultado y **quien lo ha calculado**.

    `del_nucleo` es la unica pregunta que la pantalla tiene que hacerse antes
    de pintar un veredicto. Si es `False`, el `ReverseResult` es utilizable
    —los numeros que trae son medidos— pero `diagnosis.is_pure_lut` **no es un
    veredicto**, es el valor conservador que hay que poner en la dataclass.
    """

    resultado: ReverseResult
    origen: str
    del_nucleo: bool
    fallo: str = ""

    @property
    def veredicto_fiable(self) -> bool:
        """¿Se puede pintar `is_pure_lut` como lo que dice la app?"""
        return self.del_nucleo

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

#: Por debajo de esta cobertura el sustituto escribe una frase avisando de que
#: casi todo el cubo es conjetura. **Es un umbral de REDACCION, no de
#: veredicto**: solo decide si se escribe una nota, no cambia ningun campo del
#: `ReverseResult` ni afirma nada sobre el grado.
COBERTURA_BAJA_AVISO = 0.10


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


#: Cuanto tiene que destacar un bloque sobre la media del residuo para que el
#: sustituto lo senale. **No es un umbral de veredicto**: no decide si algo es
#: un LUT ni que es lo que hay en esa zona, solo si se dibuja un recuadro.
#: Clasificar la zona (vineta, ventana, secundaria) es de `core.reverse`.
DESTAQUE_MINIMO_BLOQUE = 1.15

#: Etiqueta de los recuadros del sustituto. Deliberadamente sin clasificar: la
#: version anterior ponia «vineta» a todo bloque que tocara un borde, que es
#: inventarse una afirmacion sobre el grado a partir de donde cae un cuadrado
#: de una rejilla de 6x6.
ETIQUETA_SIN_CLASIFICAR = "zona con residuo alto (sin clasificar)"


def _puntos_calientes(residuo: np.ndarray, *, bloques: int = 6, cuantos: int = 3) -> tuple[Hotspot, ...]:
    """Los bloques donde el residuo destaca sobre la media. Nada mas.

    **No clasifica.** Etiquetar la zona («vineta», «ventana», «degradado»)
    necesita mirar la geometria del residuo, y eso lo hace `core.reverse` con
    perfiles radiales y ajustes de plano. Aqui solo se dice «aqui hay residuo
    alto», que es lo unico que se ha medido.
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
            encontrados.append(
                (m, Hotspot(x=x, y=y, w=trozo.shape[1], h=trozo.shape[0], magnitude=m,
                            label=ETIQUETA_SIN_CLASIFICAR))
            )
    encontrados.sort(key=lambda t: t[0], reverse=True)
    return tuple(
        h for m, h in encontrados[:cuantos] if m > medio * DESTAQUE_MINIMO_BLOQUE
    )


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

    # `is_pure_lut=False` SIEMPRE, y no porque se haya medido que no lo es:
    # porque **aqui no se decide eso**. Ver el docstring del modulo. Es el
    # valor conservador, el que hace trabajar de mas en vez de mandar a nadie
    # con un .cube que no reproduce el grado.
    notas_diag: list[str] = [
        "El sustituto de la GUI NO decide si un grado es un LUT puro: ese veredicto lo da "
        "core.reverse, con la fraccion reproducible Y el percentil 95 del residuo a la vez. "
        "Aqui se deja en «no es puro» porque es el lado seguro del error, no porque se haya "
        "comprobado.",
        "Queda residuo que depende de DONDE esta el pixel, no de su color: eso no cabria "
        "en un .cube. Mira el mapa de residuo.",
    ]
    if cobertura.coverage_fraction() < COBERTURA_BAJA_AVISO:
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
            is_pure_lut=False,  # el sustituto NO emite veredicto. Ver arriba.
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
) -> Inversion:
    """Devuelve una `Inversion`: el resultado y **quien lo ha calculado**.

    Si `core.reverse` esta, se llama con la firma acordada
    `invertir_grado(original, coloreado, *, tam_lut, space, min_muestras)`. Si
    esta pero se atraganta, se cae al sustituto: una pantalla en blanco no
    ayuda a nadie a las tres de la manana.

    Pero **la caida no es silenciosa**. `del_nucleo` queda a `False` y `fallo`
    trae la excepcion tal cual, y la pantalla esta obligada a mirarlo antes de
    pintar el veredicto de «es un LUT puro». Un sustituto que ademas fuera mas
    permisivo y no se notara es exactamente como se entrega un `.cube` que no
    reproduce el grado.
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
            return Inversion(resultado=resultado, origen=ORIGEN_CORE, del_nucleo=True)
        except Exception as exc:
            return Inversion(
                resultado=_invertir_sustituto(
                    original, coloreado, tam_lut=tam_lut, min_muestras=min_muestras
                ),
                origen=f"{ORIGEN_SUSTITUTO} (core.reverse falló)",
                del_nucleo=False,
                fallo=f"core.reverse ha lanzado {exc!r}",
            )
    return Inversion(
        resultado=_invertir_sustituto(
            original, coloreado, tam_lut=tam_lut, min_muestras=min_muestras
        ),
        origen=ORIGEN_SUSTITUTO,
        del_nucleo=False,
        fallo=MOTIVO or "core.reverse no está disponible",
    )


__all__ = [
    "COBERTURA_BAJA_AVISO",
    "DESTAQUE_MINIMO_BLOQUE",
    "DISPONIBLE",
    "ETIQUETA_SIN_CLASIFICAR",
    "MOTIVO",
    "ORIGEN_CORE",
    "ORIGEN_SUSTITUTO",
    "SIN_VEREDICTO",
    "Inversion",
    "TAM_REJILLA_PANEL",
    "invertir",
]
