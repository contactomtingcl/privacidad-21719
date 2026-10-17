import asyncio
import sys
import unittest
from unittest import mock
from urllib.parse import urlencode

from privacidad.canal import crear_app
from privacidad.canal.confirmacion import dias_de_espera

from .canal_apoyo import (
    HECHOS_INCIDENTE,
    SOLICITUD_AMBIGUA,
    SOLICITUD_CLARA,
    ClienteFalso,
    crear_canal,
)

BASE = "https://canal.ejemplo.cl"
ROBLES = "comercial-los-robles"
CORREO = "persona.uno@example.com"
FORM = "application/x-www-form-urlencoded"


class Respuesta:
    def __init__(self, status, cabeceras, cuerpo):
        self.status = status
        self.cabeceras = cabeceras
        self.cuerpo = cuerpo

    @property
    def html(self) -> str:
        return self.cuerpo.decode("utf-8")


def pedir(app, metodo, ruta, datos=None, *, cuerpo=None, tipo=FORM, cabeceras=None):
    """Llama a la aplicación ASGI directamente, sin servidor ni red."""
    if cuerpo is None:
        cuerpo = urlencode(datos or {}, doseq=True).encode() if metodo == "POST" else b""
    encabezados = [(b"host", b"canal.ejemplo.cl")]
    if metodo == "POST":
        encabezados += [
            (b"content-type", tipo.encode()),
            (b"content-length", str(len(cuerpo)).encode()),
        ]
    encabezados += [(k.lower().encode(), v.encode()) for k, v in (cabeceras or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": metodo,
        "scheme": "https",
        "path": ruta,
        "raw_path": ruta.encode(),
        "query_string": b"",
        "headers": encabezados,
        "server": ("canal.ejemplo.cl", 443),
        "client": ("203.0.113.9", 50000),
    }
    recibido = {}

    async def correr():
        pendiente = [{"type": "http.request", "body": cuerpo, "more_body": False}]

        async def receive():
            return pendiente.pop(0) if pendiente else {"type": "http.disconnect"}

        trozos = []

        async def send(mensaje):
            if mensaje["type"] == "http.response.start":
                recibido["status"] = mensaje["status"]
                recibido["cabeceras"] = {
                    k.decode().lower(): v.decode() for k, v in mensaje["headers"]
                }
            elif mensaje["type"] == "http.response.body":
                trozos.append(mensaje.get("body", b""))

        await app(scope, receive, send)
        return b"".join(trozos)

    cuerpo_resp = asyncio.run(correr())
    return Respuesta(recibido["status"], recibido["cabeceras"], cuerpo_resp)


class Base(unittest.TestCase):
    ia = None

    def setUp(self):
        self.ia = self.ia or ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA)
        self.canal, self.reloj, _ = crear_canal(self.ia)
        self.app = crear_app(self.canal, BASE)
        self.ruta = "/" + self.canal.enlace(ROBLES, BASE).split("/", 3)[3]

    def enviar_solicitud(self, **extra):
        datos = {
            "tipo": "solicitud",
            "texto": "Quiero saber qué datos tienen de mí.",
            "nombre": "Persona Ficticia Uno",
            "contacto": CORREO,
        } | extra
        return pedir(self.app, "POST", self.ruta, datos)


