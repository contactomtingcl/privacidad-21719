"""Lo que el programa lee al funcionar debe viajar en la imagen publicada (Render).

El 17 de octubre la demo publicada falló porque las respuestas grabadas del inventario estaban en
`resultados/`, que `.dockerignore` excluye. Estas pruebas revisan las rutas que se leen en tiempo
de ejecución contra lo que la imagen copia y excluye.
"""

import contextlib
import fnmatch
import unittest
from pathlib import Path
from unittest import mock

from privacidad.canal.modelos import RAIZ_CANAL
from privacidad.inventario import servicio
from privacidad.motor.motor import RAIZ_REGLAS
from privacidad.panel import demo

RAIZ = Path(__file__).resolve().parents[1]


def excluida(ruta: Path) -> bool:
    relativa = ruta.resolve().relative_to(RAIZ).as_posix()
    reglas = [
        linea.strip()
        for linea in (RAIZ / ".dockerignore").read_text("utf-8").splitlines()
        if linea.strip() and not linea.startswith("#")
    ]
    partes = relativa.split("/")
    for regla in reglas:
        for i in range(1, len(partes) + 1):
            if fnmatch.fnmatch("/".join(partes[:i]), regla.rstrip("/")):
                return True
    return False


def copiada(ruta: Path) -> bool:
    """El Dockerfile copia pyproject.toml, README.md, LICENSE, src/ y data/."""
    relativa = ruta.resolve().relative_to(RAIZ).as_posix()
    return relativa.split("/")[0] in {"src", "data"} or relativa in {
        "pyproject.toml",
        "README.md",
        "LICENSE",
    }


class TestImagen(unittest.TestCase):
    def test_rutas_de_ejecucion_viajan_en_la_imagen(self):
        rutas = [
            servicio.GRABADAS,
            servicio.DATOS_DEMO,
            demo.RAIZ_DEMO / "casos.yaml",
            RAIZ_CANAL / "organizaciones.yaml",
            RAIZ_CANAL / "enrutamiento.yaml",
            RAIZ_CANAL / "proveedores.yaml",
            RAIZ_REGLAS / "reglas.yaml",
            RAIZ_REGLAS / "escenarios.yaml",
            RAIZ_REGLAS / "riesgos.yaml",
        ]
        for ruta in rutas:
            self.assertTrue(ruta.exists(), ruta)
            self.assertTrue(copiada(ruta), f"{ruta} no se copia a la imagen")
            self.assertFalse(excluida(ruta), f"{ruta} queda fuera por .dockerignore")

    def test_las_planillas_de_ejemplo_tienen_su_respuesta_grabada(self):
        servicio._grabadas.cache_clear()
        grabadas = servicio._grabadas()
        for nombre in servicio.ejemplos():
            huella = servicio.huella((servicio.DATOS_DEMO / nombre).read_bytes())
            self.assertIn(huella, grabadas, nombre)

    def test_sin_respuestas_grabadas_la_demo_igual_se_siembra(self):
        from .canal_apoyo import crear_canal

        canal, *_ = crear_canal(None)
        servicio._grabadas.cache_clear()
        try:
            with mock.patch.object(servicio, "GRABADAS", RAIZ / "no-existe.json"):
                n = demo.sembrar(canal)
        finally:
            servicio._grabadas.cache_clear()
        self.assertGreater(n, 0)
        self.assertGreater(len(canal._repo.listar()), 0)


class TestErrorInesperado(unittest.TestCase):
    def test_una_falla_muestra_una_pagina_clara(self):
        from privacidad.motor import escenarios

        from .panel_apoyo import Navegador, crear_panel_de_prueba

        app, *_ = crear_panel_de_prueba(None, demo=True)

        async def sin_relanzar(scope, receive, send):
            # Starlette relanza la excepción después de responder (para que el servidor la
            # registre); aquí solo interesa lo que recibió el navegador.
            with contextlib.suppress(RuntimeError):
                await app(scope, receive, send)

        nav = Navegador(sin_relanzar)
        self.assertEqual(nav.pedir("GET", "/panel/").status, 200)
        with mock.patch.object(escenarios, "comparar", side_effect=RuntimeError("falla")):
            r = nav.pedir("GET", "/panel/simulador")
        self.assertEqual(r.status, 500)
        self.assertIn("Algo salió mal en el servidor", r.html)
        self.assertNotIn("RuntimeError", r.html)
        self.assertNotIn("Internal Server Error", r.html)


if __name__ == "__main__":
    unittest.main()
