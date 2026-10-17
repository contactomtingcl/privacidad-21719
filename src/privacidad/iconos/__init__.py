"""Íconos de Lucide (licencia ISC), guardados en el repositorio para no cargar nada de internet.

Origen: https://github.com/lucide-icons/lucide, commit 1ef60af944de207e0d5176905a0759ba12e6ee8d
(16 de octubre de 2026). La licencia está en `svg/LICENCIA-lucide.txt`.

Los íconos son decorativos: siempre van junto a un texto que dice lo mismo, por eso se marcan
`aria-hidden` y no reemplazan ninguna palabra.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from markupsafe import Markup, escape

CARPETA = Path(__file__).parent / "svg"
_NOMBRE = re.compile(r"^[a-z0-9-]+$")


@cache
def _cuerpo(nombre: str) -> str:
    """Las figuras del ícono (lo que va dentro de <svg>), sin la etiqueta de apertura."""
    if not _NOMBRE.match(nombre):
        raise ValueError(f"Nombre de ícono no válido: {nombre!r}")
    texto = (CARPETA / f"{nombre}.svg").read_text(encoding="utf-8")
    inicio = texto.index(">", texto.index("<svg")) + 1
    fin = texto.rindex("</svg>")
    return " ".join(texto[inicio:fin].split())


def icono(nombre: str, tam: int = 20, clase: str = "") -> Markup:
    """El ícono como SVG en línea, del color del texto que lo rodea."""
    clase_html = f' class="icono-svg {escape(clase)}"' if clase else ' class="icono-svg"'
    return Markup(
        f'<svg{clase_html} width="{int(tam)}" height="{int(tam)}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">{_cuerpo(nombre)}</svg>'
    )
