"""Corpus legal indexado por artículo y verificador de citas.

Regla del sistema: la IA nunca redacta el texto de un artículo. Solo entrega la
referencia (norma y artículo); el texto que ve el usuario sale de este corpus.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .modelos import Articulo, Norma, ResultadoCita
from .parser import leer_ley_21719, leer_norma_simple, normalizar_clave

RAIZ_DATOS = Path(__file__).resolve().parents[3] / "data" / "normas"

# Nombres con que una persona o un modelo pueden referirse a cada norma.
ALIAS_NORMAS: dict[str, str] = {
    "ley-19628": "ley-19628",
    "19628": "ley-19628",
    "19.628": "ley-19628",
    "ley 19.628": "ley-19628",
    "ley-21719": "ley-21719",
    "21719": "ley-21719",
    "21.719": "ley-21719",
    "ley 21.719": "ley-21719",
    "ley-21663": "ley-21663",
    "21663": "ley-21663",
    "21.663": "ley-21663",
    "ley 21.663": "ley-21663",
    "ds-662-2025": "ds-662-2025",
    "ds 662": "ds-662-2025",
    "decreto 662": "ds-662-2025",
}


def _normalizar_texto(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


class Corpus:
    """Colección de normas y artículos, con búsqueda y verificación de citas."""

    def __init__(self, normas: list[Norma], articulos: list[Articulo]) -> None:
        self.normas: dict[str, Norma] = {n.clave: n for n in normas}
        self._articulos: dict[tuple[str, str], Articulo] = {}
        for art in articulos:
            llave = (art.norma, art.clave)
            if llave in self._articulos:
                raise ValueError(f"Artículo duplicado: {llave}")
            if art.norma not in self.normas:
                raise ValueError(f"Artículo de una norma desconocida: {llave}")
            self._articulos[llave] = art

    @classmethod
    def desde_directorio(cls, raiz: Path = RAIZ_DATOS) -> Corpus:
        normas: list[Norma] = []
        articulos: list[Articulo] = []
        n, a = leer_ley_21719(raiz / "ley-21719.txt")
        normas += n
        articulos += a
        for nombre in ("ds-662-2025.txt", "ley-21663.txt"):
            norma, arts = leer_norma_simple(raiz / nombre)
            normas.append(norma)
            articulos += arts
        return cls(normas, articulos)

    # --- consulta ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._articulos)

    def articulos(self, norma: str | None = None) -> list[Articulo]:
        clave = self.resolver_norma(norma) if norma else None
        return [a for a in self._articulos.values() if clave is None or a.norma == clave]

    @staticmethod
    def resolver_norma(nombre: str) -> str:
        clave = ALIAS_NORMAS.get(nombre.strip().lower())
        if clave is None:
            raise KeyError(f"Norma no reconocida: {nombre!r}")
        return clave

    def obtener(self, norma: str, articulo: str) -> Articulo | None:
        try:
            clave_norma = self.resolver_norma(norma)
        except KeyError:
            return None
        sin_prefijo = re.sub(r"^(art[íi]culo|art\.)\s*", "", articulo.strip(), flags=re.I)
        clave = normalizar_clave(sin_prefijo)
        return self._articulos.get((clave_norma, clave))

    def verificar_cita(
        self, norma: str, articulo: str, fragmento: str | None = None
    ) -> ResultadoCita:
        """Comprueba que una cita existe y, si se entrega, que el fragmento aparece en ella.

        La comparación del fragmento ignora mayúsculas, tildes, puntuación y espacios.
        """
        art = self.obtener(norma, articulo)
        if art is None:
            return ResultadoCita(
                norma=norma,
                articulo=articulo,
                existe=False,
                motivo="El artículo no existe en el corpus indexado.",
            )
        encontrado: bool | None = None
        motivo = None
        if fragmento is not None:
            encontrado = _normalizar_texto(fragmento) in _normalizar_texto(art.texto)
            if not encontrado:
                motivo = "El fragmento citado no aparece en el texto oficial del artículo."
        return ResultadoCita(
            norma=art.norma,
            articulo=art.clave,
            existe=True,
            fragmento_encontrado=encontrado,
            texto=art.texto,
            motivo=motivo,
        )

    # --- exportación ------------------------------------------------------

    def a_dict(self) -> dict:
        return {
            "normas": [n.model_dump() for n in self.normas.values()],
            "articulos": [a.model_dump() for a in self._articulos.values()],
        }

    def a_json(self) -> str:
        return json.dumps(self.a_dict(), ensure_ascii=False, indent=2) + "\n"


@lru_cache(maxsize=1)
def corpus_por_defecto() -> Corpus:
    return Corpus.desde_directorio()
