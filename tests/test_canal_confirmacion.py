import unittest
from datetime import datetime, timedelta

from privacidad.canal import confirmacion as conf
from privacidad.canal.modelos import ZONA_CHILE, Confirmacion
from privacidad.motor import HechosSolicitud, cargar_reglas

AHORA = datetime(2026, 12, 2, 10, 0, tzinfo=ZONA_CHILE)


def hechos(**kw) -> HechosSolicitud:
    base = {"es_solicitud": True, "derechos": ["oposicion"], "requiere_confirmacion": True}
    return HechosSolicitud(**(base | kw))


class TestReglaDeConfirmacion(unittest.TestCase):
    def test_la_regla_esta_en_los_datos_con_su_fuente(self):
        regla = cargar_reglas()["reglas"]["confirmacion_titular"]
        self.assertEqual(regla["fuente"]["articulo"], "11")
        self.assertEqual(conf.dias_de_espera(), regla["parametros"]["espera_dias"])
        self.assertIn("revisión legal", regla["criterio"])


class TestLecturaMasProtectora(unittest.TestCase):
    def test_oposicion_se_lee_como_supresion(self):
        self.assertEqual(conf.lectura_mas_protectora(["oposicion"]), ["supresion"])
        self.assertEqual(conf.lectura_mas_protectora(["supresion"]), ["supresion"])

    def test_si_vienen_las_dos_queda_una(self):
        self.assertEqual(conf.lectura_mas_protectora(["oposicion", "supresion"]), ["supresion"])

    def test_los_demas_derechos_quedan_como_se_propusieron(self):
        propuesta = ["rectificacion", "bloqueo"]
        self.assertEqual(conf.lectura_mas_protectora(propuesta), propuesta)
        self.assertEqual(conf.lectura_mas_protectora(["acceso"]), ["acceso"])

    def test_no_modifica_la_lista_original(self):
        propuesta = ["oposicion", "bloqueo"]
        conf.lectura_mas_protectora(propuesta)
        self.assertEqual(propuesta, ["oposicion", "bloqueo"])


class TestPreparar(unittest.TestCase):
    def test_ambigua_queda_pendiente_con_la_pregunta_de_la_ia(self):
        c = conf.preparar(hechos(pregunta_confirmacion="¿Publicidad o borrar todo?"), AHORA)
        self.assertEqual(c.estado, "pendiente")
        self.assertEqual(c.pregunta, "¿Publicidad o borrar todo?")
        self.assertEqual(c.propuesta, ["oposicion"])
        self.assertEqual(c.vigente, ["oposicion"])
        self.assertEqual(c.espera_hasta, AHORA + timedelta(days=conf.dias_de_espera()))

    def test_sin_pregunta_de_la_ia_usa_la_generica(self):
        c = conf.preparar(hechos(), AHORA)
        self.assertEqual(c.pregunta, conf.PREGUNTA_GENERICA)

    def test_clara_no_requiere_confirmacion(self):
        c = conf.preparar(hechos(requiere_confirmacion=False), AHORA)
        self.assertEqual(c.estado, "no_requerida")
        self.assertIsNone(c.espera_hasta)
        self.assertIsNone(c.pregunta)

    def test_lo_que_no_es_solicitud_no_se_confirma(self):
        with self.assertRaises(conf.RespuestaInvalida):
            conf.preparar(HechosSolicitud(es_solicitud=False), AHORA)


class TestRespuesta(unittest.TestCase):
    def setUp(self):
        self.pendiente = conf.preparar(hechos(), AHORA)
        self.despues = AHORA + timedelta(days=1)

    def test_confirmar_lo_propuesto(self):
        c = conf.aplicar_respuesta(self.pendiente, ["oposicion"], None, self.despues)
        self.assertEqual(
            (c.estado, c.vigente, c.respondida_en), ("confirmada", ["oposicion"], self.despues)
        )

    def test_corregir(self):
        c = conf.aplicar_respuesta(
            self.pendiente, ["supresion"], " Ya no soy cliente ", self.despues
        )
        self.assertEqual((c.estado, c.vigente), ("corregida", ["supresion"]))
        self.assertEqual(c.detalle, "Ya no soy cliente")
        self.assertEqual(c.propuesta, ["oposicion"])  # lo que propuso la IA queda registrado

    def test_el_orden_y_los_repetidos_no_importan(self):
        base = conf.preparar(hechos(derechos=["rectificacion", "bloqueo"]), AHORA)
        c = conf.aplicar_respuesta(
            base, ["bloqueo", "rectificacion", "bloqueo"], None, self.despues
        )
        self.assertEqual(c.estado, "confirmada")

    def test_respuestas_invalidas(self):
        for derechos in ([], ["inventado"], ["oposicion", "inventado"]):
            with self.assertRaises(conf.RespuestaInvalida, msg=str(derechos)):
                conf.aplicar_respuesta(self.pendiente, derechos, None, self.despues)
        with self.assertRaises(conf.RespuestaInvalida):
            conf.aplicar_respuesta(
                self.pendiente, ["oposicion"], "x" * (conf.LARGO_MAXIMO_DETALLE + 1), self.despues
            )

    def test_no_se_responde_dos_veces(self):
        c = conf.aplicar_respuesta(self.pendiente, ["oposicion"], None, self.despues)
        with self.assertRaises(conf.RespuestaInvalida):
            conf.aplicar_respuesta(c, ["supresion"], None, self.despues)

    def test_se_puede_corregir_lo_que_no_requeria_confirmacion(self):
        clara = conf.preparar(hechos(requiere_confirmacion=False), AHORA)
        c = conf.aplicar_respuesta(clara, ["supresion"], None, self.despues)
        self.assertEqual(c.estado, "corregida")


class TestSinRespuesta(unittest.TestCase):
    def test_vence_exactamente_al_cumplirse_la_espera(self):
        c = conf.preparar(hechos(), AHORA)
        limite = c.espera_hasta
        self.assertFalse(conf.vencida(c, limite - timedelta(seconds=1)))
        self.assertTrue(conf.vencida(c, limite))
        self.assertFalse(conf.vencida(None, limite))

    def test_aplica_la_lectura_mas_protectora(self):
        c = conf.preparar(hechos(), AHORA)
        d = conf.aplicar_por_defecto(c, c.espera_hasta)
        self.assertEqual((d.estado, d.vigente), ("por_defecto", ["supresion"]))
        self.assertEqual(d.propuesta, ["oposicion"])

    def test_solo_aplica_a_pendientes(self):
        c = conf.aplicar_respuesta(conf.preparar(hechos(), AHORA), ["oposicion"], None, AHORA)
        self.assertFalse(conf.vencida(c, AHORA + timedelta(days=30)))
        with self.assertRaises(conf.RespuestaInvalida):
            conf.aplicar_por_defecto(c, AHORA)

    def test_una_respuesta_tardia_reemplaza_la_lectura_por_defecto(self):
        c = conf.preparar(hechos(), AHORA)
        d = conf.aplicar_por_defecto(c, c.espera_hasta)
        tardia = conf.aplicar_respuesta(d, ["oposicion"], None, c.espera_hasta + timedelta(days=1))
        self.assertEqual((tardia.estado, tardia.vigente), ("confirmada", ["oposicion"]))

    def test_hechos_vigentes_para_el_motor(self):
        c = Confirmacion(
            estado="corregida", propuesta=["oposicion"], vigente=["supresion", "bloqueo"]
        )
        h = conf.hechos_vigentes(c)
        self.assertEqual((h.es_solicitud, h.derechos), (True, ["supresion", "bloqueo"]))


if __name__ == "__main__":
    unittest.main()
