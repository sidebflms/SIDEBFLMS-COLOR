"""`gui.perfiles_trabajo.aplicar_perfil_a_estado`: el "un botón" que pidió
Mario (día 9, continuación 10) — para todo un timeline, detectar la cámara
de cada clip y hornear/desplegar el LUT que le toca (ajuste de esa cámara +
look del trabajo), sin ir cámara por cámara ni clip por clip.

**CUIDADO DELIBERADO CON `lut_dir`**: `FakeResolve` con la instalación por
defecto ("descarga") devuelve la ruta REAL de la carpeta de LUTs de Resolve
en este Mac (`core.resolve.incognitas.LUT_DIR_DESCARGA`, un path absoluto
del sistema) — escribir ahí desde un test sería tocar disco de producción
(ver `feedback_never_test_on_real_disks`). Todos los `FakeResolve` de este
fichero se construyen con `incognitas=Incognitas(instalacion="mac_app_store")`
y `home=tmp_path`, para que `lut_dir()` caiga DENTRO del `tmp_path` de cada
test, nunca en la carpeta real.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

from core.contracts import CDL, ClipRef, Confidence, MatchResult  # noqa: E402
from core.io.cube import leer_cube  # noqa: E402
from core.perfiles import PerfilCamara, PerfilTrabajo  # noqa: E402
from core.resolve import FakeResolve  # noqa: E402
from core.resolve.incognitas import Incognitas, lut_dir  # noqa: E402
from gui.datos_demo import ClipDemo, EstadoDemo  # noqa: E402
from gui.perfiles_trabajo import aplicar_perfil_a_estado  # noqa: E402


def _match_identidad() -> MatchResult:
    return MatchResult(
        cdl=CDL(),
        lut=None,
        confidence=Confidence(score=1.0, level="alta", reasons=(), metrics={}),
        delta_e_before=0.0,
        delta_e_after=0.0,
        content_mismatch=False,
    )


def _clip(clip_id: str, manufacturer: str | None, tipo: str | None = None) -> ClipDemo:
    ref = ClipRef(
        clip_id=clip_id,
        name=clip_id,
        track=1,
        index=1,
        start_frame=0,
        end_frame=99,
        camera_manufacturer=manufacturer,
        camera_type=tipo,
    )
    return ClipDemo(ref=ref, match=_match_identidad())


def _puente_sandbox(tmp_path: Path, clips: list[ClipDemo]) -> FakeResolve:
    incognitas = Incognitas(instalacion="mac_app_store")
    return FakeResolve(
        clips=[c.ref for c in clips], incognitas=incognitas, home=str(tmp_path), nodos_por_clip=3
    )


def _lut_dir_de_prueba(tmp_path: Path) -> Path:
    return Path(lut_dir(Incognitas(instalacion="mac_app_store"), home=str(tmp_path)))


def test_cada_camara_reconocida_recibe_su_propio_look_rel(tmp_path: Path):
    clips = [_clip("c1", "GoPro"), _clip("c2", "DJI"), _clip("c3", "GoPro")]
    estado = EstadoDemo(clips=clips, puente=_puente_sandbox(tmp_path, clips))
    perfil = PerfilTrabajo(
        nombre="Fabrik",
        camaras=(
            PerfilCamara(fabricante_contiene="gopro", cdl_base=CDL(saturation=1.1)),
            PerfilCamara(fabricante_contiene="dji", cdl_base=CDL(saturation=0.9)),
        ),
    )

    nuevo = aplicar_perfil_a_estado(estado, perfil)

    por_id = {c.clip_id: c for c in nuevo.clips}
    assert por_id["c1"].look_rel == por_id["c3"].look_rel  # misma camara, mismo fichero
    assert por_id["c1"].look_rel != por_id["c2"].look_rel  # camaras distintas
    assert por_id["c1"].look_rel.startswith("SIDEB/perfiles/fabrik/")


def test_los_ficheros_se_escriben_de_verdad_dentro_del_sandbox(tmp_path: Path):
    clips = [_clip("c1", "GoPro")]
    estado = EstadoDemo(clips=clips, puente=_puente_sandbox(tmp_path, clips))
    perfil = PerfilTrabajo(
        nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro", cdl_base=CDL(saturation=1.2)),)
    )

    nuevo = aplicar_perfil_a_estado(estado, perfil)

    ruta_absoluta = _lut_dir_de_prueba(tmp_path) / nuevo.clips[0].look_rel
    assert ruta_absoluta.is_file()
    lut = leer_cube(ruta_absoluta)
    assert lut.title  # se escribio con un titulo, no un LUT vacio


def test_camara_no_reconocida_se_queda_sin_look_rel_propio(tmp_path: Path):
    clips = [_clip("c1", "Canon")]
    estado = EstadoDemo(clips=clips, puente=_puente_sandbox(tmp_path, clips))
    perfil = PerfilTrabajo(nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro"),))

    nuevo = aplicar_perfil_a_estado(estado, perfil)

    assert nuevo.clips[0].look_rel is None


def test_muta_en_el_sitio_y_devuelve_el_mismo_objeto(tmp_path: Path):
    """A propósito, no un descuido: `VentanaPrincipal` reparte el MISMO
    EstadoDemo (y los mismos ClipDemo) entre varias pantallas -- si esto
    devolviera copias nuevas, sólo la pantalla que llama se enteraría del
    look_rel puesto."""
    clips = [_clip("c1", "GoPro")]
    estado = EstadoDemo(clips=clips, puente=_puente_sandbox(tmp_path, clips))
    clip_original = estado.clips[0]
    perfil = PerfilTrabajo(
        nombre="Fabrik", camaras=(PerfilCamara(fabricante_contiene="gopro", cdl_base=CDL(saturation=1.1)),)
    )

    resultado = aplicar_perfil_a_estado(estado, perfil)

    assert resultado is estado
    assert estado.clips[0] is clip_original  # mismo objeto ClipDemo, mutado
    assert estado.clips[0].look_rel is not None


def test_perfil_sin_camaras_ni_look_no_escribe_nada(tmp_path: Path):
    clips = [_clip("c1", "GoPro"), _clip("c2", None)]
    estado = EstadoDemo(clips=clips, puente=_puente_sandbox(tmp_path, clips))
    perfil = PerfilTrabajo(nombre="Vacio")

    nuevo = aplicar_perfil_a_estado(estado, perfil)

    assert all(c.look_rel is None for c in nuevo.clips)
    carpeta_perfiles = _lut_dir_de_prueba(tmp_path) / "SIDEB" / "perfiles"
    assert not carpeta_perfiles.exists()
