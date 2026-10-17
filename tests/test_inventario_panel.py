"""Inventario desde el panel: subir planilla, registro sin valores, versión mínima y relación con
los casos."""

import re
import unittest
from datetime import datetime

import pandas as pd

from privacidad.canal.modelos import ZONA_CHILE
from privacidad.canal.repositorio import RepositorioCasos
from privacidad.guardia import DatosNoSinteticosError
from privacidad.inventario import servicio

from .canal_apoyo import HECHOS_INCIDENTE, ClienteFalso
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

ROBLES = "comercial-los-robles"
AHORA = datetime(2026, 10, 17, 12, tzinfo=ZONA_CHILE)


def procesar(nombre, contenido=None, descripcion="", ahora=AHORA):
    contenido = contenido if contenido is not None else (servicio.DATOS_DEMO / nombre).read_bytes()
    return servicio.procesar(
        nombre, contenido, descripcion, id_organizacion=ROBLES, por="x", cliente=None, ahora=ahora
    )


class TestProcesar(unittest.TestCase):
    def test_ejemplo_usa_la_respuesta_grabada_y_recalcula_alertas(self):
        r = procesar("paseo_fin_de_anio.xlsx")
        self.assertEqual(r.origen_ia, "grabada")
        self.assertEqual(r.resumen.filas, 84)
        self.assertGreater(r.resumen.menores_de_14, 0)
        textos = " ".join(a.mensaje for a in r.actividad.alertas)
        self.assertNotIn("titular", textos)
        self.assertEqual(r.actividad.costo_ia_usd, 0.0)

    def test_ejemplo_se_calcula_a_su_fecha_y_no_cambia_con_los_dias(self):
        # Entre el 10 y el 28 de octubre un niño cumple 18: si las edades se calcularan a hoy,
        # los conteos dejarían de calzar con el texto grabado de la IA.
        for dia in (10, 17, 28):
            r = procesar(
                "paseo_fin_de_anio.xlsx", ahora=datetime(2026, 10, dia, 9, tzinfo=ZONA_CHILE)
            )
            self.assertEqual(r.edades_al, servicio.FECHA_EJEMPLOS)
            self.assertEqual((r.resumen.menores_de_14, r.resumen.menores_de_18), (61, 84))
            self.assertIn("84 menores de 18", r.actividad.tipo_datos.nota)

    def test_planilla_subida_se_calcula_a_hoy(self):
        ruta = servicio.DATOS_DEMO / "paseo_fin_de_anio.xlsx"
        df = pd.read_excel(ruta, dtype=str).fillna("")
        contenido = df.to_csv(index=False).encode()  # mismo contenido, otro archivo: sin grabada
        r = servicio.procesar(
            "paseo.csv",
            contenido,
            "Paseo de fin de año con los hijos de los trabajadores.",
            id_organizacion="comercial-los-robles",
            por="delegado",
            cliente=None,
            ahora=datetime(2026, 10, 28, 9, tzinfo=ZONA_CHILE),
        )
        self.assertEqual(r.edades_al.isoformat(), "2026-10-28")
        self.assertEqual(r.resumen.menores_de_18, 82)

    def test_no_guarda_valores_de_la_planilla(self):
        r = procesar("paseo_fin_de_anio.xlsx")
        df = pd.read_excel(servicio.DATOS_DEMO / "paseo_fin_de_anio.xlsx", dtype=str)
        volcado = r.model_dump_json()
        for valor in df.iloc[0].tolist():
            if len(str(valor)) >= 6:  # nombres, RUT, correos, teléfonos de la primera fila
                self.assertNotIn(str(valor), volcado)

    def test_otra_planilla_sin_ia_queda_pendiente_y_pide_descripcion(self):
        df = pd.DataFrame({"Nombre": ["Persona Uno", "Persona Dos"], "Comuna": ["Uno", "Dos"]})
        contenido = df.to_csv(index=False).encode()
        with self.assertRaises(servicio.PlanillaInvalida):
            procesar("otra.csv", contenido)
        r = procesar("otra.csv", contenido, "Lista de asistentes a una charla.")
        self.assertEqual(r.origen_ia, "sin_ia")
        self.assertEqual(r.actividad.fines.origen, "pendiente")

    def test_rechazos(self):
        with self.assertRaises(servicio.PlanillaInvalida):
            procesar("x.pdf", b"%PDF")
        with self.assertRaises(servicio.PlanillaInvalida):
            procesar("x.csv", b"")
        with self.assertRaises(servicio.PlanillaInvalida):
            procesar("x.csv", b"a" * (servicio.TAMANO_MAXIMO + 1))
        real = pd.DataFrame({"RUT": ["12.345.678-5"], "Correo": ["persona@gmail.com"]})
        with self.assertRaises(DatosNoSinteticosError):
            procesar("real.csv", real.to_csv(index=False).encode(), "Prueba")


