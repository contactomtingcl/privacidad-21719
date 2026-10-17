"""Registro de evidencia encadenado: cada evento de un caso queda anotado y no se puede alterar
sin que se note.

Cómo funciona:

- **Una cadena por organización.** Cada organización tiene su propia numeración (1, 2, 3…) y
  cada anotación apunta a la anterior de la misma organización. Así un delegado verifica su
  cadena sin ver ni depender de la de otras: no sabe cuánta actividad tienen, y su huella final
  solo cambia cuando su organización registra algo (se puede guardar y comparar después).
- Cada anotación guarda su número, el caso, el tipo de evento, el momento y el detalle, más la
  huella (SHA-256, de `hashlib`, biblioteca estándar) de la anotación anterior. Su propia huella
  se calcula sobre todo eso. Si alguien cambia o borra una anotación del medio, las huellas
  dejan de calzar y la verificación lo muestra.
- La base de datos rechaza cambios y borrados en la tabla de evidencia (disparadores de
  SQLite). Quien tenga acceso directo al archivo podría quitarlos; por eso la garantía real es
  la verificación de la cadena, no los disparadores.
- La verificación también compara la cadena con los eventos guardados en cada caso: si alguien
  edita la historia de un caso, aparece la diferencia.
- Los eventos no llevan datos personales: antes de anotar, se revisa que el detalle no tenga
  RUT, correos ni teléfonos. Si los tiene, no se guarda nada.

Límite declarado: si alguien borra las últimas anotaciones de una organización, la cadena que
queda sigue siendo coherente. Para detectarlo hay que comparar con la huella final de esa
organización guardada en otra parte (el panel y el comando `evidencia` la muestran). El sello
de tiempo, previsto en el roadmap, cumple ese papel.

El contenido que se firma es JSON con llaves ordenadas, sin espacios y en UTF-8, para que la
misma anotación produzca siempre la misma huella.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from pydantic import BaseModel, Field

from ..deteccion import detectar
from .modelos import Caso

GENESIS = "0" * 64  # "anterior" de la primera anotación de cada organización
VERSION_ESQUEMA = 2  # 2: una cadena por organización (antes, una sola para todas)
TIPOS_PROHIBIDOS = ("rut", "correo", "telefono")  # las fechas son metadatos del caso

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS evidencia (
    fila INTEGER PRIMARY KEY,
    id_organizacion TEXT NOT NULL,
    n INTEGER NOT NULL,
    id_caso TEXT NOT NULL,
    tipo TEXT NOT NULL,
    momento TEXT NOT NULL,
    detalle TEXT NOT NULL,
    anterior TEXT NOT NULL,
    huella TEXT NOT NULL UNIQUE,
    UNIQUE (id_organizacion, n)
);
CREATE INDEX IF NOT EXISTS evidencia_por_caso ON evidencia (id_caso, n);
CREATE TRIGGER IF NOT EXISTS evidencia_sin_cambios BEFORE UPDATE ON evidencia
BEGIN SELECT RAISE(ABORT, 'El registro de evidencia no admite cambios'); END;
CREATE TRIGGER IF NOT EXISTS evidencia_sin_borrado BEFORE DELETE ON evidencia
BEGIN SELECT RAISE(ABORT, 'El registro de evidencia no admite borrados'); END;
"""


class ErrorEvidencia(Exception):
    """Se intentó anotar algo que rompería la evidencia (historia cambiada o datos personales)."""


class Anotacion(BaseModel):
    n: int  # número dentro de la cadena de su organización
    id_caso: str
    id_organizacion: str
    tipo: str
    momento: str  # ISO 8601 con zona horaria
    detalle: dict[str, Any] = Field(default_factory=dict)
    anterior: str
    huella: str


class Verificacion(BaseModel):
    integra: bool
    anotaciones: int
    # Huella de la última anotación de cada organización revisada (GENESIS si no tiene ninguna).
    cabezas: dict[str, str] = Field(default_factory=dict)
    problemas: list[str] = Field(default_factory=list)

    @property
    def cabeza(self) -> str:
        """La huella final cuando se revisó una sola organización (lo normal en el panel)."""
        if len(self.cabezas) > 1:
            raise ValueError("Se revisaron varias organizaciones: usa `cabezas`")
        return next(iter(self.cabezas.values()), GENESIS)


