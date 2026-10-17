import unittest
from datetime import date, datetime, timedelta
from unittest import mock

from privacidad.canal import confirmacion as conf
from privacidad.canal.modelos import ZONA_CHILE, Confirmacion
from privacidad.motor import HechosSolicitud, cargar_reglas, decidir_solicitud

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


class TestLecturaPorDefecto(unittest.TestCase):
    def test_nunca_incluye_la_supresion(self):
        for propuesta in (["supresion"], ["oposicion"], ["supresion", "oposicion", "acceso"]):
            self.assertNotIn("supresion", conf.lectura_por_defecto(propuesta), propuesta)

    def test_oposicion_queda_con_bloqueo_temporal(self):
        self.assertEqual(conf.lectura_por_defecto(["oposicion"]), ["oposicion", "bloqueo"])

    def test_si_proponian_borrar_se_aplica_oposicion_con_bloqueo(self):
        self.assertEqual(conf.lectura_por_defecto(["supresion"]), ["oposicion", "bloqueo"])

    def test_si_vienen_las_dos_queda_una_y_un_solo_bloqueo(self):
        self.assertEqual(
            conf.lectura_por_defecto(["oposicion", "supresion"]), ["oposicion", "bloqueo"]
        )
        self.assertEqual(
            conf.lectura_por_defecto(["supresion", "bloqueo"]), ["oposicion", "bloqueo"]
        )

    def test_los_demas_derechos_quedan_como_se_propusieron(self):
        for propuesta in (["rectificacion", "bloqueo"], ["acceso"], ["portabilidad"]):
            self.assertEqual(conf.lectura_por_defecto(propuesta), propuesta)

    def test_no_modifica_la_lista_original(self):
        propuesta = ["supresion", "acceso"]
        conf.lectura_por_defecto(propuesta)
        self.assertEqual(propuesta, ["supresion", "acceso"])

    def test_solo_la_supresion_es_irreversible(self):
        self.assertTrue(conf.es_irreversible("supresion"))
        for derecho in ("acceso", "rectificacion", "oposicion", "portabilidad", "bloqueo"):
            self.assertFalse(conf.es_irreversible(derecho))

    def test_el_criterio_esta_anotado_como_pendiente_de_revision_legal(self):
        regla = cargar_reglas()["reglas"]["confirmacion_titular"]
        self.assertIn("reversible", regla["criterio"])
        self.assertIn("pendientes de revisión legal", regla["criterio"])


class TestPreparar(unittest.TestCase):
    def test_ambigua_queda_pendiente_con_la_pregunta_de_la_ia(self):
        c = conf.preparar(hechos(pregunta_confirmacion="¿Publicidad o borrar todo?"), AHORA)
        self.assertEqual(c.estado, "pendiente")
        self.assertEqual(c.pregunta, "¿Publicidad o borrar todo?")
        self.assertEqual(c.propuesta, ["oposicion"])
        # Bloqueo preventivo: la lectura por defecto lo incluiría, así que corre desde ya.
        self.assertEqual(c.vigente, ["oposicion", "bloqueo"])
        self.assertTrue(c.bloqueo_preventivo)
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

    def test_aplica_la_lectura_reversible(self):
        c = conf.preparar(hechos(), AHORA)
        d = conf.aplicar_por_defecto(c, c.espera_hasta)
        self.assertEqual((d.estado, d.vigente), ("por_defecto", ["oposicion", "bloqueo"]))
        self.assertEqual(d.propuesta, ["oposicion"])

    def test_aunque_la_ia_proponga_borrar_no_se_borra_sin_confirmacion(self):
        c = conf.preparar(hechos(derechos=["supresion"]), AHORA)
        d = conf.aplicar_por_defecto(c, c.espera_hasta)
        self.assertEqual(d.vigente, ["oposicion", "bloqueo"])
        self.assertEqual(d.propuesta, ["supresion"])

    def test_el_motor_se_niega_a_tramitar_una_supresion_por_defecto(self):
        c = Confirmacion(estado="por_defecto", propuesta=["supresion"], vigente=["supresion"])
        with self.assertRaises(conf.RespuestaInvalida):
            conf.hechos_vigentes(c)

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

    def test_pedir_la_supresion_despues_es_la_confirmacion_expresa(self):
        c = conf.preparar(hechos(), AHORA)
        d = conf.aplicar_por_defecto(c, c.espera_hasta)
        pedida = conf.aplicar_respuesta(d, ["supresion"], None, c.espera_hasta)
        self.assertEqual((pedida.estado, pedida.vigente), ("corregida", ["supresion"]))
        self.assertEqual(conf.hechos_vigentes(pedida).derechos, ["supresion"])

    def test_hechos_vigentes_para_el_motor(self):
        c = Confirmacion(
            estado="corregida", propuesta=["oposicion"], vigente=["supresion", "bloqueo"]
        )
        h = conf.hechos_vigentes(c)
        self.assertEqual((h.es_solicitud, h.derechos), (True, ["supresion", "bloqueo"]))


