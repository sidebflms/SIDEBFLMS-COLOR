"""Cuanto nos fiamos de un emparejamiento, y por que.

QUE MIDE
--------
Seis cosas bajan la confianza de verdad, y son seis cosas distintas:

| metrica                | que pregunta                                               |
|------------------------|------------------------------------------------------------|
| `n_muestras`           | ¿hay pixeles suficientes para que la estadistica signifique algo? |
| `solape`               | ¿las dos nubes de color se pisan, o son dos mundos aparte? |
| `condicion`            | ¿la nube del origen es un volumen o casi un plano/una recta? |
| `residuo_de`           | ¿lo que devuelvo reproduce de verdad la correccion o se queda corto? |
| `extrapolacion`        | ¿cuanto de la referencia cae fuera de lo que el origen ha visto? |
| `ganancia`             | ¿la correccion estira el color una barbaridad? |
| `fraccion_no_finita`   | ¿cuantos pixeles venian rotos? |

Y aparte, `desajuste` (booleano), que no es una medida de calidad del ajuste
sino de si la pregunta tenia sentido. Por eso multiplica en vez de promediar.

LA FORMULA, EXACTA
------------------
Cada metrica se convierte en una **subnota** en 0..1 con una rampa lineal entre
un valor "bien" (subnota 1) y un valor "mal" (subnota 0). Las constantes estan
abajo, con nombre, y son lo unico que hay que tocar si un dia la nota no cuadra
con lo que ve el ojo.

Luego, sobre las subnotas que de verdad se han pasado (las que faltan no cuentan
ni a favor ni en contra):

    nota = sqrt( min(subnotas) * media_geometrica(subnotas) ) * pena_desajuste

La media geometrica sola es demasiado indulgente: seis subnotas perfectas y una
de 0.30 dan 0.84, o sea "alta", y eso es mentira. El minimo solo es demasiado
severo: una sola pega convierte en "baja" un ajuste por lo demas impecable. La
media geometrica de los dos (que es lo que hace la raiz del producto) da 0.50 en
ese ejemplo, o sea "media", que es exactamente lo que hay que enseñar.

`pena_desajuste` vale 1 si las escenas son comparables y `PENA_DESAJUSTE` (0.35)
si no. Multiplicativa a proposito: un desajuste de contenido **no** se compensa
con un ajuste numericamente bueno; de hecho cuanto mejor sale el numero, mas
peligroso es.

`level` NO se calcula aqui: sale de `confidence_level()` de `core.contracts`,
que es el unico sitio de la app donde un numero se convierte en alta/media/baja.

CLAVES ACEPTADAS
----------------
`puntuar_confianza` es estricto: una clave que no conozca **lanza `TypeError`**.
Es a proposito. Esta funcion la llaman varios modulos y un `residuos=` en vez de
`residuo_de=` no puede salir como una nota silenciosamente optimista; tiene que
salir como un error que se ve a la primera.
"""

from __future__ import annotations

import numpy as np

from core.contracts import Confidence, confidence_level

__all__ = ["METRICAS_ACEPTADAS", "PENA_DESAJUSTE", "UMBRALES", "puntuar_confianza"]

#: Los dos extremos de cada rampa: (valor con subnota 1, valor con subnota 0).
UMBRALES: dict[str, tuple[float, float]] = {
    # Muestras: la rampa va en log10. 24 pixeles no es nada; 20.000 ya es de
    # sobra para diez parametros.
    "n_muestras": (20000.0, 24.0),
    # Solape de los histogramas reales DESPUES del transporte (ver
    # `solape_de_distribuciones`). Medido: el mismo plano a otra exposicion da
    # 0.99, el mismo decorado con otra persona 0.78-0.92, medio fotograma 0.88,
    # y un exterior contra un retrato 0.45. El corte va entre medias.
    "solape": (0.90, 0.40),
    # Condicion de la covarianza del origen, en log10. Medido sobre el material
    # del generador: un retrato de estudio da 1.1e3, un exterior 1.3e3, una
    # carta de color 77 y un campo de ruido 5. O sea que 1e3 NO es una nube
    # degenerada, es una escena normal: en una imagen de verdad la variacion de
    # luma es mil veces la de croma y eso no tiene nada de malo. El corte esta
    # donde deja de haber informacion: un degradado de un solo tono da 1.1e10 y
    # una rampa de gris (rango 1 de verdad) 1e299.
    "condicion": (1e5, 1e10),
    # Residuo del ajuste en ΔE2000 medio. 1.0 es el umbral clasico de "no se
    # distingue"; 8.0 es un error que se ve desde la puerta.
    "residuo_de": (1.0, 8.0),
    # Fraccion de la referencia fuera del rango observado en el origen.
    "extrapolacion": (0.02, 0.40),
    # Estirado maximo de la matriz de transporte.
    "ganancia": (4.0, 100.0),
    # Fraccion de pixeles que venian con NaN o infinito.
    "fraccion_no_finita": (0.0, 0.25),
}

