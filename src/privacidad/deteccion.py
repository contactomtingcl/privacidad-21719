"""Detección determinística de datos personales en texto y enmascarado.

Regla del sistema: lo que se puede detectar con código (RUT, correos, teléfonos,
fechas) se detecta con código. La IA solo recibe texto enmascarado y se usa para
lo ambiguo, como reconocer que "alergias" es un dato de salud.

Enmascarar no es anonimizar: el texto enmascarado sigue siendo dato personal
(art. 2 de la Ley 19.628) porque el mapa de reemplazo permite revertirlo. Por eso
el mapa nunca sale del sistema ni se envía a la IA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from . import rut as rut_mod

TipoDetectado = Literal["rut", "correo", "telefono", "fecha"]

CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Móviles con o sin +56; fijos solo con +56, para no confundirlos con montos o folios.
TELEFONO = re.compile(
    r"(?<![\d+])(?:(?:\+?56[\s-]?)?9[\s-]?\d{4}[\s-]?\d{4}"
    r"|\+?56[\s-]?(?:2|[3-7]\d)[\s-]?\d{3,4}[\s-]?\d{4})(?!\d)"
)
FECHA = re.compile(
    r"(?<!\d)(?:(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<a>\d{4})"
    r"|(?P<a2>\d{4})-(?P<m2>\d{1,2})-(?P<d2>\d{1,2}))(?!\d)"
)


@dataclass(frozen=True)
class Deteccion:
    tipo: TipoDetectado
    inicio: int
    fin: int
    valor: str


def parsear_fecha(texto: str) -> date | None:
    """Lee fechas dd/mm/aaaa, dd-mm-aaaa o aaaa-mm-dd. Devuelve None si no es válida."""
    m = FECHA.fullmatch(texto.strip())
    if not m:
        return None
    if m.group("a"):
        d, mes, a = int(m.group("d")), int(m.group("m")), int(m.group("a"))
    else:
        d, mes, a = int(m.group("d2")), int(m.group("m2")), int(m.group("a2"))
    try:
        return date(a, mes, d)
    except ValueError:
        return None


def edad_en(nacimiento: date, referencia: date) -> int:
    """Edad cumplida a la fecha de referencia."""
    cumplio = (referencia.month, referencia.day) >= (nacimiento.month, nacimiento.day)
    return referencia.year - nacimiento.year - (0 if cumplio else 1)


def detectar(texto: str) -> list[Deteccion]:
    """Encuentra RUT válidos, correos, teléfonos y fechas, sin solapamientos."""
    candidatos: list[Deteccion] = []
    for _rut, ini, fin in rut_mod.buscar(texto, solo_validos=True):
        candidatos.append(Deteccion("rut", ini, fin, texto[ini:fin]))
    for m in CORREO.finditer(texto):
        candidatos.append(Deteccion("correo", m.start(), m.end(), m.group(0)))
    for m in FECHA.finditer(texto):
        if parsear_fecha(m.group(0)):
            candidatos.append(Deteccion("fecha", m.start(), m.end(), m.group(0)))
    for m in TELEFONO.finditer(texto):
        candidatos.append(Deteccion("telefono", m.start(), m.end(), m.group(0)))

    # Prioridad ante solapamiento: el orden de la lista (RUT antes que teléfono, etc.).
    elegidos: list[Deteccion] = []
    for c in candidatos:
        if all(c.fin <= e.inicio or c.inicio >= e.fin for e in elegidos):
            elegidos.append(c)
    return sorted(elegidos, key=lambda d: d.inicio)


@dataclass
class Enmascarador:
    """Reemplaza datos detectados por marcadores estables: [RUT_1], [CORREO_2]...

    Un mismo valor recibe siempre el mismo marcador, para que la IA pueda razonar
    ("el apoderado de [RUT_1]") sin ver el dato. El mapa queda solo en memoria.
    """

    _por_valor: dict[tuple[str, str], str] = field(default_factory=dict)
    _contadores: dict[str, int] = field(default_factory=dict)

    def _marcador(self, tipo: str, valor: str) -> str:
        llave = (tipo, valor)
        if llave not in self._por_valor:
            n = self._contadores.get(tipo, 0) + 1
            self._contadores[tipo] = n
            self._por_valor[llave] = f"[{tipo.upper()}_{n}]"
        return self._por_valor[llave]

    def enmascarar(self, texto: str) -> str:
        partes, cursor = [], 0
        for d in detectar(texto):
            partes.append(texto[cursor : d.inicio])
            partes.append(self._marcador(d.tipo, d.valor))
            cursor = d.fin
        partes.append(texto[cursor:])
        return "".join(partes)

    def revertir(self, texto: str) -> str:
        """Solo para uso interno (por ejemplo, armar la respuesta final al titular)."""
        for (_, valor), marcador in self._por_valor.items():
            texto = texto.replace(marcador, valor)
        return texto

    @property
    def cantidad(self) -> int:
        return len(self._por_valor)
