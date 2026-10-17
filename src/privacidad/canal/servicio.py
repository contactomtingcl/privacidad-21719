"""Servicio del canal: recibe reportes, interpreta, pide confirmación y deja los casos listos.

Quién hace qué:

- La IA solo propone hechos (qué derecho parece ejercer el titular, qué pasó en un incidente) y
  solo recibe texto enmascarado: las funciones de `interpretacion` enmascaran antes de llamarla.
- El motor de reglas decide plazos y deberes. Si la IA falla, el caso queda "requiere revisión",
  nada se marca como "sin deber" y el reloj corre igual.
- La confirmación con el titular y la validación final son de personas.
- Cada caso se enruta al delegado y al área dueña de los datos con reglas escritas
  (`enrutamiento.py`), sin IA; cada cambio de destino queda como evento en la evidencia.

Solo datos ficticios: antes de procesar, la guardia rechaza lo que parezca un RUT, correo o
móvil reales. En modo reservado la identidad se cifra con la llave de reserva; si esa llave no
está configurada el reporte se rechaza, nunca se guarda la identidad en claro.
"""

from __future__ import annotations

import copy
import secrets
from collections.abc import Callable, Mapping
from datetime import datetime

from cryptography.fernet import MultiFernet

from .. import guardia
from ..ia.cliente import MODELO_EXTRACCION, MODELO_RAPIDO
from ..interpretacion import extraer_hechos, interpretar_solicitud
from ..interpretacion.comun import ClienteLLM
from ..interpretacion.incidentes import ExtraccionIncidente
from ..interpretacion.respaldo import resumen_respaldos
from ..interpretacion.solicitudes import InterpretacionSolicitud
from ..motor import HechosIncidente, HechosSolicitud, decidir_incidente, decidir_solicitud
from . import confirmacion as conf
from .confirmacion import RespuestaInvalida
from .delegado import AccionesDelegado
from .enlaces import enlace_canal, firma_valida
from .enrutamiento import ReglasEnrutamiento, cargar_reglas_enrutamiento, enrutar
from .modelos import Caso, Organizacion, TipoReporte, ahora_chile
from .repositorio import RepositorioCasos
from .reservado import cifrar_identidad

LARGO_MINIMO_TEXTO = 5
LARGO_MAXIMO_TEXTO = 5000
LARGO_MAXIMO_CAMPO = 200
TIPOS_INCIDENTE: tuple[TipoReporte, ...] = ("incidente", "aviso_proveedor")

# Si la IA no responde, así se muestran los relojes de la ANCI: como si fuera un ciberincidente
# dudoso (el motor lo marca "revisar" y calcula los vencimientos desde que se supo).
_HECHOS_PEOR_CASO = HechosIncidente(
    datos_personales=True, vulneracion="filtracion", ciberincidente="dudoso"
)


class ErrorCanal(Exception):
    """Base de los errores del canal."""


class OrganizacionDesconocida(ErrorCanal):
    """El enlace no corresponde a ninguna organización (o fue reemplazado)."""


class CasoNoEncontrado(ErrorCanal):
    pass


class ReservadoNoDisponible(ErrorCanal):
    """Se pidió modo reservado pero no hay llave de reserva configurada."""


def _nuevo_id() -> str:
    """Código de seguimiento aleatorio. Nunca empieza con guion, para que la línea de comandos
    no lo confunda con una opción (`--caso -abc…`)."""
    while True:
        codigo = secrets.token_urlsafe(12)
        if codigo[0] != "-":
            return codigo


