"""Actividad de tratamiento: los 11 campos del artículo 3 letra d) del DS 662.

Flujo:

1. El perfilador (sin IA) clasifica lo que puede con certeza.
2. La IA rápida clasifica solo las columnas ambiguas. Recibe el encabezado y la
   forma de los valores ("Aaaaa Aaaaa", "99.999.999-9"), nunca los valores, salvo
   en columnas categóricas de pocas opciones ("Sí", "No", "M").
3. La IA de extracción propone los campos que requieren contexto (finalidad, base
   de licitud, destinatarios, plazo de supresión). Recibe el perfil, no los datos.
4. El código verifica cada cita legal contra el corpus, descarta lo inválido y
   calcula alertas con reglas fijas.
5. Una persona valida. Nada queda como definitivo sin esa validación.

Si la IA falla, los campos quedan "pendientes" y se agrega una alerta: el sistema
nunca rellena un campo legal por defecto.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from ..corpus import corpus_por_defecto
from ..deteccion import Enmascarador
from .perfilador import PerfilPlanilla, cargar_categorias

Origen = Literal["calculado", "ia", "pendiente", "persona"]
BaseLicitud = Literal[
    "consentimiento",
    "consentimiento_expreso",
    "obligacion_financiera",
    "obligacion_legal",
    "contrato",
    "interes_legitimo",
    "defensa_de_derechos",
    "no_determinada",
]

FUNDAMENTO_BASE: dict[str, tuple[str, str]] = {
    "consentimiento": ("ley-19628", "12"),
    "consentimiento_expreso": ("ley-19628", "16"),
    "obligacion_financiera": ("ley-19628", "13"),
    "obligacion_legal": ("ley-19628", "13"),
    "contrato": ("ley-19628", "13"),
    "interes_legitimo": ("ley-19628", "13"),
    "defensa_de_derechos": ("ley-19628", "13"),
}

CATEGORIAS_EXTRA = ("no_personal", "persona_juridica")
MAX_MUESTRAS_FORMA = 5
MAX_OPCIONES_CATEGORICAS = 8
MIN_FILAS_CATEGORICA = 20


# --- modelos ---------------------------------------------------------------


class Cita(BaseModel):
    norma: str
    articulo: str


class Campo(BaseModel):
    valor: Any = None
    origen: Origen
    nota: str | None = None
    citas: list[Cita] = Field(default_factory=list)


class ColumnaFinal(BaseModel):
    nombre: str
    categoria: str | None
    origen: Origen
    justificacion: str | None = None
    necesaria: bool | None = None
    motivo_innecesaria: str | None = None


class Alerta(BaseModel):
    nivel: Literal["alta", "media", "informativa"]
    mensaje: str
    cita: Cita | None = None


class ActividadTratamiento(BaseModel):
    """Caracterización de una actividad de tratamiento (DS 662, art. 3 d)."""

    archivo: str
    descripcion_usuario: str
    tipo_datos: Campo  # i
    ambito_territorial: Campo  # ii
    bases_de_datos: Campo  # iii
    categorias_titulares: Campo  # iv
    fines: Campo  # v
    fuente: Campo  # vi
    base_licitud: Campo  # vii
    destinatarios: Campo  # viii
    transferencias_internacionales: Campo  # ix
    plazo_supresion: Campo  # x
    decisiones_automatizadas: Campo  # xi
    columnas: list[ColumnaFinal]
    alertas: list[Alerta]
    citas_rechazadas: list[str] = Field(default_factory=list)
    costo_ia_usd: float = 0.0
    validada: bool = False


class ClienteLLM(Protocol):
    def llamar(self, **kwargs: Any) -> Any: ...


# --- privacidad de lo que se envía a la IA --------------------------------


def forma(valor: str) -> str:
    """Forma de un valor sin su contenido: letras → a/A, dígitos → 9."""
    return re.sub(r"\d", "9", re.sub(r"[^\W\d_]", lambda m: "A" if m[0].isupper() else "a", valor))


def muestras_seguras(valores: list[str]) -> dict[str, Any]:
    """Lo único que la IA ve de una columna.

    Columnas categóricas (pocas opciones que se repiten) se envían enmascaradas;
    el resto, solo como formas.
    """
    no_vacios = [v.strip() for v in valores if v and v.strip()]
    conteo = Counter(no_vacios)
    if len(no_vacios) >= MIN_FILAS_CATEGORICA and 0 < len(conteo) <= MAX_OPCIONES_CATEGORICAS:
        e = Enmascarador()
        return {"tipo": "opciones", "valores": [e.enmascarar(v)[:40] for v in sorted(conteo)]}
    formas = list(dict.fromkeys(forma(v)[:40] for v in no_vacios))[:MAX_MUESTRAS_FORMA]
    return {"tipo": "formas", "valores": formas}


# --- llamadas a la IA ------------------------------------------------------

SISTEMA_COLUMNAS = """Clasificas columnas de planillas de una organización chilena según la \
Ley 19.628 (modificada por la Ley 21.719). Recibes el encabezado y, por privacidad, solo la \
forma de los valores (letras como 'a' o 'A', dígitos como '9') o, en columnas de pocas \
opciones, sus valores. Elige una categoría del catálogo, 'no_personal' si la columna no \
contiene datos de personas naturales, o 'persona_juridica' si identifica empresas. \
Si dudas entre una categoría sensible y una no sensible, elige la sensible. Justifica en \
una frase breve en español."""

SISTEMA_ACTIVIDAD = """Ayudas al delegado de protección de datos de una organización chilena \
a caracterizar una actividad de tratamiento según el artículo 3 letra d) del Decreto 662 de \
2025 y la Ley 19.628 (modificada por la Ley 21.719). Recibes la descripción que dio la \
organización y el perfil de la planilla (columnas y categorías), nunca los datos.

