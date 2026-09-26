"""Aplicar un `core.perfiles.PerfilTrabajo` a un `EstadoDemo` ya construido
(día 9, continuación 10): el "un botón" que pidió Mario — detectar la
cámara de cada clip, hornear su LUT (ajuste conocido de esa cámara + look
compartido del trabajo), desplegarlo de verdad en la carpeta de LUTs de
Resolve, y dejar cada `ClipDemo` apuntando a su propio `look_rel`.

Por qué esto SÍ escribe en disco, y por qué no es `core/`
------------------------------------------------------------
`aplicar_grado_seguro`/`SetLUT` sólo aceptan una ruta RELATIVA a la carpeta
de LUTs de Resolve — el fichero tiene que existir DE VERDAD ahí para que el
nodo de look se vea. `core.perfiles.lut_para_camara` calcula la tabla; esta
función es la que la escribe donde Resolve la va a buscar
(`puente.project_info().lut_dir`, no una ruta inventada) — por eso vive en
`gui/`, como `gui/estado_real.py`: toca disco y habla con el puente, no es
lógica pura.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.io.cube import escribir_cube
from core.perfiles import PerfilTrabajo, camara_para_clip, lut_para_camara
from gui.datos_demo import EstadoDemo

__all__ = ["aplicar_perfil_a_estado"]

#: Dónde, dentro de la carpeta de LUTs de Resolve, viven los LUTs horneados
#: de los perfiles de trabajo — junto a `SIDEB/` (el look compartido de
#: siempre, `gui.datos_demo.LOOK_REL`), no mezclados con LUTs de terceros.
_SUBCARPETA = "SIDEB/perfiles"


def _slug(texto: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return s or "camara"


def aplicar_perfil_a_estado(estado: EstadoDemo, perfil: PerfilTrabajo) -> EstadoDemo:
    """Identifica la cámara de cada clip de `estado` según `perfil`, hornea
    y despliega el LUT que le corresponde, y deja cada `ClipDemo.look_rel`
    puesto.

    **Muta `estado` y sus clips EN EL SITIO, a propósito, y devuelve el
    mismo objeto** — no una copia. `VentanaPrincipal` reparte el mismo
    `EstadoDemo` (y los mismos `ClipDemo`) entre varias pantallas
    (`PantallaClips`, `PantallaComparar`, `PantallaAplicar`); si esta función
    devolviera copias nuevas (`dataclasses.replace`), sólo la pantalla que
    llama a esto vería el `look_rel` puesto — las demás seguirían mirando
    los objetos viejos, sin enterarse. Mutar en el sitio es lo que mantiene
    a todas las pantallas de acuerdo, igual que ya pasa con el resto de
    campos de `EstadoDemo`.

    El LUT de cada cámara distinta del perfil se hornea y se escribe UNA
    sola vez (cacheado dentro de esta llamada), no una vez por clip — un
    perfil típico tiene pocas cámaras y muchos clips de cada una.

    Un clip cuya cámara no reconoce ninguna `PerfilCamara` de `perfil` se
    queda con `look_rel=None`: usa el look compartido de siempre
    (`estado.look_rel`), sin ningún ajuste de cámara horneado.
    """
    lut_dir = Path(estado.puente.project_info().lut_dir)
    perfil_slug = _slug(perfil.nombre)
    rutas_por_camara: dict[str, str | None] = {}

    for clip in estado.clips:
        camara = camara_para_clip(perfil, clip.ref)
        clave = camara.nombre_legible or camara.fabricante_contiene if camara is not None else ""

        if clave not in rutas_por_camara:
            lut = lut_para_camara(perfil, camara)
            if lut is None:
                rutas_por_camara[clave] = None
            else:
                nombre_fichero = f"{_slug(clave) if clave else 'sin-camara'}.cube"
                ruta_relativa = f"{_SUBCARPETA}/{perfil_slug}/{nombre_fichero}"
                escribir_cube(lut, lut_dir / ruta_relativa, crear_directorios=True)
                rutas_por_camara[clave] = ruta_relativa

        clip.look_rel = rutas_por_camara[clave]

    return estado
