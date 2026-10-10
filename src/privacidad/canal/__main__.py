"""Línea de comandos del canal de reporte.

    python -m privacidad.canal secreto
    python -m privacidad.canal llave
    python -m privacidad.canal enlace --org comercial-los-robles --base-url https://...
    python -m privacidad.canal servir --datos casos-demo
    python -m privacidad.canal identidad --carpeta casos-demo --caso CODIGO

Los secretos (de enlaces, de cifrado, de la API de Claude) nunca se imprimen ni se guardan en
el repositorio: los comandos `secreto` y `llave` los dejan en un archivo que solo lee su dueño
y el canal los toma de variables de entorno.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import MultiFernet

from . import enlaces, qr, reservado
from .modelos import cargar_organizaciones
from .repositorio import RepositorioCasos
from .servicio import CanalReporte
from .web import crear_app

BASE_LOCAL = "http://127.0.0.1:8080"
ARCHIVO_SECRETO = "secreto-enlaces.key"
ARCHIVO_LLAVE = "llave-reservada.key"


def _error(mensaje: str) -> int:
    print(f"Error: {mensaje}", file=sys.stderr)
    return 2


def _crear_archivo(crear, ruta: str, que: str) -> bool:
    destino = Path(ruta)
    try:
        crear(destino)
    except FileExistsError:
        _error(f"{destino} ya existe y no se sobrescribe. Bórrelo si quiere uno nuevo.")
        return False
    print(f"Listo: {que} quedó en el archivo {destino} (solo lo puede leer su dueño).")
    print("No lo comparta ni lo suba al repositorio. No se muestra en pantalla a propósito.")
    return True


def comando_secreto(args: argparse.Namespace) -> int:
    if not _crear_archivo(enlaces.guardar_secreto, args.archivo, "el secreto de los enlaces"):
        return 2
    print(
        f'Para usarlo en esta terminal:  export {enlaces.VARIABLE_SECRETO}="$(cat {args.archivo})"'
    )
    return 0


def comando_llave(args: argparse.Namespace) -> int:
    if not _crear_archivo(reservado.guardar_llave, args.archivo, "la llave del modo reservado"):
        return 2
    print(
        f"Para usarla en esta terminal:  export {reservado.VARIABLE_LLAVE_ARCHIVO}={args.archivo}"
    )
    return 0


def _secreto() -> bytes | None:
    try:
        return enlaces.secreto_desde_entorno()
    except RuntimeError as e:
        _error(str(e))
        return None


def comando_enlace(args: argparse.Namespace) -> int:
    secreto = _secreto()
    if secreto is None:
        return 2
    organizaciones = cargar_organizaciones()
    org = organizaciones.get(args.org)
    if org is None:
        return _error(f"Organización desconocida. Disponibles: {', '.join(organizaciones)}")
    url = enlaces.enlace_canal(args.base_url, org.id, org.version_enlace, secreto)
    salida = Path(args.salida or f"canal-{org.id}.svg")
    try:
        svg = qr.svg_qr(url, f"Código QR del canal de {org.nombre}")
    except RuntimeError as e:
        return _error(str(e))
    salida.write_text(svg, "utf-8")
    print(f"Enlace: {url}")
    print(f"Código QR: {salida}")
    return 0


def _cliente_ia(carpeta_datos: Path | None):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from ..ia.cliente import ClienteIA

    registro = carpeta_datos / "costos_ia.jsonl" if carpeta_datos else None
    return ClienteIA(registro=registro)


def _llaves() -> MultiFernet | None:
    return reservado.llaves_desde_entorno()


def comando_servir(args: argparse.Namespace) -> int:
    secreto = _secreto()
    if secreto is None:
        return 2
    carpeta = Path(args.datos) if args.datos else None
    organizaciones = cargar_organizaciones()
    try:
        llaves = _llaves()
    except (OSError, reservado.IdentidadReservadaError) as e:
        return _error(f"No se pudo leer la llave del modo reservado: {e}")
    cliente = _cliente_ia(carpeta)
    canal = CanalReporte(
        organizaciones=organizaciones,
        repositorio=RepositorioCasos(carpeta),
        cliente=cliente,
        secreto_enlaces=secreto,
        llaves_reservadas=llaves,
    )
    base_url = args.base_url or f"http://127.0.0.1:{args.puerto}"
    print("Canal de reporte (prototipo con datos ficticios)")
    print(f"  IA: {'activa' if cliente else 'apagada (los casos quedan en revisión)'}")
    print(f"  Modo reservado: {'activo' if llaves else 'no disponible'}")
    print(f"  Casos: {'en la carpeta ' + str(carpeta) if carpeta else 'solo en memoria'}")
    for org in organizaciones.values():
        print(f"  {org.nombre}: {canal.enlace(org.id, base_url)}")
    print("Ctrl+C para detener.")
    import uvicorn

    uvicorn.run(
        crear_app(canal, base_url),
        host=args.host,
        port=args.puerto,
        access_log=False,
        log_level="warning",
    )
    return 0


def comando_identidad(args: argparse.Namespace) -> int:
    """Para el delegado: abre la identidad reservada de un caso con la llave de reserva."""
    caso = RepositorioCasos(Path(args.carpeta)).obtener(args.caso)
    if caso is None or not caso.identidad_cifrada:
        return _error("Ese caso no existe o no tiene identidad reservada.")
    try:
        if args.llave:
            llaves = reservado.cargar_llaves(Path(args.llave).read_text("utf-8"))
        else:
            llaves = _llaves()
        if llaves is None:
            return _error(
                f"Falta la llave: use --llave ARCHIVO o la variable {reservado.VARIABLE_LLAVE}."
            )
        identidad = reservado.descifrar_identidad(llaves, caso.identidad_cifrada, caso.id)
    except (OSError, reservado.IdentidadReservadaError) as e:
        return _error(str(e))
    print(json.dumps(identidad, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m privacidad.canal", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("secreto", help="crea el secreto que firma los enlaces")
    p.add_argument("--archivo", default=ARCHIVO_SECRETO)
    p.set_defaults(funcion=comando_secreto)

    p = sub.add_parser("llave", help="crea la llave del modo reservado")
    p.add_argument("--archivo", default=ARCHIVO_LLAVE)
    p.set_defaults(funcion=comando_llave)

    p = sub.add_parser("enlace", help="genera el enlace firmado y su código QR (SVG)")
    p.add_argument("--org", required=True)
    p.add_argument("--base-url", default=BASE_LOCAL)
    p.add_argument("--salida")
    p.set_defaults(funcion=comando_enlace)

    p = sub.add_parser("servir", help="levanta el canal en este computador")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=8080)
    p.add_argument("--base-url")
    p.add_argument("--datos", help="carpeta donde guardar los casos (por defecto, memoria)")
    p.set_defaults(funcion=comando_servir)

    p = sub.add_parser("identidad", help="abre la identidad reservada de un caso (delegado)")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--caso", required=True)
    p.add_argument("--llave", help="archivo de la llave (si no, se usa la variable de entorno)")
    p.set_defaults(funcion=comando_identidad)

    args = parser.parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":
    raise SystemExit(main())
