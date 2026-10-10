"""Regenera los datos de la demo: python -m privacidad.sinteticos"""

from pathlib import Path

from . import comercial_los_robles

DESTINO = Path(__file__).resolve().parents[3] / "data" / "sinteticos" / "comercial-los-robles"

if __name__ == "__main__":
    for nombre, ruta in comercial_los_robles.generar(DESTINO).items():
        print(f"{nombre:12} {ruta.relative_to(DESTINO.parents[2])}")
