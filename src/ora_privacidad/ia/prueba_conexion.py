"""Prueba de conexión con la API de Claude. No envía ningún dato personal.

python -m ora_privacidad.ia.prueba_conexion
"""

from __future__ import annotations

from .cliente import MODELO_EXTRACCION, MODELO_RAPIDO, ClienteIA


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
        print(
            f"{modelo:20} respuesta={r.texto.strip()!r:6} "
            f"tokens={r.tokens_entrada}+{r.tokens_salida} "
            f"costo=US${r.costo_usd:.6f} tiempo={r.latencia_ms} ms"
        )
    print(f"Costo total de la prueba: US${total:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
