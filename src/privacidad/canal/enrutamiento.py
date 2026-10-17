"""Enrutamiento: a quién le llega cada caso y con qué urgencia.

Se decide con reglas escritas en `data/canal/enrutamiento.yaml`, sin IA:

- El delegado de protección de datos recibe siempre todos los casos.
- Un área recibe el caso si el mensaje menciona una de sus palabras, o si el caso es de un tipo
  que el área atiende (por ejemplo, Informática recibe los posibles ciberincidentes).
- En modo reservado el caso va solo al delegado; las áreas quedan como sugerencia.
- La urgencia sale de los plazos que calculó el motor de reglas.

Cada destino lleva su porqué en lenguaje simple. El evento que queda en la evidencia guarda solo
identificadores de área y reglas, nunca el texto del mensaje.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .. import guardia
from ..motor import Deber
from .modelos import RAIZ_CANAL, ZONA_CHILE, Asignacion, Caso, Destino, Urgencia

TipoRecibe = Literal["solicitud", "incidente", "aviso_proveedor", "ciberincidente"]

NOMBRES_DEBER = {
    "aviso_agencia": "aviso a la Agencia",
    "aviso_titulares": "aviso a los titulares",
    "reporte_anci": "primer aviso a la ANCI",
    "anci_alerta_temprana": "primer aviso a la ANCI",
    "anci_actualizacion": "actualización a la ANCI",
    "anci_informe_final": "informe final a la ANCI",
    "respuesta_solicitud": "respuesta a la persona",
    "bloqueo_temporal": "respuesta al bloqueo temporal",
    "comunicar_a_terceros": "aviso a quienes recibieron los datos",
}


# --- reglas ---------------------------------------------------------------------------


class Area(BaseModel):
    id: str
    nombre: str
    contacto: str
    datos: str
    palabras: list[str] = Field(default_factory=list)
    recibe: list[TipoRecibe] = Field(default_factory=list)


class Delegado(BaseModel):
    cargo: str
    contacto: str


class ReglasOrganizacion(BaseModel):
    delegado: Delegado
    areas: list[Area]


class ReglasUrgencia(BaseModel):
    inmediata_horas: int
    alta_dias: int


class ReglasEnrutamiento(BaseModel):
    version: str
    urgencia: ReglasUrgencia
    organizaciones: dict[str, ReglasOrganizacion]


def cargar_reglas_enrutamiento(ruta: Path | None = None) -> ReglasEnrutamiento:
    """Lee las reglas. Los contactos pasan por la guardia: solo se aceptan datos ficticios."""
    datos = yaml.safe_load((ruta or RAIZ_CANAL / "enrutamiento.yaml").read_text("utf-8"))
    guardia.exigir_sintetico(datos)
    return ReglasEnrutamiento(**datos)


# --- coincidencia de palabras --------------------------------------------------------


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes ("Remuneración" → "remuneracion"; "ñ" → "n")."""
    descompuesto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def palabras_encontradas(texto: str, palabras: list[str]) -> list[str]:
    """Palabras de la lista que aparecen en el texto, desde el inicio de una palabra."""
    base = normalizar(texto)
    return [p for p in palabras if re.search(r"\b" + re.escape(normalizar(p)), base)]


def coincidencias(texto: str, palabras: list[str]) -> list[tuple[str, str]]:
    """Como `palabras_encontradas`, pero con la palabra completa tal como aparece (sin tildes):
    la regla "remuneracion" encontró "remuneraciones". Sirve para explicar el porqué."""
    base = normalizar(texto)
    salida = []
    for palabra in palabras:
        m = re.search(r"\b" + re.escape(normalizar(palabra)) + r"\w*", base)
        if m:
            salida.append((palabra, m.group(0)))
    return salida


# --- urgencia -------------------------------------------------------------------------


def _deberes(caso: Caso) -> list[Deber]:
    if caso.resultado_incidente is not None:
        r = caso.resultado_incidente
        return [r.aviso_agencia, r.aviso_titulares, r.reporte_anci, *r.plazos_anci]
    if caso.relojes_anci_posibles:
        return list(caso.relojes_anci_posibles)
    if caso.resultado_solicitud is not None:
        r = caso.resultado_solicitud
        return [d for d in (r.respuesta, r.bloqueo, r.comunicar_terceros) if d is not None]
    return []


def _como_momento(vence: datetime | date) -> datetime:
    """Una fecha sin hora vence al final de ese día, en hora de Chile."""
    if isinstance(vence, datetime):
        return vence
    return datetime.combine(vence, time(23, 59, 59), tzinfo=ZONA_CHILE)


