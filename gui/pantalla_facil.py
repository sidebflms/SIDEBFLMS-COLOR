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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

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


class PantallaFacil(QWidget):
    """El asistente completo. Se construye una vez por `EstadoDemo`."""

    def __init__(self, estado: EstadoDemo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._estado = estado
        self._indice = 0
        self._paso_ordenar = None  # cacheado: el paso 5 lo necesita

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(12)

        self._indicador = _IndicadorPasos()
        raiz.addWidget(self._indicador)

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
            paso = ejecutar_look(self._estado)
            self._frase.setText(paso.frase)
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
        elif pid == "repasar":
            paso_ordenar = self._paso_ordenar or ejecutar_ordenar(self._estado)
            paso = ejecutar_repasar(self._estado, paso_ordenar)
            self._frase.setText(paso.frase)
            if paso.candidatos:
                primero = paso.candidatos[0]
                clip = self._estado.por_id(primero.clip_id)
                self._pregunta.setText(f"«{primero.nombre}»: {primero.motivo}")
                self._pregunta.show()
                self._visor.poner(
                    a_qimage(clip.original) if clip and clip.original is not None else None,
                    a_qimage(clip.despues()) if clip and clip.original is not None else None,
                )
            else:
                self._visor.poner(None, None, mensaje="No hay nada pendiente de revisar.")


__all__ = ["PantallaFacil"]
