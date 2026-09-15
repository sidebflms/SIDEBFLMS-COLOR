"""REVISION OLA 1 - agente G sobre `core/io/` (agente D).

Tests escritos para romper, no para confirmar. Lo que se ataca:

* El orden de los ejes a traves de un fichero .cube DE VERDAD (no en memoria):
  un LUT que solo toca el rojo tiene que seguir tocando el rojo al releerlo.
* Ficheros hostiles: tamaño declarado que no cuadra, tamaño gigante, binario,
  vacio, BOM, UTF-16, CRLF, cabeceras contradictorias.
* Zip-slip y zip-bomba en el `.sidebcolor`, con los zips FABRICADOS A MANO,
  incluido uno cuyo indice central MIENTE sobre el tamaño descomprimido (que es
  justo lo que el autor dice que su defensa cubre).
* `.npy` con pickle dentro, que es el agujero de ejecucion de codigo de verdad.
* Billion laughs y XXE en el CDL, incluido el intento de colarlos en UTF-16
  para esquivar el `re.search` de `<!DOCTYPE`.
* Cuantos FALSOS POSITIVOS da el detector de banding sobre LUT legitimos. El
  autor admite que su umbral es sensible; aqui esta el numero.
"""

from __future__ import annotations

import io
import json
import os
import struct
import warnings
import zipfile

import numpy as np
import pytest

from core.contracts import CDL, LUT3D, LUT_SIZES_SOPORTADOS
from core.io import (
    CODIGO_BANDING,
    CODIGO_GAMUT,
    MAX_ENTRADAS,
    ErrorBundle,
    ErrorFormatoCDL,
    ErrorFormatoCube,
    abrir_sesion,
    cube_a_texto,
    cube_desde_texto,
    escribir_cube,
    hald_image,
    leer_cdl,
    leer_cube,
    lut_from_hald,
    qc_lut,
)
from core.io.qc import SALTO_MINIMO_BANDING, UMBRAL_BANDING

# ---------------------------------------------------------------------------
# Utilidades: fabricar LUT legitimos
# ---------------------------------------------------------------------------


def _lut_separable(n: int, f) -> LUT3D:
    """Un LUT que aplica la misma curva `f` a los tres canales por separado."""
    x = np.linspace(0.0, 1.0, n)
    r, g, b = np.meshgrid(x, x, x, indexing="ij")
    return LUT3D(table=np.stack([f(r), f(g), f(b)], -1).astype(np.float32))


def _sesion_minima() -> dict:
    return {
        "formato": "sidebcolor",
        "formato_version": 1,
        "sesion": {
            "project_name": "REVISION",
            "created_at": "2026-09-15",
            "app_version": "0.1.0",
            "reference_clip_id": None,
            "analyses": {},
            "matches": {},
            "look_lut": None,
            "notes": [],
        },
    }


# ---------------------------------------------------------------------------
# 1. Los ejes, a traves de un fichero de verdad
# ---------------------------------------------------------------------------


def test_un_lut_que_solo_toca_el_rojo_sigue_tocando_el_rojo_tras_ir_al_disco(tmp_path):
    """La prueba de fuego de la convencion 4, pasando por el disco.

    Se fabrica un LUT en el que **solo** el canal rojo depende de la entrada
    roja, y verde y azul son la identidad. Se escribe a `.cube`, se relee, y se
    comprueba celda a celda que sigue siendo asi. Si alguien invierte la
    permutacion, este test lo caza: el LUT pasaria a tocar el azul.
    """
    n = 17
    x = np.linspace(0.0, 1.0, n)
    r, g, b = np.meshgrid(x, x, x, indexing="ij")
    tabla = np.stack([r * 0.5, g, b], -1).astype(np.float32)
    ruta = escribir_cube(LUT3D(table=tabla, title="solo rojo"), tmp_path / "rojo.cube", decimales=None)
    vuelta = leer_cube(ruta)

    np.testing.assert_allclose(vuelta.table, tabla, atol=1e-6)
    # Subir el indice ROJO baja la salida roja a la mitad y no mueve las otras.
    assert vuelta.table[-1, 0, 0, 0] == pytest.approx(0.5, abs=1e-6)
    assert vuelta.table[-1, 0, 0, 2] == pytest.approx(0.0, abs=1e-6)
    # Y subir el indice AZUL sube la salida azul, no la roja.
    assert vuelta.table[0, 0, -1, 2] == pytest.approx(1.0, abs=1e-6)
    assert vuelta.table[0, 0, -1, 0] == pytest.approx(0.0, abs=1e-6)


