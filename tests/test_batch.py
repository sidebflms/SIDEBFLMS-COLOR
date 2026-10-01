"""`core.batch.ejecutar_lote`: por trozos, reanudable, cancelable, con fallo
por ítem aislado — la pieza de arquitectura que `BITACORA.md` señalaba como
hueco ("no existe ningún orquestador... con estado reanudable"; "no hay
forma de cancelar aplicar() a mitad").
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from core.batch import ProgresoLote, ejecutar_lote


class _ErrorDeDominio(RuntimeError):
    """El tipo de fallo "esperable" en estos tests, análogo a ResolveError/ErrorAnalisis."""


class _ErrorDeVerdad(RuntimeError):
    """Un bug del programa: NO está en `excepciones`, tiene que propagarse."""


def test_todos_bien_sin_manifiesto_ni_callbacks():
    vistos = []
    resultado = ejecutar_lote(
        ["a", "b", "c"], vistos.append, excepciones=(_ErrorDeDominio,)
    )
    assert vistos == ["a", "b", "c"]
    assert resultado.hechos == ("a", "b", "c")
    assert resultado.fallidos == ()
    assert resultado.cancelado is False


def test_un_fallo_no_tumba_el_lote_y_se_aisla():
    def funcion(item_id: str) -> None:
        if item_id == "b":
            raise _ErrorDeDominio("disco lleno")

    resultado = ejecutar_lote(["a", "b", "c"], funcion, excepciones=(_ErrorDeDominio,))

    assert resultado.hechos == ("a", "c")
    assert resultado.fallidos == ("b",)
    assert resultado.resultados["b"].mensaje == "disco lleno"


def test_una_excepcion_fuera_de_la_lista_se_propaga_y_para_todo():
    """Un bug de programa no se disfraza de fallo esperable -- se ve."""

    def funcion(item_id: str) -> None:
        if item_id == "b":
            raise _ErrorDeVerdad("esto es un bug, no un fallo de item")

    with pytest.raises(_ErrorDeVerdad):
        ejecutar_lote(["a", "b", "c"], funcion, excepciones=(_ErrorDeDominio,))


def test_el_orden_se_respeta():
    vistos = []
    ejecutar_lote(["z", "a", "m"], vistos.append, excepciones=(_ErrorDeDominio,))
    assert vistos == ["z", "a", "m"]


# ---------------------------------------------------------------------------
# Cancelación
# ---------------------------------------------------------------------------


def test_cancelar_para_antes_del_siguiente_item_no_a_mitad():
    vistos = []

    def funcion(item_id: str) -> None:
        vistos.append(item_id)

    def debe_cancelar() -> bool:
        return len(vistos) >= 2  # cancela justo despues de haber hecho 2

    resultado = ejecutar_lote(
        ["a", "b", "c", "d"], funcion, excepciones=(_ErrorDeDominio,), debe_cancelar=debe_cancelar
    )

    assert vistos == ["a", "b"]  # nunca llego a intentar "c" ni "d"
    assert resultado.cancelado is True
    assert resultado.hechos == ("a", "b")
    assert "c" not in resultado.resultados
    assert "d" not in resultado.resultados


def test_reanudar_tras_cancelar_continua_donde_lo_dejo(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    vistos_1 = []

    def funcion_1(item_id: str) -> None:
        vistos_1.append(item_id)

    r1 = ejecutar_lote(
        ["a", "b", "c"],
        funcion_1,
        excepciones=(_ErrorDeDominio,),
        manifiesto=ruta,
        debe_cancelar=lambda: len(vistos_1) >= 1,
    )
    assert r1.cancelado is True
    assert vistos_1 == ["a"]

    vistos_2 = []

    def funcion_2(item_id: str) -> None:
        vistos_2.append(item_id)

    r2 = ejecutar_lote(["a", "b", "c"], funcion_2, excepciones=(_ErrorDeDominio,), manifiesto=ruta)

    assert vistos_2 == ["b", "c"]  # "a" no se repite: ya estaba en el manifiesto
    assert r2.cancelado is False
    assert r2.hechos == ("a", "b", "c")


# ---------------------------------------------------------------------------
# Manifiesto / reanudación
# ---------------------------------------------------------------------------


def test_sin_manifiesto_no_hay_nada_que_reanudar(tmp_path):
    """Sin `manifiesto`, cada llamada empieza de cero -- es el comportamiento
    de siempre (aplicar() de hoy), no una regresion."""
    vistos = []
    ejecutar_lote(["a", "b"], vistos.append, excepciones=(_ErrorDeDominio,))
    ejecutar_lote(["a", "b"], vistos.append, excepciones=(_ErrorDeDominio,))
    assert vistos == ["a", "b", "a", "b"]


def test_los_hechos_no_se_repiten_al_reanudar(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    vistos = []
    ejecutar_lote(["a", "b", "c"], vistos.append, excepciones=(_ErrorDeDominio,), manifiesto=ruta)
    vistos.clear()
    resultado = ejecutar_lote(
        ["a", "b", "c"], vistos.append, excepciones=(_ErrorDeDominio,), manifiesto=ruta
    )
    assert vistos == []  # los tres ya estaban "hecho": ni uno se vuelve a llamar
    assert resultado.hechos == ("a", "b", "c")


def test_los_fallidos_se_reintentan_por_defecto_al_reanudar(tmp_path):
    ruta = tmp_path / "manifiesto.json"

    def falla_b(item_id: str) -> None:
        if item_id == "b":
            raise _ErrorDeDominio("fallo transitorio")

    ejecutar_lote(["a", "b", "c"], falla_b, excepciones=(_ErrorDeDominio,), manifiesto=ruta)

    vistos = []
    resultado = ejecutar_lote(
        ["a", "b", "c"], vistos.append, excepciones=(_ErrorDeDominio,), manifiesto=ruta
    )
    assert vistos == ["b"]  # solo se reintenta el que fallo
    assert set(resultado.hechos) == {"a", "b", "c"}
    assert resultado.fallidos == ()


def test_reintentar_fallidos_false_no_los_vuelve_a_intentar(tmp_path):
    ruta = tmp_path / "manifiesto.json"

    def falla_b(item_id: str) -> None:
        if item_id == "b":
            raise _ErrorDeDominio("fallo de verdad")

    ejecutar_lote(["a", "b", "c"], falla_b, excepciones=(_ErrorDeDominio,), manifiesto=ruta)

    vistos = []
    resultado = ejecutar_lote(
        ["a", "b", "c"],
        vistos.append,
        excepciones=(_ErrorDeDominio,),
        manifiesto=ruta,
        reintentar_fallidos=False,
    )
    assert vistos == []
    assert resultado.fallidos == ("b",)
    assert resultado.resultados["b"].mensaje == "fallo de verdad"


def test_el_manifiesto_se_escribe_de_forma_incremental(tmp_path):
    """Simula un 'crash' a mitad: si el proceso muriera justo despues del
    segundo item, el fichero en disco ya tiene que reflejar los dos
    primeros, no solo el estado final."""
    ruta = tmp_path / "manifiesto.json"
    vistos_en_disco_tras_b = None

    def funcion(item_id: str) -> None:
        nonlocal vistos_en_disco_tras_b
        if item_id == "b" and ruta.is_file():
            vistos_en_disco_tras_b = json.loads(ruta.read_text(encoding="utf-8"))

    ejecutar_lote(["a", "b", "c"], funcion, excepciones=(_ErrorDeDominio,), manifiesto=ruta)

    # Cuando se procesaba "b", el disco ya tenia "a" escrito (de la vuelta anterior).
    assert vistos_en_disco_tras_b == {"a": {"estado": "hecho", "mensaje": ""}}

    final = json.loads(ruta.read_text(encoding="utf-8"))
    assert final.keys() == {"a", "b", "c"}


def test_manifiesto_corrupto_no_rompe_nada_empieza_de_cero(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    ruta.write_text("esto no es json valido {{{", encoding="utf-8")

    vistos = []
    resultado = ejecutar_lote(
        ["a", "b"], vistos.append, excepciones=(_ErrorDeDominio,), manifiesto=ruta
    )
    assert vistos == ["a", "b"]
    assert resultado.hechos == ("a", "b")


def test_manifiesto_con_json_valido_pero_forma_inesperada_se_ignora(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    ruta.write_text(json.dumps({"a": "no es un dict"}), encoding="utf-8")

    vistos = []
    ejecutar_lote(["a"], vistos.append, excepciones=(_ErrorDeDominio,), manifiesto=ruta)
    assert vistos == ["a"]  # no se confundio y lo trato como "ya hecho"


def test_manifiesto_que_no_se_puede_escribir_no_rompe_el_lote(tmp_path, monkeypatch):
    """La cache/el manifiesto es una optimizacion; si falla al escribir, el
    lote se completa igual (mismo criterio que core.io.biblioteca.sembrar_desde_carpeta)."""
    from pathlib import Path

    ruta = tmp_path / "no-existe" / "manifiesto.json"  # carpeta padre inexistente

    original_write_text = Path.write_text

    def _write_text_que_falla(self, *a, **k):
        if self == ruta:
            raise OSError("disco lleno, a proposito")
        return original_write_text(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", _write_text_que_falla)

    vistos = []
    resultado = ejecutar_lote(
        ["a", "b"], vistos.append, excepciones=(_ErrorDeDominio,), manifiesto=ruta
    )
    assert vistos == ["a", "b"]
    assert resultado.hechos == ("a", "b")


# ---------------------------------------------------------------------------
# callback_progreso
# ---------------------------------------------------------------------------


def test_callback_progreso_se_llama_una_vez_por_item_en_orden():
    progresos: list[ProgresoLote] = []
    ejecutar_lote(
        ["a", "b", "c"],
        lambda _i: None,
        excepciones=(_ErrorDeDominio,),
        callback_progreso=progresos.append,
    )
    assert [p.indice for p in progresos] == [1, 2, 3]
    assert all(p.total == 3 for p in progresos)
    assert [p.resultado.item_id for p in progresos] == ["a", "b", "c"]
    assert all(not p.reanudado for p in progresos)


def test_callback_progreso_marca_reanudado_para_los_que_vienen_del_manifiesto(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    ejecutar_lote(["a", "b"], lambda _i: None, excepciones=(_ErrorDeDominio,), manifiesto=ruta)

    progresos: list[ProgresoLote] = []
    ejecutar_lote(
        ["a", "b", "c"],
        lambda _i: None,
        excepciones=(_ErrorDeDominio,),
        manifiesto=ruta,
        callback_progreso=progresos.append,
    )
    reanudados = {p.resultado.item_id: p.reanudado for p in progresos}
    assert reanudados == {"a": True, "b": True, "c": False}
    # El indice sigue siendo la POSICION en la lista, no cuantos se ejecutaron.
    assert [p.indice for p in progresos] == [1, 2, 3]


def test_callback_progreso_puede_cancelar_desde_fuera():
    """El patron real de la GUI: un boton 'Cancelar' pone una bandera que
    debe_cancelar lee en la siguiente vuelta -- probado end-to-end aqui con
    una bandera de verdad, sin nada de Qt de por medio."""
    cancelar = {"pedido": False}
    vistos = []

    def funcion(item_id: str) -> None:
        vistos.append(item_id)
        if item_id == "b":
            cancelar["pedido"] = True  # el "click" ocurre dentro del callback en la GUI real

    resultado = ejecutar_lote(
        ["a", "b", "c", "d"],
        funcion,
        excepciones=(_ErrorDeDominio,),
        debe_cancelar=lambda: cancelar["pedido"],
    )
    assert vistos == ["a", "b"]
    assert resultado.cancelado is True


# ---------------------------------------------------------------------------
# concurrencia (issue #3): paralelo solo si se pide, y solo con concurrencia>1
# ---------------------------------------------------------------------------


def test_concurrencia_1_es_el_mismo_camino_de_siempre():
    """`concurrencia=1` (el defecto) no es "paralelo con un solo hilo": es
    literalmente el bucle de toda la vida. Lo unico que se puede comprobar
    desde fuera es que el comportamiento es identico -- ya lo hacen todos los
    tests de mas arriba, que no pasan `concurrencia` y siguen en verde."""
    vistos = []
    resultado = ejecutar_lote(
        ["a", "b", "c"], vistos.append, excepciones=(_ErrorDeDominio,), concurrencia=1
    )
    assert vistos == ["a", "b", "c"]
    assert resultado.hechos == ("a", "b", "c")


@pytest.mark.parametrize("concurrencia", [0, -1, 1.5, True, "4"])
def test_concurrencia_invalida_lanza_valueerror(concurrencia):
    with pytest.raises(ValueError):
        ejecutar_lote(["a"], lambda _i: None, excepciones=(_ErrorDeDominio,), concurrencia=concurrencia)


def test_concurrencia_mayor_que_uno_llama_a_todos_aunque_el_orden_no_este_garantizado():
    lock = threading.Lock()
    vistos: list[str] = []

    def funcion(item_id: str) -> None:
        with lock:
            vistos.append(item_id)

    resultado = ejecutar_lote(
        [f"c{i}" for i in range(12)], funcion, excepciones=(_ErrorDeDominio,), concurrencia=4
    )
    assert sorted(vistos) == sorted(f"c{i}" for i in range(12))
    assert set(resultado.hechos) == {f"c{i}" for i in range(12)}
    assert resultado.cancelado is False


def test_concurrencia_de_verdad_corre_en_paralelo_no_solo_lo_dice():
    """La prueba de que son hilos de verdad, no una simulacion: 8 items que
    tardan 150ms cada uno, con concurrencia=8, tienen que tardar del orden de
    150ms en total, no de 8*150ms=1.2s. Margen generoso (600ms) para no ser
    fragil en una maquina de CI ocupada."""

    def funcion(_item_id: str) -> None:
        time.sleep(0.15)

    inicio = time.monotonic()
    ejecutar_lote(
        [f"c{i}" for i in range(8)], funcion, excepciones=(_ErrorDeDominio,), concurrencia=8
    )
    duracion = time.monotonic() - inicio
    assert duracion < 0.6, f"tardo {duracion:.2f}s; con concurrencia=8 no deberia acercarse a 1.2s"


def test_concurrencia_aisla_fallos_igual_que_secuencial():
    def funcion(item_id: str) -> None:
        if item_id in ("b", "d"):
            raise _ErrorDeDominio(f"fallo de {item_id}")

    resultado = ejecutar_lote(
        ["a", "b", "c", "d", "e"], funcion, excepciones=(_ErrorDeDominio,), concurrencia=3
    )
    assert set(resultado.hechos) == {"a", "c", "e"}
    assert set(resultado.fallidos) == {"b", "d"}
    assert resultado.resultados["b"].mensaje == "fallo de b"


def test_concurrencia_propaga_excepcion_fuera_de_la_lista_igual_que_secuencial():
    def funcion(item_id: str) -> None:
        if item_id == "b":
            raise _ErrorDeVerdad("bug de verdad, no fallo de item")

    with pytest.raises(_ErrorDeVerdad):
        ejecutar_lote(["a", "b", "c", "d"], funcion, excepciones=(_ErrorDeDominio,), concurrencia=2)


def test_concurrencia_callback_y_manifiesto_se_llaman_desde_el_hilo_llamante(tmp_path):
    """Importa de verdad para quien llame desde la GUI con el patron de
    `app.processEvents()`: si `callback_progreso` llegara desde un hilo
    trabajador, Qt no lo tolera. Los trabajadores SOLO ejecutan `funcion`."""
    hilo_llamante = threading.current_thread()
    hilos_de_funcion: set[int] = set()
    hilos_de_callback: set[int] = set()
    lock = threading.Lock()

    def funcion(_item_id: str) -> None:
        with lock:
            hilos_de_funcion.add(threading.get_ident())
        time.sleep(0.02)  # dar tiempo a que varios hilos se solapen de verdad

    def callback(_progreso: ProgresoLote) -> None:
        hilos_de_callback.add(threading.get_ident())

    ejecutar_lote(
        [f"c{i}" for i in range(8)],
        funcion,
        excepciones=(_ErrorDeDominio,),
        concurrencia=4,
        callback_progreso=callback,
        manifiesto=tmp_path / "manifiesto.json",
    )

    assert hilos_de_callback == {hilo_llamante.ident}, (
        "callback_progreso se ha llamado desde un hilo que no es el llamante"
    )
    # Y la prueba de que SI hubo paralelismo real: mas de un hilo trabajador.
    assert len(hilos_de_funcion) > 1


def test_concurrencia_cancela_entre_trozos_no_a_mitad_de_uno():
    """Semantica distinta de concurrencia=1 a proposito (ver docstring del
    modulo): el trozo ya lanzado se termina ENTERO -- puede haber hasta
    `concurrencia - 1` items de mas de los que habria cancelando item a item,
    pero nunca un item a medias."""
    lock = threading.Lock()
    vistos: list[str] = []

    def funcion(item_id: str) -> None:
        with lock:
            vistos.append(item_id)

    def debe_cancelar() -> bool:
        with lock:
            return len(vistos) >= 1  # pide cancelar tras el primer item visto

    resultado = ejecutar_lote(
        [f"c{i}" for i in range(6)],
        funcion,
        excepciones=(_ErrorDeDominio,),
        concurrencia=3,
        debe_cancelar=debe_cancelar,
    )
    # El PRIMER trozo (3 items) se lanzo entero antes de que hubiera ocasion
    # de comprobar debe_cancelar() por segunda vez: los 3 se completan.
    assert len(vistos) == 3
    assert resultado.cancelado is True
    assert len(resultado.resultados) == 3
    # Los del segundo trozo no se intentaron ni a medias.
    assert set(resultado.resultados) == set(vistos)


def test_concurrencia_manifiesto_incremental_con_varios_trozos(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    ejecutar_lote(
        [f"c{i}" for i in range(10)],
        lambda _i: None,
        excepciones=(_ErrorDeDominio,),
        concurrencia=3,
        manifiesto=ruta,
    )
    final = json.loads(ruta.read_text(encoding="utf-8"))
    assert final.keys() == {f"c{i}" for i in range(10)}
    assert all(v["estado"] == "hecho" for v in final.values())


def test_concurrencia_reanudar_tras_cancelar_continua_donde_lo_dejo(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    lock = threading.Lock()
    vistos_1: list[str] = []

    def funcion_1(item_id: str) -> None:
        with lock:
            vistos_1.append(item_id)

    r1 = ejecutar_lote(
        [f"c{i}" for i in range(6)],
        funcion_1,
        excepciones=(_ErrorDeDominio,),
        concurrencia=3,
        manifiesto=ruta,
        debe_cancelar=lambda: len(vistos_1) >= 1,
    )
    assert r1.cancelado is True
    assert len(vistos_1) == 3  # el primer trozo entero

    vistos_2: list[str] = []
    r2 = ejecutar_lote(
        [f"c{i}" for i in range(6)],
        vistos_2.append,
        excepciones=(_ErrorDeDominio,),
        concurrencia=3,
        manifiesto=ruta,
    )
    # Los 3 del primer trozo no se repiten; solo los 3 que faltaban.
    assert set(vistos_2) == set(f"c{i}" for i in range(6)) - set(vistos_1)
    assert r2.cancelado is False
    assert set(r2.hechos) == {f"c{i}" for i in range(6)}
