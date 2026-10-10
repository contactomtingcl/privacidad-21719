"""RUT chileno: dígito verificador, validación, formato y detección en texto."""

from __future__ import annotations

import re
from dataclasses import dataclass

# RUT con guion: '12.345.678-5', '12345678-5', '1.234.567-K'. Sin guion no se detecta,
# para no confundir RUT con cualquier número de 8 o 9 dígitos.
_PATRON_RUT = re.compile(
    r"(?<![\w.])(?P<cuerpo>\d{1,2}(?:\.\d{3}){2}|\d{7,8})\s?-\s?(?P<dv>[\dkK])(?![\w])"
)


def calcular_dv(cuerpo: int) -> str:
    """Dígito verificador por módulo 11, como lo calcula el Registro Civil."""
    if cuerpo <= 0:
        raise ValueError("El cuerpo del RUT debe ser positivo")
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


@dataclass(frozen=True)
class Rut:
    cuerpo: int
    dv: str

    @property
    def valido(self) -> bool:
        return calcular_dv(self.cuerpo) == self.dv.upper()

    def formatear(self) -> str:
        return f"{self.cuerpo:,}".replace(",", ".") + f"-{self.dv.upper()}"

    def enmascarar(self) -> str:
        """Muestra solo los dos primeros dígitos: '12.***.***-*'."""
        f = self.formatear()
        return f[:2] + re.sub(r"[\dK]", "*", f[2:])


def parsear(texto: str) -> Rut:
    """Convierte '12.345.678-5' o '12345678-5' en un Rut. No valida el dígito."""
    m = _PATRON_RUT.fullmatch(texto.strip())
    if not m:
        raise ValueError("Formato de RUT no reconocido")
    return Rut(int(m.group("cuerpo").replace(".", "")), m.group("dv").upper())


def es_valido(texto: str) -> bool:
    try:
        return parsear(texto).valido
    except ValueError:
        return False


def buscar(texto: str, solo_validos: bool = True) -> list[tuple[Rut, int, int]]:
    """Encuentra RUT en un texto libre. Devuelve (rut, inicio, fin) de cada uno."""
    hallados = []
    for m in _PATRON_RUT.finditer(texto):
        rut = Rut(int(m.group("cuerpo").replace(".", "")), m.group("dv").upper())
        if rut.valido or not solo_validos:
            hallados.append((rut, m.start(), m.end()))
    return hallados
