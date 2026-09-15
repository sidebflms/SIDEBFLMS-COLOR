"""Que no se recorte texto a la anchura minima real de la ventana.

**Este es el test que mas importa de todo el paquete.** El recorte de texto al
redimensionar es el fallo recurrente de la app hermana de ingest, y la noche
del 14 aparecieron dos casos aqui: a 966 px los rotulos del editor de CDL
salian «SLO...», «OFF...», «PO...», «SAT...», y el pie del carril salia
«escribe en «SIDEB COL...». Los dos estan arreglados; esto es lo que impide
que vuelvan.

EL CRITERIO, QUE ES LA PARTE DIFICIL
------------------------------------
`EtiquetaElidida` **si** puede recortar a proposito: es lo que evita que un
nombre de clip de 120 caracteres deje la ventana sin poder encogerse. Asi que
el test tiene que distinguir «esto elide por diseno» de «esto elide porque no
cabe». El criterio que se ha elegido, y esta razonado en `gui/NOTAS.md`, son
tres reglas:

1. **Un `Rotulo` no elide nunca.** Los rotulos son el vocabulario fijo de la
   app: los escribe la app, son cortos, y estan puestos para decir que es cada
   cosa. Si un rotulo cabe recortado no informa de nada («SLO...» no es
   «slope»). Como `Rotulo` hereda de `EtiquetaElidida`, la capacidad de elidir
   esta ahi y esto es lo que la vigila.
2. **Una `EtiquetaElidida` que no es rotulo si puede elidir**, porque lo que
   lleva es CONTENIDO de longitud desconocida (nombres de clip, rutas, el
   resumen del proyecto). Pero con dos condiciones que tambien se comprueban:
   el texto entero tiene que seguir estando en el tooltip, y lo que se ve
   tiene que ser un trozo util (>= 12 caracteres), no «A...».
3. **Un `QLabel` normal no puede quedarse corto.** Un `QLabel` a secas **no
   elide**: se come lo que no le cabe sin puntos suspensivos, sin tooltip y sin
   avisar. Asi que para esos la regla es que el texto quepa entero. Es la regla
   que caza el caso del pie del carril.

El detector de las reglas 1 y 3 se prueba a si mismo en
`tests/test_gui_apoyo.py`, y aqui hay ademas un control negativo
(`test_el_test_falla_si_un_rotulo_se_recorta`) que estropea la interfaz a
proposito para comprobar que el test lo caza. Un test de recorte que no se
puede hacer fallar no vale nada.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from gui.pantalla_clips import COL_NOMBRE  # noqa: E402
from gui.widgets import EtiquetaElidida, Rotulo  # noqa: E402
from tests.test_gui_apoyo import (  # noqa: E402
    ALTO_MINIMO,
    ANCHURA_MINIMA,
    confianza_baja,
    demo,
    desconectado,
    esta_elidida,
    etiquetas_visibles,
    linea_que_no_cabe,
    lut_malo,
    muchos,
    redimensionar,
    tipografias_de_marca_instaladas,
    un_clip,
    vacio,
    ventana,
)

pytestmark = pytest.mark.gui

#: Cuantos caracteres tiene que quedar viendose de una etiqueta que elide para
#: que siga informando de algo. Con menos, el recorte no es «se ve el principio»
#: sino «no se ve nada».
MINIMO_UTIL = 12


def revisar(v, *, donde: str) -> list[str]:
    """Todos los problemas de texto de la ventana tal y como esta ahora."""
    problemas: list[str] = []
    for lab in etiquetas_visibles(v):
        nombre = f"{donde} · {type(lab).__name__}#{lab.objectName() or '-'}"
        if isinstance(lab, Rotulo):
            if esta_elidida(lab):
                problemas.append(
                    f"{nombre}: el rotulo {lab.texto_completo()!r} sale recortado como "
                    f"{lab.text()!r}. Un rotulo no puede elidir: es vocabulario fijo."
                )
            corte = linea_que_no_cabe(lab)
            if corte is not None:
                problemas.append(
                    f"{nombre}: el rotulo {lab.texto_completo()!r} no cabe en "
                    f"{lab.contentsRect().width()} px ({corte!r})."
                )
        elif isinstance(lab, EtiquetaElidida):
            if not esta_elidida(lab):
                continue
            visible = lab.text().rstrip("…. ")
            if len(visible) < MINIMO_UTIL:
                problemas.append(
                    f"{nombre}: elide hasta {lab.text()!r}, que ya no informa de nada "
                    f"(minimo {MINIMO_UTIL} caracteres)."
                )
            if lab.toolTip() != lab.texto_completo():
                problemas.append(
                    f"{nombre}: elide {lab.texto_completo()!r} y el texto entero NO esta "
                    f"en el tooltip, o sea que se pierde."
                )
        else:
            corte = linea_que_no_cabe(lab)
            if corte is not None:
                problemas.append(
                    f"{nombre}: un QLabel normal no elide, y {corte!r} no cabe en "
                    f"{lab.contentsRect().width()} px. Se corta en silencio."
                )
    return problemas


def _estados():
    return [
        ("nominal", demo(), None),
        ("cero clips", vacio(), None),
        ("un clip", un_clip(), None),
        ("doscientos clips", muchos(), None),
        ("confianza baja", confianza_baja(), None),
        ("resolve desconectado", desconectado(), None),
        ("lut que no pasa el qc", lut_malo(), None),
    ]


# ---------------------------------------------------------------------------
# La anchura minima
# ---------------------------------------------------------------------------


def test_la_anchura_minima_real_es_la_medida():
    """El numero de la tercera captura de cada pantalla.

    **966 la noche del 14, 985 el dia 2, 973 x 651 hoy.** Ninguno de los tres
    se ha elegido: los tres son lo que contesta el contenido. El porque de este
    ultimo cambio esta entero en `ANCHURA_MINIMA` (ancho: las columnas de
    cifras de la tabla han dejado de medirse por su cabecera; alto: las cifras
    grandes vuelven a ser grandes).

    Si esto vuelve a cambiar, cambian las capturas y cambia la documentacion:
    no se toca el numero aqui y ya. Se salta si Mario ha instalado las
    tipografias de marca, porque entonces las metricas son otras (no es un
    fallo, es otra tipografia).
    """
    instaladas = tipografias_de_marca_instaladas()
    if instaladas:
        pytest.skip(
            f"con {', '.join(instaladas)} instalada(s) las metricas cambian y la anchura "
            f"minima ya no es la medida con las alternativas"
        )
    v = ventana(demo())
    try:
        assert v.anchura_minima() == ANCHURA_MINIMA
        assert v.minimumSizeHint().width() == ANCHURA_MINIMA
        assert v.minimumSizeHint().height() == ALTO_MINIMO
    finally:
        v.close()


def test_la_ventana_se_puede_encoger_hasta_su_minimo_de_verdad():
    """Pedir 600 px y quedarse en su minimo es lo correcto; quedarse en 1200 no.

    Se compara contra lo que conteste `anchura_minima()`, no contra la constante,
    para que este test siga diciendo la verdad el dia que el minimo cambie.
    """
    v = ventana(demo())
    try:
        minimo = v.anchura_minima()
        redimensionar(v, 600, 400)
        assert v.width() >= minimo
        assert v.width() <= minimo + 2, (
            f"la ventana no baja de {v.width()} px aunque su minimo dice {minimo}"
        )
    finally:
        v.close()


# ---------------------------------------------------------------------------
# El test de verdad
# ---------------------------------------------------------------------------


def test_ninguna_etiqueta_se_recorta_a_la_anchura_minima():
    """Las cuatro pantallas, en siete estados, a la anchura minima REAL.

    Se usa la anchura que Qt dice (`anchura_minima()`), no la constante: si
    manana alguien mete un widget que empuja el minimo a 1020, este test tiene
    que seguir mirando el recorte a 1020 y es el test de arriba el que avisa de
    que el numero ha cambiado.
    """
    problemas: list[str] = []
    for nombre, estado, par in _estados():
        v = ventana(estado, par=par)
        try:
            minimo = v.anchura_minima()
            alto = max(v.minimumSizeHint().height(), 560)
            for i in range(4):
                v.ir_a(i)
                redimensionar(v, minimo, alto)
                problemas += revisar(v, donde=f"{nombre} · pantalla {i} · {minimo}px")
        finally:
            v.close()
    assert not problemas, "\n".join(problemas)


def test_ninguna_etiqueta_se_recorta_en_las_anchuras_nominales():
    """1440 y 1024, que son las otras dos anchuras de captura."""
    problemas: list[str] = []
    v = ventana(demo())
    try:
        for ancho in (1440, 1024):
            for i in range(4):
                v.ir_a(i)
                redimensionar(v, ancho, 900)
                problemas += revisar(v, donde=f"nominal · pantalla {i} · {ancho}px")
    finally:
        v.close()
    assert not problemas, "\n".join(problemas)


def test_el_pie_del_carril_dice_la_frase_entera():
    """«escribe en «SIDEB COLOR»» es la promesa de la app.

    Salia como «escribe en «SIDEB COL...» incluso a 1440, porque el carril mide
    186 px fijos. Cortar justo el nombre de la version deja la frase diciendo
    la mitad de lo que tiene que decir, asi que va en dos lineas y sin elidir.
    """
    from core.contracts import VERSION_NAME

    v = ventana(demo())
    try:
        for ancho in (1440, 1024, v.anchura_minima()):
            redimensionar(v, ancho, 700)
            textos = [lab.text() for lab in etiquetas_visibles(v)]
            pie = [t for t in textos if t.startswith("escribe en")]
            assert pie, f"a {ancho} px no se ve el pie del carril"
            assert VERSION_NAME in pie[0], (
                f"a {ancho} px el pie dice {pie[0]!r} y se ha comido el nombre de la version"
            )
    finally:
        v.close()


def test_los_rotulos_del_cdl_se_leen_enteros_a_la_anchura_minima():
    """El caso concreto de la noche del 14: «SLO...», «OFF...», «PO...», «SAT...».

    Se comprueba aparte del barrido general porque es el que se rompio, y
    porque el barrido no dice cual era.
    """
    v = ventana(demo())
    try:
        v.ir_a(3)
        redimensionar(v, v.anchura_minima(), max(v.minimumSizeHint().height(), 560))
        rotulos = {
            lab.texto_completo(): lab
            for lab in v.p_reverse.editor.findChildren(Rotulo)
            if lab.isVisible()
        }
        for esperado in ("slope", "offset", "power", "sat"):
            assert esperado in rotulos, f"falta el rotulo {esperado!r} del editor de CDL"
            lab = rotulos[esperado]
            assert not esta_elidida(lab), f"el rotulo {esperado!r} sale como {lab.text()!r}"
    finally:
        v.close()


def test_la_columna_del_nombre_de_clip_no_desaparece():
    """El nombre del clip sobrevive a la anchura minima. **Ya sin `xfail`.**

    El dia 2 esto estaba como `xfail(strict=True)` porque a la anchura minima
    la columna CLIP se quedaba en 56 px y ensenaba «A...a». El motivo era que
    las cinco columnas fijas iban a `ResizeToContents`, que las mide por el
    texto de su CABECERA y no por la cifra: prometian 356 px y ocupaban 441, y
    los 85 de diferencia se los comia el nombre.

    **Lo ha decidido Mario: a la anchura minima ceden las columnas de ΔE, no la
    del nombre.** Un ΔE es un numero de formato acotado; un nombre de clip es
    lo que te dice que fila estas mirando. Asi que las columnas de cifras
    llevan ahora un ancho fijo medido (`PantallaClips.anchos_fijos()`), las dos
    de ΔE ponen su rotulo en dos lineas para caber en lo que mide un numero, y
    la del nombre es la unica que estira. Y **sin subir la anchura minima de la
    ventana**: ha bajado de 985 a 973.
    """
    v = ventana(muchos())
    try:
        v.ir_a(0)
        redimensionar(v, v.anchura_minima(), max(v.minimumSizeHint().height(), 560))
        ancho = v.p_clips.tabla.columnWidth(COL_NOMBRE)
        assert ancho >= v.p_clips.NOMBRE_MINIMO_PX - 8, (
            f"la columna del nombre se ha quedado en {ancho} px"
        )
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Control negativo: que el test se pueda hacer fallar
# ---------------------------------------------------------------------------


def test_el_test_falla_si_un_rotulo_se_recorta():
    """Se estropea la interfaz a proposito y el detector tiene que cazarlo.

    Sin esto, un `revisar()` que por un despiste no mirara ninguna etiqueta
    pasaria siempre y nadie se enteraria.
    """
    v = ventana(demo())
    try:
        v.ir_a(3)
        redimensionar(v, v.anchura_minima(), max(v.minimumSizeHint().height(), 560))
        assert not revisar(v, donde="antes de estropear")
        rotulo = next(
            lab for lab in v.p_reverse.editor.findChildren(Rotulo)
            if lab.texto_completo() == "slope"
        )
        # El `setMaximumWidth` hace falta: desde que `Rotulo.minimumSizeHint()`
        # devuelve el texto entero, un rotulo largo ya no se recorta solo, lo
        # que hace es empujar la ventana. Para probar el DETECTOR hay que
        # forzar la situacion que ya no se da sola.
        rotulo.setMaximumWidth(50)
        rotulo.setText("slope del canal rojo verde y azul, los tres seguidos")
        redimensionar(v, v.anchura_minima(), max(v.minimumSizeHint().height(), 560))
        problemas = revisar(v, donde="estropeado")
        assert problemas, "el detector no ha visto un rotulo recortado a proposito"
        assert any("rotulo" in p for p in problemas)
    finally:
        rotulo.setMaximumWidth(16777215)
        rotulo.setText("slope")
        v.close()


def test_el_test_falla_si_un_qlabel_normal_se_queda_corto():
    """Lo mismo con el corte silencioso de un `QLabel` sin elision."""
    v = ventana(demo())
    try:
        v.ir_a(1)
        redimensionar(v, v.anchura_minima(), max(v.minimumSizeHint().height(), 560))
        assert not revisar(v, donde="antes de estropear")
        etiqueta = v.p_comparar.texto_cdl
        original = etiqueta.text()
        etiqueta.setWordWrap(False)
        etiqueta.setText("una_sola_palabra_kilometrica_que_no_cabe_en_ese_panel_ni_de_lejos")
        redimensionar(v, v.anchura_minima(), max(v.minimumSizeHint().height(), 560))
        problemas = revisar(v, donde="estropeado")
        assert problemas, "el detector no ha visto un QLabel cortado a proposito"
        assert any("en silencio" in p for p in problemas)
    finally:
        etiqueta.setWordWrap(True)
        etiqueta.setText(original)
        v.close()


def test_ninguna_cabecera_de_la_tabla_sale_recortada():
    """Las cabeceras son rotulos, y un rotulo recortado no informa de nada.

    Esto no es redundante con el barrido de arriba: el barrido mira `QLabel`, y
    una cabecera de tabla no es un `QLabel`, es un pseudo-elemento que pinta el
    estilo. Como las columnas de cifras llevan ahora un **ancho fijo calculado**
    (`PantallaClips.anchos_fijos()`), hace falta algo que compruebe que ese
    calculo sigue dando de si: si alguien alarga un rotulo de cabecera, o toca
    `RELLENO_CABECERA_PX`, o Qt cambia de criterio con sus margenes, la cabecera
    empezaria a salir «ΔE DESP...» y esto salta antes que una captura.

    Se mide contra el hueco de verdad —el que le da el estilo al texto de la
    seccion— y no contra la formula con la que se calculo el ancho, que seria
    comprobar una cuenta consigo misma.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QStyle, QStyleOptionHeader

    from gui import identidad as idn
    from gui.pantalla_clips import CABECERAS

    v = ventana(muchos())
    try:
        v.ir_a(0)
        metricas = QFontMetrics(idn.fuente_cabecera_tabla())
        for ancho in (ANCHURA_MINIMA, 1024, 1440):
            redimensionar(v, ancho, max(v.minimumSizeHint().height(), 560))
            cab = v.p_clips.tabla.horizontalHeader()
            for i, texto in enumerate(CABECERAS):
                opcion = QStyleOptionHeader()
                cab.initStyleOption(opcion)
                opcion.section = i
                opcion.text = texto
                opcion.rect = QRect(
                    cab.sectionViewportPosition(i), 0, cab.sectionSize(i), cab.height()
                )
                # El hueco REAL que el estilo le deja al texto de la seccion,
                # preguntado al estilo y no deducido de la formula con la que se
                # calculo el ancho: comprobar una cuenta consigo misma no vale.
                hueco = cab.style().subElementRect(
                    QStyle.SubElement.SE_HeaderLabel, opcion, cab
                ).width()
                pide = max(metricas.horizontalAdvance(linea) for linea in texto.split("\n"))
                assert hueco >= pide, (
                    f"a {ancho} px la cabecera {texto!r} pide {pide} px y tiene {hueco}: "
                    f"saldria recortada"
                )
    finally:
        v.close()
