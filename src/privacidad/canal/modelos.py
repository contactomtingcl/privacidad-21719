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

from ..interpretacion.respaldo import Respaldo
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
# Motivos fijos: van a la evidencia, así que no pueden traer texto libre con datos personales.
# «ia_no_leyo» lo pone el sistema (no se elige) cuando el delegado completa un reporte sin lectura.
MotivoCorreccion = Literal[
    "error_ia", "informacion_nueva", "confirmado_por_area", "otro", "ia_no_leyo"
]
MotivoDecision = Literal["datos_revisados", "consulta_area", "criterio_delegado", "otro"]
MotivoDerivacion = Literal["datos_del_area", "debe_actuar", "consulta", "otro"]
EstadoAviso = Literal["enviado", "simulado", "fallido"]
MotivoIdentidad = Literal["contactar_a_quien_reporto", "requerimiento_de_autoridad", "otro"]
# Por dónde se envió (o se hizo) algo que corresponde. Lista cerrada: va a la evidencia.
CanalEnvio = Literal["correo", "portal_oficial", "carta", "en_persona", "sistemas_internos", "otro"]
EstadoConfirmacion = Literal["no_requerida", "pendiente", "confirmada", "corregida", "por_defecto"]


def ahora_chile() -> datetime:
    """Hora actual en Chile, con zona horaria (los plazos legales se cuentan en hora local)."""
    return datetime.now(ZONA_CHILE)


class Organizacion(BaseModel):
    id: str
    nombre: str
    perfil: PerfilOrganizacion
    # Calificada por la ANCI como operador de importancia vital (Ley 21.663, art. 5 y 6).
    operador_importancia_vital: bool = False
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
    telegram: str | None = None  # id de chat para avisos por Telegram, si se configuró


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


# --- acciones del delegado --------------------------------------------------------------


class Correccion(BaseModel):
    """El delegado cambió hechos propuestos por la IA. Solo valores cerrados, sin texto libre."""

    cambios: dict[str, list[Any]]  # campo → [antes, después]
    motivo: MotivoCorreccion
    nota: str | None = None  # queda en el caso, nunca en la evidencia
    por: str  # identificador de usuario, no un nombre
    momento: datetime


class DecisionDelegado(BaseModel):
    """Resolución humana de un deber que el motor dejó en "revisar"."""

    deber: str
    decision: Literal["si", "no"]
    motivo: MotivoDecision
    por: str
    momento: datetime


class Validacion(BaseModel):
    por: str
    momento: datetime


class Derivacion(BaseModel):
    """El delegado derivó el caso a un área que el enrutamiento no eligió (o que era sugerida)."""

    area: str
    motivo: MotivoDerivacion
    por: str
    momento: datetime


class AvisoRegistrado(BaseModel):
    """Constancia de un aviso a un destino. El texto del aviso no se guarda: se puede volver a
    armar con `avisos.armar_aviso` y no lleva datos personales."""

    destino: str
    estado: EstadoAviso
    momento: datetime
    derivado: bool = False


class OrigenCascada(BaseModel):
    """El caso llegó por la red de cascada: un proveedor reportó una vez para todos sus clientes."""

    codigo: str  # código del reporte del proveedor (el mismo en cada cliente)
    proveedor: str
    nombre_proveedor: str
    servicios: list[str]  # servicios afectados que esta organización usa
    datos: str  # qué datos de ESTA organización trata el proveedor
    planilla: str | None = None  # la planilla del inventario que corresponde, si se sabe


class Envio(BaseModel):
    """El delegado dejó constancia de que envió (o hizo) algo que corresponde. El sistema no
    envía nada: solo registra lo que la persona dice que hizo, con la hora que indica."""

    deber: str
    canal: CanalEnvio
    momento: datetime  # cuándo se envió, según el delegado
    por: str
    registrado: datetime  # cuándo lo anotó en el sistema


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
    # Frase del mensaje (enmascarado) en que la IA apoyó cada hecho o derecho, y si el código la
    # encontró en el texto. Queda en el caso, nunca en la evidencia (solo sus cifras).
    respaldos_ia: dict[str, Respaldo] = Field(default_factory=dict)
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
    # Lo que hizo el delegado. `hechos_incidente` conserva siempre la propuesta de la IA.
    hechos_delegado: HechosIncidente | None = None
    correcciones: list[Correccion] = Field(default_factory=list)
    decisiones: dict[str, DecisionDelegado] = Field(default_factory=dict)
    validacion: Validacion | None = None
    envios: dict[str, Envio] = Field(default_factory=dict)  # deber (o paso de la ANCI) → envío
    derivaciones: list[Derivacion] = Field(default_factory=list)
    avisos: list[AvisoRegistrado] = Field(default_factory=list)
    cascada: OrigenCascada | None = None
    eventos: list[Evento] = Field(default_factory=list)

    def registrar(self, tipo: str, momento: datetime, /, **detalle: Any) -> None:
        self.eventos.append(Evento(tipo=tipo, momento=momento, detalle=detalle))

    @property
    def hechos_vigentes(self) -> HechosIncidente | None:
        """Los hechos con que decide el motor: los del delegado si corrigió, si no los de la IA."""
        return self.hechos_delegado or self.hechos_incidente


def cargar_organizaciones(ruta: Path | None = None) -> dict[str, Organizacion]:
    datos = yaml.safe_load((ruta or RAIZ_CANAL / "organizaciones.yaml").read_text("utf-8"))
    orgs = [Organizacion(**o) for o in datos["organizaciones"]]
    return {o.id: o for o in orgs}
