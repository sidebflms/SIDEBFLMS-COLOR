"""Las tres reglas de marca que se incumplen solas, comprobadas.

1. **`#ff6a3d` como texto e iconos de marca, si. Como pastilla, nunca.** En
   pastilla ese hexadecimal significa «Fuera» en el inventario de SIDEBFLMS, y
   reutilizarlo contaminaria los dos sistemas. Esto lo ha confirmado Mario y
   esta escrito donde se usa el color, en `gui/identidad.py`, junto a
   `BRAND_400`.
2. **El rojo no es color de error.** El naranja es marca, no alarma; el rojo se
   reserva a acciones destructivas, y en esta app no hay ninguna.
3. **Toda cifra va en monoespaciada.** Sin excepcion.

La primera se comprueba de tres formas, porque una pastilla se puede pintar de
tres: por hoja de estilo, por `setStyleSheet` local, y a mano con un `QPainter`.
La de a mano se comprueba **renderizando** la unica pastilla que hay en la app
—la insignia de confianza— y mirandole los pixeles de dentro.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

from gui import identidad as idn  # noqa: E402
from gui.widgets import (  # noqa: E402
    INSIGNIA_ALTO,
    INSIGNIA_ANCHO,
    Cifra,
    pintar_insignia_confianza,
)
from tests.test_gui_apoyo import (  # noqa: E402
    app_qt,
    asentar,
    demo,
    es_monoespaciada,
    etiquetas_visibles,
    ventana,
)

pytestmark = pytest.mark.gui

RAIZ_GUI = Path(__file__).resolve().parent.parent / "gui"

#: Los colores de `docs/IDENTIDAD.md`, literales y cerrados. Nada mas.
PALETA = {
    idn.BRAND_500,
    idn.BRAND_600,
    idn.BRAND_400,
    idn.BRAND_50,
    idn.CYAN_GLOW,
    idn.FONDO,
    idn.HONDO,
    idn.PANEL,
    idn.CRISTAL,
}

#: Los tokens de estado del inventario. Reservados: no se reutilizan aqui con
#: tratamiento de pastilla. `#3ad6cf` y `#ff6a3d` estan en las dos listas y por
#: eso son los delicados.
TOKENS_INVENTARIO = {
    "#00d492": "Disponible",
    "#ffb900": "Reservado",
    "#ff6a3d": "Fuera",
    "#3ad6cf": "En taller",
    "#71717b": "De baja",
}

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _rgb_de(hex_color: str) -> int:
    return QColor(hex_color).rgb()


# ---------------------------------------------------------------------------
# 1 · #ff6a3d nunca de pastilla
# ---------------------------------------------------------------------------


def test_la_hoja_de_estilo_no_pone_ff6a3d_de_fondo_en_ningun_sitio():
    """Ni como `background`, ni como `background-color`, ni con opacidad."""
    hoja = idn.hoja_de_estilo()
    c = QColor(idn.BRAND_400)
    marca_rgba = f"rgba({c.red()}, {c.green()}, {c.blue()}"
    culpables = []
    for linea in hoja.splitlines():
        limpia = linea.strip()
        if not limpia.startswith(("background", "alternate-background")):
            continue
        if idn.BRAND_400 in limpia or marca_rgba in limpia:
            culpables.append(limpia)
    assert not culpables, (
        "la hoja de estilo pinta un fondo con #ff6a3d, que en pastilla significa "
        "«Fuera» en el inventario:\n" + "\n".join(culpables)
    )


def test_ningun_setstylesheet_de_la_gui_pone_ff6a3d_de_fondo():
    """Lo mismo, pero en las hojas de estilo sueltas que se ponen por codigo.

    Se leen del arbol de sintaxis, para que un comentario que hable del color
    no cuente como uso.
    """
    culpables: list[str] = []
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if not (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "setStyleSheet"
            ):
                continue
            texto = ast.unparse(nodo)
            if "background" in texto and ("BRAND_400" in texto or idn.BRAND_400 in texto):
                culpables.append(f"{archivo.name}:{nodo.lineno}: {texto}")
    assert not culpables, "pastilla de #ff6a3d por setStyleSheet:\n" + "\n".join(culpables)


def test_la_insignia_de_confianza_nunca_se_rellena_de_ff6a3d():
    """La insignia ES la unica pastilla de la app: rectangulo redondeado.

    Se comprueba pintandola de verdad sobre el fondo y mirando un pixel de
    dentro. `alta` se rellena de `brand-600`, que es lo que dice la identidad;
    `media` y `baja` no se rellenan y dejan ver el fondo. Ninguna de las tres
    puede tener dentro `#ff6a3d` ni una mezcla suya.
    """
    app_qt()
    fondo = QColor(idn.FONDO)
    esperado = {
        idn.FormaConfianza.ALTA: QColor(idn.BRAND_600),
        idn.FormaConfianza.MEDIA: fondo,
        idn.FormaConfianza.BAJA: fondo,
    }
    for forma, color_dentro in esperado.items():
        img = QImage(INSIGNIA_ANCHO, INSIGNIA_ALTO, QImage.Format.Format_RGB32)
        img.fill(fondo)
        p = QPainter(img)
        pintar_insignia_confianza(p, QRect(0, 0, INSIGNIA_ANCHO, INSIGNIA_ALTO), forma, 0.5)
        p.end()
        # Un punto de dentro, lejos del medidor (izquierda) y del texto (centro).
        dentro = QColor(img.pixel(INSIGNIA_ANCHO - 4, INSIGNIA_ALTO // 2))
        assert dentro.rgb() == color_dentro.rgb(), (
            f"la pastilla de confianza {forma.value} se rellena de "
            f"{dentro.name()} y tendria que ser {color_dentro.name()}"
        )
        assert dentro.rgb() != _rgb_de(idn.BRAND_400), (
            f"la pastilla de confianza {forma.value} esta rellena de #ff6a3d, que en "
            f"pastilla significa «Fuera» en el inventario"
        )


def test_formaconfianza_no_declara_ff6a3d_como_relleno():
    for forma in idn.FormaConfianza:
        relleno = forma.relleno
        if relleno is not None:
            assert relleno.name().lower() != idn.BRAND_400.lower()


def test_la_regla_de_la_pastilla_esta_escrita_donde_se_usa_el_color():
    """Mario quiere que la regla viva en el archivo de tokens, no solo en un doc.

    Y que se vea al ir a usar el color: en el modulo de identidad, cerca de
    `BRAND_400`, no en un rincon.
    """
    fuente = (RAIZ_GUI / "identidad.py").read_text(encoding="utf-8")
    assert "BRAND_400 = " in fuente
    inicio = fuente.index("BRAND_600 = ")
    fin = fuente.index("BRAND_50 = ")
    alrededor = fuente[inicio:fin]
    assert "pastilla" in alrededor.lower(), (
        "la regla de la pastilla no esta escrita junto a BRAND_400"
    )
    assert "Fuera" in alrededor
    assert "inventario" in alrededor.lower()


def test_el_rombo_de_desajuste_no_es_una_pastilla():
    """`#ff6a3d` con relleno SI se usa, pero con forma de rombo.

    Es la distincion que hace `docs/IDENTIDAD.md`: lo reservado es el
    tratamiento de pastilla, no el hexadecimal. Un rombo no se confunde con una
    pastilla del inventario ni de lejos, y es la unica forma de rombo que hay
    en toda la interfaz.
    """
    from gui.widgets import MarcaDesajuste

    app_qt()
    marca = MarcaDesajuste(lado=24)
    marca.show()
    asentar()
    try:
        img = QImage(24, 24, QImage.Format.Format_RGB32)
        img.fill(QColor(idn.FONDO))
        marca.render(img)
        # Las cuatro esquinas quedan FUERA del rombo: siguen siendo fondo. En
        # una pastilla estarian pintadas.
        for x, y in ((1, 1), (22, 1), (1, 22), (22, 22)):
            assert QColor(img.pixel(x, y)).rgb() == _rgb_de(idn.FONDO), (
                "el aviso de desajuste pinta las esquinas: eso ya es una pastilla"
            )
    finally:
        marca.close()


# ---------------------------------------------------------------------------
# 2 · el rojo no es color de error
# ---------------------------------------------------------------------------


def test_la_paleta_de_la_gui_es_exactamente_la_de_la_identidad():
    """Ni un hexadecimal inventado en `gui/identidad.py`.

    Lo que no esta en la lista no se improvisa: se baja la opacidad de uno que
    si esta (`rgba()`), y por eso los unicos hexadecimales del modulo son los
    nueve de la identidad.
    """
    fuente = (RAIZ_GUI / "identidad.py").read_text(encoding="utf-8")
    encontrados = {h.lower() for h in _HEX.findall(fuente)}
    de_mas = encontrados - {c.lower() for c in PALETA} - {
        c.lower() for c in TOKENS_INVENTARIO
    }
    assert not de_mas, f"colores inventados en la identidad de la GUI: {sorted(de_mas)}"


def test_no_hay_ningun_rojo_de_error_en_toda_la_gui():
    """Rojo = accion destructiva, y aqui no hay ninguna.

    Se busca cualquier hexadecimal de `gui/` que sea «rojo de alarma»: tono
    entre -20 y 20 grados, saturado y claro. El naranja de marca (#e8451d,
    #ff6a3d) tiene el tono en 14-16 grados pero esta en la paleta, asi que lo
    que se comprueba es que no aparezca **ningun otro**.
    """
    culpables: list[str] = []
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            for hexa in _HEX.findall(linea):
                if hexa.lower() in {c.lower() for c in PALETA}:
                    continue
                c = QColor(hexa)
                tono = c.hue()  # -1 si es gris
                if 0 <= tono <= 20 and c.saturation() > 120 and c.value() > 120:
                    culpables.append(f"{archivo.name}:{n}: {hexa}")
    assert not culpables, (
        "rojo de alarma en la GUI; el rojo se reserva a acciones destructivas:\n"
        + "\n".join(culpables)
    )


def test_los_avisos_de_la_pantalla_de_aplicar_van_en_naranja_de_marca():
    from gui import pantalla_aplicar as pa

    fuente = (RAIZ_GUI / "pantalla_aplicar.py").read_text(encoding="utf-8")
    assert "BRAND_400" in fuente
    plan = pa.Plan(error_global="no hay conexión con DaVinci Resolve")
    html = pa.PantallaAplicar._plan_a_html.__wrapped__ if False else None  # noqa: F841
    # Se construye la pantalla de verdad, que es donde se pinta.
    v = ventana(demo())
    try:
        v.ir_a(2)
        asentar(2)
        html = v.p_aplicar._plan_a_html(plan)
        assert idn.BRAND_400 in html
        assert "#f00" not in html and "#ff0000" not in html
    finally:
        v.close()


# ---------------------------------------------------------------------------
# 3 · toda cifra en monoespaciada
# ---------------------------------------------------------------------------


def test_todas_las_cifras_de_la_app_salen_en_monoespaciada():
    """Se mide la fuente RENDERIZADA, no la que se pidio.

    Es la unica forma de cazarlo: la hoja de estilo **pisa a `setFont()`**, asi
    que un `QLabel` al que se le puso `fuente_cifra()` a mano puede acabar en
    Inter si ninguna regla del QSS le declara `font-family`. Estaba pasando en
    dos sitios (el bloque del CDL de «antes/despues» y los datos del LUT del
    panel de ingenieria inversa) y se veia en las capturas: las columnas no
    alineaban.
    """
    v = ventana(demo())
    try:
        malas: list[str] = []
        for i in range(4):
            v.ir_a(i)
            asentar(2)
            for lab in v.findChildren(Cifra):
                if lab.isVisible() and not es_monoespaciada(lab.font()):
                    malas.append(
                        f"pantalla {i} · Cifra#{lab.objectName() or '-'}: {lab.text()[:30]!r}"
                    )
        assert not malas, "cifras que NO salen en monoespaciada:\n" + "\n".join(malas)
    finally:
        v.close()


def test_los_bloques_de_numeros_que_no_son_widget_cifra_tambien_son_monoespaciados():
    """El inventario de los sitios donde hay cifras dentro de un `QLabel` normal.

    No hay heuristica que distinga «una cifra» de «una frase con numeros»
    («LUT de 17: banding (67 escalones)» es prosa), asi que la lista se escribe
    a mano. Si alguien cambia uno de estos por un `QLabel` pelado, se entera
    aqui.
    """
    v = ventana(demo())
    try:
        v.ir_a(1)
        asentar(2)
        assert es_monoespaciada(v.p_comparar.texto_cdl.font()), (
            "los diez numeros del CDL de «antes/despues» no van en monoespaciada"
        )
        v.ir_a(3)
        asentar(2)
        assert es_monoespaciada(v.p_reverse.datos_lut.font()), (
            "los datos del LUT del panel de ingenieria inversa no van en monoespaciada"
        )
        for nombre, campo in v.p_reverse.editor._campos.items():
            assert es_monoespaciada(campo.font()), (
                f"el campo {nombre} del editor de CDL no va en monoespaciada"
            )
    finally:
        v.close()


def test_los_rotulos_no_van_en_monoespaciada():
    """Control del test de arriba: si `es_monoespaciada` dijera que si a todo,
    los dos tests de cifras pasarian sin probar nada."""
    v = ventana(demo())
    try:
        from gui.widgets import Rotulo

        rotulos = [r for r in v.findChildren(Rotulo) if r.isVisible()]
        assert rotulos
        assert not any(es_monoespaciada(r.font()) for r in rotulos)
    finally:
        v.close()


# ---------------------------------------------------------------------------
# La confianza, por forma
# ---------------------------------------------------------------------------


def _borde_superior(forma: idn.FormaConfianza) -> list[bool]:
    """Que pixeles del borde de arriba estan pintados. Es lo que distingue el
    trazo continuo del discontinuo sin mirar un solo color."""
    app_qt()
    img = QImage(INSIGNIA_ANCHO, INSIGNIA_ALTO, QImage.Format.Format_RGB32)
    fondo = QColor(idn.FONDO)
    img.fill(fondo)
    p = QPainter(img)
    pintar_insignia_confianza(p, QRect(0, 0, INSIGNIA_ANCHO, INSIGNIA_ALTO), forma, 0.5)
    p.end()
    # Se mira el tramo recto de arriba, lejos de las esquinas redondeadas.
    return [
        QColor(img.pixel(x, 0)).rgb() != fondo.rgb()
        for x in range(12, INSIGNIA_ANCHO - 12)
    ]


def test_la_confianza_se_distingue_por_forma_y_no_por_semaforo():
    """Relleno solido, contorno continuo, contorno discontinuo.

    Se comprueba **en los pixeles**: el borde de arriba de `alta` y `media` es
    continuo y el de `baja` tiene huecos. Un semaforo verde/ambar/rojo no se
    leeria en blanco y negro y ademas pisaria los tokens del inventario.
    """
    alta = _borde_superior(idn.FormaConfianza.ALTA)
    media = _borde_superior(idn.FormaConfianza.MEDIA)
    baja = _borde_superior(idn.FormaConfianza.BAJA)

    assert sum(alta) / len(alta) > 0.9, "el borde de «alta» no es continuo"
    assert sum(media) / len(media) > 0.9, "el borde de «media» no es continuo"
    proporcion_baja = sum(baja) / len(baja)
    assert 0.3 < proporcion_baja < 0.85, (
        f"el borde de «baja» tendria que ser discontinuo y esta pintado al "
        f"{proporcion_baja * 100:.0f}%"
    )
    # Y ademas hay que poder contar los huecos: un trazo discontinuo alterna.
    cambios = sum(1 for a, b in zip(baja, baja[1:], strict=False) if a != b)
    assert cambios >= 4, "el borde de «baja» no alterna: no es discontinuo"


def test_las_tres_formas_llevan_distinto_numero_de_escalones():
    assert idn.FormaConfianza.ALTA.escalones == 3
    assert idn.FormaConfianza.MEDIA.escalones == 2
    assert idn.FormaConfianza.BAJA.escalones == 1
    assert idn.FormaConfianza.de_nivel("alta") is idn.FormaConfianza.ALTA
    assert idn.FormaConfianza.de_nivel("media") is idn.FormaConfianza.MEDIA
    assert idn.FormaConfianza.de_nivel("baja") is idn.FormaConfianza.BAJA


def test_las_tres_formas_se_distinguen_en_blanco_y_negro():
    """Sin color: convertidas a gris, las tres insignias siguen siendo distintas."""
    app_qt()
    grises = []
    for forma in idn.FormaConfianza:
        img = QImage(INSIGNIA_ANCHO, INSIGNIA_ALTO, QImage.Format.Format_RGB32)
        img.fill(QColor(idn.FONDO))
        p = QPainter(img)
        pintar_insignia_confianza(p, QRect(0, 0, INSIGNIA_ANCHO, INSIGNIA_ALTO), forma, 0.5)
        p.end()
        grises.append(img.convertToFormat(QImage.Format.Format_Grayscale8))
    for i in range(len(grises)):
        for j in range(i + 1, len(grises)):
            assert grises[i] != grises[j], (
                "dos niveles de confianza se ven iguales en blanco y negro"
            )


# ---------------------------------------------------------------------------
# Tipografia de marca
# ---------------------------------------------------------------------------


def test_la_pila_de_fuentes_pide_primero_la_familia_de_marca():
    """El dia que Mario instale las tres, la app las coge sola."""
    assert idn.FAMILIAS_TEXTO[0] == "Inter"
    assert idn.FAMILIAS_ROTULO[0] == "Chakra Petch"
    assert idn.FAMILIAS_CIFRA[0] == "JetBrains Mono"
    for familias in (idn.FAMILIAS_TEXTO, idn.FAMILIAS_ROTULO, idn.FAMILIAS_CIFRA):
        assert len(familias) > 1, "sin alternativa, en este Mac no se veria nada"


def test_los_rotulos_van_en_mayusculas_y_con_el_tracking_de_la_identidad():
    """10-11px, MAYUSCULAS, tracking 0.15-0.18em. QSS no tiene `text-transform`,
    asi que las mayusculas son de la fuente y hay que comprobarlo ahi."""
    from PySide6.QtGui import QFont

    from gui.widgets import Rotulo

    v = ventana(demo())
    try:
        for r in v.findChildren(Rotulo):
            if not r.isVisible():
                continue
            f = r.font()
            assert f.capitalization() == QFont.Capitalization.AllUppercase
            assert 10 <= f.pixelSize() <= 11, f"rotulo a {f.pixelSize()}px"
            em = f.letterSpacing() / f.pixelSize()
            assert 0.15 <= em <= 0.18, f"tracking de {em:.3f}em"
    finally:
        v.close()


def test_ningun_qlabel_pinta_su_propio_rectangulo_de_fondo():
    """`QLabel { background: transparent }`.

    Sin esa regla, la de `QWidget` les daba `#0a0908` y encima de un panel cada
    rotulo salia con su rectangulo negro detras. Se veia en toda la primera
    tanda de capturas.
    """
    assert "QLabel {" in idn.hoja_de_estilo()
    assert "background: transparent" in idn.hoja_de_estilo()
    v = ventana(demo())
    try:
        for lab in etiquetas_visibles(v):
            if isinstance(lab, QLabel) and lab.autoFillBackground():
                raise AssertionError(f"{lab.text()[:20]!r} pinta su propio fondo")
    finally:
        v.close()


# ---------------------------------------------------------------------------
# La escala tipografica: que lo que se pide sea lo que se pinta
# ---------------------------------------------------------------------------
#
# El dia 2 la hoja de estilo declaraba `font-size: 13px` en el selector
# `QWidget`, que casa con TODOS los widgets de la app. En Qt, una propiedad de
# fuente declarada por una regla que casa gana a `setFont()`, asi que los 22, 24
# y 26 px de las cifras grandes y los 10, 11, 12 y 15 px del texto de cuerpo
# salian todos a 13: la jerarquia entera aplanada. No era una decision de
# diseno; era un accidente. Estos tres tests son para que no vuelva.


def _familias_de_rol() -> dict[tuple[str, ...], str]:
    return {
        tuple(idn.FAMILIAS_TEXTO): "texto",
        tuple(idn.FAMILIAS_CIFRA): "cifra",
        tuple(idn.FAMILIAS_ROTULO): "rotulo",
    }


def _sin_comentarios(hoja: str) -> str:
    return re.sub(r"/\*.*?\*/", "", hoja, flags=re.DOTALL)


def test_la_hoja_de_estilo_solo_declara_un_tamano_de_letra_y_es_el_de_la_cabecera():
    """**El tamano de letra lo decide `fuente_*()`, no el QSS.** Una excepcion.

    Es la regla que impide que vuelva el aplanamiento: si una regla del QSS
    declara `font-size`, ese tamano pisa al que pida el codigo, y el dia que
    alguien escriba `Cifra(px=26)` debajo de esa regla se llevara un 13 sin
    enterarse.

    La unica excepcion es `QHeaderView::section`, y no por comodidad: la
    cabecera de una tabla es un pseudo-elemento y **no hay forma de vestirla
    desde el codigo**. Las dos que parecen que valdrian estan comprobadas y no
    valen: `QHeaderView.setFont()` lo borra Qt en el siguiente `polish`, y el
    `Qt.FontRole` del modelo no cambia el dibujo. Ver `fuente_cabecera_tabla()`.
    """
    hoja = _sin_comentarios(idn.hoja_de_estilo())
    con_tamano = []
    for selector, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", hoja):
        if "font-size" in cuerpo:
            con_tamano.append(selector.strip())
    assert con_tamano == ["QHeaderView::section"], (
        f"reglas del QSS que declaran font-size: {con_tamano}. Solo puede declararlo "
        f"la cabecera de tabla; el resto de tamanos salen de `fuente_*()`."
    )


def test_el_selector_universal_no_declara_tamano_de_letra():
    """El caso concreto del que salio todo, dicho con su nombre."""
    hoja = _sin_comentarios(idn.hoja_de_estilo())
    universal = re.search(r"QWidget\s*\{([^}]*)\}", hoja)
    assert universal is not None, "ha desaparecido la regla QWidget de la hoja"
    assert "font-size" not in universal.group(1), (
        "`QWidget` ha vuelto a declarar font-size. Esa regla casa con todos los widgets "
        "de la app y aplana la escala tipografica entera: las cifras de 22, 24 y 26 px "
        "salen a ese tamano y no al suyo."
    )


def test_cada_widget_se_pinta_con_el_tamano_de_letra_que_pide():
    """LA PRUEBA DE FONDO, y se hace sobre la ventana entera, no en un banco.

    Se intercepta cada `setFont()` de la construccion; de los que reciben una
    fuente de la identidad se apunta el tamano pedido, y al final —con la hoja
    aplicada y la ventana asentada— se mide el tamano que de verdad tiene el
    widget. Si no coinciden, alguien esta pidiendo una cosa y pintando otra.

    Antes de arreglarlo: 96 widgets pedian fuente de la identidad y 41 no
    conseguian el tamano (o la familia) que pedian.
    """
    from PySide6.QtWidgets import QWidget

    app_qt()
    pedidas: dict[int, tuple[str, int, float]] = {}
    original = QWidget.setFont
    roles = _familias_de_rol()

    def espia(self, fuente):  # noqa: ANN001
        try:
            rol = roles.get(tuple(fuente.families()))
            if rol is not None:
                pedidas[id(self)] = (rol, fuente.pixelSize(), fuente.letterSpacing())
        except Exception:  # noqa: BLE001 - un espia no puede tumbar la construccion
            pass
        return original(self, fuente)

    QWidget.setFont = espia
    try:
        v = ventana(demo())
        asentar()
    finally:
        QWidget.setFont = original

    try:
        mirados, fallos = 0, []
        for w in v.findChildren(QWidget):
            pedido = pedidas.get(id(w))
            if pedido is None:
                continue
            rol, px, tracking = pedido
            f = w.font()
            mirados += 1
            if f.pixelSize() != px:
                fallos.append(f"{type(w).__name__}: pide {px}px y se pinta a {f.pixelSize()}px")
            elif rol == "cifra" and not es_monoespaciada(f):
                fallos.append(f"{type(w).__name__}: pide monoespaciada y no la consigue")
            elif abs(f.letterSpacing() - tracking) > 0.01:
                fallos.append(
                    f"{type(w).__name__}: pide {tracking:.2f} de tracking y tiene "
                    f"{f.letterSpacing():.2f}"
                )
        assert mirados > 50, f"el espia solo ha visto {mirados} widgets: se ha quedado ciego"
        assert not fallos, (
            f"{len(fallos)} de {mirados} widgets piden una letra y se pintan con otra:\n"
            + "\n".join(fallos)
        )
    finally:
        v.close()


def test_la_ruta_del_cube_va_en_monoespaciada():
    """Una ruta es codigo, y la identidad pide monoespaciada para toda ruta.

    `gui/pantalla_aplicar.py`, `ruta_look`: se le ponia `fuente_cifra(11)` a
    mano y salia en la de texto, porque sin la clase `cifra` la unica regla que
    le declaraba familia era la universal. Y es justo donde mas se nota: una
    ruta con espacios, elidida por el medio.
    """
    v = ventana(demo())
    try:
        v.ir_a(2)
        asentar()
        ruta = v.p_aplicar.ruta_look
        assert ruta.texto_completo().endswith(".cube"), "esto ya no es la ruta del look"
        assert es_monoespaciada(ruta.font()), (
            f"la ruta del .cube sale en {ruta.font().families()[:1]} y tiene que ir "
            f"en monoespaciada"
        )
    finally:
        v.close()
