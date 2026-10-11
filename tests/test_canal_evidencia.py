import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from privacidad.canal import RepositorioCasos
from privacidad.canal.__main__ import main
from privacidad.canal.evidencia import GENESIS, ErrorEvidencia, calcular_huella
from privacidad.canal.modelos import ZONA_CHILE, Caso
from privacidad.canal.repositorio import NOMBRE_ARCHIVO

from .canal_apoyo import (
    HECHOS_INCIDENTE,
    SOLICITUD_AMBIGUA,
    ClienteFalso,
    crear_canal,
)

MOMENTO = datetime(2026, 12, 2, 10, 0, tzinfo=ZONA_CHILE)


def caso(id_caso="caso-0001-abc", eventos=("recibido",)) -> Caso:
    c = Caso(
        id=id_caso,
        id_organizacion="comercial-los-robles",
        tipo="incidente",
        ingreso=MOMENTO,
        texto="Se envió una planilla por error.",
        estado="requiere_revision",
    )
    for tipo in eventos:
        c.registrar(tipo, MOMENTO, tipo_reporte="incidente")
    return c


def abrir_directo(carpeta: Path) -> sqlite3.Connection:
    """Simula a alguien que abre el archivo por fuera de la aplicación."""
    return sqlite3.connect(carpeta / NOMBRE_ARCHIVO)


class TestCadena(unittest.TestCase):
    def test_cada_evento_queda_encadenado_al_anterior(self):
        repo = RepositorioCasos()
        repo.guardar(caso("caso-uno-0001", ("recibido", "interpretado")))
        repo.guardar(caso("caso-dos-0002", ("recibido",)))
        anotaciones = repo.evidencia()
        self.assertEqual([a.n for a in anotaciones], [1, 2, 3])
        self.assertEqual(anotaciones[0].anterior, GENESIS)
        self.assertEqual(anotaciones[1].anterior, anotaciones[0].huella)
        self.assertEqual(anotaciones[2].anterior, anotaciones[1].huella)
        self.assertEqual([a.n for a in repo.evidencia("caso-dos-0002")], [3])
        v = repo.verificar_evidencia()
        self.assertTrue(v.integra)
        self.assertEqual(v.anotaciones, 3)
        self.assertEqual(v.cabeza, anotaciones[-1].huella)

    def test_guardar_de_nuevo_solo_anota_lo_nuevo(self):
        repo = RepositorioCasos()
        c = caso()
        repo.guardar(c)
        repo.guardar(c)
        c.registrar("interpretado", MOMENTO)
        repo.guardar(c)
        self.assertEqual([a.tipo for a in repo.evidencia()], ["recibido", "interpretado"])

    def test_la_huella_es_estable(self):
        # Misma entrada, misma huella, en cualquier computador (JSON canónico + SHA-256).
        # Valor comprobado también con `sha256sum` sobre el mismo JSON.
        huella = calcular_huella(
            n=1,
            id_caso="caso-0001-abc",
            id_organizacion="comercial-los-robles",
            tipo="recibido",
            momento="2026-12-02T10:00:00-03:00",
            detalle={"b": 1, "a": "ñ"},
            anterior=GENESIS,
        )
        self.assertEqual(huella, "40102b8ceecc7a9b8179cdddfc97f148915a756dde65975cf64b92e63eb07043")


