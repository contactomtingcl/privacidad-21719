"""Lectura de textos legales y separación por artículo.

Los archivos de `data/normas/` tienen una cabecera de metadatos (`# clave: valor`)
seguida del texto oficial. Este módulo los separa en artículos sin interpretar
su contenido: el texto de cada artículo es el publicado.

La Ley 21.719 tiene una estructura especial: su "Artículo primero" contiene el
nuevo texto de la Ley 19.628. Por eso, al leerla se generan tres normas:

- ``ley-19628``: artículos de la Ley 19.628 según el texto que fija la Ley 21.719.
- ``ley-21719``: artículos propios de la Ley 21.719 y sus disposiciones transitorias.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .modelos import Articulo, Norma, TipoArticulo

_SUFIJOS = r"bis|ter|qu[áa]ter|quinquies|sexies|septies|octies|nonies|decies"
_ORDINALES = "primero|segundo|tercero|cuarto|quinto|sexto|s[ée]ptimo|octavo|noveno|d[ée]cimo"

_ENCABEZADO = re.compile(
    rf"""^\s*"?\s*Art[íi]culo\s+
        (?P<num>\d+\s*[°º]?(?:\s+(?:{_SUFIJOS}))?|(?:{_ORDINALES}))
        (?:\s+transitorio)?
        \s*\.\s*-?\s*
        (?P<resto>.*)$""",
    re.VERBOSE | re.IGNORECASE,
)
_MODIFICACION = re.compile(r"^\s*\d+\)\s+")
_REF_ARTICULO = re.compile(
    rf"art[íi]culo\s+(\d+\s*[°º]?(?:\s+(?:{_SUFIJOS}))?)(\s+transitorio)?",
    re.IGNORECASE,
)
_TITULO = re.compile(r'^\s*"?\s*(T[íi]tulo|P[áa]rrafo)\s', re.IGNORECASE)
_TRANSITORIAS = re.compile(r"^\s*DISPOSICIONES\s+TRANSITORIAS\s*$", re.IGNORECASE)
_FIN = re.compile(r"^\s*Habiéndose cumplido con lo establecido")
_META = re.compile(r"^#\s*(\w+):\s*(.*)$")


def normalizar_clave(texto: str) -> str:
    """Normaliza la clave de un artículo: '14 Sexies', '14 sexies' → '14 sexies'.

    Quita grados (°, º), tildes y espacios repetidos, y pasa a minúsculas.
    """
    t = texto.replace("°", "").replace("º", "")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _limpiar_linea(linea: str) -> str:
    return linea.strip().lstrip('"').strip()


def _cerrar_texto(lineas: list[str]) -> str:
    texto = "\n".join(lineas).strip()
    # El texto que la Ley 21.719 inserta en la Ley 19.628 va entre comillas y cierra con '".'
    # (fin del artículo, comilla de cierre, punto de la oración modificatoria). Como la
    # comilla de apertura ya se quitó, una comilla final sin pareja se elimina con su punto.
    if texto.count('"') % 2 == 1:
        texto = re.sub(r'"\.?\s*$', "", texto).rstrip()
    return texto


def _epigrafe(resto: str) -> str | None:
    """Primera oración del encabezado si es corta, p. ej. 'Derecho de acceso'."""
    m = re.match(r"^([^.]{3,120})\.\s", resto + " ")
    return m.group(1).strip() if m else None


@dataclass
class _Borrador:
    norma: str
    clave: str
    etiqueta: str
    epigrafe: str | None
    tipo: TipoArticulo
    lineas: list[str] = field(default_factory=list)

    def cerrar(self) -> Articulo:
        return Articulo(
            norma=self.norma,
            clave=self.clave,
            etiqueta=self.etiqueta,
            epigrafe=self.epigrafe,
            texto=_cerrar_texto(self.lineas),
            tipo=self.tipo,
        )


def leer_metadatos(lineas: list[str]) -> dict[str, str]:
    meta: dict[str, str] = {}
    for linea in lineas:
        m = _META.match(linea)
        if not m:
            break
        meta[m.group(1)] = m.group(2).strip()
    return meta


def _norma_desde_meta(meta: dict[str, str], clave: str | None = None) -> Norma:
    faltan = {"norma", "titulo", "publicacion", "fuente", "cobertura"} - meta.keys()
    if faltan:
        raise ValueError(f"Faltan metadatos en la cabecera: {sorted(faltan)}")
    return Norma(
        clave=clave or meta["norma"],
        titulo=meta["titulo"],
        publicacion=meta["publicacion"],
        fuente=meta["fuente"],
        cobertura=meta["cobertura"],
    )


def leer_norma_simple(ruta: Path) -> tuple[Norma, list[Articulo]]:
    """Lee una norma cuyo texto es una secuencia de artículos (decretos, leyes simples)."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    meta = leer_metadatos(lineas)
    norma = _norma_desde_meta(meta)
    articulos: list[Articulo] = []
    actual: _Borrador | None = None
    for linea in lineas:
        if _META.match(linea) or not linea.strip():
            continue
        m = _ENCABEZADO.match(linea)
        if m:
            if actual:
                articulos.append(actual.cerrar())
            clave = normalizar_clave(m.group("num"))
            actual = _Borrador(
                norma=norma.clave,
                clave=clave,
                etiqueta=f"Artículo {clave}",
                epigrafe=_epigrafe(m.group("resto")),
                tipo="texto",
                lineas=[_limpiar_linea(linea)],
            )
        elif actual:
            actual.lineas.append(_limpiar_linea(linea))
    if actual:
        articulos.append(actual.cerrar())
    return norma, articulos


