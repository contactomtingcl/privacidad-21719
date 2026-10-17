"""Operadores de importancia vital (Ley 21.663, arts. 4 y 9)."""

import unittest
from datetime import datetime, timedelta

from privacidad.motor import HechosIncidente, decidir_incidente
from privacidad.panel import vista

CONOCIDO = datetime(2026, 12, 2, 10, 0)


def hechos(**kw) -> HechosIncidente:
    base = {"datos_personales": True, "vulneracion": "acceso_no_autorizado", "ciberincidente": "si"}
    return HechosIncidente(**(base | kw))


def plazos(r):
    return {p.id: p for p in r.plazos_anci}


class TestOIV(unittest.TestCase):
    def test_empresa_privada_oiv_reporta_a_la_anci(self):
        normal = decidir_incidente(hechos(), "empresa_privada", CONOCIDO)
        oiv = decidir_incidente(hechos(), "empresa_privada", CONOCIDO, oiv=True)
        self.assertEqual(normal.reporte_anci.decision, "no")
        self.assertEqual(oiv.reporte_anci.decision, "si")
        self.assertIn("operadores de importancia vital", oiv.reporte_anci.citas[1].fragmento)

    def test_actualizacion_a_24_horas_si_se_interrumpe_el_servicio(self):
        sin = decidir_incidente(hechos(), "energia", CONOCIDO, oiv=True)
        con = decidir_incidente(hechos(interrupcion_servicio=True), "energia", CONOCIDO, oiv=True)
        self.assertEqual(plazos(sin)["anci_actualizacion"].vence, CONOCIDO + timedelta(hours=72))
        self.assertEqual(plazos(con)["anci_actualizacion"].vence, CONOCIDO + timedelta(hours=24))
        self.assertIn("veinticuatro", plazos(con)["anci_actualizacion"].citas[0].fragmento)

    def test_servicio_esencial_que_no_es_oiv_mantiene_72_horas(self):
        r = decidir_incidente(hechos(interrupcion_servicio=True), "energia", CONOCIDO)
        self.assertEqual(plazos(r)["anci_actualizacion"].vence, CONOCIDO + timedelta(hours=72))
        self.assertNotIn("anci_plan_accion", plazos(r))

    def test_plan_de_accion_en_7_dias_desde_que_se_supo(self):
        r = decidir_incidente(hechos(), "salud", CONOCIDO, oiv=True)
        self.assertEqual(plazos(r)["anci_plan_accion"].vence, CONOCIDO + timedelta(days=7))
        self.assertEqual(
            vista.despues_alerta(r.plazos_anci),
            "Después: actualización a las 72 horas e informe final a los 15 días; además, el "
            "plan de acción (máximo 7 días).",
        )

    def test_no_es_oiv_por_defecto(self):
        r = decidir_incidente(hechos(), "organismo_publico", CONOCIDO)
        self.assertEqual(
            [p.id for p in r.plazos_anci],
            ["anci_alerta_temprana", "anci_actualizacion", "anci_informe_final"],
        )


if __name__ == "__main__":
    unittest.main()
