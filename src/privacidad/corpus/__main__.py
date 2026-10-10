"""Uso:

python -m privacidad.corpus             # resumen del corpus
python -m privacidad.corpus --exportar  # regenera data/normas/indice.json
python -m privacidad.corpus --verificar # falla si indice.json está desactualizado
"""

from __future__ import annotations

import argparse
import sys

from .corpus import RAIZ_DATOS, Corpus


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m privacidad.corpus")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--exportar", action="store_true", help="regenera indice.json")
    g.add_argument("--verificar", action="store_true", help="comprueba que indice.json está al día")
    args = p.parse_args()

    corpus = Corpus.desde_directorio()
    indice = RAIZ_DATOS / "indice.json"

    if args.exportar:
        indice.write_text(corpus.a_json(), encoding="utf-8")
        print(f"Exportado {indice} ({len(corpus)} artículos)")
        return 0
    if args.verificar:
        if not indice.exists() or indice.read_text(encoding="utf-8") != corpus.a_json():
            print("indice.json está desactualizado: ejecuta --exportar", file=sys.stderr)
            return 1
        print(f"indice.json al día ({len(corpus)} artículos)")
        return 0

    for norma in corpus.normas.values():
        arts = corpus.articulos(norma.clave)
        mods = sum(a.tipo == "modificacion" for a in arts)
        resumen = f"{len(arts):3} artículos ({mods} de modificación)"
        print(f"{norma.clave:12} {resumen} · {norma.titulo[:60]}")
    print(f"Total: {len(corpus)} artículos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
