"""`invertir_grado`: dado un plano y el mismo plano ya coloreado, recuperar el grado.

Es la funcion estrella de la app. Todo lo demas de `core.reverse` existe para
que esta funcion pueda ser honesta.

EL GRADO SALE EN DOS CAPAS, Y EL ORDEN IMPORTA
-----------------------------------------------
    coloreado ~=  LUT( CDL( original ) )

**Primero el CDL, luego el LUT sobre el resultado.** Sin excepciones, sin
variantes, y es el mismo orden que usa `MatchResult` del agente C, a proposito:
dos modulos que devuelven un `(CDL, LUT)` con ordenes distintos es como se
fabrica un bug que nadie encuentra porque en las pruebas de cada uno funciona.

En Resolve eso es: el CDL en el nodo de balance y el LUT en el nodo de look,
en ese orden de cadena.

POR QUE DOS CAPAS Y NO SOLO EL LUT
----------------------------------
Un LUT solo tambien funcionaria. Pero un LUT es una caja negra de 35.937 numeros
que Mario no puede leer, no puede discutir y no puede retocar. El CDL son diez
numeros con nombre: slope, offset, power, saturacion. Sacar primero el CDL
significa que la parte del grado que se puede explicar con palabras sale
**explicada con palabras**, y el LUT se queda solo con lo que de verdad no cabe
en diez numeros. Ademas el CDL se aplica en el nodo 2 de Resolve por parametro,
sin escribir un fichero, y eso es lo unico que la API deja tocar de verdad.

Efecto secundario que tambien importa: como el CDL se lleva la mayor parte del
movimiento, lo que le queda al LUT es pequeno, y un residuo pequeno se extrapola
mucho mejor a las 35.000 celdas que nadie ha visto.

COMO SE AJUSTA EL LUT: MINIMOS CUADRADOS, NO UNA MEDIA DE CAJONES
------------------------------------------------------------------
El reparto de cada pixel a los ocho nodos que lo rodean (`acumulacion.py`) es el
adjunto exacto de la interpolacion trilineal de `LUT3D.apply`. Con eso, ajustar
el LUT es resolver `A t = y` por minimos cuadrados, y se resuelve con Jacobi
precondicionado por la diagonal:

    t <- t + D^-1 A^T (y - A t)     sobre las celdas MEDIDAS

`D = diag(suma de pesos)`. Converge siempre: por Gershgorin, los autovalores de
`D^-1 A^T A` caen en [0, 1], asi que el error nunca crece. Entre iteracion e
iteracion se vuelve a extender el residuo a las celdas sin datos, porque la
interpolacion de un pixel puede apoyarse en un nodo inventado.

La primera iteracion sola (o sea, la media ponderada) deja un ΔE2000 medio de
~2.3 en el material de prueba; con 16 iteraciones baja a las decimas. Los
numeros exactos estan en NOTAS.md.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from core.color import delta_e2000
from core.contracts import (
    CDL,
    LUT3D,
    LUT_SIZE_DEFAULT,
    WORKING_SPACE,
    ColorSpaceName,
    Confidence,
    CoverageMap,
    ReverseDiagnosis,
    ReverseResult,
    confidence_level,
)
from core.matching import (
    ajustar_cdl,
    desajuste_de_contenido,
    puntuar_confianza,
    solape_de_distribuciones,
)
from core.reverse.acumulacion import (
    Estadisticos,
    acumular_correspondencias,
    estadisticos_de_correspondencias,
    fraccion_fuera_de_dominio,
)
from core.reverse.alineado import alinear
from core.reverse.diagnostico import diagnosticar
from core.reverse.relleno import (
    LAMBDA_SUAVIDAD,
    LAMBDA_SUAVIDAD_W2,
    base_afin,
    celdas_con_dato,
    extender_suave,
    media_de_vecinos,
    proyectar_monotona,
    rejilla_de_entradas,
)
from core.umbrales import (
    MUESTRAS_MINIMAS_CDL,
    MUESTRAS_MINIMAS_CELDA,
    UMBRAL_COBERTURA_BAJA,
    UMBRAL_FUERA_DE_DOMINIO_AVISO,
)

__all__ = [
    "ITERACIONES_REFINADO",
    "MAX_PIXELES_CDL",
    "MUESTRAS_MINIMAS_CDL",
    "InformacionDeNodo",
    "invertir_grado",
]

# `MUESTRAS_MINIMAS_CDL`, `UMBRAL_COBERTURA_BAJA`, `UMBRAL_FUERA_DE_DOMINIO_AVISO`
# y `MUESTRAS_MINIMAS_CELDA` deciden lo que Mario lee en pantalla, asi que viven
# en `core.umbrales`. Se reexporta `MUESTRAS_MINIMAS_CDL` con su nombre de
# siempre porque lo importa `core.reverse` y los tests.

#: Con que se mide cuanta informacion tiene un nodo en el ajuste del LUT.
InformacionDeNodo = Literal["suma_w", "suma_w2"]

#: El ajuste del CDL es no lineal y no mejora nada por encima de este numero de
#: pixeles. El LUT si usa TODOS los pixeles: ahi cada muestra cuenta.
MAX_PIXELES_CDL: int = 60_000

#: Iteraciones de Jacobi sobre las celdas medidas. Medido en el T1: con 1 sola
#: (o sea, la media ponderada de toda la vida) el ΔE2000 medio es 1.23 y el
#: maximo 11.3; con 24 baja a 0.35 y 2.4; con 40 a 0.22 y 2.3; con 60 a 0.14 y
#: 2.30. Mas de 60 sigue bajando la media pero ya no compensa lo que tarda (unos
#: 40 ms por iteracion sobre un plano de 640x360).
ITERACIONES_REFINADO: int = 60

#: Barridos de suavizado en caliente dentro del bucle (el relleno completo, que
#: es mas caro, solo se paga al principio y al final).
_BARRIDOS_EN_BUCLE: int = 10


def _submuestra(px: np.ndarray, tope: int) -> np.ndarray:
    """Submuestreo determinista por paso constante. Sin aleatoriedad: dos
    ejecuciones tienen que dar el mismo grado."""
    if px.shape[0] <= tope:
        return px
    paso = int(np.ceil(px.shape[0] / tope))
    return px[::paso]


def invertir_grado(
    original: np.ndarray,
    coloreado: np.ndarray,
    *,
    tam_lut: int = LUT_SIZE_DEFAULT,
    space: ColorSpaceName = WORKING_SPACE,
    min_muestras: int = MUESTRAS_MINIMAS_CELDA,
    informacion: InformacionDeNodo = "suma_w",
) -> ReverseResult:
    """Recupera el grado que lleva `original` a `coloreado`.

    Las dos imagenes son `(alto, ancho, 3)` float, del **mismo plano y el mismo
    encuadre**, en `space`. Si no lo son del todo, `alinear` intenta arreglarlo
    y lo que no pueda arreglar sale en las notas y baja la confianza.

    Devuelve un `ReverseResult` con:

    * `cdl` + `lut`, en ese orden de aplicacion (`lut.apply(cdl.apply(x))`);
    * `coverage`, que dice **que celdas del cubo son datos y cuales invento**;
    * `diagnosis`, que dice cuanto del grado cabe en un `.cube`;
    * `delta_e_mean` / `_p95` / `_max`, sobre TODOS los pixeles validos.
      Los mismos numeros restringidos a la zona con cobertura estan en
      `confidence.metrics` como `de_*_cubierto`.

    `informacion` decide como se mide cuanto sabe cada nodo en el ajuste del
    LUT. El defecto, `"suma_w"`, es el de siempre y el del contrato T1.
    `"suma_w2"` es el del modo por lote; con un plano mejora T1 pero empeora lo
    tipico con un look de secundarias estrechas (`core/reverse/NOTAS.md` §12).
    """
    n = int(tam_lut)
    notas: list[str] = []

    a, b, info = alinear(original, coloreado)
    notas.extend(info["notas"])
    forma = a.shape[:2]

    src_todo = a.reshape(-1, 3).astype(np.float64)
    dst_todo = b.reshape(-1, 3).astype(np.float64)
    bueno = np.isfinite(src_todo).all(axis=1) & np.isfinite(dst_todo).all(axis=1)
    fraccion_no_finita = float(1.0 - bueno.mean()) if bueno.size else 1.0
    src = src_todo[bueno]
    dst = dst_todo[bueno]
    if fraccion_no_finita > 0.0:
        notas.append(
            f"He descartado el {fraccion_no_finita * 100:.2f}% de los pixeles por traer NaN o "
            f"infinito. El grado sale de los que quedan."
        )

    # ------------------------------------------------------------------
    # Caso degenerado: sin pixeles utiles no hay nada que devolver salvo la
    # identidad, y hay que decirlo con la confianza por los suelos.
    # ------------------------------------------------------------------
    if src.shape[0] == 0:
        return _resultado_vacio(n, forma, min_muestras, notas, fraccion_no_finita)

    # ------------------------------------------------------------------
    # Capa 1: el CDL global.
    # ------------------------------------------------------------------
    if src.shape[0] >= MUESTRAS_MINIMAS_CDL:
        cdl = ajustar_cdl(_submuestra(src, MAX_PIXELES_CDL), _submuestra(dst, MAX_PIXELES_CDL))
    else:
        cdl = CDL.identity()
        notas.append(
            f"Solo hay {src.shape[0]} pixeles validos, menos de {MUESTRAS_MINIMAS_CDL}. No ajusto "
            f"CDL (diez parametros con tan pocos datos es ruido con forma de grado): dejo la "
            f"identidad y todo el grado se va al LUT."
        )

    fuente = cdl.apply(src)
    fuera = fraccion_fuera_de_dominio(fuente)
    if fuera > UMBRAL_FUERA_DE_DOMINIO_AVISO:
        notas.append(
            f"El {fuera * 100:.2f}% de los pixeles, despues del CDL, se sale del dominio 0..1 del "
            f"LUT. Ahi el LUT sujeta al borde (igual que Resolve) y el color no se transforma."
        )

    # ------------------------------------------------------------------
    # Capa 2: el LUT residual, por minimos cuadrados sobre la rejilla.
    # ------------------------------------------------------------------
    estadisticos = estadisticos_de_correspondencias(fuente, dst, n, con_gram=True)
    cobertura = estadisticos.cobertura(min_muestras)
    medidas = celdas_con_dato(cobertura)
    entradas = rejilla_de_entradas(n)

    if not medidas.any():
        lut = LUT3D(table=entradas.astype(np.float32), title="SIDEB COLOR (sin cobertura)")
        notas.append(
            "Ni un solo pixel ha caido dentro del cubo. El LUT que devuelvo es la identidad "
            "entera: todo el grado que haya esta en el CDL."
        )
    elif fuera >= 1.0:
        # TODO el material, despues del CDL, cae fuera de 0..1. La acumulacion
        # sujeta al borde, asi que las 35.937 celdas se ajustan contra UNA sola
        # esquina del cubo, y lo que sale es un LUT **constante**: todo el gamut
        # al mismo color. `core.io.qc_lut` lo caza con el codigo `lut_plano` y
        # tiene razon, pero para entonces ya se ha entregado.
        #
        # Es un caso real: material log sin normalizar, o un EXR de un cielo.
        # La respuesta honesta es la identidad y decirlo: el grado que se pueda
        # explicar ya esta en el CDL, y el LUT no tiene ni un dato con el que
        # opinar. MEDIDO: con un plano entero en 40.0 y el coloreado en 48.0, la
        # version anterior devolvia un LUT con todas las celdas a 1.0.
        lut = LUT3D(table=entradas.astype(np.float32), title="SIDEB COLOR (fuera de dominio)")
        notas.append(
            "NINGUN pixel cae dentro del dominio 0..1 del LUT una vez aplicado el CDL: todo el "
            "material esta por encima o por debajo. Con un solo punto del cubo tocado, cualquier "
            "LUT que ajustara seria una constante; devuelvo la identidad. Si el material es log "
            "sin normalizar, normalizalo antes o dame el par ya en el espacio de trabajo."
        )
    else:
        lut = _ajustar_lut(estadisticos, medidas, entradas, informacion=informacion)

    # La varianza definitiva se mide contra el LUT ya ajustado: asi es la
    # varianza del RESIDUO de verdad y no arrastra el suelo de la rejilla.
    _, cobertura = acumular_correspondencias(
        fuente, dst, n, min_muestras=min_muestras, tabla=lut
    )
    fraccion_cubierta = cobertura.coverage_fraction()
    con_dato = celdas_con_dato(cobertura)
    n_inventadas = int((~con_dato).sum())
    notas.append(
        f"Cobertura: {int(con_dato.sum())} celdas de {n**3} han visto al menos un pixel, y de "
        f"esas {int(cobertura.covered_mask().sum())} llegan a {min_muestras} muestras "
        f"({fraccion_cubierta * 100:.2f}% del cubo). Las otras {n_inventadas} estan INVENTADAS "
        f"(extrapoladas y suavizadas): son exactamente las de `coverage.counts == 0`."
    )

    # ------------------------------------------------------------------
    # Medidas y diagnostico.
    # ------------------------------------------------------------------
    pred_img = lut.apply(cdl.apply(a.astype(np.float64)))
    de_img = np.asarray(delta_e2000(pred_img, b.astype(np.float64), space), dtype=np.float64)
    de_plano = de_img.reshape(-1)[bueno]
    fin = np.isfinite(de_plano)
    de_medio = float(de_plano[fin].mean()) if fin.any() else float("nan")
    de_p95 = float(np.percentile(de_plano[fin], 95)) if fin.any() else float("nan")
    de_max = float(de_plano[fin].max()) if fin.any() else float("nan")

    cubierto = _mascara_cubierta(fuente, cobertura, n)
    sel = cubierto & fin
    de_medio_cub = float(de_plano[sel].mean()) if sel.any() else float("nan")
    de_p95_cub = float(np.percentile(de_plano[sel], 95)) if sel.any() else float("nan")
    de_max_cub = float(de_plano[sel].max()) if sel.any() else float("nan")

    diagnosis = diagnosticar(a, b, cdl, lut, cobertura, space=space)

    hay_desajuste, distancia, razones_contenido = desajuste_de_contenido(a, b)
    if hay_desajuste:
        notas.append(
            "AVISO GORDO: estos dos planos no parecen la misma escena. "
            + " ".join(razones_contenido[:2])
        )
    if not info["fiable"]:
        notas.append(
            "El emparejamiento pixel a pixel NO esta garantizado (ver el aviso de alineado). "
            "El grado que devuelvo puede ser una media de dos escenas distintas."
        )

    solape = solape_de_distribuciones(
        _submuestra(lut.apply(cdl.apply(src)), 200_000), _submuestra(dst, 200_000)
    )
    condicion = _condicion(src)
    confianza = puntuar_confianza(
        n_muestras=int(src.shape[0]),
        solape=float(solape),
        condicion=float(condicion),
        residuo_de=de_medio,
        fraccion_no_finita=fraccion_no_finita,
        desajuste=bool(hay_desajuste),
        distancia_contenido=float(distancia),
    )
    extra = {
        "de_medio_cubierto": de_medio_cub,
        "de_p95_cubierto": de_p95_cub,
        "de_max_cubierto": de_max_cub,
        "fraccion_celdas_cubiertas": float(fraccion_cubierta),
        "celdas_inventadas": float(n_inventadas),
        "fraccion_px_en_celda_cubierta": float(sel.sum()) / max(int(fin.sum()), 1),
        "lut_reproducible": float(diagnosis.lut_reproducible),
        "correlacion_alineado": float(info["correlacion"]),
        "fraccion_fuera_de_dominio": float(fuera),
    }
    confianza = _con_razones_de_cobertura(confianza, extra, fraccion_cubierta, info)

    return ReverseResult(
        cdl=cdl,
        lut=lut,
        coverage=cobertura,
        diagnosis=diagnosis,
        delta_e_mean=de_medio,
        delta_e_p95=de_p95,
        delta_e_max=de_max,
        confidence=confianza,
        notes=tuple(notas),
    )


# ---------------------------------------------------------------------------
# Piezas internas
# ---------------------------------------------------------------------------


def _ajustar_lut(
    estadisticos: Estadisticos,
    medidas: np.ndarray,
    entradas: np.ndarray,
    *,
    iteraciones: int = ITERACIONES_REFINADO,
    inicial: LUT3D | None = None,
    informacion: InformacionDeNodo = "suma_w",
) -> LUT3D:
    """Minimos cuadrados sobre la rejilla + extension suave. Ver el docstring.

    Desde el dia 4 trabaja sobre los ESTADISTICOS (`A^T y`, `A^T A`, `D`) y no
    sobre los pixeles: la correccion de Jacobi `D^-1 A^T (y - A t)` es
    `D^-1 (A^T y - A^T A t)`, la misma cuenta reordenada. Asi el mismo codigo
    ajusta un plano o cuarenta sumados. Medido: T1 identico a 4 decimales
    (0.1415 / 1.7409) antes y despues; ver `core/reverse/NOTAS.md` §12.
    """
    n = estadisticos.n
    acumulado = estadisticos.acumulado()
    pesos = acumulado[..., 3]
    valores = np.zeros((n, n, n, 3), dtype=np.float64)
    np.divide(
        acumulado[..., :3],
        np.maximum(pesos, 1e-12)[..., None],
        out=valores,
        where=medidas[..., None],
    )
    base = base_afin(entradas, valores, medidas, pesos)
    residuo = np.zeros_like(valores)
    residuo[medidas] = valores[medidas] - base[medidas]
    if inicial is None:
        extendido = extender_suave(residuo, medidas)
    else:
        # Arranque en caliente desde un LUT ya ajustado con datos parecidos (lo
        # usa la comprobacion de coherencia del lote, que ajusta N veces el
        # lote sin un plano). El de un solo plano nunca pasa por aqui.
        extendido = np.asarray(inicial.table, dtype=np.float64) - base
        residuo = np.where(medidas[..., None], extendido, 0.0)
    tabla = np.clip(base + extendido, 0.0, 1.0)

    aty = estadisticos.suma_wy
    diagonal = np.maximum(pesos.reshape(-1), 1e-12)[:, None]
    # Mezcla de la regularizacion: una celda con muchisimos pixeles manda ella;
    # una con dos pixeles sueltos se deja llevar por sus vecinas. Es minimos
    # cuadrados regularizados, no un maquillaje: sin esto, las celdas del borde
    # del gamut (dos o tres pixeles del pelo) se ajustan al ruido y el LUT sale
    # con escalones que `qc_lut` caza con razon.
    #
    # `informacion` decide con que se mide cuanto sabe cada nodo (ver
    # `LAMBDA_SUAVIDAD_W2` en `relleno.py`): "suma_w" es lo de siempre y lo que
    # usa `invertir_grado`; "suma_w2" es la diagonal de `A^T A` y es el defecto
    # del modo por lote.
    if informacion == "suma_w":
        alfa = (pesos / (pesos + LAMBDA_SUAVIDAD))[..., None]
    elif informacion == "suma_w2":
        diag_gram = estadisticos.diagonal_gram().reshape(n, n, n)
        alfa = (diag_gram / (diag_gram + LAMBDA_SUAVIDAD_W2))[..., None]
    else:
        raise ValueError(f"informacion tiene que ser 'suma_w' o 'suma_w2', llego {informacion!r}")
    for _ in range(int(iteraciones)):
        correccion = (aty - estadisticos.aplicar_gram(tabla)) / diagonal
        paso = correccion.reshape(n, n, n, 3)
        candidato = residuo + paso
        suave = media_de_vecinos(extendido)
        residuo = np.where(medidas[..., None], alfa * candidato + (1.0 - alfa) * suave, residuo)
        extendido = extender_suave(
            residuo, medidas, barridos=_BARRIDOS_EN_BUCLE, inicial=extendido
        )
        tabla = np.clip(base + extendido, 0.0, 1.0)

    extendido = extender_suave(residuo, medidas, inicial=extendido)
    tabla = proyectar_monotona(np.clip(base + extendido, 0.0, 1.0))
    return LUT3D(table=np.clip(tabla, 0.0, 1.0).astype(np.float32), title="SIDEB COLOR")


def _mascara_cubierta(fuente: np.ndarray, cobertura: CoverageMap, n: int) -> np.ndarray:
    """(M,) bool: pixeles cuya celda mas cercana tiene muestras suficientes."""
    px = np.asarray(fuente, dtype=np.float64).reshape(-1, 3)
    t = np.clip(px, 0.0, 1.0) * (n - 1)
    i = np.rint(t).astype(np.int64)
    return cobertura.covered_mask()[i[:, 0], i[:, 1], i[:, 2]]


def _condicion(px: np.ndarray) -> float:
    """Numero de condicion de la covarianza del origen. Es lo que se hunde
    cuando el plano es de un solo color, y es exactamente lo que tiene que
    hundir la confianza: sin volumen de color no hay cubo que rellenar."""
    if px.shape[0] < 4:
        return 1e12
    cov = np.cov(px, rowvar=False)
    if not np.isfinite(cov).all():
        return 1e12
    vals = np.linalg.svd(cov, compute_uv=False)
    if vals[0] <= 0:
        return 1e12
    return float(vals[0] / max(vals[-1], 1e-300))


def _con_razones_de_cobertura(
    confianza: Confidence, extra: dict[str, float], fraccion: float, info: dict
) -> Confidence:
    """Anade a la confianza las razones que solo conoce este modulo.

    **La NOTA no se toca**: los umbrales son del agente C y hay un unico sitio
    donde un numero se convierte en alta/media/baja. Lo que si se anade son
    razones y metricas que el que lee la GUI necesita para entender el numero.
    """
    razones = list(confianza.reasons)
    if fraccion < UMBRAL_COBERTURA_BAJA:
        razones.append(
            f"El plano solo cubre el {fraccion * 100:.2f}% del cubo: casi todo el LUT esta "
            f"extrapolado. Vale para este plano; para otro con colores distintos, no."
        )
    if not info["fiable"]:
        razones.insert(
            0,
            "No puedo garantizar que las dos imagenes sean el mismo encuadre; el grado puede ser "
            "un promedio de dos escenas.",
        )
    if info["corregido"]:
        razones.append(f"He tenido que corregir un desencuadre de {info['desplazamiento']} px.")
    metricas = dict(confianza.metrics)
    metricas.update(extra)
    return Confidence(
        score=confianza.score,
        level=confidence_level(confianza.score),
        reasons=tuple(razones),
        metrics=metricas,
    )


def _resultado_vacio(
    n: int, forma: tuple[int, int], min_muestras: int, notas: list[str], no_finita: float
) -> ReverseResult:
    notas.append(
        "No queda ni un pixel valido en la pareja (todo NaN o infinito). Devuelvo la identidad y "
        "confianza cero: no hay grado que recuperar."
    )
    cobertura = CoverageMap(
        counts=np.zeros((n, n, n), dtype=np.int32),
        variance=np.zeros((n, n, n), dtype=np.float32),
        min_samples=int(min_muestras),
    )
    return ReverseResult(
        cdl=CDL.identity(),
        lut=LUT3D.identity(n),
        coverage=cobertura,
        diagnosis=ReverseDiagnosis(
            lut_reproducible=0.0,
            is_pure_lut=False,
            spatial_residual=None,
            hotspots=(),
            notes=("No hay ni un pixel finito que mirar.",),
        ),
        delta_e_mean=float("nan"),
        delta_e_p95=float("nan"),
        delta_e_max=float("nan"),
        confidence=puntuar_confianza(n_muestras=0, fraccion_no_finita=no_finita),
        notes=tuple(notas),
    )
