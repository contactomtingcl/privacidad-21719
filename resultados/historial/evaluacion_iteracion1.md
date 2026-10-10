# Evaluación con el set etiquetado

Generado el 2026-10-10 22:30 UTC con `python -m privacidad.evaluacion`. Todos los casos son ficticios (`data/evaluacion/`).

- **Sin IA:** reglas por palabras clave; los deberes y plazos los calcula el motor.
- **IA sola:** el modelo interpreta y decide, con el texto legal a la vista.
- **IA + motor:** el sistema propuesto. La IA interpreta y el motor de reglas decide.

Modelos: `claude-sonnet-5-5` para incidentes; `claude-haiku-5-5` para solicitudes y columnas. Costo total: US$1.0527.

## Incidentes (50 casos): ¿a quién hay que avisar?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Deberes de aviso detectados | 61/76 | 74/76 | 75/76 |
| Deberes omitidos (el error más grave) | 15 | 2 | 1 |
| Alarmas de más | 6 | 2 | 3 |
| Aviso a la Agencia correcto | 74.0 | 24.0 | 96.0 |
| Aviso a titulares correcto | 80.0 | 38.0 | 98.0 |
| Reporte a la ANCI correcto | 90.0 | 40.0 | 96.0 |
| Casos con los tres deberes correctos | 58.0% | 18.0% | 92.0% |

## Solicitudes de titulares (50 casos): ¿qué pide y cuándo vence?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Derecho identificado correctamente | 84.0% | 90.0% | 84.0% |
| Mensajes ambiguos detectados (para confirmar) | 0/10 | 8/10 | 7/10 |
| Confirmaciones innecesarias | 0 | 20 | 10 |
| Plazo de respuesta correcto | 40/43 | 28/43 | 42/43 |
| Plazo de bloqueo correcto | 4/4 | 1/4 | 4/4 |

## Columnas de planillas (50 casos): ¿qué dato es?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Categoría correcta | 44.0% | 94.0% | 88.0% |
| Columnas sensibles detectadas | 4/11 | 11/11 | 11/11 |
| Marcadas como sensibles sin serlo | 2 | 1 | 2 |
| Encabezados engañosos resueltos | 0/5 | 3/5 | 0/5 |
| Sin clasificar | 23 | 0 | 0 |

## Costo de IA por bloque (US$)

| Bloque | IA sola | IA + motor |
| --- | --- | --- |
| Incidentes | 0.7068 | 0.3103 |
| Solicitudes | 0.0186 | 0.0126 |
| Columnas | 0.0027 | 0.0017 |

## Límites de esta medición

- Las etiquetas fueron redactadas con asistencia de IA a partir del texto legal y están pendientes de revisión del autor y de un abogado.
- Las reglas de la línea base y las instrucciones a la IA se escribieron conociendo este set; los resultados pueden ser optimistas. Se agregará un set ciego escrito por otra persona.
- En la columna «IA + motor», las columnas de planilla que el perfilador clasifica con confianza media no se envían a la IA.
- 50 casos por bloque: cada caso equivale a 2 puntos porcentuales.

El detalle caso a caso está en `resultados/evaluacion.json`.
