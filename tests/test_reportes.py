import re
import unittest
from datetime import datetime

from privacidad.canal.delegado import AccionInvalida, CasoAjeno
from privacidad.canal.modelos import ZONA_CHILE
from privacidad.corpus import corpus_por_defecto
from privacidad.motor import HechosIncidente
from privacidad.reportes import (
    Borrador,
    DatosPersonalesEnBorrador,
    SinBorrador,
    huella_sin_digitos,
    revisar_datos_personales,
    ultima_revision,
)

from .canal_apoyo import (
    HECHOS_CIBERATAQUE,
    HECHOS_INCIDENTE,
    SOLICITUD_CLARA,
    ClienteCaido,
    ClienteFalso,
    crear_canal,
    rut_ficticio,
)

MUNI = "municipalidad-piloto"
ROBLES = "comercial-los-robles"
NOMBRE = "Rosa Valdivia Ficticia"
CORREO = "rosa@municipalidad-piloto.example"
MOVIL = "+56 9 0000 1234"
RUT = rut_ficticio(7)
TEXTO = (
    f"Entraron al servidor de beneficios con la clave de {NOMBRE}, RUT {RUT}, "
    f"correo {CORREO}, móvil {MOVIL}. Nació el 03/05/1990."
)
RESUMEN = f"{NOMBRE} reportó un acceso indebido"


def canal_con(hechos: dict | None):
    entrada = None if hechos is None else hechos | {"resumen": RESUMEN}
    cliente = ClienteFalso(registrar_hechos=entrada) if hechos is not None else ClienteCaido()
    return crear_canal(cliente)


def datos_de_personas(texto: str) -> list[str]:
    """Lo que nunca debe aparecer: lo que escribió la persona y su identidad."""
    rut_cuerpo = RUT.split("-")[0].replace(".", "")
    return [
        dato
        for dato in (NOMBRE, "Rosa", CORREO, MOVIL, "0000 1234", RUT, rut_cuerpo, "1990", "03/05")
        if dato in texto.replace(".", "") or dato in texto
    ]


class TestBorradoresDeCiberataque(unittest.TestCase):
    def setUp(self):
        self.canal, self.reloj, _ = canal_con(HECHOS_CIBERATAQUE | {"titulares_aprox": 340})
        self.cliente = self.canal._cliente
        self.caso = self.canal.recibir_incidente(MUNI, TEXTO, nombre=NOMBRE, contacto=CORREO)
        _, self.borradores = self.canal.borradores(MUNI, self.caso.id)

    def test_municipio_con_ciberataque_tiene_ambos_borradores(self):
        self.assertIsInstance(self.borradores["agencia"], Borrador)
        self.assertIsInstance(self.borradores["anci"], Borrador)

    def test_anci_no_lleva_datos_personales_ni_texto_del_reporte(self):
        texto = self.borradores["anci"].texto()
        self.assertEqual(datos_de_personas(texto), [])
        self.assertNotIn("beneficios", texto)  # tampoco el relato
        self.assertNotIn("@", texto)
        self.assertEqual([d for d in re.findall(r"\d{1,2}/\d{1,2}/\d{4}", texto)], [])

    def test_agencia_no_lleva_el_texto_ni_la_identidad_pero_si_el_contacto_del_delegado(self):
        texto = self.borradores["agencia"].texto()
        self.assertEqual(datos_de_personas(texto), [])
        self.assertIn("delegado@municipalidad-piloto.example", texto)

    def test_los_borradores_se_arman_sin_ia(self):
        llamadas = len(self.cliente.llamadas)
        self.canal.borradores(MUNI, self.caso.id)
        self.assertEqual(len(self.cliente.llamadas), llamadas)

    def test_mismo_caso_mismo_texto(self):
        _, otra_vez = self.canal.borradores(MUNI, self.caso.id)
        for destino in ("agencia", "anci"):
            self.assertEqual(otra_vez[destino].huella, self.borradores[destino].huella)

    def test_anci_trae_los_tres_vencimientos_del_motor(self):
        plazos = {p.id: p.vence for p in self.caso.resultado_incidente.plazos_anci}
        vences = [s.vence for s in self.borradores["anci"].secciones]
        self.assertEqual(
            vences,
            [
                plazos["anci_alerta_temprana"],
                plazos["anci_actualizacion"],
                plazos["anci_informe_final"],
            ],
        )

    def test_lo_que_no_se_sabe_queda_por_completar(self):
        anci = self.borradores["anci"]
        self.assertIn("tipo de amenaza o causa principal probable", anci.por_completar)
        self.assertIn("Alrededor de 340 personas.", anci.texto())
        agencia = self.borradores["agencia"]
        self.assertIn("medidas para evitar que se repita", agencia.por_completar)

    def test_menores_obligan_a_avisar_a_cada_persona(self):
        texto = self.borradores["agencia"].texto()
        self.assertIn("Corresponde avisar a cada persona afectada", texto)

    def test_registro_afectado_sale_de_las_palabras_no_del_tipo(self):
        # Informática recibe el caso por ser ciberincidente, pero ninguna de sus palabras aparece.
        caso = self.canal.recibir_incidente(MUNI, "Accedieron a las postulaciones de beneficios.")
        _, b = self.canal.borradores(MUNI, caso.id)
        self.assertIn("informatica", [d.id for d in caso.asignacion.destinos])
        texto = b["agencia"].texto()
        self.assertIn("Postulaciones a beneficios y fichas sociales", texto)
        self.assertNotIn("Sistemas, correo y equipos", texto)

    def test_cada_cita_existe_en_el_texto_oficial(self):
        corpus = corpus_por_defecto()
        for b in self.borradores.values():
            for c in b.citas:
                r = corpus.verificar_cita(c.norma, c.articulo, c.fragmento)
                self.assertTrue(r.existe and r.fragmento_encontrado, c)

    def test_nota_de_vigencia_antes_del_1_de_diciembre(self):
        canal, reloj, _ = canal_con(HECHOS_CIBERATAQUE)
        reloj.ahora = datetime(2026, 11, 2, 9, 0, tzinfo=ZONA_CHILE)
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al servidor.")
        _, b = canal.borradores(MUNI, caso.id)
        self.assertTrue(
            any("Exigible desde el 1 de diciembre de 2026" in a for a in b["agencia"].avisos)
        )

    def test_identidad_reservada_tampoco_aparece(self):
        caso = self.canal.recibir_incidente(
            MUNI, TEXTO, nombre=NOMBRE, contacto=CORREO, reservado=True
        )
        _, b = self.canal.borradores(MUNI, caso.id)
        for borrador in b.values():
            self.assertEqual(datos_de_personas(borrador.texto()), [])


