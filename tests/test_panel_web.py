import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from privacidad.canal import RepositorioCasos
from privacidad.panel import LimiteIntentos
from privacidad.panel.web import CSP_PANEL

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    HECHOS_INCIDENTE,
    ClienteFalso,
)
from .panel_apoyo import CONTRASENA, Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"
ROBLES = "comercial-los-robles"
DUDOSO = HECHOS_INCIDENTE | {"categorias_especiales": [], "ciberincidente": "dudoso"}
CARPETA_PANEL = Path(__file__).parents[1] / "src" / "privacidad" / "panel"


class RelojSesion:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class TestIngreso(unittest.TestCase):
    def setUp(self):
        self.reloj = RelojSesion()
        self.app, self.canal, _ = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), reloj_sesion=self.reloj
        )
        self.nav = Navegador(self.app)

    def test_sin_sesion_pide_entrar(self):
        r = self.nav.pedir("GET", "/panel/")
        self.assertEqual(r.status, 303)
        self.assertEqual(r.cabeceras["location"], "/panel/entrar")

    def test_cabeceras_de_seguridad(self):
        r = self.nav.pedir("GET", "/panel/entrar")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.cabeceras["content-security-policy"], CSP_PANEL)
        self.assertIn("script-src 'self'", CSP_PANEL)
        self.assertNotIn("unsafe", CSP_PANEL)
        self.assertEqual(r.cabeceras["referrer-policy"], "same-origin")
        self.assertEqual(r.cabeceras["cache-control"], "no-store")
        self.assertEqual(r.cabeceras["x-frame-options"], "DENY")

    def test_entrar_crea_una_cookie_protegida(self):
        r = entrar(self.nav)
        self.assertEqual(r.status, 303)
        self.assertEqual(r.cabeceras["location"], "/panel/")
        cookie = r.cabeceras["set-cookie"].lower()
        for atributo in ("httponly", "samesite=strict", "secure", "path=/panel"):
            self.assertIn(atributo, cookie)
        self.assertEqual(self.nav.pedir("GET", "/panel/").status, 200)

    def test_error_generico_para_contrasena_o_usuario_malos(self):
        mala = entrar(self.nav, contrasena="no-es-la-contrasena")
        inexistente = entrar(self.nav, usuario="nadie-aqui", contrasena=CONTRASENA)
        self.assertEqual(mala.status, 401)
        self.assertEqual(inexistente.status, 401)
        self.assertIn("Usuario o contraseña incorrectos", mala.html)
        self.assertIn("Usuario o contraseña incorrectos", inexistente.html)
        self.assertNotIn(CONTRASENA, mala.html)

    def test_bloqueo_tras_varios_intentos(self):
        for _ in range(5):
            entrar(self.nav, contrasena="no-es-la-contrasena")
        r = entrar(self.nav)  # ahora con la contraseña correcta
        self.assertEqual(r.status, 429)
        self.assertIn("Demasiados intentos", r.html)

    def test_sin_codigo_csrf_o_desde_otro_sitio_se_rechaza(self):
        self.nav.pedir("GET", "/panel/entrar")
        sin_codigo = self.nav.pedir(
            "POST", "/panel/entrar", {"usuario": "delegado-muni", "contrasena": CONTRASENA}
        )
        self.assertEqual(sin_codigo.status, 403)
        pagina = self.nav.pedir("GET", "/panel/entrar")
        otro_sitio = self.nav.pedir(
            "POST",
            "/panel/entrar",
            {"csrf": pagina.csrf(), "usuario": "delegado-muni", "contrasena": CONTRASENA},
            cabeceras={"origin": "https://sitio-malicioso.example"},
            origen=False,
        )
        self.assertEqual(otro_sitio.status, 403)

    def test_la_sesion_expira_por_inactividad(self):
        entrar(self.nav)
        self.reloj.t += 20 * 60
        self.assertEqual(self.nav.pedir("GET", "/panel/").status, 200)
        self.reloj.t += 31 * 60
        r = self.nav.pedir("GET", "/panel/")
        self.assertEqual(r.status, 303)
        self.assertIn("expirada=1", r.cabeceras["location"])

    def test_la_revision_automatica_no_mantiene_viva_la_sesion(self):
        entrar(self.nav)
        for _ in range(4):
            self.reloj.t += 10 * 60
            self.nav.pedir("GET", "/panel/bandeja/contenido")
        r = self.nav.pedir("GET", "/panel/bandeja/contenido", cabeceras={"hx-request": "true"})
        self.assertEqual(r.status, 401)
        self.assertIn("/panel/entrar", r.cabeceras["hx-redirect"])

    def test_salir(self):
        entrar(self.nav)
        pagina = self.nav.pedir("GET", "/panel/")
        r = self.nav.pedir("POST", "/panel/salir", {"csrf": pagina.csrf()})
        self.assertEqual(r.status, 303)
        self.assertEqual(self.nav.pedir("GET", "/panel/").status, 303)


