"""Piezas comunes para las llamadas de interpretación a la IA."""

from __future__ import annotations

from typing import Any, Protocol

from ..deteccion import Enmascarador


class ClienteLLM(Protocol):
    def llamar(self, **kwargs: Any) -> Any: ...


def entrada_herramienta(respuesta: Any, nombre: str) -> dict[str, Any] | None:
    for bloque in getattr(respuesta, "bloques_herramienta", []):
        if bloque.get("nombre") == nombre and isinstance(bloque.get("entrada"), dict):
            return bloque["entrada"]
    return None


def enmascarar(texto: str) -> str:
    """RUT, correos, teléfonos y fechas se reemplazan por marcadores antes de llamar a la IA."""
    return Enmascarador().enmascarar(texto)
