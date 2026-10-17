"""Auditoría de comprensión del delegado (17 oct): G3, G4, I1-I7, I9-I13.

Solo cambian palabras y forma: se prueba que la pantalla diga lo que el sistema sabe, sin
cambiar ninguna decisión del motor.
"""

import re
import unittest

from privacidad.canal.delegado import AccionInvalida
from privacidad.motor import HechosIncidente
from privacidad.panel import vista

from .canal_apoyo import HECHOS_INCIDENTE, SOLICITUD_AMBIGUA, ClienteFalso, crear_canal
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"
DUDOSO = HECHOS_INCIDENTE | {"categorias_especiales": [], "ciberincidente": "dudoso"}


def sin_detalles(html: str) -> str:
    """Lo que se ve sin abrir ningún plegable."""
    return re.sub(r"<details.*?</details>", "", html, flags=re.S)


class Ficha(unittest.TestCase):
    def abrir(self, cliente, texto="Se vio una planilla de otra área.", solicitud=False):
        self.app, self.canal, _ = crear_panel_de_prueba(cliente)
        if solicitud:
            self.caso = self.canal.recibir_solicitud(
                MUNI, texto, nombre="Persona Ficticia Uno", contacto="uno@example.com"
            )
        else:
            self.caso = self.canal.recibir_incidente(MUNI, texto)
        self.nav = Navegador(self.app)
        entrar(self.nav)
        return self.nav.pedir("GET", f"/panel/caso/{self.caso.id}").html


