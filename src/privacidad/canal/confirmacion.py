"""Confirmación de la interpretación con el titular.

La IA propone qué derecho ejerce la persona; el titular confirma o corrige; si no responde, el
motor aplica una regla fija. La IA nunca elige la lectura por defecto, y la confirmación no
detiene el reloj: el plazo del artículo 11 corre desde el ingreso (`decidir_solicitud` lo
calcula con la fecha de ingreso, sin importar cuándo se confirmó).

Los parámetros (días de espera y qué lecturas se confunden) están en `data/reglas/reglas.yaml`,
con su fuente, como el resto de las reglas.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..motor import HechosSolicitud, cargar_reglas
from ..motor.motor import Derecho
from .modelos import Confirmacion

DERECHOS: tuple[str, ...] = Derecho.__args__
LARGO_MAXIMO_DETALLE = 1000

# Texto para la pantalla, sin términos legales.
ETIQUETAS_DERECHO: dict[str, str] = {
    "acceso": "Saber qué datos míos tienen y para qué los usan",
    "rectificacion": "Corregir datos míos que están mal o desactualizados",
    "supresion": "Que borren mis datos",
    "oposicion": "Que dejen de usar mis datos para un fin (por ejemplo, publicidad)",
    "portabilidad": "Recibir una copia de mis datos para llevarlos a otra organización",
    "bloqueo": "Que no usen mis datos mientras se resuelve mi solicitud",
}
PREGUNTA_GENERICA = "¿Nos cuenta con sus palabras qué necesita que hagamos con sus datos?"


class RespuestaInvalida(ValueError):
    """La respuesta del titular no se puede aplicar."""


def _parametros() -> dict:
    return cargar_reglas()["reglas"]["confirmacion_titular"]["parametros"]


def dias_de_espera() -> int:
    return int(_parametros()["espera_dias"])


def es_irreversible(derecho: str) -> bool:
    """Derechos que nunca se aplican sin confirmación expresa del titular (borrar datos)."""
    return derecho in _parametros()["lectura_por_defecto"]["irreversibles"]


def lectura_por_defecto(propuesta: list[Derecho]) -> list[Derecho]:
    """Lectura reversible para cuando el titular no responde.

    Lo irreversible (supresión) se cambia por su equivalente reversible (oposición); si queda una
    oposición se agrega el bloqueo temporal de esos datos. El resto de los derechos queda igual.
    """
    reglas = _parametros()["lectura_por_defecto"]
    resultado: list[Derecho] = []
    for derecho in propuesta:
        if derecho in reglas["irreversibles"]:
            derecho = reglas["sustituto_reversible"]
        if derecho not in resultado:
            resultado.append(derecho)
    complemento = reglas["complemento_temporal"]
    if complemento["si_hay"] in resultado and complemento["agregar"] not in resultado:
        resultado.append(complemento["agregar"])
    return resultado


def preparar(hechos: HechosSolicitud, ahora: datetime) -> Confirmacion:
    """Estado inicial de la confirmación a partir de lo que propuso la IA."""
    if not hechos.es_solicitud:
        raise RespuestaInvalida("Solo se confirma lo que es una solicitud")
    propuesta = list(hechos.derechos)
    if not hechos.requiere_confirmacion:
        return Confirmacion(estado="no_requerida", propuesta=propuesta, vigente=propuesta)
    return Confirmacion(
        estado="pendiente",
        pregunta=hechos.pregunta_confirmacion or PREGUNTA_GENERICA,
        propuesta=propuesta,
        vigente=propuesta,
        espera_hasta=ahora + timedelta(days=dias_de_espera()),
    )


def aplicar_respuesta(
    conf: Confirmacion, derechos: list[str], detalle: str | None, ahora: datetime
) -> Confirmacion:
    """El titular confirma o corrige con las opciones de la pantalla (no interviene la IA)."""
    if conf.estado in ("confirmada", "corregida"):
        raise RespuestaInvalida("La confirmación ya fue respondida")
    elegidos = list(dict.fromkeys(derechos))
    if not elegidos:
        raise RespuestaInvalida("Elija al menos una opción")
    if any(d not in DERECHOS for d in elegidos):
        raise RespuestaInvalida("Opción desconocida")
    texto = (detalle or "").strip() or None
    if texto and len(texto) > LARGO_MAXIMO_DETALLE:
        raise RespuestaInvalida(f"El detalle admite hasta {LARGO_MAXIMO_DETALLE} caracteres")
    igual = set(elegidos) == set(conf.propuesta)
    return conf.model_copy(
        update={
            "estado": "confirmada" if igual else "corregida",
            "vigente": elegidos,
            "detalle": texto,
            "respondida_en": ahora,
        }
    )


def vencida(conf: Confirmacion | None, ahora: datetime) -> bool:
    return bool(
        conf and conf.estado == "pendiente" and conf.espera_hasta and ahora >= conf.espera_hasta
    )


def aplicar_por_defecto(conf: Confirmacion, ahora: datetime) -> Confirmacion:
    """Sin respuesta del titular se aplica la lectura reversible (nunca borrar datos)."""
    if conf.estado != "pendiente":
        raise RespuestaInvalida("Solo una confirmación pendiente pasa a la lectura por defecto")
    return conf.model_copy(
        update={
            "estado": "por_defecto",
            "vigente": lectura_por_defecto(conf.propuesta),
            "respondida_en": ahora,
        }
    )


def hechos_vigentes(conf: Confirmacion) -> HechosSolicitud:
    """Hechos con la lectura vigente, para que el motor calcule los plazos."""
    if conf.estado == "por_defecto" and any(es_irreversible(d) for d in conf.vigente):
        raise RespuestaInvalida("Nunca se borran datos sin confirmación expresa del titular")
    return HechosSolicitud(es_solicitud=True, derechos=list(conf.vigente))
