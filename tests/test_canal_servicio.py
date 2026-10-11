import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from privacidad import guardia
from privacidad.canal import (
    CasoNoEncontrado,
    OrganizacionDesconocida,
    ReservadoNoDisponible,
    reservado,
)
from privacidad.canal.confirmacion import RespuestaInvalida, dias_de_espera
from privacidad.guardia import DatosNoSinteticosError

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    HECHOS_INCIDENTE,
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
TEXTO = "Quiero saber qué datos tienen de mí."


def solicitud(canal, org=ROBLES, texto=TEXTO):
    return canal.recibir_solicitud(org, texto, nombre=NOMBRE, contacto=CORREO)


class TestEnlaces(unittest.TestCase):
    def test_el_enlace_abre_su_organizacion(self):
        canal, *_ = crear_canal(None)
        url = canal.enlace(ROBLES, "https://canal.ejemplo.cl")
        firma = url.rsplit("/", 1)[1]
        self.assertEqual(canal.organizacion_por_enlace(ROBLES, firma).id, ROBLES)

    def test_firma_mala_u_organizacion_ajena(self):
        canal, *_ = crear_canal(None)
        firma = canal.enlace(ROBLES, "https://canal.ejemplo.cl").rsplit("/", 1)[1]
        with self.assertRaises(OrganizacionDesconocida):
            canal.organizacion_por_enlace(MUNI, firma)
        with self.assertRaises(OrganizacionDesconocida):
            canal.organizacion_por_enlace(ROBLES, "firma-inventada")
        with self.assertRaises(OrganizacionDesconocida):
            canal.enlace("no-existe", "https://canal.ejemplo.cl")


class TestSolicitudClara(unittest.TestCase):
    def setUp(self):
        self.ia = ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA)
        self.canal, self.reloj, _ = crear_canal(self.ia)

    def test_queda_interpretada_sin_pedir_confirmacion(self):
        caso = solicitud(self.canal)
        self.assertEqual(caso.estado, "interpretado")
        self.assertEqual(caso.confirmacion.estado, "no_requerida")
        self.assertEqual(caso.confirmacion.vigente, ["acceso"])

    def test_el_motor_calcula_30_dias_desde_el_ingreso(self):
        caso = solicitud(self.canal)
        self.assertEqual(caso.resultado_solicitud.respuesta.vence, date(2027, 1, 1))

    def test_se_puede_volver_con_el_codigo(self):
        caso = solicitud(self.canal)
        self.assertEqual(self.canal.seguimiento(caso.id).id, caso.id)
        with self.assertRaises(CasoNoEncontrado):
            self.canal.seguimiento("codigo-inexistente-1")

    def test_registra_eventos_sin_texto_personal(self):
        caso = solicitud(self.canal)
        self.assertEqual([e.tipo for e in caso.eventos], ["recibido", "interpretado", "enrutado"])
        volcado = json.dumps([e.model_dump(mode="json") for e in caso.eventos])
        self.assertNotIn(NOMBRE, volcado)
        self.assertNotIn(CORREO, volcado)
        self.assertNotIn("datos tienen de mí", volcado)

    def test_registra_el_costo_de_la_ia(self):
        self.assertGreater(solicitud(self.canal).costo_usd, 0)

    def test_nombre_y_contacto_nunca_llegan_a_la_ia(self):
        solicitud(self.canal)
        visto = self.ia.lo_que_vio_la_ia()
        self.assertNotIn(NOMBRE, visto)
        self.assertNotIn(CORREO, visto)
        self.assertEqual(len(self.ia.llamadas), 1)

    def test_el_correo_dentro_del_relato_llega_enmascarado(self):
        solicitud(self.canal, texto=f"Soy {NOMBRE}, escríbanme a {CORREO} por favor, gracias.")
        visto = self.ia.lo_que_vio_la_ia()
        self.assertNotIn(CORREO, visto)

    def test_la_ia_no_decide_plazos(self):
        # aunque la IA "opine" sobre plazos, el resultado sale solo del motor
        ia = ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA | {"plazo_dias": 3})
        canal, *_ = crear_canal(ia)
        caso = solicitud(canal)
        self.assertEqual(caso.resultado_solicitud.respuesta.vence, date(2027, 1, 1))

    def test_nombre_y_contacto_son_obligatorios(self):
        with self.assertRaises(RespuestaInvalida):
            self.canal.recibir_solicitud(ROBLES, TEXTO, nombre="", contacto=CORREO)
        with self.assertRaises(RespuestaInvalida):
            self.canal.recibir_solicitud(ROBLES, TEXTO, nombre=NOMBRE, contacto=None)
        self.assertEqual(self.ia.llamadas, [])

    def test_mensaje_vacio_o_demasiado_largo(self):
        with self.assertRaises(RespuestaInvalida):
            solicitud(self.canal, texto="   ")
        with self.assertRaises(RespuestaInvalida):
            solicitud(self.canal, texto="x" * 5001)

    def test_organizacion_desconocida(self):
        with self.assertRaises(OrganizacionDesconocida):
            solicitud(self.canal, org="no-existe")

    def test_bloqueo_tiene_fecha_calculada_por_el_motor(self):
        ia = ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA | {"derechos": ["bloqueo"]})
        canal, *_ = crear_canal(ia)
        caso = solicitud(canal)
        self.assertEqual(caso.resultado_solicitud.bloqueo.vence, date(2026, 12, 4))


