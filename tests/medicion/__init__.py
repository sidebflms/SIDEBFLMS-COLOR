"""Arnes de MEDICION INDEPENDIENTE de SIDEBFLMS COLOR.

Propiedad del medidor independiente. Nada de aqui es codigo de produccion y
nada de aqui lo importa `core/`, `gui/` ni `probe/`.

Reglas del encargo, y por que estan:

1. **Material propio.** No se importa `tests/media/generate`, ni
   `tests/conftest`, ni `tests/test_entregables`. La escena, el CDL conocido,
   el LUT conocido, la vineta, la ventana y los tres LUT malos se fabrican
   aqui.
2. **Metrica de fuera.** El ΔE2000 sale de `colour-science`
   (`colour.difference.delta_E_CIE2000`), y el puente de espacios
   DWG/DaVinci Intermediate -> XYZ -> CIE L*a*b* tambien
   (`colour.models.oetf_inverse_DaVinciIntermediate`, `colour.RGB_to_XYZ`,
   `colour.XYZ_to_Lab`). En ningun sitio se llama a `core.color`, salvo en las
   comparaciones que existen precisamente para medir si los dos caminos
   coinciden, y esas estan marcadas como tales.
3. **Solo API publica.** Se entra por `invertir_grado`, `emparejar`, `qc_lut`,
   `escribir_cube` y `leer_cube`, mas las dataclases congeladas de
   `core.contracts` (que son el tipo de retorno, no hay forma de evitarlas).
4. **Semillas fijas.** Todo lo aleatorio sale de un `numpy.random.default_rng`
   con semilla escrita en el codigo.
"""
