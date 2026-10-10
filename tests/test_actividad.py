import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from privacidad import guardia
from privacidad.inventario import leer_planilla, perfilar_dataframe
from privacidad.inventario.actividad import (
    combinar_clasificacion,
    construir_actividad,
    forma,
    muestras_seguras,
)
from privacidad.inventario.perfilador import perfilar_columna
from privacidad.sinteticos import comercial_los_robles

REF = date(2026, 10, 10)
DESCRIPCION = "Planilla de Recursos Humanos para organizar el paseo de fin de año."


class IAFalsa:
    """Simula la API: devuelve respuestas fijas y guarda lo que se le envió."""

    def __init__(self, columnas=None, actividad=None, fallar=False):
        self.columnas = columnas or []
        self.actividad = actividad
        self.fallar = fallar
        self.enviado: list[str] = []

    def llamar(self, **kw):
        self.enviado.append(kw["mensajes"][0]["content"])
        if self.fallar:
            raise TimeoutError("sin conexión")
        if kw["forzar_herramienta"] == "clasificar_columnas":
            entrada = {"columnas": self.columnas}
        else:
            entrada = self.actividad
        bloques = (
            [] if entrada is None else [{"nombre": kw["forzar_herramienta"], "entrada": entrada}]
        )
        return SimpleNamespace(bloques_herramienta=bloques, costo_usd=0.001)


def propuesta(**cambios):
    base = {
        "fines": ["Organizar el paseo de fin de año"],
        "base_licitud": "consentimiento",
        "categorias_titulares": ["Trabajadores", "Hijos e hijas de trabajadores"],
        "fuente": "Formulario completado por los trabajadores",
        "destinatarios": ["no informado"],
        "ambito_territorial": "Chile",
        "transferencias_internacionales": "no informado",
        "plazo_supresion": "no informado",
        "decisiones_automatizadas": False,
        "columnas_innecesarias": [
            {"columna": "RUT hijo/a", "motivo": "No se necesita para un paseo"}
        ],
        "citas": [
            {"campo": "base_licitud", "norma": "ley-19628", "articulo": "12"},
            {"campo": "fines", "norma": "ley-19628", "articulo": "99 bis"},
        ],
    }
    base.update(cambios)
    return base


class TestPrivacidadDeLoEnviado(unittest.TestCase):
    def test_forma(self):
        self.assertEqual(forma("Ana Pérez 12"), "Aaa Aaaaa 99")

    def test_columnas_libres_se_envian_como_forma(self):
        m = muestras_seguras(["Ana Pérez", "Luis Soto"])
        self.assertEqual(m, {"tipo": "formas", "valores": ["Aaa Aaaaa", "Aaaa Aaaa"]})

    def test_columnas_categoricas_se_envian_enmascaradas(self):
        m = muestras_seguras(["Sí", "No"] * 15)
        self.assertEqual(m, {"tipo": "opciones", "valores": ["No", "Sí"]})


