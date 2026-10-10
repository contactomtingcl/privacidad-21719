"""Modelos de datos del corpus legal."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TipoArticulo = Literal["texto", "modificacion"]


class Norma(BaseModel):
    """Una norma indexada (ley, decreto) con su fuente oficial."""

    model_config = ConfigDict(frozen=True)

    clave: str = Field(description="Identificador estable, por ejemplo 'ley-19628'.")
    titulo: str
    publicacion: str
    fuente: str = Field(description="URL de la publicación oficial.")
    cobertura: str = Field(description="Qué parte de la norma está indexada.")


class Articulo(BaseModel):
    """Un artículo de una norma, con su texto tal como fue publicado."""

    model_config = ConfigDict(frozen=True)

    norma: str = Field(description="Clave de la norma a la que pertenece.")
    clave: str = Field(description="Clave normalizada: '14 sexies', '2', 'transitorio sexto'.")
    etiqueta: str = Field(description="Cómo aparece en el texto: 'Artículo 14 sexies'.")
    epigrafe: str | None = Field(default=None, description="Título corto del artículo, si tiene.")
    texto: str
    tipo: TipoArticulo = Field(
        default="texto",
        description=(
            "'texto' si es el texto completo del artículo; 'modificacion' si la norma "
            "solo publica cambios a un artículo existente."
        ),
    )

    @property
    def referencia(self) -> str:
        return f"{self.norma}:{self.clave}"


class ResultadoCita(BaseModel):
    """Resultado de verificar una cita legal contra el corpus."""

    norma: str
    articulo: str
    existe: bool
    fragmento_encontrado: bool | None = Field(
        default=None,
        description="None si no se pidió verificar un fragmento.",
    )
    texto: str | None = Field(
        default=None,
        description="Texto oficial del artículo; es lo único que se muestra al usuario.",
    )
    motivo: str | None = None

    @property
    def valida(self) -> bool:
        return self.existe and self.fragmento_encontrado is not False