def _canonico(valor: Any) -> str:
    return json.dumps(
        valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def calcular_huella(
    *,
    n: int,
    id_caso: str,
    id_organizacion: str,
    tipo: str,
    momento: str,
    detalle: dict[str, Any],
    anterior: str,
) -> str:
    contenido = {
        "n": n,
        "id_caso": id_caso,
        "id_organizacion": id_organizacion,
        "tipo": tipo,
        "momento": momento,
        "detalle": detalle,
        "anterior": anterior,
    }
    return hashlib.sha256(_canonico(contenido).encode("utf-8")).hexdigest()


def _huella_de(a: Anotacion) -> str:
    return calcular_huella(**a.model_dump(exclude={"huella"}))


def _sin_datos_personales(detalle: dict[str, Any]) -> None:
    tipos = sorted({d.tipo for d in detectar(_canonico(detalle)) if d.tipo in TIPOS_PROHIBIDOS})
    if tipos:
        # No se muestra el valor: solo qué tipo de dato apareció.
        raise ErrorEvidencia(f"El evento contiene datos personales ({', '.join(tipos)})")


def crear_tablas(con: sqlite3.Connection) -> None:
    columnas = {f[1] for f in con.execute("PRAGMA table_info(evidencia)")}
    if columnas and "fila" not in columnas:
        # Base de la versión 1 (una sola cadena). No se convierte: reescribir la evidencia es
        # justo lo que no debe pasar. Solo hubo bases con datos ficticios.
        raise ErrorEvidencia(
            "Esta base usa el formato anterior de evidencia (una sola cadena). "
            "Usa una carpeta de datos nueva."
        )
    con.executescript(_ESQUEMA)


def _fila(f: tuple) -> Anotacion:
    return Anotacion(
        n=f[0],
        id_caso=f[1],
        id_organizacion=f[2],
        tipo=f[3],
        momento=f[4],
        detalle=json.loads(f[5]),
        anterior=f[6],
        huella=f[7],
    )


_COLUMNAS = "n, id_caso, id_organizacion, tipo, momento, detalle, anterior, huella"


def leer(
    con: sqlite3.Connection, id_caso: str | None = None, id_organizacion: str | None = None
) -> list[Anotacion]:
    """Anotaciones de un caso, de una organización o de todas, en el orden en que se anotaron."""
    condiciones, valores = [], []
    if id_caso is not None:
        condiciones.append("id_caso = ?")
        valores.append(id_caso)
    if id_organizacion is not None:
        condiciones.append("id_organizacion = ?")
        valores.append(id_organizacion)
    donde = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    filas = con.execute(f"SELECT {_COLUMNAS} FROM evidencia{donde} ORDER BY fila", valores)
    return [_fila(f) for f in filas.fetchall()]


def _eventos(caso: Caso) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (e["tipo"], e["momento"], e["detalle"])
        for e in (ev.model_dump(mode="json") for ev in caso.eventos)
    ]


def _de_anotacion(a: Anotacion) -> tuple[str, str, dict[str, Any]]:
    return (a.tipo, a.momento, a.detalle)