class TestConstruirActividad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        rutas = comercial_los_robles.generar(Path(cls.tmp.name))
        cls.df = leer_planilla(rutas["paseo"])
        cls.perfil = perfilar_dataframe(cls.df, "paseo_fin_de_anio.xlsx", referencia=REF)
        cls.valores = {c: cls.df[c].tolist() for c in cls.df.columns}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def construir(self, ia):
        return construir_actividad(self.perfil, self.valores, DESCRIPCION, ia)

    def test_no_envia_ningun_rut_correo_ni_nombre(self):
        ia = IAFalsa(
            columnas=[{"nombre": "Talla polera", "categoria": "no_personal", "justificacion": "x"}],
            actividad=propuesta(),
        )
        self.construir(ia)
        enviado = "\n".join(ia.enviado)
        for valor in self.df["RUT hijo/a"].tolist() + self.df["Correo apoderado"].tolist():
            self.assertNotIn(valor, enviado)
        self.assertNotIn(self.df["Nombre hijo/a"].iloc[0], enviado)
        self.assertNotIn(guardia.rut_sintetico(1)[:6], enviado)

    def test_solo_las_ambiguas_van_a_la_ia(self):
        ia = IAFalsa(
            columnas=[
                {"nombre": "Talla polera", "categoria": "no_personal", "justificacion": "Talla"},
                {"nombre": "RUT trabajador", "categoria": "salud", "justificacion": "intento"},
            ],
            actividad=propuesta(),
        )
        act = self.construir(ia)
        cols = {c.nombre: c for c in act.columnas}
        self.assertEqual(cols["Talla polera"].categoria, "no_personal")
        self.assertEqual(cols["Talla polera"].origen, "ia")
        # La IA no puede reescribir una columna que el código ya clasificó con certeza.
        self.assertEqual(cols["RUT trabajador"].categoria, "identificador_nacional")
        self.assertEqual(cols["RUT trabajador"].origen, "calculado")

    def test_categoria_inventada_se_ignora(self):
        ia = IAFalsa(
            columnas=[{"nombre": "Talla polera", "categoria": "vestuario", "justificacion": "x"}],
            actividad=propuesta(),
        )
        cols = {c.nombre: c for c in self.construir(ia).columnas}
        self.assertEqual(cols["Talla polera"].origen, "pendiente")

    def test_citas_inexistentes_se_rechazan(self):
        act = self.construir(IAFalsa(actividad=propuesta()))
        self.assertEqual(act.citas_rechazadas, ["ley-19628 art. 99 bis (fines)"])
        self.assertEqual([c.articulo for c in act.base_licitud.citas], ["12", "12"])

    def test_alertas_fijas_aunque_la_ia_diga_consentimiento_simple(self):
        act = self.construir(IAFalsa(actividad=propuesta(base_licitud="consentimiento")))
        textos = " ".join(a.mensaje for a in act.alertas)
        self.assertIn("consentimiento expreso", textos)
        self.assertIn("61 niños o niñas menores de 14", textos)
        self.assertIn("«RUT hijo/a» parece innecesaria", textos)

    def test_sin_alerta_de_sensibles_con_consentimiento_expreso(self):
        act = self.construir(IAFalsa(actividad=propuesta(base_licitud="consentimiento_expreso")))
        self.assertFalse(
            any("consentimiento expreso del titular" in a.mensaje for a in act.alertas)
        )

    def test_columna_innecesaria_inexistente_se_ignora(self):
        p = propuesta(columnas_innecesarias=[{"columna": "Color favorito", "motivo": "x"}])
        act = self.construir(IAFalsa(actividad=p))
        self.assertFalse(any(c.necesaria is False for c in act.columnas))

    def test_si_la_ia_falla_todo_queda_pendiente_y_con_alertas_legales(self):
        act = self.construir(IAFalsa(fallar=True))
        self.assertEqual(act.base_licitud.origen, "pendiente")
        self.assertEqual(act.fines.origen, "pendiente")
        self.assertEqual(act.tipo_datos.origen, "calculado")
        textos = " ".join(a.mensaje for a in act.alertas)
        self.assertIn("IA no disponible", textos)
        self.assertIn("consentimiento expreso", textos)  # la regla legal no depende de la IA
        self.assertIn("menores de 14", textos)

    def test_sin_cliente(self):
        act = construir_actividad(self.perfil, self.valores, DESCRIPCION, None)
        self.assertEqual(act.costo_ia_usd, 0)
        self.assertEqual(act.plazo_supresion.origen, "pendiente")


if __name__ == "__main__":
    unittest.main()


class TestCombinarClasificacion(unittest.TestCase):
    def test_la_ia_corrige_una_palabra_clave_no_sensible(self):
        col = perfilar_columna("Nombre mascota", ["Toby", "Luna"])
        final = combinar_clasificacion(col, ("no_personal", "Es el nombre de un perro"))
        self.assertEqual(
            (final.categoria, final.origen, final.revisar), ("no_personal", "ia", False)
        )

    def test_la_ia_no_puede_quitar_la_marca_de_sensible(self):
        col = perfilar_columna("Raza", ["Labrador", "Poodle"])
        final = combinar_clasificacion(col, ("no_personal", "Raza de la mascota"))
        self.assertEqual(final.categoria, "origen_etnico")
        self.assertTrue(final.revisar)
        self.assertIn("no_personal", final.justificacion)

    def test_lo_confirmado_por_formato_no_se_cambia(self):
        col = perfilar_columna("RUT", [guardia.rut_sintetico(i) for i in range(1, 6)])
        final = combinar_clasificacion(col, ("persona_juridica", "x"))
        self.assertEqual((final.categoria, final.origen), ("identificador_nacional", "calculado"))