def test_en_el_fichero_el_rojo_varia_mas_rapido_y_en_el_hald_el_azul(tmp_path):
    """Los dos formatos usan ordenes OPUESTOS, y eso es correcto. Aqui se ata.

    Si alguien "unifica" los dos ordenes porque le parecen una errata, uno de
    los dos productos sale con el rojo y el azul cambiados.
    """
    n = 3
    tabla = np.zeros((n, n, n, 3), dtype=np.float32)
    tabla[1, 0, 0] = [1.0, 0.0, 0.0]  # segunda muestra del eje ROJO
    lut = LUT3D(table=tabla)

    filas = [
        linea.split()
        for linea in cube_a_texto(lut, decimales=1).splitlines()
        if linea and not linea[0].isalpha() and "_" not in linea
    ]
    # En el fichero el rojo varia mas rapido: la celda [1,0,0] es la LINEA 1.
    assert filas[1] == ["1.0", "0.0", "0.0"], filas[:4]

    # En el HALD el azul varia mas rapido: la celda [1,0,0] es el pixel n*n = 9.
    plano = hald_image(lut).reshape(-1, 3)
    assert plano[n * n].tolist() == [1.0, 0.0, 0.0]
    assert lut_from_hald(hald_image(lut), n).table.tobytes() == tabla.tobytes()


# ---------------------------------------------------------------------------
# 2. Ficheros .cube hostiles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("vacio", b""),
        ("solo espacios en blanco", b"   \n\n\t\n"),
        ("binario con bytes nulos", b"\x00\x01\x02" * 100),
        ("UTF-16 con BOM", "LUT_3D_SIZE 2\n".encode("utf-16")),
        ("LUT_3D_SIZE 4096 (pediria 824 GB)", b"LUT_3D_SIZE 4096\n0 0 0\n"),
        ("LUT_3D_SIZE 0", b"LUT_3D_SIZE 0\n"),
        ("LUT_3D_SIZE -3", b"LUT_3D_SIZE -3\n"),
        ("LUT_3D_SIZE 1 (nada que interpolar)", b"LUT_3D_SIZE 1\n0 0 0\n"),
        ("LUT_3D_SIZE 'treinta y tres'", b"LUT_3D_SIZE treinta y tres\n"),
        ("declara 8 filas y trae 7", b"LUT_3D_SIZE 2\n" + b"0 0 0\n" * 7),
        ("declara 8 filas y trae 9", b"LUT_3D_SIZE 2\n" + b"0 0 0\n" * 9),
        ("una fila con nan", b"LUT_3D_SIZE 2\n" + b"0 0 0\n" * 7 + b"nan nan nan\n"),
        ("una fila con inf", b"LUT_3D_SIZE 2\n" + b"0 0 0\n" * 7 + b"inf 0 0\n"),
        ("una fila con 4 numeros", b"LUT_3D_SIZE 2\n0 0 0 0\n" + b"0 0 0\n" * 7),
        ("3D y 1D a la vez", b"LUT_3D_SIZE 2\nLUT_1D_SIZE 8\n" + b"0 0 0\n" * 8),
        ("sin ninguna cabecera", b"0 0 0\n" * 8),
        ("el tamaño va DESPUES de los datos", b"0 0 0\n" * 8 + b"LUT_3D_SIZE 2\n"),
        ("DOMAIN_MIN por encima de DOMAIN_MAX", b"LUT_3D_SIZE 2\nDOMAIN_MIN 1 1 1\nDOMAIN_MAX 0 0 0\n" + b"0 0 0\n" * 8),
        ("DOMAIN_MIN con nan", b"LUT_3D_SIZE 2\nDOMAIN_MIN nan nan nan\n" + b"0 0 0\n" * 8),
        ("acento en latin-1", 'TITLE "graduaci\xf3n"\nLUT_3D_SIZE 2\n'.encode("latin-1") + b"0 0 0\n" * 8),
    ],
)
def test_un_cube_hostil_falla_en_castellano_y_nunca_con_un_traceback(nombre, contenido, tmp_path):
    """Veinte ficheros rotos. Ninguno puede levantar nada que no sea `ErrorIO`.

    Es la regla de la casa del modulo: lo que viene de fuera falla en castellano.
    Un `ValueError` de numpy o un `MemoryError` serian un fallo de la revision.
    """
    ruta = tmp_path / "hostil.cube"
    ruta.write_bytes(contenido)
    with pytest.raises(ErrorFormatoCube) as exc:
        leer_cube(ruta)
    assert str(exc.value), f"{nombre}: el error no dice nada"


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("BOM de UTF-8 delante", b"\xef\xbb\xbfLUT_3D_SIZE 2\n" + b"0 0 0\n" * 8),
        ("saltos de linea de Windows", b"LUT_3D_SIZE 2\r\n" + b"0 0 0\r\n" * 8),
        ("saltos de linea de Mac clasico", b"LUT_3D_SIZE 2\r" + b"0 0 0\r" * 8),
        ("separado por comas", b"# un comentario\nLUT_3D_SIZE 2\n" + b"0,0,0\n" * 8),
        ("separado por punto y coma", b"LUT_3D_SIZE 2\n" + b"0;0;0\n" * 8),
        ("tabuladores", b"LUT_3D_SIZE\t2\n" + b"0\t0\t0\n" * 8),
    ],
)
def test_un_cube_raro_pero_legitimo_si_se_lee(nombre, contenido, tmp_path):
    """La otra cara: lo que es raro pero legal NO puede rechazarse.

    Un lector demasiado estricto es tan inutil como uno que se traga cualquier
    cosa: si Mario no puede abrir el `.cube` que le manda el cliente, da igual
    lo bien defendido que este.
    """
    ruta = tmp_path / "raro.cube"
    ruta.write_bytes(contenido)
    assert leer_cube(ruta).size == 2, nombre


