"""ASC CDL en XML: `.cc`, `.ccc`, `.cdl`.

Un `.cdl` es un fichero que viene de fuera (de producción, de otra casa de
post), así que la mitad de este archivo son ficheros hostiles.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from core.contracts import CDL
from core.io import (
    ErrorFormatoCDL,
    cdl_a_xml,
    escribir_cdl,
    escribir_cdls,
    leer_cdl,
    leer_cdls,
)

es_root = os.geteuid() == 0

CDL_TIPICO = CDL(
    slope=(1.1, 0.9, 1.0),
    offset=(0.01, -0.02, 0.0),
    power=(0.95, 1.05, 1.0),
    saturation=1.2,
)


def _escribe(tmp_path, nombre, texto):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Ida y vuelta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".cc", ".ccc", ".cdl"])
def test_ida_y_vuelta_exacta(tmp_path, ext):
    ruta = escribir_cdl(CDL_TIPICO, tmp_path / f"g{ext}", cc_id="SIDEB001")
    vuelto = leer_cdl(ruta)
    assert vuelto == CDL_TIPICO
    assert leer_cdls(ruta)[0][0] == "SIDEB001"


def test_ida_y_vuelta_exacta_con_numeros_feos(tmp_path):
    """6 decimales valen para casi todo, pero un número que no cabe en 6
    decimales tiene que volver EXACTO igualmente (se cae a `repr`)."""
    feo = CDL(
        slope=(1.2345678901234, 0.1, 1.0),
        offset=(1e-9, 0.0, 0.0),
        power=(0.3333333333333333, 1.0, 1.0),
        saturation=0.9876543210987654,
    )
    vuelto = leer_cdl(escribir_cdl(feo, tmp_path / "feo.cc"))
    assert vuelto == feo
    assert vuelto.slope[0] == feo.slope[0]  # float por float, sin approx


def test_los_numeros_normales_salen_bonitos(tmp_path):
    ruta = escribir_cdl(CDL.identity(), tmp_path / "id.cc")
    texto = ruta.read_text()
    assert "<Slope>1.000000 1.000000 1.000000</Slope>" in texto
    assert "<Saturation>1.000000</Saturation>" in texto


def test_el_fichero_es_xml_limpio(tmp_path):
    ruta = escribir_cdl(CDL_TIPICO, tmp_path / "g.cdl")
    crudo = ruta.read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "sin BOM"
    assert b"\r" not in crudo, "saltos Unix"
    assert crudo.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n')
    texto = crudo.decode("utf-8")
    assert "<ColorDecisionList>" in texto and "<ColorDecision>" in texto


def test_una_coleccion_con_varios(tmp_path):
    items = [("A", CDL_TIPICO), ("B", CDL.identity()), (None, CDL(saturation=0.0))]
    ruta = escribir_cdls(items, tmp_path / "varios.ccc")
    vueltos = leer_cdls(ruta)
    assert [i for i, _ in vueltos] == ["A", "B", None]
    assert [c for _, c in vueltos] == [c for _, c in items]
    # leer_cdl coge el primero
    assert leer_cdl(ruta) == CDL_TIPICO


def test_el_cdl_leido_hace_lo_mismo_que_el_original(tmp_path):
    """La prueba que de verdad importa: que aplicado a píxeles dé lo mismo."""
    pixeles = np.array([[0.18, 0.18, 0.18], [0.9, 0.4, 0.1], [0.0, 0.0, 0.0]])
    vuelto = leer_cdl(escribir_cdl(CDL_TIPICO, tmp_path / "x.cc"))
    assert np.array_equal(vuelto.apply(pixeles), CDL_TIPICO.apply(pixeles))


def test_cdl_a_xml_no_toca_el_disco():
    assert "<ColorCorrectionCollection>" in cdl_a_xml(CDL_TIPICO, envoltorio=".ccc")


# ---------------------------------------------------------------------------
# Ficheros de otras herramientas
# ---------------------------------------------------------------------------


CON_NAMESPACE = """<?xml version="1.0" encoding="UTF-8"?>
<ColorCorrectionCollection xmlns="urn:ASC:CDL:v1.2">
  <ColorCorrection id="de_otra_casa">
    <SOPNode>
      <Description>lo que sea</Description>
      <Slope>1.5 1.0 0.5</Slope>
      <Offset>0.0 0.0 0.0</Offset>
      <Power>1.0 1.0 1.0</Power>
    </SOPNode>
    <SatNode><Saturation>0.8</Saturation></SatNode>
  </ColorCorrection>
