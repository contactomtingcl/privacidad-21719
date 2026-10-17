"""Demo pública: cada participante recibe su propia copia limpia de los casos («sala»)."""

from __future__ import annotations

import re
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from privacidad.canal.repositorio import RepositorioCasos
from privacidad.panel.demo import sembrar
from privacidad.panel.salas import SalasDemo, id_sala_valido

from .canal_apoyo import crear_canal
from .panel_apoyo import Navegador, crear_panel_de_prueba

ROBLES = "comercial-los-robles"


def ids_en_bandeja(html: str) -> set[str]:
    return set(re.findall(r"/panel/caso/([A-Za-z0-9_-]{8,64})\"", html))


class RelojManual:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


class TestSalasEnElPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app, self.canal, _ = crear_panel_de_prueba(
            None,
            demo=True,
            salas=self.crear_salas,
        )

    def crear_salas(self, canal):
        self.salas = SalasDemo(Path(self.tmp.name), canal.con_repositorio, sembrar)
        return self.salas

    def tearDown(self):
        self.salas.cerrar()
        self.tmp.cleanup()

    def enlace_de(self, nav: Navegador) -> str:
        html = nav.pedir("GET", "/panel/canal").html
        m = re.search(r'href="https://canal\.ejemplo\.cl(/canal/[^"]+)"', html)
        assert m, "la pantalla del canal no trae el enlace"
        return m.group(1).replace("&amp;", "&")

    def test_cada_participante_parte_con_la_misma_copia_limpia(self):
        a, b = Navegador(self.app), Navegador(self.app)
        casos_a = ids_en_bandeja(a.pedir("GET", "/panel/").html)
        casos_b = ids_en_bandeja(b.pedir("GET", "/panel/").html)
        self.assertTrue(casos_a)
        self.assertEqual(len(casos_a), len(casos_b))
        self.assertFalse(casos_a & casos_b, "dos participantes no comparten casos")
        # La base única del canal no recibe nada de lo que pasa en las salas.
        self.assertEqual(self.canal._repo.listar(), [])

    def test_el_enlace_y_el_qr_llevan_la_sala(self):
        nav = Navegador(self.app)
        html = nav.pedir("GET", "/panel/canal").html
        self.assertRegex(html, r'href="https://canal\.ejemplo\.cl/canal/[^"]+\?sala=[\w-]{22}"')
        self.assertRegex(html, r'src="/canal/[^"]+/qr\.svg\?sala=[\w-]{22}"')

    def test_un_reporte_por_el_enlace_llega_solo_a_la_sala_de_quien_lo_compartio(self):
        a, b = Navegador(self.app), Navegador(self.app)
        antes_b = ids_en_bandeja(b.pedir("GET", "/panel/").html)
        r = Navegador(self.app).pedir(  # otro dispositivo, sin la sesión del panel
            "POST",
            self.enlace_de(a),
            {"tipo": "incidente", "texto": "Vi que enviaron una planilla a un tercero."},
        )
        self.assertEqual(r.status, 303)
        self.assertRegex(r.cabeceras["location"], r"^/seguimiento/[\w-]+\?sala=[\w-]{22}$")
        seguimiento = Navegador(self.app).pedir("GET", r.cabeceras["location"])
        self.assertEqual(seguimiento.status, 200)
        nuevo = r.cabeceras["location"].split("/")[2].split("?")[0]
        self.assertIn(nuevo, ids_en_bandeja(a.pedir("GET", "/panel/").html))
        self.assertEqual(antes_b, ids_en_bandeja(b.pedir("GET", "/panel/").html))
        # Sin la sala, el seguimiento busca en la base única y no lo encuentra.
        self.assertEqual(Navegador(self.app).pedir("GET", f"/seguimiento/{nuevo}").status, 404)

    def test_reiniciar_entrega_una_copia_limpia_nueva(self):
        nav = Navegador(self.app)
        Navegador(self.app).pedir(
            "POST",
            self.enlace_de(nav),
            {"tipo": "incidente", "texto": "Vi que enviaron una planilla a un tercero."},
        )
        antes = ids_en_bandeja(nav.pedir("GET", "/panel/").html)
        csrf = nav.pedir("GET", "/panel/").csrf()
        nav.pedir("POST", "/panel/salir", {"csrf": csrf})
        despues = ids_en_bandeja(nav.pedir("GET", "/panel/").html)
        self.assertEqual(len(despues), len(antes) - 1)
        self.assertFalse(antes & despues)

    def test_una_sala_inventada_no_crea_nada_y_usa_la_base_unica(self):
        nav = Navegador(self.app)
        enlace = self.enlace_de(nav).split("?")[0] + "?sala=" + "x" * 22
        r = Navegador(self.app).pedir(
            "POST", enlace, {"tipo": "incidente", "texto": "Vi que enviaron una planilla."}
        )
        self.assertEqual(r.status, 303)
        self.assertNotIn("sala=", r.cabeceras["location"])
        self.assertEqual(len(self.canal._repo.listar()), 1)


