"""Semilla de `ParametrosLook` con nombre — el punto de partida de la
librería generada, no un catálogo cerrado.

TODOS LOS NÚMEROS DE AQUÍ SON HECHOS A MANO, NO MEDIDOS
----------------------------------------------------------
Ver `SUPUESTOS.md`, fila I2. Están dentro del mismo orden de magnitud que usa
`tests/fuera_de_plano/t5_material.py::tabla_look` (que sí se ha mirado con
capturas reales, aunque para looks sintéticos de test, no de producción) para
no inventar una escala nueva sin ningún punto de referencia — pero eso no los
convierte en "el look correcto de teal & orange": son un punto de partida
razonable a ojo, esperando que alguien con criterio de colorista (Mario) los
mire de verdad y diga qué cambiar. Ninguno se ha visto todavía sobre un plano
real.
"""

from __future__ import annotations

from core.looks.generador import ParametrosLook, VentanaSecundaria

__all__ = ["PRESETS"]

_TEAL_NARANJA = ParametrosLook(
    nombre="SIDEB COLOR — Teal & Naranja clásico",
    pivote_contraste=0.38,
    fuerza_contraste=0.06,
    tinte_sombras=(0.0, 0.018, 0.032),
    zona_sombras=(0.05, 0.45),
    tinte_luces=(0.028, 0.006, -0.020),
    zona_luces=(0.40, 0.85),
    compresion_croma_alta=0.22,
    zona_croma_alta=(0.10, 0.35),
    secundarias=(
        VentanaSecundaria(
            nombre="piel/naranjas",
            centro_grados=45.0,
            ancho_grados=55.0,
            desplazamiento_saturacion=0.12,
        ),
        VentanaSecundaria(
            nombre="verdes hacia amarillo",
            centro_grados=150.0,
            ancho_grados=70.0,
            desplazamiento_saturacion=-0.25,
            empuje=(0.020, 0.0, -0.008),
        ),
        VentanaSecundaria(
            nombre="azules hacia cian",
            centro_grados=-60.0,
            ancho_grados=65.0,
            empuje=(-0.006, 0.016, 0.0),
        ),
    ),
)

_CALIDO_SUELO_ALTO = ParametrosLook(
    nombre="SIDEB COLOR — Cálido, suelo alto",
    pivote_contraste=0.30,
    fuerza_contraste=0.04,
    tinte_sombras=(0.022, 0.012, -0.006),
    zona_sombras=(0.0, 0.35),
    tinte_luces=(0.014, 0.008, -0.004),
    zona_luces=(0.55, 0.95),
    compresion_croma_alta=0.15,
    zona_croma_alta=(0.15, 0.40),
    secundarias=(
        VentanaSecundaria(
            nombre="piel",
            centro_grados=45.0,
            ancho_grados=45.0,
            desplazamiento_saturacion=0.08,
        ),
    ),
)

_FRIO_CONTRASTADO = ParametrosLook(
    nombre="SIDEB COLOR — Frío, contraste duro",
    pivote_contraste=0.45,
    fuerza_contraste=0.14,
    tinte_sombras=(-0.010, 0.006, 0.026),
    zona_sombras=(0.05, 0.40),
    tinte_luces=(-0.006, 0.004, 0.010),
    zona_luces=(0.50, 0.90),
    compresion_croma_alta=0.10,
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
