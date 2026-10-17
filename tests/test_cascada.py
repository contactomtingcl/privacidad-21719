"""Red de cascada: el proveedor reporta una vez y cada cliente recibe su propio caso."""

import re
import unittest

from privacidad.canal import crear_app
from privacidad.canal.cascada import (
    ProveedorDesconocido,
    ReporteInvalido,
    cargar_proveedores,
    firma_proveedor,
)
from privacidad.canal.enlaces import firma_canal
from privacidad.guardia import DatosNoSinteticosError
from privacidad.panel import vista

from .canal_apoyo import SECRETO, crear_canal
from .panel_apoyo import Navegador, crear_panel_de_prueba

PROV = "remuneraciones-del-sur"
TEXTO = "Un ransomware cifró el servidor del portal de liquidaciones. Restauramos respaldos."


def reportar(canal, servicios=("remuneraciones", "portal"), **kw):
    datos = {
        "servicios": list(servicios),
        "vulneracion": "alteracion",
        "ciberincidente": "si",
        "interrupcion_servicio": True,
    } | kw
    return canal.recibir_reporte_proveedor(PROV, kw.pop("texto", TEXTO), **datos)


class TestCascada(unittest.TestCase):
    def setUp(self):
        self.canal, self.reloj, _ = crear_canal(None)

    def caso(self, resultado, org):
        return self.canal._repo.obtener(resultado.casos[org])

    def test_un_reporte_un_caso_por_cliente_con_su_propio_motor(self):
        r = reportar(self.canal)
        self.assertEqual(
            set(r.casos), {"comercial-los-robles", "municipalidad-piloto", "clinica-del-valle"}
        )
        robles = self.caso(r, "comercial-los-robles")
        muni = self.caso(r, "municipalidad-piloto")
        self.assertEqual(robles.resultado_incidente.reporte_anci.decision, "no")
        self.assertEqual(muni.resultado_incidente.reporte_anci.decision, "si")
        self.assertIn("sensibles", robles.hechos_incidente.categorias_especiales)
        self.assertNotIn("sensibles", muni.hechos_incidente.categorias_especiales)
        self.assertEqual(muni.hechos_incidente.titulares_aprox, 340)
        self.assertEqual(robles.cascada.codigo, muni.cascada.codigo)
        self.assertEqual(muni.ingreso, self.reloj())  # su plazo corre desde que le llega

    def test_solo_los_clientes_del_servicio_afectado(self):
        r = reportar(self.canal, servicios=("portal",))
        self.assertNotIn("municipalidad-piloto", r.casos)

    def test_cada_cliente_ve_solo_su_caso(self):
        r = reportar(self.canal)
        self.assertEqual(len(self.canal.casos_de_organizacion("municipalidad-piloto")), 1)
        caso_robles = r.casos["comercial-los-robles"]
        with self.assertRaises(LookupError):
            self.canal.caso_de_organizacion("municipalidad-piloto", caso_robles)
        muni = self.caso(r, "municipalidad-piloto")
        self.assertNotIn("Nómina de los trabajadores", muni.model_dump_json())

    def test_queda_en_el_registro_de_cada_organizacion(self):
        r = reportar(self.canal)
        for org, id_caso in r.casos.items():
            tipos = [a.tipo for a in self.canal._repo.evidencia(id_caso)]
            self.assertEqual(tipos[:2], ["recibido", "cascada"])
            self.assertTrue(self.canal._repo.verificar_evidencia(id_organizacion=org).integra)

    def test_reglas(self):
        with self.assertRaises(ReporteInvalido):
            reportar(self.canal, servicios=())
        with self.assertRaises(ReporteInvalido):
            reportar(self.canal, servicios=("inventado",))
        with self.assertRaises(DatosNoSinteticosError):
            self.canal.recibir_reporte_proveedor(
                PROV,
                "Se filtró la planilla con el RUT 12.345.678-5 de un trabajador.",
                servicios=["portal"],
                vulneracion="filtracion",
                ciberincidente="no",
                interrupcion_servicio=False,
            )

    def test_firma_propia_y_distinta_de_la_de_una_organizacion(self):
        p = cargar_proveedores()[PROV]
        firma = firma_proveedor(p, SECRETO)
        self.assertEqual(self.canal.proveedor_por_enlace(PROV, firma).id, PROV)
        with self.assertRaises(ProveedorDesconocido):
            self.canal.proveedor_por_enlace(PROV, firma_canal(PROV, 1, SECRETO))
        with self.assertRaises(ProveedorDesconocido):
            self.canal.proveedor_por_enlace("otro", firma)

    def test_vista_del_caso(self):
        r = reportar(self.canal)
        caso = self.caso(r, "municipalidad-piloto")
        pasos = vista.pasos(caso)
        self.assertEqual(pasos[1].texto, "Formulario cerrado, sin IA")
        origenes = {h.origen for h in vista.vista_hechos(caso)}
        self.assertEqual(origenes, {"del reporte del proveedor y tu relación con él"})


class TestWeb(unittest.TestCase):
    def setUp(self):
        self.canal, *_ = crear_canal(None)
        self.app = crear_app(self.canal, "https://canal.ejemplo.cl")
        self.nav = Navegador(self.app)
        self.ruta = "/" + self.canal.enlace_proveedor(PROV, "https://x.cl").split("/", 3)[3]

    def test_formulario_y_envio(self):
        self.assertEqual(self.nav.pedir("GET", self.ruta).status, 200)
        r = self.nav.pedir(
            "POST",
            self.ruta,
            {
                "servicios": ["portal", "remuneraciones"],
                "vulneracion": "alteracion",
                "ciberincidente": "si",
                "interrupcion": "si",
                "texto": TEXTO,
            },
        )
        self.assertEqual(r.status, 200)
        self.assertIn("Llegó a 3 organizaciones clientes", r.html)
        self.assertIn("Usted no ve esos casos", r.html)

    def test_sin_responder_todo(self):
        r = self.nav.pedir("POST", self.ruta, {"servicios": ["portal"], "texto": TEXTO})
        self.assertEqual(r.status, 400)
        self.assertIn("Responda todas las preguntas", r.html)

    def test_firma_falsa(self):
        self.assertEqual(self.nav.pedir("GET", f"/proveedor/{PROV}/falsa").status, 404)


class TestPanel(unittest.TestCase):
    def test_pagina_de_proveedores_en_la_demo(self):
        app, canal, _ = crear_panel_de_prueba(None, demo=True)
        html = Navegador(app).pedir("GET", "/panel/proveedores").html
        self.assertIn("Remuneraciones del Sur SpA", html)
        self.assertIn("Abrir el canal del proveedor", html)
        self.assertTrue(re.search(r'href="https://canal\.ejemplo\.cl/proveedor/', html))


if __name__ == "__main__":
    unittest.main()
