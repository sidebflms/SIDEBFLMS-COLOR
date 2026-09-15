"""Pantalla 2 — antes / despues.

POR QUE CORTINILLA Y NO OTRA COSA
---------------------------------
Se han considerado tres y se ha hecho **una sola, bien**:

* **Lado a lado.** Descartada. Con 16:9 a la mitad de ancho cada plano queda
  pequenisimo, y lo peor: el ojo compara dos sitios distintos de la pantalla, y
  para diferencias de color de 1-2 ΔE eso no funciona. Es lo que hace que dos
  tomas parezcan iguales en una revision y distintas en la sala.
* **Alternar (A/B parpadeando).** Descartada como opcion principal. Es la que
  mejor detecta diferencias pequenas, pero **no se puede capturar**: una captura
  de un parpadeo es una de las dos imagenes y ya. Y este encargo se juzga con
  capturas.
* **Cortinilla.** Elegida. El borde de la cortinilla pone los dos planos *en
  contacto*, que es donde el ojo humano detecta una diferencia de color minima,
  y una captura quieta ensena las dos mitades a la vez.

La cortinilla es **arrastrable con el raton y movible con las flechas** (Shift
para ir fino, Inicio/Fin para irse a un extremo), y la posicion se lee en
monoespaciada, como toda cifra.

Y una cosa que se olvida: el «despues» no es una simulacion. Es
`MatchResult.cdl.apply()`, o sea la formula del contrato, que es exactamente la
que Resolve ejecuta en el nodo 2. Lo que se ve aqui es lo que se vera alli.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui import identidad as idn
from gui.datos_demo import ClipDemo, EstadoDemo
from gui.imagen import a_qimage
from gui.widgets import Cifra, EtiquetaElidida, InsigniaConfianza, MarcaDesajuste, Panel, Rotulo

#: Cuanto se mueve la cortinilla con una flecha, y con Shift+flecha.
PASO_FLECHA = 0.02
PASO_FINO = 0.005


class VisorCortinilla(QWidget):
    """Dos imagenes del mismo tamano, separadas por una cortinilla vertical."""

    posicion_cambiada = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._antes: QImage | None = None
        self._despues: QImage | None = None
        self._pos = 0.5
        self._arrastrando = False
        self._mensaje = "No hay imagen para este clip."
        self.setMinimumSize(280, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    # -- datos -------------------------------------------------------------

    def poner(self, antes: QImage | None, despues: QImage | None, *, mensaje: str = "") -> None:
        self._antes, self._despues = antes, despues
        if mensaje:
            self._mensaje = mensaje
        self.update()

    def posicion(self) -> float:
        return self._pos

    def set_posicion(self, valor: float) -> None:
        nuevo = max(0.0, min(1.0, float(valor)))
        if abs(nuevo - self._pos) > 1e-9:
            self._pos = nuevo
            self.posicion_cambiada.emit(nuevo)
            self.update()

    # -- geometria ---------------------------------------------------------

    def _marco(self) -> QRect:
        """Donde cae la imagen dentro del widget, respetando la proporcion."""
        if self._despues is None:
            return self.rect()
        w, h = self._despues.width(), self._despues.height()
        if w <= 0 or h <= 0:
            return self.rect()
        disponible = self.rect().adjusted(1, 1, -1, -1)
        escala = min(disponible.width() / w, disponible.height() / h)
        ancho, alto = int(w * escala), int(h * escala)
        x = disponible.left() + (disponible.width() - ancho) // 2
        y = disponible.top() + (disponible.height() - alto) // 2
        return QRect(x, y, ancho, alto)

    # -- pintura -----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QBrush(idn.color(idn.HONDO)))
        if self._antes is None or self._despues is None:
            p.setPen(QPen(idn.color(idn.BRAND_50, idn.TEXTO_APAGADO_A)))
            p.setFont(idn.fuente_texto(13))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._mensaje)
            p.end()
            return

        marco = self._marco()
        p.drawImage(marco, self._despues)
        corte = marco.left() + int(marco.width() * self._pos)
        izquierda = QRect(marco.left(), marco.top(), max(0, corte - marco.left()), marco.height())
        if izquierda.width() > 0:
            origen = QRectF(
                0.0, 0.0,
                self._antes.width() * (izquierda.width() / marco.width()),
                float(self._antes.height()),
            )
            p.drawImage(QRectF(izquierda), self._antes, origen)

        self._rotulos(p, marco, corte)
        self._mango(p, marco, corte)
        p.setPen(QPen(idn.color(idn.BRAND_50, idn.BORDE_A), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(marco.adjusted(0, 0, -1, -1))
        p.end()

    def _rotulos(self, p: QPainter, marco: QRect, corte: int) -> None:
        f = idn.fuente_rotulo(10)
        p.setFont(f)
        metricas = QFontMetrics(f)
        for texto, a_la_izquierda in (("antes", True), ("después", False)):
            ancho = metricas.horizontalAdvance(texto.upper()) + 18
            alto = metricas.height() + 8
            if a_la_izquierda:
                if corte - marco.left() < ancho + 12:
                    continue
                caja = QRect(marco.left() + 10, marco.top() + 10, ancho, alto)
            else:
                if marco.right() - corte < ancho + 12:
                    continue
                caja = QRect(marco.right() - ancho - 10, marco.top() + 10, ancho, alto)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(10, 9, 8, 190)))
            p.drawRoundedRect(caja, 3, 3)
            p.setPen(QPen(idn.color(idn.BRAND_50 if a_la_izquierda else idn.BRAND_400)))
            p.drawText(caja, int(Qt.AlignmentFlag.AlignCenter), texto)

    def _mango(self, p: QPainter, marco: QRect, corte: int) -> None:
        """La linea de la cortinilla y su agarradero. En acento de marca."""
        p.setPen(QPen(idn.color(idn.BRAND_500), 1.5))
        p.drawLine(corte, marco.top(), corte, marco.bottom())
        cy = marco.center().y()
        agarre = QRect(corte - 7, cy - 18, 14, 36)
        p.setPen(QPen(idn.color(idn.BRAND_500), 1.0))
        p.setBrush(QBrush(idn.color(idn.BRAND_600)))
        p.drawRoundedRect(agarre, 4, 4)
        p.setPen(QPen(idn.color(idn.BRAND_50, 0.85), 1.0))
        for dx in (-2, 2):
            p.drawLine(corte + dx, cy - 7, corte + dx, cy + 7)

    # -- interaccion -------------------------------------------------------

    def _desde_x(self, x: int) -> None:
        marco = self._marco()
        if marco.width() <= 0:
            return
        self.set_posicion((x - marco.left()) / marco.width())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._arrastrando = True
        self._desde_x(event.position().toPoint().x())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._arrastrando:
            self._desde_x(event.position().toPoint().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._arrastrando = False

    def keyPressEvent(self, event) -> None:  # noqa: N802
        fino = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        paso = PASO_FINO if fino else PASO_FLECHA
        tecla = event.key()
        if tecla == Qt.Key.Key_Left:
            self.set_posicion(self._pos - paso)
        elif tecla == Qt.Key.Key_Right:
            self.set_posicion(self._pos + paso)
        elif tecla == Qt.Key.Key_Home:
            self.set_posicion(0.0)
        elif tecla == Qt.Key.Key_End:
            self.set_posicion(1.0)
        else:
            super().keyPressEvent(event)


class Miniatura(QWidget):
    """Una imagen pequena con su rotulo. Para la referencia."""

    def __init__(self, rotulo: str, parent=None) -> None:
        super().__init__(parent)
        self._img: QImage | None = None
        self._rotulo = rotulo
        self.setMinimumSize(120, 70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(120)

    def poner(self, img: QImage | None) -> None:
        self._img = img
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QBrush(idn.color(idn.HONDO)))
        if self._img is not None:
            w, h = self._img.width(), self._img.height()
            disp = self.rect().adjusted(1, 1, -1, -1)
            escala = min(disp.width() / w, disp.height() / h)
            ancho, alto = int(w * escala), int(h * escala)
            caja = QRect(disp.left() + (disp.width() - ancho) // 2,
                         disp.top() + (disp.height() - alto) // 2, ancho, alto)
            p.drawImage(caja, self._img)
        else:
            p.setPen(QPen(idn.color(idn.BRAND_50, idn.TEXTO_TENUE_A)))
            p.setFont(idn.fuente_texto(11))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "sin imagen")
        p.setPen(QPen(idn.color(idn.BRAND_50, idn.BORDE_A), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class PantallaComparar(QWidget):
    """Selector de clip + cortinilla + las cifras del emparejamiento."""

    def __init__(self, estado: EstadoDemo, parent=None) -> None:
        super().__init__(parent)
        self._estado = estado
        self._cache: dict[str, tuple[QImage | None, QImage | None]] = {}

        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)

        caja.addWidget(self._barra())

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(12)

        marco = Panel(margenes=(10, 10, 10, 10), espaciado=8)
        self.visor = VisorCortinilla()
        marco.caja.addWidget(self.visor, 1)
        pie = QHBoxLayout()
        pie.setSpacing(12)
        self.pos_texto = Cifra("50.0 %", px=12)
        pie.addWidget(Rotulo("cortinilla"), 0)
        pie.addWidget(self.pos_texto, 0)
        ayuda = EtiquetaElidida(
            "arrastra la línea · ← → mueven · Mayús+← → afinan · Inicio/Fin a los extremos",
            ancho_minimo_px=60,
        )
        ayuda.setObjectName("tenue")
        ayuda.setFont(idn.fuente_texto(11))
        pie.addWidget(ayuda, 1)
        marco.caja.addLayout(pie)
        cuerpo.addWidget(marco, 1)

        cuerpo.addWidget(self._lateral(), 0)
        caja.addLayout(cuerpo, 1)

        self.visor.posicion_cambiada.connect(
            lambda v: self.pos_texto.setText(f"{v * 100:5.1f} %")
        )
        self.selector.currentIndexChanged.connect(self._cambio)
        if estado.clips:
            self.selector.setCurrentIndex(self._primero_util())
            self._cambio()
        else:
            self._sin_clips()

    # -- construccion ------------------------------------------------------

    def _barra(self) -> QWidget:
        panel = Panel(cristal=True, margenes=(14, 10, 14, 10))
        fila = QHBoxLayout()
        fila.setSpacing(14)
        fila.addWidget(Rotulo("clip"), 0)
        self.selector = QComboBox()
        self.selector.setFont(idn.fuente_texto(13))
        self.selector.setMinimumWidth(180)
        self.selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selector.setMaximumWidth(460)
        for c in self._estado.clips:
            self.selector.addItem(c.nombre, c.clip_id)
        fila.addWidget(self.selector, 1)
        fila.addStretch(1)
        self.insignia = InsigniaConfianza(idn.FormaConfianza.ALTA, 0.0)
        fila.addWidget(self.insignia, 0)
        self.marca = MarcaDesajuste()
        fila.addWidget(self.marca, 0)
        panel.caja.addLayout(fila)
        return panel

    def _lateral(self) -> QWidget:
        lateral = QWidget()
        lateral.setMinimumWidth(200)
        lateral.setMaximumWidth(300)
        col = QVBoxLayout(lateral)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)

        panel_ref = Panel(margenes=(10, 10, 10, 10))
        panel_ref.caja.addWidget(Rotulo("referencia", acento=True))
        self.mini_ref = Miniatura("referencia")
        panel_ref.caja.addWidget(self.mini_ref)
        self.nombre_ref = EtiquetaElidida("—", modo=Qt.TextElideMode.ElideMiddle)
        self.nombre_ref.setObjectName("apagado")
        self.nombre_ref.setFont(idn.fuente_texto(12))
        panel_ref.caja.addWidget(self.nombre_ref)
        col.addWidget(panel_ref)

        panel_cifras = Panel(margenes=(14, 12, 14, 12))
        panel_cifras.caja.addWidget(Rotulo("lo que cambia", acento=True))
        self._cifras: dict[str, Cifra] = {}
        for clave, rotulo, sec in (
            ("antes", "ΔE antes", False),
            ("despues", "ΔE después", True),
        ):
            panel_cifras.caja.addWidget(Rotulo(rotulo))
            etiqueta = Cifra("—", px=24, peso=QFont.Weight.DemiBold, secundario=sec)
            self._cifras[clave] = etiqueta
            panel_cifras.caja.addWidget(etiqueta)
        col.addWidget(panel_cifras)

        panel_cdl = Panel(margenes=(14, 12, 14, 12), espaciado=4)
        panel_cdl.caja.addWidget(Rotulo("cdl del nodo 2", acento=True))
        self.texto_cdl = QLabel("—")
        self.texto_cdl.setFont(idn.fuente_cifra(11))
        self.texto_cdl.setObjectName("apagado")
        self.texto_cdl.setMinimumWidth(0)
        self.texto_cdl.setWordWrap(True)
        panel_cdl.caja.addWidget(self.texto_cdl)
        col.addWidget(panel_cdl)

        col.addStretch(1)
        return lateral

    # -- datos -------------------------------------------------------------

    def _imagenes(self, clip: ClipDemo) -> tuple[QImage | None, QImage | None]:
        if clip.clip_id in self._cache:
            return self._cache[clip.clip_id]
        if clip.original is None:
            par: tuple[QImage | None, QImage | None] = (None, None)
        else:
            despues = clip.despues()
            par = (a_qimage(clip.original), a_qimage(despues) if despues is not None else None)
        self._cache[clip.clip_id] = par
        return par

    def _sin_clips(self) -> None:
        self.selector.setEnabled(False)
        self.insignia.setVisible(False)
        self.marca.setVisible(False)
        self.visor.poner(None, None, mensaje="No hay clips que comparar.")
        self.nombre_ref.setText("—")

    def _cambio(self) -> None:
        clip = self.clip_actual()
        if clip is None:
            self._sin_clips()
            return
        antes, despues = self._imagenes(clip)
        self.visor.poner(
            antes, despues,
            mensaje=(
                f"El clip {clip.clip_id} no trae fotograma en memoria.\n"
                "Los números del emparejamiento sí son suyos; la imagen no se ha guardado."
            ),
        )
        conf = clip.match.confidence
        self.insignia.setVisible(True)
        self.insignia.actualizar(idn.FormaConfianza.de_nivel(conf.level), conf.score)
        self.marca.setVisible(clip.match.content_mismatch)
        self._cifras["antes"].setText(f"{clip.match.delta_e_before:.2f}")
        self._cifras["despues"].setText(f"{clip.match.delta_e_after:.2f}")
        cdl = clip.match.cdl
        self.texto_cdl.setText(
            f"slope  {cdl.slope[0]:.4f} {cdl.slope[1]:.4f} {cdl.slope[2]:.4f}\n"
            f"offset {cdl.offset[0]:+.4f} {cdl.offset[1]:+.4f} {cdl.offset[2]:+.4f}\n"
            f"power  {cdl.power[0]:.4f} {cdl.power[1]:.4f} {cdl.power[2]:.4f}\n"
            f"sat    {cdl.saturation:.4f}"
        )
        if self._estado.referencia_img is not None:
            self.mini_ref.poner(a_qimage(self._estado.referencia_img))
        ref = self._estado.por_id(self._estado.referencia_id or "")
        self.nombre_ref.setText(ref.nombre if ref else "referencia del proyecto")

    def _primero_util(self) -> int:
        """El primer clip que NO sea la referencia.

        Arrancar en la referencia deja la cortinilla ensenando la misma imagen a
        los dos lados y los dos ΔE a 0.00: una pantalla de comparacion que no
        compara nada. Se veia en la primera captura.
        """
        for i, clip in enumerate(self._estado.clips):
            if clip.clip_id != self._estado.referencia_id:
                return i
        return 0

    def clip_actual(self) -> ClipDemo | None:
        idx = self.selector.currentIndex()
        if idx < 0:
            return None
        return self._estado.por_id(self.selector.itemData(idx))

    def seleccionar(self, clip_id: str) -> None:
        for i in range(self.selector.count()):
            if self.selector.itemData(i) == clip_id:
                self.selector.setCurrentIndex(i)
                return


__all__ = ["PASO_FINO", "PASO_FLECHA", "Miniatura", "PantallaComparar", "VisorCortinilla"]
