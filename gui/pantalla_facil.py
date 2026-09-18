"""Pantalla del modo fácil: el asistente de 5 pasos.

Ni un ΔE, ni un CDL, ni un porcentaje de cobertura en pantalla — eso es la
promesa del encargo (día 5, tarea 3), y por eso esta pantalla NUNCA muestra un
número crudo de `core`: sólo la frase que redacta `gui.asistente_facil` (que
ya la escribe en castellano llano) y el antes/después grande.

CÓMO SE MUEVE
-------------
Un paso a la vez, en el orden fijo de `asistente_facil.ID_PASOS`. "Siguiente"
avanza; "Deshacer" retrocede. No hay nada que deshacer DE VERDAD todavía:
esta pantalla es pura previsualización — calcula y enseña, no escribe en
Resolve. Por eso "deshacer" aquí es trivialmente seguro (sólo mueve el
puntero de paso) y por eso no hace falta un botón "aplicar": aplicar de
verdad, con la red de seguridad de la versión `SIDEB COLOR`, ya existe en el
modo avanzado (`PantallaAplicar`) y esta pantalla no lo duplica.

CUANDO UN PASO TIENE ALGO QUE PREGUNTAR
-----------------------------------------
El paso 1 puede dejar clips sin resolver (`PasoOrdenar.grupos_pendientes`).
Eso se enseña como una pregunta explícita, con el fotograma de muestra que ya
trae `GrupoAmbiguo.frame_muestra_clip_id` — nunca se avanza fingiendo que se
ha decidido algo que no se sabe.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.io.biblioteca import Preset
from gui import identidad as idn
from gui.asistente_facil import (
    ID_PASOS,
    TITULOS_PASO,
    ejecutar_equilibrar,
    ejecutar_igualar,
    ejecutar_look,
    ejecutar_ordenar,
    ejecutar_repasar,
)
from gui.datos_demo import ClipDemo, EstadoDemo
from gui.imagen import a_qimage
from gui.pantalla_comparar import VisorCortinilla
from gui.tutor_datos import frases_de_clip
from gui.widgets import Panel, Rotulo, TextoAjustado, separador


class _IndicadorPasos(QWidget):
    """Fila de rótulos numerados: en qué paso está, cuáles ya se hicieron."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fila = QHBoxLayout(self)
        self._fila.setContentsMargins(0, 0, 0, 0)
        self._fila.setSpacing(6)
        self._rotulos: list[Rotulo] = []
        for i, pid in enumerate(ID_PASOS):
            r = Rotulo(f"{i + 1} · {TITULOS_PASO[pid]}", px=10)
            self._fila.addWidget(r)
            self._rotulos.append(r)
            if i < len(ID_PASOS) - 1:
                self._fila.addWidget(separador(vertical=True))

    def marcar_actual(self, indice: int) -> None:
        for i, r in enumerate(self._rotulos):
            r.setObjectName("acento" if i == indice else "tenue")
            r.style().unpolish(r)
            r.style().polish(r)


