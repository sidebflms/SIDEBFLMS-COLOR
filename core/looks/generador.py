"""Generador paramétrico de looks: un PowerGrade nuevo a partir de parámetros
con nombre, no de una tabla 3D copiada de otro sitio.

DE DÓNDE SALE LA TÉCNICA
-------------------------
No es una técnica inventada aquí: es la que usan los packs profesionales de
verdad (investigado día 9 — ver `SUPUESTOS.md`, fila I1). Un look serio se
construye como una combinación de unos pocos movimientos, en este orden:

1. Una curva de contraste en forma de S, con un pivote (el punto que no se
   mueve) — lo que le da "carácter" a un stock de película es que la curva
   trabaja distinto en sombras que en luces, no un contraste global plano.
2. Un tinte por zona tonal (sombras / altas luces), pesado por dónde cae cada
   píxel en esa zona — el ejemplo canónico es teal & orange: sombras hacia
   azul-verdoso, luces hacia naranja.
3. Compresión de la croma más alta — la saturación extrema se atenúa un poco,
   como hace un negativo de verdad, para que el look no "grite".
4. Secundarias por ventana de matiz (opcional): tocar un rango de color
   concreto (verdes, azules, naranjas/piel) sin afectar al resto.

CADA PARÁMETRO EN "0" ES UN NO-OP
-----------------------------------
A diferencia de `tests/fuera_de_plano/t5_material.py::tabla_look` (que fija
dos looks concretos con números quemados a mano, para un test), aquí CADA
parámetro por defecto no hace nada — `ParametrosLook()` sin argumentos genera,
bit a bit, la identidad (comprobado en
`tests/test_looks_generador.py::test_parametros_por_defecto_dan_la_identidad`).
Así un preset se lee literalmente como "esto es lo único que cambia", no hay
ningún efecto oculto por defecto que haya que restar mentalmente.

EN QUÉ DOMINIO TRABAJA, Y LA MISMA CAUTELA DE SIEMPRE
--------------------------------------------------------
Igual que el resto de LUTs de este proyecto (`core/reverse`, `core/io`), esto
trabaja directamente sobre los valores de la rejilla del `.cube`, que
representan `core.contracts.WORKING_SPACE` (DaVinci Intermediate,
LOGARÍTMICO, no lineal ni de pantalla) — un look serio se construye en log
(fila I1 de `SUPUESTOS.md`), así que esto está donde tiene que estar. Pero
"luma"/"croma"/"matiz" aquí son una aproximación barata (pesos de Rec.709
aplicados directamente al valor codificado, igual que ya hace
`t5_material.py`), no una medida fotométrica de verdad — la misma cautela que
ya dejó escrita el día 8 sobre saturación en espacio de trabajo
(`core/tutor/NOTAS.md`). Sirve para decidir DÓNDE aplicar un empujón
(sombras/luces/un rango de matiz), no como cifra que se le enseñe a nadie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.contracts import LUT3D
from core.reverse.relleno import rejilla_de_entradas
from core.umbrales import LUT_SIZE_DEFAULT

__all__ = ["ParametrosLook", "VentanaSecundaria", "generar_look"]

#: Mismo criterio que `tests/fuera_de_plano/t5_material.py::_LUMA`: pesos de
#: Rec.709 aplicados directamente al valor codificado (no fotométrico, ver el
#: docstring del módulo). Vector fijo, no es un umbral de calidad — no va en
#: `core/umbrales.py` por el mismo motivo que las constantes de `t5_material.py`
#: no van ahí: es geometría de la técnica, no un criterio de "esto está mal".
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


def _suave(x: np.ndarray, a: float, b: float) -> np.ndarray:
    """Smoothstep entre `a` y `b`. `a == b` da un escalón, no una división por 0."""
    ancho = b - a
    if ancho <= 0.0:
        return (x >= a).astype(np.float64)
    t = np.clip((x - a) / ancho, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class VentanaSecundaria:
    """Un ajuste de color aislado a un rango de matiz — la parte "secundarias"
    de un grade, la que toca "los verdes" o "la piel" sin mover el resto.

    `centro_grados`/`ancho_grados`: en el mismo plano oponente sencillo que
    usa `t5_material.py` (no es un espacio de matiz estándar tipo HSL — ver
    `_matiz_y_peso` más abajo). 0° está en la dirección roja-verde-menos,
    los ángulos se miden igual que `_matiz_y_peso` los calcula: no intentes
    pasar aquí un matiz HSL de una herramienta externa sin comprobarlo primero.
    """

    nombre: str
    centro_grados: float
    ancho_grados: float
    #: Multiplicador de saturación DENTRO de la ventana. 0.0 = sin cambio,
    #: -1.0 = quita toda la saturación de esa ventana, positivo la sube.
    desplazamiento_saturacion: float = 0.0
    #: Empuje aditivo (R, G, B) sobre la diferencia respecto a la luma,
    #: DENTRO de la ventana. Mismo dominio que el resto: valor de rejilla.
    empuje: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ParametrosLook:
    """Todo lo que hace falta para generar un look. Cada valor por defecto es
    un no-op — ver el docstring del módulo."""

    nombre: str = "SIDEB COLOR (look generado)"

    #: Punto de la rejilla que la curva de contraste no mueve.
    pivote_contraste: float = 0.38
    #: Fuerza de la curva en S. 0.0 = sin curva (identidad en este paso).
    fuerza_contraste: float = 0.0

    #: Empuje (R, G, B) en la zona de sombras. (0,0,0) = sin tinte.
    tinte_sombras: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: Dónde empieza/termina la zona de sombras, en luma aproximada (0..1).
    zona_sombras: tuple[float, float] = (0.05, 0.45)

    #: Empuje (R, G, B) en la zona de altas luces. (0,0,0) = sin tinte.
    tinte_luces: tuple[float, float, float] = (0.0, 0.0, 0.0)
    zona_luces: tuple[float, float] = (0.40, 0.85)

    #: 0.0 = sin compresión. 1.0 = la croma alta se aplasta a la luma (gris).
    compresion_croma_alta: float = 0.0
    zona_croma_alta: tuple[float, float] = (0.10, 0.35)

    #: Ajustes por rango de matiz, aplicados DESPUÉS de los pasos globales
    #: de arriba (mismo orden que `t5_material.py::tabla_look`).
    secundarias: tuple[VentanaSecundaria, ...] = field(default_factory=tuple)


def _curva_contraste(rgb: np.ndarray, pivote: float, fuerza: float) -> np.ndarray:
    if fuerza == 0.0:
        return rgb
    x = np.clip(rgb, 0.0, 1.0)
    return pivote + (rgb - pivote) * (1.0 + fuerza * np.sin(np.pi * x))


def _empuje_por_zona(
    rgb: np.ndarray,
    luma: np.ndarray,
    zona: tuple[float, float],
    empuje: tuple[float, float, float],
    *,
    invertido: bool,
) -> np.ndarray:
    """`invertido=False` (luces): 0 por debajo de `zona[0]`, rampa hasta 1 en
    `zona[1]`, 1 por encima — el peso crece con la luma. `invertido=True`
    (sombras): la misma rampa, pero puesta del revés (1 por debajo, 0 por
    encima) — mismo criterio que `t5_material.py::tabla_look`
    (`1.0 - _suave(...)` para sombras, `_suave(...)` tal cual para altas).
    Sin este `invertido`, "zona_sombras" pesaba MÁS cuanto más clara era la
    celda — justo al revés de lo que dice el nombre.

    EL EMPUJE SE ATENÚA ÉL SOLO CERCA DEL TECHO/SUELO, no se suma a pelo y se
    recorta después. Arreglado el día 9 mirando una captura real: el tinte de
    luces desaparecía sin avisar sobre un cielo casi blanco, porque sumar y
    luego recortar a 1.0 borra el empuje justo donde más se nota (highlights
    de verdad). La fórmula (`x + peso·e·(1-x)` subiendo, `x + peso·e·x`
    bajando — la misma aritmética que un blend "screen"/"multiply") dosifica
    el empuje según cuánto margen le queda a CADA píxel en la dirección en
    la que se mueve: pleno en el centro del rango, cada vez menos cerca del
    borde, CERO exacto en el borde — nunca lo tapa un recorte final, y sigue
    siendo cero cuando `empuje` es cero, que es lo que mantiene el "sin
    parámetros da la identidad" de `ParametrosLook()`."""
    if empuje == (0.0, 0.0, 0.0):
        return rgb
    peso = _suave(luma, zona[0], zona[1])
    if invertido:
        peso = 1.0 - peso
    empuje_arr = np.asarray(empuje, dtype=np.float64)
    margen = np.where(empuje_arr > 0.0, 1.0 - rgb, rgb)
    margen = np.clip(margen, 0.0, 1.0)
    return rgb + peso[..., None] * empuje_arr * margen


