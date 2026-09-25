"""`core.batch.ejecutar_lote`: por trozos, reanudable, cancelable, con fallo
por ítem aislado — la pieza de arquitectura que `BITACORA.md` señalaba como
hueco ("no existe ningún orquestador... con estado reanudable"; "no hay
forma de cancelar aplicar() a mitad").
"""

from __future__ import annotations

import json

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
