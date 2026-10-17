"""«Ya lo envié» (G1): validar no es enviar. El caso sigue abierto hasta que el delegado deja
constancia de que envió (o hizo) todo lo que corresponde."""

import re
import unittest
from datetime import timedelta

from privacidad.canal.delegado import (
    AccionInvalida,
    caso_abierto,
    entregas_del_caso,
    pendientes_de_envio,
)
from privacidad.panel import vista

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    HECHOS_INCIDENTE,
    SOLICITUD_CLARA,
    ClienteFalso,
    crear_canal,
)
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"
ROBLES = "comercial-los-robles"
POR = "delegado-muni"
DUDOSO = HECHOS_INCIDENTE | {"categorias_especiales": [], "ciberincidente": "dudoso"}


class TestEntregas(unittest.TestCase):
    def test_ciberataque_en_servicio_esencial(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE))
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        ids = [d.id for d in entregas_del_caso(caso)]
        self.assertEqual(
            ids,
            [
                "aviso_agencia",
                "aviso_titulares",
                "anci_alerta_temprana",
                "anci_actualizacion",
                "anci_informe_final",
            ],
        )

    def test_una_duda_no_entra_hasta_decidirla(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=DUDOSO))
        caso = canal.recibir_incidente(MUNI, "Se vio una planilla de otra área.")
        self.assertNotIn("anci_alerta_temprana", [d.id for d in entregas_del_caso(caso)])
        caso = canal.resolver_deber(
            MUNI, caso.id, "reporte_anci", "si", motivo="criterio_delegado", por=POR
        )
        self.assertIn("anci_alerta_temprana", [d.id for d in entregas_del_caso(caso)])

    def test_solicitud(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(
            ROBLES,
            "Quiero saber qué datos tienen.",
            nombre="Persona Uno",
            contacto="uno@example.com",
        )
        self.assertEqual([d.id for d in entregas_del_caso(caso)], ["respuesta_solicitud"])


class TestRegistrarEnvio(unittest.TestCase):
    def setUp(self):
        self.canal, self.reloj, _ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE))
        self.caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")

    def enviar(self, deber, **extra):
        return self.canal.registrar_envio(
            MUNI, self.caso.id, deber, canal=extra.pop("canal", "portal_oficial"), por=POR, **extra
        )

    def test_validar_no_cierra_el_caso(self):
        caso = self.canal.validar(MUNI, self.caso.id, por=POR)
        self.assertTrue(caso_abierto(caso))
        self.assertEqual(vista.estado_de(caso), ("Falta enviar", "enviar"))

    def test_se_cierra_cuando_todo_quedo_enviado(self):
        self.canal.validar(MUNI, self.caso.id, por=POR)
        for d in entregas_del_caso(self.caso):
            self.reloj.avanzar(minutes=5)
            caso = self.enviar(d.id)
        self.assertFalse(caso_abierto(caso))
        self.assertEqual(vista.estado_de(caso), ("Validado", "validado"))
        self.assertEqual(pendientes_de_envio(caso), [])

    def test_queda_en_la_evidencia_sin_datos_personales(self):
        self.reloj.avanzar(minutes=30)
        enviado = self.reloj() - timedelta(minutes=10)
        caso = self.enviar("anci_alerta_temprana", canal="correo", momento=enviado)
        ultima = self.canal._repo.evidencia(caso.id)[-2]  # la última es el nuevo enrutado
        self.assertEqual(ultima.tipo, "envio_registrado")
        self.assertEqual(ultima.detalle["deber"], "anci_alerta_temprana")
        self.assertEqual(ultima.detalle["canal"], "correo")
        self.assertEqual(ultima.detalle["enviado"], enviado.isoformat())
        self.assertTrue(self.canal._repo.verificar_evidencia(id_organizacion=MUNI).integra)

    def test_la_urgencia_deja_de_contar_lo_enviado(self):
        self.assertIn(self.caso.asignacion.proximo_plazo, ("reporte_anci", "anci_alerta_temprana"))
        caso = self.enviar("anci_alerta_temprana")
        self.assertEqual(caso.asignacion.proximo_plazo, "anci_actualizacion")

    def test_reglas(self):
        with self.assertRaises(AccionInvalida):
            self.enviar("respuesta_solicitud")  # no corresponde a este caso
        with self.assertRaises(AccionInvalida):
            self.enviar("aviso_agencia", momento=self.reloj() + timedelta(hours=1))
        with self.assertRaises(AccionInvalida):
            self.enviar("aviso_agencia", momento=self.caso.ingreso - timedelta(hours=1))
        self.enviar("aviso_agencia")
        with self.assertRaises(AccionInvalida):
            self.enviar("aviso_agencia")

    def test_relojes_muestran_lo_enviado_al_final(self):
        caso = self.enviar("anci_alerta_temprana")
        caso = self.enviar("aviso_agencia")
        relojes = vista.relojes(caso, self.reloj())
        self.assertEqual(relojes[0].titulo, "Actualización a la ANCI")
        self.assertEqual(relojes[-1].tono, "hecho")
        self.assertIn("Enviado el", relojes[-1].detalle)

    def test_recorrido_y_que_te_toca(self):
        caso = self.canal.validar(MUNI, self.caso.id, por=POR)
        self.assertEqual(vista.pasos(caso)[-1].texto, "0 de 5 enviados")
        self.assertIn("Falta enviar: aviso a la agencia", vista.que_te_toca(caso))


