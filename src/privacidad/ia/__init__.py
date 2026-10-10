"""Acceso a la API de Claude con registro de costos.

La IA solo interpreta texto ya enmascarado. Nunca decide plazos ni deberes legales.
"""

from .cliente import ClienteIA, RespuestaIA, costo_usd

__all__ = ["ClienteIA", "RespuestaIA", "costo_usd"]
