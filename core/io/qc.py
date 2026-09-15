"""Control de calidad de un LUT 3D.

Esto es lo que más importa de todo `core/io`: un `.cube` no da error, no
peta y no avisa de nada. Simplemente hace que la imagen salga mal. El QC es el
único sitio donde alguien mira el LUT y dice "esto tiene un escalón en la celda
(12, 4, 4) del eje rojo".

LA REGLA DE ORO
---------------
**Un LUT identidad tiene que pasar limpio, sin un solo aviso.** Si el QC da
falsos positivos sobre la identidad, la GUI se llena de avisos que nadie lee y
el módulo entero no sirve para nada. Ese es el test más importante del fichero
`tests/test_io_qc.py`, y cualquier umbral que se toque aquí tiene que seguir
respetándolo en 2, 17, 33 y 65.

QUÉ BUSCA, Y CÓMO
-----------------
1. `no_finito`   — NaN o infinito en la tabla. Error.
2. `lut_plano`   — todas las celdas iguales: el LUT no hace nada (o lo aplasta
                   todo a un color). Error.
3. `no_monotonia`— subes la entrada de un canal y baja su salida. Error.
                   Se mira la diagonal: eje de entrada `a` contra canal de
                   salida `a`. Un LUT puede mezclar canales todo lo que quiera
                   (eso es un tinte), pero que el rojo baje cuando subes el
                   rojo es siempre un defecto.
4. `banding`     — escalón brusco entre celdas contiguas. Ver abajo.
5. `gamut`       — valores de salida fuera de 0..1. Aviso, no error: un LUT de
                   look puede salirse a propósito y Resolve lo recorta.
6. `canales_invertidos` — el eje de entrada rojo mueve sobre todo el canal de
                   salida azul (o verde). Aviso: casi siempre es que alguien se
                   ha equivocado con la convención 4.

CÓMO SE MIDE EL BANDING, EXACTAMENTE
------------------------------------
Para cada eje de entrada `a` y cada canal de salida `c`:

    v   = tabla[..., c]
    d1  = diff(v, eje=a)          # el "paso" entre celdas contiguas, N-1 valores
    d2  = diff(d1, eje=a)         # cuánto cambia el paso, N-2 valores
    escala = mediana(|d1|)        # el paso típico de ese eje y ese canal

Se marca banding cuando **las dos** condiciones se cumplen a la vez:

    |d2| > UMBRAL_BANDING * max(escala, PISO)      (default UMBRAL_BANDING = 3)
    |d2| > SALTO_MINIMO_BANDING                     (default 0.02)

La primera condición es la que detecta el escalón: un paso que se sale tres
veces del paso típico. La segunda es la que evita el falso positivo tonto: en un
LUT casi plano la mediana es microscópica y cualquier ruido de float32 la supera
tres veces sin que se vea nada. 0.02 en salida son ~5/255, que es justo donde
una banda empieza a verse en un degradado limpio. La que protege al LUT
identidad es la SEGUNDA (su `d2` es ruido de float32, del orden de 1e-8), no la
primera; por eso se puede bajar el umbral relativo sin que la identidad se
manche.

Por qué la segunda derivada y no el salto relativo entre celdas vecinas: una
rampa con pendiente fuerte pero constante (un LUT que multiplica por 3) tiene
saltos grandes entre celdas y no produce ni una banda. Lo que se ve es el
**cambio** de pendiente, y eso es `d2`.

Aviso honesto: un LUT con una gamma muy fuerte cerca del negro (t**0.45, o su
gemela t**(1/2.2), que es la curva de salida más común que existe) **se ve
escalonado de verdad**, y el QC lo marca. Lo marca también con 65 puntos, así
que subir la resolución no es el remedio. No es un falso positivo: medido sobre
una rampa, ese LUT se desvía 11/255 de la curva que dice representar. Ver el
punto 3 de `NOTAS.md` para los números y para por qué el umbral se queda como
está.

EL AVISO INFORMA, NO BLOQUEA (y el mensaje tiene que decir POR QUÉ)
-------------------------------------------------------------------
Eso de arriba estaba bien detectado y mal contado. El aviso mandaba a arreglar
algo que en un LUT de salida **no está roto**, y Mario lo aclaró con estas
palabras: *si el LUT incluye la conversión a Rec.709, los escalones en sombras
son esperables y no son un defecto*.

Así que el mensaje ahora dice dónde está el escalón, cuánto mide, y **qué
significa que esté ahí**:

* si está en sombras (nivel de entrada <= `UMBRAL_SOMBRAS`), el texto
  `EXPLICACION_SOMBRAS` dice que en un LUT con gamma de salida eso es normal y
  no es un defecto;
* si está en los medios, `EXPLICACION_MEDIOS` dice que eso no es el
  achatamiento normal de una gamma y sí merece un vistazo.

Las dos dicen que es **un aviso y no un error**, porque lo es: `gravedad` es
`"aviso"`, `hay_errores` sigue siendo False y ni `escribir_cube` ni nadie
bloquea nada por esto. El detector no ha cambiado: lo que ha cambiado es lo que
se lee. Lo que decide la redacción es `UMBRAL_SOMBRAS`, que no toca en absoluto
lo que se marca ni cuánto.

EL RECUENTO: UN ESCALÓN NO SON MIL CELDAS
-----------------------------------------
Esto es el arreglo D-1 de la revisión de la ola 1, y es una lección que merece
quedar escrita porque no es evidente.

Un escalón vive en una POSICIÓN de la rejilla a lo largo de un eje. Pero la
tabla es un cubo: esa misma discontinuidad aparece en las `n*n` líneas
paralelas a ese eje. Contando celdas marcadas, un único escalón en el primer
intervalo de un LUT de 65 sale como **12.675 celdas** (3 ejes x 65 x 65).

Ese número no es falso, pero **miente sobre la magnitud del problema**: a quien
lo lee le dice que el LUT está roto, cuando lo que hay es un escalón en un
sitio. Así que:

* los `ProblemaQC` de banding van **agrupados por escalón** (eje, canal,
  posición), con `repeticiones` diciendo en cuántas líneas paralelas aparece;
* `metricas["escalones_de_banding"]` es el número honesto, y es el que usa
  `resumen()`, o sea el que ve Mario;
* `metricas["celdas_con_banding"]` sigue ahí, en bruto, para quien quiera el
  dato crudo. No es para enseñarlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.contracts import LUT3D

__all__ = [
    "ProblemaQC",
    "LUTQualityReport",
    "qc_lut",
    "CODIGO_NO_FINITO",
    "CODIGO_LUT_PLANO",
    "CODIGO_NO_MONOTONIA",
    "CODIGO_BANDING",
    "CODIGO_GAMUT",
    "CODIGO_CANALES_INVERTIDOS",
    "UMBRAL_BANDING",
    "SALTO_MINIMO_BANDING",
    "UMBRAL_SOMBRAS",
    "EXPLICACION_SOMBRAS",
    "EXPLICACION_MEDIOS",
    "MAX_PROBLEMAS_POR_CODIGO",
]

CODIGO_NO_FINITO = "no_finito"
CODIGO_LUT_PLANO = "lut_plano"
CODIGO_NO_MONOTONIA = "no_monotonia"
CODIGO_BANDING = "banding"
CODIGO_GAMUT = "gamut"
CODIGO_CANALES_INVERTIDOS = "canales_invertidos"

#: Cuántas veces el paso típico tiene que saltarse un cambio de pendiente para
#: contar como banding.
UMBRAL_BANDING: float = 3.0

#: Cambio de pendiente mínimo, en unidades de salida, para que cuente. 0.02 son
#: ~5/255: por debajo no se ve una banda ni buscándola.
SALTO_MINIMO_BANDING: float = 0.02

#: Hasta qué nivel de ENTRADA se considera que un escalón está "en sombras".
#: 0.125 es un octavo del recorrido de la rejilla. Con 17 puntos son los dos
#: primeros intervalos, con 33 los cuatro primeros y con 65 los ocho primeros:
#: siempre la misma zona de la imagen, mida lo que mida el LUT.
#:
#: No es un umbral de detección —no cambia lo que se marca ni cuánto— sino de
#: REDACCIÓN: decide si el aviso lleva la explicación de "esto es normal en un
#: LUT de salida" o la de "esto no es lo normal, míralo". Medido: la curva de
#: gamma de salida `x**(1/2.2)` marca exactamente un escalón por eje y siempre
#: en la posición 0, en 17, 33 y 65. O sea que cae del lado de "sombras" en los
#: tres tamaños, que es lo que Mario quiere que diga.
UMBRAL_SOMBRAS: float = 0.125

#: La frase que explica un escalón pegado al negro. Es lo que Mario pidió que
#: dijera, con sus palabras: si el LUT lleva la conversión a Rec.709, los
#: escalones en sombras son esperables y no son un defecto.
EXPLICACION_SOMBRAS = (
    "Si este LUT incluye la conversión a Rec.709 (o cualquier otra gamma de salida), los "
    "escalones en sombras son ESPERABLES y no son un defecto: la curva sube casi en vertical "
    "pegada al negro y una rejilla de puntos igual de separados no puede seguirla, ni con 65 "
    "puntos. Es un aviso, no un error: no bloquea nada, el LUT se escribe y se aplica igual. "
    "Sólo hay algo que arreglar si la banda se ve en la imagen."
)

#: Y la de un escalón que NO está pegado al negro, que es la que sí pide mirar.
EXPLICACION_MEDIOS = (
    "Este escalón no está pegado al negro, así que no es el achatamiento normal de una gamma "
    "de salida: en los medios una rejilla uniforme suele seguir bien la curva. Merece un "
    "vistazo a de dónde salió el LUT. Aun así es un aviso, no un error: no bloquea nada."
)

#: Suelo de la mediana de pasos, para no dividir por cero en un LUT plano.
_PISO_ESCALA: float = 1e-6

#: Tolerancia de monotonía. Por debajo de esto es ruido de float32, no un LUT
#: que baja.
TOL_MONOTONIA: float = 1e-5

#: Tolerancia de gamut: 1/2048, medio escalón de 11 bits. Por debajo no se ve.
TOL_GAMUT: float = 1.0 / 2048.0

#: Cuántas celdas se listan como mucho por cada tipo de problema. La GUI no va a
#: pintar 274.625 avisos; el total va en `metricas`.
MAX_PROBLEMAS_POR_CODIGO: int = 20

NOMBRE_CANAL = ("rojo", "verde", "azul")

#: código -> (clave de `metricas` con el total REAL, unidad para el resumen).
#: Lo que falte aquí se cuenta con la lista de problemas, que está recortada.
_METRICA_DE_RESUMEN: dict[str, tuple[str, str]] = {
    CODIGO_NO_FINITO: ("no_finitos", "valores"),
    CODIGO_NO_MONOTONIA: ("celdas_no_monotonas", "celdas"),
    CODIGO_BANDING: ("escalones_de_banding", "escalones"),
    CODIGO_GAMUT: ("valores_fuera_de_gamut", "valores"),
}


@dataclass(frozen=True)
class ProblemaQC:
    """Un problema concreto, en un sitio concreto. Listo para la GUI."""

    codigo: str
    gravedad: str  # "error" o "aviso"
    mensaje: str  # castellano, se enseña tal cual
    celda: tuple[int, int, int] | None = None  # (ri, gi, bi) representativa
    eje: int | None = None  # eje de ENTRADA: 0 rojo, 1 verde, 2 azul
    canal: int | None = None  # canal de SALIDA afectado
    valor: float = 0.0  # el número crudo, por si alguien quiere discutirlo
    repeticiones: int = 1
    """Cuántas celdas son EL MISMO defecto visto desde líneas paralelas.

    Sólo el detector de banding la usa hoy, y es lo que evita que la GUI diga
    "12.675 celdas con banding" cuando lo que hay es un escalón en una posición
    de la rejilla que se repite en las n*n líneas paralelas a ese eje. Ver el
    apartado "el recuento" del docstring del módulo.
    """


@dataclass(frozen=True)
class LUTQualityReport:
    """Lo que `qc_lut` devuelve. `ok` significa ni un solo problema."""

    size: int
    problemas: tuple[ProblemaQC, ...] = ()
    metricas: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True sólo si no hay NI UN aviso. Un LUT identidad tiene que dar True."""
        return not self.problemas

    @property
    def hay_errores(self) -> bool:
        """True si hay algún problema de gravedad 'error' (no sólo avisos)."""
        return any(p.gravedad == "error" for p in self.problemas)

    def por_codigo(self, codigo: str) -> tuple[ProblemaQC, ...]:
        return tuple(p for p in self.problemas if p.codigo == codigo)

    def codigos(self) -> tuple[str, ...]:
        """Los códigos presentes, sin repetir y en el orden en que aparecen."""
        vistos: list[str] = []
        for p in self.problemas:
            if p.codigo not in vistos:
                vistos.append(p.codigo)
        return tuple(vistos)

    def resumen(self) -> str:
        """Una línea en castellano para la barra de estado.

        El número que sale aquí es el que Mario va a leer, así que es el número
        que tiene que ser verdad. Para cada código se usa el total REAL de
        `metricas` (no el de la lista, que está recortada a
        `MAX_PROBLEMAS_POR_CODIGO`), y para el banding se usan **escalones**, no
        celdas: decir "12.675 celdas" de un solo escalón proyectado sobre n*n
        líneas paralelas es mentir sobre la magnitud del problema.
        """
        if self.ok:
            return f"LUT de {self.size}: limpio."
        partes = []
        for codigo in self.codigos():
            clave, unidad = _METRICA_DE_RESUMEN.get(codigo, ("", ""))
            if clave and clave in self.metricas:
                cuantos = int(self.metricas[clave])
            else:
                cuantos, unidad = len(self.por_codigo(codigo)), ""
            partes.append(f"{codigo} ({cuantos} {unidad})".replace(" )", ")"))
        return f"LUT de {self.size}: {', '.join(partes)}."


