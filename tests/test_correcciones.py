"""Cifra de correcciones del delegado, contada desde la cadena de evidencia."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from privacidad.canal import RepositorioCasos
from privacidad.canal.__main__ import main
from privacidad.canal.correcciones import medir_correcciones
from privacidad.motor import HechosIncidente

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    HECHOS_INCIDENTE,
    ClienteCaido,
    ClienteFalso,
    crear_canal,
)
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

MUNI = "municipalidad-piloto"
ROBLES = "comercial-los-robles"
CAMPOS = set(HechosIncidente.model_fields)


def hechos(**cambios) -> HechosIncidente:
    base = {k: v for k, v in HECHOS_CIBERATAQUE.items() if k in CAMPOS}
    return HechosIncidente(**(base | cambios))


class TestMedir(unittest.TestCase):
    def setUp(self):
        self.canal, _, _ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE))

    def cifra(self, org=MUNI):
        _, propias = self.canal.evidencia_de_organizacion(org)
        return medir_correcciones(propias)

    def test_sin_correcciones(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.validar(MUNI, caso.id, por="d")
        c = self.cifra()
        self.assertEqual((c.incidentes_leidos, c.corregidos), (1, 0))
        self.assertEqual((c.validados, c.validados_sin_correccion), (1, 1))

    def test_correccion_por_error_de_la_ia_que_cambia_un_deber(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.corregir_hechos(
            MUNI, caso.id, hechos(ciberincidente="no"), motivo="error_ia", por="d"
        )
        self.canal.validar(MUNI, caso.id, por="d")
        c = self.cifra()
        self.assertEqual(c.corregidos, 1)
        self.assertEqual(c.por_error_ia, 1)
        self.assertEqual(c.campos["ciberincidente"], 1)
        self.assertEqual(c.cambiaron_deber, 1)  # sin ciberincidente no hay reporte a la ANCI
        self.assertEqual((c.validados, c.validados_sin_correccion), (1, 0))

    def test_informacion_nueva_no_es_error_de_la_ia(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.corregir_hechos(
            MUNI, caso.id, hechos(titulares_aprox=40), motivo="informacion_nueva", por="d"
        )
        c = self.cifra()
        self.assertEqual(c.corregidos, 1)
        self.assertEqual(c.por_error_ia, 0)
        self.assertEqual(c.por_motivo["informacion_nueva"], 1)

    def test_volver_a_lo_que_dijo_la_ia_no_cuenta(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.corregir_hechos(
            MUNI, caso.id, hechos(ciberincidente="no"), motivo="otro", por="d"
        )
        self.canal.corregir_hechos(MUNI, caso.id, hechos(), motivo="otro", por="d")
        c = self.cifra()
        self.assertEqual(c.corregidos, 0)
        self.assertEqual(c.cambiaron_deber, 0)

    def test_una_validacion_anulada_no_cuenta(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.validar(MUNI, caso.id, por="d")
        self.canal.corregir_hechos(
            MUNI, caso.id, hechos(ciberincidente="no"), motivo="error_ia", por="d"
        )
        self.assertEqual(self.cifra().validados, 0)

    def test_si_la_ia_no_leyo_se_cuenta_aparte(self):
        canal, _, _ = crear_canal(ClienteCaido())
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        canal.corregir_hechos(MUNI, caso.id, hechos(), motivo="otro", por="d")
        _, propias = canal.evidencia_de_organizacion(MUNI)
        c = medir_correcciones(propias)
        self.assertEqual((c.incidentes_leidos, c.corregidos, c.completados_sin_ia), (0, 0, 1))

    def test_cada_organizacion_ve_lo_suyo(self):
        caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.canal.corregir_hechos(
            MUNI, caso.id, hechos(ciberincidente="no"), motivo="error_ia", por="d"
        )
        self.assertEqual(self.cifra(ROBLES).incidentes_leidos, 0)


class TestPanelYComando(unittest.TestCase):
    def test_la_pantalla_de_evidencia_la_muestra(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(MUNI, "Mandaron una planilla al proveedor equivocado.")
        canal.corregir_hechos(
            MUNI,
            caso.id,
            hechos(ciberincidente="no", titulares_aprox=3),
            motivo="error_ia",
            por="d",
        )
        nav = Navegador(app)
        entrar(nav)
        html = nav.pedir("GET", "/panel/evidencia").html
        self.assertIn("Cuánto corriges a la IA", html)
        self.assertIn("1 porque la IA leyó mal el mensaje", html)

    def test_comando(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = RepositorioCasos(Path(tmp))
            canal, _, _ = crear_canal(
                ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), repositorio=repo
            )
            caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
            canal.corregir_hechos(
                MUNI, caso.id, hechos(ciberincidente="no"), motivo="error_ia", por="d"
            )
            repo.cerrar()
            salida, errores = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
                codigo = main(["correcciones", "--carpeta", tmp, "--org", MUNI])
            self.assertEqual(codigo, 0)
            datos = json.loads(salida.getvalue())
            self.assertEqual(datos["corregidos_por_error_de_la_ia"], 1)
            self.assertEqual(datos["correcciones_que_cambiaron_un_deber"], 1)


if __name__ == "__main__":
    unittest.main()