def test_un_cube_con_dos_LUT_3D_SIZE_contradictorios_se_traga_el_ultimo(tmp_path):
    """BUG: dos cabeceras de tamaño distintas y el lector elige en silencio.

    El modulo rechaza `LUT_3D_SIZE` y `LUT_1D_SIZE` a la vez con un mensaje
    perfecto ("no se cual de los dos leer"), pero un fichero con DOS
    `LUT_3D_SIZE` distintos no le parece ambiguo: se queda con el ultimo y lee
    tan contento. Es exactamente la misma ambiguedad y el mismo riesgo (un
    fichero cortado y pegado por un exportador roto), y aqui no avisa nadie.

    ROJO a proposito.
    """
    contenido = b"LUT_3D_SIZE 2\nLUT_3D_SIZE 3\n" + b"0.5 0.5 0.5\n" * 27
    ruta = tmp_path / "doble.cube"
    ruta.write_bytes(contenido)
    with pytest.raises(ErrorFormatoCube, match="(?i)dos|ambig|cual"):
        leer_cube(ruta)


def test_un_lut_de_un_solo_color_se_escribe_pero_el_qc_lo_para(tmp_path):
    """Caso frontera: el LUT que aplasta la imagen entera a un color.

    Escribirlo es legal (el formato lo admite) y releerlo tiene que devolver lo
    mismo. Quien tiene que gritar es el QC, y grita con gravedad 'error'.
    """
    plano = LUT3D(table=np.full((17, 17, 17, 3), 0.42, dtype=np.float32))
    vuelta = leer_cube(escribir_cube(plano, tmp_path / "plano.cube", decimales=None))
    assert vuelta.table.tobytes() == plano.table.tobytes()

    informe = qc_lut(plano)
    assert not informe.ok
    assert informe.hay_errores
    assert "lut_plano" in informe.codigos()


def test_un_cube_con_nan_no_se_puede_escribir(tmp_path):
    """Un NaN en la tabla revienta Resolve. Tiene que morir en la escritura."""
    tabla = np.asarray(LUT3D.identity(17).table).copy()
    tabla[3, 4, 5, 1] = np.nan
    with pytest.raises(ErrorFormatoCube, match="no finitos"):
        escribir_cube(LUT3D(table=tabla), tmp_path / "nan.cube")
    assert not (tmp_path / "nan.cube").exists(), "ha dejado un fichero a medias"


def test_escribir_en_una_carpeta_que_no_existe_lanza_en_vez_de_fabricarla(tmp_path):
    """Convencion 7: `core/` no fabrica arboles de carpetas por su cuenta."""
    destino = tmp_path / "no" / "existe" / "x.cube"
    with pytest.raises(ErrorFormatoCube, match="no existe"):
        escribir_cube(LUT3D.identity(2), destino)
    assert not destino.parent.exists()
    escribir_cube(LUT3D.identity(2), destino, crear_directorios=True)
    assert destino.exists()


# ---------------------------------------------------------------------------
# 3. El QC: cuantos falsos positivos da de verdad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", LUT_SIZES_SOPORTADOS + (2,))
def test_la_identidad_pasa_limpia_en_2_17_33_y_65(n):
    """La regla de oro del QC. Si esto se rompe, el modulo no sirve."""
    informe = qc_lut(LUT3D.identity(n))
    assert informe.ok, informe.resumen()


