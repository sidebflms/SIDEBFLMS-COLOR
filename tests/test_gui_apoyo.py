"""Apoyo comun de los tests de interfaz, y los tests DEL apoyo.

Los otros `test_gui_*.py` importan de aqui. Este fichero prueba ademas sus
propios detectores, que es lo que impide el fallo clasico de un test de
recorte de texto: **que no detecte nada y pase siempre**. Si
`linea_que_no_cabe()` deja de ver un texto cortado, se entera aqui y no en una
captura dentro de tres meses.

Nada de esto toca disco, ni red, ni Resolve. La GUI habla siempre con
`core.resolve.FakeResolve`.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import functools  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtGui import QFontDatabase, QFontMetrics  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QLabel, QWidget  # noqa: E402

from gui import datos_demo as dd  # noqa: E402
from gui import identidad as idn  # noqa: E402
from gui.ventana import VentanaPrincipal, crear_app  # noqa: E402
from gui.widgets import EtiquetaElidida  # noqa: E402

pytestmark = pytest.mark.gui

#: La anchura minima REAL de la ventana, medida (no elegida). Es la tercera
#: anchura de captura de `docs/IDENTIDAD.md` y la que se usa para buscar
#: recortes de texto.
#:
#: **Ha bajado de 985 a 973, y el alto ha subido de 643 a 651.** Las dos cosas
#: son consecuencia del dia 3, y ninguna se ha elegido a ojo:
#:
#: * **El ancho baja 12 px** porque las columnas de cifras de la tabla de clips
#:   han dejado de medirse por su cabecera. Las cinco columnas fijas ocupaban
#:   439 px de los 492 de la tabla y la del nombre se quedaba en 56 («A...a»);
#:   ahora ocupan 345, la tabla pide 480 y el nombre tiene sus 124 px
#:   garantizados a la anchura minima. Que la ventana pueda encoger MAS no es
#:   un efecto secundario molesto: es lo que sobra al dejar de pagar por unas
#:   cabeceras de tres palabras.
#: * **El alto sube 8 px** porque las cifras grandes vuelven a ser grandes. La
#:   hoja de estilo declaraba `font-size: 13px` en el selector `QWidget`, que
#:   casa con todo, y aplastaba los 22, 24 y 26 px a 13. Quien fija el alto es
#:   el panel de ingenieria inversa, que es el mas alto de los cuatro: pide 564
#:   px de los 651.
#:
#: Antes de esto fueron 966 (noche del 14) y 985 (dia 2). Cada vez que cambia,
#: cambian las capturas y cambia la documentacion: no se toca el numero aqui y
#: ya.
#:
#: Ademas, la anchura minima ya NO depende del estado: antes, con cero clips,
#: la tabla se escondia y la ventana se dejaba encoger hasta 911 px, y ahi si
#: se recortaba texto de verdad. Ver `gui/NOTAS.md`.
#:
#: **[dia 4] El ancho se queda en 973; el alto sube de 651 a 727.** No se ha
#: elegido. El panel de ingenieria inversa ensena ahora las cifras que deciden
#: (el ΔE2000 maximo con su margen al limite, y la cobertura del cubo al mismo
#: tamano que la reproducibilidad) y una linea de lo que significa la
#: cobertura, en un panel propio encima del mapa. Para pagarlo se bajaron los
#: altos minimos de los dos mapas (170 -> 120 y 110 -> 90), la leyenda del mapa
#: paso de tres lineas a dos y la marca de limite se puso en la fila del
#: rotulo. Ademas el alto se mide ahora a la anchura minima y no en la ventana
#: de 1440, porque a 973 px el texto parte en mas lineas: medido como antes
#: saldria 713, y seria un minimo que la pantalla no cumple.
ANCHURA_MINIMA = 973
ALTO_MINIMO = 727


# ---------------------------------------------------------------------------
# QApplication y ventanas
# ---------------------------------------------------------------------------


def app_qt():
    """La `QApplication` del proceso, con la hoja de estilo puesta.

    `crear_app` reutiliza la instancia si ya existe, asi que se puede llamar
    desde cualquier test sin llevar la cuenta de quien la creo.
    """
    return crear_app([])


def asentar(veces: int = 4) -> None:
    """Deja que Qt termine layouts y repintados.

    Las mismas tres pasadas que usa `gui/capturas.py`, y por el mismo motivo:
    el primer `processEvents` resuelve el layout, el segundo los `resizeEvent`
    que re-eliden el texto y el tercero el repintado. Con una sola pasada se
    mide el texto de la anchura ANTERIOR, que es medir mentiras.
    """
    app = app_qt()
    for _ in range(veces):
        app.processEvents()


def ventana(estado=None, *, ancho: int = 1440, alto: int = 900, par=None) -> VentanaPrincipal:
    """Una `VentanaPrincipal` mostrada y asentada. Cierrala tu."""
    app_qt()
    v = VentanaPrincipal(estado if estado is not None else demo(), par_inverso=par)
    v.resize(ancho, alto)
    v.show()
    # `isVisible()` de un descendiente depende de que la VENTANA de nivel
    # superior ya este expuesta de verdad por la plataforma (offscreen
    # incluido) -- un numero fijo de `processEvents()` normalmente alcanza,
    # pero bajo carga de CPU (varios tests de GUI seguidos, uno de ellos
    # "lento") puede no haber dado tiempo. `qWaitForWindowExposed` es la
    # espera correcta de Qt para esto: bombea el bucle de eventos hasta que
    # la exposicion ocurre de verdad, en vez de contar una cifra fija de
    # pasadas y cruzar los dedos. Sospechoso de un fallo intermitente visto
    # el dia 9 en `test_gui_estados.py` (`isVisible()` en falso justo
    # despues de `ventana()`) -- ver BITACORA.md.
    QTest.qWaitForWindowExposed(v)
    asentar()
    return v


def redimensionar(v: VentanaPrincipal, ancho: int, alto: int) -> None:
    v.resize(ancho, alto)
    asentar()


# ---------------------------------------------------------------------------
# Estados de demostracion, cacheados
# ---------------------------------------------------------------------------
#
# Construir un estado cuesta entre 0,1 y 6 segundos porque se empareja de
# VERDAD con los pixeles del generador. Los estados que solo se leen se cachean;
# el que se escribe (el de la regla de oro) se construye entero cada vez, para
# que un test no vea las escrituras del anterior.


demo = functools.cache(dd.estado_demo)
vacio = functools.cache(dd.estado_vacio)
un_clip = functools.cache(dd.estado_un_clip)
confianza_baja = functools.cache(dd.estado_confianza_baja)
lut_malo = functools.cache(dd.estado_lut_malo)
par_inverso = dd.par_ingenieria_inversa  # ya viene cacheado


@functools.cache
def muchos():
    """Doscientos clips. Seis segundos de emparejamiento: se cachea o no acaba."""
    return dd.estado_muchos(200)


def desconectado():
    """Resolve caido. NO se cachea: `estado_demo()` cacheado se desconectaria."""
    est = dd.estado_demo()
    est.puente.desconectar()
    return est


# ---------------------------------------------------------------------------
# Tipografia
# ---------------------------------------------------------------------------


def tipografias_de_marca_instaladas() -> list[str]:
    """Cuales de las tres familias de marca existen en esta maquina.

    Importa para los tests que fijan un numero de pixeles: si Mario instala
    Inter, Chakra Petch y JetBrains Mono, las metricas cambian y la anchura
    minima de la ventana deja de ser 973. No es un fallo, es otra tipografia.
    """
    app_qt()  # sin QApplication, QFontDatabase aborta el proceso entero
    familias = set(QFontDatabase.families())
    return [f for f in ("Inter", "Chakra Petch", "JetBrains Mono") if f in familias]


def es_monoespaciada(fuente) -> bool:
    """¿Esta fuente pinta todas las letras del mismo ancho?

    Se mide, no se pregunta por el nombre: `QFont.families()` dice lo que se
    ha PEDIDO y `fixedPitch()` no siempre viene relleno. Si `iiii` y `MMMM`
    miden lo mismo, es monoespaciada y punto.
    """
    m = QFontMetrics(fuente)
    return m.horizontalAdvance("iiii") == m.horizontalAdvance("MMMM")


# ---------------------------------------------------------------------------
# Detectores de texto cortado
# ---------------------------------------------------------------------------


def etiquetas_visibles(raiz: QWidget) -> list[QLabel]:
    """Todos los `QLabel` visibles con texto dentro de `raiz`."""
    return [
        lab
        for lab in raiz.findChildren(QLabel)
        if lab.isVisible() and lab.text().strip()
    ]


def esta_elidida(lab: QLabel) -> bool:
    """¿Esta etiqueta esta ensenando el texto recortado con «...»?

    Solo tiene sentido en una `EtiquetaElidida`: un `QLabel` normal **no elide
    nunca**, se come el texto en silencio (por eso hace falta el otro
    detector).
    """
    return isinstance(lab, EtiquetaElidida) and lab.text() != lab.texto_completo()


def linea_que_no_cabe(lab: QLabel) -> str | None:
    """La primera linea de un `QLabel` normal que NO cabe en su ancho.

    Devuelve `None` si todo cabe. Es el detector del corte silencioso: un
    `QLabel` sin `EtiquetaElidida` detras no pone puntos suspensivos, no pone
    tooltip y no avisa; simplemente pinta hasta donde llega.

    Dos modos, porque Qt tiene dos:

    * sin `wordWrap`: cada linea entera tiene que caber en el ancho util;
    * con `wordWrap`: Qt parte por espacios pero **no parte una palabra**, asi
      que lo que tiene que caber es la palabra mas larga. Una ruta larga o un
      numero largo en una etiqueta con `wordWrap` se corta igual.

    Se mide contra `contentsRect()` y no contra `width()`: con margenes
    puestos, `width()` se pasa por lo que midan los margenes.
    """
    texto = lab.text()
    if not texto.strip():
        return None
    disponible = lab.contentsRect().width()
    metricas = QFontMetrics(lab.font())
    if lab.wordWrap():
        for palabra in texto.replace("\n", " ").split(" "):
            if palabra and metricas.horizontalAdvance(palabra) > disponible:
                return palabra
        return None
    for linea in texto.split("\n"):
        if metricas.horizontalAdvance(linea) > disponible:
            return linea
    return None


# ---------------------------------------------------------------------------
# Tests DEL apoyo: que los detectores detectan
# ---------------------------------------------------------------------------


def test_el_detector_de_corte_ve_un_qlabel_estrecho():
    """Un `QLabel` normal al que no le cabe el texto tiene que salir cazado."""
    app_qt()
    lab = QLabel("una frase que desde luego no cabe en cuarenta pixeles")
    lab.setFont(idn.fuente_texto(13))
    lab.resize(40, 20)
    assert linea_que_no_cabe(lab) is not None


def test_el_detector_de_corte_no_se_inventa_nada():
    app_qt()
    lab = QLabel("cabe")
    lab.setFont(idn.fuente_texto(13))
    lab.resize(400, 20)
    assert linea_que_no_cabe(lab) is None


def test_el_detector_de_corte_mira_los_margenes_y_no_el_width():
    """Con margenes, `width()` miente y `contentsRect()` no.

    Este es el bug real de la noche del 14: el texto se recortaba contra
    `width()` y salia cortado a lo bruto justo en el borde.
    """
    app_qt()
    lab = QLabel("doce letras")
    lab.setFont(idn.fuente_texto(13))
    ancho_justo = QFontMetrics(lab.font()).horizontalAdvance("doce letras") + 2
    lab.resize(ancho_justo, 20)
    assert linea_que_no_cabe(lab) is None
    lab.setContentsMargins(20, 0, 20, 0)
    assert linea_que_no_cabe(lab) is not None


def test_el_detector_de_corte_caza_una_palabra_larga_con_wordwrap():
    """`wordWrap` no parte palabras: una ruta larga se corta igual."""
    app_qt()
    lab = QLabel("ruta: /Library/Application_Support/Blackmagic_Design/LUT")
    lab.setFont(idn.fuente_texto(13))
    lab.setWordWrap(True)
    lab.resize(80, 200)
    assert linea_que_no_cabe(lab) is not None


def test_el_detector_de_elision_ve_una_etiqueta_elidida():
    app_qt()
    lab = EtiquetaElidida("un nombre de clip larguisimo que no va a caber ni de broma")
    lab.setFont(idn.fuente_texto(13))
    lab.show()
    lab.resize(60, 20)
    asentar()
    assert esta_elidida(lab)
    assert lab.text() != lab.texto_completo()
    assert lab.toolTip() == lab.texto_completo()


def test_el_detector_de_elision_no_marca_lo_que_cabe():
    app_qt()
    lab = EtiquetaElidida("corto")
    lab.setFont(idn.fuente_texto(13))
    lab.show()
    lab.resize(400, 20)
    asentar()
    assert not esta_elidida(lab)
    assert lab.toolTip() == ""


def test_es_monoespaciada_distingue_de_verdad():
    app_qt()
    assert es_monoespaciada(idn.fuente_cifra(13))
    assert not es_monoespaciada(idn.fuente_texto(13))


def test_la_ventana_de_apoyo_se_construye_contra_el_falso():
    from core.resolve import FakeResolve

    v = ventana()
    try:
        assert isinstance(demo().puente, FakeResolve)
        assert v.isVisible()
    finally:
        v.close()
