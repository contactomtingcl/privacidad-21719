# Privacidad 21.719

> Nombre de trabajo; el nombre definitivo se decide antes de la entrega.

Cumplimiento operativo de la Ley 21.719 para empresas medianas y municipios. Proyecto para el Desafío 1 de **ProductIA 2026** (Soho).

Privacidad 21.719 sabe qué datos personales tiene una organización, recibe en minutos los reportes de titulares, trabajadores y proveedores, decide plazos y deberes legales con reglas verificables y deja la evidencia armada.

> **Principio de diseño:** la IA interpreta, el motor de reglas decide y la persona valida. Ningún plazo ni deber legal depende de la respuesta de un modelo de IA.

## Estado

En construcción (entrega: 28 de octubre de 2026). Avance actual:

| Componente | Estado |
| --- | --- |
| Corpus legal indexado por artículo y verificador de citas | Listo |
| Guardia de datos sintéticos | Lista |
| Detección y enmascarado de RUT, correos, teléfonos y fechas | Listo |
| Inventario: perfilado de planillas y cálculo de edades | Listo |
| Inventario con IA: columnas ambiguas y registro de actividad (11 campos del DS 662) | Primera versión ([resultados de la demo](resultados/inventario_demo.md)) |
| Interpretación con IA de solicitudes de titulares y reportes de incidentes | Primera versión |
| Motor de reglas: deberes ante incidentes (Agencia, titulares, ANCI) y plazos de solicitudes | Primera versión |
| Set etiquetado de 150 casos y evaluación en tres niveles | Listo ([resultados](resultados/evaluacion.md)) |
| Canal de reporte (QR o enlace) | Pendiente |
| Registro de evidencia | Pendiente |

## Cómo ejecutar

Requiere Python 3.12 o superior.

```bash
pip install -e ".[dev]"
pytest -q                                   # pruebas
python -m privacidad.corpus             # resumen del corpus legal
python -m privacidad.corpus --verificar # comprueba que el índice está al día
python -m privacidad.sinteticos         # regenera los datos de la demo
python -m privacidad.inventario data/sinteticos/comercial-los-robles/paseo_fin_de_anio.xlsx --referencia 2026-10-10
python -m privacidad.evaluacion --sin-ia      # evaluación sin IA (sin costo)
python -m privacidad.evaluacion               # evaluación completa (requiere ANTHROPIC_API_KEY)
```

## Evaluación

El sistema se mide con 150 casos ficticios etiquetados (`data/evaluacion/`): 50 reportes de incidentes, 50 mensajes de titulares y 50 columnas de planillas. Se comparan tres niveles: reglas por palabras clave sin IA, la IA decidiendo sola con el texto legal a la vista, y el sistema propuesto (la IA interpreta y el motor de reglas decide).

Resultado de la iteración 2 ([detalle](resultados/evaluacion.md)):

| Métrica | Sin IA | IA sola | IA + motor |
| --- | --- | --- | --- |
| Incidentes: deberes de aviso detectados | 62/77 | 70/77 | 76/77 |
| Incidentes: casos con los tres deberes correctos | 58% | 32% | 96% |
| Solicitudes: derecho identificado correctamente | 84% | 90% | 96% |
| Solicitudes: plazo de respuesta correcto | 40/43 | 39/43 | 42/43 |
| Columnas: sensibles detectadas | 4/11 | 11/11 | 11/11 |

Costo de IA del sistema propuesto: US$0,006 por incidente y menos de US$0,001 por solicitud. Cuando la IA decide sola, deja como "revisar" 27 de los 37 casos en que el aviso a la Agencia es obligatorio: no se equivoca hacia el "no", pero no decide.

Límites: las etiquetas fueron redactadas con asistencia de IA y están pendientes de revisión del autor y de un abogado; las instrucciones a la IA y la línea base se escribieron conociendo el set, por lo que se agregará un set ciego escrito por otra persona. La primera medición, con sus errores, está en [`resultados/historial/`](resultados/historial/).

