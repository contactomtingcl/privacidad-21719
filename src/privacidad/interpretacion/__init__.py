"""Interpretación con IA de textos libres (mensajes de titulares y reportes de incidentes).

La IA recibe el texto enmascarado y devuelve hechos. Nunca decide deberes ni plazos.
"""

from .incidentes import ExtraccionIncidente, extraer_hechos
from .solicitudes import InterpretacionSolicitud, interpretar_solicitud

__all__ = [
    "ExtraccionIncidente",
    "InterpretacionSolicitud",
    "extraer_hechos",
    "interpretar_solicitud",
]
