"""Ejecuta la evaluación en tres niveles y calcula las métricas.

- base: reglas por palabras clave, sin IA (y el motor para deberes y plazos).
- ia_sola: la IA interpreta y decide sola, con el texto legal a la vista.
- ia_motor: el sistema propuesto. La IA interpreta (solo lo ambiguo, en columnas) y el
  motor de reglas decide deberes y plazos.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import pandas as pd

from ..interpretacion import extraer_hechos, interpretar_solicitud
from ..inventario import cargar_categorias, perfilar_dataframe
from ..inventario.actividad import clasificar_ambiguas, combinar_clasificacion
from ..motor import HechosSolicitud, decidir_incidente, decidir_solicitud
from . import ia_sola
from .base import hechos_incidente_base, hechos_solicitud_base
from .casos import (
    CasoSolicitud,
    cargar_columnas,
    cargar_incidentes,
    cargar_solicitudes,
)

FILAS_CATEGORICAS = 30
REFERENCIA = date(2026, 12, 1)
DEBERES = ("aviso_agencia", "aviso_titulares", "reporte_anci")


def _en_paralelo[T, R](
    funcion: Callable[[T], R], elementos: Iterable[T], hilos: int = 4
) -> list[R]:
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        return list(ex.map(funcion, elementos))


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


# --- columnas -----------------------------------------------------------------


def _tabla(planilla) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    datos: dict[str, list[str]] = {}
    for c in planilla.columnas:
        if c.categorica:
            datos[c.nombre] = [c.valores[i % len(c.valores)] for i in range(FILAS_CATEGORICAS)]
        else:
            datos[c.nombre] = c.valores + [""] * (FILAS_CATEGORICAS - len(c.valores))
    return pd.DataFrame(datos), datos


def metricas_columnas(filas: list[dict[str, Any]], nivel: str) -> dict[str, Any]:
    sensibles = {k for k, c in cargar_categorias().items() if c.sensible is True}
    total = len(filas)
    correctas = sum(f[nivel] == f["esperado"] for f in filas)
    gold_sens = [f for f in filas if f["esperado"] in sensibles]
    detectadas = sum(f[nivel] in sensibles for f in gold_sens)
    falsas = sum(f[nivel] in sensibles for f in filas if f["esperado"] not in sensibles)
    trampas = [f for f in filas if f["trampa"]]
    return {
        "casos": total,
        "exactitud_pct": _pct(correctas, total),
        "sensibles_detectadas": f"{detectadas}/{len(gold_sens)}",
        "sensibles_detectadas_pct": _pct(detectadas, len(gold_sens)),
        "falsos_sensibles": falsas,
        "trampas_acertadas": f"{sum(f[nivel] == f['esperado'] for f in trampas)}/{len(trampas)}",
        "sin_clasificar": sum(f[nivel] is None for f in filas),
        "enviadas_a_revision": sum(bool(f.get(f"{nivel}_revisar")) for f in filas),
    }


def evaluar_columnas(cliente=None, modelo: str | None = None) -> dict[str, Any]:
    filas: list[dict[str, Any]] = []
    costos = {"ia_sola": 0.0, "ia_motor": 0.0}
    for planilla in cargar_columnas():
        df, valores = _tabla(planilla)
        perfil = perfilar_dataframe(df, planilla.id, referencia=REFERENCIA)
        base = {c.nombre: c.categoria for c in perfil.columnas}
        ia_sola_pred: dict[str, str | None] = {}
        sistema = dict(base)
        revision: set[str] = set()
        if cliente:
            nulo = perfil.model_copy(
                update={
                    "columnas": [
                        c.model_copy(
                            update={"categoria": None, "confianza": "baja", "evidencia": []}
                        )
                        for c in perfil.columnas
                    ]
                }
            )
            res, costo = clasificar_ambiguas(nulo, valores, planilla.descripcion, cliente, modelo)
            costos["ia_sola"] += costo
            ia_sola_pred = {k: v[0] for k, v in res.items()}
            res, costo = clasificar_ambiguas(perfil, valores, planilla.descripcion, cliente, modelo)
            costos["ia_motor"] += costo
            finales = {
                c.nombre: combinar_clasificacion(c, res.get(c.nombre)) for c in perfil.columnas
            }
            sistema = {k: f.categoria for k, f in finales.items()}
            revision = {k for k, f in finales.items() if f.revisar}
        for c in planilla.columnas:
            filas.append(
                {
                    "planilla": planilla.id,
                    "columna": c.nombre,
                    "esperado": c.esperado,
                    "trampa": c.trampa,
                    "base": base[c.nombre],
                    "ia_sola": ia_sola_pred.get(c.nombre) if cliente else None,
                    "ia_motor": sistema[c.nombre] if cliente else None,
                    "ia_motor_revisar": c.nombre in revision,
                }
            )
    niveles = ["base", "ia_sola", "ia_motor"] if cliente else ["base"]
    return {
        "metricas": {n: metricas_columnas(filas, n) for n in niveles},
        "costo_usd": {n: round(costos[n], 4) for n in costos} if cliente else {},
        "casos": filas,
    }


# --- incidentes ---------------------------------------------------------------


def metricas_incidentes(filas: list[dict[str, Any]], nivel: str) -> dict[str, Any]:
    total = len(filas)
    por_deber = {}
    omitidos = alarmas = 0
    for d in DEBERES:
        aciertos = sum(f[nivel][d] == f["esperado"][d] for f in filas)
        por_deber[d] = _pct(aciertos, total)
        omitidos += sum(
            f["esperado"][d] in ("si", "revisar") and f[nivel][d] == "no" for f in filas
        )
        alarmas += sum(f["esperado"][d] == "no" and f[nivel][d] in ("si", "revisar") for f in filas)
    con_deber = sum(f["esperado"][d] in ("si", "revisar") for f in filas for d in DEBERES)
    completos = sum(all(f[nivel][d] == f["esperado"][d] for d in DEBERES) for f in filas)
    return {
        "casos": total,
        "casos_totalmente_correctos_pct": _pct(completos, total),
        "exactitud_por_deber_pct": por_deber,
        "deberes_detectados": f"{con_deber - omitidos}/{con_deber}",
        "deberes_detectados_pct": _pct(con_deber - omitidos, con_deber),
        "deberes_omitidos": omitidos,
        "alarmas_de_mas": alarmas,
        "respuestas_fallidas_ia": sum(bool(f.get(f"{nivel}_error")) for f in filas),
    }


def _deberes(resultado) -> dict[str, str]:
    return {
        "aviso_agencia": resultado.aviso_agencia.decision,
        "aviso_titulares": resultado.aviso_titulares.decision,
        "reporte_anci": resultado.reporte_anci.decision,
    }


def evaluar_incidentes(cliente=None, modelo: str | None = None) -> dict[str, Any]:
    casos = cargar_incidentes()
    extracciones = (
        _en_paralelo(lambda c: extraer_hechos(c.texto, cliente, modelo), casos) if cliente else []
    )
    solas = (
        _en_paralelo(lambda c: ia_sola.deberes_incidente(c.texto, c.perfil, cliente, modelo), casos)
        if cliente
        else []
    )
    filas = []
    for i, caso in enumerate(casos):
        fila: dict[str, Any] = {
            "id": caso.id,
            "esperado": caso.esperado.model_dump(),
            "base": _deberes(decidir_incidente(hechos_incidente_base(caso.texto), caso.perfil)),
        }
        if cliente:
            ext = extracciones[i]
            if ext.hechos is None:  # la IA falló: el caso queda para revisión humana
                fila["ia_motor"] = dict.fromkeys(DEBERES, "revisar")
            else:
                fila["ia_motor"] = _deberes(decidir_incidente(ext.hechos, caso.perfil))
            fila["ia_motor_error"] = ext.error
            fila["categorias_ia"] = ext.hechos.categorias_especiales if ext.hechos else None
            s = solas[i]
            fila["ia_sola"] = {d: getattr(s, d) or "sin_respuesta" for d in DEBERES}
            fila["ia_sola_error"] = s.error
        filas.append(fila)
    niveles = ["base", "ia_sola", "ia_motor"] if cliente else ["base"]
    return {
        "metricas": {n: metricas_incidentes(filas, n) for n in niveles},
        "costo_usd": {
            "ia_sola": round(sum(s.costo_usd for s in solas), 4),
            "ia_motor": round(sum(e.costo_usd for e in extracciones), 4),
        }
        if cliente
        else {},
        "casos": filas,
    }


# --- solicitudes --------------------------------------------------------------


def _clasificacion_correcta(
    caso: CasoSolicitud, es: bool | None, derechos: list[str], confirma: bool
) -> bool:
    e = caso.esperado
    if es is None or es != e.es_solicitud:
        return False
    if not e.es_solicitud:
        return True
    aceptadas = [set(e.derechos), *(set(a) for a in e.alternativas)]
    if set(derechos) in aceptadas:
        return True
    # Si el mensaje es ambiguo y el sistema pide confirmar, puede proponer las lecturas posibles.
    posibles = set().union(*aceptadas)
    return bool(derechos) and confirma and e.requiere_confirmacion and set(derechos) <= posibles


def metricas_solicitudes(filas: list[dict[str, Any]], nivel: str) -> dict[str, Any]:
    total = len(filas)
    correctas = sum(f[nivel]["clasificacion_correcta"] for f in filas)
    conf_gold = [f for f in filas if f["esperado"]["requiere_confirmacion"]]
    conf_pred = [f for f in filas if f[nivel]["requiere_confirmacion"]]
    vp = sum(f[nivel]["requiere_confirmacion"] for f in conf_gold)
    gold_sol = [f for f in filas if f["esperado"]["es_solicitud"]]
    plazo_ok = sum(
        f[nivel]["vence_respuesta"] == f["esperado"]["vence_respuesta"] for f in gold_sol
    )
    gold_bloq = [f for f in filas if f["esperado"].get("vence_bloqueo")]
    bloq_ok = sum(f[nivel]["vence_bloqueo"] == f["esperado"]["vence_bloqueo"] for f in gold_bloq)
    return {
        "casos": total,
        "clasificacion_correcta_pct": _pct(correctas, total),
        "ambiguos_detectados": f"{vp}/{len(conf_gold)}",
        "confirmaciones_innecesarias": len(conf_pred) - vp,
        "plazo_respuesta_correcto": f"{plazo_ok}/{len(gold_sol)}",
        "plazo_respuesta_correcto_pct": _pct(plazo_ok, len(gold_sol)),
        "plazo_bloqueo_correcto": f"{bloq_ok}/{len(gold_bloq)}",
        "respuestas_fallidas_ia": sum(bool(f.get(f"{nivel}_error")) for f in filas),
    }


def _fila_motor(caso: CasoSolicitud, hechos: HechosSolicitud | None) -> dict[str, Any]:
    if hechos is None:  # la IA falló: el plazo corre igual y el caso va a revisión
        hechos_plazo = HechosSolicitud(es_solicitud=True)
        es, derechos, conf = None, [], True
    else:
        hechos_plazo, es, derechos, conf = (
            hechos,
            hechos.es_solicitud,
            hechos.derechos,
            hechos.requiere_confirmacion,
        )
    r = decidir_solicitud(hechos_plazo, caso.ingreso)
    return {
        "es_solicitud": es,
        "derechos": derechos,
        "requiere_confirmacion": conf,
        "clasificacion_correcta": _clasificacion_correcta(caso, es, derechos, conf),
        "vence_respuesta": r.respuesta.vence.isoformat() if r.respuesta else None,
        "vence_bloqueo": r.bloqueo.vence.isoformat() if r.bloqueo else None,
    }


def evaluar_solicitudes(cliente=None, modelo: str | None = None) -> dict[str, Any]:
    casos = cargar_solicitudes()
    interpretaciones = (
        _en_paralelo(lambda c: interpretar_solicitud(c.texto, cliente, modelo), casos)
        if cliente
        else []
    )
    solas = (
        _en_paralelo(lambda c: ia_sola.solicitud(c.texto, c.ingreso, cliente, modelo), casos)
        if cliente
        else []
    )
    filas = []
    for i, caso in enumerate(casos):
        e = caso.esperado
        fila: dict[str, Any] = {
            "id": caso.id,
            "esperado": {
                "es_solicitud": e.es_solicitud,
                "derechos": e.derechos,
                "requiere_confirmacion": e.requiere_confirmacion,
                "vence_respuesta": e.vence_respuesta.isoformat() if e.vence_respuesta else None,
                "vence_bloqueo": e.vence_bloqueo.isoformat() if e.vence_bloqueo else None,
            },
            "base": _fila_motor(caso, hechos_solicitud_base(caso.texto)),
        }
        if cliente:
            fila["ia_motor"] = _fila_motor(caso, interpretaciones[i].hechos)
            fila["pregunta_confirmacion"] = (
                interpretaciones[i].hechos.pregunta_confirmacion
                if interpretaciones[i].hechos
                else None
            )
            fila["ia_motor_error"] = interpretaciones[i].error
            s = solas[i]
            fila["ia_sola_error"] = s.error
            fila["ia_sola"] = {
                "es_solicitud": s.es_solicitud,
                "derechos": s.derechos,
                "requiere_confirmacion": bool(s.requiere_confirmacion),
                "clasificacion_correcta": _clasificacion_correcta(
                    caso, s.es_solicitud, s.derechos, bool(s.requiere_confirmacion)
                ),
                "vence_respuesta": s.vence_respuesta.isoformat() if s.vence_respuesta else None,
                "vence_bloqueo": s.vence_bloqueo.isoformat() if s.vence_bloqueo else None,
            }
        filas.append(fila)
    niveles = ["base", "ia_sola", "ia_motor"] if cliente else ["base"]
    return {
        "metricas": {n: metricas_solicitudes(filas, n) for n in niveles},
        "costo_usd": {
            "ia_sola": round(sum(s.costo_usd for s in solas), 4),
            "ia_motor": round(sum(i.costo_usd for i in interpretaciones), 4),
        }
        if cliente
        else {},
        "casos": filas,
    }