class TestVersionMinima(unittest.TestCase):
    def test_clientes_sin_columnas_innecesarias_ya_no_exige_avisar_a_cada_persona(self):
        v = servicio.version_minima(procesar("clientes_marketing.csv"), "empresa_privada")
        self.assertTrue(v.quitadas)
        self.assertEqual(v.antes.si_se_filtra.aviso_titulares.decision, "si")
        self.assertEqual(v.despues.si_se_filtra.aviso_titulares.decision, "no")
        self.assertLess(v.despues.datos_personales, v.antes.datos_personales)

    def test_paseo_quita_el_rut_de_los_ninos_pero_los_deberes_siguen(self):
        v = servicio.version_minima(procesar("paseo_fin_de_anio.xlsx"), "empresa_privada")
        self.assertIn("RUT hijo/a", [n for n, _ in v.quitadas])
        self.assertEqual(v.despues.identificadores, [])
        self.assertEqual(v.despues.si_se_filtra.aviso_titulares.decision, "si")


class TestPlanillasMencionadas(unittest.TestCase):
    def test_solo_por_la_palabra_principal(self):
        registros = [procesar(n) for n in servicio.ejemplos()]
        texto = "Envié por error la planilla del paseo con datos de los hijos de los trabajadores."
        self.assertEqual(
            [r.archivo for r in servicio.planillas_mencionadas(texto, registros)],
            ["paseo_fin_de_anio.xlsx"],
        )
        self.assertEqual(servicio.planillas_mencionadas("Se cayó el sistema.", registros), [])


class TestRepositorio(unittest.TestCase):
    def test_guardar_y_listar_por_organizacion(self):
        repo = RepositorioCasos()
        repo.guardar_actividad(procesar("proveedores.csv"))
        self.assertEqual(len(repo.actividades(ROBLES)), 1)
        self.assertEqual(repo.actividades("municipalidad-piloto"), [])


def multipart(campos, archivo):
    limite = "limite123"
    partes = []
    for k, v in campos.items():
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    nombre, contenido = archivo
    partes.append(
        (
            f'--{limite}\r\nContent-Disposition: form-data; name="archivo"; '
            f'filename="{nombre}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + contenido
        + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


class TestPanel(unittest.TestCase):
    def setUp(self):
        self.app, self.canal, _ = crear_panel_de_prueba(
            ClienteFalso(registrar_hechos=HECHOS_INCIDENTE)
        )
        self.nav = Navegador(self.app)
        entrar(self.nav, usuario="delegado-robles")

    def test_ejemplo_desde_el_panel(self):
        csrf = self.nav.pedir("GET", "/panel/inventario").csrf()
        r = self.nav.pedir(
            "POST", "/panel/inventario/ejemplo", {"csrf": csrf, "archivo": "paseo_fin_de_anio.xlsx"}
        )
        self.assertEqual(r.status, 303)
        html = self.nav.pedir("GET", r.cabeceras["location"]).html
        self.assertIn("Versión mínima de la planilla", html)
        self.assertIn("vii. Base legal para usarlos", html)
        self.assertIn("se analizó y se descartó", html)
        lista = self.nav.pedir("GET", "/panel/inventario").html
        self.assertIn("paseo_fin_de_anio.xlsx", lista)
        id_ = re.search(r"/panel/inventario/([\w-]{12})\?", r.cabeceras["location"]).group(1)
        r = self.nav.pedir("POST", f"/panel/inventario/{id_}/validar", {"csrf": csrf})
        self.assertIn(
            "Registro validado por delegado-robles",
            self.nav.pedir("GET", r.cabeceras["location"]).html,
        )

    def test_subir_archivo(self):
        csrf = self.nav.pedir("GET", "/panel/inventario").csrf()
        cuerpo, tipo = multipart(
            {"csrf": csrf, "descripcion": ""},
            (
                "clientes_marketing.csv",
                (servicio.DATOS_DEMO / "clientes_marketing.csv").read_bytes(),
            ),
        )
        r = self.nav.pedir_crudo("POST", "/panel/inventario/subir", cuerpo, tipo)
        self.assertEqual(r.status, 303)

    def test_subir_sin_csrf_se_rechaza(self):
        cuerpo, tipo = multipart({"csrf": "malo"}, ("x.csv", b"a,b\n1,2\n"))
        self.assertEqual(
            self.nav.pedir_crudo("POST", "/panel/inventario/subir", cuerpo, tipo).status, 403
        )

    def test_registros_de_otra_organizacion_no_se_ven(self):
        registro = procesar("proveedores.csv")
        registro.id_organizacion = "municipalidad-piloto"
        self.canal._repo.guardar_actividad(registro)
        self.assertEqual(self.nav.pedir("GET", f"/panel/inventario/{registro.id}").status, 404)

    def test_descargar_ejemplo(self):
        r = self.nav.pedir("GET", "/panel/inventario/ejemplo/proveedores.csv")
        self.assertEqual(r.status, 200)
        self.assertIn("attachment", r.cabeceras["content-disposition"])
        self.assertEqual(
            self.nav.pedir("GET", "/panel/inventario/ejemplo/..%2Fsecreto").status, 404
        )


if __name__ == "__main__":
    unittest.main()
