"""La ventana principal: carril de navegacion + las cuatro pantallas.

LA ANCHURA MINIMA
-----------------
`minimumSizeHint()` de esta ventana es **el numero que hay que capturar**, y no
uno que quede bonito. Para que ese numero sea de verdad util, todo el texto
variable de la interfaz (nombres de clip, rutas, avisos) va en widgets que se
recortan con puntos suspensivos (`EtiquetaElidida`) o en vistas que ya eliden
solas (`QTableView`, `QListWidget`). Lo que fija la anchura minima son las
piezas que **no** pueden encoger sin mentir: la tabla de clips con sus columnas
de cifras y su insignia, y los tres campos de 4 decimales del editor de CDL.

`anchura_minima()` lo consulta despues de un `ensurePolished()`, que es lo que
hace que Qt haya calculado ya los hints de los hijos. Sin eso el numero que sale
es mas pequeno de lo real y la captura sale enganosa.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.contracts import VERSION_NAME, ResolveError
from gui import identidad as idn
from gui.datos_demo import EstadoDemo, estado_demo, par_ingenieria_inversa, parches_carta
from gui.pantalla_aplicar import PantallaAplicar
from gui.pantalla_clips import PantallaClips
from gui.pantalla_comparar import PantallaComparar
from gui.pantalla_reverse import PantallaReverse
from gui.widgets import Cifra, EtiquetaElidida, Rotulo, separador

TITULO = "SIDEBFLMS COLOR"

PANTALLAS = (
    ("clips", "Clips y confianza"),
    ("comparar", "Antes / después"),
    ("aplicar", "Aplicar"),
    ("reverse", "Ingeniería inversa"),
)

#: Ancho del carril de navegacion. Fijo: es un carril, no un panel.
ANCHO_CARRIL = 186


class VentanaPrincipal(QMainWindow):
    def __init__(self, estado: EstadoDemo | None = None, *,
                 par_inverso: tuple | None = None, parent=None) -> None:
        super().__init__(parent)
        self._estado = estado if estado is not None else estado_demo()
        self.setWindowTitle(TITULO)

        raiz = QWidget()
        self.setCentralWidget(raiz)
        fila = QHBoxLayout(raiz)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)

        fila.addWidget(self._carril(), 0)

        derecha = QWidget()
        col = QVBoxLayout(derecha)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(14)
        col.addWidget(self._cabecera())
        self.pila = QStackedWidget()
        col.addWidget(self.pila, 1)
        col.addWidget(self._pie())
        fila.addWidget(derecha, 1)

        original, coloreado = par_inverso if par_inverso is not None else par_ingenieria_inversa()
        self.p_clips = PantallaClips(self._estado)
        self.p_comparar = PantallaComparar(self._estado)
        self.p_aplicar = PantallaAplicar(self._estado)
        self.p_reverse = PantallaReverse(original, coloreado, parches=parches_carta())
        for w in (self.p_clips, self.p_comparar, self.p_aplicar, self.p_reverse):
            self.pila.addWidget(w)

        self.p_clips.clip_elegido.connect(self.p_comparar.seleccionar)
        self.p_aplicar.aplicado.connect(self._refrescar_pie)
        self.ir_a(0)
        self._refrescar_pie()

    # -- construccion ------------------------------------------------------

    def _carril(self) -> QWidget:
        carril = QWidget()
        carril.setObjectName("hondo")
        carril.setFixedWidth(ANCHO_CARRIL)
        carril.setAutoFillBackground(True)
        carril.setStyleSheet(f"QWidget#hondo {{ background: {idn.HONDO}; }}")
        col = QVBoxLayout(carril)
        col.setContentsMargins(0, 18, 0, 14)
        col.setSpacing(4)

        marca = QVBoxLayout()
        marca.setContentsMargins(16, 0, 16, 14)
        marca.setSpacing(2)
        titulo = Rotulo("sidebflms", px=11, acento=True)
        marca.addWidget(titulo)
        sub = Rotulo("color")
        marca.addWidget(sub)
        col.addLayout(marca)
        col.addWidget(separador())
        col.addSpacing(8)

        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        for i, (_, etiqueta) in enumerate(PANTALLAS):
            b = QPushButton(etiqueta)
            b.setObjectName("navegacion")
            # En MAYUSCULAS con el tracking de marca. QSS no tiene
            # `text-transform`, asi que la unica forma es la fuente.
            b.setFont(idn.fuente_rotulo(10))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.grupo.addButton(b, i)
            col.addWidget(b)
        self.grupo.idClicked.connect(self.ir_a)
        col.addStretch(1)

        # En dos lineas y NO elidida. Esta es la promesa de la app -- que no
        # toca el grado de nadie -- y salia cortada como «escribe en «SIDEB
        # COL...» incluso a 1440 de ancho, porque el carril mide 186 px. Cortar
        # justo el nombre de la version deja la frase diciendo la mitad de lo
        # que tiene que decir.
        nota = QLabel(f"escribe en\n«{VERSION_NAME}»")
        nota.setObjectName("tenue")
        nota.setFont(idn.fuente_texto(10))
        nota.setWordWrap(True)
        nota.setContentsMargins(16, 0, 16, 0)
        col.addWidget(nota)
        return carril

    def _cabecera(self) -> QWidget:
        cab = QWidget()
        fila = QHBoxLayout(cab)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(14)
        self.titulo_pantalla = Rotulo(PANTALLAS[0][1], px=11, acento=True)
        fila.addWidget(self.titulo_pantalla, 0)
        self.sub_pantalla = EtiquetaElidida("", ancho_minimo_px=60)
        self.sub_pantalla.setObjectName("apagado")
        self.sub_pantalla.setFont(idn.fuente_texto(12))
        fila.addWidget(self.sub_pantalla, 1)
        return cab

    def _pie(self) -> QWidget:
        pie = QWidget()
        fila = QHBoxLayout(pie)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(14)
        self.estado_resolve = Rotulo("resolve")
        fila.addWidget(self.estado_resolve, 0)
        self.detalle_resolve = EtiquetaElidida("", ancho_minimo_px=60)
        self.detalle_resolve.setObjectName("tenue")
        self.detalle_resolve.setFont(idn.fuente_texto(11))
        fila.addWidget(self.detalle_resolve, 1)
        self.cifra_clips = Cifra("", px=11)
        self.cifra_clips.setObjectName("apagado")
        fila.addWidget(self.cifra_clips, 0)
        return pie

    # -- estado ------------------------------------------------------------

    def ir_a(self, indice: int) -> None:
        indice = max(0, min(len(PANTALLAS) - 1, int(indice)))
        self.pila.setCurrentIndex(indice)
        boton = self.grupo.button(indice)
        if boton is not None:
            boton.setChecked(True)
        self.titulo_pantalla.setText(PANTALLAS[indice][1])
        self.sub_pantalla.setText(
            (
                "la nota de cada clip y por qué la tiene",
                "la cortinilla pone los dos planos en contacto, que es donde se ve una "
                "diferencia de color pequeña",
                f"nada se escribe fuera de la versión «{VERSION_NAME}»",
                "cuánto del grado cabe en un .cube y qué parte no es un LUT",
            )[indice]
        )

    def _refrescar_pie(self) -> None:
        try:
            conectado = self._estado.puente.is_connected()
        except ResolveError:
            conectado = False
        if conectado:
            info = self._estado.puente.project_info()
            self.estado_resolve.setText("resolve conectado")
            self.detalle_resolve.setText(
                f"{info.name} · {info.timeline_name} · {info.color_science} · LUTs en {info.lut_dir}"
            )
        else:
            self.estado_resolve.setText("resolve desconectado")
            self.detalle_resolve.setText(
                "no hay conexión; se puede mirar todo, pero no se escribe nada"
            )
        n = len(self._estado.clips)
        self.cifra_clips.setText(f"{n:d} clip" if n == 1 else f"{n:d} clips")

    # -- anchura minima ----------------------------------------------------

    def anchura_minima(self) -> int:
        """La anchura minima REAL, con los hints de los hijos ya calculados."""
        self.ensurePolished()
        for w in self.findChildren(QWidget):
            w.ensurePolished()
        QApplication.processEvents()
        return max(
            self.minimumSizeHint().width(),
            self.minimumWidth(),
        )


def crear_app(argv: list[str] | None = None) -> QApplication:
    """`QApplication` con la hoja de estilo y la fuente base ya puestas."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    app.setApplicationName(TITULO)
    app.setFont(idn.fuente_texto(13))
    app.setStyleSheet(idn.hoja_de_estilo())
    return app


__all__ = ["ANCHO_CARRIL", "PANTALLAS", "TITULO", "VentanaPrincipal", "crear_app"]
