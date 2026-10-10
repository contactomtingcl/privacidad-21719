import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from privacidad.canal import enlaces

SECRETO = b"secreto-de-prueba-que-supera-los-32-caracteres"
OTRO = b"otro-secreto-distinto-que-supera-los-32-caracteres"


class TestFirma(unittest.TestCase):
    def test_es_estable_y_valida(self):
        f1 = enlaces.firma_canal("comercial-los-robles", 1, SECRETO)
        f2 = enlaces.firma_canal("comercial-los-robles", 1, SECRETO)
        self.assertEqual(f1, f2)
        self.assertTrue(enlaces.firma_valida("comercial-los-robles", 1, f1, SECRETO))

    def test_solo_caracteres_seguros_para_una_direccion(self):
        firma = enlaces.firma_canal("comercial-los-robles", 1, SECRETO)
        self.assertRegex(firma, r"^[A-Za-z0-9_-]{40,50}$")

    def test_firma_alterada_no_vale(self):
        firma = enlaces.firma_canal("comercial-los-robles", 1, SECRETO)
        cambio = "b" if firma[-1] != "b" else "c"
        self.assertFalse(
            enlaces.firma_valida("comercial-los-robles", 1, firma[:-1] + cambio, SECRETO)
        )
        self.assertFalse(enlaces.firma_valida("comercial-los-robles", 1, "", SECRETO))
        self.assertFalse(enlaces.firma_valida("comercial-los-robles", 1, "ñandú", SECRETO))

    def test_no_sirve_para_otra_organizacion_otra_version_u_otro_secreto(self):
        firma = enlaces.firma_canal("comercial-los-robles", 1, SECRETO)
        self.assertFalse(enlaces.firma_valida("municipalidad-piloto", 1, firma, SECRETO))
        self.assertFalse(enlaces.firma_valida("comercial-los-robles", 2, firma, SECRETO))
        self.assertFalse(enlaces.firma_valida("comercial-los-robles", 1, firma, OTRO))

    def test_subir_la_version_invalida_el_enlace_anterior(self):
        vieja = enlaces.firma_canal("municipalidad-piloto", 1, SECRETO)
        nueva = enlaces.firma_canal("municipalidad-piloto", 2, SECRETO)
        self.assertNotEqual(vieja, nueva)
        self.assertFalse(enlaces.firma_valida("municipalidad-piloto", 2, vieja, SECRETO))

    def test_identificador_invalido_se_rechaza(self):
        with self.assertRaises(ValueError):
            enlaces.firma_canal("../etc", 1, SECRETO)
        self.assertFalse(enlaces.firma_valida("../etc", 1, "x", SECRETO))

    def test_secreto_corto_se_rechaza(self):
        with self.assertRaises(ValueError):
            enlaces.firma_canal("comercial-los-robles", 1, b"corto")


class TestEnlace(unittest.TestCase):
    def test_arma_la_direccion(self):
        url = enlaces.enlace_canal("https://canal.ejemplo.cl/", "comercial-los-robles", 1, SECRETO)
        firma = enlaces.firma_canal("comercial-los-robles", 1, SECRETO)
        self.assertEqual(url, f"https://canal.ejemplo.cl/canal/comercial-los-robles/{firma}")

    def test_http_solo_en_local(self):
        enlaces.enlace_canal("http://127.0.0.1:8080", "comercial-los-robles", 1, SECRETO)
        with self.assertRaises(ValueError):
            enlaces.enlace_canal("http://canal.ejemplo.cl", "comercial-los-robles", 1, SECRETO)

    def test_direccion_base_invalida(self):
        for base in ("https://", "https://x.cl/?a=1", "ftp://x.cl"):
            with self.assertRaises(ValueError):
                enlaces.enlace_canal(base, "comercial-los-robles", 1, SECRETO)


class TestSecreto(unittest.TestCase):
    def test_se_lee_del_entorno(self):
        with mock.patch.dict(os.environ, {enlaces.VARIABLE_SECRETO: SECRETO.decode()}):
            self.assertEqual(enlaces.secreto_desde_entorno(), SECRETO)

    def test_si_falta_el_mensaje_dice_como_crearlo(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            self.assertRaises(RuntimeError) as ctx,
        ):
            enlaces.secreto_desde_entorno()
        self.assertIn("python -m privacidad.canal secreto", str(ctx.exception))

    def test_secreto_corto_en_el_entorno_se_rechaza(self):
        with (
            mock.patch.dict(os.environ, {enlaces.VARIABLE_SECRETO: "corto"}),
            self.assertRaises(RuntimeError),
        ):
            enlaces.secreto_desde_entorno()

    def test_generado_cumple_el_minimo(self):
        self.assertGreaterEqual(len(enlaces.generar_secreto()), enlaces.LARGO_MINIMO_SECRETO)
        self.assertNotEqual(enlaces.generar_secreto(), enlaces.generar_secreto())

    def test_archivo_solo_para_su_dueno_y_sin_sobrescribir(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "s" / "secreto.key"
            enlaces.guardar_secreto(ruta)
            self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
            self.assertGreaterEqual(len(ruta.read_text().strip()), enlaces.LARGO_MINIMO_SECRETO)
            with self.assertRaises(FileExistsError):
                enlaces.guardar_secreto(ruta)
