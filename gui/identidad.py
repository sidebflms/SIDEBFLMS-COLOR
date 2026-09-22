"""Los colores, las fuentes y la hoja de estilo de SIDEBFLMS COLOR.

**Todo lo que hay aqui sale de `docs/IDENTIDAD.md` y es literal.** Si a alguien
le hace falta un color que no esta en la lista, no se inventa: se usa el mas
cercano y se anota. Lo que se ha anotado esta en `gui/NOTAS.md`, apartado
«colores que hicieron falta y no estaban».

LAS TRES REGLAS QUE SE INCUMPLEN SOLAS
--------------------------------------
1. **El rojo no es color de error.** El naranja de marca es marca, no alarma.
   Aqui no hay ni un solo token de error, ni de aviso, ni de «confianza baja»
   en rojo. Un aviso se distingue por forma y por texto.
2. **Los tokens de estado del inventario no se reutilizan.** `#00d492`,
   `#ffb900`, `#3ad6cf`, `#71717b` con tratamiento de pastilla estan reservados.
   La confianza y el estado de cada modulo se diferencian **por forma**: relleno,
   contorno, borde discontinuo. Ver `FormaConfianza`.
3. **Toda cifra va en monoespaciada.** Usa `fuente_cifra()` o la clase QSS
   `cifra`. Sin excepcion: dE, porcentajes, CDL, tamanos de LUT, IDs de clip.
   Ojo con **quien gana a `setFont()`**: en Qt, una propiedad de fuente
   declarada por una regla del QSS que case con el widget le gana al
   `setFont()`, y la mezcla es por propiedad (lo que la regla no declara se
   queda como lo dejo el codigo). La regla `QWidget` de aqui declara
   `font-family` y casa con TODO, asi que un `QLabel` con `fuente_cifra()`
   puesta a mano sale en la de texto si ninguna regla le declara la familia
   monoespaciada. Por eso las cifras van en la clase `Cifra`, que lleva la clase
   QSS puesta.

4. **NINGUNA REGLA DE ESTA HOJA DECLARA `font-size`.** Es la regla que impide
   que vuelva el bug de la escala tipografica del dia 2: con
   `QWidget { font-size: 13px }` puesto, los 22, 24 y 26 px de las cifras
   grandes y los 10, 11, 12 y 15 px del texto de cuerpo salian TODOS a 13, y la
   jerarquia entera quedaba aplanada. El tamano lo decide `fuente_texto()`,
   `fuente_cifra()` o `fuente_rotulo()`, y el tamano base de la app lo pone
   `QApplication.setFont()`. Unica excepcion, `QHeaderView::section`: una
   cabecera de tabla es un pseudo-elemento y no se puede vestir desde el codigo
   (comprobado con `setFont` y con `Qt.FontRole`). Todo esto, con las
   mediciones, en `gui/NOTAS.md` §12.
5. **`#ff6a3d` como pastilla, nunca.** Ver el comentario de `BRAND_400`. En
   pastilla ese hexadecimal es el estado «Fuera» del inventario de SIDEBFLMS.

SOBRE `#3ad6cf`
---------------
`cyan-glow` esta en la paleta de marca como «unico, para datos secundarios» y a
la vez es el token de estado «En taller». Aqui se usa **solo** como color de
texto/linea para datos secundarios (el eje de un grafico, la cifra de referencia
de una comparacion), nunca con tratamiento de pastilla. Misma interpretacion que
`docs/IDENTIDAD.md` hace con `#ff6a3d`.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtGui import QColor, QFont

# ---------------------------------------------------------------------------
# Color. Literal, cerrado, sin interpolar.
# ---------------------------------------------------------------------------

BRAND_500 = "#e8451d"  # acento / foco / activo
BRAND_600 = "#bb4223"  # fondo de boton primario (el 500 no pasa AA)

#: `#ff6a3d` COMO TEXTO E ICONOS DE MARCA, SI. COMO PASTILLA, NUNCA.
#:
#: Confirmado por Mario. En pastilla (fondo al 12%, borde al 25%, texto pleno)
#: este hexadecimal significa **«Fuera»** en el inventario de SIDEBFLMS, que es
#: otro sistema en produccion de la casa. Pintar aqui una pastilla `#ff6a3d`
#: diria «Fuera» a cualquiera que conozca el inventario, y contaminaria los dos
#: sistemas a la vez: aqui pareceria un estado que no existe, y alli dejaria de
#: querer decir una sola cosa.
#:
#: Lo que si se hace, porque es su funcion declarada en `docs/IDENTIDAD.md`:
#: texto, iconos, lineas y trazos de marca sobre superficie oscura. El aviso de
#: desajuste, por ejemplo, va en `#ff6a3d` pero con forma de ROMBO y no de
#: pastilla; la insignia de confianza, que si es una pastilla, se rellena con
#: `brand-600` o no se rellena.
#:
#: Es comprobable: `tests/test_gui_identidad.py` verifica que ninguna pastilla
#: de la interfaz usa este hexadecimal de fondo, ni en la hoja de estilo ni en
#: lo que se pinta a mano.
BRAND_400 = "#ff6a3d"  # texto e iconos de marca sobre oscuro. NUNCA de pastilla.

BRAND_50 = "#fdf4ee"  # texto principal sobre oscuro
CYAN_GLOW = "#3ad6cf"  # unico, datos secundarios

FONDO = "#0a0908"
HONDO = "#0d0b08"
PANEL = "#131110"
CRISTAL = "#16130f"

#: Los cuatro tonos de superficie en orden de profundidad, por si alguien
#: necesita apilar. Nada de negro puro: el mas oscuro es #0a0908.
SUPERFICIES = (FONDO, HONDO, PANEL, CRISTAL)


def rgba(hex_color: str, alpha: float) -> str:
    """`#rrggbb` + opacidad -> cadena `rgba(...)` valida en QSS.

    Es la unica forma que se usa aqui de «hacer» un color que no esta en la
    paleta: bajarle la opacidad a uno que si esta. No se mezclan hexadecimales
    a ojo ni se inventan grises, entre otras cosas porque `#71717b` (el gris del
    inventario) esta reservado y cualquier gris inventado acabaria pareciendose.
    """
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.3f})"


def color(hex_color: str, alpha: float = 1.0) -> QColor:
    """Igual que `rgba()` pero devolviendo un `QColor`, para pintar a mano."""
    c = QColor(hex_color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


#: Texto secundario y bordes. Derivados por OPACIDAD de `brand-50`, que es el
#: color de texto de la paleta. Ver NOTAS.md: la identidad no trae un token de
#: texto apagado ni de borde, y un gris inventado (#71717b y compania) esta
#: reservado al inventario.
TEXTO_APAGADO_A = 0.62
TEXTO_TENUE_A = 0.40
BORDE_A = 0.12
BORDE_FUERTE_A = 0.22

# ---------------------------------------------------------------------------
# Tipografia
# ---------------------------------------------------------------------------

#: Se pide SIEMPRE primero la familia de marca. Ninguna de las tres esta
#: instalada en este Mac (comprobado con QFontDatabase) y no se pueden
#: descargar, asi que hoy caen en la alternativa; el dia que Mario las instale
#: la app las coge sola sin tocar una linea.
FAMILIAS_TEXTO = ["Inter", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"]
FAMILIAS_ROTULO = ["Chakra Petch", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"]
FAMILIAS_CIFRA = ["JetBrains Mono", "Menlo", "Monaco", "Courier New", "monospace"]


#: Relleno horizontal de una seccion de cabecera de tabla, en px a cada lado.
#: Vive aqui y no dentro del QSS porque `gui/pantalla_clips.py` calcula con el
#: el ancho fijo de sus columnas de cifras: si el numero estuviera escrito en
#: dos sitios, el dia que uno cambiara el otro seguiria calculando con el viejo
#: y las cabeceras empezarian a salir con puntos suspensivos. Es el mismo error
#: de raiz que la escala tipografica: dos sitios decidiendo lo mismo.
RELLENO_CABECERA_PX = 6


def _qss_familias(familias: list[str]) -> str:
    return ", ".join(f'"{f}"' if " " in f else f for f in familias)


def fuente_texto(px: int = 13, peso: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(FAMILIAS_TEXTO)
    f.setPixelSize(px)
    f.setWeight(peso)
    return f


def fuente_cifra(px: int = 13, peso: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Monoespaciada. **Toda cifra pasa por aqui.**"""
    f = QFont()
    f.setFamilies(FAMILIAS_CIFRA)
    f.setPixelSize(px)
    f.setWeight(peso)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def fuente_rotulo(px: int = 10, peso: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    """Rotulo de marca: MAYUSCULAS, 10-11px, tracking 0.15-0.18em.

    El tracking se pone en pixeles absolutos (0.16em * px) y no en porcentaje:
    `PercentageSpacing` de Qt es relativo al ancho de cada glifo, o sea que un
    0.16em pedido en porcentaje sale distinto en una `I` que en una `M`. Con
    `AbsoluteSpacing` el valor es el de la identidad y punto.
    """
    f = QFont()
    f.setFamilies(FAMILIAS_ROTULO)
    f.setPixelSize(px)
    f.setWeight(peso)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.16 * px)
    return f


