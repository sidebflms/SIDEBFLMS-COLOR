"""T4 (QC de LUT), medido de fuera.

Los tres LUT malos los fabrico yo en `tests/medicion/escena.py`. NO se usa
`core.io.catalogo_luts_malos` ni ninguno de sus generadores: probar el QC con
los LUT que su propio autor diseño para que los cazara no prueba gran cosa.

LA TRAMPA DEL NO MONOTONO
-------------------------
Con tamaño 33 el paso de rejilla es 1/32 = 0.03125. Un retroceso menor que el
paso NO invierte nada: la celda 10 con 0.28125 + 0.03125 - 0.02 = 0.2925 sigue
por encima de la celda 9 (0.28125). Mi LUT copia el valor de la celda anterior
y le resta 0.05, que es mayor que el paso. Ahí cayó alguien antes; queda
comprobado abajo con una aserción explícita sobre la tabla, para que si alguien
toca mi generador se entere.

Escrituras: sólo en `tmp_path` de pytest.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import LUT3D
from core.io import (
    CODIGO_BANDING,
    CODIGO_GAMUT,
    CODIGO_NO_MONOTONIA,
    escribir_cube,
    leer_cube,
    qc_lut,
)
from tests.medicion import escena as E

pytestmark = pytest.mark.medicion


def _informe(nombre: str, **cifras) -> None:
    linea = "  ".join(f"{k}={v}" for k, v in cifras.items())
    print(f"\n[MEDICION {nombre}] {linea}")


def _lut(tabla: np.ndarray, titulo: str) -> LUT3D:
    return LUT3D(table=np.asarray(tabla, dtype=np.float32), title=titulo)


def test_T4_mi_lut_no_monotono_lo_es_de_verdad():
    """Antes de acusar al QC de no cazarlo, compruebo que mi LUT esta roto."""
    t = E.lut_no_monotono(33)
    retroceso = float(t[9, 0, 0, 0] - t[10, 0, 0, 0])
    paso = 1.0 / 32.0
    _informe("T4-trampa", retroceso=round(retroceso, 6), paso_de_rejilla=round(paso, 6))
    assert retroceso > paso, (
        f"mi LUT 'no monotono' retrocede {retroceso:.5f}, que no llega al paso de rejilla "
        f"{paso:.5f}: no invierte nada y el QC tendria razon en no avisar"
    )


def test_T4_la_identidad_pasa_limpia_en_17_33_y_65():
    """El test mas importante del QC: si da falsos positivos sobre la
    identidad, no se fia nadie de el."""
    for size in (17, 33, 65):
        informe = qc_lut(_lut(E.tabla_identidad(size), f"identidad {size}"))
        _informe(f"T4-identidad-{size}", avisos=len(informe.problemas),
                 ok=informe.ok, codigos=sorted(set(informe.codigos())))
        assert informe.ok, f"la identidad de {size} saca avisos: {informe.resumen()}"


def test_T4_caza_los_tres_luts_malos_cada_uno_por_su_nombre():
    """El criterio del encargo, tal cual: los tres, y cada uno con su codigo."""
    casos = (
        ("no monotono", E.lut_no_monotono(33), CODIGO_NO_MONOTONIA),
        ("banding", E.lut_con_banding(33), CODIGO_BANDING),
        ("fuera de gamut", E.lut_fuera_de_gamut(33), CODIGO_GAMUT),
    )
    cazados = 0
    for nombre, tabla, codigo in casos:
        informe = qc_lut(_lut(tabla, nombre))
        codigos = sorted(set(informe.codigos()))
        con_celda = any(p.celda is not None for p in informe.por_codigo(codigo))
        _informe(f"T4-{nombre}", avisos=len(informe.problemas), codigos=codigos,
                 dice_donde=con_celda)
        assert codigo in codigos, f"el QC no caza '{nombre}': {informe.resumen()}"
        cazados += 1
    _informe("T4", cazados=f"{cazados}/3")
    assert cazados == 3


def test_T4_el_no_monotono_dice_DONDE():
    """"Hay no monotonia" sin celda no le sirve a la GUI ni a Mario."""
    informe = qc_lut(_lut(E.lut_no_monotono(33), "no monotono"))
    problemas = informe.por_codigo(CODIGO_NO_MONOTONIA)
    celdas = [p.celda for p in problemas if p.celda is not None]
    _informe("T4-no-monotono-donde", n=len(problemas), primeras_celdas=celdas[:3])
    assert celdas, "caza la no monotonia pero no dice en que celda"
    # La rotura esta en el eje 0 (ROJO) ENTRE las celdas 9 y 10: el valor de la
    # 10 es el de la 9 menos 0.05. El QC señala la celda 9, o sea el borde
    # desde el que se retrocede. Es una convencion tan valida como señalar la
    # 10 (y para la GUI hasta mejor: es la ultima que todavia iba bien), asi
    # que se aceptan las dos. MEDIDO: señala la 9.
    assert any(c[0] in (9, 10) for c in celdas), (
        f"señala celdas que no tienen nada que ver con la rota: {celdas[:5]}"
    )


def test_T4_un_lut_malo_sigue_siendo_malo_despues_de_pasar_por_el_fichero(tmp_path):
    """Si escribir y releer 'arregla' un LUT roto, uno de los dos miente."""
    for nombre, tabla, codigo in (
        ("no_monotono", E.lut_no_monotono(33), CODIGO_NO_MONOTONIA),
        ("banding", E.lut_con_banding(33), CODIGO_BANDING),
        ("gamut", E.lut_fuera_de_gamut(33), CODIGO_GAMUT),
    ):
        ruta = escribir_cube(_lut(tabla, nombre), tmp_path / f"{nombre}.cube")
        releido = leer_cube(ruta)
        codigos = sorted(set(qc_lut(releido).codigos()))
        _informe(f"T4-ida-y-vuelta-{nombre}", codigos=codigos)
        assert codigo in codigos, f"pasar por el .cube ha 'arreglado' el LUT {nombre}"


def test_T4_la_identidad_sobrevive_al_fichero_en_17_33_y_65(tmp_path):
    """Y sigue pasando limpia al otro lado."""
    for size in (17, 33, 65):
        ruta = escribir_cube(_lut(E.tabla_identidad(size), f"id{size}"), tmp_path / f"id{size}.cube")
        releido = leer_cube(ruta)
        error = float(np.abs(releido.table - E.tabla_identidad(size)).max())
        informe = qc_lut(releido)
        _informe(f"T4-identidad-fichero-{size}", error_max=error, ok=informe.ok,
                 avisos=len(informe.problemas))
        assert releido.size == size
        assert error < 1e-5, f"la identidad de {size} no sobrevive al fichero: {error:.2e}"
        assert informe.ok, f"la identidad de {size} releida saca avisos: {informe.resumen()}"
