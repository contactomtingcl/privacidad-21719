"""Carga del set etiquetado (data/evaluacion)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..motor import HechosIncidente
from ..motor.motor import Decision, Derecho, PerfilOrganizacion

RAIZ_EVALUACION = Path(__file__).resolve().parents[3] / "data" / "evaluacion"


class ColumnaEtiquetada(BaseModel):
    nombre: str
    esperado: str
    valores: list[str]
    categorica: bool = False
    trampa: bool = False
    nota: str | None = None


class PlanillaEtiquetada(BaseModel):
    id: str
    descripcion: str
    columnas: list[ColumnaEtiquetada]


class DeberesEsperados(BaseModel):
    aviso_agencia: Decision
    aviso_titulares: Decision
    reporte_anci: Decision


class CasoIncidente(BaseModel):
    id: str
    perfil: PerfilOrganizacion
    texto: str
    hechos: HechosIncidente
    esperado: DeberesEsperados
    nota: str | None = None


class SolicitudEsperada(BaseModel):
    es_solicitud: bool
    derechos: list[Derecho]
    alternativas: list[list[Derecho]] = Field(default_factory=list)
    requiere_confirmacion: bool
    vence_respuesta: date | None = None
    vence_bloqueo: date | None = None


class CasoSolicitud(BaseModel):
    id: str
    ingreso: date
    texto: str
    esperado: SolicitudEsperada
    nota: str | None = None


def _leer(nombre: str, raiz: Path) -> dict:
    return yaml.safe_load((raiz / nombre).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def cargar_columnas(raiz: Path = RAIZ_EVALUACION) -> list[PlanillaEtiquetada]:
    return [PlanillaEtiquetada(**p) for p in _leer("columnas.yaml", raiz)["planillas"]]


@lru_cache(maxsize=1)
def cargar_incidentes(raiz: Path = RAIZ_EVALUACION) -> list[CasoIncidente]:
    return [CasoIncidente(**c) for c in _leer("incidentes.yaml", raiz)["casos"]]


@lru_cache(maxsize=1)
def cargar_solicitudes(raiz: Path = RAIZ_EVALUACION) -> list[CasoSolicitud]:
    return [CasoSolicitud(**c) for c in _leer("solicitudes.yaml", raiz)["casos"]]
