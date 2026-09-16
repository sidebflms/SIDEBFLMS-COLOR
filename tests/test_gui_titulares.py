"""[dia 4] La interfaz dice la cifra que DECIDE, delante, y la cobertura igual de grande.

POR QUE ESTE FICHERO EXISTE
---------------------------
Hasta el dia 3 el panel de ingenieria inversa ponia grande «cabe en un .cube» y
pequenas las tres cifras de ΔE, con el maximo («ΔE peor») la ultima y en color
secundario. Pero el criterio T1 lo suspende **el maximo**, no la media, y
medido desde fuera el maximo se queda a 0.11 del limite. Y la cobertura del
cubo —cuanto del LUT esta medido y cuanto inventado— era una cifra de 13 px en
la esquina del mapa.

Lo que se fija aqui:

* el titular de error es `ReverseResult.delta_e_max`, y su margen sale del
  limite **importado** de `core.umbrales`, no de un 3.0 escrito en `gui/`;
* la cobertura pintada es `ReverseResult.coverage.coverage_fraction()`, y se
  pinta **al mismo tamano** que la reproducibilidad, medido sobre los pixeles
  pintados y no sobre lo que se pidio (en esta app la hoja de estilo ya piso
  `setFont()` una vez);
* un maximo por encima del limite no sale en rojo y se lee «no cumple»;
* donde solo hay una media (las cifras por clip), el rotulo dice «medio».
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
import functools  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtGui import QColor, QFontInfo, QImage  # noqa: E402
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget  # noqa: E402

from core import umbrales  # noqa: E402
from gui import identidad as idn  # noqa: E402
from gui import pantalla_reverse as pr  # noqa: E402
from gui import reverse_puente as rp  # noqa: E402
from gui.pantalla_clips import CABECERAS, COL_ANTES, COL_DESPUES  # noqa: E402
from gui.widgets import EtiquetaElidida, MarcaLimite, TextoAjustado  # noqa: E402
from tests.test_gui_apoyo import (  # noqa: E402
    ANCHURA_MINIMA,
    app_qt,
    asentar,
    demo,
    par_inverso,
    redimensionar,
    ventana,
)

pytestmark = pytest.mark.gui

LIMITE = umbrales.LIMITE_T1_DELTA_E_MAXIMO
RAIZ_GUI = Path(__file__).resolve().parent.parent / "gui"


# ---------------------------------------------------------------------------
# Apoyo
# ---------------------------------------------------------------------------


@functools.cache
def _resultado_base():
    """Un `ReverseResult` de verdad sobre el par de la demo. Se cachea: tarda."""
    original, coloreado = par_inverso()
    return rp.invertir(original, coloreado, tam_lut=17).resultado


def _pantalla_con(monkeypatch, resultado) -> pr.PantallaReverse:
    """Un `PantallaReverse` que pinta EXACTAMENTE `resultado`.

    Se sustituye `invertir` en el espacio de nombres de la pantalla, con
    `del_nucleo=True`: lo que se prueba aqui es como se pinta un resultado, no
    quien lo calcula (eso es `tests/test_gui_reverse.py`).
    """
    monkeypatch.setattr(
        pr, "invertir",
        lambda *a, **k: rp.Inversion(resultado=resultado, origen=rp.ORIGEN_CORE, del_nucleo=True),
    )
    app_qt()
    original, coloreado = par_inverso()
    p = pr.PantallaReverse(original, coloreado)
    p.resize(1100, 780)
    p.show()
    asentar()
    return p


def _imagen(w: QWidget) -> QImage:
    return w.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _es_tinta(c: QColor) -> bool:
    return c.alpha() > 128 and c.lightness() > 110


def _alto_de_tinta(w: QWidget) -> int:
    """Alto, en px, de lo que de verdad se ha pintado de texto en el widget."""
    img = _imagen(w)
    filas = [
        y for y in range(img.height())
        if any(_es_tinta(img.pixelColor(x, y)) for x in range(img.width()))
    ]
    assert filas, f"{type(w).__name__} no ha pintado nada: el medidor no ve texto"
    return filas[-1] - filas[0] + 1


# ---------------------------------------------------------------------------
# 1. El titular de error es el maximo, con el margen al limite importado
# ---------------------------------------------------------------------------


def test_el_titular_de_error_es_el_delta_e_max_del_resultado():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        p = v.p_reverse
        res = p.resultado()
        assert res is not None
        assert p._de_max.text() == f"{res.delta_e_max:.2f}"
        assert p.limite_max.text() == f"/ {LIMITE:.1f}"
        assert p.marca_max.margen() == pytest.approx(LIMITE - res.delta_e_max)
        assert f"{LIMITE - res.delta_e_max:.2f}" in p.marca_max.texto()

        # Y es EL titular: mas grande que la media y el p95, que van detras.
        px_max = QFontInfo(p._de_max.font()).pixelSize()
        assert px_max == pr.PX_TITULAR
        for detras in (p._de_media, p._de_p95):
            assert QFontInfo(detras.font()).pixelSize() < px_max
        assert _alto_de_tinta(p._de_max) > _alto_de_tinta(p._de_media), (
            "el maximo no se pinta mas grande que la media: la cifra holgada sigue delante"
        )
    finally:
        v.close()


def test_el_margen_sale_del_limite_importado_y_no_de_un_numero_escrito(monkeypatch):
    """Si el limite de `core.umbrales` cambiara, la pantalla tiene que seguirlo.

    Se cambia el limite en el espacio de nombres de la pantalla por uno que no
    se parece a nada (50.0) y se comprueba que el rotulo y el margen lo usan. Un
    3.0 escrito a mano en `gui/` no se moveria.
    """
    assert pr.LIMITE_T1_DELTA_E_MAXIMO is umbrales.LIMITE_T1_DELTA_E_MAXIMO
    monkeypatch.setattr(pr, "LIMITE_T1_DELTA_E_MAXIMO", 50.0)
    res = _resultado_base()
    p = _pantalla_con(monkeypatch, res)
    try:
        assert p.limite_max.text() == "/ 50.0"
        assert p.marca_max.margen() == pytest.approx(50.0 - res.delta_e_max)
        assert p.marca_max.cumple() is (res.delta_e_max < 50.0)
    finally:
        p.close()


def _limites_escritos_a_mano(arbol: ast.AST, nombre: str) -> list[str]:
    """Restas y comparaciones contra un `float` igual a un limite del encargo.

    Solo `float`: `arr.ndim != 3` o `len(problemas) > 3` son enteros (canales
    RGB, cuantos avisos se listan) y `3 == 3.0` en Python.
    """
    limites = {umbrales.LIMITE_T1_DELTA_E_MAXIMO, umbrales.LIMITE_T3_DELTA_E_PEOR_PAR}
    malos: list[str] = []
    for nodo in ast.walk(arbol):
        lados = []
        if isinstance(nodo, ast.Compare):
            lados = [nodo.left, *nodo.comparators]
        elif isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Sub):
            lados = [nodo.left, nodo.right]
        for lado in lados:
            if (
                isinstance(lado, ast.Constant)
                and isinstance(lado.value, float)
                and lado.value in limites
            ):
                malos.append(f"{nombre}:{nodo.lineno}: {ast.unparse(nodo)}")
    return malos


def test_en_gui_no_hay_un_limite_de_criterio_escrito_a_mano():
    """Ningun `3.0` ni `2.0` restado o comparado en `gui/`: se importan.

    Solo se miran restas y comparaciones, que es donde un limite se convierte en
    margen o en «cumple». Un `3.0` de dibujo (el ancho de una barra de la
    insignia) no es un limite de nada.
    """
    malos: list[str] = []
    assert sorted(RAIZ_GUI.glob("*.py")), (
        f"no hay nada que comprobar: {RAIZ_GUI} no tiene ningun .py (carpeta movida o renombrada)"
    )
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        malos += _limites_escritos_a_mano(arbol, archivo.name)
    assert not malos, "limite del encargo escrito a mano en gui/:\n" + "\n".join(malos)


def test_el_detector_de_limites_escritos_a_mano_caza_uno():
    """Control negativo: un detector que no mira nada pasaria siempre."""
    plantado = ast.parse(
        "margen = 3.0 - res.delta_e_max\n"
        "cumple = res.delta_e_max < 3.0\n"
        "peor = par < 2.0\n"
        "canales = arr.shape[2] != 3\n"
    )
    cazados = _limites_escritos_a_mano(plantado, "plantado.py")
    assert len(cazados) == 3, cazados


# ---------------------------------------------------------------------------
# 2. La cobertura: la del CoverageMap, y del mismo tamano que la reproducible
# ---------------------------------------------------------------------------


def test_la_cobertura_pintada_es_la_del_coveragemap_del_resultado():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        p = v.p_reverse
        res = p.resultado()
        assert res is not None
        fraccion = res.coverage.coverage_fraction()
        assert p.cifra_cobertura.text() == f"{fraccion * 100:.2f}%"
        assert p.cifra_inventado.text() == f"{(1.0 - fraccion) * 100:.2f}%"
        assert p.barra_cobertura.valor() == pytest.approx(fraccion)
        celdas = int(res.coverage.covered_mask().sum())
        assert f"{celdas:,}".replace(",", ".") in p.celdas_cobertura.text()
    finally:
        v.close()


def test_la_cobertura_se_pinta_igual_de_grande_que_la_reproducibilidad():
    """Medido en lo pintado, no en lo pedido.

    Tres medidas, de menos a mas desconfiada: el tamano que resuelve Qt
    (`QFontInfo`, que ya refleja lo que la hoja de estilo haya pisado), la
    familia, y el alto de la tinta de verdad en un `grab()`. Las dos cifras
    llevan digitos y `%`, asi que su tinta tiene que medir lo mismo.
    """
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        p = v.p_reverse
        info_cob, info_repro = QFontInfo(p.cifra_cobertura.font()), QFontInfo(p.cifra_repro.font())
        assert info_cob.pixelSize() == info_repro.pixelSize() == pr.PX_TITULAR
        assert info_cob.family() == info_repro.family()
        assert info_cob.weight() == info_repro.weight()

        tinta_cob, tinta_repro = _alto_de_tinta(p.cifra_cobertura), _alto_de_tinta(p.cifra_repro)
        assert abs(tinta_cob - tinta_repro) <= 1, (
            f"la cobertura se pinta con {tinta_cob} px de alto y la reproducibilidad con "
            f"{tinta_repro}: no son igual de grandes"
        )
        # Control: el medidor distingue tamanos. La cifra de «inventado» va a 12 px.
        assert _alto_de_tinta(p.cifra_inventado) < tinta_cob - 4
    finally:
        v.close()


def test_la_pantalla_dice_que_fuera_de_este_plano_no_esta_garantizado():
    v = ventana(demo())
    try:
        v.ir_a(3)
        asentar(2)
        p = v.p_reverse
        assert p.texto_alcance.isVisible()
        texto = p.texto_alcance.text()
        assert texto == pr.TEXTO_ALCANCE
        assert "no está garantizado" in texto
        assert not any(ch.isdigit() for ch in texto), (
            "la linea de alcance lleva numeros que no salen del resultado que se ensena"
        )
        # El limite, dicho como lo que es: un objetivo del encargo.
        diag = p.texto_diag.toPlainText()
        assert "objetivo" in diag and "no una medida" in diag
    finally:
        v.close()


# ---------------------------------------------------------------------------
# 3. Por encima del limite: no es rojo, y se lee que no cumple
# ---------------------------------------------------------------------------


def _hue_rojo_de_alarma(c: QColor) -> bool:
    """Rojo de alarma: tono por debajo del de la marca (12-16 grados) o magenta."""
    h = c.hsvHue()
    return c.alpha() > 128 and c.hsvSaturation() > 120 and c.value() > 120 and (
        0 <= h <= 8 or h >= 340
    )


def _hues_de_marca() -> set[int]:
    return {idn.color(x).hsvHue() for x in (idn.BRAND_400, idn.BRAND_500, idn.BRAND_600)}


def test_un_maximo_por_encima_del_limite_no_sale_en_rojo_y_se_lee_que_no_cumple(monkeypatch):
    res = replace(_resultado_base(), delta_e_max=LIMITE + 1.5)
    p = _pantalla_con(monkeypatch, res)
    try:
        marca = p.marca_max
        assert marca.isVisible()
        assert marca.cumple() is False
        assert marca.texto() == f"no cumple · margen {-1.5:.2f}"
        assert p._de_max.text() == f"{LIMITE + 1.5:.2f}"

        img = _imagen(marca)
        rojos = [
            (x, y) for y in range(img.height()) for x in range(img.width())
            if _hue_rojo_de_alarma(img.pixelColor(x, y))
        ]
        assert not rojos, f"la marca de «no cumple» pinta {len(rojos)} px de rojo de alarma"
        # Control del detector: la marca SI pinta color (naranja de marca), y ese
        # color no lo cuenta como rojo.
        saturados = [
            img.pixelColor(x, y) for y in range(img.height()) for x in range(img.width())
            if img.pixelColor(x, y).hsvSaturation() > 120 and img.pixelColor(x, y).value() > 120
        ]
        assert saturados, "la marca no pinta nada de color: el detector de rojo no ha mirado nada"
        assert min(_hues_de_marca()) <= 16 and all(
            not _hue_rojo_de_alarma(idn.color(x)) for x in (idn.BRAND_400, idn.BRAND_500)
        )

        # Y la cifra grande tampoco cambia de color por no cumplir.
        assert p._de_max.palette().color(p._de_max.foregroundRole()).name() == (
            p.cifra_repro.palette().color(p.cifra_repro.foregroundRole()).name()
        )
    finally:
        p.close()


def _relleno_interior(marca: MarcaLimite) -> QColor:
    """El color de un punto de la marca sin texto: el margen derecho, a media altura."""
    img = _imagen(marca)
    return img.pixelColor(img.width() - 5, img.height() // 2)


def test_cumple_y_no_cumple_se_distinguen_por_forma(monkeypatch):
    """Relleno solido cuando cumple; sin relleno cuando no. Como la confianza."""
    cumple = _pantalla_con(monkeypatch, replace(_resultado_base(), delta_e_max=LIMITE - 0.11))
    try:
        assert cumple.marca_max.cumple() is True
        assert cumple.marca_max.texto() == "cumple · margen 0.11"
        fondo_cumple = _relleno_interior(cumple.marca_max)
    finally:
        cumple.close()
    no_cumple = _pantalla_con(monkeypatch, replace(_resultado_base(), delta_e_max=LIMITE + 0.11))
    try:
        fondo_no = _relleno_interior(no_cumple.marca_max)
    finally:
        no_cumple.close()

    brand_600 = idn.color(idn.BRAND_600)
    assert abs(fondo_cumple.red() - brand_600.red()) <= 3
    assert abs(fondo_cumple.green() - brand_600.green()) <= 3
    assert fondo_no.alpha() < 40 or fondo_no.lightness() < 40, (
        f"la marca de «no cumple» esta rellena ({fondo_no.name()}): la forma no la distingue"
    )


def test_justo_en_el_limite_no_cumple(monkeypatch):
    """El encargo dice «< 3.0». Un maximo de 3.0 exacto no cumple."""
    p = _pantalla_con(monkeypatch, replace(_resultado_base(), delta_e_max=LIMITE))
    try:
        assert p.marca_max.cumple() is False
        assert p.marca_max.texto().startswith("no cumple")
    finally:
        p.close()


def test_un_maximo_no_finito_no_se_lee_como_un_margen(monkeypatch):
    p = _pantalla_con(monkeypatch, replace(_resultado_base(), delta_e_max=float("nan")))
    try:
        assert p.marca_max.cumple() is False
        assert p.marca_max.texto() == "sin medir"
    finally:
        p.close()


# ---------------------------------------------------------------------------
# 4. Donde solo hay media, el rotulo dice «medio»
# ---------------------------------------------------------------------------


def test_ningun_rotulo_de_delta_e_calla_que_estadistico_es():
    """«ΔE» a secas deja leer un maximo donde hay una media.

    Las cifras por clip (`MatchResult.delta_e_before/after`) son medias y el
    contrato no trae el maximo por clip. Todo texto fijo de la app que nombre un
    ΔE tiene que decir cual: medio, maximo o p95.
    """
    for columna in (COL_ANTES, COL_DESPUES):
        assert "MEDIO" in CABECERAS[columna].split("\n"), CABECERAS[columna]

    calificados = ("medio", "máximo", "p95")
    v = ventana(demo())
    try:
        malos: list[str] = []
        for indice in range(4):
            v.ir_a(indice)
            asentar(2)
            for lab in v.findChildren(QLabel):
                texto = lab.texto_completo() if isinstance(lab, EtiquetaElidida) else lab.text()
                if "ΔE" in texto and not any(c in texto.lower() for c in calificados):
                    malos.append(f"pantalla {indice}: {texto!r}")
        # La ficha del clip pone un rotulo comun «ΔE medio» encima de «antes» y
        # «después»; esos dos no nombran ΔE y no entran aqui. Se comprueba que el
        # comun existe.
        rotulos = [
            lab.texto_completo() for lab in v.p_clips.findChildren(EtiquetaElidida)
        ]
        assert "ΔE medio" in rotulos
        assert not malos, "rotulos de ΔE sin decir si es medio, maximo o p95:\n" + "\n".join(malos)
    finally:
        v.close()


# ---------------------------------------------------------------------------
# 5. A la anchura minima el diagnostico no se aplasta
# ---------------------------------------------------------------------------


def test_texto_ajustado_declara_el_alto_de_las_lineas_que_ocupa():
    """Control: un `QLabel` con wordWrap declara UNA linea; `TextoAjustado`, las que son."""
    app_qt()
    texto = "palabra " * 30
    caja = QWidget()
    lay = QVBoxLayout(caja)
    normal = QLabel(texto)
    normal.setWordWrap(True)
    ajustado = TextoAjustado(texto)
    lay.addWidget(normal)
    lay.addWidget(ajustado)
    caja.resize(160, 600)
    caja.show()
    asentar()
    try:
        una_linea = ajustado.fontMetrics().lineSpacing()
        assert ajustado.heightForWidth(ajustado.width()) > 2 * una_linea
        assert ajustado.minimumSizeHint().height() == ajustado.heightForWidth(ajustado.width())
        # Lo que hacia el QLabel normal, y por lo que existe TextoAjustado:
        assert normal.minimumSizeHint().height() < normal.heightForWidth(normal.width())
    finally:
        caja.close()


def test_a_la_anchura_minima_ninguna_cifra_del_diagnostico_se_aplasta():
    """El bug que se vio en la primera captura del dia: «18.29» a 19 px de 31."""
    v = ventana(demo())
    try:
        v.ir_a(3)
        redimensionar(v, ANCHURA_MINIMA, 400)
        asentar(2)
        assert v.width() == ANCHURA_MINIMA
        p = v.p_reverse
        aplastadas = [
            f"{n}: {getattr(p, n).height()} px de {getattr(p, n).minimumSizeHint().height()}"
            for n in ("_de_max", "cifra_repro", "cifra_cobertura", "cifra_inventado",
                      "_de_media", "_de_p95", "texto_alcance", "leyenda")
            if getattr(p, n).height() < getattr(p, n).minimumSizeHint().height()
        ]
        assert not aplastadas, "a la anchura minima se aplasta:\n" + "\n".join(aplastadas)
        marca = p.marca_max
        assert marca.width() >= marca.sizeHint().width()
    finally:
        v.close()
