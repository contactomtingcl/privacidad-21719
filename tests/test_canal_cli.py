import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet

from privacidad.canal import RepositorioCasos, enlaces, reservado
from privacidad.canal.__main__ import main

from .canal_apoyo import HECHOS_INCIDENTE, ClienteFalso, crear_canal

URL = "https://canal.ejemplo.cl"


def ejecutar(*argv, entorno=None):
    salida, error = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, entorno or {}, clear=True),
        contextlib.redirect_stdout(salida),
        contextlib.redirect_stderr(error),
    ):
        codigo = main(list(argv))
    return codigo, salida.getvalue(), error.getvalue()


class TestSecretos(unittest.TestCase):
    def test_secreto_va_a_un_archivo_y_no_a_la_pantalla(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "secreto.key"
            codigo, salida, _ = ejecutar("secreto", "--archivo", str(ruta))
            valor = ruta.read_text().strip()
        self.assertEqual(codigo, 0)
        self.assertNotIn(valor, salida)
        self.assertIn(enlaces.VARIABLE_SECRETO, salida)

    def test_llave_va_a_un_archivo_y_no_a_la_pantalla(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "llave.key"
            codigo, salida, _ = ejecutar("llave", "--archivo", str(ruta))
            valor = ruta.read_text().strip()
            self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
        self.assertEqual(codigo, 0)
        self.assertNotIn(valor, salida)
        self.assertIn(reservado.VARIABLE_LLAVE_ARCHIVO, salida)

    def test_no_sobrescribe(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "llave.key"
            ejecutar("llave", "--archivo", str(ruta))
            antes = ruta.read_text()
            codigo, _, error = ejecutar("llave", "--archivo", str(ruta))
            self.assertEqual(ruta.read_text(), antes)
        self.assertEqual(codigo, 2)
        self.assertIn("ya existe", error)


class TestEnlace(unittest.TestCase):
    ENTORNO = {enlaces.VARIABLE_SECRETO: "secreto-de-prueba-que-supera-los-32-caracteres"}

    def test_sin_secreto(self):
        codigo, _, error = ejecutar("enlace", "--org", "comercial-los-robles")
        self.assertEqual(codigo, 2)
        self.assertIn("PRIVACIDAD_SECRETO_ENLACES", error)

    def test_organizacion_desconocida(self):
        codigo, _, error = ejecutar("enlace", "--org", "nada", entorno=self.ENTORNO)
        self.assertEqual(codigo, 2)
        self.assertIn("comercial-los-robles", error)

    def test_escribe_el_svg_y_muestra_el_enlace(self):
        falso = mock.MagicMock()
        falso.make_qr.return_value.save.side_effect = lambda salida, **kw: salida.write(b"<svg/>")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("sys.modules", {"segno": falso}):
            destino = Path(tmp) / "qr.svg"
            codigo, salida, _ = ejecutar(
                "enlace",
                "--org",
                "municipalidad-piloto",
                "--base-url",
                URL,
                "--salida",
                str(destino),
                entorno=self.ENTORNO,
            )
            self.assertEqual(destino.read_text(), "<svg/>")
        self.assertEqual(codigo, 0)
        self.assertIn(f"{URL}/canal/municipalidad-piloto/", salida)

    def test_sin_segno_dice_que_hacer(self):
        with mock.patch.dict("sys.modules", {"segno": None}):
            codigo, _, error = ejecutar(
                "enlace", "--org", "municipalidad-piloto", "--base-url", URL, entorno=self.ENTORNO
            )
        self.assertEqual(codigo, 2)
        self.assertIn("segno", error)


class TestServir(unittest.TestCase):
    ENTORNO = TestEnlace.ENTORNO

    def test_arma_el_canal_y_levanta_el_servidor_sin_registro_de_accesos(self):
        with mock.patch("uvicorn.run") as correr:
            codigo, salida, _ = ejecutar("servir", "--puerto", "9999", entorno=self.ENTORNO)
        self.assertEqual(codigo, 0)
        kwargs = correr.call_args.kwargs
        self.assertFalse(kwargs["access_log"])
        self.assertEqual((kwargs["host"], kwargs["port"]), ("127.0.0.1", 9999))
        self.assertIn("IA: apagada", salida)
        self.assertIn("Modo reservado: no disponible", salida)
        self.assertIn("http://127.0.0.1:9999/canal/comercial-los-robles/", salida)

    def test_con_llave_el_modo_reservado_se_activa_y_la_llave_no_se_imprime(self):
        llave = Fernet.generate_key().decode()
        with mock.patch("uvicorn.run"):
            _, salida, _ = ejecutar(
                "servir", entorno=self.ENTORNO | {reservado.VARIABLE_LLAVE: llave}
            )
        self.assertIn("Modo reservado: activo", salida)
        self.assertNotIn(llave, salida)

    def test_llave_mal_formada(self):
        codigo, _, error = ejecutar(
            "servir", entorno=self.ENTORNO | {reservado.VARIABLE_LLAVE: "mala"}
        )
        self.assertEqual(codigo, 2)
        self.assertNotIn("mala", error.replace("llave", ""))  # no repite el valor

    def test_sin_secreto_no_arranca(self):
        with mock.patch("uvicorn.run") as correr:
            codigo, _, _ = ejecutar("servir")
        self.assertEqual(codigo, 2)
        correr.assert_not_called()


class TestIdentidad(unittest.TestCase):
    def test_el_delegado_abre_la_identidad_con_su_llave(self):
        clave = Fernet.generate_key()
        with tempfile.TemporaryDirectory() as tmp:
            repo = RepositorioCasos(Path(tmp))
            canal, *_ = crear_canal(
                ClienteFalso(registrar_hechos=HECHOS_INCIDENTE),
                repositorio=repo,
                llaves=reservado.cargar_llaves(clave),
            )
            caso = canal.recibir_incidente(
                "comercial-los-robles",
                "Vi una filtración de datos.",
                reservado=True,
                nombre="Persona Ficticia Uno",
            )
            repo.cerrar()
            archivo = Path(tmp) / "llave.key"
            archivo.write_bytes(clave)
            codigo, salida, _ = ejecutar(
                "identidad", "--carpeta", tmp, "--caso", caso.id, "--llave", str(archivo)
            )
            self.assertEqual(codigo, 0)
            self.assertIn("Persona Ficticia Uno", salida)
            # con una llave equivocada no se abre
            otra = Path(tmp) / "otra.key"
            otra.write_bytes(Fernet.generate_key())
            codigo, _, error = ejecutar(
                "identidad", "--carpeta", tmp, "--caso", caso.id, "--llave", str(otra)
            )
            self.assertEqual(codigo, 2)
            self.assertIn("llave equivocada", error)
            # sin llave tampoco
            codigo, _, error = ejecutar("identidad", "--carpeta", tmp, "--caso", caso.id)
            self.assertEqual(codigo, 2)
            self.assertIn("Falta la llave", error)

    def test_caso_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            codigo, _, error = ejecutar(
                "identidad", "--carpeta", tmp, "--caso", "codigo-inexistente-1"
            )
        self.assertEqual(codigo, 2)
        self.assertIn("no existe", error)
