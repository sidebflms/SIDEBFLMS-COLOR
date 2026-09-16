"""La GUI no da veredictos: el de «es un LUT puro» es de `core.reverse`.

POR QUE ESTE FICHERO EXISTE
---------------------------
`gui/reverse_puente.py` tenia su propia definicion de «es un LUT puro»:

    puro = reproducible > 0.92 and not puntos      # la GUI
    reproducible >= 0.95  Y  p95 <= 1.0 dE2000     # el nucleo

Mas floja que la del nucleo, y sin mirar el percentil 95 —que es justo la
mitad de la condicion, y la que impide que una media buena esconda un p95
malo—. Y **no era codigo muerto**: `invertir()` se cae al sustituto ante
cualquier excepcion de `core.reverse`, asi que un fallo del nucleo degradaba en
silencio al criterio permisivo y la pantalla llegaba a escribir «Es un LUT
puro: todo el grado cabe en el .cube».

Esa frase, dicha en falso, manda a Mario a llevarse un `.cube` que no
reproduce el grado y a enterarse delante de un cliente. La contraria solo le
hace trabajar de mas. Estos tests fijan que el error, si lo hay, cae siempre
por ese lado.

Tambien se comprueba aqui que no hay mas umbrales redefinidos en `gui/`, que es
lo que prohibe `CONTRATOS.md`.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from gui import reverse_puente as rp  # noqa: E402
from gui.pantalla_reverse import PantallaReverse  # noqa: E402
from tests.test_gui_apoyo import app_qt, asentar, par_inverso  # noqa: E402

pytestmark = pytest.mark.gui

RAIZ_GUI = Path(__file__).resolve().parent.parent / "gui"


class _Reventon(RuntimeError):
    """Lo que lanza un `core.reverse` averiado en estos tests."""


def _par():
    """El par original/coloreado del panel: grado conocido mas vineta."""
    return par_inverso()


def _par_sin_vineta():
    """El mismo grado SIN vineta: un CDL puro, o sea un LUT de verdad.

    Es el par mas favorable que hay para que alguien se anime a decir «esto es
    un LUT puro»: no hay nada que dependa de donde esta el pixel. Si la GUI
    fuera a dar un veredicto de mas, seria aqui.
    """
    return par_inverso(con_vineta=False)


# ---------------------------------------------------------------------------
# El puente
# ---------------------------------------------------------------------------


def test_con_el_nucleo_sano_el_veredicto_es_del_nucleo():
    original, coloreado = _par()
    inv = rp.invertir(original, coloreado, tam_lut=17)
    if not rp.DISPONIBLE:
        pytest.skip(f"core.reverse no esta importable: {rp.MOTIVO}")
    assert inv.del_nucleo is True
    assert inv.origen == rp.ORIGEN_CORE
    assert inv.veredicto_fiable is True
    assert inv.fallo == ""


def test_si_el_nucleo_revienta_la_inversion_lo_dice(monkeypatch):
    """Caerse al sustituto esta bien. Caerse en silencio, no."""
    def explota(*a, **k):
        raise _Reventon("se ha caido el nucleo a media inversion")

    monkeypatch.setattr(rp, "_invertir_grado_core", explota)
    monkeypatch.setattr(rp, "DISPONIBLE", True)
    original, coloreado = _par()
    inv = rp.invertir(original, coloreado, tam_lut=17)

    assert inv.del_nucleo is False
    assert inv.veredicto_fiable is False
    assert "_Reventon" in inv.fallo or "se ha caido" in inv.fallo
    assert rp.ORIGEN_SUSTITUTO in inv.origen


@pytest.mark.parametrize("con_vineta", [True, False])
@pytest.mark.parametrize("tam", [17, 33])
def test_el_sustituto_nunca_dice_que_algo_es_un_lut_puro(monkeypatch, con_vineta, tam):
    """Ni con el par mas favorable, ni con la rejilla mas fina.

    UNA PRECISION HONESTA sobre el alcance de este test: en el par de
    demostracion el criterio viejo (`reproducible > 0.92 and not puntos`)
    **no llegaba a dispararse**, porque con un solo fotograma el sustituto se
    lleva como mucho el 0.80 del grado. O sea que el fallo era una trampa
    latente, no algo que ya estuviera saliendo en pantalla. Lo grave sigue
    siendo lo mismo: era un veredicto propio de la GUI, mas flojo que el del
    nucleo y sin la condicion del percentil 95, en un camino al que se cae ante
    CUALQUIER excepcion de `core.reverse`. Aqui se fija que ese veredicto ya no
    existe, con cualquier entrada.
    """
    def explota(*a, **k):
        raise _Reventon("nucleo averiado")

    monkeypatch.setattr(rp, "_invertir_grado_core", explota)
    monkeypatch.setattr(rp, "DISPONIBLE", True)
    original, coloreado = par_inverso(con_vineta=con_vineta)
    inv = rp.invertir(original, coloreado, tam_lut=tam)

    assert inv.del_nucleo is False
    assert inv.resultado.diagnosis.is_pure_lut is False, (
        "el sustituto de la GUI ha emitido un veredicto de «es un LUT puro», y no le toca"
    )


def test_el_sustituto_tampoco_pasaria_el_criterio_del_nucleo(monkeypatch):
    """El «False» conservador no esconde un «si» que fuera verdad.

    Se comprueba contra los umbrales DEL NUCLEO, importados de alli y no
    copiados: con lo que mide el sustituto, el nucleo tampoco diria que es un
    LUT puro. Si algun dia esto fallara, significaria que el sustituto se ha
    vuelto lo bastante bueno como para que el «no lo se» estuviera costando
    trabajo de verdad, y habria que hablarlo.
    """
    reverse = pytest.importorskip("core.reverse")
    monkeypatch.setattr(rp, "DISPONIBLE", False)
    monkeypatch.setattr(rp, "_invertir_grado_core", None)
    original, coloreado = _par_sin_vineta()
    inv = rp.invertir(original, coloreado, tam_lut=33)
    diag = inv.resultado.diagnosis
    paso_del_nucleo = (
        diag.lut_reproducible >= reverse.UMBRAL_REPRODUCIBLE_PURO
        and inv.resultado.delta_e_p95 <= reverse.UMBRAL_DE_PURO
    )
    assert not paso_del_nucleo, (
        f"el sustituto mide reproducible={diag.lut_reproducible:.3f} y "
        f"p95={inv.resultado.delta_e_p95:.3f}, que SI pasarian el criterio del nucleo: "
        f"el «no lo se» de la pantalla estaria escondiendo un si"
    )


def test_el_sustituto_deja_dicho_que_no_ha_emitido_veredicto(monkeypatch):
    monkeypatch.setattr(rp, "DISPONIBLE", False)
    monkeypatch.setattr(rp, "_invertir_grado_core", None)
    original, coloreado = _par_sin_vineta()
    inv = rp.invertir(original, coloreado, tam_lut=17)
    notas = " ".join(inv.resultado.diagnosis.notes)
    assert "NO decide" in notas
    assert "core.reverse" in notas


def test_el_sustituto_no_clasifica_las_zonas_calientes(monkeypatch):
    """Decir «vineta» porque el bloque toca un borde es inventarse un dato."""
    monkeypatch.setattr(rp, "DISPONIBLE", False)
    monkeypatch.setattr(rp, "_invertir_grado_core", None)
    original, coloreado = _par()
    inv = rp.invertir(original, coloreado, tam_lut=17)
    assert inv.resultado.diagnosis.hotspots, (
        "no hay nada que comprobar: el sustituto no ha devuelto ni una zona caliente, y el "
        "bucle de abajo no miraria ninguna etiqueta"
    )
    for h in inv.resultado.diagnosis.hotspots:
        assert h.label == rp.ETIQUETA_SIN_CLASIFICAR, (
            f"el sustituto ha clasificado una zona como {h.label!r} sin haberlo medido"
        )


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------


def test_la_pantalla_no_dice_que_es_un_lut_puro_si_el_nucleo_ha_fallado(monkeypatch):
    """El test que pedia el auditor, y el que cierra el agujero.

    Con `core.reverse` lanzando, la pantalla tiene que decir que no lo sabe,
    ensenar el aviso de sustituto, y **no** escribir la frase peligrosa.
    """
    def explota(*a, **k):
        raise _Reventon("nucleo averiado")

    monkeypatch.setattr(rp, "_invertir_grado_core", explota)
    monkeypatch.setattr(rp, "DISPONIBLE", True)
    app_qt()
    original, coloreado = _par_sin_vineta()
    p = PantallaReverse(original, coloreado)
    p.resize(1100, 700)
    p.show()
    asentar()
    try:
        texto = p.texto_diag.toPlainText()
        assert p.veredicto_fiable() is False
        assert "Es un LUT puro" not in texto, f"la pantalla ha dicho lo que no sabe:\n{texto}"
        assert rp.SIN_VEREDICTO.split(":")[0] in texto
        assert p.aviso_sustituto.isVisible(), (
            "la caida a sustituto no se ve por ninguna parte: eso es caerse en silencio"
        )
        assert "core.reverse" in p.texto_sustituto.text()
    finally:
        p.close()


def test_con_el_nucleo_sano_la_pantalla_pinta_el_veredicto_del_nucleo():
    if not rp.DISPONIBLE:
        pytest.skip(f"core.reverse no esta importable: {rp.MOTIVO}")
    app_qt()
    original, coloreado = _par()
    p = PantallaReverse(original, coloreado)
    p.resize(1100, 700)
    p.show()
    asentar()
    try:
        assert p.veredicto_fiable() is True
        assert not p.aviso_sustituto.isVisible()
        res = p.resultado()
        assert res is not None
        texto = p.texto_diag.toPlainText()
        if res.diagnosis.is_pure_lut:
            assert texto.startswith("Es un LUT puro")
        else:
            assert texto.startswith("NO es un LUT puro")
        assert rp.SIN_VEREDICTO not in texto
    finally:
        p.close()


def test_sin_par_que_invertir_la_pantalla_no_afirma_nada():
    app_qt()
    p = PantallaReverse(None, None)
    p.resize(1100, 700)
    p.show()
    asentar()
    try:
        assert p.veredicto_fiable() is False
        assert p.aviso_no_disponible.isVisible()
        assert "Es un LUT puro" not in p.texto_diag.toPlainText()
    finally:
        p.close()


# ---------------------------------------------------------------------------
# Que no haya mas umbrales redefinidos en gui/
# ---------------------------------------------------------------------------

#: Nombres que en este proyecto son «una medida que se convierte en veredicto».
#: Compararlos con un numero escrito a mano dentro de `gui/` es redefinir un
#: umbral, que es lo que prohibe CONTRATOS.md.
_MEDIDAS = re.compile(
    r"^(score|reproducible|lut_reproducible|delta_e\w*|de_\w*|residuo\w*|p95|confidence"
    r"|coverage_fraction)$"
)


def _nombre_de(nodo: ast.AST) -> str:
    """El identificador «final» de una expresion: `res.diagnosis.lut_reproducible`
    -> `lut_reproducible`; `cob.coverage_fraction()` -> `coverage_fraction`."""
    if isinstance(nodo, ast.Attribute):
        return nodo.attr
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Call):
        return _nombre_de(nodo.func)
    return ""


def _modulos_gui():
    for archivo in sorted(RAIZ_GUI.glob("*.py")):
        yield archivo, ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))


def test_la_gui_no_redefine_ningun_umbral_de_veredicto():
    """`CONTRATOS.md`: el sitio donde un numero se convierte en alta/media/baja,
    o en «es un LUT puro», tiene que ser uno solo.

    Se mira el arbol de sintaxis y no el texto: un comentario que EXPLIQUE el
    umbral que se quito no puede hacer fallar el test, y un umbral escondido
    dentro de una expresion si tiene que salir.

    Los umbrales de REDACCION o de DIBUJO (cuanta barra se pinta, si se escribe
    una frase de aviso) no son veredictos; van con nombre y con su comentario,
    y por eso lo que se busca es la comparacion contra un NUMERO suelto.
    """
    culpables: list[str] = []
    assert list(_modulos_gui()), f"no hay nada que comprobar: {RAIZ_GUI} sin ningun .py"
    for archivo, arbol in _modulos_gui():
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Compare):
                continue
            lados = [nodo.left, *nodo.comparators]
            nombres = [_nombre_de(x) for x in lados]
            numeros = [
                isinstance(x, ast.Constant) and isinstance(x.value, int | float)
                and not isinstance(x.value, bool)
                for x in lados
            ]
            if any(_MEDIDAS.match(n) for n in nombres if n) and any(numeros):
                culpables.append(f"{archivo.name}:{nodo.lineno}: {ast.unparse(nodo)}")
    assert not culpables, (
        "umbral de veredicto redefinido en la GUI (CONTRATOS.md lo prohibe):\n"
        + "\n".join(culpables)
    )


def test_la_gui_no_construye_un_veredicto_positivo_de_lut_puro():
    """Ningun sitio de `gui/` puede poner `is_pure_lut` a otra cosa que `False`.

    El unico `is_pure_lut=` que puede haber aqui es el valor conservador del
    sustituto. Si aparece uno calculado, alguien ha vuelto a escribir el
    criterio del nucleo en la GUI.
    """
    malos: list[str] = []
    assert list(_modulos_gui()), f"no hay nada que comprobar: {RAIZ_GUI} sin ningun .py"
    for archivo, arbol in _modulos_gui():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.keyword) and nodo.arg == "is_pure_lut":
                valor = nodo.value
                if not (isinstance(valor, ast.Constant) and valor.value is False):
                    malos.append(f"{archivo.name}:{valor.lineno}: {ast.unparse(valor)}")
    assert not malos, "la GUI esta decidiendo si algo es un LUT puro:\n" + "\n".join(malos)


def test_la_gui_no_reimplementa_confidence_level():
    """El nivel de confianza sale de `Confidence.level`, nunca de un umbral local.

    `CONFIDENCE_ALTA` y `CONFIDENCE_MEDIA` son del contrato y solo los mira
    `confidence_level()`. En `gui/` no tienen nada que hacer, ni por su nombre
    ni copiados como numero dentro de una COMPARACION.

    Lo de «dentro de una comparacion» no es una rebaja, es precision: `0.45` y
    `0.75` tambien son opacidades de la paleta (`rgba(BRAND_400, 0.45)`), y ahi
    no son un umbral de nada. Lo que delata una reimplementacion es comparar
    algo contra ese numero.
    """
    from core.contracts import CONFIDENCE_ALTA, CONFIDENCE_MEDIA

    malos: list[str] = []
    assert list(_modulos_gui()), f"no hay nada que comprobar: {RAIZ_GUI} sin ningun .py"
    for archivo, arbol in _modulos_gui():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Name) and nodo.id in ("CONFIDENCE_ALTA", "CONFIDENCE_MEDIA"):
                malos.append(f"{archivo.name}:{nodo.lineno}: usa {nodo.id}")
            if not isinstance(nodo, ast.Compare):
                continue
            for lado in (nodo.left, *nodo.comparators):
                if (
                    isinstance(lado, ast.Constant)
                    and isinstance(lado.value, float)
                    and lado.value in (CONFIDENCE_ALTA, CONFIDENCE_MEDIA)
                ):
                    malos.append(
                        f"{archivo.name}:{nodo.lineno}: compara contra {lado.value}, que es "
                        f"un umbral de confianza del contrato"
                    )
    assert not malos, "la GUI reimplementa el nivel de confianza:\n" + "\n".join(malos)