def test_cuantos_falsos_positivos_da_el_qc_sobre_luts_legitimos():
    """El numero que pide la revision, medido sobre seis LUT legitimos.

    Cuatro de los seis pasan limpios en los tres tamaños. Los que NO pasan son:

    * **la curva de gamma de salida** (x**(1/2.2), que es el LUT mas comun que
      existe): banding en 17, 33 y 65;
    * **un CDL realista** convertido a LUT: aviso de gamut, que es correcto por
      diseño (se sale de 0..1 y Resolve recorta).

    RONDA 2 — **este test estaba de mas y lo relajo yo**. En la ronda 1 exigia
    `sucios[...] == [17, 33, 65]`, o sea que la gamma saliera sucia en los tres
    tamaños. D me hizo notar, con razon, que eso le cerraba una de las dos
    salidas que yo mismo le habia propuesto (excluir el primer intervalo de la
    rejilla dejaria la gamma limpia y este test se pondria rojo). Un test de
    revision tiene que afirmar **el defecto**, no la implementacion concreta del
    defecto.

    Asi que ahora afirmo solo lo que de verdad creo que tiene que cumplirse:
    los cuatro limpios siguen limpios, y si la gamma se marca, se marca por
    banding y por nada mas. El recuento exacto se mide y se enseña en el mensaje
    del assert, para que quede en la salida de pytest sin congelar nada.
    """
    legitimos = {
        "identidad": lambda t: t,
        "contraste suave (smoothstep)": lambda t: t * t * (3.0 - 2.0 * t),
        "curva en S suave": lambda t: np.clip(
            0.5 + (t - 0.5) * 1.25 + 0.15 * np.sin(2 * np.pi * (t - 0.5)) / (2 * np.pi), 0.0, 1.0
        ),
        "gamma 2.2 (pantalla -> lineal)": lambda t: np.power(np.maximum(t, 0.0), 2.2),
        "gamma de salida (lineal -> pantalla)": lambda t: np.power(np.maximum(t, 0.0), 1.0 / 2.2),
    }
    limpios: dict[str, list[int]] = {}
    sucios: dict[str, list[int]] = {}
    for nombre, f in legitimos.items():
        for n in LUT_SIZES_SOPORTADOS:
            informe = qc_lut(_lut_separable(n, f))
            (limpios if informe.ok else sucios).setdefault(nombre, []).append(n)

    # Lo que NO se negocia: estos cuatro son limpios en los tres tamaños.
    for debe_estar_limpio in (
        "identidad",
        "contraste suave (smoothstep)",
        "curva en S suave",
        "gamma 2.2 (pantalla -> lineal)",
    ):
        assert debe_estar_limpio not in sucios, (
            f"FALSO POSITIVO NUEVO: '{debe_estar_limpio}' se marca en {sucios[debe_estar_limpio]}. "
            f"Recuento completo: {sucios}"
        )

    # La gamma de salida: hoy se marca en los tres. No lo congelo (D puede
    # decidir excluir el primer intervalo y entonces saldria limpia, que seria
    # una mejora); lo que si exijo es que si se marca sea SOLO por banding.
    marcados = sucios.get("gamma de salida (lineal -> pantalla)", [])
    for n in marcados:
        assert qc_lut(_lut_separable(n, legitimos["gamma de salida (lineal -> pantalla)"])).codigos() == (
            CODIGO_BANDING,
        ), f"la gamma de salida con N={n} se marca por algo que no es banding"

    # Un CDL realista convertido a LUT: solo aviso de gamut, nunca de banding.
    cdl = CDL(slope=(1.05, 1.0, 0.95), offset=(0.01, 0.0, -0.01), power=(0.95, 1.0, 1.05), saturation=1.1)
    for n in LUT_SIZES_SOPORTADOS:
        base = LUT3D.identity(n)
        tabla = cdl.apply(np.asarray(base.table).reshape(-1, 3)).reshape(n, n, n, 3)
        codigos = qc_lut(LUT3D(table=tabla.astype(np.float32))).codigos()
        assert CODIGO_BANDING not in codigos, f"banding falso en el CDL con N={n}"
        assert codigos == (CODIGO_GAMUT,)