# ---------------------------------------------------------------------------
# Detectores
# ---------------------------------------------------------------------------


def _celda(idx: np.ndarray) -> tuple[int, int, int]:
    return (int(idx[0]), int(idx[1]), int(idx[2]))


def _no_finitos(table: np.ndarray) -> tuple[list[ProblemaQC], int]:
    mal = ~np.isfinite(table)
    total = int(mal.sum())
    if total == 0:
        return [], 0
    idx = np.argwhere(mal)[:MAX_PROBLEMAS_POR_CODIGO]
    problemas = []
    for fila in idx:
        celda = _celda(fila)
        canal = int(fila[3])
        valor = float(table[celda][canal])
        problemas.append(
            ProblemaQC(
                codigo=CODIGO_NO_FINITO,
                gravedad="error",
                mensaje=(
                    f"la celda {celda} tiene {valor} en el canal {NOMBRE_CANAL[canal]}: "
                    "un LUT con NaN o infinito no se puede ni escribir ni aplicar"
                ),
                celda=celda,
                canal=canal,
                valor=valor,
            )
        )
    return problemas, total


def _lut_plano(table: np.ndarray) -> list[ProblemaQC]:
    plano = table.reshape(-1, 3)
    if not np.isfinite(plano).all():
        return []  # ya lo cuenta _no_finitos; ptp con NaN no dice nada
    recorrido = float(np.ptp(plano, axis=0).max())
    if recorrido > 1e-6:
        return []
    color = tuple(round(float(v), 6) for v in plano[0])
    return [
        ProblemaQC(
            codigo=CODIGO_LUT_PLANO,
            gravedad="error",
            mensaje=(
                f"todas las celdas valen lo mismo ({color}): este LUT aplasta la imagen "
                "entera a un solo color"
            ),
            valor=recorrido,
        )
    ]


