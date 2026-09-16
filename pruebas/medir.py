"""Medir el grado sobre las parejas localizadas: T1, T5 y cobertura del cubo.

NADA DE ESTE ARCHIVO ESCRIBE. Recibe fotogramas en memoria y devuelve numeros.
Lo que haya que guardar lo guarda `primera_real.py` a traves de la guarda.

LAS TRES MEDIDAS
----------------
- **T1 · ida y vuelta sobre el mismo plano.** Se saca el grado de un plano
  (`core.reverse.invertir_grado`, bruto -> master) y se aplica a ese mismo
  bruto. Se compara con el master. Es el techo: si aqui sale mal, no hay grado
  que llevarse. **El titular es el ΔE2000 MAXIMO en la zona cubierta** (decidido
  el dia 3: es el que suspende); el medio va detras.
- **T5 · el grado de un plano aplicado a los demas.** Lo que de verdad importa:
  con el grado sacado del plano A, ¿como de cerca queda el bruto B del master B?
  Se mide para todas las parejas (A, B) con A distinto de B. Se dan el maximo y
  el medio sobre todos los pixeles, y los mismos numeros restringidos a los
  pixeles de B cuyo color **si vio** el plano A (celda del cubo con datos) — el
  resto del cubo de A es invento del relleno de huecos, y conviene separarlo.
- **Cobertura del cubo** de cada plano: cuantas celdas del LUT de 33³ tienen
  datos de verdad.

ENCUADRE ANTES DE MEDIR
-----------------------
La localizacion da la geometria a 128 px de ancho, con un error de un pixel de
escaneo (unos 15 px en un 1920). Aqui, en tres pasos:

1. se afina a `ANCHO_AFINADO` px: escala en pasos del 0.5% y posicion libre;
2. se recorta a resolucion completa y se reducen bruto y master **al menos a la
   mitad** (y como mucho a `ancho_analisis`), para que el filtro de reescalado
   con que se hizo el master pese poco;
3. **registro subpixel** afin por ECC sobre la estructura, y el bruto se
   remuestrea sobre la rejilla del master.

Lo que aporta cada paso esta medido en `pruebas/NOTAS.md` §3.

Y un limite que no se puede quitar: en un borde, un grado no lineal no da el
mismo color aplicado antes o despues de reescalar. Incluso **el grado
verdadero** aplicado al bruto ya encajado deja ΔE alto en los bordes. Por eso el
informe da, al lado del maximo, el maximo **lejos de bordes**.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from core.color import delta_e2000, to_working
from core.contracts import LUT_SIZE_DEFAULT, WORKING_SPACE, ReverseResult
from core.reverse import alinear, invertir_grado

from .localizar import Geometria, estructura, luma

__all__ = [
    "ANCHO_AFINADO",
    "Pareja",
    "MedidaT1",
    "MedidaT5",
    "afinar_encuadre",
    "preparar_pareja",
    "medir_t1",
    "medir_t5",
]

#: Ancho al que se afina el encuadre antes de recortar a resolucion completa.
ANCHO_AFINADO: int = 480


@dataclass
class Pareja:
    """Bruto recortado y master, al mismo tamano y en el espacio de trabajo."""

    nombre: str
    bruto: np.ndarray  # (h, w, 3) float32, WORKING_SPACE
    master: np.ndarray  # (h, w, 3) float32, WORKING_SPACE
    recorte_px: tuple[int, int, int, int]  # (x, y, ancho, alto) en el bruto completo
    encaje_afinado: float
    notas: list[str] = field(default_factory=list)


@dataclass
class MedidaT1:
    de_max_cubierto: float
    de_p95_cubierto: float
    de_medio_cubierto: float
    de_max_cubierto_sin_bordes: float
    de_medio_cubierto_sin_bordes: float
    fraccion_bordes: float
    de_max_todo: float
    de_medio_todo: float
    celdas_con_datos: int
    celdas_totales: int
    fraccion_cubierta: float
    lut_reproducible: float
    es_lut_puro: bool
    confianza_grado: float
    nivel_grado: str
    cdl: dict
    notas: list[str]


@dataclass
class MedidaT5:
    origen: str  # plano del que se saca el grado
    destino: str  # plano al que se aplica
    de_max: float
    de_p95: float
    de_medio: float
    de_max_zona_vista: float
    de_medio_zona_vista: float
    fraccion_zona_vista: float  # fraccion de pixeles de B en celdas con datos de A
    de_max_sin_bordes: float
    de_max_zona_vista_sin_bordes: float


def _redim(img: np.ndarray, ancho: int, alto: int) -> np.ndarray:
    h, w = img.shape[:2]
    interp = cv2.INTER_AREA if ancho <= w else cv2.INTER_LINEAR
    return cv2.resize(np.ascontiguousarray(img, dtype=np.float32), (int(ancho), int(alto)),
                      interpolation=interp)


def afinar_encuadre(
    bruto_luma: np.ndarray, master_luma: np.ndarray, g: Geometria, *, rango: float = 0.03,
    paso: float = 0.005,
) -> Geometria:
    """Afina escala (+-`rango`) y posicion a la resolucion de `master_luma`."""
    mh, mw = master_luma.shape
    bh, bw = bruto_luma.shape
    plantilla = estructura(master_luma)
    escala_max = min(1.0, (bh / bw) / (mh / mw))
    mejor = Geometria(g.escala, g.x, g.y, -1.0)
    n = int(round(rango / paso))
    holgura = int(round(0.04 * mw)) + 4
    for k in range(-n, n + 1):
        s = min(g.escala * (1.0 + paso * k), escala_max)
        ancho = int(round(mw / s))
        alto = int(round(ancho * bh / bw))
        if ancho < mw or alto < mh:
            continue
        est = estructura(_redim(bruto_luma, ancho, alto))
        px, py = int(round(g.x * ancho)), int(round(g.y * alto))
        x0, y0 = max(px - holgura, 0), max(py - holgura, 0)
        x1, y1 = min(px + holgura + mw, ancho), min(py + holgura + mh, alto)
        zona = est[y0:y1, x0:x1]
        if zona.shape[0] < mh or zona.shape[1] < mw:
            continue
        r = cv2.matchTemplate(zona, plantilla, cv2.TM_CCOEFF_NORMED)
        _, v, _, (qx, qy) = cv2.minMaxLoc(r)
        if np.isfinite(v) and v > mejor.ncc:
            mejor = Geometria(mw / ancho, (x0 + qx) / ancho, (y0 + qy) / alto, float(v))
    return mejor if mejor.ncc >= 0 else g


def _registro_subpixel(
    base: np.ndarray, movil: np.ndarray, forma: tuple[int, int]
) -> tuple[np.ndarray | None, float]:
    """Afin (2x3) que lleva `base` (coords destino) a `movil`, por ECC sobre la estructura.

    Devuelve (matriz o None si no converge, correlacion final). ECC maximiza la
    correlacion, que es invariante a brillo y contraste; sobre la estructura local
    lo es ademas a un grado. Es lo que baja el encaje de "un pixel" a "una
    fraccion de pixel", y en bordes finos esa diferencia es la del ΔE maximo.
    """
    h, w = forma
    t = estructura(luma(base))
    m = estructura(luma(movil))
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        cc, warp = cv2.findTransformECC(
            t, m, warp, cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5,
        )
    except cv2.error:
        return None, 0.0
    # Un afin que se aleje mucho de la identidad no es un afinado: es otra cosa.
    if not np.all(np.isfinite(warp)) or np.abs(warp[:, :2] - np.eye(2)).max() > 0.05 or (
        np.abs(warp[:, 2]).max() > 0.05 * max(h, w)
    ):
        return None, float(cc)
    return warp, float(cc)


def preparar_pareja(
    nombre: str,
    bruto_u16: np.ndarray,
    master_u16: np.ndarray,
    area_activa_rel: tuple[float, float, float, float],
    g: Geometria,
    *,
    espacio_bruto: str,
    espacio_master: str,
    ancho_analisis: int,
    reduccion_minima: int = 2,
    subpixel: bool = True,
) -> Pareja:
    """Recorta el bruto donde esta el plano, lo registra al master y pasa a WORKING_SPACE.

    `reduccion_minima` y `subpixel` existen para poder MEDIR lo que aporta cada
    cosa (`tests/test_pruebas_medir.py`); el script usa siempre los valores por
    defecto.

    `area_activa_rel` = (y0, y1, x0, x1) del master sin bandas negras, en 0..1.

    Tres pasos: (1) afinar escala y posicion a `ANCHO_AFINADO` px; (2) recortar a
    resolucion completa con margen y llevar los dos al mismo tamano (el menor de
    los dos, y como mucho `ancho_analisis`); (3) registro subpixel afin por ECC y
    remuestreo del bruto sobre la rejilla del master. Si el paso 3 no converge,
    se mide con el recorte entero y se dice.
    """
    notas: list[str] = []
    bruto = bruto_u16.astype(np.float32) / 65535.0
    master = master_u16.astype(np.float32) / 65535.0
    MH, MW = master.shape[:2]
    ay0, ay1, ax0, ax1 = area_activa_rel
    my0, my1 = int(round(ay0 * MH)), int(round(ay1 * MH))
    mx0, mx1 = int(round(ax0 * MW)), int(round(ax1 * MW))
    master = master[my0:my1, mx0:mx1]
    MH, MW = master.shape[:2]
    BH, BW = bruto.shape[:2]

    # 1. afinar a ANCHO_AFINADO
    aw = min(ANCHO_AFINADO, MW)
    ah = max(int(round(aw * MH / MW)), 8)
    ml = luma(_redim(master, aw, ah))
    bw_af = min(BW, int(round(aw / max(g.escala, 1e-3) * 1.1)))
    bl = luma(_redim(bruto, bw_af, max(int(round(bw_af * BH / BW)), 8)))
    g2 = afinar_encuadre(bl, ml, g)

    # 2. recorte a resolucion completa, con margen para el registro
    cw = min(int(round(g2.escala * BW)), BW)
    ch = min(int(round(cw * MH / MW)), BH)
    cx = min(max(int(round(g2.x * BW)), 0), BW - cw)
    cy = min(max(int(round(g2.y * BH)), 0), BH - ch)
    # Como mucho la MITAD del master y del recorte: el master se hizo reescalando el
    # bruto con un filtro que no conocemos, y un grado no lineal no conmuta con un
    # reescalado. Reducir los dos al menos a la mitad hace que ese filtro pese poco.
    # Medido en el montaje sintetico: `pruebas/NOTAS.md` §3.
    tw = max(min(ancho_analisis, MW // reduccion_minima, cw // reduccion_minima), 16)
    th = max(int(round(tw * MH / MW)), 8)
    f = tw / cw  # pixeles de analisis por pixel del bruto
    margen = int(np.ceil(0.02 * cw)) + 2
    ex0, ey0 = max(cx - margen, 0), max(cy - margen, 0)
    ex1, ey1 = min(cx + cw + margen, BW), min(cy + ch + margen, BH)
    ancho_ext = max(int(round((ex1 - ex0) * f)), 8)
    alto_ext = max(int(round((ey1 - ey0) * f)), 8)
    bruto_ext = _redim(bruto[ey0:ey1, ex0:ex1], ancho_ext, alto_ext)
    m = _redim(master, tw, th)
    notas.append(f"medido a {tw}x{th} (el master activo es {MW}x{MH})")

    # 3. registro subpixel: la rejilla del master manda
    ox, oy = (cx - ex0) * f, (cy - ey0) * f
    inicial = bruto_ext[int(round(oy)) : int(round(oy)) + th, int(round(ox)) : int(round(ox)) + tw]
    b = inicial
    encaje = 0.0
    if inicial.shape[:2] == (th, tw) and not subpixel:
        b = inicial
        notas.append("sin registro subpixel (pedido)")
    elif inicial.shape[:2] == (th, tw):
        desplazado = np.float32([[1, 0, ox], [0, 1, oy]])
        movil = cv2.warpAffine(bruto_ext, desplazado, (tw, th),
                               flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_REPLICATE)
        warp, encaje = _registro_subpixel(m, movil, (th, tw))
        if warp is not None:
            total = warp.astype(np.float64).copy()
            total[:, 2] += (ox, oy)
            b = cv2.warpAffine(bruto_ext, total.astype(np.float32), (tw, th),
                               flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_REPLICATE)
            notas.append(
                f"registro subpixel: desplazamiento ({warp[0, 2]:+.2f}, {warp[1, 2]:+.2f}) px, "
                f"escala ({warp[0, 0]:.4f}, {warp[1, 1]:.4f}), correlacion {encaje:.3f}"
            )
        else:
            b = movil
            notas.append(
                "el registro subpixel no ha convergido: se mide con el recorte a pixel entero, "
                "y el ΔE maximo puede salir inflado por los bordes"
            )
    else:
        b = _redim(bruto[cy : cy + ch, cx : cx + cw], tw, th)
        notas.append("recorte pegado al borde del bruto: sin registro subpixel")

    return Pareja(
        nombre=nombre,
        bruto=np.asarray(to_working(np.ascontiguousarray(b), espacio_bruto), dtype=np.float32),  # type: ignore[arg-type]
        master=np.asarray(to_working(m, espacio_master), dtype=np.float32),  # type: ignore[arg-type]
        recorte_px=(cx, cy, cw, ch),
        encaje_afinado=float(encaje or g2.ncc),
        notas=notas,
    )


#: Fraccion de pixeles con mas gradiente que se considera "borde".
FRACCION_BORDES: float = 0.15


def mascara_bordes(img_trabajo: np.ndarray) -> np.ndarray:
    """(h, w) bool: el `FRACCION_BORDES` de pixeles con mas gradiente, ensanchado 1 px.

    Ahi es donde un reescalado distinto o un encaje a media fraccion de pixel
    cambian el color de un pixel mezclado aunque el grado sea perfecto. Es una
    ayuda para leer el ΔE maximo, NO un sustituto: el titular sigue siendo el
    maximo con bordes.
    """
    y = luma(np.asarray(img_trabajo, dtype=np.float32))
    gx = cv2.Sobel(y, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(y, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    umbral = float(np.percentile(mag, 100.0 * (1.0 - FRACCION_BORDES)))
    borde = (mag >= umbral).astype(np.uint8)
    return cv2.dilate(borde, np.ones((3, 3), np.uint8)).astype(bool)


def medir_t1(p: Pareja, *, tam_lut: int = LUT_SIZE_DEFAULT) -> tuple[ReverseResult, MedidaT1]:
    r = invertir_grado(p.bruto, p.master, tam_lut=tam_lut)
    m = r.confidence.metrics
    e = _errores(r, p)  # el mismo calculo que T5, sobre su propio plano
    con_datos = int(np.count_nonzero(r.coverage.covered_mask()))
    return r, MedidaT1(
        de_max_cubierto=float(m.get("de_max_cubierto", float("nan"))),
        de_p95_cubierto=float(m.get("de_p95_cubierto", float("nan"))),
        de_medio_cubierto=float(m.get("de_medio_cubierto", float("nan"))),
        de_max_cubierto_sin_bordes=e["max_vista_sin_bordes"],
        de_medio_cubierto_sin_bordes=e["medio_vista_sin_bordes"],
        fraccion_bordes=e["fraccion_bordes"],
        de_max_todo=float(r.delta_e_max),
        de_medio_todo=float(r.delta_e_mean),
        celdas_con_datos=con_datos,
        celdas_totales=int(r.coverage.counts.size),
        fraccion_cubierta=float(r.coverage.coverage_fraction()),
        lut_reproducible=float(r.diagnosis.lut_reproducible),
        es_lut_puro=bool(r.diagnosis.is_pure_lut),
        confianza_grado=float(r.confidence.score),
        nivel_grado=str(r.confidence.level),
        cdl={
            "slope": list(map(float, r.cdl.slope)),
            "offset": list(map(float, r.cdl.offset)),
            "power": list(map(float, r.cdl.power)),
            "saturation": float(r.cdl.saturation),
        },
        notas=[*p.notas, *r.notes],
    )


def _zona_vista(fuente_post_cdl: np.ndarray, r: ReverseResult) -> np.ndarray:
    """(M,) bool: pixel cuya celda mas cercana del cubo de `r` tiene datos.

    Misma definicion que la zona cubierta de `invertir_grado` (celda mas cercana
    con `counts >= min_samples`), reescrita aqui porque la de alli es privada.
    """
    n = r.coverage.size
    px = np.asarray(fuente_post_cdl, dtype=np.float64).reshape(-1, 3)
    i = np.rint(np.clip(px, 0.0, 1.0) * (n - 1)).astype(np.int64)
    return r.coverage.covered_mask()[i[:, 0], i[:, 1], i[:, 2]]


def _errores(r: ReverseResult, destino: Pareja) -> dict[str, float]:
    """ΔE2000 del grado `r` aplicado al bruto de `destino`, contra su master."""
    a, b, _ = alinear(destino.bruto, destino.master)
    post_cdl = r.cdl.apply(a.astype(np.float64))
    pred = r.lut.apply(post_cdl)
    de = np.asarray(delta_e2000(pred, b.astype(np.float64), WORKING_SPACE), dtype=np.float64)
    de = de.reshape(-1)
    fin = np.isfinite(de)
    vista = _zona_vista(post_cdl, r) & fin
    lejos = ~mascara_bordes(b).reshape(-1)

    def maximo(sel: np.ndarray) -> float:
        return float(de[sel].max()) if sel.any() else float("nan")

    def medio(sel: np.ndarray) -> float:
        return float(de[sel].mean()) if sel.any() else float("nan")

    return {
        "max": maximo(fin),
        "p95": float(np.percentile(de[fin], 95)) if fin.any() else float("nan"),
        "medio": medio(fin),
        "max_vista": maximo(vista),
        "medio_vista": medio(vista),
        "fraccion_vista": float(vista.sum()) / max(int(fin.sum()), 1),
        "max_sin_bordes": maximo(fin & lejos),
        "max_vista_sin_bordes": maximo(vista & lejos),
        "medio_vista_sin_bordes": medio(vista & lejos),
        "fraccion_bordes": float((~lejos).mean()),
    }


def medir_t5(origen: str, r: ReverseResult, destino: Pareja) -> MedidaT5:
    """Grado sacado de `origen` aplicado al bruto de `destino`, contra su master."""
    e = _errores(r, destino)
    return MedidaT5(
        origen=origen, destino=destino.nombre, de_max=e["max"], de_p95=e["p95"],
        de_medio=e["medio"], de_max_zona_vista=e["max_vista"],
        de_medio_zona_vista=e["medio_vista"], fraccion_zona_vista=e["fraccion_vista"],
        de_max_sin_bordes=e["max_sin_bordes"],
        de_max_zona_vista_sin_bordes=e["max_vista_sin_bordes"],
    )
