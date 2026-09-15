"""El diagnostico: ¿cuanto de este grado me puedo llevar en un `.cube`?

Esta es la pregunta que hace especial a `core.reverse`. Recuperar un LUT lo hace
cualquiera; decir **hasta donde llega el LUT y donde empieza lo que no es un
LUT** es lo que evita entregarle a un cliente un `.cube` que "casi" reproduce el
grado y que falla justo en la cara del actor.

DE QUE ESTA HECHO EL DIAGNOSTICO
--------------------------------
1. `residuo` = ΔE2000 por pixel entre lo que predice `LUT(CDL(original))` y el
   coloreado de verdad. Es el mapa `spatial_residual`.
2. `movimiento` = ΔE2000 por pixel entre el original y el coloreado. Es "cuanto
   grado hay".
3. `lut_reproducible = 1 - media(residuo) / media(movimiento)`, sujeto a 0..1.
   Se lee en castellano: **"de todo lo que este grado mueve el color, me llevo
   este tanto por uno"**. Si el grado no mueve nada (los dos planos son el
   mismo), la fraccion no esta definida y se devuelve 1.0 si el residuo tambien
   es despreciable, que es lo cierto: un grado identidad es un LUT identidad.

POR QUE ESA FORMULA Y NO "1 - residuo/8"
----------------------------------------
Porque un residuo de 2 dE2000 sobre un grado que mueve 40 es ruido, y el mismo
residuo de 2 sobre un grado que mueve 3 es que no has recuperado nada. Un numero
absoluto no distingue esos dos casos y este si. El absoluto tambien se da
(`residuo_de_medio`, `residuo_de_p95`), porque para decidir si se entrega hace
falta saber si lo que falta **se ve**.

SEPARAR UNA VINETA DE UNA VENTANA: HASTA DONDE LLEGA ESTE DETECTOR
------------------------------------------------------------------
Una vineta es **radial, centrada y monotona**: el residuo solo depende de la
distancia al centro y crece con ella. Una ventana es **compacta y esta donde
esta**. Un degradado es **lineal**: crece en una direccion.

El detector, en este orden:

1. **Vineta**: se bina el residuo por distancia normalizada al centro (24
   coronas). Si el perfil radial explica una fraccion apreciable de la varianza
   del residuo (`R2 >= UMBRAL_R2_RADIAL`), **crece** con el radio (correlacion
   de Pearson con el radio >= `UMBRAL_MONOTONIA_RADIAL`) y el recorrido del
   perfil supera `UMBRAL_DE_HOTSPOT`, se emite un `Hotspot` "vineta" que cubre
   la imagen entera. Cubrir la imagen entera es deliberado: una vineta no tiene
   una "zona", tiene una forma.
2. Se **resta el modelo radial** y se vuelve a mirar. Esto es lo que permite que
   una vineta y una ventana convivan: sin restar la vineta, la ventana de una
   esquina se funde con la corona exterior y sale un unico manchurron.
3. **Degradado**: sobre lo que queda se ajusta `res ~ a*x + b*y + c`. Si explica
   `>= UMBRAL_R2_LINEAL` y el recorrido se ve, sale un `Hotspot` "degradado" de
   la imagen entera.
4. **Zona local**: lo que queda se suaviza, se umbraliza y se etiquetan las
   componentes conexas. Cada componente con area suficiente sale como
   `Hotspot` "zona local" con su caja y su magnitud.

**LIMITES QUE HAY QUE SABER** (medidos, no supuestos; los numeros estan en
`NOTAS.md`):

- Una vineta **descentrada** no se detecta como vineta: el centro se supone en
  el centro geometrico del fotograma. Saldra como una o varias "zona local".
- Una ventana **centrada y redonda** es indistinguible de una vineta invertida
  con este detector. Si ademas el grado la hace crecer hacia fuera, se etiqueta
  "vineta". Es el falso positivo conocido.
- Una vineta que **aclara** en vez de oscurecer se detecta igual (el residuo
  ΔE2000 no tiene signo), lo cual es correcto.
- El detector **no sabe de sujetos**: una correccion secundaria por tono de piel
  (todas las caras, esten donde esten) sale como varias "zona local" repartidas,
  no como "una secundaria de piel". Eso ya no es geometria, es segmentacion, y
  no esta.
- Cuando no encaja en ninguna de las tres formas pero el residuo esta ahi, se
  emite "zona local" con su caja. Decir "hay algo espacial aqui" sin saber que es
  sigue siendo informacion util; inventarse la etiqueta no lo seria.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from core.color import delta_e2000
from core.contracts import (
    CDL,
    LUT3D,
    WORKING_SPACE,
    ColorSpaceName,
    CoverageMap,
    Hotspot,
    ReverseDiagnosis,
)

__all__ = [
    "AREA_MINIMA_HOTSPOT",
    "MAX_HOTSPOTS",
    "UMBRAL_DE_HOTSPOT",
    "UMBRAL_DE_PURO",
    "UMBRAL_MONOTONIA_RADIAL",
    "UMBRAL_R2_LINEAL",
    "UMBRAL_R2_RADIAL",
    "UMBRAL_REPRODUCIBLE_PURO",
    "diagnosticar",
    "mapa_de_residuo",
]

#: Un ΔE2000 de 1.0 es el umbral clasico de "dos colores que no se distinguen
#: puestos uno al lado del otro". Por debajo de eso no hay nada que senalar.
UMBRAL_DE_HOTSPOT: float = 1.0

#: Lo mismo, aplicado al percentil 95 del residuo, para decidir `is_pure_lut`.
#: O sea: "el 95% de la imagen esta por debajo de lo que el ojo distingue".
UMBRAL_DE_PURO: float = 1.0

#: Y ademas hay que haberse llevado casi todo el grado.
UMBRAL_REPRODUCIBLE_PURO: float = 0.95

#: Cuanta varianza del residuo tiene que explicar el perfil radial.
UMBRAL_R2_RADIAL: float = 0.30

#: Y cuanto tiene que crecer con el radio (Pearson perfil vs radio).
UMBRAL_MONOTONIA_RADIAL: float = 0.80

#: Cuanta varianza tiene que explicar un plano inclinado para llamarlo degradado.
UMBRAL_R2_LINEAL: float = 0.50

#: Area minima de una componente conexa, en fraccion de la imagen. Por debajo es
#: grano, no una zona.
AREA_MINIMA_HOTSPOT: float = 0.002

#: Mas de esto no se ensena: la GUI no cabe y nadie lee doce cajas.
MAX_HOTSPOTS: int = 8

_CORONAS: int = 24


def mapa_de_residuo(
    original: np.ndarray,
    coloreado: np.ndarray,
    cdl: CDL,
    lut: LUT3D,
    *,
    space: ColorSpaceName = WORKING_SPACE,
) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve `(residuo, movimiento)`, los dos en ΔE2000 por pixel `(h, w)`.

    `residuo`   = lo que el grado hace y `LUT(CDL(x))` NO explica.
    `movimiento`= lo que el grado hace, sin mas.
    """
    orig = np.asarray(original, dtype=np.float64)
    col = np.asarray(coloreado, dtype=np.float64)
    pred = lut.apply(cdl.apply(orig))
    residuo = np.asarray(delta_e2000(pred, col, space), dtype=np.float64)
    movimiento = np.asarray(delta_e2000(orig, col, space), dtype=np.float64)
    return residuo, movimiento


