"""Simulador de escenarios: ley vigente frente a la postergación (Boletín 18.623-07)."""

import unittest
from datetime import date

import yaml

from privacidad.corpus import corpus_por_defecto
from privacidad.motor import HechosIncidente
from privacidad.motor.escenarios import (
    RAIZ_NORMAS,
    RAIZ_REGLAS,
    cargar_escenarios,
    comparar,
    extracto,
)
from privacidad.panel import vista

from .canal_apoyo import HECHOS_INCIDENTE, ClienteFalso
from .panel_apoyo import Navegador, crear_panel_de_prueba, entrar

PASEO = HechosIncidente(**vista.EJEMPLOS_SIMULADOR["paseo"][1])
ATAQUE = HechosIncidente(**vista.EJEMPLOS_SIMULADOR["clientes"][1])


def por_deber(sim):
    return {f.deber: f for f in sim.filas}


class TestFuentes(unittest.TestCase):
    def test_citas_verificadas_contra_el_corpus(self):
        corpus = corpus_por_defecto()
        datos = yaml.safe_load((RAIZ_REGLAS / "escenarios.yaml").read_text("utf-8"))
        fuentes = [datos["escenarios"]["vigente"]["fuente"]]
        fuentes += [f for s in datos["sanciones"].values() for f in s["fuentes"]]
        for f in fuentes:
            r = corpus.verificar_cita(f["norma"], str(f["articulo"]), f["fragmento"])
            self.assertTrue(r.existe and r.fragmento_encontrado, f)

    def test_el_proyecto_se_cita_desde_su_extracto_y_no_es_ley(self):
        post = cargar_escenarios()["postergacion"]
        texto = extracto(post)
        self.assertIn(post.fragmento, texto)
        self.assertIn("No es ley", texto)
        self.assertIn("No es ley", post.estado)
        self.assertTrue((RAIZ_NORMAS / post.documento).is_file())
        self.assertEqual(post.vigencia_ley_21719, date(2027, 12, 1))


class TestComparar(unittest.TestCase):
    def test_entre_fechas_cambia_la_exigibilidad_no_la_decision(self):
        vigente, post = comparar(PASEO, "empresa_privada", date(2027, 3, 1))
        a, b = por_deber(vigente), por_deber(post)
        self.assertEqual(a["aviso_agencia"].decision, b["aviso_agencia"].decision)
        self.assertTrue(a["aviso_agencia"].exigible)
        self.assertFalse(b["aviso_agencia"].exigible)
        self.assertEqual(b["aviso_agencia"].consecuencias, [])

    def test_antes_de_ambas_fechas_no_es_exigible_en_ninguno(self):
        for sim in comparar(PASEO, "empresa_privada", date(2026, 11, 1)):
            self.assertFalse(por_deber(sim)["aviso_agencia"].exigible)

    def test_amonestacion_del_primer_anio(self):
        vigente, post = comparar(PASEO, "empresa_privada", date(2028, 1, 15))
        textos = lambda s: [c.texto for c in por_deber(s)["aviso_agencia"].consecuencias]  # noqa: E731
        # 2028-01: fuera del primer año de la ley vigente, dentro del primero de la postergada.
        self.assertFalse(any("amonestación" in t for t in textos(vigente)))
        self.assertTrue(any("amonestación" in t for t in textos(post)))
        vigente, _ = comparar(PASEO, "empresa_privada", date(2027, 3, 1), menor_tamano=True)
        self.assertTrue(any("amonestación" in t for t in textos(vigente)))

    def test_organo_publico_tiene_otra_sancion(self):
        vigente, _ = comparar(PASEO, "organismo_publico", date(2028, 6, 1))
        textos = [c.texto for c in por_deber(vigente)["aviso_agencia"].consecuencias]
        self.assertTrue(any("jefe superior" in t for t in textos))
        self.assertIn("datos sensibles", por_deber(vigente)["aviso_agencia"].nota)

    def test_la_anci_no_depende_del_escenario(self):
        vigente, post = comparar(ATAQUE, "organismo_publico", date(2027, 3, 1))
        self.assertEqual(por_deber(vigente)["reporte_anci"], por_deber(post)["reporte_anci"])
        self.assertTrue(por_deber(vigente)["reporte_anci"].exigible)
        filas = vista.comparar_filas([vigente, post])
        self.assertFalse(next(f for f in filas if f.deber == "reporte_anci").cambia)
        self.assertTrue(next(f for f in filas if f.deber == "aviso_agencia").cambia)


class TestPantalla(unittest.TestCase):
    def test_pagina_y_desde_un_caso(self):
        app, canal, _ = crear_panel_de_prueba(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente("municipalidad-piloto", "Se perdió una planilla.")
        nav = Navegador(app)
        entrar(nav)
        r = nav.pedir("GET", "/panel/simulador")
        self.assertEqual(r.status, 200)
        self.assertIn("Si se aprueba la postergación", r.html)
        self.assertIn("Aún no exigible", r.html)
        r = nav.pedir("GET", f"/panel/simulador?caso={caso.id}&fecha=2027-03-01")
        self.assertIn(f'Los hechos del caso <span class="mono">{caso.id}</span>', r.html)
        self.assertEqual(nav.pedir("GET", "/panel/simulador?caso=noexiste12345").status, 404)
        ficha = nav.pedir("GET", f"/panel/caso/{caso.id}").html
        self.assertIn(f"/panel/simulador?caso={caso.id}", ficha)


if __name__ == "__main__":
    unittest.main()
