"""Pantalla 4 — ingenieria inversa de un grado.

Par original/coloreado -> el grado recuperado, **en dos capas**, mas el mapa de
cobertura y el diagnostico.

LAS CUATRO COSAS QUE ENSENA, Y POR QUE ESTAN ASI
------------------------------------------------
1. **El CDL con sus diez numeros, legibles y editables.** Editables porque un
   grado recuperado es un punto de partida, no un veredicto: el colorista mira
   el `slope` del azul, ve que se ha pasado, y lo baja. Cada campo es
   monoespaciado (identidad) y al tocarlo se repinta la tira de parches, para
   que el numero y lo que hace se vean a la vez.
2. **El LUT, con su QC de verdad.** `core.io.qc_lut` sobre el LUT que ha salido.
   Si tiene problemas, se listan con su mensaje; no se esconde ninguno.
3. **El mapa de cobertura**, que es lo que contesta «¿de donde ha salido esto?».
   Celda con datos reales = parche relleno; celda inventada = tablero de ajedrez
   oscuro. **La diferencia es de textura, no de color**: se lee en blanco y
   negro y no toma prestado ningun token del inventario.
4. **El diagnostico**: cuanto del grado cabe en un `.cube`, si es un LUT puro, y
   el mapa de residuo espacial con sus zonas calientes. Esto es lo que dice si
   habia una ventana o una vineta, que es lo que un `.cube` **no** se lleva.

SI `core.reverse` NO ESTA, O FALLA
----------------------------------
El panel se dibuja igual. `gui.reverse_puente` protege el import y, si hace
falta, calcula un sustituto; la pantalla pone por escrito quien ha calculado lo
que se esta viendo. Ver el docstring de `gui/reverse_puente.py`.

**Y entonces la pantalla NO dice si el grado es un LUT puro.** Ese veredicto lo
da `core.reverse` y aqui solo se pinta. Si no lo ha dado el nucleo, lo que se
escribe es «no se ha podido decidir», y se ensena ademas un aviso de que lo que
hay delante lo ha calculado un sustituto. El motivo esta en `gui/NOTAS.md`: la
frase «es un LUT puro» es la mas peligrosa que puede decir esta app, porque
manda a Mario a llevarse un `.cube` que no reproduce el grado y a enterarse
delante de un cliente. Si hay que equivocarse, se hace hacia «no lo se» o hacia
«no es puro», que solo hacen trabajar de mas.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QLocale, QRect, Qt
from PySide6.QtGui import QBrush, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.contracts import CDL, LUT_SIZES_SOPORTADOS, CoverageMap, ReverseResult
from core.io import qc_lut
from gui import identidad as idn
from gui.imagen import a_qimage, tira_de_color
from gui.reverse_puente import SIN_VEREDICTO, TAM_REJILLA_PANEL, Inversion, invertir
from gui.widgets import (
    BarraProporcion,
    Cifra,
    EtiquetaElidida,
    InsigniaConfianza,
    Panel,
    Rotulo,
    separador,
)

#: Cuantos cortes del cubo se ensenan en el montaje. Ocho es lo que cabe en dos
#: filas de cuatro a 1024 px sin que la celda baje de 4 px, que es donde deja de
#: distinguirse el tablero de ajedrez del relleno.
CORTES_MONTAJE = 8


# ---------------------------------------------------------------------------
# El mapa de cobertura
# ---------------------------------------------------------------------------


def montaje_cobertura(cobertura: CoverageMap, *, cortes: int = CORTES_MONTAJE,
                      columnas: int = 4, hueco: int = 6) -> QImage:
    """Cortes del cubo a lo largo del eje AZUL, en una rejilla.

    Dentro de cada corte: el eje horizontal es el ROJO y el vertical el VERDE
    (creciendo hacia arriba, como en un vectorscopio y no como en una matriz).
    Relleno = celdas con muestras reales; tablero de ajedrez = celdas
    inventadas.
    """
    n = cobertura.size
    counts = np.asarray(cobertura.counts)
    mask = cobertura.covered_mask()
    indices = np.unique(np.linspace(0, n - 1, min(cortes, n)).round().astype(int))
    filas = int(np.ceil(len(indices) / columnas))

    alto = filas * n + (filas - 1) * hueco
    ancho = min(columnas, len(indices)) * n + (min(columnas, len(indices)) - 1) * hueco
    lienzo = np.zeros((max(alto, 1), max(ancho, 1), 3), dtype=np.uint8)
    lienzo[:, :] = _rgb(idn.FONDO)

    tope = float(np.log1p(counts.max())) if counts.max() > 0 else 1.0
    marca = np.array(_rgb(idn.BRAND_400), dtype=np.float64)
    ajedrez_a = np.array(_rgb(idn.HONDO), dtype=np.uint8)
    ajedrez_b = np.array(_rgb(idn.PANEL), dtype=np.uint8)

    ri, gi = np.mgrid[0:n, 0:n]
    tablero = ((ri + gi) % 2 == 0)

    for k, b in enumerate(indices):
        corte_counts = counts[:, :, b].T[::-1]  # (verde, rojo), verde hacia arriba
        corte_mask = mask[:, :, b].T[::-1]
        celda = np.where(tablero[..., None], ajedrez_a, ajedrez_b).astype(np.uint8)
        if corte_mask.any():
            t = (np.log1p(corte_counts) / tope)[..., None]
            relleno = (marca * (0.30 + 0.70 * np.clip(t, 0.0, 1.0))).astype(np.uint8)
            celda = np.where(corte_mask[..., None], relleno, celda)
        fila, col = divmod(k, columnas)
        y, x = fila * (n + hueco), col * (n + hueco)
        lienzo[y : y + n, x : x + n] = celda

    datos = np.ascontiguousarray(lienzo)
    img = QImage(datos.data, datos.shape[1], datos.shape[0], 3 * datos.shape[1],
                 QImage.Format.Format_RGB888)
    return img.copy()


def _rgb(hex_color: str) -> tuple[int, int, int]:
    c = idn.color(hex_color)
    return (c.red(), c.green(), c.blue())


class VistaMapa(QWidget):
    """Pinta un `QImage` a pixel gordo (sin suavizar) y centrado."""

    def __init__(self, *, alto_minimo: int = 150, parent=None) -> None:
        super().__init__(parent)
        self._img: QImage | None = None
        self._vacio = "sin datos"
        self.setMinimumHeight(alto_minimo)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def poner(self, img: QImage | None, *, vacio: str = "sin datos") -> None:
        self._img, self._vacio = img, vacio
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QBrush(idn.color(idn.HONDO)))
        if self._img is None or self._img.isNull():
            p.setPen(QPen(idn.color(idn.BRAND_50, idn.TEXTO_TENUE_A)))
            p.setFont(idn.fuente_texto(12))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._vacio)
            p.end()
            return
        disp = self.rect().adjusted(4, 4, -4, -4)
        w, h = self._img.width(), self._img.height()
        escala = min(disp.width() / w, disp.height() / h)
        ancho, alto = max(1, int(w * escala)), max(1, int(h * escala))
        caja = QRect(disp.left() + (disp.width() - ancho) // 2,
                     disp.top() + (disp.height() - alto) // 2, ancho, alto)
        # Sin suavizado: una celda del cubo es una celda, no un degradado.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(caja, self._img)
        p.end()


def mapa_de_residuo(residuo: np.ndarray | None) -> QImage | None:
    """El residuo espacial normalizado, en una rampa de MARCA.

    De `fondo` a `brand-600`, `brand-500`, `brand-400` y `brand-50`. Es una
    rampa monocroma de la familia: lo que cambia es la luminosidad, no el tono,
    asi que no hay ningun semaforo escondido aqui.
    """
    if residuo is None:
        return None
    r = np.clip(np.nan_to_num(np.asarray(residuo, dtype=np.float64)), 0.0, 1.0)
    paradas = np.array(
        [_rgb(idn.FONDO), _rgb(idn.BRAND_600), _rgb(idn.BRAND_500),
         _rgb(idn.BRAND_400), _rgb(idn.BRAND_50)],
        dtype=np.float64,
    )
    pos = np.linspace(0.0, 1.0, len(paradas))
    salida = np.stack([np.interp(r, pos, paradas[:, k]) for k in range(3)], axis=-1)
    datos = np.ascontiguousarray(salida.astype(np.uint8))
    img = QImage(datos.data, datos.shape[1], datos.shape[0], 3 * datos.shape[1],
                 QImage.Format.Format_RGB888)
    return img.copy()


# ---------------------------------------------------------------------------
# El editor de los diez numeros
# ---------------------------------------------------------------------------


class EditorCDL(QWidget):
    """Los diez numeros del CDL, legibles y editables. Todos monoespaciados."""

    LIMITES = {
        "slope": (0.0, 10.0),
        "offset": (-1.0, 1.0),
        "power": (0.01, 10.0),  # power > 0 o el contrato lanza
        "sat": (0.0, 4.0),
    }

    def __init__(self, al_cambiar, parent=None) -> None:
        super().__init__(parent)
        self._al_cambiar = al_cambiar
        self._original = CDL()
        self._mostrado = CDL()
        self._campos: dict[str, QDoubleSpinBox] = {}
        rejilla = QGridLayout(self)
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setHorizontalSpacing(8)
        rejilla.setVerticalSpacing(6)

        rejilla.addWidget(QLabel(""), 0, 0)
        for c, canal in enumerate("RGB"):
            e = Cifra(canal, px=11)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setObjectName("apagado")
            rejilla.addWidget(e, 0, c + 1)

        # Los cuatro rotulos de la izquierda NO pueden recortarse: el sentido de
        # este panel es que los diez numeros del CDL se lean y se toquen, y
        # «SLO...» / «PO...» no se lee. A la anchura minima de la ventana salian
        # asi, y estaba en la captura. Se le da a la columna 0 el ancho que de
        # verdad necesita el mas largo, medido, no a ojo.
        #
        # «saturación» se acorta a «sat» a proposito y no por falta de sitio:
        # con la palabra entera esta columna se come 30 px que a 966 de ancho
        # le hacen falta a los campos. «SAT» es como viene rotulado en
        # cualquier panel de CDL, asi que no se pierde nada.
        rotulos = [Rotulo(t) for t in ("slope", "offset", "power", "sat")]
        for f, r in enumerate(rotulos):
            rejilla.addWidget(r, f + 1, 0)
        rejilla.setColumnMinimumWidth(0, max(r.sizeHint().width() for r in rotulos) + 4)

        for f, grupo in enumerate(("slope", "offset", "power")):
            for c, canal in enumerate("rgb"):
                campo = self._campo(grupo)
                self._campos[f"{grupo}_{canal}"] = campo
                rejilla.addWidget(campo, f + 1, c + 1)
        campo = self._campo("sat")
        self._campos["sat"] = campo
        rejilla.addWidget(campo, 4, 1)
        rejilla.setColumnStretch(1, 1)
        rejilla.setColumnStretch(2, 1)
        rejilla.setColumnStretch(3, 1)

    def _campo(self, grupo: str) -> QDoubleSpinBox:
        campo = QDoubleSpinBox()
        campo.setDecimals(4)
        campo.setSingleStep(0.01)
        campo.setRange(*self.LIMITES[grupo])
        campo.setFont(idn.fuente_cifra(12))
        campo.setMinimumWidth(78)
        campo.setAlignment(Qt.AlignmentFlag.AlignRight)
        campo.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        # Punto decimal y no coma. La configuracion regional de este Mac es
        # espanola y Qt escribia «1,1510»; pero un CDL se lee y se escribe con
        # punto en los .cc, los .cdl y los .cube, y el resto de la app lo pinta
        # con punto. Dos notaciones en la misma pantalla es una invitacion a
        # teclear mal un numero.
        campo.setLocale(QLocale(QLocale.Language.C))
        campo.valueChanged.connect(lambda _: self._al_cambiar())
        return campo

    def poner(self, cdl: CDL) -> None:
        self._original = cdl
        for campo in self._campos.values():
            campo.blockSignals(True)
        for i, canal in enumerate("rgb"):
            self._campos[f"slope_{canal}"].setValue(cdl.slope[i])
            self._campos[f"offset_{canal}"].setValue(cdl.offset[i])
            self._campos[f"power_{canal}"].setValue(cdl.power[i])
        self._campos["sat"].setValue(cdl.saturation)
        for campo in self._campos.values():
            campo.blockSignals(False)
        # Lo que se compara para decidir si esta «editado» es esto y no el CDL
        # que llego: los campos tienen 4 decimales, asi que un CDL recuperado
        # con 1.1509876... se ensena como 1.1510 y salia marcado como editado
        # nada mas abrir la pantalla. Se veia en la primera captura.
        self._mostrado = self.cdl()
        self._al_cambiar()

    def restaurar(self) -> None:
        self.poner(self._original)

    def original(self) -> CDL:
        return self._original

    def cdl(self) -> CDL:
        """El CDL tal y como esta en los campos. `power` nunca llega a 0."""
        v = {k: campo.value() for k, campo in self._campos.items()}
        return CDL(
            slope=(v["slope_r"], v["slope_g"], v["slope_b"]),
            offset=(v["offset_r"], v["offset_g"], v["offset_b"]),
            power=(max(v["power_r"], 1e-6), max(v["power_g"], 1e-6), max(v["power_b"], 1e-6)),
            saturation=v["sat"],
        )

    def editado(self) -> bool:
        a, b = self.cdl(), self._mostrado
        return not (
            np.allclose(a.slope, b.slope, atol=1e-9)
            and np.allclose(a.offset, b.offset, atol=1e-9)
            and np.allclose(a.power, b.power, atol=1e-9)
            and abs(a.saturation - b.saturation) < 1e-9
        )


class TiraParches(QWidget):
    """Una tira de parches. Para ver que hace el CDL sin mirar un numero."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._img: QImage | None = None
        self.setFixedHeight(26)
        self.setMinimumWidth(80)

    def poner(self, img: QImage) -> None:
        self._img = img
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        if self._img is not None:
            p.drawImage(self.rect(), self._img)
        p.setPen(QPen(idn.color(idn.BRAND_50, idn.BORDE_A), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------


class PantallaReverse(QWidget):
    """El panel entero. Si `core.reverse` no esta, se dibuja igual y lo dice."""

    def __init__(self, original: np.ndarray | None, coloreado: np.ndarray | None,
                 *, parches: np.ndarray | None = None, parent=None) -> None:
        super().__init__(parent)
        self._original = original
        self._coloreado = coloreado
        self._parches = parches
        self._resultado: ReverseResult | None = None
        self._inversion: Inversion | None = None
        self._origen = ""

        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)
        caja.addWidget(self._cabecera())

        self.division = QSplitter(Qt.Orientation.Horizontal)
        self.division.setChildrenCollapsible(False)
        self.division.setHandleWidth(12)
        self.division.addWidget(self._columna_capas())
        self.division.addWidget(self._columna_cobertura())
        self.division.setStretchFactor(0, 2)
        self.division.setStretchFactor(1, 3)
        self.division.setSizes([420, 700])
        caja.addWidget(self.division, 1)

        # Dos avisos distintos y que NO se confunden:
        #
        # * `aviso_sustituto`: hay resultado, pero NO lo ha calculado
        #   `core.reverse`. Se puede trabajar con los numeros, pero el veredicto
        #   de «es un LUT puro» no se ha emitido y no se pinta. Tiene que verse:
        #   caerse a un sustituto esta bien, caerse en silencio no.
        # * `aviso_no_disponible`: no hay resultado ninguno. La pantalla se
        #   apaga y dice por que.
        self.aviso_sustituto = Panel(cristal=True, margenes=(14, 10, 14, 10))
        self.aviso_sustituto.caja.addWidget(
            Rotulo("esto no lo ha calculado core.reverse", acento=True)
        )
        self.texto_sustituto = QLabel("")
        self.texto_sustituto.setWordWrap(True)
        self.texto_sustituto.setMinimumWidth(0)
        self.texto_sustituto.setStyleSheet(f"color: {idn.BRAND_400};")
        self.aviso_sustituto.caja.addWidget(self.texto_sustituto)
        caja.addWidget(self.aviso_sustituto)
        self.aviso_sustituto.setVisible(False)

        self.aviso_no_disponible = Panel(cristal=True)
        self.aviso_no_disponible.caja.addWidget(Rotulo("módulo no disponible", acento=True))
        self.texto_no_disponible = QLabel("")
        self.texto_no_disponible.setWordWrap(True)
        self.texto_no_disponible.setMinimumWidth(0)
        self.aviso_no_disponible.caja.addWidget(self.texto_no_disponible)
        caja.addWidget(self.aviso_no_disponible)
        self.aviso_no_disponible.setVisible(False)

        self.recalcular()

    # -- construccion ------------------------------------------------------

    def _cabecera(self) -> QWidget:
        panel = Panel(cristal=True, margenes=(14, 10, 14, 10))
        fila = QHBoxLayout()
        fila.setSpacing(14)
        fila.addWidget(Rotulo("grado recuperado de", acento=True), 0)
        self.origen_texto = EtiquetaElidida("—", ancho_minimo_px=80)
        self.origen_texto.setFont(idn.fuente_texto(12))
        fila.addWidget(self.origen_texto, 1)
        fila.addWidget(Rotulo("rejilla"), 0)
        self.selector_tam = QComboBox()
        self.selector_tam.setFont(idn.fuente_cifra(12))
        for tam in LUT_SIZES_SOPORTADOS:
            self.selector_tam.addItem(f"{tam}³", tam)
        self.selector_tam.setCurrentIndex(
            list(LUT_SIZES_SOPORTADOS).index(TAM_REJILLA_PANEL)
            if TAM_REJILLA_PANEL in LUT_SIZES_SOPORTADOS
            else 0
        )
        self.selector_tam.setFixedWidth(84)
        fila.addWidget(self.selector_tam, 0)
        self.btn_recalcular = QPushButton("Recalcular")
        self.btn_recalcular.clicked.connect(self.recalcular)
        fila.addWidget(self.btn_recalcular, 0)
        self.insignia = InsigniaConfianza(idn.FormaConfianza.ALTA, 0.0)
        fila.addWidget(self.insignia, 0)
        panel.caja.addLayout(fila)
        return panel

    def _columna_capas(self) -> QWidget:
        envoltorio = QScrollArea()
        envoltorio.setWidgetResizable(True)
        envoltorio.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        envoltorio.setMinimumWidth(320)
        dentro = QWidget()
        col = QVBoxLayout(dentro)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)

        # --- par original / coloreado ---
        panel_par = Panel(margenes=(12, 12, 12, 12))
        panel_par.caja.addWidget(Rotulo("el par", acento=True))
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.mini_original = _MiniPar("original")
        self.mini_coloreado = _MiniPar("coloreado")
        fila.addWidget(self.mini_original, 1)
        fila.addWidget(self.mini_coloreado, 1)
        panel_par.caja.addLayout(fila)
        col.addWidget(panel_par)

        # --- capa 1: CDL ---
        panel_cdl = Panel(margenes=(12, 12, 12, 12))
        cab = QHBoxLayout()
        cab.addWidget(Rotulo("capa 1 · cdl (nodo 2)", acento=True), 1)
        self.marca_editado = Rotulo("editado")
        self.marca_editado.setVisible(False)
        cab.addWidget(self.marca_editado, 0)
        panel_cdl.caja.addLayout(cab)
        self.editor = EditorCDL(self._cdl_cambiado)
        panel_cdl.caja.addWidget(self.editor)
        panel_cdl.caja.addWidget(separador())
        panel_cdl.caja.addWidget(Rotulo("parches · original / con el cdl"))
        self.tira_origen = TiraParches()
        self.tira_cdl = TiraParches()
        panel_cdl.caja.addWidget(self.tira_origen)
        panel_cdl.caja.addWidget(self.tira_cdl)
        pie = QHBoxLayout()
        pie.addStretch(1)
        self.btn_restaurar = QPushButton("Restaurar el recuperado")
        self.btn_restaurar.clicked.connect(self.editor.restaurar)
        pie.addWidget(self.btn_restaurar)
        panel_cdl.caja.addLayout(pie)
        col.addWidget(panel_cdl)

        # --- capa 2: LUT ---
        panel_lut = Panel(margenes=(12, 12, 12, 12))
        panel_lut.caja.addWidget(Rotulo("capa 2 · lut (nodo 3)", acento=True))
        # Igual que el CDL de «antes/despues»: con `setFont(fuente_cifra(12))`
        # salia en Inter, porque la hoja de estilo pisa a `setFont()`. El id
        # `cifraApagada` es el que trae la monoespaciada de verdad.
        self.datos_lut = QLabel("—")
        self.datos_lut.setObjectName("cifraApagada")
        self.datos_lut.setMinimumWidth(0)
        self.datos_lut.setWordWrap(True)
        panel_lut.caja.addWidget(self.datos_lut)
        panel_lut.caja.addWidget(separador())
        panel_lut.caja.addWidget(Rotulo("control de calidad del lut"))
        self.texto_qc = QLabel("—")
        self.texto_qc.setWordWrap(True)
        self.texto_qc.setMinimumWidth(0)
        panel_lut.caja.addWidget(self.texto_qc)
        col.addWidget(panel_lut)

        col.addStretch(1)
        envoltorio.setWidget(dentro)
        # La anchura minima se PREGUNTA al contenido. Antes estaba puesta a ojo
        # en 320 y la rejilla del CDL necesita 380: a 908 px la columna B de los
        # campos se salia del panel y no habia barra que lo dijera, porque la
        # barra horizontal esta apagada. Ahora la anchura minima de la ventana
        # crece lo que haga falta y no se corta nada.
        envoltorio.setMinimumWidth(dentro.minimumSizeHint().width() + 16)
        return envoltorio

    def _columna_cobertura(self) -> QWidget:
        envoltorio = QWidget()
        # Sin `setMinimumWidth(300)`. Ese 300 estaba puesto a ojo y se quedaba
        # corto: la columna necesita 366 px para que quepan los cuatro rotulos
        # del diagnostico («cabe en un .cube», «ΔE medio», «ΔE p95», «ΔE peor»)
        # en la misma fila. Con el 300, la ventana se podia encoger hasta 911
        # px con el timeline vacio y ahi salian «cabe en …», «mapa de cobertu…»
        # y «residuo espaci…». Ahora la anchura minima la calcula Qt a partir
        # del contenido, que es lo que ya hace la columna de al lado.
        col = QVBoxLayout(envoltorio)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)

        panel_cob = Panel(margenes=(12, 12, 12, 12))
        cab = QHBoxLayout()
        cab.addWidget(Rotulo("mapa de cobertura", acento=True), 1)
        self.cifra_cobertura = Cifra("—", px=13)
        cab.addWidget(self.cifra_cobertura, 0)
        panel_cob.caja.addLayout(cab)
        self.leyenda = QLabel(
            "Relleno = celdas medidas de verdad.   "
            "Tablero de ajedrez = celdas inventadas (las rellena el módulo, "
            "no las ha visto nadie).   Cortes a lo largo del azul; dentro de "
            "cada corte, horizontal = rojo, vertical = verde."
        )
        self.leyenda.setWordWrap(True)
        self.leyenda.setObjectName("tenue")
        self.leyenda.setMinimumWidth(0)
        self.leyenda.setFont(idn.fuente_texto(11))
        panel_cob.caja.addWidget(self.leyenda)
        self.vista_cobertura = VistaMapa(alto_minimo=170)
        panel_cob.caja.addWidget(self.vista_cobertura, 1)
        col.addWidget(panel_cob, 3)

        panel_diag = Panel(margenes=(12, 12, 12, 12))
        panel_diag.caja.addWidget(Rotulo("diagnóstico", acento=True))
        fila = QHBoxLayout()
        fila.setSpacing(18)
        bloque = QVBoxLayout()
        bloque.setSpacing(2)
        bloque.addWidget(Rotulo("cabe en un .cube"))
        self.cifra_repro = Cifra("—", px=26, peso=QFont.Weight.DemiBold)
        bloque.addWidget(self.cifra_repro)
        self.barra_repro = BarraProporcion(0.0)
        bloque.addWidget(self.barra_repro)
        fila.addLayout(bloque, 1)
        for clave, rotulo in (("media", "ΔE medio"), ("p95", "ΔE p95"), ("max", "ΔE peor")):
            b = QVBoxLayout()
            b.setSpacing(2)
            b.addWidget(Rotulo(rotulo))
            etq = Cifra("—", px=18, peso=QFont.Weight.DemiBold, secundario=(clave != "media"))
            setattr(self, f"_de_{clave}", etq)
            b.addWidget(etq)
            b.addStretch(1)
            fila.addLayout(b, 0)
        panel_diag.caja.addLayout(fila)
        panel_diag.caja.addWidget(separador())

        fila2 = QHBoxLayout()
        fila2.setSpacing(12)
        izq = QVBoxLayout()
        izq.setSpacing(4)
        izq.addWidget(Rotulo("qué NO es un lut"))
        # QTextBrowser: el diagnostico de `core.reverse` son varios parrafos
        # largos y un QLabel se come en silencio todo lo que no le cabe. Aqui
        # aparece una barra y se lee entero.
        self.texto_diag = QTextBrowser()
        self.texto_diag.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.texto_diag.setMinimumWidth(0)
        self.texto_diag.setMinimumHeight(80)
        izq.addWidget(self.texto_diag, 1)
        fila2.addLayout(izq, 3)
        der = QVBoxLayout()
        der.setSpacing(4)
        # «en el fotograma» se recortaba a la anchura minima. «residuo espacial»
        # dice lo mismo, cabe, y ademas es el nombre del campo del contrato
        # (`ReverseDiagnosis.spatial_residual`), asi que une los dos vocabularios.
        der.addWidget(Rotulo("residuo espacial"))
        self.vista_residuo = VistaMapa(alto_minimo=110)
        der.addWidget(self.vista_residuo, 1)
        fila2.addLayout(der, 2)
        panel_diag.caja.addLayout(fila2, 1)
        col.addWidget(panel_diag, 2)
        return envoltorio

    # -- calculo -----------------------------------------------------------

    def recalcular(self) -> None:
        if self._original is None or self._coloreado is None:
            self._sin_par()
            return
        tam = self.selector_tam.currentData() or TAM_REJILLA_PANEL
        try:
            inversion = invertir(self._original, self._coloreado, tam_lut=int(tam))
        except Exception as exc:  # el modulo de otro puede lanzar lo que sea
            self._sin_modulo(f"la inversión ha fallado: {exc!r}")
            return
        self._inversion = inversion
        self._resultado, self._origen = inversion.resultado, inversion.origen
        self._pintar()

    def resultado(self) -> ReverseResult | None:
        return self._resultado

    def origen(self) -> str:
        return self._origen

    def inversion(self) -> Inversion | None:
        """La inversion entera, con quien la ha calculado. Para los tests."""
        return self._inversion

    def veredicto_fiable(self) -> bool:
        """¿Se puede pintar `is_pure_lut` como el veredicto de la app?

        Solo si lo ha dado `core.reverse`. Si no, la pantalla dice que no lo
        sabe; no lo decide ella, y menos hacia el lado optimista.
        """
        return self._inversion is not None and self._inversion.veredicto_fiable

    def _sin_par(self) -> None:
        self._sin_modulo("No hay par original/coloreado que invertir.")

    def _sin_modulo(self, motivo: str) -> None:
        self._inversion = None
        self._resultado = None
        self.aviso_sustituto.setVisible(False)
        self.aviso_no_disponible.setVisible(True)
        self.texto_no_disponible.setText(
            f"{motivo}\n\nEl resto de la aplicación sigue funcionando: esta pantalla es la "
            f"única que necesita core.reverse."
        )
        self.division.setEnabled(False)
        self.insignia.setVisible(False)
        self.origen_texto.setText("no disponible")
        self.texto_diag.setPlainText(SIN_VEREDICTO)

    def _pintar(self) -> None:
        res = self._resultado
        assert res is not None
        fiable = self.veredicto_fiable()
        self.aviso_no_disponible.setVisible(False)
        self.aviso_sustituto.setVisible(not fiable)
        if not fiable:
            fallo = self._inversion.fallo if self._inversion is not None else ""
            self.texto_sustituto.setText(
                f"Lo que se ve aquí lo ha calculado el sustituto de la GUI. {fallo}\n"
                f"Los números son medidos y sirven para trabajar, pero el veredicto de "
                f"«es un LUT puro» NO se ha emitido: ese lo da sólo core.reverse, y hasta "
                f"que conteste la pantalla dice que no lo sabe."
            )
        self.division.setEnabled(True)
        self.insignia.setVisible(True)
        self.origen_texto.setText(self._origen)
        self.insignia.actualizar(
            idn.FormaConfianza.de_nivel(res.confidence.level), res.confidence.score
        )

        if self._original is not None:
            self.mini_original.poner(a_qimage(self._original))
        if self._coloreado is not None:
            self.mini_coloreado.poner(a_qimage(self._coloreado))

        self.editor.poner(res.cdl)

        lut = res.lut
        self.datos_lut.setText(
            f"{lut.size}³ = {lut.size ** 3:,} celdas\n"
            f"dominio {lut.domain_min[0]:.2f}–{lut.domain_max[0]:.2f}\n"
            f"título: {lut.title}".replace(",", ".")
        )
        informe = qc_lut(lut)
        if informe.ok:
            self.texto_qc.setText(informe.resumen())
            self.texto_qc.setStyleSheet("")
        else:
            lineas = [informe.resumen()]
            lineas += [f"· {p.mensaje}" for p in informe.problemas[:6]]
            if len(informe.problemas) > 6:
                lineas.append(f"· … y {len(informe.problemas) - 6} más")
            self.texto_qc.setText("\n".join(lineas))
            self.texto_qc.setStyleSheet(f"color: {idn.BRAND_400};")

        cob = res.coverage
        fraccion = cob.coverage_fraction()
        celdas = int(cob.covered_mask().sum())
        self.cifra_cobertura.setText(
            f"{celdas:,}".replace(",", ".") + f" / {cob.size ** 3:,}".replace(",", ".")
            + f"  ·  {fraccion * 100:.2f} %"
        )
        self.vista_cobertura.poner(montaje_cobertura(cob),
                                   vacio="ni una celda con datos reales")

        diag = res.diagnosis
        self.cifra_repro.setText(f"{diag.lut_reproducible * 100:.1f} %")
        self.barra_repro.set_valor(diag.lut_reproducible)
        self._de_media.setText(f"{res.delta_e_mean:.2f}")
        self._de_p95.setText(f"{res.delta_e_p95:.2f}")
        self._de_max.setText(f"{res.delta_e_max:.2f}")

        # El veredicto se PINTA, no se decide. Y si no lo ha dado el nucleo, lo
        # que se escribe es «no se ha podido decidir», que no es lo mismo que
        # «no es un LUT puro» ni, sobre todo, que «es un LUT puro». Decir «es
        # un LUT» cuando no lo es manda a Mario a llevarse un .cube que no
        # reproduce el grado; decir «no lo se» solo le hace mirarlo.
        lineas = []
        if not fiable:
            lineas.append(SIN_VEREDICTO)
        else:
            lineas.append(
                "Es un LUT puro: todo el grado cabe en el .cube."
                if diag.is_pure_lut
                else "NO es un LUT puro: queda algo que depende de dónde está el píxel."
            )
        lineas += [f"· {n}" for n in diag.notes]
        for h in diag.hotspots:
            lineas.append(
                f"· {h.label} en ({h.x}, {h.y}) {h.w}×{h.h} px — {h.magnitude:.2f} ΔE"
            )
        lineas += [f"· {n}" for n in res.notes]
        self.texto_diag.setPlainText("\n".join(lineas))
        self.vista_residuo.poner(mapa_de_residuo(diag.spatial_residual),
                                 vacio="sin mapa de residuo")

    def _cdl_cambiado(self) -> None:
        self.marca_editado.setVisible(self.editor.editado())
        parches = self._parches
        if parches is None:
            return
        self.tira_origen.poner(tira_de_color(parches))
        self.tira_cdl.poner(tira_de_color(self.editor.cdl().apply(parches).astype(np.float32)))


class _MiniPar(QWidget):
    """Una imagen del par con su rotulo debajo."""

    def __init__(self, rotulo: str, parent=None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self.vista = VistaMapa(alto_minimo=96)
        col.addWidget(self.vista, 1)
        r = Rotulo(rotulo)
        r.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(r)

    def poner(self, img: QImage) -> None:
        self.vista.poner(img)


__all__ = [
    "CORTES_MONTAJE",
    "EditorCDL",
    "PantallaReverse",
    "TiraParches",
    "VistaMapa",
    "mapa_de_residuo",
    "montaje_cobertura",
]