def _monotonia(table: np.ndarray, tol: float) -> tuple[list[ProblemaQC], int, float]:
    problemas: list[ProblemaQC] = []
    total = 0
    peor = 0.0
    for eje in range(3):
        v = table[..., eje]
        if v.shape[eje] < 2:
            continue
        d = np.diff(v, axis=eje)
        mal = d < -tol
        cuantos = int(mal.sum())
        total += cuantos
        if cuantos == 0:
            continue
        peor = min(peor, float(np.nanmin(d)))
        idx = np.argwhere(mal)[: MAX_PROBLEMAS_POR_CODIGO - len(problemas)]
        for fila in idx:
            desde = _celda(fila)
            hasta = list(desde)
            hasta[eje] += 1
            caida = float(d[tuple(fila)])
            problemas.append(
                ProblemaQC(
                    codigo=CODIGO_NO_MONOTONIA,
                    gravedad="error",
                    mensaje=(
                        f"eje {NOMBRE_CANAL[eje]}: al pasar de la celda {desde} a la "
                        f"{tuple(hasta)} la salida del canal {NOMBRE_CANAL[eje]} BAJA "
                        f"{abs(caida):.4f} en vez de subir"
                    ),
                    celda=desde,
                    eje=eje,
                    canal=eje,
                    valor=caida,
                )
            )
        if len(problemas) >= MAX_PROBLEMAS_POR_CODIGO:
            break
    return problemas, total, peor


