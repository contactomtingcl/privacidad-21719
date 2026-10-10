"""Corpus legal indexado por artículo."""

from .corpus import RAIZ_DATOS, Corpus, corpus_por_defecto
from .modelos import Articulo, Norma, ResultadoCita
from .parser import normalizar_clave

__all__ = [
    "RAIZ_DATOS",
    "Articulo",
    "Corpus",
    "Norma",
    "ResultadoCita",
    "corpus_por_defecto",
    "normalizar_clave",
]