@pytest.mark.parametrize("n", LUT_SIZES_SOPORTADOS)
def test_el_aviso_de_banding_de_la_gamma_apunta_al_primer_intervalo_y_va_agrupado(n):
    """Diseccion del falso positivo: donde esta, y que el recuento ya no engaña.

    En `x**(1/2.2)` el unico punto marcado es el indice 0 del eje, o sea el
    primer escalon de la rejilla, pegado al negro, donde la curva tiene
    pendiente infinita. Se marca en CADA una de las n*n lineas paralelas y en
    los 3 ejes.

    RONDA 1: `metricas['celdas_con_banding']` salia 12.675 en N=65 y el informe
    listaba 20 avisos, cuando es **una sola posicion de rejilla**.

    RONDA 2: D lo ha agrupado por eje. Ahora se listan 3 problemas (uno por eje)
    en vez de 20, el mensaje dice explicitamente "en el primer intervalo de la
    rejilla (pegado al negro)" y hay una metrica nueva, `escalones_de_banding`.
    **No congelo ninguna de las dos cifras** (fue el error que cometi en la
    ronda 1): afirmo que van agrupadas y que apuntan donde tienen que apuntar.
    """
    lut = _lut_separable(n, lambda t: np.power(np.maximum(t, 0.0), 1.0 / 2.2))
    informe = qc_lut(lut)
    avisos = informe.por_codigo(CODIGO_BANDING)

    # Agrupado: como mucho uno por eje, no uno por linea de la rejilla.
    assert 0 < len(avisos) <= 3, f"N={n}: {len(avisos)} avisos de banding, esperaba <= 3"
    assert len({a.eje for a in avisos}) == len(avisos), "hay dos avisos del mismo eje"

    # Y cada uno apunta al primer intervalo de su eje.
    for a in avisos:
        assert a.celda[a.eje] == 1, f"el aviso del eje {a.eje} apunta a {a.celda}"
        assert a.gravedad == "aviso"

    # La causa, medida a mano sin pasar por el modulo: solo el indice 0.
    tabla = np.asarray(lut.table, dtype=np.float64)
    d1 = np.diff(tabla[..., 0], axis=0)
    d2 = np.abs(np.diff(d1, axis=0))
    escala = float(np.median(np.abs(d1)))
    marcados = (d2 > UMBRAL_BANDING * max(escala, 1e-6)) & (d2 > SALTO_MINIMO_BANDING)
    assert sorted(set(np.argwhere(marcados)[:, 0].tolist())) == [0]


def test_el_qc_encuentra_el_escalon_de_verdad_cuando_lo_hay():
    """Contrapeso: el detector tiene que seguir cazando un escalon real.

    Un salto de 0.3 en mitad de la rampa es una banda evidentisima. Si por
    calmar los falsos positivos alguien sube el umbral hasta que esto pase
    limpio, el detector deja de servir.
    """
    n = 33
    x = np.linspace(0.0, 1.0, n)
    curva = x.copy()
    curva[n // 2 :] += 0.3
    lut = _lut_separable(n, lambda t: np.interp(t, x, np.clip(curva, 0.0, 1.5)))
    codigos = qc_lut(lut).codigos()
    assert CODIGO_BANDING in codigos


def test_el_qc_no_revienta_con_un_lut_lleno_de_nan_ni_con_uno_de_tamaño_2():
    """Casos frontera del propio QC: NaN por todas partes y la rejilla minima."""
    nan = LUT3D(table=np.full((17, 17, 17, 3), np.nan, dtype=np.float32))
    informe = qc_lut(nan)
    assert informe.hay_errores
    assert "no_finito" in informe.codigos()
    assert informe.metricas["no_finitos"] == 17**3 * 3
    # Con 2 muestras por eje no hay segunda derivada: no puede haber banding.
    assert CODIGO_BANDING not in qc_lut(LUT3D.identity(2)).codigos()


# ---------------------------------------------------------------------------
# 4. El `.sidebcolor`: zip-slip y zip-bomba fabricados a mano
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta_mala",
    [
        "../../../../etc/passwd",
        "/etc/passwd",
        "luts/../../fuera.cube",
        "C:/Windows/system32/x.cube",
        "luts\\..\\..\\fuera.cube",
        "./x.cube",
        "luts//x.cube",
    ],
)
def test_zip_slip_con_el_zip_fabricado_a_mano(ruta_mala, tmp_path):
    """Siete rutas hostiles metidas en el zip a mano, no con la API del modulo.

    El autor dice que rechaza el archivo ENTERO si cualquier entrada es
    peligrosa, aunque hoy no se extraiga nada al disco. Se comprueba de verdad.
    """
    ruta = tmp_path / "slip.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(_sesion_minima()))
        zf.writestr(ruta_mala, "cualquier cosa")
    with pytest.raises(ErrorBundle, match="(?i)peligrosa"):
        abrir_sesion(ruta)