class TestPaginas(Base):
    def test_inicio(self):
        r = pedir(self.app, "GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn("Canal de privacidad", r.html)

    def test_formulario_de_la_organizacion(self):
        r = pedir(self.app, "GET", self.ruta)
        self.assertEqual(r.status, 200)
        self.assertIn("Comercial Los Robles", r.html)
        self.assertIn('lang="es"', r.html)
        self.assertIn("Prototipo con datos ficticios", r.html)

    def test_modo_reservado_visible_y_habilitado_solo_si_hay_llave(self):
        self.assertNotIn(
            'name="reservado" value="1" disabled', pedir(self.app, "GET", self.ruta).html
        )
        canal, *_ = crear_canal(None, con_reservado=False)
        app = crear_app(canal, BASE)
        ruta = "/" + canal.enlace(ROBLES, BASE).split("/", 3)[3]
        html = pedir(app, "GET", ruta).html
        self.assertIn('name="reservado" value="1" disabled', html)
        self.assertIn("No está disponible en este canal", html)

    def test_firma_invalida_responde_igual_que_pagina_inexistente(self):
        mala = pedir(self.app, "GET", f"/canal/{ROBLES}/firma-inventada-que-no-vale")
        inexistente = pedir(self.app, "GET", "/no/existe")
        otra_org = pedir(self.app, "GET", "/canal/no-existe/" + self.ruta.rsplit("/", 1)[1])
        self.assertEqual({mala.status, inexistente.status, otra_org.status}, {404})
        self.assertEqual(mala.html, inexistente.html)
        self.assertEqual(mala.html, otra_org.html)

    def test_metodo_no_permitido(self):
        r = pedir(self.app, "POST", "/", {"a": "b"})
        self.assertEqual(r.status, 405)
        self.assertIn("allow", r.cabeceras)
        self.assertEqual(pedir(self.app, "GET", self.ruta + "/confirmar").status, 404)

    def test_cabeceras_de_seguridad_en_todas_las_respuestas(self):
        for r in (
            pedir(self.app, "GET", self.ruta),
            pedir(self.app, "GET", "/no/existe"),
            self.enviar_solicitud(),
        ):
            self.assertEqual(r.cabeceras["cache-control"], "no-store")
            self.assertEqual(r.cabeceras["x-content-type-options"], "nosniff")
            self.assertEqual(r.cabeceras["referrer-policy"], "no-referrer")
            self.assertEqual(r.cabeceras["x-frame-options"], "DENY")
            csp = r.cabeceras["content-security-policy"]
            self.assertIn("default-src 'none'", csp)
            self.assertNotIn("script-src", csp)
            self.assertIn("frame-ancestors 'none'", csp)

    def test_las_paginas_no_traen_scripts(self):
        self.assertNotIn("<script", pedir(self.app, "GET", self.ruta).html.lower())


class TestEnvioDeSolicitud(Base):
    def test_flujo_completo_hasta_el_seguimiento(self):
        r = self.enviar_solicitud()
        self.assertEqual(r.status, 303)
        destino = r.cabeceras["location"]
        self.assertTrue(destino.startswith("/seguimiento/"))
        seguimiento = pedir(self.app, "GET", destino)
        self.assertEqual(seguimiento.status, 200)
        self.assertIn("Recibimos su mensaje", seguimiento.html)
        self.assertIn("1 de enero de 2027", seguimiento.html)
        self.assertIn(destino.rsplit("/", 1)[1], seguimiento.html)

    def test_la_pagina_de_seguimiento_no_repite_el_relato_ni_la_identidad(self):
        destino = self.enviar_solicitud().cabeceras["location"]
        html = pedir(self.app, "GET", destino).html
        self.assertNotIn("Persona Ficticia Uno", html)
        self.assertNotIn(CORREO, html)

    def test_faltan_datos_vuelve_al_formulario_con_el_mensaje(self):
        r = self.enviar_solicitud(nombre="")
        self.assertEqual(r.status, 400)
        self.assertIn("Falta completar", r.html)
        self.assertIn("Quiero saber qué datos tienen de mí.", r.html)  # no pierde lo escrito
        self.assertEqual(self.canal.casos_de(ROBLES), [])

    def test_datos_que_parecen_reales_se_rechazan(self):
        r = self.enviar_solicitud(contacto="juan.perez@gmail.com")
        self.assertEqual(r.status, 400)
        self.assertIn("parecen reales", r.html)
        self.assertEqual(self.ia.llamadas, [])

    def test_solicitud_en_modo_reservado_no_se_acepta(self):
        r = self.enviar_solicitud(reservado="1")
        self.assertEqual(r.status, 400)
        self.assertIn("solo para avisos de incidente", r.html)
        self.assertEqual(self.canal.casos_de(ROBLES), [])

    def test_lo_que_escribe_la_persona_se_escapa(self):
        ataque = '"><script>alert(1)</script>'
        r = self.enviar_solicitud(texto=ataque, nombre="")  # falta el nombre: se vuelve a mostrar
        self.assertEqual(r.status, 400)
        self.assertNotIn("<script>alert(1)</script>", r.html)
        self.assertIn("&lt;script&gt;", r.html)


class TestIncidentesPorLaWeb(Base):
    ia = ClienteFalso(registrar_hechos=HECHOS_INCIDENTE)

    def enviar_incidente(self, **extra):
        datos = {
            "tipo": "incidente",
            "texto": "Vi que enviaron una planilla a un tercero.",
        } | extra
        return pedir(self.app, "POST", self.ruta, datos)

    def test_aviso_anonimo(self):
        r = self.enviar_incidente()
        self.assertEqual(r.status, 303)
        html = pedir(self.app, "GET", r.cabeceras["location"]).html
        self.assertIn("quedó anónimo", html)

    def test_aviso_reservado(self):
        r = self.enviar_incidente(reservado="1", nombre="Persona Ficticia Uno", contacto=CORREO)
        self.assertEqual(r.status, 303)
        html = pedir(self.app, "GET", r.cabeceras["location"]).html
        self.assertIn("modo reservado", html)
        self.assertIn("llave de acceso restringido", html)
        self.assertNotIn("Persona Ficticia Uno", html)
        id_caso = r.cabeceras["location"].rsplit("/", 1)[1]
        guardado = self.canal.obtener(id_caso)
        self.assertTrue(guardado.identidad_cifrada)
        self.assertNotIn("Persona Ficticia Uno", guardado.model_dump_json())

    def test_reservado_sin_llave_se_informa(self):
        canal, *_ = crear_canal(ClienteFalso(), con_reservado=False)
        app = crear_app(canal, BASE)
        ruta = "/" + canal.enlace(ROBLES, BASE).split("/", 3)[3]
        r = pedir(
            app,
            "POST",
            ruta,
            {"tipo": "incidente", "texto": "Un aviso reservado.", "reservado": "1"},
        )
        self.assertEqual(r.status, 400)
        self.assertIn("no está disponible", r.html)

    def test_tipo_desconocido(self):
        r = self.enviar_incidente(tipo="otra-cosa")
        self.assertEqual(r.status, 400)


class TestConfirmacionPorLaWeb(Base):
    ia = ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA)

    def abrir(self):
        destino = self.enviar_solicitud().cabeceras["location"]
        return destino, destino.rsplit("/", 1)[1]

    def test_muestra_la_pregunta_las_opciones_y_la_espera(self):
        destino, _ = self.abrir()
        html = pedir(self.app, "GET", destino).html
        self.assertIn("necesitamos confirmar", html)
        self.assertIn("publicidad", html)
        self.assertIn(f"Si no responde en {dias_de_espera()} días", html)
        self.assertIn("Que borren mis datos", html)
        self.assertIn("Este plazo corre desde que llegó su mensaje", html)
        self.assertIn("extenderlo una sola vez, hasta por 30 días más", html)

    def test_avisa_el_bloqueo_preventivo_sin_marcarlo_en_el_formulario(self):
        destino, _ = self.abrir()
        html = pedir(self.app, "GET", destino).html
        self.assertIn("por precaución, no usaremos sus datos", html)
        # Se marca lo que propuso el sistema, no el bloqueo preventivo: confirmar sin tocar nada
        # no debe pedir el bloqueo.
        self.assertIn('value="oposicion" checked', html)
        self.assertNotIn('value="bloqueo" checked', html)

    def test_el_titular_corrige_y_ve_lo_que_se_tramita(self):
        destino, id_caso = self.abrir()
        r = pedir(
            self.app,
            "POST",
            destino + "/confirmar",
            {"derechos": ["supresion"], "detalle": "Borren todo"},
        )
        self.assertEqual((r.status, r.cabeceras["location"]), (303, destino))
        html = pedir(self.app, "GET", destino).html
        self.assertIn("Gracias por confirmar", html)
        self.assertIn("Que borren mis datos", html)
        self.assertEqual(self.canal.obtener(id_caso).confirmacion.estado, "corregida")

    def test_sin_elegir_nada_se_pide_elegir(self):
        destino, _ = self.abrir()
        r = pedir(self.app, "POST", destino + "/confirmar", {"detalle": "hola"})
        self.assertEqual(r.status, 400)
        self.assertIn("Elija al menos una opción", r.html)
        self.assertIn("necesitamos confirmar", r.html)  # sigue viendo la pregunta

    def test_opcion_inventada(self):
        destino, _ = self.abrir()
        r = pedir(self.app, "POST", destino + "/confirmar", {"derechos": ["inventado"]})
        self.assertEqual(r.status, 400)

    def test_detalle_con_datos_reales(self):
        destino, _ = self.abrir()
        r = pedir(
            self.app,
            "POST",
            destino + "/confirmar",
            {"derechos": ["oposicion"], "detalle": "ana@gmail.com"},
        )
        self.assertEqual(r.status, 400)
        self.assertIn("parecen reales", r.html)

    def test_pasada_la_espera_se_ve_la_lectura_reversible_y_se_avisa_que_puede_pedir_borrar(self):
        destino, id_caso = self.abrir()
        self.reloj.avanzar(days=dias_de_espera() + 1)
        html = pedir(self.app, "GET", destino).html
        self.assertIn("Como no recibimos su respuesta", html)
        self.assertIn("sin borrar ningún dato", html)
        self.assertIn("Que dejen de usar mis datos para un fin", html)
        self.assertIn("Que no usen mis datos mientras se resuelve", html)
        self.assertIn("Si quiere que borremos sus datos", html)
        self.assertIn("pedir que borremos sus datos", html)
        self.assertIn("Sobre dejar de usar sus datos mientras se resuelve", html)
        self.assertEqual(self.canal.obtener(id_caso).confirmacion.vigente, ["oposicion", "bloqueo"])

    def test_la_espera_avisa_que_no_se_borra_nada(self):
        destino, _ = self.abrir()
        html = pedir(self.app, "GET", destino).html
        self.assertIn("sin borrarlos", html)

    def test_pedir_la_supresion_despues_del_defecto(self):
        destino, id_caso = self.abrir()
        self.reloj.avanzar(days=dias_de_espera() + 1)
        pedir(self.app, "GET", destino)
        r = pedir(self.app, "POST", destino + "/confirmar", {"derechos": ["supresion"]})
        self.assertEqual(r.status, 303)
        self.assertEqual(self.canal.obtener(id_caso).confirmacion.vigente, ["supresion"])

    def test_codigos_invalidos_o_desconocidos(self):
        self.assertEqual(pedir(self.app, "GET", "/seguimiento/codigo-inexistente-1").status, 404)
        self.assertEqual(pedir(self.app, "GET", "/seguimiento/corto").status, 404)
        r = pedir(
            self.app,
            "POST",
            "/seguimiento/codigo-inexistente-1/confirmar",
            {"derechos": ["acceso"]},
        )
        self.assertEqual(r.status, 404)


