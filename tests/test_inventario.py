import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from privacidad import guardia
from privacidad.corpus import corpus_por_defecto
from privacidad.inventario import cargar_categorias, perfilar_archivo, perfilar_dataframe
from privacidad.inventario.perfilador import categoria_por_encabezado
from privacidad.sinteticos import comercial_los_robles

REF = date(2026, 10, 10)


class TestCatalogo(unittest.TestCase):
    def test_cada_categoria_cita_la_ley_textualmente(self):
        corpus = corpus_por_defecto()
        for clave, cat in cargar_categorias().items():
            f = cat.fundamento
            self.assertTrue(
                corpus.verificar_cita(f.norma, f.articulo, f.fragmento).valida,
                f"{clave}: la cita no aparece en {f.norma} art. {f.articulo}",
            )

    def test_frase_especifica_gana(self):
        self.assertEqual(categoria_por_encabezado("Previsión de salud")[0].clave, "prevision_salud")
        self.assertEqual(categoria_por_encabezado("Alergias")[0].clave, "salud")
        self.assertEqual(categoria_por_encabezado("Celular apoderado")[0].clave, "telefono")
        self.assertEqual(categoria_por_encabezado("Nombre hijo/a")[0].clave, "nombre")
        self.assertEqual(categoria_por_encabezado("Talla polera"), (None, None))


class TestPlanillasDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rutas = comercial_los_robles.generar(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_generador_es_determinista(self):
        with tempfile.TemporaryDirectory() as otro:
            rutas2 = comercial_los_robles.generar(Path(otro))
            for clave, ruta in self.rutas.items():
                leer = pd.read_excel if ruta.suffix == ".xlsx" else pd.read_csv
                pd.testing.assert_frame_equal(leer(ruta, dtype=str), leer(rutas2[clave], dtype=str))

    def test_planilla_del_paseo(self):
        p = perfilar_archivo(self.rutas["paseo"], referencia=REF)
        self.assertEqual(p.filas, 84)
        self.assertEqual(p.menores.menores_de_14, 61)
        self.assertEqual(p.menores.menores_de_18, 84)
        self.assertEqual(p.categorias_sensibles, ["salud"])
        self.assertIn("menores", p.especiales)
        por_nombre = {c.nombre: c for c in p.columnas}
        self.assertTrue(por_nombre["RUT hijo/a"].contexto_menores)
        self.assertEqual(por_nombre["RUT hijo/a"].confianza, "alta")
        self.assertEqual(por_nombre["Correo apoderado"].categoria, "correo")
        self.assertEqual(p.requieren_revision, ["Talla polera"])

    def test_nomina(self):
        p = perfilar_archivo(self.rutas["nomina"], referencia=REF)
        self.assertEqual(p.categorias_sensibles, ["afiliacion_sindical", "salud"])
        self.assertIn("financiero", p.especiales)
        por_nombre = {c.nombre: c for c in p.columnas}
        self.assertEqual(por_nombre["Previsión de salud"].sensible, "revisar")
        self.assertIsNone(p.menores)

    def test_proveedores_rut_de_empresa_requiere_revision(self):
        p = perfilar_archivo(self.rutas["proveedores"], referencia=REF)
        rut_empresa = next(c for c in p.columnas if c.nombre == "RUT empresa")
        self.assertTrue(rut_empresa.requiere_revision)
        self.assertEqual(rut_empresa.confianza, "baja")

    def test_todos_los_archivos_pasan_la_guardia(self):
        for ruta in self.rutas.values():
            perfilar_archivo(ruta, referencia=REF)  # lanzaría DatosNoSinteticosError


class TestGuardiaEnInventario(unittest.TestCase):
    def test_rechaza_planilla_con_datos_reales(self):
        df = pd.DataFrame({"RUT": ["12.345.678-5"], "Nombre": ["X"]})
        with self.assertRaises(guardia.DatosNoSinteticosError):
            perfilar_dataframe(df, referencia=REF)

    def test_conflicto_encabezado_y_valores(self):
        df = pd.DataFrame({"Comuna": [guardia.rut_sintetico(i) for i in range(5)]})
        col = perfilar_dataframe(df, referencia=REF).columnas[0]
        self.assertEqual(col.confianza, "baja")
        self.assertTrue(col.requiere_revision)


if __name__ == "__main__":
    unittest.main()
