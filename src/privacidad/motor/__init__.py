"""Motor de reglas legales: decide deberes y plazos. No usa IA."""

from .motor import (
    Deber,
    HechosIncidente,
    HechosSolicitud,
    ResultadoIncidente,
    ResultadoSolicitud,
    cargar_reglas,
    decidir_incidente,
    decidir_solicitud,
    es_servicio_esencial,
    sumar_dias_habiles,
)

__all__ = [
    "Deber",
    "HechosIncidente",
    "HechosSolicitud",
    "ResultadoIncidente",
    "ResultadoSolicitud",
    "cargar_reglas",
    "decidir_incidente",
    "decidir_solicitud",
    "es_servicio_esencial",
    "sumar_dias_habiles",
]