class TestCuandoNoHayBorrador(unittest.TestCase):
    def test_empresa_privada_no_reporta_a_la_anci(self):
        canal, _, _ = canal_con(HECHOS_CIBERATAQUE)
        caso = canal.recibir_incidente(ROBLES, "Entraron sin permiso al servidor de la nómina.")
        _, b = canal.borradores(ROBLES, caso.id)
        self.assertIsInstance(b["agencia"], Borrador)
        self.assertIsInstance(b["anci"], SinBorrador)
        self.assertIn("servicio esencial", b["anci"].motivo)

    def test_papel_perdido_en_el_municipio_no_va_a_la_anci(self):
        canal, _, _ = canal_con(HECHOS_INCIDENTE)
        caso = canal.recibir_incidente(MUNI, "Se envió una planilla de beneficios por error.")
        _, b = canal.borradores(MUNI, caso.id)
        self.assertIsInstance(b["anci"], SinBorrador)

    def test_si_la_ia_no_respondio_pide_completar_hechos(self):
        canal, _, _ = canal_con(None)
        caso = canal.recibir_incidente(MUNI, "Algo pasó con el servidor.")
        _, b = canal.borradores(MUNI, caso.id)
        for s in b.values():
            self.assertIsInstance(s, SinBorrador)
            self.assertIn("completa los hechos", s.motivo)

    def test_solicitud_de_titular_no_se_reporta(self):
        canal, _, _ = crear_canal(ClienteFalso(interpretar_solicitud=SOLICITUD_CLARA))
        caso = canal.recibir_solicitud(
            ROBLES, "Quiero saber qué datos tienen de mí.", nombre="Ana", contacto=CORREO
        )
        _, b = canal.borradores(ROBLES, caso.id)
        self.assertTrue(all(isinstance(s, SinBorrador) for s in b.values()))

    def test_revisar_queda_avisado_y_un_no_del_delegado_quita_el_borrador(self):
        canal, _, _ = canal_con(HECHOS_INCIDENTE | {"riesgo_mitigado": True})
        caso = canal.recibir_incidente(MUNI, "Se perdió un pendrive cifrado con la planilla.")
        _, b = canal.borradores(MUNI, caso.id)
        self.assertEqual(b["agencia"].decision, "revisar")
        self.assertTrue(any("«Decide tú»" in a for a in b["agencia"].avisos))
        canal.resolver_deber(
            MUNI, caso.id, "aviso_agencia", "no", motivo="datos_revisados", por="delegado-muni"
        )
        _, b = canal.borradores(MUNI, caso.id)
        self.assertIsInstance(b["agencia"], SinBorrador)

    def test_hechos_corregidos_por_el_delegado_cambian_el_borrador(self):
        canal, _, _ = canal_con(HECHOS_CIBERATAQUE)
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al servidor.")
        corregidos = HechosIncidente(**(HECHOS_CIBERATAQUE | {"titulares_aprox": 25}))
        canal.corregir_hechos(
            MUNI, caso.id, corregidos, motivo="informacion_nueva", por="delegado-muni"
        )
        _, b = canal.borradores(MUNI, caso.id)
        self.assertIn("Alrededor de 25 personas.", b["anci"].texto())


