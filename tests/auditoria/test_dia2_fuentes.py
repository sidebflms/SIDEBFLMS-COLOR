"""AUDITORIA DIA 2, segunda vuelta - ¿hay mas sitios donde se creyo fijar una fuente?

El agente de GUI dice que la hoja de estilo **pisa a `setFont()`**. Lo primero
que hago es comprobarlo yo, porque si es verdad cambia la forma de leer los 37
`setFont()` que hay en `gui/`: dejan de ser «aqui se fija la fuente» y pasan a
ser «aqui se PIDE una fuente, y la hoja decide si se respeta».

SUITE SIDEBFLMS (2026-10-07), decision de Mario: **ya no hay monoespaciada**. La cifra es
Montserrat con cifras tabulares (`tnum`). Estos tests NO se retiran: se adaptan. Donde
antes se medía «¿mide igual una `i` que una `M`?» (mono), ahora se mide
`es_cifra_de_la_suite` (la familia que resuelve Qt es Montserrat, los diez digitos miden lo
mismo y la fuente lleva `tnum`): el mismo «yo queria cifra aqui y acabo sin ella», con la
vara nueva. Los controles negativos siguen fabricando el fallo (ahora con una etiqueta
plantada en una fuente que NO es de cifra) para que el espia no se quede ciego.

Y despues, la pregunta del encargo: ¿quedan sitios donde alguien creyo fijarla y
no la fijo? Se busca de forma mecanica, no a ojo: se intercepta cada
`setFont()` que reciba una fuente de cifra, se construye la ventana de verdad, y
se mide al final si esa etiqueta acaba como cifra de la suite.

Nada de esto toca `gui/`. Solo lo observa.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget  # noqa: E402

from gui import identidad as idn  # noqa: E402
from tests.test_gui_apoyo import app_qt, asentar, es_cifra_de_la_suite, ventana  # noqa: E402

pytestmark = pytest.mark.gui


def _mide_cifra(fuente) -> bool:
    """Vara de la suite (antes: «mide monoespaciada»): Montserrat + digitos tabulares."""
    return es_cifra_de_la_suite(fuente)


def test_AUDF_la_hoja_de_estilo_respeta_la_cifra_pedida_con_setFont():
    """El hecho de fondo, comprobado en aislamiento y no de oidas.

    Antes (con mono): la hoja de estilo pisaba a `setFont()` y una etiqueta con la
    fuente de cifra a mano dejaba de ser monoespaciada en cuanto la hoja entraba en
    juego. Con la suite (Montserrat para todo) la familia de la hoja y la de la cifra
    son la misma, y la hoja **no quita `tnum`**: la etiqueta sigue siendo una cifra
    tabular con la hoja puesta. Sin trucos: es un `QLabel` sin clase ni objectName.

    Si esto se pone rojo, la hoja (o una version de Qt) vuelve a pisar la fuente de
    cifra y los `setFont()` de `gui/` vuelven a ser «aqui se PIDE una cifra y la hoja
    decide»: habria que rehacer el test para medir cual de las dos gana.
    """
    app = app_qt()
    raiz = QWidget()
    QVBoxLayout(raiz).addWidget(lab := QLabel("123.456"))
    lab.setFont(idn.fuente_cifra(13))

    antes_familias = list(lab.font().families())
    antes_cifra = _mide_cifra(lab.font())

    app.setStyleSheet(idn.hoja_de_estilo())
    raiz.show()
    asentar()

    despues_familias = list(lab.font().families())
    despues_cifra = _mide_cifra(lab.font())
    raiz.close()

    print(f"\n[AUDF] antes de la hoja  : {antes_familias[:2]} cifra={antes_cifra}")
    print(f"[AUDF] despues de la hoja: {despues_familias[:2]} cifra={despues_cifra}")

    assert antes_cifra is True, "la fuente de cifra ya no es cifra de la suite ni antes de la hoja"
    assert despues_cifra is True, (
        "la hoja de estilo ha vuelto a pisar la fuente de cifra de setFont(): la etiqueta ya "
        "no es Montserrat con cifras tabulares tras aplicar la hoja"
    )


def test_AUDF_las_tipografias_de_marca_no_estan_instaladas_en_esta_maquina():
    """Contexto imprescindible para leer lo de arriba y para leer las capturas.

    Akira no esta instalada aqui (y no va en el repo: es publica). Los titulos salen en
    Montserrat 800 y la cifra en Montserrat `tnum`, que SI va en el repo
    (`gui/fuentes/`): ya no dependemos de ningun sustituto del sistema para la cifra.
    """
    from tests.test_gui_apoyo import tipografias_de_marca_instaladas

    instaladas = tipografias_de_marca_instaladas()
    print(f"\n[AUDF] tipografias de marca instaladas: {instaladas or 'NINGUNA'}")
    # No es un fallo: es un hecho que hay que tener delante al mirar una captura.
    assert isinstance(instaladas, list)


def _vigilar_peticiones_de_cifra(construir):
    """Construye con `construir()` espiando `QWidget.setFont`.

    Devuelve `(raiz, vivos, fallidos)`: los widgets que pidieron la fuente de
    cifra y siguen vivos, y de esos los que al final NO acaban como cifra de la suite.
    `raiz` es lo que devolvio `construir()`; cierralo tu.
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
        raiz = construir()
        asentar()
    finally:
        QWidget.setFont = original

    vivos = [(w, n) for w, n in pedidas if _sigue_vivo(w)]
    fallidos = [(w, n) for w, n in vivos if not _mide_cifra(w.font())]
    print(f"\n[AUDF] widgets que PIDIERON fuente de cifra: {len(pedidas)} "
          f"(vivos al final: {len(vivos)})")
    for w, n in vivos:
        marca = "cifra" if _mide_cifra(w.font()) else "NO CIFRA"
        etiqueta = w.text()[:30] if isinstance(w, QLabel) else ""
        print(f"[AUDF]   {n:<18} objectName={w.objectName()!r:<14} "
              f"clase={w.property('class')!r:<10} {marca:<8} {etiqueta!r}")
    for w, _n in fallidos:
        texto = w.text() if isinstance(w, QLabel) else ""
        print(f"[AUDF] FALLIDO -> {_linaje(w)}  texto={texto!r}")
    return raiz, vivos, fallidos