class TestDatosReales(unittest.TestCase):
    def test_se_rechaza_antes_de_llamar_a_la_ia(self):
        ia = ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA)
        canal, *_ = crear_canal(ia)
        real = "Mi correo es juan.perez@gmail.com y quiero saber qué datos tienen."
        with self.assertRaises(DatosNoSinteticosError):
            solicitud(canal, texto=real)
        with self.assertRaises(DatosNoSinteticosError):
            canal.recibir_solicitud(ROBLES, TEXTO, nombre=NOMBRE, contacto="juan@gmail.com")
        with self.assertRaises(DatosNoSinteticosError):
            canal.recibir_incidente(ROBLES, "Mi RUT es 12.345.678-5, filtraron datos.")
        self.assertEqual(ia.llamadas, [])
        self.assertEqual(canal.casos_de(ROBLES), [])

    def test_los_datos_ficticios_pasan(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        solicitud(canal, texto=f"Mi RUT es {guardia.rut_sintetico(7)}, ¿qué datos tienen de mí?")


class TestConfirmacion(unittest.TestCase):
    def setUp(self):
        self.canal, self.reloj, _ = crear_canal(
            ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA)
        )
        self.caso = solicitud(self.canal, texto="No quiero más correos de ustedes, por favor.")

    def test_queda_pendiente_con_la_pregunta_y_la_fecha_limite(self):
        c = self.caso.confirmacion
        self.assertEqual(self.caso.estado, "pendiente_confirmacion")
        self.assertEqual(c.estado, "pendiente")
        self.assertIn("publicidad", c.pregunta)
        self.assertEqual(c.espera_hasta, self.caso.ingreso + timedelta(days=dias_de_espera()))

    def test_el_plazo_corre_desde_el_ingreso_aun_pendiente(self):
        self.assertEqual(self.caso.resultado_solicitud.respuesta.vence, date(2027, 1, 1))

    def test_confirmar_lo_propuesto(self):
        self.reloj.avanzar(hours=3)
        caso = self.canal.responder_confirmacion(self.caso.id, derechos=["oposicion"])
        self.assertEqual(caso.confirmacion.estado, "confirmada")
        self.assertEqual(caso.estado, "interpretado")
        self.assertEqual(caso.confirmacion.vigente, ["oposicion"])

    def test_corregir_cambia_la_lectura_pero_no_el_plazo(self):
        self.reloj.avanzar(days=3)
        caso = self.canal.responder_confirmacion(
            self.caso.id, derechos=["supresion"], detalle="Quiero que borren todo."
        )
        self.assertEqual(caso.confirmacion.estado, "corregida")
        self.assertEqual(caso.confirmacion.vigente, ["supresion"])
        self.assertEqual(caso.confirmacion.detalle, "Quiero que borren todo.")
        self.assertEqual(caso.resultado_solicitud.respuesta.vence, date(2027, 1, 1))

    def test_respuesta_invalida(self):
        for derechos in ([], ["inventado"]):
            with self.assertRaises(RespuestaInvalida):
                self.canal.responder_confirmacion(self.caso.id, derechos=derechos)

    def test_no_se_responde_dos_veces(self):
        self.canal.responder_confirmacion(self.caso.id, derechos=["oposicion"])
        with self.assertRaises(RespuestaInvalida):
            self.canal.responder_confirmacion(self.caso.id, derechos=["supresion"])

    def test_detalle_con_datos_reales_se_rechaza(self):
        with self.assertRaises(DatosNoSinteticosError):
            self.canal.responder_confirmacion(
                self.caso.id, derechos=["oposicion"], detalle="escríbanme a ana@gmail.com"
            )
        self.assertEqual(self.canal.obtener(self.caso.id).confirmacion.estado, "pendiente")

    def test_no_se_confirma_un_incidente_ni_un_caso_ajeno(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        incidente = canal.recibir_incidente(ROBLES, "Enviamos una planilla por error.")
        with self.assertRaises(RespuestaInvalida):
            canal.responder_confirmacion(incidente.id, derechos=["acceso"])
        with self.assertRaises(CasoNoEncontrado):
            canal.responder_confirmacion("codigo-inexistente-1", derechos=["acceso"])


class TestRespuestaPorDefecto(unittest.TestCase):
    def setUp(self):
        self.canal, self.reloj, _ = crear_canal(
            ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA)
        )
        self.caso = solicitud(self.canal)

    def test_antes_de_vencer_no_cambia_nada(self):
        self.reloj.avanzar(days=dias_de_espera() - 1)
        self.assertEqual(self.canal.resolver_vencidas(), [])
        self.assertEqual(self.canal.seguimiento(self.caso.id).confirmacion.estado, "pendiente")

    def test_sin_respuesta_se_aplica_la_lectura_reversible_sin_borrar(self):
        self.reloj.avanzar(days=dias_de_espera(), minutes=1)
        resueltos = self.canal.resolver_vencidas()
        self.assertEqual([c.id for c in resueltos], [self.caso.id])
        caso = self.canal.obtener(self.caso.id)
        self.assertEqual(caso.confirmacion.estado, "por_defecto")
        self.assertEqual(caso.confirmacion.vigente, ["oposicion", "bloqueo"])
        self.assertNotIn("supresion", caso.confirmacion.vigente)
        self.assertEqual(caso.confirmacion.propuesta, ["oposicion"])
        self.assertEqual(caso.resultado_solicitud.bloqueo.vence, date(2026, 12, 4))
        self.assertEqual(caso.resultado_solicitud.respuesta.vence, date(2027, 1, 1))
        evento = next(e for e in caso.eventos if e.tipo == "confirmacion_por_defecto")
        self.assertIn("confirmacion_titular", evento.detalle["criterio"])
        self.assertIn("sin supresión", evento.detalle["criterio"])

    def test_al_volver_con_el_codigo_se_aplica_sola(self):
        self.reloj.avanzar(days=dias_de_espera() + 1)
        caso = self.canal.seguimiento(self.caso.id)
        self.assertEqual(caso.confirmacion.estado, "por_defecto")

    def test_es_idempotente(self):
        self.reloj.avanzar(days=dias_de_espera() + 1)
        self.canal.resolver_vencidas()
        self.assertEqual(self.canal.resolver_vencidas(), [])
        n = len(self.canal.obtener(self.caso.id).eventos)
        self.canal.seguimiento(self.caso.id)
        self.assertEqual(len(self.canal.obtener(self.caso.id).eventos), n)

    def test_el_titular_puede_pedir_la_supresion_cuando_quiera(self):
        self.reloj.avanzar(days=dias_de_espera() + 1)
        self.canal.seguimiento(self.caso.id)
        caso = self.canal.responder_confirmacion(self.caso.id, derechos=["supresion"])
        self.assertEqual(caso.confirmacion.estado, "corregida")
        self.assertEqual(caso.confirmacion.vigente, ["supresion"])

    def test_el_titular_aun_puede_corregir_despues_del_defecto(self):
        self.reloj.avanzar(days=dias_de_espera() + 1)
        self.canal.seguimiento(self.caso.id)
        caso = self.canal.responder_confirmacion(self.caso.id, derechos=["oposicion"])
        self.assertEqual(caso.confirmacion.vigente, ["oposicion"])


