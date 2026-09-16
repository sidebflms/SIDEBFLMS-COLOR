"""El detector espacial de `core.reverse`: que separa, y con cuanto margen.

QUE SE PRUEBA AQUI
------------------
Que `diagnosticar` distingue las cuatro cosas que un `.cube` NO se lleva, y
—esto es igual de importante— **que no las ve donde no las hay**. Un detector
que siempre dice «aqui hay algo espacial» es tan inutil como uno que nunca lo
dice, y ademas es peor, porque el que lo lea dejara de hacerle caso.

Los seis montajes son los del encargo del dia 2:

    T2a  vineta sola            -> etiqueta "vineta" y centro cerca del centro
    T2b  ventana sola           -> IoU > 0.5 con la caja real
    T2c  vineta + ventana       -> las dos, por separado
    T2d  solo CDL + LUT         -> ~100% LUT, CERO falsos positivos
    T2e  grano anadido          -> "textura", NO "ventana"
    T2f  compresion h264 fuerte -> sigue sin ver nada espacial

Los tres ultimos son tan importantes como los tres primeros: son los que
impiden arreglar la ceguera a la vineta pasandose de frenada.

EL SENTIDO DEL FALLO
--------------------
Decir «esto es un LUT» cuando no lo es manda a Mario a exportar un `.cube` que
no reproduce el grado y a enterarse delante de un cliente. Decir «aqui hay algo»
cuando no lo hay solo le hace mirar dos veces. **Donde hay que elegir, estos
tests aceptan el falso positivo y no el falso negativo**, y donde un caso deja
un falso positivo conocido se dice con su cifra en vez de aflojar el umbral.

DE DONDE SALE EL MATERIAL
-------------------------
Todo de `tests/media/generate.py`, con semilla fija. Ni un fichero real, ni un
disco montado. Lo unico que se escribe es el clip h264 del T2f, y va en el
`tmp_path` de pytest.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import from_working, to_working
from core.contracts import CDL, LUT3D, LUT_SIZE_DEFAULT
from core.reverse import (
    SUELO_GANANCIA_LOCAL,
    UMBRAL_MONOTONIA_RADIAL,
    UMBRAL_R2_RADIAL,
    UMBRAL_RECORRIDO_GANANCIA,
    UMBRAL_TEXTURA,
    analizar_espacial,
    invertir_grado,
)
from tests.conftest import requiere_ffmpeg
from tests.media import generate as gen

#: El mismo grado conocido que usa `tests/test_entregables.py`. Se repite aqui a
#: proposito en vez de importarlo: ese archivo es del orquestador y no quiero que
#: un cambio suyo mueva estas cifras sin que nadie se entere.
CDL_CONOCIDO = CDL(
    slope=(1.06, 1.00, 0.94),
    offset=(0.012, 0.000, -0.008),
    power=(0.96, 1.00, 1.04),
    saturation=1.12,
)

#: Y la misma caja de ventana, por lo mismo.
CAJA_VENTANA = (440, 30, 170, 120)

#: Sigma del grano gaussiano que se le suma al coloreado en el T2e. Medido: con
#: esto la desviacion tipica del residuo de alta frecuencia sale en 3.8 dE2000,
#: o sea mas del doble del umbral de textura.
SIGMA_GRANO = 0.012

#: Semilla del grano. Fija: dos ejecuciones tienen que dar el mismo veredicto.
SEMILLA_GRANO = 20260915


def _lut_de_look_conocido(size: int = LUT_SIZE_DEFAULT) -> LUT3D:
    """Un look suave y monotono: sube el contraste y vira las sombras a frio."""
    t = LUT3D.identity(size).table.astype(np.float64)
    r, g, b = t[..., 0], t[..., 1], t[..., 2]

    def curva(x: np.ndarray) -> np.ndarray:
        return np.clip(x + 0.12 * np.sin(np.pi * np.clip(x, 0, 1)) * (x - 0.5) * 2, 0, 1)

    nr = curva(r) * 1.02
    ng = curva(g)
    nb = curva(b) * 0.98 + 0.03 * (1.0 - np.clip(b, 0, 1))
    return LUT3D(
        table=np.clip(np.stack([nr, ng, nb], -1), 0, 1).astype(np.float32),
        title="look conocido",
    )


def _coloreado_limpio(original: np.ndarray) -> np.ndarray:
    """`LUT(CDL(original))`: un grado que SI cabe entero en un `.cube`."""
    return _lut_de_look_conocido().apply(CDL_CONOCIDO.apply(original)).astype(np.float32)


def _vineta_descentrada(img: np.ndarray, *, strength: float, cx: float, cy: float) -> np.ndarray:
    """Como `gen.apply_vignette` pero con el centro donde se le diga.

    `cx`, `cy` en coordenadas -1..1 con el centro del fotograma en (0, 0). El
    generador no tiene esta variante y no la anado ahi: `tests/media/` no es mio.
    """
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx - (w - 1) / 2) / ((w - 1) / 2) - cx
    v = (yy - (h - 1) / 2) / ((h - 1) / 2) - cy
    d = np.clip(np.sqrt(u**2 + v**2) / np.sqrt(2), 0.0, 1.0)
    return (np.asarray(img, dtype=np.float64) * (1.0 - strength * d**2.2)[..., None]).astype(
        np.float32
    )


@pytest.fixture(scope="module")
def montajes(estudio_trabajo) -> dict[str, np.ndarray]:
    """Los cinco coloreados que no necesitan ffmpeg, en espacio de trabajo."""
    base = _coloreado_limpio(estudio_trabajo)
    rng = np.random.default_rng(SEMILLA_GRANO)
    return {
        "T2d nada espacial": base,
        "T2e grano": (base + rng.normal(0.0, SIGMA_GRANO, base.shape)).astype(np.float32),
        "T2a vineta sola": gen.apply_vignette(base, strength=0.55).astype(np.float32),
        "T2a vineta floja": gen.apply_vignette(base, strength=0.35).astype(np.float32),
        "T2b ventana sola": gen.apply_window(
            base, box=CAJA_VENTANA, gain=1.6, feather=18
        ).astype(np.float32),
        "T2c vineta+ventana": gen.apply_window(
            gen.apply_vignette(base, strength=0.45), box=CAJA_VENTANA, gain=1.6, feather=18
        ).astype(np.float32),
    }


@pytest.fixture(scope="module")
def resueltos(estudio_trabajo, montajes) -> dict[str, object]:
    """`invertir_grado` de cada montaje. Es caro (60 iteraciones de Jacobi por
    caso), asi que se paga una vez para todo el modulo."""
    return {n: invertir_grado(estudio_trabajo, col) for n, col in montajes.items()}


def _locales(diag) -> list:
    return [hp for hp in diag.hotspots if hp.label == "zona local"]


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / float(union) if union > 0 else 0.0


# ---------------------------------------------------------------------------
# La tabla de separacion. Es la prueba de que el detector separa, y es de donde
# salen las cifras de NOTAS.md: si alguien las cambia, aqui se ven las nuevas.
# ---------------------------------------------------------------------------


def test_tabla_de_separacion(estudio_trabajo, montajes, resueltos, capsys):
    """Imprime y comprueba las tres pruebas sobre los seis montajes.

    Lo que se afirma no es una cifra concreta (esas cambian si alguien toca el
    ajuste del LUT), sino **el orden de magnitud entre familias**: que lo
    espacial y lo no espacial no se toquen.
    """
    print(
        f"\n{'montaje':22s} {'rec_gan':>8s} {'R2_rad':>7s} {'r_radio':>8s} "
        f"{'textura':>8s} {'pico_loc':>9s}  etiquetas"
    )
    medidas: dict[str, object] = {}
    for nombre, col in montajes.items():
        res = resueltos[nombre]
        pred = res.lut.apply(res.cdl.apply(estudio_trabajo.astype(np.float64)))
        from core.color import delta_e2000

        residuo = np.asarray(
            delta_e2000(pred, col.astype(np.float64)), dtype=np.float64
        )
        a = analizar_espacial(residuo, pred, col.astype(np.float64))
        medidas[nombre] = a
        print(
            f"{nombre:22s} {a.recorrido_ganancia:8.3f} {a.r2_radial:7.3f} "
            f"{a.pearson_radial:+8.3f} {a.textura:8.3f} {a.pico_local:9.4f}  "
            f"{[hp.label for hp in res.diagnosis.hotspots]}"
        )

    limpio = medidas["T2d nada espacial"]
    grano = medidas["T2e grano"]
    vineta = medidas["T2a vineta floja"]
    ventana = medidas["T2b ventana sola"]

    # 1. El recorrido de la ganancia radial separa lo espacial de lo que no lo es.
    assert vineta.recorrido_ganancia > 5.0 * ventana.recorrido_ganancia or (
        vineta.recorrido_ganancia >= UMBRAL_RECORRIDO_GANANCIA
        and ventana.recorrido_ganancia < UMBRAL_RECORRIDO_GANANCIA
    ), (
        f"la vineta mas floja ({vineta.recorrido_ganancia:.3f}) no se separa de una ventana "
        f"({ventana.recorrido_ganancia:.3f}) por el recorrido de ganancia"
    )
    assert limpio.recorrido_ganancia < UMBRAL_RECORRIDO_GANANCIA / 4.0
    assert grano.recorrido_ganancia < UMBRAL_RECORRIDO_GANANCIA / 4.0

    # 2. El signo distingue las dos familias sin ambiguedad.
    assert vineta.pearson_radial < -UMBRAL_MONOTONIA_RADIAL, (
        "una vineta que oscurece hacia fuera tiene que correlar NEGATIVO con el radio"
    )
    assert abs(ventana.pearson_radial) < UMBRAL_MONOTONIA_RADIAL

    # 3. La alta frecuencia separa el grano de todo lo demas.
    assert grano.textura > 2.0 * max(
        limpio.textura, vineta.textura, ventana.textura
    ), (
        f"el grano ({grano.textura:.2f} dE2000 de alta frecuencia) no destaca sobre lo espacial "
        f"({vineta.textura:.2f} / {ventana.textura:.2f})"
    )

    # 4. El pico del residuo de ganancia local separa la ventana del grano.
    assert ventana.pico_local > SUELO_GANANCIA_LOCAL > grano.pico_local, (
        f"ventana={ventana.pico_local:.4f} suelo={SUELO_GANANCIA_LOCAL} "
        f"grano={grano.pico_local:.4f}"
    )


# ---------------------------------------------------------------------------
# T2a - la vineta sola. Es el fallo que se vino a arreglar.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["T2a vineta sola", "T2a vineta floja"])
def test_T2a_una_vineta_sola_se_etiqueta_como_vineta(estudio_trabajo, montajes, resueltos, caso):
    """Con una vineta y nada mas, el diagnostico tiene que decir «vineta».

    Esto es exactamente lo que la version de la noche 1 NO hacia: el perfil
    radial del ΔE2000 se quedaba en R2=0.2887 contra una puerta de 0.30. Medido
    sobre el campo de GANANCIA, la misma vineta da R2 > 0.8.
    """
    d = resueltos[caso].diagnosis
    etiquetas = [hp.label for hp in d.hotspots]
    assert not d.is_pure_lut, "dice que una vineta es un LUT puro"
    assert "vineta" in etiquetas, f"no la etiqueta como vineta: {etiquetas}"

    # Y el texto tiene que decirlo en castellano, que es lo que lee Mario.
    texto = " ".join(d.notes).lower()
    assert "vineta" in texto


@pytest.mark.parametrize("caso", ["T2a vineta sola", "T2a vineta floja"])
def test_T2a_el_centro_estimado_cae_cerca_del_centro_del_cuadro(
    estudio_trabajo, montajes, resueltos, caso
):
    """El centro NO se supone: se estima. Con una vineta centrada tiene que
    salir el centro del fotograma, y ese es el cierre del circulo."""
    from core.color import delta_e2000

    res = resueltos[caso]
    col = montajes[caso].astype(np.float64)
    pred = res.lut.apply(res.cdl.apply(estudio_trabajo.astype(np.float64)))
    residuo = np.asarray(delta_e2000(pred, col), dtype=np.float64)
    a = analizar_espacial(residuo, pred, col)

    h, w = residuo.shape
    cx, cy = a.centro
    error = float(np.hypot(cx - (w - 1) / 2, cy - (h - 1) / 2))
    print(f"\n[{caso}] centro estimado=({cx:.1f}, {cy:.1f}) error={error:.1f} px")
    # Una decima del lado corto. No es una tolerancia de conveniencia: la caida
    # de una vineta es plana cerca del centro, asi que ahi el centro esta mal
    # condicionado y pedir mas seria pedir precision que el dato no tiene.
    assert error < 0.10 * min(h, w), f"el centro estimado se va {error:.1f} px"


def test_T2a_una_vineta_DESCENTRADA_tambien_se_ve(estudio_trabajo):
    """El limite que la noche 1 dejaba escrito («una vineta descentrada no se
    detecta, el centro se supone en el centro del fotograma») ya no existe,
    porque el centro se ajusta. Se comprueba con la caida puesta a mano en el
    tercio superior izquierdo."""
    base = _coloreado_limpio(estudio_trabajo)
    col = _vineta_descentrada(base, strength=0.55, cx=-0.4, cy=-0.35)
    res = invertir_grado(estudio_trabajo, col)
    d = res.diagnosis
    etiquetas = [hp.label for hp in d.hotspots]

    from core.color import delta_e2000

    pred = res.lut.apply(res.cdl.apply(estudio_trabajo.astype(np.float64)))
    residuo = np.asarray(delta_e2000(pred, col.astype(np.float64)), dtype=np.float64)
    a = analizar_espacial(residuo, pred, col.astype(np.float64))
    h, w = residuo.shape
    esperado = ((-0.4 + 1) * (w - 1) / 2, (-0.35 + 1) * (h - 1) / 2)
    print(
        f"\n[T2a-descentrada] centro real={esperado[0]:.0f},{esperado[1]:.0f} "
        f"estimado={a.centro[0]:.0f},{a.centro[1]:.0f} etiquetas={etiquetas}"
    )
    assert "vineta" in etiquetas, f"no ve una vineta descentrada: {etiquetas}"
    # El centro estimado tiene que caer del lado bueno del fotograma, no en el
    # medio. No se pide precision: se pide que NO sea el centro por defecto.
    assert a.centro[0] < (w - 1) / 2, "el centro estimado no se ha movido a la izquierda"
    assert a.centro[1] < (h - 1) / 2, "el centro estimado no se ha movido hacia arriba"


# ---------------------------------------------------------------------------
# T2b - la ventana sola, que es lo que ya funcionaba y no se puede romper.
# ---------------------------------------------------------------------------


def test_T2b_una_ventana_sola_se_localiza(resueltos):
    """Lo de ahora no se puede perder: IoU con la caja real por encima de 0.5."""
    d = resueltos["T2b ventana sola"].diagnosis
    locales = _locales(d)
    assert locales, f"no senala ninguna zona: {[hp.label for hp in d.hotspots]}"
    hp = max(locales, key=lambda z: z.magnitude)
    solape = _iou((hp.x, hp.y, hp.w, hp.h), CAJA_VENTANA)
    print(f"\n[T2b] caja={hp.x},{hp.y},{hp.w},{hp.h} real={CAJA_VENTANA} IoU={solape:.3f}")
    assert solape > 0.5, f"la caja que senala solapa solo el IoU {solape:.2f} con la real"
    assert "vineta" not in [z.label for z in d.hotspots], "confunde una ventana con una vineta"


def test_T2b_una_ventana_floja_tambien_se_ve(estudio_trabajo):
    """El umbral local es un contorno a media altura del pico, asi que no tiene
    escala: una ventana de +15% se recorta igual que una de +60%. Si alguien lo
    cambia por un numero absoluto en dE2000, este test se pone rojo."""
    base = _coloreado_limpio(estudio_trabajo)
    col = gen.apply_window(base, box=CAJA_VENTANA, gain=1.15, feather=18).astype(np.float32)
    d = invertir_grado(estudio_trabajo, col).diagnosis
    locales = _locales(d)
    assert locales, "una ventana de +15% se le escapa entera"
    hp = max(locales, key=lambda z: z.magnitude)
    solape = _iou((hp.x, hp.y, hp.w, hp.h), CAJA_VENTANA)
    print(f"\n[T2b-floja] IoU={solape:.3f} repro={d.lut_reproducible:.3f}")
    assert solape > 0.5


def test_T2b_una_ventana_que_solo_cambia_el_TINTE_tambien_se_ve(estudio_trabajo):
    """El campo de ganancia se mide **por canal** justamente para esto: una
    secundaria que sube el rojo y baja el azul sin tocar el brillo es invisible
    en un campo de luma."""
    base = _coloreado_limpio(estudio_trabajo)
    col = gen.apply_window(
        base, box=CAJA_VENTANA, gain=1.0, tint=(1.10, 1.0, 0.90), feather=18
    ).astype(np.float32)
    d = invertir_grado(estudio_trabajo, col).diagnosis
    locales = _locales(d)
    assert locales, "una ventana que solo cambia el tinte se le escapa entera"
    hp = max(locales, key=lambda z: z.magnitude)
    solape = _iou((hp.x, hp.y, hp.w, hp.h), CAJA_VENTANA)
    print(f"\n[T2b-tinte] IoU={solape:.3f}")
    assert solape > 0.4, f"IoU {solape:.2f}: la localiza, pero peor de lo esperado"


# ---------------------------------------------------------------------------
# T2c - las dos a la vez, cada una por su lado.
# ---------------------------------------------------------------------------


def test_T2c_vineta_y_ventana_salen_por_separado(resueltos):
    """El caso que da sentido a restar el modelo radial antes de buscar zonas.

    Sin restarlo, la ventana de la esquina se funde con la corona exterior de la
    vineta y sale un unico manchurron que no es ninguna de las dos cosas.
    """
    d = resueltos["T2c vineta+ventana"].diagnosis
    etiquetas = [hp.label for hp in d.hotspots]
    assert not d.is_pure_lut
    assert "vineta" in etiquetas, f"pierde la vineta: {etiquetas}"
    locales = _locales(d)
    assert locales, f"pierde la ventana: {etiquetas}"
    hp = max(locales, key=lambda z: z.magnitude)
    solape = _iou((hp.x, hp.y, hp.w, hp.h), CAJA_VENTANA)
    print(f"\n[T2c] etiquetas={etiquetas} IoU_ventana={solape:.3f}")
    assert solape > 0.5, f"la zona que senala no es la ventana (IoU {solape:.2f})"


def test_T2c_la_vineta_nunca_se_cae_por_el_tope_de_hotspots(resueltos):
    """`MAX_HOTSPOTS` recorta, y si recortara por magnitud a secas la vineta
    (magnitud = residuo medio del cuadro) se quedaria fuera por culpa de las
    esquinas, que son ESA MISMA vineta. El titular no se pierde por el detalle."""
    for caso in ("T2a vineta sola", "T2c vineta+ventana"):
        d = resueltos[caso].diagnosis
        assert "vineta" in [hp.label for hp in d.hotspots], caso


# ---------------------------------------------------------------------------
# T2d - el contrapeso: cero falsos positivos donde no hay nada espacial.
# ---------------------------------------------------------------------------


def test_T2d_sin_nada_espacial_dice_que_SI_es_un_lut(resueltos):
    """CERO hotspots. Ni vineta, ni degradado, ni textura, ni zona local."""
    d = resueltos["T2d nada espacial"].diagnosis
    print(
        f"\n[T2d] repro={d.lut_reproducible:.4f} puro={d.is_pure_lut} "
        f"etiquetas={[hp.label for hp in d.hotspots]}"
    )
    assert d.hotspots == (), f"se inventa {len(d.hotspots)} zona(s) donde solo hay un LUT"
    assert d.is_pure_lut, f"no reconoce un LUT puro: reproducible={d.lut_reproducible:.4f}"


def test_T2d_un_degradado_no_aparece_donde_no_lo_hay(estudio_trabajo, resueltos):
    """La puerta del degradado es la mas facil de disparar sin querer, porque
    casi cualquier residuo tiene algo de inclinacion. Se comprueba en los cinco
    montajes: la unica forma global que puede salir es la vineta."""
    for caso, res in resueltos.items():
        etiquetas = [hp.label for hp in res.diagnosis.hotspots]
        assert "degradado" not in etiquetas, f"{caso} ve un degradado que no existe: {etiquetas}"


# ---------------------------------------------------------------------------
# T2e - el grano es textura, no una ventana.
# ---------------------------------------------------------------------------


def test_T2e_el_grano_se_reporta_como_textura(resueltos):
    """Grano gaussiano con semilla fija encima del coloreado.

    Es la otra familia de cosas que no caben en un LUT, y confundirla con una
    ventana manda a Mario a buscar un power window que no existe.
    """
    d = resueltos["T2e grano"].diagnosis
    etiquetas = [hp.label for hp in d.hotspots]
    print(f"\n[T2e] repro={d.lut_reproducible:.4f} etiquetas={etiquetas}")
    assert "textura" in etiquetas, f"no lo llama textura: {etiquetas}"
    assert not _locales(d), f"confunde grano con zonas locales: {etiquetas}"
    assert "vineta" not in etiquetas
    texto = " ".join(d.notes).lower()
    assert "grano" in texto, "no menciona el grano en ninguna nota"


def test_T2e_el_umbral_de_textura_tiene_margen(estudio_trabajo, montajes, resueltos):
    """No basta con que pase: hace falta saber por cuanto. Si el margen se come,
    este test lo dice antes de que el detector empiece a fallar en silencio."""
    from core.color import delta_e2000

    valores = {}
    for caso in ("T2d nada espacial", "T2e grano", "T2b ventana sola", "T2a vineta sola"):
        res = resueltos[caso]
        col = montajes[caso].astype(np.float64)
        pred = res.lut.apply(res.cdl.apply(estudio_trabajo.astype(np.float64)))
        residuo = np.asarray(delta_e2000(pred, col), dtype=np.float64)
        valores[caso] = analizar_espacial(residuo, pred, col).textura
    print(f"\n[T2e-margen] umbral={UMBRAL_TEXTURA} {valores}")
    assert valores["T2e grano"] > UMBRAL_TEXTURA * 1.3
    assert max(v for k, v in valores.items() if k != "T2e grano") < UMBRAL_TEXTURA * 0.8


# ---------------------------------------------------------------------------
# T2f - compresion fuerte: ruido de verdad, nada espacial.
# ---------------------------------------------------------------------------


def _visible(escena_lineal: np.ndarray) -> np.ndarray:
    """Recorta a lo que cabe en un fichero de video de 8 bits.

    Sin esto, el T2f mediria dos cosas a la vez: la compresion **y** el recorte
    de los especulares del generador, que se salen de 1.0 a proposito. Se le
    aplica a los dos lados de la pareja, asi que lo que queda es la compresion.
    """
    return gen.srgb_eotf(np.clip(gen.srgb_oetf(escena_lineal), 0.0, 1.0)).astype(np.float32)


@requiere_ffmpeg
def test_T2f_la_compresion_h264_no_inventa_nada_espacial(escena_estudio, tmp_path):
    """Un h264 de verdad (ffmpeg, yuv420p 8 bits) encima de un grado que SI es
    un LUT. El ruido de compresion tiene que quedarse en «esto no sale exacto»,
    no en «hay una ventana ahi».

    Lo unico que este test escribe esta en `tmp_path`.
    """
    escena = _visible(escena_estudio.image)
    original = to_working(escena, "linear_rec709")
    coloreado = _coloreado_limpio(original)

    # Al fichero va el coloreado, en escena-lineal y ya recortado a lo visible.
    col_lineal = _visible(from_working(coloreado, "linear_rec709"))
    ruta = gen.make_clip(tmp_path / "coloreado.mp4", [col_lineal] * 3, codec="h264")

    from core.analysis import extraer_fotogramas

    fotogramas = extraer_fotogramas(ruta, n_fotogramas=3, space="rec709")
    col_comprimido = np.asarray(fotogramas[len(fotogramas) // 2], dtype=np.float32)

    res = invertir_grado(original, col_comprimido)
    d = res.diagnosis
    etiquetas = [hp.label for hp in d.hotspots]
    print(
        f"\n[T2f] repro={d.lut_reproducible:.4f} puro={d.is_pure_lut} "
        f"dE medio={res.delta_e_mean:.3f} p95={res.delta_e_p95:.3f} etiquetas={etiquetas}"
    )

    # LO QUE IMPORTA: no se inventa geometria. La compresion degrada la cifra
    # (y eso es correcto: parte del grado ya no se puede recuperar), pero no
    # puede convertirse en una ventana ni en una vineta.
    assert not _locales(d), f"ve zonas locales donde solo hay compresion: {etiquetas}"
    assert "vineta" not in etiquetas
    assert "degradado" not in etiquetas
    assert d.lut_reproducible > 0.90, (
        f"la compresion se lleva por delante la fraccion reproducible: "
        f"{d.lut_reproducible:.4f}"
    )


# ---------------------------------------------------------------------------
# Las tres puertas de la vineta, una a una. Si manana alguien afloja una,
# aqui se ve cual.
# ---------------------------------------------------------------------------


def test_las_tres_puertas_de_la_vineta_se_cierran_por_separado(
    estudio_trabajo, montajes, resueltos
):
    """Cada puerta tiene que rechazar por su cuenta el caso que le toca."""
    from core.color import delta_e2000

    def analisis(caso):
        res = resueltos[caso]
        col = montajes[caso].astype(np.float64)
        pred = res.lut.apply(res.cdl.apply(estudio_trabajo.astype(np.float64)))
        residuo = np.asarray(delta_e2000(pred, col), dtype=np.float64)
        return analizar_espacial(residuo, pred, col)

    limpio = analisis("T2d nada espacial")
    ventana = analisis("T2b ventana sola")
    vineta = analisis("T2a vineta sola")

    # El caso limpio suspende las tres.
    assert limpio.recorrido_ganancia < UMBRAL_RECORRIDO_GANANCIA
    assert limpio.r2_radial < UMBRAL_R2_RADIAL

    # La ventana suspende el R2 y la monotonia, que son las que dicen «radial».
    assert ventana.r2_radial < UMBRAL_R2_RADIAL, (
        f"una ventana explica un R2 radial de {ventana.r2_radial:.3f}: el detector la va a "
        f"llamar vineta"
    )
    assert abs(ventana.pearson_radial) < UMBRAL_MONOTONIA_RADIAL

    # Y la vineta aprueba las tres con margen.
    assert vineta.recorrido_ganancia > 2.0 * UMBRAL_RECORRIDO_GANANCIA
    assert vineta.r2_radial > 1.5 * UMBRAL_R2_RADIAL
    assert abs(vineta.pearson_radial) > 1.2 * UMBRAL_MONOTONIA_RADIAL


def test_una_vineta_que_ACLARA_hacia_fuera_tambien_se_detecta(estudio_trabajo):
    """Y el signo se reporta. Las dos son igual de imposibles de meter en un
    LUT, pero al colorista no le da igual cual de las dos es."""
    base = _coloreado_limpio(estudio_trabajo)
    h, w = base.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx - (w - 1) / 2) / ((w - 1) / 2)
    v = (yy - (h - 1) / 2) / ((h - 1) / 2)
    d = np.sqrt(u**2 + v**2) / np.sqrt(2)
    col = (base.astype(np.float64) * (1.0 + 0.55 * d**2.2)[..., None]).astype(np.float32)

    res = invertir_grado(estudio_trabajo, col)
    from core.color import delta_e2000

    pred = res.lut.apply(res.cdl.apply(estudio_trabajo.astype(np.float64)))
    residuo = np.asarray(delta_e2000(pred, col.astype(np.float64)), dtype=np.float64)
    a = analizar_espacial(residuo, pred, col.astype(np.float64))
    etiquetas = [hp.label for hp in res.diagnosis.hotspots]
    print(f"\n[vineta-que-aclara] pearson={a.pearson_radial:+.3f} etiquetas={etiquetas}")
    assert "vineta" in etiquetas
    assert a.pearson_radial > 0, "una vineta que aclara tiene que correlar POSITIVO con el radio"
    assert "aclara" in " ".join(res.diagnosis.notes)


# ===========================================================================
# DIA 4 - La zona PRINCIPAL. El mapa de calor acertaba y la primera linea no.
# ===========================================================================
#
# La medicion independiente del dia 3 encontro que, con una vineta y una
# ventana suaves aplicadas en luz lineal y una sombra profunda en una esquina,
# la primera "zona local" era un cuadrito de 31x29 px en esa esquina, con
# solape 0.0 con la ventana, y la ventana salia segunda. La causa medida (y
# escrita en `core/reverse/NOTAS.md` §6.7) fue el ORDEN: las zonas se
# ordenaban por pico y despues por el ΔE2000 medio de su RECTANGULO, y los dos
# estadisticos premian lo pequeno y concentrado. Hoy se ordenan por masa.
#
# El montaje de aqui es MIO y no importa nada de `tests/medicion/`: otra
# escena ("el taller"), otra esquina, otra caja. Lo que comparte con aquel es
# la receta del fallo: sombra profunda en una esquina, color variado que el
# LUT absorbe a trozos, y lo espacial aplicado EN LUZ LINEAL.

from core.color import log_decode, log_encode  # noqa: E402
from core.contracts import LUMA_REC709, WORKING_SPACE  # noqa: E402
from core.reverse.diagnostico import _zonas  # noqa: E402
from tests.conftest import a_trabajo  # noqa: E402

#: La ventana del taller, lejos de la sombra pero en su lado del cuadro.
CAJA_TALLER = (360, 180, 190, 110)

#: Una ventana DENTRO de una sombra profunda (la del taller con la sombra
#: grande). Medido: la luminancia lineal media de esa caja esta 1.33 paradas
#: por debajo de la mediana del cuadro.
CAJA_EN_SOMBRA = (520, 250, 110, 100)

#: Parches del taller, escena-lineal Rec.709. Saturados y variados a proposito:
#: son lo que hace que el LUT absorba la ventana a trozos, que es la mitad de la
#: receta del fallo.
_PARCHES_TALLER = np.array(
    [
        [0.40, 0.06, 0.05], [0.05, 0.30, 0.07], [0.04, 0.07, 0.38], [0.45, 0.38, 0.04],
        [0.30, 0.05, 0.32], [0.04, 0.33, 0.36], [0.55, 0.22, 0.05], [0.12, 0.10, 0.30],
        [0.25, 0.42, 0.08], [0.60, 0.60, 0.58], [0.02, 0.02, 0.02], [0.18, 0.18, 0.18],
        [0.35, 0.20, 0.14], [0.07, 0.15, 0.05], [0.50, 0.08, 0.20],
    ]
)


def _escena_taller(
    *, sombra: bool = True, radio_x: float = 0.18, radio_y: float = 0.28, semilla: int = 7
) -> np.ndarray:
    """El taller, ya en espacio de trabajo: fondo en degradado, 15 parches, una
    sombra profunda en la esquina INFERIOR DERECHA (suelo al 4%, unas 4.6
    paradas) y grano sembrado proporcional a la raiz de la senal."""
    h, w = 360, 640
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    u, v = xx / (w - 1), yy / (h - 1)
    arriba = np.array([0.16, 0.18, 0.26])
    abajo = np.array([0.30, 0.22, 0.14])
    img = (arriba * (1 - v)[..., None] + abajo * v[..., None]) * (0.35 + 0.65 * u**1.2)[..., None]
    for k, color in enumerate(_PARCHES_TALLER):
        x0, y0 = 30 + (k % 5) * 84, 24 + (k // 5) * 84
        img[y0 : y0 + 68, x0 : x0 + 68] = color
    if sombra:
        campo = np.exp(-(((yy - h) / (radio_y * h)) ** 2 + ((xx - w) / (radio_x * w)) ** 2))
        img = img * np.clip(1.0 - campo, 0.04, 1.0)[..., None]
    img = img + rng.normal(0.0, 0.005, img.shape) * np.sqrt(np.clip(img, 0.0, None) + 0.01)
    return a_trabajo(np.clip(img, 0.0, None))


def _en_luz_lineal(
    coloreado: np.ndarray, *, vineta: float, caja: tuple[int, int, int, int] | None,
    ganancia: float = 1.5,
) -> np.ndarray:
    """Vineta y ventana aplicadas EN LUZ LINEAL: se decodifica la curva del
    espacio de trabajo, se multiplica y se vuelve a codificar. Es un obturado
    optico y un foco, no una ganancia sobre valores logaritmicos."""
    lin = log_decode(np.asarray(coloreado, dtype=np.float64), WORKING_SPACE)
    if vineta:
        lin = gen.apply_vignette(lin, strength=vineta, power=1.8).astype(np.float64)
    if caja is not None:
        lin = gen.apply_window(
            lin, box=caja, gain=ganancia, tint=(1.0, 1.0, 1.0), feather=10
        ).astype(np.float64)
    return log_encode(lin, WORKING_SPACE).astype(np.float32)


@pytest.fixture(scope="module")
def taller() -> dict[str, tuple[np.ndarray, object]]:
    """(original, resultado) de cada montaje del taller. Se paga una vez."""
    normal = _escena_taller()
    grande = _escena_taller(radio_x=0.30, radio_y=0.45)
    montajes = {
        "vineta+ventana": (normal, _en_luz_lineal(
            _coloreado_limpio(normal), vineta=0.42, caja=CAJA_TALLER)),
        "ventana sola": (normal, _en_luz_lineal(
            _coloreado_limpio(normal), vineta=0.0, caja=CAJA_TALLER)),
        "nada espacial": (normal, _coloreado_limpio(normal)),
        "en sombra+vineta": (grande, _en_luz_lineal(
            _coloreado_limpio(grande), vineta=0.42, caja=CAJA_EN_SOMBRA)),
        "en sombra sola": (grande, _en_luz_lineal(
            _coloreado_limpio(grande), vineta=0.0, caja=CAJA_EN_SOMBRA)),
    }
    return {n: (o, invertir_grado(o, c)) for n, (o, c) in montajes.items()}


def _imprimir(caso: str, d, caja) -> None:
    print(f"\n[{caso}] etiquetas={[hp.label for hp in d.hotspots]}")
    for i, hp in enumerate(_locales(d)):
        b = (hp.x, hp.y, hp.w, hp.h)
        extra = f" IoU={_iou(b, caja):.3f}" if caja else ""
        print(f"[{caso}]   #{i} {b} mag={hp.magnitude:.3f}{extra}")


@pytest.mark.parametrize("caso", ["vineta+ventana", "ventana sola"])
def test_T2g_la_zona_principal_es_la_ventana_y_no_la_esquina_en_sombra(taller, caso):
    """La primera "zona local" es la que la GUI lista primero. Tiene que ser la
    ventana, con IoU > 0.5, aunque haya una esquina en sombra con mas ΔE2000
    medio en su rectangulo.

    Medido con el codigo del dia 3 sobre este mismo montaje: en los dos casos la
    primera era (559,204,81,83) / (563,218,77,33), en el borde de la sombra, con
    IoU 0.000, y la ventana salia segunda con IoU 0.898 / 0.922.
    """
    _, res = taller[caso]
    d = res.diagnosis
    _imprimir(f"T2g {caso}", d, CAJA_TALLER)
    locales = _locales(d)
    assert locales, f"no senala ninguna zona: {[hp.label for hp in d.hotspots]}"
    primera = locales[0]
    iou = _iou((primera.x, primera.y, primera.w, primera.h), CAJA_TALLER)
    assert iou > 0.5, (
        f"la zona principal es ({primera.x},{primera.y},{primera.w},{primera.h}) y solapa "
        f"IoU {iou:.3f} con la ventana {CAJA_TALLER}"
    )


def test_T2g_el_montaje_sigue_teniendo_la_trampa(taller):
    """EL CENTINELA DEL TEST DE ARRIBA. Si esto se pone rojo, el test de arriba
    pasa sin probar nada, y hay que saberlo.

    Se reordenan las zonas con el criterio viejo (ΔE2000 medio del
    RECTANGULO, que es la misma cuenta sobre el mapa normalizado) y se afirma
    que con ese criterio la primera NO seria la ventana. Se hace sobre "ventana
    sola", donde el margen medido es amplio: 5.772 contra 3.962 ΔE2000 con el
    codigo del dia 3. En "vineta+ventana" el margen era del 2% (4.996 contra
    4.902) y no sirve de centinela.

    Si un dia la esquina deja de salir como zona -- por ejemplo porque se
    arregle el ajuste del LUT en las sombras --, esto salta y el test de arriba
    necesita otro montaje; no es que el detector haya empeorado.
    """
    _, res = taller["ventana sola"]
    d = res.diagnosis
    mapa = np.asarray(d.spatial_residual, dtype=np.float64)
    por_rectangulo = sorted(
        _locales(d),
        key=lambda hp: -float(np.nanmean(mapa[hp.y : hp.y + hp.h, hp.x : hp.x + hp.w])),
    )
    assert por_rectangulo, "el taller ya no emite ninguna zona local"
    vieja = por_rectangulo[0]
    iou = _iou((vieja.x, vieja.y, vieja.w, vieja.h), CAJA_TALLER)
    print(f"\n[T2g-trampa] criterio viejo pondria primera ({vieja.x},{vieja.y},{vieja.w},"
          f"{vieja.h}) IoU={iou:.3f}")
    assert iou < 0.5, (
        "con el criterio del dia 3 la ventana ya saldria primera: el montaje ha dejado de "
        "tener la trampa y el test de la zona principal no prueba nada"
    )


def test_T2g_una_ventana_en_sombra_de_verdad_se_sigue_viendo(taller):
    """El caso contrario. Arreglar la esquina a base de ignorar las sombras
    cambiaria un fallo por otro: una ventana DENTRO de una sombra profunda
    tiene que seguir saliendo, y primera."""
    original, res = taller["en sombra+vineta"]
    lum = log_decode(np.asarray(original, dtype=np.float64), WORKING_SPACE) @ LUMA_REC709
    x, y, w, h = CAJA_EN_SOMBRA
    paradas = float(np.log2(lum[y : y + h, x : x + w].mean() / np.median(lum)))
    d = res.diagnosis
    _imprimir("T2g en sombra", d, CAJA_EN_SOMBRA)
    print(f"[T2g en sombra] la caja esta {paradas:+.2f} paradas respecto a la mediana")
    # Que la sombra sea de verdad: si alguien toca la escena y la caja deja de
    # estar a oscuras, este test dejaria de probar lo que dice.
    assert paradas < -1.0, f"la caja 'en sombra' solo esta {paradas:+.2f} paradas por debajo"
    locales = _locales(d)
    assert locales, "una ventana en sombra se le escapa entera"
    primera = locales[0]
    iou = _iou((primera.x, primera.y, primera.w, primera.h), CAJA_EN_SOMBRA)
    assert iou > 0.5, f"la zona principal solapa IoU {iou:.3f} con la ventana en sombra"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "LIMITE CONOCIDO, MEDIDO EL 2026-09-16, NO ARREGLADO. La misma ventana en sombra "
        "(520,250,110,100), ganancia 1.5 en luz lineal, SIN vineta, sobre el taller con la "
        "sombra grande: la zona de mas masa es (0,0,113,360), la franja oscura del borde "
        "IZQUIERDO, con 6.04 dE2000 medio y IoU 0.000; la ventana sale partida en "
        "(515,243,88,61) IoU 0.377 y (490,259,150,101) IoU 0.620. Con el orden del dia 3 "
        "tambien salia primera la franja (6.04 era tambien el mayor dE2000 medio), asi que "
        "no es una regresion del orden por masa. Es la HUELLA de la ventana en el LUT: una "
        "ventana que aclara colores oscuros ensena al LUT a aclarar esos colores, y el LUT "
        "los aclara tambien en todo el resto de lo oscuro del cuadro, que aqui es mucho. "
        "Eso es residuo real y ninguna forma de ordenar lo distingue de la ventana."
    ),
)
def test_T2g_una_ventana_en_sombra_sin_vineta_limite_conocido(taller):
    """Lo mismo que el test de arriba pero sin vineta. Ver el `reason`."""
    _, res = taller["en sombra sola"]
    d = res.diagnosis
    _imprimir("T2g en sombra sin vineta", d, CAJA_EN_SOMBRA)
    locales = _locales(d)
    assert locales
    primera = locales[0]
    assert _iou((primera.x, primera.y, primera.w, primera.h), CAJA_EN_SOMBRA) > 0.5


def test_T2g_el_taller_sin_nada_espacial_no_se_inventa_zonas(taller):
    """El contrapeso, en MI escena: la sombra profunda por si sola, sin nada
    espacial encima, no puede convertirse en una zona."""
    _, res = taller["nada espacial"]
    d = res.diagnosis
    print(f"\n[T2g nada] repro={d.lut_reproducible:.4f} puro={d.is_pure_lut} "
          f"etiquetas={[hp.label for hp in d.hotspots]}")
    assert d.hotspots == (), f"se inventa {len(d.hotspots)} zona(s) en el taller sin nada espacial"


# ---------------------------------------------------------------------------
# DIA 4 - Masa contra intensidad
# ---------------------------------------------------------------------------


def _dos_ventanas(original: np.ndarray, ventanas) -> object:
    col = _coloreado_limpio(original)
    for caja, ganancia in ventanas:
        col = gen.apply_window(col, box=caja, gain=ganancia, tint=(1.0, 1.0, 1.0), feather=12)
    return invertir_grado(original, np.asarray(col, dtype=np.float32)).diagnosis


def test_T2h_una_zona_grande_y_floja_va_antes_que_una_pequena_e_intensa(estudio_trabajo):
    """Grande y floja: (20,200,240,140) a x1.35. Pequena e intensa:
    (500,40,60,50) a x1.9. Gana la GRANDE, y es lo correcto por tres razones:

    1. La primera linea dice **que reconstruir primero para recuperar mas
       imagen**. La grande cambia mas cuadro (medido: masa 7831 contra 2157).
    2. Lo pequeno e intenso es exactamente lo que fabrican los artefactos -- la
       esquina en sombra del dia 3 era 31x29 px --; lo grande y coherente no lo
       fabrica un artefacto local.
    3. La pequena NO se pierde: sale segunda, con su ΔE2000 medio, que es MAYOR
       (24.17 contra 12.35) y se lee en la misma linea.

    El precio, dicho: un retoque diminuto y muy fuerte (unos ojos) saldra detras
    de un lavado amplio y suave aunque al ojo le importe mas. Lo que se ordena
    es cuanta imagen cambia, no cuanto llama la atencion.
    """
    grande, pequena = ((20, 200, 240, 140), 1.35), ((500, 40, 60, 50), 1.9)
    d = _dos_ventanas(estudio_trabajo, [grande, pequena])
    _imprimir("T2h grande-floja vs pequena-intensa", d, grande[0])
    locales = _locales(d)
    assert len(locales) >= 2, f"no salen las dos: {[(z.x, z.y, z.w, z.h) for z in locales]}"
    primera, segunda = locales[0], locales[1]
    assert _iou((primera.x, primera.y, primera.w, primera.h), grande[0]) > 0.5
    assert _iou((segunda.x, segunda.y, segunda.w, segunda.h), pequena[0]) > 0.5
    # Y la competicion es de verdad: por ΔE2000 medio la pequena iria primero.
    assert segunda.magnitude > primera.magnitude, (
        "la pequena ya no es la mas intensa: este test ha dejado de enfrentar masa e intensidad"
    )


def test_T2h_si_la_intensa_tambien_cambia_mas_imagen_va_primera(estudio_trabajo):
    """El contrario, para que quede claro que se ordena por MASA y no por AREA:
    (470,30,130,120) a x2.0 contra (20,220,200,110) a x1.4. La intensa tiene
    mas masa (medido: 10848 contra 1322 del trozo mayor de la floja) y va
    primera."""
    intensa, floja = ((470, 30, 130, 120), 2.0), ((20, 220, 200, 110), 1.4)
    d = _dos_ventanas(estudio_trabajo, [floja, intensa])
    _imprimir("T2h intensa con mas masa", d, intensa[0])
    locales = _locales(d)
    assert locales
    primera = locales[0]
    assert _iou((primera.x, primera.y, primera.w, primera.h), intensa[0]) > 0.5


def test_zonas_ordena_por_masa_y_mide_el_residuo_sobre_la_componente():
    """`_zonas` a pelo, sin LUT de por medio, con un campo fabricado:

    - una meseta grande y baja (60x60 a 0.2: masa 720),
    - un pico pequeno y alto (12x12 a 1.0: masa 144),
    - y una "L" (dos brazos de 40x6) cuyo rectangulo es casi todo vacio.

    Por pico iria primero el pico; por masa, la meseta. Y el residuo de la L
    se promedia sobre sus pixeles (todos a 10.0), no sobre su rectangulo, que
    daria 10.0 x 444/1600 = 2.8."""
    campo = np.zeros((200, 200))
    residuo = np.zeros((200, 200))
    campo[20:80, 20:80] = 0.2
    campo[150:162, 150:162] = 1.0
    campo[120:160, 20:26] = 0.5
    campo[154:160, 20:60] = 0.5
    residuo[120:160, 20:26] = 10.0
    residuo[154:160, 20:60] = 10.0
    zonas = _zonas(campo, 0.1, residuo)
    cajas = [z.caja for z in zonas]
    print(f"\n[_zonas] {[(z.caja, round(z.masa, 1), round(z.residuo_medio, 3)) for z in zonas]}")
    assert cajas[0] == (20, 20, 60, 60), f"la meseta no va primera: {cajas}"
    ele = next(z for z in zonas if z.caja == (20, 120, 40, 40))
    assert ele.residuo_medio == pytest.approx(10.0), (
        f"el residuo de la L se promedia sobre su rectangulo: {ele.residuo_medio}"
    )
    assert [z.masa for z in zonas] == sorted((z.masa for z in zonas), reverse=True)
