import unittest

from privacidad.reportes import huella_sin_digitos

from .canal_apoyo import HECHOS_CIBERATAQUE, HECHOS_INCIDENTE, ClienteFalso, rut_ficticio
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"
ROBLES = "comercial-los-robles"
NOMBRE = "Rosa Valdivia Ficticia"
CORREO = "rosa@municipalidad-piloto.example"


class TestBorradoresEnElPanel(unittest.TestCase):
    def setUp(self):
        self.app, self.canal, self.reloj = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE | {"resumen": "Acceso indebido."})
        )
        self.caso = self.canal.recibir_incidente(
            MUNI,
            f"Entraron al servidor con la clave de {NOMBRE}, RUT {rut_ficticio(4)}.",
            nombre=NOMBRE,
            contacto=CORREO,
        )
        self.nav = Navegador(self.app)
        entrar(self.nav)
        self.ruta = f"/panel/caso/{self.caso.id}/borrador"

    def test_la_ficha_muestra_los_dos_borradores(self):
        r = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}")
        self.assertEqual(r.status, 200)
        self.assertIn("Borradores de reporte", r.html)
        self.assertIn(f"{self.ruta}/agencia", r.html)
        self.assertIn(f"{self.ruta}/anci", r.html)

    def test_la_pagina_del_borrador_anci_no_muestra_datos_personales(self):
        r = self.nav.pedir("GET", f"{self.ruta}/anci")
        self.assertEqual(r.status, 200)
        self.assertIn("Alerta temprana", r.html)
        self.assertIn('<mark class="completar">', r.html)
        for dato in (NOMBRE, CORREO, rut_ficticio(4)):
            self.assertNotIn(dato, r.html)

    def test_descarga_el_texto(self):
        r = self.nav.pedir("GET", f"{self.ruta}/anci/descargar")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.cabeceras["content-type"].startswith("text/plain"))
        self.assertIn("attachment", r.cabeceras["content-disposition"])
        self.assertIn("Borrador de reporte al CSIRT Nacional", r.cuerpo.decode())

    def test_marcar_revisado_queda_en_la_evidencia(self):
        pagina = self.nav.pedir("GET", f"{self.ruta}/anci")
        _, b = self.canal.borradores(MUNI, self.caso.id)
        r = self.nav.pedir(
            "POST",
            f"{self.ruta}/anci/revisado",
            {"csrf": pagina.csrf(), "huella": b["anci"].huella},
        )
        self.assertEqual(r.status, 303)
        self.assertIn("cambio=revisado", r.cabeceras["location"])
        ultima = self.canal._repo.evidencia(self.caso.id)[-1]
        self.assertEqual(ultima.tipo, "borrador_revisado")
        self.assertEqual(ultima.detalle["huella"], huella_sin_digitos(b["anci"].huella))
        self.assertEqual(ultima.detalle["por"], "delegado-muni")
        ficha = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}?cambio=revisado")
        self.assertIn("Marcaste que revisaste el borrador", ficha.html)
        self.assertIn("todavía no lo envías", ficha.html)
        self.assertIn("revisó un borrador de reporte", ficha.html)

    def test_huella_antigua_muestra_el_error_sin_anotar(self):
        pagina = self.nav.pedir("GET", f"{self.ruta}/anci")
        antes = len(self.canal._repo.evidencia(self.caso.id))
        r = self.nav.pedir(
            "POST", f"{self.ruta}/anci/revisado", {"csrf": pagina.csrf(), "huella": "0" * 64}
        )
        self.assertEqual(r.status, 400)
        self.assertIn("El borrador cambió", r.html)
        self.assertEqual(len(self.canal._repo.evidencia(self.caso.id)), antes)

    def test_sin_codigo_csrf_se_rechaza(self):
        r = self.nav.pedir("POST", f"{self.ruta}/anci/revisado", {"huella": "x"})
        self.assertEqual(r.status, 403)

    def test_destino_desconocido_o_sin_borrador_responde_404(self):
        self.assertEqual(self.nav.pedir("GET", f"{self.ruta}/otro").status, 404)
        self.canal._cliente.entradas["registrar_hechos"] = HECHOS_INCIDENTE | {"resumen": "x"}
        papel = self.canal.recibir_incidente(MUNI, "Se envió una planilla por error.")
        r = self.nav.pedir("GET", f"/panel/caso/{papel.id}/borrador/anci")
        self.assertEqual(r.status, 404)

    def test_otra_organizacion_no_ve_el_borrador(self):
        otro = Navegador(self.app)
        entrar(otro, usuario="delegado-robles")
        for ruta in (f"{self.ruta}/anci", f"{self.ruta}/anci/descargar"):
            self.assertEqual(otro.pedir("GET", ruta).status, 404)


if __name__ == "__main__":
    unittest.main()
