"""Frase de respaldo: el fragmento del mensaje en que la IA dice apoyarse para cada hecho.

La IA copia la frase; el código comprueba que esa frase esté de verdad en el texto que la IA
recibió (ya enmascarado). La comparación ignora mayúsculas, tildes, puntuación y espacios, y
exige palabras completas ("rut" no calza dentro de "ruta").

La frase no decide nada: el motor decide con los hechos. Sirve para que el delegado valide más
rápido y para medir cuántas veces la IA se apoya en algo que el mensaje no dice.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel

LARGO_MAXIMO_FRASE = 300
_PALABRA = re.compile(r"\w+")


class Respaldo(BaseModel):
    frase: str  # tal como la copió la IA (con marcadores como [RUT_1], nunca el dato)
    verificada: bool  # la frase aparece en el texto que la IA recibió


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y solo palabras separadas por un espacio."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c)
    )
    return " ".join(_PALABRA.findall(sin_tildes))


def esta_en(frase: str, texto: str) -> bool:
    f = normalizar(frase)
    return len(f) >= 3 and f" {f} " in f" {normalizar(texto)} "


def leer_respaldos(entrada: Any, campos: set[str], texto_visto: str) -> dict[str, Respaldo]:
    """Toma las frases que entregó la IA (solo para campos conocidos y como texto) y verifica
    cada una contra el texto que la IA vio. Lo vacío o con otra forma se descarta."""
    if not isinstance(entrada, dict):
        return {}
    salida = {}
    for campo, frase in entrada.items():
        if campo not in campos or not isinstance(frase, str):
            continue
        frase = " ".join(frase.split())[:LARGO_MAXIMO_FRASE]
        if frase:
            salida[campo] = Respaldo(frase=frase, verificada=esta_en(frase, texto_visto))
    return salida


def resumen_respaldos(respaldos: dict[str, Respaldo]) -> dict[str, int]:
    """Cifras para la evidencia: cuántas frases y cuántas verificadas (nunca el texto)."""
    return {
        "respaldos": len(respaldos),
        "respaldos_verificados": sum(r.verificada for r in respaldos.values()),
    }
