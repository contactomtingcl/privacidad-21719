# Evaluación con el set etiquetado

Generado el 2026-10-17 18:03 UTC con `python -m privacidad.evaluacion`. Todos los casos son ficticios (`data/evaluacion/`).

- **Sin IA:** reglas por palabras clave; los deberes y plazos los calcula el motor.
- **IA sola:** el modelo interpreta y decide, con el texto legal a la vista.
- **IA + motor:** el sistema propuesto. La IA interpreta y el motor de reglas decide.

Modelos: `claude-sonnet-5-5` para incidentes; `claude-haiku-5-5` para solicitudes y columnas. Costo total: US$1.4161.

## Incidentes (50 casos): ¿a quién hay que avisar?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Deberes de aviso detectados | 62/77 | 69/77 | 75/77 |
| Deberes omitidos (el error más grave) | 15 | 8 | 2 |
| Alarmas de más | 5 | 11 | 0 |
| Aviso a la Agencia correcto | 74.0% | 42.0% | 92.0% |
| Aviso a titulares correcto | 80.0% | 70.0% | 100.0% |
| Reporte a la ANCI correcto | 90.0% | 78.0% | 98.0% |
| Casos con los tres deberes correctos | 58.0% | 36.0% | 92.0% |
| Respuestas fallidas de la IA | 0 | 0 | 0 |

## Solicitudes de titulares (50 casos): ¿qué pide y cuándo vence?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Derecho identificado correctamente | 84.0% | 90.0% | 100.0% |
| Mensajes ambiguos detectados (para confirmar) | 0/10 | 7/10 | 8/10 |
| Confirmaciones innecesarias | 0 | 8 | 4 |
| Plazo de respuesta correcto | 40/43 | 39/43 | 43/43 |
| Plazo de bloqueo correcto | 4/4 | 1/4 | 4/4 |
| Respuestas fallidas de la IA | 0 | 0 | 0 |

## Frase de respaldo de la IA (IA + motor)

La IA copia el fragmento del mensaje en que apoya cada hecho o derecho; el código comprueba que esté en el texto que la IA recibió (enmascarado). La frase no decide nada.

| Métrica | Incidentes | Solicitudes |
| --- | --- | --- |
| Frases entregadas | 176 | 52 |
| Frases encontradas en el mensaje | 176/176 (100.0%) | 52/52 (100.0%) |
| Hechos o derechos afirmados con frase verificada | 151/158 (95.6%) | 52/52 (100.0%) |

## Columnas de planillas (50 casos): ¿qué dato es?

| Métrica | Sin IA (palabras clave) | IA sola | IA + motor |
| --- | --- | --- | --- |
| Categoría correcta | 44.0% | 92.0% | 88.0% |
| Columnas sensibles detectadas | 4/11 | 11/11 | 11/11 |
| Marcadas como sensibles sin serlo | 2 | 1 | 2 |
| Encabezados engañosos resueltos | 0/5 | 3/5 | 1/5 |
| Sin clasificar | 23 | 0 | 0 |
| Correcciones de la IA enviadas a revisión humana | 0 | 0 | 1 |

## Costo de IA por bloque (US$)

| Bloque | IA sola | IA + motor |
| --- | --- | --- |
| Incidentes | 0.9489 | 0.4259 |
| Solicitudes | 0.0205 | 0.0157 |
| Columnas | 0.0027 | 0.0024 |

## Límites de esta medición

- Las etiquetas fueron redactadas con asistencia de IA a partir del texto legal y están pendientes de revisión del autor y de un abogado.
- Las reglas de la línea base y las instrucciones a la IA se escribieron conociendo este set; los resultados pueden ser optimistas. Se agregará un set ciego escrito por otra persona.
- En columnas, «IA + motor» significa perfilador más IA: la IA no puede cambiar lo que el código confirmó por formato, ni quitar la marca de sensible (esa corrección queda para revisión humana).
- 50 casos por bloque: cada caso equivale a 2 puntos porcentuales.

El detalle caso a caso está en `resultados/evaluacion.json`.
