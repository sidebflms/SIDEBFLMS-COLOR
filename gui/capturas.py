"""Regenera `capturas/` entera de una sentada.

    QT_QPA_PLATFORM=offscreen .venv/bin/python -m gui.capturas

Tres anchuras por pantalla, como manda `docs/IDENTIDAD.md`: **1440, 1024 y la
anchura minima REAL de la ventana**, que se pregunta a Qt
(`VentanaPrincipal.anchura_minima()`) y no se decide a ojo. La tercera no es un
capricho: en la app hermana de ingest el recorte de texto al redimensionar ha
sido un fallo recurrente, y solo se ve estrujando la ventana hasta donde de.

Ademas de las cuatro pantallas nominales se captura **un caso frontera por
fichero**: cero clips, un clip, doscientos, confianza baja en todos, clip sin
imagen, Resolve desconectado, un fallo de escritura de verdad, un LUT que no
pasa el QC y una cobertura casi nula.

El indice que se imprime al final es el que va al informe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from gui import datos_demo as dd
from gui import reverse_puente as rp
from gui.ventana import VentanaPrincipal, crear_app

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "capturas"

ANCHURAS_NOMINALES = (1440, 1024)
ALTO_NOMINAL = 900


@dataclass(frozen=True)
class Captura:
    nombre: str
    descripcion: str


def _asentar(app: QApplication, ventana: VentanaPrincipal, veces: int = 3) -> None:
    """Deja que Qt termine layouts y repintados antes de disparar.

    Tres pasadas y no una: el primer `processEvents` resuelve el layout, el
    segundo los `resizeEvent` que reeliden el texto, y el tercero el repintado
    con el texto ya recortado. Con una sola pasada salen capturas con el texto
    de la anchura anterior, que es una captura mentirosa.
    """
    for _ in range(veces):
        app.processEvents()


def _disparar(app: QApplication, ventana: VentanaPrincipal, ruta: Path,
              ancho: int, alto: int) -> None:
    ventana.resize(QSize(ancho, alto))
    _asentar(app, ventana)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not ventana.grab().save(str(ruta), "PNG"):
        raise RuntimeError(f"no se ha podido guardar {ruta}")


def _ventana(app: QApplication, estado, indice: int, *, par=None) -> VentanaPrincipal:
    ventana = VentanaPrincipal(estado, par_inverso=par)
    ventana.resize(1440, ALTO_NOMINAL)
    ventana.show()
    ventana.ir_a(indice)
    _asentar(app, ventana)
    return ventana


def generar(destino: Path = DESTINO) -> list[Captura]:
    app = crear_app([])
    hechas: list[Captura] = []
    destino.mkdir(parents=True, exist_ok=True)

    base = dd.estado_demo()
    patron = VentanaPrincipal(base)
    patron.resize(1440, ALTO_NOMINAL)
    patron.show()
    _asentar(app, patron)
    minimo = patron.anchura_minima()
    alto_minimo = max(patron.minimumSizeHint().height(), 560)
    patron.close()

    anchuras = (*ANCHURAS_NOMINALES, minimo)

    nominales = (
        (0, "01-clips", "lista de clips con su confianza por forma y la ficha de razones"),
        (1, "02-comparar", "antes/después con la cortinilla a la mitad"),
        (2, "03-aplicar", "plan de escritura antes de aplicar, con la versión SIDEB COLOR"),
        (3, "04-reverse", "panel de ingeniería inversa: CDL, LUT, cobertura y diagnóstico"),
    )
    for indice, nombre, desc in nominales:
        ventana = _ventana(app, dd.estado_demo(), indice)
        for ancho in anchuras:
            alto = ALTO_NOMINAL if ancho != minimo else alto_minimo
            fichero = destino / f"{nombre}-{ancho}.png"
            _disparar(app, ventana, fichero, ancho, alto)
            hechas.append(Captura(fichero.name, f"{desc} · {ancho}×{alto}"))
        ventana.close()

    # --- casos frontera -------------------------------------------------
    frontera: list[tuple[str, str, int, object, int, int]] = []

    frontera.append(("05-clips-cero", "cero clips: la pantalla lo dice en vez de quedarse en blanco",
                     0, dd.estado_vacio(), 1024, ALTO_NOMINAL))
    frontera.append(("06-clips-uno", "un solo clip", 0, dd.estado_un_clip(), 1024, ALTO_NOMINAL))

    muchos = dd.estado_muchos(200)
    frontera.append(("07-clips-doscientos", "doscientos clips, con nombres largos elididos",
                     0, muchos, 1024, ALTO_NOMINAL))
    frontera.append(("07-clips-doscientos-minimo",
                     "los mismos doscientos a la anchura mínima", 0, muchos, minimo, alto_minimo))
    frontera.append(("08-comparar-sin-imagen",
                     "clip del lote grande sin fotograma en memoria: se dice, no se revienta",
                     1, muchos, 1024, ALTO_NOMINAL))

    frontera.append(("09-clips-confianza-baja",
                     "confianza baja en todos: cuatro contornos discontinuos seguidos",
                     0, dd.estado_confianza_baja(), 1024, ALTO_NOMINAL))
    frontera.append(("10-aplicar-desconectado",
                     "Resolve desconectado: el botón se apaga y se explica por qué",
                     2, dd.estado_desconectado(), 1024, ALTO_NOMINAL))
    frontera.append(("10-aplicar-desconectado-minimo",
                     "lo mismo a la anchura mínima", 2, dd.estado_desconectado(), minimo,
                     alto_minimo))
    frontera.append(("11-aplicar-lut-malo",
                     "el look no pasa el QC: se avisa antes de escribirlo, y en naranja de marca",
                     2, dd.estado_lut_malo(), 1024, ALTO_NOMINAL))

    for nombre, desc, indice, estado, ancho, alto in frontera:
        ventana = _ventana(app, estado, indice)
        if nombre == "08-comparar-sin-imagen":
            ventana.p_comparar.seleccionar("clip100")
            _asentar(app, ventana)
        fichero = destino / f"{nombre}.png"
        _disparar(app, ventana, fichero, ancho, alto)
        hechas.append(Captura(fichero.name, f"{desc} · {ancho}×{alto}"))
        ventana.close()

    # --- aplicar de verdad, con y sin averia ----------------------------
    estado_ok = dd.estado_demo()
    ventana = _ventana(app, estado_ok, 2)
    ventana.p_aplicar._aplicar_lote()
    _asentar(app, ventana)
    fichero = destino / "12-aplicar-resultado.png"
    _disparar(app, ventana, fichero, 1024, ALTO_NOMINAL)
    hechas.append(Captura(fichero.name,
                          "después de aplicar: qué se escribió y en qué versión · 1024×900"))
    ventana.close()

    estado_fallo = dd.estado_demo()
    estado_fallo.puente.fallar_en("set_lut", "no se encuentra el .cube en la carpeta de LUTs")
    ventana = _ventana(app, estado_fallo, 2)
    ventana.p_aplicar._aplicar_lote()
    _asentar(app, ventana)
    fichero = destino / "13-aplicar-averia.png"
    _disparar(app, ventana, fichero, 1024, ALTO_NOMINAL)
    hechas.append(Captura(fichero.name,
                          "avería de FakeResolve en set_lut: el lote sigue y el fallo se cuenta"
                          " · 1024×900"))
    ventana.close()

    # --- ingenieria inversa: casos frontera -----------------------------
    ventana = _ventana(app, dd.estado_demo(), 3)
    ventana.p_reverse.selector_tam.setCurrentIndex(2)  # 65^3
    ventana.p_reverse.recalcular()
    _asentar(app, ventana)
    fichero = destino / "14-reverse-cobertura-casi-nula.png"
    _disparar(app, ventana, fichero, 1024, ALTO_NOMINAL)
    hechas.append(Captura(fichero.name,
                          "rejilla de 65³ con un solo fotograma: cobertura casi nula · 1024×900"))
    ventana.close()

    par_puro = dd.par_ingenieria_inversa(con_vineta=False)
    ventana = _ventana(app, dd.estado_demo(), 3, par=par_puro)
    _asentar(app, ventana)
    fichero = destino / "15-reverse-sin-vineta.png"
    _disparar(app, ventana, fichero, 1024, ALTO_NOMINAL)
    hechas.append(Captura(fichero.name,
                          "el mismo grado sin viñeta: el diagnóstico cambia · 1024×900"))
    ventana.close()

    # --- core.reverse averiado: el sustituto TIENE que verse --------------
    # Caerse a un sustituto esta bien para poder trabajar; caerse en silencio a
    # uno que ademas diera veredictos mas flojos, no. Esta captura es la prueba
    # de que se ve, y de que la pantalla dice que no sabe si es un LUT puro en
    # vez de decidirlo ella.
    original = rp._invertir_grado_core
    disponible = rp.DISPONIBLE

    def _revienta(*a, **k):
        raise RuntimeError("avería simulada de core.reverse para la captura")

    rp._invertir_grado_core = _revienta
    rp.DISPONIBLE = True
    try:
        ventana = _ventana(app, dd.estado_demo(), 3)
        _asentar(app, ventana)
        fichero = destino / "16-reverse-sustituto.png"
        _disparar(app, ventana, fichero, 1024, ALTO_NOMINAL)
        hechas.append(Captura(
            fichero.name,
            "core.reverse averiado: se avisa de que lo ha calculado el sustituto y la "
            "pantalla NO dice si es un LUT puro · 1024×900",
        ))
        ventana.close()
    finally:
        rp._invertir_grado_core = original
        rp.DISPONIBLE = disponible

    return hechas


def main() -> int:
    hechas = generar()
    ancho = max(len(c.nombre) for c in hechas)
    print(f"{len(hechas)} capturas en {DESTINO}\n")
    for c in hechas:
        print(f"  {c.nombre.ljust(ancho)}  {c.descripcion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