def anotar_eventos(con: sqlite3.Connection, caso: Caso) -> list[Anotacion]:
    """Anota los eventos nuevos del caso. Debe llamarse dentro de la transacción que guarda el
    caso, para que ambos queden o ninguno."""
    ya = leer(con, caso.id)
    eventos = _eventos(caso)
    if len(eventos) < len(ya) or any(
        _de_anotacion(a) != ev for a, ev in zip(ya, eventos, strict=False)
    ):
        raise ErrorEvidencia("La historia de un caso no se puede cambiar ni acortar")
    nuevos = eventos[len(ya) :]
    for _, _, detalle in nuevos:
        _sin_datos_personales(detalle)

    ultima = con.execute(
        "SELECT n, huella FROM evidencia WHERE id_organizacion = ? ORDER BY n DESC LIMIT 1",
        (caso.id_organizacion,),
    ).fetchone()
    n, anterior = ultima if ultima else (0, GENESIS)
    anotadas = []
    for tipo, momento, detalle in nuevos:
        n += 1
        huella = calcular_huella(
            n=n,
            id_caso=caso.id,
            id_organizacion=caso.id_organizacion,
            tipo=tipo,
            momento=momento,
            detalle=detalle,
            anterior=anterior,
        )
        con.execute(
            f"INSERT INTO evidencia ({_COLUMNAS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (n, caso.id, caso.id_organizacion, tipo, momento, _canonico(detalle), anterior, huella),
        )
        anotadas.append(
            Anotacion(
                n=n,
                id_caso=caso.id,
                id_organizacion=caso.id_organizacion,
                tipo=tipo,
                momento=momento,
                detalle=detalle,
                anterior=anterior,
                huella=huella,
            )
        )
        anterior = huella
    return anotadas


def _revisar_eslabones(anotaciones: list[Anotacion]) -> list[str]:
    """Revisa una cadena (la de una organización): numeración seguida, enlaces y huellas."""
    problemas: list[str] = []
    anterior = GENESIS
    for esperado, a in enumerate(sorted(anotaciones, key=lambda a: a.n), start=1):
        if a.n != esperado:
            problemas.append(f"Falta la anotación {esperado} (sigue la {a.n}): hubo un borrado")
        if a.anterior != anterior:
            problemas.append(f"La anotación {a.n} no apunta a la anterior: la cadena se cortó")
        if _huella_de(a) != a.huella:
            problemas.append(f"La anotación {a.n} fue modificada: su huella no calza")
        anterior = a.huella
    return problemas


def verificar_cadena(
    anotaciones: list[Anotacion],
    casos: list[Caso] | None = None,
    cabeza_esperada: str | None = None,
    organizaciones: list[str] | None = None,
) -> Verificacion:
    """Revisa la cadena de cada organización presente (o de las indicadas en `organizaciones`,
    que puede incluir una sin anotaciones) y, si se entregan, la compara con los casos y con una
    huella final guardada antes en otra parte."""
    por_org: dict[str, list[Anotacion]] = {o: [] for o in organizaciones or []}
    for a in anotaciones:
        por_org.setdefault(a.id_organizacion, []).append(a)
    varias = len(por_org) > 1

    def prefijo(org: str) -> str:
        return f"{org}: " if varias else ""

    problemas: list[str] = []
    cabezas: dict[str, str] = {}
    for org, propias in por_org.items():
        for p in _revisar_eslabones(propias):
            problemas.append(prefijo(org) + p)
        cabezas[org] = max(propias, key=lambda a: a.n).huella if propias else GENESIS
    if len(problemas) > 20:
        problemas = problemas[:20] + ["Hay más problemas; se muestran los primeros."]

    if casos is not None:
        por_caso: dict[str, list[Anotacion]] = {}
        for a in anotaciones:
            por_caso.setdefault(a.id_caso, []).append(a)
        ids = set()
        for caso in casos:
            ids.add(caso.id)
            registrados = [_de_anotacion(a) for a in por_caso.get(caso.id, [])]
            if registrados != _eventos(caso):
                problemas.append(
                    prefijo(caso.id_organizacion)
                    + f"La historia del caso {caso.id} no coincide con la evidencia"
                )
        for id_caso in sorted(set(por_caso) - ids):
            problemas.append(
                prefijo(por_caso[id_caso][0].id_organizacion)
                + f"Hay evidencia del caso {id_caso}, pero el caso ya no existe"
            )

    if cabeza_esperada is not None and cabeza_esperada not in {a.huella for a in anotaciones}:
        problemas.append(
            "La huella guardada aparte no está en la cadena: se borró o cambió el final"
        )
    return Verificacion(
        integra=not problemas,
        anotaciones=len(anotaciones),
        cabezas=cabezas,
        problemas=problemas,
    )
