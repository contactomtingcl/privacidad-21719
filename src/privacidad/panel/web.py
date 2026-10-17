"""Panel del delegado: pantallas web montadas en `/panel`, en el mismo programa que el canal.

Seguridad (cada punto tiene su prueba en `tests/test_panel_web.py`):

- **Sesión** en una cookie firmada (Starlette + itsdangerous), solo para `/panel`, con
  `HttpOnly`, `SameSite=Strict` y `Secure` cuando se publica con HTTPS. Expira a los 30 minutos
  sin uso y a las 8 horas en total. La revisión automática de la bandeja no la mantiene viva.
- **Contra clics falsos desde otro sitio (CSRF):** cada formulario y cada llamada de htmx lleva
  un código propio de la sesión; además se revisa la cabecera `Origin`.
- **Política de contenido estricta:** solo scripts, estilos y fuentes servidos por el mismo
  panel; nada de JavaScript escrito dentro de las páginas; htmx sin `eval`.
- **Aislamiento:** cada delegado ve solo su organización. Un caso ajeno responde 404, igual que
  uno inexistente.
- **Identidad reservada:** pide de nuevo la contraseña y un motivo, y queda en la evidencia.
- **Modo demo:** sin contraseña, solo datos ficticios, con aviso visible; ahí no se abren
  identidades reservadas.
"""

from __future__ import annotations

import hmac
import re
import secrets
import sqlite3
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from babel.dates import format_date
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ..canal.confirmacion import ETIQUETAS_DERECHO
from ..canal.correcciones import medir_correcciones
from ..canal.delegado import AccionInvalida, CasoAjeno, caso_abierto
from ..canal.evidencia import Anotacion, Verificacion
from ..canal.modelos import ZONA_CHILE, Organizacion
from ..canal.repositorio import NOMBRE_ARCHIVO, RepositorioCasos
from ..canal.reservado import IdentidadReservadaError
from ..canal.servicio import CanalReporte
from ..canal.web import _leer_formulario, _uno
from ..guardia import DatosNoSinteticosError
from ..iconos import icono
from ..motor import HechosIncidente, escenarios
from ..reportes import DESTINOS, NOMBRE_DESTINO, Borrador, ultima_revision
from ..reportes.borradores import PERFILES
from . import vista
from .salas import SalasDemo
from .usuarios import LimiteIntentos, RegistroUsuarios

BASE = "/panel"
CARPETA = Path(__file__).parent
USUARIO_DEMO = "delegado-demo"
# Filtros de la bandeja. «Validados» tiene su propia entrada en el menú lateral; en la bandeja
# solo se filtra por urgencia, que es una sola dimensión y se entiende de un vistazo.
FILTROS_URGENCIA = {
    "abiertos": "Todas",
    "inmediata": "Inmediata",
    "alta": "Alta",
    "normal": "Normal",
}
FILTROS = {**FILTROS_URGENCIA, "validados": "Validados"}
CSP_PANEL = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; "
    "frame-ancestors 'none'"
)
# "same-origin": el navegador envía la cabecera Origin en los formularios del propio panel (con
# "no-referrer" la manda como "null" y la revisión de origen no podría distinguir).
CABECERAS = {
    "Content-Security-Policy": CSP_PANEL,
    "Cache-Control": "no-store",
    "Referrer-Policy": "same-origin",
}


@dataclass
class ConfigPanel:
    secreto_sesion: str
    usuarios: RegistroUsuarios | None = None
    demo: bool = False
    # Solo en demo: una copia limpia de los casos por participante (ver `salas.py`). Sin ella, la
    # demo usa la base única del canal (así la usan las pruebas antiguas).
    salas: SalasDemo | None = None
    https: bool = True
    limite: LimiteIntentos = field(default_factory=LimiteIntentos)
    inactividad: timedelta = timedelta(minutes=30)
    duracion_maxima: timedelta = timedelta(hours=8)
    reloj_sesion: Callable[[], float] = time.time


class NoAutenticado(Exception):
    def __init__(self, expirada: bool = False) -> None:
        self.expirada = expirada


@dataclass
class Contexto:
    usuario: str
    org: Organizacion
    csrf: str
    demo: bool
    canal: CanalReporte
    sala: str | None = None


NORMAS = {
    "ley-19628": "Ley 19.628",
    "ley-21719": "Ley 21.719",
    "ley-21663": "Ley 21.663",
    "ds-662-2025": "Decreto 662 de 2025",
}
_MARCADOR = re.compile(r"\[[A-Z]+_\d+\]")