class TestFallasDeLaIA(unittest.TestCase):
    def test_si_la_ia_cae_el_caso_va_a_revision_y_el_reloj_corre(self):
        canal, *_ = crear_canal(ClienteCaido())
        caso = solicitud(canal)
        self.assertEqual(caso.estado, "requiere_revision")
        self.assertIsNotNone(caso.error_ia)
        self.assertEqual(caso.resultado_solicitud.respuesta.vence, date(2027, 1, 1))
        self.assertIn("ia_sin_respuesta", [e.tipo for e in caso.eventos])

    def test_sin_ia_configurada(self):
        canal, *_ = crear_canal(None)
        caso = solicitud(canal)
        self.assertEqual(caso.estado, "requiere_revision")
        self.assertEqual(caso.error_ia, "sin_ia")

    def test_ia_sin_respuesta_util(self):
        canal, *_ = crear_canal(ClienteFalso())  # no devuelve la herramienta
        caso = solicitud(canal)
        self.assertEqual(caso.estado, "requiere_revision")
        self.assertIsNotNone(caso.resultado_solicitud)

    def test_no_es_una_solicitud(self):
        ia = ClienteFalso(interpretar_solicitud={"es_solicitud": False, "derechos": []})
        canal, *_ = crear_canal(ia)
        caso = solicitud(canal, texto="Muchas gracias por la atención de ayer.")
        self.assertEqual(caso.estado, "sin_solicitud")
        self.assertIsNone(caso.resultado_solicitud)

    def test_incidente_con_ia_caida_muestra_relojes_posibles_de_la_anci(self):
        canal, *_ = crear_canal(ClienteCaido())
        caso = canal.recibir_incidente(MUNI, "Un virus cifró los equipos del municipio.")
        self.assertEqual(caso.estado, "requiere_revision")
        self.assertIsNone(caso.resultado_incidente)
        self.assertTrue(caso.relojes_anci_posibles)
        self.assertTrue(all(d.vence for d in caso.relojes_anci_posibles[:2]))

    def test_una_empresa_privada_no_tiene_relojes_anci(self):
        canal, *_ = crear_canal(ClienteCaido())
        caso = canal.recibir_incidente(ROBLES, "Un virus cifró los equipos de la empresa.")
        self.assertEqual(caso.relojes_anci_posibles, [])