class TestCuerpoDeLaPeticion(Base):
    def test_cuerpo_demasiado_grande(self):
        r = pedir(self.app, "POST", self.ruta, cuerpo=b"texto=" + b"a" * 30_000)
        self.assertEqual(r.status, 413)
        self.assertEqual(self.canal.casos_de(ROBLES), [])

    def test_content_length_mentiroso_tambien_se_corta(self):
        r = pedir(
            self.app,
            "POST",
            self.ruta,
            cuerpo=b"texto=" + b"a" * 30_000,
            cabeceras={"x-ignorado": "1"},
        )
        self.assertEqual(r.status, 413)

    def test_solo_formularios(self):
        r = pedir(self.app, "POST", self.ruta, cuerpo=b'{"texto": "hola"}', tipo="application/json")
        self.assertEqual(r.status, 415)

    def test_bytes_que_no_son_utf8(self):
        r = pedir(self.app, "POST", self.ruta, cuerpo=b"texto=\xff\xfe\xfa")
        self.assertEqual(r.status, 400)

    def test_demasiados_campos(self):
        cuerpo = "&".join(f"c{i}=1" for i in range(200)).encode()
        self.assertEqual(pedir(self.app, "POST", self.ruta, cuerpo=cuerpo).status, 400)


class TestCodigoQr(Base):
    def test_sirve_el_svg_del_enlace_firmado(self):
        falso = mock.MagicMock()
        falso.make_qr.return_value.save.side_effect = lambda salida, **kw: salida.write(b"<svg/>")
        with mock.patch.dict(sys.modules, {"segno": falso}):
            r = pedir(self.app, "GET", self.ruta + "/qr.svg")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.cabeceras["content-type"], "image/svg+xml")
        self.assertIn("sandbox", r.cabeceras["content-security-policy"])
        falso.make_qr.assert_called_once_with(BASE + self.ruta, error="m")

    def test_firma_mala_no_da_qr(self):
        self.assertEqual(
            pedir(self.app, "GET", f"/canal/{ROBLES}/mala-firma-1234567890/qr.svg").status, 404
        )

    def test_sin_segno_responde_no_disponible(self):
        with mock.patch.dict(sys.modules, {"segno": None}):
            r = pedir(self.app, "GET", self.ruta + "/qr.svg")
        self.assertEqual(r.status, 503)

    def test_con_segno_real(self):
        try:
            import segno  # noqa: F401
        except ImportError:
            self.skipTest("segno no está instalada aquí (sí en GitHub Actions)")
        r = pedir(self.app, "GET", self.ruta + "/qr.svg")
        self.assertEqual(r.status, 200)
        self.assertIn("<svg", r.html)