def _media_finita(a: np.ndarray) -> float:
    fin = np.isfinite(a)
    return float(a[fin].mean()) if fin.any() else float("nan")


def _suavizar(a: np.ndarray, radio: int) -> np.ndarray:
    if radio < 1:
        return a
    return ndimage.uniform_filter(a, size=2 * radio + 1, mode="nearest")


def _radio_normalizado(h: int, w: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx - (w - 1) / 2) / max((w - 1) / 2, 1e-9)
    v = (yy - (h - 1) / 2) / max((h - 1) / 2, 1e-9)
    return np.sqrt(u * u + v * v) / np.sqrt(2.0)


def _perfil_radial(res: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(modelo (h,w), perfil (_CORONAS,), centros de corona (_CORONAS,))."""
    h, w = res.shape
    r = _radio_normalizado(h, w)
    bordes = np.linspace(0.0, r.max() + 1e-9, _CORONAS + 1)
    idx = np.clip(np.digitize(r, bordes) - 1, 0, _CORONAS - 1)
    plano = idx.ravel()
    val = res.ravel()
    fin = np.isfinite(val)
    cnt = np.bincount(plano[fin], minlength=_CORONAS).astype(np.float64)
    suma = np.bincount(plano[fin], weights=val[fin], minlength=_CORONAS)
    perfil = np.divide(suma, np.maximum(cnt, 1.0))
    # coronas vacias: se copia la ultima que hubiera
    vacias = cnt == 0
    if vacias.any() and not vacias.all():
        buenas = np.flatnonzero(~vacias)
        perfil[vacias] = np.interp(np.flatnonzero(vacias), buenas, perfil[buenas])
    centros = 0.5 * (bordes[:-1] + bordes[1:])
    return perfil[idx], perfil, centros


def _r2(res: np.ndarray, modelo: np.ndarray) -> float:
    fin = np.isfinite(res) & np.isfinite(modelo)
    if fin.sum() < 16:
        return 0.0
    y = res[fin]
    m = modelo[fin]
    var = float(((y - y.mean()) ** 2).mean())
    if var <= 1e-12:
        return 0.0
    err = float(((y - m) ** 2).mean())
    return float(np.clip(1.0 - err / var, 0.0, 1.0))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64) - np.mean(a)
    b = np.asarray(b, dtype=np.float64) - np.mean(b)
    den = float(np.sqrt((a @ a) * (b @ b)))
    return float(a @ b / den) if den > 1e-30 else 0.0


def _modelo_lineal(res: np.ndarray) -> np.ndarray:
    h, w = res.shape
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx / max(w - 1, 1)).ravel()
    v = (yy / max(h - 1, 1)).ravel()
    y = res.ravel()
    fin = np.isfinite(y)
    if fin.sum() < 16:
        return np.zeros_like(res)
    dis = np.stack([u[fin], v[fin], np.ones(int(fin.sum()))], axis=1)
    sol, *_ = np.linalg.lstsq(dis, y[fin], rcond=None)
    return (np.stack([u, v, np.ones_like(u)], axis=1) @ sol).reshape(h, w)


def _componentes(res: np.ndarray, umbral: float) -> list[tuple[tuple[int, int, int, int], float]]:
    h, w = res.shape
    marcado = np.isfinite(res) & (res > umbral)
    if not marcado.any():
        return []
    etiquetas, cuantas = ndimage.label(marcado)
    fuera: list[tuple[tuple[int, int, int, int], float]] = []
    area_min = max(int(AREA_MINIMA_HOTSPOT * h * w), 4)
    for rebanada, k in zip(ndimage.find_objects(etiquetas), range(1, cuantas + 1), strict=True):
        if rebanada is None:
            continue
        trozo = etiquetas[rebanada] == k
        if int(trozo.sum()) < area_min:
            continue
        sy, sx = rebanada
        caja = (int(sx.start), int(sy.start), int(sx.stop - sx.start), int(sy.stop - sy.start))
        vals = res[rebanada][trozo]
        fuera.append((caja, float(np.nanmean(vals))))
    return fuera


def diagnosticar(
    original: np.ndarray,
    coloreado: np.ndarray,
    cdl: CDL,
    lut: LUT3D,
    cobertura: CoverageMap,
    *,
    space: ColorSpaceName = WORKING_SPACE,
) -> ReverseDiagnosis:
    """¿Cuanto de este grado cabe en un `.cube`, y que se queda fuera?

    `original` y `coloreado` tienen que venir **ya alineados** (misma forma).
    `cobertura` no cambia el diagnostico geometrico: entra para poder avisar de
    que un residuo alto puede ser falta de cobertura y no algo espacial, que son
    dos enfermedades distintas con el mismo sintoma.
    """
    residuo, movimiento = mapa_de_residuo(original, coloreado, cdl, lut, space=space)
    h, w = residuo.shape
    notas: list[str] = []

    res_medio = _media_finita(residuo)
    mov_medio = _media_finita(movimiento)
    finitos = np.isfinite(residuo)
    res_p95 = float(np.percentile(residuo[finitos], 95)) if finitos.any() else float("nan")
    res_max = float(residuo[finitos].max()) if finitos.any() else float("nan")

    if not np.isfinite(res_medio) or not np.isfinite(mov_medio):
        reproducible = 0.0
        notas.append(
            "Hay pixeles no finitos (NaN o infinito) en la pareja; el diagnostico solo mira "
            "los finitos y la fraccion reproducible no es de fiar."
        )
    elif mov_medio < 0.05:
        # El grado no mueve el color: no hay fraccion que calcular.
        reproducible = 1.0 if res_medio < 0.05 else 0.0
        notas.append(
            f"El coloreado apenas se mueve respecto al original ({mov_medio:.3f} dE2000 de media). "
            f"Esto no es un grado, es el mismo plano."
        )
    else:
        reproducible = float(np.clip(1.0 - res_medio / mov_medio, 0.0, 1.0))

    if not finitos.any():
        return ReverseDiagnosis(
            lut_reproducible=0.0,
            is_pure_lut=False,
            spatial_residual=None,
            hotspots=(),
            notes=(*notas, "No queda ni un pixel finito que mirar."),
        )

    # --- 1. ¿hay una vineta? ---
    radio = max(min(h, w) // 48, 1)
    suave = _suavizar(np.where(finitos, residuo, res_medio), radio)
    modelo_radial, perfil, centros = _perfil_radial(suave)
    r2_radial = _r2(suave, modelo_radial)
    crece = _pearson(perfil, centros)
    recorrido_radial = float(perfil.max() - perfil.min())
    hotspots: list[Hotspot] = []
    hay_vineta = (
        r2_radial >= UMBRAL_R2_RADIAL
        and crece >= UMBRAL_MONOTONIA_RADIAL
        and recorrido_radial >= UMBRAL_DE_HOTSPOT
    )
    if hay_vineta:
        hotspots.append(
            Hotspot(x=0, y=0, w=w, h=h, magnitude=float(np.nanmean(suave)), label="vineta")
        )
        notas.append(
            f"El residuo es radial y crece hacia los bordes ({recorrido_radial:.2f} dE2000 del "
            f"centro a la esquina, R2={r2_radial:.2f}): tiene toda la pinta de una vineta, y una "
            f"vineta NO cabe en un LUT."
        )
        resto = suave - modelo_radial
    else:
        resto = suave.copy()

    # --- 2. ¿un degradado? ---
    modelo_lin = _modelo_lineal(resto)
    r2_lineal = _r2(resto, modelo_lin)
    recorrido_lin = float(np.nanmax(modelo_lin) - np.nanmin(modelo_lin))
    if r2_lineal >= UMBRAL_R2_LINEAL and recorrido_lin >= UMBRAL_DE_HOTSPOT:
        hotspots.append(
            Hotspot(x=0, y=0, w=w, h=h, magnitude=float(np.nanmean(np.abs(resto))), label="degradado")
        )
        notas.append(
            f"Lo que queda del residuo crece en linea recta de un lado a otro del fotograma "
            f"({recorrido_lin:.2f} dE2000, R2={r2_lineal:.2f}): parece un degradado, no un LUT."
        )
        resto = resto - modelo_lin

    # --- 3. zonas locales ---
    base = float(np.nanmedian(resto))
    mad = float(np.nanmedian(np.abs(resto - base)))
    umbral = max(UMBRAL_DE_HOTSPOT, base + 4.0 * 1.4826 * mad)
    for caja, _magnitud in _componentes(resto, umbral):
        x, y, cw, ch = caja
        # La magnitud se reporta sobre el residuo TOTAL, no sobre el resto: al
        # usuario le importa cuanto se desvia ahi de verdad, no cuanto se desvia
        # una vez le he quitado los modelos que yo he decidido quitarle.
        real = float(np.nanmean(residuo[y : y + ch, x : x + cw]))
        hotspots.append(Hotspot(x=x, y=y, w=cw, h=ch, magnitude=real, label="zona local"))
    locales = [hp for hp in hotspots if hp.label == "zona local"]
    if locales:
        notas.append(
            f"Hay {len(locales)} zona(s) del fotograma donde el residuo se dispara por encima de "
            f"{umbral:.2f} dE2000 sin que el color lo explique: pinta de ventana o de secundaria."
        )

    hotspots.sort(key=lambda hp: -hp.magnitude)
    hotspots = hotspots[:MAX_HOTSPOTS]

    puro = (
        not hotspots
        and np.isfinite(res_p95)
        and res_p95 <= UMBRAL_DE_PURO
        and reproducible >= UMBRAL_REPRODUCIBLE_PURO
    )
    if puro:
        notas.insert(
            0,
            f"Este grado SI es un LUT: el 95% del fotograma cae por debajo de {res_p95:.2f} dE2000 "
            f"de error y me llevo el {reproducible * 100:.1f}% del movimiento de color.",
        )
    else:
        notas.insert(
            0,
            f"Me llevo el {reproducible * 100:.1f}% del grado en un .cube. Lo que queda: "
            f"{res_medio:.2f} dE2000 de media, {res_p95:.2f} en el percentil 95 y {res_max:.2f} "
            f"en el peor pixel.",
        )

    fraccion = cobertura.coverage_fraction()
    if fraccion < 0.005 and not puro:
        notas.append(
            f"Ojo: el plano solo cubre el {fraccion * 100:.2f}% de las celdas del cubo. Parte del "
            f"residuo puede ser falta de datos y no algo espacial."
        )

    # `spatial_residual` va NORMALIZADO 0..1 dividiendo por el maximo, porque es
    # un mapa para pintar. La magnitud en dE2000 vive en `Hotspot.magnitude` y en
    # la primera nota; asi no hay dos sitios donde mirar el mismo numero.
    tope = res_max if np.isfinite(res_max) and res_max > 1e-9 else 1.0
    mapa = (residuo / tope).astype(np.float32)
    notas.append(f"`spatial_residual` esta normalizado: 1.0 equivale a {tope:.2f} dE2000.")

    return ReverseDiagnosis(
        lut_reproducible=float(reproducible),
        is_pure_lut=bool(puro),
        spatial_residual=mapa,
        hotspots=tuple(hotspots),
        notes=tuple(notas),
    )