def test_zip_bomba_con_el_indice_honesto(tmp_path):
    """300 MB declarados en 300 KB de zip. Se corta antes de descomprimir."""
    ruta = tmp_path / "bomba.sidebcolor"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", json.dumps(_sesion_minima()))
        zf.writestr("arrays/gorda.npy", b"\0" * (300 * 1024 * 1024))
    assert ruta.stat().st_size < 2 * 1024 * 1024, "el zip de ataque tiene que ser pequeño"
    with pytest.raises(ErrorBundle, match="(?i)bomba"):
        abrir_sesion(ruta)


def test_zip_bomba_con_el_indice_MENTIROSO(tmp_path):
    """El ataque que el autor dice cubrir: el indice del zip miente.

    Se fabrica un zip con una entrada de 300 MB y se parchea A MANO el campo
    `uncompressed size` del directorio central para que diga 10 bytes. Asi
    `_revisar_zip` (que suma lo declarado) no ve nada raro y la unica defensa
    que queda es el tope duro de `_leer_entrada`.

    Resultado: **la defensa aguanta** y sale `ErrorBundle`.

    RONDA 2 — **CORRIJO UN DATO MIO DE LA RONDA 1.** Entonces escribi que esto
    "obliga a leer un cuarto de giga a memoria antes de decir que no", con una
    medicion de 430 -> 686 MB de RSS. **Era falso, y el error era de metodo**:
    estaba midiendo el RSS del proceso que FABRICA el zip, que si reserva los
    400 MB del payload, no el de `abrir_sesion`. D me lo corrigio y tiene razon.

    Medido bien, en un proceso que solo abre el fichero ya fabricado: **0,0 MB
    de subida de RSS y 0,4 ms**. El motivo es que `ZipExtFile` limita lo que
    descomprime al `file_size` que declara el directorio central, asi que un
    indice que miente diciendo 10 bytes hace que se lean 10 bytes; el fallo sale
    despues, en el CRC. Mentir a la baja no compra nada.

    (Donde SI hay amplificacion es en un indice HONESTO justo por debajo del
    tope: ver `test_el_coste_de_memoria_esta_en_el_indice_honesto_no_en_el_que_miente`.)
    """
    ruta = tmp_path / "mentira.sidebcolor"
    entrada = "arrays/a000_fingerprint.npy"
    documento = _sesion_minima()
    documento["sesion"]["analyses"]["a"] = {
        "clip_id": "c",
        "path": "p",
        "stats": {
            "mean": [0.0] * 3,
            "std": [0.0] * 3,
            "cov": [[0.0] * 3] * 3,
            "percentiles": [[0.0] * 3] * 11,
            "black_point": [0.0] * 3,
            "white_point": [0.0] * 3,
            "saturation_hist": [0.0] * 64,
            "skin_locus": None,
            "skin_fraction": 0.0,
            "n_samples": 1,
        },
        "fingerprint": entrada,
        "width": 1,
        "height": 1,
        "frame_count": 1,
        "sampled_frames": 1,
        "source_space": None,
        "pixels": None,
        "warnings": [],
    }
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", json.dumps(documento))
        zf.writestr(entrada, b"\0" * (400 * 1024 * 1024))

    crudo = bytearray(ruta.read_bytes())
    posicion = 0
    parcheadas = 0
    while True:
        posicion = crudo.find(b"PK\x01\x02", posicion)
        if posicion < 0:
            break
        largo = struct.unpack_from("<H", crudo, posicion + 28)[0]
        if bytes(crudo[posicion + 46 : posicion + 46 + largo]).decode() == entrada:
            struct.pack_into("<I", crudo, posicion + 24, 10)
            parcheadas += 1
        posicion += 4
    ruta.write_bytes(bytes(crudo))
    assert parcheadas == 1
    assert {z.filename: z.file_size for z in zipfile.ZipFile(ruta).infolist()}[entrada] == 10

    assert ruta.stat().st_size < 2 * 1024 * 1024
    with pytest.raises(ErrorBundle):
        abrir_sesion(ruta)


