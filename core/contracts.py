"""CONTRATOS CONGELADOS de SIDEBFLMS COLOR.

Este archivo es propiedad EXCLUSIVA del orquestador. Ningun agente lo edita.
Si tu modulo necesita cambiar una firma o un campo, pidelo; no lo cambies.

Todo lo que cruza una frontera entre modulos vive aqui. Los modulos pueden
tener sus propios tipos internos, pero no pueden aparecer en una firma publica.

CONVENCIONES QUE NO SE NEGOCIAN
-------------------------------
1. Imagenes: numpy float32, forma (alto, ancho, 3), canales en orden R, G, B.
   Rango nominal 0..1 pero los valores FUERA de rango son legales y hay que
   preservarlos (el material log y el sobreexpuesto los tienen). Nada de uint8
   en las fronteras entre modulos.
2. Listas de pixeles: forma (N, 3) float32/float64, mismo orden RGB.
3. Espacio de trabajo: `WORKING_SPACE` (DaVinci Wide Gamut + DaVinci
   Intermediate). Toda estadistica, todo emparejamiento y el dominio de todo
   LUT viven ahi salvo que la firma diga otra cosa.
4. LUT3D.table se indexa `table[ri, gi, bi] -> (r, g, b)`. El eje 0 es ROJO.
   (Ojo: en el FICHERO .cube el rojo es el que varia mas rapido, o sea que el
   orden de lineas del fichero es el de `table.transpose(2,1,0,3).reshape(-1,3)`.
   El agente D es el unico que tiene que pensar en esto.)
5. Indices de nodo de Resolve: 1-based, como la API. Dentro de core NO se usan
   indices de nodo salvo en `core.resolve`.
6. Nada en `core/` importa PySide6 ni DaVinciResolveScript.
7. Ninguna funcion de `core/` escribe fuera de una ruta que le pasen por
   parametro. Cero escrituras en el sistema, en ~ o en /Volumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

import numpy as np

from core.umbrales import (
    CONFIDENCE_ALTA,
    CONFIDENCE_MEDIA,
    LUT_SIZE_DEFAULT,
    MUESTRAS_MINIMAS_CELDA,
)

# ---------------------------------------------------------------------------
# Constantes congeladas
# ---------------------------------------------------------------------------
#
# Las tres que deciden un veredicto que el usuario ve --CONFIDENCE_ALTA,
# CONFIDENCE_MEDIA y LUT_SIZE_DEFAULT-- se DEFINEN en `core/umbrales.py`, que es
# el unico sitio donde se escribe un criterio de decision, y se reexportan desde
# aqui para no romper a nadie. `core.umbrales` no importa nada de `core/`, asi
# que no hay ciclo.

#: Espacio en el que opera todo el nucleo.
WORKING_SPACE: str = "davinci_wg_intermediate"

#: Tamanos de rejilla que sabemos leer y escribir.
LUT_SIZES_SOPORTADOS: tuple[int, ...] = (17, 33, 65)

#: Percentiles que guarda ColorStats, en este orden exacto.
PERCENTILE_LEVELS: tuple[float, ...] = (0.1, 1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0, 99.0, 99.9)

#: Numero de bins del histograma de saturacion de ColorStats.
SAT_BINS: int = 64

#: Longitud del vector de huella de contenido (ClipAnalysis.fingerprint).
FINGERPRINT_LEN: int = 96

#: Nombre de la version de Resolve donde escribe la app. Nunca se toca otra.
VERSION_NAME: str = "SIDEB COLOR"

#: Indices de nodo del diseno de tres nodos (seccion 3 del encargo).
NODE_NORMALIZACION: int = 1
NODE_BALANCE: int = 2
NODE_LOOK: int = 3

#: Pesos de luma Rec.709. Los usa el CDL para la saturacion, y solo para eso.
LUMA_REC709 = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)

ColorSpaceName = Literal[
    "slog3_sgamut3cine",
    "vlog_vgamut",
    "clog3_cinemagamut",
    "dlog_dgamut",
    "rec709",
    "davinci_wg_intermediate",
    "linear_davinci_wg",
    "linear_rec709",  # escena-lineal en primarios Rec.709: lo que produce el generador
]

ConfidenceLevel = Literal["alta", "media", "baja"]

Array = np.ndarray


# ---------------------------------------------------------------------------
# 1. Estadistica de color
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ColorStats:
    """Resumen estadistico de la distribucion de color de un plano.

    Todos los arrays en float64 y en `WORKING_SPACE` salvo `skin_locus`, que va
    en Oklab porque es donde el locus de pieles tiene sentido.
    """

    mean: Array  # (3,)
    std: Array  # (3,)
    cov: Array  # (3, 3) covarianza RGB
    percentiles: Array  # (len(PERCENTILE_LEVELS), 3)
    black_point: Array  # (3,) percentil bajo robusto
    white_point: Array  # (3,) percentil alto robusto
    saturation_hist: Array  # (SAT_BINS,) normalizado, suma 1
    skin_locus: Array | None  # (3,) Oklab medio de los pixeles de piel, o None
    skin_fraction: float  # 0..1
    n_samples: int

    _ARRAY_FIELDS = (
        "mean",
        "std",
        "cov",
        "percentiles",
        "black_point",
        "white_point",
        "saturation_hist",
    )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {k: np.asarray(getattr(self, k)).tolist() for k in self._ARRAY_FIELDS}
        d["skin_locus"] = None if self.skin_locus is None else np.asarray(self.skin_locus).tolist()
        d["skin_fraction"] = float(self.skin_fraction)
        d["n_samples"] = int(self.n_samples)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ColorStats:
        kw = {k: np.asarray(d[k], dtype=np.float64) for k in cls._ARRAY_FIELDS}
        skin = d.get("skin_locus")
        return cls(
            skin_locus=None if skin is None else np.asarray(skin, dtype=np.float64),
            skin_fraction=float(d["skin_fraction"]),
            n_samples=int(d["n_samples"]),
            **kw,
        )


# ---------------------------------------------------------------------------
# 2. CDL
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CDL:
    """ASC CDL. Es lo unico que la API de Resolve deja escribir por parametro.

    Formula, en este orden y sin atajos:
        x   = in * slope + offset
        x   = max(x, 0)            <- el clamp ANTES de la potencia es del estandar
        out = x ** power
        luma = 0.2126 R + 0.7152 G + 0.0722 B   (Rec.709)
        out = luma + saturation * (out - luma)

    `slope`, `offset` y `power` son tuplas de 3 (R, G, B). `power` > 0 siempre.
    """

    slope: tuple[float, float, float] = (1.0, 1.0, 1.0)
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    power: tuple[float, float, float] = (1.0, 1.0, 1.0)
    saturation: float = 1.0

    def __post_init__(self) -> None:
        for name in ("slope", "offset", "power"):
            value = tuple(float(v) for v in getattr(self, name))
            if len(value) != 3:
                raise ValueError(f"CDL.{name} tiene que tener 3 componentes, no {len(value)}")
            if not all(np.isfinite(value)):
                raise ValueError(f"CDL.{name} tiene valores no finitos: {value}")
            object.__setattr__(self, name, value)
        if any(p <= 0.0 for p in self.power):
            raise ValueError(f"CDL.power tiene que ser > 0 en los tres canales: {self.power}")
        sat = float(self.saturation)
        if not np.isfinite(sat):
            raise ValueError("CDL.saturation no es finito")
        object.__setattr__(self, "saturation", sat)

    def apply(self, rgb: Array) -> Array:
        """rgb (..., 3) float -> (..., 3) float. No recorta el resultado final.

        El unico recorte es el `max(x, 0)` antes de la potencia, que manda el
        estandar ASC CDL (elevar un negativo a 0.8 daria NaN).
        """
        arr = np.asarray(rgb, dtype=np.float64)
        if arr.shape[-1] != 3:
            raise ValueError(f"esperaba (..., 3), llego {arr.shape}")
        x = arr * np.asarray(self.slope) + np.asarray(self.offset)
        np.maximum(x, 0.0, out=x)
        out = np.power(x, np.asarray(self.power))
        if self.saturation != 1.0:
            luma = out @ LUMA_REC709
            out = luma[..., None] + self.saturation * (out - luma[..., None])
        return out

    def is_identity(self, tol: float = 1e-6) -> bool:
        return (
            np.allclose(self.slope, 1.0, atol=tol)
            and np.allclose(self.offset, 0.0, atol=tol)
            and np.allclose(self.power, 1.0, atol=tol)
            and abs(self.saturation - 1.0) <= tol
        )

    def as_resolve_payload(self, node_index: int) -> dict[str, str]:
        """Diccionario listo para `timelineItem.SetCDL(...)`.

        Resolve espera las claves 'NodeIndex', 'Slope', 'Offset', 'Power' y
        'Saturation', con los tres numeros separados por espacios en una cadena.
        """
        if node_index < 1:
            raise ValueError("los indices de nodo de Resolve son 1-based")
        fmt = lambda t: " ".join(f"{v:.6f}" for v in t)  # noqa: E731
        return {
            "NodeIndex": str(int(node_index)),
            "Slope": fmt(self.slope),
            "Offset": fmt(self.offset),
            "Power": fmt(self.power),
            "Saturation": f"{self.saturation:.6f}",
        }

    @staticmethod
    def identity() -> CDL:
        return CDL()


# ---------------------------------------------------------------------------
# 3. LUT 3D
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class LUT3D:
    """LUT 3D cubica. `table` es (N, N, N, 3) float32 indexada [r, g, b]."""

    table: Array
    domain_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    domain_max: tuple[float, float, float] = (1.0, 1.0, 1.0)
    title: str = "SIDEB COLOR"

    def __post_init__(self) -> None:
        table = np.asarray(self.table, dtype=np.float32)
        if table.ndim != 4 or table.shape[3] != 3:
            raise ValueError(f"LUT3D.table tiene que ser (N, N, N, 3), llego {table.shape}")
        n = table.shape[0]
        if table.shape[:3] != (n, n, n):
            raise ValueError(f"LUT3D.table tiene que ser cubica, llego {table.shape[:3]}")
        if n < 2:
            raise ValueError("un LUT 3D necesita al menos 2 muestras por eje")
        object.__setattr__(self, "table", table)
        object.__setattr__(self, "domain_min", tuple(float(v) for v in self.domain_min))
        object.__setattr__(self, "domain_max", tuple(float(v) for v in self.domain_max))
        if any(b <= a for a, b in zip(self.domain_min, self.domain_max, strict=True)):
            raise ValueError(f"dominio invalido: {self.domain_min} -> {self.domain_max}")

    @property
    def size(self) -> int:
        return int(self.table.shape[0])

    def apply(self, rgb: Array) -> Array:
        """Interpolacion trilineal. Fuera de dominio: se sujeta al borde.

        Sujetar y no extrapolar es deliberado: es lo que hace Resolve, y asi lo
        que veas aqui es lo que veras alli.
        """
        arr = np.asarray(rgb, dtype=np.float64)
        if arr.shape[-1] != 3:
            raise ValueError(f"esperaba (..., 3), llego {arr.shape}")
        shape = arr.shape
        flat = arr.reshape(-1, 3)
        n = self.size
        dmin = np.asarray(self.domain_min)
        dmax = np.asarray(self.domain_max)
        t = np.clip((flat - dmin) / (dmax - dmin), 0.0, 1.0)
        pos = t * (n - 1)
        i0 = np.clip(np.floor(pos).astype(np.int64), 0, n - 2)
        f = pos - i0
        fr, fg, fb = f[:, 0:1], f[:, 1:2], f[:, 2:3]
        r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
        r1, g1, b1 = r0 + 1, g0 + 1, b0 + 1
        tab = self.table.astype(np.float64, copy=False)
        c00 = tab[r0, g0, b0] * (1 - fr) + tab[r1, g0, b0] * fr
        c10 = tab[r0, g1, b0] * (1 - fr) + tab[r1, g1, b0] * fr
        c01 = tab[r0, g0, b1] * (1 - fr) + tab[r1, g0, b1] * fr
        c11 = tab[r0, g1, b1] * (1 - fr) + tab[r1, g1, b1] * fr
        c0 = c00 * (1 - fg) + c10 * fg
        c1 = c01 * (1 - fg) + c11 * fg
        return (c0 * (1 - fb) + c1 * fb).reshape(shape)

    @staticmethod
    def identity(size: int = LUT_SIZE_DEFAULT) -> LUT3D:
        axis = np.linspace(0.0, 1.0, size, dtype=np.float32)
        r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")
        return LUT3D(table=np.stack([r, g, b], axis=-1).astype(np.float32), title="Identidad")


# ---------------------------------------------------------------------------
# 4. Confianza
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Confidence:
    """Cuanto nos fiamos de un resultado, y por que.

    `score` en 0..1. `level` se deriva de score con los umbrales de
    `confidence_level()`. `reasons` son frases en castellano para la GUI, en
    orden de importancia. `metrics` son los numeros crudos por si alguien quiere
    discutir la nota.
    """

    score: float
    level: ConfidenceLevel
    reasons: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)


def confidence_level(score: float) -> ConfidenceLevel:
    """Unico sitio donde un numero se convierte en alta/media/baja."""
    if score >= CONFIDENCE_ALTA:
        return "alta"
    if score >= CONFIDENCE_MEDIA:
        return "media"
    return "baja"


# ---------------------------------------------------------------------------
# 5. Analisis de clip
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ClipAnalysis:
    """Lo que el agente B saca de un fichero de video o de una secuencia."""

    clip_id: str
    path: str
    stats: ColorStats
    fingerprint: Array  # (FINGERPRINT_LEN,) float32, norma L2 = 1
    width: int
    height: int
    frame_count: int  # fotogramas del clip segun ffprobe, 0 si no se sabe
    sampled_frames: int  # fotogramas que se han mirado de verdad
    source_space: ColorSpaceName | None  # None = no se ha podido deducir
    pixels: Array | None = None  # (M, 3) muestra de pixeles, si se pidio
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 6. Emparejamiento
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class MatchResult:
    """Resultado de llevar un clip al espacio de una referencia."""

    cdl: CDL
    lut: LUT3D | None
    confidence: Confidence
    delta_e_before: float
    delta_e_after: float
    content_mismatch: bool  # True = las dos escenas no son comparables
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 7. Cobertura y diagnostico de ingenieria inversa
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class CoverageMap:
    """Cuantas muestras reales cayeron en cada celda del cubo, y como de
    dispersas estaban. `variance` alta en una celda = ese color no se transforma
    siempre igual, o sea que el grado NO es solo un LUT."""

    counts: Array  # (N, N, N) int32
    variance: Array  # (N, N, N) float32, varianza del residuo por celda
    #: Cuantas muestras reales necesita una celda para no contar como inventada.
    #: El valor vive en `core.umbrales`, no aqui: era una segunda escritura del
    #: mismo criterio, que es la forma exacta del bug de `reverse_puente`.
    min_samples: int = MUESTRAS_MINIMAS_CELDA

    @property
    def size(self) -> int:
        return int(self.counts.shape[0])

    def covered_mask(self) -> Array:
        """(N, N, N) bool: celdas con muestras reales suficientes."""
        return np.asarray(self.counts) >= self.min_samples

    def coverage_fraction(self) -> float:
        """Fraccion de celdas del cubo con datos reales."""
        mask = self.covered_mask()
        return float(mask.sum()) / float(mask.size)


@dataclass(frozen=True)
class Hotspot:
    """Zona de la imagen donde el grado hace algo que un LUT no puede hacer."""

    x: int
    y: int
    w: int
    h: int
    magnitude: float  # residuo medio en la zona, en unidades de dE2000
    #: Etiqueta de que clase de cosa no-LUT es. Valores que emite hoy
    #: `core.reverse`: "vineta", "zona local", "degradado" y "textura" (grano,
    #: enfoque, reduccion de ruido: lo que vive en la alta frecuencia). Es `str`
    #: libre a proposito -- la GUI la imprime tal cual -- pero si anades una,
    #: escribela aqui: esta lista es lo unico que hay para saber que esperar.
    label: str


@dataclass(frozen=True, eq=False)
class ReverseDiagnosis:
    """La pregunta que de verdad importa: cuanto de este grado me puedo llevar."""

    lut_reproducible: float  # 0..1
    is_pure_lut: bool
    spatial_residual: Array | None  # (h, w) float32 normalizado, o None
    hotspots: tuple[Hotspot, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, eq=False)
class ReverseResult:
    """Par original/coloreado -> el grado, en dos capas."""

    cdl: CDL
    lut: LUT3D
    coverage: CoverageMap
    diagnosis: ReverseDiagnosis
    delta_e_mean: float
    delta_e_p95: float
    delta_e_max: float
    confidence: Confidence
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 8. Puente con Resolve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClipRef:
    """Un clip del timeline, tal y como lo ve la app."""

    clip_id: str  # identificador estable dentro de la sesion
    name: str
    track: int
    index: int  # posicion en el timeline, 1-based
    start_frame: int
    end_frame: int
    file_path: str | None = None


@dataclass(frozen=True)
class NodeInfo:
    index: int  # 1-based
    label: str
    enabled: bool
    lut_path: str | None  # ruta RELATIVA, que es lo unico que devuelve la API


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    timeline_name: str
    color_science: str  # p.ej. "DaVinci YRGB Color Managed"
    timeline_color_space: str
    lut_dir: str  # carpeta de LUTs, depende de si es descarga directa o MAS
    resolve_version: str
    is_studio: bool


@dataclass(frozen=True)
class StillRef:
    still_id: str
    album: str
    label: str = ""


class ResolveError(RuntimeError):
    """Cualquier fallo hablando con Resolve. La GUI captura solo esto."""


@runtime_checkable
class ResolveBridge(Protocol):
    """LO UNICO que la app puede pedirle a Resolve.

    Cada metodo de aqui corresponde 1:1 con una llamada VERIFICADA de la API
    (seccion 2 del encargo). Si echas algo en falta, no existe: cambia el
    diseno. Implementaciones: `FakeResolve` (siempre) y `LiveResolve` (solo si
    manana el probe dice que se puede).

    Todos los `node_index` son 1-based.
    """

    # --- conexion y contexto ---
    def is_connected(self) -> bool: ...
    def project_info(self) -> ProjectInfo: ...
    def open_page(self, page: str) -> bool: ...

    # --- clips ---
    def list_clips(self) -> list[ClipRef]: ...
    def list_nodes(self, clip_id: str) -> list[NodeInfo]: ...

    # --- versiones: la red de seguridad, siempre antes de escribir nada ---
    def version_names(self, clip_id: str) -> list[str]: ...
    def current_version(self, clip_id: str) -> str: ...
    def add_version(self, clip_id: str, name: str = VERSION_NAME) -> bool: ...
    def load_version(self, clip_id: str, name: str) -> bool: ...

    # --- escritura de color ---
    def set_cdl(self, clip_id: str, node_index: int, cdl: CDL) -> bool: ...
    def set_lut(self, clip_id: str, node_index: int, lut_rel_path: str) -> bool: ...
    def get_lut(self, clip_id: str, node_index: int) -> str | None: ...
    def set_node_enabled(self, clip_id: str, node_index: int, enabled: bool) -> bool: ...
    def copy_grades(self, source_clip_id: str, target_clip_ids: list[str]) -> bool: ...
    def reset_all_grades(self, clip_id: str) -> bool: ...
    def refresh_lut_list(self) -> bool: ...

    # --- grupos de color: donde vive el nodo 3 si se hace por proyecto ---
    def color_groups(self) -> list[str]: ...
    def add_color_group(self, name: str) -> bool: ...
    def delete_color_group(self, name: str) -> bool: ...
    def set_group_post_clip_lut(self, group: str, node_index: int, lut_rel_path: str) -> bool: ...

    # --- galeria / stills ---
    def grab_still(self) -> StillRef: ...
    def gallery_albums(self) -> list[str]: ...
    def create_powergrade_album(self, name: str) -> bool: ...
    def export_stills(
        self, stills: list[StillRef], directory: str, prefix: str, fmt: str
    ) -> list[str]: ...


# ---------------------------------------------------------------------------
# 9. Bundle de proyecto (.sidebcolor)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ColorSession:
    """Lo que se guarda y se abre. El agente D lo serializa a un .sidebcolor
    (zip: session.json + luts/*.cube + miniaturas opcionales)."""

    project_name: str
    created_at: str  # ISO 8601
    app_version: str
    reference_clip_id: str | None
    analyses: dict[str, ClipAnalysis] = field(default_factory=dict)
    matches: dict[str, MatchResult] = field(default_factory=dict)
    look_lut: LUT3D | None = None
    notes: tuple[str, ...] = ()


__all__ = [
    "WORKING_SPACE",
    "LUMA_REC709",
    "LUT_SIZE_DEFAULT",
    "LUT_SIZES_SOPORTADOS",
    "PERCENTILE_LEVELS",
    "SAT_BINS",
    "FINGERPRINT_LEN",
    "VERSION_NAME",
    "NODE_NORMALIZACION",
    "NODE_BALANCE",
    "NODE_LOOK",
    "ColorSpaceName",
    "ConfidenceLevel",
    "ColorStats",
    "CDL",
    "LUT3D",
    "Confidence",
    "CONFIDENCE_ALTA",
    "CONFIDENCE_MEDIA",
    "confidence_level",
    "ClipAnalysis",
    "MatchResult",
    "CoverageMap",
    "Hotspot",
    "ReverseDiagnosis",
    "ReverseResult",
    "ClipRef",
    "NodeInfo",
    "ProjectInfo",
    "StillRef",
    "ResolveError",
    "ResolveBridge",
    "ColorSession",
]
