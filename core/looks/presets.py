"""Semilla de `ParametrosLook` con nombre — el punto de partida de la
librería generada, no un catálogo cerrado.

TODOS LOS NÚMEROS DE AQUÍ SON HECHOS A MANO, NO MEDIDOS
----------------------------------------------------------
Ver `SUPUESTOS.md`, fila I2. La primera versión (día 9) partió del mismo
orden de magnitud que `tests/fuera_de_plano/t5_material.py::tabla_look` para
no inventar una escala sin ningún punto de referencia. Tras mirar capturas
reales de esa primera versión (rostro y cielo, día 9) se subieron las
magnitudes ~2-3x — se veían demasiado sutiles — y se reforzó en concreto el
empuje cálido de la ventana de piel de `teal_naranja_clasico`, que era el
efecto de firma del estilo y apenas se notaba. Nada de esto convierte a estos
presets en "el look correcto": siguen siendo un punto de partida a ojo,
esperando que alguien con criterio de colorista (Mario) los mire de verdad
sobre un plano real y diga qué cambiar.
"""

from __future__ import annotations

from core.looks.generador import ParametrosLook, VentanaSecundaria

__all__ = ["PRESETS"]

_TEAL_NARANJA = ParametrosLook(
    nombre="SIDEB COLOR — Teal & Naranja clásico",
    pivote_contraste=0.38,
    fuerza_contraste=0.15,
    tinte_sombras=(0.0, 0.045, 0.08),
    zona_sombras=(0.05, 0.45),
    tinte_luces=(0.07, 0.015, -0.05),
    zona_luces=(0.40, 0.85),
    compresion_croma_alta=0.35,
    zona_croma_alta=(0.10, 0.35),
    secundarias=(
        # La piel/naranjas es el efecto de firma de este estilo: además de
        # subir su saturación, se le da un empuje cálido propio (no basta
        # con el tinte_luces global) — es el ajuste que pedimos reforzar
        # tras mirar las capturas del día 9 (apenas se notaba en piel).
        VentanaSecundaria(
            nombre="piel/naranjas",
            centro_grados=45.0,
            ancho_grados=55.0,
            desplazamiento_saturacion=0.45,
            empuje=(0.035, 0.010, -0.025),
        ),
        VentanaSecundaria(
            nombre="verdes hacia amarillo",
            centro_grados=150.0,
            ancho_grados=70.0,
            desplazamiento_saturacion=-0.45,
            empuje=(0.045, 0.0, -0.018),
        ),
        VentanaSecundaria(
            nombre="azules hacia cian",
            centro_grados=-60.0,
            ancho_grados=65.0,
            empuje=(-0.015, 0.04, 0.0),
        ),
    ),
)

_CALIDO_SUELO_ALTO = ParametrosLook(
    nombre="SIDEB COLOR — Cálido, suelo alto",
    pivote_contraste=0.30,
    fuerza_contraste=0.06,
    tinte_sombras=(0.033, 0.018, -0.009),
    zona_sombras=(0.0, 0.35),
    tinte_luces=(0.021, 0.012, -0.006),
    zona_luces=(0.55, 0.95),
    compresion_croma_alta=0.20,
    zona_croma_alta=(0.15, 0.40),
    secundarias=(
        VentanaSecundaria(
            nombre="piel",
            centro_grados=45.0,
            ancho_grados=45.0,
            desplazamiento_saturacion=0.14,
        ),
    ),
)

_FRIO_CONTRASTADO = ParametrosLook(
    nombre="SIDEB COLOR — Frío, contraste duro",
    pivote_contraste=0.45,
    fuerza_contraste=0.22,
    tinte_sombras=(-0.025, 0.015, 0.065),
    zona_sombras=(0.05, 0.40),
    tinte_luces=(-0.015, 0.010, 0.025),
    zona_luces=(0.50, 0.90),
    compresion_croma_alta=0.18,
    zona_croma_alta=(0.10, 0.30),
    secundarias=(),
)

#: `id` en minúsculas y sin espacios, para poder usarlo como clave de
#: `lut_rel_path` o de una fila de biblioteca sin volver a decidir un slug.
PRESETS: dict[str, ParametrosLook] = {
    "teal_naranja_clasico": _TEAL_NARANJA,
    "calido_suelo_alto": _CALIDO_SUELO_ALTO,
    "frio_contrastado": _FRIO_CONTRASTADO,
}
