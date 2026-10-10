"""Prueba de conexión con la API de Claude. No envía ningún dato personal.

python -m privacidad.ia.prueba_conexion
"""

from __future__ import annotations

import os

from .cliente import MODELO_EXTRACCION, MODELO_RAPIDO, ClienteIA


def _informar(linea: str) -> None:
    """Imprime y, en GitHub Actions, publica la línea como anotación visible en la ejecución."""
    print(linea)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=Prueba de conexión::{linea}")


def main() -> int:
    cliente = ClienteIA()
    total = 0.0
    for modelo in (MODELO_RAPIDO, MODELO_EXTRACCION):
        r = cliente.llamar(
            modelo=modelo,
            sistema="Eres una prueba de conexión.",
            mensajes=[{"role": "user", "content": "Responde únicamente con la palabra: OK"}],
            max_tokens=10,
            proposito="prueba de conexión",
        )
        total += r.costo_usd
        _informar(
            f"{modelo}: respuesta={r.texto.strip()!r} tokens={r.tokens_entrada}+{r.tokens_salida} "
            f"costo=US${r.costo_usd:.6f} tiempo={r.latencia_ms} ms"
        )
    _informar(f"Costo total de la prueba: US${total:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