class TestAislamiento(unittest.TestCase):
    def test_un_delegado_no_alcanza_casos_de_otra_organizacion(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        ajeno = canal.recibir_incidente(ROBLES, "Planilla del paseo enviada por error.")
        propio = canal.recibir_incidente(MUNI, "Planilla de beneficios enviada por error.")
        nav = Navegador(app)
        entrar(nav, "delegado-muni")
        bandeja = nav.pedir("GET", "/panel/")
        self.assertIn(propio.id, bandeja.html)
        self.assertNotIn(ajeno.id, bandeja.html)
        self.assertEqual(nav.pedir("GET", f"/panel/caso/{ajeno.id}").status, 404)
        csrf = bandeja.csrf()
        for accion in ("validar", "corregir", "resolver", "identidad"):
            r = nav.pedir("POST", f"/panel/caso/{ajeno.id}/{accion}", {"csrf": csrf})
            self.assertEqual(r.status, 404, accion)
        self.assertIsNone(canal.obtener(ajeno.id).validacion)
        evidencia = nav.pedir("GET", "/panel/evidencia")
        self.assertNotIn(ajeno.id[:4] + "…", evidencia.html)


class TestAcciones(unittest.TestCase):
    def setUp(self):
        self.app, self.canal, _ = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE)
        )
        self.caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.nav = Navegador(self.app)
        entrar(self.nav)
        self.csrf = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}").csrf()

    def test_la_ficha_muestra_relojes_hechos_y_fuentes(self):
        r = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}")
        self.assertEqual(r.status, 200)
        self.assertIn("Primer aviso a la ANCI", r.html)
        self.assertIn("propuesto por la IA", r.html)
        self.assertIn("data-vence=", r.html)
        self.assertIn("Ver fuente legal", r.html)
        self.assertIn("Ley 21.663", r.html)

    def test_corregir_recalcula_y_redirige_con_el_cambio(self):
        datos = {
            "csrf": self.csrf,
            "vulneracion": "comunicacion_no_autorizada",
            "ciberincidente": "no",
            "datos_personales": "si",
            "riesgo_mitigado": "no",
            "interrupcion_servicio": "no",
            "titulares_aprox": "",
            "motivo": "confirmado_por_area",
            "nota": "",
        }
        r = self.nav.pedir("POST", f"/panel/caso/{self.caso.id}/corregir", datos)
        self.assertEqual(r.status, 303)
        self.assertIn("cambio=corregido", r.cabeceras["location"])
        caso = self.canal.obtener(self.caso.id)
        self.assertEqual(caso.resultado_incidente.reporte_anci.decision, "no")
        self.assertEqual(caso.correcciones[0].por, "delegado-muni")
        pagina = self.nav.pedir("GET", r.cabeceras["location"])
        self.assertIn("corregido por ti", pagina.html)
        self.assertIn("Corregiste los hechos", pagina.html)

    def test_formulario_malo_responde_400(self):
        r = self.nav.pedir(
            "POST",
            f"/panel/caso/{self.caso.id}/corregir",
            {"csrf": self.csrf, "vulneracion": "inventada", "ciberincidente": "no", "motivo": "x"},
        )
        self.assertEqual(r.status, 400)
        self.assertIn("Completa todos los campos", r.html)
        completo = {
            "csrf": self.csrf,
            "vulneracion": "inventada",
            "ciberincidente": "no",
            "datos_personales": "si",
            "riesgo_mitigado": "no",
            "interrupcion_servicio": "no",
            "motivo": "error_ia",
        }
        r = self.nav.pedir("POST", f"/panel/caso/{self.caso.id}/corregir", completo)
        self.assertEqual(r.status, 400)
        self.assertIn("Revisa los datos", r.html)

    def test_validar(self):
        r = self.nav.pedir("POST", f"/panel/caso/{self.caso.id}/validar", {"csrf": self.csrf})
        self.assertEqual(r.status, 303)
        pagina = self.nav.pedir("GET", r.cabeceras["location"])
        self.assertIn("Validado por delegado-muni", pagina.html)


