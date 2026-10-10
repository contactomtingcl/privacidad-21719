import stat
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from privacidad.canal import RepositorioCasos
from privacidad.canal.modelos import ZONA_CHILE, Caso
from privacidad.canal.repositorio import NOMBRE_ARCHIVO, id_caso_valido


def caso(id_caso="caso-0001-abc", org="comercial-los-robles", dia=2) -> Caso:
    c = Caso(
        id=id_caso,
        id_organizacion=org,
        tipo="solicitud",
        ingreso=datetime(2026, 12, dia, 10, 0, tzinfo=ZONA_CHILE),
        texto="Quiero saber qué datos tienen de mí.",
        estado="requiere_revision",
        identidad={"nombre": "Persona Ficticia", "contacto": "persona@ejemplo.cl"},
    )
    c.registrar("recibido", c.ingreso, tipo="solicitud")
    return c


class TestRepositorio(unittest.TestCase):
    def test_guardar_y_obtener(self):
        repo = RepositorioCasos()
        repo.guardar(caso())
        leido = repo.obtener("caso-0001-abc")
        self.assertEqual(leido, caso())
        self.assertEqual(leido.ingreso.utcoffset(), caso().ingreso.utcoffset())

    def test_inexistente_o_invalido(self):
        repo = RepositorioCasos()
        self.assertIsNone(repo.obtener("caso-que-no-existe"))
        self.assertIsNone(repo.obtener("../../etc/passwd"))
        self.assertIsNone(repo.obtener("'; DROP TABLE casos; --"))

    def test_guardar_dos_veces_reemplaza(self):
        repo = RepositorioCasos()
        c = caso()
        repo.guardar(c)
        c.estado = "interpretado"
        repo.guardar(c)
        self.assertEqual(len(repo.listar()), 1)
        self.assertEqual(repo.obtener(c.id).estado, "interpretado")

    def test_listar_en_orden_de_ingreso(self):
        repo = RepositorioCasos()
        repo.guardar(caso("caso-tercero-03", dia=4))
        repo.guardar(caso("caso-primero-01", dia=2))
        repo.guardar(caso("caso-segundo-02", dia=3))
        self.assertEqual(
            [c.id for c in repo.listar()],
            ["caso-primero-01", "caso-segundo-02", "caso-tercero-03"],
        )

    def test_id_invalido_no_se_guarda(self):
        with self.assertRaises(ValueError):
            RepositorioCasos().guardar(caso("corto"))

    def test_en_carpeta_persiste_y_solo_lo_lee_su_dueno(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp) / "datos"
            repo = RepositorioCasos(carpeta)
            repo.guardar(caso())
            repo.cerrar()
            archivo = carpeta / NOMBRE_ARCHIVO
            self.assertEqual(stat.S_IMODE(archivo.stat().st_mode), 0o600)
            otro = RepositorioCasos(carpeta)
            self.assertEqual(otro.obtener("caso-0001-abc"), caso())
            otro.cerrar()

    def test_validacion_de_ids(self):
        self.assertTrue(id_caso_valido("AbC_123-xyz0"))
        for malo in ("", "abc", "a/b/c/d/e/f/g", "x" * 65, "con espacio 123"):
            self.assertFalse(id_caso_valido(malo), malo)
