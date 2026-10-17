"""Red de cascada: un proveedor reporta una vez y cada organización cliente recibe su caso.

Cómo funciona:

- Cada proveedor tiene un enlace propio, firmado (sal distinta de la de los canales de las
  organizaciones, para que una firma no sirva en el otro). Ahí reporta con un formulario
  cerrado: qué pasó, si afectó sistemas, si interrumpió el servicio y qué servicios afectó, más
  un texto libre que pasa por la guardia de datos sintéticos. La IA no participa.
- Por cada cliente que usa alguno de esos servicios se crea un caso en la organización
  cliente, con **sus** datos: qué datos le entrega al proveedor, de qué tipo y cuántas personas
  (declarado en `data/canal/proveedores.yaml`). Con eso y lo que reportó el proveedor, el motor
  de esa organización decide sus deberes y plazos con su propio perfil (un municipio tiene el
  reloj de la ANCI; una empresa privada, no).
- El plazo de cada cliente corre desde que el reporte le llega (cuando «se tuvo conocimiento»),
  no desde que el proveedor supo.
- Ningún cliente ve los casos de otro: cada caso vive en su organización, con su propio registro
  de lo actuado. El proveedor ve a qué clientes llegó, pero no sus decisiones.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Mapping
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from itsdangerous import Signer
from pydantic import BaseModel, Field

from .. import guardia
from ..motor import HechosIncidente, decidir_incidente
from ..motor.motor import CategoriaEspecial, Vulneracion
from .modelos import RAIZ_CANAL, Caso, Organizacion, OrigenCascada

SAL = "privacidad-21719.proveedor"
VULNERACIONES_PROVEEDOR = {
    "acceso_no_autorizado": "Alguien entró sin permiso a nuestros sistemas",
    "filtracion": "Se filtraron datos",
    "alteracion": "Se alteraron o cifraron datos (por ejemplo, ransomware)",
    "perdida": "Se perdieron datos",
    "destruccion": "Se destruyeron datos",
    "comunicacion_no_autorizada": "Se enviaron datos a quien no debía",
}
CIBER_PROVEEDOR = {"si": "Sí", "no": "No", "dudoso": "Todavía no se sabe"}
LARGO_MAXIMO_TEXTO = 2000


class ProveedorDesconocido(LookupError):
    pass


class ReporteInvalido(ValueError):
    """El reporte del proveedor no se puede aplicar. El mensaje es para la persona."""


class Cliente(BaseModel):
    org: str
    servicios: list[str]
    datos: str
    categorias: list[CategoriaEspecial] = Field(default_factory=list)
    titulares_aprox: int | None = None
    planilla: str | None = None


class Proveedor(BaseModel):
    id: str
    nombre: str
    contacto: str
    version_enlace: int = 1
    servicios: dict[str, str]
    clientes: list[Cliente]


class ResultadoCascada(BaseModel):
    codigo: str  # código del reporte del proveedor, común a todos sus casos
    proveedor: str
    recibido: datetime
    casos: dict[str, str]  # organización → código del caso en esa organización


@lru_cache(maxsize=1)
def cargar_proveedores(ruta: Path | None = None) -> dict[str, Proveedor]:
    datos = yaml.safe_load((ruta or RAIZ_CANAL / "proveedores.yaml").read_text("utf-8"))
    salida = {}
    for id_, p in datos["proveedores"].items():
        proveedor = Proveedor(id=id_, **p)
        guardia.exigir_sintetico({"contacto": proveedor.contacto})
        for c in proveedor.clientes:
            desconocidos = set(c.servicios) - set(proveedor.servicios)
            if desconocidos:
                raise ValueError(f"{id_}: servicios desconocidos {sorted(desconocidos)}")
        salida[id_] = proveedor
    return salida


def _firmador(secreto: bytes) -> Signer:
    return Signer(secreto, salt=SAL, key_derivation="hmac", digest_method=hashlib.sha256)


def firma_proveedor(proveedor: Proveedor, secreto: bytes) -> str:
    mensaje = f"{proveedor.id}:{proveedor.version_enlace}".encode()
    return _firmador(secreto).get_signature(mensaje).decode("ascii")


def firma_proveedor_valida(proveedor: Proveedor, firma: str, secreto: bytes) -> bool:
    mensaje = f"{proveedor.id}:{proveedor.version_enlace}".encode()
    return _firmador(secreto).verify_signature(mensaje, firma.encode("utf-8", "replace"))


def proveedores_de(id_organizacion: str) -> list[tuple[Proveedor, Cliente]]:
    """Los proveedores de la red que tratan datos de esta organización."""
    return [
        (p, c)
        for p in cargar_proveedores().values()
        for c in p.clientes
        if c.org == id_organizacion
    ]


class AccionesCascada:
    """Se mezcla con `CanalReporte`: usa su repositorio, su reloj, sus secretos y su
    enrutamiento (incluidos los avisos)."""

    _organizaciones: dict[str, Organizacion]
    _secreto: bytes
    _reloj: Callable[[], datetime]
    _nuevo_id: Callable[[], str]
    _repo: object
    _enrutar: Callable[[Caso, datetime], None]

    def proveedor_por_enlace(self, id_proveedor: str, firma: str) -> Proveedor:
        p = cargar_proveedores().get(id_proveedor)
        if p is None or not firma_proveedor_valida(p, firma, self._secreto):
            raise ProveedorDesconocido(id_proveedor)
        return p

    def enlace_proveedor(self, id_proveedor: str, base_url: str) -> str:
        p = cargar_proveedores()[id_proveedor]
        return f"{base_url.rstrip('/')}/proveedor/{p.id}/{firma_proveedor(p, self._secreto)}"

    def recibir_reporte_proveedor(
        self,
        id_proveedor: str,
        texto: str,
        *,
        servicios: list[str],
        vulneracion: Vulneracion,
        ciberincidente: Literal["si", "no", "dudoso"],
        interrupcion_servicio: bool,
    ) -> ResultadoCascada:
        proveedor = cargar_proveedores().get(id_proveedor)
        if proveedor is None:
            raise ProveedorDesconocido(id_proveedor)
        texto = " ".join((texto or "").split())
        if len(texto) < 10:
            raise ReporteInvalido("Describa en una o dos frases qué ocurrió.")
        if len(texto) > LARGO_MAXIMO_TEXTO:
            raise ReporteInvalido(f"El texto admite hasta {LARGO_MAXIMO_TEXTO} caracteres.")
        servicios = [s for s in dict.fromkeys(servicios) if s in proveedor.servicios]
        if not servicios:
            raise ReporteInvalido("Indique qué servicio se vio afectado.")
        guardia.exigir_sintetico({"texto": texto})

        ahora = self._reloj()  # para cada cliente, aquí empieza «se tuvo conocimiento»
        codigo = secrets.token_urlsafe(9)
        casos: dict[str, str] = {}
        for cliente in proveedor.clientes:
            if not set(cliente.servicios) & set(servicios):
                continue
            org = self._organizaciones.get(cliente.org)
            if org is None:
                continue
            hechos = HechosIncidente(
                datos_personales=True,
                vulneracion=vulneracion,
                categorias_especiales=list(cliente.categorias),
                riesgo_mitigado=False,
                ciberincidente=ciberincidente,
                interrupcion_servicio=interrupcion_servicio,
                titulares_aprox=cliente.titulares_aprox,
            )
            afectados = [proveedor.servicios[s] for s in servicios if s in cliente.servicios]
            caso = Caso(
                id=self._nuevo_id(),
                id_organizacion=org.id,
                tipo="aviso_proveedor",
                ingreso=ahora,
                texto=texto,
                estado="interpretado",
                resumen_ia=f"{proveedor.nombre}: incidente en {', '.join(afectados).lower()}",
                cascada=OrigenCascada(
                    codigo=codigo,
                    proveedor=proveedor.id,
                    nombre_proveedor=proveedor.nombre,
                    servicios=afectados,
                    datos=cliente.datos,
                    planilla=cliente.planilla,
                ),
                hechos_incidente=hechos,
            )
            caso.resultado_incidente = decidir_incidente(
                hechos, org.perfil, ahora, org.operador_importancia_vital
            )
            r = caso.resultado_incidente
            caso.registrar(
                "recibido", ahora, tipo="aviso_proveedor", reservado=False, con_identidad=False
            )
            caso.registrar(
                "cascada",
                ahora,
                codigo=codigo,
                proveedor=proveedor.id,
                servicios=servicios,
                aviso_agencia=r.aviso_agencia.decision,
                aviso_titulares=r.aviso_titulares.decision,
                reporte_anci=r.reporte_anci.decision,
            )
            self._enrutar(caso, ahora)
            self._repo.guardar(caso)  # type: ignore[attr-defined]
            casos[org.id] = caso.id
        if not casos:
            raise ReporteInvalido("Ningún cliente usa ese servicio.")
        return ResultadoCascada(codigo=codigo, proveedor=proveedor.id, recibido=ahora, casos=casos)


def nombres_clientes(resultado: ResultadoCascada, organizaciones: Mapping[str, Organizacion]):
    return [organizaciones[o].nombre for o in resultado.casos if o in organizaciones]


__all__ = [
    "AccionesCascada",
    "Cliente",
    "Proveedor",
    "ProveedorDesconocido",
    "ReporteInvalido",
    "ResultadoCascada",
    "cargar_proveedores",
    "proveedores_de",
]