def _urgencia(
    caso: Caso, ahora: datetime, reglas: ReglasUrgencia
) -> tuple[Urgencia, str, str | None, datetime | None]:
    enviados = set(caso.envios)
    if "anci_alerta_temprana" in enviados:
        enviados.add("reporte_anci")  # su plazo es el de la alerta temprana
    vigentes = [
        d for d in _deberes(caso) if d.decision in ("si", "revisar") and d.id not in enviados
    ]
    con_fecha = [(d, _como_momento(d.vence)) for d in vigentes if d.vence is not None]
    proximo, vence = min(con_fecha, key=lambda par: par[1]) if con_fecha else (None, None)
    nombre = NOMBRES_DEBER.get(proximo.id, proximo.id) if proximo else None

    if vence is not None and vence <= ahora:
        return "inmediata", f"El plazo de {nombre} ya venció.", proximo.id, vence
    if vence is not None and vence - ahora <= timedelta(hours=reglas.inmediata_horas):
        return (
            "inmediata",
            f"El plazo de {nombre} vence en menos de {reglas.inmediata_horas} horas.",
            proximo.id,
            vence,
        )
    agencia = next((d for d in vigentes if d.id == "aviso_agencia"), None)
    if agencia is not None:
        return (
            "alta",
            "Corresponde avisar a la Agencia, o hay que revisarlo, sin dilaciones indebidas.",
            proximo.id if proximo else None,
            vence,
        )
    if caso.tipo != "solicitud" and caso.resultado_incidente is None:
        return (
            "alta",
            "La IA no pudo leer el incidente: se trata como urgente hasta que el delegado lo vea.",
            proximo.id if proximo else None,
            vence,
        )
    if vence is not None and vence - ahora <= timedelta(days=reglas.alta_dias):
        return (
            "alta",
            f"El plazo de {nombre} vence en menos de {reglas.alta_dias} días.",
            proximo.id,
            vence,
        )
    if vence is not None:
        return "normal", f"El plazo más cercano es el de {nombre}.", proximo.id, vence
    return "normal", "No hay plazos legales corriendo para este caso.", None, None


# --- enrutamiento --------------------------------------------------------------------


def _es_ciberincidente(caso: Caso) -> bool:
    hechos = caso.hechos_vigentes  # los del delegado si corrigió, si no los de la IA
    if hechos is not None:
        return hechos.ciberincidente in ("si", "dudoso")
    # Si la IA no respondió y el motor mostró relojes posibles de la ANCI, se trata como posible.
    return bool(caso.relojes_anci_posibles)


def _destino_area(area: Area, caso: Caso) -> Destino | None:
    porques: list[str] = []
    motivos: list[str] = []
    pares = coincidencias(caso.texto, area.palabras)
    encontradas = [regla for regla, _ in pares]
    if encontradas:
        lista = ", ".join(f"«{visto}»" for _, visto in pares)
        porques.append(f"el mensaje menciona {lista}, datos que administra esta área")
        motivos += [f"palabra:{p}" for p in encontradas]
    if caso.tipo in area.recibe:
        porques.append("atiende este tipo de reporte")
        motivos.append(f"tipo:{caso.tipo}")
    if "ciberincidente" in area.recibe and caso.tipo != "solicitud" and _es_ciberincidente(caso):
        porques.append("puede ser un ciberincidente (sistemas o redes)")
        motivos.append("tipo:ciberincidente")
    if not porques:
        return None
    porque = "; ".join(porques)
    return Destino(
        rol="area",
        id=area.id,
        nombre=area.nombre,
        contacto=area.contacto,
        porque=porque[0].upper() + porque[1:] + ".",
        motivos=motivos,
    )


def enrutar(caso: Caso, reglas: ReglasEnrutamiento, ahora: datetime) -> Asignacion:
    org = reglas.organizaciones.get(caso.id_organizacion)
    if org is None:
        raise KeyError(f"Sin reglas de enrutamiento para {caso.id_organizacion}")
    areas = [d for a in org.areas if (d := _destino_area(a, caso)) is not None]

    if caso.reservado:
        porque_delegado = (
            "Recibe todos los casos. Este es reservado: solo lo ve el delegado, que decide si lo "
            "deriva a un área."
        )
        destinos, sugeridas = [], areas
    else:
        porque_delegado = "Recibe todos los casos y valida cada decisión."
        if not areas:
            porque_delegado += " Ninguna área coincide: el delegado decide a quién derivarlo."
        destinos, sugeridas = areas, []
    delegado = Destino(
        rol="delegado",
        id="delegado",
        nombre=org.delegado.cargo,
        contacto=org.delegado.contacto,
        porque=porque_delegado,
        motivos=["siempre"] + (["reservado"] if caso.reservado else []),
    )
    urgencia, porque_urgencia, proximo, vence = _urgencia(caso, ahora, reglas.urgencia)
    return Asignacion(
        version_reglas=reglas.version,
        destinos=[delegado, *destinos],
        sugeridas=sugeridas,
        urgencia=urgencia,
        porque_urgencia=porque_urgencia,
        proximo_plazo=proximo,
        vence=vence,
    )