def test_el_coste_de_memoria_esta_en_el_indice_honesto_no_en_el_que_miente(tmp_path):
    """Donde esta de verdad la amplificacion del `.sidebcolor`, medida.

    El tope por entrada de `_leer_entrada` es `max_descomprimido`, o sea los
    mismos 256 MB que el presupuesto de TODO el archivo. Asi que una entrada que
    declara honestamente 250 MB pasa el chequeo del indice (250 < 256) y se lee
    entera. Comprimida es un zip de ~250 KB: **amplificacion de unas 1.000 a 1**.

    No es un bug: el presupuesto de 256 MB esta documentado y el fallo es limpio.
    Pero es el numero que hay que mirar si algun dia se quiere apretar, y no el
    del indice mentiroso, que no cuesta nada (ver el test de arriba).

    Se comprueba con `max_descomprimido` bajado a 4 MB para no reservar un cuarto
    de giga dentro de la suite: la propiedad es la misma y se ve igual de bien.
    """
    entrada = "arrays/a000_fingerprint.npy"
    tope = 4 * 1024 * 1024
    ruta = tmp_path / "honesta.sidebcolor"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", json.dumps(_sesion_minima()))
        # Justo por debajo del tope: el chequeo del indice la deja pasar.
        zf.writestr(entrada, b"\0" * (tope - 1024))

    declarado = {z.filename: z.file_size for z in zipfile.ZipFile(ruta).infolist()}[entrada]
    assert declarado < tope, "el indice es honesto y cabe en el presupuesto"
    amplificacion = declarado / ruta.stat().st_size
    assert amplificacion > 100, f"amplificacion medida: {amplificacion:.0f}:1"

    # Y se abre sin protestar: no es una bomba, es una entrada grande dentro del
    # presupuesto declarado. Eso es lo que hace que el coste sea real.
    assert abrir_sesion(ruta, max_descomprimido=tope).project_name == "REVISION"

    # Un byte mas y ya no cabe: el chequeo del indice la corta antes de leer.
    grande = tmp_path / "pasada.sidebcolor"
    with zipfile.ZipFile(grande, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", json.dumps(_sesion_minima()))
        zf.writestr(entrada, b"\0" * (tope + 1024))
    with pytest.raises(ErrorBundle, match="(?i)bomba"):
        abrir_sesion(grande, max_descomprimido=tope)


def test_un_zip_con_diez_mil_entradas_se_rechaza(tmp_path):
    ruta = tmp_path / "muchas.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(_sesion_minima()))
        for i in range(MAX_ENTRADAS + 5):
            zf.writestr(f"relleno/{i}", b"")
    with pytest.raises(ErrorBundle, match="(?i)entradas"):
        abrir_sesion(ruta)


def test_un_npy_con_pickle_no_ejecuta_nada(tmp_path):
    """El agujero de verdad: `np.load` con pickle ejecuta codigo al cargar.

    Se fabrica un `.npy` cuyo pickle llamaria a `os.system`. Tiene que fallar al
    cargarlo, y el fichero testigo NO puede aparecer.
    """
    testigo = tmp_path / "PWNED"

    class Payload:
        def __reduce__(self):
            return (os.system, (f"touch {testigo}",))

    buf = io.BytesIO()
    np.save(buf, np.array([Payload()], dtype=object), allow_pickle=True)

    documento = _sesion_minima()
    documento["sesion"]["analyses"]["a"] = {
        "clip_id": "c",
        "path": "p",
        "stats": None,
        "fingerprint": "arrays/a000_fingerprint.npy",
        "width": 1,
        "height": 1,
        "frame_count": 1,
        "sampled_frames": 1,
        "source_space": None,
        "pixels": None,
        "warnings": [],
    }
    ruta = tmp_path / "pickle.sidebcolor"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("session.json", json.dumps(documento))
        zf.writestr("arrays/a000_fingerprint.npy", buf.getvalue())

    with pytest.raises(ErrorBundle):
        abrir_sesion(ruta)
    assert not testigo.exists(), "SE HA EJECUTADO EL PICKLE"


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("no es un zip", b"esto no es un zip, ni de lejos"),
        ("zip vacio de verdad", b""),
        ("zip sin session.json", None),
    ],
)
def test_un_sidebcolor_roto_falla_como_ErrorBundle(nombre, contenido, tmp_path):
    ruta = tmp_path / "roto.sidebcolor"
    if contenido is None:
        with zipfile.ZipFile(ruta, "w") as zf:
            zf.writestr("otra_cosa.txt", "hola")
    else:
        ruta.write_bytes(contenido)
    with pytest.raises(ErrorBundle):
        abrir_sesion(ruta)


def test_session_json_duplicado_gana_el_ultimo(tmp_path):
    """Un zip puede traer dos entradas con el mismo nombre. Gana la segunda.

    No es explotable hoy (no se extrae nada al disco), pero queda escrito: si
    algun dia alguien añade "extraer miniaturas", el fichero que se valida y el
    que se extrae podrian no ser el mismo.
    """
    ruta = tmp_path / "dup.sidebcolor"
    with warnings.catch_warnings():
        # zipfile avisa de "Duplicate name"; es justo lo que queremos fabricar.
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(ruta, "w") as zf:
            zf.writestr("session.json", json.dumps(_sesion_minima()))
            zf.writestr("session.json", json.dumps({"formato": "otra_cosa"}))
    with pytest.raises(ErrorBundle, match="(?i)no es una sesion|no es una sesión"):
        abrir_sesion(ruta)