## Corpus legal

El texto que el sistema muestra al usuario sale siempre de `data/normas/`, nunca de un modelo de IA. Si la IA cita un artículo, el verificador comprueba que el artículo existe y que el fragmento citado aparece en el texto oficial.

| Norma | Clave | Cobertura | Fuente |
| --- | --- | --- | --- |
| Ley 19.628 según el texto fijado por la Ley 21.719 | `ley-19628` | Artículos 1 a 16 sexies y 20 a 55 con texto completo; 2, 17, 18 y 19 como instrucciones de modificación | [Diario Oficial, 13 dic 2024](https://www.diariooficial.interior.gob.cl/publicaciones/2024/12/13/44023/01/2583630.pdf) |
| Ley 21.719 (artículos propios y transitorios) | `ley-21719` | Completa | Misma publicación |
| Decreto 662 de 2025, reglamento del modelo de prevención | `ds-662-2025` | Artículos 1, 2, 3, 6, 7, 8, 11 y 13 | [Diario Oficial, 9 sept 2026](https://www.diariooficial.interior.gob.cl/publicaciones/2026/09/09/44546/01/2865940.pdf) |
| Ley 21.663, Ley Marco de Ciberseguridad | `ley-21663` | Artículos 1, 4, 9, 27, 38 y 40 | [Diario Oficial, 8 abr 2024](https://www.diariooficial.interior.gob.cl/publicaciones/2024/04/08/43820/01/2475674.pdf) |

`data/normas/indice.json` es el índice exportado (107 artículos). La integración continua falla si queda desactualizado respecto de los textos.

## Datos: solo sintéticos

Las bases del concurso (sección 11) prohíben usar datos reales. La guardia (`src/privacidad/guardia.py`) se ejecuta antes de procesar cualquier dato y rechaza lo que podría ser real, sin mostrar el valor completo en los mensajes de error.

Convenciones del proyecto para datos sintéticos:

- **RUT:** cuerpo entre 50.000.000 y 59.999.999, con dígito verificador válido. Es una convención interna para reconocer los datos de prueba; un RUT fuera de ese tramo se trata como posiblemente real.
- **Correo:** dominios reservados por los RFC 2606 y 6761 (`example.com`, `example.org`, `example.net`, `.example`, `.test`, `.invalid`).
- **Móvil:** `+56 9 0000 XXXX`.

Los datos de la demo son de **Comercial Los Robles**, una empresa mediana ficticia de 120 trabajadores (`data/sinteticos/comercial-los-robles/`): la planilla del paseo de fin de año (84 hijos e hijas, 61 menores de 14 años, con alergias), la nómina de remuneraciones, la base de clientes para publicidad y los proveedores con los datos que reciben. El generador es determinista: la misma semilla produce los mismos datos.

Límites conocidos: la guardia detecta RUT escritos con guion y no puede reconocer nombres o direcciones reales; por eso los generadores de datos usan listas cerradas de nombres ficticios.

## Trabajo previo y uso de IA

- **Trabajo previo del autor:** el diseño se inspira en la experiencia previa del autor con sistemas de enrutamiento de alertas y con la arquitectura "la IA interpreta, el motor decide, la persona valida" de su proyecto [Motor de Ejecutabilidad](https://github.com/contactomtingcl/motor-ejecutabilidad) (Claude Impact Lab 2026). No se reutiliza código de otros proyectos: todo el código de este repositorio se escribe desde cero durante ProductIA, a partir del 10 de octubre de 2026, y es de autoría individual.
- **Uso de IA en el desarrollo:** el código se escribe con asistencia de Claude (Anthropic) bajo dirección y revisión del autor. La declaración completa de uso de IA (modelos, prompts, datos y supervisión humana) se publicará en `docs/`.

## Licencia

Código fuente visible para evaluación; todos los derechos reservados. Ver [LICENSE](LICENSE).
