"""T1 (ingenieria inversa) y T2 (deteccion de lo que no es un LUT), medidos de fuera.

Entrada unica al repo: `core.reverse.invertir_grado`. Nada de `analizar_espacial`,
nada de `_mascara_cubierta`, nada con guion bajo delante.

SOBRE QUE PIXELES SE MIDE EL T1
-------------------------------
Lo publicado (0.1415 / 1.7409) es "en la zona con cobertura". Segun
`core/reverse/invertir.py` eso significa, literalmente: pixeles cuya celda MAS
CERCANA del cubo tiene al menos `min_samples` (4) muestras reales, donde la
celda se busca sobre el **original ya pasado por el CDL** (que es el dominio
del LUT) y con los valores sujetos a 0..1.

Esa mascara se recalcula aqui con numpy puro a partir de lo que devuelve la
API publica (`resultado.cdl` y `resultado.coverage.covered_mask()`). No se
llama a la funcion interna del repo. Y se dan las dos cifras -- zona cubierta y
plano entero -- porque son numeros distintos y confundirlos es la forma facil
de comparar dos medidas correctas que no son comparables.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.reverse import invertir_grado
from tests.medicion import escena as E
from tests.medicion import metrica as M

pytestmark = pytest.mark.medicion


def _informe(nombre: str, **cifras) -> None:
    linea = "  ".join(f"{k}={v:.6g}" for k, v in cifras.items())
    print(f"\n[MEDICION {nombre}] {linea}")


def _mascara_zona_cubierta(fuente_post_cdl: np.ndarray, cobertura) -> np.ndarray:
    """(alto, ancho) bool: pixeles cuya celda mas cercana tiene muestras suficientes.

    Reimplementado aqui con numpy puro. `cobertura.covered_mask()` es API
    publica del contrato (`CoverageMap`), asi que entra por la puerta.
    """
    n = cobertura.size
    px = np.clip(np.asarray(fuente_post_cdl, dtype=np.float64), 0.0, 1.0) * (n - 1)
    i = np.rint(px).astype(np.int64)
    cubiertas = np.asarray(cobertura.covered_mask(), dtype=bool)
    return cubiertas[i[..., 0], i[..., 1], i[..., 2]]


# ---------------------------------------------------------------------------
# T1
# ---------------------------------------------------------------------------


def test_T1_ingenieria_inversa():
    """Criterio publicado: ΔE2000 medio < 1.0 y maximo < 3.0 en la zona cubierta.
    Cifra publicada: 0.1415 / 1.7409."""
    original = E.escena_trabajo()
    tabla = E.tabla_lut_conocida()
    coloreado = E.coloreado(original, tabla)

    resultado = invertir_grado(original, coloreado)

    # La reconstruccion tal y como la haria la GUI: LUT(CDL(original)).
    reconstruido = resultado.lut.apply(resultado.cdl.apply(original.astype(np.float64)))

    de = M.delta_e2000_wg(coloreado, reconstruido)
    fuente = resultado.cdl.apply(original.astype(np.float64))
    cubierto = _mascara_zona_cubierta(fuente, resultado.coverage)

    cub = M.resumen_de(de, cubierto)
    todo = M.resumen_de(de)

    _informe(
        "T1",
        de_medio_cubierto=cub["medio"],
        de_max_cubierto=cub["max"],
        de_p95_cubierto=cub["p95"],
        de_medio_todo=todo["medio"],
        de_max_todo=todo["max"],
        fraccion_pixeles_cubiertos=float(cubierto.mean()),
        cobertura_del_cubo=resultado.coverage.coverage_fraction(),
    )
    # Y lo que dice el repo de si mismo sobre el MISMO montaje, para poder
    # separar "material distinto" de "metrica distinta".
    m = resultado.confidence.metrics
    _informe(
        "T1-lo-que-dice-el-repo",
        de_medio_cubierto=float(m.get("de_medio_cubierto", float("nan"))),
        de_max_cubierto=float(m.get("de_max_cubierto", float("nan"))),
        de_medio_todo=resultado.delta_e_mean,
        de_max_todo=resultado.delta_e_max,
    )

    assert cub["medio"] < 1.0, f"ΔE2000 medio en la zona cubierta: {cub['medio']:.4f}"
    assert cub["max"] < 3.0, f"ΔE2000 maximo en la zona cubierta: {cub['max']:.4f}"


def test_T1_el_mapa_de_cobertura_no_marca_como_real_lo_que_se_invento():
    """Recuento propio, trilineal y sobre el dominio del LUT (post-CDL).

    No es una de las cuatro cifras, pero si el mapa de cobertura mintiera, la
    cifra del T1 estaria medida sobre los pixeles equivocados y no valdria.
    """
    original = E.escena_trabajo()
    resultado = invertir_grado(original, E.coloreado(original, E.tabla_lut_conocida()),
                               min_muestras=4)
    cob = resultado.coverage
    n = cob.size

    fuente = resultado.cdl.apply(original.astype(np.float64))
    px = np.clip(fuente.reshape(-1, 3), 0.0, 1.0) * (n - 1)
    i0 = np.clip(np.floor(px).astype(np.int64), 0, n - 2)
    # Aqui solo importa QUE celdas toca cada pixel, no con cuanto peso: la
    # pregunta es si la cobertura marca como "tengo datos" alguna celda donde no
    # cayo ni una muestra. Los pesos trilineales no hacen falta para eso.
    tocadas = np.zeros((n, n, n), dtype=bool)
    for kr in (0, 1):
        for kg in (0, 1):
            for kb in (0, 1):
                idx = (i0[:, 0] + kr, i0[:, 1] + kg, i0[:, 2] + kb)
                tocadas[idx] = True

    reales = np.asarray(cob.covered_mask(), dtype=bool)
    mienten = int((reales & ~tocadas).sum())
    _informe(
        "T1-cobertura",
        celdas_con_dato=float(reales.sum()),
        total=float(reales.size),
        fraccion=cob.coverage_fraction(),
        celdas_que_mienten=float(mienten),
    )
    assert mienten == 0, f"{mienten} celdas dicen tener datos y no los tienen"


# ---------------------------------------------------------------------------
# T2
# ---------------------------------------------------------------------------


def test_T2_deteccion_de_lo_que_no_es_un_lut():
    """Criterio publicado: no decir 100% LUT, y señalar la zona.
    Cifra publicada: 70.0% reproducible, zona solapada (100% la noche 1, 99.4% el dia 2)."""
    original = E.escena_trabajo()
    tabla = E.tabla_lut_conocida()
    coloreado = E.coloreado_con_lo_espacial(original, tabla)

    resultado = invertir_grado(original, coloreado)
    d = resultado.diagnosis

    etiquetas = sorted({hp.label for hp in d.hotspots})
    print(f"\n[MEDICION T2-etiquetas] {etiquetas}")

    _informe(
        "T2",
        lut_reproducible=d.lut_reproducible,
        is_pure_lut=float(d.is_pure_lut),
        n_hotspots=float(len(d.hotspots)),
    )

    assert not d.is_pure_lut, "dice que es 100% LUT con una vineta y una ventana encima"
    assert d.lut_reproducible < 1.0
    assert d.spatial_residual is not None, "no deja mapa del residuo espacial"
    assert len(d.hotspots) > 0, "no señala ninguna zona"


def _solape_con(hp, caja) -> float:
    """Fraccion del hotspot que cae dentro de `caja`. Es la misma cuenta que
    hace el repo en su propio T2: se divide por el area del HOTSPOT."""
    x, y, w, h = caja
    sx = max(0, min(x + w, hp.x + hp.w) - max(x, hp.x))
    sy = max(0, min(y + h, hp.y + hp.h) - max(y, hp.y))
    return (sx * sy) / float(hp.w * hp.h)


def _principal(hotspots, etiqueta: str | None = None):
    """La zona PRINCIPAL: la primera de la tupla, en el orden en que llega.

    DESDE EL DIA 4 ES EL CONTRATO (`ReverseDiagnosis.hotspots` en
    `core/contracts.py`, commit 86da011): los hotspots vienen **ordenados por
    importancia y el primero es el principal**, que es exactamente el orden en
    que la GUI los lista. Hasta el dia 3 este arnes elegia con
    `max(magnitude)`, que entonces coincidia con el orden de la tupla porque el
    modulo reordenaba por magnitud. Ya no reordena (ordena por masa), y elegir
    por magnitud dejaria de probar lo que la interfaz enseña.

    Con `etiqueta`, la primera de esa etiqueta, respetando el mismo orden. Hace
    falta porque las etiquetas de forma (`vineta`, `textura`) van siempre
    delante y no son la ventana.
    """
    candidatas = [hp for hp in hotspots if etiqueta is None or hp.label == etiqueta]
    return candidatas[0] if candidatas else None


#: Lo que sale HOY, en el ORDEN DE LA TUPLA, medido el 2026-09-16 contra el
#: commit 86da011 y aferrado en
#: `test_T2_las_dos_cajas_y_su_orden_estan_aferrados`. Es el montaje del xfail
#: de abajo: mi escena con viñeta y ventana aplicadas en luz lineal.
#: (caja, magnitud).
#:
#: HISTORIA, para que nadie la reconstruya a mano:
#:   dia 3 (hasta 71448ff): #0 (0,284,31,29) mag 12.725531826505737
#:                          #1 (89,301,251,104) mag 11.377186278350779
#:     -> magnitud = ΔE2000 medio del RECTANGULO; orden por esa magnitud.
#:   dia 4 (86da011):       #0 (89,301,251,104) mag 14.93420487819448
#:                          #1 (0,284,31,29) mag 12.297431460074693
#:     -> magnitud = ΔE2000 medio de los PIXELES de la zona; orden por masa.
#:   Las dos cajas son LAS MISMAS en los dos, y `lut_reproducible` es el mismo
#:   bit a bit (0.9083604985578424). Solo cambia el orden y la magnitud.
CAJAS_ESPERADAS_T2 = (
    ((89, 301, 251, 104), 14.93420487819448),
    ((0, 284, 31, 29), 12.297431460074693),
)

#: `lut_reproducible` del mismo montaje, identico el dia 3 y el dia 4.
REPRODUCIBLE_ESPERADO_T2 = 0.9083604985578424


def test_T2_las_dos_cajas_y_su_orden_estan_aferrados():
    """EL CENTINELA DEL XFAIL DE ABAJO. Este test SI tiene que estar en verde.

    POR QUE EXISTE
    --------------
    El `xfail(strict=True)` de abajo afirma algo sobre **cual es la zona que el
    modulo declara principal**. Si el montaje se moviera por debajo, ese xfail
    podria pasar a XPASS -- que con `strict=True` es rojo -- y nadie sabria si
    es que el limite se ha cerrado o es que ha cambiado otra cosa.

    Asi que aqui se aferran las dos cajas, su ORDEN y sus magnitudes. Si mañana
    cambian, rojo en este test, diciendo exactamente que ha cambiado.

    YA SALTO UNA VEZ, Y PARA ESO ESTABA (dia 4)
    -------------------------------------------
    El commit 86da011 cambio el orden de las zonas (de ΔE del rectangulo a
    masa) y la definicion de `magnitude` (de ΔE medio del rectangulo a ΔE medio
    de los pixeles de la zona). Este centinela salto con "el hotspot #0 era
    (0, 284, 31, 29) y ahora es (89,301,251,104)". Lo verifico su autor, no
    quien cambio el detector, y se re-aferro al estado nuevo porque el cambio
    es legitimo: las cajas no se mueven, `lut_reproducible` no se mueve, y la
    nueva `magnitude` es una lectura mas fiel del contrato ("residuo medio en
    la zona"). Detalle y verificacion en MEDICION-INDEPENDIENTE.md, seccion 3.

    LO QUE ESTE TEST YA NO AFIRMA, Y POR QUE
    -----------------------------------------
    El dia 3 afirmaba un margen de magnitud entre las dos cajas (11.85%) como
    "el desempate". **Ya no es el desempate**: el orden va por masa, y la masa
    no sale por la API publica (`Hotspot` no la lleva). El margen de magnitud
    de hoy (21.44%) se sigue vigilando, pero como centinela de la DEFINICION de
    `magnitude`, no como el motivo del orden. Las masas que cita el autor del
    cambio (3909 contra 142) son cifra suya: yo no las he medido, porque solo
    se ven por `analizar_espacial`, que el encargo de esta medicion me prohibe
    llamar.

    DETERMINISMO: medido el dia 3, NO re-medido contra 86da011
    ----------------------------------------------------------
    El dia 3, contra el codigo de entonces: magnitudes bit a bit iguales en 18
    ejecuciones con `OMP_NUM_THREADS` en 1, 2, 8 y sin fijar. Contra 86da011 no
    he repetido ese barrido (la maquina estaba compartida y a carga ~40); lo
    unico medido hoy es que dos ejecuciones separadas del mismo commit dan los
    mismos 17 digitos. Lo que no depende del commit sigue igual: la
    aleatoriedad de `core` esta sembrada y `pytest-randomly` no esta instalado
    en este venv, asi que `-p no:randomly` es un no-op.
    """
    original = E.escena_trabajo()
    coloreado = E.coloreado_con_lo_espacial(original, E.tabla_lut_conocida())
    d = invertir_grado(original, coloreado).diagnosis
    hs = list(d.hotspots)  # EN EL ORDEN DE LA TUPLA, que es el del contrato

    for i, hp in enumerate(hs):
        print(
            f"\n[MEDICION T2-aferrado] #{i} {hp.label!r} ({hp.x},{hp.y},{hp.w},{hp.h}) "
            f"mag={hp.magnitude!r} solape={_solape_con(hp, E.CAJA_VENTANA):.4f}"
        )
    if len(hs) >= 2:
        _informe(
            "T2-aferrado-margen",
            margen_de_magnitud=hs[0].magnitude / hs[1].magnitude - 1.0,
            max_magnitud_coincide_con_la_primera=float(
                max(hs, key=lambda z: z.magnitude) is hs[0]
            ),
        )

    pista = (
        "el montaje del xfail de T2 se ha movido. Mira MEDICION-INDEPENDIENTE.md "
        "seccion 3 antes de tocar nada: si esto cambia, el xfail de abajo puede pasar "
        "a XPASS sin que el limite se haya cerrado. Lo decide el autor de la medicion, "
        "no quien cambio el detector"
    )
    assert d.lut_reproducible == pytest.approx(REPRODUCIBLE_ESPERADO_T2, rel=1e-9), (
        f"lut_reproducible era {REPRODUCIBLE_ESPERADO_T2} y ahora es {d.lut_reproducible}: {pista}"
    )
    assert len(hs) == 2, f"esperaba 2 hotspots y hay {len(hs)}: {pista}"
    for i, (caja, magnitud) in enumerate(CAJAS_ESPERADAS_T2):
        hp = hs[i]
        assert hp.label == "zona local", f"el hotspot #{i} ya no es 'zona local': {pista}"
        assert (hp.x, hp.y, hp.w, hp.h) == caja, (
            f"el hotspot #{i} era {caja} y ahora es ({hp.x},{hp.y},{hp.w},{hp.h}): {pista}"
        )
        assert hp.magnitude == pytest.approx(magnitud, rel=1e-6), (
            f"la magnitud del hotspot #{i} era {magnitud} y ahora es {hp.magnitude}: {pista}"
        )

    # Centinela de la DEFINICION de magnitud, no del orden (ver docstring).
    # Dia 3, con ΔE del rectangulo: 11.85% y en el orden contrario.
    # Dia 4, con ΔE de los pixeles de la zona: 21.44%.
    margen = hs[0].magnitude / hs[1].magnitude - 1.0
    assert 0.18 < margen < 0.25, (
        f"el margen de magnitud entre #0 y #1 era del 21.44% y ahora es del {margen:.2%}: "
        f"¿ha vuelto a cambiar la definicion de Hotspot.magnitude? {pista}"
    )


#: El `reason` del xfail de abajo, escrito aparte porque es largo y porque la
#: regla de las cifras de CONTRATOS.md pide que lleve numeros reproducibles.
#: Todas las cifras estan MEDIDAS el 2026-09-16 contra el commit 86da011 sobre
#: el montaje que monta ESTE MISMO test, no sobre otro.
#:
#: REESCRITO EL DIA 4. El reason del dia 3 decia que la zona principal era la
#: esquina (0,284,31,29) con solape 0.0000. Despues de 86da011 la principal es
#: la ventana con solape 0.4294. El test seguia en XFAIL, pero **la descripcion
#: ya no era cierta**, que es exactamente el fallo que la regla de las cifras
#: existe para cazar (CONTRATOS.md, AUDITORIA-DIA2.md caso 4).
_RAZON_XFAIL_T2 = (
    "LIMITE CONOCIDO Y VIVO, MEDIDO EL 2026-09-16 CONTRA 86da011, NO ARREGLADO A PROPOSITO. "
    "QUE FALLA: la CAJA de la ventana, no el detector y ya no el orden. "
    "CIFRAS, sobre el montaje de este mismo test (mi escena 720x405 semilla 20260915, "
    "viñeta 0.42 + ventana real (96,250,190,110) ganancia 1.55 aplicadas EN LUZ LINEAL): "
    "la zona PRINCIPAL -- la primera 'zona local' de la tupla, que es lo que dice el contrato "
    "desde el dia 4 y lo que lista la GUI -- es (89,301,251,104), magnitud 14.93420487819448, "
    "y solapa 0.4294 con la ventana real, contra el umbral de 0.80 que el repo afirma en su "
    "propio T2. La segunda es la esquina en sombra (0,284,31,29), magnitud 12.297431460074693, "
    "solape 0.0000. lut_reproducible=0.9083604985578424. "
    "QUE CAMBIO EL DIA 4 Y QUE NO: hasta 71448ff la principal era la esquina (solape 0.0000) "
    "y con 86da011 la ventana pasa a primera. El porque (orden por masa en vez de por ΔE2000 medio "
    "del rectangulo, y magnitud medida sobre los pixeles de la zona) lo he LEIDO en el diff, no "
    "lo he medido: la masa no sale por la API publica. Lo MEDIDO, volcando todos los hotspots "
    "de mis ocho montajes distintos contra 71448ff y contra 86da011: en este montaje las dos cajas son "
    "las MISMAS y lut_reproducible es identico bit a bit; se arreglo el orden, no la caja. El orden y las magnitudes estan aferrados en "
    "test_T2_las_dos_cajas_y_su_orden_estan_aferrados, que es un test EN VERDE: si se mueven, "
    "salta ese y no este. "
    "POR QUE ES LA CAJA Y NO EL DETECTOR: el 93.6% de los 500 pixeles de mayor residuo SI caen "
    "dentro de la ventana real, y el residuo medio dentro (0.3689) es 4.74 veces el de fuera "
    "(0.0779): el mapa de calor acierta, y lo que falla es la geometria de la caja principal. "
    "En horizontal cubre la ventana entera (190 de 190 px) y se pasa 54 px por la derecha "
    "(llega a x=340, la ventana a x=286); en vertical empieza 51 px MAS ABAJO (y=301 contra "
    "y=250) y baja hasta el borde del cuadro (y=405, la ventana acaba en y=360), asi que solo "
    "59 de sus 104 px de alto caen dentro. Area 26104 px contra 20900 de la ventana (1.25x). "
    "190x59/26104 = 0.4294. "
    "CUANDO SI PASA: con la convencion del repo, aplicando la MISMA viñeta y la MISMA ventana "
    "sobre la imagen ya codificada en vez de en luz lineal, sale lut_reproducible=0.6844 "
    "(publicado 0.7002), aparece la etiqueta 'vineta', y la primera 'zona local' es "
    "(98,257,229,105) con solape 0.8053 > 0.80: pasaria. O sea que el limite aparece cuando lo "
    "espacial es SUAVE, que es el caso de una viñeta optica real. Ese caso tambien esta "
    "afirmado en verde en test_T2_atribucion_luz_lineal_contra_imagen_codificada. "
    "QUE HARIA FALTA PARA CERRARLO: no basta con reordenar (ya se hizo, y la caja sigue en "
    "0.4294) ni con retocar un umbral de magnitud. Tampoco se arregla quitando la sombra: con "
    "sombra=False y ventana sola, la principal ya es la ventana, (57,244,226,120), pero solapa "
    "0.7585 < 0.80; y con sombra=True y ventana sola la principal SIGUE siendo la esquina "
    "(0,274,41,41), solape 0.0000. Hace falta que la caja de la ventana se ajuste a la ventana. "
    "Segun el autor de 86da011, que probo cuatro formas y cada una rompia otro caso, eso pide "
    "mirar bordes, que es otro detector: esa cifra es suya y no esta medida aqui. "
    "COMANDO QUE REPRODUCE LAS DOS COSAS (el rojo y el caso que si pasa): "
    "cd '/Users/mariobote/Documents/Varios/CLAUDE CODE/sidebflms-color' && "
    ".venv/bin/python -m pytest tests/medicion/test_t1_t2.py -s -k T2 "
    "-- mira las lineas [MEDICION T2-cajas], [MEDICION T2-aferrado], [MEDICION T2-atribucion] "
    "y [MEDICION T2-sonda]. Ficha completa de cada cifra (montaje, comando y fecha) en "
    "MEDICION-INDEPENDIENTE.md, seccion 3. "
    "SI ESTO PASA A XPASS: comprobad primero que el centinela sigue en verde; si el centinela "
    "salta a la vez, lo que se ha movido es el montaje o el detector, no se ha cerrado el "
    "limite. Si el centinela sigue verde y esto pasa, es imposible con las cifras de arriba: "
    "algo esta mal en el propio test. Y no toqueis el montaje de este test: aflojarlo seria "
    "exactamente la forma de hacerlo desaparecer sin arreglarlo."
)


@pytest.mark.xfail(strict=True, reason=_RAZON_XFAIL_T2)
def test_T2_la_zona_senalada_cae_donde_esta_mi_ventana():
    """Mi caja contra la suya, y el residuo dentro contra el de fuera.

    **ESTE TEST ESTA EN `xfail(strict=True)` Y ES EL RESULTADO, NO UN PENDIENTE.**
    El criterio y el montaje son los que eran: no se han tocado ni se deben
    tocar. Lo que se afirma es lo mismo que el repo afirma de si mismo en su
    T2, y con mi material no se cumple. Las cifras estan en el `reason`.

    El criterio que se afirma es el mismo que el repo afirma de si mismo: la
    zona local PRINCIPAL -- la primera de la tupla, que es lo que dice el
    contrato desde el dia 4 y lo que lista la GUI -- tiene que solapar mas del
    80% con la ventana real. Hasta el dia 3 se elegia con `max(magnitude)`.
    Al lado se informa de todos los hotspots, del mejor solape de cualquiera de
    ellos y de donde caen de verdad los pixeles de mayor residuo, porque si el
    criterio no se cumple hay que poder decir si falla el detector o solo la
    forma en que recorta la caja.
    """
    original = E.escena_trabajo()
    coloreado = E.coloreado_con_lo_espacial(original, E.tabla_lut_conocida())
    d = invertir_grado(original, coloreado).diagnosis

    residuo = d.spatial_residual
    assert residuo is not None

    x, y, w, h = E.CAJA_VENTANA
    dentro = float(np.nanmean(residuo[y:y + h, x:x + w]))
    mascara_fuera = np.ones(residuo.shape, dtype=bool)
    mascara_fuera[y:y + h, x:x + w] = False
    fuera = float(np.nanmean(residuo[mascara_fuera]))

    # Donde caen de verdad los 500 pixeles de mayor residuo. Esto no depende de
    # como se recorten las cajas.
    plano = np.asarray(residuo, dtype=np.float64)
    top = np.dstack(np.unravel_index(np.argsort(plano.ravel())[-500:], plano.shape))[0]
    top_dentro = float(
        ((top[:, 0] >= y) & (top[:, 0] < y + h) & (top[:, 1] >= x) & (top[:, 1] < x + w)).mean()
    )

    print(f"\n[MEDICION T2-cajas] mia={E.CAJA_VENTANA}")
    for hp in d.hotspots:
        print(
            f"[MEDICION T2-cajas]   {hp.label!r} ({hp.x},{hp.y},{hp.w},{hp.h}) "
            f"mag={hp.magnitude:.4f} solape={_solape_con(hp, E.CAJA_VENTANA):.4f}"
        )

    locales = [hp for hp in d.hotspots if hp.label == "zona local"]
    mejor = max((_solape_con(hp, E.CAJA_VENTANA) for hp in d.hotspots), default=float("nan"))
    _informe(
        "T2-zona",
        residuo_dentro=dentro,
        residuo_fuera=fuera,
        razon=dentro / max(fuera, 1e-9),
        mejor_solape_de_cualquier_hotspot=mejor,
        fraccion_top500_residuo_en_mi_ventana=top_dentro,
    )
    assert dentro > fuera * 2.0, (
        f"el residuo dentro de la ventana ({dentro:.4f}) no destaca sobre el resto ({fuera:.4f})"
    )
    if not locales:
        pytest.fail(
            "no emite ninguna 'zona local'; las etiquetas que emite son "
            f"{sorted({hp.label for hp in d.hotspots})}"
        )

    hp = _principal(d.hotspots, "zona local")
    solape = _solape_con(hp, E.CAJA_VENTANA)
    _informe("T2-zona-principal", solape=solape, magnitud=hp.magnitude)
    assert solape > 0.8, (
        f"la zona principal que señala ({hp.x},{hp.y},{hp.w},{hp.h}) no cae dentro de mi "
        f"ventana {E.CAJA_VENTANA}: solo solapa el {solape:.1%}"
    )


def test_T2_de_donde_sale_cada_hotspot_vineta_ventana_y_sombra():
    """Sonda para poder atribuir la diferencia, no para arreglarla.

    Se mide el diagnostico con la vineta sola, con la ventana sola y con las
    dos, y cada una de esas tres con mi escena TAL CUAL y con la sombra
    profunda de la esquina quitada. La sombra es lo unico de mi escena que no
    esta en la del repo, y es la sospechosa de la zona local espuria de la
    esquina inferior izquierda.

    Lo unico que se afirma es lo que manda el criterio del encargo: con algo
    espacial encima, el diagnostico NO puede decir que es 100% LUT.
    """
    tabla = E.tabla_lut_conocida()
    for sombra in (True, False):
        original = E.escena_trabajo(sombra=sombra)
        for nombre, kw in (
            ("vineta-sola", {"ganancia_ventana": 1.0}),
            ("ventana-sola", {"vineta": 0.0}),
            ("las-dos", {}),
        ):
            d = invertir_grado(
                original, E.coloreado_con_lo_espacial(original, tabla, **kw)
            ).diagnosis
            print(
                f"\n[MEDICION T2-sonda] sombra={sombra} caso={nombre} "
                f"reproducible={d.lut_reproducible:.4f} pure={d.is_pure_lut} "
                f"n_hotspots={len(d.hotspots)}"
            )
            for hp in d.hotspots:
                print(
                    f"[MEDICION T2-sonda]   {hp.label!r} ({hp.x},{hp.y},{hp.w},{hp.h}) "
                    f"mag={hp.magnitude:.4f} solape={_solape_con(hp, E.CAJA_VENTANA):.4f}"
                )
            assert not d.is_pure_lut, (
                f"con {nombre} encima (sombra={sombra}) dice que es 100% LUT"
            )

            # Los dos casos de "ventana sola" los cita el reason del xfail de
            # T2 en "que haria falta para cerrarlo", asi que se afirman aqui.
            # Medido el 2026-09-16 contra 86da011, en el orden de la tupla.
            principal = _principal(d.hotspots, "zona local")
            if nombre == "ventana-sola" and principal is not None:
                caja = (principal.x, principal.y, principal.w, principal.h)
                solape = _solape_con(principal, E.CAJA_VENTANA)
                esperado = {True: ((0, 274, 41, 41), 0.0), False: ((57, 244, 226, 120), 0.7585)}
                caja_esp, solape_esp = esperado[sombra]
                assert caja == caja_esp and solape == pytest.approx(solape_esp, abs=1e-4), (
                    f"ventana sola, sombra={sombra}: la principal era {caja_esp} con solape "
                    f"{solape_esp} y ahora es {caja} con {solape:.4f}. El reason del xfail de "
                    f"T2 cita este caso: hay que revisarlo"
                )
            elif nombre == "ventana-sola":
                pytest.fail(f"ventana sola, sombra={sombra}: ya no emite ninguna 'zona local'")


def test_T2_atribucion_luz_lineal_contra_imagen_codificada():
    """¿De donde sale el hueco entre mi 0.908 y el 0.700 publicado?

    La sospecha es que no es el detector, sino DONDE se aplica lo espacial: una
    ganancia de 0.58x duele muchisimo mas encima de una curva logaritmica que
    encima de luz lineal, porque en log la misma ganancia es un desplazamiento
    constante enorme. Aqui se mide la misma vineta y la misma ventana de las
    dos maneras. Se informa; no se afirma cual esta bien, porque las dos son
    defendibles (la mia es mas fisica, la suya es lo que hace un colorista
    encima de un plano ya gradado).
    """
    original = E.escena_trabajo()
    tabla = E.tabla_lut_conocida()
    for nombre, en_lineal in (("luz-lineal (la mia)", True), ("codificada (la suya)", False)):
        d = invertir_grado(
            original, E.coloreado_con_lo_espacial(original, tabla, en_lineal=en_lineal)
        ).diagnosis
        mejor = max((_solape_con(hp, E.CAJA_VENTANA) for hp in d.hotspots), default=float("nan"))
        print(
            f"\n[MEDICION T2-atribucion] {nombre}: reproducible={d.lut_reproducible:.4f} "
            f"pure={d.is_pure_lut} n_hotspots={len(d.hotspots)} mejor_solape={mejor:.4f}"
        )
        for hp in d.hotspots:
            print(
                f"[MEDICION T2-atribucion]   {hp.label!r} ({hp.x},{hp.y},{hp.w},{hp.h}) "
                f"mag={hp.magnitude:.4f} solape={_solape_con(hp, E.CAJA_VENTANA):.4f}"
            )
        assert not d.is_pure_lut, f"con {nombre} dice que es 100% LUT"

        if not en_lineal:
            # El `reason` del xfail cita este caso como "cuando SI pasa". Si lo
            # cita, se afirma: una cifra publicada en un reason que no esta
            # afirmada en ningun sitio es un recuerdo, no una medida.
            # Medido el 2026-09-16 contra 86da011 (y la misma caja el dia 3).
            principal = _principal(d.hotspots, "zona local")
            assert principal is not None, "en el caso codificado ya no hay 'zona local'"
            caja = (principal.x, principal.y, principal.w, principal.h)
            solape = _solape_con(principal, E.CAJA_VENTANA)
            assert caja == (98, 257, 229, 105), (
                f"la zona principal del caso codificado era (98,257,229,105) y ahora es {caja}: "
                f"el reason del xfail de T2 cita esta caja, hay que revisarlo"
            )
            assert solape > 0.8, (
                f"el caso codificado ya no pasa el criterio ({solape:.4f}): el reason del xfail "
                f"de T2 dice que si pasa, hay que revisarlo"
            )
            assert "vineta" in {hp.label for hp in d.hotspots}, (
                "el caso codificado ya no etiqueta 'vineta': el reason del xfail lo afirma"
            )
            assert d.lut_reproducible == pytest.approx(0.6844404189343802, rel=1e-6), (
                f"lut_reproducible del caso codificado era 0.6844 y ahora es "
                f"{d.lut_reproducible}: el reason del xfail lo cita"
            )


def test_T2_contrapeso_sin_nada_espacial_dice_que_SI_es_un_lut():
    """Un detector que siempre dice "hay algo espacial" es tan inutil como uno
    que nunca lo dice. Esta es la mitad que casi nadie mide."""
    original = E.escena_trabajo()
    d = invertir_grado(original, E.coloreado(original, E.tabla_lut_conocida())).diagnosis
    _informe("T2-contrapeso", lut_reproducible=d.lut_reproducible,
             is_pure_lut=float(d.is_pure_lut), n_hotspots=float(len(d.hotspots)))
    assert d.is_pure_lut, (
        f"dice que hay algo espacial donde solo hay un CDL y un LUT: "
        f"reproducible={d.lut_reproducible:.4f}"
    )
