"""Almacén de casos del canal en SQLite (biblioteca estándar de Python).

Es el almacén del prototipo con datos ficticios: en memoria o en un archivo dentro de una
carpeta. El diseño final usa PostgreSQL (ver el documento de arquitectura); el resto del canal
solo conoce esta interfaz, así que el cambio queda en este archivo.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import UTC
from pathlib import Path

from .modelos import Caso

_ID_CASO = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
NOMBRE_ARCHIVO = "casos.sqlite3"


def id_caso_valido(id_caso: str) -> bool:
    return bool(_ID_CASO.fullmatch(id_caso))


class RepositorioCasos:
    def __init__(self, carpeta: Path | None = None) -> None:
        self._cerrojo = threading.Lock()
        if carpeta is None:
            self._con = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            carpeta.mkdir(parents=True, exist_ok=True)
            ruta = carpeta / NOMBRE_ARCHIVO
            self._con = sqlite3.connect(ruta, check_same_thread=False)
        with self._con:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS casos ("
                "id TEXT PRIMARY KEY, id_organizacion TEXT NOT NULL, "
                "ingreso_utc TEXT NOT NULL, datos TEXT NOT NULL)"
            )
        if carpeta is not None:
            ruta.chmod(0o600)  # los casos contienen datos personales: solo el dueño lee

    def guardar(self, caso: Caso) -> None:
        if not id_caso_valido(caso.id):
            raise ValueError("Identificador de caso inválido")
        ingreso_utc = caso.ingreso.astimezone(UTC).isoformat()
        with self._cerrojo, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO casos (id, id_organizacion, ingreso_utc, datos) "
                "VALUES (?, ?, ?, ?)",
                (caso.id, caso.id_organizacion, ingreso_utc, caso.model_dump_json()),
            )

    def obtener(self, id_caso: str) -> Caso | None:
        if not id_caso_valido(id_caso):
            return None
        with self._cerrojo:
            fila = self._con.execute("SELECT datos FROM casos WHERE id = ?", (id_caso,)).fetchone()
        return Caso.model_validate_json(fila[0]) if fila else None

    def listar(self) -> list[Caso]:
        with self._cerrojo:
            filas = self._con.execute("SELECT datos FROM casos ORDER BY ingreso_utc, id").fetchall()
        return [Caso.model_validate_json(f[0]) for f in filas]

    def cerrar(self) -> None:
        with self._cerrojo:
            self._con.close()