class CanalReporte(AccionesDelegado):
    def __init__(
        self,
        *,
        organizaciones: Mapping[str, Organizacion],
        repositorio: RepositorioCasos,
        cliente: ClienteLLM | None,
        secreto_enlaces: bytes,
        llaves_reservadas: MultiFernet | None = None,
        reloj: Callable[[], datetime] = ahora_chile,
        nuevo_id: Callable[[], str] = _nuevo_id,
        modelo_solicitudes: str = MODELO_RAPIDO,
        modelo_incidentes: str = MODELO_EXTRACCION,
        enrutamiento: ReglasEnrutamiento | None = None,
    ) -> None:
        self._organizaciones = dict(organizaciones)
        self._enrutamiento = enrutamiento or cargar_reglas_enrutamiento()
        sin_reglas = sorted(set(self._organizaciones) - set(self._enrutamiento.organizaciones))
        if sin_reglas:
            raise ValueError(f"Organizaciones sin reglas de enrutamiento: {', '.join(sin_reglas)}")
        self._repo = repositorio
        self._cliente = cliente
        self._secreto = secreto_enlaces
        self._llaves = llaves_reservadas
        self._reloj = reloj
        self._nuevo_id = nuevo_id
        self._modelo_solicitudes = modelo_solicitudes
        self._modelo_incidentes = modelo_incidentes

    def con_repositorio(self, repositorio: RepositorioCasos) -> CanalReporte:
        """El mismo canal (organizaciones, IA, secretos, reglas) sobre otro almacén de casos. Lo
        usan las salas de la demo: una copia propia por participante."""
        copia = copy.copy(self)
        copia._repo = repositorio
        return copia

    # --- enlaces ---------------------------------------------------------------------

    @property
    def reservado_disponible(self) -> bool:
        return self._llaves is not None

    def organizacion_por_enlace(self, id_organizacion: str, firma: str) -> Organizacion:
        org = self._organizaciones.get(id_organizacion)
        if not org or not firma_valida(org.id, org.version_enlace, firma, self._secreto):
            raise OrganizacionDesconocida(id_organizacion)
        return org

    def enlace(self, id_organizacion: str, base_url: str) -> str:
        org = self._organizaciones.get(id_organizacion)
        if not org:
            raise OrganizacionDesconocida(id_organizacion)
        return enlace_canal(base_url, org.id, org.version_enlace, self._secreto)

    # --- validación de lo que escribe la persona ----------------------------------------

    @staticmethod
    def _limpiar(texto: str | None, campo: str, *, obligatorio: bool, maximo: int) -> str | None:
        valor = (texto or "").strip()
        if not valor:
            if obligatorio:
                raise RespuestaInvalida(f"Falta completar: {campo}")
            return None
        if len(valor) > maximo:
            raise RespuestaInvalida(f"{campo[0].upper()}{campo[1:]}: máximo {maximo} caracteres")
        return valor

    def _texto(self, texto: str | None) -> str:
        valor = self._limpiar(texto, "el mensaje", obligatorio=True, maximo=LARGO_MAXIMO_TEXTO)
        assert valor is not None
        if len(valor) < LARGO_MINIMO_TEXTO:
            raise RespuestaInvalida("Cuéntenos con un poco más de detalle")
        return valor

    @staticmethod
    def _solo_sintetico(**campos: str | None) -> None:
        guardia.exigir_sintetico({k: v for k, v in campos.items() if v})

    def _organizacion(self, id_organizacion: str) -> Organizacion:
        org = self._organizaciones.get(id_organizacion)
        if not org:
            raise OrganizacionDesconocida(id_organizacion)
        return org

    # --- solicitudes de titulares -----------------------------------------------------

    def recibir_solicitud(
        self, id_organizacion: str, texto: str, *, nombre: str | None, contacto: str | None
    ) -> Caso:
        """Mensaje de un titular. El artículo 11 exige identificar a la persona y un medio
        para responderle, por eso nombre y contacto son obligatorios aquí."""
        self._organizacion(id_organizacion)
        texto = self._texto(texto)
        nombre = self._limpiar(nombre, "su nombre", obligatorio=True, maximo=LARGO_MAXIMO_CAMPO)
        contacto = self._limpiar(
            contacto, "un correo para responderle", obligatorio=True, maximo=LARGO_MAXIMO_CAMPO
        )
        self._solo_sintetico(texto=texto, nombre=nombre, contacto=contacto)

        ahora = self._reloj()
        caso = Caso(
            id=self._nuevo_id(),
            id_organizacion=id_organizacion,
            tipo="solicitud",
            ingreso=ahora,
            texto=texto,
            estado="requiere_revision",
            identidad={"nombre": nombre or "", "contacto": contacto or ""},
        )
        caso.registrar("recibido", ahora, tipo="solicitud")

        interpretacion = self._interpretar_solicitud(texto)
        caso.costo_usd = interpretacion.costo_usd
        caso.resumen_ia = interpretacion.resumen
        caso.respaldos_ia = interpretacion.respaldos
        hechos = interpretacion.hechos
        if hechos is None:
            # La IA no respondió: el plazo corre igual y el caso va a revisión humana.
            caso.error_ia = interpretacion.error
            caso.resultado_solicitud = decidir_solicitud(
                HechosSolicitud(es_solicitud=True), ahora.date()
            )
            caso.registrar("ia_sin_respuesta", ahora, error=interpretacion.error)
        elif not hechos.es_solicitud:
            caso.hechos_solicitud = hechos
            caso.estado = "sin_solicitud"
            caso.registrar(
                "interpretado", ahora, es_solicitud=False, modelo=self._modelo_solicitudes
            )
        else:
            caso.hechos_solicitud = hechos
            caso.confirmacion = conf.preparar(hechos, ahora)
            caso.estado = (
                "pendiente_confirmacion"
                if caso.confirmacion.estado == "pendiente"
                else "interpretado"
            )
            caso.registrar(
                "interpretado",
                ahora,
                es_solicitud=True,
                derechos=list(hechos.derechos),
                requiere_confirmacion=hechos.requiere_confirmacion,
                modelo=self._modelo_solicitudes,
                **resumen_respaldos(caso.respaldos_ia),
            )
            if caso.confirmacion.estado == "pendiente":
                caso.registrar(
                    "confirmacion_solicitada",
                    ahora,
                    espera_hasta=caso.confirmacion.espera_hasta.isoformat()
                    if caso.confirmacion.espera_hasta
                    else None,
                )
            self._recalcular_plazos(caso)
        self._enrutar(caso, ahora)
        self._repo.guardar(caso)
        return caso

    def _enrutar(self, caso: Caso, ahora: datetime) -> None:
        """Decide a quién le llega el caso. Solo se anota en la evidencia si cambió algo."""
        nueva = enrutar(caso, self._enrutamiento, ahora)
        anterior = caso.asignacion
        caso.asignacion = nueva
        if anterior is None or anterior.para_evidencia() != nueva.para_evidencia():
            caso.registrar("enrutado", ahora, **nueva.para_evidencia())

    def _interpretar_solicitud(self, texto: str) -> InterpretacionSolicitud:
        if self._cliente is None:
            return InterpretacionSolicitud(hechos=None, error="sin_ia")
        return interpretar_solicitud(texto, self._cliente, self._modelo_solicitudes)

    def _recalcular_plazos(self, caso: Caso) -> None:
        """El plazo siempre se cuenta desde el ingreso, aunque la lectura cambie después."""
        assert caso.confirmacion is not None
        caso.resultado_solicitud = decidir_solicitud(
            conf.hechos_vigentes(caso.confirmacion), caso.ingreso.date()
        )

    def responder_confirmacion(
        self, id_caso: str, *, derechos: list[str], detalle: str | None = None
    ) -> Caso:
        """El titular confirma o corrige lo que entendió el sistema."""
        caso = self.obtener(id_caso)
        if caso.tipo != "solicitud" or caso.confirmacion is None:
            raise RespuestaInvalida("Este caso no tiene una lectura que confirmar")
        detalle = self._limpiar(
            detalle, "el detalle", obligatorio=False, maximo=conf.LARGO_MAXIMO_DETALLE
        )
        self._solo_sintetico(detalle=detalle)
        ahora = self._reloj()
        propuesta = list(caso.confirmacion.propuesta)
        caso.confirmacion = conf.aplicar_respuesta(caso.confirmacion, derechos, detalle, ahora)
        caso.estado = "interpretado"
        self._recalcular_plazos(caso)
        caso.registrar(
            "confirmacion_respondida",
            ahora,
            resultado=caso.confirmacion.estado,
            propuesta=propuesta,
            vigente=list(caso.confirmacion.vigente),
            con_detalle=bool(caso.confirmacion.detalle),
        )
        self._enrutar(caso, ahora)
        self._repo.guardar(caso)
        return caso

    def resolver_vencidas(self) -> list[Caso]:
        """Aplica la lectura por defecto a toda confirmación cuyo tiempo de espera terminó."""
        resueltos = []
        for caso in self._repo.listar():
            if self._resolver_si_vence(caso):
                resueltos.append(caso)
        return resueltos

    def _resolver_si_vence(self, caso: Caso) -> bool:
        ahora = self._reloj()
        if not conf.vencida(caso.confirmacion, ahora):
            return False
        assert caso.confirmacion is not None
        propuesta = list(caso.confirmacion.propuesta)
        caso.confirmacion = conf.aplicar_por_defecto(caso.confirmacion, ahora)
        caso.estado = "interpretado"
        self._recalcular_plazos(caso)
        caso.registrar(
            "confirmacion_por_defecto",
            ahora,
            propuesta=propuesta,
            vigente=list(caso.confirmacion.vigente),
            criterio="lectura reversible, sin supresión (regla confirmacion_titular)",
        )
        self._enrutar(caso, ahora)
        self._repo.guardar(caso)
        return True

    # --- incidentes y avisos de proveedores --------------------------------------------

    def recibir_incidente(
        self,
        id_organizacion: str,
        texto: str,
        *,
        tipo: TipoReporte = "incidente",
        reservado: bool = False,
        nombre: str | None = None,
        contacto: str | None = None,
    ) -> Caso:
        """Reporte de una persona de la organización o aviso de un proveedor.

        La identidad es opcional. Con `reservado` se cifra con la llave de reserva;
        sin él, queda visible para el equipo. Sin nombre ni contacto el reporte es anónimo.
        """
        if tipo not in TIPOS_INCIDENTE:
            raise RespuestaInvalida("Tipo de reporte desconocido")
        org = self._organizacion(id_organizacion)
        texto = self._texto(texto)
        nombre = self._limpiar(nombre, "su nombre", obligatorio=False, maximo=LARGO_MAXIMO_CAMPO)
        contacto = self._limpiar(
            contacto, "el contacto", obligatorio=False, maximo=LARGO_MAXIMO_CAMPO
        )
        self._solo_sintetico(texto=texto, nombre=nombre, contacto=contacto)
        if reservado and self._llaves is None:
            raise ReservadoNoDisponible("El modo reservado no está configurado en este canal")

        ahora = self._reloj()  # desde aquí corre "se tuvo conocimiento"
        id_caso = self._nuevo_id()
        caso = Caso(
            id=id_caso,
            id_organizacion=id_organizacion,
            tipo=tipo,
            ingreso=ahora,
            texto=texto,
            estado="requiere_revision",
            reservado=reservado,
        )
        identidad = {k: v for k, v in (("nombre", nombre), ("contacto", contacto)) if v}
        if identidad and reservado and self._llaves is not None:
            caso.identidad_cifrada = cifrar_identidad(self._llaves, identidad, id_caso)
        elif identidad:
            caso.identidad = identidad
        caso.registrar(
            "recibido",
            ahora,
            tipo=tipo,
            reservado=reservado,
            con_identidad=bool(identidad),
        )

        extraccion = self._extraer(texto)
        caso.costo_usd = extraccion.costo_usd
        caso.resumen_ia = extraccion.resumen
        caso.respaldos_ia = extraccion.respaldos
        if extraccion.hechos is None:
            caso.error_ia = extraccion.error
            posibles = decidir_incidente(_HECHOS_PEOR_CASO, org.perfil, ahora)
            if posibles.reporte_anci.decision != "no":
                caso.relojes_anci_posibles = [posibles.reporte_anci, *posibles.plazos_anci]
            caso.registrar("ia_sin_respuesta", ahora, error=extraccion.error)
        else:
            caso.hechos_incidente = extraccion.hechos
            caso.resultado_incidente = decidir_incidente(extraccion.hechos, org.perfil, ahora)
            caso.estado = "interpretado"
            resultado = caso.resultado_incidente
            caso.registrar(
                "interpretado",
                ahora,
                modelo=self._modelo_incidentes,
                aviso_agencia=resultado.aviso_agencia.decision,
                aviso_titulares=resultado.aviso_titulares.decision,
                reporte_anci=resultado.reporte_anci.decision,
                **resumen_respaldos(caso.respaldos_ia),
            )
        self._enrutar(caso, ahora)
        self._repo.guardar(caso)
        return caso

    def _extraer(self, texto: str) -> ExtraccionIncidente:
        if self._cliente is None:
            return ExtraccionIncidente(hechos=None, error="sin_ia")
        return extraer_hechos(texto, self._cliente, self._modelo_incidentes)

    # --- consulta -----------------------------------------------------------------------

    def obtener(self, id_caso: str) -> Caso:
        caso = self._repo.obtener(id_caso)
        if caso is None:
            raise CasoNoEncontrado(id_caso)
        return caso

    def seguimiento(self, id_caso: str) -> Caso:
        """Lo que ve la persona al volver con su código; antes aplica la espera vencida."""
        caso = self.obtener(id_caso)
        if self._resolver_si_vence(caso):
            caso = self.obtener(id_caso)
        return caso

    def casos_de(self, id_organizacion: str) -> list[Caso]:
        return [c for c in self._repo.listar() if c.id_organizacion == id_organizacion]


__all__ = [
    "CanalReporte",
    "CasoNoEncontrado",
    "ErrorCanal",
    "OrganizacionDesconocida",
    "RespuestaInvalida",
    "ReservadoNoDisponible",
]
