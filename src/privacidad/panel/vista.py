"""Traduce un caso a lo que muestra el panel, en lenguaje simple.

Aquí no se decide nada: solo se presentan las decisiones del motor y del delegado. Los textos
legales salen de las citas del motor (verificadas contra el corpus), nunca de la IA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from babel.dates import format_date

from ..canal.delegado import (
    caso_abierto,
    deberes_del_caso,
    decision_final,
    entregas_del_caso,
    pendientes_de_envio,
    por_resolver,
)
from ..canal.evidencia import Anotacion
from ..canal.modelos import ZONA_CHILE, Caso, Envio
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
    "anci_plan_accion": "Plan de acción a la ANCI",
    "respuesta_solicitud": "Responder a la persona",
    "bloqueo_temporal": "Bloquear sus datos mientras se resuelve",
    "comunicar_a_terceros": "Avisar a quienes recibieron sus datos",
}
DECISION = {"si": "Corresponde", "no": "No corresponde", "revisar": "Decide tú"}
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
CANALES_ENVIO = {
    "correo": "Correo electrónico",
    "portal_oficial": "Portal o formulario oficial",
    "carta": "Carta",
    "en_persona": "En persona",
    "sistemas_internos": "En nuestros sistemas",
    "otro": "Otro",
}
MOTIVOS_CORRECCION = {
    "error_ia": "La IA leyó mal el mensaje",
    "informacion_nueva": "Llegó información nueva",
    "confirmado_por_area": "El área responsable lo confirmó",
    "otro": "Otro motivo",
}
MOTIVO_SIN_LECTURA = "La IA no pudo leerlo"
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
SIN_LECTURA = "Sin lectura de la IA"
ESTADOS = {
    "interpretado": "Por validar",
    "requiere_revision": SIN_LECTURA,
    "pendiente_confirmacion": "Espera a la persona",
    "sin_solicitud": "Por leer",
}
EVENTOS = {
    "recibido": "Reporte recibido por el canal",
    "interpretado": "La IA propuso su lectura",
    "ia_sin_respuesta": "La IA no respondió: quedó sin lectura",
    "confirmacion_solicitada": "Se pidió confirmación a la persona",
    "confirmacion_respondida": "La persona respondió",
    "confirmacion_por_defecto": "Sin respuesta: se aplicó la lectura reversible",
    "enrutado": "Se decidió a quién enviarlo",
    "hechos_corregidos": "{por} corrigió hechos",
    "deber_resuelto": "{por} resolvió una duda",
    "validado": "{por} validó la decisión",
    "validacion_anulada": "La validación se anuló por un cambio",
    "identidad_abierta": "{por} abrió la identidad reservada",
    "editado_a_mano": "Editado a mano (alteración de la demo)",
    "borrador_revisado": "{por} revisó un borrador de reporte",
    "envio_registrado": "{por} registró un envío",
    "aviso": "Aviso a un destino",
    "cascada": "Llegó por la red de cascada desde un proveedor",
    "derivado": "{por} derivó el caso a un área",
}
ESTADOS_AVISO = {
    "enviado": "aviso enviado por correo",
    "simulado": "aviso en la bandeja de salida de la demo (no sale correo)",
    "fallido": "el aviso falló",
}
MOTIVOS_DERIVACION = {
    "datos_del_area": "Son datos que administra esa área",
    "debe_actuar": "Esa área tiene que hacer algo",
    "consulta": "Necesito consultarle",
    "otro": "Otro motivo",
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
        if pendientes_de_envio(caso):
            return "Falta enviar", "enviar"
        return "Validado", "validado"
    if caso.tipo != "solicitud" and caso.hechos_vigentes is None:
        return SIN_LECTURA, "revision"
    etiqueta = ESTADOS.get(caso.estado, "Por leer")
    return etiqueta, {"Por validar": "validar", SIN_LECTURA: "revision"}.get(etiqueta, "espera")


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
    por_enviar: int = 0  # validados con algo que corresponde y aún no se envía

    @property
    def para_validar(self) -> int:
        """Todo lo que espera la validación del delegado, haya o no lectura de la IA."""
        return self.por_validar + self.revision


def resumen_bandeja(casos: list[Caso], ahora: datetime) -> Resumen:
    abiertos = [c for c in casos if caso_abierto(c)]
    sin_validar = [c for c in casos if c.validacion is None]
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
        por_validar=sum(1 for c in sin_validar if estado_de(c)[1] == "validar"),
        revision=sum(1 for c in sin_validar if estado_de(c)[1] == "revision"),
        validados=len(validados),
        validados_hoy=sum(
            1 for c in validados if c.validacion.momento.astimezone(ZONA_CHILE).date() == hoy
        ),
        por_enviar=sum(1 for c in validados if pendientes_de_envio(c)),
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
                f"El motor no pudo decidirlo y decidiste «{DECISION[final]}» "
                f"({MOTIVOS_DECISION[caso.decisiones[d.id].motivo].lower()})."
            )
        pendiente = d.id in pendientes
        if pendiente:
            de_quien = "El motor no puede decidirlo con estos hechos: decide tú."
        else:
            de_quien = "decidido por ti" if humano else "decidido por el motor"
        salida.append(
            VistaDeber(
                id=d.id,
                titulo=TITULOS_DEBER.get(d.id, d.id),
                decision=final,
                etiqueta=DECISION[final],
                de_quien=de_quien,
                porque=porque,
                plazo=aclarar_habiles(d.plazo),
                vence=momento(d.vence),
                citas=[c.model_dump() for c in d.citas],
                pendiente=pendiente,
            )
        )
    return salida


HABILES = "días hábiles"
ACLARACION_HABILES = "días hábiles (no cuentan fines de semana ni feriados)"


def aclarar_habiles(texto: str | None) -> str | None:
    """Que «2 días hábiles» no parezca contradecir un anillo que cuenta días de calendario."""
    if not texto or ACLARACION_HABILES in texto:
        return texto
    return texto.replace(HABILES, ACLARACION_HABILES, 1)


TITULO_RELOJ_ANCI = "Primer aviso a la ANCI"


def despues_alerta(pasos: list[Deber]) -> str:
    """«Después: …» con los plazos que de verdad corren (24 o 72 horas; plan de acción)."""
    ids = {p.id: p for p in pasos}
    actualizacion = ids.get("anci_actualizacion")
    horas = 72
    if actualizacion and actualizacion.citas and "veinticuatro" in actualizacion.citas[0].fragmento:
        horas = 24
    texto = f"Después: actualización a las {horas} horas e informe final a los 15 días"
    if "anci_plan_accion" in ids:
        texto += "; además, el plan de acción (máximo 7 días)"
    return texto + "."


@dataclass
class Reloj:
    titulo: str
    detalle: str
    vence: datetime | None
    total_s: int  # duración total del plazo, para el anillo
    tono: str  # "rojo" | "ambar" | "neutro" | "hecho"
    deber: str | None = None


def fecha_hora(valor: datetime) -> str:
    local = valor.astimezone(ZONA_CHILE)
    return f"el {format_date(local, format='long', locale='es_CL')} a las {hora(local)}"


def texto_envio(envio: Envio) -> str:
    return f"Enviado {fecha_hora(envio.momento)} · {CANALES_ENVIO[envio.canal].lower()}"


def _reloj_enviado(titulo: str, envio: Envio) -> Reloj:
    return Reloj(titulo, texto_envio(envio) + ".", None, 0, "hecho", envio.deber)


def relojes(caso: Caso, ahora: datetime) -> list[Reloj]:
    """Los plazos del caso. Lo ya enviado queda al final, con la hora en que se envió."""
    salida: list[Reloj] = []
    r = caso.resultado_incidente
    if r is not None:
        anci = [p for p in r.plazos_anci if r.reporte_anci.decision in ("si", "revisar")]
        if anci and decision_final(caso, r.reporte_anci) != "no":
            pendientes = [p for p in anci if p.id not in caso.envios]
            if pendientes:
                siguiente = pendientes[0]
                vence = momento(siguiente.vence)
                es_primero = siguiente.id == "anci_alerta_temprana"
                salida.append(
                    Reloj(
                        titulo=TITULO_RELOJ_ANCI
                        if es_primero
                        else TITULOS_DEBER.get(siguiente.id, siguiente.id),
                        detalle=despues_alerta(anci)
                        if es_primero
                        else f"Van {len(anci) - len(pendientes)} de {len(anci)} pasos enviados.",
                        vence=vence,
                        total_s=int((vence - caso.ingreso).total_seconds()) if vence else 0,
                        tono="rojo",
                        deber=siguiente.id,
                    )
                )
            else:
                ultimo = caso.envios[anci[-1].id]
                salida.append(_reloj_enviado("Los tres reportes a la ANCI", ultimo))
        if "aviso_agencia" in caso.envios:
            salida.append(_reloj_enviado("Aviso a la Agencia", caso.envios["aviso_agencia"]))
        elif decision_final(caso, r.aviso_agencia) != "no":
            minutos = max(0, int((ahora - caso.ingreso).total_seconds() // 60))
            salida.append(
                Reloj(
                    titulo="Avisar a la Agencia lo antes posible",
                    detalle=f"La ley no fija horas. Corre desde las {hora(caso.ingreso)}, "
                    f"cuando se supo: lleva {minutos} minutos.",
                    vence=None,
                    total_s=0,
                    tono="ambar",
                    deber="aviso_agencia",
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
            if d is not None and d.id in caso.envios:
                salida.append(_reloj_enviado(TITULOS_DEBER.get(d.id, d.id), caso.envios[d.id]))
            elif d is not None and d.vence is not None and d.decision != "no":
                vence = momento(d.vence)
                salida.append(
                    Reloj(
                        titulo=TITULOS_DEBER.get(d.id, d.id),
                        detalle=aclarar_habiles(d.plazo) or "",
                        vence=vence,
                        total_s=int((vence - caso.ingreso).total_seconds()),
                        tono="rojo" if d.id == "bloqueo_temporal" else "ambar",
                        deber=d.id,
                    )
                )
    return sorted(salida, key=lambda r: r.tono == "hecho")


@dataclass
class SiguientePaso:
    """Qué hacer cuando el plazo más cercano ya venció. No decide nada: el deber no cambia."""

    texto: str
    borradores: list[tuple[str, str]]  # (destino, texto del botón)


def siguiente_paso(f: Ficha, destinos_con_borrador: list[str]) -> SiguientePaso:
    reloj = f.relojes[0]
    if reloj.deber and reloj.deber.startswith("anci_"):
        texto = (
            f"Venció el plazo de «{reloj.titulo.lower()}», pero el deber sigue: envíalo cuanto "
            "antes por el canal oficial y marca «Ya lo envié»."
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
    "riesgo_mitigado": "¿Se puede descartar que alguien viera los datos?",
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
        elif caso.cascada is not None:
            origen = "del reporte del proveedor y tu relación con él"
        else:
            origen = "propuesto por la IA"
        de_la_ia = origen == "propuesto por la IA"
        respaldo = caso.respaldos_ia.get(campo) if de_la_ia else None
        sin_respaldo = con_frases and de_la_ia and respaldo is None and campo in afirmados
        salida.append(
            VistaHecho(campo, etiqueta, _valor(campo, datos[campo]), origen, respaldo, sin_respaldo)
        )
    return salida


def conteo_deberes(caso: Caso) -> str:
    """«1 corresponde, 1 por decidir»: cuenta lo que vale ahora, sea del motor o tuyo."""
    finales = [decision_final(caso, d) for d in deberes_del_caso(caso)]
    n_si, n_duda = finales.count("si"), finales.count("revisar")
    partes = [f"{n_si} corresponde{'n' if n_si != 1 else ''}"] if n_si else []
    if n_duda:
        partes.append(f"{n_duda} por decidir")
    return ", ".join(partes) or "Ninguno corresponde"


def por_que_no_validar(caso: Caso) -> str | None:
    """Lo que falta para poder validar (las mismas condiciones que exige `validar`)."""
    if caso.validacion is not None:
        return None
    if caso.tipo != "solicitud" and caso.hechos_vigentes is None:
        return "Primero completa los hechos"
    if caso.tipo == "solicitud" and caso.estado != "interpretado":
        return "Primero espera la respuesta de la persona"
    n = len(por_resolver(caso))
    if n:
        return f"Primero decide {n} deber{'es' if n != 1 else ''}"
    return None


def que_te_toca(caso: Caso) -> str:
    """Una línea arriba de la ficha: qué tiene que hacer el delegado en este caso."""
    if caso.validacion is not None:
        pendientes = pendientes_de_envio(caso)
        if pendientes:
            nombres = ", ".join(NOMBRES_ENVIO.get(d.id, d.id).lower() for d in pendientes)
            return (
                f"Validaste la decisión. Falta enviar: {nombres}. El sistema no envía nada: "
                "envíalo tú y marca «Ya lo envié»."
            )
        if entregas_del_caso(caso):
            return "Validaste y quedó registrado el envío de todo lo que corresponde."
        return "Validaste la decisión. Con estos hechos no corresponde enviar nada."
    falta = por_que_no_validar(caso)
    if falta == "Primero completa los hechos":
        return "La IA no pudo leer este reporte: completa los hechos y el motor decidirá."
    if falta and falta.startswith("Primero decide"):
        return f"{falta[len('Primero ') :].capitalize()} que el motor no pudo resolver y valida."
    if falta:
        return "La persona todavía no confirma lo que pide: el plazo corre igual."
    return "Revisa lo que decidió el motor y valídalo."


NOMBRES_ENVIO = {
    "aviso_agencia": "Aviso a la Agencia",
    "aviso_titulares": "Aviso a cada persona afectada",
    "reporte_anci": "Primer aviso a la ANCI",
    "anci_alerta_temprana": "Primer aviso a la ANCI (alerta temprana)",
    "anci_actualizacion": "Actualización a la ANCI",
    "anci_informe_final": "Informe final a la ANCI",
    "anci_plan_accion": "Plan de acción a la ANCI",
    "respuesta_solicitud": "Respuesta a la persona",
    "bloqueo_temporal": "Bloqueo de sus datos",
    "comunicar_a_terceros": "Aviso a quienes recibieron sus datos",
}
BORRADOR_DE = {
    "aviso_agencia": "agencia",
    "reporte_anci": "anci",
    "anci_alerta_temprana": "anci",
    "anci_actualizacion": "anci",
    "anci_informe_final": "anci",
    "anci_plan_accion": "anci",
}
GUIAS_ENVIO = {
    "aviso_agencia": "Usa el borrador y envíalo por el canal oficial de la Agencia.",
    "aviso_titulares": (
        "Avisa a cada persona afectada en lenguaje claro: qué datos, qué consecuencias y qué "
        "medidas (a los menores, por medio de sus padres o representantes)."
    ),
    "reporte_anci": "Usa el borrador y envíalo por el canal oficial de la ANCI.",
    "anci_alerta_temprana": "Usa el borrador y envíalo por el canal oficial de la ANCI.",
    "anci_actualizacion": "Actualiza a la ANCI con lo que se sabe ahora (usa el mismo borrador).",
    "anci_informe_final": "Envía a la ANCI el informe final del incidente.",
    "anci_plan_accion": (
        "Como operador de importancia vital, informa a la ANCI tu plan de acción apenas lo "
        "adoptes (a más tardar en 7 días desde que se supo)."
    ),
    "bloqueo_temporal": (
        "Deja de usar sus datos para lo que pidió suspender, hasta responderle. Esto no se "
        "envía: lo haces en tus sistemas."
    ),
    "comunicar_a_terceros": (
        "Avisa del cambio a quienes recibieron sus datos (proveedores u otros). El inventario "
        "muestra a quién se entregaron."
    ),
}


@dataclass
class VistaEnvio:
    id: str
    titulo: str
    guia: str
    vence: datetime | None
    envio: Envio | None
    boton: str  # «Ya lo envié» o «Ya lo hice»
    borrador: str | None  # destino del borrador que sirve para enviarlo
    vigente: bool = True  # False: se envió, pero con los hechos de hoy ya no corresponde

    @property
    def texto_envio(self) -> str:
        return texto_envio(self.envio) if self.envio else ""


def _guia(caso: Caso, d: Deber) -> str:
    if d.id != "respuesta_solicitud":
        return GUIAS_ENVIO.get(d.id, "")
    contacto = (caso.identidad or {}).get("contacto")
    vence = momento(d.vence)
    plazo = f" antes del {format_date(vence, format='long', locale='es_CL')}" if vence else ""
    destino = f" a {contacto}" if contacto else ""
    return (
        f"Respóndele tú por escrito{destino}{plazo}: qué pidió, qué hiciste y, si no "
        "corresponde, por qué. El sistema no envía la respuesta."
    )


def vista_envios(caso: Caso) -> list[VistaEnvio]:
    entregas = entregas_del_caso(caso)
    ids = {d.id for d in entregas}
    salida = [
        VistaEnvio(
            id=d.id,
            titulo=NOMBRES_ENVIO.get(d.id, TITULOS_DEBER.get(d.id, d.id)),
            guia=_guia(caso, d),
            vence=momento(d.vence),
            envio=caso.envios.get(d.id),
            boton="Ya lo hice" if d.id == "bloqueo_temporal" else "Ya lo envié",
            borrador=BORRADOR_DE.get(d.id),
        )
        for d in entregas
    ]
    for id_deber, envio in caso.envios.items():
        if id_deber not in ids:
            salida.append(
                VistaEnvio(
                    id=id_deber,
                    titulo=NOMBRES_ENVIO.get(id_deber, id_deber),
                    guia="",
                    vence=None,
                    envio=envio,
                    boton="",
                    borrador=None,
                    vigente=False,
                )
            )
    return salida


@dataclass
class VistaDestino:
    id: str
    nombre: str
    porque: str
    estado_aviso: str | None  # None: todavía no hay aviso (por ejemplo, sin mensajero)
    fallido: bool
    asunto: str | None = None
    cuerpo: str | None = None


def vista_destinos(caso: Caso, organizacion: str, url_panel: str | None) -> list[VistaDestino]:
    """A quién le llega el caso y si se le avisó. El aviso se vuelve a armar para mostrarlo:
    es el mismo texto que salió (no lleva datos personales)."""
    from ..canal.avisos import AvisoConDatosPersonales, armar_aviso
    from ..canal.enrutamiento import NOMBRES_DEBER

    if caso.asignacion is None:
        return []
    ultimo = {a.destino: a for a in caso.avisos}
    derivadas = {d.area for d in caso.derivaciones}
    salida = []
    for d in caso.asignacion.destinos:
        aviso = ultimo.get(d.id)
        estado = None
        if aviso:
            estado = f"{ESTADOS_AVISO[aviso.estado].capitalize()} · {hora(aviso.momento)}"
        try:
            armado = armar_aviso(caso, d, organizacion, NOMBRES_DEBER, url_panel, d.id in derivadas)
            asunto, cuerpo = armado.asunto, armado.cuerpo
        except AvisoConDatosPersonales:
            asunto = cuerpo = None
        salida.append(
            VistaDestino(
                d.id,
                d.nombre,
                d.porque,
                estado,
                bool(aviso and aviso.estado == "fallido"),
                asunto if aviso else None,
                cuerpo if aviso else None,
            )
        )
    return salida


# --- inventario -----------------------------------------------------------------------

CAMPOS_DS662 = {
    "tipo_datos": "i. Tipo de datos",
    "ambito_territorial": "ii. Ámbito territorial",
    "bases_de_datos": "iii. Bases de datos",
    "categorias_titulares": "iv. A quiénes pertenecen los datos",
    "fines": "v. Para qué se usan",
    "fuente": "vi. De dónde vienen",
    "base_licitud": "vii. Base legal para usarlos",
    "destinatarios": "viii. Con quién se comparten",
    "transferencias_internacionales": "ix. Envíos fuera de Chile",
    "plazo_supresion": "x. Cuándo se borran",
    "decisiones_automatizadas": "xi. Decisiones automatizadas",
}
BASES_LICITUD = {
    "consentimiento": "Consentimiento",
    "consentimiento_expreso": "Consentimiento expreso",
    "obligacion_financiera": "Obligación económica o financiera",
    "obligacion_legal": "Obligación legal",
    "contrato": "Contrato",
    "interes_legitimo": "Interés legítimo",
    "defensa_de_derechos": "Defensa de derechos",
    "no_determinada": "No determinada",
}
ORIGEN_CAMPO = {
    "calculado": "calculado",
    "ia": "propuesto por la IA",
    "pendiente": "pendiente",
    "persona": "completado por ti",
}
ORIGEN_INVENTARIO = {
    "grabada": (
        "Planilla de ejemplo: la IA respondió antes y la respuesta quedó grabada (demo sin "
        "conexión)."
    ),
    "ia": "La IA leyó los encabezados y la forma de los valores, nunca los valores.",
    "sin_ia": "Sin IA disponible: lo que necesita contexto quedó pendiente.",
}


def valor_campo(clave: str, valor: Any) -> str:
    if valor is None or valor == "":
        return "—"
    if clave == "base_licitud":
        return BASES_LICITUD.get(str(valor), str(valor))
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, list):
        return "; ".join(str(v) for v in valor) or "—"
    return str(valor)


@dataclass
class VistaCampo:
    clave: str
    etiqueta: str
    valor: str
    origen: str
    nota: str | None
    citas: list[Any]


def campos_ds662(actividad: Any) -> list[VistaCampo]:
    salida = []
    for clave, etiqueta in CAMPOS_DS662.items():
        c = getattr(actividad, clave)
        salida.append(
            VistaCampo(
                clave,
                etiqueta,
                valor_campo(clave, c.valor),
                ORIGEN_CAMPO.get(c.origen, c.origen),
                c.nota,
                list(c.citas),
            )
        )
    return salida


# --- simulador de escenarios ---------------------------------------------------------

EJEMPLOS_SIMULADOR = {
    "paseo": (
        "Planilla del paseo enviada por error a un proveedor (84 niños y niñas, con alergias)",
        {
            "datos_personales": True,
            "vulneracion": "comunicacion_no_autorizada",
            "categorias_especiales": ["menores_14", "sensibles"],
            "riesgo_mitigado": False,
            "ciberincidente": "no",
            "interrupcion_servicio": False,
            "titulares_aprox": 84,
        },
    ),
    "clientes": (
        "Ciberataque con acceso a la base de clientes (datos financieros)",
        {
            "datos_personales": True,
            "vulneracion": "acceso_no_autorizado",
            "categorias_especiales": ["financieros"],
            "riesgo_mitigado": False,
            "ciberincidente": "si",
            "interrupcion_servicio": False,
            "titulares_aprox": 1200,
        },
    ),
    "caida": (
        "Ransomware que detiene la atención y cifra fichas con datos de salud",
        {
            "datos_personales": True,
            "vulneracion": "alteracion",
            "categorias_especiales": ["sensibles"],
            "riesgo_mitigado": False,
            "ciberincidente": "si",
            "interrupcion_servicio": True,
            "titulares_aprox": 5000,
        },
    ),
}
NOMBRES_SIMULADOR = {
    "aviso_agencia": "Avisar a la Agencia de Protección de Datos",
    "aviso_titulares": "Avisar a cada persona afectada",
    "reporte_anci": "Reportar a la ANCI (Ley 21.663)",
}


@dataclass
class FilaComparada:
    deber: str
    titulo: str
    decision: str
    columnas: list[Any]  # una FilaSimulada por escenario
    cambia: bool


def comparar_filas(simulaciones: list) -> list[FilaComparada]:
    salida = []
    for i, fila in enumerate(simulaciones[0].filas):
        columnas = [s.filas[i] for s in simulaciones]
        firma = {(c.exigible, c.nota, tuple(x.texto for x in c.consecuencias)) for c in columnas}
        salida.append(
            FilaComparada(
                deber=fila.deber,
                titulo=NOMBRES_SIMULADOR.get(fila.deber, fila.deber),
                decision=DECISION[fila.decision],
                columnas=columnas,
                cambia=len(firma) > 1,
            )
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
    sin_hechos = caso.tipo != "solicitud" and caso.hechos_vigentes is None
    entregas = entregas_del_caso(caso)
    enviados = sum(1 for d in entregas if d.id in caso.envios)
    if sin_hechos:
        envio = Paso("Tú envías", "Espera los hechos", False)
    elif not entregas:
        envio = Paso("Tú envías", "Nada que enviar", caso.validacion is not None)
    else:
        dudas = len(por_resolver(caso))
        texto = f"{enviados} de {len(entregas)} enviado{'s' if len(entregas) != 1 else ''}"
        if dudas:
            texto += f", {dudas} por decidir"
        envio = Paso("Tú envías", texto, enviados == len(entregas) and not dudas)
    if caso.cascada is not None:
        llegada = Paso("Llegó por la red", f"{hora(caso.ingreso)} · reporte del proveedor", True)
        lectura = Paso("Hechos del proveedor", "Formulario cerrado, sin IA", True)
    else:
        llegada = Paso("Llegó por el canal", f"{hora(caso.ingreso)} · enlace o código QR", True)
        lectura = Paso(
            "La IA propone",
            f"Leyó el texto con los datos tapados ({hora(ia.momento)})" if ia else "No respondió",
            ia is not None or caso.hechos_delegado is not None,
        )
    return [
        llegada,
        lectura,
        Paso(
            "El motor decide",
            "Espera los hechos" if sin_hechos else conteo_deberes(caso),
            not sin_hechos,
        ),
        Paso(
            "Tú validas",
            f"Validado a las {hora(caso.validacion.momento)}" if caso.validacion else "Pendiente",
            caso.validacion is not None,
        ),
        envio,
    ]


@dataclass
class Hito:
    texto: str
    hora: str
    huella: str
    tipo: str


def _nombres_destino(caso: Caso) -> dict[str, str]:
    a = caso.asignacion
    return {d.id: d.nombre for d in (a.destinos + a.sugeridas)} if a else {}


def linea_de_tiempo(caso: Caso, anotaciones: list[Anotacion]) -> list[Hito]:
    nombres = _nombres_destino(caso)
    salida = []
    for i, e in enumerate(caso.eventos):
        texto = EVENTOS.get(e.tipo, e.tipo).format(por=e.detalle.get("por", "El delegado"))
        if e.tipo == "enrutado":
            n = len(e.detalle.get("destinos", []))
            texto = f"Se decidió a quién le llega: {n} destino{'s' if n != 1 else ''}"
        elif e.tipo == "aviso":
            destino = nombres.get(e.detalle.get("destino", ""), "un destino")
            texto = f"{destino}: {ESTADOS_AVISO.get(e.detalle.get('estado', ''), 'aviso')}"
        elif e.tipo == "derivado":
            area = nombres.get(e.detalle.get("area", ""), "un área")
            texto = f"{e.detalle.get('por', 'El delegado')} derivó el caso a {area}"
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
    falta_para_validar: str | None
    que_te_toca: str
    envios: list[VistaEnvio] = field(default_factory=list)
    valores: dict[str, Any] = field(default_factory=dict)  # para el formulario de corrección


def ficha(caso: Caso, anotaciones: list[Anotacion], ahora: datetime) -> Ficha:
    vigentes = caso.hechos_vigentes
    valores = (
        vigentes.model_dump(mode="json")
        if vigentes
        else {  # la IA no leyó: el formulario parte vacío para no parecer una lectura
            "datos_personales": None,
            "vulneracion": None,
            "categorias_especiales": [],
            "riesgo_mitigado": None,
            "ciberincidente": None,
            "interrupcion_servicio": None,
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
        falta_para_validar=por_que_no_validar(caso),
        que_te_toca=que_te_toca(caso),
        envios=vista_envios(caso),
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
    pendiente: bool = False  # todavía no se sabe: faltan los hechos (no es «no corresponde»)

    @property
    def estado(self) -> str:
        if self.pendiente:
            return "Pendiente"
        if self.borrador is None:
            return "No corresponde"
        if self.revision and self.revision.vigente:
            return f"Revisado por {self.revision.por} a las {hora(self.revision.momento)}"
        if self.revision:
            return "Cambió después de tu revisión: revísalo de nuevo"
        n = len(self.borrador.por_completar)
        return f"Listo para revisar · {n} campo{'s' if n != 1 else ''} por completar"


def vista_borradores(caso: Caso, borradores: dict) -> list[VistaBorrador]:
    sin_hechos = caso.tipo != "solicitud" and caso.hechos_vigentes is None
    salida = []
    for destino in DESTINOS:
        b = borradores.get(destino)
        if isinstance(b, Borrador):
            salida.append(
                VistaBorrador(destino, NOMBRE_DESTINO[destino], b, None, ultima_revision(caso, b))
            )
        else:
            motivo = b.motivo if isinstance(b, SinBorrador) else "No hay borrador."
            if sin_hechos:
                motivo = "Completa los hechos y se arma."
            salida.append(
                VistaBorrador(destino, NOMBRE_DESTINO[destino], None, motivo, None, sin_hechos)
            )
    return salida