def _banding(
    table: np.ndarray, umbral: float, salto_minimo: float
) -> tuple[list[ProblemaQC], int, int, float]:
    """Devuelve (problemas, celdas marcadas, ESCALONES distintos, peor salto).

    La diferencia entre "celdas marcadas" y "escalones distintos" es la clave
    del arreglo D-1. Ver el apartado "el recuento" del docstring del módulo.
    """
    problemas: list[ProblemaQC] = []
    total_celdas = 0
    total_escalones = 0
    peor = 0.0
    for eje in range(3):
        if table.shape[eje] < 3:
            continue  # con 2 muestras no hay segunda derivada que valga
        otros = tuple(a for a in range(3) if a != eje)
        for canal in range(3):
            v = table[..., canal]
            d1 = np.diff(v, axis=eje)
            d2 = np.diff(d1, axis=eje)
            if d2.size == 0:
                continue
            escala = float(np.median(np.abs(d1)))
            limite = umbral * max(escala, _PISO_ESCALA)
            abs_d2 = np.abs(d2)
            mal = (abs_d2 > limite) & (abs_d2 > salto_minimo)
            cuantos = int(mal.sum())
            total_celdas += cuantos
            if cuantos == 0:
                continue
            peor = max(peor, float(np.nanmax(abs_d2[mal])))

            # AGRUPAR POR ESCALÓN. Un escalón es una POSICIÓN de la rejilla a lo
            # largo de `eje`, no una celda: la misma discontinuidad aparece en
            # las n*n líneas paralelas a ese eje. Colapsamos los otros dos ejes.
            por_posicion = mal.sum(axis=otros)  # (n-2,)
            total_escalones += int((por_posicion > 0).sum())
            for pos in np.argwhere(por_posicion > 0).ravel():
                if len(problemas) >= MAX_PROBLEMAS_POR_CODIGO:
                    break
                corte = [slice(None), slice(None), slice(None)]
                corte[eje] = int(pos)
                plano_mal = mal[tuple(corte)]
                plano_d2 = np.where(plano_mal, abs_d2[tuple(corte)], -np.inf)
                fila, columna = np.unravel_index(int(np.argmax(plano_d2)), plano_d2.shape)

                indice = [0, 0, 0]
                indice[eje] = int(pos)
                indice[otros[0]] = int(fila)
                indice[otros[1]] = int(columna)
                salto = float(d2[tuple(indice)])
                celda = list(indice)
                celda[eje] += 1  # la celda que comparten los dos pasos
                repeticiones = int(por_posicion[pos])
                # El nivel de entrada de la celda que comparten los dos pasos.
                # Es lo que decide si el aviso se redacta como "normal en un LUT
                # de salida" o como "esto pide un vistazo". Ver UMBRAL_SOMBRAS.
                n_eje = int(table.shape[eje])
                nivel_entrada = (int(pos) + 1) / (n_eje - 1)
                en_sombras = nivel_entrada <= UMBRAL_SOMBRAS
                if pos == 0:
                    donde = "el primer intervalo de la rejilla (pegado al negro)"
                elif en_sombras:
                    donde = f"el intervalo {int(pos)} de la rejilla (todavía en sombras)"
                else:
                    donde = f"el intervalo {int(pos)} de la rejilla"
                extra = (
                    ""
                    if repeticiones == 1
                    else (
                        f" Es UN escalón, no {repeticiones}: se repite en {repeticiones} "
                        "líneas paralelas del cubo porque son la misma discontinuidad vista "
                        "desde cada una."
                    )
                )
                problemas.append(
                    ProblemaQC(
                        codigo=CODIGO_BANDING,
                        gravedad="aviso",
                        mensaje=(
                            f"eje {NOMBRE_CANAL[eje]}, canal {NOMBRE_CANAL[canal]}: en "
                            f"{donde}, alrededor de la celda {tuple(celda)}, el paso entre "
                            f"celdas cambia {abs(salto):.4f} de golpe (el paso típico de este "
                            f"eje es {escala:.4f}), y eso en un degradado puede verse como una "
                            f"banda.{extra} "
                            + (
                                EXPLICACION_SOMBRAS if en_sombras else EXPLICACION_MEDIOS
                            )
                        ),
                        celda=(celda[0], celda[1], celda[2]),
                        eje=eje,
                        canal=canal,
                        valor=salto,
                        repeticiones=repeticiones,
                    )
                )
    return problemas, total_celdas, total_escalones, peor


