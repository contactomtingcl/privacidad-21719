"""Riesgo de infracción por planilla (arts. 34 bis, 34 ter, 34 quáter y 35)."""

import unittest
from datetime import datetime

import yaml

from privacidad.canal.modelos import ZONA_CHILE
from privacidad.corpus import corpus_por_defecto
from privacidad.inventario import riesgos, servicio
from privacidad.motor.motor import RAIZ_REGLAS

from .canal_apoyo import HECHOS_INCIDENTE, ClienteFalso
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

AHORA = datetime(2026, 10, 17, 12, tzinfo=ZONA_CHILE)


def registro(nombre):
    return servicio.procesar(
        nombre,
        (servicio.DATOS_DEMO / nombre).read_bytes(),
        "",
        id_organizacion="comercial-los-robles",
        por="x",
        cliente=None,
        ahora=AHORA,
    )


def reglas(r):
    return [h.regla for h in r.hallazgos]


class TestFuentes(unittest.TestCase):
    def test_cada_cita_existe_en_el_corpus(self):
        corpus = corpus_por_defecto()
        d = yaml.safe_load((RAIZ_REGLAS / "riesgos.yaml").read_text("utf-8"))
        fuentes = [v["fuente"] for v in d["sanciones_por_nivel"].values()]
        fuentes += [
            r[k] for r in d["reglas"].values() for k in ("fuente", "fuente_agravante") if k in r
        ]
        for f in fuentes:
            r = corpus.verificar_cita(f["norma"], str(f["articulo"]), f["fragmento"])
            self.assertTrue(r.existe and r.fragmento_encontrado, f)


class TestEvaluar(unittest.TestCase):
    def test_paseo(self):
        r = riesgos.evaluar(registro("paseo_fin_de_anio.xlsx"))
        self.assertEqual(r.nivel, "grave")
        self.assertIn("datos_de_menores", reglas(r))
        menores = next(h for h in r.hallazgos if h.regla == "datos_de_menores")
        self.assertEqual(menores.agravante, "gravisima")
        self.assertIn("34 quater", menores.fuente_agravante.articulo)

    def test_nomina_sin_consentimiento_expreso_y_su_version_minima(self):
        reg = registro("nomina_trabajadores.xlsx")
        antes = riesgos.evaluar(reg)
        self.assertIn("sensibles_sin_consentimiento_expreso", reglas(antes))
        self.assertIn("datos_innecesarios", reglas(antes))
        quitar = {c.nombre for c in reg.actividad.columnas if c.necesaria is False}
        despues = riesgos.evaluar(reg, quitar)
        self.assertNotIn("sensibles_sin_consentimiento_expreso", reglas(despues))
        self.assertNotIn("datos_innecesarios", reglas(despues))

    def test_proveedores_sin_riesgo_visible(self):
        r = riesgos.evaluar(registro("proveedores.csv"))
        self.assertIsNone(r.nivel)
        self.assertIsNone(r.sancion)

    def test_sin_ia_falta_la_base_legal(self):
        import pandas as pd

        df = pd.DataFrame({"Nombre": ["Persona Uno"], "Correo": ["uno@example.com"]})
        reg = servicio.procesar(
            "lista.csv",
            df.to_csv(index=False).encode(),
            "Lista de asistentes.",
            id_organizacion="x",
            por="x",
            cliente=None,
            ahora=AHORA,
        )
        self.assertIn("sin_base_legal", reglas(riesgos.evaluar(reg)))


class TestOrganoPublico(unittest.TestCase):
    def test_sancion_del_articulo_44(self):
        r = riesgos.evaluar(registro("nomina_trabajadores.xlsx"), perfil="organismo_publico")
        self.assertIn("jefe superior", r.sancion)
        self.assertEqual(r.fuente_sancion.articulo, "44")


class TestPanel(unittest.TestCase):
    def test_se_muestra_en_la_ficha_y_la_lista(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        reg = registro("nomina_trabajadores.xlsx")
        canal._repo.guardar_actividad(reg)
        nav = Navegador(app)
        entrar(nav, usuario="delegado-robles")
        html = nav.pedir("GET", f"/panel/inventario/{reg.id}").html
        self.assertIn("Riesgo de infracción si no se corrige", html)
        self.assertIn("Datos sensibles sin consentimiento expreso", html)
        self.assertIn("Si se confirma una infracción grave: multa de hasta 10.000 UTM.", html)
        self.assertIn("Riesgo grave", nav.pedir("GET", "/panel/inventario").html)


if __name__ == "__main__":
    unittest.main()
