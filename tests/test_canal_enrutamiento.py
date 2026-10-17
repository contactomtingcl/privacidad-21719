import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from privacidad.canal import CanalReporte, RepositorioCasos, cargar_organizaciones
from privacidad.canal.confirmacion import dias_de_espera
from privacidad.canal.enrutamiento import (
    cargar_reglas_enrutamiento,
    normalizar,
    palabras_encontradas,
)
from privacidad.guardia import DatosNoSinteticosError

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    HECHOS_INCIDENTE,
    SECRETO,
    SOLICITUD_AMBIGUA,
    SOLICITUD_CLARA,
    ClienteCaido,
    ClienteFalso,
    crear_canal,
)

ROBLES = "comercial-los-robles"
MUNI = "municipalidad-piloto"
NOMBRE = "Persona Ficticia Uno"
CORREO = "persona.uno@example.com"


def ids(destinos):
    return [d.id for d in destinos]


def ultimo_enrutado(caso):
    return [e for e in caso.eventos if e.tipo == "enrutado"][-1]


class TestPalabras(unittest.TestCase):
    def test_sin_mayusculas_ni_tildes(self):
        self.assertEqual(normalizar("Remuneración CAMPAÑA"), "remuneracion campana")

    def test_desde_el_inicio_de_una_palabra(self):
        self.assertEqual(
            palabras_encontradas("Revisen mis remuneraciones", ["remuneracion"]), ["remuneracion"]
        )
        self.assertEqual(palabras_encontradas("Hubo un repaseo general", ["paseo"]), [])

    def test_frases(self):
        self.assertEqual(
            palabras_encontradas("Llegó una Orden de Compra rara", ["orden de compra"]),
            ["orden de compra"],
        )


class TestReglas(unittest.TestCase):
    def test_todas_las_organizaciones_tienen_reglas(self):
        reglas = cargar_reglas_enrutamiento()
        self.assertEqual(set(cargar_organizaciones()), set(reglas.organizaciones))

    def test_contactos_reales_se_rechazan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "enrutamiento.yaml"
            texto = (Path(__file__).parents[1] / "data/canal/enrutamiento.yaml").read_text()
            ruta.write_text(
                texto.replace("delegado@comercial-los-robles.example", "alguien@gmail.com")
            )
            with self.assertRaises(DatosNoSinteticosError):
                cargar_reglas_enrutamiento(ruta)

    def test_organizacion_sin_reglas_no_arranca(self):
        reglas = cargar_reglas_enrutamiento()
        del reglas.organizaciones[MUNI]
        with self.assertRaises(ValueError):
            CanalReporte(
                organizaciones=cargar_organizaciones(),
                repositorio=RepositorioCasos(),
                cliente=None,
                secreto_enlaces=SECRETO,
                enrutamiento=reglas,
            )


class TestSolicitudes(unittest.TestCase):
    def test_publicidad_va_al_delegado_y_a_marketing(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(
            ROBLES, "No quiero recibir más publicidad.", nombre=NOMBRE, contacto=CORREO
        )
        a = caso.asignacion
        self.assertEqual(ids(a.destinos), ["delegado", "marketing"])
        self.assertIn("«publicidad»", a.destinos[1].porque)
        self.assertEqual(a.urgencia, "normal")
        self.assertEqual(a.proximo_plazo, "respuesta_solicitud")

    def test_sin_area_que_coincida_queda_solo_el_delegado(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(
            ROBLES, "Quiero saber qué datos tienen de mí.", nombre=NOMBRE, contacto=CORREO
        )
        self.assertEqual(ids(caso.asignacion.destinos), ["delegado"])
        self.assertIn("Ninguna área coincide", caso.asignacion.destinos[0].porque)

    def test_solicitud_con_ia_caida_igual_se_enruta(self):
        canal, *_ = crear_canal(ClienteCaido())
        caso = canal.recibir_solicitud(
            ROBLES, "Corrijan mi sueldo en la nómina.", nombre=NOMBRE, contacto=CORREO
        )
        self.assertEqual(ids(caso.asignacion.destinos), ["delegado", "rrhh"])
        self.assertEqual(caso.asignacion.proximo_plazo, "respuesta_solicitud")

    def test_el_evento_no_lleva_texto_ni_contactos(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(
            ROBLES, "No quiero recibir más publicidad.", nombre=NOMBRE, contacto=CORREO
        )
        volcado = json.dumps(ultimo_enrutado(caso).detalle, ensure_ascii=False)
        self.assertNotIn("No quiero", volcado)
        self.assertNotIn("@", volcado)
        self.assertNotIn(NOMBRE, volcado)
        self.assertIn("palabra:publicidad", volcado)

    def test_la_lectura_por_defecto_reenruta_y_queda_en_la_evidencia(self):
        canal, reloj, _ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA))
        caso = canal.recibir_solicitud(
            ROBLES, "Ya no quiero sus correos de ofertas.", nombre=NOMBRE, contacto=CORREO
        )
        # Bloqueo preventivo: su plazo (2 días hábiles) se avisa desde el ingreso, no recién
        # cuando termina la espera de la confirmación.
        self.assertEqual(caso.asignacion.urgencia, "alta")
        self.assertEqual(caso.asignacion.proximo_plazo, "bloqueo_temporal")
        reloj.avanzar(days=dias_de_espera() + 1)
        caso = canal.seguimiento(caso.id)
        # Si nadie registró que lo hizo, al terminar la espera el bloqueo ya está vencido.
        self.assertEqual(caso.asignacion.urgencia, "inmediata")
        self.assertEqual(caso.asignacion.proximo_plazo, "bloqueo_temporal")
        self.assertIn("ya venció", caso.asignacion.porque_urgencia)
        self.assertEqual([e.tipo for e in caso.eventos].count("enrutado"), 2)

    def test_sin_cambios_no_se_anota_de_nuevo(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA))
        caso = canal.recibir_solicitud(
            ROBLES, "Ya no quiero sus correos de ofertas.", nombre=NOMBRE, contacto=CORREO
        )
        # Confirma también el bloqueo: la lectura vigente no cambia y no se reenruta.
        caso = canal.responder_confirmacion(caso.id, derechos=["oposicion", "bloqueo"])
        self.assertEqual([e.tipo for e in caso.eventos].count("enrutado"), 1)


