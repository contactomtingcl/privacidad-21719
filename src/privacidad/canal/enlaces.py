"""Enlaces firmados del canal.

Cada organización tiene un enlace propio: `/canal/<organización>/<firma>`. La firma la calcula
`itsdangerous` (HMAC-SHA256 con un secreto del servidor), así que nadie puede inventar el enlace
de otra organización ni enviar reportes a un canal que no existe. Si el enlace se filtra, se
sube la versión de la organización y el enlace anterior deja de funcionar (el QR se imprime de
nuevo).

El secreto nunca se guarda en el repositorio: se lee de la variable de entorno
`PRIVACIDAD_SECRETO_ENLACES`.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from itsdangerous import Signer

VARIABLE_SECRETO = "PRIVACIDAD_SECRETO_ENLACES"
LARGO_MINIMO_SECRETO = 32
_SAL = "privacidad-21719/canal/v1"
_ID_ORGANIZACION = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def generar_secreto() -> str:
    """Secreto nuevo para guardar en la variable de entorno (se imprime solo en tu terminal)."""
    return secrets.token_urlsafe(48)


def guardar_secreto(ruta: Path) -> Path:
    """Guarda un secreto nuevo en un archivo que solo puede leer su dueño. No sobrescribe."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        f.write(generar_secreto() + "\n")
    return ruta


def secreto_desde_entorno() -> bytes:
    valor = os.environ.get(VARIABLE_SECRETO, "")
    if len(valor) < LARGO_MINIMO_SECRETO:
        raise RuntimeError(
            f"Falta la variable de entorno {VARIABLE_SECRETO} (mínimo {LARGO_MINIMO_SECRETO} "
            "caracteres). Se crea con: python -m privacidad.canal secreto"
        )
    return valor.encode("utf-8")


def id_organizacion_valido(id_organizacion: str) -> bool:
    return bool(_ID_ORGANIZACION.fullmatch(id_organizacion))


def _firmador(secreto: bytes) -> Signer:
    if len(secreto) < LARGO_MINIMO_SECRETO:
        raise ValueError("El secreto de enlaces es demasiado corto")
    return Signer(secreto, salt=_SAL, key_derivation="hmac", digest_method=hashlib.sha256)


def _mensaje(id_organizacion: str, version: int) -> bytes:
    if not id_organizacion_valido(id_organizacion):
        raise ValueError("Identificador de organización inválido")
    return f"{id_organizacion}:{version}".encode()


def firma_canal(id_organizacion: str, version: int, secreto: bytes) -> str:
    firmador = _firmador(secreto)
    return firmador.get_signature(_mensaje(id_organizacion, version)).decode("ascii")


def firma_valida(id_organizacion: str, version: int, firma: str, secreto: bytes) -> bool:
    if not id_organizacion_valido(id_organizacion):
        return False
    return _firmador(secreto).verify_signature(
        _mensaje(id_organizacion, version), firma.encode("utf-8", "replace")
    )


def _base_valida(base_url: str) -> str:
    partes = urlsplit(base_url)
    local = partes.hostname in {"localhost", "127.0.0.1", "::1"}
    if partes.scheme != "https" and not (partes.scheme == "http" and local):
        raise ValueError("La dirección base debe ser https (http solo para localhost)")
    if not partes.netloc or partes.query or partes.fragment:
        raise ValueError("Dirección base inválida")
    return base_url.rstrip("/")


def enlace_canal(base_url: str, id_organizacion: str, version: int, secreto: bytes) -> str:
    firma = firma_canal(id_organizacion, version, secreto)
    return f"{_base_valida(base_url)}/canal/{id_organizacion}/{firma}"
