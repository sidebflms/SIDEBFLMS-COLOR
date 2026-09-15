"""Excepciones, validaciones y la *secuencia segura* de escritura en Resolve.

El `Protocol` `ResolveBridge` vive en `core.contracts` y esta congelado. Aqui va
todo lo que las dos implementaciones (`FakeResolve` y, si manana se puede,
`LiveResolve`) comparten:

* La familia de excepciones. **Todas heredan de `ResolveError`**, que es lo unico
  que la GUI captura. Si anades una, que herede tambien.
* Las validaciones de los argumentos que la API real se toma a mal (indices de
  nodo 1-based, rutas de LUT relativas, nombres de version).
* `aplicar_grado_seguro()`, que es el unico camino por el que la app deberia
  escribir color. Hace las cosas en el orden que no rompe nada.

QUE SIGNIFICA "NADA DESTRUCTIVO"
--------------------------------
Antes de escribir un solo numero se crea (o se selecciona, si ya existe) la
version `SIDEB COLOR`. Todo lo que hace la app vive ahi. El grado que Mario
tenia queda intacto en su version, y para recuperarlo solo tiene que cargar la
suya. Esto importa especialmente porque `ApplyGradeFromDRX` **reemplaza el arbol
de nodos entero**: si algun dia la app lo usa, sin version previa se cargaria el
trabajo de alguien.

**Y no depende de que nadie se acuerde.** El puente se niega en redondo a
escribir grado en un clip cuya version activa no sea una de la app: `set_cdl`,
`set_lut`, `set_node_enabled`, `copy_grades` y `reset_all_grades` lanzan
`EscrituraFueraDeVersion`. Hasta la revision de la ronda 1 esto era solo una
convencion que vivia dentro de `aplicar_grado_seguro()`, y una convencion la
rompe cualquiera que tenga el puente a mano. Ahora es un `if`.

La via de escape existe, se llama `PELIGRO_escribir_fuera_de_la_version`, es un
atributo del puente y tiene ese nombre para que se vea de lejos. La app no la
usa nunca; los tests si, cuando montan "el grado que el usuario ya tenia".

CUANDO SE LANZA Y CUANDO SE DEVUELVE False
-------------------------------------------
* **Lanza `ResolveError`** todo lo que es un error de programa o una precondicion
  rota: no hay conexion, el clip no existe, el indice de nodo es 0, la ruta del
  LUT es absoluta, el nombre de version esta vacio, no hay timeline.
* **Devuelve `False`** lo que la API real contesta que no sin que nadie haya
  hecho nada mal: crear una version con un nombre que ya existe, cargar una
  version que no esta. Son respuestas, no averias.

Quien llama tiene que mirar el bool. Por eso `aplicar_grado_seguro` existe: para
que no haya que acordarse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from core.contracts import (
    CDL,
    NODE_BALANCE,
    NODE_LOOK,
    NODE_NORMALIZACION,
    VERSION_NAME,
    NodeInfo,
    ResolveBridge,
    ResolveError,
)
from core.resolve.incognitas import (
    INCOGNITAS_CONSERVADORAS,
    Incognitas,
    extensiones_lut_aceptadas,
)

# ---------------------------------------------------------------------------
# Excepciones. Todas heredan de ResolveError: la GUI captura solo esa.
# ---------------------------------------------------------------------------


class ResolveNoConectado(ResolveError):
    """No hay conexion con Resolve (no esta abierto, o el puente esta cerrado)."""


class TimelineNoAbierto(ResolveError):
    """Hay proyecto pero no hay timeline activo. Sin timeline no hay clips."""


class ClipNoEncontrado(ResolveError):
    """Ese `clip_id` no esta en el timeline actual."""


class GrupoNoEncontrado(ResolveError):
    """Ese grupo de color no existe en el proyecto."""


class NodoInvalido(ResolveError):
    """Indice de nodo fuera de rango, o 0/negativo (la API es 1-based)."""


class RutaLUTInvalida(ResolveError):
    """La ruta del LUT no vale: absoluta, vacia, o con una extension que no entra."""


class VersionInvalida(ResolveError):
    """Nombre de version vacio o que no existe cuando tendria que existir."""


class EscrituraFueraDeVersion(ResolveError):
    """Se ha intentado escribir grado en una version que no es la de la app.

    Esta es **la regla de oro convertida en error**. Hasta la ronda 1 de revision
    la regla vivia solo dentro de `aplicar_grado_seguro()`, o sea que se cumplia
    si el que llamaba se acordaba. Ahora la impone el propio puente: `set_cdl`,
    `set_lut`, `set_node_enabled`, `copy_grades` y `reset_all_grades` se niegan a
    escribir si la version activa del clip no es una nuestra.
    """


class VersionIndeterminada(EscrituraFueraDeVersion):
    """No se ha podido saber en que version esta el clip, asi que no se escribe.

    Es distinto de `EscrituraFueraDeVersion` a secas: alli SABEMOS que la version
    es del usuario; aqui no sabemos nada. `GetCurrentVersion()` ha devuelto una
    cadena vacia, un `None` o algo que no es un nombre.

    **Aun asi bloquea**, y hereda de `EscrituraFueraDeVersion` para que quien ya
    capturaba aquella siga capturando esta. El razonamiento esta entero en
    NOTAS.md; el resumen es que las dos salidas no cuestan lo mismo: si
    bloqueamos y resulta que no hacia falta, se pierde una mañana y no se rompe
    nada; si escribimos y resulta que estabamos en la version del usuario, se
    pierde el trabajo de alguien y no hay deshacer.

    Lo que si cambia es el mensaje: este dice que el sospechoso es la API y no
    el usuario, y donde mirar.
    """


class OperacionNoDisponible(ResolveError):
    """La API no tiene esto, o una incognita F0-n dice que hoy asumimos que no."""


# ---------------------------------------------------------------------------
# Validaciones de argumentos
# ---------------------------------------------------------------------------


def validar_indice_nodo(node_index: int, n_nodos: int | None = None) -> int:
    """Los indices de nodo de Resolve son 1-based. El 0 no existe.

    Si se pasa `n_nodos`, comprueba tambien el limite superior. La API real, con
    un indice fuera de rango, devuelve False sin decir por que; preferimos
    lanzar y que se vea donde estaba el fallo.
    """
    # Un entero de verdad y nada mas. NO se admite un float, ni una cadena, ni
    # un bool, y sobre todo NO se trunca: `int(2.9999999999)` es 2, o sea que un
    # indice calculado que para cualquiera es el nodo 3 acabaria escribiendo en
    # el 2 sin decir ni mu. Escribir en el nodo equivocado en silencio es justo
    # el fallo que este modulo existe para evitar. Si a alguien le llega un
    # indice decimal, que decida EL si es el 2 o el 3, y que lo redondee donde
    # se pueda ver. Aqui no se adivina.
    if isinstance(node_index, bool) or not isinstance(node_index, int):
        raise NodoInvalido(
            f"el indice de nodo tiene que ser un entero, y llego {node_index!r} "
            f"({type(node_index).__name__}). No se convierte solo a proposito: truncar un "
            f"2.9999999999 daria el nodo 2 cuando se queria el 3, y nadie se enteraria. "
            f"Redondealo tu con round() antes de llamar."
        )
    idx = node_index
    if idx < 1:
        raise NodoInvalido(
            f"los indices de nodo de Resolve son 1-based: {idx} no es un nodo valido"
        )
    if n_nodos is not None and idx > n_nodos:
        raise NodoInvalido(f"el clip tiene {n_nodos} nodos y se ha pedido el {idx}")
    return idx


def validar_ruta_lut_relativa(
    lut_rel_path: str, incognitas: Incognitas = INCOGNITAS_CONSERVADORAS
) -> str:
    """`SetLUT` quiere una ruta RELATIVA a la carpeta de LUTs de Resolve.

    Una ruta absoluta se la traga sin protestar y luego el nodo se queda sin
    LUT, que es el peor de los fallos: silencioso. Aqui se corta antes.
    """
    if not isinstance(lut_rel_path, str) or not lut_rel_path.strip():
        raise RutaLUTInvalida("la ruta del LUT esta vacia")
    ruta = lut_rel_path.strip()
    if os.path.isabs(ruta) or ruta.startswith("~"):
        raise RutaLUTInvalida(
            f"SetLUT quiere una ruta RELATIVA a la carpeta de LUTs de Resolve, "
            f"no una absoluta: {ruta!r}"
        )
    partes = ruta.replace("\\", "/").split("/")
    if any(p == ".." for p in partes):
        raise RutaLUTInvalida(f"la ruta del LUT no puede salirse de la carpeta de LUTs: {ruta!r}")
    aceptadas = extensiones_lut_aceptadas(incognitas)
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in aceptadas:
        raise RutaLUTInvalida(
            f"extension {ext or '(ninguna)'} no aceptada; hoy se admiten {', '.join(aceptadas)}. "
            f"Si es un .dctl, mira la incognita F0-3."
        )
    return ruta


def validar_nombre_version(name: str) -> str:
    """Una version sin nombre no se puede volver a cargar. La API deja crearla."""
    if not isinstance(name, str) or not name.strip():
        raise VersionInvalida(
            "el nombre de la version no puede estar vacio: sin nombre no hay forma "
            "de volver a cargarla con LoadVersionByName"
        )
    return name.strip()


# ---------------------------------------------------------------------------
# Base comun de las implementaciones
# ---------------------------------------------------------------------------


def es_version_nuestra(nombre: str) -> bool:
    """¿Esa version la ha creado la app?

    Por convenio de nombre, y no hay otra forma: la API no marca de ningun modo
    quien creo una version. Valen `SIDEB COLOR` y cualquiera que empiece por
    `SIDEB COLOR ` (la del probe es `SIDEB COLOR PROBE`). `Version 1`, `Cliente`
    o lo que sea que tenga Mario, no.

    Si alguien llama a una version suya `SIDEB COLOR loquesea`, la app se la
    creera. Es el precio de no tener forma de preguntarlo; el nombre es lo
    bastante raro como para que no pase por accidente.
    """
    return nombre == VERSION_NAME or nombre.startswith(VERSION_NAME + " ")


class BaseResolveBridge:
    """Lo que `FakeResolve` y `LiveResolve` hacen igual.

    No es un `Protocol` ni pretende serlo: es solo para no escribir dos veces
    las mismas cuatro validaciones. Quien manda sigue siendo
    `core.contracts.ResolveBridge`.

    Aqui vive tambien **la regla de oro**, que ya no es una convencion: es un
    `if`. Ver `_exigir_version_propia`.
    """

    incognitas: Incognitas = INCOGNITAS_CONSERVADORAS

    #: VIA DE ESCAPE. Ponlo a True y el puente deja de proteger la version del
    #: usuario: se escribe donde sea que este, y si eso pisa el grado de alguien,
    #: es cosa tuya. Se llama asi de feo A PROPOSITO, para que salte a la vista
    #: en una revision y para que se pueda buscar con grep en dos segundos.
    #:
    #: Usos legitimos, que los hay:
    #:   * los tests, cuando montan "el grado que el usuario ya tenia";
    #:   * una herramienta de diagnostico que tenga que tocar la version actual
    #:     a sabiendas (el probe, por ejemplo).
    #: Uso ilegitimo: la app. Si la app lo necesita, el diseno esta mal.
    #:
    #: Es un atributo y no un metodo para que se vea en el sitio donde se pone,
    #: y para que no se pueda llamar de pasada desde otro modulo.
    PELIGRO_escribir_fuera_de_la_version: bool = False

    def _validar_lut(self, lut_rel_path: str) -> str:
        return validar_ruta_lut_relativa(lut_rel_path, self.incognitas)

    @staticmethod
    def _validar_nodo(node_index: int, n_nodos: int | None = None) -> int:
        return validar_indice_nodo(node_index, n_nodos)

    def _exigir_version_propia(self, clip_id: str, version_activa: str, operacion: str) -> None:
        """LA REGLA DE ORO. Nada de escribir encima del grado de nadie.

        Se llama al final de las validaciones de cada escritura, justo antes de
        tocar nada: asi un indice de nodo malo o una ruta de LUT mala siguen
        saliendo como lo que son, y no disfrazados de problema de version.
        """
        if self.PELIGRO_escribir_fuera_de_la_version:
            return
        # Caso 1: no se puede SABER en que version estamos. Nadie ha visto
        # nunca `GetCurrentVersion()` contestar contra Resolve de verdad, asi
        # que este camino es perfectamente posible manana por la mañana.
        if not isinstance(version_activa, str) or not version_activa.strip():
            raise VersionIndeterminada(
                f"{operacion}: no he podido saber en que version de color esta el clip "
                f"{clip_id!r}. GetCurrentVersion() ha devuelto {version_activa!r}, que no es un "
                f"nombre de version.\n"
                f"No escribo nada: si resultara que el clip esta en la version del usuario, le "
                f"borraria el grado y no hay forma de deshacerlo.\n"
                f"Esto huele a la API, no a ti. Ejecuta `python3 probe/api_probe.py` y mira la "
                f"pregunta V-0, que es justo esta. Si el probe dice que GetCurrentVersion va bien "
                f"en tu Resolve y aun asi sale esto, avisame.\n"
                f"Para salir del paso a sabiendas: "
                f"`bridge.PELIGRO_escribir_fuera_de_la_version = True`."
            )
        # Caso 2: se sabe, y no es nuestra.
        if es_version_nuestra(version_activa):
            return
        raise EscrituraFueraDeVersion(
            f"{operacion}: la version activa del clip {clip_id!r} es {version_activa!r}, que no "
            f"es de la app. Ahi esta el grado del usuario y no se toca.\n"
            f"Antes de escribir hay que crear o seleccionar la version {VERSION_NAME!r}: la "
            f"forma buena es `aplicar_grado_seguro(bridge, clip_id, ...)`, que ya lo hace, o "
            f"`asegurar_version(bridge, clip_id)` si quieres escribir tu a mano.\n"
            f"Si de verdad sabes lo que haces y quieres escribir encima, pon "
            f"`bridge.PELIGRO_escribir_fuera_de_la_version = True`."
        )

    @staticmethod
    def _validar_version(name: str) -> str:
        return validar_nombre_version(name)


# ---------------------------------------------------------------------------
# La secuencia segura
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoAplicacion:
    """Que se ha escrito de verdad en un clip, y que avisos han salido."""

    clip_id: str
    version: str
    cdl_escrito: bool
    lut_escrito: bool
    avisos: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return self.cdl_escrito or self.lut_escrito


def asegurar_pagina_color(
    bridge: ResolveBridge, incognitas: Incognitas = INCOGNITAS_CONSERVADORAS
) -> bool:
    """Abre la pagina de color si la incognita F0-5 dice que hace falta.

    Llamarlo de mas solo cambia de pagina. No llamarlo cuando hacia falta puede
    dejar escrituras que no se aplican y no avisan, asi que por defecto se llama.
    """
    # TODO(F0-5) Unico sitio donde se decide si hace falta OpenPage("color").
    if not incognitas.requiere_open_page:
        return False
    return bool(bridge.open_page("color"))


def asegurar_version(
    bridge: ResolveBridge, clip_id: str, nombre: str = VERSION_NAME
) -> str:
    """Deja el clip con la version `nombre` activa, creandola si no estaba.

    Es idempotente a proposito: volver a pasar la app por el mismo clip no tiene
    que crear `SIDEB COLOR 2`, `SIDEB COLOR 3`... Devuelve el nombre de la
    version activa al terminar.
    """
    nombre = validar_nombre_version(nombre)
    existentes = bridge.version_names(clip_id)
    if nombre in existentes:
        if bridge.current_version(clip_id) != nombre and not bridge.load_version(clip_id, nombre):
            raise VersionInvalida(
                f"la version {nombre!r} existe en {clip_id} pero Resolve no la ha cargado"
            )
    else:
        if not bridge.add_version(clip_id, nombre):
            raise VersionInvalida(f"Resolve no ha creado la version {nombre!r} en {clip_id}")
        # La semantica real: crear una version la deja seleccionada. Lo
        # comprobamos igualmente, porque si no lo hiciera escribiriamos encima
        # del grado de Mario.
        if bridge.current_version(clip_id) != nombre:
            bridge.load_version(clip_id, nombre)
    actual = bridge.current_version(clip_id)
    if actual != nombre:
        raise VersionInvalida(
            f"despues de asegurar {nombre!r}, la version activa de {clip_id} sigue siendo "
            f"{actual!r}. No se escribe nada: seria encima del grado original."
        )
    return actual


def _proyecto_gestionado(bridge: ResolveBridge) -> bool:
    """¿La normalizacion la hace la gestion de color del proyecto?

    Si el proyecto esta en 'DaVinci YRGB Color Managed' (o similar), el nodo 1
    puede estar vacio y aun asi el material llega normalizado. Si es 'DaVinci
    YRGB' a secas, un nodo 1 vacio significa que no normaliza nadie.
    """
    try:
        return "managed" in bridge.project_info().color_science.lower()
    except ResolveError:
        return False


def verificar_estructura_nodos(bridge: ResolveBridge, clip_id: str) -> tuple[str, ...]:
    """Comprueba que el clip tiene los tres nodos del diseno. Devuelve avisos.

    **La app no crea nodos porque la API no sabe crear nodos.** No hay
    `AddNode`, no hay forma de reordenarlos ni de borrarlos. Asi que lo unico
    que se puede hacer es mirar si estan y decirlo claro si no. Si faltan, se
    lanza: escribir un CDL en el nodo 2 de un clip que solo tiene uno no falla
    con estruendo, falla en silencio.
    """
    nodos = bridge.list_nodes(clip_id)
    avisos: list[str] = []
    if len(nodos) < NODE_LOOK:
        raise NodoInvalido(
            f"el clip {clip_id} tiene {len(nodos)} nodo(s) y el diseno necesita {NODE_LOOK} "
            f"(1 normalizacion, 2 balance, 3 look). La API de Resolve NO sabe crear nodos: "
            f"hay que anadirlos a mano en la pagina de color, o partir de un PowerGrade que "
            f"ya los traiga."
        )
    por_indice = {n.index: n for n in nodos}
    norm = por_indice.get(NODE_NORMALIZACION)
    if norm is None:
        raise NodoInvalido(f"el clip {clip_id} no tiene nodo {NODE_NORMALIZACION}")
    if not norm.enabled:
        avisos.append(
            f"el nodo {NODE_NORMALIZACION} (normalizacion) esta desactivado; la app no lo toca, "
            f"pero el resultado no sera el esperado"
        )
    if norm.lut_path is None and not _proyecto_gestionado(bridge):
        avisos.append(
            f"el nodo {NODE_NORMALIZACION} (normalizacion) no tiene LUT y el proyecto no esta en "
            f"gestion de color de Resolve: no hay nada normalizando el material. El balance y el "
            f"look van a salir raros."
        )
    if len(nodos) > NODE_LOOK:
        avisos.append(
            f"el clip tiene {len(nodos)} nodos y la app solo escribe en el {NODE_BALANCE} y el "
            f"{NODE_LOOK}; los demas se quedan como estaban"
        )
    return tuple(avisos)


def aplicar_grado_seguro(
    bridge: ResolveBridge,
    clip_id: str,
    *,
    cdl: CDL | None = None,
    lut_rel_path: str | None = None,
    version: str = VERSION_NAME,
    incognitas: Incognitas = INCOGNITAS_CONSERVADORAS,
    verificar_lut: bool = True,
) -> ResultadoAplicacion:
    """El **unico** camino por el que la app deberia escribir color.

    El orden no es negociable:

    1. Abrir la pagina de color, si F0-5 dice que hace falta.
    2. Crear o seleccionar la version `SIDEB COLOR`. Nada se escribe antes.
    3. Verificar que estan los tres nodos. Si no estan, se para aqui.
    4. Escribir el CDL en el nodo 2 (balance).
    5. Escribir el LUT en el nodo 3 (look), con ruta relativa.
    6. Releer el LUT con `GetLUT` para confirmar. El CDL no se puede releer:
       `GetCDL` no existe en la API.

    Si no se pasa ni `cdl` ni `lut_rel_path` no se escribe nada, pero la version
    se crea igual: deja el clip preparado y no cuesta nada.
    """
    if lut_rel_path is not None:
        lut_rel_path = validar_ruta_lut_relativa(lut_rel_path, incognitas)
    if not es_version_nuestra(validar_nombre_version(version)):
        raise VersionInvalida(
            f"la app solo escribe en versiones suyas, y {version!r} no lo es. Tiene que ser "
            f"{VERSION_NAME!r} o empezar por {VERSION_NAME + ' '!r}."
        )

    asegurar_pagina_color(bridge, incognitas)
    activa = asegurar_version(bridge, clip_id, version)
    avisos = list(verificar_estructura_nodos(bridge, clip_id))

    cdl_escrito = False
    if cdl is not None:
        if cdl.is_identity():
            avisos.append(
                f"el CDL del clip {clip_id} es la identidad; se escribe igualmente para que el "
                f"nodo {NODE_BALANCE} quede en un estado conocido"
            )
        if not bridge.set_cdl(clip_id, NODE_BALANCE, cdl):
            raise ResolveError(
                f"Resolve no ha aceptado el CDL en el nodo {NODE_BALANCE} de {clip_id}"
            )
        cdl_escrito = True

    lut_escrito = False
    if lut_rel_path is not None:
        if not bridge.set_lut(clip_id, NODE_LOOK, lut_rel_path):
            raise ResolveError(
                f"Resolve no ha aceptado el LUT {lut_rel_path!r} en el nodo {NODE_LOOK} de "
                f"{clip_id}. Comprueba que el .cube esta dentro de la carpeta de LUTs y que se "
                f"ha llamado a RefreshLUTList()"
            )
        lut_escrito = True
        if verificar_lut:
            leido = bridge.get_lut(clip_id, NODE_LOOK)
            if leido is None:
                avisos.append(
                    f"GetLUT no devuelve nada para el nodo {NODE_LOOK} de {clip_id} despues de "
                    f"escribirlo; el look podria no estar puesto"
                )
            elif os.path.basename(leido) != os.path.basename(lut_rel_path):
                avisos.append(
                    f"GetLUT devuelve {leido!r} y se escribio {lut_rel_path!r}; Resolve puede "
                    f"normalizar la ruta, pero conviene mirarlo"
                )

    return ResultadoAplicacion(
        clip_id=clip_id,
        version=activa,
        cdl_escrito=cdl_escrito,
        lut_escrito=lut_escrito,
        avisos=tuple(avisos),
    )


def copiar_grado_seguro(
    bridge: ResolveBridge,
    clip_origen: str,
    clips_destino: list[str],
    *,
    version: str = VERSION_NAME,
) -> ResultadoAplicacion:
    """Copia el grado de un clip a otros SIN pisarle el grado a nadie.

    `CopyGrades` reemplaza el arbol de nodos entero del destino, en la version
    que tenga activa. Llamarlo a pelo sobre clips que estan en la version del
    usuario es la forma mas rapida de cargarse una tarde de trabajo. Asi que
    aqui se le crea (o se le selecciona) la version `SIDEB COLOR` a **cada
    destino** antes de copiar nada.

    Si algun destino no se puede preparar, no se copia a ninguno.
    """
    if not clips_destino:
        return ResultadoAplicacion(
            clip_id=clip_origen,
            version=bridge.current_version(clip_origen),
            cdl_escrito=False,
            lut_escrito=False,
            avisos=("no se ha dado ningun clip de destino: no se ha copiado nada",),
        )
    for destino in clips_destino:
        asegurar_version(bridge, destino, version)
    origen_version = bridge.current_version(clip_origen)
    avisos: list[str] = []
    if not es_version_nuestra(origen_version):
        avisos.append(
            f"el clip de origen {clip_origen!r} esta en la version {origen_version!r}, que no es "
            f"de la app: se copia el grado que haya ahi, que es el del usuario"
        )
    if not bridge.copy_grades(clip_origen, list(clips_destino)):
        raise ResolveError(
            f"Resolve no ha copiado el grado de {clip_origen!r} a {clips_destino}"
        )
    return ResultadoAplicacion(
        clip_id=clip_origen,
        version=origen_version,
        cdl_escrito=True,
        lut_escrito=True,
        avisos=tuple(avisos),
    )


def resumen_nodos(nodos: list[NodeInfo]) -> str:
    """Una linea legible por nodo, para la GUI y para los informes."""
    if not nodos:
        return "(sin nodos)"
    lineas = []
    for n in nodos:
        estado = "on" if n.enabled else "OFF"
        lut = n.lut_path or "-"
        etiqueta = n.label or "(sin etiqueta)"
        lineas.append(f"{n.index}. {etiqueta} [{estado}] LUT: {lut}")
    return "\n".join(lineas)


__all__ = [
    "BaseResolveBridge",
    "ClipNoEncontrado",
    "EscrituraFueraDeVersion",
    "GrupoNoEncontrado",
    "NodoInvalido",
    "OperacionNoDisponible",
    "ResolveNoConectado",
    "ResultadoAplicacion",
    "RutaLUTInvalida",
    "TimelineNoAbierto",
    "VersionIndeterminada",
    "VersionInvalida",
    "aplicar_grado_seguro",
    "asegurar_pagina_color",
    "asegurar_version",
    "copiar_grado_seguro",
    "es_version_nuestra",
    "resumen_nodos",
    "validar_indice_nodo",
    "validar_nombre_version",
    "validar_ruta_lut_relativa",
    "verificar_estructura_nodos",
]
