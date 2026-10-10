import unittest

from ora_privacidad import guardia, rut


class TestConvencionSintetica(unittest.TestCase):
    def test_generadores_producen_datos_aceptados(self):
        for semilla in range(0, 5000, 37):
            r = guardia.rut_sintetico(semilla)
            self.assertTrue(rut.es_valido(r), r)
            texto = f"{r} {guardia.movil_sintetico(semilla)} ana{semilla}@empresa.example"
            self.assertEqual(guardia.revisar(texto), [], texto)

    def test_correos_reservados(self):
        for correo in ("a@example.com", "b@rrhh.example.org", "c@x.test", "d@y.invalid"):
            self.assertEqual(guardia.revisar(correo), [], correo)


class TestRechazos(unittest.TestCase):
    def test_rut_fuera_del_tramo(self):
        h = guardia.revisar("RUT 12.345.678-5")
        self.assertEqual([x.tipo for x in h], ["rut"])
        self.assertNotIn("345.678", h[0].valor_enmascarado)

    def test_rut_con_dv_invalido_no_se_considera_rut(self):
        self.assertEqual(guardia.revisar("12.345.678-4"), [])

    def test_correo_real(self):
        h = guardia.revisar("contacto@gmail.com")
        self.assertEqual(h[0].tipo, "correo")
        self.assertEqual(h[0].valor_enmascarado, "c***@gmail.com")

    def test_dominio_parecido_no_engana(self):
        self.assertEqual(guardia.revisar("x@example.com.cl")[0].tipo, "correo")
        self.assertEqual(guardia.revisar("x@notexample.com")[0].tipo, "correo")

    def test_movil_real(self):
        for tel in ("+56 9 8765 4321", "987654321", "+56987654321"):
            h = guardia.revisar(tel)
            self.assertEqual([x.tipo for x in h], ["telefono"], tel)
            self.assertNotIn("8765", h[0].valor_enmascarado)


class TestEstructuras(unittest.TestCase):
    def test_tabla_indica_el_campo(self):
        filas = [
            {"nombre": "Hijo Uno", "rut": guardia.rut_sintetico(1)},
            {"nombre": "Hijo Dos", "rut": "12.345.678-5", "correo": "p@gmail.com"},
        ]
        h = guardia.revisar(filas)
        self.assertEqual({(x.tipo, x.campo) for x in h}, {("rut", "rut"), ("correo", "correo")})

    def test_exigir_lanza_error_sin_revelar_valores(self):
        with self.assertRaises(guardia.DatosNoSinteticosError) as ctx:
            guardia.exigir_sintetico({"rut": "12.345.678-5"})
        self.assertNotIn("345.678", str(ctx.exception))
        self.assertEqual(len(ctx.exception.hallazgos), 1)

    def test_exigir_acepta_sinteticos(self):
        guardia.exigir_sintetico({"rut": guardia.rut_sintetico(7), "n": 3, "x": None})


if __name__ == "__main__":
    unittest.main()
