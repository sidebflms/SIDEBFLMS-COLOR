"""`gui.despliegue_presets.desplegar_preset_elegido` (día 9, continuación 12):
el punto 2 de la lista de Mario — conectar el preset que se elige en el
selector de modo fácil con el fichero real que Resolve necesita.

**CUIDADO DELIBERADO CON `lut_dir`**: igual que en `test_gui_perfiles_trabajo.py`,
todos los `FakeResolve` de aquí se construyen con
`incognitas=Incognitas(instalacion="mac_app_store")` y `home=tmp_path`, para
que la carpeta de LUTs "de Resolve" caiga dentro de `tmp_path` — nunca en la
carpeta real del sistema.
"""

from __future__ import annotations

from pathlib import Path

from core.contracts import CDL, LUT3D, ClipRef, Confidence, MatchResult
from core.io.biblioteca import Preset
from core.io.cube import leer_cube
from core.resolve import FakeResolve
from core.resolve.incognitas import Incognitas, lut_dir
from gui.datos_demo import ClipDemo, EstadoDemo
from gui.despliegue_presets import desplegar_preset_elegido


def _match_identidad() -> MatchResult:
    return MatchResult(
        cdl=CDL(), lut=None, confidence=Confidence(score=1.0, level="alta", reasons=(), metrics={}),
        delta_e_before=0.0, delta_e_after=0.0, content_mismatch=False,
    )


def _clip(clip_id: str) -> ClipDemo:
    ref = ClipRef(clip_id=clip_id, name=clip_id, track=1, index=1, start_frame=0, end_frame=99)
    return ClipDemo(ref=ref, match=_match_identidad())


def _estado_sandbox(tmp_path: Path) -> EstadoDemo:
    clips = [_clip("c1")]
    incognitas = Incognitas(instalacion="mac_app_store")
    puente = FakeResolve(clips=[c.ref for c in clips], incognitas=incognitas, home=str(tmp_path))
    return EstadoDemo(clips=clips, puente=puente)


def _lut_dir_de_prueba(tmp_path: Path) -> Path:
    return Path(lut_dir(Incognitas(instalacion="mac_app_store"), home=str(tmp_path)))


def _preset(nombre: str = "Look Uno") -> Preset:
    return Preset(id="look-uno", nombre=nombre, tamano_rejilla=3, ruta_origen="/no/existe.cube")


def test_escribe_el_cube_dentro_del_sandbox_y_no_en_el_sistema(tmp_path: Path):
    estado = _estado_sandbox(tmp_path)
    look = LUT3D.identity(3)

    ruta_relativa = desplegar_preset_elegido(estado, preset=_preset(), look=look)

    ruta_absoluta = _lut_dir_de_prueba(tmp_path) / ruta_relativa
    assert ruta_absoluta.is_file()
    assert ruta_relativa.startswith("SIDEB/presets/")


def test_deja_estado_look_rel_apuntando_al_fichero_escrito(tmp_path: Path):
    estado = _estado_sandbox(tmp_path)
    look = LUT3D.identity(3)

    ruta_relativa = desplegar_preset_elegido(estado, preset=_preset(), look=look)

    assert estado.look_rel == ruta_relativa
    assert estado.look is look


def test_el_cube_escrito_se_puede_releer(tmp_path: Path):
    estado = _estado_sandbox(tmp_path)
    look = LUT3D.identity(3)

    ruta_relativa = desplegar_preset_elegido(estado, preset=_preset(), look=look)

    releido = leer_cube(_lut_dir_de_prueba(tmp_path) / ruta_relativa)
    assert releido.table.shape == look.table.shape


def test_presets_distintos_van_a_ficheros_distintos(tmp_path: Path):
    estado = _estado_sandbox(tmp_path)
    look = LUT3D.identity(3)

    ruta_uno = desplegar_preset_elegido(estado, preset=_preset("Look Uno"), look=look)
    ruta_dos = desplegar_preset_elegido(
        estado,
        preset=Preset(id="look-dos", nombre="Look Dos", tamano_rejilla=3, ruta_origen="/no/existe.cube"),
        look=look,
    )

    assert ruta_uno != ruta_dos
