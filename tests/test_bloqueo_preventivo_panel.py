"""Bloqueo preventivo en el panel del delegado: se explica como preventivo y, si la persona
aclara que no lo pide, se indica levantarlo."""

import unittest

from privacidad.panel import vista

from .canal_apoyo import SOLICITUD_AMBIGUA, ClienteFalso, crear_canal

ROBLES = "comercial-los-robles"
CORREO = "persona.ficticia@example.com"


class TestPanel(unittest.TestCase):
    def setUp(self):
        self.canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA))
        self.caso = self.canal.recibir_solicitud(
            ROBLES,
            "Ya no quiero sus correos de ofertas.",
            nombre="Persona Ficticia",
            contacto=CORREO,
        )

    def envio_bloqueo(self, caso):
        return next(e for e in vista.vista_envios(caso) if e.id == "bloqueo_temporal")

    def test_la_guia_dice_que_es_preventivo(self):
        e = self.envio_bloqueo(self.caso)
        self.assertIn("Por precaución", e.guia)
        self.assertNotIn("lo que pidió suspender", e.guia)

    def test_si_se_levanta_despues_de_aplicarlo_se_indica_volver_a_usarlos(self):
        self.canal.registrar_envio(
            ROBLES, self.caso.id, "bloqueo_temporal", canal="otro", por="delegado-demo"
        )
        caso = self.canal.responder_confirmacion(self.caso.id, derechos=["oposicion"])
        e = self.envio_bloqueo(caso)
        self.assertFalse(e.vigente)
        self.assertIn("levántalo", e.guia)
