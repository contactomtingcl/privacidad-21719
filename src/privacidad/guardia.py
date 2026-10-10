"""Guardia de datos sintéticos.

Las bases de ProductIA (sección 11) solo permiten datos de sandbox, sintéticos o
anonimizados. Esta guardia se ejecuta antes de procesar cualquier dato y rechaza
lo que podría ser un dato real.

Convenciones del proyecto para datos sintéticos:

- RUT: cuerpo entre 50.000.000 y 59.999.999, con dígito verificador válido.
  Es una convención interna para reconocer nuestros datos de prueba; cualquier RUT
  fuera de ese tramo se trata como posiblemente real.
- Correo: dominios reservados para documentación y pruebas por los RFC 2606 y
  6761 (example.com, example.org, example.net y los dominios .example, .test e .invalid).
- Teléfono móvil: +56 9 0000 XXXX. Cualquier otro móvil se trata como posiblemente real.

La guardia no puede reconocer nombres o direcciones reales: por eso los
generadores de datos del proyecto usan listas cerradas de nombres ficticios.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from . import rut as rut_mod

RANGO_RUT_SINTETICO = range(50_000_000, 60_000_000)
DOMINIOS_RESERVADOS = ("example.com", "example.org", "example.net")
TLD_RESERVADOS = (".example", ".test", ".invalid")
PREFIJO_MOVIL_SINTETICO = "90000"  # +56 9 0000 XXXX

_CORREO = re.compile(r"[\w.+-]+@(?P<dominio>[\w-]+(?:\.[\w-]+)+)")
_MOVIL = re.compile(r"(?<!\d)(?:\+?56[\s-]?)?9[\s-]?\d{4}[\s-]?\d{4}(?!\d)")

TipoDato = Literal["rut", "correo", "telefono"]


@dataclass(frozen=True)
class Hallazgo:
    """Un dato que no cumple la convención sintética. Nunca guarda el valor completo."""

    tipo: TipoDato
    valor_enmascarado: str
    campo: str | None = None

    def describir(self) -> str:
        lugar = f" en '{self.campo}'" if self.campo else ""
        return f"{self.tipo} posiblemente real{lugar}: {self.valor_enmascarado}"


class DatosNoSinteticosError(ValueError):
    """Se lanza cuando la entrada contiene datos que podrían ser reales."""

    def __init__(self, hallazgos: list[Hallazgo]) -> None:
        self.hallazgos = hallazgos
        detalle = "; ".join(h.describir() for h in hallazgos[:5])
        extra = f" (y {len(hallazgos) - 5} más)" if len(hallazgos) > 5 else ""
        super().__init__(f"Se rechazaron {len(hallazgos)} dato(s): {detalle}{extra}")


def _correo_es_sintetico(dominio: str) -> bool:
    d = dominio.lower()
    return (
        d in DOMINIOS_RESERVADOS
        or any(d.endswith("." + r) for r in DOMINIOS_RESERVADOS)
        or d.endswith(TLD_RESERVADOS)
    )


def _enmascarar_correo(correo: str) -> str:
    usuario, _, dominio = correo.partition("@")
    return f"{usuario[:1]}***@{dominio}"


def _digitos_movil(texto: str) -> str:
    d = re.sub(r"\D", "", texto)
    return d[2:] if d.startswith("56") and len(d) == 11 else d


def revisar_texto(texto: str, campo: str | None = None) -> list[Hallazgo]:
    """Devuelve los datos del texto que no cumplen la convención sintética."""
    hallazgos: list[Hallazgo] = []
    for rut, _, _ in rut_mod.buscar(texto, solo_validos=True):
        if rut.cuerpo not in RANGO_RUT_SINTETICO:
            hallazgos.append(Hallazgo("rut", rut.enmascarar(), campo))
    for m in _CORREO.finditer(texto):
        if not _correo_es_sintetico(m.group("dominio")):
            hallazgos.append(Hallazgo("correo", _enmascarar_correo(m.group(0)), campo))
    for m in _MOVIL.finditer(texto):
        digitos = _digitos_movil(m.group(0))
        if not digitos.startswith(PREFIJO_MOVIL_SINTETICO):
            hallazgos.append(Hallazgo("telefono", f"+56 {digitos[:1]} **** {digitos[-2:]}", campo))
    return hallazgos


def revisar(dato: Any, campo: str | None = None) -> list[Hallazgo]:
    """Revisa un texto, un registro (dict) o una colección de registros, de forma recursiva."""
    if dato is None:
        return []
    if isinstance(dato, str):
        return revisar_texto(dato, campo)
    if isinstance(dato, Mapping):
        hallazgos: list[Hallazgo] = []
        for clave, valor in dato.items():
            hallazgos += revisar(valor, str(clave))
        return hallazgos
    if isinstance(dato, Iterable) and not isinstance(dato, (bytes, bytearray)):
        hallazgos = []
        for elemento in dato:
            hallazgos += revisar(elemento, campo)
        return hallazgos
    return revisar_texto(str(dato), campo)


def exigir_sintetico(dato: Any) -> None:
    """Lanza DatosNoSinteticosError si el dato contiene algo que podría ser real."""
    hallazgos = revisar(dato)
    if hallazgos:
        raise DatosNoSinteticosError(hallazgos)


def rut_sintetico(semilla: int) -> str:
    """Genera un RUT sintético válido y determinista dentro del tramo reservado."""
    cuerpo = RANGO_RUT_SINTETICO.start + (semilla % len(RANGO_RUT_SINTETICO))
    return rut_mod.Rut(cuerpo, rut_mod.calcular_dv(cuerpo)).formatear()


def movil_sintetico(semilla: int) -> str:
    return f"+56 9 0000 {semilla % 10_000:04d}"
