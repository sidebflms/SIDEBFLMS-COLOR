"""Crear/editar/borrar perfiles de trabajo (día 9, continuación 14).

Hasta hoy `core.io.perfiles.guardar_perfil` existía y funcionaba —tenía sus
propios tests desde que se creó (continuación 10)— pero nada en la GUI lo
llamaba: un perfil de trabajo ("Fabrik", con sus cámaras conocidas) sólo se
podía montar a mano en Python. `DialogoPerfiles` es la pieza que faltaba:
una lista de los perfiles ya guardados en la carpeta configurada, y un
formulario para crear uno nuevo o editar uno existente — nombre, un look
compartido opcional (un `.cube` cualquiera), y una fila por cámara con su
propio CDL de partida.

Reutiliza `gui.pantalla_reverse.EditorCDL` tal cual para los diez números de
cada CDL — son el mismo control, no hace falta uno segundo.

POR QUÉ UN `QDialog`, NO UNA SEXTA PANTALLA DE NAVEGACIÓN
-----------------------------------------------------------
Gestionar perfiles es una tarea de "configurar una vez, usar muchas veces",
no un paso del flujo normal de trabajo (`VentanaPrincipal.PANTALLAS` son los
cuatro pasos de siempre). Vive como diálogo modal, abierto desde el botón
"Gestionar perfiles…" que ya está junto al selector en `PantallaAplicar`, y
al cerrarse esa pantalla refresca su lista de perfiles disponibles — el
diálogo no sabe nada de `EstadoDemo`, sólo de la carpeta de perfiles.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.contracts import CDL
from core.io.cube import leer_cube
from core.io.errores import ErrorFormatoCube, ErrorPerfil
from core.io.perfiles import borrar_perfil, cargar_perfil, guardar_perfil, listar_perfiles
from core.perfiles import PerfilCamara, PerfilTrabajo
from gui.pantalla_reverse import EditorCDL
from gui.widgets import Panel, Rotulo, separador

__all__ = ["DialogoPerfiles", "FilaCamara"]


def _slug(texto: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return s or "perfil"


class FilaCamara(QWidget):
    """Una `PerfilCamara`: a qué clip reconoce (por subcadena) + su CDL de
    partida. `EditorCDL` no necesita callback aquí — no hay ninguna vista
    previa que repintar al cambiar un número, sólo se lee al guardar."""

    def __init__(self, al_quitar, parent=None) -> None:
        super().__init__(parent)
        self._al_quitar = al_quitar
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(6)

        fila_campos = QHBoxLayout()
        fila_campos.setSpacing(6)
        self.campo_fabricante = QLineEdit()
        self.campo_fabricante.setPlaceholderText("fabricante contiene… (p.ej. gopro)")
        self.campo_tipo = QLineEdit()
        self.campo_tipo.setPlaceholderText("tipo contiene… (opcional)")
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("nombre legible (opcional)")
        for campo in (self.campo_fabricante, self.campo_tipo, self.campo_nombre):
            fila_campos.addWidget(campo)
        btn_quitar = QPushButton("Quitar cámara")
        btn_quitar.clicked.connect(lambda: self._al_quitar(self))
        fila_campos.addWidget(btn_quitar)
        caja.addLayout(fila_campos)

        self.editor_cdl = EditorCDL(lambda: None)
        self.editor_cdl.poner(CDL())
        caja.addWidget(self.editor_cdl)
        caja.addWidget(separador())

    def poner(self, camara: PerfilCamara) -> None:
        self.campo_fabricante.setText(camara.fabricante_contiene)
        self.campo_tipo.setText(camara.tipo_contiene)
        self.campo_nombre.setText(camara.nombre_legible)
        self.editor_cdl.poner(camara.cdl_base)

    def perfil_camara(self) -> PerfilCamara:
        return PerfilCamara(
            fabricante_contiene=self.campo_fabricante.text().strip(),
            tipo_contiene=self.campo_tipo.text().strip(),
            nombre_legible=self.campo_nombre.text().strip(),
            cdl_base=self.editor_cdl.cdl(),
        )


class DialogoPerfiles(QDialog):
    def __init__(self, carpeta_raiz: str | Path, parent=None) -> None:
        super().__init__(parent)
        self._carpeta_raiz = Path(carpeta_raiz)
        #: Slug de carpeta del perfil que se está editando; `None` = uno
        #: nuevo, sin guardar todavía.
        self._carpeta_actual: str | None = None
        self._filas_camara: list[FilaCamara] = []

        self.setWindowTitle("Perfiles de trabajo")
        self.resize(860, 580)
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(16, 16, 16, 16)
        raiz.setSpacing(12)

        division = QSplitter()
        raiz.addWidget(division)

        # -- izquierda: la lista -----------------------------------------
        izq = Panel(margenes=(12, 12, 12, 12))
        izq.setMinimumWidth(200)
        izq.caja.addWidget(Rotulo("perfiles guardados", acento=True))
        self.lista = QListWidget()
        self.lista.currentTextChanged.connect(self._seleccionar)
        izq.caja.addWidget(self.lista, 1)
        fila_botones = QHBoxLayout()
        self.btn_nuevo = QPushButton("Nuevo")
        self.btn_nuevo.clicked.connect(self._nuevo)
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_eliminar.clicked.connect(self._eliminar)
        fila_botones.addWidget(self.btn_nuevo)
        fila_botones.addWidget(self.btn_eliminar)
        izq.caja.addLayout(fila_botones)
        division.addWidget(izq)

        # -- derecha: el formulario ----------------------------------------
        der = Panel(margenes=(12, 12, 12, 12))
        der.caja.addWidget(Rotulo("nombre", acento=True))
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("p.ej. Fabrik")
        der.caja.addWidget(self.campo_nombre)

        der.caja.addWidget(separador())
        der.caja.addWidget(Rotulo("look compartido (opcional)", acento=True))
        fila_look = QHBoxLayout()
        self.campo_look = QLineEdit()
        self.campo_look.setPlaceholderText("ningún .cube elegido")
        self.campo_look.setReadOnly(True)
        fila_look.addWidget(self.campo_look, 1)
        self.btn_examinar_look = QPushButton("Examinar…")
        self.btn_examinar_look.clicked.connect(self._examinar_look)
        fila_look.addWidget(self.btn_examinar_look)
        self.btn_quitar_look = QPushButton("Quitar")
        self.btn_quitar_look.clicked.connect(self._quitar_look)
        fila_look.addWidget(self.btn_quitar_look)
        der.caja.addLayout(fila_look)

        der.caja.addWidget(separador())
        fila_camaras_titulo = QHBoxLayout()
        fila_camaras_titulo.addWidget(Rotulo("cámaras conocidas", acento=True), 1)
        self.btn_anadir_camara = QPushButton("Añadir cámara")
        self.btn_anadir_camara.clicked.connect(lambda: self._anadir_fila_camara())
        fila_camaras_titulo.addWidget(self.btn_anadir_camara, 0)
        der.caja.addLayout(fila_camaras_titulo)

        self._area_camaras = QScrollArea()
        self._area_camaras.setWidgetResizable(True)
        self._contenedor_camaras = QWidget()
        self._caja_camaras = QVBoxLayout(self._contenedor_camaras)
        self._caja_camaras.setContentsMargins(0, 0, 0, 0)
        self._caja_camaras.addStretch(1)
        self._area_camaras.setWidget(self._contenedor_camaras)
        der.caja.addWidget(self._area_camaras, 1)

        fila_guardar = QHBoxLayout()
        fila_guardar.addStretch(1)
        self.btn_guardar = QPushButton("Guardar perfil")
        self.btn_guardar.setObjectName("primario")
        self.btn_guardar.clicked.connect(self._guardar)
        fila_guardar.addWidget(self.btn_guardar)
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cerrar.clicked.connect(self.accept)
        fila_guardar.addWidget(self.btn_cerrar)
        der.caja.addLayout(fila_guardar)

        division.addWidget(der)
        division.setSizes([220, 600])

        self._refrescar_lista()
        # Si ya hay perfiles guardados, se abre sobre el primero -- no en
        # blanco fingiendo que no hay nada que editar. Explícito y no un
        # efecto colateral de mostrar la ventana: Qt puede, por su cuenta,
        # marcar la fila 0 como actual la primera vez que un `QListWidget`
        # con selección se hace visible, y eso dispararía `_seleccionar`
        # DESPUÉS de este `__init__` si aquí se llamara a `_nuevo()` sin
        # condición — un test que nunca hace `.show()` no lo vería nunca,
        # que es justo como se encontró mirando una captura real.
        if self.lista.count():
            self.lista.setCurrentRow(0)
        else:
            self._nuevo()

    # -- la lista de la izquierda --------------------------------------------

    def _refrescar_lista(self, *, seleccionar: str | None = None) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        self.lista.addItems(listar_perfiles(self._carpeta_raiz))
        self.lista.blockSignals(False)
        if seleccionar is not None:
            coincidencias = self.lista.findItems(seleccionar, Qt.MatchFlag.MatchExactly)
            if coincidencias:
                self.lista.setCurrentItem(coincidencias[0])

    def _seleccionar(self, carpeta: str) -> None:
        if not carpeta:
            return
        try:
            perfil = cargar_perfil(self._carpeta_raiz / carpeta)
        except ErrorPerfil as exc:
            QMessageBox.warning(self, "Perfiles de trabajo", f"No se ha podido abrir «{carpeta}»: {exc}")
            return
        self._carpeta_actual = carpeta
        self._poner_perfil(perfil)

    def _nuevo(self) -> None:
        self._carpeta_actual = None
        self.lista.blockSignals(True)
        self.lista.setCurrentRow(-1)
        self.lista.blockSignals(False)
        self._poner_perfil(PerfilTrabajo(nombre=""))

    # -- el formulario de la derecha ------------------------------------------

    def _poner_perfil(self, perfil: PerfilTrabajo) -> None:
        self.campo_nombre.setText(perfil.nombre)
        self.campo_look.setText("")
        self.campo_look.setProperty("ruta_look_elegida", None)
        for fila in list(self._filas_camara):
            self._quitar_fila_camara(fila)
        for camara in perfil.camaras:
            self._anadir_fila_camara(camara)
        if perfil.look is not None:
            self.campo_look.setText("(look ya guardado en este perfil)")

    def _anadir_fila_camara(self, camara: PerfilCamara | None = None) -> None:
        fila = FilaCamara(self._quitar_fila_camara)
        if camara is not None:
            fila.poner(camara)
        self._caja_camaras.insertWidget(self._caja_camaras.count() - 1, fila)
        self._filas_camara.append(fila)

    def _quitar_fila_camara(self, fila: FilaCamara) -> None:
        self._caja_camaras.removeWidget(fila)
        fila.setParent(None)
        fila.deleteLater()
        if fila in self._filas_camara:
            self._filas_camara.remove(fila)

    def _examinar_look(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir look", "", "LUT (*.cube)")
        if ruta:
            self.campo_look.setText(ruta)
            self.campo_look.setProperty("ruta_look_elegida", ruta)

    def _quitar_look(self) -> None:
        self.campo_look.clear()
        self.campo_look.setProperty("ruta_look_elegida", None)

    # -- guardar / eliminar ----------------------------------------------------

    def _perfil_actual(self) -> PerfilTrabajo:
        """Lo que hay en el formulario ahora mismo. Puede lanzar
        `ErrorFormatoCube` si se eligió un `.cube` nuevo y no se puede leer."""
        look = None
        ruta_nueva = self.campo_look.property("ruta_look_elegida")
        if ruta_nueva:
            look = leer_cube(ruta_nueva)
        elif self._carpeta_actual is not None and self.campo_look.text():
            # No se tocó el selector de look: si el perfil ya tenía uno
            # guardado, se conserva tal cual releyéndolo de su propio
            # fichero -- no hay que pedirle a Mario que lo vuelva a elegir
            # sólo por cambiar el nombre o una cámara.
            anterior = cargar_perfil(self._carpeta_raiz / self._carpeta_actual)
            look = anterior.look
        camaras = tuple(fila.perfil_camara() for fila in self._filas_camara)
        return PerfilTrabajo(nombre=self.campo_nombre.text().strip(), camaras=camaras, look=look)

    def _guardar(self) -> None:
        nombre = self.campo_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Guardar perfil", "Ponle un nombre al perfil.")
            return
        try:
            perfil = self._perfil_actual()
        except (ErrorFormatoCube, ErrorPerfil) as exc:
            QMessageBox.warning(self, "Guardar perfil", f"El look elegido no se puede leer: {exc}")
            return

        slug = self._carpeta_actual or _slug(nombre)
        if self._carpeta_actual is None and slug in listar_perfiles(self._carpeta_raiz):
            respuesta = QMessageBox.question(
                self, "Guardar perfil",
                f"Ya existe un perfil guardado como «{slug}». ¿Sobrescribirlo?",
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return

        try:
            guardar_perfil(perfil, self._carpeta_raiz / slug, crear_directorios=True)
        except ErrorPerfil as exc:
            QMessageBox.warning(self, "Guardar perfil", f"No se ha podido guardar: {exc}")
            return

        self._carpeta_actual = slug
        self._refrescar_lista(seleccionar=slug)

    def _eliminar(self) -> None:
        if self._carpeta_actual is None:
            return
        respuesta = QMessageBox.question(
            self, "Eliminar perfil",
            f"¿Borrar el perfil «{self._carpeta_actual}»? Esto no se puede deshacer.",
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        try:
            borrar_perfil(self._carpeta_raiz / self._carpeta_actual)
        except ErrorPerfil as exc:
            QMessageBox.warning(self, "Eliminar perfil", str(exc))
            return
        self._refrescar_lista()
        self._nuevo()
