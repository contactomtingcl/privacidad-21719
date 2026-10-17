"""Borradores de reporte a la Agencia de Protección de Datos y a la ANCI, armados desde el caso.

Quién hace qué ("la IA interpreta, el motor decide, la persona valida"):

- Los borradores se arman **con código, sin IA**: no cuestan nada y siempre dan el mismo texto
  para el mismo caso. Usan los hechos vigentes (los del delegado si los corrigió) y los plazos que
  calculó el motor. Solo se arman si el deber es "sí" o está en "revisar".
- Lo que el sistema no sabe no se inventa: queda como «[Completar: …]» para el delegado.
- El delegado revisa, completa y envía. El sistema nunca envía nada a una autoridad.

Datos personales:

- **ANCI:** el art. 27 de la Ley 21.663 pide omitir todo dato personal. El borrador se arma solo
  con valores de lista cerrada, cifras y fechas escritas en palabras; nunca recibe el texto del
  reporte, el resumen de la IA ni la identidad de quien reportó. Antes de entregarlo, el código
  revisa que no queden RUT, correos, teléfonos ni fechas numéricas; si encuentra uno, no lo
  entrega (`DatosPersonalesEnBorrador`).
- **Agencia:** tampoco lleva el texto ni la identidad; el único correo permitido es el contacto
  institucional del delegado (ficticio, de `data/canal/enrutamiento.yaml`).

Las citas salen de `data/reglas/reglas.yaml`, cuyos fragmentos verifican las pruebas contra el
texto oficial de `data/normas/`. El formato oficial de cada reporte lo fijan la Agencia y el
reglamento de la Ley 21.663, que no están en el corpus: el borrador ordena el contenido que piden
las leyes y hay que trasladarlo al formulario que corresponda.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Literal

from babel.dates import format_date, format_time
from pydantic import BaseModel, Field

from ..canal.delegado import decision_final
from ..canal.enrutamiento import ReglasOrganizacion
from ..canal.modelos import ZONA_CHILE, Caso, Organizacion
from ..deteccion import FECHA, detectar, parsear_fecha
from ..motor import Deber
from ..motor.motor import NOMBRES_CATEGORIA, Cita, cargar_reglas

Destino = Literal["agencia", "anci"]
DESTINOS: tuple[Destino, ...] = ("agencia", "anci")
NOMBRE_DESTINO = {
    "agencia": "Agencia de Protección de Datos Personales",
    "anci": "Equipo nacional de respuesta a incidentes (CSIRT Nacional de la ANCI)",
}
PERFILES = {
    "empresa_privada": "Empresa privada",
    "organismo_publico": "Organismo de la Administración del Estado",
    "salud": "Prestador de salud",
    "banca_financiero": "Banca y servicios financieros",
    "telecomunicaciones": "Telecomunicaciones",
    "energia": "Energía",
    "agua_saneamiento": "Agua y saneamiento",
    "transporte": "Transporte",
    "combustibles": "Combustibles",
    "infraestructura_digital": "Infraestructura digital",
    "servicios_ti_terceros": "Servicios de tecnologías de la información a terceros",
    "seguridad_social": "Seguridad social",
    "postal": "Servicio postal",
}
VULNERACIONES = {
    "filtracion": "filtración de datos personales",
    "perdida": "pérdida de datos personales",
    "alteracion": "alteración de datos personales",
    "destruccion": "destrucción de datos personales",
    "acceso_no_autorizado": "acceso no autorizado a datos personales",
    "comunicacion_no_autorizada": "comunicación no autorizada de datos personales",
    "ninguna": "sin vulneración de datos personales",
}
CIBER = {"si": "Sí", "no": "No", "dudoso": "Aún no se sabe"}
_COMPLETAR = re.compile(r"\[Completar: ([^\]]+)\]")


def completar(que: str) -> str:
    return f"[Completar: {que}]"


def _personas(n: int) -> str:
    return f"Alrededor de {n} persona{'' if n == 1 else 's'}."


def si_no(valor: bool) -> str:
    return "Sí" if valor else "No"


def _momento(valor: datetime | date) -> str:
    """Fecha en palabras ("2 de diciembre de 2026, 10:00"): una fecha numérica podría confundirse
    con una fecha de nacimiento, y la revisión de datos personales las rechaza."""
    if isinstance(valor, datetime):
        local = valor.astimezone(ZONA_CHILE)
        return (
            f"{format_date(local, format='long', locale='es_CL')}, "
            f"{format_time(local, format='HH:mm', locale='es_CL')} (hora de Chile)"
        )
    return format_date(valor, format="long", locale="es_CL")


def _fechas_en_palabras(texto: str) -> str:
    """ "Exigible desde el 01-12-2026" → "Exigible desde el 1 de diciembre de 2026"."""

    def cambiar(m: re.Match[str]) -> str:
        fecha = parsear_fecha(m.group(0))
        return _momento(fecha) if fecha else m.group(0)

    return FECHA.sub(cambiar, texto)


def _cita(id_regla: str) -> Cita:
    f = cargar_reglas()["reglas"][id_regla]["fuente"]
    return Cita(norma=f["norma"], articulo=str(f["articulo"]), fragmento=f["fragmento"])


# --- modelo -----------------------------------------------------------------------------


class Seccion(BaseModel):
    titulo: str
    lineas: list[str]
    vence: datetime | None = None


class Borrador(BaseModel):
    destino: Destino
    titulo: str
    decision: Literal["si", "revisar"]
    avisos: list[str] = Field(default_factory=list)
    secciones: list[Seccion]
    citas: list[Cita]

    @property
    def por_completar(self) -> list[str]:
        """Lo que falta, en orden y sin repetir."""
        vistos: dict[str, None] = {}
        for s in self.secciones:
            for linea in s.lineas:
                for m in _COMPLETAR.finditer(linea):
                    vistos.setdefault(m.group(1), None)
        return list(vistos)

    def texto(self) -> str:
        """Texto plano para copiar o descargar. Es lo que se firma al marcarlo revisado."""
        partes = [self.titulo, "=" * len(self.titulo), ""]
        partes += [f"AVISO: {a}" for a in self.avisos]
        if self.avisos:
            partes.append("")
        for s in self.secciones:
            partes += [s.titulo, "-" * len(s.titulo)]
            partes += [f"- {linea}" for linea in s.lineas]
            partes.append("")
        partes.append("Fuente legal (texto oficial en data/normas/):")
        partes += [f"- {c.norma}, art. {c.articulo}: «{c.fragmento}»" for c in self.citas]
        return "\n".join(partes) + "\n"

    @property
    def huella(self) -> str:
        return hashlib.sha256(self.texto().encode("utf-8")).hexdigest()


def huella_sin_digitos(huella: str) -> str:
    """La misma huella SHA-256 escrita con letras (0→g … 9→p; a-f quedan igual).

    La evidencia rechaza todo detalle donde aparezca algo con forma de teléfono o RUT, y una
    huella hexadecimal puede traer, por azar, nueve dígitos seguidos. Con letras eso no pasa y la
    huella se puede volver a convertir sin perder nada."""
    return huella.translate(_SIN_DIGITOS)


_SIN_DIGITOS = str.maketrans("0123456789", "ghijklmnop")


class SinBorrador(BaseModel):
    """Por qué no hay borrador para un destino (se muestra al delegado)."""

    destino: Destino
    motivo: str


class DatosPersonalesEnBorrador(Exception):
    """El borrador quedó con algo que parece un dato personal: no se entrega."""


# --- revisión de datos personales ---------------------------------------------------------


def revisar_datos_personales(texto: str, permitidos: frozenset[str] = frozenset()) -> None:
    """Rechaza el borrador si encuentra RUT, correos, teléfonos o fechas numéricas, salvo los
    valores permitidos (por ejemplo, el correo institucional del delegado). No muestra el valor
    encontrado, solo su tipo."""
    encontrados = sorted({d.tipo for d in detectar(texto) if d.valor not in permitidos})
    if encontrados:
        raise DatosPersonalesEnBorrador(
            "El borrador contiene algo que parece un dato personal "
            f"({', '.join(encontrados)}). No se entrega."
        )


# --- armado -------------------------------------------------------------------------------


def _deber(caso: Caso, id_deber: str) -> Deber | None:
    r = caso.resultado_incidente
    if r is None:
        return None
    return {"aviso_agencia": r.aviso_agencia, "reporte_anci": r.reporte_anci}.get(id_deber)


def _registros_posibles(caso: Caso, reglas: ReglasOrganizacion) -> list[str]:
    """Registros de las áreas cuyas palabras aparecen en el reporte (aunque sea reservado). Un
    área que lo recibió solo por el tipo de reporte (Informática ante un ciberincidente) no dice
    qué datos se vieron afectados, así que no se cuenta."""
    if caso.asignacion is None:
        return []
    ids = {
        d.id
        for d in [*caso.asignacion.destinos, *caso.asignacion.sugeridas]
        if any(m.startswith("palabra:") for m in d.motivos)
    }
    return [f"{a.datos} ({a.nombre})" for a in reglas.areas if a.id in ids]


def _avisos_comunes(decision: str, deber: Deber) -> list[str]:
    avisos = [
        "Borrador para revisión del delegado. El sistema no lo envía: la persona revisa, completa "
        "y envía por el canal oficial."
    ]
    if decision == "revisar":
        avisos.append(
            "El motor no pudo decidir este deber («Decide tú»): decide en la ficha si "
            "corresponde antes de enviarlo."
        )
    if deber.nota_vigencia:
        avisos.append(_fechas_en_palabras(deber.nota_vigencia))
    return avisos


def borrador_agencia(caso: Caso, org: Organizacion, reglas: ReglasOrganizacion) -> Borrador:
    hechos = caso.hechos_vigentes
    deber = _deber(caso, "aviso_agencia")
    assert hechos is not None and deber is not None and caso.resultado_incidente is not None
    decision = decision_final(caso, deber)
    titulares = caso.resultado_incidente.aviso_titulares
    decision_titulares = decision_final(caso, titulares)

    categorias = [NOMBRES_CATEGORIA[c].capitalize() for c in hechos.categorias_especiales]
    registros = _registros_posibles(caso, reglas)
    lineas_categorias = [f"Categorías especiales afectadas: {c}." for c in categorias] or [
        "No se informaron datos sensibles, de menores de 14 años ni financieros."
    ]
    lineas_categorias += [f"Registro posiblemente afectado (a confirmar): {r}." for r in registros]
    lineas_categorias.append(
        completar("otras categorías de datos afectadas (por ejemplo, identificación o contacto)")
    )

    efectos = [
        f"Interrumpió algún servicio a las personas: {si_no(hechos.interrupcion_servicio)}.",
        f"Afecta redes o sistemas informáticos: {CIBER[hechos.ciberincidente]}.",
    ]
    if hechos.riesgo_mitigado:
        efectos.append(
            "Hay razones para pensar que los datos no quedaron expuestos: "
            + completar("cuáles (por ejemplo, cifrado o equipo recuperado sin abrir)")
        )
    efectos.append(completar("consecuencias posibles para las personas afectadas"))

    if decision_titulares == "no":
        aviso_personas = [f"No corresponde avisar a cada persona: {titulares.porque}"]
    else:
        aviso_personas = [
            "Corresponde avisar a cada persona afectada (a los menores, por medio de sus padres "
            "o representantes), en lenguaje claro: qué datos, qué consecuencias y qué medidas."
            + (
                " El motor no pudo decidirlo: lo decide el delegado."
                if decision_titulares == "revisar"
                else ""
            ),
            completar("cómo y cuándo se avisará a las personas"),
        ]

    secciones = [
        Seccion(
            titulo="1. Responsable de los datos",
            lineas=[
                f"Organización: {org.nombre}.",
                f"Tipo: {PERFILES.get(org.perfil, org.perfil)}.",
                f"Contacto: {reglas.delegado.cargo}, {reglas.delegado.contacto}.",
            ],
        ),
        Seccion(
            titulo="2. Naturaleza de la vulneración",
            lineas=[
                f"Qué pasó: {VULNERACIONES[hechos.vulneracion].capitalize()}.",
                f"Cuándo se supo: {_momento(caso.ingreso)}.",
                completar("descripción breve de lo ocurrido, sin nombres ni RUT"),
            ],
        ),
        Seccion(titulo="3. Efectos", lineas=efectos),
        Seccion(titulo="4. Categorías de datos", lineas=lineas_categorias),
        Seccion(
            titulo="5. Número aproximado de personas afectadas",
            lineas=[
                _personas(hechos.titulares_aprox)
                if hechos.titulares_aprox is not None
                else completar("número aproximado de personas afectadas")
            ],
        ),
        Seccion(
            titulo="6. Medidas adoptadas",
            lineas=[
                completar("medidas para gestionar la vulneración"),
                completar("medidas para evitar que se repita"),
            ],
        ),
        Seccion(titulo="7. Aviso a las personas afectadas", lineas=aviso_personas),
    ]
    avisos = _avisos_comunes(decision, deber)
    avisos.append(
        "Este borrador ordena lo que pide el art. 14 sexies. Si la Agencia fija un formulario, "
        "hay que traspasarlo a él."
    )
    borrador = Borrador(
        destino="agencia",
        titulo="Borrador de reporte a la Agencia de Protección de Datos Personales",
        decision=decision,  # type: ignore[arg-type]  # "no" se descarta antes de llamar
        avisos=avisos,
        secciones=secciones,
        citas=[_cita("aviso_agencia"), _cita("contenido_reporte_agencia")]
        + ([_cita("aviso_titulares")] if decision_titulares != "no" else []),
    )
    revisar_datos_personales(borrador.texto(), frozenset({reglas.delegado.contacto}))
    return borrador


def borrador_anci(caso: Caso, org: Organizacion) -> Borrador:
    """Solo valores cerrados, cifras y fechas en palabras: nada del texto ni de la identidad."""
    hechos = caso.hechos_vigentes
    deber = _deber(caso, "reporte_anci")
    assert hechos is not None and deber is not None and caso.resultado_incidente is not None
    decision = decision_final(caso, deber)
    plazos = {p.id: p for p in caso.resultado_incidente.plazos_anci}

    def vence(id_plazo: str) -> datetime | None:
        p = plazos.get(id_plazo)
        return p.vence if p and isinstance(p.vence, datetime) else None

    afectados = (
        _personas(hechos.titulares_aprox)
        if hechos.titulares_aprox is not None
        else completar("número aproximado de personas afectadas")
    )
    secciones = [
        Seccion(
            titulo="1. Alerta temprana (plazo: 3 horas desde que se supo)",
            vence=vence("anci_alerta_temprana"),
            lineas=[
                f"Institución: {org.nombre}.",
                f"Servicio esencial: {PERFILES.get(org.perfil, org.perfil)}.",
                f"Cuándo se supo: {_momento(caso.ingreso)}.",
                f"Qué ocurrió: {VULNERACIONES[hechos.vulneracion].capitalize()}.",
                f"Afecta redes o sistemas informáticos: {CIBER[hechos.ciberincidente]}.",
                f"Involucra datos personales: {si_no(hechos.datos_personales)}.",
                f"Interrumpe el servicio: {si_no(hechos.interrupcion_servicio)}.",
                completar("si el incidente sigue en curso"),
                completar("canal institucional de contacto, sin nombres de personas"),
            ],
        ),
        Seccion(
            titulo="2. Actualización (plazo: 72 horas desde que se supo)",
            vence=vence("anci_actualizacion"),
            lineas=[
                f"Personas afectadas: {afectados}",
                completar("duración del incidente"),
                completar("extensión geográfica de la zona afectada"),
                completar("evaluación inicial de la gravedad y el impacto"),
                completar(
                    "indicadores de compromiso, si existen (la ley no considera la dirección IP "
                    "un dato personal)"
                ),
            ],
        ),
        Seccion(
            titulo="3. Informe final (plazo: 15 días corridos desde la alerta temprana)",
            vence=vence("anci_informe_final"),
            lineas=[
                completar("descripción detallada del incidente, con su gravedad e impacto"),
                completar("tipo de amenaza o causa principal probable"),
                completar("medidas de mitigación aplicadas y en curso"),
                completar("repercusiones fuera de Chile, si las hay"),
            ],
        ),
    ]
    avisos = _avisos_comunes(decision, deber)
    avisos += [
        "Sin datos personales (art. 27 de la Ley 21.663): no incluyas nombres, RUT, correos ni "
        "teléfonos de personas al completarlo. El sistema arma este borrador sin el texto del "
        "reporte y lo revisa antes de mostrarlo.",
        "El formato oficial lo fija el reglamento de la Ley 21.663, que no está en el corpus de "
        "este sistema: traspasa el contenido al formulario de la ANCI.",
        "Si el informe final se entrega con el incidente aún en curso, se reemplaza por uno sobre "
        "la situación en ese momento (art. 9, letra d).",
    ]
    borrador = Borrador(
        destino="anci",
        titulo="Borrador de reporte al CSIRT Nacional (ANCI)",
        decision=decision,  # type: ignore[arg-type]
        avisos=avisos,
        secciones=secciones,
        citas=[
            _cita("anci_alerta_temprana"),
            _cita("anci_contenido_actualizacion"),
            _cita("anci_contenido_informe_final"),
            _cita("anci_criterios_efecto"),
            _cita("anci_sin_datos_personales"),
            _cita("anci_ip_no_es_dato_personal"),
        ],
    )
    revisar_datos_personales(borrador.texto())
    return borrador


def borradores_del_caso(
    caso: Caso, org: Organizacion, reglas: ReglasOrganizacion
) -> dict[Destino, Borrador | SinBorrador]:
    """Un borrador por destino, o el motivo por el que no lo hay."""
    if caso.tipo == "solicitud":
        return {
            d: SinBorrador(destino=d, motivo="Las solicitudes de las personas no se reportan.")
            for d in DESTINOS
        }
    if caso.hechos_vigentes is None or caso.resultado_incidente is None:
        motivo = "La IA no pudo leer este reporte: completa los hechos y se arma el borrador."
        return {d: SinBorrador(destino=d, motivo=motivo) for d in DESTINOS}

    salida: dict[Destino, Borrador | SinBorrador] = {}
    for destino, id_deber in (("agencia", "aviso_agencia"), ("anci", "reporte_anci")):
        deber = _deber(caso, id_deber)
        assert deber is not None
        if decision_final(caso, deber) == "no":
            salida[destino] = SinBorrador(destino=destino, motivo=f"No corresponde: {deber.porque}")
            continue
        try:
            salida[destino] = (
                borrador_agencia(caso, org, reglas)
                if destino == "agencia"
                else borrador_anci(caso, org)
            )
        except DatosPersonalesEnBorrador as e:
            salida[destino] = SinBorrador(destino=destino, motivo=str(e))
    return salida


class Revision(BaseModel):
    """Última vez que el delegado marcó revisado el borrador de un destino."""

    por: str
    momento: datetime
    vigente: bool  # False si el borrador cambió después (por ejemplo, porque se corrigieron hechos)


def ultima_revision(caso: Caso, borrador: Borrador) -> Revision | None:
    huella = huella_sin_digitos(borrador.huella)
    for e in reversed(caso.eventos):
        if e.tipo == "borrador_revisado" and e.detalle.get("destino") == borrador.destino:
            return Revision(
                por=e.detalle.get("por", ""),
                momento=e.momento,
                vigente=e.detalle.get("huella") == huella,
            )
    return None
