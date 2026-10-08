"""Modo cristal de la suite, aproximado en Qt (prototipo 2026-10-06).

QUE ES REAL Y QUE ES UNA APROXIMACION
-------------------------------------
La web usa `backdrop-filter: blur(8px) saturate(160%)`. **Qt no tiene
desenfoque de fondo.** Lo que hay aqui:

* REAL: el relleno translucido (bajo texto rgb(20 20 20 / .54), fuerte .68; el .2 de la web no da 4,5:1 con texto), el filo de
  1 px en degradado (blanco arriba-izquierda -> naranja #e8451d/.42
  abajo-derecha), el brillo superior (inset 0 1px 0 blanco/.09) y el reflejo
  (degradado blanco .06 -> .01 -> .025).
* APROXIMADO: el desenfoque. El fondo de la ventana (`FondoSuite`) es ESTATICO
  y se desenfoca UNA vez por tamano (reducir/ampliar suavizado, ~8 px); cada
  panel de cristal pinta ahi su trozo del fondo ya desenfocado. Eso imita el
  `backdrop-filter` sobre un fondo fijo. NO desenfoca otros widgets que haya
  detras (una imagen, otro panel), ni aplica `saturate(160%)`.
* NO HECHO: la sombra larga (0 24px 60px -28px negro/.7): sobre #1e1e1e no se
  ve y cuesta un paintEvent con blur por panel.

ENTORNO DE COLOR: el fondo lleva curvas de nivel naranja al 9 % y un resplandor
del 4 %; alrededor de la imagen (visor de la cortinilla, mapas) NO hay cristal ni
naranja: `Panel(neutro=True)` pinta el filo sin naranja y los visores van sobre
`HONDO` (#141414) liso.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from gui import identidad as idn

#: Tokens de cristal de `suite/tokens.css`. **Bajo texto, el relleno es >= 54 %**
#: (`--sb-glass-fill-text`): con el 20 % de la web el texto sobre cristal no llega a
#: 4,5:1 (leccion de los prototipos). `RELLENO_DECORATIVO` (20 %, el de la web) solo
#: serviria para un cristal SIN texto encima y hoy no lo usa nadie.
RELLENO_DECORATIVO = (20, 20, 20, int(0.20 * 255))
RELLENO = (20, 20, 20, int(0.54 * 255))          # --sb-glass-fill-text: paneles con texto
RELLENO_FUERTE = (20, 20, 20, int(0.68 * 255))   # --sb-glass-fill-hud: bandas y avisos
BLUR_PX = 8
LINEAS_ALPHA = 0.09  # curvas de nivel: naranja al 9 %
RESPLANDOR_ALPHA = 0.04


def _curvas(ancho: int, alto: int) -> list[np.ndarray]:
    """Curvas de nivel de un campo suave y determinista (semilla fija).

    Se calcula en una rejilla pequena y se estira al tamano de la ventana. Sin
    dependencias nuevas: `numpy` y `cv2` ya son de la app.
    """
    import cv2

    rng = np.random.default_rng(20261006)
    campo = rng.standard_normal((90, 144)).astype(np.float32)
    campo = cv2.GaussianBlur(campo, (0, 0), 9.0)
    campo = cv2.GaussianBlur(campo, (0, 0), 4.0) + 0.0
    campo = (campo - campo.min()) / (campo.max() - campo.min())
    # Inclinacion diagonal, como las curvas de la web.
    yy, xx = np.mgrid[0:90, 0:144].astype(np.float32)
    campo = 0.55 * campo + 0.45 * ((xx / 144.0) * 0.8 + (yy / 90.0) * 0.5)
    campo = (campo - campo.min()) / (campo.max() - campo.min())
    salida: list[np.ndarray] = []
    for nivel in np.linspace(0.08, 0.92, 15):
        mascara = (campo >= nivel).astype(np.uint8) * 255
        contornos, _ = cv2.findContours(mascara, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for c in contornos:
            if len(c) < 24:
                continue
            pts = c[:, 0, :].astype(np.float32)
            # Los puntos pegados al borde de la rejilla son el marco, no la curva.
            dentro = (pts[:, 0] > 1) & (pts[:, 0] < 142) & (pts[:, 1] > 1) & (pts[:, 1] < 88)
            if dentro.sum() < 24:
                continue
            # Se parte la polilinea en tramos continuos de puntos interiores.
            cortes = np.flatnonzero(np.diff(dentro.astype(np.int8)) != 0) + 1
            for tramo, ok in zip(np.split(pts, cortes), np.split(dentro, cortes), strict=True):
                if ok[0] and len(tramo) >= 24:
                    tramo = tramo.copy()
                    tramo[:, 0] *= ancho / 143.0
                    tramo[:, 1] *= alto / 89.0
                    salida.append(tramo)
    return salida


class FondoSuite(QWidget):
    """Raiz de la ventana: pinta el fondo base y las curvas de nivel."""

    es_fondo_suite = True

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pm: QPixmap | None = None
        self._pm_desenfocado: QPixmap | None = None
        self._tam = (0, 0)
        self._curvas_cache: list[np.ndarray] | None = None

    def _construir(self) -> None:
        w, h = max(self.width(), 1), max(self.height(), 1)
        if (w, h) == self._tam and self._pm is not None:
            return
        self._tam = (w, h)
        if self._curvas_cache is None:
            self._curvas_cache = _curvas(1000, 1000)
        pm = QPixmap(w, h)
        pm.fill(QColor(idn.FONDO))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Resplandor de marca arriba a la derecha, como la web (4 %).
        rad = QRadialGradient(QPointF(w * 0.92, h * 0.02), max(w, h) * 0.55)
        rad.setColorAt(0.0, idn.color(idn.BRAND_500, RESPLANDOR_ALPHA))
        rad.setColorAt(1.0, idn.color(idn.BRAND_500, 0.0))
        p.fillRect(pm.rect(), QBrush(rad))
        pen = QPen(idn.color(idn.BRAND_500, LINEAS_ALPHA), 1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for pts in self._curvas_cache:
            poli = QPolygonF([QPointF(x * w / 1000.0, y * h / 1000.0) for x, y in pts[::3]])
            p.drawPolyline(poli)
        p.end()
        self._pm = pm
        # Desenfoque ~8 px: bajar a 1/8 y subir suavizado, dos veces.
        img = pm.toImage()
        for _ in range(2):
            chica = img.scaled(max(w // 8, 1), max(h // 8, 1), Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            img = chica.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self._pm_desenfocado = QPixmap.fromImage(img)

    def recorte_desenfocado(self, rect) -> QPixmap | None:
        self._construir()
        if self._pm_desenfocado is None:
            return None
        return self._pm_desenfocado.copy(rect)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._construir()
        p = QPainter(self)
        if self._pm is not None:
            p.drawPixmap(0, 0, self._pm)
        p.end()


def _fondo_de(widget: QWidget) -> FondoSuite | None:
    w = widget.parentWidget()
    while w is not None:
        if getattr(w, "es_fondo_suite", False):
            return w
        w = w.parentWidget()
    return None


def pintar_cristal(
    p: QPainter,
    widget: QWidget,
    *,
    radio: float = idn.RADIO_TARJETA,
    fuerte: bool = False,
    neutro: bool = False,
) -> None:
    """Pinta el cristal en todo el rectangulo de `widget`.

    `neutro=True`: el filo no lleva el naranja de abajo-derecha (se usa en los
    marcos de las imagenes: el naranja no compite con el color que se juzga).
    """
    r = QRectF(widget.rect())
    ruta = QPainterPath()
    ruta.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radio, radio)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setClipPath(ruta)
    fondo = _fondo_de(widget)
    recorte = None
    if fondo is not None:
        origen = widget.mapTo(fondo, widget.rect().topLeft())
        recorte = fondo.recorte_desenfocado(widget.rect().translated(origen))
    if recorte is not None:
        p.drawPixmap(0, 0, recorte)
    else:  # sin fondo de suite (dialogos): base opaca para que el texto no pierda contraste
        p.fillPath(ruta, QColor(idn.FONDO))
    relleno = QColor(*(RELLENO_FUERTE if fuerte else RELLENO))
    p.fillPath(ruta, relleno)
    # Reflejo: degradado blanco .06 -> .01 (42 %) -> .025
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0.0, QColor(255, 255, 255, int(.06 * 255)))
    g.setColorAt(0.42, QColor(255, 255, 255, int(.01 * 255)))
    g.setColorAt(1.0, QColor(255, 255, 255, int(.025 * 255)))
    p.fillPath(ruta, QBrush(g))
    p.setClipping(False)
    # Brillo superior de 1 px (inset 0 1px 0 blanco .09)
    p.setPen(QPen(QColor(255, 255, 255, int(.09 * 255)), 1.0))
    p.drawLine(QPointF(r.left() + radio * 0.6, r.top() + 1.5), QPointF(r.right() - radio * 0.6, r.top() + 1.5))
    # Filo degradado de 1 px: blanco .34 -> .06 (30 %) -> .03 (62 %) -> naranja .42
    f = QLinearGradient(r.topLeft(), r.bottomRight())
    f.setColorAt(0.0, QColor(255, 255, 255, int(.34 * 255)))
    f.setColorAt(0.30, QColor(255, 255, 255, int(.06 * 255)))
    f.setColorAt(0.62, QColor(255, 255, 255, int(.03 * 255)))
    f.setColorAt(1.0, QColor(255, 255, 255, int(.06 * 255)) if neutro else idn.color(idn.BRAND_500, .42))
    p.setPen(QPen(QBrush(f), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(ruta)
    p.restore()


__all__ = ["FondoSuite", "pintar_cristal", "RELLENO", "RELLENO_DECORATIVO", "RELLENO_FUERTE"]