def fuente_cabecera_tabla() -> QFont:
    """La fuente con la que la hoja de estilo pinta las cabeceras de tabla.

    Es `fuente_rotulo(10)` **sin el tracking**, y no porque nos guste: la
    cabecera de una tabla es un pseudo-elemento de QSS y es el unico rotulo de
    la app que no se puede vestir desde el codigo. Comprobado: un
    `QHeaderView.setFont()` lo borra Qt en el siguiente `polish`, y el
    `Qt.FontRole` del modelo no cambia el dibujo ni un pixel. Como QSS no sabe
    escribir el tracking, la cabecera va sin el.

    Existe para poder MEDIR con la misma letra con la que se pinta:
    `gui/pantalla_clips.py` calcula con esto el ancho de sus columnas de cifras.
    Medir con el tracking puesto daria columnas mas anchas de lo necesario.
    """
    f = QFont()
    f.setFamilies(FAMILIAS_ROTULO)
    f.setPixelSize(10)
    f.setWeight(QFont.Weight.DemiBold)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    return f


# ---------------------------------------------------------------------------
# La confianza se diferencia POR FORMA
# ---------------------------------------------------------------------------


class FormaConfianza(Enum):
    """Como se dibuja cada nivel de confianza. **Sin semaforo de colores.**

    Los tres viven en la paleta de marca; lo que cambia es la FORMA del recuadro
    y cuantos escalones lleva el medidor:

    * `alta`  — relleno solido (brand-600), medidor lleno   ###
    * `media` — contorno continuo (brand-400), medidor a dos ##-
    * `baja`  — contorno DISCONTINUO (brand-400 apagado), medidor a uno #--

    Se reconoce en blanco y negro, y en una captura al 50% se distingue el
    relleno del contorno discontinuo sin leer el texto. Un semaforo
    verde/ambar/rojo no cumpliria ninguna de las dos cosas, y ademas pisaria los
    tokens del inventario.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"

    @property
    def escalones(self) -> int:
        return {"alta": 3, "media": 2, "baja": 1}[self.value]

    @property
    def relleno(self) -> QColor | None:
        """Color de relleno, o None si la forma es de contorno."""
        return color(BRAND_600) if self is FormaConfianza.ALTA else None

    @property
    def trazo(self) -> QColor:
        if self is FormaConfianza.ALTA:
            return color(BRAND_500)
        if self is FormaConfianza.MEDIA:
            return color(BRAND_400)
        return color(BRAND_400, 0.55)

    @property
    def discontinuo(self) -> bool:
        return self is FormaConfianza.BAJA

    @property
    def texto(self) -> QColor:
        return color(BRAND_50) if self is FormaConfianza.ALTA else color(BRAND_400)

    @staticmethod
    def de_nivel(nivel: str) -> FormaConfianza:
        """`Confidence.level` ('alta'/'media'/'baja') -> forma."""
        return FormaConfianza(nivel)


# ---------------------------------------------------------------------------
# Hoja de estilo
# ---------------------------------------------------------------------------


def hoja_de_estilo() -> str:
    """QSS de toda la app. Se aplica en el `QApplication`, una sola vez."""
    texto = _qss_familias(FAMILIAS_TEXTO)
    cifra = _qss_familias(FAMILIAS_CIFRA)
    rotulo = _qss_familias(FAMILIAS_ROTULO)
    borde = rgba(BRAND_50, BORDE_A)
    borde_fuerte = rgba(BRAND_50, BORDE_FUERTE_A)
    apagado = rgba(BRAND_50, TEXTO_APAGADO_A)
    tenue = rgba(BRAND_50, TEXTO_TENUE_A)
    return f"""
    /* EL SELECTOR UNIVERSAL NO DECLARA `font-size`. NO SE LE VUELVE A PONER.
       Aqui estuvo el bug de la escala tipografica: `QWidget` casa con TODOS los
       widgets de la app, y una propiedad de fuente declarada en una regla que
       casa gana a `setFont()`. Con `font-size: 13px` aqui, los 22, 24 y 26 px
       de las cifras grandes y los 10, 11, 12 y 15 px del texto de cuerpo se
       pintaban todos a 13: la jerarquia entera aplanada. El tamano base lo pone
       ahora `QApplication.setFont(fuente_texto(13))` en `crear_app()`, que SI
       cede ante un `setFont()` del widget.
       La familia se queda: es la unica declaracion de fuente que se quiere
       universal (que nada salga en la fuente del sistema por descuido), y la
       familia de cada rol la traen las reglas de abajo. */
    QWidget {{
        background: {FONDO};
        color: {BRAND_50};
        font-family: {texto};
    }}
    QMainWindow, QDialog {{ background: {FONDO}; }}

    /* Las etiquetas NO pintan fondo. La regla QWidget de arriba les da
       `fondo` (#0a0908) y, encima de un panel (#131110), cada rotulo salia
       con su propio rectangulo negro detras. Se veia en todas las capturas
       de la primera tanda. */
    QLabel {{ background: transparent; }}
    QTextBrowser, QTextEdit {{
        background: transparent;
        border: none;
        color: {BRAND_50};
        selection-background-color: {rgba(BRAND_500, 0.35)};
    }}

    /* --- superficies --- */
    QFrame#panel {{
        background: {PANEL};
        border: 1px solid {borde};
        border-radius: 6px;
    }}
    QFrame#cristal {{
        background: {CRISTAL};
        border: 1px solid {borde};
        border-radius: 6px;
    }}
    QFrame#hondo {{ background: {HONDO}; border: none; }}
    QFrame#separador {{ background: {borde}; border: none; max-height: 1px; }}

    /* --- texto --- */
    /* Ni `#rotulo` ni `#titulo` declaran `font-size`, y es a proposito: el
       tamano y el tracking (0.16em ABSOLUTO, que QSS no sabe escribir) tienen
       que salir de la misma llamada a `fuente_rotulo(px)`. Cuando el tamano lo
       ponia la hoja y el tracking el codigo, salia un tracking de 10px sobre
       una letra de 11: 0,145em, por debajo del 0,15 de la identidad. */
    QLabel#rotulo {{
        font-family: {rotulo};
        font-weight: 600;
        color: {apagado};
    }}
    QLabel#titulo {{
        font-family: {rotulo};
        font-weight: 700;
        color: {BRAND_400};
    }}
    QLabel#apagado {{ color: {apagado}; }}
    QLabel#tenue {{ color: {tenue}; }}
    QLabel.cifra, QLabel#cifra {{ font-family: {cifra}; }}
    /* Bloques de cifras apagadas: el CDL del lateral de «antes/despues» y los
       datos del LUT del panel de ingenieria inversa. El id hace falta para la
       FAMILIA -- la regla `QWidget` reparte la de texto a todo el mundo y gana a
       `setFont()`--, pero el TAMANO lo pone la pantalla con `fuente_cifra(11)`.
       (Aqui habia ademas un `QLabel#cifraGrande` con `font-size: 26px` que no
       usaba nadie. Se ha quitado: era una trampa esperando a que alguien le
       pusiera ese id a una cifra de otro tamano.) */
    QLabel#cifraApagada {{
        font-family: {cifra};
        color: {apagado};
    }}
    QLabel#secundario {{ color: {CYAN_GLOW}; font-family: {cifra}; }}

    /* --- botones --- */
    QPushButton {{
        background: transparent;
        border: 1px solid {borde_fuerte};
        border-radius: 5px;
        padding: 7px 14px;
        color: {BRAND_50};
    }}
    QPushButton:hover {{ border-color: {BRAND_400}; color: {BRAND_400}; }}
    QPushButton:pressed {{ background: {rgba(BRAND_500, 0.16)}; }}
    QPushButton:disabled {{ color: {tenue}; border-color: {borde}; }}
    QPushButton#primario {{
        background: {BRAND_600};
        border: 1px solid {BRAND_500};
        color: {BRAND_50};
        font-weight: 600;
    }}
    QPushButton#primario:hover {{ background: {BRAND_500}; color: {BRAND_50}; }}
    QPushButton#primario:disabled {{
        background: {rgba(BRAND_600, 0.35)};
        border-color: {borde};
        color: {tenue};
    }}
    QPushButton#navegacion {{
        text-align: left;
        border: none;
        border-left: 2px solid transparent;
        border-radius: 0px;
        padding: 10px 14px;
        color: {apagado};
        font-family: {rotulo};
        font-weight: 600;
    }}
    QPushButton#navegacion:hover {{ color: {BRAND_50}; background: {rgba(BRAND_50, 0.04)}; }}
    QPushButton#navegacion:checked {{
        color: {BRAND_400};
        border-left: 2px solid {BRAND_500};
        background: {rgba(BRAND_500, 0.10)};
    }}

    /* --- entradas --- */
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
        background: {HONDO};
        border: 1px solid {borde_fuerte};
        border-radius: 4px;
        padding: 5px 7px;
        selection-background-color: {rgba(BRAND_500, 0.45)};
        font-family: {cifra};
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: {BRAND_500};
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
    QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; background: transparent; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        border: 1px solid {borde_fuerte};
        selection-background-color: {rgba(BRAND_500, 0.30)};
    }}

    /* --- tabla de clips --- */
    QTableView {{
        background: {PANEL};
        alternate-background-color: {CRISTAL};
        gridline-color: transparent;
        border: 1px solid {borde};
        border-radius: 6px;
        selection-background-color: {rgba(BRAND_500, 0.22)};
        selection-color: {BRAND_50};
        outline: none;
    }}
    /* LA UNICA REGLA DE LA HOJA QUE DECLARA UN TAMANO DE LETRA, y es una
       excepcion con motivo medido: la cabecera de una tabla es un
       PSEUDO-ELEMENTO, y no hay forma de darle la fuente desde el codigo.
       Comprobadas las dos:
         * `QHeaderView.setFont(fuente_rotulo(10))` -> Qt se la borra en el
           siguiente `polish` y la deja en la heredada (13 px, familia de texto).
         * `headerData(..., Qt.FontRole)` -> el dibujo de la cabecera no cambia
           ni un pixel; manda esta regla.
       O sea que aqui el tamano SI tiene que estar. Lo que no se puede escribir
       en QSS es el tracking, asi que los rotulos de la cabecera son el unico
       sitio de la app que va sin el 0,15-0,18em de la identidad. Esta anotado.
       El relleno sale de `RELLENO_CABECERA_PX` porque con el mismo numero se
       calcula el ancho de las columnas de cifras en `gui/pantalla_clips.py`. */
    QHeaderView::section {{
        background: {HONDO};
        color: {apagado};
        border: none;
        border-bottom: 1px solid {borde};
        padding: 8px {RELLENO_CABECERA_PX}px;
        font-family: {rotulo};
        font-size: 10px;
        font-weight: 600;
    }}
    QTableView::item {{ padding: 4px 6px; }}
    QTableCornerButton::section {{ background: {HONDO}; border: none; }}

    QListWidget {{
        background: {PANEL};
        border: 1px solid {borde};
        border-radius: 6px;
        outline: none;
    }}
    QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {rgba(BRAND_50, 0.05)}; }}
    QListWidget::item:selected {{ background: {rgba(BRAND_500, 0.22)}; color: {BRAND_50}; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 13px; height: 13px;
        border: 1px solid {borde_fuerte};
        border-radius: 3px;
        background: {HONDO};
    }}
    QCheckBox::indicator:checked {{ background: {BRAND_600}; border-color: {BRAND_500}; }}

    /* --- barras --- */
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0px; }}
    QScrollBar::handle:vertical {{
        background: {rgba(BRAND_50, 0.16)}; border-radius: 4px; min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {rgba(BRAND_400, 0.55)}; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0px; }}
    QScrollBar::handle:horizontal {{
        background: {rgba(BRAND_50, 0.16)}; border-radius: 4px; min-width: 28px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QSplitter::handle {{ background: {borde}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}

    QToolTip {{
        background: {CRISTAL};
        color: {BRAND_50};
        border: 1px solid {BRAND_600};
        padding: 5px 7px;
    }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


__all__ = [
    "BORDE_A",
    "BORDE_FUERTE_A",
    "BRAND_50",
    "BRAND_400",
    "BRAND_500",
    "BRAND_600",
    "CRISTAL",
    "CYAN_GLOW",
    "FAMILIAS_CIFRA",
    "FAMILIAS_ROTULO",
    "FAMILIAS_TEXTO",
    "FONDO",
    "HONDO",
    "PANEL",
    "RELLENO_CABECERA_PX",
    "SUPERFICIES",
    "TEXTO_APAGADO_A",
    "TEXTO_TENUE_A",
    "FormaConfianza",
    "color",
    "fuente_cabecera_tabla",
    "fuente_cifra",
    "fuente_rotulo",
    "fuente_texto",
    "hoja_de_estilo",
    "rgba",
]
