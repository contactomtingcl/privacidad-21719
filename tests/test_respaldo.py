import unittest

from privacidad.canal import RepositorioCasos
from privacidad.evaluacion.ejecutar import metricas_respaldo
from privacidad.interpretacion import extraer_hechos, interpretar_solicitud
from privacidad.interpretacion.incidentes import afirmados_incidente
from privacidad.interpretacion.respaldo import Respaldo, esta_en, leer_respaldos, normalizar
from privacidad.motor import HechosIncidente
from privacidad.panel.demo import sembrar

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    SOLICITUD_CLARA,
    ClienteFalso,
    crear_canal,
)
from .panel_apoyo import Navegador, crear_panel_de_prueba

MUNI = "municipalidad-piloto"
CORREO = "soporte@municipalidad-piloto.example"
TEXTO = f"Alguien entró con la cuenta {CORREO} desde fuera del municipio y vio postulaciones."
INVENTADA = "cifraron todos los servidores con ransomware"


class TestComparacion(unittest.TestCase):
    def test_ignora_mayusculas_tildes_y_puntuacion(self):
        self.assertEqual(normalizar("¡Se PERDIÓ el pendrive!"), "se perdio el pendrive")
        self.assertTrue(esta_en("se perdio el PENDRIVE", "Ayer se perdió el pendrive, creo."))

    def test_exige_palabras_completas(self):
        self.assertFalse(esta_en("rut", "la ruta del camión"))
        self.assertTrue(esta_en("el [RUT_1] del", "anotó el [RUT_1] del vecino"))

    def test_frases_muy_cortas_no_cuentan(self):
        self.assertFalse(esta_en("a", "a b c"))

    def test_solo_campos_conocidos_y_texto(self):
        r = leer_respaldos(
            {"vulneracion": "entró con la cuenta", "otro": "x y z", "riesgo_mitigado": 3},
            {"vulneracion", "riesgo_mitigado"},
            "Alguien entró con la cuenta.",
        )
        self.assertEqual(list(r), ["vulneracion"])
        self.assertTrue(r["vulneracion"].verificada)


def cliente_con(respaldos: dict) -> ClienteFalso:
    return ClienteFalso(
        registrar_hechos=HECHOS_CIBERATAQUE | {"titulares_aprox": 40, "respaldos": respaldos}
    )


class TestExtraccion(unittest.TestCase):
    def test_frase_del_texto_enmascarado_se_verifica_y_la_inventada_no(self):
        cliente = cliente_con(
            {
                "vulneracion": "entró con la cuenta [CORREO_1] desde fuera del municipio",
                "ciberincidente": INVENTADA,
            }
        )
        ext = extraer_hechos(TEXTO, cliente, "modelo")
        self.assertTrue(ext.respaldos["vulneracion"].verificada)
        self.assertFalse(ext.respaldos["ciberincidente"].verificada)
        # Las instrucciones piden la frase; la IA sigue viendo solo el texto enmascarado.
        self.assertIn("respaldos", cliente.lo_que_vio_la_ia())
        self.assertNotIn(CORREO, cliente.lo_que_vio_la_ia())

    def test_una_frase_con_el_dato_real_no_se_verifica(self):
        # La IA nunca vio el correo: si lo "cita", no viene del texto que recibió.
        ext = extraer_hechos(TEXTO, cliente_con({"vulneracion": f"la cuenta {CORREO}"}), "m")
        self.assertFalse(ext.respaldos["vulneracion"].verificada)

    def test_solicitud_guarda_frases_solo_de_los_derechos_leidos(self):
        cliente = ClienteFalso(
            interpretar_solicitud=SOLICITUD_CLARA
            | {"respaldos": {"acceso": "qué datos tienen de mí", "supresion": "bórrenlo todo"}}
        )
        r = interpretar_solicitud("Quiero saber qué datos tienen de mí.", cliente, "m")
        self.assertEqual(list(r.respaldos), ["acceso"])
        self.assertTrue(r.respaldos["acceso"].verificada)

    def test_sin_respaldos_sigue_funcionando(self):
        ext = extraer_hechos(TEXTO, ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), "m")
        self.assertIsNotNone(ext.hechos)
        self.assertEqual(ext.respaldos, {})