class TestIncidentes(unittest.TestCase):
    def test_el_motor_decide_los_deberes(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(ROBLES, "Enviamos una planilla de menores a un proveedor.")
        r = caso.resultado_incidente
        self.assertEqual(caso.estado, "interpretado")
        self.assertEqual(r.aviso_agencia.decision, "si")
        self.assertEqual(r.reporte_anci.decision, "no")

    def test_ciberataque_en_municipio_activa_los_relojes_de_la_anci(self):
        canal, reloj, _ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE))
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al servidor de registros.")
        r = caso.resultado_incidente
        self.assertEqual(r.reporte_anci.decision, "si")
        self.assertEqual(r.reporte_anci.vence, reloj.ahora + timedelta(hours=3))

    def test_aviso_de_proveedor(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(
            ROBLES, "Somos el proveedor de nube y tuvimos un incidente.", tipo="aviso_proveedor"
        )
        self.assertEqual(caso.tipo, "aviso_proveedor")

    def test_tipo_desconocido(self):
        canal, *_ = crear_canal(ClienteFalso())
        with self.assertRaises(RespuestaInvalida):
            canal.recibir_incidente(ROBLES, "Un texto cualquiera.", tipo="solicitud")

    def test_el_relato_llega_enmascarado_a_la_ia(self):
        ia = ClienteFalso(registrar_hechos=HECHOS_INCIDENTE)
        canal, *_ = crear_canal(ia)
        canal.recibir_incidente(
            ROBLES, f"Se filtró la ficha de {guardia.rut_sintetico(3)}.", nombre=NOMBRE
        )
        visto = ia.lo_que_vio_la_ia()
        self.assertNotIn(guardia.rut_sintetico(3), visto)
        self.assertNotIn(NOMBRE, visto)


class TestModoReservado(unittest.TestCase):
    def test_la_identidad_se_guarda_cifrada_y_el_delegado_la_abre(self):
        canal, _, llaves = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(
            ROBLES,
            "Vi que enviaron una planilla a un tercero.",
            reservado=True,
            nombre=NOMBRE,
            contacto=CORREO,
        )
        guardado = canal.obtener(caso.id)
        self.assertTrue(guardado.reservado)
        self.assertIsNone(guardado.identidad)
        volcado = guardado.model_dump_json()
        self.assertNotIn(NOMBRE, volcado)
        self.assertNotIn(CORREO, volcado)
        abierta = reservado.descifrar_identidad(llaves, guardado.identidad_cifrada, caso.id)
        self.assertEqual(abierta, {"nombre": NOMBRE, "contacto": CORREO})

    def test_la_ia_nunca_ve_la_identidad_reservada(self):
        ia = ClienteFalso(registrar_hechos=HECHOS_INCIDENTE)
        canal, *_ = crear_canal(ia)
        canal.recibir_incidente(
            ROBLES,
            "Vi que enviaron una planilla a un tercero.",
            reservado=True,
            nombre=NOMBRE,
            contacto=CORREO,
        )
        self.assertNotIn(NOMBRE, ia.lo_que_vio_la_ia())

    def test_sin_llave_se_rechaza_y_no_se_guarda_nada(self):
        canal, *_ = crear_canal(ClienteFalso(), con_reservado=False)
        self.assertFalse(canal.reservado_disponible)
        with self.assertRaises(ReservadoNoDisponible):
            canal.recibir_incidente(ROBLES, "Un aviso reservado.", reservado=True, nombre=NOMBRE)
        self.assertEqual(canal.casos_de(ROBLES), [])

    def test_reservado_y_anonimo_no_tiene_identidad(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(ROBLES, "Aviso reservado, sin nombre.", reservado=True)
        self.assertIsNone(caso.identidad_cifrada)
        self.assertIsNone(caso.identidad)

    def test_sin_reserva_la_identidad_queda_visible_para_el_equipo(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(ROBLES, "Aviso con nombre.", nombre=NOMBRE)
        self.assertEqual(caso.identidad, {"nombre": NOMBRE})
        self.assertIsNone(caso.identidad_cifrada)

    def test_los_eventos_dicen_que_hubo_identidad_pero_no_cual(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(
            ROBLES, "Aviso reservado con nombre.", reservado=True, nombre=NOMBRE
        )
        self.assertTrue(caso.eventos[0].detalle["con_identidad"])
        self.assertNotIn(NOMBRE, json.dumps([e.model_dump(mode="json") for e in caso.eventos]))


class TestPersistenciaEnCarpeta(unittest.TestCase):
    def test_los_casos_sobreviven_a_un_reinicio(self):
        import tempfile

        from privacidad.canal import RepositorioCasos

        with tempfile.TemporaryDirectory() as tmp:
            repo = RepositorioCasos(Path(tmp))
            canal, *_ = crear_canal(
                ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA), repositorio=repo
            )
            caso = solicitud(canal)
            repo.cerrar()
            nuevo = RepositorioCasos(Path(tmp))
            self.assertEqual(nuevo.obtener(caso.id).estado, "interpretado")
            nuevo.cerrar()
