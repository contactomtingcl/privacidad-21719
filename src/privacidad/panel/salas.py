"""Demo pública: una copia limpia de los casos ficticios para cada participante («sala»).

Sin esto, la demo era una sola base compartida: lo que corregía o validaba un evaluador lo veía
el siguiente, y la cifra de correcciones mezclaba a todos. Ahora cada sesión nueva del panel en
modo demo recibe su propia sala:

- Una carpeta propia con su base SQLite, sembrada al crearla con `demo.sembrar` (los mismos
  casos ficticios y respuestas grabadas, con los relojes recién partidos). Sembrar toma
  centésimas de segundo y la base pesa menos de 100 KB.
- El enlace del canal y su QR, vistos desde el panel, llevan `?sala=…`: un reporte enviado desde
  otro dispositivo (por ejemplo, escaneando el QR con el teléfono) llega a la misma sala.
- «Reiniciar la sesión de demo» cierra la sesión y la siguiente visita recibe una sala nueva.

Las salas son copias desechables de datos ficticios: se borran enteras cuando llevan más de
`vida` sin uso o cuando hay más de `maximo`. Dentro de cada sala la evidencia sigue sin admitir
cambios ni borrados; lo que se borra es la copia completa, no anotaciones sueltas.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import shutil
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from ..canal.repositorio import NOMBRE_ARCHIVO, RepositorioCasos
from ..canal.servicio import CanalReporte

_ID_SALA = re.compile(r"^[A-Za-z0-9_-]{22}$")


def id_sala_valido(id_sala: str | None) -> bool:
    return bool(id_sala) and bool(_ID_SALA.fullmatch(id_sala or ""))


class SalasDemo:
    """Crea, abre y limpia las salas de la demo. Segura para usar desde varios hilos."""

    def __init__(
        self,
        carpeta: Path,
        fabrica: Callable[[RepositorioCasos], CanalReporte],
        sembrar: Callable[[CanalReporte], int],
        *,
        maximo: int = 200,
        abiertas: int = 32,
        vida: timedelta = timedelta(days=2),
        reloj: Callable[[], float] = time.time,
    ) -> None:
        self._carpeta = carpeta
        self._fabrica = fabrica
        self._sembrar = sembrar
        self._maximo = maximo
        self._max_abiertas = abiertas
        self._vida = vida.total_seconds()
        self._reloj = reloj
        self._abiertas: OrderedDict[str, CanalReporte] = OrderedDict()
        self._cerrojo = threading.Lock()
        carpeta.mkdir(parents=True, exist_ok=True)

    def _ruta(self, id_sala: str) -> Path:
        return self._carpeta / id_sala

    def existe(self, id_sala: str | None) -> bool:
        return id_sala_valido(id_sala) and (self._ruta(id_sala) / NOMBRE_ARCHIVO).is_file()  # type: ignore[arg-type]

    def crear(self) -> str:
        """Una sala nueva con los casos de la demo recién sembrados."""
        with self._cerrojo:
            self._limpiar()
            id_sala = secrets.token_urlsafe(16)
            canal = self._fabrica(RepositorioCasos(self._ruta(id_sala)))
            self._sembrar(canal)
            self._guardar_abierta(id_sala, canal)
            self._tocar(id_sala)
            return id_sala

    def canal(self, id_sala: str) -> CanalReporte | None:
        """El canal de una sala existente, o None si no existe (o ya se limpió)."""
        if not self.existe(id_sala):
            return None
        with self._cerrojo:
            canal = self._abiertas.get(id_sala)
            if canal is None:
                if not self.existe(id_sala):
                    return None
                canal = self._fabrica(RepositorioCasos(self._ruta(id_sala)))
                self._guardar_abierta(id_sala, canal)
            else:
                self._abiertas.move_to_end(id_sala)
            self._tocar(id_sala)
            return canal

    def cerrar(self) -> None:
        """Cierra las bases abiertas (al detener el servidor o al terminar una prueba)."""
        with self._cerrojo:
            while self._abiertas:
                _, canal = self._abiertas.popitem()
                canal._repo.cerrar()

    def cantidad(self) -> int:
        return sum(1 for _ in self._salas_en_disco())

    # --- interno (con el cerrojo tomado) -------------------------------------------------

    def _guardar_abierta(self, id_sala: str, canal: CanalReporte) -> None:
        self._abiertas[id_sala] = canal
        self._abiertas.move_to_end(id_sala)
        while len(self._abiertas) > self._max_abiertas:
            _, vieja = self._abiertas.popitem(last=False)
            vieja._repo.cerrar()

    def _tocar(self, id_sala: str) -> None:
        """Marca la sala como usada ahora (la fecha del archivo es su último uso)."""
        ahora = self._reloj()
        with contextlib.suppress(OSError):
            os.utime(self._ruta(id_sala) / NOMBRE_ARCHIVO, (ahora, ahora))

    def _salas_en_disco(self) -> list[tuple[float, str]]:
        salas = []
        for ruta in self._carpeta.iterdir():
            base = ruta / NOMBRE_ARCHIVO
            if id_sala_valido(ruta.name) and base.is_file():
                salas.append((base.stat().st_mtime, ruta.name))
        return sorted(salas)

    def _borrar(self, id_sala: str) -> None:
        canal = self._abiertas.pop(id_sala, None)
        if canal is not None:
            canal._repo.cerrar()
        shutil.rmtree(self._ruta(id_sala), ignore_errors=True)

    def _limpiar(self) -> None:
        """Borra las salas sin uso hace más de `vida` y, si aún sobran, las más antiguas, dejando
        espacio para la que se va a crear."""
        salas = self._salas_en_disco()
        limite = self._reloj() - self._vida
        vigentes = []
        for momento, id_sala in salas:
            if momento < limite:
                self._borrar(id_sala)
            else:
                vigentes.append(id_sala)
        while len(vigentes) >= self._maximo:
            self._borrar(vigentes.pop(0))


__all__ = ["SalasDemo", "id_sala_valido"]