</ColorCorrectionCollection>
"""


def test_lee_un_ccc_con_espacio_de_nombres(tmp_path):
    cc_id, cdl = leer_cdls(_escribe(tmp_path, "ns.ccc", CON_NAMESPACE))[0]
    assert cc_id == "de_otra_casa"
    assert cdl.slope == (1.5, 1.0, 0.5)
    assert cdl.saturation == 0.8


def test_sin_satnode_la_saturacion_es_1(tmp_path):
    texto = """<ColorCorrection><SOPNode>
        <Slope>2 2 2</Slope><Offset>0 0 0</Offset><Power>1 1 1</Power>
    </SOPNode></ColorCorrection>"""
    assert leer_cdl(_escribe(tmp_path, "sinsat.cc", texto)).saturation == 1.0


def test_solo_satnode_el_sop_es_neutro(tmp_path):
    texto = "<ColorCorrection><SatNode><Saturation>0.5</Saturation></SatNode></ColorCorrection>"
    cdl = leer_cdl(_escribe(tmp_path, "solosat.cc", texto))
    assert cdl.slope == (1.0, 1.0, 1.0) and cdl.saturation == 0.5


def test_numeros_separados_por_comas(tmp_path):
    texto = """<ColorCorrection><SOPNode>
        <Slope>1.0, 2.0, 3.0</Slope><Offset>0 0 0</Offset><Power>1 1 1</Power>
    </SOPNode></ColorCorrection>"""
    assert leer_cdl(_escribe(tmp_path, "comas.cc", texto)).slope == (1.0, 2.0, 3.0)


# ---------------------------------------------------------------------------
# Ficheros hostiles
# ---------------------------------------------------------------------------


def test_power_cero_da_un_error_legible_no_una_excepcion_cruda(tmp_path):
    """`CDL` rechaza power <= 0 en el constructor a propósito. Leer un fichero
    con Power 0 tiene que salir como `ErrorFormatoCDL` con una frase que se
    pueda enseñar, no como el ValueError pelado de la dataclase."""
    texto = """<ColorCorrection><SOPNode>
        <Slope>1 1 1</Slope><Offset>0 0 0</Offset><Power>0 1 1</Power>
    </SOPNode></ColorCorrection>"""
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "p0.cc", texto))
    msg = str(e.value)
    assert "power" in msg.lower()
    assert "p0.cc" in msg
    assert "no es un grado" in msg


def test_power_negativo_tambien(tmp_path):
    texto = """<ColorCorrection><SOPNode>
        <Slope>1 1 1</Slope><Offset>0 0 0</Offset><Power>1 -2 1</Power>
    </SOPNode></ColorCorrection>"""
    with pytest.raises(ErrorFormatoCDL):
        leer_cdl(_escribe(tmp_path, "pneg.cc", texto))


def test_la_bomba_de_entidades_ni_se_intenta_parsear(tmp_path):
    """'Billion laughs'. Sin DTD no hay expansión, y aquí el DTD se rechaza de
    entrada: el fichero ni llega al parser."""
    bomba = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<ColorCorrection><SOPNode><Slope>&lol2; 1 1</Slope></SOPNode></ColorCorrection>
"""
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "bomba.cc", bomba))
    msg = str(e.value)
    assert "DOCTYPE" in msg and "No lo abro" in msg


def test_entidad_externa_rechazada(tmp_path):
    """XXE: leer /etc/passwd desde el XML. Mismo cortafuegos."""
    xxe = """<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<ColorCorrection><SOPNode><Slope>&xxe; 1 1</Slope></SOPNode></ColorCorrection>
"""
    with pytest.raises(ErrorFormatoCDL):
        leer_cdl(_escribe(tmp_path, "xxe.cc", xxe))


