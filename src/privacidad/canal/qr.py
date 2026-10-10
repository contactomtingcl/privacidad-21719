"""Código QR del enlace del canal, generado con la librería segno.

No hay código propio de codificación: segno implementa la norma ISO/IEC 18004 y se declara en
`pyproject.toml`. Se importa al usarla para que el resto del canal funcione aunque no esté
instalada (por ejemplo, en un entorno sin acceso a PyPI).
"""

from __future__ import annotations

import io

NIVEL_CORRECCION = "m"  # recupera hasta ~15 % del código dañado o sucio
BORDE_MODULOS = 4  # zona de silencio que exige la norma


def svg_qr(texto: str, etiqueta: str, *, escala: int = 8) -> str:
    """SVG independiente (con declaración XML), listo para imprimir o abrir en el navegador."""
    try:
        import segno
    except ImportError as e:  # pragma: no cover - se prueba simulando la falta
        raise RuntimeError(
            'Falta la librería segno para generar el código QR. Se instala con: pip install -e "."'
        ) from e
    codigo = segno.make_qr(texto, error=NIVEL_CORRECCION)
    salida = io.BytesIO()
    codigo.save(
        salida,
        kind="svg",
        scale=escala,
        border=BORDE_MODULOS,
        dark="#000000",
        light="#ffffff",
        title=etiqueta,
    )
    return salida.getvalue().decode("utf-8")
