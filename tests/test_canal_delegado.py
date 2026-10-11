import json
import unittest
from datetime import timedelta

from privacidad.canal import RepositorioCasos
from privacidad.canal.delegado import AccionInvalida, CasoAjeno, decision_final, por_resolver
from privacidad.guardia import DatosNoSinteticosError
from privacidad.motor import HechosIncidente

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
POR = "delegado-muni"


def hechos(**cambios) -> HechosIncidente:
    datos = {k: v for k, v in HECHOS_CIBERATAQUE.items() if k != "resumen"}
    return HechosIncidente(**(datos | cambios))


class TestAcceso(unittest.TestCase):
    def test_un_caso_de_otra_organizacion_se_ve_como_inexistente(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(ROBLES, "Enviamos una planilla por error.")
        self.assertEqual(canal.caso_de_organizacion(ROBLES, caso.id).id, caso.id)
        with self.assertRaises(CasoAjeno):
            canal.caso_de_organizacion(MUNI, caso.id)
        with self.assertRaises(CasoAjeno):
            canal.caso_de_organizacion(MUNI, "no-existe-0001")
        with self.assertRaises(CasoAjeno):
            canal.validar(MUNI, caso.id, por=POR)
        with self.assertRaises(CasoAjeno):
            canal.corregir_hechos(MUNI, caso.id, hechos(), motivo="error_ia", por=POR)
        self.assertEqual([c.id for c in canal.casos_de_organizacion(MUNI)], [])


class TestCorregirHechos(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioCasos()
        self.canal, self.reloj, _ = crear_canal(
            ClienteFalso(registrar_hechos=HECHOS_CIBERATAQUE), repositorio=self.repo
        )
        self.caso = self.canal.recibir_incidente(MUNI, "Accedieron sin permiso al sistema.")
        self.reloj.avanzar(minutes=21)

    def corregir(self, **cambios):
        return self.canal.corregir_hechos(
            MUNI, self.caso.id, hechos(**cambios), motivo="confirmado_por_area", por=POR
        )

    def test_el_motor_recalcula_y_quita_el_reloj_de_la_anci(self):
        self.assertEqual(self.caso.resultado_incidente.reporte_anci.decision, "si")
        self.assertEqual(self.caso.asignacion.urgencia, "inmediata")
        caso = self.corregir(ciberincidente="no", vulneracion="comunicacion_no_autorizada")
        self.assertEqual(caso.resultado_incidente.reporte_anci.decision, "no")
        self.assertEqual(caso.resultado_incidente.aviso_agencia.decision, "si")
        self.assertNotIn("informatica", [d.id for d in caso.asignacion.destinos])
        self.assertEqual(caso.asignacion.urgencia, "alta")

    def test_la_propuesta_de_la_ia_se_conserva(self):
        caso = self.corregir(ciberincidente="no")
        self.assertEqual(caso.hechos_incidente.ciberincidente, "si")
        self.assertEqual(caso.hechos_vigentes.ciberincidente, "no")
        self.assertEqual(caso.correcciones[0].cambios, {"ciberincidente": ["si", "no"]})

    def test_el_plazo_sigue_contando_desde_el_ingreso(self):
        caso = self.corregir(titulares_aprox=40)
        self.assertEqual(
            caso.resultado_incidente.reporte_anci.vence, self.caso.ingreso + timedelta(hours=3)
        )

    def test_queda_en_la_evidencia_sin_la_nota(self):
        caso = self.canal.corregir_hechos(
            MUNI,
            self.caso.id,
            hechos(ciberincidente="no"),
            motivo="otro",
            nota="Lo confirmó Informática por teléfono.",
            por=POR,
        )
        evento = next(e for e in caso.eventos if e.tipo == "hechos_corregidos")
        self.assertEqual(evento.detalle["cambios"], {"ciberincidente": ["si", "no"]})
        self.assertEqual(evento.detalle["por"], POR)
        self.assertTrue(evento.detalle["con_nota"])
        volcado = "".join(a.model_dump_json() for a in self.repo.evidencia())
        self.assertNotIn("Informática por teléfono", volcado)
        self.assertTrue(self.repo.verificar_evidencia().integra)

    def test_sin_cambios_o_con_nota_real_se_rechaza(self):
        with self.assertRaises(AccionInvalida):
            self.corregir()
        with self.assertRaises(DatosNoSinteticosError):
            self.canal.corregir_hechos(
                MUNI,
                self.caso.id,
                hechos(ciberincidente="no"),
                motivo="otro",
                nota="Escribir a alguien@gmail.com",
                por=POR,
            )

    def test_una_solicitud_no_se_corrige_aqui(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(ROBLES, "Quiero mis datos.", nombre=NOMBRE, contacto=CORREO)
        with self.assertRaises(AccionInvalida):
            canal.corregir_hechos(ROBLES, caso.id, hechos(), motivo="error_ia", por=POR)

    def test_si_la_ia_cayo_el_delegado_completa_los_hechos(self):
        canal, *_ = crear_canal(ClienteCaido())
        caso = canal.recibir_incidente(MUNI, "Algo raro pasó con los datos.")
        self.assertEqual(caso.estado, "requiere_revision")
        with self.assertRaises(AccionInvalida):
            canal.validar(MUNI, caso.id, por=POR)
        caso = canal.corregir_hechos(
            MUNI, caso.id, hechos(ciberincidente="no"), motivo="error_ia", por=POR
        )
        self.assertEqual(caso.estado, "interpretado")
        self.assertEqual(caso.relojes_anci_posibles, [])
        self.assertIsNotNone(caso.resultado_incidente)


class TestDudasYValidacion(unittest.TestCase):
    def setUp(self):
        dudoso = HECHOS_INCIDENTE | {"categorias_especiales": [], "ciberincidente": "dudoso"}
        self.canal, *_ = crear_canal(ClienteFalso(registrar_hechos=dudoso))
        self.caso = self.canal.recibir_incidente(MUNI, "Se vio una planilla de otra área.")
        self.dudas = [d.id for d in por_resolver(self.caso)]

    def test_no_se_valida_con_dudas_pendientes(self):
        self.assertIn("reporte_anci", self.dudas)
        with self.assertRaises(AccionInvalida) as error:
            self.canal.validar(MUNI, self.caso.id, por=POR)
        self.assertIn("Revisar", str(error.exception))

    def test_resolver_y_validar(self):
        for deber in self.dudas:
            self.canal.resolver_deber(
                MUNI, self.caso.id, deber, "no", motivo="datos_revisados", por=POR
            )
        caso = self.canal.validar(MUNI, self.caso.id, por=POR)
        self.assertEqual(caso.validacion.por, POR)
        evento = caso.eventos[-1]
        self.assertEqual(evento.tipo, "validado")
        self.assertEqual(evento.detalle["deberes"]["reporte_anci"], "no")
        anci = caso.resultado_incidente.reporte_anci
        self.assertEqual(anci.decision, "revisar")  # el motor no cambia: decide la persona
        self.assertEqual(decision_final(caso, anci), "no")
        with self.assertRaises(AccionInvalida):
            self.canal.validar(MUNI, self.caso.id, por=POR)

    def test_solo_se_resuelve_lo_que_esta_en_duda(self):
        with self.assertRaises(AccionInvalida):
            self.canal.resolver_deber(
                MUNI, self.caso.id, "aviso_agencia", "no", motivo="otro", por=POR
            )
        with self.assertRaises(AccionInvalida):
            self.canal.resolver_deber(
                MUNI, self.caso.id, self.dudas[0], "talvez", motivo="otro", por=POR
            )

    def test_corregir_despues_de_validar_anula_la_validacion(self):
        for deber in self.dudas:
            self.canal.resolver_deber(MUNI, self.caso.id, deber, "no", motivo="otro", por=POR)
        self.canal.validar(MUNI, self.caso.id, por=POR)
        caso = self.canal.corregir_hechos(
            MUNI, self.caso.id, hechos(ciberincidente="si"), motivo="informacion_nueva", por=POR
        )
        self.assertIsNone(caso.validacion)
        self.assertIn("validacion_anulada", [e.tipo for e in caso.eventos])

    def test_una_solicitud_esperando_al_titular_no_se_valida(self):
        canal, *_ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_AMBIGUA))
        caso = canal.recibir_solicitud(ROBLES, "No más correos.", nombre=NOMBRE, contacto=CORREO)
        with self.assertRaises(AccionInvalida):
            canal.validar(ROBLES, caso.id, por=POR)


class TestIdentidad(unittest.TestCase):
    def test_abrir_deja_constancia_sin_la_identidad(self):
        repo = RepositorioCasos()
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE), repositorio=repo)
        caso = canal.recibir_incidente(
            ROBLES, "Un aviso reservado.", reservado=True, nombre=NOMBRE, contacto=CORREO
        )
        identidad = canal.abrir_identidad(
            ROBLES, caso.id, motivo="contactar_a_quien_reporto", por=POR
        )
        self.assertEqual(identidad["nombre"], NOMBRE)
        caso = canal.obtener(caso.id)
        self.assertEqual(caso.eventos[-1].tipo, "identidad_abierta")
        volcado = json.dumps([a.model_dump(mode="json") for a in repo.evidencia()])
        self.assertNotIn(NOMBRE, volcado)
        self.assertNotIn(CORREO, volcado)

    def test_sin_identidad_o_sin_llave(self):
        canal, *_ = crear_canal(ClienteFalso(registrar_hechos=HECHOS_INCIDENTE))
        caso = canal.recibir_incidente(ROBLES, "Un aviso con nombre visible.", nombre=NOMBRE)
        with self.assertRaises(AccionInvalida):
            canal.abrir_identidad(ROBLES, caso.id, motivo="otro", por=POR)
        reservado = canal.recibir_incidente(ROBLES, "Otro aviso.", reservado=True, nombre=NOMBRE)
        canal._llaves = None
        with self.assertRaises(AccionInvalida):
            canal.abrir_identidad(ROBLES, reservado.id, motivo="otro", por=POR)


if __name__ == "__main__":
    unittest.main()
