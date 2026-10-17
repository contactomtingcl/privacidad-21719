import unittest
from datetime import date, datetime

from privacidad.corpus import corpus_por_defecto
from privacidad.motor import (
    HechosIncidente,
    HechosSolicitud,
    cargar_reglas,
    decidir_incidente,
    decidir_solicitud,
    sumar_dias_habiles,
)


def hechos(**kw) -> HechosIncidente:
    base = {
        "datos_personales": True,
        "vulneracion": "filtracion",
        "categorias_especiales": [],
        "ciberincidente": "si",
    }
    return HechosIncidente(**(base | kw))


class TestFuentes(unittest.TestCase):
    def test_cada_fragmento_existe_en_el_texto_oficial(self):
        corpus = corpus_por_defecto()
        reglas = cargar_reglas()
        fuentes = [r["fuente"] for r in reglas["reglas"].values()]
        fuentes += [
            r["fuente_prorroga"] for r in reglas["reglas"].values() if "fuente_prorroga" in r
        ]
        fuentes.append(reglas["servicios_esenciales"]["fuente"])
        fuentes.append(reglas["vigencias"]["ley-21719"]["fuente"])
        for f in fuentes:
            r = corpus.verificar_cita(f["norma"], str(f["articulo"]), f["fragmento"])
            self.assertTrue(r.existe and r.fragmento_encontrado, f)


class TestIncidente(unittest.TestCase):
    def test_filtracion_comun_avisa_solo_a_la_agencia(self):
        r = decidir_incidente(hechos(ciberincidente="no"), "empresa_privada")
        self.assertEqual(r.aviso_agencia.decision, "si")
        self.assertEqual(r.aviso_titulares.decision, "no")
        self.assertEqual(r.reporte_anci.decision, "no")

    def test_datos_de_menores_obligan_a_avisar_a_titulares(self):
        r = decidir_incidente(hechos(categorias_especiales=["menores_14"]), "empresa_privada")
        self.assertEqual(r.aviso_titulares.decision, "si")
        self.assertIn("menores de 14", r.aviso_titulares.porque)

    def test_sin_datos_personales_no_hay_aviso(self):
        r = decidir_incidente(hechos(datos_personales=False), "empresa_privada")
        self.assertEqual(r.aviso_agencia.decision, "no")
        self.assertEqual(r.aviso_titulares.decision, "no")

    def test_riesgo_mitigado_queda_para_revision_humana(self):
        r = decidir_incidente(
            hechos(riesgo_mitigado=True, categorias_especiales=["sensibles"]), "empresa_privada"
        )
        self.assertEqual(r.aviso_agencia.decision, "revisar")
        self.assertEqual(r.aviso_titulares.decision, "revisar")

    def test_municipio_con_ciberataque_reporta_a_anci_con_tres_relojes(self):
        conocido = datetime(2026, 12, 3, 9, 15)
        r = decidir_incidente(hechos(), "organismo_publico", conocimiento=conocido)
        self.assertEqual(r.reporte_anci.decision, "si")
        self.assertEqual(r.reporte_anci.vence, datetime(2026, 12, 3, 12, 15))
        vencimientos = {p.id: p.vence for p in r.plazos_anci}
        self.assertEqual(vencimientos["anci_actualizacion"], datetime(2026, 12, 6, 9, 15))
        self.assertEqual(vencimientos["anci_informe_final"], datetime(2026, 12, 18, 12, 15))

    def test_municipio_con_carpeta_de_papel_perdida_no_va_a_anci(self):
        r = decidir_incidente(
            hechos(vulneracion="perdida", ciberincidente="no"), "organismo_publico"
        )
        self.assertEqual(r.reporte_anci.decision, "no")
        self.assertEqual(r.aviso_agencia.decision, "si")

    def test_duda_sobre_ciberincidente_queda_para_revision(self):
        r = decidir_incidente(hechos(ciberincidente="dudoso"), "salud")
        self.assertEqual(r.reporte_anci.decision, "revisar")

    def test_nota_de_vigencia_antes_del_1_de_diciembre(self):
        r = decidir_incidente(hechos(), "empresa_privada", conocimiento=datetime(2026, 11, 2, 10))
        self.assertIn("01-12-2026", r.aviso_agencia.nota_vigencia)
        r = decidir_incidente(hechos(), "empresa_privada", conocimiento=datetime(2026, 12, 2, 10))
        self.assertIsNone(r.aviso_agencia.nota_vigencia)


class TestSolicitud(unittest.TestCase):
    def test_plazo_de_30_dias_corridos(self):
        r = decidir_solicitud(
            HechosSolicitud(es_solicitud=True, derechos=["acceso"]), date(2026, 12, 2)
        )
        self.assertEqual(r.respuesta.vence, date(2027, 1, 1))
        self.assertIsNone(r.bloqueo)
        self.assertIsNone(r.comunicar_terceros)

    def test_bloqueo_cuenta_dias_habiles_sin_fin_de_semana_ni_feriados(self):
        # Viernes 9 de octubre de 2026: sábado, domingo y lunes 12 (feriado) no cuentan.
        self.assertEqual(sumar_dias_habiles(date(2026, 10, 9), 2)[0], date(2026, 10, 14))
        r = decidir_solicitud(
            HechosSolicitud(es_solicitud=True, derechos=["supresion", "bloqueo"]), date(2026, 10, 9)
        )
        self.assertEqual(r.bloqueo.vence, date(2026, 10, 14))
        self.assertFalse(r.bloqueo.a_confirmar)  # calendario verificado para 2026 y 2027
        self.assertIsNotNone(r.comunicar_terceros)

    def test_traslados_y_feriado_adicional_de_2027(self):
        # Martes 29 de junio de 2027: San Pedro y San Pablo pasa al lunes 28 (Ley 19.668).
        self.assertEqual(sumar_dias_habiles(date(2027, 6, 25), 1)[0], date(2027, 6, 29))
        # 18 y 19 de septiembre de 2027 caen sábado y domingo: el viernes 17 es feriado
        # (Ley 20.983). Jueves 16 + 1 día hábil = lunes 20.
        self.assertEqual(sumar_dias_habiles(date(2027, 9, 16), 1)[0], date(2027, 9, 20))

    def test_fuera_del_calendario_verificado_queda_a_confirmar(self):
        self.assertTrue(sumar_dias_habiles(date(2027, 12, 20), 2)[1])
        self.assertFalse(sumar_dias_habiles(date(2027, 12, 30), 2)[1])  # termina en 2028
        self.assertFalse(sumar_dias_habiles(date(2025, 12, 30), 2)[1])

    def test_no_solicitud_no_genera_plazos(self):
        r = decidir_solicitud(HechosSolicitud(es_solicitud=False), date(2026, 12, 2))
        self.assertIsNone(r.respuesta)


if __name__ == "__main__":
    unittest.main()
