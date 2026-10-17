"""Almacén de casos del canal en SQLite (biblioteca estándar de Python).

Es el almacén del prototipo con datos ficticios: en memoria o en un archivo dentro de una
carpeta. El diseño final usa PostgreSQL (ver el documento de arquitectura); el resto del canal
solo conoce esta interfaz, así que el cambio queda en este archivo.

Cada vez que se guarda un caso, sus eventos nuevos se anotan en el registro de evidencia
encadenado (`evidencia.py`) dentro de la misma transacción: o quedan el caso y su evidencia, o
no queda ninguno.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import UTC
from pathlib import Path
from typing import Any

from . import evidencia
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
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS actividades ("
                "id TEXT PRIMARY KEY, id_organizacion TEXT NOT NULL, "
                "subida_utc TEXT NOT NULL, datos TEXT NOT NULL)"
            )
        evidencia.crear_tablas(self._con)
        if carpeta is not None:
            ruta.chmod(0o600)  # los casos contienen datos personales: solo el dueño lee

    def guardar(self, caso: Caso) -> None:
        if not id_caso_valido(caso.id):
            raise ValueError("Identificador de caso inválido")
        ingreso_utc = caso.ingreso.astimezone(UTC).isoformat()
        with self._cerrojo, self._con:
            evidencia.anotar_eventos(self._con, caso)
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

    def evidencia(
        self, id_caso: str | None = None, id_organizacion: str | None = None
    ) -> list[evidencia.Anotacion]:
        """Anotaciones de un caso, de una organización o de todas."""
        with self._cerrojo:
            return evidencia.leer(self._con, id_caso, id_organizacion)

    def verificar_evidencia(
        self, cabeza_esperada: str | None = None, id_organizacion: str | None = None
    ) -> evidencia.Verificacion:
        """Revisa la cadena de una organización (o la de todas) y la compara con la historia
        guardada en cada uno de sus casos."""
        with self._cerrojo:
            anotaciones = evidencia.leer(self._con, id_organizacion=id_organizacion)
        casos = self.listar()
        if id_organizacion is not None:
            casos = [c for c in casos if c.id_organizacion == id_organizacion]
        return evidencia.verificar_cadena(
            anotaciones,
            casos,
            cabeza_esperada,
            organizaciones=[id_organizacion] if id_organizacion else None,
        )

    # --- inventario: registros de actividades (sin los valores de las planillas) ---------

    def guardar_actividad(self, registro: Any) -> None:
        """Guarda un `inventario.servicio.RegistroActividad` (o lo reemplaza)."""
        with self._cerrojo, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO actividades (id, id_organizacion, subida_utc, datos) "
                "VALUES (?, ?, ?, ?)",
                (
                    registro.id,
                    registro.id_organizacion,
                    registro.subida.astimezone(UTC).isoformat(),
                    registro.model_dump_json(),
                ),
            )

    def actividades(self, id_organizacion: str) -> list[Any]:
        from ..inventario.servicio import RegistroActividad

        with self._cerrojo:
            filas = self._con.execute(
                "SELECT datos FROM actividades WHERE id_organizacion = ? ORDER BY subida_utc, id",
                (id_organizacion,),
            ).fetchall()
        return [RegistroActividad.model_validate_json(f[0]) for f in filas]

    def copiar_a(self, destino: Path) -> None:
        """Copia completa y consistente de la base (API de respaldo de SQLite). La usa la demo
        para mostrar una alteración real sin tocar la base verdadera."""
        with self._cerrojo:
            copia = sqlite3.connect(destino)
            try:
                self._con.backup(copia)
            finally:
                copia.close()
        destino.chmod(0o600)

    def cerrar(self) -> None:
        with self._cerrojo:
            self._con.close()
