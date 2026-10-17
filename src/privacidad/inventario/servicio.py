"""Inventario desde el panel: subir una planilla, armar su registro y proponer la versión mínima.

Qué se guarda y qué no:

- **La planilla no se guarda.** Se lee en memoria, pasa por la guardia de datos sintéticos, se
  perfila y se descarta. Queda solo el registro de la actividad de tratamiento (los 11 campos del
  DS 662, la clasificación de columnas y las alertas) y un resumen sin valores: filas, columnas y
  conteo de menores. Así el inventario no se convierte en otra copia de los datos.
- La IA ve solo encabezados y la forma de los valores (`actividad.muestras_seguras`), nunca los
  valores.
- Las planillas de ejemplo de la demo usan las respuestas de la IA grabadas en
  `resultados/inventario_demo.json`, si el archivo es idéntico (misma huella SHA-256) al del
  repositorio. Así la demo funciona sin conexión y sin costo, y queda dicho en pantalla.

Versión mínima (rediseño contrafactual): se quitan las columnas que el registro marca como
innecesarias y el **motor** vuelve a decidir qué habría que hacer si la planilla se filtrara. La
comparación usa solo cálculo y reglas, sin IA.
"""

from __future__ import annotations

import hashlib
import io
import json
import secrets
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from ..motor import HechosIncidente, ResultadoIncidente, decidir_incidente
from .actividad import (
    ActividadTratamiento,
    ClienteLLM,
    calcular_alertas,
    categorias_sensibles,
    construir_actividad,
)
from .perfilador import PerfilPlanilla, cargar_categorias, perfilar_dataframe

RAIZ = Path(__file__).resolve().parents[3]
DATOS_DEMO = RAIZ / "data" / "sinteticos" / "comercial-los-robles"
GRABADAS = RAIZ / "resultados" / "inventario_demo.json"
TAMANO_MAXIMO = 2 * 1024 * 1024  # 2 MB: planillas de una empresa mediana, no bases completas
EXTENSIONES = (".xlsx", ".csv")
LARGO_MAXIMO_DESCRIPCION = 600

OrigenIA = Literal["grabada", "ia", "sin_ia"]


class PlanillaInvalida(ValueError):
    """La planilla no se puede procesar. El mensaje es para la persona."""


class ColumnaResumen(BaseModel):
    nombre: str
    categoria: str | None
    especiales: list[str] = Field(default_factory=list)
    contexto_menores: bool = False


class ResumenPlanilla(BaseModel):
    """Lo que se conserva de la planilla: estructura y conteos, ningún valor."""

    filas: int
    columnas: list[ColumnaResumen]
    menores_de_14: int = 0
    menores_de_16: int = 0
    menores_de_18: int = 0


class RegistroActividad(BaseModel):
    id: str
    id_organizacion: str
    archivo: str
    huella: str  # SHA-256 del archivo subido, para reconocerlo sin guardarlo
    subida: datetime
    por: str
    origen_ia: OrigenIA
    actividad: ActividadTratamiento
    resumen: ResumenPlanilla
    validada_por: str | None = None
    validada_en: datetime | None = None


# --- lectura -----------------------------------------------------------------------------


def huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def leer_bytes(nombre: str, contenido: bytes) -> pd.DataFrame:
    extension = Path(nombre).suffix.lower()
    if extension not in EXTENSIONES:
        raise PlanillaInvalida("Sube una planilla Excel (.xlsx) o CSV.")
    if not contenido:
        raise PlanillaInvalida("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise PlanillaInvalida("La planilla supera los 2 MB. Sube una más pequeña.")
    try:
        if extension == ".xlsx":
            df = pd.read_excel(io.BytesIO(contenido), dtype=str)
        else:
            df = pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python")
    except Exception as e:  # pandas lanza tipos muy distintos según el formato
        raise PlanillaInvalida("No se pudo leer la planilla. Revisa que no esté dañada.") from e
    if df.empty or len(df.columns) == 0:
        raise PlanillaInvalida("La planilla no tiene filas.")
    return df.fillna("")


def _resumen(perfil: PerfilPlanilla) -> ResumenPlanilla:
    m = perfil.menores
    return ResumenPlanilla(
        filas=perfil.filas,
        columnas=[
            ColumnaResumen(
                nombre=c.nombre,
                categoria=c.categoria,
                especiales=c.especiales,
                contexto_menores=c.contexto_menores,
            )
            for c in perfil.columnas
        ],
        menores_de_14=m.menores_de_14 if m else 0,
        menores_de_16=m.menores_de_16 if m else 0,
        menores_de_18=m.menores_de_18 if m else 0,
    )


@lru_cache(maxsize=1)
def _grabadas() -> dict[str, dict[str, Any]]:
    """Respuestas grabadas por huella del archivo de ejemplo correspondiente."""
    if not GRABADAS.is_file():
        return {}
    salida = {}
    for a in json.loads(GRABADAS.read_text("utf-8")):
        ruta = DATOS_DEMO / a["archivo"]
        if ruta.is_file():
            salida[huella(ruta.read_bytes())] = a
    return salida


def ejemplos() -> list[str]:
    return sorted(p.name for p in DATOS_DEMO.iterdir() if p.suffix.lower() in EXTENSIONES)


def procesar(
    nombre: str,
    contenido: bytes,
    descripcion: str,
    *,
    id_organizacion: str,
    por: str,
    cliente: ClienteLLM | None,
    ahora: datetime,
) -> RegistroActividad:
    """Lee, revisa y arma el registro. Lanza `PlanillaInvalida` o `DatosNoSinteticosError`."""
    descripcion = " ".join((descripcion or "").split())
    if len(descripcion) > LARGO_MAXIMO_DESCRIPCION:
        raise PlanillaInvalida(
            f"La descripción admite hasta {LARGO_MAXIMO_DESCRIPCION} caracteres."
        )
    df = leer_bytes(nombre, contenido)
    archivo = Path(nombre).name
    # La guardia corre dentro de `perfilar_dataframe` (exigir_sinteticos=True).
    perfil = perfilar_dataframe(df, archivo, referencia=ahora.date())
    firma = huella(contenido)
    grabada = _grabadas().get(firma)
    if grabada is not None:
        actividad = ActividadTratamiento.model_validate(grabada)
        actividad.costo_ia_usd = 0.0
        # Las alertas no dependen de la IA: se recalculan con el código de hoy.
        actividad.alertas = calcular_alertas(perfil, actividad)
        origen: OrigenIA = "grabada"
    else:
        if not descripcion:
            raise PlanillaInvalida(
                "Describe en una o dos frases para qué se usa la planilla y con quién se comparte."
            )
        valores = {str(c): df[c].astype(str).tolist() for c in df.columns}
        actividad = construir_actividad(perfil, valores, descripcion, cliente)
        origen = "ia" if cliente is not None else "sin_ia"
    return RegistroActividad(
        id=secrets.token_urlsafe(9),
        id_organizacion=id_organizacion,
        archivo=archivo,
        huella=firma,
        subida=ahora,
        por=por,
        origen_ia=origen,
        actividad=actividad,
        resumen=_resumen(perfil),
    )


# --- versión mínima ------------------------------------------------------------------------


class Exposicion(BaseModel):
    columnas_personales: int
    datos_personales: int  # celdas: filas × columnas personales
    columnas_sensibles: list[str]
    identificadores: list[str]  # columnas con RUT u otro identificador nacional
    de_menores: list[str]  # columnas con datos de niños, niñas o adolescentes
    hechos: HechosIncidente
    si_se_filtra: ResultadoIncidente


class VersionMinima(BaseModel):
    quitadas: list[tuple[str, str]]  # (columna, por qué no se necesita)
    antes: Exposicion
    despues: Exposicion


def _exposicion(
    registro: RegistroActividad, quitar: set[str], perfil_org: str, oiv: bool
) -> Exposicion:
    cats = cargar_categorias()
    columnas = [c for c in registro.actividad.columnas if c.nombre not in quitar]
    resumen = {c.nombre: c for c in registro.resumen.columnas}
    personales = [c for c in columnas if c.categoria in cats]
    sensibles = categorias_sensibles(columnas)
    nombres_sensibles = [c.nombre for c in columnas if c.categoria in sensibles]
    financieros = any(
        "financiero" in cats[c.categoria].especial for c in columnas if c.categoria in cats
    )
    de_menores = [
        c.nombre for c in personales if resumen.get(c.nombre) and resumen[c.nombre].contexto_menores
    ]
    especiales: list[str] = []
    if nombres_sensibles:
        especiales.append("sensibles")
    if registro.resumen.menores_de_14 and de_menores:
        especiales.append("menores_14")
    if financieros:
        especiales.append("financieros")
    hechos = HechosIncidente(
        datos_personales=bool(personales),
        vulneracion="filtracion",
        categorias_especiales=especiales,  # type: ignore[arg-type]
        riesgo_mitigado=False,
        ciberincidente="no",
        interrupcion_servicio=False,
        titulares_aprox=registro.resumen.filas,
    )
    return Exposicion(
        columnas_personales=len(personales),
        datos_personales=len(personales) * registro.resumen.filas,
        columnas_sensibles=nombres_sensibles,
        identificadores=[c.nombre for c in personales if c.categoria == "identificador_nacional"],
        de_menores=de_menores,
        hechos=hechos,
        si_se_filtra=decidir_incidente(hechos, perfil_org, None, oiv),  # type: ignore[arg-type]
    )


def version_minima(
    registro: RegistroActividad, perfil_org: str, oiv: bool = False
) -> VersionMinima:
    """Quita lo que el registro marca como innecesario y vuelve a decidir con el motor."""
    quitadas = [
        (c.nombre, c.motivo_innecesaria or "No se necesita para la finalidad.")
        for c in registro.actividad.columnas
        if c.necesaria is False
    ]
    nombres = {n for n, _ in quitadas}
    return VersionMinima(
        quitadas=quitadas,
        antes=_exposicion(registro, set(), perfil_org, oiv),
        despues=_exposicion(registro, nombres, perfil_org, oiv),
    )


# --- relación con los casos ------------------------------------------------------------------

_VACIAS = {"de", "del", "la", "las", "los", "y", "con", "para", "por", "anio", "datos"}


def _palabra_principal(registro: RegistroActividad) -> str | None:
    """La primera palabra con sentido del nombre del archivo («paseo», «nomina», «clientes»).
    Solo esa: las demás («trabajadores», «marketing») aparecen en muchos mensajes."""
    stem = Path(registro.archivo).stem.lower().replace("-", "_")
    return next((p for p in stem.split("_") if len(p) >= 5 and p not in _VACIAS), None)


def planillas_mencionadas(
    texto: str, registros: list[RegistroActividad]
) -> list[RegistroActividad]:
    """Planillas del inventario que el mensaje parece nombrar (por ejemplo, «la planilla del
    paseo»). Es solo una sugerencia para el delegado: no cambia ningún hecho ni deber."""
    from ..canal.enrutamiento import normalizar

    normal = f" {normalizar(texto)} "
    salida = []
    for r in registros:
        palabra = _palabra_principal(r)
        if palabra and f" {palabra}" in normal:
            salida.append(r)
    return salida


__all__ = [
    "DATOS_DEMO",
    "TAMANO_MAXIMO",
    "PlanillaInvalida",
    "cargar_categorias",
    "RegistroActividad",
    "VersionMinima",
    "ejemplos",
    "planillas_mencionadas",
    "procesar",
    "version_minima",
]
