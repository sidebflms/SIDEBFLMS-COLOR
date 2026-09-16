"""La guarda de escritura de la primera prueba con material real.

POR QUE EXISTE
--------------
El dia 1 de otro proyecto de Mario se dejaron carpetas de prueba escritas en un
disco de produccion real. Esto es lo que impide que vuelva a pasar, y lo impide
**en el codigo**, no en la intencion de quien lo ejecute.

LA REGLA, ENTERA
----------------
Toda escritura del script de la primera prueba pasa por un objeto `Guarda`, y la
guarda solo deja escribir si el destino cumple las CUATRO cosas a la vez:

1. Esta **dentro de `pruebas/trabajo/`** de este repo, despues de resolver
   enlaces simbolicos y `..`. Un `pruebas/trabajo/../../x` o un enlace que salga
   de ahi se rechaza.
2. **No esta dentro de ninguna ruta de origen** (la carpeta del master, las
   carpetas de los brutos, y las carpetas de los ficheros de bruto sueltos),
   ni resueltas ni tal cual se escribieron.
3. **No esta en `/Volumes`**. El repo vive en el disco del ordenador; si alguien
   lo mueve a un disco externo, la guarda deja de escribir y lo dice, porque un
   disco externo en esta casa es, hasta que se demuestre lo contrario, un disco
   de produccion.
4. **No existe ya**. Se escribe con `open(..., "xb")`: nunca se sobreescribe
   nada, ni siquiera un fichero propio.

Si cualquiera de las cuatro falla, lanza `EscrituraProhibida` y no escribe ni un
byte. La comprobacion se repite en el momento de escribir (no solo al crear la
guarda) y se vuelve a resolver la carpeta padre justo antes de abrir el
fichero, para que un enlace simbolico creado entre medias no la burle.

Y se falla cerrado desde el principio: si la carpeta de trabajo esta dentro de
un origen (alguien ha pasado el repo entero como carpeta de brutos) o un origen
esta dentro de la carpeta de trabajo, la guarda **no se construye**.

LO QUE ESTE ARCHIVO NO HACE
---------------------------
No lee nada, no borra nada y no conoce ffmpeg. Solo decide si se puede escribir
y, si se puede, escribe.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "RAIZ_REPO",
    "RAIZ_TRABAJO",
    "EscrituraProhibida",
    "Guarda",
    "carpetas_protegidas",
]

#: Raiz del repo, resuelta. `pruebas/guarda.py` -> dos niveles arriba.
RAIZ_REPO: Path = Path(__file__).resolve().parent.parent

#: La UNICA carpeta donde el script de la primera prueba puede escribir.
RAIZ_TRABAJO: Path = RAIZ_REPO / "pruebas" / "trabajo"

#: Raiz de los discos externos en macOS. Nunca se escribe debajo.
_VOLUMES = Path("/Volumes")


class EscrituraProhibida(RuntimeError):
    """Se ha intentado escribir donde no se puede. No se ha escrito nada."""


def _resolver(ruta: str | os.PathLike[str]) -> Path:
    """Ruta absoluta, sin `..` y con los enlaces simbolicos de lo que exista resueltos."""
    return Path(os.path.abspath(os.fspath(ruta))).resolve(strict=False)


def _dentro(ruta: Path, carpeta: Path) -> bool:
    return ruta == carpeta or ruta.is_relative_to(carpeta)


def carpetas_protegidas(origenes: Iterable[str | os.PathLike[str]]) -> tuple[Path, ...]:
    """Las carpetas donde no se escribe nunca, a partir de las rutas de origen.

    Para una carpeta, la carpeta. Para un fichero, **la carpeta que lo contiene**:
    escribir al lado del master es escribir en la carpeta de origen. Se guardan
    las dos formas, la escrita y la resuelta, por si una de ellas es un enlace.
    """
    salida: set[Path] = set()
    for o in origenes:
        literal = Path(os.path.abspath(os.fspath(o)))
        resuelta = _resolver(o)
        for p in (literal, resuelta):
            # Un fichero (o algo que no es carpeta) protege su carpeta.
            salida.add(p if p.is_dir() else p.parent)
    return tuple(sorted(salida))


class Guarda:
    """Unica puerta de escritura del script de la primera prueba."""

    def __init__(
        self,
        origenes: Iterable[str | os.PathLike[str]],
        raiz_trabajo: str | os.PathLike[str] = RAIZ_TRABAJO,
    ) -> None:
        esperada = _resolver(RAIZ_TRABAJO)
        literal_esperada = RAIZ_REPO / "pruebas" / "trabajo"
        if esperada != _resolver(RAIZ_REPO) / "pruebas" / "trabajo" or (
            literal_esperada.is_symlink()
        ):
            raise EscrituraProhibida(
                f"`pruebas/trabajo` es un enlace simbolico que apunta a {esperada}. "
                f"No escribo: la carpeta de trabajo tiene que ser una carpeta de verdad "
                f"dentro del repo."
            )
        raiz = _resolver(raiz_trabajo)
        if not _dentro(raiz, esperada):
            raise EscrituraProhibida(
                f"La carpeta de trabajo tiene que estar dentro de {esperada}, y me han "
                f"pedido {raiz}. No escribo nada."
            )
        if _dentro(raiz, _VOLUMES):
            raise EscrituraProhibida(
                f"La carpeta de trabajo ({raiz}) esta en un disco externo. El repo tiene "
                f"que estar en el disco del ordenador; no escribo en /Volumes."
            )
        protegidas = carpetas_protegidas(origenes)
        for p in protegidas:
            if _dentro(raiz, p):
                raise EscrituraProhibida(
                    f"La carpeta de trabajo ({raiz}) queda DENTRO de una carpeta de origen "
                    f"({p}). Eso significaria escribir en el origen. No sigo."
                )
            if _dentro(p, raiz):
                raise EscrituraProhibida(
                    f"Una ruta de origen ({p}) esta dentro de la carpeta de trabajo ({raiz}). "
                    f"El origen tiene que ser el material de verdad, no algo de pruebas/trabajo."
                )
        self._raiz = raiz
        self._protegidas = protegidas

    # ------------------------------------------------------------------
    @property
    def raiz(self) -> Path:
        return self._raiz

    @property
    def protegidas(self) -> tuple[Path, ...]:
        return self._protegidas

    def comprobar(self, destino: str | os.PathLike[str]) -> Path:
        """Devuelve el destino resuelto si se puede escribir; si no, lanza."""
        d = _resolver(destino)
        literal = Path(os.path.abspath(os.fspath(destino)))
        if d == self._raiz or not d.is_relative_to(self._raiz):
            raise EscrituraProhibida(
                f"Destino fuera de la carpeta de trabajo: {d} (la unica permitida es "
                f"{self._raiz}). No escribo."
            )
        for forma in (d, literal):
            if _dentro(forma, _VOLUMES):
                raise EscrituraProhibida(f"Destino en un disco externo: {forma}. No escribo.")
            for p in self._protegidas:
                if _dentro(forma, p):
                    raise EscrituraProhibida(
                        f"Destino dentro de una carpeta de origen ({p}): {forma}. No escribo."
                    )
        return d

    def crear_carpeta(self, ruta: str | os.PathLike[str]) -> Path:
        """Crea una carpeta (y sus padres) dentro de la carpeta de trabajo.

        Los padres se crean de uno en uno, comprobando cada uno, para que ningun
        `mkdir(parents=True)` pueda crear algo fuera. La raiz de trabajo se
        crea si no existe, que es la unica excepcion a "tiene que estar dentro".
        """
        d = self.comprobar(ruta)
        pendientes: list[Path] = []
        p = d
        while p != self._raiz and not p.exists():
            pendientes.append(p)
            p = p.parent
        if not self._raiz.exists():
            # La raiz ya se verifico en el constructor: esta dentro de
            # `pruebas/trabajo`, y `pruebas/` existe porque este archivo vive ahi.
            self._raiz.mkdir(parents=True, exist_ok=True)
        for q in reversed(pendientes):
            self.comprobar(q)
            q.mkdir(exist_ok=False)
        if not d.is_dir():
            raise EscrituraProhibida(f"{d} existe y no es una carpeta. No escribo.")
        return d

    def escribir_bytes(self, ruta: str | os.PathLike[str], datos: bytes) -> Path:
        """Escribe un fichero NUEVO. Nunca sobreescribe."""
        d = self.comprobar(ruta)
        padre = _resolver(d.parent)
        if not padre.is_dir():
            raise EscrituraProhibida(
                f"La carpeta {padre} no existe. Creala antes con la guarda. No escribo."
            )
        # Segunda comprobacion, justo antes de abrir: por si entre medias alguien
        # ha cambiado una carpeta por un enlace.
        d = self.comprobar(padre / d.name)
        with open(d, "xb") as f:
            f.write(datos)
        return d

    def escribir_texto(self, ruta: str | os.PathLike[str], texto: str) -> Path:
        return self.escribir_bytes(ruta, texto.encode("utf-8"))
