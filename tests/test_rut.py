import unittest

from ora_privacidad import rut


class TestDigitoVerificador(unittest.TestCase):
    def test_casos_conocidos(self):
        self.assertEqual(rut.calcular_dv(11_111_111), "1")
        self.assertEqual(rut.calcular_dv(12_345_678), "5")

    def test_dv_k_y_cero(self):
        dvs = {rut.calcular_dv(n) for n in range(1_000_000, 1_000_200)}
        self.assertIn("K", dvs)
        self.assertIn("0", dvs)

    def test_cuerpo_invalido(self):
        with self.assertRaises(ValueError):
            rut.calcular_dv(0)


class TestValidacionYFormato(unittest.TestCase):
    def test_formatos_aceptados(self):
        for t in ("12.345.678-5", "12345678-5", "12345678 - 5"):
            self.assertTrue(rut.es_valido(t), t)

    def test_dv_incorrecto(self):
        self.assertFalse(rut.es_valido("12.345.678-4"))

    def test_k_minuscula(self):
        cuerpo = next(n for n in range(1_000_000, 1_001_000) if rut.calcular_dv(n) == "K")
        self.assertTrue(rut.es_valido(f"{cuerpo}-k"))

    def test_formatear_y_enmascarar(self):
        r = rut.parsear("12345678-5")
        self.assertEqual(r.formatear(), "12.345.678-5")
        self.assertEqual(r.enmascarar(), "12.***.***-*")
        self.assertNotIn("345", r.enmascarar())


class TestBusqueda(unittest.TestCase):
    def test_encuentra_en_texto(self):
        hallados = rut.buscar("Pago a 12.345.678-5 y a 11111111-1 el lunes")
        self.assertEqual([h[0].formatear() for h in hallados], ["12.345.678-5", "11.111.111-1"])

    def test_ignora_invalidos_y_numeros_sueltos(self):
        self.assertEqual(rut.buscar("Folio 123456785, ref 12.345.678-4"), [])
        self.assertEqual(len(rut.buscar("12.345.678-4", solo_validos=False)), 1)


if __name__ == "__main__":
    unittest.main()
