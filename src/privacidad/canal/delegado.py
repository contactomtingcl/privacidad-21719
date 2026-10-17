"""Acciones del delegado sobre un caso: corregir hechos, resolver dudas, validar, dejar constancia
de lo que envió y abrir una identidad reservada.

Las reglas que sostienen el principio "la IA interpreta, el motor decide, la persona valida":

- El delegado corrige **hechos**, nunca plazos ni deberes: con los hechos corregidos el motor
  vuelve a decidir. La propuesta original de la IA se conserva para comparar.
- Lo que el motor deja en "revisar" lo resuelve el delegado con un sí o un no y un motivo.
- No se puede validar mientras quede algo por resolver; si después se corrige algo, la
  validación anterior se anula y queda anotado.
- Validar no es enviar: el sistema no envía nada a las autoridades ni a las personas. Por cada
  cosa que corresponde, el delegado marca «Ya lo envié» (canal y hora). El caso sigue abierto
  hasta que todo lo que corresponde quede enviado.
- Cada acción deja un evento en la evidencia con el identificador del usuario y un motivo de una
  lista cerrada. Las notas libres quedan solo en el caso, nunca en la cadena.
- Un delegado solo alcanza los casos de su organización. Un caso ajeno responde igual que uno
  inexistente, para no revelar que existe.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from cryptography.fernet import MultiFernet

from .. import guardia
from ..motor import Deber, HechosIncidente, decidir_incidente
from .enrutamiento import ReglasEnrutamiento
from .evidencia import Anotacion, Verificacion
from .modelos import (
    CanalEnvio,
    Caso,
    Correccion,
    DecisionDelegado,
    Envio,
    MotivoCorreccion,
    MotivoDecision,
    MotivoIdentidad,
    Organizacion,
    Validacion,
)
from .repositorio import RepositorioCasos
from .reservado import descifrar_identidad

LARGO_MAXIMO_NOTA = 300


class AccionInvalida(Exception):
    """La acción no se puede hacer en el estado actual del caso. El mensaje es para la persona."""


class CasoAjeno(LookupError):
    """El caso no existe o es de otra organización (se tratan igual a propósito)."""


def deberes_del_caso(caso: Caso) -> list[Deber]:
    if caso.resultado_incidente is not None:
        r = caso.resultado_incidente
        return [r.aviso_agencia, r.aviso_titulares, r.reporte_anci]
    if caso.resultado_solicitud is not None:
        r = caso.resultado_solicitud
        return [d for d in (r.respuesta, r.bloqueo, r.comunicar_terceros) if d is not None]
    return []


def entregas_del_caso(caso: Caso) -> list[Deber]:
    """Lo que el delegado tiene que enviar (o hacer) porque corresponde, en orden de plazo.

    En la ANCI cuenta cada paso por separado (alerta temprana, actualización e informe final),
    porque cada uno tiene su plazo. Un deber en duda no entra hasta que el delegado lo decida.
    """
    if caso.resultado_incidente is not None:
        r = caso.resultado_incidente
        salida = [
            d for d in (r.aviso_agencia, r.aviso_titulares) if decision_final(caso, d) == "si"
        ]
        if decision_final(caso, r.reporte_anci) == "si":
            salida += r.plazos_anci or [r.reporte_anci]
        return salida
    return [d for d in deberes_del_caso(caso) if decision_final(caso, d) == "si"]


def pendientes_de_envio(caso: Caso) -> list[Deber]:
    return [d for d in entregas_del_caso(caso) if d.id not in caso.envios]


def caso_abierto(caso: Caso) -> bool:
    """Un caso sigue en la bandeja hasta validarlo y enviar todo lo que corresponde."""
    return caso.validacion is None or bool(pendientes_de_envio(caso))


def por_resolver(caso: Caso) -> list[Deber]:
    """Deberes que el motor dejó en "revisar" y que el delegado aún no decide."""
    return [
        d for d in deberes_del_caso(caso) if d.decision == "revisar" and d.id not in caso.decisiones
    ]


def decision_final(caso: Caso, deber: Deber) -> str:
    """Lo que vale para este deber: la del motor, o la del delegado si el motor dejó una duda."""
    if deber.decision == "revisar" and deber.id in caso.decisiones:
        return caso.decisiones[deber.id].decision
    return deber.decision


def _cambios(antes: HechosIncidente | None, despues: HechosIncidente) -> dict[str, list[Any]]:
    previo = antes.model_dump(mode="json") if antes else {}
    nuevo = despues.model_dump(mode="json")
    return {k: [previo.get(k), v] for k, v in nuevo.items() if previo.get(k) != v}


class AccionesDelegado:
    """Se mezcla con `CanalReporte`: usa su repositorio, su reloj y su enrutamiento."""

    _repo: RepositorioCasos
    _organizaciones: dict[str, Organizacion]
    _reloj: Callable[[], datetime]
    _llaves: MultiFernet | None
    _enrutar: Callable[[Caso, datetime], None]
    _enrutamiento: ReglasEnrutamiento

    # --- acceso ------------------------------------------------------------------------

    def caso_de_organizacion(self, id_organizacion: str, id_caso: str) -> Caso:
        caso = self._repo.obtener(id_caso)
        if caso is None or caso.id_organizacion != id_organizacion:
            raise CasoAjeno(id_caso)
        return caso

    def casos_de_organizacion(self, id_organizacion: str) -> list[Caso]:
        return [c for c in self._repo.listar() if c.id_organizacion == id_organizacion]

    def evidencia_de_organizacion(
        self, id_organizacion: str, cabeza_esperada: str | None = None
    ) -> tuple[Verificacion, list[Anotacion]]:
        """Revisa solo la cadena de esta organización: no depende de otras ni las menciona."""
        verificacion = self._repo.verificar_evidencia(cabeza_esperada, id_organizacion)
        return verificacion, self._repo.evidencia(id_organizacion=id_organizacion)

    # --- acciones ----------------------------------------------------------------------

    def _anular_validacion(self, caso: Caso, ahora: datetime, por: str, causa: str) -> None:
        if caso.validacion is not None:
            caso.validacion = None
            caso.registrar("validacion_anulada", ahora, por=por, causa=causa)

    def corregir_hechos(
        self,
        id_organizacion: str,
        id_caso: str,
        hechos: HechosIncidente,
        *,
        motivo: MotivoCorreccion,
        por: str,
        nota: str | None = None,
    ) -> Caso:
        caso = self.caso_de_organizacion(id_organizacion, id_caso)
        if caso.tipo == "solicitud":
            raise AccionInvalida(
                "Lo que pidió una persona se confirma con ella, no se corrige aquí."
            )
        nota = (nota or "").strip() or None
        if nota and len(nota) > LARGO_MAXIMO_NOTA:
            raise AccionInvalida(f"La nota admite hasta {LARGO_MAXIMO_NOTA} caracteres.")
        guardia.exigir_sintetico({"nota": nota} if nota else {})
        if caso.hechos_vigentes is None:
            motivo = "ia_no_leyo"  # no hay lectura que corregir: el motivo es ese y no otro
        elif motivo == "ia_no_leyo":
            raise AccionInvalida("La IA sí leyó este reporte: elige otro motivo.")
        cambios = _cambios(caso.hechos_vigentes, hechos)
        if not cambios:
            raise AccionInvalida("No cambiaste ningún hecho.")

        ahora = self._reloj()
        org = self._organizaciones[caso.id_organizacion]
        caso.hechos_delegado = hechos
        caso.correcciones.append(
            Correccion(cambios=cambios, motivo=motivo, nota=nota, por=por, momento=ahora)
        )
        # El plazo se sigue contando desde que se supo (el ingreso), no desde la corrección.
        caso.resultado_incidente = decidir_incidente(hechos, org.perfil, caso.ingreso)
        caso.relojes_anci_posibles = []
        caso.estado = "interpretado"
        r = caso.resultado_incidente
        caso.registrar(
            "hechos_corregidos",
            ahora,
            cambios=cambios,
            motivo=motivo,
            por=por,
            con_nota=bool(nota),
            aviso_agencia=r.aviso_agencia.decision,
            aviso_titulares=r.aviso_titulares.decision,
            reporte_anci=r.reporte_anci.decision,
        )
        self._anular_validacion(caso, ahora, por, "hechos_corregidos")
        self._enrutar(caso, ahora)
        self._repo.guardar(caso)
        return caso

    def resolver_deber(
        self,
        id_organizacion: str,
        id_caso: str,
        deber: str,
        decision: str,
        *,
        motivo: MotivoDecision,
        por: str,
    ) -> Caso:
        caso = self.caso_de_organizacion(id_organizacion, id_caso)
        if decision not in ("si", "no"):
            raise AccionInvalida("Elige sí o no.")
        actual = next((d for d in deberes_del_caso(caso) if d.id == deber), None)
        if actual is None or actual.decision != "revisar":
            raise AccionInvalida("Ese deber no está esperando tu decisión.")
        ahora = self._reloj()
        caso.decisiones[deber] = DecisionDelegado(
            deber=deber,
            decision=decision,  # type: ignore[arg-type]  # validado arriba
            motivo=motivo,
            por=por,
            momento=ahora,
        )
        caso.registrar(
            "deber_resuelto", ahora, deber=deber, decision=decision, motivo=motivo, por=por
        )
        self._anular_validacion(caso, ahora, por, "deber_resuelto")
        self._repo.guardar(caso)
        return caso

    def registrar_envio(
        self,
        id_organizacion: str,
        id_caso: str,
        id_deber: str,
        *,
        canal: CanalEnvio,
        por: str,
        momento: datetime | None = None,
    ) -> Caso:
        """Deja constancia de que el delegado envió (o hizo) algo que corresponde. La hora la
        indica él (pudo enviarlo antes de anotarlo), pero no puede ser antes del ingreso del caso
        ni en el futuro."""
        caso = self.caso_de_organizacion(id_organizacion, id_caso)
        ahora = self._reloj()
        momento = momento or ahora
        if id_deber in caso.envios:
            raise AccionInvalida("Esto ya quedó registrado como enviado.")
        if id_deber not in {d.id for d in entregas_del_caso(caso)}:
            raise AccionInvalida(
                "Esto no corresponde enviarlo con lo que se sabe hoy. Si el motor dejó una duda, "
                "decide primero si corresponde."
            )
        if momento.tzinfo is None:
            raise AccionInvalida("Indica la hora con su zona horaria.")
        if momento > ahora + timedelta(minutes=1):
            raise AccionInvalida("La hora del envío no puede ser en el futuro.")
        if momento < caso.ingreso - timedelta(minutes=1):
            raise AccionInvalida("La hora del envío no puede ser anterior al ingreso del caso.")
        caso.envios[id_deber] = Envio(
            deber=id_deber, canal=canal, momento=momento, por=por, registrado=ahora
        )
        caso.registrar(
            "envio_registrado",
            ahora,
            por=por,
            deber=id_deber,
            canal=canal,
            enviado=momento.isoformat(),
        )
        self._enrutar(caso, ahora)  # la urgencia ya no cuenta lo que se envió
        self._repo.guardar(caso)
        return caso

    def validar(self, id_organizacion: str, id_caso: str, *, por: str) -> Caso:
        caso = self.caso_de_organizacion(id_organizacion, id_caso)
        if caso.validacion is not None:
            raise AccionInvalida("Este caso ya está validado.")
        if caso.tipo != "solicitud" and caso.hechos_vigentes is None:
            raise AccionInvalida(
                "La IA no pudo leer este reporte. "
                "Primero completa los hechos con «Completar hechos»."
            )
        if caso.tipo == "solicitud" and caso.estado != "interpretado":
            raise AccionInvalida(
                "Esta solicitud todavía no tiene una lectura vigente: espera la respuesta de la "
                "persona o confírmala con ella."
            )
        pendientes = por_resolver(caso)
        if pendientes:
            n = len(pendientes)
            raise AccionInvalida(
                f"Antes de validar, decide {n} deber{'es' if n > 1 else ''} marcado"
                f"{'s' if n > 1 else ''} «Decide tú»."
            )
        ahora = self._reloj()
        caso.validacion = Validacion(por=por, momento=ahora)
        caso.registrar(
            "validado",
            ahora,
            por=por,
            deberes={d.id: decision_final(caso, d) for d in deberes_del_caso(caso)},
        )
        self._repo.guardar(caso)
        return caso

    def borradores(self, id_organizacion: str, id_caso: str) -> tuple[Caso, dict]:
        """Borradores de reporte a la Agencia y a la ANCI, armados ahora desde el caso."""
        from ..reportes import borradores_del_caso  # importación tardía: reportes usa este módulo

        caso = self.caso_de_organizacion(id_organizacion, id_caso)
        org = self._organizaciones[caso.id_organizacion]
        reglas = self._enrutamiento.organizaciones[caso.id_organizacion]
        return caso, borradores_del_caso(caso, org, reglas)

    def marcar_borrador_revisado(
        self, id_organizacion: str, id_caso: str, destino: str, huella: str, *, por: str
    ) -> Caso:
        """Deja constancia de que el delegado revisó un borrador. La evidencia guarda la huella
        del texto revisado (nunca el texto) y cuántos campos quedaban por completar."""
        from ..reportes import Borrador, huella_sin_digitos

        caso, borradores = self.borradores(id_organizacion, id_caso)
        actual = borradores.get(destino)
        if not isinstance(actual, Borrador):
            raise AccionInvalida("No hay un borrador para ese destino.")
        if not hmac.compare_digest(huella.encode(), actual.huella.encode()):
            raise AccionInvalida(
                "El borrador cambió desde que lo abriste (por ejemplo, se corrigieron hechos). "
                "Revísalo de nuevo."
            )
        caso.registrar(
            "borrador_revisado",
            self._reloj(),
            destino=destino,
            huella=huella_sin_digitos(actual.huella),
            por_completar=len(actual.por_completar),
            por=por,
        )
        self._repo.guardar(caso)
        return caso

    def abrir_identidad(
        self, id_organizacion: str, id_caso: str, *, motivo: MotivoIdentidad, por: str
    ) -> Mapping[str, str]:
        """Descifra la identidad reservada y deja constancia de quién la abrió y por qué.
        La capa web exige antes volver a escribir la contraseña."""
        caso = self.caso_de_organizacion(id_organizacion, id_caso)
        if not caso.identidad_cifrada:
            raise AccionInvalida("Este caso no tiene una identidad reservada.")
        if self._llaves is None:
            raise AccionInvalida("La llave del modo reservado no está disponible en este servidor.")
        identidad = descifrar_identidad(self._llaves, caso.identidad_cifrada, caso.id)
        caso.registrar("identidad_abierta", self._reloj(), motivo=motivo, por=por)
        self._repo.guardar(caso)
        return identidad


__all__ = [
    "AccionInvalida",
    "AccionesDelegado",
    "CasoAjeno",
    "decision_final",
    "deberes_del_caso",
    "por_resolver",
]