#: Cuanto multiplica un desajuste de contenido. Ver el docstring.
PENA_DESAJUSTE: float = 0.35

METRICAS_ACEPTADAS: tuple[str, ...] = (
    *UMBRALES.keys(),
    "desajuste",
    "distancia_contenido",
)


def _rampa(valor: float, bien: float, mal: float, *, log: bool = False) -> float:
    """Subnota 0..1: 1 en `bien`, 0 en `mal`, lineal en medio."""
    v = float(valor)
    if not np.isfinite(v):
        return 0.0
    if log:
        v = np.log10(max(v, 1e-12))
        bien = np.log10(max(bien, 1e-12))
        mal = np.log10(max(mal, 1e-12))
    if bien == mal:
        return 1.0 if v == bien else 0.0
    return float(np.clip((v - mal) / (bien - mal), 0.0, 1.0))


def puntuar_confianza(**metricas: float) -> Confidence:
    """Convierte un puñado de metricas crudas en un `Confidence`.

    Todas las claves son opcionales; las que no se pasan no cuentan. Las claves
    aceptadas son las de `METRICAS_ACEPTADAS`; cualquier otra lanza `TypeError`.

        n_muestras          int, el MENOR de los dos recuentos
        solape              0..1, coeficiente de Bhattacharyya
        condicion           >= 1, numero de condicion de la covarianza de origen
        residuo_de          ΔE2000 medio que queda tras aplicar la correccion
        extrapolacion       0..1, fraccion de la referencia fuera de rango
        ganancia            estirado maximo de la matriz de transporte
        fraccion_no_finita  0..1, pixeles descartados por NaN/inf
        desajuste           bool, de `desajuste_de_contenido`
        distancia_contenido float, informativa (va a `metrics`, no puntua)
    """
    desconocidas = sorted(set(metricas) - set(METRICAS_ACEPTADAS))
    if desconocidas:
        raise TypeError(
            f"puntuar_confianza: no conozco {desconocidas}. "
            f"Las claves validas son {sorted(METRICAS_ACEPTADAS)}"
        )

    crudas: dict[str, float] = {}
    subnotas: dict[str, float] = {}

    if "n_muestras" in metricas:
        n = float(metricas["n_muestras"])
        crudas["n_muestras"] = n
        subnotas["n_muestras"] = _rampa(n, *UMBRALES["n_muestras"], log=True)
    if "solape" in metricas:
        s = float(metricas["solape"])
        crudas["solape"] = s
        subnotas["solape"] = _rampa(s, *UMBRALES["solape"])
    if "condicion" in metricas:
        c = float(metricas["condicion"])
        crudas["condicion"] = c
        subnotas["condicion"] = _rampa(max(c, 1.0), *UMBRALES["condicion"], log=True)
    if "residuo_de" in metricas:
        r = float(metricas["residuo_de"])
        crudas["residuo_de"] = r
        subnotas["residuo_de"] = _rampa(r, *UMBRALES["residuo_de"])
    if "extrapolacion" in metricas:
        e = float(metricas["extrapolacion"])
        crudas["extrapolacion"] = e
        subnotas["extrapolacion"] = _rampa(e, *UMBRALES["extrapolacion"])
    if "ganancia" in metricas:
        g = float(metricas["ganancia"])
        crudas["ganancia"] = g
        subnotas["ganancia"] = _rampa(max(g, 1.0), *UMBRALES["ganancia"], log=True)
    if "fraccion_no_finita" in metricas:
        f = float(metricas["fraccion_no_finita"])
        crudas["fraccion_no_finita"] = f
        subnotas["fraccion_no_finita"] = _rampa(f, *UMBRALES["fraccion_no_finita"])

    desajuste = bool(metricas.get("desajuste", False))
    if "distancia_contenido" in metricas:
        crudas["distancia_contenido"] = float(metricas["distancia_contenido"])
    crudas["desajuste"] = 1.0 if desajuste else 0.0

    if subnotas:
        valores = np.array(list(subnotas.values()), dtype=np.float64)
        minimo = float(valores.min())
        geometrica = float(np.exp(np.mean(np.log(np.maximum(valores, 1e-12)))))
        nota = float(np.sqrt(minimo * geometrica))
    else:
        # Sin ninguna metrica no hay nada que puntuar. 0.5 y se dice por que.
        nota = 0.5
    if desajuste:
        nota *= PENA_DESAJUSTE
    nota = float(np.clip(nota, 0.0, 1.0))

    crudas.update({f"subnota_{k}": float(v) for k, v in subnotas.items()})
    crudas["nota"] = nota

    return Confidence(
        score=nota,
        level=confidence_level(nota),
        reasons=_razones(subnotas, crudas, desajuste),
        metrics=crudas,
    )