class TestCasoYEvidencia(unittest.TestCase):
    def test_el_caso_guarda_las_frases_y_la_evidencia_solo_las_cifras(self):
        canal, _, _ = crear_canal(
            cliente_con({"vulneracion": "entró con la cuenta", "ciberincidente": INVENTADA})
        )
        caso = canal.recibir_incidente(MUNI, TEXTO)
        self.assertEqual(len(caso.respaldos_ia), 2)
        evento = next(e for e in caso.eventos if e.tipo == "interpretado")
        self.assertEqual(evento.detalle["respaldos"], 2)
        self.assertEqual(evento.detalle["respaldos_verificados"], 1)
        cadena = str([a.detalle for a in canal._repo.evidencia(caso.id)])
        self.assertNotIn("entró con la cuenta", cadena)
        self.assertNotIn("ransomware", cadena)


class TestPanel(unittest.TestCase):
    def test_la_ficha_muestra_la_frase_y_avisa_lo_no_verificado(self):
        app, canal, _ = crear_panel_de_prueba(
            cliente_con({"vulneracion": "entró con la cuenta", "ciberincidente": INVENTADA}),
            demo=True,
        )
        caso = canal.recibir_incidente(MUNI, TEXTO)
        nav = Navegador(app)
        inicio = nav.pedir("GET", "/panel/")
        nav.pedir("POST", "/panel/demo/organizacion", {"csrf": inicio.csrf(), "org": MUNI})
        ficha = nav.pedir("GET", f"/panel/caso/{caso.id}")
        self.assertEqual(ficha.status, 200)
        self.assertIn("Se basó en: «entró con la cuenta»", ficha.html)
        self.assertIn("La IA citó algo que no está en el mensaje", ficha.html)
        # titulares_aprox = 40 sin frase: el panel pide revisarlo.
        self.assertIn("La IA no citó una frase del mensaje para este dato", ficha.html)


class TestCasosAntiguos(unittest.TestCase):
    def test_un_caso_leido_antes_de_las_frases_no_se_marca(self):
        from privacidad.panel.vista import vista_hechos

        canal, _, _ = crear_canal(cliente_con({"vulneracion": "entró con la cuenta"}))
        caso = canal.recibir_incidente(MUNI, TEXTO)
        self.assertTrue(any(h.sin_respaldo for h in vista_hechos(caso)))
        for e in caso.eventos:  # así quedaba un caso del 11 de octubre
            e.detalle.pop("respaldos", None)
            e.detalle.pop("respaldos_verificados", None)
        caso.respaldos_ia = {}
        self.assertFalse(any(h.sin_respaldo for h in vista_hechos(caso)))

    def test_la_demo_cambia_de_carpeta_si_cambian_sus_casos(self):
        import tempfile
        from pathlib import Path

        from privacidad.panel.demo import version_demo

        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "casos.yaml"
            ruta.write_text("casos: []", encoding="utf-8")
            antes = version_demo(ruta)
            ruta.write_text("casos: [] # cambio", encoding="utf-8")
            self.assertNotEqual(antes, version_demo(ruta))


class TestDemoYMedicion(unittest.TestCase):
    def test_todas_las_frases_grabadas_de_la_demo_estan_en_su_mensaje(self):
        canal, _, _ = crear_canal(ClienteFalso(), repositorio=RepositorioCasos())
        sembrar(canal)
        respaldos = [r for c in canal._repo.listar() for r in c.respaldos_ia.values()]
        self.assertGreater(len(respaldos), 10)
        self.assertTrue(all(r.verificada for r in respaldos))

    def test_afirmados_no_incluye_los_no_por_omision(self):
        h = HechosIncidente(
            datos_personales=True, vulneracion="perdida", ciberincidente="no", titulares_aprox=3
        )
        self.assertEqual(
            afirmados_incidente(h), {"datos_personales", "vulneracion", "titulares_aprox"}
        )

    def test_metricas_de_respaldo(self):
        si, no = Respaldo(frase="a b c", verificada=True), Respaldo(frase="x", verificada=False)
        m = metricas_respaldo(
            [({"vulneracion", "datos_personales"}, {"vulneracion": si, "ciberincidente": no})]
        )
        self.assertEqual(m["frases_verificadas"], "1/2")
        self.assertEqual(m["afirmados_con_frase_verificada"], "1/2")
        self.assertEqual(m["afirmados_con_frase_verificada_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
