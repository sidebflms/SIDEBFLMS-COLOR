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

# SUITE (prototipo 2026-10-06): estos valores son los de `suite/tokens.css` v2,
# que son los de sidebflms.com tal cual esta hoy. Los NOMBRES se conservan para
# que el cambio sea un parche pequeno; lo que cambia es el valor.
BRAND_500 = "#e8451d"  # acento: SOLO display grande, iconos, filetes (4,2:1) -- no texto
BRAND_600 = "#bb4223"  # fondo de boton primario (crema encima 4,57:1); hover SUBE a BRAND_500

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

BRAND_50 = "#f2ece4"  # texto principal (suite: --sb-bone, 14,2:1)
SMOKE = "#938e89"  # texto secundario (suite: --sb-smoke). NUNCA con opacity
CYAN_GLOW = "#3ad6cf"  # unico, datos secundarios

FONDO = "#1e1e1e"  # suite --sb-ink-800: fondo base
HONDO = "#141414"  # suite --sb-ink-900: carril, entorno NEUTRO alrededor de la imagen
PANEL = "#262626"  # suite --sb-ink-700: superficies opacas (menus, combos)
CRISTAL = "#262626"  # filas alternas / tooltip; el cristal real se pinta en `widgets.Panel`
LINEA = "#333130"  # suite --sb-ink-600

#: Los cuatro tonos de superficie en orden de profundidad, por si alguien
#: necesita apilar. Nada de negro puro: el mas oscuro es #141414.
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
TEXTO_APAGADO_A = 0.62  # OBSOLETO en la suite: ver TEXTO_APAGADO (solido)
#: 0,40 -> 0,56 (auditoría de diseño 2026-10-06): a 0,40 el texto tenue daba
#: 3,55-3,63:1 sobre las cuatro superficies, por debajo del 4,5:1 de WCAG AA
#: para texto normal. A 0,56 da 5,95-6,06:1. Sigue siendo `brand-50` bajado de
#: opacidad, no un gris nuevo. OJO: queda cerca de 0,62 (apagado); la jerarquía
#: entre los dos ya se ve poco y la distingue sobre todo el uso, no el tono.
TEXTO_TENUE_A = 0.56
BORDE_A = 0.12
BORDE_FUERTE_A = 0.22

#: SUITE: texto secundario SOLIDO (--sb-smoke), nunca por opacidad. Sobre
#: #262626 da 4,7:1; sobre #1e1e1e 5,1:1. La suite NO tiene un tercer escalon
#: («tenue»): apagado y tenue son el mismo color y la jerarquia la dan el
#: tamano y el peso. Se propone `--sb-ink-faint` (ver INFORME).
TEXTO_APAGADO = SMOKE
TEXTO_TENUE = SMOKE
#: Borde de campo/boton: smoke al 55 % sobre #1e1e1e = 3,0:1 (el 1,86:1 de la
#: auditoria). Es un borde, no un texto: aqui la opacidad si vale.
BORDE_CONTROL_A = 0.55
#: Radios de la suite (la web): tarjeta 16, control 8, pildora.
RADIO_TARJETA = 16
RADIO_CONTROL = 8

# ---------------------------------------------------------------------------
# Tipografia
# ---------------------------------------------------------------------------

#: Suelo de tamano para TODO texto informativo (rotulos, cabeceras de tabla,
#: insignias, pie, notas, cifras pequenas) y tamano del cuerpo (tablas y
#: parrafos). Auditoria de diseno 2026-10-06: habia 44 textos a 10 px y 44 a
#: 11 px; por debajo de 12 px no se lee con comodidad en una pantalla de
#: trabajo. **Aqui y en ningun otro sitio se decide el numero**: el error de
#: raiz de la escala tipografica era justo dos sitios decidiendo lo mismo.
PX_MIN_INFORMATIVO = 12
PX_CUERPO = 14

