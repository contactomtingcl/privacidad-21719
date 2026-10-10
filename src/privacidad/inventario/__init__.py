"""Inventario de datos personales a partir de planillas."""

from .perfilador import (
    PerfilColumna,
    PerfilPlanilla,
    ResumenMenores,
    cargar_categorias,
    leer_planilla,
    perfilar_archivo,
    perfilar_dataframe,
)

__all__ = [
    "PerfilColumna",
    "PerfilPlanilla",
    "ResumenMenores",
    "cargar_categorias",
    "leer_planilla",
    "perfilar_archivo",
    "perfilar_dataframe",
]
