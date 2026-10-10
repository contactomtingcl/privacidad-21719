"""Piezas compartidas por las pruebas del canal (no son pruebas)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from cryptography.fernet import Fernet, MultiFernet

from privacidad import guardia
from privacidad.canal import CanalReporte, RepositorioCasos, cargar_organizaciones
from privacidad.canal.modelos import ZONA_CHILE
from privacidad.canal.reservado import cargar_llaves

SECRETO = b"secreto-de-prueba-que-supera-los-32-caracteres"
INICIO = datetime(2026, 12, 2, 10, 0, tzinfo=ZONA_CHILE)  # miércoles

SOLICITUD_CLARA = {
    "es_solicitud": True,
    "derechos": ["acceso"],
    "requiere_confirmacion": False,
    "resumen": "Quiere saber qué datos tienen.",
}
SOLICITUD_AMBIGUA = {
    "es_solicitud": True,
    "derechos": ["oposicion"],
    "requiere_confirmacion": True,
    "pregunta_confirmacion": "¿Quiere dejar de recibir publicidad o que borremos sus datos?",
    "resumen": "No quiere más correos.",
}
HECHOS_INCIDENTE = {
    "datos_personales": True,
    "vulneracion": "comunicacion_no_autorizada",
    "categorias_especiales": ["menores_14"],
    "riesgo_mitigado": False,
    "ciberincidente": "no",
    "interrupcion_servicio": False,
    "resumen": "Se envió una planilla a un proveedor por error.",
}
HECHOS_CIBERATAQUE = HECHOS_INCIDENTE | {
    "vulneracion": "acceso_no_autorizado",
    "ciberincidente": "si",
}


class RelojFijo:
    """Reloj que solo avanza cuando la prueba lo pide."""

    def __init__(self, inicio: datetime = INICIO) -> None:
        self.ahora = inicio

    def __call__(self) -> datetime:
        return self.ahora

    def avanzar(self, **kwargs: float) -> None:
        self.ahora += timedelta(**kwargs)


class ClienteFalso:
    """Imita a ClienteIA: devuelve la entrada de herramienta configurada para cada propósito."""

    def __init__(self, **entradas: dict[str, Any] | None) -> None:
        self.entradas = entradas
        self.llamadas: list[dict[str, Any]] = []

    def llamar(self, **kwargs: Any) -> Any:
        self.llamadas.append(kwargs)
        nombre = kwargs["forzar_herramienta"]
        entrada = self.entradas.get(nombre)
        if entrada is None:
            return SimpleNamespace(
                bloques_herramienta=[], costo_usd=0.001, motivo_termino="end_turn"
            )
        return SimpleNamespace(
            bloques_herramienta=[{"nombre": nombre, "entrada": dict(entrada)}], costo_usd=0.002
        )

    def lo_que_vio_la_ia(self) -> str:
        return "\n".join(
            m["content"] for llamada in self.llamadas for m in llamada["mensajes"]
        ) + "\n".join(llamada["sistema"] for llamada in self.llamadas)


class ClienteCaido:
    """La API no responde."""

    def llamar(self, **kwargs: Any) -> Any:
        raise ConnectionError("sin conexión")


def llaves_de_prueba() -> MultiFernet:
    return cargar_llaves(Fernet.generate_key())


def crear_canal(
    cliente: Any,
    *,
    con_reservado: bool = True,
    reloj: RelojFijo | None = None,
    repositorio: RepositorioCasos | None = None,
    llaves: MultiFernet | None = None,
):
    """Canal con las organizaciones de demostración. Devuelve (canal, reloj, llaves)."""
    llaves = llaves or llaves_de_prueba()
    reloj = reloj or RelojFijo()
    canal = CanalReporte(
        organizaciones=cargar_organizaciones(),
        repositorio=repositorio or RepositorioCasos(),
        cliente=cliente,
        secreto_enlaces=SECRETO,
        llaves_reservadas=llaves if con_reservado else None,
        reloj=reloj,
    )
    return canal, reloj, llaves


def rut_ficticio(semilla: int = 1) -> str:
    return guardia.rut_sintetico(semilla)
