"""La biblioteca de presets del modo fácil, y el bundle de UN preset suelto.

Día 6, tarea 4. **Distinto de `core.io.bundle`**, que guarda una SESIÓN de
proyecto entera (análisis, matches, look). Aquí un preset es un LOOK SUELTO:
lo que viaja de un Mac a otro cuando alguien comparte "prueba este look mío"
— exactamente el caso de uso de `.drx`/`.cube` que Mario ya vive a diario,
sólo que empaquetado con sus dependencias y avisando de lo que falte.

QUÉ TRAE UN BUNDLE DE PRESET
------------------------------
Un `.sidebcolor` de preset es un zip con:

    preset.json     metadatos: nombre, procedencia, dependencias declaradas
    look.cube       el LUT en sí, en modo exacto (igual que core.io.bundle)
    miniatura.png   opcional: un fotograma de muestra CON el look aplicado,
                    sobre una escena SINTÉTICA del generador — nunca sobre
                    material real de Mario (regla del encargo del día 6)

Reutiliza las defensas de `core.io.bundle` contra zip-slip y zip-bomba: son
las mismas funciones, no una reimplementación con las mismas garantías "a
ojo" — un bundle de preset abierto en un Mac ajeno merece el mismo cuidado
que una sesión completa.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from core.contracts import LUT3D
from core.io.bundle import MAX_DESCOMPRIMIDO, _abrir_zip, _leer_entrada, _revisar_zip
from core.io.cube import cube_a_texto, cube_desde_texto, leer_cube
from core.io.errores import ErrorBundle, ErrorFormatoCube, describe_ruta
from core.io.qc import clasificar_lut

__all__ = [
    "EXTENSION_PRESET",
    "FORMATO_VERSION_PRESET",
    "Preset",
    "PresetAbierto",
    "nombre_legible",
    "sembrar_desde_carpeta",
    "sembrar_desde_drx",
    "generar_miniatura",
    "exportar_preset",
    "abrir_preset",
]

EXTENSION_PRESET: str = ".sidebcolor"
FORMATO_VERSION_PRESET: int = 1

_NOMBRE_PRESET_JSON = "preset.json"
_NOMBRE_LUT = "look.cube"
_NOMBRE_MINIATURA = "miniatura.png"

#: Tamaño de la miniatura embebida. Pequeño a propósito: el bundle viaja por
#: WeTransfer/AirDrop, no hace falta un fotograma a resolución de entrega.
ANCHO_MINIATURA = 320
ALTO_MINIATURA = 180


@dataclass(frozen=True)
class Preset:
    """Un look de la biblioteca, tal y como lo enseña el paso 4 del modo fácil."""

    id: str  # slug estable, derivado del nombre de archivo
    nombre: str  # legible: SIN la extensión, con los espacios limpios
    tamano_rejilla: int
    ruta_origen: str  # informativa: de qué archivo se sembró (NO se versiona ni viaja)
    #: Rutas de LUT que un `.drx` de origen declaraba (si el preset se sembró
    #: a partir de un PowerGrade, no de un `.cube` suelto). Vacío si no aplica.
    dependencias_declaradas: tuple[str, ...] = field(default_factory=tuple)
    #: "conversion" | "look" | None, medido con `core.io.qc.clasificar_lut`
    #: (día 6). `None` sólo si `sembrar_desde_carpeta`/`sembrar_desde_drx` no
    #: pudieron leer el `.cube` para medirlo — no debería pasar en uso normal,
    #: ya que las dos funciones ya necesitan cargarlo para saber su rejilla.
    clasificacion: str | None = None
    #: Avisos de procedencia (día 7, tarea 4): sólo lo llena
    #: `sembrar_desde_drx`, con `core.io.drx.advertencia_version_desconocida`
    #: si el `.drx` de origen vino de una versión de Resolve nunca comprobada
    #: contra material real. Vacío en el caso normal y siempre en presets
    #: sembrados de un `.cube` suelto (no hay versión de Resolve que avisar).
    advertencias: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PresetAbierto:
    """Lo que devuelve `abrir_preset`: el preset, su LUT, y los avisos."""

    preset: Preset
    lut: LUT3D
    miniatura: np.ndarray | None  # (alto, ancho, 3) float32 codificado Rec.709, o None
    #: Dependencias que `preset.dependencias_declaradas` menciona pero que NO
    #: vinieron dentro del bundle. Un preset con avisos se puede seguir
    #: abriendo — el `.cube` principal siempre está completo — pero si
    #: dependía de OTRO LUT externo (p.ej. una conversión de espacio previa
    #: que no se horneó dentro), aplicarlo sin decir esto sale mal en silencio.
    avisos: tuple[str, ...] = field(default_factory=tuple)


def _slug(texto: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return s or "preset"


def nombre_legible(ruta: str | Path) -> str:
    """El nombre de archivo, sin extensión y con espacios limpios.

    Los nombres reales de Mario (`"SIDEBFLMS NIGHT SONY.cube"`, `"4 (-)
    AMSTERDAM SILVER V2.cube"`) ya son descriptivos por sí solos — no hace
    falta adivinar una taxonomía que no está en ningún sitio. Lo único que se
    limpia es la extensión y el espaciado sobrante; no se reordenan palabras
    ni se adivina una categoría que el nombre no dice.
    """
    base = Path(ruta).stem
    return re.sub(r"\s+", " ", base).strip()


def sembrar_desde_carpeta(carpeta: str | Path) -> list[Preset]:
    """Recorre `carpeta` (recursivo) y construye un `Preset` por cada `.cube`.

    No lee ni modifica nada más que abrir cada `.cube` para saber su tamaño
    de rejilla — no copia, no mueve, no escribe. `carpeta` puede ser
    `tests/luts_reales/`, de sólo lectura.
    """
    base = Path(carpeta)
    presets: list[Preset] = []
    if not base.is_dir():
        return presets
    for ruta in sorted(base.rglob("*.cube")):
        try:
            lut = leer_cube(ruta)
        except ErrorFormatoCube:
            continue  # un .cube que no se puede leer no entra en la biblioteca, no rompe la siembra
        nombre = nombre_legible(ruta)
        presets.append(
            Preset(
                id=_slug(f"{ruta.parent.name}-{nombre}" if ruta.parent != base else nombre),
                nombre=nombre,
                tamano_rejilla=lut.size,
                ruta_origen=str(ruta),
                clasificacion=clasificar_lut(lut),
            )
        )
    return presets


def sembrar_desde_drx(ruta_drx: str | Path, carpeta_luts: str | Path) -> tuple[Preset, LUT3D] | None:
    """Un `Preset` a partir de un PowerGrade `.drx` real, en vez de un `.cube` suelto.

    Usa `core.io.drx.buscar_rutas_referenciadas` (día 6, tarea 1) para saber
    qué LUT(s) referencia el grado. Si hay más de uno (el caso confirmado de
    "conversión + look", ver `core/io/FORMATO-DRX.md` §3.2), el ÚLTIMO es el
    look — el que se empaqueta como `look.cube` del preset — y los demás se
    guardan como `dependencias_declaradas`: el PowerGrade original los
    necesitaba, pero un bundle de preset sólo lleva el look, nunca la cadena
    de conversión de cámara completa (eso es tarea del paso 1 del modo fácil,
    "ordenar la casa", no de la biblioteca de looks).

    `None` si el `.drx` no referencia ningún LUT, o si el que sería el look
    no se encuentra (por nombre) dentro de `carpeta_luts` — sin el archivo
    real no hay nada que empaquetar.

    Día 7, tarea 4: si el `.drx` fue escrito por una versión de Resolve
    nunca comprobada contra material real, el `Preset` resultante lleva ese
    aviso en `advertencias` — el protobuf del grado no tiene esquema
    publicado y los campos podrían haberse movido; avisa en vez de dar por
    buenas unas rutas de LUT que podrían estar mal leídas en silencio.
    """
    from core.io.drx import (
        advertencia_version_desconocida,
        buscar_rutas_referenciadas,
        version_resolve,
    )

    rutas = buscar_rutas_referenciadas(ruta_drx)
    if not rutas:
        return None
    ruta_look, dependencias = rutas[-1], rutas[:-1]

    base = Path(carpeta_luts)
    candidato = next(base.rglob(Path(ruta_look).name), None)
    if candidato is None:
        return None
    try:
        lut = leer_cube(candidato)
    except ErrorFormatoCube:
        return None
    aviso_version = advertencia_version_desconocida(version_resolve(ruta_drx))
    advertencias = (aviso_version,) if aviso_version is not None else ()
    nombre = nombre_legible(candidato)
    preset = Preset(
        id=_slug(nombre),
        nombre=nombre,
        tamano_rejilla=lut.size,
        ruta_origen=str(candidato),
        dependencias_declaradas=dependencias,
        clasificacion=clasificar_lut(lut),
        advertencias=advertencias,
    )
    return preset, lut


def generar_miniatura(lut: LUT3D) -> np.ndarray:
    """Un fotograma pequeño CON el look aplicado, sobre una escena sintética.

    Nunca sobre material real: la escena sale de `tests/media/generate.py`,
    el mismo generador que usa el resto de la app para sus capturas y
    demostraciones (`gui/datos_demo.py`). Devuelve valores en `WORKING_SPACE`.
    """
    from core.color import to_working
    from tests.media import generate as gen

    escena = to_working(gen.studio_scene(skin_tone_index=2).image, "linear_rec709")
    paso_y = max(1, escena.shape[0] // ALTO_MINIATURA)
    paso_x = max(1, escena.shape[1] // ANCHO_MINIATURA)
    reducida = escena[::paso_y, ::paso_x][:ALTO_MINIATURA, :ANCHO_MINIATURA]
    return lut.apply(reducida).astype(np.float32)


def _a_uint8_rec709(miniatura_working: np.ndarray) -> np.ndarray:
    """`(alto, ancho, 3)` en `WORKING_SPACE` -> `(alto, ancho, 3)` uint8 Rec.709.

    La misma cuenta que `gui.imagen.a_uint8` (curva de Rec.709 + recorte +
    escalado a 0..255), reimplementada aquí en vez de importada: `core/` no
    importa `gui/` — sería invertir la dirección de dependencias del
    proyecto (`gui` depende de `core`, nunca al revés) — y tampoco PySide6
    (contrato 6 de `core/contracts.py`). `core.color.from_working` sí es de
    `core`, así que no hay problema en usarla aquí directamente.
    """
    from core.color import from_working

    pantalla = from_working(np.asarray(miniatura_working, dtype=np.float32), "rec709")
    pantalla = np.nan_to_num(np.asarray(pantalla, dtype=np.float64), nan=0.0, posinf=1.0, neginf=0.0)
    return (np.clip(pantalla, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _miniatura_a_png(miniatura_working: np.ndarray) -> bytes:
    """`(alto, ancho, 3)` en `WORKING_SPACE` -> bytes PNG (Rec.709 codificado).

    Todo en memoria con OpenCV (`cv2.imencode`), sin tocar disco: `core/`
    sólo escribe en una ruta que le pasen por parámetro (contrato 7), y un
    fichero temporal de por medio sería exactamente ese tipo de escritura no
    controlada.
    """
    import cv2

    rgb = _a_uint8_rec709(miniatura_working)
    bgr = np.ascontiguousarray(rgb[..., ::-1])  # OpenCV codifica en BGR
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise ErrorBundle("no se ha podido codificar la miniatura a PNG")
    return buf.tobytes()


def _png_a_array(png_bytes: bytes) -> np.ndarray | None:
    """Bytes PNG -> `(alto, ancho, 3)` float32 en 0..1, codificado Rec.709
    (tal y como se guardó: quien la use la pinta directamente, no la
    reprocesa a `WORKING_SPACE`). Todo en memoria, sin fichero temporal."""
    import cv2

    datos = np.frombuffer(png_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(datos, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    rgb = bgr[..., ::-1]
    return np.ascontiguousarray(rgb).astype(np.float32) / 255.0


def exportar_preset(
    preset: Preset,
    lut: LUT3D,
    destino: str | Path,
    *,
    miniatura: np.ndarray | None = None,
    crear_directorios: bool = False,
) -> Path:
    """Escribe `destino` (con `.sidebcolor` si no lo trae ya) con el preset.

    Igual que `escribir_cube`/`guardar_sesion`: si la carpeta de destino no
    existe, se lanza en vez de crearla, salvo `crear_directorios=True`.
    """
    destino = Path(destino)
    if destino.suffix != EXTENSION_PRESET:
        destino = destino.with_suffix(EXTENSION_PRESET)

    if not destino.parent.exists():
        if not crear_directorios:
            raise ErrorBundle(
                f"la carpeta '{destino.parent}' no existe; créala tú o llama con "
                "crear_directorios=True"
            )
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorBundle(f"no puedo crear la carpeta '{destino.parent}': {exc}") from exc

    metadatos = {
        "formato_version": FORMATO_VERSION_PRESET,
        "creado": datetime.now(UTC).isoformat(timespec="seconds"),
        "id": preset.id,
        "nombre": preset.nombre,
        "tamano_rejilla": preset.tamano_rejilla,
        "dependencias_declaradas": list(preset.dependencias_declaradas),
        "clasificacion": preset.clasificacion,
    }

    try:
        with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_NOMBRE_PRESET_JSON, json.dumps(metadatos, indent=2, ensure_ascii=False))
            zf.writestr(_NOMBRE_LUT, cube_a_texto(lut, decimales=None))
            if miniatura is not None:
                zf.writestr(_NOMBRE_MINIATURA, _miniatura_a_png(miniatura))
    except PermissionError as exc:
        raise ErrorBundle(f"no tengo permiso para escribir en '{describe_ruta(destino)}'") from exc
    except OSError as exc:
        raise ErrorBundle(f"no puedo escribir '{describe_ruta(destino)}': {exc}") from exc
    return destino


def abrir_preset(ruta: str | Path) -> PresetAbierto:
    """Abre un `.sidebcolor` de preset. Lanza `ErrorBundle` si está corrupto,
    manipulado, o simplemente no es un bundle de preset (p.ej. es una SESIÓN
    completa de `core.io.bundle`, que usa otro esquema de zip).
    """
    ruta = Path(ruta)
    nombre = describe_ruta(ruta)
    with _abrir_zip(ruta) as zf:
        _revisar_zip(zf, nombre=nombre, max_descomprimido=MAX_DESCOMPRIMIDO)
        try:
            crudo = _leer_entrada(zf, _NOMBRE_PRESET_JSON, nombre=nombre, tope=1024 * 1024)
        except ErrorBundle as exc:
            raise ErrorBundle(
                f"'{nombre}' no trae {_NOMBRE_PRESET_JSON}: no es un bundle de preset "
                "(¿será una sesión .sidebcolor completa, de core.io.bundle?)"
            ) from exc
        try:
            metadatos = json.loads(crudo.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ErrorBundle(f"'{nombre}': {_NOMBRE_PRESET_JSON} no es JSON válido -> {exc}") from exc

        deps_declaradas = tuple(metadatos.get("dependencias_declaradas") or ())
        preset = Preset(
            id=str(metadatos.get("id", "")),
            nombre=str(metadatos.get("nombre", nombre)),
            tamano_rejilla=int(metadatos.get("tamano_rejilla", 0)),
            ruta_origen=str(ruta),
            dependencias_declaradas=deps_declaradas,
            clasificacion=metadatos.get("clasificacion"),
        )

        # `errors="strict"`, no "replace": un `.cube` corrupto tiene que
        # decirlo como corrupto, no colarse con caracteres de reemplazo que
        # luego fallan (si fallan) con un mensaje de sintaxis que no dice
        # cuál es la causa real. Mismo criterio que `core/io/bundle.py::_lut`.
        crudo_lut = _leer_entrada(zf, _NOMBRE_LUT, nombre=nombre, tope=64 * 1024 * 1024)
        try:
            cube_texto = crudo_lut.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ErrorBundle(f"'{nombre}': {_NOMBRE_LUT} no es UTF-8 válido -> {exc}") from exc
        lut = cube_desde_texto(cube_texto, nombre=f"{nombre}:{_NOMBRE_LUT}")

        miniatura = None
        if _NOMBRE_MINIATURA in zf.namelist():
            png_bytes = _leer_entrada(zf, _NOMBRE_MINIATURA, nombre=nombre, tope=8 * 1024 * 1024)
            miniatura = _png_a_array(png_bytes)

    # Avisos: dependencias que el ORIGEN declaraba y que este bundle no trae
    # dentro de sí (el bundle sólo empaqueta `look.cube`, nunca los LUTs de
    # conversión previos que un .drx pudiera encadenar). No es un fallo del
    # bundle — es exactamente lo que hay que decir antes de aplicarlo.
    avisos = tuple(
        f"este preset venía de un PowerGrade que además usaba «{dep}», y ese LUT NO viaja "
        "dentro de este bundle: revisa si hace falta antes de aplicar el look."
        for dep in deps_declaradas
    )
    return PresetAbierto(preset=preset, lut=lut, miniatura=miniatura, avisos=avisos)