def _gamut(table: np.ndarray, tol: float) -> tuple[list[ProblemaQC], int, float, float]:
    finitos = np.isfinite(table)
    if not finitos.any():
        return [], 0, float("nan"), float("nan")
    minimo = float(np.nanmin(np.where(finitos, table, np.nan)))
    maximo = float(np.nanmax(np.where(finitos, table, np.nan)))
    fuera = finitos & ((table < -tol) | (table > 1.0 + tol))
    total = int(fuera.sum())
    if total == 0:
        return [], 0, minimo, maximo
    idx = np.argwhere(fuera)[:MAX_PROBLEMAS_POR_CODIGO]
    problemas = []
    for fila in idx:
        celda = _celda(fila)
        canal = int(fila[3])
        valor = float(table[celda][canal])
        lado = "por debajo de 0" if valor < 0 else "por encima de 1"
        problemas.append(
            ProblemaQC(
                codigo=CODIGO_GAMUT,
                gravedad="aviso",
                mensaje=(
                    f"la celda {celda} saca {valor:.4f} en el canal {NOMBRE_CANAL[canal]}, "
                    f"{lado}: Resolve lo recortará y ese detalle se pierde"
                ),
                celda=celda,
                canal=canal,
                valor=valor,
            )
        )
    return problemas, total, minimo, maximo