def _razones(
    subnotas: dict[str, float], crudas: dict[str, float], desajuste: bool
) -> tuple[str, ...]:
    """Frases en castellano, ordenadas de la pega mas grave a la mas leve.

    Van tal cual a la pantalla que mira Mario, asi que dicen QUE pasa y POR QUE
    importa, no el nombre de la variable.
    """
    fuera: list[str] = []
    if desajuste:
        fuera.append(
            "Los dos planos no parecen la misma escena. Aunque el numero salga "
            "bien, esto no es un igualado: revisalo con los ojos antes de usarlo."
        )

    frases: dict[str, str] = {}
    if "n_muestras" in subnotas:
        frases["n_muestras"] = (
            f"Hay pocos pixeles analizados ({crudas['n_muestras']:.0f}): con tan "
            "poca muestra la estadistica es fragil y el resultado puede cambiar "
            "mucho de un fotograma a otro."
        )
    if "solape" in subnotas:
        frases["solape"] = (
            "Aun despues de corregirlo, el plano y la referencia no tienen el "
            f"mismo reparto de color (solape {crudas['solape']:.0%}): se les puede "
            "igualar la media, pero no van a acabar de parecerse."
        )
    if "condicion" in subnotas:
        frases["condicion"] = (
            "La nube de color del plano es casi plana "
            f"(condicion {crudas['condicion']:.0e}): hay una direccion del color "
            "en la que no hay variacion que medir, y lo que se haga ahi es "
            "invencion."
        )
    if "residuo_de" in subnotas:
        frases["residuo_de"] = (
            f"La correccion no llega del todo: quedan {crudas['residuo_de']:.1f} "
            "de ΔE2000 respecto a lo que haria falta. Por encima de 2 ya se nota "
            "a ojo en una cara."
        )
    if "extrapolacion" in subnotas:
        frases["extrapolacion"] = (
            f"Un {crudas['extrapolacion']:.0%} de la referencia cae fuera del "
            "rango de color que tiene el plano: ahi se esta extrapolando, no "
            "igualando."
        )
    if "ganancia" in subnotas:
        frases["ganancia"] = (
            f"La correccion estira el color hasta {crudas['ganancia']:.0f}x en "
            "alguna direccion. Eso casi siempre significa que al material no le "
            "queda esa informacion y lo que va a salir es ruido de color."
        )
    if "fraccion_no_finita" in subnotas:
        frases["fraccion_no_finita"] = (
            f"Un {crudas['fraccion_no_finita']:.1%} de los pixeles no eran "
            "numeros validos y se han descartado. Mira el fichero de origen."
        )

    for clave, _ in sorted(subnotas.items(), key=lambda par: par[1]):
        if subnotas[clave] < 0.85 and clave in frases:
            fuera.append(frases[clave])

    if not fuera:
        if not subnotas:
            fuera.append(
                "No se ha medido nada con que puntuar este resultado; la nota es "
                "un valor por defecto, no una medida."
            )
        else:
            fuera.append(
                "Las dos distribuciones se solapan bien y la correccion las deja "
                "practicamente encima: no hay nada que objetar."
            )
    return tuple(fuera)