def _marcadores(texto: str) -> Markup:
    """Escapa el texto y resalta los marcadores del enmascarado ([RUT_1], [CORREO_2]…)."""
    seguro = str(escape(texto))
    return Markup(_MARCADOR.sub(lambda m: f"<mark>{m.group(0)}</mark>", seguro))


_COMPLETAR = re.compile(r"\[Completar: [^\]]+\]")


def _por_completar(texto: str) -> Markup:
    """Escapa el texto y resalta lo que el delegado debe completar."""
    seguro = str(escape(texto))
    return Markup(_COMPLETAR.sub(lambda m: f'<mark class="completar">{m.group(0)}</mark>', seguro))


def _entorno() -> Environment:
    entorno = Environment(
        loader=FileSystemLoader(CARPETA / "plantillas"), autoescape=True, undefined=StrictUndefined
    )
    entorno.filters["fecha"] = lambda v: format_date(v, format="long", locale="es_CL")
    entorno.filters["hora"] = vista.hora
    entorno.filters["iso"] = lambda v: v.isoformat() if v else ""
    entorno.filters["corto"] = lambda h: f"{h[:6]}…{h[-2:]}" if h else ""
    entorno.filters["norma"] = lambda clave: NORMAS.get(clave, clave)
    entorno.filters["evento"] = lambda tipo: vista.EVENTOS.get(tipo, tipo).format(por="Delegado")
    entorno.filters["hora_iso"] = lambda texto: vista.hora(datetime.fromisoformat(texto))
    entorno.filters["marcadores"] = _marcadores
    entorno.filters["por_completar"] = _por_completar
    entorno.globals.update(
        BASE=BASE,
        FILTROS=FILTROS,
        FILTROS_URGENCIA=FILTROS_URGENCIA,
        icono=icono,
        MOTIVOS_CORRECCION=vista.MOTIVOS_CORRECCION,
        MOTIVOS_DECISION=vista.MOTIVOS_DECISION,
        MOTIVOS_IDENTIDAD=vista.MOTIVOS_IDENTIDAD,
        CANALES_ENVIO=vista.CANALES_ENVIO,
        MOTIVO_SIN_LECTURA=vista.MOTIVO_SIN_LECTURA,
        MOTIVOS_DERIVACION=vista.MOTIVOS_DERIVACION,
        VULNERACIONES=vista.VULNERACIONES,
        CATEGORIAS=vista.CATEGORIAS,
        CIBER=vista.CIBER,
        ETIQUETAS_HECHO=vista.ETIQUETAS_HECHO,
        ETIQUETAS_DERECHO=ETIQUETAS_DERECHO,
    )
    return entorno


def _simular_alteracion(canal: CanalReporte, id_org: str) -> tuple[Verificacion, list, int | None]:
    """Demo: altera de verdad una COPIA de la base y corre la misma verificación real."""
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / NOMBRE_ARCHIVO
        canal._repo.copiar_a(destino)
        propias = canal._repo.evidencia(id_organizacion=id_org)
        objetivo = propias[-3].n if len(propias) >= 3 else (propias[0].n if propias else None)
        if objetivo is not None:
            con = sqlite3.connect(destino)
            con.execute("DROP TRIGGER IF EXISTS evidencia_sin_cambios")
            con.execute(
                "UPDATE evidencia SET tipo = 'editado_a_mano' WHERE id_organizacion = ? AND n = ?",
                (id_org, objetivo),
            )
            con.commit()
            con.close()
        copia = RepositorioCasos(Path(carpeta))
        try:
            verificacion = copia.verificar_evidencia(id_organizacion=id_org)
            anotaciones = copia.evidencia(id_organizacion=id_org)
        finally:
            copia.cerrar()
    return verificacion, anotaciones, objetivo


CAMPOS_OBLIGATORIOS = (
    "vulneracion",
    "ciberincidente",
    "datos_personales",
    "riesgo_mitigado",
    "interrupcion_servicio",
)