def test_xml_mal_formado(tmp_path):
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "roto.cc", "<ColorCorrection><SOPNode>"))
    assert "bien formado" in str(e.value)


def test_xml_valido_pero_que_no_es_un_cdl(tmp_path):
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "otro.cc", "<rss><canal/></rss>"))
    assert "ColorCorrection" in str(e.value) and "rss" in str(e.value)


def test_colorcorrection_vacio(tmp_path):
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "vac.cc", "<ColorCorrection/>"))
    assert "está vacío" in str(e.value)


def test_slope_con_letras(tmp_path):
    texto = "<ColorCorrection><SOPNode><Slope>uno dos tres</Slope></SOPNode></ColorCorrection>"
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "letras.cc", texto))
    assert "no es un número" in str(e.value) and "uno" in str(e.value)


def test_slope_con_dos_numeros(tmp_path):
    texto = "<ColorCorrection><SOPNode><Slope>1 1</Slope></SOPNode></ColorCorrection>"
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "dos.cc", texto))
    assert "3 números" in str(e.value)


def test_saturacion_no_finita(tmp_path):
    texto = """<ColorCorrection><SatNode><Saturation>NaN</Saturation></SatNode></ColorCorrection>"""
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(_escribe(tmp_path, "nan.cc", texto))
    assert "finito" in str(e.value)


def test_fichero_vacio(tmp_path):
    ruta = tmp_path / "v.cc"
    ruta.write_bytes(b"")
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(ruta)
    assert "vacío" in str(e.value)


def test_fichero_que_no_existe(tmp_path):
    with pytest.raises(ErrorFormatoCDL) as e:
        leer_cdl(tmp_path / "ni_idea.cdl")
    assert "no existe" in str(e.value)


@pytest.mark.skipif(es_root, reason="root lee cualquier cosa")
def test_fichero_sin_permiso(tmp_path):
    ruta = escribir_cdl(CDL.identity(), tmp_path / "c.cc")
    ruta.chmod(0o000)
    try:
        with pytest.raises(ErrorFormatoCDL) as e:
            leer_cdl(ruta)
        assert "permiso" in str(e.value)
    finally:
        ruta.chmod(0o644)


# ---------------------------------------------------------------------------
# Escritura: casos frontera
# ---------------------------------------------------------------------------


def test_extension_desconocida(tmp_path):
    with pytest.raises(ErrorFormatoCDL) as e:
        escribir_cdl(CDL.identity(), tmp_path / "x.xml")
    assert ".ccc" in str(e.value)


def test_un_cc_no_admite_varios(tmp_path):
    with pytest.raises(ErrorFormatoCDL) as e:
        escribir_cdls([("a", CDL.identity()), ("b", CDL.identity())], tmp_path / "x.cc")
    assert "UN solo" in str(e.value)


def test_directorio_que_no_existe(tmp_path):
    destino = tmp_path / "no" / "existe" / "x.cc"
    with pytest.raises(ErrorFormatoCDL) as e:
        escribir_cdl(CDL.identity(), destino)
    assert "no existe" in str(e.value)
    assert not destino.parent.exists()
    escribir_cdl(CDL.identity(), destino, crear_directorios=True)
    assert destino.is_file()


def test_lista_vacia(tmp_path):
    with pytest.raises(ErrorFormatoCDL):
        escribir_cdls([], tmp_path / "x.ccc")


def test_si_no_puede_crear_la_carpeta_da_errorformatocdl(tmp_path, monkeypatch):
    """Bug real encontrado en revisión: `ruta.parent.mkdir(...)` no estaba
    protegido, a diferencia de `core.io.cube.escribir_cube`."""
    from pathlib import Path

    def _mkdir_que_falla(self, *a, **k):
        raise OSError("permiso denegado")

    monkeypatch.setattr(Path, "mkdir", _mkdir_que_falla)
    with pytest.raises(ErrorFormatoCDL, match="no puedo crear la carpeta"):
        escribir_cdl(CDL.identity(), tmp_path / "no" / "existe" / "x.cc", crear_directorios=True)