class TestPorLaWeb(unittest.TestCase):
    def setUp(self):
        self.app, self.canal, self.reloj = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE)
        )
        self.caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.nav = Navegador(self.app)
        entrar(self.nav)

    def test_formulario_y_registro(self):
        html = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}").html
        self.assertIn("Lo que tienes que enviar", html)
        self.assertIn(">Ya lo envié</summary>", html)
        self.assertIn('<option value="" disabled selected>Elige…</option>', html)
        csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        r = self.nav.pedir(
            "POST",
            f"/panel/caso/{self.caso.id}/enviado",
            {"csrf": csrf, "deber": "aviso_agencia", "canal": "portal_oficial", "momento": ""},
        )
        self.assertEqual(r.status, 303)
        html = self.nav.pedir("GET", r.cabeceras["location"]).html
        self.assertIn("Quedó registrado el envío", html)
        self.assertIn("registrado por delegado-muni", html)

    def test_sin_canal_no_se_registra(self):
        csrf = self.nav.pedir("GET", f"/panel/caso/{self.caso.id}").csrf()
        r = self.nav.pedir(
            "POST",
            f"/panel/caso/{self.caso.id}/enviado",
            {"csrf": csrf, "deber": "aviso_agencia", "canal": "fax", "momento": ""},
        )
        self.assertEqual(r.status, 400)
        self.assertIn("Elige por dónde lo enviaste", r.html)

    def test_validado_con_algo_por_enviar_sigue_en_la_bandeja(self):
        self.canal.validar(MUNI, self.caso.id, por=POR)
        bandeja = self.nav.pedir("GET", "/panel/").html
        self.assertIn(self.caso.id, bandeja)
        self.assertIn("Falta enviar", bandeja)
        self.assertIn("con algo por enviar", bandeja)


if __name__ == "__main__":
    unittest.main()


class TestRespuestaALaPersona(unittest.TestCase):
    """I8: la ficha de una solicitud dice a quién y hasta cuándo responder; el sistema no envía."""

    def test_guia_con_contacto_y_fecha(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(
            MUNI, "Quiero saber qué datos tienen.", nombre="Persona Uno", contacto="uno@example.com"
        )
        nav = Navegador(app)
        entrar(nav)
        html = nav.pedir("GET", f"/panel/caso/{caso.id}").html
        self.assertIn("Respuesta a la persona", html)
        self.assertIn("Respóndele tú por escrito a uno@example.com antes del", html)
        self.assertIn("El sistema no envía la respuesta.", html)
