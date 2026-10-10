"""Cliente mínimo de la API de Claude con medición de costo y tiempo por llamada."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RUTA_PRECIOS = Path(__file__).resolve().parents[3] / "data" / "precios_modelos.yaml"
MODELO_RAPIDO = "claude-haiku-5-5"  # clasificar columnas y tareas en volumen
MODELO_EXTRACCION = "claude-sonnet-5-5"  # extracción estructurada con herramientas


@lru_cache(maxsize=1)
def _precios() -> dict[str, dict[str, float]]:
    return yaml.safe_load(RUTA_PRECIOS.read_text(encoding="utf-8"))["modelos"]


def costo_usd(modelo: str, tokens_entrada: int, tokens_salida: int) -> float:
    """Costo de una llamada según la tabla de precios publicada."""
    p = _precios()[modelo]
    limite = p.get("limite_tramo_tokens")
    if limite and tokens_entrada > limite:
        entrada, salida = p["entrada_sobre_limite"], p["salida_sobre_limite"]
    else:
        entrada, salida = p["entrada"], p["salida"]
    return round((tokens_entrada * entrada + tokens_salida * salida) / 1_000_000, 8)


@dataclass
class RespuestaIA:
    modelo: str
    texto: str
    bloques_herramienta: list[dict[str, Any]] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    latencia_ms: int = 0


class ClienteIA:
    """Envuelve la API de Claude. Lee la llave desde ANTHROPIC_API_KEY.

    Cada llamada se puede anotar en un registro JSONL con modelo, tokens, costo y
    propósito, nunca con el contenido enviado.
    """

    def __init__(self, registro: Path | None = None) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("Falta la variable de entorno ANTHROPIC_API_KEY")
        import anthropic  # dependencia opcional: pip install -e ".[ia]"

        self._api = anthropic.Anthropic()
        self._registro = registro

    def llamar(
        self,
        *,
        modelo: str,
        sistema: str,
        mensajes: list[dict[str, Any]],
        herramientas: list[dict[str, Any]] | None = None,
        forzar_herramienta: str | None = None,
        max_tokens: int = 1024,
        proposito: str = "",
    ) -> RespuestaIA:
        inicio = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": modelo,
            "system": sistema,
            "messages": mensajes,
            "max_tokens": max_tokens,
        }
        if herramientas:
            kwargs["tools"] = herramientas
        if forzar_herramienta:
            kwargs["tool_choice"] = {"type": "tool", "name": forzar_herramienta}
        r = self._api.messages.create(**kwargs)
        latencia = int((time.perf_counter() - inicio) * 1000)

        texto = "".join(b.text for b in r.content if b.type == "text")
        herramienta = [
            {"nombre": b.name, "entrada": b.input} for b in r.content if b.type == "tool_use"
        ]
        respuesta = RespuestaIA(
            modelo=r.model,
            texto=texto,
            bloques_herramienta=herramienta,
            tokens_entrada=r.usage.input_tokens,
            tokens_salida=r.usage.output_tokens,
            costo_usd=costo_usd(modelo, r.usage.input_tokens, r.usage.output_tokens),
            latencia_ms=latencia,
        )
        self._anotar(respuesta, proposito)
        return respuesta

    def _anotar(self, respuesta: RespuestaIA, proposito: str) -> None:
        if not self._registro:
            return
        fila = {
            k: v for k, v in asdict(respuesta).items() if k not in ("texto", "bloques_herramienta")
        }
        fila |= {"proposito": proposito, "fecha": datetime.now(UTC).isoformat(timespec="seconds")}
        self._registro.parent.mkdir(parents=True, exist_ok=True)
        with self._registro.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