class TestBloqueoPreventivo(unittest.TestCase):
    """Opción B (decisión de Matías, 17 oct): si la lectura por defecto incluiría un bloqueo,
    se aplica desde el ingreso y se levanta si la persona aclara que no lo pide."""

    def test_si_la_lectura_por_defecto_lo_incluiria_corre_desde_el_ingreso(self):
        c = conf.preparar(hechos(derechos=["supresion"]), AHORA)
        self.assertTrue(c.bloqueo_preventivo)
        self.assertIn("bloqueo", c.vigente)
        r = decidir_solicitud(conf.hechos_vigentes(c), AHORA.date())
        self.assertIsNotNone(r.bloqueo)
        self.assertIn("Bloqueo preventivo", r.bloqueo.porque)
        # 2 días hábiles desde el ingreso (miércoles 2 → viernes 4 de diciembre de 2026).
        self.assertEqual(r.bloqueo.vence, date(2026, 12, 4))

    def test_no_se_agrega_si_la_lectura_por_defecto_no_lo_tendria(self):
        c = conf.preparar(hechos(derechos=["acceso"]), AHORA)
        self.assertFalse(c.bloqueo_preventivo)
        self.assertEqual(c.vigente, ["acceso"])

    def test_si_la_persona_ya_lo_pidio_no_es_preventivo(self):
        c = conf.preparar(hechos(derechos=["oposicion", "bloqueo"]), AHORA)
        self.assertFalse(c.bloqueo_preventivo)
        r = decidir_solicitud(conf.hechos_vigentes(c), AHORA.date())
        self.assertNotIn("preventivo", r.bloqueo.porque)

    def test_no_se_agrega_si_la_espera_no_aplica(self):
        c = conf.preparar(hechos(requiere_confirmacion=False), AHORA)
        self.assertFalse(c.bloqueo_preventivo)
        self.assertEqual(c.vigente, ["oposicion"])

    def test_se_levanta_si_aclara_que_no_lo_pide(self):
        c = conf.preparar(hechos(), AHORA)
        c = conf.aplicar_respuesta(c, ["oposicion"], None, AHORA + timedelta(hours=5))
        self.assertEqual(c.estado, "confirmada")  # confirmó lo que propuso el sistema
        self.assertTrue(conf.bloqueo_levantado(c))
        r = decidir_solicitud(conf.hechos_vigentes(c), AHORA.date())
        self.assertIsNone(r.bloqueo)

    def test_sigue_si_lo_confirma(self):
        c = conf.preparar(hechos(), AHORA)
        c = conf.aplicar_respuesta(c, ["oposicion", "bloqueo"], None, AHORA)
        self.assertFalse(conf.bloqueo_levantado(c))
        r = decidir_solicitud(conf.hechos_vigentes(c), AHORA.date())
        self.assertNotIn("preventivo", r.bloqueo.porque)  # ahora lo pidió ella

    def test_sin_respuesta_sigue_y_el_plazo_no_cambia(self):
        c = conf.preparar(hechos(derechos=["supresion"]), AHORA)
        antes = decidir_solicitud(conf.hechos_vigentes(c), AHORA.date()).bloqueo
        c = conf.aplicar_por_defecto(c, AHORA + timedelta(days=conf.dias_de_espera()))
        self.assertEqual(c.vigente, ["oposicion", "bloqueo"])
        self.assertFalse(conf.bloqueo_levantado(c))
        despues = decidir_solicitud(conf.hechos_vigentes(c), AHORA.date()).bloqueo
        self.assertEqual(despues.vence, antes.vence)
        self.assertIn("Bloqueo preventivo", despues.porque)

    def test_se_puede_apagar_en_la_regla(self):
        params = dict(conf._parametros()) | {"bloqueo_preventivo": False}
        with mock.patch.object(conf, "_parametros", return_value=params):
            c = conf.preparar(hechos(), AHORA)
        self.assertFalse(c.bloqueo_preventivo)
        self.assertEqual(c.vigente, ["oposicion"])

    def test_la_regla_lo_declara_pendiente_de_revision_legal(self):
        regla = cargar_reglas()["reglas"]["confirmacion_titular"]
        self.assertTrue(regla["parametros"]["bloqueo_preventivo"])
        self.assertIn("bloqueo preventivo", regla["criterio"])
        self.assertIn("revisión legal", regla["criterio"])


if __name__ == "__main__":
    unittest.main()
