"""Línea base sin IA: reglas por palabras clave, hechas de buena fe.

Representa lo que una organización podría montar con filtros simples. Sirve para medir
cuánto aporta la IA y cuánto aporta el motor.
"""

from __future__ import annotations

import re
import unicodedata

from ..motor import HechosIncidente, HechosSolicitud


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _hay(texto: str, patron: str) -> bool:
    return re.search(patron, texto) is not None


# --- incidentes -------------------------------------------------------------

_SIN_EFECTO = (
    r"nadie hizo clic|los bloqueo|bloqueo durante|no hubo (ningun )?(acceso|ingreso)|"
    r"no se perdio|no se accedio|no hubo acceso a datos|todo normal|ya la arreglamos"
)
_DATOS = (
    r"datos|nombre|rut|correo|direccion|telefono|ficha|planilla|base|liquidacion|curriculum|"
    r"listado|clientes|pacientes|socios|vecinos|trabajadores|postulantes|contribuyentes|carnet"
)


def hechos_incidente_base(texto: str) -> HechosIncidente:
    t = _norm(texto)
    sin_efecto = _hay(t, _SIN_EFECTO)
    if sin_efecto:
        vulneracion = "ninguna"
    elif _hay(t, r"robaron|robo|perd|olvid|extravi|basura"):
        vulneracion = "perdida"
    elif _hay(t, r"ransomware|cifr"):
        vulneracion = "alteracion"
    elif _hay(t, r"borre|borro|elimin"):
        vulneracion = "destruccion"
    elif _hay(t, r"hacke|acceso|entro|descarg|export|malware|espia|ip extranjera"):
        vulneracion = "acceso_no_autorizado"
    elif _hay(t, r"public|expuest|filtr|visible|vendio|tiktok"):
        vulneracion = "filtracion"
    elif _hay(t, r"por error|equivoc|mande|mando|envi"):
        vulneracion = "comunicacion_no_autorizada"
    else:
        vulneracion = "ninguna"

    categorias = []
    if _hay(
        t,
        r"salud|licencia medica|diagnost|clinic|alergia|examen|vih|medicament|subsidio|"
        r"registro social|ayudas sociales|ingresos del hogar|sindica",
    ):
        categorias.append("sensibles")
    if _hay(t, r"nino|ninos|hijos|jardin infantil"):
        categorias.append("menores_14")
    if _hay(t, r"deuda|credito|mora|por cobrar|deben"):
        categorias.append("financieros")

    if _hay(
        t,
        r"hacke|malware|ransomware|phishing|ataque|servidor|sistema|correo falso|drive|"
        r"web|internet|ip |crm|firewall|nube|programa espia|clave",
    ):
        ciber = "si"
    elif _hay(t, r"pendrive|notebook|disco|celular"):
        ciber = "dudoso"
    else:
        ciber = "no"

    return HechosIncidente(
        datos_personales=_hay(t, _DATOS) and not sin_efecto,
        vulneracion=vulneracion,
        categorias_especiales=categorias,
        riesgo_mitigado=_hay(t, r"cifrad|bitlocker|restaur|borrado remoto"),
        ciberincidente=ciber,
        interrupcion_servicio=_hay(t, r"caid|no podemos atender|no pudo atender|suspend"),
    )


# --- solicitudes ------------------------------------------------------------

_PALABRAS_DERECHO = {
    "acceso": r"saber|que datos|tienen datos|quiero ver|explique|a que empresas|a quien|que hacen|"
    r"me manden todo|mandan todo|manden todos",
    "rectificacion": r"corrij|mal escrit|esta mal|actualizar|cambiar mi|el nuevo es|es el antiguo|"
    r"error en mi|rectific",
    "supresion": r"borr|elimin|saquen|sacar",
    "oposicion": r"no quiero que|dejen de|no me (llamen|manden)|me opongo|no usen|no autorizo|"
    r"retiro mi consentimiento|de baja|publicidad|ofertas",
    "portabilidad": r"otra empresa|formato|excel|otro sistema|directamente",
    "bloqueo": r"bloque|suspen|mientras|hasta que",
}


def hechos_solicitud_base(texto: str) -> HechosSolicitud:
    t = _norm(texto)
    derechos = [d for d, patron in _PALABRAS_DERECHO.items() if _hay(t, patron)]
    return HechosSolicitud(es_solicitud=bool(derechos), derechos=derechos)
