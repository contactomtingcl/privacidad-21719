"""Canal de reporte: enlace o QR, confirmación al titular y modo reservado.

La IA solo propone hechos sobre texto enmascarado; el motor decide plazos y deberes; las
personas confirman y validan. Ver `servicio.CanalReporte` para el flujo completo.
"""

from .modelos import Caso, Organizacion, cargar_organizaciones
from .repositorio import RepositorioCasos
from .servicio import (
    CanalReporte,
    CasoNoEncontrado,
    ErrorCanal,
    OrganizacionDesconocida,
    ReservadoNoDisponible,
)
from .web import crear_app

__all__ = [
    "CanalReporte",
    "Caso",
    "CasoNoEncontrado",
    "ErrorCanal",
    "Organizacion",
    "OrganizacionDesconocida",
    "RepositorioCasos",
    "ReservadoNoDisponible",
    "cargar_organizaciones",
    "crear_app",
]
