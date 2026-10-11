"""Demo pública del panel: casos ficticios con respuestas de la IA grabadas.

Los casos de `data/demo/casos.yaml` entran por el mismo canal que un reporte real (guardia,
enmascarado, motor, enrutamiento y evidencia), con dos diferencias declaradas:

- La IA no se llama: un cliente grabado devuelve la respuesta guardada para ese texto, y cada
  evento la marca con el modelo "respuesta-grabada". Así la demo funciona sin conexión ni costo.
- La hora de ingreso se adelanta unos minutos u horas, para que los relojes se vean corriendo.

Los reportes que llegan después, en vivo, usan la IA real si hay llave configurada.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from ..canal.delegado import por_resolver
from ..canal.modelos import ahora_chile
from ..canal.servicio import CanalReporte

RAIZ_DEMO = Path(__file__).resolve().parents[3] / "data" / "demo"
MODELO_GRABADO = "respuesta-grabada"
USUARIO_SEMILLA = "delegado-demo"


class ClienteGrabado:
    """Imita al cliente de IA: responde con la entrada grabada cuyo texto coincide."""

    def __init__(self, respuestas: list[tuple[str, dict[str, Any] | None]]) -> None:
        self._respuestas = respuestas

    def llamar(self, **kwargs: Any) -> Any:
        mensajes = " ".join(m["content"] for m in kwargs.get("mensajes", []))
        normalizado = " ".join(mensajes.split())
        for clave, ia in self._respuestas:
            if clave in normalizado:
                if ia is None:
                    raise ConnectionError("respuesta grabada: la IA no respondió")
                if ia["herramienta"] != kwargs.get("forzar_herramienta"):
                    break
                return SimpleNamespace(
                    bloques_herramienta=[
                        {"nombre": ia["herramienta"], "entrada": dict(ia["entrada"])}
                    ],
                    costo_usd=0.0,
                )
        return SimpleNamespace(bloques_herramienta=[], costo_usd=0.0, motivo_termino="end_turn")


def _clave(texto: str) -> str:
    """Un trozo del texto sin datos detectables, para reconocerlo ya enmascarado."""
    return " ".join(texto.split())[:60]


class _RelojAtrasado:
    def __init__(self) -> None:
        self.momento: datetime | None = None

    def __call__(self) -> datetime:
        return self.momento or ahora_chile()


def sembrar(canal: CanalReporte, ruta: Path | None = None) -> int:
    """Carga los casos de la demo en el repositorio del canal. Devuelve cuántos cargó."""
    datos = yaml.safe_load((ruta or RAIZ_DEMO / "casos.yaml").read_text("utf-8"))["casos"]
    grabado = ClienteGrabado([(_clave(c["texto"]), c.get("ia")) for c in datos])
    reloj = _RelojAtrasado()
    semilla = CanalReporte(
        organizaciones=canal._organizaciones,
        repositorio=canal._repo,
        cliente=grabado,
        secreto_enlaces=canal._secreto,
        llaves_reservadas=canal._llaves,
        reloj=reloj,
        modelo_solicitudes=MODELO_GRABADO,
        modelo_incidentes=MODELO_GRABADO,
        enrutamiento=canal._enrutamiento,
    )
    ahora = ahora_chile()
    for c in sorted(datos, key=lambda c: -c["hace_minutos"]):
        reloj.momento = ahora - timedelta(minutes=c["hace_minutos"])
        texto = " ".join(c["texto"].split())
        if c["tipo"] == "solicitud":
            caso = semilla.recibir_solicitud(
                c["org"], texto, nombre=c["nombre"], contacto=c["contacto"]
            )
        else:
            caso = semilla.recibir_incidente(
                c["org"],
                texto,
                tipo=c["tipo"],
                reservado=bool(c.get("reservado")) and canal.reservado_disponible,
                nombre=c.get("nombre"),
                contacto=c.get("contacto"),
            )
        if c.get("validar"):
            reloj.momento = reloj.momento + timedelta(minutes=12)
            for deber in por_resolver(caso):
                semilla.resolver_deber(
                    c["org"],
                    caso.id,
                    deber.id,
                    "no",
                    motivo="criterio_delegado",
                    por=USUARIO_SEMILLA,
                )
            semilla.validar(c["org"], caso.id, por=USUARIO_SEMILLA)
    return len(datos)