class TestBorradorConDatoPersonalNoSeEntrega(unittest.TestCase):
    def test_si_algo_se_cuela_el_borrador_no_se_entrega(self):
        from privacidad.reportes import borradores_del_caso

        canal, _, _ = canal_con(HECHOS_CIBERATAQUE)
        caso = canal.recibir_incidente(MUNI, "Accedieron sin permiso al servidor.")
        org = canal._organizaciones[MUNI].model_copy(update={"nombre": f"Municipio {MOVIL}"})
        b = borradores_del_caso(caso, org, canal._enrutamiento.organizaciones[MUNI])
        for destino in ("agencia", "anci"):
            self.assertIsInstance(b[destino], SinBorrador)
            self.assertIn("parece un dato personal (telefono)", b[destino].motivo)
            self.assertNotIn("0000", b[destino].motivo)


class TestRevisionDeDatosPersonales(unittest.TestCase):
    def test_rechaza_rut_correo_telefono_y_fecha_sin_mostrar_el_valor(self):
        for texto in (f"RUT {RUT}", f"escribir a {CORREO}", f"llamar al {MOVIL}", "el 03/05/1990"):
            with self.assertRaises(DatosPersonalesEnBorrador) as e:
                revisar_datos_personales(texto)
            self.assertNotIn(texto.split()[-1], str(e.exception))

    def test_permite_el_contacto_institucional(self):
        revisar_datos_personales("Contacto: delegado@x.example", frozenset({"delegado@x.example"}))

    def test_huella_con_letras_vuelve_a_la_original(self):
        original = "0123456789abcdef" * 4
        letras = huella_sin_digitos(original)
        self.assertIsNone(re.search(r"\d", letras))
        vuelta = letras.translate(str.maketrans("ghijklmnop", "0123456789"))
        self.assertEqual(vuelta, original)


class TestMarcarRevisado(unittest.TestCase):
    def setUp(self):
        self.canal, self.reloj, _ = canal_con(HECHOS_CIBERATAQUE)
        self.caso = self.canal.recibir_incidente(MUNI, TEXTO)
        _, self.b = self.canal.borradores(MUNI, self.caso.id)

    def marcar(self, destino="anci", huella=None, org=MUNI):
        return self.canal.marcar_borrador_revisado(
            org, self.caso.id, destino, huella or self.b[destino].huella, por="delegado-muni"
        )

    def test_queda_en_la_evidencia_con_la_huella_y_sin_el_texto(self):
        self.reloj.avanzar(minutes=20)
        caso = self.marcar()
        evento = caso.eventos[-1]
        self.assertEqual(evento.tipo, "borrador_revisado")
        self.assertEqual(evento.detalle["huella"], huella_sin_digitos(self.b["anci"].huella))
        self.assertEqual(evento.detalle["por_completar"], len(self.b["anci"].por_completar))
        self.assertTrue(self.canal._repo.verificar_evidencia().integra)
        anotada = self.canal._repo.evidencia(caso.id)[-1]
        self.assertEqual(anotada.tipo, "borrador_revisado")
        self.assertNotIn("Alerta temprana", str(anotada.detalle))
        revision = ultima_revision(caso, self.b["anci"])
        self.assertTrue(revision.vigente)

    def test_una_huella_antigua_se_rechaza(self):
        with self.assertRaises(AccionInvalida):
            self.marcar(huella="0" * 64)

    def test_si_cambian_los_hechos_la_revision_deja_de_estar_vigente(self):
        self.marcar()
        corregidos = HechosIncidente(**(HECHOS_CIBERATAQUE | {"interrupcion_servicio": True}))
        self.canal.corregir_hechos(
            MUNI, self.caso.id, corregidos, motivo="informacion_nueva", por="delegado-muni"
        )
        caso, b = self.canal.borradores(MUNI, self.caso.id)
        self.assertFalse(ultima_revision(caso, b["anci"]).vigente)

    def test_destino_sin_borrador_no_se_marca(self):
        canal, _, _ = canal_con(HECHOS_INCIDENTE)
        caso = canal.recibir_incidente(MUNI, "Se envió una planilla por error.")
        with self.assertRaises(AccionInvalida):
            canal.marcar_borrador_revisado(MUNI, caso.id, "anci", "x" * 64, por="d")

    def test_otra_organizacion_no_alcanza_el_caso(self):
        with self.assertRaises(CasoAjeno):
            self.marcar(org=ROBLES)


if __name__ == "__main__":
    unittest.main()
