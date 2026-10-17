"""Piezas compartidas por las pruebas del panel (no son pruebas)."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlencode

from privacidad.canal import crear_app
from privacidad.panel import ConfigPanel, LimiteIntentos, RegistroUsuarios

from .canal_apoyo import crear_canal

HOST = "canal.ejemplo.cl"
COSTO_PRUEBA = {"n": 2**4, "r": 8, "p": 1}  # scrypt barato solo para las pruebas
CONTRASENA = "una-clave-larga-de-prueba"


class Respuesta:
    def __init__(self, status, cabeceras, cuerpo):
        self.status = status
        self.cabeceras = cabeceras
        self.cuerpo = cuerpo

    @property
    def html(self) -> str:
        return self.cuerpo.decode("utf-8")

    def csrf(self) -> str:
        m = re.search(r'name="csrf" value="([^"]+)"', self.html)
        assert m, "la página no trae código CSRF"
        return m.group(1)


class Navegador:
    """Llama a la aplicación ASGI directamente y guarda la cookie de sesión del panel."""

    def __init__(self, app):
        self.app = app
        self.cookie: str | None = None

    def pedir_crudo(self, metodo, ruta, cuerpo: bytes, tipo: str):
        """POST con un cuerpo ya armado (por ejemplo, multipart para subir un archivo)."""
        return self.pedir(metodo, ruta, cuerpo_crudo=(cuerpo, tipo))

    def pedir(self, metodo, ruta, datos=None, *, cabeceras=None, origen=True, cuerpo_crudo=None):
        cuerpo = urlencode(datos or {}, doseq=True).encode() if metodo == "POST" else b""
        tipo = b"application/x-www-form-urlencoded"
        if cuerpo_crudo is not None:
            cuerpo, tipo_texto = cuerpo_crudo
            tipo = tipo_texto.encode()
        ruta, _, consulta = ruta.partition("?")
        encabezados = [(b"host", HOST.encode())]
        if metodo == "POST":
            encabezados += [
                (b"content-type", tipo),
                (b"content-length", str(len(cuerpo)).encode()),
            ]
            if origen:
                encabezados.append((b"origin", f"https://{HOST}".encode()))
        if self.cookie:
            encabezados.append((b"cookie", self.cookie.encode()))
        encabezados += [(k.lower().encode(), v.encode()) for k, v in (cabeceras or {}).items()]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": metodo,
            "scheme": "https",
            "path": ruta,
            "raw_path": ruta.encode(),
            "query_string": consulta.encode(),
            "root_path": "",
            "headers": encabezados,
            "server": (HOST, 443),
            "client": ("203.0.113.9", 50000),
        }
        recibido: dict = {"cookies": []}

        async def correr():
            pendiente = [{"type": "http.request", "body": cuerpo, "more_body": False}]

            async def receive():
                return pendiente.pop(0) if pendiente else {"type": "http.disconnect"}

            trozos = []

            async def send(mensaje):
                if mensaje["type"] == "http.response.start":
                    recibido["status"] = mensaje["status"]
                    recibido["cabeceras"] = {}
                    for k, v in mensaje["headers"]:
                        k, v = k.decode().lower(), v.decode()
                        if k == "set-cookie":
                            recibido["cookies"].append(v)
                        recibido["cabeceras"][k] = v
                elif mensaje["type"] == "http.response.body":
                    trozos.append(mensaje.get("body", b""))

            await self.app(scope, receive, send)
            return b"".join(trozos)

        cuerpo_respuesta = asyncio.run(correr())
        for c in recibido["cookies"]:
            if c.startswith("panel_sesion="):
                valor = c.split(";", 1)[0]
                self.cookie = None if valor == "panel_sesion=" or "Max-Age=0" in c else valor
        return Respuesta(recibido["status"], recibido["cabeceras"], cuerpo_respuesta)


def crear_panel_de_prueba(
    cliente,
    *,
    demo=False,
    usuarios=None,
    limite=None,
    reloj_sesion=None,
    repositorio=None,
    reloj=None,
    salas=None,
):
    canal, reloj_canal, llaves = crear_canal(cliente, repositorio=repositorio, reloj=reloj)
    if usuarios is None and not demo:
        usuarios = RegistroUsuarios(costo=COSTO_PRUEBA)
        usuarios.crear("delegado-muni", "municipalidad-piloto", CONTRASENA)
        usuarios.crear("delegado-robles", "comercial-los-robles", CONTRASENA)
    config = ConfigPanel(
        secreto_sesion="secreto-de-sesion-de-prueba-suficientemente-largo",
        usuarios=usuarios,
        demo=demo,
        https=True,
        limite=limite or LimiteIntentos(),
        salas=salas(canal) if callable(salas) else salas,
    )
    if reloj_sesion is not None:
        config.reloj_sesion = reloj_sesion
    app = crear_app(canal, f"https://{HOST}", panel=config)
    return app, canal, reloj_canal


def entrar(nav: Navegador, usuario="delegado-muni", contrasena=CONTRASENA):
    pagina = nav.pedir("GET", "/panel/entrar")
    return nav.pedir(
        "POST",
        "/panel/entrar",
        {"csrf": pagina.csrf(), "usuario": usuario, "contrasena": contrasena},
    )
