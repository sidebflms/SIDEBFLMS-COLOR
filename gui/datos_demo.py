"""Material de prueba para las capturas y los tests de la GUI.

**Cero material real.** Todo sale de `tests/media/generate.py`, que es el
generador del orquestador. Aqui no se abre un fichero de `/Volumes`, ni de `~`,
ni de ningun sitio: las imagenes se calculan.

Tampoco se inventan resultados. Los `MatchResult` que ven las pantallas salen de
`core.matching.emparejar` con los pixeles de verdad, la confianza es la que
calcula `core.matching`, y el LUT pasa por `core.io.qc_lut` de verdad. Si un
numero sale feo en una captura es porque es el numero que sale.

LOS ESTADOS QUE HAY, Y POR QUE
------------------------------
Uno por cada caso frontera del encargo:

| Constructor | Caso |
|---|---|
| `estado_demo()` | el caso nominal, con un nombre de clip larguisimo y un desajuste de contenido de verdad |
| `estado_vacio()` | cero clips |
| `estado_un_clip()` | un clip |
| `estado_muchos()` | doscientos clips |
| `estado_confianza_baja()` | confianza baja en todos |
| `estado_desconectado()` | Resolve «desconectado» |
| `estado_lut_malo()` | un LUT que no pasa el QC |
| `reverse_de_demostracion()` | el par original/coloreado del panel de ingenieria inversa |
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

import numpy as np

from core.color import to_working
from core.contracts import (
    CDL,
    LUT3D,
    LUT_SIZE_DEFAULT,
    ClipRef,
    Confidence,
    MatchResult,
    ResolveBridge,
)
from core.io import catalogo_luts_malos, qc_lut
from core.io.qc import LUTQualityReport
from core.matching import desajuste_de_contenido, emparejar
from core.resolve import FakeResolve
from tests.media import generate as gen

#: Ruta RELATIVA del look dentro de la carpeta de LUTs de Resolve. Relativa
#: porque `SetLUT` se traga una absoluta sin protestar y luego el nodo se queda
#: sin LUT (ver `core.resolve.bridge.validar_ruta_lut_relativa`).
LOOK_REL = "SIDEB/SIDEB COLOR look.cube"

#: Submuestreo de las imagenes antes de emparejar. 640x360 entero tarda 0,15 s
#: por clip; con `[::4, ::4]` son 0,08 s y el CDL sale igual hasta el cuarto
#: decimal, porque el emparejamiento compara DISTRIBUCIONES, no pixel con pixel.
PASO_EMPAREJAR = 4
PASO_EMPAREJAR_LOTE = 8


# ---------------------------------------------------------------------------
# Escenas
# ---------------------------------------------------------------------------


@functools.cache
def _estudio(indice_piel: int, ev: float = 0.0) -> np.ndarray:
    """Retrato de estudio en espacio de trabajo. Cacheado: es determinista."""
    return to_working(gen.studio_scene(skin_tone_index=indice_piel, key_ev=ev).image, "linear_rec709")


@functools.cache
def _exterior() -> np.ndarray:
    return to_working(gen.exterior_scene().image, "linear_rec709")


def _px(img: np.ndarray, paso: int) -> np.ndarray:
    return np.ascontiguousarray(img[::paso, ::paso].reshape(-1, 3))


# ---------------------------------------------------------------------------
# Un clip de la sesion
# ---------------------------------------------------------------------------


@dataclass
class ClipDemo:
    """Un clip tal y como lo ven las pantallas."""

    ref: ClipRef
    match: MatchResult
    original: np.ndarray | None = None  # (h, w, 3) en espacio de trabajo
    razones_desajuste: tuple[str, ...] = ()
    #: Día 9 (continuación 10): ruta RELATIVA de un LUT de look propio de
    #: ESTE clip, para cuando distintos clips del mismo lote necesitan un
    #: nodo 3 distinto (p.ej. `core.perfiles`: cada cámara de un perfil de
    #: trabajo hornea su propio ajuste + el look compartido en un LUT
    #: propio). `None` = usa `EstadoDemo.look_rel`, el de siempre.
    look_rel: str | None = None

    @property
    def clip_id(self) -> str:
        return self.ref.clip_id

    @property
    def nombre(self) -> str:
        return self.ref.name

    def despues(self) -> np.ndarray | None:
        """El clip con su CDL puesto. Es el «despues» de la comparacion.

        No es una simulacion de Resolve: es **el mismo `CDL.apply()`** del
        contrato, que es exactamente la formula que Resolve ejecuta en el nodo 2.
        """
        if self.original is None:
            return None
        return self.match.cdl.apply(self.original).astype(np.float32)


@dataclass
class EstadoDemo:
    """Todo lo que una pantalla necesita para dibujarse.

    `puente` es un `ResolveBridge` cualquiera — pese al nombre de la clase
    (que sigue reflejando el uso original, sólo datos de demostración), desde
    `gui/estado_real.py` (día 9) este mismo tipo también envuelve una
    conexión real a `LiveResolve`. Nada de la GUI mira el tipo concreto, sólo
    llama a lo que `ResolveBridge` promete.
    """

    clips: list[ClipDemo]
    puente: ResolveBridge
    referencia_id: str | None = None
    look: LUT3D | None = None
    look_rel: str = LOOK_REL
    informe_lut: LUTQualityReport | None = None
    referencia_img: np.ndarray | None = None
    notas: tuple[str, ...] = field(default_factory=tuple)

    def por_id(self, clip_id: str) -> ClipDemo | None:
        for c in self.clips:
            if c.clip_id == clip_id:
                return c
        return None


# ---------------------------------------------------------------------------
# Construccion
# ---------------------------------------------------------------------------


def _ref(i: int, nombre: str) -> ClipRef:
    return ClipRef(
        clip_id=f"clip{i:03d}",
        name=nombre,
        track=1,
        index=i,
        start_frame=(i - 1) * 120,
        end_frame=(i - 1) * 120 + 119,
        file_path=None,  # no hay material real y no lo va a haber
    )


def _clip(i: int, nombre: str, img: np.ndarray, referencia: np.ndarray, *,
          paso: int = PASO_EMPAREJAR, guardar_imagen: bool = True) -> ClipDemo:
    match = emparejar(_px(img, paso), _px(referencia, paso))
    razones: tuple[str, ...] = ()
    if match.content_mismatch:
        _, _, razones = desajuste_de_contenido(img, referencia)
    return ClipDemo(
        ref=_ref(i, nombre),
        match=match,
        original=img if guardar_imagen else None,
        razones_desajuste=razones,
    )


def look_de_demostracion(tam: int = LUT_SIZE_DEFAULT) -> LUT3D:
    """Un look de verdad: un CDL calido y contrastado horneado en una rejilla.

    Se hornea con `CDL.apply()` sobre la rejilla identidad, o sea que el `.cube`
    resultante hace en el nodo 3 exactamente lo que haria ese CDL. Sirve para
    que el QC tenga algo real que mirar.
    """
    base = LUT3D.identity(tam)
    cdl = CDL(slope=(0.98, 0.95, 0.90), offset=(0.004, 0.0, 0.010),
              power=(1.02, 1.0, 0.97), saturation=1.06)
    # El recorte a 0..1 NO es una manera de que el QC pase: un `.cube` es una
    # tabla de salida y la saturacion por encima de 1 se sale del cubo por los
    # dos lados. Un look que no recorta arrastra valores fuera de gamut que
    # Resolve va a recortar igual al mostrarlos, asi que se recorta aqui, donde
    # se ve. `qc_lut` lo confirma: sin recorte avisa de 4.060 valores fuera de
    # gamut, y son reales.
    tabla = np.clip(cdl.apply(base.table), 0.0, 1.0).astype(np.float32)
    return LUT3D(table=tabla, title="SIDEB COLOR look")


def _puente(clips: list[ClipDemo], *, conectado: bool = True, nodos: int = 3) -> FakeResolve:
    return FakeResolve(
        clips=[c.ref for c in clips],
        nodos_por_clip=nodos,
        conectado=conectado,
        project_name="SIDEB · DEMO",
        timeline_name="TL 01 MONTAJE",
    )


NOMBRE_LARGO = (
    "A001_C014_20260915_SIDEBFILMS_entrevista_pasillo_segunda_toma_"
    "con_ventana_detras_y_reflejo_en_el_cristal_TOMA_04_v3_FINAL"
)


def estado_demo() -> EstadoDemo:
    """El caso nominal: seis clips, uno con nombre larguisimo y uno cruzado.

    El clip 5 es el exterior comparado contra el retrato de estudio: son
    deliberadamente incomparables, asi que `content_mismatch` sale True de
    verdad y la pantalla tiene que ensenarlo.
    """
    referencia = _estudio(2)
    entradas = [
        (1, "A001_C001_maestro_referencia", _estudio(2)),
        (2, "A001_C002_contraplano", _estudio(4)),
        (3, "A001_C003_plano_corto", _estudio(1, ev=0.6)),
        (4, NOMBRE_LARGO, _estudio(5, ev=-0.4)),
        (5, "B002_C001_exterior_calle", _exterior()),
        (6, "A001_C004_recurso_manos", _estudio(0, ev=0.3)),
        # Casi tres pasos por encima de la referencia: el ajuste sale, pero la
        # nota baja a MEDIA. Esta a proposito para que en una sola captura se
        # vean las tres formas de confianza (relleno, contorno, discontinuo).
        (7, "A001_C005_plano_ventana", _estudio(5, ev=1.8)),
    ]
    clips = [_clip(i, n, img, referencia) for i, n, img in entradas]
    look = look_de_demostracion()
    return EstadoDemo(
        clips=clips,
        puente=_puente(clips),
        referencia_id="clip001",
        referencia_img=referencia,
        look=look,
        informe_lut=qc_lut(look),
        notas=("referencia: clip001 · A001_C001_maestro_referencia",),
    )


def estado_vacio() -> EstadoDemo:
    """Cero clips. El timeline esta abierto pero no hay nada seleccionado."""
    look = look_de_demostracion()
    return EstadoDemo(clips=[], puente=_puente([]), referencia_id=None,
                      look=look, informe_lut=qc_lut(look))


def estado_un_clip() -> EstadoDemo:
    """Un clip, que ademas es su propia referencia: el CDL sale casi identidad."""
    referencia = _estudio(2)
    clips = [_clip(1, "A001_C001_unico", _estudio(3), referencia)]
    look = look_de_demostracion()
    return EstadoDemo(clips=clips, puente=_puente(clips), referencia_id="clip001",
                      referencia_img=referencia, look=look, informe_lut=qc_lut(look))


def estado_muchos(n: int = 200) -> EstadoDemo:
    """Doscientos clips. Sin guardar las imagenes: no caben y no hacen falta.

    Las pantallas que necesitan imagen (la comparacion) tienen que aguantar un
    clip sin imagen y decirlo, en vez de reventar.
    """
    referencia = _estudio(2)
    variantes = [(_estudio(i % 6, ev=(i % 7 - 3) * 0.25)) for i in range(6 * 7)]
    clips = []
    for i in range(1, n + 1):
        img = variantes[i % len(variantes)]
        nombre = NOMBRE_LARGO if i % 37 == 0 else f"A{1 + i // 60:03d}_C{i:03d}_toma"
        clips.append(_clip(i, nombre, img, referencia, paso=PASO_EMPAREJAR_LOTE,
                           guardar_imagen=(i <= 3)))
    look = look_de_demostracion()
    return EstadoDemo(clips=clips, puente=_puente(clips), referencia_id="clip001",
                      referencia_img=referencia, look=look, informe_lut=qc_lut(look))


def estado_confianza_baja() -> EstadoDemo:
    """Confianza baja en todos: cada clip se empareja contra una escena que no
    tiene nada que ver. No se trucan las notas; se eligen pares malos."""
    referencia = _exterior()
    entradas = [
        (1, "A001_C001_interior_noche", _estudio(0, ev=-1.2)),
        (2, "A001_C002_interior_dia", _estudio(3, ev=0.9)),
        (3, "A001_C003_primer_plano", _estudio(5, ev=-0.7)),
        (4, NOMBRE_LARGO, _estudio(1, ev=1.1)),
    ]
    clips = [_clip(i, n, img, referencia) for i, n, img in entradas]
    look = look_de_demostracion()
    return EstadoDemo(clips=clips, puente=_puente(clips), referencia_id=None,
                      referencia_img=referencia, look=look, informe_lut=qc_lut(look))


def estado_desconectado() -> EstadoDemo:
    """Resolve cerrado a media faena. La GUI tiene que decirlo y no dejar aplicar."""
    est = estado_demo()
    est.puente.desconectar()
    return est


def estado_lut_malo() -> EstadoDemo:
    """Un look que NO pasa el QC. Sale del catalogo de LUT rotos de `core.io`."""
    est = estado_demo()
    catalogo = catalogo_luts_malos(size=17)
    malo = catalogo["no_monotono"] if "no_monotono" in catalogo else next(iter(catalogo.values()))
    est.look = malo
    est.informe_lut = qc_lut(malo)
    return est


@functools.cache
def parches_carta() -> np.ndarray:
    """Los 24 parches del ColorChecker, un color por parche, en trabajo.

    Se usan en el editor de CDL para ver que hace un numero. Salen del
    generador, no de una tabla copiada de internet: se mide el centro de cada
    parche de la carta sintetica.
    """
    carta = to_working(gen.colorchecker(), "linear_rec709")
    alto, ancho = carta.shape[:2]
    ph, pw = alto / 4, ancho / 6
    colores = []
    for f in range(4):
        for c in range(6):
            y, x = int((f + 0.5) * ph), int((c + 0.5) * pw)
            colores.append(carta[y, x])
    return np.asarray(colores, dtype=np.float32)


#: El grado que se esconde en el par de ingenieria inversa. Se deja publico a
#: proposito: el panel tiene que poder compararse contra la verdad conocida.
#: Ojo con los numeros: el CDL se aplica en el ESPACIO DE TRABAJO, que es
#: logaritmico. Un `slope` de 1.10 ahi no es «un 10% mas de ganancia», es un
#: cambio de contraste enorme; la primera version de este grado dejaba la cara
#: naranja fosforito. Estos valores son los de un look calido normalito.
GRADO_OCULTO = CDL(slope=(1.030, 1.000, 0.968), offset=(0.006, 0.0, 0.012),
                   power=(0.985, 1.0, 1.020), saturation=1.07)


@functools.cache
def par_ingenieria_inversa(*, con_vineta: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """El par original/coloreado del panel 4.

    El «coloreado» es el original con `GRADO_OCULTO` **y una vineta**. La vineta
    es lo que hace que el caso sea interesante: depende de DONDE esta el pixel,
    o sea que un `.cube` no se la puede llevar, y el diagnostico tiene que
    decirlo. Sin ella el panel saldria siempre «es un LUT puro» y no se veria si
    el diagnostico funciona.
    """
    original = _estudio(2)
    coloreado = GRADO_OCULTO.apply(original).astype(np.float32)
    if con_vineta:
        coloreado = gen.apply_vignette(coloreado, strength=0.35)
    return original, coloreado.astype(np.float32)


def match_con_desajuste_y_confianza_alta() -> MatchResult:
    """Un `MatchResult` con `content_mismatch=True` y confianza ALTA.

    No sale de `emparejar` y no puede salir: `puntuar_confianza` penaliza el
    desajuste con un factor de 0,35, asi que por ese camino nunca hay un
    desajuste con nota alta. Pero **el contrato dice que la GUI tiene que
    ensenar el desajuste aunque la confianza salga alta** (CONTRATOS.md,
    `MatchResult`), y eso hay que poder probarlo. Asi que se construye la
    dataclass del contrato a mano, que es justo para lo que esta.
    """
    return MatchResult(
        cdl=CDL(slope=(1.04, 1.0, 0.96), offset=(0.002, 0.0, 0.004), power=(0.98, 1.0, 1.02)),
        lut=None,
        confidence=Confidence(
            score=0.92,
            level="alta",
            reasons=("El ajuste es firme: hay muestras de sobra y el residuo es pequeno.",),
            metrics={"solape": 0.94, "residuo_de": 0.6},
        ),
        delta_e_before=4.1,
        delta_e_after=0.7,
        content_mismatch=True,
        notes=("el numero es bueno pero las dos escenas no son la misma",),
    )


__all__ = [
    "LOOK_REL",
    "NOMBRE_LARGO",
    "PASO_EMPAREJAR",
    "PASO_EMPAREJAR_LOTE",
    "ClipDemo",
    "EstadoDemo",
    "estado_confianza_baja",
    "estado_demo",
    "estado_desconectado",
    "estado_lut_malo",
    "estado_muchos",
    "estado_un_clip",
    "estado_vacio",
    "GRADO_OCULTO",
    "look_de_demostracion",
    "par_ingenieria_inversa",
    "parches_carta",
    "match_con_desajuste_y_confianza_alta",
]
