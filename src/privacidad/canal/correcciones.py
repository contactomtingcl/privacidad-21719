"""Cifra de correcciones: cuánto corrige la persona lo que leyó la IA, medido desde la evidencia.

Se calcula solo con la cadena de evidencia (no con la tabla de casos), para que cualquiera pueda
recalcularla y comprobar que nadie la retocó: la cadena se verifica antes de contar.

Qué se cuenta, sin interpretar:

- Incidentes que la IA leyó: casos de incidente con el evento «interpretado».
- Corregidos: de esos, los casos en que al final al menos un hecho quedó distinto de lo que propuso
  la IA. Si el delegado cambió un hecho y después lo devolvió a lo que dijo la IA, no cuenta.
- Por motivo: el motivo de lista cerrada que eligió el delegado. Solo «La IA leyó mal el mensaje»
  es un error de la IA; «Llegó información nueva» o «El área lo confirmó» no lo son.
- Cambió un deber: la corrección hizo que el motor decidiera distinto sobre avisar a la Agencia, a
  las personas o a la ANCI. Muestra por qué la validación humana importa.
- Validados sin corrección: casos que el delegado revisó y validó tal como los leyó la IA. Solo
  los validados dicen algo: un caso abierto todavía puede corregirse.
- Completados sin IA: incidentes que la IA no pudo leer y el delegado completó. No son
  correcciones (no había nada que corregir) y se muestran aparte.
- Solicitudes: cuántas lecturas confirmó la propia persona y cuántas corrigió ella.

Límite: con datos ficticios esta cifra mide el mecanismo, no el desempeño real de la IA. La cifra
que vale es la de las pruebas con usuarios, guardada con su fecha.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .evidencia import Anotacion

DEBERES = ("aviso_agencia", "aviso_titulares", "reporte_anci")
TIPOS_INCIDENTE = ("incidente", "aviso_proveedor")


@dataclass
class CifraCorrecciones:
    incidentes_leidos: int = 0
    corregidos: int = 0
    por_motivo: Counter = field(default_factory=Counter)  # casos con al menos ese motivo
    campos: Counter = field(default_factory=Counter)  # casos en que ese hecho quedó distinto
    cambiaron_deber: int = 0
    validados: int = 0  # incidentes leídos por la IA y validados (sin anulación posterior)
    validados_sin_correccion: int = 0
    completados_sin_ia: int = 0
    dudas_resueltas: int = 0
    solicitudes_confirmadas: int = 0  # la persona confirmó lo que entendió la IA
    solicitudes_corregidas: int = 0  # la persona corrigió lo que entendió la IA

    @property
    def por_error_ia(self) -> int:
        return self.por_motivo.get("error_ia", 0)

    def como_dict(self) -> dict[str, Any]:
        return {
            "incidentes_leidos_por_la_ia": self.incidentes_leidos,
            "corregidos": self.corregidos,
            "corregidos_por_error_de_la_ia": self.por_error_ia,
            "por_motivo": dict(sorted(self.por_motivo.items())),
            "hechos_corregidos": dict(sorted(self.campos.items())),
            "correcciones_que_cambiaron_un_deber": self.cambiaron_deber,
            "validados": self.validados,
            "validados_sin_correccion": self.validados_sin_correccion,
            "completados_sin_ia": self.completados_sin_ia,
            "dudas_resueltas": self.dudas_resueltas,
            "solicitudes_confirmadas_por_la_persona": self.solicitudes_confirmadas,
            "solicitudes_corregidas_por_la_persona": self.solicitudes_corregidas,
        }


@dataclass
class _Caso:
    tipo: str | None = None
    leido_por_ia: bool = False
    sin_ia: bool = False
    deberes_ia: dict[str, str] = field(default_factory=dict)
    deberes_final: dict[str, str] = field(default_factory=dict)
    valor_ia: dict[str, Any] = field(default_factory=dict)  # lo que propuso la IA, por hecho
    valor_final: dict[str, Any] = field(default_factory=dict)
    motivos: set[str] = field(default_factory=set)
    corregido_alguna_vez: bool = False
    validado: bool = False

    def hechos_distintos(self) -> set[str]:
        return {c for c, v in self.valor_final.items() if v != self.valor_ia.get(c)}


def medir_correcciones(anotaciones: list[Anotacion]) -> CifraCorrecciones:
    """Recorre la evidencia en orden y cuenta. Las anotaciones deben venir ya verificadas."""
    casos: dict[str, _Caso] = {}
    cifra = CifraCorrecciones()
    for a in sorted(anotaciones, key=lambda x: x.n):
        c = casos.setdefault(a.id_caso, _Caso())
        d = a.detalle
        if a.tipo == "recibido":
            c.tipo = d.get("tipo")
        elif a.tipo == "interpretado" and c.tipo in TIPOS_INCIDENTE:
            c.leido_por_ia = True
            c.deberes_ia = {k: d[k] for k in DEBERES if k in d}
            c.deberes_final = dict(c.deberes_ia)
        elif a.tipo == "ia_sin_respuesta" and c.tipo in TIPOS_INCIDENTE:
            c.sin_ia = True
        elif a.tipo == "hechos_corregidos":
            c.corregido_alguna_vez = True
            for campo, (antes, despues) in d.get("cambios", {}).items():
                c.valor_ia.setdefault(campo, antes)  # la primera vez que cambia, «antes» es la IA
                c.valor_final[campo] = despues
            c.motivos.add(d.get("motivo", "otro"))
            c.deberes_final = {k: d[k] for k in DEBERES if k in d}
        elif a.tipo == "deber_resuelto":
            cifra.dudas_resueltas += 1
        elif a.tipo == "validado":
            c.validado = True
        elif a.tipo == "validacion_anulada":
            c.validado = False
        elif a.tipo == "confirmacion_respondida":
            if d.get("resultado") == "confirmada":
                cifra.solicitudes_confirmadas += 1
            elif d.get("resultado") == "corregida":
                cifra.solicitudes_corregidas += 1

    for c in casos.values():
        if c.sin_ia and not c.leido_por_ia:
            if c.corregido_alguna_vez:
                cifra.completados_sin_ia += 1
            continue
        if not c.leido_por_ia:
            continue
        cifra.incidentes_leidos += 1
        distintos = c.hechos_distintos()
        if distintos:
            cifra.corregidos += 1
            cifra.campos.update(distintos)
            cifra.por_motivo.update(c.motivos)
            if c.deberes_final != c.deberes_ia:
                cifra.cambiaron_deber += 1
        if c.validado:
            cifra.validados += 1
            if not distintos:
                cifra.validados_sin_correccion += 1
    return cifra
