"""Modo reservado: la identidad de quien reporta se guarda cifrada.

No hay criptografía propia: se usa Fernet, la receta de alto nivel de la biblioteca
`cryptography` (AES-128-CBC con autenticación HMAC-SHA256, con detección de alteraciones).
`MultiFernet` permite rotar la llave: la primera cifra y todas pueden descifrar.

La llave de cifrado nunca va en el repositorio ni en un chat: se crea en tu computador con
`python -m privacidad.canal llave` (queda en un archivo de solo lectura para ti) y el canal la
lee de la variable de entorno `PRIVACIDAD_LLAVE_RESERVADA` (o del archivo que indica
`PRIVACIDAD_LLAVE_RESERVADA_ARCHIVO`).

Límites que se declaran en el README:

- Con una llave simétrica, quien administra el servidor y tiene la llave puede abrir las
  identidades. Se reduce con una llave distinta de la de la IA y fuera del repositorio; pasar a
  un esquema donde el servidor solo pueda cifrar queda en el roadmap.
- El cifrado protege los campos de identidad del formulario. Si la persona escribe su nombre
  dentro del relato, ese texto no se cifra; los nombres no se detectan automáticamente.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

PREFIJO = "f1."
_BLOQUE = 256  # el largo del texto cifrado no revela el largo del nombre ni del contacto
VARIABLE_LLAVE = "PRIVACIDAD_LLAVE_RESERVADA"
VARIABLE_LLAVE_ARCHIVO = "PRIVACIDAD_LLAVE_RESERVADA_ARCHIVO"


class IdentidadReservadaError(ValueError):
    """No se pudo cifrar o descifrar la identidad."""


def guardar_llave(ruta: Path) -> Path:
    """Crea una llave nueva en un archivo que solo puede leer su dueño. No sobrescribe."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as f:
        f.write(Fernet.generate_key() + b"\n")
    return ruta


def cargar_llaves(valor: str | bytes) -> MultiFernet:
    """Una o varias llaves separadas por coma; la primera cifra y todas descifran."""
    texto = valor.decode("utf-8") if isinstance(valor, bytes) else valor
    partes = [p.strip() for p in texto.replace("\n", ",").split(",") if p.strip()]
    if not partes:
        raise IdentidadReservadaError("No hay ninguna llave")
    try:
        return MultiFernet([Fernet(p) for p in partes])
    except ValueError as e:
        raise IdentidadReservadaError("La llave no tiene el formato correcto") from e


def llaves_desde_entorno() -> MultiFernet | None:
    """None si el modo reservado no está configurado (el canal lo rechaza, nunca lo simula)."""
    directa = os.environ.get(VARIABLE_LLAVE)
    if directa:
        return cargar_llaves(directa)
    archivo = os.environ.get(VARIABLE_LLAVE_ARCHIVO)
    return cargar_llaves(Path(archivo).read_text("utf-8")) if archivo else None


def cifrar_identidad(llaves: MultiFernet, datos: dict[str, Any], id_caso: str) -> str:
    """Cifra la identidad. El identificador del caso viaja dentro, para que un texto cifrado
    no se pueda pegar en otro caso sin que se note al abrirlo."""
    plano = json.dumps(
        {"caso": id_caso, "identidad": datos}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    plano = plano.ljust(-(-len(plano) // _BLOQUE) * _BLOQUE, b" ")  # relleno que JSON ignora
    return PREFIJO + llaves.encrypt(plano).decode("ascii")


def descifrar_identidad(llaves: MultiFernet, sobre: str, id_caso: str) -> dict[str, Any]:
    """Solo para quien tiene la llave: abre la identidad guardada en un caso."""
    if not sobre.startswith(PREFIJO):
        raise IdentidadReservadaError("Formato de identidad reservada desconocido")
    try:
        contenido = json.loads(llaves.decrypt(sobre[len(PREFIJO) :].encode("ascii")))
    except (InvalidToken, ValueError) as e:
        raise IdentidadReservadaError("No se pudo abrir: llave equivocada o dato alterado") from e
    if contenido.get("caso") != id_caso:
        raise IdentidadReservadaError("Esta identidad pertenece a otro caso")
    return contenido["identidad"]
