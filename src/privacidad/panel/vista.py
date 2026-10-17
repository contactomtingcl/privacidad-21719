"""Traduce un caso a lo que muestra el panel, en lenguaje simple.

Aquí no se decide nada: solo se presentan las decisiones del motor y del delegado. Los textos
legales salen de las citas del motor (verificadas contra el corpus), nunca de la IA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from ..canal.delegado import deberes_del_caso, decision_final, por_resolver
from ..canal.evidencia import Anotacion
from ..canal.modelos import ZONA_CHILE, Caso
from ..deteccion import Enmascarador
from ..interpretacion.incidentes import afirmados_incidente
from ..interpretacion.respaldo import Respaldo
from ..motor import Deber
from ..reportes import (
    DESTINOS,
    NOMBRE_DESTINO,
    Borrador,
    Revision,
    SinBorrador,
    ultima_revision,
)

ORDEN_URGENCIA = {"inmediata": 0, "alta": 1, "normal": 2}
ETIQUETA_URGENCIA = {"inmediata": "Inmediata", "alta": "Alta", "normal": "Normal"}
TIPOS = {
    "solicitud": "Solicitud de una persona",
    "incidente": "Incidente",
    "aviso_proveedor": "Aviso de proveedor",
}
TITULOS_DEBER = {
    "aviso_agencia": "Avisar a la Agencia de Protección de Datos",
    "aviso_titulares": "Avisar a cada persona afectada",
    "reporte_anci": "Avisar al equipo nacional de ciberseguridad (ANCI)",
    "anci_alerta_temprana": "Primer aviso a la ANCI",
    "anci_actualizacion": "Actualización a la ANCI",
    "anci_informe_final": "Informe final a la ANCI",
    "respuesta_solicitud": "Responder a la persona",
    "bloqueo_temporal": "Bloquear sus datos mientras se resuelve",
    "comunicar_a_terceros": "Avisar a quienes recibieron sus datos",
}
DECISION = {"si": "Sí", "no": "No", "revisar": "Revisar"}
VULNERACIONES = {
    "filtracion": "Se filtraron datos",
    "perdida": "Se perdieron datos",
    "alteracion": "Se alteraron datos",
    "destruccion": "Se destruyeron datos",
    "acceso_no_autorizado": "Alguien entró sin permiso",
    "comunicacion_no_autorizada": "Se enviaron datos a quien no debía",
    "ninguna": "No hubo vulneración",
}
CATEGORIAS = {
    "sensibles": "Datos sensibles (por ejemplo, de salud)",
    "menores_14": "De niños o niñas menores de 14 años",
    "financieros": "Financieros o comerciales",
}
CIBER = {"si": "Sí", "no": "No", "dudoso": "No se sabe"}
MOTIVOS_CORRECCION = {
    "error_ia": "La IA leyó mal el mensaje",
    "informacion_nueva": "Llegó información nueva",
    "confirmado_por_area": "El área responsable lo confirmó",
    "otro": "Otro motivo",
}
MOTIVOS_DECISION = {
    "datos_revisados": "Revisé qué datos había",
    "consulta_area": "Lo consulté con el área",
    "criterio_delegado": "Criterio del delegado",
    "otro": "Otro motivo",
}
MOTIVOS_IDENTIDAD = {
    "contactar_a_quien_reporto": "Necesito contactar a quien reportó",
    "requerimiento_de_autoridad": "Lo pide una autoridad",
    "otro": "Otro motivo",
}
ESTADOS = {
    "interpretado": "Por validar",
    "requiere_revision": "Requiere revisión",
    "pendiente_confirmacion": "Espera al titular",
    "sin_solicitud": "Por revisar",
}
EVENTOS = {
    "recibido": "Reporte recibido por el canal",
    "interpretado": "La IA propuso su lectura",
    "ia_sin_respuesta": "La IA no respondió: pasó a revisión",
    "confirmacion_solicitada": "Se pidió confirmación al titular",
    "confirmacion_respondida": "El titular respondió",
    "confirmacion_por_defecto": "Sin respuesta: se aplicó la lectura reversible",
    "enrutado": "Se decidió a quién enviarlo",
    "hechos_corregidos": "{por} corrigió hechos",
    "deber_resuelto": "{por} resolvió una duda",
    "validado": "{por} validó la decisión",
    "validacion_anulada": "La validación se anuló por un cambio",
    "identidad_abierta": "{por} abrió la identidad reservada",
    "editado_a_mano": "Editado a mano (alteración de la demo)",
    "borrador_revisado": "{por} revisó un borrador de reporte",
}


def momento(valor: datetime | date | None) -> datetime | None:
    """Una fecha sin hora vence al final de ese día, en hora de Chile."""
    if valor is None or isinstance(valor, datetime):
        return valor
    return datetime.combine(valor, time(23, 59, 59), tzinfo=ZONA_CHILE)


def hora(valor: datetime) -> str:
    return valor.astimezone(ZONA_CHILE).strftime("%H:%M")


def cuanto_falta(vence: datetime | None, ahora: datetime) -> str:
    if vence is None:
        return "Sin plazo fijo"
    resta = vence - ahora
    if resta <= timedelta(0):
        return "Vencido"
    horas, resto = divmod(int(resta.total_seconds()), 3600)
    if horas < 48:
        return f"{horas} h {resto // 60:02d} min"
    return f"{horas // 24} días"


@dataclass
class Fila:
    id: str
    urgencia: str
    etiqueta_urgencia: str
    tipo: str
    resumen: str
    destinos: str
    plazo: str
    vence: datetime | None
    estado: str
    clase_estado: str
    nueva: bool = False


def resumen_de(caso: Caso) -> str:
    if caso.resumen_ia:
        return caso.resumen_ia
    texto = " ".join(Enmascarador().enmascarar(caso.texto).split())
    return texto if len(texto) <= 90 else texto[:87].rstrip() + "…"


def estado_de(caso: Caso) -> tuple[str, str]:
    if caso.validacion is not None:
        return "Validado", "validado"
    if caso.tipo != "solicitud" and caso.hechos_vigentes is None:
        return "Requiere revisión", "revision"
    etiqueta = ESTADOS.get(caso.estado, "Por revisar")
    return etiqueta, {"Por validar": "validar", "Requiere revisión": "revision"}.get(
        etiqueta, "espera"
    )


def fila(caso: Caso, ahora: datetime, desde: datetime | None = None) -> Fila:
    a = caso.asignacion
    urgencia = a.urgencia if a else "normal"
    vence = a.vence if a else None
    plazo = "Sin plazo fijo"
    if a and a.proximo_plazo:
        nombre = TITULOS_DEBER.get(a.proximo_plazo, a.proximo_plazo)
        plazo = f"{nombre}: {cuanto_falta(vence, ahora)}"
    elif a and a.urgencia == "alta" and caso.tipo != "solicitud":
        plazo = "Agencia: lo antes posible"
    estado, clase = estado_de(caso)
    destinos = ", ".join(d.nombre for d in a.destinos) if a else "Delegado"
    if a and caso.reservado:
        destinos += " (reservado)"
    return Fila(
        id=caso.id,
        urgencia=urgencia,
        etiqueta_urgencia=ETIQUETA_URGENCIA[urgencia],
        tipo=TIPOS[caso.tipo] + (" reservado" if caso.reservado else ""),
        resumen=resumen_de(caso),
        destinos=destinos,
        plazo=plazo,
        vence=vence,
        estado=estado,
        clase_estado=clase,
        nueva=bool(desde and caso.ingreso > desde),
    )


def ordenar(casos: list[Caso]) -> list[Caso]:
    def llave(c: Caso) -> tuple:
        a = c.asignacion
        lejos = datetime.max.replace(tzinfo=ZONA_CHILE)
        return (
            ORDEN_URGENCIA[a.urgencia if a else "normal"],
            (a.vence if a and a.vence else lejos),
            c.ingreso,
        )

    return sorted(casos, key=llave)


@dataclass
class Resumen:
    abiertos: int
    plazos: int  # casos abiertos con una fecha límite legal (corriendo o ya vencida)
    plazos_vencidos: int
    plazos_cercanos: int  # vencen dentro de 3 horas; no incluye los ya vencidos
    por_validar: int  # la IA propuso y el delegado aún no valida
    revision: int  # la IA no pudo leerlos: el delegado los lee y valida igual
    validados: int
    validados_hoy: int

    @property
    def para_validar(self) -> int:
        """Todo lo que espera la validación del delegado, haya o no lectura de la IA."""
        return self.por_validar + self.revision


def resumen_bandeja(casos: list[Caso], ahora: datetime) -> Resumen:
    abiertos = [c for c in casos if c.validacion is None]
    con_plazo = [c for c in abiertos if c.asignacion and c.asignacion.vence]
    vencidos = [c for c in con_plazo if c.asignacion.vence <= ahora]
    hoy = ahora.astimezone(ZONA_CHILE).date()
    validados = [c for c in casos if c.validacion is not None]
    return Resumen(
        abiertos=len(abiertos),
        plazos=len(con_plazo),
        plazos_vencidos=len(vencidos),
        plazos_cercanos=sum(
            1 for c in con_plazo if timedelta(0) < c.asignacion.vence - ahora <= timedelta(hours=3)
        ),
        por_validar=sum(1 for c in abiertos if estado_de(c)[1] == "validar"),
        revision=sum(1 for c in abiertos if estado_de(c)[1] == "revision"),
        validados=len(validados),
        validados_hoy=sum(
            1 for c in validados if c.validacion.momento.astimezone(ZONA_CHILE).date() == hoy
        ),
    )


# --- ficha del caso -----------------------------------------------------------------


@dataclass
class VistaDeber:
    id: str
    titulo: str
    decision: str  # la que vale: del motor, o del delegado si el motor dudó
    etiqueta: str
    de_quien: str
    porque: str
    plazo: str | None
    vence: datetime | None
    citas: list[dict[str, str]]
    pendiente: bool


def vista_deberes(caso: Caso) -> list[VistaDeber]:
    pendientes = {d.id for d in por_resolver(caso)}
    salida = []
    for d in deberes_del_caso(caso):
        final = decision_final(caso, d)
        humano = d.decision == "revisar" and d.id in caso.decisiones
        porque = d.porque
        if humano:
            porque = (
                f"El motor dejó la duda y decidiste «{DECISION[final]}» "
                f"({MOTIVOS_DECISION[caso.decisiones[d.id].motivo].lower()})."
            )
        salida.append(
            VistaDeber(
                id=d.id,
                titulo=TITULOS_DEBER.get(d.id, d.id),
                decision=final,
                etiqueta=DECISION[final],
                de_quien="decidido por ti" if humano else "decidido por el motor",
                porque=porque,
                plazo=d.plazo,
                vence=momento(d.vence),
                citas=[c.model_dump() for c in d.citas],
                pendiente=d.id in pendientes,
            )
        )
    return salida


TITULO_RELOJ_ANCI = "Primer aviso a la ANCI"


@dataclass
class Reloj:
    titulo: str
    detalle: str
    vence: datetime | None
    total_s: int  # duración total del plazo, para el anillo
    tono: str  # "rojo" | "ambar" | "neutro"


def relojes(caso: Caso, ahora: datetime) -> list[Reloj]:
    salida: list[Reloj] = []
    r = caso.resultado_incidente
    if r is not None:
        anci = [p for p in r.plazos_anci if r.reporte_anci.decision in ("si", "revisar")]
        if anci and decision_final(caso, r.reporte_anci) != "no":
            primero = anci[0]
            vence = momento(primero.vence)
            salida.append(
                Reloj(
                    titulo=TITULO_RELOJ_ANCI,
                    detalle="Después: actualización a las 72 horas e informe final a los 15 días.",
                    vence=vence,
                    total_s=int((vence - caso.ingreso).total_seconds()) if vence else 0,
                    tono="rojo",
                )
            )
        if decision_final(caso, r.aviso_agencia) != "no":
            minutos = max(0, int((ahora - caso.ingreso).total_seconds() // 60))
            salida.append(
                Reloj(
                    titulo="Avisar a la Agencia lo antes posible",
                    detalle=f"La ley no fija horas. Corre desde las {hora(caso.ingreso)}, "
                    f"cuando se supo: lleva {minutos} minutos.",
                    vence=None,
                    total_s=0,
                    tono="ambar",
                )
            )
    elif caso.relojes_anci_posibles:
        primero = caso.relojes_anci_posibles[0]
        vence = momento(primero.vence)
        salida.append(
            Reloj(
                titulo="Posible aviso a la ANCI",
                detalle="La IA no leyó el reporte: así correría si fuera un ciberincidente.",
                vence=vence,
                total_s=int((vence - caso.ingreso).total_seconds()) if vence else 0,
                tono="rojo",
            )
        )
    elif caso.resultado_solicitud is not None:
        for d in (caso.resultado_solicitud.bloqueo, caso.resultado_solicitud.respuesta):
            if d is not None and d.vence is not None and d.decision != "no":
                vence = momento(d.vence)
                salida.append(
                    Reloj(
                        titulo=TITULOS_DEBER.get(d.id, d.id),
                        detalle=d.plazo or "",
                        vence=vence,
                        total_s=int((vence - caso.ingreso).total_seconds()),
                        tono="rojo" if d.id == "bloqueo_temporal" else "ambar",
                    )
                )
    return salida


@dataclass
class SiguientePaso:
    """Qué hacer cuando el plazo más cercano ya venció. No decide nada: el deber no cambia."""

    texto: str
    borradores: list[tuple[str, str]]  # (destino, texto del botón)


def siguiente_paso(f: Ficha, destinos_con_borrador: list[str]) -> SiguientePaso:
    reloj = f.relojes[0]
    if reloj.titulo == TITULO_RELOJ_ANCI:
        texto = (
            "Venció el plazo del primer aviso a la ANCI, pero el deber sigue: envíalo cuanto "
            "antes por el canal oficial."
        )
    elif f.caso.tipo == "solicitud":
        texto = (
            f"Venció el plazo para «{reloj.titulo.lower()}», pero el deber sigue: "
            "respóndele a la persona cuanto antes."
        )
    else:
        texto = (
            "Venció el plazo que correría si fuera un ciberincidente: lee el reporte y "
            "completa los hechos cuanto antes."
        )
    corto = {"anci": "la ANCI", "agencia": "la Agencia"}
    botones = [(d, f"Abrir borrador para {corto[d]}") for d in destinos_con_borrador]
    return SiguientePaso(texto, botones)


@dataclass
class VistaHecho:
    campo: str
    etiqueta: str
    valor: str
    origen: str  # "propuesto por la IA" | "corregido por ti" | "completado por ti"
    respaldo: Respaldo | None = None  # solo si el valor sigue siendo el que propuso la IA
    sin_respaldo: bool = False  # la IA lo afirmó sin citar una frase del mensaje


def _valor(campo: str, v: Any) -> str:
    if campo == "vulneracion":
        return VULNERACIONES.get(v, str(v))
    if campo == "categorias_especiales":
        return ", ".join(CATEGORIAS.get(c, c) for c in v) or "Ninguno"
    if campo == "ciberincidente":
        return CIBER.get(v, str(v))
    if campo == "titulares_aprox":
        return "No se sabe" if v is None else str(v)
    return "Sí" if v else "No"


ETIQUETAS_HECHO = {
    "vulneracion": "Qué pasó",
    "datos_personales": "¿Hay datos de personas?",
    "categorias_especiales": "Datos especialmente protegidos",
    "ciberincidente": "¿Afectó sistemas informáticos?",
    "riesgo_mitigado": "¿Hay razón para pensar que nadie los vio?",
    "interrupcion_servicio": "¿Se interrumpió un servicio?",
    "titulares_aprox": "Personas afectadas (aprox.)",
}


def vista_hechos(caso: Caso) -> list[VistaHecho]:
    vigentes = caso.hechos_vigentes
    if vigentes is None:
        return []
    ia = caso.hechos_incidente.model_dump() if caso.hechos_incidente else {}
    datos = vigentes.model_dump()
    afirmados = afirmados_incidente(vigentes)
    # Solo se pide frase a la IA desde el 12 de octubre: un caso leído antes no se marca.
    con_frases = any(e.tipo == "interpretado" and "respaldos" in e.detalle for e in caso.eventos)
    salida = []
    for campo, etiqueta in ETIQUETAS_HECHO.items():
        if not ia:
            origen = "completado por ti"
        elif ia.get(campo) != datos[campo]:
            origen = "corregido por ti"
        else:
            origen = "propuesto por la IA"
        de_la_ia = origen == "propuesto por la IA"
        respaldo = caso.respaldos_ia.get(campo) if de_la_ia else None
        sin_respaldo = con_frases and de_la_ia and respaldo is None and campo in afirmados
        salida.append(
            VistaHecho(campo, etiqueta, _valor(campo, datos[campo]), origen, respaldo, sin_respaldo)
        )
    return salida


@dataclass
class Paso:
    titulo: str
    texto: str
    listo: bool


def pasos(caso: Caso) -> list[Paso]:
    tipos = {e.tipo: e for e in reversed(caso.eventos)}
    ia = tipos.get("interpretado")
    n_si = sum(1 for d in deberes_del_caso(caso) if decision_final(caso, d) == "si")
    return [
        Paso("Llegó por el canal", f"{hora(caso.ingreso)} · enlace o código QR", True),
        Paso(
            "La IA propone",
            f"Leyó el texto con los datos tapados ({hora(ia.momento)})" if ia else "No respondió",
            ia is not None or caso.hechos_delegado is not None,
        ),
        Paso("El motor decide", f"{n_si} deber{'es' if n_si != 1 else ''} con su artículo", True),
        Paso(
            "Tú validas",
            f"Validado a las {hora(caso.validacion.momento)}" if caso.validacion else "Pendiente",
            caso.validacion is not None,
        ),
    ]


@dataclass
class Hito:
    texto: str
    hora: str
    huella: str
    tipo: str


def linea_de_tiempo(caso: Caso, anotaciones: list[Anotacion]) -> list[Hito]:
    salida = []
    for i, e in enumerate(caso.eventos):
        texto = EVENTOS.get(e.tipo, e.tipo).format(por=e.detalle.get("por", "El delegado"))
        if e.tipo == "enrutado":
            n = len(e.detalle.get("destinos", []))
            texto = f"Enviado a {n} destino{'s' if n != 1 else ''}"
        huella = anotaciones[i].huella if i < len(anotaciones) else ""
        salida.append(
            Hito(texto, e.momento.astimezone(ZONA_CHILE).strftime("%H:%M:%S"), huella, e.tipo)
        )
    return salida


@dataclass
class Ficha:
    caso: Caso
    fila: Fila
    texto_enmascarado: str
    hechos: list[VistaHecho]
    deberes: list[VistaDeber]
    relojes: list[Reloj]
    pasos: list[Paso]
    linea: list[Hito]
    pendientes: int
    puede_corregir: bool
    valores: dict[str, Any] = field(default_factory=dict)  # para el formulario de corrección


def ficha(caso: Caso, anotaciones: list[Anotacion], ahora: datetime) -> Ficha:
    vigentes = caso.hechos_vigentes
    valores = (
        vigentes.model_dump(mode="json")
        if vigentes
        else {
            "datos_personales": True,
            "vulneracion": "filtracion",
            "categorias_especiales": [],
            "riesgo_mitigado": False,
            "ciberincidente": "dudoso",
            "interrupcion_servicio": False,
            "titulares_aprox": None,
        }
    )
    return Ficha(
        caso=caso,
        fila=fila(caso, ahora),
        texto_enmascarado=Enmascarador().enmascarar(caso.texto),
        hechos=vista_hechos(caso),
        deberes=vista_deberes(caso),
        relojes=relojes(caso, ahora),
        pasos=pasos(caso),
        linea=linea_de_tiempo(caso, anotaciones),
        pendientes=len(por_resolver(caso)),
        puede_corregir=caso.tipo != "solicitud",
        valores=valores,
    )


def deber_por_id(caso: Caso, id_deber: str) -> Deber | None:
    return next((d for d in deberes_del_caso(caso) if d.id == id_deber), None)


# --- borradores de reporte ----------------------------------------------------------------


@dataclass
class VistaBorrador:
    destino: str
    nombre: str
    borrador: Borrador | None
    motivo: str | None  # por qué no hay borrador
    revision: Revision | None

    @property
    def estado(self) -> str:
        if self.borrador is None:
            return "No corresponde"
        if self.revision and self.revision.vigente:
            return f"Revisado por {self.revision.por} a las {hora(self.revision.momento)}"
        if self.revision:
            return "Cambió después de tu revisión: revísalo de nuevo"
        n = len(self.borrador.por_completar)
        return f"Listo para revisar · {n} campo{'s' if n != 1 else ''} por completar"


def vista_borradores(caso: Caso, borradores: dict) -> list[VistaBorrador]:
    salida = []
    for destino in DESTINOS:
        b = borradores.get(destino)
        if isinstance(b, Borrador):
            salida.append(
                VistaBorrador(destino, NOMBRE_DESTINO[destino], b, None, ultima_revision(caso, b))
            )
        else:
            motivo = b.motivo if isinstance(b, SinBorrador) else "No hay borrador."
            salida.append(VistaBorrador(destino, NOMBRE_DESTINO[destino], None, motivo, None))
    return salida
