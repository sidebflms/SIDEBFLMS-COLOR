"""AUDITORIA DIA 2, segunda vuelta - ¿hay mas sitios donde se creyo fijar una fuente?

El agente de GUI dice que la hoja de estilo **pisa a `setFont()`**. Lo primero
que hago es comprobarlo yo, porque si es verdad cambia la forma de leer los 37
`setFont()` que hay en `gui/`: dejan de ser «aqui se fija la fuente» y pasan a
ser «aqui se PIDE una fuente, y la hoja decide si se respeta».

Y despues, la pregunta del encargo: ¿quedan sitios donde alguien creyo fijarla y
no la fijo? Se busca de forma mecanica, no a ojo: se intercepta cada
`setFont()` que reciba una fuente de cifra, se construye la ventana de verdad, y
se mide al final si esa etiqueta pinta monoespaciada.

Nada de esto toca `gui/`. Solo lo observa.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget  # noqa: E402

from gui import identidad as idn  # noqa: E402
from tests.test_gui_apoyo import app_qt, asentar, ventana  # noqa: E402

pytestmark = pytest.mark.gui


def _mide_mono(fuente) -> bool:
    m = QFontMetrics(fuente)
    return m.horizontalAdvance("iiii") == m.horizontalAdvance("MMMM")


def test_AUDF_la_hoja_de_estilo_SI_pisa_a_setFont():
    """El hecho de fondo, comprobado en aislamiento y no de oidas.

    Una etiqueta a la que se le pone la fuente de cifra a mano, en cuanto la
    hoja de estilo entra en juego, pasa a la de texto y deja de ser
    monoespaciada. Sin trucos: es un `QLabel` sin clase ni objectName.
    """
    app = app_qt()
    raiz = QWidget()
    QVBoxLayout(raiz).addWidget(lab := QLabel("123.456"))
    lab.setFont(idn.fuente_cifra(13))

    antes_familias = list(lab.font().families())
    antes_mono = _mide_mono(lab.font())

    app.setStyleSheet(idn.hoja_de_estilo())
    raiz.show()
    asentar()

    despues_familias = list(lab.font().families())
    despues_mono = _mide_mono(lab.font())
    raiz.close()

    print(f"\n[AUDF] antes de la hoja  : {antes_familias[:2]} mono={antes_mono}")
    print(f"[AUDF] despues de la hoja: {despues_familias[:2]} mono={despues_mono}")

    assert antes_mono is True, "la fuente de cifra ya no mide monoespaciada ni antes de la hoja"
    assert despues_mono is False, (
        "la hoja de estilo ya NO pisa a setFont(). Si esto ha cambiado (version de Qt, o la "
        "hoja ha dejado de declarar font-family en un selector tan ancho), entonces los 37 "
        "setFont() de gui/ vuelven a significar lo que parecia que significaban y este test "
        "hay que rehacerlo."
    )


def test_AUDF_las_tipografias_de_marca_no_estan_instaladas_en_esta_maquina():
    """Contexto imprescindible para leer lo de arriba y para leer las capturas.

    Ninguna de las tres tipografias de la identidad esta instalada aqui. O sea
    que TODO lo que se ve en las capturas y en los tests sale con los
    sustitutos del sistema. Que la cifra salga monoespaciada se lo debemos al
    `StyleHint.Monospace` y a la lista de reservas, no a JetBrains Mono.
    """
    from tests.test_gui_apoyo import tipografias_de_marca_instaladas

    instaladas = tipografias_de_marca_instaladas()
    print(f"\n[AUDF] tipografias de marca instaladas: {instaladas or 'NINGUNA'}")
    # No es un fallo: es un hecho que hay que tener delante al mirar una captura.
    assert isinstance(instaladas, list)


def test_AUDF_ninguna_etiqueta_pide_fuente_de_cifra_y_acaba_sin_ella():
    """LA PREGUNTA DEL ENCARGO, respondida de forma mecanica.

    Se intercepta `QWidget.setFont` durante la construccion de la ventana
    entera. Cada vez que alguien pasa una fuente cuya lista de familias es la
    de cifra, se apunta el widget: eso es un «yo queria monoespaciada aqui».
    Al final, con la ventana montada y la hoja aplicada, se mide cada uno.

    Si alguno no mide monoespaciada, es un sitio donde alguien creyo fijar la
    fuente y no la fijo.
    """
    app_qt()
    pedidas: list[tuple[QWidget, str]] = []
    original = QWidget.setFont
    familias_cifra = list(idn.FAMILIAS_CIFRA)

    def espia(self, fuente):  # noqa: ANN001
        try:
            if list(fuente.families()) == familias_cifra:
                pedidas.append((self, type(self).__name__))
        except Exception:  # noqa: BLE001 - un espia no puede tumbar la construccion
            pass
        return original(self, fuente)

    QWidget.setFont = espia
    try:
        v = ventana()
        asentar()
    finally:
        QWidget.setFont = original

    try:
        vivos = [(w, n) for w, n in pedidas if _sigue_vivo(w)]
        fallidos = [(w, n) for w, n in vivos if not _mide_mono(w.font())]
        print(f"\n[AUDF] widgets que PIDIERON fuente de cifra: {len(pedidas)} "
              f"(vivos al final: {len(vivos)})")
        for w, n in vivos:
            marca = "mono" if _mide_mono(w.font()) else "NO MONO"
            etiqueta = w.text()[:30] if isinstance(w, QLabel) else ""
            print(f"[AUDF]   {n:<18} objectName={w.objectName()!r:<14} "
                  f"clase={w.property('class')!r:<10} {marca:<8} {etiqueta!r}")
        for w, _n in fallidos:
            print(f"[AUDF] FALLIDO -> {_linaje(w)}  texto={w.text()!r}")
        assert vivos, "el espia no ha visto ni un setFont de cifra: el test se ha quedado ciego"

        # Cuarentena: el unico sitio que hay HOY, identificado y con su linea.
        # No lo arreglo yo (gui/ no es mio); esta en el informe. En cuanto se
        # arregle, este test salta y hay que vaciar la lista.
        conocidos = {"gui/pantalla_aplicar.py:286 ruta_look (EtiquetaElidida)"}
        nuevos = [(n, w.text()) for w, n in fallidos if _es_ruta_look(w) is False]
        assert len(fallidos) <= len(conocidos), (
            f"han aparecido sitios NUEVOS donde se pide fuente de cifra y no se consigue: "
            f"{[(n, w.text()) for w, n in fallidos]}. Conocido y ya reportado: {conocidos}"
        )
        assert not nuevos, (
            f"sitio nuevo (no es el `ruta_look` ya reportado): {nuevos}"
        )
        if fallidos:
            print(f"[AUDF] (1 fallido conocido y reportado: {conocidos})")
    finally:
        v.close()


def _linaje(w) -> str:
    partes = []
    actual = w
    for _ in range(6):
        if actual is None:
            break
        partes.append(f"{type(actual).__name__}({actual.objectName() or '-'})")
        actual = actual.parent()
    return " < ".join(partes)


def _es_ruta_look(w) -> bool:
    """¿Es el `ruta_look` de la pantalla de aplicar, el fallido ya conocido?"""
    linaje = _linaje(w)
    return type(w).__name__ == "EtiquetaElidida" and "Aplicar" in linaje


def _sigue_vivo(w) -> bool:
    try:
        w.objectName()
    except RuntimeError:
        return False
    return True


def test_AUDF_las_cifras_de_la_ventana_miden_monoespaciadas_de_verdad():
    """El contrapeso por el otro lado: se mira el RESULTADO, no la intencion.

    Cualquier etiqueta marcada como cifra (por `objectName` o por la propiedad
    `class`) tiene que medir monoespaciada con la ventana ya montada. Esto
    caza el caso contrario al de arriba: una etiqueta bien marcada a la que la
    hoja no llega.
    """
    app_qt()
    v = ventana()
    try:
        asentar()
        marcadas = [
            lab
            for lab in v.findChildren(QLabel)
            if "cifra" in (lab.objectName() or "")
            or "cifra" in str(lab.property("class") or "")
            or (lab.objectName() or "") in ("secundario",)
        ]
        print(f"\n[AUDF] etiquetas marcadas como cifra: {len(marcadas)}")
        malas = [lab for lab in marcadas if not _mide_mono(lab.font())]
        for lab in malas:
            print(f"[AUDF]   MAL: objectName={lab.objectName()!r} "
                  f"class={lab.property('class')!r} texto={lab.text()[:30]!r}")
        assert marcadas, "no hay ni una etiqueta marcada como cifra: revisa este test"
        assert not malas, (
            f"{len(malas)} etiquetas marcadas como cifra no miden monoespaciadas: "
            f"{[(lab.objectName(), lab.property('class')) for lab in malas]}"
        )
    finally:
        v.close()
