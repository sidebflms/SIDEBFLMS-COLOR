"""El informe de la primera prueba: cifras reales al lado de las sinteticas.

No escribe nada: devuelve el texto (`informe.md`) y el diccionario (`informe.json`).
`primera_real.py` los guarda a traves de la guarda.

LA REGLA DEL INFORME
--------------------
Da cifras y dice que significan. **No decide por Mario.** Donde hay un limite
escrito en `CIFRAS.md` se pone al lado; donde no lo hay, se dice que no lo hay.
Las cifras sinteticas se leen de `CIFRAS.md` en el momento (ver `cifras_ref.py`).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict
from typing import Any

from . import cifras_ref
from .localizar import Aparicion, Localizacion
from .medir import MedidaT1, MedidaT5

__all__ = ["componer"]


def _f(v: float | None, dec: int = 2) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v:.{dec}f}"


def _tc(fotograma: int, fps: float) -> str:
    """Codigo de tiempo hh:mm:ss:ff desde el principio del fichero."""
    fps_i = max(int(round(fps)), 1)
    s, ff = divmod(int(fotograma), fps_i)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{ff:02d}"


def _mediana(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and math.isfinite(x)]
    return statistics.median(v) if v else None


def _maximo(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and math.isfinite(x)]
    return max(v) if v else None


def _ref_texto(refs: list[cifras_ref.Referencia] | str) -> str:
    if isinstance(refs, str):
        return refs
    partes = []
    for r in refs:
        montaje = f" ({r.montaje})" if r.montaje else ""
        partes.append(f"{r.valor}{montaje}")
    return "<br>".join(partes)


def _limite(refs: list[cifras_ref.Referencia] | str) -> str:
    if isinstance(refs, str):
        return "no escrito en CIFRAS.md"
    lims = sorted({r.limite for r in refs if r.limite})
    return " / ".join(lims) if lims else "no escrito en CIFRAS.md"


def componer(
    *,
    fecha: str,
    argumentos: dict[str, Any],
    master: dict[str, Any],
    brutos: list[dict[str, Any]],
    ignorados: list[tuple[str, str]],
    localizacion: Localizacion,
    fps_master: float,
    medidas_t1: dict[int, MedidaT1],
    medidas_t5: list[MedidaT5],
    errores_medida: dict[int, str],
    ficheros: dict[int, dict[str, str]],
    avisos: list[str],
    tiempos: dict[str, float],
) -> tuple[str, dict[str, Any]]:
    refs = cifras_ref.referencias_para_informe()
    ap = localizacion.apariciones
    aceptadas = [(i, a) for i, a in enumerate(ap, start=1) if a.aceptada]
    medidas = [(i, a, medidas_t1[i]) for i, a in aceptadas if i in medidas_t1]

    t1_max = [m.de_max_cubierto for _, _, m in medidas]
    t1_med = [m.de_medio_cubierto for _, _, m in medidas]
    t1_max_sb = [m.de_max_cubierto_sin_bordes for _, _, m in medidas]
    cob = [m.fraccion_cubierta * 100.0 for _, _, m in medidas]
    celdas = [m.celdas_con_datos for _, _, m in medidas]
    t5_max = [m.de_max for m in medidas_t5]
    t5_med = [m.de_medio for m in medidas_t5]
    t5_max_v = [m.de_max_zona_vista for m in medidas_t5]
    t5_max_sb = [m.de_max_sin_bordes for m in medidas_t5]

    L: list[str] = []
    w = L.append
    w(f"# Primera prueba con material real — {fecha}")
    w("")
    w("Informe generado por `pruebas/primera_real.py`. **Da cifras y dice qué significan; "
      "la decisión es tuya.** Las cifras sintéticas de la columna de la derecha se han leído "
      "de `CIFRAS.md` en el momento de generar este informe.")
    w("")
    w("## 1 · Las cifras")
    w("")
    w(f"Planos localizados y medidos: **{len(medidas)}** de {len(ap)} apariciones candidatas "
      f"({len(aceptadas)} con confianza alta). Brutos leídos: {len(brutos)}.")
    w("")
    w("| Cifra | Material real | Límite (CIFRAS.md) | Referencia sintética (CIFRAS.md) |")
    w("|---|---|---|---|")
    w(f"| **T1 · ΔE2000 máximo, zona cubierta — el peor plano** | **{_f(_maximo(t1_max))}** "
      f"| {_limite(refs['t1_max'])} | {_ref_texto(refs['t1_max'])} |")
    w(f"| T1 · ΔE2000 máximo, zona cubierta — mediana de los planos | {_f(_mediana(t1_max))} "
      f"| {_limite(refs['t1_max'])} | (misma referencia) |")
    w(f"| T1 · ΔE2000 máximo, zona cubierta, **lejos de bordes** — el peor plano | "
      f"{_f(_maximo(t1_max_sb))} | — | — (no hay cifra sintética equivalente) |")
    w(f"| T1 · ΔE2000 medio, zona cubierta — mediana de los planos | {_f(_mediana(t1_med))} "
      f"| {_limite(refs['t1_medio'])} | {_ref_texto(refs['t1_medio'])} |")
    celdas_med = _mediana([float(c) for c in celdas])
    cob_texto = (
        f"**{_f(_mediana(cob))}%** ({int(celdas_med)} celdas de 35.937, mediana)"
        if celdas_med is not None else "—"
    )
    w(f"| **Cobertura del cubo por plano** | {cob_texto} · peor {_f(min(cob) if cob else None)}% "
      f"· mejor {_f(max(cob) if cob else None)}% | {_limite(refs['cobertura'])} "
      f"| {_ref_texto(refs['cobertura'])} |")
    w(f"| **T5 · ΔE2000 máximo — la peor pareja** | **{_f(_maximo(t5_max))}** "
      f"| {_limite(refs['t5_max'])} | {_ref_texto(refs['t5_max'])} |")
    w(f"| T5 · ΔE2000 máximo — mediana de las parejas | {_f(_mediana(t5_max))} "
      f"| {_limite(refs['t5_max'])} | (misma referencia) |")
    w(f"| T5 · ΔE2000 máximo **lejos de bordes** — la peor pareja | {_f(_maximo(t5_max_sb))} "
      f"| — | — |")
    w(f"| T5 · ΔE2000 máximo sólo en colores que el plano de origen vio — mediana | "
      f"{_f(_mediana(t5_max_v))} | {_limite(refs['t5_max'])} | — |")
    w(f"| T5 · ΔE2000 medio — mediana de las parejas | {_f(_mediana(t5_med))} "
      f"| {_limite(refs['t5_medio'])} | {_ref_texto(refs['t5_medio'])} |")
    w("")
    w("**Cómo leer la tabla.** ΔE2000 es la diferencia de color que ve un ojo: por debajo de "
      "1 no se distingue, de 1 a 3 se nota comparando lado a lado, por encima de 3 se ve. "
      "El **máximo** es el peor píxel de la zona medida; el **medio**, la media. Se da primero "
      "el máximo porque es el que suspende. Sobre material real el máximo sale casi siempre "
      "más alto que en sintético: un brillo quemado, el grano o un borde encajado a medio "
      "píxel bastan para subirlo, así que mira también el medio y las hojas de contacto.")
    w("")
    w("**Las filas «lejos de bordes»** quitan el 15% de píxeles con más contraste local. No "
      "sustituyen al máximo: sirven para leerlo. En un borde, un píxel es mezcla de dos "
      "colores, y el máster se hizo reescalando el bruto con un filtro que no conocemos; un "
      "grado no lineal no da el mismo color si se aplica antes o después de reescalar. "
      "Medido en sintético: aplicando **el grado verdadero** al bruto ya encajado, el máximo "
      "contra el máster sale alto sólo por eso. Así que: **si el máximo es alto y el de lejos "
      "de bordes es bajo, el problema son los bordes, no el grado. Si los dos son altos, el "
      "grado no cabe.**")
    w("")
    w("- **T1** es el techo: el grado sacado de un plano, aplicado a ese mismo plano. Si T1 "
      "sale mal en un plano, en ese plano hay algo que un CDL + LUT no reproduce (una ventana, "
      "una viñeta, una secundaria) o el encuadre no quedó bien encajado.")
    w("- **T5** es lo que importa: el grado de un plano aplicado a otro. **Si T1 sale bien y T5 "
      "sale mal**, el grado no es el mismo en todos los planos (se coloreó plano a plano) o "
      "el plano de origen no vio los colores del de destino y el cubo se los inventó. Para "
      "separar las dos cosas compara la fila «sólo en colores que el plano de origen vio» "
      "con la de todos los píxeles: si en los colores vistos sale bien y en el total mal, es "
      "cobertura; si sale mal en los dos, es que el grado cambia de plano a plano.")
    w("- **Cobertura**: qué parte del cubo tiene datos reales. El resto lo rellena el "
      "programa. Un plano solo cubre muy poco; es normal y es lo que hay que tener presente "
      "al entregar un `.cube`.")
    w("")

    # --- avisos -----------------------------------------------------------
    if avisos:
        w("## 2 · Avisos")
        w("")
        for a in avisos:
            w(f"- {a}")
        w("")

    # --- localizacion -----------------------------------------------------
    w("## 3 · Dónde está cada bruto dentro del máster")
    w("")
    w("La localización busca por **forma**, no por color (el color es justo lo que cambia). "
      "La confianza es la peor de tres notas: encaje de la forma, diferencia con el mejor "
      "candidato de otro bruto, y duración. **Sólo se miden las de confianza alta.** Las "
      "constantes de la confianza no están calibradas con material real: esta prueba es la "
      "primera vez.")
    w("")
    w("| # | Bruto | Máster (desde – hasta) | Fotograma del bruto medido | Recorte | Encaje | "
      "Confianza | ¿Se mide? |")
    w("|---|---|---|---|---|---|---|---|")
    for i, a in enumerate(ap, start=1):
        g = a.geometria
        recorte = f"{g.escala * 100:.0f}% del ancho, esquina ({g.x:.2f}, {g.y:.2f})"
        medida = "sí" if a.aceptada else "**no**"
        if a.aceptada and i in errores_medida:
            medida = "falló al medir"
        w(f"| {i} | {a.bruto} | {_tc(a.master_desde, fps_master)} – "
          f"{_tc(a.master_hasta, fps_master)} ({a.n} fot.) | {a.bruto_medida} | {recorte} | "
          f"{_f(min([g.ncc, *[v for _, v in a.verificaciones]]), 3)} | {a.nivel} "
          f"({_f(a.confianza)}) | {medida} |")
    w("")
    rechazadas = [(i, a) for i, a in enumerate(ap, start=1) if not a.aceptada]
    if rechazadas:
        w("### Descartadas, y por qué")
        w("")
        for i, a in rechazadas:
            w(f"- **#{i} ({a.bruto}, {_tc(a.master_desde, fps_master)})**: "
              + ("; ".join(a.razones) if a.razones else "confianza por debajo de alta") + ".")
        w("")
    w("### Brutos que no aparecen en el máster")
    w("")
    if localizacion.no_encontrados:
        for n in localizacion.no_encontrados:
            w(f"- {n}")
    else:
        w("- Ninguno: todos los brutos leídos se han encontrado con confianza alta.")
    w("")
    if localizacion.tramos_sin_bruto:
        w("### Tramos del máster sin bruto")
        w("")
        for desde, hasta, motivo in localizacion.tramos_sin_bruto:
            w(f"- {_tc(desde, fps_master)} – {_tc(hasta, fps_master)} ({hasta - desde} fot.): "
              f"{motivo}")
        w("")
    if ignorados:
        w("### Ficheros que no se han podido leer")
        w("")
        for ruta, motivo in ignorados:
            w(f"- `{ruta}`: {motivo}")
        w("")

    # --- T1 por plano -----------------------------------------------------
    w("## 4 · T1 plano a plano")
    w("")
    if medidas:
        w("| # | Bruto | **ΔE2000 máx.** (zona cubierta) | máx. lejos de bordes | p95 | medio | "
          "**Cobertura** | Cabe en un LUT | Confianza del grado |")
        w("|---|---|---|---|---|---|---|---|---|")
        for i, a, m in medidas:
            w(f"| {i} | {a.bruto} | **{_f(m.de_max_cubierto)}** | "
              f"{_f(m.de_max_cubierto_sin_bordes)} | {_f(m.de_p95_cubierto)} | "
              f"{_f(m.de_medio_cubierto)} | **{m.fraccion_cubierta * 100:.2f}%** "
              f"({m.celdas_con_datos} celdas) | {m.lut_reproducible * 100:.0f}% | "
              f"{m.nivel_grado} ({_f(m.confianza_grado)}) |")
        w("")
    else:
        w("No se ha medido ningún plano.")
        w("")
    for i, err in errores_medida.items():
        w(f"- #{i}: no se pudo medir: {err}")
    if errores_medida:
        w("")

    # --- T5 ---------------------------------------------------------------
    w("## 5 · T5: el grado de un plano aplicado a los demás")
    w("")
    if medidas_t5:
        nombres = {i: f"#{i} {a.bruto}" for i, a, _ in medidas}
        por_origen: dict[str, list[MedidaT5]] = {}
        for m in medidas_t5:
            por_origen.setdefault(m.origen, []).append(m)
        w("Resumen por plano de origen (el grado sale de este plano y se aplica a todos los "
          "demás):")
        w("")
        w("| Origen | **ΔE2000 máx., peor destino** | máx., mediana | medio, mediana | "
          "máx. en colores vistos, mediana |")
        w("|---|---|---|---|---|")
        for origen, ms in por_origen.items():
            w(f"| {origen} | **{_f(_maximo([x.de_max for x in ms]))}** | "
              f"{_f(_mediana([x.de_max for x in ms]))} | {_f(_mediana([x.de_medio for x in ms]))} | "
              f"{_f(_mediana([x.de_max_zona_vista for x in ms]))} |")
        w("")
        if len(nombres) <= 12:
            w("Matriz completa, ΔE2000 máximo (fila = origen del grado, columna = destino):")
            w("")
            cols = list(nombres.values())
            w("| origen \\ destino | " + " | ".join(cols) + " |")
            w("|---|" + "---|" * len(cols))
            idx = {(m.origen, m.destino): m for m in medidas_t5}
            for o in cols:
                fila = [
                    "—" if o == d else _f(idx[(o, d)].de_max) if (o, d) in idx else "·"
                    for d in cols
                ]
                w(f"| {o} | " + " | ".join(fila) + " |")
            w("")
        else:
            w("Hay más de 12 planos: la matriz completa está en `informe.json`.")
            w("")
    else:
        w("No hay T5: hacen falta al menos dos planos medidos.")
        w("")

    # --- ficheros y parametros -------------------------------------------
    w("## 6 · Qué se ha guardado")
    w("")
    w("Todo dentro de esta carpeta. Ni un byte en los discos de origen.")
    w("")
    for i, fs in ficheros.items():
        w(f"- #{i}: " + ", ".join(f"`{v}`" for v in fs.values()))
    w("")
    w("## 7 · Cómo se hizo")
    w("")
    w(f"- Máster: `{master.get('ruta')}` · {master.get('ancho')}×{master.get('alto')} · "
      f"{_f(master.get('fps'), 3)} fps · {master.get('codec')} · espacio usado "
      f"`{master.get('espacio')}`")
    for b in brutos:
        w(f"- Bruto `{b.get('nombre')}`: {b.get('ancho')}×{b.get('alto')} · "
          f"{_f(b.get('fps'), 3)} fps · {b.get('codec')} · espacio usado `{b.get('espacio')}`")
    w(f"- Parámetros de localización: `{localizacion.parametros}`")
    w(f"- Argumentos: `{argumentos}`")
    w("- Tiempos: " + ", ".join(f"{k} {v:.1f} s" for k, v in tiempos.items()))
    w("")
    w("## 8 · Lo que esta prueba NO dice")
    w("")
    w("- No dice si el grado es bueno: dice si se puede **reproducir**.")
    w("- No se ha escrito nada en DaVinci Resolve ni se ha conectado con él.")
    w("- Las constantes de la localización y los umbrales de confianza (`CONFIDENCE_ALTA`, "
      "`CONFIDENCE_MEDIA`) no están medidos sobre material real. Si todo sale descartado con "
      "encajes altos (0.8 o más), es probable que los umbrales sean demasiado estrictos para "
      "material real, no que no esté el plano.")
    w("")

    datos: dict[str, Any] = {
        "fecha": fecha,
        "argumentos": argumentos,
        "master": master,
        "brutos": brutos,
        "ignorados": [{"ruta": r, "motivo": m} for r, m in ignorados],
        "localizacion": {
            "parametros": localizacion.parametros,
            "no_encontrados": localizacion.no_encontrados,
            "tramos_sin_bruto": [
                {"desde": d, "hasta": h, "motivo": m} for d, h, m in localizacion.tramos_sin_bruto
            ],
            "apariciones": [_aparicion_json(i, a, fps_master) for i, a in enumerate(ap, start=1)],
        },
        "t1": {str(i): asdict(m) for i, m in medidas_t1.items()},
        "t5": [asdict(m) for m in medidas_t5],
        "errores_medida": {str(k): v for k, v in errores_medida.items()},
        "resumen": {
            "t1_de_max_cubierto_peor": _maximo(t1_max),
            "t1_de_max_cubierto_mediana": _mediana(t1_max),
            "t1_de_medio_cubierto_mediana": _mediana(t1_med),
            "t1_de_max_cubierto_sin_bordes_peor": _maximo(t1_max_sb),
            "t5_de_max_sin_bordes_peor": _maximo(t5_max_sb),
            "cobertura_pct_mediana": _mediana(cob),
            "t5_de_max_peor": _maximo(t5_max),
            "t5_de_max_mediana": _mediana(t5_max),
            "t5_de_medio_mediana": _mediana(t5_med),
            "t5_de_max_zona_vista_mediana": _mediana(t5_max_v),
        },
        "referencias_cifras_md": {
            k: (v if isinstance(v, str) else [asdict(r) for r in v]) for k, v in refs.items()
        },
        "ficheros": {str(k): v for k, v in ficheros.items()},
        "avisos": avisos,
        "tiempos_s": tiempos,
    }
    return "\n".join(L) + "\n", datos


def _aparicion_json(i: int, a: Aparicion, fps: float) -> dict[str, Any]:
    d = asdict(a)
    d["numero"] = i
    d["tc_desde"] = _tc(a.master_desde, fps)
    d["tc_hasta"] = _tc(a.master_hasta, fps)
    return d
