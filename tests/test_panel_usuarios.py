import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from privacidad.canal import RepositorioCasos
from privacidad.canal.__main__ import main
from privacidad.panel.demo import MODELO_GRABADO, sembrar
from privacidad.panel.usuarios import ErrorUsuarios, RegistroUsuarios, nombre_valido

from .canal_apoyo import crear_canal
from .panel_apoyo import COSTO_PRUEBA

CLAVE = "una-clave-larga-de-prueba"


class TestRegistro(unittest.TestCase):
    def test_verifica_la_contrasena(self):
        registro = RegistroUsuarios(costo=COSTO_PRUEBA)
        registro.crear("delegado-muni", "municipalidad-piloto", CLAVE)
        self.assertEqual(registro.verificar("delegado-muni", CLAVE).usuario, "delegado-muni")
        self.assertIsNone(registro.verificar("delegado-muni", CLAVE + "x"))
        self.assertIsNone(registro.verificar("nadie-aqui", CLAVE))

    def test_el_archivo_no_guarda_la_contrasena_y_solo_lo_lee_su_dueno(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "usuarios.json"
            RegistroUsuarios(ruta, costo=COSTO_PRUEBA).crear("delegado-muni", "org", CLAVE)
            self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
            contenido = ruta.read_text()
            self.assertNotIn(CLAVE, contenido)
            datos = json.loads(contenido)["usuarios"][0]
            self.assertEqual(len(bytes.fromhex(datos["sal"])), 16)
            # Otra instancia lee el mismo archivo y verifica igual
            otro = RegistroUsuarios(ruta, costo=COSTO_PRUEBA)
            self.assertIsNotNone(otro.verificar("delegado-muni", CLAVE))

    def test_dos_usuarios_con_la_misma_contrasena_tienen_huellas_distintas(self):
        registro = RegistroUsuarios(costo=COSTO_PRUEBA)
        a = registro.crear("delegado-uno", "org", CLAVE)
        b = registro.crear("delegado-dos", "org", CLAVE)
        self.assertNotEqual(a.huella, b.huella)

    def test_reglas_de_nombres_y_contrasenas(self):
        registro = RegistroUsuarios(costo=COSTO_PRUEBA)
        for malo in ("ab", "Delegado", "persona@example.com", "con espacio", "-empieza"):
            self.assertFalse(nombre_valido(malo), malo)
            with self.assertRaises(ErrorUsuarios):
                registro.crear(malo, "org", CLAVE)
        with self.assertRaises(ErrorUsuarios):
            registro.crear("delegado-muni", "org", "corta")
        with self.assertRaises(ErrorUsuarios):
            registro.crear("delegado-muni", "org", "delegado-muni-2026!")
        registro.crear("delegado-muni", "org", CLAVE)
        with self.assertRaises(ErrorUsuarios):
            registro.crear("delegado-muni", "org", CLAVE)

    def test_el_costo_por_defecto_es_el_recomendado(self):
        from privacidad.panel.usuarios import COSTO

        self.assertGreaterEqual(COSTO["n"], 2**15)


class TestComandoUsuario(unittest.TestCase):
    def ejecutar(self, *argv, claves):
        salida, error = io.StringIO(), io.StringIO()
        with (
            mock.patch("getpass.getpass", side_effect=claves),
            contextlib.redirect_stdout(salida),
            contextlib.redirect_stderr(error),
        ):
            codigo = main(list(argv))
        return codigo, salida.getvalue(), error.getvalue()

    def test_crea_el_usuario_sin_mostrar_la_contrasena(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = (
                "usuario",
                "--datos",
                tmp,
                "--org",
                "municipalidad-piloto",
                "--usuario",
                "dpd-1",
            )
            codigo, salida, _ = self.ejecutar(*args, claves=[CLAVE, CLAVE])
            self.assertEqual(codigo, 0)
            self.assertNotIn(CLAVE, salida)
            self.assertTrue((Path(tmp) / "usuarios.json").exists())
            codigo, _, error = self.ejecutar(
                *args[:-1], "dpd-2", claves=[CLAVE, "otra-distinta-xx"]
            )
            self.assertEqual(codigo, 2)
            self.assertIn("no coinciden", error)

    def test_organizacion_desconocida(self):
        with tempfile.TemporaryDirectory() as tmp:
            codigo, _, _ = self.ejecutar(
                "usuario", "--datos", tmp, "--org", "no-existe", "--usuario", "dpd-1", claves=[]
            )
        self.assertEqual(codigo, 2)


class TestSembrarDemo(unittest.TestCase):
    def test_carga_los_casos_por_el_canal_real(self):
        repo = RepositorioCasos()
        canal, *_ = crear_canal(None, repositorio=repo)
        n = sembrar(canal)
        casos = repo.listar()
        self.assertEqual(len(casos), n)
        self.assertTrue(repo.verificar_evidencia().integra)
        modelos = {
            e.detalle.get("modelo") for c in casos for e in c.eventos if e.tipo == "interpretado"
        }
        self.assertEqual(modelos, {MODELO_GRABADO})
        self.assertTrue(any(c.validacion for c in casos))
        self.assertTrue(any(c.estado == "requiere_revision" for c in casos))
        self.assertTrue(any(c.identidad_cifrada for c in casos))
        reservado = next(c for c in casos if c.reservado)
        self.assertNotIn("Trabajadora", json.dumps(reservado.model_dump(mode="json")))


if __name__ == "__main__":
    unittest.main()