#: Se pide SIEMPRE primero la familia de marca. Ninguna de las tres esta
#: instalada en este Mac (comprobado con QFontDatabase) y no se pueden
#: descargar, asi que hoy caen en la alternativa; el dia que Mario las instale
#: la app las coge sola sin tocar una linea.
FAMILIAS_TEXTO = ["Montserrat", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"]
FAMILIAS_ROTULO = ["Montserrat", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"]
#: SUITE: sin mono. Las cifras van en Montserrat con `tnum` (cifras tabulares):
#: todas las cifras miden lo mismo y las columnas alinean a la derecha igual.
#: Lo que se pierde, dicho en el INFORME: 0/O y l/1 en ids y rutas, y la
#: columna de decimales cuando el numero no lleva decimales fijos.
FAMILIAS_CIFRA = ["Montserrat", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"]
#: Akira Expanded: SOLO >= 18 px y SOLO ASCII (104 glifos: sin tildes, sin n con tilde, sin Delta).
#: **El archivo de Akira NO va en el repo** (licencia comercial de SIDEBFLMS, repo
#: publico): se busca en `gui/fuentes/` y luego entre las fuentes instaladas del
#: sistema; si no aparece, el titulo cae a Montserrat 800 (`fuente_display`).
PX_DISPLAY_MIN = 18
FAMILIA_DISPLAY_RESPALDO = "Montserrat"
PESO_DISPLAY_RESPALDO = QFont.Weight.ExtraBold


#: Relleno horizontal de una seccion de cabecera de tabla, en px a cada lado.
#: Vive aqui y no dentro del QSS porque `gui/pantalla_clips.py` calcula con el
#: el ancho fijo de sus columnas de cifras: si el numero estuviera escrito en
#: dos sitios, el dia que uno cambiara el otro seguiria calculando con el viejo
#: y las cabeceras empezarian a salir con puntos suspensivos. Es el mismo error
#: de raiz que la escala tipografica: dos sitios decidiendo lo mismo.
RELLENO_CABECERA_PX = 6


def _qss_familias(familias: list[str]) -> str:
    return ", ".join(f'"{f}"' if " " in f else f for f in familias)


#: Tracking de los rotulos: 0,16em -> 0,10em. Montserrat es mas ancha que Chakra Petch y la suite
#: usa 0,08em en `.sb-btn`; 0,10 deja algo de aire sin ensanchar la ventana.
TRACKING_EM = 0.10


def fuente_texto(px: int = PX_CUERPO, peso: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(FAMILIAS_TEXTO)
    f.setPixelSize(px)
    f.setWeight(peso)
    # SUITE: cifras tabulares tambien en el texto corrido. Los bloques HTML de
    # Aplicar (CDL, versiones) llevan cifras dentro de texto y no pasan por
    # `fuente_cifra`; sin `tnum` salian con cifras de ancho distinto y las
    # columnas del plan dejaban de alinear.
    f.setFeature(QFont.Tag("tnum"), 1)
    return f


def fuente_cifra(px: int = PX_CUERPO, peso: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Monoespaciada. **Toda cifra pasa por aqui.**"""
    f = QFont()
    f.setFamilies(FAMILIAS_CIFRA)
    f.setPixelSize(px)
    f.setWeight(peso)
    # SUITE: no hay mono. Cifras tabulares de Montserrat (`tnum`).
    f.setFeature(QFont.Tag("tnum"), 1)
    return f


#: Familia de Akira encontrada (`""` = ya se busco y no esta; `None` = sin buscar).
_AKIRA: str | None = None
#: Archivos ya registrados en Qt -> su indice (para no registrarlos dos veces).
_REGISTRADAS: dict[str, int] = {}


def familia_akira(*, volver_a_buscar: bool = False) -> str:
    """El nombre de la familia de Akira Expanded, o `""` si no esta disponible.

    Orden de busqueda: 1) `gui/fuentes/` (lo que `cargar_fuentes()` registro);
    2) las fuentes instaladas en el sistema. No se mira por el nombre del fichero
    (el de la casa es «SIDEBFLMS TIPOGRAFIA (c SIDEBFLMS).otf») sino por el nombre
    de FAMILIA: cualquier familia que contenga «akira».
    """
    global _AKIRA
    if _AKIRA is None or volver_a_buscar:
        from PySide6.QtGui import QFontDatabase

        _AKIRA = next((f for f in QFontDatabase.families() if "akira" in f.lower()), "")
    return _AKIRA


def fuente_display(px: int = PX_DISPLAY_MIN) -> QFont:
    """Akira Expanded (suite) para titulos. SOLO >= 18 px y SOLO ASCII.

    Si Akira no esta (CI, un clon publico: el archivo no se versiona), cae a
    **Montserrat 800** al mismo tamano, sin romper nada.
    """
    f = QFont()
    akira = familia_akira()
    if akira:
        f.setFamilies([akira])
        f.setWeight(QFont.Weight.Normal)  # Akira solo tiene un peso: no se le pide negrita
    else:
        f.setFamilies([FAMILIA_DISPLAY_RESPALDO])
        f.setWeight(PESO_DISPLAY_RESPALDO)
    f.setPixelSize(max(px, PX_DISPLAY_MIN))
    f.setFeature(QFont.Tag("tnum"), 1)
    return f


def regla_display_qss() -> str:
    """La regla QSS de `QLabel#display`, con la familia y el peso que toquen.

    Hace falta en QSS porque la regla `QWidget { font-family }` gana a `setFont()`.
    """
    akira = familia_akira()
    if akira:
        return f'QLabel#display {{ font-family: "{akira}"; font-weight: normal; color: {BRAND_50}; }}'
    return (
        f'QLabel#display {{ font-family: "{FAMILIA_DISPLAY_RESPALDO}"; font-weight: 800; '
        f"color: {BRAND_50}; }}"
    )


def cargar_fuentes() -> list[str]:
    """Registra las fuentes de `gui/fuentes/` y devuelve las familias cargadas.

    * **Montserrat** (licencia OFL) va en el repo: 5 pesos estaticos.
    * **Akira** NO va en el repo (licencia comercial de la casa; el repo de COLOR
      es publico): Mario copia a mano el `.otf` a `gui/fuentes/` en su equipo
      (esta en `.gitignore`). En la CI y en clones publicos no estara y los
      titulos saldran en Montserrat 800.

    Si una carpeta o un archivo faltan o no se pueden leer, no se rompe nada.
    """
    from pathlib import Path

    from PySide6.QtGui import QFontDatabase

    cargadas: list[str] = []
    carpeta = Path(__file__).resolve().parent / "fuentes"
    if carpeta.is_dir():
        for archivo in sorted(carpeta.iterdir()):
            if archivo.suffix.lower() not in (".ttf", ".otf"):
                continue
            clave = str(archivo)
            if clave not in _REGISTRADAS:  # `crear_app()` se llama muchas veces (tests)
                _REGISTRADAS[clave] = QFontDatabase.addApplicationFont(clave)
            if _REGISTRADAS[clave] >= 0:
                cargadas += QFontDatabase.applicationFontFamilies(_REGISTRADAS[clave])
    familia_akira(volver_a_buscar=True)
    return cargadas


def fuente_rotulo(px: int = PX_MIN_INFORMATIVO, peso: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    """Rotulo de marca: MAYUSCULAS, 12px (era 10-11; ver `PX_MIN_INFORMATIVO`),
    tracking 0.15-0.18em.

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
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, TRACKING_EM * px)
    return f


def fuente_cabecera_tabla() -> QFont:
    """La fuente con la que la hoja de estilo pinta las cabeceras de tabla.

    Es `fuente_rotulo(PX_MIN_INFORMATIVO)` **sin el tracking**, y no porque nos guste: la
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
    f.setPixelSize(PX_MIN_INFORMATIVO)
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
    """QSS de toda la app (suite). Se aplica en el `QApplication`, una sola vez.

    PROTOTIPO SUITE 2026-10-06. Reglas que se mantienen: ninguna regla declara
    `font-size` (salvo la cabecera de tabla), sin rojo, sin pastillas de estado.
    Lo nuevo: el fondo y los paneles son TRANSLUCIDOS (el cristal se pinta en
    `widgets.Panel` y `ventana.FondoSuite`, no en QSS: QSS no tiene desenfoque),
    botones en pildora, foco 2 px #ff6a3d, radios de la web (8 / 16 / pildora).
    """
    texto = _qss_familias(FAMILIAS_TEXTO)
    cifra = _qss_familias(FAMILIAS_CIFRA)
    rotulo = _qss_familias(FAMILIAS_ROTULO)
    borde = rgba(BRAND_50, 0.09)  # --sb-glass-stroke
    borde_control = rgba(SMOKE, BORDE_CONTROL_A)
    from pathlib import Path

    # El check va en SVG junto al logo (QSS `image:` necesita archivo). Si falta, el
    # relleno naranja del recuadro marcado sigue distinguiendo marcado de vacio.
    _chk = Path(__file__).resolve().parent / "logo" / "check.svg"
    check = f'image: url("{_chk.as_posix()}");' if _chk.is_file() else ""
    apagado = SMOKE
    tenue = SMOKE
    vidrio_campo = "rgba(20, 20, 20, 0.55)"
    return f"""
    /* EL SELECTOR UNIVERSAL NO DECLARA `font-size`. NO SE LE VUELVE A PONER
       (ver NOTAS.md §12). Suite: `QWidget` ya NO pinta fondo -- el fondo y el
       cristal los pinta la ventana --, asi que las curvas de nivel se ven a
       traves de todo lo transparente. Quien necesite fondo opaco lo declara. */
    QWidget {{
        background: transparent;
        color: {BRAND_50};
        font-family: {texto};
    }}
    QMainWindow, QDialog, QMessageBox {{ background: {FONDO}; }}

    QLabel {{ background: transparent; }}
    QTextBrowser, QTextEdit {{
        background: transparent;
        border: none;
        color: {BRAND_50};
        selection-background-color: {rgba(BRAND_500, 0.35)};
    }}

    /* --- superficies: el cristal lo pinta `Panel.paintEvent` --- */
    QFrame#panel, QFrame#cristal {{ background: transparent; border: none; }}
    QFrame#hondo, QWidget#hondo {{ background: {HONDO}; border: none; }}
    QFrame#separador {{ background: {borde}; border: none; max-height: 1px; }}

    /* --- texto --- */
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
    QLabel#cifraApagada {{
        font-family: {cifra};
        color: {apagado};
    }}
    {regla_display_qss()}
    QLabel#secundario {{ color: {CYAN_GLOW}; font-family: {cifra}; }}

    /* --- botones: PILDORA, texto en frase (NO mayusculas: los textos largos como
       «Copiar nodos al resto» volverian a cortarse, PR #7) y foco de 2 px (el borde
       de 1 px pasa a 2 px y el relleno baja 1 px para que el boton no cambie de
       tamano) --- */
    QPushButton {{
        background: transparent;
        border: 1px solid {borde_control};
        /* QSS: un radio MAYOR que la mitad del alto no se pinta (sale esquina viva);
           15 px da pildora en los botones de 30-34 px de alto. */
        border-radius: 15px;
        padding: 7px 16px;
        color: {BRAND_50};
        font-weight: 600;
    }}
    QPushButton:hover {{ border-color: {BRAND_400}; color: {BRAND_400}; }}
    QPushButton:pressed {{ background: {rgba(BRAND_500, 0.16)}; }}
    QPushButton:focus {{ border: 2px solid {BRAND_400}; padding: 6px 15px; }}
    QPushButton:disabled {{ color: {SMOKE}; border-color: {borde}; }}
    QPushButton#primario {{
        background: {BRAND_600};
        border: 1px solid {BRAND_600};
        color: {BRAND_50};
        font-weight: 700;
    }}
    /* Hover SUBE a #e8451d (como la web): solo con raton. Con crema encima da ~3,5:1,
       por debajo de 4,5:1 -- aceptado por Mario (decision por defecto v3 de la suite). */
    QPushButton#primario:hover {{ background: {BRAND_500}; border-color: {BRAND_500}; color: {BRAND_50}; }}
    QPushButton#primario:focus {{ border: 2px solid {BRAND_400}; }}
    QPushButton#primario:disabled {{
        background: {rgba(BRAND_600, 0.35)};
        border-color: {borde};
        color: {SMOKE};
    }}
    QPushButton#navegacion {{
        text-align: left;
        /* Borde transparente de 1 px (2 a la izquierda) y no `none`: asi el foco
           (abajo) solo cambia su COLOR. Con `none`, el foco le anadia un borde y
           el boton crecia 2 px al recibirlo -- un indicador de foco no puede
           mover el layout. */
        border: 1px solid transparent;
        border-left: 2px solid transparent;
        border-radius: 0px;
        /* El borde transparente de arriba (1 px arriba, abajo y a la derecha) se
           descuenta del relleno: el boton no crece por el. El carril mide 186 px
           fijos y «INGENIERIA INVERSA» va justa: con la letra de 12 px (bloque 3
           de la auditoria de diseno) pide 187, asi que a la derecha se quita 1 px
           mas. El texto va alineado a la izquierda: no se nota. */
        padding: 9px 12px 9px 14px;
        color: {apagado};
        font-family: {rotulo};
        font-weight: 600;
    }}
    QPushButton#navegacion:hover {{ color: {BRAND_50}; background: {rgba(BRAND_50, 0.04)}; }}
    QPushButton#navegacion:focus {{ border-left: 2px solid {BRAND_400}; padding: 10px 14px; }}
    QPushButton#navegacion:checked {{
        color: {BRAND_400};
        border-left: 2px solid {BRAND_500};
        background: {rgba(BRAND_50, 0.05)};
    }}
    /* Despues de `:checked` a proposito: con foco Y marcado, gana el foco. El
       boton de navegacion tiene un borde transparente que el foco colorea. */
    QPushButton#navegacion:focus {{
        /* Misma geometria que en reposo (el `QPushButton:focus` generico pasa el
           borde a 2 px y haria crecer el boton): aqui solo cambia el COLOR. */
        border: 1px solid {BRAND_400};
        border-left: 2px solid {BRAND_400};
        padding: 9px 12px 9px 14px;
    }}

    /* --- entradas --- */
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
        background: {vidrio_campo};
        border: 1px solid {borde_control};
        border-radius: {RADIO_CONTROL}px;
        padding: 5px 9px;
        selection-background-color: {rgba(BRAND_500, 0.45)};
        font-family: {cifra};
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{
        border: 2px solid {BRAND_400};
        padding: 4px 8px;
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
    QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; background: transparent; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        border: 1px solid {borde_control};
        selection-background-color: {rgba(BRAND_50, 0.10)};
    }}

    /* --- tabla de clips --- */
    QTableView {{
        background: transparent;
        alternate-background-color: {rgba(BRAND_50, 0.025)};
        gridline-color: transparent;
        border: 2px solid transparent;
        border-radius: {RADIO_CONTROL}px;
        selection-background-color: {rgba(BRAND_50, 0.08)};
        selection-color: {BRAND_50};
        outline: none;
    }}
    QTableView:focus {{ border: 2px solid {BRAND_400}; }}
    /* LA UNICA REGLA DE LA HOJA QUE DECLARA UN TAMANO DE LETRA (ver NOTAS.md
       §12): la cabecera de tabla es un pseudo-elemento. */
    QHeaderView::section {{
        background: transparent;
        color: {apagado};
        border: none;
        border-bottom: 1px solid {borde};
        padding: 8px {RELLENO_CABECERA_PX}px;
        font-family: {rotulo};
        font-size: {PX_MIN_INFORMATIVO}px;
        font-weight: 600;
    }}
    QTableView:focus {{ border-color: {BRAND_400}; }}
    QTableView::item {{ padding: 4px 6px; }}
    QTableCornerButton::section {{ background: transparent; border: none; }}

    QListWidget {{
        background: {vidrio_campo};
        border: 2px solid transparent;
        border-radius: {RADIO_CONTROL}px;
        outline: none;
    }}
    QListWidget:focus {{ border: 2px solid {BRAND_400}; }}
    QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {rgba(BRAND_50, 0.05)}; }}
    QListWidget::item:selected {{ background: {rgba(BRAND_50, 0.08)}; color: {BRAND_50}; }}

    QListWidget::indicator {{
        width: 13px; height: 13px;
        border: 1px solid {borde_control};
        border-radius: 3px;
        background: {vidrio_campo};
    }}
    QListWidget::indicator:checked {{ background: {BRAND_600}; border-color: {BRAND_600}; {check} }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 13px; height: 13px;
        border: 1px solid {borde_control};
        border-radius: 3px;
        background: {vidrio_campo};
    }}
    QCheckBox::indicator:checked {{ background: {BRAND_600}; border-color: {BRAND_600}; {check} }}
    QCheckBox:focus {{ color: {BRAND_400}; }}

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

    /* Barra de progreso de MARCA (era el azul del sistema): vidrio de campo, borde de
       control y relleno brand-600. Solo la usa el dialogo de «Reanalizar timeline». */
    QProgressBar {{
        background: {vidrio_campo};
        border: 1px solid {borde_control};
        border-radius: {RADIO_CONTROL}px;
        text-align: center;
        color: {BRAND_50};
        min-height: 16px;
    }}
    QProgressBar::chunk {{ background: {BRAND_600}; border-radius: 7px; }}

    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:horizontal {{ width: 8px; }}
    QSplitter::handle:vertical {{ height: 8px; }}

    QToolTip {{
        background: {PANEL};
        color: {BRAND_50};
        border: 1px solid {borde_control};
        border-radius: 8px;
        padding: 5px 7px;
    }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


__all__ = [
    "BORDE_A",
    "BORDE_FUERTE_A",
    "PX_CUERPO",
    "PX_MIN_INFORMATIVO",
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
    "fuente_display",
    "cargar_fuentes",
    "SMOKE",
    "LINEA",
    "TEXTO_APAGADO",
    "TEXTO_TENUE",
    "FAMILIA_DISPLAY_RESPALDO",
    "familia_akira",
    "regla_display_qss",
    "PX_DISPLAY_MIN",
    "RADIO_TARJETA",
    "RADIO_CONTROL",
    "BORDE_CONTROL_A",
    "TRACKING_EM",
    "fuente_rotulo",
    "fuente_texto",
    "hoja_de_estilo",
    "rgba",
]
