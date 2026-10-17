"""Riesgo de infracción por planilla: qué calificación tendría cada conducta si no se corrige.

Las reglas (nivel, texto y fuente) están en `data/reglas/riesgos.yaml`; aquí solo las condiciones,
calculadas con el registro de la planilla, sin IA. No es una calificación de infracción: el
sistema no sabe, por ejemplo, si existe el consentimiento que la planilla supone. Muestra el
riesgo y qué lo corrige, con el artículo que lo respalda.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from ..motor.motor import RAIZ_REGLAS, Cita
from .actividad import categorias_sensibles
from .perfilador import cargar_categorias

Nivel = Literal["leve", "grave", "gravisima"]
ORDEN = {"leve": 0, "grave": 1, "gravisima": 2}
ETIQUETAS = {"leve": "Leve", "grave": "Grave", "gravisima": "Gravísima"}
BASES = {
    "consentimiento": "Consentimiento",
    "obligacion_financiera": "Obligación económica o financiera",
    "obligacion_legal": "Obligación legal",
    "contrato": "Contrato",
    "interes_legitimo": "Interés legítimo",
    "defensa_de_derechos": "Defensa de derechos",
}
INTERNOS = ("de la organización", "interno", "interna", "no informado")


class Hallazgo(BaseModel):
    regla: str
    nivel: Nivel
    agravante: Nivel | None = None
    titulo: str
    detalle: str  # qué se vio en la planilla
    si: str  # la conducta que tendría esa calificación
    corrige: str
    fuente: Cita
    fuente_agravante: Cita | None = None


class Riesgo(BaseModel):
    nivel: Nivel | None  # el más alto (sin contar agravantes); None si no hay hallazgos
    hallazgos: list[Hallazgo]
    sancion: str | None  # lo que arriesga el nivel más alto (art. 35)
    fuente_sancion: Cita | None


@lru_cache(maxsize=1)
def cargar_reglas_riesgo(ruta: Path | None = None) -> dict:
    return yaml.safe_load((ruta or RAIZ_REGLAS / "riesgos.yaml").read_text(encoding="utf-8"))


def _cita(f: dict) -> Cita:
    return Cita(norma=f["norma"], articulo=str(f["articulo"]), fragmento=f["fragmento"])


def _hallazgo(regla: str, detalle: str) -> Hallazgo:
    r = cargar_reglas_riesgo()["reglas"][regla]
    return Hallazgo(
        regla=regla,
        nivel=r["nivel"],
        agravante=r.get("agravante"),
        titulo=r["titulo"],
        detalle=detalle,
        si=r["si"],
        corrige=r["corrige"],
        fuente=_cita(r["fuente"]),
        fuente_agravante=_cita(r["fuente_agravante"]) if "fuente_agravante" in r else None,
    )


def _externos(valor: object) -> list[str]:
    lista = valor if isinstance(valor, list) else [valor] if valor else []
    return [str(d) for d in lista if d and not any(i in str(d).lower() for i in INTERNOS)]


def evaluar(registro, quitar: set[str] | None = None, perfil: str | None = None) -> Riesgo:
    """Riesgo de un `servicio.RegistroActividad`. Con `quitar`, como si esas columnas no
    estuvieran (versión mínima). Un organismo público no paga las multas del art. 35: se le
    aplica el art. 44 (multa al jefe superior del servicio)."""
    quitar = quitar or set()
    a = registro.actividad
    cats = cargar_categorias()
    columnas = [c for c in a.columnas if c.nombre not in quitar]
    personales = [c for c in columnas if c.categoria in cats]
    hallazgos: list[Hallazgo] = []

    innecesarias = [c.nombre for c in columnas if c.necesaria is False]
    if innecesarias:
        hallazgos.append(
            _hallazgo(
                "datos_innecesarios", "Columnas: " + ", ".join(f"«{n}»" for n in innecesarias) + "."
            )
        )

    resumen = {c.nombre: c for c in registro.resumen.columnas}
    de_menores = [
        c.nombre for c in personales if c.nombre in resumen and resumen[c.nombre].contexto_menores
    ]
    if de_menores and registro.resumen.menores_de_18:
        hallazgos.append(
            _hallazgo(
                "datos_de_menores",
                f"Hay datos de {registro.resumen.menores_de_18} menores de 18 años "
                f"({registro.resumen.menores_de_14} menores de 14).",
            )
        )

    base = a.base_licitud.valor if a.base_licitud.origen != "pendiente" else None
    sensibles = categorias_sensibles(columnas)
    if sensibles and base not in (None, "no_determinada", "consentimiento_expreso"):
        nombres = ", ".join(cats[s].etiqueta.lower() for s in sensibles)
        hallazgos.append(
            _hallazgo(
                "sensibles_sin_consentimiento_expreso",
                f"Datos sensibles ({nombres}) con base legal propuesta "
                f"«{BASES.get(base, base).lower()}», no consentimiento expreso.",
            )
        )
    if personales and base in (None, "no_determinada"):
        hallazgos.append(
            _hallazgo("sin_base_legal", "El registro no tiene una base legal identificada.")
        )

    externos = _externos(a.destinatarios.valor) if a.destinatarios.origen != "pendiente" else []
    if personales and externos:
        hallazgos.append(
            _hallazgo("comunicacion_a_terceros", "Se entregan a: " + "; ".join(externos) + ".")
        )

    nivel = max((h.nivel for h in hallazgos), key=ORDEN.__getitem__, default=None)
    sancion = cargar_reglas_riesgo()["sanciones_por_nivel"][nivel] if nivel else None
    texto = None
    if sancion:
        multa = sancion["texto"][0].lower() + sancion["texto"][1:]
        texto = f"Si se confirma una infracción {ETIQUETAS[nivel].lower()}: {multa}"
    fuente = _cita(sancion["fuente"]) if sancion else None
    if sancion and perfil == "organismo_publico":
        from ..motor.escenarios import sancion as sancion_escenarios

        s = sancion_escenarios("multa_organos_publicos")
        texto, fuente = (
            f"Si se confirma una infracción: {s.texto[0].lower()}{s.texto[1:]}",
            s.fuentes[0],
        )
    return Riesgo(
        nivel=nivel,
        hallazgos=sorted(hallazgos, key=lambda h: -ORDEN[h.nivel]),
        sancion=texto,
        fuente_sancion=fuente,
    )


__all__ = ["ETIQUETAS", "Hallazgo", "Riesgo", "cargar_reglas_riesgo", "evaluar"]
