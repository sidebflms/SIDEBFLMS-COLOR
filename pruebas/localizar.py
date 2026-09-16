"""Localizar cada bruto dentro del master: donde sale, recortado como, y con que confianza.

EL PROBLEMA
-----------
El master es la pieza entregada entera. Cada bruto aparece dentro **en algun
momento, recortado, y con otro color**. El color es distinto a proposito (es el
grado que se quiere extraer), asi que **no se puede buscar por color**: se busca
por **estructura**.

Emparejar mal un bruto con el plano equivocado produce un "grado" basura con
muy buena cara. Por eso todo este archivo esta escrito para **decir que no**
antes que para acertar mucho.

COMO LO HACE, EN CINCO PASOS
----------------------------
1. **Escanear el master** entero a 128 px de ancho, fotograma a fotograma. De
   cada fotograma se guarda su luma en 8 bits y su huella de contenido
   (`core.analysis.huella_de_contenido`, ciega al color: invariancia al grado
   medida en `CIFRAS.md`). Se detectan los **cortes** comparando la estructura
   de cada fotograma con la del anterior, y las **bandas negras** (letterbox).
2. **Escanear los brutos** a 256 px de ancho y a `muestreo` fotogramas por
   segundo (2 por defecto). De cada muestra se guardan la luma y un **banco de
   huellas**: la del fotograma entero y las de 14 recortes a dos escalas (para
   encontrar planos reencuadrados, cuya huella completa ya no se parece).
3. **Busqueda gruesa**: cada cierto numero de fotogramas del master (`paso`), su
   huella contra todo el banco. Salen los candidatos: las mejores muestras de
   los 4 brutos que mas se parecen.
4. **Refinado por estructura**: a cada candidato se le busca la escala y la
   posicion exactas con correlacion normalizada de la **estructura local** de
   la luma (luma menos su media local, dividida por su desviacion local). Eso
   quita el brillo y el contraste de cada zona, que es lo que cambia un grado, y
   deja los bordes, que es lo que no cambia. Despues se afina el **fotograma
   exacto** leyendo el bruto a su cadencia completa alrededor de la muestra.
5. **Agrupar y verificar**: los puntos consecutivos que caen en el mismo bruto
   con el mismo desfase de tiempo forman una **aparicion**. Se verifica leyendo
   los fotogramas que el desfase predice en otros puntos del plano. Si el plano
   se movia y la prediccion no encaja, no era ese.

LA CONFIANZA, Y LO QUE NO ESTA MEDIDO
-------------------------------------
Tres notas de 0 a 1 y **manda la peor**:

- **encaje**: la peor correlacion de estructura entre el punto elegido y las
  verificaciones. Se mapea linealmente entre `NCC_NADA` (0) y `NCC_PLENO` (1).
- **margen**: cuanto mejor encaja este bruto que el mejor de OTRO bruto,
  medido como cociente de desajustes `(1 - ncc_otro) / (1 - ncc_este)`. Una toma
  gemela (toma 1 / toma 2) da un cociente cercano a 1 y hunde la nota.
- **duracion**: fotogramas de la aparicion frente a `FOTOGRAMAS_FIABLES`.

La nota se convierte en alta/media/baja con `core.contracts.confidence_level`, el
unico sitio del proyecto que lo hace. **Solo se aceptan las de nivel `alta`.**

**Ninguna de estas constantes esta medida sobre material real.** Estan puestas a
mano y comprobadas **solo** contra el montaje sintetico de
`tests/test_pruebas_localizar.py`, cuyas cifras (encajes correctos, encajes de la
toma gemela) estan en `pruebas/NOTAS.md` con el comando que las reproduce. La
primera prueba real es justo lo que dira si valen.

LO QUE NO SABE HACER (dicho aqui y en el instructivo)
-----------------------------------------------------
- Planos **retocados en velocidad** (camara lenta en montaje, rampas): se asume
  que un segundo del master es un segundo del bruto.
- Planos **volteados, rotados o estabilizados** en montaje, o con **pantalla
  partida / imagen dentro de imagen**.
- **Pixel no cuadrado** (anamorfico sin desanamorfizar): la proporcion se toma
  de la resolucion del fichero.
- Recortes mas pequenos que `escala_minima` del ancho del bruto (0.5 por
  defecto): no se buscan.
- Rotulos grandes encima del plano bajan el encaje (y por tanto la confianza),
  pero no lo confunden con otro plano.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from core.analysis import huella_de_contenido
from core.contracts import FINGERPRINT_LEN, LUMA_REC709, confidence_level

from . import lectura

__all__ = [
    "ANCHO_ESCANEO_BRUTO",
    "ANCHO_ESCANEO_MASTER",
    "Aparicion",
    "EscaneoBruto",
    "EscaneoMaster",
    "Geometria",
    "Localizacion",
    "buscar_geometria",
    "escanear_bruto",
    "escanear_master",
    "estructura",
    "localizar",
]

# ---------------------------------------------------------------------------
# Constantes. Ninguna medida sobre material real: ver el docstring.
# ---------------------------------------------------------------------------

#: Ancho al que se escanea el master. 128 px bastan para la estructura de un
#: plano y hacen que escanear 5 minutos de master quepa en unos cientos de MB.
ANCHO_ESCANEO_MASTER: int = 128

#: Ancho al que se escanea cada bruto: el doble que el master, para que un
#: recorte a la mitad del ancho siga teniendo 128 px reales sin inventar detalle.
ANCHO_ESCANEO_BRUTO: int = 256

#: Desviacion del suavizado que define "local" en la estructura, en pixeles del
#: tamano al que se compara (128 de ancho).
SIGMA_ESTRUCTURA: float = 1.5

#: Suavizado previo, en los mismos pixeles. Quita el detalle de menos de un pixel
#: de escaneo (rayas finas, grano), que al reducir el master y el bruto desde
#: tamanos distintos cae con fases distintas y parece "otra estructura". Lo que
#: separa del fotograma vecino, con y sin el, esta medido en `pruebas/NOTAS.md` §2
#: (`test_pruebas_medir.py -k prefiltro`).
SIGMA_PREFILTRO: float = 1.2

#: Suelo de la varianza local (en luma 0..1 al cuadrado). Por debajo, la zona se
#: trata como plana y no aporta: evita que el ruido de un cielo liso "encaje".
EPS_ESTRUCTURA: float = 0.01**2

#: Por debajo de esta correlacion entre un fotograma y el anterior, hay corte.
UMBRAL_CORTE: float = 0.35

#: Un fotograma con menos textura media que esto es negro, blanco o un fundido
#: a color plano: no se localiza.
TEXTURA_MINIMA: float = 0.15

#: Recortes del banco de huellas: (escala relativa a la maxima, rejilla de posiciones).
BANCO_RECORTES: tuple[tuple[float, int], ...] = ((1.0, 1), (0.75, 2), (0.56, 3))

#: Muestras de luma por segundo que se guardan de cada bruto. Decodificar cuesta lo
#: mismo con 2 que con 4 (ffmpeg decodifica todos y tira los que sobran); lo que
#: sube es la memoria: 256x144 bytes por muestra.
MUESTREO_BRUTOS: float = 4.0

#: Filas por segundo del banco de huellas. El banco solo tiene que acercarse (a
#: un segundo); lo fino lo hacen las lumas. Es lo caro del escaneo de brutos.
MUESTREO_BANCO: float = 2.0

#: Cada cuantos fotogramas del master se busca.
PASO_MASTER: int = 12

#: Recorte mas pequeno que se busca, como fraccion del ancho del bruto.
ESCALA_MINIMA: float = 0.5

#: Fotogramas del master con los que se verifica cada aparicion, como mucho.
VERIFICACIONES_MAX: int = 4

#: Candidatos por punto: las N mejores muestras de los M brutos que mas se parecen.
BRUTOS_CANDIDATOS: int = 4
MUESTRAS_POR_BRUTO: int = 2

#: Encaje de estructura que vale 0 y que vale 1 en la nota de confianza.
NCC_NADA: float = 0.60
NCC_PLENO: float = 0.90

#: Cociente de desajustes (otro bruto / este) que vale 0 y que vale 1.
MARGEN_NADA: float = 1.0
MARGEN_PLENO: float = 2.5

#: Fotogramas a partir de los cuales la duracion no resta confianza.
FOTOGRAMAS_FIABLES: int = 12

#: Tolerancia para decir que dos puntos tienen "el mismo desfase", en fotogramas
#: del bruto, ademas de la incertidumbre del muestreo.
TOLERANCIA_DESFASE_FOTOGRAMAS: float = 2.0


# ---------------------------------------------------------------------------
# Estructura local
# ---------------------------------------------------------------------------


def luma(rgb: np.ndarray) -> np.ndarray:
    """(h, w, 3) valores de codigo -> (h, w) float32. Pesos Rec.709 del contrato."""
    return (np.asarray(rgb, dtype=np.float32) @ np.asarray(LUMA_REC709, dtype=np.float32)).astype(
        np.float32
    )


def estructura(y: np.ndarray, sigma: float = SIGMA_ESTRUCTURA) -> np.ndarray:
    """Luma menos su media local, dividida por su desviacion local.

    Un grado cambia brillo y contraste de cada zona; esto los quita y deja la
    forma. Las zonas planas (varianza local < `EPS_ESTRUCTURA`) salen cerca de 0.
    """
    y = np.asarray(y, dtype=np.float32)
    if SIGMA_PREFILTRO > 0:
        y = cv2.GaussianBlur(y, (0, 0), SIGMA_PREFILTRO)
    mu = cv2.GaussianBlur(y, (0, 0), sigma)
    d = y - mu
    var = cv2.GaussianBlur(d * d, (0, 0), sigma)
    return (d / np.sqrt(var + EPS_ESTRUCTURA)).astype(np.float32)


def huella_de_luma(y: np.ndarray) -> np.ndarray:
    """`huella_de_contenido` de una luma suelta.

    La huella solo mira la luma (Rec.709 del contrato) y los pesos suman 1, asi
    que pasarle la luma repetida en los tres canales da la misma huella que la
    imagen en color. Asi el escaneo no tiene que guardar color.
    """
    y = np.asarray(y, dtype=np.float32)
    return huella_de_contenido(np.repeat(y[..., None], 3, axis=2))


def _ncc_misma_forma(a: np.ndarray, b: np.ndarray) -> float:
    r = cv2.matchTemplate(a.astype(np.float32), b.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    v = float(r.max())
    return v if math.isfinite(v) else 0.0


@dataclass(frozen=True)
class Geometria:
    """Donde esta el plano del master dentro del bruto. Todo normalizado 0..1."""

    escala: float  # ancho del recorte / ancho del bruto
    x: float  # esquina izquierda, fraccion del ancho del bruto
    y: float  # esquina superior, fraccion del alto del bruto
    ncc: float  # correlacion de estructura en esa posicion

    def alto_rel(self, aspecto_master: float, aspecto_bruto: float) -> float:
        """Alto del recorte como fraccion del alto del bruto. aspecto = alto/ancho."""
        return self.escala * aspecto_master / aspecto_bruto


def _escalas(escala_max: float, escala_min: float, razon: float) -> list[float]:
    out = []
    s = escala_max
    while s >= escala_min * 0.999:
        out.append(s)
        s *= razon
    return out


def buscar_geometria(
    bruto_luma: np.ndarray,
    master_luma: np.ndarray,
    *,
    escala_min: float,
    escalas: Iterable[float] | None = None,
    afinar: bool = True,
) -> Geometria:
    """Mejor escala y posicion de `master_luma` dentro de `bruto_luma`.

    `master_luma` se compara a su tamano; el bruto se reescala para que el
    recorte candidato mida lo mismo. Devuelve ncc = 0 si ninguna escala cabe.
    """
    mh, mw = master_luma.shape
    bh, bw = bruto_luma.shape
    plantilla = estructura(master_luma)
    aspecto_m, aspecto_b = mh / mw, bh / bw
    escala_max = min(1.0, aspecto_b / aspecto_m)
    lista = list(escalas) if escalas is not None else _escalas(escala_max, escala_min, 0.95)

    def probar(s: float) -> Geometria | None:
        ancho = int(round(mw / s))
        alto = int(round(ancho * aspecto_b))
        if ancho < mw or alto < mh:
            return None
        interp = cv2.INTER_AREA if ancho <= bw else cv2.INTER_LINEAR
        est = estructura(cv2.resize(bruto_luma, (ancho, alto), interpolation=interp))
        r = cv2.matchTemplate(est, plantilla, cv2.TM_CCOEFF_NORMED)
        _, v, _, (px, py) = cv2.minMaxLoc(r)
        if not math.isfinite(v):
            return None
        return Geometria(escala=mw / ancho, x=px / ancho, y=py / alto, ncc=float(v))

    mejor = Geometria(escala=escala_max, x=0.0, y=0.0, ncc=0.0)
    for s in lista:
        g = probar(s)
        if g is not None and g.ncc > mejor.ncc:
            mejor = g
    if afinar and mejor.ncc > 0:
        for k in (-3, -2, -1, 1, 2, 3):
            s = mejor.escala * (1.0 + 0.012 * k)
            if s > escala_max * 1.0001 or s < escala_min * 0.97:
                continue
            g = probar(s)
            if g is not None and g.ncc > mejor.ncc:
                mejor = g
    return mejor


def encaje_fijo(bruto_luma: np.ndarray, master_luma: np.ndarray, g: Geometria,
                holgura_px: int = 4) -> Geometria:
    """Encaje con la escala de `g` y la posicion libre en +-`holgura_px`."""
    mh, mw = master_luma.shape
    bh, bw = bruto_luma.shape
    ancho = int(round(mw / g.escala))
    alto = int(round(ancho * bh / bw))
    if ancho < mw or alto < mh:
        return Geometria(g.escala, g.x, g.y, 0.0)
    interp = cv2.INTER_AREA if ancho <= bw else cv2.INTER_LINEAR
    est = estructura(cv2.resize(bruto_luma, (ancho, alto), interpolation=interp))
    px, py = int(round(g.x * ancho)), int(round(g.y * alto))
    x0, y0 = max(px - holgura_px, 0), max(py - holgura_px, 0)
    x1, y1 = min(px + holgura_px + mw, ancho), min(py + holgura_px + mh, alto)
    zona = est[y0:y1, x0:x1]
    if zona.shape[0] < mh or zona.shape[1] < mw:
        return Geometria(g.escala, g.x, g.y, 0.0)
    r = cv2.matchTemplate(zona, estructura(master_luma), cv2.TM_CCOEFF_NORMED)
    _, v, _, (qx, qy) = cv2.minMaxLoc(r)
    v = float(v) if math.isfinite(v) else 0.0
    return Geometria(escala=mw / ancho, x=(x0 + qx) / ancho, y=(y0 + qy) / alto, ncc=v)


# ---------------------------------------------------------------------------
# Escaneo del master
# ---------------------------------------------------------------------------


@dataclass
class EscaneoMaster:
    ruta: Path
    info: lectura.InfoMedio
    lumas: np.ndarray  # (n, h, w) uint8
    huellas: np.ndarray  # (n, 96) float32, del area activa
    similitud_anterior: np.ndarray  # (n,) float32; [0] = 0
    textura: np.ndarray  # (n,) float32
    area_activa: tuple[int, int, int, int]  # (y0, y1, x0, x1) en pixeles de escaneo
    cortes: list[int]  # indices donde empieza un tramo nuevo (incluye 0)

    @property
    def n(self) -> int:
        return int(self.lumas.shape[0])

    def luma_activa(self, k: int) -> np.ndarray:
        y0, y1, x0, x1 = self.area_activa
        return self.lumas[k, y0:y1, x0:x1].astype(np.float32) / 255.0

    def tramos(self) -> list[tuple[int, int]]:
        """[(desde, hasta_exclusivo)] entre cortes."""
        bordes = [*self.cortes, self.n]
        return [(bordes[i], bordes[i + 1]) for i in range(len(bordes) - 1) if bordes[i + 1] > bordes[i]]


def _area_activa(maximos_fila: np.ndarray, maximos_col: np.ndarray) -> tuple[int, int, int, int]:
    """Quita bandas negras: filas/columnas de los bordes que nunca pasan de negro."""
    umbral = 6  # de 255: negro con ruido de compresion
    filas = np.nonzero(maximos_fila > umbral)[0]
    cols = np.nonzero(maximos_col > umbral)[0]
    if filas.size == 0 or cols.size == 0:
        return (0, maximos_fila.size, 0, maximos_col.size)
    return (int(filas[0]), int(filas[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)


def escanear_master(
    ruta: Path, info: lectura.InfoMedio, *, progreso: Callable[[str], None] | None = None,
    fotogramas: Iterable[np.ndarray] | None = None,
) -> EscaneoMaster:
    """Primera pasada: luma 8 bits, cortes y bandas negras. Solo lee."""
    it = fotogramas if fotogramas is not None else lectura.recorrer(ruta, info, ANCHO_ESCANEO_MASTER)
    lumas: list[np.ndarray] = []
    sim: list[float] = []
    tex: list[float] = []
    anterior: np.ndarray | None = None
    for k, rgb in enumerate(it):
        y = luma(rgb)
        lumas.append(np.clip(np.round(y * 255.0), 0, 255).astype(np.uint8))
        est = estructura(y)
        tex.append(float(np.mean(np.abs(est))))
        if anterior is None:
            sim.append(0.0)
        else:
            m = 8
            centro = est[m:-m, m:-m]
            sim.append(_ncc_misma_forma(anterior, centro))
        anterior = est
        if progreso and k % 500 == 0 and k:
            progreso(f"  master: {k} fotogramas escaneados")
    if not lumas:
        raise lectura.ErrorLectura(f"no he podido leer ni un fotograma del master {ruta.name}")
    L = np.stack(lumas)
    area = _area_activa(L.max(axis=(0, 2)), L.max(axis=(0, 1)))
    y0, y1, x0, x1 = area
    huellas = np.stack(
        [huella_de_luma(fila[y0:y1, x0:x1].astype(np.float32) / 255.0) for fila in L]
    ).astype(np.float32)
    sim_arr = np.asarray(sim, dtype=np.float32)
    tex_arr = np.asarray(tex, dtype=np.float32)
    cortes = [0]
    for k in range(1, L.shape[0]):
        vacio_cambia = (tex_arr[k] < TEXTURA_MINIMA) != (tex_arr[k - 1] < TEXTURA_MINIMA)
        if sim_arr[k] < UMBRAL_CORTE or vacio_cambia:
            cortes.append(k)
    return EscaneoMaster(ruta, info, L, huellas, sim_arr, tex_arr, area, cortes)


# ---------------------------------------------------------------------------
# Escaneo de los brutos
# ---------------------------------------------------------------------------


def escalas_cerca(escala: float, escala_min: float, escala_max: float,
                  paso_rel: float = 0.015, pasos: int = 3) -> list[float]:
    """Escalas alrededor de `escala`, para buscar sin volver a barrer todo."""
    out: list[float] = []
    for k in range(-pasos, pasos + 1):
        s = escala * (1.0 + paso_rel * k)
        if s < escala_min * 0.97:
            continue
        # Lo que se pasa del maximo se sujeta al maximo, no se tira: si no, un
        # plano a escala 1.0 buscado desde 0.992 nunca prueba el 1.0.
        s = min(s, escala_max)
        if all(abs(s - o) > 1e-6 for o in out):
            out.append(s)
    return out or [escala]


def _escala_max(master_luma: np.ndarray, bruto_luma: np.ndarray) -> float:
    mh, mw = master_luma.shape
    bh, bw = bruto_luma.shape
    return min(1.0, (bh / bw) / (mh / mw))


# ---------------------------------------------------------------------------
# Escaneo de los brutos
# ---------------------------------------------------------------------------


@dataclass
class EscaneoBruto:
    nombre: str
    ruta: Path
    info: lectura.InfoMedio
    muestreo: float  # muestras de luma por segundo
    paso_banco: int  # una fila del banco cada `paso_banco` muestras
    lumas: np.ndarray  # (k, h, w) uint8 a ANCHO_ESCANEO_BRUTO
    banco: np.ndarray  # (ceil(k / paso_banco), r, 96) float32
    recortes: list[tuple[float, float, float]]  # (escala, x, y) de cada columna del banco

    @property
    def n(self) -> int:
        return int(self.lumas.shape[0])

    def instante(self, muestra: int) -> float:
        return muestra / self.muestreo

    def luma(self, muestra: int) -> np.ndarray:
        return self.lumas[muestra].astype(np.float32) / 255.0


def recortes_del_banco(aspecto_master: float, aspecto_bruto: float) -> list[tuple[float, float, float]]:
    """Recortes (escala, x, y) del banco: el cuadro entero y dos escalas de reencuadre."""
    smax = min(1.0, aspecto_bruto / aspecto_master)
    out: list[tuple[float, float, float]] = []
    for rel, rejilla in BANCO_RECORTES:
        s = smax * rel
        h = s * aspecto_master / aspecto_bruto
        if rejilla == 1:
            out.append((s, (1 - s) / 2, (1 - h) / 2))
            continue
        posiciones = np.linspace(0.0, 1.0, rejilla)
        puntos = [(px, py) for py in posiciones for px in posiciones]
        if rejilla == 2:
            puntos.append((0.5, 0.5))
        for px, py in puntos:
            out.append((s, (1 - s) * px, (1 - h) * py))
    return out


def escanear_bruto(
    nombre: str, ruta: Path, info: lectura.InfoMedio, *, aspecto_master: float,
    muestreo: float = MUESTREO_BRUTOS, fotogramas: Iterable[np.ndarray] | None = None,
) -> EscaneoBruto:
    """Luma a `muestreo` fps y banco de huellas a `MUESTREO_BANCO` fps. Solo lee."""
    it = fotogramas if fotogramas is not None else lectura.recorrer(
        ruta, info, ANCHO_ESCANEO_BRUTO, fps=muestreo
    )
    paso_banco = max(int(round(muestreo / MUESTREO_BANCO)), 1)
    lumas: list[np.ndarray] = []
    banco: list[np.ndarray] = []
    recortes: list[tuple[float, float, float]] = []
    for k, rgb in enumerate(it):
        h, w = rgb.shape[:2]
        if not recortes:
            recortes = recortes_del_banco(aspecto_master, h / w)
        l8 = np.clip(np.round(luma(rgb) * 255.0), 0, 255).astype(np.uint8)
        lumas.append(l8)
        if k % paso_banco:
            continue
        lf = l8.astype(np.float32) / 255.0
        fila = []
        for s, x, y in recortes:
            x0, y0 = int(round(x * w)), int(round(y * h))
            ww = max(int(round(s * w)), 8)
            hh = max(int(round(ww * aspecto_master)), 8)
            fila.append(huella_de_luma(lf[y0 : y0 + hh, x0 : x0 + ww]))
        banco.append(np.stack(fila))
    if not lumas:
        raise lectura.ErrorLectura(f"no he podido leer ni un fotograma de {ruta.name}")
    return EscaneoBruto(
        nombre, ruta, info, float(muestreo), paso_banco, np.stack(lumas),
        np.stack(banco).astype(np.float32), recortes,
    )


# ---------------------------------------------------------------------------
# Localizacion
# ---------------------------------------------------------------------------


@dataclass
class Candidato:
    bruto: str
    muestra: int
    geometria: Geometria


@dataclass
class Punto:
    """Un fotograma del master donde se ha buscado."""

    master: int
    tramo: int
    vacio: bool = False
    propio: Candidato | None = None
    alternativo: Candidato | None = None  # el mejor de OTRO bruto

    @property
    def cociente(self) -> float:
        """(1 - encaje del otro bruto) / (1 - encaje propio). Alto = sin ambiguedad."""
        if self.propio is None:
            return 0.0
        otro = self.alternativo.geometria.ncc if self.alternativo else 0.0
        return (1.0 - max(otro, 0.0)) / max(1.0 - self.propio.geometria.ncc, 0.02)


@dataclass
class Aparicion:
    """Un trozo del master que sale de un bruto (o eso se cree, con su confianza)."""

    bruto: str
    master_desde: int
    master_hasta: int  # exclusivo
    desfase_s: float  # instante_bruto - instante_master
    geometria: Geometria  # en el fotograma de medida
    master_medida: int  # fotograma del master elegido para medir
    bruto_medida: int  # fotograma del bruto que le corresponde
    verificaciones: list[tuple[int, float]]  # (fotograma del master, encaje)
    alternativa: str | None
    ncc_alternativa: float
    ncc_propio_mediano: float
    margen: float
    nota_encaje: float
    nota_margen: float
    nota_duracion: float
    confianza: float
    nivel: str
    aceptada: bool
    razones: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return self.master_hasta - self.master_desde


@dataclass
class Localizacion:
    apariciones: list[Aparicion]
    no_encontrados: list[str]
    tramos_sin_bruto: list[tuple[int, int, str]]  # (desde, hasta, motivo)
    parametros: dict


def _clip01(v: float) -> float:
    return float(min(max(v, 0.0), 1.0))


def _candidatos(huella: np.ndarray, brutos: list[EscaneoBruto]) -> list[tuple[str, int]]:
    """Las mejores muestras de los brutos que mas se parecen, sin repetir instante."""
    por_bruto: list[tuple[float, str, list[int]]] = []
    for b in brutos:
        sims = (b.banco @ huella).max(axis=1)  # (filas,)
        orden = np.argsort(-sims)
        elegidas: list[int] = []
        separacion = max(int(round(MUESTREO_BANCO)), 1)  # un segundo, en filas del banco
        for i in orden:
            if all(abs(int(i) - j) >= separacion for j in elegidas):
                elegidas.append(int(i))
            if len(elegidas) >= MUESTRAS_POR_BRUTO:
                break
        por_bruto.append((float(sims.max()), b.nombre, [f * b.paso_banco for f in elegidas]))
    por_bruto.sort(key=lambda t: -t[0])
    salida = []
    for _, nombre, muestras in por_bruto[:BRUTOS_CANDIDATOS]:
        salida.extend((nombre, m) for m in muestras)
    return salida


def _afinar_en_muestras(b: EscaneoBruto, c: Candidato, ml: np.ndarray, escala_min: float) -> Candidato:
    """Recorre las muestras de luma vecinas (+-0.75 s) buscando la que mejor encaja."""
    radio = int(math.ceil(0.75 * b.muestreo))
    mejor = c
    smax = _escala_max(ml, b.luma(0))
    for j in range(max(c.muestra - radio, 0), min(c.muestra + radio + 1, b.n)):
        g = buscar_geometria(
            b.luma(j), ml, escala_min=escala_min,
            escalas=escalas_cerca(c.geometria.escala, escala_min, smax), afinar=False,
        )
        if g.ncc > mejor.geometria.ncc:
            mejor = Candidato(b.nombre, j, g)
    return mejor


def _mejor_en_ventana(
    b: EscaneoBruto, primero: int, n: int, master_luma: np.ndarray, g: Geometria,
    escala_min: float, leer: Callable[[EscaneoBruto, int, int], np.ndarray],
) -> tuple[int, Geometria]:
    """Fotograma del bruto (a cadencia completa) que mejor encaja cerca de `g`."""
    primero = max(primero, 0)
    fot = leer(b, primero, n)
    mejor_i, mejor_g = -1, Geometria(g.escala, g.x, g.y, 0.0)
    for j in range(fot.shape[0]):
        lj = luma(fot[j])
        gj = buscar_geometria(
            lj, master_luma, escala_min=escala_min,
            escalas=escalas_cerca(g.escala, escala_min, _escala_max(master_luma, lj)),
            afinar=False,
        )
        if gj.ncc > mejor_g.ncc:
            mejor_i, mejor_g = primero + j, gj
    return mejor_i, mejor_g


def _leer_ventana_real(b: EscaneoBruto, primero: int, n: int) -> np.ndarray:
    return lectura.ventana(b.ruta, b.info, primero, n, ANCHO_ESCANEO_BRUTO)


def _puntuar(
    *, encaje: float, verificado: bool, ncc_propio: float, ncc_alt: float,
    alternativa: str | None, n_fot: int,
) -> tuple[float, float, float, float, float, str, list[str]]:
    """(margen, nota_encaje, nota_margen, nota_duracion, confianza, nivel, razones)."""
    margen = (1.0 - max(ncc_alt, 0.0)) / max(1.0 - ncc_propio, 0.02)
    nota_encaje = _clip01((encaje - NCC_NADA) / (NCC_PLENO - NCC_NADA))
    nota_margen = _clip01((margen - MARGEN_NADA) / (MARGEN_PLENO - MARGEN_NADA))
    nota_duracion = _clip01(n_fot / FOTOGRAMAS_FIABLES)
    razones: list[str] = []
    if not verificado:
        nota_encaje = min(nota_encaje, 0.5)
        razones.append(
            "no hay otro fotograma del plano con el que verificar el desfase: con uno solo "
            "no se puede distinguir de una toma parecida"
        )
    conf = min(nota_encaje, nota_margen, nota_duracion)
    nivel = confidence_level(conf)
    if nota_encaje < 1.0 and verificado:
        razones.append(
            f"la estructura encaja {encaje:.3f} en el peor punto verificado "
            f"(cuenta como pleno a partir de {NCC_PLENO})"
        )
    if nota_margen < 1.0:
        otro = alternativa or "otro bruto"
        razones.append(
            f"poca diferencia con el mejor candidato de otro bruto ({otro}: encaja "
            f"{ncc_alt:.3f}, y este {ncc_propio:.3f}; cociente de desajustes {margen:.2f}, "
            f"pleno a partir de {MARGEN_PLENO}). Puede ser una toma gemela, un clip "
            f"duplicado, o un plano que encaja mal"
        )
    if nota_duracion < 1.0:
        razones.append(
            f"plano muy corto: {n_fot} fotogramas (fiable a partir de {FOTOGRAMAS_FIABLES})"
        )
    return margen, nota_encaje, nota_margen, nota_duracion, conf, nivel, razones


def localizar(
    master: EscaneoMaster,
    brutos: list[EscaneoBruto],
    *,
    paso: int = PASO_MASTER,
    escala_minima: float = ESCALA_MINIMA,
    leer_ventana: Callable[[EscaneoBruto, int, int], np.ndarray] = _leer_ventana_real,
    progreso: Callable[[str], None] | None = None,
) -> Localizacion:
    """Encuentra las apariciones de los brutos en el master. Solo lee."""
    por_nombre = {b.nombre: b for b in brutos}
    fm = master.info.fps if master.info.fps > 0 else 25.0
    tramos = master.tramos()

    # --- 1. puntos de busqueda: cada `paso` fotogramas de cada tramo ----------
    puntos: list[Punto] = []
    for t, (desde, hasta) in enumerate(tramos):
        largo = hasta - desde
        n_pts = max(1, int(math.ceil(largo / paso)))
        for i in range(n_pts):
            k = int(desde + (i + 0.5) * largo / n_pts)
            puntos.append(Punto(master=k, tramo=t, vacio=bool(master.textura[k] < TEXTURA_MINIMA)))

    # --- 2. busqueda gruesa por huella, refinado por estructura y por tiempo --
    for i, p in enumerate(puntos):
        if progreso and i % 25 == 0:
            progreso(f"  buscando: punto {i + 1} de {len(puntos)}")
        if p.vacio or not brutos:
            continue
        ml = master.luma_activa(p.master)
        cands = [
            Candidato(nombre, m, buscar_geometria(por_nombre[nombre].luma(m), ml,
                                                  escala_min=escala_minima))
            for nombre, m in _candidatos(master.huellas[p.master], brutos)
        ]
        if not cands:
            continue
        cands.sort(key=lambda c: -c.geometria.ncc)
        p.propio = _afinar_en_muestras(por_nombre[cands[0].bruto], cands[0], ml, escala_minima)
        otros = [c for c in cands if c.bruto != p.propio.bruto]
        if otros:
            # El alternativo se afina IGUAL que el propio: si no, el margen saldria
            # inflado por comparar un candidato afinado con uno sin afinar.
            p.alternativo = _afinar_en_muestras(por_nombre[otros[0].bruto], otros[0], ml, escala_minima)

    # --- 3. agrupar puntos consecutivos con el mismo bruto y desfase ----------
    def desfase(p: Punto) -> float:
        return por_nombre[p.propio.bruto].instante(p.propio.muestra) - p.master / fm  # type: ignore[union-attr]

    grupos: list[list[int]] = []  # indices en `puntos`
    for i, p in enumerate(puntos):
        if p.propio is None:
            continue
        if grupos and grupos[-1][-1] == i - 1:
            q = puntos[i - 1]
            b = por_nombre[p.propio.bruto]
            tol = 1.0 / b.muestreo + TOLERANCIA_DESFASE_FOTOGRAMAS / max(b.info.fps, 1.0)
            if q.propio.bruto == p.propio.bruto and abs(desfase(p) - desfase(q)) <= tol:  # type: ignore[union-attr]
                grupos[-1].append(i)
                continue
        grupos.append([i])

    # --- 4. fotograma exacto de cada grupo ----------------------------------
    afinados: list[dict] = []
    for g in grupos:
        propios = [puntos[i] for i in g]
        b = por_nombre[propios[0].propio.bruto]  # type: ignore[union-attr]
        fb = b.info.fps if b.info.fps > 0 else fm
        mejor = max(propios, key=lambda r: r.propio.geometria.ncc)  # type: ignore[union-attr]
        ml = master.luma_activa(mejor.master)
        centro = int(round(b.instante(mejor.propio.muestra) * fb))  # type: ignore[union-attr]
        # Ventana de un intervalo de muestreo entero a cada lado: en una
        # panoramica la muestra elegida puede estar desplazada, y si el fotograma
        # bueno queda fuera se elige uno vecino que encaja casi igual.
        media = int(math.ceil(fb / b.muestreo)) + 2
        idx_b, g_fino = _mejor_en_ventana(
            b, centro - media, 2 * media + 1, ml, mejor.propio.geometria,  # type: ignore[union-attr]
            escala_minima, leer_ventana,
        )
        if idx_b < 0:
            idx_b, g_fino = centro, mejor.propio.geometria  # type: ignore[union-attr]
        afinados.append({
            "g": list(g), "b": b, "mejor": mejor, "idx_b": idx_b, "geom": g_fino,
            "desf": idx_b / fb - mejor.master / fm,
        })

    # --- 5. fusionar grupos contiguos del mismo bruto y el mismo desfase fino --
    fusion: list[dict] = []
    for a in afinados:
        if fusion:
            u = fusion[-1]
            fb = a["b"].info.fps if a["b"].info.fps > 0 else fm
            if (
                u["b"].nombre == a["b"].nombre
                and u["g"][-1] == a["g"][0] - 1
                and abs(u["desf"] - a["desf"]) <= TOLERANCIA_DESFASE_FOTOGRAMAS / fb
            ):
                base = a if a["geom"].ncc > u["geom"].ncc else u
                fusion[-1] = {**base, "g": u["g"] + a["g"]}
                continue
        fusion.append(a)

    # --- 6. extension, verificacion y confianza -------------------------------
    apariciones: list[Aparicion] = []
    for a in fusion:
        g = a["g"]
        propios = [puntos[i] for i in g]
        b = a["b"]
        fb = b.info.fps if b.info.fps > 0 else fm
        mejor, idx_b, g_fino, desf = a["mejor"], a["idx_b"], a["geom"], a["desf"]

        primero, ultimo = propios[0], propios[-1]
        previo = puntos[g[0] - 1] if g[0] > 0 else None
        if previo is None or previo.tramo != primero.tramo:
            desde = tramos[primero.tramo][0]
        else:
            desde = (previo.master + primero.master) // 2 + 1
        siguiente = puntos[g[-1] + 1] if g[-1] + 1 < len(puntos) else None
        if siguiente is None or siguiente.tramo != ultimo.tramo:
            hasta = tramos[ultimo.tramo][1]
        else:
            hasta = (ultimo.master + siguiente.master) // 2 + 1

        objetivos = [p.master for p in propios if p is not mejor]
        if len(objetivos) > VERIFICACIONES_MAX:
            sel = np.linspace(0, len(objetivos) - 1, VERIFICACIONES_MAX)
            objetivos = [objetivos[int(round(j))] for j in sel]
        if not objetivos:
            objetivos = [k for k in (mejor.master - 3, mejor.master + 3) if desde <= k < hasta]
        verifs: list[tuple[int, float]] = []
        for k in objetivos:
            pred = int(round((k / fm + desf) * fb))
            if pred < 0 or (b.info.n_fotogramas and pred >= b.info.n_fotogramas):
                verifs.append((k, 0.0))
                continue
            _, gv = _mejor_en_ventana(
                b, pred - 1, 3, master.luma_activa(k), g_fino, escala_minima, leer_ventana
            )
            verifs.append((k, gv.ncc))

        encaje = min([g_fino.ncc, *[v for _, v in verifs]])
        # Margen: el punto MEDIANO del grupo. No el peor, porque un punto dentro
        # de un fundido tiene poco encaje propio y daria un margen bajo que no
        # habla de ambiguedad; y no el mejor, porque una toma gemela es ambigua
        # en todo el plano y la mediana lo recoge igual. El encaje ya lo vigila
        # la verificacion.
        mediano = sorted(propios, key=lambda r: r.cociente)[(len(propios) - 1) // 2]
        alt = mediano.alternativo
        margen, n_e, n_m, n_d, conf, nivel, razones = _puntuar(
            encaje=encaje, verificado=bool(verifs),
            ncc_propio=mediano.propio.geometria.ncc,  # type: ignore[union-attr]
            ncc_alt=alt.geometria.ncc if alt else 0.0,
            alternativa=alt.bruto if alt else None, n_fot=hasta - desde,
        )
        apariciones.append(Aparicion(
            bruto=b.nombre, master_desde=desde, master_hasta=hasta, desfase_s=desf,
            geometria=g_fino, master_medida=mejor.master, bruto_medida=idx_b,
            verificaciones=verifs, alternativa=alt.bruto if alt else None,
            ncc_alternativa=alt.geometria.ncc if alt else 0.0,
            ncc_propio_mediano=mediano.propio.geometria.ncc,  # type: ignore[union-attr]
            margen=margen, nota_encaje=n_e, nota_margen=n_m, nota_duracion=n_d,
            confianza=conf, nivel=nivel, aceptada=(nivel == "alta"), razones=razones,
        ))

    usados = {a.bruto for a in apariciones if a.aceptada}
    no_encontrados = [b.nombre for b in brutos if b.nombre not in usados]

    cubiertos = np.zeros(master.n, dtype=bool)
    for a in apariciones:
        if a.aceptada:
            cubiertos[a.master_desde : a.master_hasta] = True
    sin_bruto: list[tuple[int, int, str]] = []
    for desde, hasta in tramos:
        if cubiertos[desde:hasta].any():
            continue
        vacio = float(np.mean(master.textura[desde:hasta] < TEXTURA_MINIMA)) > 0.5
        motivo = (
            "negro, blanco o color plano (nada que localizar)"
            if vacio
            else "ningun bruto encaja con confianza alta"
        )
        sin_bruto.append((desde, hasta, motivo))

    return Localizacion(
        apariciones=apariciones,
        no_encontrados=no_encontrados,
        tramos_sin_bruto=sin_bruto,
        parametros={
            "paso": paso,
            "escala_minima": escala_minima,
            "ancho_escaneo_master": ANCHO_ESCANEO_MASTER,
            "ancho_escaneo_bruto": ANCHO_ESCANEO_BRUTO,
            "muestreo_brutos_fps": sorted({b.muestreo for b in brutos}),
            "muestreo_banco_fps": MUESTREO_BANCO,
            "ncc_nada": NCC_NADA,
            "ncc_pleno": NCC_PLENO,
            "margen_nada": MARGEN_NADA,
            "margen_pleno": MARGEN_PLENO,
            "fotogramas_fiables": FOTOGRAMAS_FIABLES,
            "umbral_corte": UMBRAL_CORTE,
            "tramos_detectados": len(tramos),
            "puntos_de_busqueda": len(puntos),
            "area_activa_escaneo": list(master.area_activa),
            "fingerprint_len": FINGERPRINT_LEN,
        },
    )
