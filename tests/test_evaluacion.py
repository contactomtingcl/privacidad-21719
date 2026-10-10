import unittest
from types import SimpleNamespace

from privacidad import guardia
from privacidad.evaluacion import ejecutar
from privacidad.evaluacion.casos import cargar_columnas, cargar_incidentes, cargar_solicitudes
from privacidad.inventario import cargar_categorias
from privacidad.inventario.actividad import CATEGORIAS_EXTRA
from privacidad.motor import HechosSolicitud, decidir_incidente, decidir_solicitud


class TestSetEtiquetado(unittest.TestCase):
    def test_hay_150_casos(self):
        columnas = sum(len(p.columnas) for p in cargar_columnas())
        self.assertEqual(
            (columnas, len(cargar_incidentes()), len(cargar_solicitudes())), (50, 50, 50)
        )

    def test_ids_unicos(self):
        for casos in (cargar_incidentes(), cargar_solicitudes()):
            ids = [c.id for c in casos]
            self.assertEqual(len(ids), len(set(ids)))

    def test_todo_es_sintetico(self):
        guardia.exigir_sintetico([c.valores for p in cargar_columnas() for c in p.columnas])
        guardia.exigir_sintetico([c.texto for c in cargar_incidentes()])
        guardia.exigir_sintetico([c.texto for c in cargar_solicitudes()])

    def test_categorias_esperadas_existen(self):
        validas = set(cargar_categorias()) | set(CATEGORIAS_EXTRA)
        for p in cargar_columnas():
            for c in p.columnas:
                self.assertIn(c.esperado, validas, c.nombre)

    def test_deberes_esperados_coinciden_con_el_motor(self):
        for caso in cargar_incidentes():
            r = decidir_incidente(caso.hechos, caso.perfil)
            obtenido = {
                "aviso_agencia": r.aviso_agencia.decision,
                "aviso_titulares": r.aviso_titulares.decision,
                "reporte_anci": r.reporte_anci.decision,
            }
            self.assertEqual(obtenido, caso.esperado.model_dump(), caso.id)

    def test_plazos_calculados_a_mano_coinciden_con_el_motor(self):
        for caso in cargar_solicitudes():
            e = caso.esperado
            self.assertTrue(e.es_solicitud or not e.requiere_confirmacion, caso.id)
            if not e.es_solicitud:
                self.assertIsNone(e.vence_respuesta, caso.id)
                continue
            r = decidir_solicitud(
                HechosSolicitud(es_solicitud=True, derechos=e.derechos), caso.ingreso
            )
            self.assertEqual(r.respuesta.vence, e.vence_respuesta, caso.id)
            self.assertEqual(r.bloqueo.vence if r.bloqueo else None, e.vence_bloqueo, caso.id)


class IAFalsa:
    """Responde siempre lo mismo y guarda lo que recibe, para revisar el enmascarado."""

    def __init__(self, falla: bool = False) -> None:
        self.falla = falla
        self.recibido: list[str] = []

    def llamar(self, **kw):
        self.recibido.append(kw["mensajes"][0]["content"])
        if self.falla:
            raise TimeoutError("sin conexión")
        nombre = kw["forzar_herramienta"]
        entradas = {
            "registrar_hechos": {
                "datos_personales": True,
                "vulneracion": "filtracion",
                "categorias_especiales": [],
                "riesgo_mitigado": False,
                "ciberincidente": "no",
                "interrupcion_servicio": False,
                "resumen": "x",
            },
            "decidir_deberes": {
                "aviso_agencia": "si",
                "aviso_titulares": "no",
                "reporte_anci": "no",
                "razon": "x",
            },
            "interpretar_solicitud": {
                "es_solicitud": True,
                "derechos": ["acceso"],
                "requiere_confirmacion": False,
                "resumen": "x",
            },
            "interpretar_y_calcular": {
                "es_solicitud": True,
                "derechos": ["acceso"],
                "requiere_confirmacion": False,
                "vence_respuesta": "2027-01-01",
            },
            "clasificar_columnas": {"columnas": []},
        }
        return SimpleNamespace(
            bloques_herramienta=[{"nombre": nombre, "entrada": entradas[nombre]}], costo_usd=0.001
        )


class TestEjecucion(unittest.TestCase):
    def test_linea_base_sin_ia(self):
        r = ejecutar.evaluar_incidentes()
        self.assertEqual(list(r["metricas"]), ["base"])
        self.assertEqual(r["metricas"]["base"]["casos"], 50)

    def test_tres_niveles_con_ia_falsa(self):
        ia = IAFalsa()
        r = ejecutar.evaluar_solicitudes(ia, "modelo-falso")
        self.assertEqual(list(r["metricas"]), ["base", "ia_sola", "ia_motor"])
        self.assertAlmostEqual(r["costo_usd"]["ia_motor"], 0.05)
        # El teléfono del caso sol-28 nunca llega a la IA.
        self.assertFalse(any("0000 1234" in m for m in ia.recibido))
        self.assertTrue(any("[TELEFONO_1]" in m for m in ia.recibido))

    def test_si_la_ia_falla_el_caso_queda_para_revision(self):
        r = ejecutar.evaluar_incidentes(IAFalsa(falla=True), "modelo-falso")
        caso = r["casos"][0]
        self.assertEqual(set(caso["ia_motor"].values()), {"revisar"})
        self.assertEqual(r["metricas"]["ia_motor"]["deberes_omitidos"], 0)

    def test_si_la_ia_falla_el_plazo_de_la_solicitud_corre_igual(self):
        r = ejecutar.evaluar_solicitudes(IAFalsa(falla=True), "modelo-falso")
        caso = r["casos"][0]
        self.assertIsNotNone(caso["ia_motor"]["vence_respuesta"])
        self.assertTrue(caso["ia_motor"]["requiere_confirmacion"])


if __name__ == "__main__":
    unittest.main()
