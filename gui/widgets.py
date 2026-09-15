"""Piezas reutilizables de la interfaz.

Lo importante que vive aqui:

* `EtiquetaElidida` — un `QLabel` que **se recorta con puntos suspensivos** en
  vez de empujar el ancho minimo de la ventana. `QLabel` a secas pide de ancho
  minimo lo que mida su texto entero, asi que un solo nombre de clip largo hace
  que la ventana no se pueda encoger. Ese es exactamente el fallo recurrente de
  la app hermana de ingest, y por eso casi todo el texto variable de esta GUI
  pasa por aqui.
* `pintar_insignia_confianza` — la confianza **por forma**, no por color de
  semaforo. Se usa desde un widget suelto y desde el delegado de la tabla, para
  que las dos se dibujen con el mismo codigo.
* `Cifra` — `QLabel` monoespaciado. Toda cifra de la app es una de estas.
* `MarcaDesajuste` — el aviso de «estas dos escenas no son comparables». En
  naranja de marca y con forma propia (rombo), **nunca en rojo**.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from gui import identidad as idn

# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------


class EtiquetaElidida(QLabel):
    """`QLabel` que recorta con «...» en vez de imponer un ancho minimo.

    Las tres piezas, y las tres importan:

    * `sizeHint()` pide el ancho del texto entero, para que en una ventana
      holgada el layout le de lo que necesita.
    * `minimumSizeHint()` devuelve `ancho_minimo_px`, para que al estrujar la
      ventana el widget CEDA en vez de empujar la anchura minima hacia arriba.
    * El texto se recorta contra el ancho MENOS los margenes, no contra
      `width()` a secas. Con margenes puestos, `width()` se pasa por lo que
      midan los margenes y el texto sale cortado a lo bruto justo en el borde.
      Ese fue un bug real de esta noche: el «escribe en «SIDEB COLOR»» del
      carril salia como «escribe en «SIDEB COLOF».

    Un `QLabel` normal hace justo lo contrario: su ancho minimo es el de su
    texto entero, o sea que un nombre de clip largo deja la ventana sin poder
    encogerse. Ese es el fallo recurrente de la app hermana de ingest.
    """

    def __init__(
        self,
        texto: str = "",
        *,
        modo: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
        ancho_minimo_px: int = 40,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._texto_completo = texto
        self._modo = modo
        self._ancho_minimo = ancho_minimo_px
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._refrescar()

    def texto_completo(self) -> str:
        return self._texto_completo

    def setText(self, texto: str) -> None:  # noqa: N802  (API de Qt)
        self._texto_completo = texto
        self.updateGeometry()
        self._refrescar()

    def _margen_horizontal(self) -> int:
        m = self.contentsMargins()
        return m.left() + m.right()

    def _refrescar(self) -> None:
        metricas = QFontMetrics(self.font())
        disponible = max(self.width() - self._margen_horizontal() - 1, 8)
        recortado = metricas.elidedText(self._texto_completo, self._modo, disponible)
        super().setText(recortado)
        # El texto entero siempre accesible aunque se vea recortado.
        self.setToolTip(self._texto_completo if recortado != self._texto_completo else "")

    def sizeHint(self) -> QSize:  # noqa: N802
        metricas = QFontMetrics(self.font())
        return QSize(
            metricas.horizontalAdvance(self._texto_completo) + self._margen_horizontal() + 2,
            metricas.height(),
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        metricas = QFontMetrics(self.font())
        return QSize(self._ancho_minimo + self._margen_horizontal(), metricas.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refrescar()

    def setFont(self, font: QFont) -> None:  # noqa: N802
        super().setFont(font)
        self.updateGeometry()
        self._refrescar()


class Rotulo(EtiquetaElidida):
    """Rotulo de marca: MAYUSCULAS, 10-11px, tracking 0.16em.

    **Un rotulo no se recorta nunca**, y eso lo impone `minimumSizeHint()`, no
    la buena voluntad: devuelve el ancho del texto ENTERO, o sea que el layout
    no puede estrujarlo. Un rotulo es el vocabulario fijo de la app —lo escribe
    la app, es corto, y esta puesto para decir que es cada cosa—, asi que
    recortado no informa de nada: «SLO...» no es «slope» y «CABE ...» no es
    «cabe en un .cube». Si un rotulo no cabe, lo que tiene que crecer es la
    anchura minima de la ventana, que para eso se mide.

    Hereda igualmente de `EtiquetaElidida`, y eso sigue teniendo sentido como
    ultimo recurso: si alguien le pone un `setMinimumWidth()` por encima o lo
    mete en un sitio que lo estruja de todas formas, saldra con puntos
    suspensivos y con el texto entero en el tooltip, en vez de comerse la
    ultima letra en silencio. Pero `tests/test_gui_texto.py` comprueba que ese
    ultimo recurso no se usa en ninguna pantalla.
    """

    #: Tamanos de la identidad: 10px el rotulo normal, 11px el de acento. Son
    #: los mismos que declara la hoja de estilo para `#rotulo` y `#titulo`, y
    #: tienen que coincidir: **el QSS pisa a `setFont()` en familia y tamano,
    #: pero NO en el tracking**, que no se puede escribir en QSS. Si aqui se
    #: construye la fuente a 10px y el QSS la pinta a 11, el tracking absoluto
    #: se queda en el de 10 y sale un 0.145em donde la identidad pide 0.15-0.18.
    PX_NORMAL = 10
    PX_ACENTO = 11

    def __init__(self, texto: str = "", *, px: int | None = None, acento: bool = False,
                 ancho_minimo_px: int = 30, parent: QWidget | None = None) -> None:
        super().__init__(texto, ancho_minimo_px=ancho_minimo_px, parent=parent)
        self.setObjectName("titulo" if acento else "rotulo")
        if px is None:
            px = self.PX_ACENTO if acento else self.PX_NORMAL
        self.setFont(idn.fuente_rotulo(px, QFont.Weight.Bold if acento else QFont.Weight.DemiBold))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """El texto entero. Un rotulo no cede ancho: lo cede la ventana."""
        return self.sizeHint()


class Cifra(QLabel):
    """Toda cifra de la app. Monoespaciada, sin excepcion (identidad)."""

    def __init__(self, texto: str = "", *, px: int = 13, peso: QFont.Weight = QFont.Weight.Normal,
                 secundario: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setFont(idn.fuente_cifra(px, peso))
        if secundario:
            self.setObjectName("secundario")
        else:
            self.setProperty("class", "cifra")


class Panel(QFrame):
    """Superficie `panel` con borde y radio. Trae su propio layout vertical."""

    def __init__(self, *, cristal: bool = False, margenes: tuple[int, int, int, int] = (14, 12, 14, 12),
                 espaciado: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cristal" if cristal else "panel")
        self.caja = QVBoxLayout(self)
        self.caja.setContentsMargins(*margenes)
        self.caja.setSpacing(espaciado)


def separador(vertical: bool = False) -> QFrame:
    linea = QFrame()
    linea.setObjectName("separador")
    linea.setFrameShape(QFrame.Shape.VLine if vertical else QFrame.Shape.HLine)
    if vertical:
        linea.setFixedWidth(1)
        linea.setMaximumHeight(16777215)
    else:
        linea.setFixedHeight(1)
    return linea


def fila_dato(rotulo: str, valor: str, *, secundario: bool = False) -> QWidget:
    """Una linea «ROTULO ....... valor». El valor siempre en monoespaciada."""
    w = QWidget()
    caja = QHBoxLayout(w)
    caja.setContentsMargins(0, 0, 0, 0)
    caja.setSpacing(10)
    # Sin `setMinimumWidth(0)`: eso le quitaba al rotulo su ancho minimo y lo
    # dejaba elidir, que es justo lo que `Rotulo` no hace.
    r = Rotulo(rotulo)
    caja.addWidget(r, 1)
    v = Cifra(valor, secundario=secundario)
    v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    caja.addWidget(v, 0)
    return w


# ---------------------------------------------------------------------------
# La confianza, por forma
# ---------------------------------------------------------------------------

#: Tamano nominal de la insignia. El delegado de la tabla usa el mismo.
INSIGNIA_ALTO = 22
INSIGNIA_ANCHO = 108


def pintar_insignia_confianza(
    p: QPainter,
    rect: QRect | QRectF,
    forma: idn.FormaConfianza,
    score: float,
) -> None:
    """Dibuja la insignia de confianza dentro de `rect`.

    **Tres formas distintas, un solo color de familia.** Relleno solido para
    alta, contorno continuo para media, contorno DISCONTINUO para baja; y un
    medidor de tres escalones a la izquierda con 3, 2 o 1 encendidos. Se lee en
    escala de grises y se lee a media resolucion, que es justo lo que un
    semaforo verde/ambar/rojo no hace (y ademas ese semaforo pisaria los tokens
    del inventario).
    """
    r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    trazo = QPen(forma.trazo, 1.0)
    if forma.discontinuo:
        trazo.setStyle(Qt.PenStyle.DashLine)
        trazo.setDashPattern([3.0, 2.5])
    p.setPen(trazo)
    p.setBrush(QBrush(forma.relleno) if forma.relleno is not None else Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, 4.0, 4.0)

    # Medidor de tres escalones.
    alto_util = r.height() - 10.0
    ancho_barra = 3.0
    x = r.left() + 9.0
    for i in range(3):
        encendido = i < forma.escalones
        alto = alto_util * (0.42 + 0.29 * i)
        barra = QRectF(x, r.center().y() + alto_util / 2 - alto, ancho_barra, alto)
        p.setPen(Qt.PenStyle.NoPen)
        if encendido:
            p.setBrush(QBrush(forma.texto))
            p.drawRect(barra)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            apagado = QPen(forma.texto, 1.0)
            apagado.setStyle(Qt.PenStyle.DotLine)
            p.setPen(apagado)
            p.drawRect(barra.adjusted(0.5, 0.5, -0.5, -0.5))
        x += ancho_barra + 3.0

    # Nivel + puntuacion. La puntuacion, en monoespaciada.
    p.setPen(QPen(forma.texto))
    x_texto = x + 6.0
    f_nivel = idn.fuente_rotulo(10)
    p.setFont(f_nivel)
    ancho_nivel = QFontMetrics(f_nivel).horizontalAdvance(forma.value.upper()) + 4
    p.drawText(
        QRectF(x_texto, r.top(), ancho_nivel, r.height()),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        forma.value.upper(),
    )
    p.setFont(idn.fuente_cifra(11))
    p.drawText(
        QRectF(x_texto + ancho_nivel + 4, r.top(), r.right() - x_texto - ancho_nivel - 8, r.height()),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        f"{score * 100:.0f}%",
    )
    p.restore()


class InsigniaConfianza(QWidget):
    """La insignia suelta, para las fichas de detalle."""

    def __init__(self, forma: idn.FormaConfianza, score: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._forma = forma
        self._score = float(score)
        self.setFixedSize(INSIGNIA_ANCHO, INSIGNIA_ALTO)
        self.setToolTip(f"confianza {forma.value}: {self._score * 100:.0f}%")

    def actualizar(self, forma: idn.FormaConfianza, score: float) -> None:
        self._forma, self._score = forma, float(score)
        self.setToolTip(f"confianza {forma.value}: {self._score * 100:.0f}%")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        pintar_insignia_confianza(p, self.rect(), self._forma, self._score)
        p.end()


class MarcaDesajuste(QWidget):
    """«Estas dos escenas no son comparables». Rombo con admiracion.

    Va en naranja de marca (`brand-400`) y **no en rojo**: es un aviso, no una
    accion destructiva. Se distingue del resto por la forma (rombo), que es la
    unica de la interfaz.
    """

    def __init__(self, *, lado: int = 18, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(lado, lado)
        self.setToolTip("desajuste de contenido: las dos escenas no son comparables")

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        rombo = QPolygonF(
            [
                QPointF(r.center().x(), r.top()),
                QPointF(r.right(), r.center().y()),
                QPointF(r.center().x(), r.bottom()),
                QPointF(r.left(), r.center().y()),
            ]
        )
        ruta = QPainterPath()
        ruta.addPolygon(rombo)
        ruta.closeSubpath()
        p.setPen(QPen(idn.color(idn.BRAND_400), 1.2))
        p.setBrush(QBrush(idn.color(idn.BRAND_400, 0.16)))
        p.drawPath(ruta)
        p.setFont(idn.fuente_cifra(10, QFont.Weight.Bold))
        p.setPen(QPen(idn.color(idn.BRAND_400)))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "!")
        p.end()


# ---------------------------------------------------------------------------
# Barra de proporcion (cobertura, lut_reproducible, progreso de lote)
# ---------------------------------------------------------------------------


class BarraProporcion(QWidget):
    """Una barra 0..1 de marca. Sin semaforo: el color no cambia con el valor.

    Lo que cambia con el valor es la **longitud**, que es lo unico que tiene que
    cambiar. Si el valor esta por debajo de `umbral_hueco` se dibuja ademas el
    resto con trazo discontinuo, la misma gramatica de forma que la confianza
    baja.
    """

    def __init__(self, valor: float = 0.0, *, alto: int = 8, umbral_hueco: float = 0.5,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._valor = max(0.0, min(1.0, float(valor)))
        self._umbral = umbral_hueco
        self.setFixedHeight(alto)
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def valor(self) -> float:
        return self._valor

    def set_valor(self, valor: float) -> None:
        self._valor = max(0.0, min(1.0, float(valor)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radio = r.height() / 2
        p.setPen(QPen(idn.color(idn.BRAND_50, idn.BORDE_A), 1.0))
        p.setBrush(QBrush(idn.color(idn.HONDO)))
        p.drawRoundedRect(r, radio, radio)
        ancho = r.width() * self._valor
        if ancho > 1.0:
            lleno = QRectF(r.left(), r.top(), ancho, r.height())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(idn.color(idn.BRAND_500)))
            p.drawRoundedRect(lleno, radio, radio)
        if self._valor < self._umbral and r.width() - ancho > 4:
            pluma = QPen(idn.color(idn.BRAND_400, 0.45), 1.0)
            pluma.setStyle(Qt.PenStyle.DashLine)
            pluma.setDashPattern([2.5, 2.5])
            p.setPen(pluma)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(r.left() + ancho, r.top(), r.width() - ancho, r.height()),
                              radio, radio)
        p.end()


def color_texto(alpha: float = 1.0) -> QColor:
    return idn.color(idn.BRAND_50, alpha)


__all__ = [
    "INSIGNIA_ALTO",
    "INSIGNIA_ANCHO",
    "BarraProporcion",
    "Cifra",
    "EtiquetaElidida",
    "InsigniaConfianza",
    "MarcaDesajuste",
    "Panel",
    "Rotulo",
    "color_texto",
    "fila_dato",
    "pintar_insignia_confianza",
    "separador",
]