class TestOtrosEstados(Base):
    def test_sin_ia_el_titular_ve_que_una_persona_revisara(self):
        canal, *_ = crear_canal(None)
        app = crear_app(canal, BASE)
        ruta = "/" + canal.enlace(ROBLES, BASE).split("/", 3)[3]
        r = pedir(
            app,
            "POST",
            ruta,
            {
                "tipo": "solicitud",
                "texto": "Quiero mis datos, gracias.",
                "nombre": "Persona Ficticia Uno",
                "contacto": CORREO,
            },
        )
        html = pedir(app, "GET", r.cabeceras["location"]).html
        self.assertIn("Una persona del equipo revisará su mensaje", html)
        self.assertIn("1 de enero de 2027", html)

    def test_mensaje_que_no_es_una_solicitud(self):
        canal, *_ = crear_canal(
            ClienteFalso(interpretar_solicitud={"es_solicitud": False, "derechos": []})
        )
        app = crear_app(canal, BASE)
        ruta = "/" + canal.enlace(ROBLES, BASE).split("/", 3)[3]
        r = pedir(
            app,
            "POST",
            ruta,
            {
                "tipo": "solicitud",
                "texto": "Gracias por todo, adiós.",
                "nombre": "Persona Ficticia Uno",
                "contacto": CORREO,
            },
        )
        html = pedir(app, "GET", r.cabeceras["location"]).html
        self.assertIn("no parece pedir algo sobre sus datos", html)