Reglas:
- Propones; una persona decide. Si la descripción no informa un campo, responde exactamente \
"no informado". No inventes proveedores, países ni plazos que no se deduzcan de la descripción.
- Para la base de licitud usa una de las opciones. Los datos sensibles requieren \
consentimiento expreso (art. 16), salvo las excepciones de la ley.
- Marca como innecesaria toda columna que no sea necesaria, adecuada ni pertinente para la \
finalidad descrita (principio de proporcionalidad, art. 3 c).
- En las citas indica solo la norma y el artículo, sin texto; el sistema muestra el texto \
oficial. Normas válidas: ley-19628, ley-21719, ds-662-2025, ley-21663.
- Escribe en español claro, sin jerga legal innecesaria."""


def _herramienta_columnas() -> dict[str, Any]:
    opciones = [*cargar_categorias().keys(), *CATEGORIAS_EXTRA]
    return {
        "name": "clasificar_columnas",
        "description": "Registra la categoría de cada columna ambigua.",
        "input_schema": {
            "type": "object",
            "properties": {
                "columnas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {"type": "string"},
                            "categoria": {"type": "string", "enum": opciones},
                            "justificacion": {"type": "string"},
                        },
                        "required": ["nombre", "categoria", "justificacion"],
                    },
                }
            },
            "required": ["columnas"],
        },
    }


def _herramienta_actividad() -> dict[str, Any]:
    texto = {"type": "string"}
    lista = {"type": "array", "items": {"type": "string"}}
    return {
        "name": "proponer_actividad",
        "description": "Propone los campos de la actividad de tratamiento que requieren contexto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fines": lista,
                "base_licitud": {"type": "string", "enum": list(BaseLicitud.__args__)},
                "interes_legitimo": texto,
                "categorias_titulares": lista,
                "fuente": texto,
                "destinatarios": lista,
                "ambito_territorial": texto,
                "transferencias_internacionales": texto,
                "plazo_supresion": texto,
                "decisiones_automatizadas": {"type": "boolean"},
                "columnas_innecesarias": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"columna": texto, "motivo": texto},
                        "required": ["columna", "motivo"],
                    },
                },
                "citas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"campo": texto, "norma": texto, "articulo": texto},
                        "required": ["campo", "norma", "articulo"],
                    },
                },
            },
            "required": [
                "fines",
                "base_licitud",
                "categorias_titulares",
                "fuente",
                "destinatarios",
                "ambito_territorial",
                "transferencias_internacionales",
                "plazo_supresion",
                "decisiones_automatizadas",
                "columnas_innecesarias",
                "citas",
            ],
        },
    }


def _entrada_herramienta(respuesta: Any, nombre: str) -> dict[str, Any] | None:
    for bloque in getattr(respuesta, "bloques_herramienta", []):
        if bloque.get("nombre") == nombre and isinstance(bloque.get("entrada"), dict):
            return bloque["entrada"]
    return None


def clasificar_ambiguas(
    perfil: PerfilPlanilla,
    valores_por_columna: dict[str, list[str]],
    descripcion: str,
    cliente: ClienteLLM,
    modelo: str,
) -> tuple[dict[str, tuple[str, str]], float]:
    """Clasifica con IA las columnas sin categoría o con confianza baja.

    Devuelve {columna: (categoria, justificacion)} solo con respuestas válidas, y el costo.
    """
    ambiguas = [c for c in perfil.columnas if c.categoria is None or c.confianza == "baja"]
    if not ambiguas:
        return {}, 0.0
    carga = [
        {
            "nombre": c.nombre,
            "categoria_detectada": c.categoria,
            "evidencia": c.evidencia,
            "muestras": muestras_seguras(valores_por_columna.get(c.nombre, [])),
        }
        for c in ambiguas
    ]
    mensaje = (
        f"Uso de la planilla, según la organización: {descripcion}\n\n"
        f"Columnas a clasificar (JSON): {json.dumps(carga, ensure_ascii=False)}"
    )
    r = cliente.llamar(
        modelo=modelo,
        sistema=SISTEMA_COLUMNAS,
        mensajes=[{"role": "user", "content": mensaje}],
        herramientas=[_herramienta_columnas()],
        forzar_herramienta="clasificar_columnas",
        max_tokens=1500,
        proposito="inventario: clasificar columnas ambiguas",
    )
    entrada = _entrada_herramienta(r, "clasificar_columnas") or {}
    validas = set(cargar_categorias()) | set(CATEGORIAS_EXTRA)
    nombres = {c.nombre for c in ambiguas}
    resultado = {
        item["nombre"]: (item["categoria"], item.get("justificacion", ""))
        for item in entrada.get("columnas", [])
        if isinstance(item, dict)
        and item.get("nombre") in nombres
        and item.get("categoria") in validas
    }
    return resultado, getattr(r, "costo_usd", 0.0)


# --- reglas fijas ------------------------------------------------------------


def _cita_valida(norma: str, articulo: str) -> bool:
    return corpus_por_defecto().verificar_cita(norma, articulo).existe


def categorias_sensibles(columnas: list[ColumnaFinal]) -> list[str]:
    """Categorías sensibles según la clasificación final (cálculo o IA)."""
    cats = cargar_categorias()
    return sorted(
        {
            c.categoria
            for c in columnas
            if c.categoria in cats and cats[c.categoria].sensible is True
        }
    )


def calcular_alertas(perfil: PerfilPlanilla, actividad: ActividadTratamiento) -> list[Alerta]:
    """Alertas determinísticas: no dependen de la IA."""
    alertas: list[Alerta] = []
    sensibles = categorias_sensibles(actividad.columnas)
    if sensibles and actividad.base_licitud.valor != "consentimiento_expreso":
        etiquetas = cargar_categorias()
        alertas.append(
            Alerta(
                nivel="alta",
                mensaje=(
                    "La planilla tiene datos sensibles ("
                    + ", ".join(etiquetas[c].etiqueta.lower() for c in sensibles)
                    + "). Requieren consentimiento expreso del titular, salvo excepción legal."
                ),
                cita=Cita(norma="ley-19628", articulo="16"),
            )
        )
    if perfil.menores and perfil.menores.menores_de_14:
        alertas.append(
            Alerta(
                nivel="alta",
                mensaje=(
                    f"Hay datos de {perfil.menores.menores_de_14} niños o niñas menores de 14 "
                    "años: se requiere consentimiento de sus padres o representantes legales, y "
                    "ante una filtración hay que avisar a cada titular a través de ellos."
                ),
                cita=Cita(norma="ley-19628", articulo="16 quater"),
            )
        )
    adolescentes_16 = (
        perfil.menores.menores_de_16 - perfil.menores.menores_de_14 if perfil.menores else 0
    )
    if adolescentes_16 and sensibles:
        alertas.append(
            Alerta(
                nivel="alta",
                mensaje=(
                    f"Hay {adolescentes_16} adolescentes menores de 16 años con datos sensibles: "
                    "requieren consentimiento de sus padres o representantes legales."
                ),
                cita=Cita(norma="ley-19628", articulo="16 quater"),
            )
        )
    for col in actividad.columnas:
        if col.necesaria is False:
            alertas.append(
                Alerta(
                    nivel="media",
                    mensaje=(
                        f"La columna «{col.nombre}» parece innecesaria: {col.motivo_innecesaria}"
                    ),
                    cita=Cita(norma="ley-19628", articulo="3"),
                )
            )
    if "financiero" in perfil.especiales:
        alertas.append(
            Alerta(
                nivel="informativa",
                mensaje=(
                    "Contiene datos económicos o financieros: ante una filtración hay que avisar "
                    "también a cada titular."
                ),
                cita=Cita(norma="ley-19628", articulo="14 sexies"),
            )
        )
    for nombre, campo in actividad.model_dump().items():
        if isinstance(campo, dict) and campo.get("origen") == "pendiente":
            alertas.append(
                Alerta(nivel="media", mensaje=f"El campo «{nombre}» quedó pendiente de completar.")
            )
    return alertas


def _tipo_datos(perfil: PerfilPlanilla, columnas: list[ColumnaFinal]) -> Campo:
    etiquetas = cargar_categorias()
    cats = sorted({etiquetas[c.categoria].etiqueta for c in columnas if c.categoria in etiquetas})
    sensibles = [etiquetas[c].etiqueta for c in categorias_sensibles(columnas)]
    nota = (
        "Incluye datos sensibles: " + ", ".join(sensibles) if sensibles else "Sin datos sensibles"
    )
    if perfil.menores and perfil.menores.menores_de_18:
        nota += f". Incluye datos de {perfil.menores.menores_de_18} menores de 18 años"
    return Campo(valor=cats, origen="calculado", nota=nota)


# --- orquestación ------------------------------------------------------------


def construir_actividad(
    perfil: PerfilPlanilla,
    valores_por_columna: dict[str, list[str]],
    descripcion: str,
    cliente: ClienteLLM | None,
    modelo_columnas: str = "claude-haiku-5-5",
    modelo_actividad: str = "claude-sonnet-5-5",
) -> ActividadTratamiento:
    """Arma la actividad de tratamiento. Con `cliente=None` todo lo contextual queda pendiente."""
    costo = 0.0
    clasificadas: dict[str, tuple[str, str]] = {}
    propuesta: dict[str, Any] | None = None
    nota_falla: str | None = None

    if cliente is not None:
        try:
            clasificadas, c1 = clasificar_ambiguas(
                perfil, valores_por_columna, descripcion, cliente, modelo_columnas
            )
            costo += c1
        except Exception as e:  # la IA no es crítica: el caso queda para revisión humana
            nota_falla = f"IA no disponible para clasificar columnas ({type(e).__name__})"

    columnas: list[ColumnaFinal] = []
    for c in perfil.columnas:
        if c.nombre in clasificadas:
            cat, just = clasificadas[c.nombre]
            columnas.append(
                ColumnaFinal(nombre=c.nombre, categoria=cat, origen="ia", justificacion=just)
            )
        elif c.categoria is not None and c.confianza != "baja":
            columnas.append(
                ColumnaFinal(
                    nombre=c.nombre,
                    categoria=c.categoria,
                    origen="calculado",
                    justificacion="; ".join(c.evidencia),
                )
            )
        else:
            columnas.append(
                ColumnaFinal(nombre=c.nombre, categoria=c.categoria, origen="pendiente")
            )

    if cliente is not None and nota_falla is None:
        try:
            resumen = {
                "archivo": perfil.archivo,
                "filas": perfil.filas,
                "columnas": [{"nombre": c.nombre, "categoria": c.categoria} for c in columnas],
                "categorias_sensibles": perfil.categorias_sensibles,
                "menores": perfil.menores.model_dump(mode="json") if perfil.menores else None,
            }
            r = cliente.llamar(
                modelo=modelo_actividad,
                sistema=SISTEMA_ACTIVIDAD,
                mensajes=[
                    {
                        "role": "user",
                        "content": (
                            f"Descripción de la organización: {descripcion}\n\n"
                            "Perfil de la planilla (JSON): "
                            + json.dumps(resumen, ensure_ascii=False)
                        ),
                    }
                ],
                herramientas=[_herramienta_actividad()],
                forzar_herramienta="proponer_actividad",
                max_tokens=2500,
                proposito="inventario: proponer actividad de tratamiento",
            )
            costo += getattr(r, "costo_usd", 0.0)
            propuesta = _entrada_herramienta(r, "proponer_actividad")
            if propuesta is None:
                nota_falla = "La IA no entregó una propuesta válida"
        except Exception as e:
            nota_falla = f"IA no disponible para proponer la actividad ({type(e).__name__})"

    # Citas: se conservan solo las que existen en el corpus.
    citas_por_campo: dict[str, list[Cita]] = {}
    rechazadas: list[str] = []
    for cita in (propuesta or {}).get("citas", []):
        if not isinstance(cita, dict):
            continue
        norma, art, campo = (
            cita.get("norma", ""),
            str(cita.get("articulo", "")),
            cita.get("campo", ""),
        )
        if _cita_valida(norma, art):
            citas_por_campo.setdefault(campo, []).append(Cita(norma=norma, articulo=art))
        else:
            rechazadas.append(f"{norma} art. {art} ({campo})")

    def campo_ia(clave: str) -> Campo:
        if propuesta is None or clave not in propuesta:
            return Campo(origen="pendiente", nota=nota_falla)
        return Campo(valor=propuesta[clave], origen="ia", citas=citas_por_campo.get(clave, []))

    base = campo_ia("base_licitud")
    if base.origen == "ia" and base.valor in FUNDAMENTO_BASE:
        norma, art = FUNDAMENTO_BASE[base.valor]
        base.citas = [Cita(norma=norma, articulo=art), *base.citas]
        if base.valor == "interes_legitimo":
            base.nota = (propuesta or {}).get(
                "interes_legitimo"
            ) or "Falta describir el interés legítimo"

    existentes = {c.nombre for c in columnas}
    for item in (propuesta or {}).get("columnas_innecesarias", []):
        if isinstance(item, dict) and item.get("columna") in existentes:
            for col in columnas:
                if col.nombre == item["columna"]:
                    col.necesaria = False
                    col.motivo_innecesaria = item.get("motivo")
    if propuesta is not None:
        for col in columnas:
            if col.necesaria is None and col.categoria not in CATEGORIAS_EXTRA:
                col.necesaria = True

    actividad = ActividadTratamiento(
        archivo=perfil.archivo,
        descripcion_usuario=descripcion,
        tipo_datos=_tipo_datos(perfil, columnas),
        ambito_territorial=campo_ia("ambito_territorial"),
        bases_de_datos=Campo(valor=[perfil.archivo], origen="calculado"),
        categorias_titulares=campo_ia("categorias_titulares"),
        fines=campo_ia("fines"),
        fuente=campo_ia("fuente"),
        base_licitud=base,
        destinatarios=campo_ia("destinatarios"),
        transferencias_internacionales=campo_ia("transferencias_internacionales"),
        plazo_supresion=campo_ia("plazo_supresion"),
        decisiones_automatizadas=campo_ia("decisiones_automatizadas"),
        columnas=columnas,
        alertas=[],
        citas_rechazadas=rechazadas,
        costo_ia_usd=round(costo, 6),
    )
    actividad.alertas = calcular_alertas(perfil, actividad)
    if nota_falla:
        actividad.alertas.insert(0, Alerta(nivel="media", mensaje=nota_falla))
    return actividad
