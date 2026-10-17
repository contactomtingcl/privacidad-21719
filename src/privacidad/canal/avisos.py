"""Avisos a quienes les llega un caso: el delegado y las áreas del enrutamiento o derivadas.

Qué lleva un aviso (y qué no):

- Lleva el código del caso, el tipo, la urgencia, el plazo más cercano y por qué le llega a ese
  destino. Al delegado, además, el enlace al panel.
- **No lleva el mensaje ni datos personales.** El texto de quien reportó puede identificar a
  alguien; las áreas reciben solo lo necesario para saber que tienen un caso y el delegado les da
  los detalles. Antes de enviar se revisa que el aviso no tenga RUT, correos ni teléfonos (el
  correo del destinatario va solo en el encabezado). Si los tuviera, no se envía.
- En un caso reservado, las áreas no reciben aviso salvo que el delegado lo derive; aun así, el
  aviso nunca lleva la identidad.

Cómo sale:

- Con `PRIVACIDAD_SMTP_HOST` configurado, por correo con `smtplib` (biblioteca estándar), con
  STARTTLS y usuario y contraseña si se indican. La contraseña vive en una variable de entorno,
  nunca en el repositorio.
- Con `PRIVACIDAD_TELEGRAM_TOKEN` (el token del bot, en una variable de entorno), además por
  Telegram a los destinos que tienen `telegram` (id de chat) en `data/canal/enrutamiento.yaml`,
  con `urllib` (biblioteca estándar) contra la API de bots de Telegram.
- Sin servidor de correo (la demo y las pruebas), el aviso queda en una bandeja de salida
  simulada: se arma igual, se registra como «simulado» y no sale a ninguna parte. Los correos de
  la demo son ficticios (dominios `.example`).

Si el envío falla, el caso no se pierde: el aviso queda «fallido» en el caso y en el registro, y
el panel lo muestra.
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from typing import Protocol

from babel.dates import format_date

from ..deteccion import detectar
from .modelos import ZONA_CHILE, Caso, Destino

TIPOS_CASO = {
    "solicitud": "Solicitud de una persona",
    "incidente": "Incidente",
    "aviso_proveedor": "Aviso de proveedor",
}
URGENCIAS = {"inmediata": "inmediata", "alta": "alta", "normal": "normal"}
PROHIBIDOS = ("rut", "correo", "telefono")


class AvisoConDatosPersonales(Exception):
    """El aviso armado tiene algo que parece un dato personal: no se envía."""


@dataclass
class Aviso:
    para: str  # correo del destino (solo en el encabezado)
    destino: str  # id del destino
    asunto: str
    cuerpo: str
    telegram: str | None = None  # id de chat de Telegram del destino, si tiene


class Mensajero(Protocol):
    simulado: bool

    def enviar(self, aviso: Aviso) -> None: ...


@dataclass
class BandejaSalida:
    """Sin servidor de correo: guarda los avisos en memoria y no los envía."""

    simulado: bool = True
    enviados: list[Aviso] = field(default_factory=list)

    def enviar(self, aviso: Aviso) -> None:
        self.enviados.append(aviso)


@dataclass
class CorreoSMTP:
    host: str
    puerto: int = 587
    usuario: str | None = None
    contrasena: str | None = None
    remitente: str = "avisos@privacidad.example"
    timeout: float = 10.0
    simulado: bool = False

    def enviar(self, aviso: Aviso) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self.remitente
        mensaje["To"] = aviso.para
        mensaje["Subject"] = aviso.asunto
        mensaje.set_content(aviso.cuerpo)
        with smtplib.SMTP(self.host, self.puerto, timeout=self.timeout) as smtp:
            smtp.starttls()
            if self.usuario and self.contrasena:
                smtp.login(self.usuario, self.contrasena)
            smtp.send_message(mensaje)


@dataclass
class Telegram:
    """Envía el aviso a un chat de Telegram con la API de bots (urllib, biblioteca estándar)."""

    token: str
    timeout: float = 10.0
    simulado: bool = False
    api: str = "https://api.telegram.org"

    def enviar(self, aviso: Aviso) -> None:
        if not aviso.telegram:
            return
        datos = urllib.parse.urlencode(
            {"chat_id": aviso.telegram, "text": f"{aviso.asunto}\n\n{aviso.cuerpo}"}
        ).encode()
        url = f"{self.api}/bot{self.token}/sendMessage"
        with urllib.request.urlopen(url, data=datos, timeout=self.timeout) as respuesta:
            cuerpo = json.loads(respuesta.read().decode("utf-8") or "{}")
        if not cuerpo.get("ok"):
            raise OSError("Telegram no aceptó el mensaje")


@dataclass
class Varios:
    """Correo (o bandeja simulada) y, si se configuró, Telegram. Si uno falla, el aviso falla."""

    canales: list[Mensajero]

    @property
    def simulado(self) -> bool:
        return all(c.simulado for c in self.canales)

    def enviar(self, aviso: Aviso) -> None:
        for canal in self.canales:
            canal.enviar(aviso)


def salio_de_verdad(mensajero: Mensajero, aviso: Aviso) -> bool:
    """¿Salió por algún canal real? Telegram solo cuenta si el destino tiene chat."""
    if isinstance(mensajero, Varios):
        return any(salio_de_verdad(c, aviso) for c in mensajero.canales)
    if isinstance(mensajero, Telegram):
        return bool(aviso.telegram)
    return not mensajero.simulado


def mensajero_desde_entorno() -> Mensajero:
    host = os.environ.get("PRIVACIDAD_SMTP_HOST")
    correo: Mensajero = (
        CorreoSMTP(
            host=host,
            puerto=int(os.environ.get("PRIVACIDAD_SMTP_PUERTO", "587")),
            usuario=os.environ.get("PRIVACIDAD_SMTP_USUARIO"),
            contrasena=os.environ.get("PRIVACIDAD_SMTP_CONTRASENA"),
            remitente=os.environ.get("PRIVACIDAD_SMTP_REMITENTE", "avisos@privacidad.example"),
        )
        if host
        else BandejaSalida()
    )
    token = os.environ.get("PRIVACIDAD_TELEGRAM_TOKEN")
    return Varios([correo, Telegram(token)]) if token else correo


def _cuando(valor: datetime) -> str:
    local = valor.astimezone(ZONA_CHILE)
    dia = format_date(local, "d 'de' MMMM", locale="es_CL")
    return f"{dia} a las {local:%H:%M}"


def revisar_aviso(texto: str) -> None:
    tipos = sorted({d.tipo for d in detectar(texto) if d.tipo in PROHIBIDOS})
    if tipos:
        raise AvisoConDatosPersonales(f"El aviso tiene algo que parece {', '.join(tipos)}")


def armar_aviso(
    caso: Caso,
    destino: Destino,
    organizacion: str,
    nombres_deber: dict[str, str],
    url_panel: str | None = None,
    derivado: bool = False,
) -> Aviso:
    a = caso.asignacion
    tipo = TIPOS_CASO.get(caso.tipo, caso.tipo)
    urgencia = URGENCIAS.get(a.urgencia, a.urgencia) if a else "normal"
    lineas = [
        f"{organizacion}: {'te derivaron' if derivado else 'llegó'} un caso por el canal de "
        "privacidad.",
        "",
        f"Código del caso: {caso.id}",
        f"Tipo: {tipo}{' (reservado)' if caso.reservado else ''}",
        f"Urgencia: {urgencia}",
    ]
    if a and a.proximo_plazo and a.vence:
        nombre = nombres_deber.get(a.proximo_plazo, a.proximo_plazo)
        lineas.append(f"Plazo más cercano: {nombre}, vence el {_cuando(a.vence)}.")
    lineas += ["", f"Por qué te llega: {destino.porque}", ""]
    if destino.rol == "delegado":
        if url_panel:
            lineas.append(f"Ábrelo en el panel: {url_panel}/panel/caso/{caso.id}")
        lineas.append("Este aviso no incluye el mensaje: está en el panel.")
    else:
        lineas += [
            "Este aviso no incluye el mensaje ni datos de personas. El delegado de protección "
            "de datos te dará los detalles que necesites.",
            "No reenvíes este correo.",
        ]
    lineas += [
        "",
        "Lo envía automáticamente el canal de privacidad. Los plazos los calcula un motor de "
        "reglas; la IA no decide plazos ni deberes.",
    ]
    cuerpo = "\n".join(lineas)
    asunto = f"[{urgencia.capitalize()}] Caso {caso.id}: {tipo.lower()}"
    revisar_aviso(asunto + "\n" + cuerpo)
    return Aviso(
        para=destino.contacto,
        destino=destino.id,
        asunto=asunto,
        cuerpo=cuerpo,
        telegram=destino.telegram,
    )


__all__ = [
    "Aviso",
    "AvisoConDatosPersonales",
    "BandejaSalida",
    "CorreoSMTP",
    "Telegram",
    "Varios",
    "Mensajero",
    "armar_aviso",
    "salio_de_verdad",
    "mensajero_desde_entorno",
    "revisar_aviso",
]