class TestLimpiezaDeSalas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.tmp.name)
        self.canal, *_ = crear_canal(None)
        self.reloj = RelojManual()
        self.creadas: list[SalasDemo] = []

    def tearDown(self):
        for salas in self.creadas:
            salas.cerrar()
        self.tmp.cleanup()

    def salas(self, **opciones) -> SalasDemo:
        salas = SalasDemo(
            self.carpeta, self.canal.con_repositorio, sembrar, reloj=self.reloj, **opciones
        )
        self.creadas.append(salas)
        return salas

    def test_identificador_de_sala(self):
        salas = self.salas()
        sala = salas.crear()
        self.assertTrue(id_sala_valido(sala))
        for malo in (None, "", "../" + "a" * 19, "a" * 21, "a" * 23, "a b" + "c" * 19):
            self.assertFalse(id_sala_valido(malo), malo)
            self.assertIsNone(salas.canal(malo or ""))

    def test_se_borran_las_salas_sin_uso(self):
        salas = self.salas(vida=timedelta(hours=1))
        vieja = salas.crear()
        self.reloj.t += 2 * 3600
        nueva = salas.crear()
        self.assertIsNone(salas.canal(vieja))
        self.assertIsNotNone(salas.canal(nueva))
        self.assertEqual(salas.cantidad(), 1)

    def test_usar_una_sala_la_mantiene_viva(self):
        salas = self.salas(vida=timedelta(hours=1))
        sala = salas.crear()
        self.reloj.t += 3000
        salas.canal(sala)
        self.reloj.t += 3000
        salas.crear()
        self.assertIsNotNone(salas.canal(sala))

    def test_tope_de_salas_borra_las_mas_antiguas(self):
        salas = self.salas(maximo=2)
        creadas = []
        for _ in range(3):
            creadas.append(salas.crear())
            self.reloj.t += 60
        self.assertEqual(salas.cantidad(), 2)
        self.assertIsNone(salas.canal(creadas[0]))

    def test_las_salas_cerradas_se_reabren_desde_el_disco(self):
        salas = self.salas(abiertas=1)
        primera = salas.crear()
        casos = [c.id for c in salas.canal(primera).casos_de(ROBLES)]
        salas.crear()  # cierra la primera en memoria
        self.assertEqual([c.id for c in salas.canal(primera).casos_de(ROBLES)], casos)

    def test_cada_sala_tiene_su_evidencia_integra(self):
        salas = self.salas()
        for _ in range(2):
            canal = salas.canal(salas.crear())
            self.assertTrue(canal._repo.verificar_evidencia().integra)


class TestConRepositorio(unittest.TestCase):
    def test_comparte_todo_menos_los_casos(self):
        canal, *_ = crear_canal(None)
        otro = canal.con_repositorio(RepositorioCasos())
        self.assertIsNot(otro._repo, canal._repo)
        self.assertEqual(otro.enlace(ROBLES, "https://x.cl"), canal.enlace(ROBLES, "https://x.cl"))
        otro.recibir_incidente(ROBLES, "Vi que enviaron una planilla a un tercero.")
        self.assertEqual(len(otro.casos_de(ROBLES)), 1)
        self.assertEqual(canal.casos_de(ROBLES), [])


if __name__ == "__main__":
    unittest.main()
