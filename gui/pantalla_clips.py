"""Pantalla 1 — la lista de clips con su confianza.

LO QUE HAY QUE MIRAR AQUI
-------------------------
* **La confianza se diferencia por FORMA.** La columna CONFIANZA la pinta
  `DelegadoConfianza`, que llama al mismo `pintar_insignia_confianza` que usa la
  ficha de detalle. Relleno solido = alta, contorno = media, contorno
  discontinuo = baja. Ni un semaforo, ni un token del inventario.
* **Las razones se ensenan tal cual.** `Confidence.reasons` viene en castellano
  y ordenado por importancia desde `core.matching`, escrito para que lo lea
  Mario. Aqui no se reescribe, no se recorta y no se traduce: se pone.
* **El desajuste de contenido se ve aunque la confianza salga alta.** Es lo que
  dice CONTRATOS.md de `MatchResult.content_mismatch`, y por eso el aviso es una
  columna propia y un bloque propio en el detalle, no una nota al pie de la
  confianza. La marca es un rombo naranja de marca; **no es roja**, porque es un
  aviso y no una accion destructiva.
* **Toda cifra va en monoespaciada**: los dos ΔE, el porcentaje de la insignia y
  el identificador del clip.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui import identidad as idn
from gui.datos_demo import ClipDemo, EstadoDemo
from gui.widgets import (
    INSIGNIA_ALTO,
    INSIGNIA_ANCHO,
    Cifra,
    EtiquetaElidida,
    InsigniaConfianza,
    MarcaDesajuste,
    Panel,
    Rotulo,
    pintar_insignia_confianza,
    separador,
)

COL_INDICE, COL_NOMBRE, COL_ANTES, COL_DESPUES, COL_CONFIANZA, COL_AVISO = range(6)
#: En MAYUSCULAS aqui y no por hoja de estilo: QSS no tiene `text-transform`,
#: asi que un rotulo en minusculas se queda en minusculas y se desentona con
#: todos los demas rotulos de la app.
#: Las dos de ΔE van en DOS LINEAS, y no es un capricho de maquetacion: es lo
#: que hace que su columna quepa en lo que mide un numero. «ΔE DESPUÉS» seguido
#: mide 63 px y obliga a una columna de 83; partido, la palabra mas ancha es
#: «DESPUÉS» (47 px) y la columna baja a 67. Los 16 px de diferencia, por dos
#: columnas, son los que se lleva el nombre del clip. **No se abrevia ninguna
#: palabra**: «ΔE DESP.» habria costado lo mismo y diria menos.
#:
#: [dia 4] Y ahora en TRES lineas, con «MEDIO» en medio. Las dos cifras son
#: `MatchResult.delta_e_before` / `delta_e_after`, que son MEDIAS, y el contrato
#: no trae el maximo por clip. Rotularlas «ΔE» a secas dejaba leer un maximo
#: donde hay una media, que es la cifra holgada. En una sola linea, «ΔE MEDIO»
#: mide 49 px y ensancharia las dos columnas 8 px entre las dos, o sea la
#: ventana; en tres, la palabra mas ancha sigue siendo «DESPUÉS» y el ancho no
#: se mueve. Lo que crece es el alto de la cabecera.
CABECERAS = ("#", "CLIP", "ΔE\nMEDIO\nANTES", "ΔE\nMEDIO\nDESPUÉS", "CONFIANZA", "AVISO")

#: Papel propio para sacar el `ClipDemo` de una fila sin pasar por el texto.
ROL_CLIP = int(Qt.ItemDataRole.UserRole) + 1


class ModeloClips(QAbstractTableModel):
    """La tabla. Un modelo de verdad y no un `QTableWidget` relleno a mano:
    con doscientos clips el widget crea 1.200 celdas y el modelo ninguna."""

    def __init__(self, clips: list[ClipDemo], parent=None) -> None:
        super().__init__(parent)
        self._clips = list(clips)

    def clips(self) -> list[ClipDemo]:
        return list(self._clips)

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._clips)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(CABECERAS)

    def headerData(self, seccion, orientacion, rol=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return CABECERAS[seccion]
        return None

    def data(self, index: QModelIndex, rol=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        clip = self._clips[index.row()]
        col = index.column()
        if rol == ROL_CLIP:
            return clip
        if rol == Qt.ItemDataRole.DisplayRole:
            if col == COL_INDICE:
                return f"{clip.ref.index:03d}"
            if col == COL_NOMBRE:
                return clip.nombre
            if col == COL_ANTES:
                return f"{clip.match.delta_e_before:6.2f}"
            if col == COL_DESPUES:
                return f"{clip.match.delta_e_after:6.2f}"
            return None
        if rol == Qt.ItemDataRole.FontRole:
            if col in (COL_INDICE, COL_ANTES, COL_DESPUES):
                return idn.fuente_cifra(12)  # toda cifra, monoespaciada
            if col == COL_NOMBRE:
                return idn.fuente_texto(13)
        if rol == Qt.ItemDataRole.ForegroundRole:
            if col == COL_INDICE:
                return idn.color(idn.BRAND_50, idn.TEXTO_TENUE_A)
            if col == COL_ANTES:
                return idn.color(idn.BRAND_50, idn.TEXTO_APAGADO_A)
            if col == COL_DESPUES:
                return idn.color(idn.CYAN_GLOW)  # el dato secundario de la fila
        if rol == Qt.ItemDataRole.TextAlignmentRole and col in (COL_INDICE, COL_ANTES, COL_DESPUES):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if rol == Qt.ItemDataRole.ToolTipRole and col == COL_NOMBRE:
            return clip.nombre
        if rol == Qt.ItemDataRole.ToolTipRole and col == COL_AVISO and clip.match.content_mismatch:
            return "desajuste de contenido: las dos escenas no son comparables"
        return None


class DelegadoConfianza(QStyledItemDelegate):
    """Pinta la insignia. Mismo codigo que la ficha de detalle, a proposito."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        clip: ClipDemo = index.data(ROL_CLIP)
        self.initStyleOption(option, index)
        option.text = ""
        option.widget.style().drawControl(
            option.widget.style().ControlElement.CE_ItemViewItem, option, painter, option.widget
        )
        conf = clip.match.confidence
        forma = idn.FormaConfianza.de_nivel(conf.level)
        r = option.rect
        alto = min(INSIGNIA_ALTO, r.height() - 6)
        caja = r.adjusted(6, (r.height() - alto) // 2, 0, 0)
        caja.setWidth(min(INSIGNIA_ANCHO, r.width() - 12))
        caja.setHeight(alto)
        pintar_insignia_confianza(painter, caja, forma, conf.score)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(INSIGNIA_ANCHO + 16, INSIGNIA_ALTO + 10)


class DelegadoAviso(QStyledItemDelegate):
    """El rombo de desajuste de contenido. Vacio si no lo hay."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        clip: ClipDemo = index.data(ROL_CLIP)
        self.initStyleOption(option, index)
        option.text = ""
        option.widget.style().drawControl(
            option.widget.style().ControlElement.CE_ItemViewItem, option, painter, option.widget
        )
        if not clip.match.content_mismatch:
            return
        r = option.rect
        lado = min(16, r.height() - 8)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = r.center().x() + 1, r.center().y() + 1
        rombo = QPolygonF(
            [
                QPointF(cx, cy - lado / 2),
                QPointF(cx + lado / 2, cy),
                QPointF(cx, cy + lado / 2),
                QPointF(cx - lado / 2, cy),
            ]
        )
        painter.setPen(QPen(idn.color(idn.BRAND_400), 1.2))
        painter.setBrush(QBrush(idn.color(idn.BRAND_400, 0.16)))
        painter.drawPolygon(rombo)
        painter.setFont(idn.fuente_cifra(9, QFont.Weight.Bold))
        painter.setPen(QPen(idn.color(idn.BRAND_400)))
        painter.drawText(r, int(Qt.AlignmentFlag.AlignCenter), "!")
        painter.restore()

    #: Lo que ocupa el rombo con su aire. `PantallaClips.anchos_fijos()` lo
    #: lee de aqui para no repetir el numero.
    ANCHO = 46

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(self.ANCHO, INSIGNIA_ALTO + 10)


def _ancho_cabecera(metricas: QFontMetrics, texto: str) -> int:
    """Lo que ocupa de ancho un rotulo de cabecera, que puede ir en dos lineas."""
    return max(metricas.horizontalAdvance(linea) for linea in texto.split("\n"))


# ---------------------------------------------------------------------------
# La ficha de detalle
# ---------------------------------------------------------------------------


class FichaClip(QWidget):
    """Lo que se sabe del clip seleccionado, incluidas las razones en castellano."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # La anchura minima se pone al final del constructor, medida. Ver alli.
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        self.panel = Panel()
        caja.addWidget(self.panel)

        self.rotulo_titulo = Rotulo("clip seleccionado", acento=True)
        self.panel.caja.addWidget(self.rotulo_titulo)

        self.nombre = EtiquetaElidida("", modo=Qt.TextElideMode.ElideMiddle, ancho_minimo_px=60)
        self.nombre.setFont(idn.fuente_texto(15, QFont.Weight.DemiBold))
        self.panel.caja.addWidget(self.nombre)

        self.identificador = Cifra("", px=11)
        self.identificador.setObjectName("apagado")
        self.identificador.setFont(idn.fuente_cifra(11))
        self.panel.caja.addWidget(self.identificador)

        self.panel.caja.addWidget(separador())

        fila = QHBoxLayout()
        fila.setSpacing(10)
        self.insignia = InsigniaConfianza(idn.FormaConfianza.ALTA, 0.0)
        fila.addWidget(self.insignia, 0, Qt.AlignmentFlag.AlignLeft)
        fila.addStretch(1)
        self.panel.caja.addLayout(fila)

        # [dia 4] «ΔE MEDIO» encima de las dos, y no «ΔE antes» / «ΔE después»:
        # son medias (`MatchResult.delta_e_before/after`) y el contrato no trae
        # el maximo por clip, asi que no se puede ensenar la cifra que decide.
        # Lo que hay se rotula con su nombre. Un solo rotulo comun y no
        # «ΔE medio antes» / «ΔE medio después» por el ancho: esos dos seguidos
        # piden 252 px y la ficha tiene 246, o sea que ensancharian la ventana.
        self.panel.caja.addWidget(Rotulo("ΔE medio"))
        cifras = QHBoxLayout()
        cifras.setSpacing(18)
        for rotulo, attr in (("antes", "_de_antes"), ("después", "_de_despues")):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(Rotulo(rotulo))
            etiqueta = Cifra("—", px=22, peso=QFont.Weight.DemiBold,
                             secundario=(attr == "_de_despues"))
            setattr(self, attr, etiqueta)
            col.addWidget(etiqueta)
            cifras.addLayout(col)
        cifras.addStretch(1)
        self.panel.caja.addLayout(cifras)

        self.panel.caja.addWidget(separador())
        self.panel.caja.addWidget(Rotulo("por qué esta nota"))
        self.razones = QLabel("—")
        self.razones.setWordWrap(True)
        self.razones.setObjectName("apagado")
        # Riesgo conocido y no arreglado (`gui/NOTAS.md`) si esto entra algún
        # día en una columna con scroll horizontal apagado.
        self.razones.setMinimumWidth(0)
        self.razones.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.razones.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.panel.caja.addWidget(self.razones, 1)

        self.bloque_desajuste = Panel(cristal=True)
        cab = QHBoxLayout()
        cab.setSpacing(8)
        cab.addWidget(MarcaDesajuste(), 0)
        t = Rotulo("desajuste de contenido", acento=True)
        cab.addWidget(t, 1)
        self.bloque_desajuste.caja.addLayout(cab)
        self.texto_desajuste = QLabel("")
        self.texto_desajuste.setWordWrap(True)
        # Mismo riesgo sin arreglar — ver `gui/NOTAS.md`.
        self.texto_desajuste.setMinimumWidth(0)
        self.bloque_desajuste.caja.addWidget(self.texto_desajuste)
        caja.addWidget(self.bloque_desajuste)
        # La anchura minima se mide ANTES de esconder el bloque de desajuste,
        # y a proposito: un widget escondido no cuenta para el layout, asi que
        # si el minimo se preguntara despues, la ficha podria encogerse hasta
        # que el rotulo «desajuste de contenido» saliera como «desajuste de
        # conteni…» justo cuando hay desajuste, que es cuando hace falta
        # leerlo. Y la anchura minima de la ventana no puede depender de que
        # clip haya seleccionado.
        self.setMinimumWidth(
            max(
                240,
                self.bloque_desajuste.minimumSizeHint().width(),
                self.panel.minimumSizeHint().width(),
            )
        )
        self.bloque_desajuste.setVisible(False)
        caja.setStretch(0, 1)
        self.mostrar(None)

    def mostrar(self, clip: ClipDemo | None) -> None:
        if clip is None:
            self.nombre.setText("—")
            self.identificador.setText("")
            self._de_antes.setText("—")
            self._de_despues.setText("—")
            self.razones.setText("Selecciona un clip para ver por qué tiene esa nota.")
            self.insignia.setVisible(False)
            self.bloque_desajuste.setVisible(False)
            return
        self.insignia.setVisible(True)
        conf = clip.match.confidence
        self.nombre.setText(clip.nombre)
        self.identificador.setText(f"{clip.clip_id} · pista {clip.ref.track} · "
                                   f"{clip.ref.start_frame}-{clip.ref.end_frame}")
        self._de_antes.setText(f"{clip.match.delta_e_before:.2f}")
        self._de_despues.setText(f"{clip.match.delta_e_after:.2f}")
        self.insignia.actualizar(idn.FormaConfianza.de_nivel(conf.level), conf.score)
        razones = conf.reasons or ("Sin comentarios: el ajuste no ha encontrado nada raro.",)
        self.razones.setText("\n\n".join(f"· {r}" for r in razones))
        hay = clip.match.content_mismatch
        self.bloque_desajuste.setVisible(hay)
        if hay:
            motivos = clip.razones_desajuste or clip.match.notes
            self.texto_desajuste.setText(
                "\n\n".join(f"· {m}" for m in motivos)
                or "· Las dos escenas no son comparables."
            )


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------


class PantallaClips(QWidget):
    """Tabla + ficha. Emite `clip_elegido` para que la ventana sincronice."""

    clip_elegido = Signal(str)

    def __init__(self, estado: EstadoDemo, parent=None) -> None:
        super().__init__(parent)
        self._estado = estado
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)

        caja.addWidget(self._resumen())

        self.division = QSplitter(Qt.Orientation.Horizontal)
        self.division.setChildrenCollapsible(False)
        self.division.setHandleWidth(12)

        self.tabla = QTableView()
        self.modelo = ModeloClips(estado.clips)
        self.tabla.setModel(self.modelo)
        self.tabla.setItemDelegateForColumn(COL_CONFIANZA, DelegadoConfianza(self.tabla))
        self.tabla.setItemDelegateForColumn(COL_AVISO, DelegadoAviso(self.tabla))
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.setWordWrap(False)
        self.tabla.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        cab = self.tabla.horizontalHeader()
        # Aqui NO se llama a `cab.setFont()`, y esta comprobado por que: Qt le
        # borra la fuente a la cabecera en el siguiente `polish` y la deja en la
        # heredada. El `FontRole` del modelo tampoco lo mira. La cabecera de una
        # tabla solo se puede vestir desde `QHeaderView::section`, que es la
        # unica regla de la hoja que declara un tamano de letra. Lo que se hace
        # aqui es MEDIR con esa misma fuente (`fuente_cabecera_tabla`).
        #
        # LAS QUE CEDEN SON LAS COLUMNAS DE CIFRAS, NO LA DEL NOMBRE.
        # Decision de Mario, y este es el sitio donde se cumple. Un ΔE es un
        # numero de formato acotado: «000.00» y ya, asi que su columna se puede
        # clavar a lo que mide ese numero. Un nombre de clip es un
        # identificador de longitud desconocida y es lo que dice QUE fila estas
        # mirando, asi que es el que se queda todo lo que sobra.
        #
        # Antes era al reves: las cinco columnas fijas iban a
        # `ResizeToContents`, que las mide por su CABECERA, y la del nombre
        # estiraba con un suelo de 56 px. A la anchura minima las cinco se
        # llevaban 439 px de los 492 de la tabla y el nombre se quedaba en 56:
        # «A...a».
        anchos = self.anchos_fijos()
        cab.setMinimumSectionSize(min(anchos.values()))
        for columna, ancho in anchos.items():
            cab.setSectionResizeMode(columna, QHeaderView.ResizeMode.Fixed)
            cab.resizeSection(columna, ancho)
        cab.setSectionResizeMode(COL_NOMBRE, QHeaderView.ResizeMode.Stretch)
        cab.setHighlightSections(False)
        self.tabla.setMinimumWidth(self.ancho_minimo_util())
        self.division.addWidget(self.tabla)

        contenedor = QScrollArea()
        contenedor.setWidgetResizable(True)
        contenedor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.ficha = FichaClip()
        contenedor.setWidget(self.ficha)
        # Lo que pida la ficha, mas la barra vertical: la barra horizontal esta
        # apagada, asi que lo que no cabe de ancho no se ve y no lo dice nadie.
        contenedor.setMinimumWidth(
            self.ficha.minimumWidth() + contenedor.verticalScrollBar().sizeHint().width()
        )
        self.division.addWidget(contenedor)
        self.division.setStretchFactor(0, 3)
        self.division.setStretchFactor(1, 2)
        self.division.setSizes([820, 400])
        caja.addWidget(self.division, 1)

        self.vacio = self._panel_vacio()
        caja.addWidget(self.vacio)

        # La anchura minima de la pantalla NO puede depender de cuantos clips
        # haya. Con cero clips la tabla se esconde, un widget escondido no
        # cuenta para el layout, y la ventana entera se podia encoger 55 px por
        # debajo de su minimo de siempre; ahi el panel de ingenieria inversa
        # salia con los rotulos recortados. Se fija aqui, con la tabla y la
        # ficha como testigos, y ya no se mueve.
        self.setMinimumWidth(
            self.tabla.minimumWidth() + contenedor.minimumWidth() + self.division.handleWidth()
        )

        self.tabla.selectionModel().selectionChanged.connect(self._cambio)
        if estado.clips:
            self.tabla.selectRow(0)
        self._aplicar_vacio()

    # -- construccion ------------------------------------------------------

    def _resumen(self) -> QWidget:
        panel = Panel(cristal=True, margenes=(14, 10, 14, 10))
        fila = QHBoxLayout()
        fila.setSpacing(26)
        clips = self._estado.clips
        cuenta = {"alta": 0, "media": 0, "baja": 0}
        for c in clips:
            cuenta[c.match.confidence.level] += 1
        desajustes = sum(1 for c in clips if c.match.content_mismatch)

        def bloque(rotulo: str, valor: str, *, secundario: bool = False) -> QVBoxLayout:
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(Rotulo(rotulo))
            col.addWidget(Cifra(valor, px=17, peso=QFont.Weight.DemiBold, secundario=secundario))
            return col

        fila.addLayout(bloque("clips", f"{len(clips):d}"))
        fila.addLayout(bloque("alta / media / baja",
                              f"{cuenta['alta']:d} / {cuenta['media']:d} / {cuenta['baja']:d}"))
        fila.addLayout(bloque("desajustes de contenido", f"{desajustes:d}", secundario=True))
        fila.addStretch(1)
        panel.caja.addLayout(fila)
        return panel

    def _panel_vacio(self) -> QWidget:
        panel = Panel(margenes=(24, 24, 24, 24))
        panel.caja.addWidget(Rotulo("sin clips", acento=True))
        t = QLabel(
            "El timeline está abierto pero no hay ningún clip que analizar.\n\n"
            "Añade clips al timeline en Resolve y vuelve a leerlo, o abre una sesión "
            "guardada (.sidebcolor)."
        )
        t.setWordWrap(True)
        t.setObjectName("apagado")
        # Mismo riesgo sin arreglar — ver `gui/NOTAS.md`.
        t.setMinimumWidth(0)
        panel.caja.addWidget(t)
        panel.caja.addStretch(1)
        return panel

    def _aplicar_vacio(self) -> None:
        hay = bool(self._estado.clips)
        self.division.setVisible(hay)
        self.vacio.setVisible(not hay)

    # -- interaccion -------------------------------------------------------

    def _cambio(self) -> None:
        clip = self.clip_actual()
        self.ficha.mostrar(clip)
        if clip is not None:
            self.clip_elegido.emit(clip.clip_id)

    def clip_actual(self) -> ClipDemo | None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self.modelo.data(filas[0], ROL_CLIP)

    def seleccionar(self, clip_id: str) -> None:
        for fila, clip in enumerate(self.modelo.clips()):
            if clip.clip_id == clip_id:
                self.tabla.selectRow(fila)
                return

    #: Cuanto nombre de clip tiene que quedar SIEMPRE visible. Por debajo de
    #: esto la columna no informa de nada: «A00...» no es un nombre.
    #:
    #: 124 px no es un numero bonito: los doce primeros caracteres del nombre
    #: mas largo de la demo, con su elipsis detras, miden 105 px en la fuente de
    #: texto de 13 px, y con el relleno de celda se van a 117. Doce caracteres
    #: utiles es el mismo criterio con el que `tests/test_gui_texto.py` acepta
    #: que una etiqueta elida. 124 deja un margen corto por encima de eso.
    NOMBRE_MINIMO_PX = 124

    #: Relleno horizontal de una celda, a cada lado: `QTableView::item` del QSS.
    RELLENO_CELDA_PX = 6

    #: Lo que Qt suma por su cuenta a una seccion o a una celda, ademas del
    #: padding del QSS. **Medido, no estimado**, y hay un test que lo vigila
    #: (`test_ninguna_cabecera_de_la_tabla_sale_recortada`): si Qt cambiara de
    #: criterio, la cabecera empezaria a salir con puntos suspensivos y el test
    #: lo dice antes que una captura.
    MARGEN_SECCION_PX = 8

    #: El texto mas ancho que puede aparecer en cada columna de cifras. Los dos
    #: ΔE los formatea `ModeloClips.data()` como `{:6.2f}`, o sea seis huecos
    #: monoespaciados; el indice, como `{:03d}`.
    TEXTO_MAS_ANCHO = {COL_INDICE: "000", COL_ANTES: "000.00", COL_DESPUES: "000.00"}

    def anchos_fijos(self) -> dict[int, int]:
        """Ancho fijo de cada columna que NO es la del nombre, medido.

        **Un solo calculo para dos usos**, y ahi esta el arreglo de fondo: con
        esto se fijan las columnas y con esto se calcula `ancho_minimo_util()`.
        El dia 2 eran dos cuentas distintas: la estimacion daba 356 px para las
        cinco columnas fijas y de verdad ocupaban 439 (medido hoy; la nota del
        dia 2 decia 441), y esa diferencia se la comia la columna del nombre.

        Cada columna se lleva lo que necesite la mas ancha de sus dos cosas: la
        cifra (en monoespaciada de 12) o su propia cabecera. Ninguna cabecera se
        recorta, y hay un test que lo comprueba preguntandole al estilo.
        """
        m_cifra = QFontMetrics(idn.fuente_cifra(12))
        # La de la cabecera se mide **como la pinta la hoja de estilo**, o sea
        # sin el tracking: el QSS no sabe escribirlo y un `setFont()` sobre la
        # cabecera Qt lo borra en el siguiente `polish` (comprobado). Medir con
        # el tracking puesto daria columnas mas anchas de lo que hace falta:
        # «ANTES» mide 33 px sin el y 41 con el, «DESPUES» 47 y 58.
        m_rotulo = QFontMetrics(idn.fuente_cabecera_tabla())
        anchos: dict[int, int] = {}
        for columna, texto in self.TEXTO_MAS_ANCHO.items():
            anchos[columna] = max(
                m_cifra.horizontalAdvance(texto) + 2 * self.RELLENO_CELDA_PX,
                _ancho_cabecera(m_rotulo, CABECERAS[columna]) + 2 * idn.RELLENO_CABECERA_PX,
            ) + self.MARGEN_SECCION_PX
        # Estas dos no llevan texto: las pinta un delegado y su `sizeHint` manda.
        for columna, pedido in (
            (COL_CONFIANZA, INSIGNIA_ANCHO + 16),
            (COL_AVISO, DelegadoAviso.ANCHO),
        ):
            anchos[columna] = max(
                pedido,
                _ancho_cabecera(m_rotulo, CABECERAS[columna])
                + 2 * idn.RELLENO_CABECERA_PX
                + self.MARGEN_SECCION_PX,
            )
        return anchos

    def ancho_minimo_util(self) -> int:
        """Lo que de verdad necesita la tabla para no comerse las columnas.

        Las columnas fijas, lo que midan; el nombre, su suelo; y lo que se come
        el envoltorio de la vista: la barra de desplazamiento vertical (con
        doscientos clips esta siempre puesta) y los dos bordes del marco. Los
        dos ultimos no son adorno: sin contarlos, los px que falten salen de la
        columna que estira, o sea del nombre.
        """
        barra = self.tabla.verticalScrollBar().sizeHint().width()
        marco = 2 * self.tabla.frameWidth()
        return sum(self.anchos_fijos().values()) + self.NOMBRE_MINIMO_PX + barra + marco


__all__ = [
    "CABECERAS",
    "COL_AVISO",
    "COL_CONFIANZA",
    "COL_NOMBRE",
    "ROL_CLIP",
    "DelegadoAviso",
    "DelegadoConfianza",
    "FichaClip",
    "ModeloClips",
    "PantallaClips",
]