def _comprimir_croma_alta(
    rgb: np.ndarray, luma: np.ndarray, fuerza: float, zona: tuple[float, float]
) -> np.ndarray:
    if fuerza <= 0.0:
        return rgb
    croma = np.linalg.norm(rgb - luma[..., None], axis=-1)
    peso = _suave(croma, zona[0], zona[1])
    comp = 1.0 - np.clip(fuerza, 0.0, 1.0) * peso
    return luma[..., None] + comp[..., None] * (rgb - luma[..., None])


def _matiz_y_peso(dif: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Plano oponente sencillo sobre `dif` (RGB menos su luma) — el mismo
    truco de `t5_material.py`: no es un espacio de matiz estándar, es barato
    y basta para separar ventanas anchas (verdes/azules/naranjas)."""
    opa = dif[..., 0] - dif[..., 1]
    opb = 0.5 * (dif[..., 0] + dif[..., 1]) - dif[..., 2]
    tono = np.degrees(np.arctan2(opb, opa))
    peso_croma = np.hypot(opa, opb)
    return tono, peso_croma


def _aplicar_secundaria(rgb: np.ndarray, luma: np.ndarray, ventana: VentanaSecundaria) -> np.ndarray:
    dif = rgb - luma[..., None]
    tono, peso_croma = _matiz_y_peso(dif)
    peso_cerca_del_gris = _suave(peso_croma, 0.01, 0.20)
    d = np.abs((tono - ventana.centro_grados + 180.0) % 360.0 - 180.0)
    ancho = max(ventana.ancho_grados, 1e-6)
    dentro = np.where(
        d < ventana.ancho_grados, 0.5 + 0.5 * np.cos(np.pi * d / ancho), 0.0
    ) * peso_cerca_del_gris

    factor_sat = 1.0 + ventana.desplazamiento_saturacion * dentro
    dif = dif * factor_sat[..., None]
    resultado = luma[..., None] + dif

    empuje_arr = np.asarray(ventana.empuje, dtype=np.float64)
    if (empuje_arr != 0.0).any():
        # Mismo criterio de margen que `_empuje_por_zona`: el empuje de una
        # secundaria (por ejemplo, calentar la piel) también puede caer cerca
        # del techo/suelo -- sin esto se recortaría en silencio igual que le
        # pasaba al tinte de luces/sombras antes del día 9.
        margen = np.where(empuje_arr > 0.0, 1.0 - resultado, resultado)
        margen = np.clip(margen, 0.0, 1.0)
        resultado = resultado + dentro[..., None] * empuje_arr * margen
    return resultado


def generar_look(parametros: ParametrosLook, *, n: int = LUT_SIZE_DEFAULT) -> LUT3D:
    """`ParametrosLook` -> `LUT3D`, lista para escribir con
    `core.io.cube.escribir_cube` o para meter en la biblioteca.

    Determinista: los mismos parámetros dan, bit a bit, el mismo LUT.
    """
    entradas = rejilla_de_entradas(n)
    out = _curva_contraste(entradas, parametros.pivote_contraste, parametros.fuerza_contraste)

    luma = out @ _LUMA
    out = _empuje_por_zona(
        out, luma, parametros.zona_sombras, parametros.tinte_sombras, invertido=True
    )
    luma = out @ _LUMA
    out = _empuje_por_zona(
        out, luma, parametros.zona_luces, parametros.tinte_luces, invertido=False
    )

    luma = out @ _LUMA
    out = _comprimir_croma_alta(out, luma, parametros.compresion_croma_alta, parametros.zona_croma_alta)

    for ventana in parametros.secundarias:
        luma = out @ _LUMA
        out = _aplicar_secundaria(out, luma, ventana)

    tabla = np.clip(out, 0.0, 1.0).astype(np.float32)
    return LUT3D(table=tabla, title=parametros.nombre)
