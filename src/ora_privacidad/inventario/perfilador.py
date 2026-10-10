"""Perfilado determinístico de planillas: qué datos personales tiene cada columna.

Combina dos señales y deja constancia de ambas:

1. El encabezado de la columna, comparado con el catálogo de `data/categorias.yaml`.
2. El formato de los valores: RUT válidos, correos, teléfonos y fechas.

Lo que estas señales no resuelven queda marcado como "requiere revisión" para que
lo interprete la IA y lo valide una persona. Este módulo no llama a ningún modelo.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, Field

from .. import guardia
from ..deteccion import CORREO, TELEFONO, edad_en, parsear_fecha
from ..rut import es_valido

RUTA_CATEGORIAS = Path(__file__).resolve().parents[3] / "data" / "categorias.yaml"
UMBRAL_FORMATO = 0.6  # fracción mínima de valores con un formato para considerarlo dominante
_CONTEXTO_MENORES = re.compile(r"\b(hijo|hija|hijos|hijas|nino|nina|ninos|menor|menores|alumno)\b")
_CONTEXTO_JURIDICO = re.compile(r"\b(empresa|razon social|proveedor|sociedad)\b")

Sensibilidad = bool | Literal["revisar"]
Confianza = Literal["alta", "media", "baja"]


class Fundamento(BaseModel):
    norma: str
    articulo: str
    fragmento: str


class Categoria(BaseModel):
    clave: str
    etiqueta: str
    palabras: list[str]
    sensible: Sensibilidad
    especial: list[str] = Field(default_factory=list)
    fundamento: Fundamento


class PerfilColumna(BaseModel):
    nombre: str
    categoria: str | None
    etiqueta: str | None
    sensible: Sensibilidad
    especiales: list[str]
    contexto_menores: bool = Field(
        description="El encabezado indica que los datos son de niños, niñas o adolescentes."
    )
    confianza: Confianza
    requiere_revision: bool
    evidencia: list[str]
    valores_no_vacios: int
    formatos: dict[str, float] = Field(description="Fracción de valores con cada formato.")


class ResumenMenores(BaseModel):
    columna: str
    referencia: date
    con_fecha_valida: int
    menores_de_14: int
    menores_de_16: int
    menores_de_18: int


class PerfilPlanilla(BaseModel):
    archivo: str
    filas: int
    columnas: list[PerfilColumna]
    menores: ResumenMenores | None
    columnas_personales: int
    categorias_sensibles: list[str]
    especiales: list[str]
    requieren_revision: list[str]


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


@lru_cache(maxsize=1)
def cargar_categorias(ruta: Path = RUTA_CATEGORIAS) -> dict[str, Categoria]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    return {
        clave: Categoria(clave=clave, **valores) for clave, valores in datos["categorias"].items()
    }


def _prioridad(cat: Categoria) -> int:
    if cat.clave == "parentesco":
        return 0  # es contexto, no el tipo de dato
    if cat.sensible is True:
        return 3
    if cat.sensible == "revisar":
        return 2
    return 1


def categoria_por_encabezado(encabezado: str) -> tuple[Categoria | None, str | None]:
    """Devuelve la categoría que mejor calza con el encabezado y la palabra que la activó.

    Si una frase encontrada contiene a otra ("previsión de salud" contiene "salud"),
    gana la más específica. Entre frases independientes, gana la categoría de mayor
    prioridad (sensibles primero) y luego la frase más larga.
    """
    norm = f" {_normalizar(encabezado)} "
    encontradas = [
        (cat, palabra, _normalizar(palabra))
        for cat in cargar_categorias().values()
        for palabra in cat.palabras
        if f" {_normalizar(palabra)} " in norm
    ]
    especificas = [
        e
        for e in encontradas
        if not any(f" {e[2]} " in f" {o[2]} " and e[2] != o[2] for o in encontradas)
    ]
    if not especificas:
        return None, None
    cat, palabra, _ = max(especificas, key=lambda e: (_prioridad(e[0]), len(e[2])))
    return cat, palabra


def _fecha_de_celda(valor: str) -> date | None:
    v = valor.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", v):  # celdas de fecha de Excel
        v = v[:10]
    return parsear_fecha(v)


def _formatos(valores: list[str]) -> dict[str, float]:
    if not valores:
        return {}
    n = len(valores)
    conteo = {
        "rut": sum(es_valido(v) for v in valores),
        "correo": sum(bool(CORREO.fullmatch(v.strip())) for v in valores),
        "telefono": sum(bool(TELEFONO.fullmatch(v.strip())) for v in valores),
        "fecha": sum(_fecha_de_celda(v) is not None for v in valores),
    }
    return {k: round(c / n, 3) for k, c in conteo.items() if c}


_CATEGORIA_POR_FORMATO = {
    "rut": "identificador_nacional",
    "correo": "correo",
    "telefono": "telefono",
}


def perfilar_columna(nombre: str, valores: list[str]) -> PerfilColumna:
    cats = cargar_categorias()
    no_vacios = [v for v in valores if v and v.strip()]
    formatos = _formatos(no_vacios)
    dominante = max(formatos, key=formatos.get) if formatos else None
    if dominante and formatos[dominante] < UMBRAL_FORMATO:
        dominante = None

    por_encabezado, palabra = categoria_por_encabezado(nombre)
    evidencia: list[str] = []
    if por_encabezado:
        evidencia.append(f"El encabezado contiene «{palabra}»")
    if dominante:
        evidencia.append(f"{formatos[dominante]:.0%} de los valores tiene formato de {dominante}")

    categoria: Categoria | None = por_encabezado
    confianza: Confianza = "media" if por_encabezado else "baja"

    if dominante in _CATEGORIA_POR_FORMATO:
        por_formato = cats[_CATEGORIA_POR_FORMATO[dominante]]
        if por_encabezado is None or por_encabezado.clave in (por_formato.clave, "parentesco"):
            categoria, confianza = por_formato, "alta"
        else:
            confianza = "baja"  # encabezado y valores no coinciden: lo decide una persona
            evidencia.append(
                f"Los valores parecen {por_formato.etiqueta.lower()}, "
                f"pero el encabezado sugiere {por_encabezado.etiqueta.lower()}"
            )
    elif dominante == "fecha" and por_encabezado is not None:
        confianza = "alta"

    contexto_menores = bool(_CONTEXTO_MENORES.search(_normalizar(nombre)))
    if contexto_menores:
        evidencia.append("El encabezado indica datos de hijos o hijas")
    if categoria is not None and _CONTEXTO_JURIDICO.search(_normalizar(nombre)):
        confianza = "baja"  # el RUT o el nombre de una empresa no es dato personal
        evidencia.append("Puede referirse a una persona jurídica, que no es titular de datos")

    return PerfilColumna(
        nombre=nombre,
        categoria=categoria.clave if categoria else None,
        etiqueta=categoria.etiqueta if categoria else None,
        sensible=categoria.sensible if categoria else False,
        especiales=list(categoria.especial) if categoria else [],
        contexto_menores=contexto_menores,
        confianza=confianza,
        requiere_revision=confianza == "baja"
        or (categoria is not None and categoria.sensible == "revisar"),
        evidencia=evidencia,
        valores_no_vacios=len(no_vacios),
        formatos=formatos,
    )


def _resumen_menores(
    df: pd.DataFrame, columnas: list[PerfilColumna], referencia: date
) -> ResumenMenores | None:
    candidatas = [c for c in columnas if c.categoria == "fecha_nacimiento"]
    if not candidatas:
        return None
    col = max(candidatas, key=lambda c: c.formatos.get("fecha", 0))
    edades = [
        edad_en(f, referencia) for v in df[col.nombre] if (f := _fecha_de_celda(v)) is not None
    ]
    return ResumenMenores(
        columna=col.nombre,
        referencia=referencia,
        con_fecha_valida=len(edades),
        menores_de_14=sum(e < 14 for e in edades),
        menores_de_16=sum(e < 16 for e in edades),
        menores_de_18=sum(e < 18 for e in edades),
    )


def leer_planilla(ruta: Path, hoja: str | int = 0) -> pd.DataFrame:
    if ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(ruta, sheet_name=hoja, dtype=str)
    elif ruta.suffix.lower() == ".csv":
        df = pd.read_csv(ruta, dtype=str, sep=None, engine="python")
    else:
        raise ValueError(f"Formato no soportado: {ruta.suffix}")
    return df.fillna("")


def perfilar_dataframe(
    df: pd.DataFrame,
    archivo: str = "",
    referencia: date | None = None,
    exigir_sinteticos: bool = True,
) -> PerfilPlanilla:
    """Perfila una tabla. Con `exigir_sinteticos`, la guardia rechaza datos posiblemente reales."""
    df = df.astype(str).fillna("")
    if exigir_sinteticos:
        guardia.exigir_sintetico(df.to_dict(orient="records"))
    referencia = referencia or date.today()
    columnas = [perfilar_columna(str(c), df[c].tolist()) for c in df.columns]
    personales = [c for c in columnas if c.categoria is not None]
    especiales = sorted({e for c in columnas for e in c.especiales})
    menores = _resumen_menores(df, columnas, referencia)
    if menores and menores.menores_de_18:
        especiales = sorted({*especiales, "menores"})
    return PerfilPlanilla(
        archivo=archivo,
        filas=len(df),
        columnas=columnas,
        menores=menores,
        columnas_personales=len(personales),
        categorias_sensibles=sorted({c.categoria for c in columnas if c.sensible is True}),
        especiales=especiales,
        requieren_revision=[c.nombre for c in columnas if c.requiere_revision],
    )


def perfilar_archivo(
    ruta: Path, referencia: date | None = None, exigir_sinteticos: bool = True
) -> PerfilPlanilla:
    return perfilar_dataframe(
        leer_planilla(ruta), ruta.name, referencia=referencia, exigir_sinteticos=exigir_sinteticos
    )
