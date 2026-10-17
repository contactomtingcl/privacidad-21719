"""Avisos a los destinos (G5) y «Derivar a…» (G6).

Lo esencial: cada destino recibe un aviso una sola vez, el aviso nunca lleva el mensaje ni datos
personales (tampoco la identidad en un reservado), un fallo de correo no detiene el caso y todo
queda en el registro.
"""

import smtplib
import unittest
from unittest import mock

from privacidad.canal.avisos import (
    AvisoConDatosPersonales,
    BandejaSalida,
    CorreoSMTP,
    mensajero_desde_entorno,
    revisar_aviso,
)
from privacidad.canal.delegado import AccionInvalida
from privacidad.canal.repositorio import RepositorioCasos
from privacidad.panel import vista

from .canal_apoyo import HECHOS_CIBERATAQUE, HECHOS_INCIDENTE, ClienteFalso, crear_canal
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"
POR = "delegado-muni"


def canal_con_bandeja(hechos=HECHOS_INCIDENTE):
    canal, reloj, _ = crear_canal(ClienteFalso(registrar_hechos=hechos))
    bandeja = BandejaSalida()
    canal._mensajero = bandeja
    canal._url_panel = "https://canal.ejemplo.cl"
    return canal, bandeja, reloj


class TestAvisos(unittest.TestCase):
    def test_cada_destino_recibe_un_aviso_sin_el_mensaje(self):
        canal, bandeja, _ = canal_con_bandeja()
        caso = canal.recibir_incidente(MUNI, "Se envió la ficha social de un vecino por error.")
        destinos = {d.id for d in caso.asignacion.destinos}
        self.assertEqual({a.destino for a in bandeja.enviados}, destinos)
        self.assertIn("social", destinos)
        for aviso in bandeja.enviados:
            self.assertNotIn("vecino", aviso.cuerpo)
            self.assertIn(caso.id, aviso.cuerpo)
        delegado = next(a for a in bandeja.enviados if a.destino == "delegado")
        self.assertIn(f"https://canal.ejemplo.cl/panel/caso/{caso.id}", delegado.cuerpo)
        area = next(a for a in bandeja.enviados if a.destino == "social")
        self.assertNotIn("/panel/", area.cuerpo)
        self.assertIn("No reenvíes este correo", area.cuerpo)
        self.assertTrue(all(a.estado == "simulado" for a in caso.avisos))

    def test_no_se_repite_al_volver_a_enrutar(self):
        canal, bandeja, _ = canal_con_bandeja(HECHOS_CIBERATAQUE)
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al servidor.")
        antes = len(bandeja.enviados)
        canal.registrar_envio(MUNI, caso.id, "aviso_agencia", canal="portal_oficial", por=POR)
        self.assertEqual(len(bandeja.enviados), antes)

    def test_reservado_solo_al_delegado(self):
        canal, bandeja, _ = canal_con_bandeja()
        caso = canal.recibir_incidente(
            MUNI, "Se envió la ficha social de un vecino.", reservado=True, nombre="Persona Uno"
        )
        self.assertEqual([a.destino for a in bandeja.enviados], ["delegado"])
        self.assertNotIn("Persona Uno", bandeja.enviados[0].cuerpo)
        self.assertIn("(reservado)", bandeja.enviados[0].cuerpo)
        self.assertTrue(caso.asignacion.sugeridas)

    def test_un_fallo_no_detiene_el_caso_y_queda_anotado(self):
        canal, _, _ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        roto = mock.Mock(simulado=False)
        roto.enviar.side_effect = smtplib.SMTPException("sin conexión")
        canal._mensajero = roto
        caso = canal.recibir_incidente(MUNI, "Se envió la ficha social de un vecino.")
        self.assertTrue(all(a.estado == "fallido" for a in caso.avisos))
        self.assertIn("aviso", [e.tipo for e in caso.eventos])
        self.assertTrue(canal._repo.verificar_evidencia(id_organizacion=MUNI).integra)

    def test_el_aviso_se_bloquea_si_trae_un_dato_personal(self):
        with self.assertRaises(AvisoConDatosPersonales):
            revisar_aviso("Por qué te llega: escribió persona@example.com")
        revisar_aviso("Caso abc. Plazo más cercano: vence el 17 de octubre a las 03:13.")

    def test_sin_servidor_de_correo_la_bandeja_es_simulada(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertTrue(mensajero_desde_entorno().simulado)
        with mock.patch.dict("os.environ", {"PRIVACIDAD_SMTP_HOST": "smtp.example"}, clear=True):
            m = mensajero_desde_entorno()
            self.assertIsInstance(m, CorreoSMTP)
            self.assertFalse(m.simulado)

    def test_correo_smtp_con_la_biblioteca_estandar(self):
        correo = CorreoSMTP(host="smtp.example", usuario="u", contrasena="c")
        from privacidad.canal.avisos import Aviso

        with mock.patch("smtplib.SMTP") as smtp:
            correo.enviar(Aviso("area@x.example", "area", "Asunto", "Cuerpo"))
        servidor = smtp.return_value.__enter__.return_value
        servidor.starttls.assert_called_once()
        servidor.login.assert_called_once_with("u", "c")
        enviado = servidor.send_message.call_args[0][0]
        self.assertEqual(enviado["To"], "area@x.example")


class TestDerivar(unittest.TestCase):
    def setUp(self):
        self.canal, self.bandeja, _ = canal_con_bandeja()
        self.caso = self.canal.recibir_incidente(MUNI, "Algo raro pasó con unos papeles.")

    def test_deriva_avisa_y_queda_en_el_registro(self):
        caso = self.canal.derivar(MUNI, self.caso.id, "personal", motivo="debe_actuar", por=POR)
        self.assertIn("personal", [d.id for d in caso.asignacion.destinos])
        aviso = self.bandeja.enviados[-1]
        self.assertEqual(aviso.destino, "personal")
        self.assertIn("te derivaron un caso", aviso.cuerpo)
        self.assertIn("derivado", [e.tipo for e in caso.eventos])
        self.assertTrue(self.canal._repo.verificar_evidencia(id_organizacion=MUNI).integra)

    def test_la_derivacion_sobrevive_al_reenrutar(self):
        self.canal.derivar(MUNI, self.caso.id, "personal", motivo="consulta", por=POR)
        caso = self.canal.corregir_hechos(
            MUNI,
            self.caso.id,
            self.caso.hechos_vigentes.model_copy(update={"vulneracion": "perdida"}),
            motivo="informacion_nueva",
            por=POR,
        )
        self.assertIn("personal", [d.id for d in caso.asignacion.destinos])

    def test_reservado_se_puede_derivar_sin_identidad(self):
        caso = self.canal.recibir_incidente(
            MUNI, "Se envió la ficha social de un vecino.", reservado=True, nombre="Persona Uno"
        )
        caso = self.canal.derivar(MUNI, caso.id, "social", motivo="datos_del_area", por=POR)
        aviso = self.bandeja.enviados[-1]
        self.assertEqual(aviso.destino, "social")
        self.assertNotIn("Persona Uno", aviso.cuerpo)
        self.assertNotIn("social", [s.id for s in caso.asignacion.sugeridas])

    def test_reglas(self):
        with self.assertRaises(AccionInvalida):
            self.canal.derivar(MUNI, self.caso.id, "inventada", motivo="otro", por=POR)
        self.canal.derivar(MUNI, self.caso.id, "personal", motivo="otro", por=POR)
        with self.assertRaises(AccionInvalida):
            self.canal.derivar(MUNI, self.caso.id, "personal", motivo="otro", por=POR)


class TestPanel(unittest.TestCase):
    def test_estado_del_aviso_vista_previa_y_derivar(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        canal._mensajero = BandejaSalida()
        caso = canal.recibir_incidente(MUNI, "Algo raro pasó con unos papeles.")
        nav = Navegador(app)
        entrar(nav)
        html = nav.pedir("GET", f"/panel/caso/{caso.id}").html
        self.assertIn("bandeja de salida de la demo (no sale correo)", html)
        self.assertIn("Ver el aviso", html)
        self.assertIn("Derivar a…", html)
        csrf = nav.pedir("GET", f"/panel/caso/{caso.id}").csrf()
        r = nav.pedir(
            "POST",
            f"/panel/caso/{caso.id}/derivar",
            {"csrf": csrf, "area": "personal", "motivo": "debe_actuar"},
        )
        self.assertEqual(r.status, 303)
        html = nav.pedir("GET", r.cabeceras["location"]).html
        self.assertIn("Derivaste el caso", html)
        self.assertIn("Lo derivó el delegado: esa área tiene que hacer algo.", html)

    def test_linea_de_tiempo_nombra_el_destino(self):
        canal, _, _ = canal_con_bandeja()
        caso = canal.recibir_incidente(MUNI, "Se envió la ficha social de un vecino.")
        textos = [h.texto for h in vista.linea_de_tiempo(caso, [])]
        self.assertTrue(
            any(t.startswith("Dirección de Desarrollo Comunitario: aviso") for t in textos)
        )


class TestRepositorio(unittest.TestCase):
    def test_avisos_y_derivaciones_se_guardan(self):
        canal, _, _ = canal_con_bandeja()
        canal._repo = RepositorioCasos()
        caso = canal.recibir_incidente(MUNI, "Algo raro pasó con unos papeles.")
        canal.derivar(MUNI, caso.id, "personal", motivo="otro", por=POR)
        guardado = canal._repo.obtener(caso.id)
        self.assertEqual(guardado.derivaciones[0].area, "personal")
        self.assertTrue(guardado.avisos)


if __name__ == "__main__":
    unittest.main()


class TestTelegram(unittest.TestCase):
    def test_envia_con_urllib_solo_si_hay_chat(self):
        from privacidad.canal.avisos import Aviso, Telegram

        t = Telegram(token="token-de-prueba")
        with mock.patch("urllib.request.urlopen") as abrir:
            t.enviar(Aviso("a@x.example", "area", "Asunto", "Cuerpo"))
            abrir.assert_not_called()
            abrir.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'
            t.enviar(Aviso("a@x.example", "area", "Asunto", "Cuerpo", telegram="123"))
            url = abrir.call_args[0][0]
            self.assertIn("/bottoken-de-prueba/sendMessage", url)
            self.assertIn(b"chat_id=123", abrir.call_args[1]["data"])

    def test_rechazo_de_telegram_es_un_fallo(self):
        from privacidad.canal.avisos import Aviso, Telegram

        with mock.patch("urllib.request.urlopen") as abrir:
            abrir.return_value.__enter__.return_value.read.return_value = b'{"ok": false}'
            with self.assertRaises(OSError):
                Telegram(token="t").enviar(Aviso("a@x.example", "a", "A", "C", telegram="1"))

    def test_con_token_se_suma_a_la_bandeja(self):
        from privacidad.canal.avisos import Varios

        with mock.patch.dict("os.environ", {"PRIVACIDAD_TELEGRAM_TOKEN": "t"}, clear=True):
            m = mensajero_desde_entorno()
        self.assertIsInstance(m, Varios)
        self.assertFalse(m.simulado)


class TestEstadoReal(unittest.TestCase):
    def test_solo_telegram_sin_chat_no_cuenta_como_enviado(self):
        from privacidad.canal.avisos import Aviso, Telegram, Varios, salio_de_verdad

        m = Varios([BandejaSalida(), Telegram(token="t")])
        self.assertFalse(salio_de_verdad(m, Aviso("a@x.example", "a", "A", "C")))
        self.assertTrue(salio_de_verdad(m, Aviso("a@x.example", "a", "A", "C", telegram="1")))
