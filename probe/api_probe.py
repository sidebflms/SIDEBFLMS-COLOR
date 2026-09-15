#!/usr/bin/env python3
"""
=============================================================================
 SIDEBFLMS COLOR - SONDA DE LA API DE DAVINCI RESOLVE
=============================================================================

QUE ES ESTO
  Un script que le hace seis preguntas a tu DaVinci Resolve y apunta las
  respuestas. La app entera esta escrita asumiendo lo peor en esas seis cosas;
  cuando tengamos las respuestas de verdad, se cambian seis constantes y la app
  deja de ir a ciegas.

  Antes que las seis hace una septima comprobacion, la V-0, que es la mas
  importante de todas y no cuesta nada porque solo lee: comprueba que Resolve
  sabe decirnos en que version de color esta cada clip. La app pregunta eso
  antes de cada escritura para no pisarte el grado; si Resolve no contesta, la
  app no escribe. Sale de las primeras.

QUE NECESITAS ANTES DE EMPEZAR
  1. DaVinci Resolve **Studio** abierto (la version gratuita no deja que un
     script de fuera le hable).
  2. Un proyecto abierto, con un **timeline abierto** que tenga al menos un
     clip. Que sea un proyecto de pruebas, no uno de un cliente.
  3. En Resolve: Preferencias > System > General > "External scripting using"
     puesto en **Local**. Si esta en "None", nada de esto funciona.

COMO SE EJECUTA
  Lo mas prudente primero, que no toca nada de nada:

      python3 probe/api_probe.py --solo-diagnostico

  Eso te dice si encuentra Resolve y si tu Python puede hablar con el. Ni se
  conecta, ni escribe un solo fichero: te lo cuenta por pantalla y se va. Si
  sale bien, la pasada completa:

      python3 probe/api_probe.py --informe ~/Desktop/informe_resolve.json

  Te va a preguntar antes de escribir nada. Hasta que contestes "s", el script
  solo lee.

  SOBRE LOS FICHEROS QUE DEJA: **sin `--informe` no escribe ninguno.** Nada de
  encontrarte dos ficheros sueltos en la carpeta desde la que lo ejecutaste. Si
  se te olvida poner `--informe` en la pasada completa, el informe cae dentro
  del directorio de pruebas (que ya has autorizado) y te dice donde.

QUE VA A TOCAR (y solo si dices que si)
  - Crea una version de color nueva llamada "SIDEB COLOR PROBE" en UN clip (el
    primero del timeline, o el que le digas con --clip). Tu grado se queda
    donde estaba, en su version. Al terminar vuelve a dejar seleccionada la
    version que tenias.
  - Dentro de esa version escribe un CDL y un LUT, para ver si se aplican.
  - Coge dos o tres stills en la galeria y los borra al terminar.
  - Escribe ficheros sueltos en el directorio temporal que tu elijas con
    --dir-pruebas (por defecto, uno nuevo dentro de la carpeta temporal del
    sistema).

  Lo unico que puede quedarse por ahi es la version "SIDEB COLOR PROBE": la API
  de Resolve puede no tener forma de borrar versiones. Si se queda, la borras
  tu en la pagina de color, boton derecho sobre el clip > Local Versions.

SI ALGO FALLA
  El script no te va a soltar un traceback: te dice que ha pasado y que hacer.
  Si aun asi peta, mandame el fichero .json del informe y el texto de la
  pantalla.

  Este script usa SOLO la biblioteca estandar de Python. No hace falta instalar
  nada, ni el entorno virtual del proyecto. Se puede copiar suelto a cualquier
  sitio y ejecutarlo.
=============================================================================
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import platform
import sys
import tempfile

VERSION_PROBE = "SIDEB COLOR PROBE"
ANCHO = 78

# Rutas habituales del modulo de scripting en macOS.
MODULOS_DESCARGA = (
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve"
    "/Developer/Scripting/Modules"
)
MODULOS_MAS = (
    "~/Library/Containers/com.blackmagic-design.DaVinciResolveAppStore/Data"
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve"
    "/Developer/Scripting/Modules"
)
LIB_DESCARGA = (
    "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
)
LIB_MAS = (
    "~/Applications/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
)
LUT_DIR_DESCARGA = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
LUT_DIR_MAS = (
    "~/Library/Containers/com.blackmagic-design.DaVinciResolveAppStore/Data"
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
)


# ---------------------------------------------------------------------------
# Salida por pantalla
# ---------------------------------------------------------------------------


def titulo(texto: str) -> None:
    print()
    print("=" * ANCHO)
    print(texto.upper())
    print("=" * ANCHO)


def apartado(texto: str) -> None:
    print()
    print("-" * ANCHO)
    print(texto)
    print("-" * ANCHO)


def linea(texto: str = "") -> None:
    print(texto)


def ok(texto: str) -> None:
    print(f"  [OK]    {texto}")


def mal(texto: str) -> None:
    print(f"  [FALLO] {texto}")


def duda(texto: str) -> None:
    print(f"  [?]     {texto}")


def nota(texto: str) -> None:
    print(f"          {texto}")


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------


class Informe:
    """Recoge todo lo que va pasando para escribirlo luego en JSON y en texto."""

    def __init__(self) -> None:
        self.datos: dict = {
            "generado": datetime.datetime.now().isoformat(timespec="seconds"),
            "probe_version": 1,
            "entorno": {},
            "resolve": {},
            "preguntas": {},
            "errores": [],
            "avisos": [],
            "limpieza": {},
        }

    def responder(
        self, clave: str, pregunta: str, respuesta, detalle: str, consecuencia: str
    ) -> None:
        self.datos["preguntas"][clave] = {
            "pregunta": pregunta,
            "respuesta": respuesta,
            "detalle": detalle,
            "consecuencia_para_la_app": consecuencia,
        }
        etiqueta = {True: "SI", False: "NO", None: "SIN RESPUESTA"}.get(respuesta, str(respuesta))
        apartado(f"{clave}  {pregunta}")
        linea(f"  RESPUESTA: {etiqueta}")
        linea(f"  QUE HE VISTO: {detalle}")
        linea(f"  QUE SIGNIFICA: {consecuencia}")

    def error(self, texto: str) -> None:
        self.datos["errores"].append(texto)

    def aviso(self, texto: str) -> None:
        self.datos["avisos"].append(texto)
        nota(f"aviso: {texto}")

    def a_texto(self) -> str:
        d = self.datos
        out = []
        out.append("INFORME DE LA SONDA DE LA API DE RESOLVE - SIDEBFLMS COLOR")
        out.append(f"Generado: {d['generado']}")
        out.append("")
        out.append("ENTORNO")
        for k, v in d["entorno"].items():
            out.append(f"  {k}: {v}")
        out.append("")
        out.append("RESOLVE")
        for k, v in d["resolve"].items():
            out.append(f"  {k}: {v}")
        out.append("")
        out.append("LAS PREGUNTAS")
        for clave, p in d["preguntas"].items():
            etiqueta = {True: "SI", False: "NO", None: "SIN RESPUESTA"}.get(
                p["respuesta"], str(p["respuesta"])
            )
            out.append("")
            out.append(f"  {clave}  {p['pregunta']}")
            out.append(f"    RESPUESTA:  {etiqueta}")
            out.append(f"    QUE HE VISTO:  {p['detalle']}")
            out.append(f"    QUE SIGNIFICA: {p['consecuencia_para_la_app']}")
        if d["avisos"]:
            out.append("")
            out.append("AVISOS")
            out.extend(f"  - {a}" for a in d["avisos"])
        if d["errores"]:
            out.append("")
            out.append("ERRORES")
            out.extend(f"  - {e}" for e in d["errores"])
        if d["limpieza"]:
            out.append("")
            out.append("LIMPIEZA")
            for k, v in d["limpieza"].items():
                out.append(f"  {k}: {v}")
        out.append("")
        return "\n".join(out)

    def escribir(self, ruta_json: str) -> tuple[str, str]:
        ruta_json = os.path.abspath(os.path.expanduser(ruta_json))
        carpeta = os.path.dirname(ruta_json) or "."
        os.makedirs(carpeta, exist_ok=True)
        with open(ruta_json, "w", encoding="utf-8") as fh:
            json.dump(self.datos, fh, indent=2, ensure_ascii=False)
        ruta_txt = os.path.splitext(ruta_json)[0] + ".txt"
        with open(ruta_txt, "w", encoding="utf-8") as fh:
            fh.write(self.a_texto())
        return ruta_json, ruta_txt


# ---------------------------------------------------------------------------
# Paso 1: el entorno
# ---------------------------------------------------------------------------


def mirar_entorno(inf: Informe) -> None:
    apartado("1. TU PYTHON")
    ent = inf.datos["entorno"]
    ent["python"] = sys.version.split()[0]
    ent["ejecutable"] = sys.executable
    ent["arquitectura"] = platform.machine()
    ent["so"] = f"{platform.system()} {platform.release()}"
    ent["RESOLVE_SCRIPT_API"] = os.environ.get("RESOLVE_SCRIPT_API", "(sin definir)")
    ent["RESOLVE_SCRIPT_LIB"] = os.environ.get("RESOLVE_SCRIPT_LIB", "(sin definir)")
    ent["PYTHONPATH"] = os.environ.get("PYTHONPATH", "(sin definir)")
    for k, v in ent.items():
        linea(f"  {k}: {v}")

    if platform.machine() != "arm64" and platform.system() == "Darwin":
        inf.aviso(
            f"tu Python es {platform.machine()}, no arm64. En un Mac de Apple Silicon la "
            f"libreria de Resolve es arm64 y no va a cargar. Usa /usr/bin/python3."
        )

    candidatos = {
        "modulos_descarga_directa": MODULOS_DESCARGA,
        "modulos_mac_app_store": MODULOS_MAS,
        "lut_descarga_directa": LUT_DIR_DESCARGA,
        "lut_mac_app_store": LUT_DIR_MAS,
    }
    linea()
    linea("  Carpetas de Resolve que hay en esta maquina:")
    for nombre, ruta in candidatos.items():
        existe = os.path.isdir(os.path.expanduser(ruta))
        ent[nombre] = {"ruta": os.path.expanduser(ruta), "existe": existe}
        marca = "SI" if existe else "no"
        linea(f"    [{marca:>2}] {nombre}: {os.path.expanduser(ruta)}")


# ---------------------------------------------------------------------------
# Paso 2: encontrar e importar el modulo
# ---------------------------------------------------------------------------


def explicar_fallo_import(exc: BaseException) -> list[str]:
    """Traduce el error de importacion a algo que se pueda arreglar."""
    texto = str(exc)
    consejos: list[str] = []
    if isinstance(exc, ModuleNotFoundError):
        consejos.append(
            "No encuentro el modulo 'DaVinciResolveScript'. Eso casi siempre significa que "
            "las variables de entorno no estan puestas. Pega esto en la terminal y vuelve "
            "a ejecutar (es para la instalacion por descarga directa):"
        )
        consejos.append("")
        # RESOLVE_SCRIPT_API apunta a .../Developer/Scripting, que es la carpeta
        # que CONTIENE Modules. Es el orden que pide el README de Blackmagic.
        consejos.append(f'  export RESOLVE_SCRIPT_API="{os.path.dirname(MODULOS_DESCARGA)}"')
        consejos.append(f'  export RESOLVE_SCRIPT_LIB="{LIB_DESCARGA}"')
        consejos.append(f'  export PYTHONPATH="$PYTHONPATH:{MODULOS_DESCARGA}"')
        consejos.append("")
        consejos.append(
            "Si Resolve lo instalaste desde la Mac App Store, las rutas son estas otras "
            "(mira arriba, en 'Carpetas de Resolve que hay en esta maquina', cual de las "
            "dos sale con [SI]):"
        )
        consejos.append("")
        consejos.append(
            f'  export RESOLVE_SCRIPT_API="{os.path.dirname(os.path.expanduser(MODULOS_MAS))}"'
        )
        consejos.append(f'  export RESOLVE_SCRIPT_LIB="{os.path.expanduser(LIB_MAS)}"')
        consejos.append(
            f'  export PYTHONPATH="$PYTHONPATH:{os.path.expanduser(MODULOS_MAS)}"'
        )
    elif "incompatible architecture" in texto or "mach-o" in texto.lower():
        consejos.append(
            "La libreria de Resolve y tu Python son de arquitecturas distintas (uno arm64 y "
            "el otro x86_64). Prueba con el Python del sistema: /usr/bin/python3"
        )
    elif "symbol not found" in texto.lower() or "undefined symbol" in texto.lower():
        consejos.append(
            "La libreria fusionscript esta compilada para otra version de Python. Prueba con "
            "/usr/bin/python3 (el que trae macOS) antes que con uno de Homebrew."
        )
    else:
        consejos.append(
            "Error al importar el modulo de scripting. Comprueba que Resolve esta instalado "
            "y que RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB apuntan a donde toca."
        )
    return consejos


def importar_modulo(inf: Informe):
    """Devuelve (modulo, tipo_instalacion) o (None, None)."""
    apartado("2. EL MODULO DE SCRIPTING")

    rutas = []
    api = os.environ.get("RESOLVE_SCRIPT_API")
    if api:
        rutas.append(os.path.join(api, "Modules"))
    rutas.append(os.path.expanduser(MODULOS_DESCARGA))
    rutas.append(os.path.expanduser(MODULOS_MAS))

    instalacion = None
    for ruta in rutas:
        if os.path.isdir(ruta):
            if ruta not in sys.path:
                sys.path.append(ruta)
            if "DaVinciResolveAppStore" in ruta:
                instalacion = "mac_app_store"
            elif instalacion is None:
                instalacion = "descarga"
            ok(f"anadida al path: {ruta}")

    if instalacion is None:
        mal("no he encontrado la carpeta Modules de Resolve en ningun sitio conocido")

    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-not-found]  # noqa: N813
    except BaseException as exc:  # noqa: BLE001 - aqui queremos cazarlo todo
        mal(f"no se ha podido importar el modulo: {type(exc).__name__}: {exc}")
        linea()
        for c in explicar_fallo_import(exc):
            linea(f"  {c}")
        inf.error(f"import DaVinciResolveScript: {type(exc).__name__}: {exc}")
        inf.datos["resolve"]["modulo_importado"] = False
        inf.datos["resolve"]["error_import"] = f"{type(exc).__name__}: {exc}"
        return None, instalacion

    ok(f"modulo importado desde {getattr(dvr, '__file__', '(sin __file__)')}")
    inf.datos["resolve"]["modulo_importado"] = True
    inf.datos["resolve"]["modulo_ruta"] = getattr(dvr, "__file__", "")
    if instalacion is None and getattr(dvr, "__file__", ""):
        instalacion = (
            "mac_app_store" if "DaVinciResolveAppStore" in dvr.__file__ else "descarga"
        )
    return dvr, instalacion


# ---------------------------------------------------------------------------
# Paso 3: conectar
# ---------------------------------------------------------------------------


def conectar(dvr, inf: Informe):
    apartado("3. CONEXION CON RESOLVE")
    try:
        resolve = dvr.scriptapp("Resolve")
    except BaseException as exc:  # noqa: BLE001
        mal(f"scriptapp('Resolve') ha reventado: {type(exc).__name__}: {exc}")
        inf.error(f"scriptapp: {type(exc).__name__}: {exc}")
        return None
    if resolve is None:
        mal("scriptapp('Resolve') ha devuelto None: no hay nadie al otro lado.")
        linea()
        linea("  Las tres razones, por orden de probabilidad:")
        linea("    1. DaVinci Resolve no esta abierto. Abrelo y espera a que cargue del todo.")
        linea("    2. En Resolve, Preferencias > System > General > 'External scripting")
        linea("       using' esta en 'None'. Ponlo en 'Local' y reinicia Resolve.")
        linea("    3. Es la version gratuita. La API de scripting externo es de Studio.")
        inf.error("scriptapp('Resolve') devolvio None")
        return None

    try:
        producto = resolve.GetProductName()
        version = resolve.GetVersionString()
    except BaseException as exc:  # noqa: BLE001
        producto, version = "(desconocido)", "(desconocido)"
        inf.error(f"GetProductName/GetVersionString: {exc}")

    es_studio = "studio" in str(producto).lower()
    inf.datos["resolve"]["producto"] = producto
    inf.datos["resolve"]["version"] = version
    inf.datos["resolve"]["es_studio"] = es_studio
    ok(f"conectado a {producto} {version}")
    if not es_studio:
        mal(
            "esto NO es Resolve Studio. La app de color necesita Studio: la version gratuita "
            "no tiene ni scripting externo ni exportacion de LUTs."
        )
        inf.error("la instalacion no es Studio")
    return resolve


def contexto(resolve, inf: Informe):
    """Devuelve (project, timeline, items) o Nones, explicando que falta."""
    try:
        pm = resolve.GetProjectManager()
        project = pm.GetCurrentProject() if pm else None
    except BaseException as exc:  # noqa: BLE001
        mal(f"no he podido pedir el proyecto: {exc}")
        inf.error(f"GetCurrentProject: {exc}")
        return None, None, []
    if project is None:
        mal("no hay ningun proyecto abierto. Abre uno (de pruebas) y vuelve a ejecutar.")
        inf.error("no hay proyecto abierto")
        return None, None, []
    ok(f"proyecto: {project.GetName()}")
    inf.datos["resolve"]["proyecto"] = project.GetName()

    timeline = project.GetCurrentTimeline()
    if timeline is None:
        mal("hay proyecto pero no hay timeline abierto. Abre un timeline con clips.")
        inf.error("no hay timeline abierto")
        return project, None, []
    ok(f"timeline: {timeline.GetName()}")
    inf.datos["resolve"]["timeline"] = timeline.GetName()

    items = []
    try:
        n_pistas = int(timeline.GetTrackCount("video"))
        for pista in range(1, n_pistas + 1):
            items.extend(timeline.GetItemListInTrack("video", pista) or [])
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetItemListInTrack: {exc}")
    inf.datos["resolve"]["clips_en_timeline"] = len(items)
    if not items:
        mal("el timeline no tiene clips de video. Mete uno y vuelve a ejecutar.")
        inf.error("timeline sin clips")
    else:
        ok(f"{len(items)} clip(s) de video en el timeline")

    for clave, metodo in (
        ("gestion_de_color", "colorScienceMode"),
        ("timeline_color_space", "colorSpaceTimeline"),
    ):
        try:
            inf.datos["resolve"][clave] = project.GetSetting(metodo)
        except BaseException:  # noqa: BLE001
            inf.datos["resolve"][clave] = "(no se ha podido leer)"
    return project, timeline, items


# ---------------------------------------------------------------------------
# Utilidades de medida
# ---------------------------------------------------------------------------


def leer_ppm_medio(ruta: str) -> float | None:
    """Media de los pixeles de un PPM binario (P6), en 0..1. Solo stdlib.

    Se usa un PPM justamente porque se puede leer sin instalar nada: es el
    unico formato de `ExportStills` que se parsea en veinte lineas.
    """
    try:
        with open(ruta, "rb") as fh:
            datos = fh.read()
    except OSError:
        return None
    if not datos.startswith(b"P6"):
        return None
    campos: list[bytes] = []
    i = 2
    while len(campos) < 3 and i < len(datos):
        while i < len(datos) and datos[i : i + 1].isspace():
            i += 1
        if datos[i : i + 1] == b"#":
            while i < len(datos) and datos[i : i + 1] not in (b"\n", b"\r"):
                i += 1
            continue
        j = i
        while j < len(datos) and not datos[j : j + 1].isspace():
            j += 1
        campos.append(datos[i:j])
        i = j
    if len(campos) < 3:
        return None
    try:
        maxval = int(campos[2])
    except ValueError:
        return None
    i += 1  # el unico byte blanco que sigue a maxval
    cuerpo = datos[i:]
    if not cuerpo:
        return None
    if maxval > 255:
        muestras = [
            (cuerpo[k] << 8) | cuerpo[k + 1] for k in range(0, len(cuerpo) - 1, 2 * 97)
        ]
    else:
        muestras = list(cuerpo[::97])  # una de cada 97: sobra para una media
    if not muestras:
        return None
    return sum(muestras) / (len(muestras) * maxval)


def ficheros_nuevos(carpeta: str, antes: set[str]) -> list[str]:
    try:
        ahora = set(os.listdir(carpeta))
    except OSError:
        return []
    return sorted(ahora - antes)


# ---------------------------------------------------------------------------
# Las preguntas de solo lectura
# ---------------------------------------------------------------------------


def pregunta_f0_6(inf: Informe, importado: bool) -> None:
    detalle = (
        f"Python {sys.version.split()[0]} ({platform.machine()}) desde {sys.executable}. "
        f"{'Import limpio.' if importado else 'El import ha fallado.'}"
    )
    inf.responder(
        "F0-6",
        "¿Este Python importa el modulo de scripting de Resolve limpiamente?",
        bool(importado),
        detalle,
        (
            "Si es que si con el Python 3.12 arm64 del proyecto, LiveResolve puede vivir dentro "
            "de la app. Si solo funciona con /usr/bin/python3, la app tendra que hablar con "
            "Resolve por un proceso aparte, y eso es un rediseno de medio dia."
        )
        if importado
        else (
            "Sin esto no hay LiveResolve que valga. Arregla primero las variables de entorno "
            "que salen arriba y vuelve a ejecutar."
        ),
    )


def pregunta_f0_4(inf: Informe, instalacion: str | None, project) -> None:
    descarga = os.path.isdir(os.path.expanduser(LUT_DIR_DESCARGA))
    mas = os.path.isdir(os.path.expanduser(LUT_DIR_MAS))
    # Solo se elige una si no hay ambiguedad: o lo dice el modulo importado, o
    # solo existe una de las dos carpetas.
    elegida = None
    if (instalacion == "mac_app_store" and mas) or (mas and not descarga):
        elegida = os.path.expanduser(LUT_DIR_MAS)
    elif (instalacion == "descarga" and descarga) or (descarga and not mas):
        elegida = LUT_DIR_DESCARGA

    detalle = (
        (
            f"El modulo de scripting se ha cargado de una instalacion por {instalacion}. "
            if instalacion
            else "No he podido cargar el modulo de scripting de ninguna de las dos "
            "instalaciones conocidas. "
        )
        + f"Carpeta de LUTs de descarga directa: {'existe' if descarga else 'no existe'}. "
        + f"Carpeta de LUTs del Mac App Store: {'existe' if mas else 'no existe'}."
    )
    if project is not None:
        with contextlib.suppress(BaseException):
            detalle += (
                f" Ajuste de color del proyecto: {project.GetSetting('colorScienceMode')}."
            )
    inf.responder(
        "F0-4",
        "¿La instalacion es descarga directa o Mac App Store? (cambia la carpeta de LUTs)",
        instalacion or "sin determinar",
        detalle,
        (
            f"La app tiene que copiar sus .cube a: {elegida}. Pon "
            f"Incognitas(instalacion='{instalacion}') en core/resolve/incognitas.py."
        )
        if elegida
        else (
            "No se puede decidir sola: existen las dos carpetas o no existe ninguna. Mira en "
            "Resolve, Project Settings > Color Management > Open LUT Folder, y apunta la ruta."
        ),
    )


def pregunta_v0_version_actual(inf: Informe, items) -> None:
    """LA PRIMERA. ¿Que contesta `GetCurrentVersion()` en un clip sin tocar?

    Esto no es una de las seis incognitas: es un riesgo que nos hemos creado
    nosotros. La app, antes de escribir NADA, pregunta en que version de color
    esta el clip, y si no le contestan un nombre reconocible **se niega a
    escribir**. Es a proposito (ver core/resolve/NOTAS.md), pero significa que
    si `GetCurrentVersion()` se porta raro en esta build, la app no sirve para
    nada hasta que alguien lo mire.

    Es de solo lectura, asi que se contesta sin permiso y sin tocar el proyecto.
    """
    respuestas = []
    usables = 0
    for i, item in enumerate(items[:12], start=1):
        fila = {"clip": i, "nombre_clip": None, "crudo": None, "tipo": None, "usable": False}
        try:
            fila["nombre_clip"] = str(item.GetName())
            actual = item.GetCurrentVersion()
            fila["crudo"] = repr(actual)
            fila["tipo"] = type(actual).__name__
            nombre = actual.get("versionName") if isinstance(actual, dict) else actual
            fila["nombre_version"] = None if nombre is None else str(nombre)
            fila["usable"] = bool(isinstance(nombre, str) and nombre.strip())
        except BaseException as exc:  # noqa: BLE001
            fila["error"] = f"{type(exc).__name__}: {exc}"
            inf.error(f"GetCurrentVersion en el clip {i}: {exc}")
        usables += 1 if fila["usable"] else 0
        respuestas.append(fila)

    inf.datos["resolve"]["get_current_version"] = respuestas
    total = len(respuestas)
    todas = total > 0 and usables == total
    if total == 0:
        detalle = "No habia clips que mirar."
    else:
        muestra = respuestas[0]
        detalle = (
            f"He mirado {total} clip(s) sin tocar nada. Devuelven un nombre de version usable "
            f"{usables} de {total}. El primero ({muestra.get('nombre_clip')!r}) contesta "
            f"{muestra.get('crudo')} (tipo {muestra.get('tipo')}), que la app leeria como "
            f"{muestra.get('nombre_version')!r}."
        )
    inf.responder(
        "V-0",
        "¿Que devuelve GetCurrentVersion() en un clip recien abierto? (de esto depende "
        "que la app pueda escribir algo)",
        todas if total else None,
        detalle,
        (
            "Perfecto. La regla de oro puede preguntar la version antes de cada escritura, que "
            "es lo que impide que la app pise el grado del usuario."
            if todas
            else "CUIDADO: con esto la app se NEGARIA a escribir en los clips que no contestan "
            "un nombre (lanza VersionIndeterminada). Es deliberado —mejor no escribir que "
            "escribir encima del grado de alguien— pero hay que arreglarlo antes de usarla: "
            "mandame este informe y miro como leer la version de otra forma."
        ),
    )


def pregunta_f0_5_lectura(inf: Informe, resolve) -> str | None:
    """Apunta en que pagina estamos antes de tocar nada."""
    try:
        pagina = resolve.GetCurrentPage()
        ok(f"pagina actual de Resolve: {pagina}")
        inf.datos["resolve"]["pagina_al_empezar"] = pagina
        return pagina
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetCurrentPage: {exc}")
        return None


def buscar_dctl(inf: Informe, instalacion: str | None, dctl_manual: str | None) -> str | None:
    """Busca un .dctl dentro de la carpeta de LUTs, para poder probar F0-3."""
    if dctl_manual:
        return dctl_manual
    base = (
        os.path.expanduser(LUT_DIR_MAS)
        if instalacion == "mac_app_store"
        else LUT_DIR_DESCARGA
    )
    if not os.path.isdir(base):
        return None
    for raiz, _dirs, ficheros in os.walk(base):
        for f in ficheros:
            if f.lower().endswith(".dctl"):
                rel = os.path.relpath(os.path.join(raiz, f), base)
                inf.datos["resolve"]["dctl_encontrado"] = rel
                return rel
    return None


# ---------------------------------------------------------------------------
# Las preguntas que escriben
# ---------------------------------------------------------------------------


def preguntar_permiso(args, items, dir_pruebas: str) -> bool:
    apartado("PERMISO PARA ESCRIBIR")
    linea("  A partir de aqui el script deja de ser de solo lectura. Va a:")
    linea()
    linea(f"    - Crear la version de color '{VERSION_PROBE}' en el clip:")
    linea(f"        {items[args.clip - 1].GetName()}")
    linea("      Tu grado NO se toca: se queda en la version que tiene ahora, y al")
    linea("      terminar el script vuelve a dejarla seleccionada.")
    linea(f"    - Escribir un CDL y un LUT dentro de esa version '{VERSION_PROBE}'.")
    linea("    - Coger 2 o 3 stills en la galeria, y borrarlos al terminar.")
    linea(f"    - Escribir ficheros de prueba aqui: {dir_pruebas}")
    linea()
    linea("  Lo unico que puede quedarse es la version de color, si la API no")
    linea("  permite borrarla. Se borra a mano en dos clics.")
    linea()
    try:
        respuesta = input("  ¿Sigo? Escribe 's' y pulsa intro (cualquier otra cosa = no): ")
    except (EOFError, KeyboardInterrupt):
        linea()
        return False
    return respuesta.strip().lower() in ("s", "si", "sí", "y", "yes")


def crear_version_probe(inf: Informe, item) -> tuple[str | None, dict]:
    """Crea la version de sonda. Devuelve (version_original, medidas)."""
    medidas: dict = {}
    try:
        actual = item.GetCurrentVersion()
        original = actual.get("versionName") if isinstance(actual, dict) else str(actual)
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetCurrentVersion: {exc}")
        original = None
    medidas["version_original"] = original
    ok(f"version que tenias seleccionada: {original!r}")

    try:
        grafo = item.GetNodeGraph(1)
        medidas["nodos_antes"] = int(grafo.GetNumNodes()) if grafo else None
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetNodeGraph/GetNumNodes antes: {exc}")
        medidas["nodos_antes"] = None

    try:
        creada = bool(item.AddVersion(VERSION_PROBE, 0))
    except BaseException as exc:  # noqa: BLE001
        mal(f"AddVersion ha reventado: {exc}")
        inf.error(f"AddVersion: {exc}")
        return original, medidas
    medidas["add_version"] = creada
    if not creada:
        # Lo mas probable: ya existe de una pasada anterior.
        try:
            item.LoadVersionByName(VERSION_PROBE, 0)
            ok(f"la version {VERSION_PROBE!r} ya existia; la he seleccionado")
        except BaseException as exc:  # noqa: BLE001
            inf.error(f"LoadVersionByName: {exc}")
    else:
        ok(f"creada la version {VERSION_PROBE!r}")

    try:
        actual = item.GetCurrentVersion()
        medidas["version_tras_crear"] = (
            actual.get("versionName") if isinstance(actual, dict) else str(actual)
        )
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetCurrentVersion tras AddVersion: {exc}")

    try:
        grafo = item.GetNodeGraph(1)
        medidas["nodos_despues"] = int(grafo.GetNumNodes()) if grafo else None
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetNodeGraph/GetNumNodes despues: {exc}")
        medidas["nodos_despues"] = None

    inf.datos["resolve"]["version_probe"] = medidas
    return original, medidas


def pregunta_extra_nodos(inf: Informe, medidas: dict) -> None:
    antes = medidas.get("nodos_antes")
    despues = medidas.get("nodos_despues")
    hereda = None
    if isinstance(antes, int) and isinstance(despues, int):
        hereda = despues >= antes and despues > 1
    inf.responder(
        "EXTRA",
        "¿Una version nueva hereda el arbol de nodos, o empieza en blanco?",
        hereda,
        f"El clip tenia {antes} nodo(s) antes de AddVersion y {despues} despues.",
        (
            "Hereda. Perfecto: la app puede escribir en el nodo 2 y en el 3 de la version "
            "SIDEB COLOR sin mas."
            if hereda
            else "La version nueva empieza con un solo nodo. Esto es gordo: la API NO sabe crear "
            "nodos, asi que la app no puede montar los tres nodos ella sola. Habria que "
            "partir de un PowerGrade de tres nodos y aplicarlo con ApplyGradeFromDRX, o "
            "pedirle a quien monta que deje los tres nodos hechos."
        ),
    )


def pregunta_f0_5(inf: Informe, resolve, item, pagina_inicial: str | None) -> None:
    """¿Hace falta OpenPage('color') para escribir grado?

    Se mide con SetLUT/GetLUT y no con SetCDL porque **GetCDL no existe**: el
    LUT es lo unico que se puede volver a leer para saber si se escribio.
    """
    detalle_partes = []
    resultado = None
    try:
        if pagina_inicial and pagina_inicial != "edit":
            resolve.OpenPage("edit")
        detalle_partes.append("puesto Resolve en la pagina de edicion")

        grafo = item.GetNodeGraph(1)
        n = int(grafo.GetNumNodes())
        objetivo = 2 if n >= 2 else 1
        lut_previo = item.GetLUT(objetivo)
        detalle_partes.append(f"LUT del nodo {objetivo} antes: {lut_previo!r}")

        # Un LUT que trae Resolve de serie en cualquier instalacion.
        candidatos = ["DaVinci Resolve/Sony/S-Log3 to Rec709.cube", "Sony/S-Log3 to Rec709.cube"]
        escrito = None
        for cand in candidatos:
            if item.SetLUT(objetivo, cand):
                escrito = cand
                break
        if escrito is None:
            detalle_partes.append(
                "SetLUT ha dicho que no con todos los LUT de serie que he probado, asi que no "
                "puedo distinguir 'hace falta OpenPage' de 'ese LUT no esta'"
            )
        else:
            leido = item.GetLUT(objetivo)
            detalle_partes.append(f"tras SetLUT({objetivo}, {escrito!r}) GetLUT devuelve {leido!r}")
            funciono_sin_color = bool(leido)
            # Ahora con la pagina de color abierta, para comparar.
            resolve.OpenPage("color")
            item.SetLUT(objetivo, lut_previo or "")
            resultado = not funciono_sin_color
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"prueba F0-5: {type(exc).__name__}: {exc}")
        detalle_partes.append(f"ha saltado {type(exc).__name__}: {exc}")

    inf.responder(
        "F0-5",
        "¿Hace falta OpenPage('color') antes de escribir grado por script?",
        resultado,
        ". ".join(detalle_partes)
        + ". OJO: medido con SetLUT/GetLUT, porque GetCDL no existe y un SetCDL no se puede "
        "releer.",
        (
            "Hace falta. Dejalo como esta: requiere_open_page=True."
            if resultado
            else "No hace falta, pero la app lo llama igualmente porque no cuesta nada y el "
            "riesgo de no llamarlo es una escritura silenciosa que no se aplica."
        ),
    )


def pregunta_f0_3(inf: Informe, item, dctl_rel: str | None) -> None:
    resultado = None
    if dctl_rel is None:
        detalle = (
            "No hay ningun .dctl en tu carpeta de LUTs, asi que no he podido probarlo. "
            "Si te interesa la respuesta, copia un .dctl a la carpeta de LUTs y vuelve a "
            "ejecutar con --dctl RUTA_RELATIVA."
        )
    else:
        try:
            grafo = item.GetNodeGraph(1)
            objetivo = 2 if int(grafo.GetNumNodes()) >= 2 else 1
            previo = item.GetLUT(objetivo)
            acepto = bool(item.SetLUT(objetivo, dctl_rel))
            leido = item.GetLUT(objetivo)
            resultado = acepto and bool(leido)
            detalle = (
                f"SetLUT({objetivo}, {dctl_rel!r}) devolvio {acepto} y GetLUT devuelve {leido!r}."
            )
            item.SetLUT(objetivo, previo or "")
        except BaseException as exc:  # noqa: BLE001
            detalle = f"ha saltado {type(exc).__name__}: {exc}"
            inf.error(f"prueba F0-3: {exc}")
    inf.responder(
        "F0-3",
        "¿SetLUT() acepta un .dctl?",
        resultado,
        detalle,
        "Se puede ofrecer el .dctl como formato del nodo 3. Pon setlut_acepta_dctl=True."
        if resultado
        else "El nodo 3 se queda solo con .cube, que es lo que la app genera igualmente. No se "
        "pierde nada.",
    )


def preguntas_stills(inf: Informe, project, timeline, item, dir_pruebas: str) -> None:
    """F0-1 (.drx) y F0-2 (¿el still lleva el grado?), de una sentada."""
    gallery = None
    album = None
    stills: list = []
    try:
        gallery = project.GetGallery()
        album = gallery.GetCurrentStillAlbum() if gallery else None
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"GetGallery/GetCurrentStillAlbum: {exc}")

    if album is None:
        for clave, pregunta in (
            ("F0-1", "¿ExportStills(..., 'drx') funciona en esta build?"),
            ("F0-2", "¿El still exportado lleva el grado aplicado o el material limpio?"),
        ):
            inf.responder(
                clave,
                pregunta,
                None,
                "No he podido coger el album actual de la galeria, asi que no he podido "
                "exportar ningun still.",
                "Sin respuesta: la app sigue asumiendo lo peor.",
            )
        return

    medias: dict[str, float | None] = {}
    try:
        grafo = item.GetNodeGraph(1)
        n_nodos = int(grafo.GetNumNodes())
        objetivo = 2 if n_nodos >= 2 else 1

        # 1) Un grado brutal e inconfundible: casi negro y sin color.
        item.SetCDL(
            {
                "NodeIndex": str(objetivo),
                "Slope": "0.05 0.05 0.05",
                "Offset": "0.0 0.0 0.0",
                "Power": "1.0 1.0 1.0",
                "Saturation": "0.0",
            }
        )
        antes = set(os.listdir(dir_pruebas))
        s1 = timeline.GrabStill()
        if s1:
            stills.append(s1)
            album.ExportStills([s1], dir_pruebas, "conGrado", "ppm")
            nuevos = ficheros_nuevos(dir_pruebas, antes)
            medias["con_grado"] = (
                leer_ppm_medio(os.path.join(dir_pruebas, nuevos[0])) if nuevos else None
            )

        # 2) El mismo fotograma con el nodo apagado.
        grafo.SetNodeEnabled(objetivo, False)
        antes = set(os.listdir(dir_pruebas))
        s2 = timeline.GrabStill()
        if s2:
            stills.append(s2)
            album.ExportStills([s2], dir_pruebas, "sinGrado", "ppm")
            nuevos = ficheros_nuevos(dir_pruebas, antes)
            medias["sin_grado"] = (
                leer_ppm_medio(os.path.join(dir_pruebas, nuevos[0])) if nuevos else None
            )
        grafo.SetNodeEnabled(objetivo, True)
    except BaseException as exc:  # noqa: BLE001
        inf.error(f"prueba F0-2: {type(exc).__name__}: {exc}")

    inf.datos["resolve"]["medias_stills"] = medias
    con, sin = medias.get("con_grado"), medias.get("sin_grado")
    if con is None or sin is None:
        respuesta_2 = None
        detalle_2 = (
            f"No he podido medir los dos stills (medias: {medias}). Puede que ExportStills no "
            f"escriba .ppm en esta build; mira que hay en {dir_pruebas}."
        )
    else:
        respuesta_2 = con < sin * 0.5
        detalle_2 = (
            f"Con un CDL de slope 0.05 y saturacion 0 el still exportado tiene un brillo medio "
            f"de {con:.4f}; con ese mismo nodo apagado, {sin:.4f}."
        )
    inf.responder(
        "F0-2",
        "¿El still exportado lleva el grado aplicado o el material limpio?",
        respuesta_2,
        detalle_2,
        "Lleva el grado. La app puede usar stills como 'el clip ya graduado' y medir sobre "
        "ellos: pon still_lleva_grado=True y se abre la puerta a la ingenieria inversa dentro "
        "de Resolve."
        if respuesta_2
        else "Sale limpio (o no se ha podido medir). La app NO puede medir el grado a traves de "
        "los stills: se queda midiendo sobre el fichero de origen, que es lo que hace hoy.",
    )

    # F0-1: el .drx
    respuesta_1 = None
    try:
        if stills:
            antes = set(os.listdir(dir_pruebas))
            devuelto = album.ExportStills([stills[0]], dir_pruebas, "probeDRX", "drx")
            nuevos = [f for f in ficheros_nuevos(dir_pruebas, antes) if f.lower().endswith(".drx")]
            respuesta_1 = bool(nuevos)
            detalle_1 = (
                f"ExportStills(..., 'drx') devolvio {devuelto!r} y en el directorio han "
                f"aparecido: {nuevos or 'ningun .drx'}."
            )
        else:
            detalle_1 = "No he llegado a coger ningun still, asi que no he podido exportarlo."
    except BaseException as exc:  # noqa: BLE001
        detalle_1 = f"ha saltado {type(exc).__name__}: {exc}"
        inf.error(f"prueba F0-1: {exc}")
    inf.responder(
        "F0-1",
        "¿ExportStills(..., 'drx') funciona en esta build?",
        respuesta_1,
        detalle_1,
        "Funciona: la app puede exportar PowerGrades a .drx y guardarlos en la sesion. Pon "
        "export_drx_funciona=True."
        if respuesta_1
        else "No escribe el .drx. La app no ofrece esa exportacion; los looks viajan como .cube, "
        "que es lo que ya hace.",
    )

    # Limpieza de la galeria.
    if stills:
        try:
            album.DeleteStills(stills)
            inf.datos["limpieza"]["stills_borrados"] = len(stills)
            ok(f"borrados {len(stills)} still(s) de la galeria")
        except BaseException as exc:  # noqa: BLE001
            inf.datos["limpieza"]["stills_borrados"] = f"fallo: {exc}"
            inf.aviso(
                f"no he podido borrar los {len(stills)} stills de la galeria; borralos tu "
                f"(estan en el album actual, son los ultimos)"
            )


def limpiar(inf: Informe, item, original: str | None, resolve, pagina_inicial: str | None) -> None:
    apartado("LIMPIEZA")
    # Dejar el nodo de la version de sonda sin CDL raro, por si la version se queda.
    try:
        grafo = item.GetNodeGraph(1)
        objetivo = 2 if int(grafo.GetNumNodes()) >= 2 else 1
        item.SetCDL(
            {
                "NodeIndex": str(objetivo),
                "Slope": "1.0 1.0 1.0",
                "Offset": "0.0 0.0 0.0",
                "Power": "1.0 1.0 1.0",
                "Saturation": "1.0",
            }
        )
        ok("CDL de la version de sonda devuelto a neutro")
    except BaseException as exc:  # noqa: BLE001
        inf.aviso(f"no he podido dejar el CDL en neutro: {exc}")

    if original:
        try:
            item.LoadVersionByName(original, 0)
            inf.datos["limpieza"]["version_restaurada"] = original
            ok(f"vuelta a tu version {original!r}")
        except BaseException as exc:  # noqa: BLE001
            inf.datos["limpieza"]["version_restaurada"] = f"fallo: {exc}"
            mal(f"NO he podido volver a tu version {original!r}: {exc}")
            inf.aviso(
                f"cambia a mano a la version {original!r} en la pagina de color antes de seguir "
                f"trabajando"
            )

    # Borrar la version de sonda: este metodo NO esta en la lista de llamadas
    # verificadas, asi que se prueba con hasattr y se informa de si existe.
    if hasattr(item, "DeleteVersionByName"):
        try:
            borrada = bool(item.DeleteVersionByName(VERSION_PROBE, 0))
            inf.datos["limpieza"]["version_probe_borrada"] = borrada
            (ok if borrada else mal)(f"DeleteVersionByName({VERSION_PROBE!r}) -> {borrada}")
        except BaseException as exc:  # noqa: BLE001
            inf.datos["limpieza"]["version_probe_borrada"] = f"fallo: {exc}"
            mal(f"DeleteVersionByName ha fallado: {exc}")
    else:
        inf.datos["limpieza"]["version_probe_borrada"] = "el metodo no existe en esta API"
        duda("la API no tiene DeleteVersionByName en esta build")
    if inf.datos["limpieza"].get("version_probe_borrada") is not True:
        inf.aviso(
            f"la version {VERSION_PROBE!r} se queda en el clip. Borrala a mano: pagina de color, "
            f"boton derecho sobre el clip > Local Versions."
        )

    if pagina_inicial:
        try:
            resolve.OpenPage(pagina_inicial)
            ok(f"Resolve devuelto a la pagina {pagina_inicial!r}")
        except BaseException as exc:  # noqa: BLE001
            inf.aviso(f"no he podido volver a la pagina {pagina_inicial!r}: {exc}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="api_probe.py",
        description=(
            "Sonda de la API de DaVinci Resolve para SIDEBFLMS COLOR. Le hace seis preguntas "
            "a tu Resolve y escribe un informe. Empieza siempre por --solo-diagnostico."
        ),
        epilog=(
            "EJEMPLOS:\n"
            "  python3 probe/api_probe.py --solo-diagnostico\n"
            "  python3 probe/api_probe.py --informe ~/Desktop/informe_resolve.json\n"
            "\n"
            "Antes de escribir nada te va a preguntar. Hasta entonces solo lee."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--informe",
        default=None,
        help="donde dejar el informe JSON (al lado se escribe el .txt). SIN esto no se "
        "escribe ningun fichero: el resumen sale solo por pantalla.",
    )
    p.add_argument(
        "--solo-diagnostico",
        action="store_true",
        help="mira el entorno y si el modulo se importa, y PARA. No se conecta a Resolve y no "
        "escribe ningun fichero (salvo que pidas --informe). Empieza siempre por aqui.",
    )
    p.add_argument(
        "--no-escribir",
        action="store_true",
        help="se conecta y mira, pero no crea versiones ni stills. Solo responde las preguntas "
        "que se pueden contestar leyendo.",
    )
    p.add_argument(
        "--si",
        action="store_true",
        help="no preguntar antes de escribir. Usalo solo en la segunda pasada, cuando ya sepas "
        "lo que hace.",
    )
    p.add_argument(
        "--clip",
        type=int,
        default=1,
        help="numero del clip del timeline sobre el que hacer las pruebas (1 = el primero).",
    )
    p.add_argument(
        "--dir-pruebas",
        default=None,
        help="carpeta donde escribir los ficheros de prueba. Por defecto, una carpeta nueva "
        "dentro de la temporal del sistema.",
    )
    p.add_argument(
        "--dctl",
        default=None,
        help="ruta RELATIVA a la carpeta de LUTs de un .dctl, para poder responder F0-3.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    inf = Informe()

    titulo("sonda de la api de davinci resolve - sidebflms color")
    linea("Esto no toca tu grado. Antes de escribir algo, te pregunta.")

    mirar_entorno(inf)
    dvr, instalacion = importar_modulo(inf)
    pregunta_f0_6(inf, dvr is not None)
    pregunta_f0_4(inf, instalacion, None)

    if args.solo_diagnostico:
        apartado("PARO AQUI (--solo-diagnostico)")
        if dvr is None:
            linea("  No he llegado a encontrar Resolve. Arregla lo de arriba y repite.")
        else:
            linea("  El modulo se importa. Ya puedes ejecutar sin --solo-diagnostico.")
        return terminar(inf, args)

    if dvr is None:
        apartado("NO SIGO")
        linea("  Sin el modulo de scripting no hay nada que preguntar. Arregla lo de arriba.")
        return terminar(inf, args)

    resolve = conectar(dvr, inf)
    if resolve is None:
        return terminar(inf, args)

    project, timeline, items = contexto(resolve, inf)
    # LA PRIMERA de todas, y de solo lectura: de que GetCurrentVersion conteste
    # bien depende que la app pueda escribir algo. Ver NOTAS.md, hallazgo E-3.
    if items:
        pregunta_v0_version_actual(inf, items)
    pagina_inicial = pregunta_f0_5_lectura(inf, resolve)
    inf.datos["preguntas"].pop("F0-4", None)
    pregunta_f0_4(inf, instalacion, project)
    dctl_rel = buscar_dctl(inf, instalacion, args.dctl)

    if not items:
        apartado("NO SIGO")
        linea("  Necesito un timeline con al menos un clip para el resto de preguntas.")
        return terminar(inf, args)

    if args.clip < 1 or args.clip > len(items):
        apartado("NO SIGO")
        linea(f"  --clip {args.clip} no vale: el timeline tiene {len(items)} clip(s).")
        inf.error(f"--clip {args.clip} fuera de rango")
        return terminar(inf, args)

    if args.no_escribir:
        apartado("PARO AQUI (--no-escribir)")
        linea("  Las preguntas F0-1, F0-2, F0-3 y F0-5 necesitan escribir para responderse.")
        return terminar(inf, args)

    dir_pruebas = args.dir_pruebas or tempfile.mkdtemp(prefix="sidebcolor_probe_")
    dir_pruebas = os.path.abspath(os.path.expanduser(dir_pruebas))
    os.makedirs(dir_pruebas, exist_ok=True)

    if not (args.si or preguntar_permiso(args, items, dir_pruebas)):
        apartado("DE ACUERDO, NO ESCRIBO NADA")
        linea("  Te dejo el informe con lo que he podido contestar leyendo.")
        return terminar(inf, args)

    # Ya ha dado permiso para escribir en `dir_pruebas`, asi que si no ha pedido
    # informe a ningun sitio, el informe cae ahi y no en su carpeta actual.
    if not args.informe:
        args.informe = os.path.join(dir_pruebas, "informe_probe_resolve.json")
        linea(f"  El informe lo dejare en {args.informe}")

    item = items[args.clip - 1]
    original, medidas = crear_version_probe(inf, item)
    pregunta_extra_nodos(inf, medidas)
    pregunta_f0_5(inf, resolve, item, pagina_inicial)
    pregunta_f0_3(inf, item, dctl_rel)
    preguntas_stills(inf, project, timeline, item, dir_pruebas)
    limpiar(inf, item, original, resolve, pagina_inicial)
    inf.datos["limpieza"]["dir_pruebas"] = dir_pruebas
    linea()
    linea(f"  Los ficheros de prueba se quedan en {dir_pruebas} por si quieres mirarlos.")
    return terminar(inf, args)


def terminar(inf: Informe, args) -> int:
    # Sin --informe NO se escribe nada, ni un fichero. Este script se ejecuta
    # desde donde a uno le pille (normalmente desde el propio repo) y no va a
    # dejar cosas sueltas por ahi sin que se las hayan pedido.
    ruta_json = ruta_txt = None
    if args.informe:
        try:
            ruta_json, ruta_txt = inf.escribir(args.informe)
        except OSError as exc:
            titulo("no he podido escribir el informe")
            linea(f"  {exc}")
            linea()
            linea(inf.a_texto())
            return 2
    titulo("resumen")
    sin_responder = [k for k, v in inf.datos["preguntas"].items() if v["respuesta"] is None]
    v0 = inf.datos["preguntas"].get("V-0")
    if v0 is not None and v0["respuesta"] is not True:
        linea("  *** MIRA PRIMERO LA V-0: si Resolve no dice en que version esta un clip,")
        linea("      la app no va a escribir nada. Es lo primero que hay que arreglar. ***")
        linea()
    for clave, p in inf.datos["preguntas"].items():
        etiqueta = {True: "SI", False: "NO", None: "SIN RESPUESTA"}.get(
            p["respuesta"], str(p["respuesta"])
        )
        linea(f"  {clave:<6} {etiqueta:<14} {p['pregunta']}")
    if inf.datos["avisos"]:
        linea()
        linea("  Cosas que mirar:")
        for a in inf.datos["avisos"]:
            linea(f"    - {a}")
    linea()
    if ruta_json:
        linea(f"  Informe JSON: {ruta_json}")
        linea(f"  Informe texto: {ruta_txt}")
        linea()
        linea("  Mandame el .json y ya cambio yo las seis constantes.")
    else:
        linea("  No he escrito ningun fichero: no me has pedido informe.")
        linea("  Para guardarlo, vuelve a ejecutar lo mismo anadiendo:")
        linea("      --informe ~/Desktop/informe_resolve.json")
    return 1 if (inf.datos["errores"] or sin_responder) else 0


if __name__ == "__main__":
    sys.exit(main())