class TestDudasPorLaWeb(unittest.TestCase):
    def test_no_valida_con_dudas_y_luego_si(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=DUDOSO))
        caso = canal.recibir_incidente(MUNI, "Se vio una planilla de otra área.")
        nav = Navegador(app)
        entrar(nav)
        csrf = nav.pedir("GET", f"/panel/caso/{caso.id}").csrf()
        r = nav.pedir("POST", f"/panel/caso/{caso.id}/validar", {"csrf": csrf})
        self.assertEqual(r.status, 400)
        self.assertIn("Decide tú", r.html)
        r = nav.pedir(
            "POST",
            f"/panel/caso/{caso.id}/resolver",
            {"csrf": csrf, "deber": "reporte_anci", "decision": "no", "motivo": "consulta_area"},
        )
        self.assertEqual(r.status, 303)
        r = nav.pedir("POST", f"/panel/caso/{caso.id}/validar", {"csrf": csrf})
        self.assertEqual(r.status, 303)


class TestIdentidad(unittest.TestCase):
    def setUp(self):
        self.app, self.canal, _ = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_INCIDENTE)
        )
        self.caso = self.canal.recibir_incidente(
            ROBLES, "Un aviso reservado.", reservado=True, nombre="Persona Ficticia Cinco"
        )
        self.nav = Navegador(self.app)
        entrar(self.nav, "delegado-robles")
        self.csrf = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}").csrf()

    def abrir(self, contrasena):
        return self.nav.pedir(
            "POST",
            f"/panel/caso/{self.caso.id}/identidad",
            {"csrf": self.csrf, "contrasena": contrasena, "motivo": "contactar_a_quien_reporto"},
        )

    def test_pide_la_contrasena_y_deja_constancia(self):
        mala = self.abrir("no-es-la-contrasena")
        self.assertEqual(mala.status, 401)
        self.assertNotIn("Persona Ficticia Cinco", mala.html)
        buena = self.abrir(CONTRASENA)
        self.assertEqual(buena.status, 200)
        self.assertIn("Persona Ficticia Cinco", buena.html)
        caso = self.canal.obtener(self.caso.id)
        self.assertEqual(caso.eventos[-1].tipo, "identidad_abierta")
        self.assertEqual(caso.eventos[-1].detalle["por"], "delegado-robles")
        despues = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}")
        self.assertNotIn("Persona Ficticia Cinco", despues.html)


