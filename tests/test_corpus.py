import unittest

from ora_privacidad.corpus import RAIZ_DATOS, Corpus, normalizar_clave


class TestCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = Corpus.desde_directorio()

    def test_normas_cargadas(self):
        self.assertEqual(
            set(self.corpus.normas), {"ley-19628", "ley-21719", "ds-662-2025", "ley-21663"}
        )
        for norma in self.corpus.normas.values():
            self.assertTrue(norma.fuente.startswith("https://"))

    def test_articulos_que_usa_el_motor(self):
        requeridos = {
            "ley-19628": [
                "1",
                "2",
                "3",
                "5",
                "6",
                "7",
                "8",
                "8 bis",
                "8 ter",
                "9",
                "11",
                "13",
                "14 ter",
                "14 quater",
                "14 quinquies",
                "14 sexies",
                "15 bis",
                "15 ter",
                "16",
                "16 quater",
                "23",
                "27",
                "34 bis",
                "34 ter",
                "34 quater",
                "35",
                "39",
                "44",
                "47",
                "49",
                "50",
            ],
            "ley-21719": ["transitorio primero", "transitorio sexto"],
            "ds-662-2025": ["3", "8"],
            "ley-21663": ["1", "4", "9", "27"],
        }
        for norma, claves in requeridos.items():
            for clave in claves:
                self.assertIsNotNone(self.corpus.obtener(norma, clave), f"{norma} {clave}")

    def test_secuencia_completa_de_la_ley_19628(self):
        claves = [a.clave for a in self.corpus.articulos("ley-19628")]
        for n in [*range(1, 17), *range(20, 56)]:
            self.assertIn(str(n), claves)
        self.assertEqual(len(claves), len(set(claves)))

    def test_texto_es_el_oficial_y_esta_bien_cortado(self):
        art = self.corpus.obtener("ley-19628", "14 sexies")
        self.assertTrue(art.texto.startswith("Artículo 14 sexies.- Deber de reportar"))
        self.assertIn("sin dilaciones indebidas", art.texto)
        self.assertNotIn("Artículo 14 septies", art.texto)
        for a in self.corpus.articulos():
            self.assertFalse(a.texto.endswith(".."), a.referencia)
            orden_de_cambio = r"\n\d+\) (Reemplázase|Sustitúyese|Intercálanse)"
            self.assertNotRegex(a.texto, orden_de_cambio, a.referencia)

    def test_modificaciones_marcadas(self):
        self.assertEqual(self.corpus.obtener("ley-19628", "2").tipo, "modificacion")
        self.assertEqual(self.corpus.obtener("ley-19628", "11").tipo, "texto")

    def test_epigrafe(self):
        self.assertEqual(self.corpus.obtener("ley-19628", "5").epigrafe, "Derecho de acceso")
        self.assertEqual(self.corpus.obtener("ley-21663", "9").epigrafe, "Deber de reportar")


class TestVerificarCita(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = Corpus.desde_directorio()

    def test_cita_valida_con_fragmento(self):
        r = self.corpus.verificar_cita("Ley 21.663", "art. 9", "plazo máximo de tres horas")
        self.assertTrue(r.valida)
        self.assertIn("alerta temprana", r.texto)

    def test_fragmento_ignora_tildes_y_puntuacion(self):
        r = self.corpus.verificar_cita("19.628", "Artículo 14 sexies", "SIN DILACIONES, indebidas")
        self.assertTrue(r.valida)

    def test_fragmento_inventado(self):
        r = self.corpus.verificar_cita("ley-19628", "14 sexies", "dentro de 72 horas")
        self.assertTrue(r.existe)
        self.assertFalse(r.valida)

    def test_articulo_inexistente(self):
        r = self.corpus.verificar_cita("ley-19628", "99 bis")
        self.assertFalse(r.existe)
        self.assertFalse(r.valida)
        self.assertIsNone(r.texto)

    def test_norma_desconocida(self):
        self.assertFalse(self.corpus.verificar_cita("GDPR", "33").existe)

    def test_normalizacion_de_claves(self):
        self.assertEqual(normalizar_clave("14 Quáter"), "14 quater")
        self.assertEqual(normalizar_clave("1°  bis"), "1 bis")
        self.assertEqual(self.corpus.obtener("ley-19628", "16 quáter").clave, "16 quater")


class TestIndiceExportado(unittest.TestCase):
    def test_indice_al_dia(self):
        indice = RAIZ_DATOS / "indice.json"
        self.assertTrue(indice.exists(), "Falta data/normas/indice.json")
        self.assertEqual(
            indice.read_text(encoding="utf-8"),
            Corpus.desde_directorio().a_json(),
            "indice.json desactualizado: ejecuta python -m ora_privacidad.corpus --exportar",
        )


if __name__ == "__main__":
    unittest.main()
