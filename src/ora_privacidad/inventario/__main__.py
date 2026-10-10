"""Perfila una planilla: python -m ora_privacidad.inventario ARCHIVO [--referencia AAAA-MM-DD]"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .perfilador import perfilar_archivo

_SENSIBLE = {True: "SENSIBLE", False: "", "revisar": "revisar"}


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m ora_privacidad.inventario")
    p.add_argument("archivo", type=Path)
    p.add_argument(
        "--referencia",
        type=date.fromisoformat,
        default=None,
        help="fecha para calcular edades (por defecto, hoy)",
    )
    p.add_argument("--json", action="store_true", help="salida en JSON")
    args = p.parse_args()

    perfil = perfilar_archivo(args.archivo, referencia=args.referencia)
    if args.json:
        print(perfil.model_dump_json(indent=2))
        return 0

    print(
        f"{perfil.archivo}: {perfil.filas} filas, "
        f"{perfil.columnas_personales} de {len(perfil.columnas)} columnas con datos personales\n"
    )
    for c in perfil.columnas:
        etiqueta = c.etiqueta or "Sin clasificar"
        marcas = " ".join(
            m
            for m in (
                _SENSIBLE[c.sensible],
                "MENORES" if c.contexto_menores else "",
                "REVISAR" if c.requiere_revision else "",
            )
            if m
        )
        print(f"  {c.nombre:40} {etiqueta:38} {c.confianza:5}  {marcas}")
    if perfil.menores:
        m = perfil.menores
        print(
            f"\nEdades al {m.referencia:%d/%m/%Y} ({m.columna}): "
            f"{m.menores_de_14} menores de 14, {m.menores_de_16} menores de 16, "
            f"{m.menores_de_18} menores de 18, de {m.con_fecha_valida} con fecha válida"
        )
    if perfil.categorias_sensibles:
        print("Datos sensibles:", ", ".join(perfil.categorias_sensibles))
    if perfil.especiales:
        print("Categorías especiales:", ", ".join(perfil.especiales))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
