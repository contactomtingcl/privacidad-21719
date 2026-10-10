import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet

from privacidad.canal import reservado

IDENTIDAD = {"nombre": "Persona Ficticia Uno", "contacto": "persona.uno@ejemplo.cl"}
CASO = "caso-de-prueba-1"


def llaves():
    return reservado.cargar_llaves(Fernet.generate_key())


class TestCifrado(unittest.TestCase):
    def test_ida_y_vuelta(self):
        k = llaves()
        sobre = reservado.cifrar_identidad(k, IDENTIDAD, CASO)
        self.assertEqual(reservado.descifrar_identidad(k, sobre, CASO), IDENTIDAD)

    def test_el_texto_cifrado_no_deja_ver_la_identidad(self):
        sobre = reservado.cifrar_identidad(llaves(), IDENTIDAD, CASO)
        self.assertTrue(sobre.startswith(reservado.PREFIJO))
        for dato in IDENTIDAD.values():
            self.assertNotIn(dato, sobre)

    def test_cifrar_dos_veces_da_textos_distintos(self):
        k = llaves()
        self.assertNotEqual(
            reservado.cifrar_identidad(k, IDENTIDAD, CASO),
            reservado.cifrar_identidad(k, IDENTIDAD, CASO),
        )

    def test_el_largo_no_revela_el_largo_del_nombre(self):
        k = llaves()
        corto = reservado.cifrar_identidad(k, {"nombre": "Ana"}, CASO)
        largo = reservado.cifrar_identidad(k, {"nombre": "Ana María de los Ángeles"}, CASO)
        self.assertEqual(len(corto), len(largo))

    def test_con_acentos_y_enes(self):
        k = llaves()
        datos = {"nombre": "Ñandú Peña Ibáñez"}
        sobre = reservado.cifrar_identidad(k, datos, CASO)
        self.assertEqual(reservado.descifrar_identidad(k, sobre, CASO), datos)

    def test_llave_equivocada_falla(self):
        sobre = reservado.cifrar_identidad(llaves(), IDENTIDAD, CASO)
        with self.assertRaises(reservado.IdentidadReservadaError):
            reservado.descifrar_identidad(llaves(), sobre, CASO)

    def test_texto_alterado_falla(self):
        k = llaves()
        sobre = reservado.cifrar_identidad(k, IDENTIDAD, CASO)
        cambio = "A" if sobre[-3] != "A" else "B"
        alterado = sobre[:-3] + cambio + sobre[-2:]
        with self.assertRaises(reservado.IdentidadReservadaError):
            reservado.descifrar_identidad(k, alterado, CASO)

    def test_no_se_puede_pegar_en_otro_caso(self):
        k = llaves()
        sobre = reservado.cifrar_identidad(k, IDENTIDAD, CASO)
        with self.assertRaises(reservado.IdentidadReservadaError):
            reservado.descifrar_identidad(k, sobre, "otro-caso-distinto")

    def test_formato_desconocido(self):
        with self.assertRaises(reservado.IdentidadReservadaError):
            reservado.descifrar_identidad(llaves(), "x9.abc", CASO)


class TestRotacion(unittest.TestCase):
    def test_la_llave_nueva_abre_lo_antiguo(self):
        vieja = Fernet.generate_key()
        nueva = Fernet.generate_key()
        sobre = reservado.cifrar_identidad(reservado.cargar_llaves(vieja), IDENTIDAD, CASO)
        ambas = reservado.cargar_llaves(nueva + b"," + vieja)
        self.assertEqual(reservado.descifrar_identidad(ambas, sobre, CASO), IDENTIDAD)
        # y lo nuevo se cifra con la primera
        sobre2 = reservado.cifrar_identidad(ambas, IDENTIDAD, CASO)
        solo_nueva = reservado.cargar_llaves(nueva)
        self.assertEqual(reservado.descifrar_identidad(solo_nueva, sobre2, CASO), IDENTIDAD)


class TestCargaDeLlaves(unittest.TestCase):
    def test_llave_con_formato_incorrecto(self):
        for valor in ("", "   ", "no-es-una-llave"):
            with self.assertRaises(reservado.IdentidadReservadaError):
                reservado.cargar_llaves(valor)

    def test_archivo_solo_para_su_dueno_y_sin_sobrescribir(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "carpeta" / "llave.key"
            reservado.guardar_llave(ruta)
            self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
            reservado.cargar_llaves(ruta.read_text())
            with self.assertRaises(FileExistsError):
                reservado.guardar_llave(ruta)

    def test_sin_configurar_devuelve_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(reservado.llaves_desde_entorno())

    def test_desde_la_variable(self):
        clave = Fernet.generate_key().decode()
        with mock.patch.dict(os.environ, {reservado.VARIABLE_LLAVE: clave}, clear=True):
            self.assertIsNotNone(reservado.llaves_desde_entorno())

    def test_desde_un_archivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "llave.key"
            reservado.guardar_llave(ruta)
            with mock.patch.dict(
                os.environ, {reservado.VARIABLE_LLAVE_ARCHIVO: str(ruta)}, clear=True
            ):
                self.assertIsNotNone(reservado.llaves_desde_entorno())