def leer_ley_21719(ruta: Path) -> tuple[list[Norma], list[Articulo]]:
    """Lee la Ley 21.719 y separa el nuevo texto de la Ley 19.628 de los artículos propios."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    meta = leer_metadatos(lineas)
    norma_21719 = _norma_desde_meta(meta)
    norma_19628 = Norma(
        clave="ley-19628",
        titulo=(
            "Ley N° 19.628, sobre protección de los datos personales, "
            "según el texto que fija el artículo primero de la Ley N° 21.719"
        ),
        publicacion=norma_21719.publicacion,
        fuente=norma_21719.fuente,
        cobertura=(
            "artículos con texto completo fijado por la Ley 21.719; los artículos que la ley "
            "solo modifica (2, 17, 18 y 19) se indexan como 'modificacion'"
        ),
    )

    por_clave: dict[tuple[str, str], Articulo] = {}
    orden: list[tuple[str, str]] = []

    def guardar(art: Articulo) -> None:
        llave = (art.norma, art.clave)
        previo = por_clave.get(llave)
        if previo is None:
            orden.append(llave)
            por_clave[llave] = art
        elif previo.tipo == "modificacion" and art.tipo == "texto":
            por_clave[llave] = art  # el texto completo reemplaza la instrucción de cambio
        elif previo.tipo == "modificacion" and art.tipo == "modificacion":
            por_clave[llave] = art.model_copy(update={"texto": previo.texto + "\n" + art.texto})
        elif art.tipo == "texto":
            raise ValueError(f"Artículo duplicado en el corpus: {llave}")

    actual: _Borrador | None = None
    en_primero = False  # dentro del "Artículo primero" (texto de la Ley 19.628)
    en_transitorias = False
    en_encabezado = False

    def cerrar_actual() -> None:
        nonlocal actual
        if actual:
            guardar(actual.cerrar())
        actual = None

    for linea in lineas:
        if _META.match(linea) or not linea.strip():
            continue
        if _FIN.match(linea):
            break
        if _TRANSITORIAS.match(linea):
            cerrar_actual()
            en_primero, en_transitorias, en_encabezado = False, True, False
            continue

        m = _ENCABEZADO.match(linea)
        if m:
            cerrar_actual()
            en_encabezado = False
            num = m.group("num")
            es_ordinal = not num[0].isdigit()
            if es_ordinal:
                ordinal = normalizar_clave(num)
                if ordinal == "primero" and not en_transitorias:
                    en_primero = True  # contenedor: no es un artículo en sí
                    continue
                en_primero = False
                clave = f"transitorio {ordinal}" if en_transitorias else ordinal
                etiqueta = (
                    f"Artículo {ordinal} transitorio" if en_transitorias else f"Artículo {ordinal}"
                )
                norma = norma_21719.clave
            else:
                clave = normalizar_clave(num)
                etiqueta = f"Artículo {clave}"
                norma = norma_19628.clave
            actual = _Borrador(
                norma=norma,
                clave=clave,
                etiqueta=etiqueta,
                epigrafe=_epigrafe(m.group("resto")),
                tipo="texto",
                lineas=[_limpiar_linea(linea)],
            )
            continue

        if en_primero and _MODIFICACION.match(linea):
            cerrar_actual()
            en_encabezado = False
            ref = _REF_ARTICULO.search(linea)
            if ref and not ref.group(2):  # se ignoran referencias a artículos transitorios
                clave = normalizar_clave(ref.group(1))
                actual = _Borrador(
                    norma=norma_19628.clave,
                    clave=clave,
                    etiqueta=f"Artículo {clave}",
                    epigrafe=None,
                    tipo="modificacion",
                    lineas=[_limpiar_linea(linea)],
                )
            continue

        if _TITULO.match(linea):
            cerrar_actual()
            en_encabezado = True
            continue
        if en_encabezado:
            continue  # descripción del título o párrafo
        if actual:
            actual.lineas.append(_limpiar_linea(linea))

    cerrar_actual()
    return [norma_19628, norma_21719], [por_clave[k] for k in orden]
