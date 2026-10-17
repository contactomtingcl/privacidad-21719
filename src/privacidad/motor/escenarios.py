"""Simulador de escenarios: el mismo incidente, con la ley vigente y con la postergación.

Lo que corresponde hacer lo decide siempre el motor con las reglas vigentes (`decidir_incidente`);
el escenario no toca esa decisión. Cambia dos cosas, y solo para la Ley 21.719:

- **Desde cuándo es exigible.** Antes de la fecha de vigencia del escenario, avisar a la Agencia
  y a las personas es una buena práctica, no una obligación sancionable.
- **Qué sanción se arriesga en el primer año.** La ley vigente permite amonestar en vez de multar
  solo a las empresas de menor tamaño; el proyecto lo extiende a todos los responsables.

El reporte a la ANCI (Ley 21.663) no depende de ningún escenario: ya es exigible.

Las reglas y sus fuentes están en `data/reglas/escenarios.yaml`; las citas a leyes se verifican
contra el corpus en las pruebas, y el proyecto de ley se lee de un extracto guardado en
`data/normas/proyectos/` (no es ley: se muestra siempre como escenario).
"""

from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .motor import (
    RAIZ_REGLAS,
    Cita,
    Deber,
    HechosIncidente,
    PerfilOrganizacion,
    cargar_reglas,
    decidir_incidente,
)

RAIZ_NORMAS = RAIZ_REGLAS.parent / "normas"
ZONA = "America/Santiago"


class Escenario(BaseModel):
    id: str
    nombre: str
    estado: str
    vigencia_ley_21719: date
    amonestacion_a_todos: bool
    fuente: Cita | None = None  # cita de una ley (verificada contra el corpus)
    documento: str | None = None  # extracto de un proyecto, en data/normas/
    fragmento: str | None = None
    url: str | None = None


class Sancion(BaseModel):
    texto: str
    fuentes: list[Cita]


class FilaSimulada(BaseModel):
    """Un deber en un escenario."""

    deber: str
    decision: str  # la del motor: igual en todos los escenarios
    exigible: bool
    exigible_desde: date | None
    consecuencias: list[Sancion] = Field(default_factory=list)
    nota: str


class Simulacion(BaseModel):
    escenario: Escenario
    fecha: date
    filas: list[FilaSimulada]


@lru_cache(maxsize=1)
def _datos(ruta: Path | None = None) -> dict:
    return yaml.safe_load((ruta or RAIZ_REGLAS / "escenarios.yaml").read_text(encoding="utf-8"))


def cargar_escenarios() -> dict[str, Escenario]:
    salida = {}
    for id_, e in _datos()["escenarios"].items():
        fuente = e.get("fuente")
        salida[id_] = Escenario(
            id=id_,
            nombre=e["nombre"],
            estado=e["estado"],
            vigencia_ley_21719=e["vigencia_ley_21719"],
            amonestacion_a_todos=e["amonestacion_a_todos"],
            fuente=Cita(
                norma=fuente["norma"],
                articulo=str(fuente["articulo"]),
                fragmento=fuente["fragmento"],
            )
            if fuente
            else None,
            documento=e.get("documento"),
            fragmento=e.get("fragmento"),
            url=e.get("url"),
        )
    return salida


def sancion(clave: str) -> Sancion:
    s = _datos()["sanciones"][clave]
    return Sancion(
        texto=s["texto"],
        fuentes=[
            Cita(norma=f["norma"], articulo=str(f["articulo"]), fragmento=f["fragmento"])
            for f in s["fuentes"]
        ],
    )


def extracto(escenario: Escenario) -> str | None:
    """El texto del proyecto guardado en el repositorio, para mostrar y verificar la cita."""
    if not escenario.documento:
        return None
    return (RAIZ_NORMAS / escenario.documento).read_text(encoding="utf-8")


def _ley(id_deber: str) -> str:
    reglas = cargar_reglas()["reglas"]
    if id_deber in reglas:
        return reglas[id_deber]["ley"]
    return "ley-21663" if id_deber.startswith(("reporte_anci", "anci_")) else "ley-21719"