class TestValidarConRazon(Ficha):
    """G4: el botón dice qué falta en vez de fallar al apretarlo."""

    def test_con_una_duda_del_motor(self):
        html = self.abrir(ClienteFalso(registrar_hechos=DUDOSO))
        self.assertRegex(html, r"<button[^>]*disabled[^>]*>Validar decisión</button>")
        self.assertIn("Primero decide 1 deber", html)
        self.assertNotIn(f"/caso/{self.caso.id}/validar", html)

    def test_sin_lectura_de_la_ia(self):
        html = self.abrir(None)
        self.assertIn("Primero completa los hechos", html)
        self.assertIn("completa los hechos y el motor decidirá", html)

    def test_solicitud_esperando_a_la_persona(self):
        html = self.abrir(
            ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA),
            "Ya no quiero sus correos de ofertas.",
            solicitud=True,
        )
        self.assertIn("Primero espera la respuesta de la persona", html)

    def test_las_razones_son_las_mismas_que_exige_validar(self):
        for cliente in (None, ClienteFalso(registrar_hechos=DUDOSO)):
            canal, *_ = crear_canal(cliente)
            caso = canal.recibir_incidente(MUNI, "Se vio una planilla de otra área.")
            self.assertIsNotNone(vista.por_que_no_validar(caso))
            with self.assertRaises(AccionInvalida):
                canal.validar(MUNI, caso.id, por="delegado-muni")

    def test_sin_nada_pendiente_se_puede_validar(self):
        html = self.abrir(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        self.assertIn(f"/caso/{self.caso.id}/validar", html)
        self.assertNotRegex(html, r"<button[^>]*disabled[^>]*>Validar decisión")


class TestPalabras(Ficha):
    def test_deberes_dicen_a_que_responden(self):  # I2, I3
        html = self.abrir(ClienteFalso(registrar_hechos=DUDOSO))
        self.assertIn(">Decide tú</span>", html)
        self.assertIn("El motor no puede decidirlo con estos hechos: decide tú.", html)
        self.assertIn(">Corresponde</span>", html)
        self.assertIn("¿Por qué?</label>", html)
        self.assertIn('<option value="" disabled selected>Elige…</option>', html)
        self.assertNotIn(">Revisar</span>", html)

    def test_recorrido_cuenta_lo_que_corresponde_y_lo_que_falta(self):  # I6
        self.abrir(ClienteFalso(registrar_hechos=DUDOSO))
        self.assertRegex(vista.conteo_deberes(self.caso), r"^\d+ corresponden?, 1 por decidir$")
        html = self.abrir(None)
        self.assertIn("Espera los hechos", html)
        self.assertNotIn("0 deberes", html)

    def test_borradores_pendientes_no_dicen_no(self):  # G3
        html = self.abrir(None)
        self.assertIn(">Pendiente</span>", html)
        self.assertIn("Completa los hechos y se arma.", html)
        self.assertNotIn(">No</span>", html)

    def test_sin_lectura_y_doble_negacion(self):  # I1, I5
        html = self.abrir(None)
        self.assertIn("¿Se puede descartar que alguien viera los datos?", html)
        self.assertNotIn("nadie los vio", html)
        bandeja = self.nav.pedir("GET", "/panel/").html
        self.assertIn("Sin lectura de la IA", bandeja)
        self.assertNotIn("Requiere revisión", bandeja)

    def test_dias_habiles_aclarados(self):  # I7
        self.assertEqual(
            vista.aclarar_habiles("2 días hábiles"),
            "2 días hábiles (no cuentan fines de semana ni feriados)",
        )
        self.assertEqual(
            vista.aclarar_habiles(vista.aclarar_habiles("2 días hábiles")).count("("), 1
        )
        self.assertIsNone(vista.aclarar_habiles(None))

    def test_la_persona_y_no_el_titular(self):  # I4
        html = self.abrir(
            ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA),
            "Ya no quiero sus correos de ofertas.",
            solicitud=True,
        )
        visible = re.sub(r"<blockquote>.*?</blockquote>", "", html, flags=re.S)
        self.assertNotRegex(visible.lower(), r"\btitular")

    def test_codigo_del_caso_con_etiqueta_y_huellas_plegadas(self):  # I9, I10, I11, I12
        html = self.abrir(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        self.assertIn(f'Código del caso: <span class="mono">{self.caso.id}</span>', html)
        self.assertIn("Registro de lo actuado", html)
        self.assertIn("Así lo leyó la IA, con los datos personales tapados.", html)
        huella = self.canal._repo.evidencia(self.caso.id)[0].huella
        corta = f"{huella[:6]}…{huella[-2:]}"
        self.assertIn(corta, html)
        self.assertNotIn(corta, sin_detalles(html))
        self.assertIn("Revisa lo que decidió el motor y valídalo.", html)


class TestRegistro(unittest.TestCase):
    def setUp(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        canal.recibir_incidente(MUNI, "Se vio una planilla de otra área.")
        self.nav = Navegador(app)
        entrar(self.nav)

    def test_nombre_y_anotaciones_sin_huellas_a_la_vista(self):  # I9, I11
        html = self.nav.pedir("GET", "/panel/evidencia").html
        self.assertIn("<h1>Registro de lo actuado</h1>", html)
        self.assertIn("Anotación 1", html)
        self.assertNotIn("n.º", html)
        visible = sin_detalles(html)
        texto = re.sub(r"<[^>]+>", " ", visible)  # sin etiquetas ni atributos (data-copiar)
        self.assertNotRegex(texto, r"\b[0-9a-f]{64}\b")
        self.assertIn("Copiar código del registro", visible)

    def test_borrador_dice_que_revisar_no_es_enviar(self):  # I13
        bandeja = self.nav.pedir("GET", "/panel/").html
        id_caso = re.search(r"/panel/caso/([\w-]+)\"", bandeja).group(1)
        html = self.nav.pedir("GET", f"/panel/caso/{id_caso}/borrador/agencia").html
        self.assertIn("Revisé este borrador (todavía no lo envío)", html)
        self.assertNotIn("Marcar como revisado", html)


if __name__ == "__main__":
    unittest.main()


class TestFormularioSinLectura(Ficha):
    """G2: si la IA no leyó, el formulario parte vacío y el motivo lo pone el sistema."""

    def test_parte_vacio_con_motivo_fijo(self):
        html = self.abrir(None)
        formulario = html[html.index("/corregir") :]
        formulario = formulario[: formulario.index("</form>")]
        self.assertEqual(formulario.count('<option value="" disabled selected>Elige…</option>'), 5)
        self.assertNotIn("selected>Se filtraron datos", formulario)
        self.assertIn("La IA no pudo leerlo", formulario)
        self.assertIn('name="motivo" value="ia_no_leyo"', formulario)
        self.assertNotIn("La IA leyó mal el mensaje", formulario)
        self.assertIn("Completa lo que sepas", formulario)
        self.assertIn("Guardar los hechos", formulario)

    def test_el_motivo_queda_como_sin_lectura_aunque_manden_otro(self):
        self.abrir(None)
        hechos = HechosIncidente(
            datos_personales=True,
            vulneracion="filtracion",
            riesgo_mitigado=False,
            ciberincidente="no",
        )
        caso = self.canal.corregir_hechos(
            MUNI, self.caso.id, hechos, motivo="error_ia", por="delegado-muni"
        )
        self.assertEqual(caso.correcciones[-1].motivo, "ia_no_leyo")
        with self.assertRaises(AccionInvalida):
            self.canal.corregir_hechos(
                MUNI,
                self.caso.id,
                hechos.model_copy(update={"vulneracion": "perdida"}),
                motivo="ia_no_leyo",
                por="delegado-muni",
            )

    def test_con_lectura_de_la_ia_el_motivo_se_elige(self):
        html = self.abrir(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        formulario = html[html.index("/corregir") :]
        self.assertIn('<select id="motivo-correccion" name="motivo" required>', formulario)
        self.assertIn("Aplicar corrección", formulario)
