"""Extracción de hechos desde el reporte de un incidente.

La IA solo describe lo que pasó (hechos). Los deberes y plazos los decide el motor.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..motor import HechosIncidente
from ..motor.motor import CategoriaEspecial, Vulneracion
from .comun import ClienteLLM, enmascarar, entrada_herramienta, sin_respuesta
from .respaldo import Respaldo, leer_respaldos

SISTEMA = """Lees reportes de incidentes escritos por personas de una organización chilena y \
describes los hechos. No decides si hay que avisar a alguien: eso lo hace el sistema con \
reglas fijas. Describe solo lo que el texto dice o permite deducir con seguridad.

Campos:
- datos_personales: el incidente involucra información de personas naturales identificables.
- vulneracion: qué les pasó a los datos personales por una falla de seguridad: filtracion, \
perdida, alteracion (incluye cifrado por ransomware), destruccion, acceso_no_autorizado, \
comunicacion_no_autorizada (envío o exposición a quien no debía verlos), o ninguna (no hubo \
pérdida, exposición ni acceso indebido, por ejemplo un ataque bloqueado, una caída sin daño a \
los datos, un acceso autorizado o un reclamo que no es un incidente).
- categorias_especiales: incluye "sensibles" si hay datos de salud, situación socioeconómica \
(por ejemplo, ingresos o beneficios sociales), afiliación sindical o política, \
religión, origen étnico, biometría o vida sexual; "menores_14" si hay datos de niños o niñas \
menores de 14 años; "financieros" si hay datos sobre obligaciones económicas, \
financieras, bancarias o comerciales (por ejemplo, deudas o créditos). Un RUT, nombre, \
correo, dirección o sueldo, por sí solos, no son categorías especiales.
- riesgo_mitigado: true solo si hay una razón concreta y verificable para pensar que nadie \
pudo leer o usar los datos (por ejemplo, cifrado fuerte o evidencia técnica de que nadie \
accedió).
- ciberincidente: "si" si afecta redes, sistemas o cuentas informáticas (malware, ataque, \
intrusión, configuración expuesta, caída de sistemas); "no" si es papel, un error humano de \
envío o una conversación; "dudoso" si es la pérdida o robo de un dispositivo o soporte digital \
sin evidencia de ataque.
- interrupcion_servicio: el incidente impidió prestar un servicio a las personas.
- titulares_aprox: número de personas afectadas si el texto lo dice; si no, omítelo.

El texto puede traer marcadores como [RUT_1] en lugar de datos personales.

En respaldos, para cada hecho que afirmas, copia el fragmento exacto del reporte que lo \
sostiene (de 3 a 20 palabras, sin cambiar ni resumir nada; los marcadores se copian tal cual). \
Si un hecho no sale de una frase concreta (por ejemplo, un "no" porque el texto no lo menciona), \
no pongas respaldo para ese hecho. El sistema comprueba que cada fragmento esté en el texto."""


CAMPOS_RESPALDO = set(HechosIncidente.model_fields)


def afirmados_incidente(h: HechosIncidente) -> set[str]:
    """Hechos que la IA afirma (los que deberían tener una frase que los sostenga). Un "no" por
    omisión, como "no interrumpió el servicio", no necesita frase."""
    afirmados = {
        "datos_personales": h.datos_personales,
        "vulneracion": h.vulneracion != "ninguna",
        "categorias_especiales": bool(h.categorias_especiales),
        "riesgo_mitigado": h.riesgo_mitigado,
        "ciberincidente": h.ciberincidente != "no",
        "interrupcion_servicio": h.interrupcion_servicio,
        "titulares_aprox": h.titulares_aprox is not None,
    }
    return {campo for campo, si in afirmados.items() if si}


class ExtraccionIncidente(BaseModel):
    hechos: HechosIncidente | None
    resumen: str | None = None
    respaldos: dict[str, Respaldo] = Field(default_factory=dict)
    costo_usd: float = 0.0
    error: str | None = None


def _herramienta() -> dict[str, Any]:
    return {
        "name": "registrar_hechos",
        "description": "Registra los hechos del incidente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "datos_personales": {"type": "boolean"},
                "vulneracion": {"type": "string", "enum": list(Vulneracion.__args__)},
                "categorias_especiales": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(CategoriaEspecial.__args__)},
                },
                "riesgo_mitigado": {"type": "boolean"},
                "ciberincidente": {"type": "string", "enum": ["si", "no", "dudoso"]},
                "interrupcion_servicio": {"type": "boolean"},
                "titulares_aprox": {"type": "integer"},
                "resumen": {"type": "string", "description": "Qué pasó, en una frase."},
                "respaldos": {
                    "type": "object",
                    "description": "Fragmento textual del reporte que sostiene cada hecho.",
                    "properties": {c: {"type": "string"} for c in sorted(CAMPOS_RESPALDO)},
                },
            },
            "required": [
                "datos_personales",
                "vulneracion",
                "categorias_especiales",
                "riesgo_mitigado",
                "ciberincidente",
                "interrupcion_servicio",
                "resumen",
                "respaldos",
            ],
        },
    }


def extraer_hechos(texto: str, cliente: ClienteLLM, modelo: str) -> ExtraccionIncidente:
    visto = enmascarar(texto)
    try:
        r = cliente.llamar(
            modelo=modelo,
            sistema=SISTEMA,
            mensajes=[{"role": "user", "content": f"Reporte:\n{visto}"}],
            herramientas=[_herramienta()],
            forzar_herramienta="registrar_hechos",
            max_tokens=1500,
            proposito="incidentes: extraer hechos",
        )
    except Exception as e:
        return ExtraccionIncidente(hechos=None, error=type(e).__name__)
    costo = getattr(r, "costo_usd", 0.0)
    entrada = entrada_herramienta(r, "registrar_hechos")
    if not entrada:
        return ExtraccionIncidente(hechos=None, costo_usd=costo, error=sin_respuesta(r))
    resumen = entrada.pop("resumen", None)
    respaldos = leer_respaldos(entrada.pop("respaldos", None), CAMPOS_RESPALDO, visto)
    entrada = {k: v for k, v in entrada.items() if v is not None}
    if not isinstance(entrada.get("titulares_aprox"), int):
        entrada.pop("titulares_aprox", None)  # dato informativo; no decide nada
    try:
        hechos = HechosIncidente(**entrada)
    except ValidationError:
        return ExtraccionIncidente(hechos=None, costo_usd=costo, error="respuesta_invalida")
    return ExtraccionIncidente(hechos=hechos, resumen=resumen, respaldos=respaldos, costo_usd=costo)