def _fila(
    deber: Deber,
    escenario: Escenario,
    fecha: date,
    perfil: PerfilOrganizacion,
    oiv: bool,
    menor_tamano: bool,
    sensibles: bool,
) -> FilaSimulada:
    if _ley(deber.id) == "ley-21663":
        if deber.decision == "no":
            return FilaSimulada(
                deber=deber.id,
                decision="no",
                exigible=True,
                exigible_desde=None,
                nota=deber.porque + " Ningún escenario lo cambia.",
            )
        consecuencias = [sancion("omitir_reporte_anci")]
        return FilaSimulada(
            deber=deber.id,
            decision=deber.decision,
            exigible=True,
            exigible_desde=None,
            consecuencias=consecuencias,
            nota="Ley 21.663: ya es exigible y ningún escenario lo cambia."
            + (" Operador de importancia vital: multas al doble." if oiv else ""),
        )
    desde = escenario.vigencia_ley_21719
    exigible = fecha >= desde
    if deber.decision == "no":
        return FilaSimulada(
            deber=deber.id,
            decision="no",
            exigible=exigible,
            exigible_desde=desde,
            nota="Con estos hechos no corresponde.",
        )
    if not exigible:
        return FilaSimulada(
            deber=deber.id,
            decision=deber.decision,
            exigible=False,
            exigible_desde=desde,
            nota=f"Aún no es exigible (rige desde el {desde:%d-%m-%Y}): hacerlo es una buena "
            "práctica, sin sanción de la Ley 21.719.",
        )
    consecuencias = [sancion("omitir_comunicacion")]
    publico = perfil == "organismo_publico"
    consecuencias.append(sancion("multa_organos_publicos" if publico else "multa_privados"))
    primer_anio = fecha < date(desde.year + 1, desde.month, desde.day)
    amonestable = escenario.amonestacion_a_todos or (menor_tamano and not publico)
    nota = "Ya rige: si no se cumple, se arriesga una sanción."
    if primer_anio and amonestable:
        consecuencias.append(sancion("amonestacion_primer_anio"))
        nota = "Primer año de vigencia: la Agencia puede amonestar en vez de multar."
    elif primer_anio:
        nota = (
            "Primer año de vigencia, pero la amonestación en vez de multa es solo para empresas "
            "de menor tamaño."
        )
    if publico and sensibles:
        nota += " Con datos sensibles, la multa es la más alta."
    return FilaSimulada(
        deber=deber.id,
        decision=deber.decision,
        exigible=True,
        exigible_desde=desde,
        consecuencias=consecuencias,
        nota=nota,
    )


def simular(
    hechos: HechosIncidente,
    perfil: PerfilOrganizacion,
    fecha: date,
    escenario: Escenario,
    *,
    oiv: bool = False,
    menor_tamano: bool = False,
) -> Simulacion:
    """Simula un incidente conocido en `fecha` (a las 10:00, hora de Chile) en un escenario."""
    from zoneinfo import ZoneInfo

    conocimiento = datetime.combine(fecha, time(10, 0), tzinfo=ZoneInfo(ZONA))
    r = decidir_incidente(hechos, perfil, conocimiento, oiv)
    sensibles = "sensibles" in hechos.categorias_especiales
    deberes = [r.aviso_agencia, r.aviso_titulares, r.reporte_anci]
    filas = [_fila(d, escenario, fecha, perfil, oiv, menor_tamano, sensibles) for d in deberes]
    return Simulacion(escenario=escenario, fecha=fecha, filas=filas)


def comparar(
    hechos: HechosIncidente,
    perfil: PerfilOrganizacion,
    fecha: date,
    *,
    oiv: bool = False,
    menor_tamano: bool = False,
) -> list[Simulacion]:
    return [
        simular(hechos, perfil, fecha, e, oiv=oiv, menor_tamano=menor_tamano)
        for e in cargar_escenarios().values()
    ]


__all__ = ["Escenario", "Simulacion", "cargar_escenarios", "comparar", "extracto", "simular"]
