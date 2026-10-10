import unittest
from datetime import date

from ora_privacidad import guardia
from ora_privacidad.deteccion import Enmascarador, detectar, edad_en, parsear_fecha


class TestDeteccion(unittest.TestCase):
    def test_tipos_detectados(self):
        rut = guardia.rut_sintetico(3)
        texto = f"Envié la planilla de {rut} a ana@x.example, cel +56 9 0000 0001, nac. 03/02/2015"
        self.assertEqual([d.tipo for d in detectar(texto)], ["rut", "correo", "telefono", "fecha"])

    def test_no_confunde_montos_con_telefonos(self):
        self.assertEqual(detectar("Monto 3123 4567 y folio 12345678"), [])

    def test_fijo_requiere_prefijo(self):
        self.assertEqual([d.tipo for d in detectar("Llamar al +56 41 234 5678")], ["telefono"])

    def test_fechas(self):
        self.assertEqual(parsear_fecha("03/02/2015"), date(2015, 2, 3))
        self.assertEqual(parsear_fecha("2015-02-03"), date(2015, 2, 3))
        self.assertIsNone(parsear_fecha("31/02/2015"))

    def test_edad(self):
        ref = date(2026, 10, 10)
        self.assertEqual(edad_en(date(2012, 10, 10), ref), 14)
        self.assertEqual(edad_en(date(2012, 10, 11), ref), 13)


class TestEnmascarador(unittest.TestCase):
    def test_enmascara_y_reutiliza_marcadores(self):
        rut = guardia.rut_sintetico(5)
        e = Enmascarador()
        salida = e.enmascarar(f"{rut} pidió borrar. Repito: {rut}. Correo b@y.example")
        self.assertEqual(salida, "[RUT_1] pidió borrar. Repito: [RUT_1]. Correo [CORREO_1]")
        self.assertNotIn(rut, salida)
        self.assertEqual(e.cantidad, 2)

    def test_revertir(self):
        e = Enmascarador()
        original = "Contacto: c@z.example y +56 9 0000 0042"
        self.assertEqual(e.revertir(e.enmascarar(original)), original)


if __name__ == "__main__":
    unittest.main()