# ---------------------------------------------------------------------------
# 5. El CDL: bombas de entidades y XXE
# ---------------------------------------------------------------------------


_BILLION_LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
    "<ColorCorrection><SOPNode><Slope>&lol3; 1 1</Slope></SOPNode></ColorCorrection>"
)


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("billion laughs en UTF-8", _BILLION_LAUGHS.encode("utf-8")),
        ("billion laughs colado en UTF-16", _BILLION_LAUGHS.encode("utf-16")),
        (
            "XXE leyendo un fichero local",
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b"<ColorCorrection><SOPNode><Slope>&x; 1 1</Slope></SOPNode></ColorCorrection>",
        ),
        ("DOCTYPE con un espacio para esquivar el filtro", b"<! DOCTYPE r><ColorCorrection/>"),
        ("fichero vacio", b""),
        ("no es XML", b"hola que tal"),
        ("XML sin ningun ColorCorrection", b"<otracosa/>"),
        ("Power a 0 (no es un grado)", b"<ColorCorrection><SOPNode><Slope>1 1 1</Slope><Power>0 1 1</Power></SOPNode></ColorCorrection>"),
        ("Slope con nan", b"<ColorCorrection><SOPNode><Slope>nan 1 1</Slope></SOPNode></ColorCorrection>"),
        ("Slope con 2 numeros", b"<ColorCorrection><SOPNode><Slope>1 1</Slope></SOPNode></ColorCorrection>"),
        ("anidamiento de 5000 niveles", b"<ColorCorrection>" + b"<a>" * 5000 + b"</a>" * 5000 + b"</ColorCorrection>"),
    ],
)
def test_un_cdl_hostil_no_se_abre_y_no_revienta(nombre, contenido, tmp_path):
    """La bomba de UTF-16 es la interesante.

    El filtro del autor es un `re.search` de `<!DOCTYPE` sobre el TEXTO, asi que
    en UTF-16 no casaria. Lo que salva la situacion es la capa de antes: el
    fichero se decodifica como UTF-8 estricto y el UTF-16 no pasa. La defensa
    aguanta, pero aguanta por una razon distinta de la que dice NOTAS.md, y eso
    importa el dia que alguien "mejore" la lectura aceptando otros encodings.
    """
    ruta = tmp_path / "hostil.cdl"
    ruta.write_bytes(contenido)
    with pytest.raises(ErrorFormatoCDL):
        leer_cdl(ruta)


def test_un_cdl_legitimo_con_namespace_ASC_si_se_lee(tmp_path):
    """Contrapeso: no vale con rechazarlo todo."""
    ruta = tmp_path / "bueno.cc"
    ruta.write_bytes(
        b'<ColorCorrection xmlns="urn:ASC:CDL:v1.2"><SOPNode><Slope>2 2 2</Slope>'
        b"<Offset>0 0 0</Offset><Power>1 1 1</Power></SOPNode>"
        b"<SatNode><Saturation>0.8</Saturation></SatNode></ColorCorrection>"
    )
    cdl = leer_cdl(ruta)
    assert cdl.slope == (2.0, 2.0, 2.0)
    assert cdl.saturation == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# 6. Ida y vuelta exacta del bundle
# ---------------------------------------------------------------------------


def test_el_modo_exacto_del_bundle_aguanta_valores_minusculos_y_enormes():
    """Nueve cifras SIGNIFICATIVAS, no nueve decimales. Aqui esta la diferencia.

    Se prueba con valores donde el espaciado del float32 es microscopico
    (1e-7) y con valores grandes. Con 6 decimales la ida y vuelta NO es exacta;
    con `decimales=None` si.
    """
    rng = np.random.default_rng(1234)
    tabla = (rng.random((17, 17, 17, 3)) * np.float32(1e-4)).astype(np.float32)
    tabla[0, 0, 0] = [1.2e-7, 3.4e-6, 9.9e-5]
    tabla[1, 1, 1] = [12.5, -3.25, 1000.125]
    lut = LUT3D(table=tabla, domain_max=(1100.0, 1100.0, 1100.0))

    exacto = cube_desde_texto(cube_a_texto(lut, decimales=None))
    assert exacto.table.tobytes() == tabla.tobytes()

    aproximado = cube_desde_texto(cube_a_texto(lut, decimales=6))
    assert aproximado.table.tobytes() != tabla.tobytes()