def _afirmar_ninguna_peticion_fallida(vivos, fallidos) -> None:
    assert vivos, "el espia no ha visto ni un setFont de cifra: el test se ha quedado ciego"
    # Dia 4: aqui habia una cuarentena para `ruta_look` (gui/pantalla_aplicar.py).
    # Se arreglo el dia 3 y la cuarentena seguia dando verde sin vigilar nada
    # (`0 <= 1`), y ademas daba por «ya conocida» a CUALQUIER EtiquetaElidida de
    # PantallaAplicar. Ya no hay conocidos: cualquier fallido es rojo.
    assert not fallidos, (
        f"{len(fallidos)} sitio(s) piden fuente de cifra y no la consiguen: "
        f"{[(n, _linaje(w)) for w, n in fallidos]}"
    )


def test_AUDF_ninguna_etiqueta_pide_fuente_de_cifra_y_acaba_sin_ella():
    """LA PREGUNTA DEL ENCARGO, respondida de forma mecanica.

    Se intercepta `QWidget.setFont` durante la construccion de la ventana
    entera. Cada vez que alguien pasa una fuente cuya lista de familias es la
    de cifra, se apunta el widget: eso es un «yo queria cifra aqui».
    Al final, con la ventana montada y la hoja aplicada, se mide cada uno.

    Si alguno no acaba como cifra de la suite (Montserrat con digitos tabulares), es un
    sitio donde alguien creyo fijar la fuente y no la fijo.
    """
    v, vivos, fallidos = _vigilar_peticiones_de_cifra(ventana)
    try:
        _afirmar_ninguna_peticion_fallida(vivos, fallidos)
    finally:
        v.close()


def test_AUDF_control_negativo_una_etiqueta_plantada_sin_cifra_pone_rojo():
    """Control negativo del test de arriba: que de verdad se puede poner rojo.

    Se planta en la ventana real un `QLabel` sin clase que pide `fuente_cifra` con
    `setFont()` y al que luego se le impone, con su propia hoja, otra familia
    (`Courier New`): acaba sin ser cifra de la suite. El espia tiene que verlo y la
    afirmacion tiene que fallar.
    """
    plantada: list[QLabel] = []

    def construir():
        v = ventana()
        lab = QLabel("123.456", v.centralWidget() or v)
        lab.setObjectName("plantadaPorElControlNegativo")
        lab.setFont(idn.fuente_cifra(13))
        lab.setStyleSheet("QLabel { font-family: 'Courier New'; }")
        lab.show()
        plantada.append(lab)
        return v

    v, vivos, fallidos = _vigilar_peticiones_de_cifra(construir)
    try:
        assert any(w is plantada[0] for w, _n in fallidos), (
            "la etiqueta plantada no sale como fallida: el control negativo no ha "
            "conseguido fabricar el fallo, asi que no demuestra nada"
        )
        with pytest.raises(AssertionError, match="piden fuente de cifra y no la consiguen"):
            _afirmar_ninguna_peticion_fallida(vivos, fallidos)
    finally:
        v.close()


def test_AUDF_control_negativo_sin_peticiones_el_test_no_se_queda_ciego():
    """Si nadie pide la fuente de cifra, el test no puede dar verde en vacio."""
    def construir():
        w = QWidget()
        QVBoxLayout(w).addWidget(QLabel("sin cifra"))
        w.show()
        return w

    w, vivos, fallidos = _vigilar_peticiones_de_cifra(construir)
    try:
        assert vivos == [] and fallidos == []
        with pytest.raises(AssertionError, match="se ha quedado ciego"):
            _afirmar_ninguna_peticion_fallida(vivos, fallidos)
    finally:
        w.close()


def _linaje(w) -> str:
    partes = []
    actual = w
    for _ in range(6):
        if actual is None:
            break
        partes.append(f"{type(actual).__name__}({actual.objectName() or '-'})")
        actual = actual.parent()
    return " < ".join(partes)


def _sigue_vivo(w) -> bool:
    try:
        w.objectName()
    except RuntimeError:
        return False
    return True


def test_AUDF_las_cifras_de_la_ventana_son_cifras_de_la_suite_de_verdad():
    """El contrapeso por el otro lado: se mira el RESULTADO, no la intencion.

    Cualquier etiqueta marcada como cifra (por `objectName` o por la propiedad
    `class`) tiene que ser cifra de la suite (Montserrat tabular) con la ventana ya montada. Esto
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
        malas = [lab for lab in marcadas if not _mide_cifra(lab.font())]
        for lab in malas:
            print(f"[AUDF]   MAL: objectName={lab.objectName()!r} "
                  f"class={lab.property('class')!r} texto={lab.text()[:30]!r}")
        assert marcadas, "no hay ni una etiqueta marcada como cifra: revisa este test"
        assert not malas, (
            f"{len(malas)} etiquetas marcadas como cifra no son cifras de la suite: "
            f"{[(lab.objectName(), lab.property('class')) for lab in malas]}"
        )
    finally:
        v.close()
