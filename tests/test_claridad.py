"""Cambios de claridad del 17 de octubre (revisión de diseño con la mentora de Soho).

Lo que se prueba aquí es que las pantallas digan las cosas con exactitud: ninguna etiqueta cambia
una decisión del motor ni oculta un plazo, un vencimiento o una alteración de la evidencia.
"""

import re
import unittest

from markupsafe import Markup

from privacidad.iconos import icono
from privacidad.motor import cargar_reglas
from privacidad.panel import vista

from .canal_apoyo import HECHOS_CIBERATAQUE, ClienteFalso, RelojFijo, crear_canal
from .panel_apoyo import HOST, Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"


class TestIconos(unittest.TestCase):
    def test_decorativo_y_del_color_del_texto(self):
        svg = icono("clock", 16)
        self.assertIsInstance(svg, Markup)
        self.assertIn('aria-hidden="true"', svg)
        self.assertIn('stroke="currentColor"', svg)
        self.assertNotIn("<script", svg)

    def test_rechaza_nombres_raros(self):
        with self.assertRaises(ValueError):
            icono("../reglas")


class TestResumenBandeja(unittest.TestCase):
    def setUp(self):
        self.reloj = RelojFijo()
        self.canal, _, _ = crear_canal(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), reloj=self.reloj
        )

    def resumen(self):
        return vista.resumen_bandeja(self.canal.casos_de_organizacion(MUNI), self.reloj())

    def test_los_vencidos_no_se_cuentan_como_por_vencer(self):
        self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        r = self.resumen()
        self.assertEqual((r.plazos, r.plazos_vencidos, r.plazos_cercanos), (1, 0, 1))
        self.reloj.avanzar(hours=4)  # la alerta temprana a la ANCI es de 3 horas
        r = self.resumen()
        self.assertEqual((r.plazos, r.plazos_vencidos, r.plazos_cercanos), (1, 1, 0))

    def test_por_validar_suma_los_que_la_ia_no_pudo_leer(self):
        self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        r = self.resumen()
        self.assertEqual(r.para_validar, r.por_validar + r.revision)

    def test_validados_hoy(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.validar(MUNI, caso.id, por="delegado-muni")
        r = self.resumen()
        self.assertEqual((r.validados, r.validados_hoy), (1, 1))
        self.reloj.avanzar(days=1)
        self.assertEqual(self.resumen().validados_hoy, 0)


class TestBandeja(unittest.TestCase):
    def setUp(self):
        self.reloj = RelojFijo()
        self.app, self.canal, _ = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), reloj=self.reloj
        )
        self.caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.nav = Navegador(self.app)
        entrar(self.nav)

    def test_tarjetas_con_nombres_exactos(self):
        html = self.nav.pedir("GET", "/panel/").html
        for texto in ("Casos con fecha límite legal", "Por validar", "Validados"):
            self.assertIn(texto, html)
        for viejo in ("Plazos legales corriendo", "Esperan tu validación", "Cadena de evidencia"):
            self.assertNotIn(viejo, html)
        self.assertIn("Los plazos y deberes los decide el motor", html)

    def test_un_solo_acceso_a_la_evidencia_con_su_estado(self):
        html = self.nav.pedir("GET", "/panel/").html
        self.assertEqual(html.count('href="/panel/evidencia"'), 2)  # menú lateral y botón
        self.assertRegex(html, r"Ver registro</span><small>Íntegra</small>")

    def test_el_tema_vive_en_el_menu_y_no_junto_a_botones_importantes(self):
        for ruta in ("/panel/", f"/panel/caso/{self.caso.id}", "/panel/evidencia"):
            html = self.nav.pedir("GET", ruta).html
            self.assertEqual(html.count("data-cambiar-tema"), 1, ruta)
            menu = html[
                html.index('<nav class="menu"') : html.index(
                    "</nav>", html.index('<nav class="menu"')
                )
            ]
            self.assertIn("data-cambiar-tema", menu, ruta)

    def test_filtro_solo_por_urgencia_con_su_nombre(self):
        html = self.nav.pedir("GET", "/panel/").html
        filtros = html[
            html.index('<nav class="filtros"') : html.index(
                "</nav>", html.index('<nav class="filtros"')
            )
        ]
        self.assertIn("Urgencia según plazo", filtros)
        self.assertNotIn("Validados", filtros)  # tiene su propia entrada en el menú
        self.assertIn("Todas", filtros)

    def test_vencido_ofrece_el_paso_siguiente_y_no_esconde_el_deber(self):
        self.reloj.avanzar(hours=4)
        html = self.nav.pedir("GET", "/panel/bandeja/contenido").html
        self.assertIn("1 vencido", html)
        self.assertIn("pero el deber sigue", html)
        self.assertIn(f"/panel/caso/{self.caso.id}/borrador/anci", html)
        self.assertIn("Abrir borrador para la ANCI", html)

    def test_sin_vencer_no_hay_paso_siguiente(self):
        html = self.nav.pedir("GET", "/panel/bandeja/contenido").html
        self.assertNotIn("pero el deber sigue", html)
        self.assertIn("1 vence en menos de 3 horas", html)


class TestCanal(unittest.TestCase):
    def setUp(self):
        self.app, self.canal, _ = crear_panel_de_prueba(ClienteFalso())
        self.nav = Navegador(self.app)

    def formulario(self) -> str:
        enlace = self.canal.enlace(MUNI, f"https://{HOST}")
        return self.nav.pedir("GET", enlace[len(f"https://{HOST}") :]).html

    def test_cada_opcion_dice_para_quien_es_con_un_ejemplo(self):
        html = self.formulario()
        self.assertEqual(html.count('class="opcion tipo"'), 3)
        self.assertEqual(html.count("Ejemplo:"), 3)
        self.assertEqual(html.count('aria-hidden="true"'), 3)

    def test_promete_solo_lo_que_hace_con_el_plazo_de_las_reglas(self):
        html = self.formulario()
        p = cargar_reglas()["reglas"]["respuesta_solicitud"]["plazo"]
        self.assertIn(f"dentro de {p['valor']} días corridos", html)
        self.assertIn(f"hasta por {p['prorroga_dias_corridos']} días más", html)
        self.assertIn("código de seguimiento", html)
        self.assertNotRegex(html, re.compile(r"le (avisaremos|escribiremos) por correo", re.I))

    def test_el_seguimiento_de_un_incidente_no_promete_revisarlo_hoy(self):
        caso = self.canal.recibir_incidente(MUNI, "Se perdió un pendrive con una planilla.")
        html = self.nav.pedir("GET", f"/seguimiento/{caso.id}").html
        self.assertNotIn("revisará hoy", html)
        self.assertIn("ya llegó a la persona encargada de protección de datos", html)


if __name__ == "__main__":
    unittest.main()