def _canales_invertidos(table: np.ndarray) -> list[ProblemaQC]:
    if not np.isfinite(table).all():
        return []
    m = np.zeros((3, 3), dtype=np.float64)
    for eje in range(3):
        if table.shape[eje] < 2:
            return []
        for canal in range(3):
            m[eje, canal] = float(np.mean(np.diff(table[..., canal], axis=eje)))
    problemas: list[ProblemaQC] = []
    for eje in range(3):
        fila = np.abs(m[eje])
        dominante = int(np.argmax(fila))
        if dominante == eje:
            continue
        # Sólo avisamos si el otro canal domina CLARAMENTE. Un LUT que
        # desatura mueve los tres canales por igual y no es un eje invertido.
        if fila[dominante] > 2.0 * fila[eje] + 1e-6:
            problemas.append(
                ProblemaQC(
                    codigo=CODIGO_CANALES_INVERTIDOS,
                    gravedad="aviso",
                    mensaje=(
                        f"subir la entrada {NOMBRE_CANAL[eje]} mueve sobre todo el canal de "
                        f"salida {NOMBRE_CANAL[dominante]} ({fila[dominante]:.4f}) y casi nada "
                        f"el {NOMBRE_CANAL[eje]} ({fila[eje]:.4f}): huele a ejes cambiados al "
                        "leer o escribir el .cube"
                    ),
                    eje=eje,
                    canal=dominante,
                    valor=float(fila[dominante]),
                )
            )
    return problemas


