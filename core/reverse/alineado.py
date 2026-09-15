"""Alineado de la pareja original / coloreado.

POR QUE EXISTE ESTE ARCHIVO
---------------------------
Todo lo demas de `core.reverse` se apoya en una suposicion muy fuerte: que el
pixel (y, x) del original y el pixel (y, x) del coloreado son **el mismo punto
de la escena**. Si eso no se cumple, la nube de correspondencias que acumulamos
deja de ser una funcion de color y pasa a ser una nube de pares al azar; el LUT
sale suavizado hacia la media y el diagnostico dice "aqui hay algo espacial"
cuando lo unico que hay es un pixel de desplazamiento.

Asi que aqui se hacen tres cosas, y solo tres:

1. **Igualar resolucion.** Si vienen a tamanos distintos se reescala al mas
   pequeno de los dos. Reescalar hacia arriba inventa detalle y el detalle
   inventado se mete en el LUT como si fuera medida.
2. **Estimar un desplazamiento entero** por correlacion de fase.
3. **Verificarlo de verdad antes de aplicarlo**, comparando la correlacion de
   los gradientes con y sin el desplazamiento. La correlacion de fase se
   equivoca, y aqui una equivocacion sale cara.

LO QUE NO HACE, Y HAY QUE SABERLO
---------------------------------
- No corrige rotacion, escala local, ni desplazamientos subpixel. Un
  desplazamiento de medio pixel se queda sin corregir y se nota en el residuo.
- No corrige desplazamientos mayores que `MAX_DESPLAZAMIENTO_PX`. Por encima de
  eso lo mas probable es que no sean el mismo plano, y desplazar 200 pixeles
  una imagen para que "encaje" es como se fabrica un resultado bonito y falso.
- Cuando no se fia, **no corrige y lo dice** (`info["fiable"] = False`). Bajar
  la confianza es responsabilidad de quien llama; aqui solo se informa.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "MAX_DESPLAZAMIENTO_PX",
    "MARGEN_MEJORA",
    "UMBRAL_CORRELACION_FIABLE",
    "alinear",
    "correlacion_de_gradientes",
    "redimensionar",
]

#: Por encima de esto no se corrige: no es un desencuadre, es otro plano.
MAX_DESPLAZAMIENTO_PX: int = 32

#: Cuanto tiene que mejorar la correlacion de gradientes para aplicar el
#: desplazamiento. Sin margen, el ruido decide y se desplaza por nada.
MARGEN_MEJORA: float = 0.01

#: Por debajo de esta correlacion de gradientes decimos que no nos fiamos de que
#: sean el mismo encuadre. Medido: el mismo plano da >0.9; un retrato contra un
#: exterior da ~0.0.
UMBRAL_CORRELACION_FIABLE: float = 0.50


def redimensionar(img: np.ndarray, alto: int, ancho: int) -> np.ndarray:
    """Reescala bilinealmente (alto, ancho, 3). Numpy puro, sin OpenCV.

    Se usa el convenio de centro de pixel (`+0.5`), que es el de OpenCV y el de
    ffmpeg; con el convenio de esquina la imagen se desplaza medio pixel y eso
    es justo lo que este archivo intenta evitar.
    """
    arr = np.asarray(img, dtype=np.float64)
    h, w = arr.shape[:2]
    if (h, w) == (int(alto), int(ancho)):
        return arr.astype(np.float32)
    y = np.clip((np.arange(alto) + 0.5) * h / alto - 0.5, 0.0, h - 1.0)
    x = np.clip((np.arange(ancho) + 0.5) * w / ancho - 0.5, 0.0, w - 1.0)
    y0 = np.floor(y).astype(np.int64)
    x0 = np.floor(x).astype(np.int64)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)
    fy = (y - y0)[:, None, None]
    fx = (x - x0)[None, :, None]
    arriba = arr[y0][:, x0] * (1 - fx) + arr[y0][:, x1] * fx
    abajo = arr[y1][:, x0] * (1 - fx) + arr[y1][:, x1] * fx
    return (arriba * (1 - fy) + abajo * fy).astype(np.float32)


def _luma(img: np.ndarray) -> np.ndarray:
    """(h, w, 3) -> (h, w) float64 con los no finitos puestos a la media."""
    arr = np.asarray(img, dtype=np.float64)
    y = arr.mean(axis=2)
    finito = np.isfinite(y)
    if not finito.all():
        relleno = float(y[finito].mean()) if finito.any() else 0.0
        y = np.where(finito, y, relleno)
    return y


def _gradiente(y: np.ndarray) -> np.ndarray:
    """Magnitud del gradiente, que es lo que de verdad dice si dos imagenes
    estan encajadas: el color puede cambiar entero con el grado, los bordes no
    se mueven.

    Con menos de dos pixeles en algun eje no hay gradiente que calcular y
    `np.gradient` **lanza**. Se devuelven ceros: una imagen de 1 px no tiene
    bordes, y eso no es un error, es un dato (ver `correlacion_de_gradientes`).
    """
    if min(y.shape[:2]) < 2:
        return np.zeros_like(y)
    gy, gx = np.gradient(y)
    return np.sqrt(gy * gy + gx * gx)


def correlacion_de_gradientes(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson entre las magnitudes de gradiente de dos imagenes ya recortadas.

    1.0 = los bordes caen exactamente en el mismo sitio. Es invariante a
    cualquier grado que no mueva los bordes, o sea a cualquier grado.

    Con una imagen de menos de 8 pixeles (o de menos de 2 en algun eje) se
    devuelve **0.0**, que es lo que hay que devolver: no es que los bordes no
    encajen, es que no hay bordes que comparar, y quien llama tiene que tratar
    eso como "no me fio" y no como "encaja perfecto". `alinear` lo hace.
    """
    ga = _gradiente(_luma(a)).ravel()
    gb = _gradiente(_luma(b)).ravel()
    if ga.size < 8:
        return 0.0
    ga = ga - ga.mean()
    gb = gb - gb.mean()
    den = float(np.sqrt((ga @ ga) * (gb @ gb)))
    if den <= 1e-30:
        return 0.0
    return float(ga @ gb / den)


