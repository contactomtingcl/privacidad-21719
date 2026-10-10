"""Interpretación de mensajes de titulares: qué derecho ejercen y si hay que confirmarlo.

La IA propone; el titular confirma cuando el mensaje es ambiguo; el motor calcula los
plazos. Si la IA falla, el mensaje queda como "requiere revisión" y el plazo corre igual.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..motor import HechosSolicitud
from ..motor.motor import Derecho
from .comun import ClienteLLM, enmascarar, entrada_herramienta, sin_respuesta

DERECHOS: tuple[str, ...] = Derecho.__args__

SISTEMA = """Interpretas mensajes que personas envían a una organización chilena por su canal \
de privacidad. Determinas si el mensaje ejerce alguno de los derechos del artículo 4 de la Ley \
19.628 (modificada por la Ley 21.719) y cuáles:

- acceso: saber si tratan sus datos, cuáles, para qué, de dónde salieron, a quién se \
entregaron, por cuánto tiempo, o la lógica de una decisión automatizada.
- rectificacion: corregir o actualizar datos inexactos, desactualizados o incompletos.
- supresion: eliminar sus datos (todos o una parte).
- oposicion: que dejen de usar sus datos para un fin determinado (por ejemplo, publicidad, \
perfiles o estadísticas) sin pedir que los borren. Retirar el consentimiento para un fin \
cuenta como oposición a ese fin.
- portabilidad: recibir sus datos en un formato electrónico estructurado o que se transfieran \
a otra organización.
- bloqueo: suspender temporalmente el uso de sus datos mientras se resuelve una rectificación, \
supresión u oposición.

Reglas:
- Un reclamo comercial, un trámite, una felicitación, un saludo o el aviso de un incidente \
(por ejemplo, "me llegó la boleta de otra persona") no es una solicitud de derechos.
- Marca requiere_confirmacion cuando el mensaje admite lecturas con respuestas distintas (por \
ejemplo, "no quiero más correos" puede ser oposición a la publicidad o supresión de los datos), \
o cuando le falta algo que la ley pide para tramitarlo: qué datos o qué tratamiento, la \
corrección precisa en una rectificación, la causal en una oposición basada en interés \
legítimo, o, si pide solo bloqueo, a qué solicitud acompaña.
- Si requiere confirmación, escribe una pregunta corta y amable, en español de Chile y sin \
términos legales, que el titular pueda responder con un clic o una frase.
- No pidas confirmación por verificar la identidad del titular o de su representante, ni por \
detalles que el delegado puede resolver al tramitar: eso lo maneja otro paso del proceso.
- El bloqueo temporal siempre acompaña a otra solicitud: si pide no usar sus datos mientras se \
corrigen, borran o se resuelve su oposición, incluye también ese derecho.
- Por privacidad, el texto trae marcadores como [RUT_1], [CORREO_1] o [TELEFONO_1] en lugar de \
los datos. Cada marcador es un dato que el titular sí escribió: si dice "mi nuevo teléfono es \
[TELEFONO_1]", la corrección está completa.
- No calcules plazos: los calcula el sistema."""


class InterpretacionSolicitud(BaseModel):
    hechos: HechosSolicitud | None
    resumen: str | None = None
    costo_usd: float = 0.0
    error: str | None = None


def _herramienta() -> dict[str, Any]:
    return {
        "name": "interpretar_solicitud",
        "description": "Registra cómo se interpreta el mensaje del titular.",
        "input_schema": {
            "type": "object",
            "properties": {
                "es_solicitud": {"type": "boolean"},
                "derechos": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(DERECHOS)},
                },
                "requiere_confirmacion": {"type": "boolean"},
                "pregunta_confirmacion": {"type": "string"},
                "resumen": {
                    "type": "string",
                    "description": "Qué entendiste, en una frase para el delegado.",
                },
            },
            "required": ["es_solicitud", "derechos", "requiere_confirmacion", "resumen"],
        },
    }


def interpretar_solicitud(texto: str, cliente: ClienteLLM, modelo: str) -> InterpretacionSolicitud:
    try:
        r = cliente.llamar(
            modelo=modelo,
            sistema=SISTEMA,
            mensajes=[{"role": "user", "content": f"Mensaje del titular:\n{enmascarar(texto)}"}],
            herramientas=[_herramienta()],
            forzar_herramienta="interpretar_solicitud",
            max_tokens=1000,
            proposito="canal: interpretar solicitud",
        )
    except Exception as e:  # la falla de la IA no detiene el caso
        return InterpretacionSolicitud(hechos=None, error=type(e).__name__)
    costo = getattr(r, "costo_usd", 0.0)
    entrada = entrada_herramienta(r, "interpretar_solicitud")
    if not entrada:
        return InterpretacionSolicitud(hechos=None, costo_usd=costo, error=sin_respuesta(r))
    derechos = [d for d in entrada.get("derechos", []) if d in DERECHOS]
    es_solicitud = bool(entrada.get("es_solicitud")) and bool(derechos)
    hechos = HechosSolicitud(
        es_solicitud=es_solicitud,
        derechos=list(dict.fromkeys(derechos)) if es_solicitud else [],
        requiere_confirmacion=bool(entrada.get("requiere_confirmacion")) and es_solicitud,
        pregunta_confirmacion=entrada.get("pregunta_confirmacion") or None,
    )
    return InterpretacionSolicitud(hechos=hechos, resumen=entrada.get("resumen"), costo_usd=costo)