class TestDemo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = RepositorioCasos(Path(self.tmp.name))
        self.app, self.canal, _ = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), demo=True, repositorio=self.repo
        )
        self.nav = Navegador(self.app)

    def tearDown(self):
        self.repo.cerrar()
        self.tmp.cleanup()

    def test_entra_sin_contrasena_con_aviso(self):
        r = self.nav.pedir("GET", "/panel/")
        self.assertEqual(r.status, 200)
        self.assertIn("demo pública", r.html)
        self.assertEqual(self.nav.pedir("GET", "/panel/entrar").status, 303)

    def test_cambiar_de_organizacion(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        csrf = self.nav.pedir("GET", "/panel/").csrf()
        self.nav.pedir("POST", "/panel/demo/organizacion", {"csrf": csrf, "org": MUNI})
        self.assertIn(caso.id, self.nav.pedir("GET", "/panel/").html)

    def test_en_la_demo_no_se_abren_identidades(self):
        caso = self.canal.recibir_incidente(
            ROBLES, "Aviso reservado.", reservado=True, nombre="X Y"
        )
        csrf = self.nav.pedir("GET", "/panel/").csrf()
        r = self.nav.pedir(
            "POST",
            f"/panel/caso/{caso.id}/identidad",
            {"csrf": csrf, "contrasena": "lo-que-sea", "motivo": "otro"},
        )
        self.assertEqual(r.status, 403)
        self.assertNotIn("X Y", r.html)

    def test_la_alteracion_simulada_es_real_pero_sobre_una_copia(self):
        csrf = self.nav.pedir("GET", "/panel/").csrf()
        self.nav.pedir("POST", "/panel/demo/organizacion", {"csrf": csrf, "org": MUNI})
        for i in range(2):
            self.canal.recibir_incidente(MUNI, f"Accedieron sin permiso al sistema {i}.")
        r = self.nav.pedir("POST", "/panel/evidencia/simular", {"csrf": csrf})
        self.assertEqual(r.status, 200)
        self.assertIn("fue alterada", r.html)
        self.assertIn("fue modificada", r.html)
        self.assertTrue(self.repo.verificar_evidencia().integra)
        r = self.nav.pedir("POST", "/panel/evidencia/revisar", {"csrf": csrf})
        self.assertIn("Registro íntegro", r.html)

    def test_la_bandeja_marca_lo_que_llego_despues(self):
        csrf = self.nav.pedir("GET", "/panel/").csrf()
        self.nav.pedir("POST", "/panel/demo/organizacion", {"csrf": csrf, "org": MUNI})
        desde = "2026-12-02T09:59:00-03:00"
        self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        r = self.nav.pedir("GET", f"/panel/bandeja/contenido?desde={desde}")
        self.assertIn("fila nueva", r.html)
        self.assertIn("Llegó un reporte nuevo", r.html)


class TestSinInterferencia(unittest.TestCase):
    def test_pantalla_del_canal_con_enlace_firmado(self):
        app, canal, _ = crear_panel_de_prueba(None, demo=True)
        r = Navegador(app).pedir("GET", "/panel/canal")
        self.assertEqual(r.status, 200)
        enlace = canal.enlace("comercial-los-robles", "https://canal.ejemplo.cl")
        self.assertIn(enlace, r.html)
        self.assertIn(enlace.removeprefix("https://canal.ejemplo.cl") + "/qr.svg", r.html)

    def test_ruta_de_salud_para_el_hosting(self):
        app, *_ = crear_panel_de_prueba(None)
        r = Navegador(app).pedir("GET", "/salud")
        self.assertEqual((r.status, r.cuerpo), (200, b"ok"))

    def test_el_canal_publico_sigue_igual(self):
        app, canal, _ = crear_panel_de_prueba(None)
        r = Navegador(app).pedir("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIsNone(Navegador(app).cookie)


class TestPlantillasSinCodigoEnLinea(unittest.TestCase):
    """La política de contenido prohíbe scripts y estilos escritos dentro de las páginas."""

    def test_sin_script_ni_style_ni_manejadores_en_linea(self):
        for ruta in (CARPETA_PANEL / "plantillas").glob("*.html"):
            texto = ruta.read_text("utf-8")
            self.assertNotRegex(texto, r"<script(?![^>]*\bsrc=)", ruta.name)
            self.assertNotIn("<style", texto, ruta.name)
            self.assertNotRegex(texto, r"\sstyle=", ruta.name)
            self.assertNotRegex(texto, r"\son[a-z]+=", ruta.name)
            self.assertNotIn("hx-on", texto, ruta.name)


class TestLimite(unittest.TestCase):
    def test_bloquea_y_libera(self):
        ahora = [0.0]
        from datetime import datetime, timedelta

        base = datetime(2026, 12, 2)
        limite = LimiteIntentos(maximo=3, reloj=lambda: base + timedelta(seconds=ahora[0]))
        for _ in range(3):
            limite.fallo("a")
        self.assertTrue(limite.bloqueado("a"))
        self.assertFalse(limite.bloqueado("b"))
        ahora[0] = 16 * 60
        self.assertFalse(limite.bloqueado("a"))


class TestCopia(unittest.TestCase):
    def test_copiar_a_no_toca_la_base_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
            canal.recibir_incidente(MUNI, "Planilla enviada por error.")
            destino = Path(tmp) / "copia.sqlite3"
            canal._repo.copiar_a(destino)
            con = sqlite3.connect(destino)
            n = con.execute("SELECT COUNT(*) FROM evidencia").fetchone()[0]
            con.close()
            self.assertEqual(n, len(canal._repo.evidencia()))
            self.assertTrue(re.fullmatch(r"\d+", str(n)))


if __name__ == "__main__":
    unittest.main()