def _correlacion_de_fase(a: np.ndarray, b: np.ndarray) -> tuple[int, int, float]:
    """Desplazamiento entero (dy, dx) de `b` respecto de `a`, y fuerza del pico.

    Se correlaciona sobre el gradiente y con ventana de Hann: asi la estimacion
    no depende de que el grado haya cambiado el brillo medio, que es
    exactamente lo que pasa siempre en este modulo.
    """
    ga = _gradiente(_luma(a))
    gb = _gradiente(_luma(b))
    h, w = ga.shape
    ventana = np.hanning(h)[:, None] * np.hanning(w)[None, :]
    fa = np.fft.rfft2((ga - ga.mean()) * ventana)
    fb = np.fft.rfft2((gb - gb.mean()) * ventana)
    cruz = fa * np.conj(fb)
    cruz /= np.maximum(np.abs(cruz), 1e-12)
    corr = np.fft.irfft2(cruz, s=(h, w))
    idx = int(np.argmax(corr))
    iy, ix = divmod(idx, w)
    pico = float(corr.flat[idx])
    sigma = float(corr.std())
    fuerza = pico / sigma if sigma > 1e-30 else 0.0
    dy = iy if iy <= h // 2 else iy - h
    dx = ix if ix <= w // 2 else ix - w
    # El signo: `corr` tiene su maximo en el desplazamiento que hay que aplicar
    # a `b` para llegar a `a`. Lo devolvemos como "b esta desplazado (dy,dx)".
    return int(dy), int(dx), fuerza


def _recortar(a: np.ndarray, b: np.ndarray, dy: int, dx: int) -> tuple[np.ndarray, np.ndarray]:
    """Recorta las dos al solape suponiendo `b[y+dy, x+dx] ~ grado(a[y, x])`."""
    h, w = a.shape[:2]
    ay0, ay1 = max(0, -dy), min(h, h - dy)
    ax0, ax1 = max(0, -dx), min(w, w - dx)
    if ay1 <= ay0 or ax1 <= ax0:
        return a, b
    return (
        a[ay0:ay1, ax0:ax1],
        b[ay0 + dy : ay1 + dy, ax0 + dx : ax1 + dx],
    )