class _SelectorPresets(QWidget):
    """Fila horizontal, con scroll, de chips «Nombre legible» — nunca un
    nombre de archivo. Uno por preset de la biblioteca (día 6, tarea 4). La
    miniatura GRANDE del elegido ya la enseña el visor cortinilla del paso
    (antes/después); aquí sólo hace falta poder ELEGIR entre varios, así que
    no se renderiza una miniatura por cada chip — con 79 presets reales eso
    sería mucho coste de render para un selector de texto."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFixedHeight(48)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenido = QWidget()
        self._fila = QHBoxLayout(contenido)
        self._fila.setContentsMargins(0, 0, 0, 0)
        self._fila.setSpacing(6)
        self._fila.addStretch(1)
        self._area.setWidget(contenido)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self._area)
        self._botones: dict[str, QPushButton] = {}

    def poner(self, presets: tuple[Preset, ...], elegido_id: str | None, al_elegir) -> None:
        for b in self._botones.values():
            b.setParent(None)
        self._botones.clear()
        for preset in presets:
            b = QPushButton(preset.nombre)
            b.setObjectName("navegacion")
            b.setCheckable(True)
            b.setChecked(preset.id == elegido_id)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _checked, pid=preset.id: al_elegir(pid))
            self._fila.insertWidget(self._fila.count() - 1, b)
            self._botones[preset.id] = b
        self.setVisible(bool(presets))


#: Cuántos candidatos del paso 5 se enseñan en la lista. No es un capricho de
#: diseño: es lo que se ha MEDIDO (`CIFRAS.md` §18, precisión@5 y @10) — más
#: allá de 10 no hay ninguna cifra publicada que diga si el orden sigue
#: sirviendo, así que enseñar más sería una promesa sin medir detrás.
MAX_CANDIDATOS_REPASO = 10


class _BotonRepaso(QPushButton):
    """Una fila de `_ListaRepaso`: el texto se recorta con «…» al ancho real
    del botón, no a lo bruto en el borde.

    Día 7: capturada la anchura mínima (973px) del recorrido completo, el
    motivo de un candidato salía cortado a mitad de palabra y sin ninguna
    marca de que faltaba texto — el mismo fallo que `gui.widgets.EtiquetaElidida`
    ya existe para resolver en las etiquetas normales, pero un botón
    clicable no puede ser un `QLabel`. El texto completo siempre queda
    accesible por el tooltip.

    La primera versión sólo recortaba el TEXTO y se quedaba igual de rota:
    `QPushButton.sizeHint()`/`minimumSizeHint()` de Qt se calculan a partir
    del texto que el botón tiene puesto en cada momento, así que un botón
    con el texto completo pedía un ancho mínimo más ancho que la ventana —
    la `QScrollArea` (sin barra horizontal) le daba ese ancho de todas
    formas y el sobrante quedaba fuera de la vista, sin recortar y sin
    aviso. Por eso aquí, igual que en `EtiquetaElidida`, el tamaño que pide
    el widget se DESACOPLA del texto que se ve: `sizeHint()` mira el texto
    COMPLETO (para que una ventana holgada lo enseñe entero) y
    `minimumSizeHint()` es un ancho mínimo fijo pequeño (para que el layout
    pueda encogerlo de verdad), nunca lo que mide el texto ya recortado.
    """

    _ANCHO_MINIMO_PX = 80

    def __init__(self, texto_completo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._texto_completo = texto_completo
        self.setToolTip(texto_completo)
        # Un QPushButton normal tiene política horizontal `Minimum`, que para
        # Qt significa "el ancho de `sizeHint()` es también el mínimo": con el
        # `sizeHint()` de abajo devolviendo el ancho del texto COMPLETO, el
        # botón nunca se habría podido encoger por debajo de eso, por mucho
        # que `minimumSizeHint()` dijera otra cosa — el mismo bug de fondo,
        # sólo que un nivel más abajo. `Preferred` es la política que SÍ dice
        # "el mínimo de verdad es `minimumSizeHint()`, `sizeHint()` es sólo lo
        # ideal" (la misma que usa `gui.widgets.EtiquetaElidida`).
        self.setSizePolicy(QSizePolicy.Policy.Preferred, self.sizePolicy().verticalPolicy())
        super().setText(texto_completo)
        self._refrescar()

    def _margen_horizontal(self) -> int:
        m = self.contentsMargins()
        # +24px: el relleno interno que Qt añade a un QPushButton (chrome del
        # estilo) no está en `contentsMargins()`; sin este margen extra el
        # recorte se come el último carácter contra el borde del botón.
        return m.left() + m.right() + 24

    def _refrescar(self) -> None:
        metricas = QFontMetrics(self.font())
        disponible = max(self.width() - self._margen_horizontal(), 8)
        recortado = metricas.elidedText(self._texto_completo, Qt.TextElideMode.ElideRight, disponible)
        super().setText(recortado)

    def sizeHint(self) -> QSize:  # noqa: N802  (override de Qt)
        metricas = QFontMetrics(self.font())
        ancho = metricas.horizontalAdvance(self._texto_completo) + self._margen_horizontal()
        return QSize(ancho, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802  (override de Qt)
        return QSize(self._ANCHO_MINIMO_PX, super().sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802  (override de Qt)
        super().resizeEvent(event)
        self._refrescar()


class _ListaRepaso(QWidget):
    """La lista del paso 5, completa (hasta `MAX_CANDIDATOS_REPASO`) y en
    orden — antes sólo se enseñaba el primer candidato, lo que rompía la
    promesa de "estos los miraría yo, por orden": si sólo se ve uno, no hay
    orden que enseñar (día 7, tarea 3)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setMaximumHeight(180)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenido = QWidget()
        self._columna = QVBoxLayout(contenido)
        self._columna.setContentsMargins(0, 0, 0, 0)
        self._columna.setSpacing(2)
        self._area.setWidget(contenido)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self._area)
        self._botones: list[_BotonRepaso] = []

    def poner(self, candidatos: tuple, elegido_id: str | None, al_elegir) -> None:
        for b in self._botones:
            b.setParent(None)
        self._botones.clear()
        for i, c in enumerate(candidatos[:MAX_CANDIDATOS_REPASO], start=1):
            b = _BotonRepaso(f"{i}. {c.nombre} — {c.motivo}")
            b.setObjectName("navegacion")
            b.setCheckable(True)
            b.setChecked(c.clip_id == elegido_id)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("text-align: left;")
            b.clicked.connect(lambda _checked, cid=c.clip_id: al_elegir(cid))
            self._columna.addWidget(b)
            self._botones.append(b)
        self.setVisible(bool(candidatos))