# ---------------------------------------------------------------------------
# La función pública
# ---------------------------------------------------------------------------


def qc_lut(
    lut: LUT3D,
    *,
    umbral_banding: float = UMBRAL_BANDING,
    salto_minimo_banding: float = SALTO_MINIMO_BANDING,
    tol_monotonia: float = TOL_MONOTONIA,
    tol_gamut: float = TOL_GAMUT,
) -> LUTQualityReport:
    """Pasa el LUT por los seis detectores y devuelve el informe.

    `informe.ok` es True sólo si no hay ni un aviso. `informe.hay_errores`
    distingue "esto no se puede ni escribir" de "esto es raro, mírate lo".

    Cada problema dice **dónde** está (celda, eje de entrada, canal de salida)
    porque la GUI lo va a enseñar y "hay banding" sin más no le sirve a nadie.
    """
    table = np.asarray(lut.table, dtype=np.float64)
    problemas: list[ProblemaQC] = []
    metricas: dict[str, float] = {"size": float(lut.size), "celdas": float(lut.size**3)}

    p_nan, n_nan = _no_finitos(table)
    problemas += p_nan
    metricas["no_finitos"] = float(n_nan)

    problemas += _lut_plano(table)

    p_mono, n_mono, peor_caida = _monotonia(table, tol_monotonia)
    problemas += p_mono
    metricas["celdas_no_monotonas"] = float(n_mono)
    metricas["peor_caida_monotonia"] = float(peor_caida)

    p_band, n_celdas_band, n_escalones, peor_salto = _banding(
        table, umbral_banding, salto_minimo_banding
    )
    problemas += p_band
    # OJO a la diferencia, que es el arreglo D-1 de la revisión:
    #   `celdas_con_banding`  = celdas marcadas, en bruto. Sube con n**2 aunque
    #                           el defecto sea uno solo. NO es lo que se enseña.
    #   `escalones_de_banding`= posiciones distintas de la rejilla. ES el número
    #                           que dice la verdad, y el que usa `resumen()`.
    metricas["celdas_con_banding"] = float(n_celdas_band)
    metricas["escalones_de_banding"] = float(n_escalones)
    metricas["peor_salto_banding"] = float(peor_salto)

    p_gam, n_gam, minimo, maximo = _gamut(table, tol_gamut)
    problemas += p_gam
    metricas["valores_fuera_de_gamut"] = float(n_gam)
    metricas["minimo"] = minimo
    metricas["maximo"] = maximo

    problemas += _canales_invertidos(table)

    metricas["problemas_listados"] = float(len(problemas))
    return LUTQualityReport(size=lut.size, problemas=tuple(problemas), metricas=metricas)
