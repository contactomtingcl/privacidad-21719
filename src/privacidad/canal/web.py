"""Capa web del canal: formulario, código QR, seguimiento y confirmación.

Está hecha con Starlette (rutas y respuestas) y Jinja2 (pantallas con escape automático). Esta
capa solo traduce entre pantallas y `CanalReporte`; las decisiones viven en el servicio y el
motor. Las pantallas no usan JavaScript: funcionan en cualquier celular, con teclado y con
lector de pantalla.

Decisiones de privacidad:

- No registra direcciones IP ni el contenido de las solicitudes (el servidor se levanta con el
  registro de accesos apagado).
- Cabeceras estrictas: sin scripts, sin marcos, sin caché, sin referencia de origen.
- Un enlace con firma inválida responde igual que una página inexistente.
- Nada de lo que escribe la persona entra sin escapar al HTML (autoescape de Jinja2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from babel.dates import format_date
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from ..guardia import DatosNoSinteticosError
from . import qr
from .confirmacion import ETIQUETAS_DERECHO, RespuestaInvalida, dias_de_espera
from .modelos import Caso, Organizacion
from .repositorio import id_caso_valido
from .servicio import CanalReporte, CasoNoEncontrado, OrganizacionDesconocida, ReservadoNoDisponible

MAX_CUERPO = 20_000
MAX_CAMPOS = 50
CARPETA_PLANTILLAS = Path(__file__).parent / "plantillas"

TIPOS = {
    "solicitud": "Quiero ejercer un derecho sobre mis datos personales",
    "incidente": "Quiero avisar de un incidente de seguridad",
    "aviso_proveedor": "Soy proveedor y quiero avisar de un incidente",
}

MENSAJE_NO_SINTETICO = (
    "Detectamos datos que parecen reales (RUT, correo o teléfono). Este prototipo solo admite "
    "datos ficticios: reemplácelos y envíe de nuevo."
)

_CSP_PAGINA = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; "
    "frame-ancestors 'none'"
)
_CSP_IMAGEN = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
_CABECERAS_SEGURAS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": _CSP_PAGINA,
}


def fecha_larga(valor: date | datetime | str | None) -> str:
    """'2 de diciembre de 2026', en español de Chile."""
    if valor is None:
        return ""
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    if isinstance(valor, datetime):
        valor = valor.date()
    return format_date(valor, format="long", locale="es_CL")


def crear_entorno() -> Environment:
    entorno = Environment(
        loader=FileSystemLoader(CARPETA_PLANTILLAS),
        autoescape=True,
        undefined=StrictUndefined,
    )
    entorno.filters["fecha"] = fecha_larga
    entorno.globals["ETIQUETAS_DERECHO"] = ETIQUETAS_DERECHO
    entorno.globals["TIPOS"] = TIPOS
    return entorno


async def _cabeceras_seguras(
    request: Request, siguiente: Callable[[Request], Awaitable[Response]]
) -> Response:
    respuesta = await siguiente(request)
    for nombre, valor in _CABECERAS_SEGURAS.items():
        respuesta.headers.setdefault(nombre, valor)
    return respuesta


async def _leer_formulario(request: Request) -> dict[str, list[str]]:
    """Lee un formulario de hasta MAX_CUERPO bytes sin cargar cuerpos enormes en memoria."""
    tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if tipo != "application/x-www-form-urlencoded":
        raise HTTPException(415)
    largo = request.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > MAX_CUERPO:
        raise HTTPException(413)
    cuerpo = bytearray()
    async for trozo in request.stream():
        cuerpo += trozo
        if len(cuerpo) > MAX_CUERPO:
            raise HTTPException(413)
    try:
        return parse_qs(cuerpo.decode("utf-8"), keep_blank_values=True, max_num_fields=MAX_CAMPOS)
    except ValueError as e:  # UnicodeDecodeError también es ValueError
        raise HTTPException(400) from e


def _uno(datos: dict[str, list[str]], clave: str) -> str:
    return (datos.get(clave) or [""])[0]


def crear_app(canal: CanalReporte, base_url: str, panel: Any = None) -> Starlette:
    """Arma la aplicación web. `base_url` es la dirección pública con la que se arman los QR.
    Con `panel` (un `privacidad.panel.web.ConfigPanel`) monta también el panel del delegado en
    `/panel`."""
    plantillas = crear_entorno()

    def pagina(nombre: str, status: int = 200, **contexto: Any) -> HTMLResponse:
        contexto.setdefault("error", None)
        contexto.setdefault("dias_espera", dias_de_espera())
        return HTMLResponse(plantillas.get_template(nombre).render(**contexto), status)

    def simple(titulo: str, mensaje: str, status: int = 200) -> HTMLResponse:
        return pagina("pagina_simple.html", status, titulo=titulo, mensaje=mensaje)

    def organizacion(request: Request) -> Organizacion:
        try:
            return canal.organizacion_por_enlace(
                request.path_params["org"], request.path_params["firma"]
            )
        except OrganizacionDesconocida as e:
            raise HTTPException(404) from e

    def formulario(
        org: Organizacion, valores: dict[str, str], error: str | None = None, status: int = 200
    ) -> HTMLResponse:
        return pagina(
            "formulario.html",
            status,
            org=org,
            valores=valores,
            error=error,
            reservado_disponible=canal.reservado_disponible,
        )

    def seguimiento_html(caso: Caso, error: str | None = None, status: int = 200) -> HTMLResponse:
        return pagina("seguimiento.html", status, caso=caso, error=error)

    def caso_de(request: Request) -> Caso:
        id_caso = request.path_params["id"]
        if not id_caso_valido(id_caso):
            raise HTTPException(404)
        try:
            return canal.seguimiento(id_caso)
        except CasoNoEncontrado as e:
            raise HTTPException(404) from e

    async def inicio(_: Request) -> Response:
        return simple(
            "Canal de privacidad",
            "Para usar este canal, abra el enlace o escanee el código QR que le entregó su "
            "organización.",
        )

    async def salud(_: Request) -> Response:
        """Para el hosting: responde si el programa está vivo, sin datos de ningún caso."""
        return Response("ok", media_type="text/plain")

    async def ver_formulario(request: Request) -> Response:
        return formulario(organizacion(request), {})

    async def enviar_formulario(request: Request) -> Response:
        org = organizacion(request)
        datos = await _leer_formulario(request)
        valores = {k: _uno(datos, k) for k in ("tipo", "texto", "nombre", "contacto", "reservado")}
        tipo = valores["tipo"] or "solicitud"
        reservado = valores["reservado"] == "1"
        if tipo == "solicitud" and reservado:
            return formulario(
                org,
                valores,
                "El modo reservado es solo para avisos de incidente. Para ejercer un derecho "
                "necesitamos saber quién es y dónde responderle.",
                400,
            )
        try:
            if tipo == "solicitud":
                caso = await run_in_threadpool(
                    canal.recibir_solicitud,
                    org.id,
                    valores["texto"],
                    nombre=valores["nombre"],
                    contacto=valores["contacto"],
                )
            else:
                caso = await run_in_threadpool(
                    canal.recibir_incidente,
                    org.id,
                    valores["texto"],
                    tipo=tipo,  # type: ignore[arg-type]  # el servicio valida el tipo
                    reservado=reservado,
                    nombre=valores["nombre"],
                    contacto=valores["contacto"],
                )
        except DatosNoSinteticosError:
            return formulario(org, valores, MENSAJE_NO_SINTETICO, 400)
        except ReservadoNoDisponible:
            return formulario(org, valores, "El modo reservado no está disponible.", 400)
        except RespuestaInvalida as e:
            return formulario(org, valores, str(e), 400)
        return RedirectResponse(f"/seguimiento/{caso.id}", status_code=303)

    async def ver_qr(request: Request) -> Response:
        org = organizacion(request)
        try:
            svg = qr.svg_qr(canal.enlace(org.id, base_url), f"Código QR del canal de {org.nombre}")
        except RuntimeError as e:
            raise HTTPException(503) from e
        return Response(
            svg, media_type="image/svg+xml", headers={"Content-Security-Policy": _CSP_IMAGEN}
        )

    async def ver_seguimiento(request: Request) -> Response:
        return seguimiento_html(await run_in_threadpool(caso_de, request))

    async def confirmar(request: Request) -> Response:
        id_caso = request.path_params["id"]
        if not id_caso_valido(id_caso):
            raise HTTPException(404)
        datos = await _leer_formulario(request)
        try:
            await run_in_threadpool(
                canal.responder_confirmacion,
                id_caso,
                derechos=datos.get("derechos", []),
                detalle=_uno(datos, "detalle"),
            )
        except CasoNoEncontrado as e:
            raise HTTPException(404) from e
        except DatosNoSinteticosError:
            caso = await run_in_threadpool(caso_de, request)
            return seguimiento_html(caso, MENSAJE_NO_SINTETICO, 400)
        except RespuestaInvalida as e:
            caso = await run_in_threadpool(caso_de, request)
            return seguimiento_html(caso, str(e), 400)
        return RedirectResponse(f"/seguimiento/{id_caso}", status_code=303)

    async def error_http(_: Request, exc: Exception) -> Response:
        assert isinstance(exc, HTTPException)
        titulos = {
            400: ("No pudimos leer el formulario", "Revise los datos e intente de nuevo."),
            404: ("Página no encontrada", "Esta dirección no existe o ya no está vigente."),
            405: ("Acción no permitida", "Esta página no admite esa acción."),
            413: ("Mensaje demasiado largo", "Acorte el texto e intente de nuevo."),
            415: ("Formato no admitido", "Envíe el formulario desde la página del canal."),
            503: ("No disponible por ahora", "Intente de nuevo más tarde."),
        }
        titulo, mensaje = titulos.get(exc.status_code, ("Algo salió mal", "Intente de nuevo."))
        respuesta = simple(titulo, mensaje, exc.status_code)
        for nombre, valor in (exc.headers or {}).items():
            respuesta.headers[nombre] = valor
        return respuesta

    rutas = [
        Route("/", inicio, methods=["GET"]),
        Route("/salud", salud, methods=["GET"]),
        Route("/canal/{org}/{firma}", ver_formulario, methods=["GET"]),
        Route("/canal/{org}/{firma}", enviar_formulario, methods=["POST"]),
        Route("/canal/{org}/{firma}/qr.svg", ver_qr, methods=["GET"]),
        Route("/seguimiento/{id}", ver_seguimiento, methods=["GET"]),
        Route("/seguimiento/{id}/confirmar", confirmar, methods=["POST"]),
    ]
    if panel is not None:
        from ..panel.web import BASE, crear_panel  # import tardío: el panel depende del canal

        rutas.append(Mount(BASE, app=crear_panel(canal, panel)))
    return Starlette(
        routes=rutas,
        middleware=[Middleware(BaseHTTPMiddleware, dispatch=_cabeceras_seguras)],
        exception_handlers={HTTPException: error_http},
    )


__all__ = ["crear_app", "crear_entorno", "fecha_larga"]