#: Alto máximo del contenido de `_PanelTutor` — el mismo recurso que
#: `_ListaRepaso` (más abajo) para la misma razón: sin un tope, con
#: bastantes frases el panel podía crecer hasta empujar los botones
#: Deshacer/Siguiente paso fuera de la ventana a la anchura mínima, sin
#: ninguna barra que avisara de que faltaba contenido (día 8, aviso de
#: Mario tras el bug del panel "por qué" de `pantalla_comparar.py` — la
#: misma clase de fallo, aplicada aquí antes de que llegara a pasar).
#: La CABECERA ("EL TUTOR DICE") vive FUERA del área con tope, así que
#: siempre se ve aunque el contenido necesite desplazarse.
ALTO_MAXIMO_PANEL_TUTOR = 140


class _PanelTutor(QWidget):
    """Las frases del tutor sobre el clip que se está mirando ahora — día 8,
    tarea 2.6. SÓLO el texto: ni ΔE, ni CDL, ni nombre de característica, ni
    umbral. Eso es lo que enseña el modo avanzado (`gui/pantalla_reverse.py`);
    aquí `core.tutor.catalogo.Frase.texto` es el único campo que se lee.

    Prioridad vertical del paso "look" a la anchura mínima (día 8): 1) el
    antes/después, 2) la frase de qué ha hecho la app, 3) los botones de
    seguir/deshacer — los tres SIEMPRE visibles, nunca comprimidos por este
    panel — y 4) esto, visible entero si cabe, con scroll (nunca oculto sin
    aviso) si no. El que cede espacio primero es el visor de antes/después
    (`VisorCortinilla` tiene un mínimo bajo, 170px, y `stretch=1`), no este
    panel ni los botones."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._panel = Panel()
        self._rotulo = Rotulo("EL TUTOR DICE")
        self._panel.caja.addWidget(self._rotulo)
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setMaximumHeight(ALTO_MAXIMO_PANEL_TUTOR)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenido = QWidget()
        self._columna = QVBoxLayout(contenido)
        self._columna.setContentsMargins(0, 0, 0, 0)
        self._columna.setSpacing(6)
        self._area.setWidget(contenido)
        self._panel.caja.addWidget(self._area)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self._panel)
        self._etiquetas: list[TextoAjustado] = []

    def poner(self, frases: tuple) -> None:
        for etiqueta in self._etiquetas:
            etiqueta.setParent(None)
        self._etiquetas.clear()
        for frase in frases:
            etiqueta = TextoAjustado(f"·  {frase.texto}")
            etiqueta.setFont(idn.fuente_texto(13))
            self._columna.addWidget(etiqueta)
            self._etiquetas.append(etiqueta)
        self.setVisible(bool(frases))


class PantallaFacil(QWidget):
    """El asistente completo. Se construye una vez por `EstadoDemo`."""

    def __init__(
        self,
        estado: EstadoDemo,
        parent: QWidget | None = None,
        *,
        biblioteca: tuple[Preset, ...] = (),
    ) -> None:
        super().__init__(parent)
        self._estado = estado
        self._biblioteca = biblioteca
        self._preset_elegido_id: str | None = biblioteca[0].id if biblioteca else None
        self._indice = 0
        self._paso_ordenar = None  # cacheado: el paso 5 lo necesita
        self._repaso_elegido_id: str | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(12)

        self._indicador = _IndicadorPasos()
        raiz.addWidget(self._indicador)

        self._selector_presets = _SelectorPresets()
        self._selector_presets.hide()
        raiz.addWidget(self._selector_presets)

        self._visor = VisorCortinilla()
        raiz.addWidget(self._visor, 1)

        self._panel_texto = Panel()
        self._frase = TextoAjustado("")
        self._frase.setFont(idn.fuente_texto(15))
        self._panel_texto.caja.addWidget(self._frase)
        self._pregunta = TextoAjustado("")
        self._pregunta.setObjectName("acento")
        self._pregunta.setFont(idn.fuente_texto(13))
        self._pregunta.hide()
        self._panel_texto.caja.addWidget(self._pregunta)
        raiz.addWidget(self._panel_texto)

        self._panel_tutor = _PanelTutor()
        self._panel_tutor.hide()
        raiz.addWidget(self._panel_tutor)

        self._lista_repaso = _ListaRepaso()
        self._lista_repaso.hide()
        raiz.addWidget(self._lista_repaso)

        fila = QHBoxLayout()
        self.boton_deshacer = QPushButton("Deshacer")
        self.boton_deshacer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_deshacer.clicked.connect(self.deshacer)
        fila.addWidget(self.boton_deshacer)
        fila.addStretch(1)
        self.boton_siguiente = QPushButton("Siguiente paso")
        self.boton_siguiente.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_siguiente.clicked.connect(self.siguiente)
        fila.addWidget(self.boton_siguiente)
        raiz.addLayout(fila)

        self._mostrar_paso(0)

    # -- navegacion ----------------------------------------------------------

    def paso_actual(self) -> str:
        return ID_PASOS[self._indice]

    def siguiente(self) -> None:
        if self._indice < len(ID_PASOS) - 1:
            self._indice += 1
            self._mostrar_paso(self._indice)

    def deshacer(self) -> None:
        """Retrocede un paso. No hay nada escrito que deshacer de verdad todavía
        (ver el docstring del módulo): esto sólo mueve el puntero."""
        if self._indice > 0:
            self._indice -= 1
            self._mostrar_paso(self._indice)

    def _elegir_preset(self, preset_id: str) -> None:
        self._preset_elegido_id = preset_id
        self._mostrar_paso(self._indice)

    # -- por paso --------------------------------------------------------------

    def _clip_con_imagen(self, *, evitar_referencia: bool = False) -> ClipDemo | None:
        """El primer clip con imagen cargada.

        `evitar_referencia=True` para los pasos que ajustan color (igualar,
        equilibrar, look): la referencia se empareja consigo misma y el CDL
        sale casi la identidad, así que enseñarla ahí no demuestra nada — el
        antes y el después saldrían iguales aunque el ajuste esté bien.
        """
        candidato_referencia: ClipDemo | None = None
        for c in self._estado.clips:
            if c.original is None:
                continue
            if evitar_referencia and c.clip_id == self._estado.referencia_id:
                candidato_referencia = c
                continue
            return c
        return candidato_referencia

    def _mostrar_paso(self, indice: int) -> None:
        self._indicador.marcar_actual(indice)
        self.boton_deshacer.setEnabled(indice > 0)
        self.boton_siguiente.setText(
            "Siguiente paso" if indice < len(ID_PASOS) - 1 else "Terminado"
        )
        self.boton_siguiente.setEnabled(indice < len(ID_PASOS) - 1)
        self._pregunta.hide()
        if ID_PASOS[indice] != "look":
            self._selector_presets.hide()
            self._panel_tutor.hide()

        pid = ID_PASOS[indice]
        if pid == "ordenar":
            self._paso_ordenar = ejecutar_ordenar(self._estado)
            self._frase.setText(self._paso_ordenar.frase)
            if self._paso_ordenar.grupos_pendientes:
                grupo = self._paso_ordenar.grupos_pendientes[0]
                self._pregunta.setText(grupo.pregunta)
                self._pregunta.show()
            clip = self._clip_con_imagen()
            self._visor.poner(
                a_qimage(clip.original) if clip else None,
                a_qimage(clip.original) if clip else None,
                mensaje="Ordenar la casa no cambia ningún píxel: sólo la configuración del proyecto.",
            )
        elif pid == "igualar":
            paso = ejecutar_igualar(self._estado)
            self._frase.setText(paso.frase)
            clip = self._clip_con_imagen(evitar_referencia=True)
            self._visor.poner(
                a_qimage(clip.original) if clip else None,
                a_qimage(clip.despues()) if clip else None,
            )
        elif pid == "equilibrar":
            clip = self._clip_con_imagen(evitar_referencia=True)
            if clip is not None:
                paso = ejecutar_equilibrar(clip)
                self._frase.setText(paso.frase)
            else:
                self._frase.setText("No hay ningún clip que equilibrar.")
            self._visor.poner(
                a_qimage(clip.original) if clip else None,
                a_qimage(clip.despues()) if clip else None,
            )
        elif pid == "look":
            paso = ejecutar_look(
                self._estado, biblioteca=self._biblioteca, preset_elegido_id=self._preset_elegido_id
            )
            self._frase.setText(paso.frase)
            self._selector_presets.poner(paso.presets_disponibles, self._preset_elegido_id, self._elegir_preset)
            clip = self._clip_con_imagen(evitar_referencia=True)
            despues_look = None
            antes_look = None
            if clip is not None and paso.look is not None:
                antes_look = clip.despues()
                despues_look = paso.look.apply(antes_look).astype(antes_look.dtype)
            self._visor.poner(
                a_qimage(antes_look) if antes_look is not None else None,
                a_qimage(despues_look) if despues_look is not None else None,
            )
            self._panel_tutor.poner(frases_de_clip(self._estado, clip) if clip is not None else ())
        elif pid == "repasar":
            paso_ordenar = self._paso_ordenar or ejecutar_ordenar(self._estado)
            paso = ejecutar_repasar(self._estado, paso_ordenar)
            self._frase.setText(paso.frase)
            if paso.candidatos:
                # El elegido sigue siendo válido si el usuario ya había hecho
                # click en la lista en una vuelta anterior a este paso; si no
                # (o si ya no está en la lista), se cae al primero — que es
                # el que el orden dice que conviene mirar antes.
                ids_candidatos = {c.clip_id for c in paso.candidatos}
                if self._repaso_elegido_id not in ids_candidatos:
                    self._repaso_elegido_id = paso.candidatos[0].clip_id
                elegido = next(c for c in paso.candidatos if c.clip_id == self._repaso_elegido_id)

                self._lista_repaso.poner(paso.candidatos, self._repaso_elegido_id, self._elegir_repaso)
                self._pregunta.setText(f"«{elegido.nombre}»: {elegido.motivo}")
                self._pregunta.show()
                clip = self._estado.por_id(elegido.clip_id)
                self._visor.poner(
                    a_qimage(clip.original) if clip and clip.original is not None else None,
                    a_qimage(clip.despues()) if clip and clip.original is not None else None,
                )
            else:
                self._lista_repaso.poner((), None, self._elegir_repaso)
                self._visor.poner(None, None, mensaje="No hay nada pendiente de revisar.")
        if pid != "repasar":
            self._lista_repaso.hide()

    def _elegir_repaso(self, clip_id: str) -> None:
        self._repaso_elegido_id = clip_id
        self._mostrar_paso(self._indice)


__all__ = ["PantallaFacil"]