def _hechos_del_formulario(datos: dict[str, list[str]]) -> HechosIncidente:
    if any(not _uno(datos, campo) for campo in CAMPOS_OBLIGATORIOS):
        raise AccionInvalida("Completa todos los campos: elige una opción en cada uno.")
    titulares = _uno(datos, "titulares_aprox").strip()
    return HechosIncidente(
        datos_personales=_uno(datos, "datos_personales") == "si",
        vulneracion=_uno(datos, "vulneracion"),  # type: ignore[arg-type]
        categorias_especiales=datos.get("categorias_especiales", []),  # type: ignore[arg-type]
        riesgo_mitigado=_uno(datos, "riesgo_mitigado") == "si",
        ciberincidente=_uno(datos, "ciberincidente"),  # type: ignore[arg-type]
        interrupcion_servicio=_uno(datos, "interrupcion_servicio") == "si",
        titulares_aprox=int(titulares) if titulares.isdigit() else None,
    )


def crear_panel(canal: CanalReporte, config: ConfigPanel) -> Starlette:
    if not config.demo and config.usuarios is None:
        raise ValueError("Sin modo demo, el panel necesita un registro de usuarios")
    plantillas = _entorno()
    organizaciones = canal._organizaciones
    reloj = canal._reloj

    def responder(nombre: str, status: int = 200, **contexto: Any) -> HTMLResponse:
        contexto.setdefault("error", None)
        contexto.setdefault("aviso", None)
        html = plantillas.get_template(nombre).render(**contexto)
        return HTMLResponse(html, status, headers=CABECERAS)

    # --- sesión ----------------------------------------------------------------------

    def contexto(request: Request, *, refrescar: bool = True) -> Contexto:
        s = request.session
        ahora = config.reloj_sesion()
        if config.demo:
            if s.get("u") != USUARIO_DEMO or s.get("org") not in organizaciones:
                s.clear()
                s.update(
                    u=USUARIO_DEMO,
                    org=next(iter(organizaciones)),
                    csrf=secrets.token_urlsafe(32),
                    inicio=ahora,
                    ultimo=ahora,
                )
        elif "u" not in s:
            raise NoAutenticado()
        elif (
            ahora - s.get("ultimo", 0) > config.inactividad.total_seconds()
            or ahora - s.get("inicio", 0) > config.duracion_maxima.total_seconds()
            or (config.usuarios and config.usuarios.obtener(s["u"]) is None)
            or s.get("org") not in organizaciones
        ):
            s.clear()
            raise NoAutenticado(expirada=True)
        if refrescar:
            s["ultimo"] = ahora
        propio, sala = canal, None
        if config.demo and config.salas is not None:
            sala = s.get("sala")
            propio = config.salas.canal(sala) if sala else None
            if propio is None:  # sesión nueva, reiniciada o sala ya limpiada: copia limpia
                sala = config.salas.crear()
                s["sala"] = sala
                propio = config.salas.canal(sala)
            assert propio is not None
        return Contexto(s["u"], organizaciones[s["org"]], s["csrf"], config.demo, propio, sala)

    def mismo_origen(request: Request) -> bool:
        origen = request.headers.get("origin")
        if origen is None:
            return True  # navegadores antiguos; SameSite=Strict y el código CSRF siguen protegiendo
        esperado = urlparse(str(request.base_url))
        dado = urlparse(origen)
        return (dado.scheme, dado.netloc) == (esperado.scheme, esperado.netloc)

    async def formulario_seguro(request: Request) -> dict[str, list[str]]:
        datos = await _leer_formulario(request)
        enviado = _uno(datos, "csrf") or request.headers.get("x-csrf", "")
        guardado = request.session.get("csrf", "")
        if not guardado or not hmac.compare_digest(enviado, guardado) or not mismo_origen(request):
            raise HTTPException(403)
        return datos

    # --- ingreso ---------------------------------------------------------------------

    async def ver_entrar(request: Request) -> Response:
        if config.demo:
            return RedirectResponse(f"{BASE}/", 303)
        if "u" in request.session:
            try:
                contexto(request)
                return RedirectResponse(f"{BASE}/", 303)
            except NoAutenticado:
                pass
        request.session.setdefault("csrf", secrets.token_urlsafe(32))
        aviso = None
        if request.query_params.get("expirada"):
            aviso = "Tu sesión se cerró por inactividad. Vuelve a entrar."
        elif request.query_params.get("salio"):
            aviso = "Saliste del panel."
        return responder("entrar.html", csrf=request.session["csrf"], aviso=aviso)

    async def entrar(request: Request) -> Response:
        if config.demo:
            return RedirectResponse(f"{BASE}/", 303)
        datos = await formulario_seguro(request)
        usuario = _uno(datos, "usuario").strip().lower()[:64]
        contrasena = _uno(datos, "contrasena")
        csrf = request.session["csrf"]
        if config.limite.bloqueado(usuario):
            return responder(
                "entrar.html",
                429,
                csrf=csrf,
                error="Demasiados intentos. Espera 15 minutos y vuelve a intentarlo.",
            )
        assert config.usuarios is not None
        encontrado = await run_in_threadpool(config.usuarios.verificar, usuario, contrasena)
        if encontrado is None or encontrado.id_organizacion not in organizaciones:
            config.limite.fallo(usuario)
            return responder(
                "entrar.html", 401, csrf=csrf, error="Usuario o contraseña incorrectos."
            )
        config.limite.exito(usuario)
        ahora = config.reloj_sesion()
        request.session.clear()
        request.session.update(
            u=encontrado.usuario,
            org=encontrado.id_organizacion,
            csrf=secrets.token_urlsafe(32),
            inicio=ahora,
            ultimo=ahora,
        )
        return RedirectResponse(f"{BASE}/", 303)

    async def salir(request: Request) -> Response:
        await formulario_seguro(request)
        request.session.clear()
        return RedirectResponse(f"{BASE}/" if config.demo else f"{BASE}/entrar?salio=1", 303)

    async def cambiar_organizacion(request: Request) -> Response:
        if not config.demo:
            raise HTTPException(404)
        datos = await formulario_seguro(request)
        org = _uno(datos, "org")
        if org in organizaciones:
            request.session["org"] = org
        return RedirectResponse(f"{BASE}/", 303)

    # --- bandeja ---------------------------------------------------------------------

    def siguiente_paso(
        ctx: Contexto, f: vista.Ficha | None, ahora: datetime
    ) -> vista.SiguientePaso | None:
        """Si el plazo más cercano del caso urgente ya venció, qué puede hacer el delegado ahora.

        No cambia ninguna decisión: el deber sigue igual aunque el plazo haya vencido. Solo ofrece
        el paso que ya existe (por ejemplo, el borrador para la ANCI) en vez de un contador.
        """
        if f is None or not f.relojes or f.relojes[0].vence is None:
            return None
        if f.relojes[0].vence > ahora:
            return None
        destinos = []
        if f.relojes[0].titulo == vista.TITULO_RELOJ_ANCI:
            _, borradores = ctx.canal.borradores(ctx.org.id, f.caso.id)
            if isinstance(borradores.get("anci"), Borrador):
                destinos.append("anci")
        return vista.siguiente_paso(f, destinos)

    def datos_bandeja(ctx: Contexto, filtro: str, desde: datetime | None) -> dict[str, Any]:
        ahora = reloj()
        casos = vista.ordenar(ctx.canal.casos_de_organizacion(ctx.org.id))
        abiertos = [c for c in casos if caso_abierto(c)]
        if filtro == "validados":
            elegidos = [c for c in casos if c.validacion is not None]
        elif filtro in ("inmediata", "alta", "normal"):
            elegidos = [c for c in abiertos if c.asignacion and c.asignacion.urgencia == filtro]
        else:
            elegidos = abiertos
        filas = [vista.fila(c, ahora, desde) for c in elegidos]
        urgente = next(
            (c for c in abiertos if c.asignacion and c.asignacion.urgencia != "normal"), None
        )
        verificacion, _ = ctx.canal.evidencia_de_organizacion(ctx.org.id)
        ficha_urgente = vista.ficha(urgente, [], ahora) if urgente else None
        return {
            "filas": filas,
            "filtro": filtro,
            "resumen": vista.resumen_bandeja(casos, ahora),
            "urgente": ficha_urgente,
            "siguiente": siguiente_paso(ctx, ficha_urgente, ahora),
            "integra": verificacion.integra,
            "nuevas": sum(1 for f in filas if f.nueva),
            "en_vivo": desde is not None,  # en la revisión periódica no se repiten las entradas
            "nuevas_revision": sum(1 for f in filas if f.nueva and f.clase_estado == "revision"),
            "ahora": ahora,
        }

    def filtro_de(request: Request) -> str:
        filtro = request.query_params.get("filtro", "abiertos")
        return filtro if filtro in FILTROS else "abiertos"

    async def bandeja(request: Request) -> Response:
        ctx = contexto(request)
        filtro = filtro_de(request)
        return responder(
            "bandeja.html",
            ctx=ctx,
            organizaciones=organizaciones,
            seccion="validados" if filtro == "validados" else "bandeja",
            **datos_bandeja(ctx, filtro, None),
        )

    async def bandeja_contenido(request: Request) -> Response:
        """Lo que pide htmx cada pocos segundos. No mantiene viva la sesión."""
        try:
            ctx = contexto(request, refrescar=False)
        except NoAutenticado:
            return Response(status_code=401, headers={"HX-Redirect": f"{BASE}/entrar?expirada=1"})
        try:
            desde = datetime.fromisoformat(request.query_params.get("desde", ""))
        except ValueError:
            desde = None
        return responder(
            "_bandeja_contenido.html", ctx=ctx, **datos_bandeja(ctx, filtro_de(request), desde)
        )

    # --- ficha del caso --------------------------------------------------------------

    def caso_o_404(ctx: Contexto, id_caso: str):
        try:
            return ctx.canal.caso_de_organizacion(ctx.org.id, id_caso)
        except CasoAjeno as e:
            raise HTTPException(404) from e

    def ver_ficha(
        ctx: Contexto,
        id_caso: str,
        *,
        status: int = 200,
        error: str | None = None,
        cambio: str | None = None,
        identidad: dict | None = None,
    ) -> HTMLResponse:
        caso = caso_o_404(ctx, id_caso)
        anotaciones = ctx.canal._repo.evidencia(caso.id)
        _, borradores = ctx.canal.borradores(ctx.org.id, caso.id)
        return responder(
            "caso.html",
            status,
            ctx=ctx,
            organizaciones=organizaciones,
            f=vista.ficha(caso, anotaciones, reloj()),
            borradores=vista.vista_borradores(caso, borradores),
            ahora=reloj(),
            seccion="bandeja",
            error=error,
            cambio=cambio,
            identidad=identidad,
            destinos=vista.vista_destinos(caso, ctx.org.nombre, ctx.canal._url_panel),
            areas_derivar=[
                (a.id, a.nombre)
                for a in ctx.canal._enrutamiento.organizaciones[ctx.org.id].areas
                if not caso.asignacion or a.id not in {d.id for d in caso.asignacion.destinos}
            ],
            ahora_local=reloj().astimezone(ZONA_CHILE).strftime("%Y-%m-%dT%H:%M"),
            minimo_local=caso.ingreso.astimezone(ZONA_CHILE).strftime("%Y-%m-%dT%H:%M"),
        )

    async def caso(request: Request) -> Response:
        ctx = contexto(request)
        cambio = request.query_params.get("cambio")
        if cambio not in ("corregido", "resuelto", "validado", "revisado", "enviado", "derivado"):
            cambio = None
        return ver_ficha(ctx, request.path_params["id"], cambio=cambio)

    async def accion(
        request: Request, hacer: Callable[[Contexto, dict, str], Any], cambio: str
    ) -> Response:
        ctx = contexto(request)
        datos = await formulario_seguro(request)
        id_caso = request.path_params["id"]
        try:
            hacer(ctx, datos, id_caso)
        except CasoAjeno as e:
            raise HTTPException(404) from e
        except AccionInvalida as e:
            return ver_ficha(ctx, id_caso, status=400, error=str(e))
        except DatosNoSinteticosError:
            return ver_ficha(
                ctx,
                id_caso,
                status=400,
                error="La nota parece tener datos reales. Usa solo datos ficticios.",
            )
        except (ValidationError, ValueError):
            return ver_ficha(ctx, id_caso, status=400, error="Revisa los datos del formulario.")
        return RedirectResponse(f"{BASE}/caso/{id_caso}?cambio={cambio}", 303)

    async def corregir(request: Request) -> Response:
        def hacer(ctx: Contexto, datos: dict, id_caso: str) -> None:
            ctx.canal.corregir_hechos(
                ctx.org.id,
                id_caso,
                _hechos_del_formulario(datos),
                motivo=_uno(datos, "motivo"),  # type: ignore[arg-type]
                nota=_uno(datos, "nota"),
                por=ctx.usuario,
            )

        return await accion(request, hacer, "corregido")

    async def resolver(request: Request) -> Response:
        def hacer(ctx: Contexto, datos: dict, id_caso: str) -> None:
            ctx.canal.resolver_deber(
                ctx.org.id,
                id_caso,
                _uno(datos, "deber"),
                _uno(datos, "decision"),
                motivo=_uno(datos, "motivo"),
                por=ctx.usuario,  # type: ignore[arg-type]
            )

        return await accion(request, hacer, "resuelto")

    async def validar(request: Request) -> Response:
        def hacer(ctx: Contexto, datos: dict, id_caso: str) -> None:
            ctx.canal.validar(ctx.org.id, id_caso, por=ctx.usuario)

        return await accion(request, hacer, "validado")

    async def registrar_envio(request: Request) -> Response:
        def hacer(ctx: Contexto, datos: dict, id_caso: str) -> None:
            texto = _uno(datos, "momento").strip()
            momento = None
            if texto:
                try:
                    momento = datetime.fromisoformat(texto)
                except ValueError as e:
                    raise AccionInvalida("Revisa la fecha y hora del envío.") from e
                if momento.tzinfo is None:
                    momento = momento.replace(tzinfo=ZONA_CHILE)
            canal_envio = _uno(datos, "canal")
            if canal_envio not in vista.CANALES_ENVIO:
                raise AccionInvalida("Elige por dónde lo enviaste.")
            ctx.canal.registrar_envio(
                ctx.org.id,
                id_caso,
                _uno(datos, "deber"),
                canal=canal_envio,  # type: ignore[arg-type]  # validado arriba
                por=ctx.usuario,
                momento=momento,
            )

        return await accion(request, hacer, "enviado")

    async def simulador(request: Request) -> Response:
        """Mismo incidente, ley vigente y postergación lado a lado. No guarda nada."""
        ctx = contexto(request)
        q = request.query_params
        id_caso = q.get("caso", "")
        caso_base = None
        if id_caso:
            try:
                caso_base = ctx.canal.caso_de_organizacion(ctx.org.id, id_caso)
            except CasoAjeno as e:
                raise HTTPException(404) from e
        ejemplo = q.get("ejemplo", "paseo")
        if ejemplo not in vista.EJEMPLOS_SIMULADOR:
            ejemplo = "paseo"
        if caso_base is not None and caso_base.hechos_vigentes is not None:
            hechos = caso_base.hechos_vigentes
        else:
            caso_base = None
            hechos = HechosIncidente(**vista.EJEMPLOS_SIMULADOR[ejemplo][1])
        perfil = q.get("perfil", ctx.org.perfil)
        if perfil not in PERFILES:
            perfil = ctx.org.perfil
        try:
            fecha = date.fromisoformat(q.get("fecha", "2027-03-01"))
        except ValueError:
            fecha = date(2027, 3, 1)
        enviado = "fecha" in q
        oiv = q.get("oiv") == "1" if enviado else ctx.org.operador_importancia_vital
        menor = q.get("menor") == "1"
        simulaciones = escenarios.comparar(hechos, perfil, fecha, oiv=oiv, menor_tamano=menor)  # type: ignore[arg-type]
        return responder(
            "simulador.html",
            ctx=ctx,
            organizaciones=organizaciones,
            seccion="simulador",
            simulaciones=simulaciones,
            filas=vista.comparar_filas(simulaciones),
            ejemplos=vista.EJEMPLOS_SIMULADOR,
            ejemplo=ejemplo,
            caso_base=caso_base,
            perfiles=PERFILES,
            perfil=perfil,
            fecha=fecha,
            oiv=oiv,
            menor=menor,
            extracto=next(
                (escenarios.extracto(s.escenario) for s in simulaciones if s.escenario.documento),
                None,
            ),
        )

    async def derivar(request: Request) -> Response:
        def hacer(ctx: Contexto, datos: dict, id_caso: str) -> None:
            motivo = _uno(datos, "motivo")
            if motivo not in vista.MOTIVOS_DERIVACION:
                raise AccionInvalida("Elige por qué lo derivas.")
            ctx.canal.derivar(
                ctx.org.id,
                id_caso,
                _uno(datos, "area"),
                motivo=motivo,  # type: ignore[arg-type]  # validado arriba
                por=ctx.usuario,
            )

        return await accion(request, hacer, "derivado")

    async def abrir_identidad(request: Request) -> Response:
        ctx = contexto(request)
        datos = await formulario_seguro(request)
        id_caso = request.path_params["id"]
        caso_o_404(ctx, id_caso)
        if ctx.demo:
            return ver_ficha(
                ctx, id_caso, status=403, error="En la demo no se abren identidades reservadas."
            )
        if config.limite.bloqueado(ctx.usuario):
            return ver_ficha(
                ctx, id_caso, status=429, error="Demasiados intentos. Espera 15 minutos."
            )
        assert config.usuarios is not None
        ok = await run_in_threadpool(
            config.usuarios.verificar, ctx.usuario, _uno(datos, "contrasena")
        )
        if ok is None:
            config.limite.fallo(ctx.usuario)
            return ver_ficha(ctx, id_caso, status=401, error="La contraseña no es correcta.")
        config.limite.exito(ctx.usuario)
        motivo = _uno(datos, "motivo")
        if motivo not in vista.MOTIVOS_IDENTIDAD:
            return ver_ficha(ctx, id_caso, status=400, error="Elige un motivo.")
        try:
            identidad = ctx.canal.abrir_identidad(
                ctx.org.id,
                id_caso,
                motivo=motivo,  # type: ignore[arg-type]
                por=ctx.usuario,
            )
        except (AccionInvalida, IdentidadReservadaError) as e:
            return ver_ficha(ctx, id_caso, status=400, error=str(e))
        return ver_ficha(ctx, id_caso, identidad=dict(identidad), cambio="identidad")

    # --- borradores de reporte --------------------------------------------------------

    def borrador_o_404(ctx: Contexto, id_caso: str, destino: str):
        if destino not in DESTINOS:
            raise HTTPException(404)
        try:
            caso, borradores = ctx.canal.borradores(ctx.org.id, id_caso)
        except CasoAjeno as e:
            raise HTTPException(404) from e
        b = borradores[destino]
        if not isinstance(b, Borrador):
            raise HTTPException(404)
        return caso, b

    def ver_borrador_pagina(
        ctx: Contexto, id_caso: str, destino: str, *, status: int = 200, error: str | None = None
    ) -> HTMLResponse:
        caso, b = borrador_o_404(ctx, id_caso, destino)
        return responder(
            "borrador.html",
            status,
            ctx=ctx,
            organizaciones=organizaciones,
            seccion="bandeja",
            caso=caso,
            b=b,
            nombre_destino=NOMBRE_DESTINO[b.destino],
            revision=ultima_revision(caso, b),
            error=error,
        )

    async def ver_borrador(request: Request) -> Response:
        ctx = contexto(request)
        return ver_borrador_pagina(ctx, request.path_params["id"], request.path_params["destino"])

    async def descargar_borrador(request: Request) -> Response:
        ctx = contexto(request)
        caso, b = borrador_o_404(ctx, request.path_params["id"], request.path_params["destino"])
        return Response(
            b.texto(),
            media_type="text/plain; charset=utf-8",
            headers=CABECERAS
            | {"Content-Disposition": f'attachment; filename="borrador-{b.destino}-{caso.id}.txt"'},
        )

    async def marcar_revisado(request: Request) -> Response:
        ctx = contexto(request)
        datos = await formulario_seguro(request)
        id_caso, destino = request.path_params["id"], request.path_params["destino"]
        borrador_o_404(ctx, id_caso, destino)
        try:
            ctx.canal.marcar_borrador_revisado(
                ctx.org.id, id_caso, destino, _uno(datos, "huella"), por=ctx.usuario
            )
        except AccionInvalida as e:
            return ver_borrador_pagina(ctx, id_caso, destino, status=400, error=str(e))
        return RedirectResponse(f"{BASE}/caso/{id_caso}?cambio=revisado", 303)

    # --- evidencia -------------------------------------------------------------------

    def datos_evidencia(
        verificacion: Verificacion, anotaciones: list[Anotacion], alterada: int | None = None
    ) -> dict[str, Any]:
        return {
            "v": verificacion,
            "bloques": anotaciones[-12:],
            "total_propias": len(anotaciones),
            "alterada": alterada,
        }

    async def ver_canal(request: Request) -> Response:
        """El enlace del canal de la organización y su código QR, para repartirlo o mostrarlo."""
        ctx = contexto(request)
        raiz = f"{request.url.scheme}://{request.url.netloc}"
        enlace = ctx.canal.enlace(ctx.org.id, raiz)
        # En la demo, el enlace lleva la sala: el reporte enviado desde el teléfono llega a la
        # misma copia que el participante ve en su panel.
        sufijo = f"?sala={ctx.sala}" if ctx.sala else ""
        return responder(
            "canal.html",
            ctx=ctx,
            organizaciones=organizaciones,
            seccion="canal",
            enlace=enlace + sufijo,
            qr=enlace[len(raiz) :] + "/qr.svg" + sufijo,
        )

    async def evidencia(request: Request) -> Response:
        ctx = contexto(request)
        v, propias = ctx.canal.evidencia_de_organizacion(ctx.org.id)
        return responder(
            "evidencia.html",
            ctx=ctx,
            organizaciones=organizaciones,
            seccion="evidencia",
            escaneo=False,
            # La cifra solo se calcula sobre una cadena que calza: si no, no es confiable.
            cifra=medir_correcciones(propias) if v.integra else None,
            **datos_evidencia(v, propias),
        )

    async def evidencia_revisar(request: Request) -> Response:
        ctx = contexto(request)
        await formulario_seguro(request)
        v, propias = await run_in_threadpool(ctx.canal.evidencia_de_organizacion, ctx.org.id)
        return responder("_verificacion.html", ctx=ctx, escaneo=True, **datos_evidencia(v, propias))

    async def evidencia_simular(request: Request) -> Response:
        ctx = contexto(request)
        if not ctx.demo:
            raise HTTPException(404)
        await formulario_seguro(request)
        v, propias, n = await run_in_threadpool(_simular_alteracion, ctx.canal, ctx.org.id)
        return responder(
            "_verificacion.html", ctx=ctx, escaneo=True, **datos_evidencia(v, propias, n)
        )

    # --- errores ---------------------------------------------------------------------

    async def no_autenticado(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, NoAutenticado)
        destino = f"{BASE}/entrar" + ("?expirada=1" if exc.expirada else "")
        if request.headers.get("hx-request"):
            return Response(status_code=401, headers={"HX-Redirect": destino})
        return RedirectResponse(destino, 303)

    async def error_http(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, HTTPException)
        mensajes = {
            403: "Esta acción no se pudo verificar. Recarga la página e inténtalo de nuevo.",
            404: "No encontramos esa página o ese caso.",
            405: "Esta página no admite esa acción.",
            413: "El formulario es demasiado largo.",
            415: "Envía el formulario desde el panel.",
        }
        return responder(
            "error.html",
            exc.status_code,
            mensaje=mensajes.get(exc.status_code, "Algo salió mal. Intenta de nuevo."),
        )

    rutas = [
        Route("/", bandeja, methods=["GET"]),
        Route("/bandeja/contenido", bandeja_contenido, methods=["GET"]),
        Route("/entrar", ver_entrar, methods=["GET"]),
        Route("/entrar", entrar, methods=["POST"]),
        Route("/salir", salir, methods=["POST"]),
        Route("/demo/organizacion", cambiar_organizacion, methods=["POST"]),
        Route("/caso/{id}", caso, methods=["GET"]),
        Route("/caso/{id}/corregir", corregir, methods=["POST"]),
        Route("/caso/{id}/resolver", resolver, methods=["POST"]),
        Route("/caso/{id}/validar", validar, methods=["POST"]),
        Route("/caso/{id}/enviado", registrar_envio, methods=["POST"]),
        Route("/caso/{id}/derivar", derivar, methods=["POST"]),
        Route("/caso/{id}/identidad", abrir_identidad, methods=["POST"]),
        Route("/caso/{id}/borrador/{destino}", ver_borrador, methods=["GET"]),
        Route("/caso/{id}/borrador/{destino}/descargar", descargar_borrador, methods=["GET"]),
        Route("/caso/{id}/borrador/{destino}/revisado", marcar_revisado, methods=["POST"]),
        Route("/canal", ver_canal, methods=["GET"]),
        Route("/simulador", simulador, methods=["GET"]),
        Route("/evidencia", evidencia, methods=["GET"]),
        Route("/evidencia/revisar", evidencia_revisar, methods=["POST"]),
        Route("/evidencia/simular", evidencia_simular, methods=["POST"]),
        Mount("/estaticos", app=StaticFiles(directory=CARPETA / "estaticos")),
    ]
    return Starlette(
        routes=rutas,
        middleware=[
            Middleware(
                SessionMiddleware,
                secret_key=config.secreto_sesion,
                session_cookie="panel_sesion",
                max_age=int(config.duracion_maxima.total_seconds()),
                path=BASE,
                same_site="strict",
                https_only=config.https,
            )
        ],
        exception_handlers={NoAutenticado: no_autenticado, HTTPException: error_http},
    )


__all__ = ["BASE", "ConfigPanel", "crear_panel"]
