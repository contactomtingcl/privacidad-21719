"""Datos del canal: organizaciones, casos, eventos y confirmaciones.

Un caso nunca guarda la identidad reservada en claro: queda dentro de `identidad_cifrada`.
Los eventos describen qué pasó sin copiar datos personales; el texto del titular vive solo en
el caso. Así el registro de evidencia (`evidencia.py`) encadena los eventos sin arrastrar datos
personales.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from ..motor import (
    Deber,
    HechosIncidente,
    HechosSolicitud,
    ResultadoIncidente,
    ResultadoSolicitud,
)
from ..motor.motor import Derecho, PerfilOrganizacion

RAIZ_CANAL = Path(__file__).resolve().parents[3] / "data" / "canal"
ZONA_CHILE = ZoneInfo("America/Santiago")

TipoReporte = Literal["solicitud", "incidente", "aviso_proveedor"]
EstadoCaso = Literal[
    "pendiente_confirmacion",  # falta que el titular confirme qué pidió
    "interpretado",  # hay una lectura vigente (confirmada, corregida o por defecto)
    "requiere_revision",  # la IA no respondió: lo revisa el delegado; los plazos corren igual
    "sin_solicitud",  # el mensaje no ejerce un derecho; lo revisa una persona
]
Urgencia = Literal["inmediata", "alta", "normal"]
EstadoConfirmacion = Literal["no_requerida", "pendiente", "confirmada", "corregida", "por_defecto"]


def ahora_chile() -> datetime:
    """Hora actual en Chile, con zona horaria (los plazos legales se cuentan en hora local)."""
    return datetime.now(ZONA_CHILE)


class Organizacion(BaseModel):
    id: str
    nombre: str
    perfil: PerfilOrganizacion
    version_enlace: int = 1


class Evento(BaseModel):
    tipo: str
    momento: datetime
    detalle: dict[str, Any] = Field(default_factory=dict)


class Confirmacion(BaseModel):
    """Lo que el sistema entendió y lo que respondió el titular."""

    estado: EstadoConfirmacion
    pregunta: str | None = None
    propuesta: list[Derecho] = Field(default_factory=list)  # lectura propuesta por la IA
    vigente: list[Derecho] = Field(default_factory=list)  # lectura con que se tramita hoy
    detalle: str | None = None  # lo que el titular agregó con sus palabras
    espera_hasta: datetime | None = None
    respondida_en: datetime | None = None


# --- enrutamiento ------------------------------------------------------------------------


class Destino(BaseModel):
    rol: Literal["delegado", "area"]
    id: str
    nombre: str
    contacto: str
    porque: str
    motivos: list[str] = Field(default_factory=list)  # claves de regla, para la evidencia


class Asignacion(BaseModel):
    version_reglas: str
    destinos: list[Destino]
    # En modo reservado: áreas que recibirían el caso si no fuera reservado. Las ve el delegado.
    sugeridas: list[Destino] = Field(default_factory=list)
    urgencia: Urgencia
    porque_urgencia: str
    proximo_plazo: str | None = None  # id del deber que vence primero
    vence: datetime | None = None

    def para_evidencia(self) -> dict:
        """Lo que se anota en el registro: identificadores y reglas, sin texto del mensaje."""
        return {
            "version_reglas": self.version_reglas,
            "destinos": [{"id": d.id, "motivos": d.motivos} for d in self.destinos],
            "sugeridas": [{"id": d.id, "motivos": d.motivos} for d in self.sugeridas],
            "urgencia": self.urgencia,
            "proximo_plazo": self.proximo_plazo,
            "vence": self.vence.isoformat() if self.vence else None,
        }


class Caso(BaseModel):
    id: str  # también es el código de seguimiento que recibe la persona
    id_organizacion: str
    tipo: TipoReporte
    ingreso: datetime
    texto: str
    estado: EstadoCaso
    reservado: bool = False
    identidad: dict[str, str] | None = None  # solo si la persona no pidió reserva
    identidad_cifrada: str | None = None
    resumen_ia: str | None = None
    error_ia: str | None = None
    costo_usd: float = 0.0
    hechos_solicitud: HechosSolicitud | None = None
    confirmacion: Confirmacion | None = None
    resultado_solicitud: ResultadoSolicitud | None = None
    hechos_incidente: HechosIncidente | None = None
    resultado_incidente: ResultadoIncidente | None = None
    # Si la IA no respondió: relojes de la ANCI que correrían si el incidente resultara de
    # ciberseguridad, para que el delegado los vea desde el primer minuto.
    relojes_anci_posibles: list[Deber] = Field(default_factory=list)
    asignacion: Asignacion | None = None  # a quién le llegó y con qué urgencia
    eventos: list[Evento] = Field(default_factory=list)

    def registrar(self, tipo: str, momento: datetime, /, **detalle: Any) -> None:
        self.eventos.append(Evento(tipo=tipo, momento=momento, detalle=detalle))


def cargar_organizaciones(ruta: Path | None = None) -> dict[str, Organizacion]:
    datos = yaml.safe_load((ruta or RAIZ_CANAL / "organizaciones.yaml").read_text("utf-8"))
    orgs = [Organizacion(**o) for o in datos["organizaciones"]]
    return {o.id: o for o in orgs}