def alinear(original: np.ndarray, coloreado: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Deja las dos imagenes con la misma forma y, si puede, encajadas.

    Devuelve `(original_alineado, coloreado_alineado, info)`. `info` trae:

    ``escalado``        True si hubo que reescalar alguna de las dos.
    ``forma_original``  formas de entrada, tal cual llegaron.
    ``desplazamiento``  (dy, dx) que se ha APLICADO (0,0 si no se corrigio).
    ``desplazamiento_detectado``  lo que dijo la correlacion de fase.
    ``corregido``       si se aplico el desplazamiento.
    ``fuerza_pico``     pico/sigma de la correlacion de fase.
    ``correlacion``     correlacion de gradientes final, 0..1.
    ``fiable``          False = no garantizo que sean el mismo encuadre.
    ``notas``           frases en castellano, listas para la GUI.
    """
    a = np.asarray(original, dtype=np.float32)
    b = np.asarray(coloreado, dtype=np.float32)
    for nombre, arr in (("original", a), ("coloreado", b)):
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError(f"{nombre}: esperaba (alto, ancho, 3), llego {arr.shape}")
        if arr.shape[0] < 1 or arr.shape[1] < 1:
            raise ValueError(f"{nombre}: imagen vacia {arr.shape}")

    notas: list[str] = []
    info: dict = {
        "forma_original": (tuple(a.shape), tuple(b.shape)),
        "escalado": False,
        "desplazamiento": (0, 0),
        "desplazamiento_detectado": (0, 0),
        "corregido": False,
        "fuerza_pico": 0.0,
        "correlacion": 0.0,
        "fiable": True,
    }

    # 1. Resolucion. Al mas pequeno: subir de resolucion inventa detalle y el
    #    detalle inventado acaba dentro del LUT como si fuera una medida.
    if a.shape[:2] != b.shape[:2]:
        ha, wa = a.shape[:2]
        hb, wb = b.shape[:2]
        alto, ancho = (ha, wa) if ha * wa <= hb * wb else (hb, wb)
        a = redimensionar(a, alto, ancho)
        b = redimensionar(b, alto, ancho)
        info["escalado"] = True
        notas.append(
            f"Las dos imagenes venian a tamanos distintos ({ha}x{wa} y {hb}x{wb}); "
            f"he reescalado las dos a {alto}x{ancho}, que es la mas pequena."
        )

    # 2. Desplazamiento. Solo tiene sentido con superficie suficiente.
    h, w = a.shape[:2]
    if h >= 16 and w >= 16:
        dy, dx, fuerza = _correlacion_de_fase(a, b)
        info["desplazamiento_detectado"] = (dy, dx)
        info["fuerza_pico"] = fuerza
        corr_cero = correlacion_de_gradientes(a, b)
        if (dy, dx) != (0, 0) and max(abs(dy), abs(dx)) <= MAX_DESPLAZAMIENTO_PX:
            # 3. Verificarlo: no nos fiamos de la FFT, lo medimos.
            a_d, b_d = _recortar(a, b, dy, dx)
            corr_desp = correlacion_de_gradientes(a_d, b_d)
            if corr_desp > corr_cero + MARGEN_MEJORA:
                a, b = a_d, b_d
                info["desplazamiento"] = (dy, dx)
                info["corregido"] = True
                info["correlacion"] = corr_desp
                notas.append(
                    f"He detectado y corregido un desplazamiento de {dy:+d} filas y "
                    f"{dx:+d} columnas (la correlacion de bordes sube de "
                    f"{corr_cero:.3f} a {corr_desp:.3f})."
                )
            else:
                info["correlacion"] = corr_cero
                notas.append(
                    f"La correlacion de fase sugeria un desplazamiento de ({dy:+d}, {dx:+d}) "
                    f"pero no mejora el encaje de bordes ({corr_desp:.3f} frente a "
                    f"{corr_cero:.3f}); lo he descartado y he dejado las imagenes como venian."
                )
        else:
            info["correlacion"] = corr_cero
            if (dy, dx) != (0, 0):
                notas.append(
                    f"La correlacion de fase sugeria un desplazamiento de ({dy:+d}, {dx:+d}), "
                    f"mas de {MAX_DESPLAZAMIENTO_PX} px. No lo corrijo: a esa distancia lo mas "
                    f"probable es que no sean el mismo plano."
                )
    else:
        info["correlacion"] = correlacion_de_gradientes(a, b)
        notas.append(
            "Imagen demasiado pequena para estimar desplazamiento; doy por bueno el encuadre."
        )

    if info["correlacion"] < UMBRAL_CORRELACION_FIABLE:
        info["fiable"] = False
        notas.append(
            f"NO puedo garantizar que las dos imagenes sean el mismo encuadre: los bordes solo "
            f"correlan {info['correlacion']:.3f} (por debajo de {UMBRAL_CORRELACION_FIABLE:.2f}). "
            f"Todo lo que venga despues se apoya en un emparejamiento pixel a pixel que puede no "
            f"serlo."
        )

    info["notas"] = tuple(notas)
    return np.ascontiguousarray(a), np.ascontiguousarray(b), info