class TestLaHistoriaNoSeReescribe(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioCasos()
        self.caso = caso(eventos=("recibido", "interpretado"))
        self.repo.guardar(self.caso)

    def test_quitar_un_evento_se_rechaza_y_no_cambia_nada(self):
        self.caso.eventos.pop()
        self.caso.estado = "interpretado"
        with self.assertRaises(ErrorEvidencia):
            self.repo.guardar(self.caso)
        self.assertEqual(self.repo.obtener(self.caso.id).estado, "requiere_revision")
        self.assertEqual(len(self.repo.obtener(self.caso.id).eventos), 2)

    def test_cambiar_un_evento_se_rechaza(self):
        self.caso.eventos[0].detalle["tipo_reporte"] = "otro"
        with self.assertRaises(ErrorEvidencia):
            self.repo.guardar(self.caso)

    def test_datos_personales_en_un_evento_se_rechazan_sin_guardar(self):
        self.caso.registrar("nota", MOMENTO, contacto="persona.uno@example.com")
        with self.assertRaises(ErrorEvidencia) as error:
            self.repo.guardar(self.caso)
        self.assertNotIn("persona.uno", str(error.exception))
        self.assertEqual(len(self.repo.evidencia()), 2)
        self.assertEqual(len(self.repo.obtener(self.caso.id).eventos), 2)

    def test_la_base_rechaza_cambios_y_borrados(self):
        con = self.repo._con
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("UPDATE evidencia SET tipo = 'otro' WHERE n = 1")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM evidencia WHERE n = 1")
        self.assertTrue(self.repo.verificar_evidencia().integra)


class TestAlteracionesPorFuera(unittest.TestCase):
    """Alguien con acceso al archivo quita las protecciones y altera la evidencia."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.tmp.name)
        repo = RepositorioCasos(self.carpeta)
        repo.guardar(caso("caso-uno-0001", ("recibido", "interpretado", "enrutado")))
        repo.guardar(caso("caso-dos-0002", ("recibido",)))
        self.cabeza = repo.verificar_evidencia().cabeza
        repo.cerrar()
        self.con = abrir_directo(self.carpeta)
        self.con.execute("DROP TRIGGER evidencia_sin_cambios")
        self.con.execute("DROP TRIGGER evidencia_sin_borrado")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def verificar(self, cabeza=None):
        self.con.commit()
        repo = RepositorioCasos(self.carpeta)
        try:
            return repo.verificar_evidencia(cabeza)
        finally:
            repo.cerrar()

    def test_sin_tocar_nada_esta_integra(self):
        self.assertTrue(self.verificar(self.cabeza).integra)

    def test_cambiar_una_anotacion(self):
        self.con.execute("UPDATE evidencia SET tipo = 'cerrado' WHERE n = 2")
        v = self.verificar()
        self.assertFalse(v.integra)
        self.assertTrue(any("anotación 2 fue modificada" in p for p in v.problemas))

    def test_borrar_una_anotacion_del_medio(self):
        self.con.execute("DELETE FROM evidencia WHERE n = 2")
        v = self.verificar()
        self.assertFalse(v.integra)
        self.assertTrue(any("Falta la anotación 2" in p for p in v.problemas))

    def test_borrar_el_final_solo_se_detecta_con_la_huella_guardada(self):
        self.con.execute("DELETE FROM evidencia WHERE n = 4")
        # Límite declarado: sin la huella final guardada aparte, la cadena corta se ve coherente
        # (solo se nota que el caso perdió su evento).
        v = self.verificar()
        self.assertFalse(v.integra)
        self.assertTrue(any("caso-dos-0002" in p for p in v.problemas))
        self.assertFalse(self.verificar(self.cabeza).integra)

    def test_borrar_un_caso_completo_y_su_final(self):
        self.con.execute("DELETE FROM evidencia WHERE n = 4")
        self.con.execute("DELETE FROM casos WHERE id = 'caso-dos-0002'")
        self.assertTrue(self.verificar().integra)  # sin huella guardada, no se nota
        v = self.verificar(self.cabeza)
        self.assertFalse(v.integra)
        self.assertTrue(any("huella guardada aparte" in p for p in v.problemas))

    def test_editar_la_historia_dentro_del_caso(self):
        fila = self.con.execute("SELECT datos FROM casos WHERE id = 'caso-uno-0001'").fetchone()
        alterado = fila[0].replace('"enrutado"', '"cerrado"')
        self.con.execute("UPDATE casos SET datos = ? WHERE id = 'caso-uno-0001'", (alterado,))
        v = self.verificar()
        self.assertFalse(v.integra)
        self.assertTrue(any("caso-uno-0001 no coincide" in p for p in v.problemas))


class TestFlujoCompleto(unittest.TestCase):
    def test_todo_lo_que_pasa_en_el_canal_queda_en_la_evidencia(self):
        ia = ClienteFalso(
            interpretar_solicitud=SOLICITUD_AMBIGUA, registrar_hechos=HECHOS_INCIDENTE
        )
        repo = RepositorioCasos()
        canal, *_ = crear_canal(ia, repositorio=repo)
        s = canal.recibir_solicitud(
            "comercial-los-robles",
            "Ya no quiero sus correos de ofertas.",
            nombre="Persona Ficticia Uno",
            contacto="persona.uno@example.com",
        )
        s = canal.responder_confirmacion(s.id, derechos=["oposicion"])
        i = canal.recibir_incidente(
            "comercial-los-robles",
            "Envié la planilla del paseo a un proveedor por error.",
            reservado=True,
            nombre="Persona Ficticia Dos",
        )
        v = repo.verificar_evidencia()
        self.assertTrue(v.integra)
        self.assertEqual(v.anotaciones, len(s.eventos) + len(i.eventos))
        tipos = [a.tipo for a in repo.evidencia(s.id)]
        self.assertEqual(
            tipos,
            [
                "recibido",
                "interpretado",
                "confirmacion_solicitada",
                "enrutado",
                "confirmacion_respondida",
            ],
        )
        volcado = "".join(a.model_dump_json() for a in repo.evidencia())
        for privado in ("Persona Ficticia", "persona.uno", "planilla del paseo", "ofertas"):
            self.assertNotIn(privado, volcado)


class TestComando(unittest.TestCase):
    def ejecutar(self, *argv):
        salida = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stdout(salida),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            codigo = main(list(argv))
        return codigo, salida.getvalue()

    def test_revisa_la_cadena_y_muestra_un_caso(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = RepositorioCasos(Path(tmp))
            repo.guardar(caso())
            cabeza = repo.verificar_evidencia().cabeza
            repo.cerrar()
            codigo, salida = self.ejecutar("evidencia", "--carpeta", tmp)
            self.assertEqual(codigo, 0)
            self.assertIn("Cadena íntegra: 1 anotaciones", salida)
            self.assertIn(cabeza, salida)
            codigo, salida = self.ejecutar(
                "evidencia", "--carpeta", tmp, "--caso", "caso-0001-abc", "--cabeza", cabeza
            )
            self.assertEqual(codigo, 0)
            self.assertIn('"tipo":"recibido"', salida)

    def test_alteracion_devuelve_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = RepositorioCasos(Path(tmp))
            repo.guardar(caso())
            repo.cerrar()
            con = abrir_directo(Path(tmp))
            con.execute("DROP TRIGGER evidencia_sin_cambios")
            con.execute("UPDATE evidencia SET tipo = 'cerrado'")
            con.commit()
            con.close()
            codigo, salida = self.ejecutar("evidencia", "--carpeta", tmp)
        self.assertEqual(codigo, 1)
        self.assertIn("ATENCIÓN", salida)

    def test_carpeta_sin_casos(self):
        with tempfile.TemporaryDirectory() as tmp:
            codigo, _ = self.ejecutar("evidencia", "--carpeta", tmp)
            self.assertFalse((Path(tmp) / NOMBRE_ARCHIVO).exists())
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
