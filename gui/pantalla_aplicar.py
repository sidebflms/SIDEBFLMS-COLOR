"""Pantalla 3 — aplicar, por lotes o clip a clip.

LAS DOS COSAS QUE ESTA PANTALLA TIENE QUE HACER BIEN
----------------------------------------------------
1. **Que se vea que va a pasar ANTES de que pase.** El panel del plan se
   construye leyendo el puente y **sin escribir nada**: que version esta activa
   hoy, si la version `SIDEB COLOR` ya existe o hay que crearla, cuantos nodos
   tiene el clip, y que numeros van a ir al nodo 2 y que `.cube` al nodo 3. Si
   un clip no tiene los tres nodos, sale en el plan como «no se puede», porque
   la API de Resolve **no sabe crear nodos** y eso no lo arregla la app.
2. **Que el camino de error este probado.** Todo lo que se escribe pasa por
   `aplicar_grado_seguro`, y lo unico que se captura es `ResolveError` —que es
   lo que dice CONTRATOS.md—. Un fallo de un clip no tumba el lote: se apunta,
   se ensena con su mensaje en castellano y se sigue con el siguiente.

LA REGLA DE ORO NO SE TOCA
--------------------------
Aqui **no** se llama a `set_cdl` ni a `set_lut` a pelo. Ni una vez. Se llama a
`aplicar_grado_seguro`, que crea o selecciona la version `SIDEB COLOR` antes de
escribir un solo numero. Si alguien lo cambiara, el puente lanzaria
`EscrituraFueraDeVersion`... pero es que ademas hay un test que lo comprueba
mirando en que version quedaron las escrituras.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.batch import ProgresoLote, ejecutar_lote
from core.contracts import NODE_BALANCE, NODE_LOOK, VERSION_NAME, ResolveError
from core.io.errores import ErrorPerfil
from core.io.perfiles import cargar_perfil, listar_perfiles
from core.resolve import (
    ResultadoAplicacion,
    aplicar_grado_seguro,
    copiar_grado_seguro,
    es_version_nuestra,
    verificar_estructura_nodos,
)
from gui import identidad as idn
from gui.datos_demo import ClipDemo, EstadoDemo
from gui.dialogo_perfil import DialogoPerfiles
from gui.perfiles_trabajo import aplicar_perfil_a_estado
from gui.widgets import Cifra, EtiquetaElidida, Panel, Rotulo, separador

# ---------------------------------------------------------------------------
# El plan. Logica pura: se puede probar sin abrir una ventana.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineaPlan:
    """Lo que le va a pasar a un clip. **Nada de esto escribe.**"""

    clip_id: str
    nombre: str
    version_actual: str
    version_ya_existe: bool
    n_nodos: int
    puede: bool
    motivo: str = ""
    avisos: tuple[str, ...] = ()
    resumen_cdl: tuple[str, ...] = ()
    #: Día 9 (continuación 10): el look que le toca a ESTE clip
    #: (`clip.look_rel` si un perfil de trabajo le puso uno propio, si no
    #: `estado.look_rel`, el compartido). Se guarda aquí, no se relee de
    #: `estado.look_rel` al pintar — un perfil de trabajo puede dejar cada
    #: clip con un LUT distinto, y "qué va a pasar" tiene que decir el de
    #: CADA clip, no el mismo para todos.
    look_rel: str = ""

    @property
    def accion_version(self) -> str:
        if self.version_ya_existe:
            return f"se selecciona {VERSION_NAME!r} (ya estaba)"
        return f"se crea {VERSION_NAME!r}"


@dataclass
class Plan:
    lineas: list[LineaPlan] = field(default_factory=list)
    error_global: str = ""

    @property
    def aplicables(self) -> list[LineaPlan]:
        return [linea for linea in self.lineas if linea.puede]

    @property
    def bloqueados(self) -> list[LineaPlan]:
        return [linea for linea in self.lineas if not linea.puede]


def _resumen_cdl(clip: ClipDemo) -> tuple[str, str]:
    """Los diez numeros en DOS lineas.

    En una sola linea no cabian a 908 px y el panel se comia el `sat` sin
    ponerle siquiera puntos suspensivos. Partirlo en slope/offset y power/sat
    es ademas como se leen: ganancia y elevacion por un lado, gamma y
    saturacion por otro.
    """
    c = clip.match.cdl
    return (
        f"slope {c.slope[0]:.4f} {c.slope[1]:.4f} {c.slope[2]:.4f}   "
        f"offset {c.offset[0]:+.4f} {c.offset[1]:+.4f} {c.offset[2]:+.4f}",
        f"power {c.power[0]:.4f} {c.power[1]:.4f} {c.power[2]:.4f}   "
        f"sat {c.saturation:.4f}",
    )


def construir_plan(estado: EstadoDemo, clip_ids: list[str]) -> Plan:
    """Lee el puente y dice que pasaria. **No escribe ni un byte.**

    Es deliberado que las excepciones se conviertan en lineas del plan en vez de
    subir: el plan es justo el sitio donde Mario tiene que enterarse de que un
    clip no se puede tocar, y enterarse **antes** de darle al boton.
    """
    plan = Plan()
    puente = estado.puente
    try:
        if not puente.is_connected():
            plan.error_global = (
                "No hay conexión con DaVinci Resolve. Ábrelo, comprueba que es Studio y que "
                "el scripting externo está en 'Local' en Preferencias > System > General."
            )
            return plan
    except ResolveError as exc:
        plan.error_global = str(exc)
        return plan

    for clip_id in clip_ids:
        clip = estado.por_id(clip_id)
        if clip is None:
            continue
        try:
            versiones = puente.version_names(clip_id)
            actual = puente.current_version(clip_id)
            nodos = puente.list_nodes(clip_id)
        except ResolveError as exc:
            plan.lineas.append(
                LineaPlan(clip_id=clip_id, nombre=clip.nombre, version_actual="?",
                          version_ya_existe=False, n_nodos=0, puede=False, motivo=str(exc))
            )
            continue

        avisos: list[str] = []
        puede, motivo = True, ""
        try:
            avisos.extend(verificar_estructura_nodos(puente, clip_id))
        except ResolveError as exc:
            puede, motivo = False, str(exc)

        if not es_version_nuestra(actual):
            avisos.append(
                f"hoy está en la versión {actual!r}, que es la de Mario: no se toca. "
                f"El grado de la app va a otra versión."
            )
        plan.lineas.append(
            LineaPlan(
                clip_id=clip_id,
                nombre=clip.nombre,
                version_actual=actual,
                version_ya_existe=VERSION_NAME in versiones,
                n_nodos=len(nodos),
                puede=puede,
                motivo=motivo,
                avisos=tuple(avisos),
                resumen_cdl=_resumen_cdl(clip),
                look_rel=clip.look_rel if clip.look_rel is not None else estado.look_rel,
            )
        )
    return plan


@dataclass(frozen=True)
class ResultadoClip:
    clip_id: str
    nombre: str
    ok: bool
    version: str
    mensaje: str
    avisos: tuple[str, ...] = ()


def aplicar(estado: EstadoDemo, clip_ids: list[str]) -> list[ResultadoClip]:
    """Escribe de verdad, siempre por `aplicar_grado_seguro`.

    Un fallo de un clip no tumba el lote. Y se captura **solo** `ResolveError`:
    si sale otra cosa es un bug de la app y tiene que verse, no taparse.
    """
    resultados: list[ResultadoClip] = []
    puente = estado.puente
    try:
        puente.refresh_lut_list()
    except ResolveError as exc:
        resultados.append(
            ResultadoClip(clip_id="", nombre="(proyecto)", ok=False, version="",
                          mensaje=f"No se ha podido refrescar la lista de LUTs: {exc}")
        )
    for clip_id in clip_ids:
        clip = estado.por_id(clip_id)
        if clip is None:
            continue
        look_rel = clip.look_rel if clip.look_rel is not None else estado.look_rel
        try:
            res: ResultadoAplicacion = aplicar_grado_seguro(
                puente, clip_id, cdl=clip.match.cdl, lut_rel_path=look_rel
            )
            resultados.append(
                ResultadoClip(
                    clip_id=clip_id,
                    nombre=clip.nombre,
                    ok=res.ok,
                    version=res.version,
                    mensaje=(
                        f"nodo {NODE_BALANCE} ← CDL · nodo {NODE_LOOK} ← {look_rel}"
                        if res.ok
                        else "no se ha escrito nada"
                    ),
                    avisos=res.avisos,
                )
            )
        except ResolveError as exc:
            resultados.append(
                ResultadoClip(clip_id=clip_id, nombre=clip.nombre, ok=False, version="",
                              mensaje=str(exc))
            )
    return resultados


def aplicar_cancelable(
    estado: EstadoDemo,
    clip_ids: list[str],
    *,
    callback_progreso: Callable[[ProgresoLote], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
) -> list[ResultadoClip]:
    """Como `aplicar()`, pero por trozos: admite pararse a mitad.

    `BITACORA.md` (Bloque 3, punto 8): `aplicar()` es un bucle síncrono sin
    ningún punto de cancelación — con un lote muy grande, o Resolve real con
    latencia de verdad por llamada, no hay manera de pararlo desde la
    interfaz salvo matar la app entera. Esta función es la MISMA escritura
    (mismo `aplicar_grado_seguro`, sólo `ResolveError` capturado por clip —
    no es una segunda implementación de la regla de oro) envuelta en
    `core.batch.ejecutar_lote`, que llama a `callback_progreso` después de
    cada clip. Quien la use desde la GUI puede, dentro de ese callback,
    pintar una barra de progreso Y bombear `QApplication.processEvents()`
    (mismo patrón que `gui/capturas.py::_asentar`) para que un botón
    "Cancelar" real pueda pulsarse entre clip y clip — sin hilos, sin
    `QThread` (este proyecto no usa ninguno, ver `gui/NOTAS.md`).

    Sin `manifiesto` (a propósito, a diferencia de `core.analysis.lote`):
    reanudar un lote de "aplicar" interrumpido a través de un reinicio de la
    app es un caso mucho más raro que reanudar un análisis largo — y el
    ahorro real está en no perder lo que ya se ESCRIBIÓ (que ya vive en
    Resolve, no en un fichero de progreso), no en no tener que reescribirlo.
    Si algún día hace falta, se añade igual que en
    `core.analysis.lote.analizar_lote`.
    """
    detalles: dict[str, ResultadoClip] = {}
    puente = estado.puente
    try:
        puente.refresh_lut_list()
    except ResolveError as exc:
        detalles[""] = ResultadoClip(
            clip_id="", nombre="(proyecto)", ok=False, version="",
            mensaje=f"No se ha podido refrescar la lista de LUTs: {exc}",
        )

    def _uno(clip_id: str) -> None:
        clip = estado.por_id(clip_id)
        if clip is None:
            return
        look_rel = clip.look_rel if clip.look_rel is not None else estado.look_rel
        try:
            res: ResultadoAplicacion = aplicar_grado_seguro(
                puente, clip_id, cdl=clip.match.cdl, lut_rel_path=look_rel
            )
        except ResolveError as exc:
            detalles[clip_id] = ResultadoClip(
                clip_id=clip_id, nombre=clip.nombre, ok=False, version="", mensaje=str(exc)
            )
            raise  # ejecutar_lote lo captura tambien, para su propio aislamiento/manifiesto
        detalles[clip_id] = ResultadoClip(
            clip_id=clip_id,
            nombre=clip.nombre,
            ok=res.ok,
            version=res.version,
            mensaje=(
                f"nodo {NODE_BALANCE} ← CDL · nodo {NODE_LOOK} ← {look_rel}"
                if res.ok
                else "no se ha escrito nada"
            ),
            avisos=res.avisos,
        )

    ejecutar_lote(
        clip_ids,
        _uno,
        excepciones=(ResolveError,),
        callback_progreso=callback_progreso,
        debe_cancelar=debe_cancelar,
    )
    # Orden de clip_ids, no el de un dict: los que no llegaron a intentarse
    # (cancelado a mitad, o clip_id que no existe en el estado) simplemente
    # no aparecen -- igual que `aplicar()` con un clip_id inexistente.
    if "" in detalles:
        return [detalles[""]] + [detalles[cid] for cid in clip_ids if cid in detalles]
    return [detalles[cid] for cid in clip_ids if cid in detalles]


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------


class PantallaAplicar(QWidget):
    """Seleccion + plan + resultado."""

    aplicado = Signal()

    def __init__(self, estado: EstadoDemo, *, perfiles_carpeta: str | Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self._estado = estado
        self._perfiles_carpeta = Path(perfiles_carpeta) if perfiles_carpeta is not None else None
        # Ver `_estado_botones`: el último plan de LOTE calculado, para no
        # reconstruirlo entero sólo porque cambió la fila con el foco.
        self._ultimo_plan: Plan = Plan()
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)

        self.banda = Panel(cristal=True, margenes=(14, 10, 14, 10))
        self.texto_banda = EtiquetaElidida("", ancho_minimo_px=60)
        self.texto_banda.setFont(idn.fuente_texto(12))
        fila_banda = QHBoxLayout()
        fila_banda.setSpacing(12)
        self.rotulo_banda = Rotulo("resolve", acento=True)
        fila_banda.addWidget(self.rotulo_banda, 0)
        fila_banda.addWidget(self.texto_banda, 1)
        self.banda.caja.addLayout(fila_banda)
        caja.addWidget(self.banda)

        division = QSplitter(Qt.Orientation.Horizontal)
        division.setChildrenCollapsible(False)
        division.setHandleWidth(12)

        # --- izquierda: que clips ---
        izq = Panel(margenes=(12, 12, 12, 12))
        izq.setMinimumWidth(232)
        izq.caja.addWidget(Rotulo("clips a los que aplicar", acento=True))
        self.lista = QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lista.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        # Sin esto la lista saca barra horizontal y corta el nombre a hachazos
        # en vez de elidirlo. Se veia en la captura de 908 px.
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lista.setWordWrap(False)
        self.lista.setFont(idn.fuente_texto(12))
        izq.caja.addWidget(self.lista, 1)
        botones_sel = QHBoxLayout()
        botones_sel.setSpacing(8)
        self.btn_todos = QPushButton("Todos")
        self.btn_ninguno = QPushButton("Ninguno")
        botones_sel.addWidget(self.btn_todos)
        botones_sel.addWidget(self.btn_ninguno)
        botones_sel.addStretch(1)
        izq.caja.addLayout(botones_sel)

        # --- preparar nodos desde una plantilla (día 9, continuación 11) ---
        # El bloqueo real de "aplicar": un clip nuevo sólo tiene 1 nodo, y la
        # API de Resolve no sabe crear nodos (`core/resolve/NOTAS.md` §3.2;
        # `ApplyGradeFromDRX` se descartó, no existe en esta build). La única
        # vía que queda es que Mario prepare A MANO un clip con los 3 nodos
        # y esta app propague esa estructura al resto por script —
        # `copiar_grado_seguro` (`core/resolve/bridge.py`) ya existe para
        # esto exactamente, sólo le faltaba un botón.
        izq.caja.addWidget(separador())
        izq.caja.addWidget(Rotulo("preparar nodos", acento=True))
        self.texto_preparar_nodos = QLabel(
            "Enfoca en la lista el clip que ya tenga los 3 nodos preparados a "
            "mano, marca los clips destino arriba, y pulsa:"
        )
        self.texto_preparar_nodos.setWordWrap(True)
        self.texto_preparar_nodos.setMinimumWidth(0)
        self.texto_preparar_nodos.setFont(idn.fuente_texto(11))
        izq.caja.addWidget(self.texto_preparar_nodos)
        self.btn_preparar_nodos = QPushButton("Copiar la estructura de nodos al resto marcado")
        izq.caja.addWidget(self.btn_preparar_nodos)

        izq.caja.addWidget(separador())
        izq.caja.addWidget(Rotulo("look · nodo 3", acento=True))
        self.ruta_look = EtiquetaElidida(estado.look_rel, modo=Qt.TextElideMode.ElideMiddle,
                                         ancho_minimo_px=60)
        # Una RUTA es codigo, y la identidad pide monoespaciada para toda ruta.
        # La clase `cifra` no es decoracion: es lo que hace que la hoja de
        # estilo le de la familia monoespaciada. Sin ella, el `setFont()` de
        # aqui pedia JetBrains Mono y la regla `QWidget` le devolvia Inter, que
        # es justo donde mas se nota (ruta con espacios, elidida por el medio).
        self.ruta_look.setProperty("class", "cifra")
        self.ruta_look.setFont(idn.fuente_cifra(11))
        izq.caja.addWidget(self.ruta_look)
        self.texto_look = QLabel("")
        self.texto_look.setWordWrap(True)
        # 0 no arregla nada por sí solo (`gui/NOTAS.md`): hoy no vive dentro
        # de una columna acotada con scroll horizontal apagado, así que no se
        # nota — se romperá igual si algún día se mete en algo así.
        self.texto_look.setMinimumWidth(0)
        self.texto_look.setFont(idn.fuente_texto(11))
        izq.caja.addWidget(self.texto_look)

        # --- perfil de trabajo (día 9, continuación 10) ---
        # El "un botón" que pidió Mario: para un tipo de trabajo recurrente
        # (p.ej. "Fabrik", varias cámaras conocidas), detecta la cámara de
        # CADA clip del lote y le hornea su LUT (ajuste de esa cámara + look
        # compartido) de una sola vez — sin ir cámara por cámara ni clip por
        # clip. Ver `gui/perfiles_trabajo.py`.
        izq.caja.addWidget(separador())
        izq.caja.addWidget(Rotulo("perfil de trabajo", acento=True))
        self.selector_perfil = QComboBox()
        self.selector_perfil.setFont(idn.fuente_texto(12))
        izq.caja.addWidget(self.selector_perfil)
        fila_perfil = QHBoxLayout()
        fila_perfil.setSpacing(8)
        self.btn_aplicar_perfil = QPushButton("Aplicar perfil a todo el lote")
        fila_perfil.addWidget(self.btn_aplicar_perfil, 1)
        # Día 9 (continuación 14): hasta hoy `guardar_perfil` existía en
        # código pero nadie en la GUI lo llamaba — un perfil sólo se podía
        # montar a mano en Python. Ver `gui/dialogo_perfil.py`.
        self.btn_gestionar_perfiles = QPushButton("Gestionar…")
        self.btn_gestionar_perfiles.clicked.connect(self._gestionar_perfiles)
        fila_perfil.addWidget(self.btn_gestionar_perfiles, 0)
        izq.caja.addLayout(fila_perfil)
        self._refrescar_perfiles_disponibles()
        division.addWidget(izq)

        # --- derecha: plan y resultado ---
        der = QWidget()
        der.setMinimumWidth(330)
        col = QVBoxLayout(der)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)

        panel_plan = Panel(margenes=(14, 12, 14, 12))
        cab = QHBoxLayout()
        cab.addWidget(Rotulo("qué va a pasar", acento=True), 1)
        self.contador = Cifra("0 clips", px=12)
        cab.addWidget(self.contador, 0)
        panel_plan.caja.addLayout(cab)
        panel_plan.caja.addWidget(separador())
        # QTextBrowser y no un QLabel dentro de un QScrollArea: un QLabel con
        # texto enriquecido pide de ancho minimo el de su linea mas larga, y con
        # la barra horizontal apagada eso no se ve como una barra que falta, se
        # ve como texto cortado. Aqui el que envuelve y desplaza es el widget.
        self.texto_plan = QTextBrowser()
        self.texto_plan.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.texto_plan.setOpenExternalLinks(False)
        self.texto_plan.setMinimumWidth(0)
        panel_plan.caja.addWidget(self.texto_plan, 1)
        col.addWidget(panel_plan, 4)

        acciones = QHBoxLayout()
        acciones.setSpacing(10)
        self.btn_uno = QPushButton("Aplicar sólo a este clip")
        self.btn_lote = QPushButton("Aplicar al lote")
        self.btn_lote.setObjectName("primario")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_uno)
        acciones.addWidget(self.btn_lote)
        col.addLayout(acciones)

        self.panel_resultado = Panel(cristal=True, margenes=(14, 12, 14, 12))
        self.panel_resultado.caja.addWidget(Rotulo("resultado", acento=True))
        self.texto_resultado = QTextBrowser()
        self.texto_resultado.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.texto_resultado.setMinimumWidth(0)
        self.texto_resultado.setMinimumHeight(70)
        self.texto_resultado.setPlainText("Todavía no se ha aplicado nada.")
        self.panel_resultado.caja.addWidget(self.texto_resultado, 1)
        col.addWidget(self.panel_resultado, 2)

        division.addWidget(der)
        division.setStretchFactor(0, 2)
        division.setStretchFactor(1, 3)
        division.setSizes([340, 800])
        caja.addWidget(division, 1)

        self.btn_todos.clicked.connect(lambda: self._marcar_todos(True))
        self.btn_ninguno.clicked.connect(lambda: self._marcar_todos(False))
        self.lista.itemChanged.connect(lambda _: self.refrescar_plan())
        self.lista.currentRowChanged.connect(lambda _: self._estado_botones())
        self.btn_lote.clicked.connect(self._aplicar_lote)
        self.btn_uno.clicked.connect(self._aplicar_uno)
        self.btn_aplicar_perfil.clicked.connect(self._aplicar_perfil_de_trabajo)
        self.btn_preparar_nodos.clicked.connect(self._preparar_nodos_desde_plantilla)

        self._rellenar_lista()
        self._estado_look()
        self.refrescar_plan()

    # -- construccion ------------------------------------------------------

    def _rellenar_lista(self) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        for clip in self._estado.clips:
            it = QListWidgetItem(f"{clip.ref.index:03d}  {clip.nombre}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, clip.clip_id)
            it.setToolTip(f"{clip.clip_id} · {clip.nombre}\nconfianza {clip.match.confidence.level}")
            if clip.match.confidence.level == "baja":
                it.setForeground(idn.color(idn.BRAND_400))
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        if self.lista.count():
            self.lista.setCurrentRow(0)

    def _estado_look(self) -> None:
        """El QC del `.cube` que va al nodo 3, **antes** de escribirlo.

        Un LUT con problemas no se bloquea: se escribe si Mario quiere. Pero
        enterarse despues de haberlo puesto en 200 clips no es enterarse.
        """
        informe = self._estado.informe_lut
        if informe is None:
            self.texto_look.setText("Sin LUT de look: sólo se escribe el CDL del nodo 2.")
            self.texto_look.setStyleSheet("")
            return
        if informe.ok:
            self.texto_look.setText(f"QC: {informe.resumen()}")
            self.texto_look.setStyleSheet(f"color: {idn.rgba(idn.BRAND_50, idn.TEXTO_APAGADO_A)};")
            return
        lineas = [f"QC: {informe.resumen()}"]
        lineas += [f"· {p.mensaje}" for p in informe.problemas[:3]]
        if len(informe.problemas) > 3:
            lineas.append(f"· … y {len(informe.problemas) - 3} más")
        lineas.append("Se puede escribir igualmente; el aviso queda aquí.")
        self.texto_look.setText("\n".join(lineas))
        self.texto_look.setStyleSheet(f"color: {idn.BRAND_400};")

    def _marcar_todos(self, marcado: bool) -> None:
        self.lista.blockSignals(True)
        for i in range(self.lista.count()):
            self.lista.item(i).setCheckState(
                Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked
            )
        self.lista.blockSignals(False)
        self.refrescar_plan()

    # -- estado ------------------------------------------------------------

    def seleccionados(self) -> list[str]:
        return [
            self.lista.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.lista.count())
            if self.lista.item(i).checkState() == Qt.CheckState.Checked
        ]

    def clip_enfocado(self) -> str | None:
        it = self.lista.currentItem()
        return None if it is None else it.data(Qt.ItemDataRole.UserRole)

    def plan_actual(self) -> Plan:
        return construir_plan(self._estado, self.seleccionados())

    def refrescar_plan(self) -> None:
        plan = self.plan_actual()
        self._ultimo_plan = plan
        conectado = not plan.error_global
        self._banda(conectado, plan.error_global)
        self.contador.setText(f"{len(plan.aplicables)} de {len(self.seleccionados())} clips")
        self.texto_plan.setHtml(self._plan_a_html(plan))
        self._estado_botones(plan)

    def _banda(self, conectado: bool, error: str) -> None:
        if conectado:
            info = self._estado.puente.project_info()
            self.rotulo_banda.setText("resolve conectado")
            self.texto_banda.setText(
                f"{info.name} · {info.timeline_name} · {info.color_science} · "
                f"{info.resolve_version}"
            )
        else:
            self.rotulo_banda.setText("resolve desconectado")
            self.texto_banda.setText(error or "No hay conexión con DaVinci Resolve.")

    def _estado_botones(self, plan: Plan | None = None) -> None:
        """`plan=None` (llamado desde `currentRowChanged`) significa "sólo ha
        cambiado la fila con el foco, no lo que está marcado" — `btn_lote`
        depende de `seleccionados()` (las casillas), no del foco, así que se
        reutiliza `self._ultimo_plan` en vez de reconstruir el plan del lote
        entero. Antes de este arreglo, cada clic para mirar otro clip en la
        lista disparaba `construir_plan()` sobre TODOS los clips marcados
        (3 llamadas al puente por clip) sólo para decidir el estado de un
        botón que el foco ni siquiera afecta — con 200 clips marcados, unas
        600 llamadas a la API de Resolve por cada clic de navegación."""
        if plan is not None:
            self._ultimo_plan = plan
        hay = bool(self._ultimo_plan.aplicables)
        self.btn_lote.setEnabled(hay)
        enfocado = self.clip_enfocado()
        self.btn_uno.setEnabled(
            bool(enfocado) and any(linea.clip_id == enfocado and linea.puede
                                   for linea in construir_plan(self._estado,
                                                               [enfocado] if enfocado else []).lineas)
        )

    # -- pintar el plan ----------------------------------------------------

    def _plan_a_html(self, plan: Plan) -> str:
        cifra = ", ".join(f'"{f}"' for f in idn.FAMILIAS_CIFRA)
        apagado = idn.rgba(idn.BRAND_50, idn.TEXTO_APAGADO_A)
        if plan.error_global:
            return (
                f'<div style="color:{idn.BRAND_400};">{plan.error_global}</div>'
                f'<div style="color:{apagado}; margin-top:8px;">'
                f"No se puede aplicar nada mientras no haya conexión. "
                f"El plan y los números siguen aquí; no se pierde nada.</div>"
            )
        if not plan.lineas:
            return f'<div style="color:{apagado};">No hay ningún clip marcado.</div>'

        partes: list[str] = []
        nuevas = sum(1 for linea in plan.lineas if linea.puede and not linea.version_ya_existe)
        reusadas = sum(1 for linea in plan.lineas if linea.puede and linea.version_ya_existe)
        partes.append(
            f'<div style="color:{idn.BRAND_400};">'
            f"Se crea la versión <span style='font-family:{cifra};'>{VERSION_NAME}</span> "
            f"en {nuevas} clip(s) y se reutiliza en {reusadas}. "
            f"El grado original de cada clip se queda en su versión, intacto.</div><br>"
        )
        informe = self._estado.informe_lut
        if informe is not None and not informe.ok:
            partes.append(
                f'<div style="color:{idn.BRAND_400}; margin-bottom:10px;">'
                f"El look que va al nodo {NODE_LOOK} no pasa el QC: "
                f"{_escapar(informe.resumen())}</div>"
            )
        for linea in plan.lineas:
            if linea.puede:
                partes.append(
                    f'<div style="margin-bottom:10px;">'
                    f'<span style="font-family:{cifra}; color:{apagado};">{linea.clip_id}</span> '
                    f"<b>{_escapar(linea.nombre)}</b><br>"
                    f'<span style="color:{apagado};">· {linea.accion_version}; hoy está en '
                    f"<span style='font-family:{cifra};'>{_escapar(linea.version_actual)}</span>"
                    f"<br>· nodo {NODE_BALANCE} ← "
                    + "<br>&nbsp;&nbsp;".join(
                        f"<span style='font-family:{cifra};'>{_escapar(t)}</span>"
                        for t in linea.resumen_cdl
                    )
                    + f"<br>· nodo {NODE_LOOK} ← "
                    f"<span style='font-family:{cifra};'>{_escapar(linea.look_rel)}</span>"
                    f"<br>· nodo 1 (normalización): no se toca</span>"
                    + "".join(
                        f'<br><span style="color:{idn.BRAND_400};">· aviso: {_escapar(a)}</span>'
                        for a in linea.avisos
                    )
                    + "</div>"
                )
            else:
                partes.append(
                    f'<div style="margin-bottom:10px;">'
                    f'<span style="font-family:{cifra}; color:{apagado};">{linea.clip_id}</span> '
                    f"<b>{_escapar(linea.nombre)}</b><br>"
                    f'<span style="color:{idn.BRAND_400};">· NO SE PUEDE: '
                    f"{_escapar(linea.motivo)}</span></div>"
                )
        return "".join(partes)

    # -- aplicar -----------------------------------------------------------

    def _aplicar_lote(self) -> None:
        self._ejecutar([linea.clip_id for linea in self.plan_actual().aplicables])

    def _aplicar_uno(self) -> None:
        enfocado = self.clip_enfocado()
        if enfocado:
            self._ejecutar([enfocado])

    # -- perfil de trabajo (día 9, continuación 10) -------------------------

    def _refrescar_perfiles_disponibles(self) -> None:
        self.selector_perfil.clear()
        self.btn_gestionar_perfiles.setEnabled(self._perfiles_carpeta is not None)
        if self._perfiles_carpeta is None:
            self.selector_perfil.addItem("(sin carpeta de perfiles configurada)")
            self.selector_perfil.setEnabled(False)
            self.btn_aplicar_perfil.setEnabled(False)
            return
        nombres = listar_perfiles(self._perfiles_carpeta)
        if not nombres:
            self.selector_perfil.addItem("(no hay ningún perfil guardado todavía)")
            self.selector_perfil.setEnabled(False)
            self.btn_aplicar_perfil.setEnabled(False)
            return
        self.selector_perfil.setEnabled(True)
        self.btn_aplicar_perfil.setEnabled(True)
        for nombre in nombres:
            self.selector_perfil.addItem(nombre)

    def _gestionar_perfiles(self) -> None:
        if self._perfiles_carpeta is None:
            return
        dialogo = DialogoPerfiles(self._perfiles_carpeta, parent=self)
        dialogo.exec()
        self._refrescar_perfiles_disponibles()

    def _aplicar_perfil_de_trabajo(self) -> None:
        if self._perfiles_carpeta is None or not self.selector_perfil.isEnabled():
            return
        nombre = self.selector_perfil.currentText()
        try:
            perfil = cargar_perfil(self._perfiles_carpeta / nombre)
        except ErrorPerfil as exc:
            QMessageBox.warning(self, "Perfil de trabajo", f"No se ha podido cargar «{nombre}»: {exc}")
            return

        aplicar_perfil_a_estado(self._estado, perfil)

        # `ruta_look`/`texto_look` (arriba, columna izquierda) siguen
        # mostrando el look COMPARTIDO de todo el lote (`estado.look_rel`) —
        # es una cabecera de "el look de este lote", y con un perfil cada
        # clip puede tener el suyo propio. El PLAN de la derecha (`qué va a
        # pasar`) sí es exacto por clip (`LineaPlan.look_rel`); se avisa aquí
        # de la cabecera nada más, no de todo el panel.
        con_camara = sum(1 for c in self._estado.clips if c.look_rel is not None)
        self.texto_resultado.setPlainText(
            f"Perfil «{perfil.nombre}» aplicado: {con_camara} de {len(self._estado.clips)} "
            "clip(s) con ajuste de cámara propio; el resto usa el look compartido de siempre. "
            "El plan de la derecha ya muestra el LUT real de cada clip — la cabecera "
            "«look · nodo 3» de la izquierda sigue mostrando sólo el compartido."
        )
        self.refrescar_plan()

    def _preparar_nodos_desde_plantilla(self) -> None:
        plantilla = self.clip_enfocado()
        if plantilla is None:
            QMessageBox.warning(
                self, "Preparar nodos",
                "Enfoca en la lista el clip que ya tiene los 3 nodos preparados a mano.",
            )
            return
        destinos = [cid for cid in self.seleccionados() if cid != plantilla]
        if not destinos:
            QMessageBox.warning(
                self, "Preparar nodos",
                "Marca (con la casilla) al menos un clip destino distinto del enfocado.",
            )
            return
        try:
            resultado = copiar_grado_seguro(self._estado.puente, plantilla, destinos)
        except ResolveError as exc:
            QMessageBox.warning(self, "Preparar nodos", f"No se ha podido copiar la estructura: {exc}")
            return

        avisos = "; ".join(resultado.avisos) if resultado.avisos else "ninguno"
        self.texto_resultado.setPlainText(
            f"Estructura de nodos de «{plantilla}» copiada a {len(destinos)} clip(s): "
            f"{', '.join(destinos)}. Avisos: {avisos}. Revisa el plan — deberían dejar de "
            "salir bloqueados por número de nodos, y ya se puede aplicar de verdad."
        )
        self.refrescar_plan()

    def _ejecutar(self, clip_ids: list[str]) -> None:
        resultados = aplicar(self._estado, clip_ids)
        self.texto_resultado.setHtml(self._resultado_a_html(resultados))
        self.refrescar_plan()
        self.aplicado.emit()

    def _resultado_a_html(self, resultados: list[ResultadoClip]) -> str:
        cifra = ", ".join(f'"{f}"' for f in idn.FAMILIAS_CIFRA)
        apagado = idn.rgba(idn.BRAND_50, idn.TEXTO_APAGADO_A)
        if not resultados:
            return f'<div style="color:{apagado};">No se ha aplicado nada.</div>'
        bien = [r for r in resultados if r.ok]
        mal = [r for r in resultados if not r.ok]
        partes = [
            f'<div>Escrito en <span style="font-family:{cifra};">{len(bien)}</span> clip(s); '
            f'<span style="font-family:{cifra};">{len(mal)}</span> sin escribir.</div><br>'
        ]
        for r in mal:
            partes.append(
                f'<div style="margin-bottom:8px; color:{idn.BRAND_400};">'
                f'<span style="font-family:{cifra};">{r.clip_id or "—"}</span> '
                f"{_escapar(r.nombre)}<br>· {_escapar(r.mensaje)}</div>"
            )
        for r in bien:
            partes.append(
                f'<div style="margin-bottom:6px; color:{apagado};">'
                f'<span style="font-family:{cifra};">{r.clip_id}</span> '
                f"{_escapar(r.nombre)} → versión "
                f'<span style="font-family:{cifra};">{_escapar(r.version)}</span><br>'
                f"· {_escapar(r.mensaje)}"
                + "".join(f"<br>· aviso: {_escapar(a)}" for a in r.avisos)
                + "</div>"
            )
        return "".join(partes)


def _escapar(texto: str) -> str:
    return (
        str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


__all__ = [
    "LineaPlan",
    "PantallaAplicar",
    "Plan",
    "ResultadoClip",
    "aplicar",
    "construir_plan",
]