class TestIncidentes(unittest.TestCase):
    def test_la_planilla_del_paseo_va_a_recursos_humanos(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(
            ROBLES, "Envié la planilla del paseo al correo de un proveedor por error."
        )
        a = caso.asignacion
        self.assertEqual(ids(a.destinos), ["delegado", "rrhh"])
        self.assertEqual(a.urgencia, "alta")
        self.assertIn("Agencia", a.porque_urgencia)

    def test_ciberataque_en_municipio_es_inmediato_y_va_a_informatica(self):
        canal, reloj, _ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE))
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema de registros.")
        a = caso.asignacion
        self.assertEqual(ids(a.destinos), ["delegado", "informatica"])
        self.assertIn("ciberincidente", a.destinos[1].porque)
        self.assertEqual(a.urgencia, "inmediata")
        self.assertEqual(a.vence, reloj.ahora + timedelta(hours=3))
        self.assertIn("ANCI", a.porque_urgencia)

    def test_ia_caida_en_municipio_usa_los_relojes_posibles(self):
        canal, reloj, _ = crear_canal(ClienteCaido())
        caso = canal.recibir_incidente(MUNI, "Algo raro pasó con los datos.")
        a = caso.asignacion
        self.assertEqual(ids(a.destinos), ["delegado", "informatica"])
        self.assertEqual(a.urgencia, "inmediata")
        self.assertEqual(a.vence, reloj.ahora + timedelta(hours=3))

    def test_ia_caida_en_empresa_privada_es_urgencia_alta(self):
        canal, *_ = crear_canal(ClienteCaido())
        caso = canal.recibir_incidente(ROBLES, "Algo raro pasó con los datos.")
        self.assertEqual(caso.asignacion.urgencia, "alta")
        self.assertIn("IA no pudo leer", caso.asignacion.porque_urgencia)

    def test_aviso_de_proveedor_va_a_compras(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(
            ROBLES, "Somos el proveedor de nube y tuvimos un incidente.", tipo="aviso_proveedor"
        )
        self.assertEqual(ids(caso.asignacion.destinos), ["delegado", "compras"])
        self.assertIn("tipo:aviso_proveedor", caso.asignacion.destinos[1].motivos)

    def test_reservado_va_solo_al_delegado(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(
            ROBLES,
            "Envié la planilla del paseo a un proveedor por error.",
            reservado=True,
            nombre=NOMBRE,
        )
        a = caso.asignacion
        self.assertEqual(ids(a.destinos), ["delegado"])
        self.assertEqual(ids(a.sugeridas), ["rrhh"])
        self.assertIn("reservado", a.destinos[0].porque)
        detalle = ultimo_enrutado(caso).detalle
        self.assertEqual([d["id"] for d in detalle["destinos"]], ["delegado"])


if __name__ == "__main__":
    unittest.main()
