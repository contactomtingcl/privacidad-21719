# Evaluación con el set etiquetado

Generado el 2026-10-10 22:36 UTC con `python -m privacidad.evaluacion`. Todos los casos son ficticios (`data/evaluacion/`).

- **Sin IA:** reglas por palabras clave; los deberes y plazos los calcula el motor.
- **IA sola:** el modelo interpreta y decide, con el texto legal a la vista.
- **IA + motor:** el sistema propuesto. La IA interpreta y el motor de reglas decide.

Modelos: `claude-sonnet-5-5` para incidentes; `claude-haiku-5-5` para solicitudes y columnas. Costo total: US$1.2916.

## Incidentes (50 casos): ¿a quién hay que avisar?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Deberes de aviso detectados | 62/77 | 70/77 | 76/77 |
| Deberes omitidos (el error más grave) | 15 | 7 | 1 |
| Alarmas de más | 5 | 8 | 0 |
| Aviso a la Agencia correcto | 74.0% | 38.0% | 96.0% |
| Aviso a titulares correcto | 80.0% | 68.0% | 100.0% |
| Reporte a la ANCI correcto | 90.0% | 84.0% | 100.0% |
| Casos con los tres deberes correctos | 58.0% | 32.0% | 96.0% |
| Respuestas fallidas de la IA | 0 | 0 | 0 |

## Solicitudes de titulares (50 casos): ¿qué pide y cuándo vence?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Derecho identificado correctamente | 84.0% | 90.0% | 96.0% |
| Mensajes ambiguos detectados (para confirmar) | 0/10 | 7/10 | 7/10 |
| Confirmaciones innecesarias | 0 | 9 | 2 |
| Plazo de respuesta correcto | 40/43 | 39/43 | 42/43 |
| Plazo de bloqueo correcto | 4/4 | 1/4 | 4/4 |
| Respuestas fallidas de la IA | 0 | 0 | 0 |

## Columnas de planillas (50 casos): ¿qué dato es?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Categoría correcta | 44.0% | 90.0% | 90.0% |
| Columnas sensibles detectadas | 4/11 | 11/11 | 11/11 |
| Marcadas como sensibles sin serlo | 2 | 1 | 2 |
| Encabezados engañosos resueltos | 0/5 | 3/5 | 1/5 |
| Sin clasificar | 23 | 0 | 0 |
| Correcciones de la IA enviadas a revisión humana | 0 | 0 | 1 |

## Costo de IA por bloque (US$)

| Bloque | IA sola | IA + motor |
| --- | --- | --- |
| Incidentes | 0.9417 | 0.3117 |
| Solicitudes | 0.0199 | 0.0131 |
| Columnas | 0.0027 | 0.0025 |

## Límites de esta medición

- Las etiquetas fueron redactadas con asistencia de IA a partir del texto legal y están pendientes de revisión del autor y de un abogado.
- Las reglas de la línea base y las instrucciones a la IA se escribieron conociendo este set; los resultados pueden ser optimistas. Se agregará un set ciego escrito por otra persona.
- En columnas, «IA + motor» significa perfilador más IA: la IA no puede cambiar lo que el código confirmó por formato, ni quitar la marca de sensible (esa corrección queda para revisión humana).
- 50 casos por bloque: cada caso equivale a 2 puntos porcentuales.

El detalle caso a caso está en `resultados/evaluacion.json`.
