"""Motor de reglas: decide deberes y plazos legales a partir de hechos.

Los hechos los puede proponer la IA (interpretando un reporte) o una persona; el
motor nunca llama a la IA. Cada decisión trae su porqué en lenguaje llano y la
cita del artículo, con el fragmento verificado contra el corpus.

Tres valores posibles por deber:

- "si": la regla se cumple con los hechos entregados.
- "no": la regla no aplica.
- "revisar": los hechos dejan una duda que la ley obliga a ponderar (por ejemplo,
  si existe "riesgo razonable"). El motor no la resuelve: la marca para el delegado.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

RAIZ_REGLAS = Path(__file__).resolve().parents[3] / "data" / "reglas"

Decision = Literal["si", "no", "revisar"]
Vulneracion = Literal[
    "filtracion",
    "perdida",
    "alteracion",
    "destruccion",
    "acceso_no_autorizado",
    "comunicacion_no_autorizada",
    "ninguna",
]
CategoriaEspecial = Literal["sensibles", "menores_14", "financieros"]
Derecho = Literal["acceso", "rectificacion", "supresion", "oposicion", "portabilidad", "bloqueo"]
PerfilOrganizacion = Literal[
    "empresa_privada",
    "organismo_publico",
    "salud",
    "banca_financiero",
    "telecomunicaciones",
    "energia",
    "agua_saneamiento",
    "transporte",
    "combustibles",
    "infraestructura_digital",
    "servicios_ti_terceros",
    "seguridad_social",
    "postal",
]

NOMBRES_CATEGORIA = {
    "sensibles": "datos sensibles",
    "menores_14": "datos de niños o niñas menores de 14 años",
    "financieros": "datos financieros o comerciales",
}


# --- datos de entrada y salida --------------------------------------------


class HechosIncidente(BaseModel):
    """Lo que se sabe de un incidente. No contiene datos personales."""

    datos_personales: bool = Field(description="¿El incidente involucra datos personales?")
    vulneracion: Vulneracion
    categorias_especiales: list[CategoriaEspecial] = Field(default_factory=list)
    riesgo_mitigado: bool = Field(
        False,
        description="Hay una razón concreta para pensar que nadie pudo leer o usar los datos "
        "(cifrado fuerte, equipo recuperado sin abrir, borrado antes de cualquier acceso).",
    )
    ciberincidente: Literal["si", "no", "dudoso"] = Field(
        description="¿Afecta redes o sistemas informáticos (ataque, malware, acceso indebido)?"
    )
    interrupcion_servicio: bool = False
    titulares_aprox: int | None = None


class HechosSolicitud(BaseModel):
    es_solicitud: bool
    derechos: list[Derecho] = Field(default_factory=list)
    requiere_confirmacion: bool = False
    pregunta_confirmacion: str | None = None


class Cita(BaseModel):
    norma: str
    articulo: str
    fragmento: str


class Deber(BaseModel):
    id: str
    decision: Decision
    porque: str
    plazo: str | None = None
    vence: datetime | date | None = None
    a_confirmar: bool = False
    citas: list[Cita] = Field(default_factory=list)
    nota_vigencia: str | None = None


class ResultadoIncidente(BaseModel):
    aviso_agencia: Deber
    aviso_titulares: Deber
    reporte_anci: Deber
    plazos_anci: list[Deber] = Field(default_factory=list)


class ResultadoSolicitud(BaseModel):
    respuesta: Deber | None
    bloqueo: Deber | None = None
    comunicar_terceros: Deber | None = None


# --- reglas cargadas desde YAML -------------------------------------------


@lru_cache(maxsize=1)
def cargar_reglas(ruta: Path | None = None) -> dict:
    return yaml.safe_load((ruta or RAIZ_REGLAS / "reglas.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def cargar_feriados(ruta: Path | None = None) -> tuple[frozenset[date], bool]:
    datos = yaml.safe_load((ruta or RAIZ_REGLAS / "feriados.yaml").read_text(encoding="utf-8"))
    return frozenset(datos["feriados"]), bool(datos.get("verificado"))


def _regla(id_regla: str) -> dict:
    return cargar_reglas()["reglas"][id_regla]


def _cita(id_regla: str) -> Cita:
    f = _regla(id_regla)["fuente"]
    return Cita(norma=f["norma"], articulo=str(f["articulo"]), fragmento=f["fragmento"])


def _nota_vigencia(id_regla: str, referencia: date | None) -> str | None:
    ley = _regla(id_regla)["ley"]
    desde = cargar_reglas()["vigencias"][ley]["desde"]
    if referencia and desde and referencia < desde:
        return f"Exigible desde el {desde:%d-%m-%Y}; antes de esa fecha es una buena práctica."
    return None


def es_servicio_esencial(perfil: str) -> bool:
    return perfil in cargar_reglas()["servicios_esenciales"]["perfiles"]


def sumar_dias_habiles(inicio: date, dias: int) -> tuple[date, bool]:
    """Suma días hábiles (lunes a viernes no feriados). Devuelve la fecha y si el
    calendario de feriados está verificado."""
    feriados, verificado = cargar_feriados()
    actual, contados = inicio, 0
    while contados < dias:
        actual += timedelta(days=1)
        if actual.weekday() < 5 and actual not in feriados:
            contados += 1
    return actual, verificado


# --- incidentes -----------------------------------------------------------


def decidir_incidente(
    hechos: HechosIncidente,
    perfil: PerfilOrganizacion,
    conocimiento: datetime | None = None,
) -> ResultadoIncidente:
    """Aplica el art. 14 sexies (Agencia y titulares) y los arts. 4, 9 y 27 de la Ley 21.663."""
    referencia = conocimiento.date() if conocimiento else None
    cats = [NOMBRES_CATEGORIA[c] for c in hechos.categorias_especiales]

    # Aviso a la Agencia.
    if not hechos.datos_personales or hechos.vulneracion == "ninguna":
        agencia = Deber(
            id="aviso_agencia",
            decision="no",
            porque="No hay una vulneración que afecte datos personales.",
        )
    elif hechos.riesgo_mitigado:
        agencia = Deber(
            id="aviso_agencia",
            decision="revisar",
            porque="Hubo una vulneración, pero hay razones para pensar que los datos no "
            "quedaron expuestos. La ley exige avisar si hay riesgo razonable: el delegado "
            "debe decidirlo y dejar registro de por qué.",
        )
    else:
        agencia = Deber(
            id="aviso_agencia",
            decision="si",
            porque="Hubo una vulneración que afecta datos personales y no hay nada que "
            "descarte el riesgo para las personas.",
        )
    agencia.citas = [_cita("aviso_agencia")]
    agencia.plazo = _regla("aviso_agencia")["plazo"]["valor"]
    agencia.nota_vigencia = _nota_vigencia("aviso_agencia", referencia)

    # Aviso a cada titular.
    if agencia.decision == "no" or not cats:
        titulares = Deber(
            id="aviso_titulares",
            decision="no",
            porque="No corresponde avisar a la Agencia."
            if agencia.decision == "no"
            else "Los datos afectados no son sensibles, de menores de 14 ni financieros.",
        )
    else:
        titulares = Deber(
            id="aviso_titulares",
            decision=agencia.decision,
            porque=f"La vulneración afecta {', '.join(cats)}: hay que avisar a cada persona "
            "(a los menores, por medio de sus padres o representantes).",
        )
    titulares.citas = [_cita("aviso_titulares")]
    titulares.plazo = _regla("aviso_titulares")["plazo"]["valor"]
    titulares.nota_vigencia = _nota_vigencia("aviso_titulares", referencia)

    # Reporte a la ANCI.
    fuente_esenciales = cargar_reglas()["servicios_esenciales"]["fuente"]
    cita_esencial = Cita(
        norma=fuente_esenciales["norma"],
        articulo=str(fuente_esenciales["articulo"]),
        fragmento=fuente_esenciales["fragmento"],
    )
    significativo = hechos.datos_personales or hechos.interrupcion_servicio
    if not es_servicio_esencial(perfil):
        anci = Deber(
            id="reporte_anci",
            decision="no",
            porque="La organización no presta un servicio esencial según la Ley 21.663.",
        )
    elif hechos.ciberincidente == "no":
        anci = Deber(
            id="reporte_anci",
            decision="no",
            porque="No es un incidente de ciberseguridad (no afecta redes ni sistemas).",
        )
    elif hechos.ciberincidente == "dudoso" or not significativo:
        anci = Deber(
            id="reporte_anci",
            decision="revisar",
            porque="No está claro si es un incidente de ciberseguridad con efecto "
            "significativo. Ante la duda conviene enviar la alerta temprana: el plazo es "
            "de 3 horas.",
        )
    else:
        anci = Deber(
            id="reporte_anci",
            decision="si",
            porque="Servicio esencial con un incidente de ciberseguridad que afecta sistemas "
            "con datos personales o interrumpe el servicio. El reporte no debe incluir "
            "datos personales.",
        )
    anci.citas = [cita_esencial, _cita("anci_efecto_significativo"), _cita("anci_alerta_temprana")]

    plazos: list[Deber] = []
    if anci.decision != "no":
        anci.plazo = "3 horas desde que se supo"
        if conocimiento:
            alerta = conocimiento + timedelta(
                hours=_regla("anci_alerta_temprana")["plazo"]["valor"]
            )
            anci.vence = alerta
            for id_regla in ("anci_alerta_temprana", "anci_actualizacion", "anci_informe_final"):
                p = _regla(id_regla)["plazo"]
                if p["tipo"] == "horas":
                    vence: datetime = conocimiento + timedelta(hours=p["valor"])
                else:  # días corridos desde la alerta temprana (se usa su vencimiento máximo)
                    vence = alerta + timedelta(days=p["valor"])
                plazos.append(
                    Deber(
                        id=id_regla,
                        decision=anci.decision,
                        porque=_regla(id_regla)["descripcion"],
                        vence=vence,
                        citas=[_cita(id_regla)],
                    )
                )
    return ResultadoIncidente(
        aviso_agencia=agencia, aviso_titulares=titulares, reporte_anci=anci, plazos_anci=plazos
    )


# --- solicitudes de titulares ---------------------------------------------


def decidir_solicitud(hechos: HechosSolicitud, ingreso: date) -> ResultadoSolicitud:
    """Calcula plazos del art. 11. La confirmación con el titular no detiene el reloj."""
    if not hechos.es_solicitud:
        return ResultadoSolicitud(respuesta=None)
    p = _regla("respuesta_solicitud")["plazo"]
    respuesta = Deber(
        id="respuesta_solicitud",
        decision="si",
        porque="Toda solicitud del titular debe tener acuse de recibo y respuesta por escrito. "
        "El plazo corre desde el ingreso, aunque se esté confirmando con la persona qué pidió.",
        plazo=f"{p['valor']} días corridos (prorrogable una vez por {p['prorroga_dias_corridos']})",
        vence=ingreso + timedelta(days=p["valor"]),
        citas=[_cita("respuesta_solicitud")],
        nota_vigencia=_nota_vigencia("respuesta_solicitud", ingreso),
    )
    bloqueo = None
    if "bloqueo" in hechos.derechos:
        dias = _regla("bloqueo_temporal")["plazo"]["valor"]
        vence, verificado = sumar_dias_habiles(ingreso, dias)
        bloqueo = Deber(
            id="bloqueo_temporal",
            decision="si",
            porque="Pidió suspender el uso de sus datos mientras se resuelve. Hasta responder, "
            "esos datos no se pueden usar.",
            plazo=f"{dias} días hábiles",
            vence=vence,
            a_confirmar=not verificado,
            citas=[_cita("bloqueo_temporal")],
            nota_vigencia=_nota_vigencia("bloqueo_temporal", ingreso),
        )
    terceros = None
    if {"rectificacion", "supresion", "oposicion"} & set(hechos.derechos):
        terceros = Deber(
            id="comunicar_a_terceros",
            decision="si",
            porque="Si estos datos se entregaron a proveedores u otros, hay que avisarles el "
            "cambio. El inventario muestra a quién se entregaron.",
            citas=[_cita("comunicar_a_terceros")],
        )
    return ResultadoSolicitud(respuesta=respuesta, bloqueo=bloqueo, comunicar_terceros=terceros)
