"""Usuarios del panel del delegado y límite de intentos de ingreso.

- Las contraseñas nunca se guardan: se guarda su huella con **scrypt** (`hashlib`, biblioteca
  estándar de Python; RFC 7914), con una sal aleatoria por usuario. Comparar en tiempo
  constante (`hmac.compare_digest`) evita revelar cuánto de la contraseña coincidía.
- Si el usuario no existe, se calcula igual una huella de relleno: así una respuesta rápida no
  revela qué usuarios existen.
- El archivo de usuarios lo puede leer solo su dueño (permisos 600) y nunca va al repositorio.
- No hay página de registro: los usuarios se crean con
  `python -m privacidad.canal usuario --datos CARPETA --org ORGANIZACION --usuario NOMBRE`.
- Tras 5 intentos fallidos en 15 minutos, el usuario queda bloqueado 15 minutos. El contador vive
  en memoria: se reinicia si se reinicia el servidor (límite declarado).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

NOMBRE_ARCHIVO = "usuarios.json"
LARGO_MINIMO = 12
LARGO_MAXIMO = 200
# Costo de scrypt: 2^15 iteraciones de memoria (32 MB) por intento. Las pruebas usan menos.
COSTO = {"n": 2**15, "r": 8, "p": 1}
_MEMORIA_MAXIMA = 128 * 1024 * 1024
_NOMBRE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


class ErrorUsuarios(ValueError):
    """El mensaje se muestra a quien administra; nunca incluye la contraseña."""


class Usuario(BaseModel):
    usuario: str
    id_organizacion: str
    rol: Literal["delegado"] = "delegado"
    sal: str
    huella: str
    n: int
    r: int
    p: int


def _derivar(contrasena: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        contrasena.encode("utf-8"), salt=sal, n=n, r=r, p=p, maxmem=_MEMORIA_MAXIMA, dklen=32
    )


def nombre_valido(usuario: str) -> bool:
    """Minúsculas, números, punto, guion o guion bajo; 3 a 32 caracteres. Sin @: un
    identificador, nunca un correo ni un nombre de persona."""
    return bool(_NOMBRE.fullmatch(usuario))


class RegistroUsuarios:
    def __init__(self, ruta: Path | None = None, *, costo: dict[str, int] | None = None) -> None:
        self._ruta = ruta
        self._costo = dict(costo or COSTO)
        self._cerrojo = threading.Lock()
        self._usuarios: dict[str, Usuario] = {}
        if ruta is not None and ruta.exists():
            datos = json.loads(ruta.read_text("utf-8"))
            self._usuarios = {u["usuario"]: Usuario(**u) for u in datos["usuarios"]}
        # Huella de relleno para usuarios inexistentes (mismo costo que una real).
        self._relleno = secrets.token_bytes(16)

    def _guardar(self) -> None:
        if self._ruta is None:
            return
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        contenido = json.dumps(
            {"usuarios": [u.model_dump() for u in self._usuarios.values()]},
            ensure_ascii=False,
            indent=2,
        )
        descriptor, temporal = tempfile.mkstemp(dir=self._ruta.parent, prefix=".usuarios-")
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as f:
                f.write(contenido)
            os.replace(temporal, self._ruta)
        except BaseException:
            Path(temporal).unlink(missing_ok=True)
            raise

    def crear(self, usuario: str, id_organizacion: str, contrasena: str) -> Usuario:
        if not nombre_valido(usuario):
            raise ErrorUsuarios(
                "El usuario debe tener de 3 a 32 caracteres: minúsculas, números, punto o guion."
            )
        if len(contrasena) < LARGO_MINIMO:
            raise ErrorUsuarios(f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres.")
        if len(contrasena) > LARGO_MAXIMO:
            raise ErrorUsuarios(f"La contraseña admite hasta {LARGO_MAXIMO} caracteres.")
        if usuario in contrasena.lower():
            raise ErrorUsuarios("La contraseña no puede contener el nombre de usuario.")
        with self._cerrojo:
            if usuario in self._usuarios:
                raise ErrorUsuarios("Ese usuario ya existe.")
            sal = secrets.token_bytes(16)
            nuevo = Usuario(
                usuario=usuario,
                id_organizacion=id_organizacion,
                sal=sal.hex(),
                huella=_derivar(contrasena, sal, **self._costo).hex(),
                **self._costo,
            )
            self._usuarios[usuario] = nuevo
            self._guardar()
        return nuevo

    def obtener(self, usuario: str) -> Usuario | None:
        return self._usuarios.get(usuario)

    def verificar(self, usuario: str, contrasena: str) -> Usuario | None:
        """El usuario si la contraseña es correcta; None en cualquier otro caso."""
        contrasena = contrasena[:LARGO_MAXIMO]
        encontrado = self._usuarios.get(usuario)
        if encontrado is None:
            _derivar(contrasena, self._relleno, **self._costo)
            return None
        calculada = _derivar(
            contrasena, bytes.fromhex(encontrado.sal), encontrado.n, encontrado.r, encontrado.p
        )
        return encontrado if hmac.compare_digest(calculada.hex(), encontrado.huella) else None

    def __len__(self) -> int:
        return len(self._usuarios)


class LimiteIntentos:
    """Bloquea un usuario tras varios intentos fallidos seguidos."""

    def __init__(
        self,
        *,
        maximo: int = 5,
        ventana: timedelta = timedelta(minutes=15),
        bloqueo: timedelta = timedelta(minutes=15),
        reloj: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._maximo = maximo
        self._ventana = ventana
        self._bloqueo = bloqueo
        self._reloj = reloj
        self._fallos: dict[str, list[datetime]] = {}
        self._hasta: dict[str, datetime] = {}
        self._cerrojo = threading.Lock()

    def bloqueado(self, usuario: str) -> bool:
        with self._cerrojo:
            hasta = self._hasta.get(usuario)
            if hasta and self._reloj() < hasta:
                return True
            self._hasta.pop(usuario, None)
            return False

    def fallo(self, usuario: str) -> None:
        with self._cerrojo:
            ahora = self._reloj()
            recientes = [t for t in self._fallos.get(usuario, []) if ahora - t < self._ventana]
            recientes.append(ahora)
            self._fallos[usuario] = recientes
            if len(recientes) >= self._maximo:
                self._hasta[usuario] = ahora + self._bloqueo
                self._fallos[usuario] = []

    def exito(self, usuario: str) -> None:
        with self._cerrojo:
            self._fallos.pop(usuario, None)
