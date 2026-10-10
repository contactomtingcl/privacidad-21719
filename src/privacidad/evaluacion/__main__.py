"""Evaluación reproducible del sistema con el set etiquetado.

    python -m privacidad.evaluacion           # tres niveles (requiere ANTHROPIC_API_KEY)
    python -m privacidad.evaluacion --sin-ia  # solo la línea base, sin costo

Escribe resultados/evaluacion.json y resultados/evaluacion.md.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from .ejecutar import evaluar_columnas, evaluar_incidentes, evaluar_solicitudes

RAIZ = Path(__file__).resolve().parents[3]
SALIDA = RAIZ / "resultados"
NOMBRES = {"base": "Sin IA (palabras clave)", "ia_sola": "IA sola", "ia_motor": "IA + motor"}


def _tabla(metricas: dict, filas: list[tuple[str, str]]) -> list[str]:
    niveles = list(metricas)
    lineas = [
        "| Métrica | " + " | ".join(NOMBRES[n] for n in niveles) + " |",
        "| --- |" + " --- |" * len(niveles),
    ]
    for clave, etiqueta in filas:
        valores = []
        for n in niveles:
            v = metricas[n]
            for parte in clave.split("."):
                v = v.get(parte) if isinstance(v, dict) else None
            valores.append("—" if v is None else (f"{v}%" if clave.endswith("_pct") else str(v)))
        lineas.append(f"| {etiqueta} | " + " | ".join(valores) + " |")
    return lineas


def _markdown(r: dict) -> str:
    m = [
        "# Evaluación con el set etiquetado",
        "",
        f"Generado el {r['fecha']} con `python -m privacidad.evaluacion`. "
        "Todos los casos son ficticios (`data/evaluacion/`).",
        "",
        "- **Sin IA:** reglas por palabras clave; los deberes y plazos los calcula el motor.",
        "- **IA sola:** el modelo interpreta y decide, con el texto legal a la vista.",
        "- **IA + motor:** el sistema propuesto. La IA interpreta y el motor de reglas decide.",
        "",
        f"Modelos: {r['modelos']}. Costo total: US${r['costo_total_usd']}.",
        "",
        "## Incidentes (50 casos): ¿a quién hay que avisar?",
        "",
        *_tabla(
            r["incidentes"]["metricas"],
            [
                ("deberes_detectados", "Deberes de aviso detectados"),
                ("deberes_omitidos", "Deberes omitidos (el error más grave)"),
                ("alarmas_de_mas", "Alarmas de más"),
                ("exactitud_por_deber_pct.aviso_agencia", "Aviso a la Agencia correcto"),
                ("exactitud_por_deber_pct.aviso_titulares", "Aviso a titulares correcto"),
                ("exactitud_por_deber_pct.reporte_anci", "Reporte a la ANCI correcto"),
                ("casos_totalmente_correctos_pct", "Casos con los tres deberes correctos"),
            ],
        ),
        "",
        "## Solicitudes de titulares (50 casos): ¿qué pide y cuándo vence?",
        "",
        *_tabla(
            r["solicitudes"]["metricas"],
            [
                ("clasificacion_correcta_pct", "Derecho identificado correctamente"),
                ("ambiguos_detectados", "Mensajes ambiguos detectados (para confirmar)"),
                ("confirmaciones_innecesarias", "Confirmaciones innecesarias"),
                ("plazo_respuesta_correcto", "Plazo de respuesta correcto"),
                ("plazo_bloqueo_correcto", "Plazo de bloqueo correcto"),
            ],
        ),
        "",
        "## Columnas de planillas (50 casos): ¿qué dato es?",
        "",
        *_tabla(
            r["columnas"]["metricas"],
            [
                ("exactitud_pct", "Categoría correcta"),
                ("sensibles_detectadas", "Columnas sensibles detectadas"),
                ("falsos_sensibles", "Marcadas como sensibles sin serlo"),
                ("trampas_acertadas", "Encabezados engañosos resueltos"),
                ("sin_clasificar", "Sin clasificar"),
            ],
        ),
        "",
        "## Costo de IA por bloque (US$)",
        "",
        "| Bloque | IA sola | IA + motor |",
        "| --- | --- | --- |",
    ]
    for bloque in ("incidentes", "solicitudes", "columnas"):
        c = r[bloque]["costo_usd"]
        m.append(f"| {bloque.capitalize()} | {c.get('ia_sola', '—')} | {c.get('ia_motor', '—')} |")
    m += [
        "",
        "## Límites de esta medición",
        "",
        "- Las etiquetas fueron redactadas con asistencia de IA a partir del texto legal y están "
        "pendientes de revisión del autor y de un abogado.",
        "- Las reglas de la línea base y las instrucciones a la IA se escribieron conociendo este "
        "set; los resultados pueden ser optimistas. Se agregará un set ciego escrito por otra "
        "persona.",
        "- En la columna «IA + motor», las columnas de planilla que el perfilador clasifica con "
        "confianza media no se envían a la IA.",
        "- 50 casos por bloque: cada caso equivale a 2 puntos porcentuales.",
        "",
        "El detalle caso a caso está en `resultados/evaluacion.json`.",
    ]
    return "\n".join(m) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m privacidad.evaluacion")
    p.add_argument("--sin-ia", action="store_true", help="solo la línea base, sin llamar a la IA")
    args = p.parse_args()

    cliente = None
    modelos = "ninguno"
    rapido = extraccion = None
    if not args.sin_ia:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("Falta ANTHROPIC_API_KEY. Usa --sin-ia para la línea base.")
        from ..ia import ClienteIA
        from ..ia.cliente import MODELO_EXTRACCION, MODELO_RAPIDO

        cliente = ClienteIA(registro=SALIDA / "costos_ia.jsonl")
        rapido, extraccion = MODELO_RAPIDO, MODELO_EXTRACCION
        modelos = f"`{extraccion}` para incidentes; `{rapido}` para solicitudes y columnas"

    inicio = time.perf_counter()
    r = {
        "fecha": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "modelos": modelos,
        "incidentes": evaluar_incidentes(cliente, extraccion),
        "solicitudes": evaluar_solicitudes(cliente, rapido),
        "columnas": evaluar_columnas(cliente, rapido),
    }
    r["segundos"] = round(time.perf_counter() - inicio, 1)
    r["costo_total_usd"] = round(
        sum(sum(r[b]["costo_usd"].values()) for b in ("incidentes", "solicitudes", "columnas")), 4
    )
    SALIDA.mkdir(exist_ok=True)
    nombre = "evaluacion_base" if args.sin_ia else "evaluacion"
    (SALIDA / f"{nombre}.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (SALIDA / f"{nombre}.md").write_text(_markdown(r), encoding="utf-8")
    for bloque in ("incidentes", "solicitudes", "columnas"):
        print(bloque, json.dumps(r[bloque]["metricas"], ensure_ascii=False))
        if os.environ.get("GITHUB_ACTIONS"):
            print(
                f"::notice title={bloque}::{json.dumps(r[bloque]['metricas'], ensure_ascii=False)}"
            )
    print(f"Costo total US${r['costo_total_usd']} en {r['segundos']} s")


if __name__ == "__main__":
    main()
