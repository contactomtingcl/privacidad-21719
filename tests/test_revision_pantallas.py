"""Hallazgos de la revisión de punta a punta del 17 de octubre (computador y celular)."""

import unittest
from pathlib import Path

from .canal_apoyo import SOLICITUD_CLARA, ClienteFalso
from .panel_apoyo import Navegador, crear_panel_de_prueba

RAIZ = Path(__file__).resolve().parents[1]
CORREO = "persona.ficticia@example.com"
ORGS = ("comercial-los-robles", "municipalidad-piloto", "clinica-del-valle")


class TestBandeja(unittest.TestCase):
    def test_bandeja_vacia_en_la_demo_dice_como_probar(self):
        app, *_ = crear_panel_de_prueba(None, demo=True)
        html = Navegador(app).pedir("GET", "/panel/").html
        self.assertIn("Para probar, envía un reporte desde", html)
        self.assertIn('href="/panel/proveedores"', html)

    def test_cada_dato_de_la_fila_lleva_su_etiqueta_para_el_celular(self):
        app, canal, _ = crear_panel_de_prueba(
            ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA), demo=True
        )
        for org in ORGS:
            canal.recibir_solicitud(
                org,
                "Quiero saber qué datos tienen de mí.",
                nombre="Persona Ficticia",
                contacto=CORREO,
            )
        html = Navegador(app).pedir("GET", "/panel/").html
        for etiqueta in ("Se envió a", "Próximo plazo", "Estado"):
            self.assertIn(f'data-etiqueta="{etiqueta}"', html)
        self.assertNotIn("Para probar, envía un reporte desde", html)

    def test_en_el_celular_la_fila_es_una_tarjeta(self):
        css = (RAIZ / "src/privacidad/panel/estaticos/panel.css").read_text("utf-8")
        self.assertIn(".tabla .ancho{min-width:0}", css)
        self.assertIn("content:attr(data-etiqueta)", css)


class TestCanal(unittest.TestCase):
    def test_las_listas_del_formulario_tienen_el_estilo_de_los_demas_campos(self):
        base = (RAIZ / "src/privacidad/canal/plantillas/base.html").read_text("utf-8")
        self.assertIn("input[type=text],input[type=email],textarea,select{width:100%", base)


if __name__ == "__main__":
    unittest.main()
