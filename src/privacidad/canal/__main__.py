"""Línea de comandos del canal de reporte.

    python -m privacidad.canal secreto
    python -m privacidad.canal llave
    python -m privacidad.canal enlace --org comercial-los-robles --base-url https://...
    python -m privacidad.canal servir --datos casos-demo [--demo]
    python -m privacidad.canal usuario --datos casos-demo --org ORGANIZACION --usuario NOMBRE
    python -m privacidad.canal identidad --carpeta casos-demo --caso CODIGO
    python -m privacidad.canal evidencia --carpeta casos-demo [--caso CODIGO] [--cabeza HUELLA]
    python -m privacidad.canal correcciones --carpeta casos-demo [--org ORGANIZACION]

Los secretos (de enlaces, de cifrado, de la API de Claude) nunca se imprimen ni se guardan en
el repositorio: los comandos `secreto` y `llave` los dejan en un archivo que solo lee su dueño
y el canal los toma de variables de entorno.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import MultiFernet

from . import enlaces, qr, reservado
from .modelos import cargar_organizaciones
from .repositorio import NOMBRE_ARCHIVO, RepositorioCasos
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


VARIABLE_SECRETO_PANEL = "PRIVACIDAD_SECRETO_PANEL"


def _config_panel(args: argparse.Namespace, carpeta: Path | None, base_url: str, canal=None):
    """Configuración del panel del delegado, o None si no hay con qué abrirlo."""
    from ..panel import ConfigPanel, RegistroUsuarios
    from ..panel.usuarios import NOMBRE_ARCHIVO as ARCHIVO_USUARIOS

    secreto = os.environ.get(VARIABLE_SECRETO_PANEL)
    if not secreto:
        secreto = secrets.token_urlsafe(32)
        print(f"  Panel: sin {VARIABLE_SECRETO_PANEL}; las sesiones se cierran al reiniciar.")
    https = base_url.startswith("https://")
    if args.demo:
        return ConfigPanel(
            secreto_sesion=secreto, demo=True, https=https, salas=_salas_demo(carpeta, canal)
        )
    if carpeta is None or not (carpeta / ARCHIVO_USUARIOS).is_file():
        print("  Panel: apagado (no hay usuarios; créalos con el comando `usuario`).")
        return None
    usuarios = RegistroUsuarios(carpeta / ARCHIVO_USUARIOS)
    return ConfigPanel(secreto_sesion=secreto, usuarios=usuarios, https=https)


def _salas_demo(carpeta: Path | None, canal: CanalReporte | None):
    """Una copia limpia de la demo por participante (ver `panel/salas.py`). Necesita carpeta."""
    if carpeta is None or canal is None:
        return None
    from ..panel.demo import sembrar
    from ..panel.salas import SalasDemo

    return SalasDemo(carpeta / "salas", canal.con_repositorio, sembrar)


def comando_servir(args: argparse.Namespace) -> int:
    secreto = _secreto()
    if secreto is None:
        return 2
    carpeta = Path(args.datos) if args.datos else None
    if carpeta is not None and args.demo:
        from ..panel.demo import version_demo

        carpeta = carpeta / f"demo-{version_demo()}"
        carpeta.mkdir(parents=True, exist_ok=True)
    organizaciones = cargar_organizaciones()
    try:
        llaves = _llaves()
    except (OSError, reservado.IdentidadReservadaError) as e:
        return _error(f"No se pudo leer la llave del modo reservado: {e}")
    if llaves is None and args.demo:
        # Solo para la demo: una llave que vive en memoria y desaparece al detener el servidor.
        # En la demo nunca se abren identidades reservadas.
        from cryptography.fernet import Fernet

        llaves = reservado.cargar_llaves(Fernet.generate_key())
    cliente = _cliente_ia(carpeta)
    repositorio = RepositorioCasos(carpeta)
    canal = CanalReporte(
        organizaciones=organizaciones,
        repositorio=repositorio,
        cliente=cliente,
        secreto_enlaces=secreto,
        llaves_reservadas=llaves,
    )
    base_url = args.base_url or f"http://127.0.0.1:{args.puerto}"
    print("Canal de reporte (prototipo con datos ficticios)")
    print(f"  IA: {'activa' if cliente else 'apagada (los casos quedan en revisión)'}")
    print(f"  Modo reservado: {'activo' if llaves else 'no disponible'}")
    print(f"  Casos: {'en la carpeta ' + str(carpeta) if carpeta else 'solo en memoria'}")
    if args.demo and not repositorio.listar():
        from ..panel.demo import sembrar

        print(
            f"  Demo: {sembrar(canal)} casos ficticios cargados con respuestas grabadas de la IA."
        )
    panel = _config_panel(args, carpeta, base_url, canal)
    if panel is not None and panel.salas is not None:
        print("  Demo: cada participante recibe su propia copia limpia de los casos.")
    for org in organizaciones.values():
        print(f"  {org.nombre}: {canal.enlace(org.id, base_url)}")
    if panel is not None:
        print(f"  Panel del delegado: {base_url}/panel/")
    print("Ctrl+C para detener.")
    import uvicorn

    uvicorn.run(
        crear_app(canal, base_url, panel=panel),
        host=args.host,
        port=args.puerto,
        access_log=False,
        log_level="warning",
        # Detrás del proxy de un servicio de hosting (Render), la conexión con el navegador es
        # HTTPS aunque al programa le llegue HTTP: se confía en las cabeceras X-Forwarded-*
        # solo cuando se indica, porque ahí nadie más puede llegar directo al programa.
        proxy_headers=True,
        forwarded_allow_ips="*" if args.detras_de_proxy else None,
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


def comando_evidencia(args: argparse.Namespace) -> int:
    """Revisa la cadena de evidencia de una organización (o la de cada una) y, si se pide,
    muestra la de un caso."""
    carpeta = Path(args.carpeta)
    if not (carpeta / NOMBRE_ARCHIVO).is_file():
        return _error(f"No hay casos guardados en {carpeta}.")
    repo = RepositorioCasos(carpeta)
    try:
        if args.caso:
            anotaciones = repo.evidencia(args.caso)
            if not anotaciones:
                return _error("Ese caso no existe o no tiene evidencia.")
            for a in anotaciones:
                print(a.model_dump_json())
        if args.cabeza and not args.org:
            return _error("La huella final es de una organización: indíquela con --org.")
        resultado = repo.verificar_evidencia(args.cabeza, args.org)
    finally:
        repo.cerrar()
    if resultado.integra:
        print(f"Cadena íntegra: {resultado.anotaciones} anotaciones revisadas, ninguna alterada.")
    else:
        print("ATENCIÓN: la evidencia fue alterada.")
        for problema in resultado.problemas:
            print(f"  - {problema}")
    for org, cabeza in sorted(resultado.cabezas.items()):
        print(f"Huella final de {org}: {cabeza}")
    print(
        "Guárdela fuera de este computador. Si alguien borra las últimas anotaciones, se "
        "detecta revisando con --org, --cabeza y esa huella."
    )
    return 0 if resultado.integra else 1


def comando_correcciones(args: argparse.Namespace) -> int:
    """Cuánto corrige la persona lo que leyó la IA, contado desde la evidencia verificada."""
    from .correcciones import medir_correcciones

    carpeta = Path(args.carpeta)
    if not (carpeta / NOMBRE_ARCHIVO).is_file():
        return _error(f"No hay casos guardados en {carpeta}.")
    repo = RepositorioCasos(carpeta)
    try:
        if args.cabeza and not args.org:
            return _error("La huella final es de una organización: indíquela con --org.")
        verificacion = repo.verificar_evidencia(args.cabeza, args.org)
        anotaciones = repo.evidencia(id_organizacion=args.org)
    finally:
        repo.cerrar()
    if not verificacion.integra:
        return _error("La evidencia fue alterada: no se calcula la cifra (no sería confiable).")
    cifra = medir_correcciones(anotaciones)
    print(json.dumps(cifra.como_dict(), ensure_ascii=False, indent=2))
    print(f"Calculada sobre {verificacion.anotaciones} anotaciones verificadas.", file=sys.stderr)
    return 0


def comando_usuario(args: argparse.Namespace) -> int:
    """Crea un usuario del panel. La contraseña se escribe sin que se vea en pantalla."""
    from ..panel import RegistroUsuarios
    from ..panel.usuarios import NOMBRE_ARCHIVO as ARCHIVO_USUARIOS
    from ..panel.usuarios import ErrorUsuarios

    if args.org not in cargar_organizaciones():
        return _error("Organización desconocida.")
    contrasena = getpass.getpass("Contraseña (no se ve al escribir): ")
    if contrasena != getpass.getpass("Repítela: "):
        return _error("Las contraseñas no coinciden.")
    try:
        RegistroUsuarios(Path(args.datos) / ARCHIVO_USUARIOS).crear(
            args.usuario, args.org, contrasena
        )
    except ErrorUsuarios as e:
        return _error(str(e))
    print(f"Listo: el usuario {args.usuario} puede entrar al panel de {args.org}.")
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
    p.add_argument("--demo", action="store_true", help="panel sin contraseña y casos ficticios")
    p.add_argument(
        "--detras-de-proxy",
        action="store_true",
        help="confía en las cabeceras X-Forwarded-* del hosting (solo detrás de su proxy)",
    )
    p.set_defaults(funcion=comando_servir)

    p = sub.add_parser("usuario", help="crea un usuario del panel del delegado")
    p.add_argument("--datos", required=True, help="carpeta de los casos")
    p.add_argument("--org", required=True)
    p.add_argument("--usuario", required=True)
    p.set_defaults(funcion=comando_usuario)

    p = sub.add_parser("identidad", help="abre la identidad reservada de un caso (delegado)")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--caso", required=True)
    p.add_argument("--llave", help="archivo de la llave (si no, se usa la variable de entorno)")
    p.set_defaults(funcion=comando_identidad)

    p = sub.add_parser("evidencia", help="revisa la cadena de evidencia (delegado)")
    p.add_argument("--carpeta", required=True)
    p.add_argument("--caso", help="muestra además la evidencia de este caso")
    p.add_argument("--org", help="solo la cadena de esta organización")
    p.add_argument("--cabeza", help="huella final guardada antes, para detectar borrados")
    p.set_defaults(funcion=comando_evidencia)

    p = sub.add_parser(
        "correcciones", help="cuánto corrige la persona lo que leyó la IA (desde la evidencia)"
    )
    p.add_argument("--carpeta", required=True)
    p.add_argument("--org", help="solo esta organización")
    p.add_argument("--cabeza", help="huella final guardada antes, para detectar borrados")
    p.set_defaults(funcion=comando_correcciones)

    args = parser.parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":
    raise SystemExit(main())
