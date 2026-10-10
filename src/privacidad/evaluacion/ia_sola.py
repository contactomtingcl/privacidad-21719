"""Comparación: la IA decide sola, con el texto de la ley a la vista.

No se usa en el producto. Existe para medir qué pasa si se le deja a un modelo de
lenguaje la decisión legal, frente a que la IA solo describa los hechos y decida el motor.
Para que la comparación sea justa, la IA recibe los mismos artículos que usa el motor.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from ..corpus import corpus_por_defecto
from ..interpretacion.comun import ClienteLLM, enmascarar, entrada_herramienta
from ..interpretacion.solicitudes import DERECHOS
from ..interpretacion.solicitudes import SISTEMA as SISTEMA_SOLICITUD

DECISIONES = ["si", "no", "revisar"]


def _articulos(*refs: tuple[str, str]) -> str:
    c = corpus_por_defecto()
    return "\n\n".join(c.obtener(n, a).texto for n, a in refs)


class DeberesIA(BaseModel):
    aviso_agencia: str | None = None
    aviso_titulares: str | None = None
    reporte_anci: str | None = None
    costo_usd: float = 0.0
    error: str | None = None


def deberes_incidente(texto: str, perfil: str, cliente: ClienteLLM, modelo: str) -> DeberesIA:
    sistema = (
        "Eres asesor de cumplimiento de una organización chilena. Con el texto legal que "
        "sigue, decide qué deberes de aviso genera el incidente reportado. Responde 'si' si el "
        "deber aplica, 'no' si no aplica y 'revisar' si la ley exige una ponderación que no se "
        "puede resolver con lo que dice el reporte.\n\n"
        "Ley 19.628 (texto de la Ley 21.719):\n"
        + _articulos(("ley-19628", "14 sexies"))
        + "\n\nLey 21.663, Ley Marco de Ciberseguridad:\n"
        + _articulos(("ley-21663", "4"), ("ley-21663", "9"), ("ley-21663", "27"))
    )
    herramienta = {
        "name": "decidir_deberes",
        "description": "Registra los deberes de aviso.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aviso_agencia": {"type": "string", "enum": DECISIONES},
                "aviso_titulares": {"type": "string", "enum": DECISIONES},
                "reporte_anci": {"type": "string", "enum": DECISIONES},
                "razon": {"type": "string"},
            },
            "required": ["aviso_agencia", "aviso_titulares", "reporte_anci", "razon"],
        },
    }
    mensaje = f"Tipo de organización: {perfil.replace('_', ' ')}.\n\nReporte:\n{enmascarar(texto)}"
    try:
        r = cliente.llamar(
            modelo=modelo,
            sistema=sistema,
            mensajes=[{"role": "user", "content": mensaje}],
            herramientas=[herramienta],
            forzar_herramienta="decidir_deberes",
            max_tokens=600,
            proposito="evaluacion: IA sola decide deberes",
        )
    except Exception as e:
        return DeberesIA(error=type(e).__name__)
    entrada = entrada_herramienta(r, "decidir_deberes") or {}
    return DeberesIA(
        aviso_agencia=entrada.get("aviso_agencia"),
        aviso_titulares=entrada.get("aviso_titulares"),
        reporte_anci=entrada.get("reporte_anci"),
        costo_usd=getattr(r, "costo_usd", 0.0),
        error=None if entrada else "sin_respuesta",
    )


class SolicitudIA(BaseModel):
    es_solicitud: bool | None = None
    derechos: list[str] = []
    requiere_confirmacion: bool | None = None
    vence_respuesta: date | None = None
    vence_bloqueo: date | None = None
    costo_usd: float = 0.0
    error: str | None = None


def _fecha(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def solicitud(texto: str, ingreso: date, cliente: ClienteLLM, modelo: str) -> SolicitudIA:
    sistema = (
        SISTEMA_SOLICITUD.replace("- No calcules plazos: los calcula el sistema.", "")
        + "\n\nAdemás calcula las fechas de vencimiento según este artículo (los días hábiles "
        "excluyen sábados, domingos y feriados de Chile):\n\n" + _articulos(("ley-19628", "11"))
    )
    herramienta = {
        "name": "interpretar_y_calcular",
        "description": "Registra la interpretación y los plazos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "es_solicitud": {"type": "boolean"},
                "derechos": {"type": "array", "items": {"type": "string", "enum": list(DERECHOS)}},
                "requiere_confirmacion": {"type": "boolean"},
                "vence_respuesta": {"type": "string", "description": "AAAA-MM-DD o vacío"},
                "vence_bloqueo": {"type": "string", "description": "AAAA-MM-DD o vacío"},
            },
            "required": ["es_solicitud", "derechos", "requiere_confirmacion"],
        },
    }
    mensaje = (
        f"Fecha de ingreso: {ingreso.isoformat()}.\n\nMensaje del titular:\n{enmascarar(texto)}"
    )
    try:
        r = cliente.llamar(
            modelo=modelo,
            sistema=sistema,
            mensajes=[{"role": "user", "content": mensaje}],
            herramientas=[herramienta],
            forzar_herramienta="interpretar_y_calcular",
            max_tokens=600,
            proposito="evaluacion: IA sola interpreta y calcula plazos",
        )
    except Exception as e:
        return SolicitudIA(error=type(e).__name__)
    entrada = entrada_herramienta(r, "interpretar_y_calcular") or {}
    derechos = [d for d in entrada.get("derechos", []) if d in DERECHOS]
    es = bool(entrada.get("es_solicitud")) and bool(derechos)
    return SolicitudIA(
        es_solicitud=es if entrada else None,
        derechos=derechos if es else [],
        requiere_confirmacion=bool(entrada.get("requiere_confirmacion")) and es,
        vence_respuesta=_fecha(entrada.get("vence_respuesta")),
        vence_bloqueo=_fecha(entrada.get("vence_bloqueo")),
        costo_usd=getattr(r, "costo_usd", 0.0),
        error=None if entrada else "sin_respuesta",
    )
