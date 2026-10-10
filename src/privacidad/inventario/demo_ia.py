"""Ejecuta el inventario con IA sobre las cuatro planillas de la demo.

    python -m privacidad.inventario.demo_ia

Escribe resultados/inventario_demo.json (completo) y resultados/inventario_demo.md (resumen).
Requiere ANTHROPIC_API_KEY. Solo procesa datos sintéticos.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..ia import ClienteIA
from .actividad import construir_actividad
from .perfilador import cargar_categorias, leer_planilla, perfilar_dataframe

RAIZ = Path(__file__).resolve().parents[3]
DATOS = RAIZ / "data" / "sinteticos" / "comercial-los-robles"
RESULTADOS = RAIZ / "resultados"
REFERENCIA = date(2026, 10, 10)

DESCRIPCIONES = {
    "paseo_fin_de_anio.xlsx": (
        "Planilla que pidió Recursos Humanos a los trabajadores para organizar el paseo de fin "
        "de año con sus hijos e hijas. La comparte con el proveedor Eventos Laja SpA."
    ),
    "nomina_trabajadores.xlsx": (
        "Nómina para calcular y pagar remuneraciones y cotizaciones. La procesa el proveedor "
        "Remuneraciones del Sur SpA."
    ),
    "clientes_marketing.csv": (
        "Base de clientes para enviar ofertas y publicidad por correo y celular. Las campañas "
        "las envía el proveedor Publicidad Austral SpA."
    ),
    "proveedores.csv": "Registro de proveedores y de sus personas de contacto comerciales.",
}


def _resumen_md(actividades: list[dict], costo_total: float) -> str:
    etiquetas = {k: v.etiqueta for k, v in cargar_categorias().items()}
    lineas = [
        "# Inventario con IA: planillas de la demo",
        "",
        "Datos sintéticos de Comercial Los Robles. Generado por "
        "`python -m privacidad.inventario.demo_ia`.",
        "",
        f"Costo total de IA: US${costo_total:.4f}",
        "",
    ]
    for a in actividades:
        lineas += [f"## {a['archivo']}", "", f"> {a['descripcion_usuario']}", ""]
        lineas.append("| Columna | Categoría | Origen | ¿Necesaria? |")
        lineas.append("| --- | --- | --- | --- |")
        for c in a["columnas"]:
            cat = etiquetas.get(c["categoria"], c["categoria"] or "—")
            nec = {True: "Sí", False: f"No: {c['motivo_innecesaria']}", None: "—"}[c["necesaria"]]
            lineas.append(f"| {c['nombre']} | {cat} | {c['origen']} | {nec} |")
        lineas.append("")
        for campo in (
            "fines",
            "base_licitud",
            "categorias_titulares",
            "destinatarios",
            "plazo_supresion",
        ):
            v = a[campo]
            lineas.append(f"- **{campo}** ({v['origen']}): {v['valor']}")
        lineas += ["", "**Alertas**", ""]
        lineas += [f"- [{al['nivel']}] {al['mensaje']}" for al in a["alertas"]] or ["- Ninguna"]
        if a["citas_rechazadas"]:
            lineas.append(f"- Citas de la IA rechazadas por no existir: {a['citas_rechazadas']}")
        lineas += ["", f"Costo IA: US${a['costo_ia_usd']:.4f}", ""]
    return "\n".join(lineas)


def main() -> int:
    RESULTADOS.mkdir(exist_ok=True)
    cliente = ClienteIA(registro=RESULTADOS / "costos_ia.jsonl")
    actividades = []
    for archivo, descripcion in DESCRIPCIONES.items():
        df = leer_planilla(DATOS / archivo)
        perfil = perfilar_dataframe(df, archivo, referencia=REFERENCIA)
        valores = {c: df[c].tolist() for c in df.columns}
        actividad = construir_actividad(perfil, valores, descripcion, cliente)
        actividades.append(actividad.model_dump(mode="json"))
        print(f"{archivo}: {len(actividad.alertas)} alertas, US${actividad.costo_ia_usd:.4f}")
    costo = sum(a["costo_ia_usd"] for a in actividades)
    (RESULTADOS / "inventario_demo.json").write_text(
        json.dumps(actividades, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (RESULTADOS / "inventario_demo.md").write_text(
        _resumen_md(actividades, costo), encoding="utf-8"
    )
    print(f"::notice title=Inventario demo::4 planillas, costo total US${costo:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
