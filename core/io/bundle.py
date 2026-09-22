"""El fichero de proyecto `.sidebcolor`: guardar y abrir una `ColorSession`.

QUÉ HAY DENTRO
--------------
Un zip corriente y moliente, que se puede abrir con el Finder:

    session.json                 toda la sesión menos los arrays grandes
    luts/look.cube               el LUT de look, si lo hay
    luts/match_000.cube          un .cube por cada MatchResult que traiga LUT
    arrays/a000_fingerprint.npy  la huella de cada ClipAnalysis
    arrays/a000_pixels.npy       la muestra de píxeles, si la hay

Los `.cube` de dentro se escriben en **modo exacto** (`decimales=None`, o sea
`%.9g`: nueve cifras SIGNIFICATIVAS) y no con los 6 decimales de costumbre. No
es capricho: guardar y abrir tiene que devolver la misma tabla **bit a bit**, y
9 cifras significativas son la garantía de ida y vuelta del float32 en IEEE 754.

Nueve *decimales* NO habrían servido, y esta es la trampa en la que es fácil
caer: con 9 decimales un valor de 0,9 vuelve perfecto, pero uno de 0,000012 se
pierde, porque el espaciado del float32 se encoge según baja el valor mientras
que el número de decimales no. Las cifras significativas sí se adaptan.

El precio es que los valores por debajo de 1e-4 salen en notación científica
(`1.2e-05`). Se lee sin problema con `float()` y con el `atof` de C, y estos
`.cube` sólo los abre la app; los que se le entregan a Resolve salen con
`escribir_cube()` y sus 6 decimales de siempre.

Los arrays de `ClipAnalysis` van en `.npy` porque son datos, no LUT, y `.npy`
es exacto y barato.

UN `.sidebcolor` VIENE DE FUERA
-------------------------------
Se lo pueden pasar a Mario por WeTransfer. Así que al abrirlo:

* **Zip-slip**: se rechaza el archivo entero si CUALQUIER entrada tiene una
  ruta absoluta, un `..`, una barra invertida o empieza por `/`. Aquí nunca se
  extrae nada al disco (se lee todo en memoria con `zf.read`), así que el
  ataque no llegaría a ninguna parte igualmente, pero la comprobación está y
  está probada: el día que alguien añada un "extraer miniaturas a una carpeta"
  la defensa ya estará puesta.
* **Zip-bomba**: se suma el tamaño descomprimido que declara el índice del zip
  y se rechaza si pasa de `MAX_DESCOMPRIMIDO`. Y como **el índice puede
  mentir**, cada entrada se lee además con un tope duro ajustado a lo que esa
  entrada declara: si dice 10 bytes y trae 400 MB, se leen 11 y se corta.
* **`np.load(..., allow_pickle=False)`**, siempre. Un `.npy` con pickle dentro
  ejecuta código arbitrario al cargarlo; ese es el agujero de verdad y el flag
  no se toca.
* Tope al número de entradas, para que un zip con un millón de ficheros de 0
  bytes no se coma el rato.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from core.contracts import (
    CDL,
    LUT3D,
    ClipAnalysis,
    ColorSession,
    ColorStats,
    Confidence,
    MatchResult,
)

from .cube import cube_a_texto, cube_desde_texto
from .errores import ErrorBundle, describe_ruta

__all__ = [
    "EXTENSION_BUNDLE",
    "FORMATO_VERSION",
    "MAX_DESCOMPRIMIDO",
    "MAX_ENTRADAS",
    "DECIMALES_LUT_BUNDLE",
    "guardar_sesion",
    "abrir_sesion",
]

EXTENSION_BUNDLE: str = ".sidebcolor"

#: Versión del formato de `session.json`. Sube cuando cambie la estructura.
FORMATO_VERSION: int = 1

#: Tope de bytes descomprimidos de todo el archivo. 256 MB da para una sesión
#: con varios LUT de 65 (9,6 MB de texto cada uno) y muestras de píxeles
#: grandes, y sigue cabiendo de sobra en la RAM de cualquier Mac.
MAX_DESCOMPRIMIDO: int = 256 * 1024 * 1024

#: Tope de entradas del zip. Una sesión normal tiene menos de 100.
MAX_ENTRADAS: int = 10_000

#: `None` = modo exacto (9 cifras significativas). Ver el docstring del módulo.
#: No lo pongas en 6 "para que se lea mejor": rompe la ida y vuelta.
DECIMALES_LUT_BUNDLE: int | None = None

_NOMBRE_SESION = "session.json"


# ---------------------------------------------------------------------------
# Serialización de las piezas
# ---------------------------------------------------------------------------


def _cdl_a_dict(cdl: CDL) -> dict[str, Any]:
    return {
        "slope": list(cdl.slope),
        "offset": list(cdl.offset),
        "power": list(cdl.power),
        "saturation": float(cdl.saturation),
    }


def _cdl_desde_dict(d: dict[str, Any]) -> CDL:
    try:
        return CDL(
            slope=tuple(d["slope"]),
            offset=tuple(d["offset"]),
            power=tuple(d["power"]),
            saturation=float(d["saturation"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorBundle(f"el CDL guardado en la sesión no es válido: {exc}") from exc


def _confianza_a_dict(c: Confidence) -> dict[str, Any]:
    return {
        "score": float(c.score),
        "level": str(c.level),
        "reasons": list(c.reasons),
        "metrics": {str(k): float(v) for k, v in c.metrics.items()},
    }


def _confianza_desde_dict(d: dict[str, Any]) -> Confidence:
    try:
        return Confidence(
            score=float(d["score"]),
            level=d["level"],
            reasons=tuple(d.get("reasons", ())),
            metrics={str(k): float(v) for k, v in (d.get("metrics") or {}).items()},
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorBundle(f"la confianza guardada en la sesión no es válida: {exc}") from exc


def _lut_a_dict(lut: LUT3D, fichero: str) -> dict[str, Any]:
    return {
        "fichero": fichero,
        "title": lut.title,
        "domain_min": list(lut.domain_min),
        "domain_max": list(lut.domain_max),
    }


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------


def _npy_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, np.asarray(arr), allow_pickle=False)
    return buf.getvalue()


def guardar_sesion(
    sesion: ColorSession,
    ruta: str | Path,
    *,
    crear_directorios: bool = False,
    decimales_lut: int | None = DECIMALES_LUT_BUNDLE,
) -> Path:
    """Escribe la sesión como `.sidebcolor`. Devuelve la ruta.

    Igual que `escribir_cube`: si la carpeta de destino no existe, se lanza en
    vez de crearla, salvo `crear_directorios=True`.
    """
    ruta = Path(ruta)
    nombre = describe_ruta(ruta)
    if not ruta.parent.exists():
        if not crear_directorios:
            raise ErrorBundle(
                f"la carpeta '{ruta.parent}' no existe; créala tú o llama con "
                "crear_directorios=True"
            )
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorBundle(f"no puedo crear la carpeta '{ruta.parent}': {exc}") from exc

    adjuntos: dict[str, bytes] = {}

    # --- análisis ---
    analyses: dict[str, Any] = {}
    for i, (clave, an) in enumerate(sesion.analyses.items()):
        if not isinstance(an, ClipAnalysis):
            raise ErrorBundle(f"analyses['{clave}'] no es un ClipAnalysis sino un {type(an).__name__}")
        f_fp = f"arrays/a{i:03d}_fingerprint.npy"
        adjuntos[f_fp] = _npy_bytes(np.asarray(an.fingerprint, dtype=np.float32))
        f_px: str | None = None
        if an.pixels is not None:
            f_px = f"arrays/a{i:03d}_pixels.npy"
            adjuntos[f_px] = _npy_bytes(np.asarray(an.pixels, dtype=np.float32))
        analyses[clave] = {
            "clip_id": an.clip_id,
            "path": an.path,
            "stats": an.stats.to_dict(),
            "fingerprint": f_fp,
            "width": int(an.width),
            "height": int(an.height),
            "frame_count": int(an.frame_count),
            "sampled_frames": int(an.sampled_frames),
            "source_space": an.source_space,
            "pixels": f_px,
            "warnings": list(an.warnings),
        }

    # --- emparejamientos ---
    matches: dict[str, Any] = {}
    for i, (clave, m) in enumerate(sesion.matches.items()):
        if not isinstance(m, MatchResult):
            raise ErrorBundle(f"matches['{clave}'] no es un MatchResult sino un {type(m).__name__}")
        lut_info = None
        if m.lut is not None:
            f_lut = f"luts/match_{i:03d}.cube"
            adjuntos[f_lut] = cube_a_texto(m.lut, decimales=decimales_lut).encode("ascii")
            lut_info = _lut_a_dict(m.lut, f_lut)
        matches[clave] = {
            "cdl": _cdl_a_dict(m.cdl),
            "lut": lut_info,
            "confidence": _confianza_a_dict(m.confidence),
            "delta_e_before": float(m.delta_e_before),
            "delta_e_after": float(m.delta_e_after),
            "content_mismatch": bool(m.content_mismatch),
            "notes": list(m.notes),
        }

    # --- LUT de look ---
    look = None
    if sesion.look_lut is not None:
        f_look = "luts/look.cube"
        adjuntos[f_look] = cube_a_texto(sesion.look_lut, decimales=decimales_lut).encode("ascii")
        look = _lut_a_dict(sesion.look_lut, f_look)

    documento = {
        "formato": "sidebcolor",
        "formato_version": FORMATO_VERSION,
        "sesion": {
            "project_name": sesion.project_name,
            "created_at": sesion.created_at,
            "app_version": sesion.app_version,
            "reference_clip_id": sesion.reference_clip_id,
            "analyses": analyses,
            "matches": matches,
            "look_lut": look,
            "notes": list(sesion.notes),
        },
    }

    try:
        with zipfile.ZipFile(ruta, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                _NOMBRE_SESION,
                json.dumps(documento, ensure_ascii=False, indent=2, allow_nan=False),
            )
            for interno, datos in adjuntos.items():
                zf.writestr(interno, datos)
    except ValueError as exc:
        # json.dumps con allow_nan=False lanza ValueError ante un NaN suelto.
        raise ErrorBundle(
            f"no puedo guardar '{nombre}': hay un valor no finito (NaN o infinito) en la "
            f"sesión y JSON no sabe escribirlo -> {exc}"
        ) from exc
    except PermissionError as exc:
        raise ErrorBundle(f"no tengo permiso para escribir en '{nombre}'") from exc
    except OSError as exc:
        raise ErrorBundle(f"no puedo escribir '{nombre}': {exc}") from exc
    return ruta


# ---------------------------------------------------------------------------
# Abrir
# ---------------------------------------------------------------------------


def _nombre_seguro(interno: str) -> bool:
    """¿Es una ruta interna de zip inofensiva? (defensa contra zip-slip)"""
    if not interno or interno.startswith("/") or interno.startswith("\\"):
        return False
    if "\\" in interno:  # separador de Windows: no lo usamos nunca al escribir
        return False
    if ":" in interno:  # 'C:/...' o un stream alternativo de NTFS
        return False
    partes = interno.split("/")
    return all(p not in ("", ".", "..") for p in partes)


def _abrir_zip(ruta: Path) -> zipfile.ZipFile:
    nombre = describe_ruta(ruta)
    if not ruta.exists():
        raise ErrorBundle(f"no existe el fichero '{ruta}'")
    if ruta.is_dir():
        raise ErrorBundle(f"'{nombre}' es una carpeta, no un {EXTENSION_BUNDLE}")
    if ruta.stat().st_size == 0:
        raise ErrorBundle(f"el fichero '{nombre}' está vacío")
    try:
        return zipfile.ZipFile(ruta, "r")
    except zipfile.BadZipFile as exc:
        raise ErrorBundle(
            f"'{nombre}' no es un zip válido; un {EXTENSION_BUNDLE} es un zip -> {exc}"
        ) from exc
    except PermissionError as exc:
        raise ErrorBundle(f"no tengo permiso para leer '{nombre}'") from exc
    except OSError as exc:
        raise ErrorBundle(f"no puedo leer '{nombre}': {exc}") from exc


def _revisar_zip(zf: zipfile.ZipFile, *, nombre: str, max_descomprimido: int) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_ENTRADAS:
        raise ErrorBundle(
            f"'{nombre}' tiene {len(infos)} entradas y el tope son {MAX_ENTRADAS}: "
            "esto no es una sesión, es un ataque o un fichero equivocado"
        )
    total = 0
    for zi in infos:
        if not _nombre_seguro(zi.filename):
            raise ErrorBundle(
                f"'{nombre}' trae una entrada con una ruta peligrosa: '{zi.filename}'. "
                "Un .sidebcolor legítimo no sale nunca de su propia carpeta. No lo abro."
            )
        total += zi.file_size
        if total > max_descomprimido:
            raise ErrorBundle(
                f"'{nombre}' declara más de {max_descomprimido // (1024 * 1024)} MB "
                "descomprimidos: huele a zip-bomba y no lo voy a desempaquetar"
            )


def _leer_entrada(zf: zipfile.ZipFile, interno: str, *, nombre: str, tope: int) -> bytes:
    """Lee una entrada con un tope DURO, porque el índice del zip puede mentir.

    El tope se ciñe al tamaño que la entrada DECLARA, no al tope global. Lo
    declarado ya lo ha validado `_revisar_zip` contra el tope global, así que
    ceñirse a ello no abre ningún hueco: un índice que declare de más se corta
    antes, y uno que declare de menos se pilla aquí.

    UNA PRECISIÓN, porque la revisión de la ola 1 dejó escrito lo contrario y
    conviene no construir nada encima de un dato falso: la revisión dice que
    con un índice mentiroso "el tope duro es `max_descomprimido` (256 MB), así
    que un fichero de 400 KB obliga a leer un cuarto de giga a memoria antes de
    decir que no". **Eso no pasa, ni pasaba antes de este cambio.**
    `zipfile.ZipExtFile` limita por su cuenta la lectura a `file_size` del
    directorio central (o sea, a los 10 bytes que declara el atacante) y
    verifica el CRC al llegar al final, que es donde salta. Medido con el zip
    del propio revisor: 300 MB reales, 299 KB en disco, `BadZipFile` en 0,057 s
    y sin descomprimir nada.

    Entonces, ¿para qué sirve este tope si `zipfile` ya corta? Para el caso que
    el CRC no cubre: un atacante que controla el zip entero puede declarar 10
    bytes **y** poner el CRC de esos 10 bytes. Ahí no hay error de CRC y la
    única defensa es esta. Es cinturón y tirantes, no el cinturón.
    """
    try:
        info = zf.getinfo(interno)
    except KeyError as exc:
        raise ErrorBundle(
            f"'{nombre}' está incompleto: la sesión referencia '{interno}' y no está dentro"
        ) from exc
    declarado = int(info.file_size)
    limite = min(declarado, tope)
    try:
        with zf.open(interno, "r") as fh:
            datos = fh.read(limite + 1)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ErrorBundle(f"'{nombre}': no puedo leer '{interno}' -> {exc}") from exc
    if len(datos) > limite:
        if declarado > tope:
            raise ErrorBundle(
                f"'{nombre}': la entrada '{interno}' se pasa del tope de "
                f"{tope // (1024 * 1024)} MB al descomprimir (zip-bomba)"
            )
        raise ErrorBundle(
            f"'{nombre}': el índice del zip miente sobre '{interno}' (dice {declarado} bytes "
            "y trae más). Un fichero así está corrupto o está preparado para hacer daño; "
            "no lo abro."
        )
    return datos


def _array(
    zf: zipfile.ZipFile, interno: str, *, nombre: str, tope: int, que: str
) -> np.ndarray:
    datos = _leer_entrada(zf, interno, nombre=nombre, tope=tope)
    try:
        # allow_pickle=False NO SE TOCA: con pickle, abrir un .sidebcolor que te
        # han mandado por correo ejecuta el código que lleve dentro.
        return np.load(io.BytesIO(datos), allow_pickle=False)
    except Exception as exc:  # noqa: BLE001 - np.load lanza de todo
        raise ErrorBundle(f"'{nombre}': '{interno}' ({que}) no es un .npy legible -> {exc}") from exc


def _lut(
    zf: zipfile.ZipFile, info: dict[str, Any], *, nombre: str, tope: int
) -> LUT3D:
    interno = info.get("fichero")
    if not isinstance(interno, str):
        raise ErrorBundle(f"'{nombre}': una entrada de LUT no dice en qué fichero está")
    texto = _leer_entrada(zf, interno, nombre=nombre, tope=tope).decode("utf-8-sig", errors="strict")
    lut = cube_desde_texto(texto, nombre=f"{nombre}:{interno}")
    # El .cube lleva dominio y título, pero el JSON es la fuente de verdad para
    # los metadatos (el TITLE del .cube se recorta a 100 caracteres).
    return LUT3D(
        table=lut.table,
        domain_min=tuple(info.get("domain_min", lut.domain_min)),
        domain_max=tuple(info.get("domain_max", lut.domain_max)),
        title=str(info.get("title", lut.title)),
    )


def abrir_sesion(ruta: str | Path, *, max_descomprimido: int = MAX_DESCOMPRIMIDO) -> ColorSession:
    """Abre un `.sidebcolor` y devuelve la `ColorSession` equivalente.

    Equivalente significa equivalente: los arrays de numpy vuelven bit a bit
    iguales (ver el docstring del módulo para el detalle de los 9 decimales).

    Levanta `ErrorBundle` ante cualquier fichero corrupto, hostil o de una
    versión de formato que no entendemos.
    """
    ruta = Path(ruta)
    nombre = describe_ruta(ruta)
    zf = _abrir_zip(ruta)
    try:
        _revisar_zip(zf, nombre=nombre, max_descomprimido=max_descomprimido)
        crudo = _leer_entrada(zf, _NOMBRE_SESION, nombre=nombre, tope=max_descomprimido)
        try:
            documento = json.loads(crudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErrorBundle(f"'{nombre}': {_NOMBRE_SESION} no es JSON válido -> {exc}") from exc
        if not isinstance(documento, dict) or documento.get("formato") != "sidebcolor":
            raise ErrorBundle(
                f"'{nombre}' es un zip, pero su {_NOMBRE_SESION} no es una sesión de "
                "SIDEBFLMS COLOR"
            )
        version = documento.get("formato_version")
        if version != FORMATO_VERSION:
            raise ErrorBundle(
                f"'{nombre}' está en la versión de formato {version!r} y esta versión de la "
                f"app sólo entiende la {FORMATO_VERSION}"
            )
        datos = documento.get("sesion")
        if not isinstance(datos, dict):
            raise ErrorBundle(f"'{nombre}': falta el bloque 'sesion' en {_NOMBRE_SESION}")

        return _sesion_desde_dict(datos, zf, nombre=nombre, tope=max_descomprimido)
    finally:
        zf.close()


def _sesion_desde_dict(
    datos: dict[str, Any], zf: zipfile.ZipFile, *, nombre: str, tope: int
) -> ColorSession:
    try:
        analyses: dict[str, ClipAnalysis] = {}
        for clave, d in (datos.get("analyses") or {}).items():
            pixels = None
            if d.get("pixels"):
                pixels = _array(zf, d["pixels"], nombre=nombre, tope=tope, que="pixels")
            analyses[clave] = ClipAnalysis(
                clip_id=d["clip_id"],
                path=d["path"],
                stats=ColorStats.from_dict(d["stats"]),
                fingerprint=_array(
                    zf, d["fingerprint"], nombre=nombre, tope=tope, que="fingerprint"
                ),
                width=int(d["width"]),
                height=int(d["height"]),
                frame_count=int(d["frame_count"]),
                sampled_frames=int(d["sampled_frames"]),
                source_space=d.get("source_space"),
                pixels=pixels,
                warnings=tuple(d.get("warnings", ())),
            )

        matches: dict[str, MatchResult] = {}
        for clave, d in (datos.get("matches") or {}).items():
            matches[clave] = MatchResult(
                cdl=_cdl_desde_dict(d["cdl"]),
                lut=None if not d.get("lut") else _lut(zf, d["lut"], nombre=nombre, tope=tope),
                confidence=_confianza_desde_dict(d["confidence"]),
                delta_e_before=float(d["delta_e_before"]),
                delta_e_after=float(d["delta_e_after"]),
                content_mismatch=bool(d["content_mismatch"]),
                notes=tuple(d.get("notes", ())),
            )

        look = datos.get("look_lut")
        return ColorSession(
            project_name=str(datos["project_name"]),
            created_at=str(datos["created_at"]),
            app_version=str(datos["app_version"]),
            reference_clip_id=datos.get("reference_clip_id"),
            analyses=analyses,
            matches=matches,
            look_lut=None if not look else _lut(zf, look, nombre=nombre, tope=tope),
            notes=tuple(datos.get("notes", ())),
        )
    except ErrorBundle:
        raise
    except KeyError as exc:
        raise ErrorBundle(f"'{nombre}': a la sesión le falta el campo {exc}") from exc
    except (TypeError, ValueError, AttributeError) as exc:
        raise ErrorBundle(f"'{nombre}': la sesión guardada está corrupta -> {exc}") from exc
