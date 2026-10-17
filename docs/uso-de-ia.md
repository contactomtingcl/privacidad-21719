# Declaración de uso de IA

Entregable 06 de ProductIA: modelos, prompts, datasets y supervisión humana. Estado al 17 de octubre de 2026.

Hay dos usos distintos: la IA **dentro del producto** (lo que hace cuando alguien lo usa) y la IA **en el desarrollo** (cómo se construyó).

## 1. IA dentro del producto

### Qué hace y qué no hace

| La IA sí | La IA nunca |
| --- | --- |
| Lee un reporte de incidente y propone los hechos (qué les pasó a los datos, si hay datos sensibles o de menores, si fue un ciberincidente). | Decide si hay que avisar a la Agencia, a las personas o a la ANCI. Lo decide el motor de reglas. |
| Lee el mensaje de una persona y propone qué derechos ejerce (acceso, rectificación, supresión, oposición, portabilidad, bloqueo) y si conviene preguntarle qué quiso decir. | Calcula plazos. Los calcula el motor desde la fecha de ingreso, con días hábiles y feriados verificados. |
| Clasifica columnas ambiguas de una planilla y redacta el registro de actividad del DS 662 en lenguaje simple. | Ve los valores de una planilla. Recibe encabezados y la forma de los valores (`aaaa 9999`), o valores enmascarados si la columna tiene pocas opciones. |
| Copia la frase del mensaje en que apoya cada hecho o derecho. | Recibe RUT, correos, teléfonos o fechas: llegan como marcadores (`[RUT_1]`). |
| | Escribe los borradores para la Agencia y la ANCI, los avisos a las áreas o el texto legal que se muestra: todo eso sale de código y del corpus oficial. |

### Modelos

| Tarea | Modelo | Archivo |
| --- | --- | --- |
| Solicitudes de personas | `claude-haiku-5-5` | `src/privacidad/interpretacion/solicitudes.py` |
| Reportes de incidentes | `claude-sonnet-5-5` | `src/privacidad/interpretacion/incidentes.py` |
| Columnas ambiguas de planillas | `claude-haiku-5-5` | `src/privacidad/inventario/actividad.py` |
| Registro de actividad (DS 662) | `claude-sonnet-5-5` | `src/privacidad/inventario/actividad.py` |

Proveedor: Anthropic, por su API (`src/privacidad/ia/cliente.py`). No hay ajuste fino (fine-tuning) ni modelos propios. La llave vive como secreto de GitHub y de Render, nunca en el repositorio.

### Prompts

Los prompts están completos en el código, sin partes ocultas:

- `SISTEMA` en `interpretacion/incidentes.py` y en `interpretacion/solicitudes.py`.
- `SISTEMA_COLUMNAS` y `SISTEMA_ACTIVIDAD` en `inventario/actividad.py`.
- `evaluacion/ia_sola.py` arma los prompts de «la IA decidiendo sola» (con el texto legal a la vista) solo para medir; el producto no los usa.

Decisiones de diseño de los prompts:

- **Salida estructurada:** cada llamada responde llamando a una herramienta con un esquema JSON fijo (listas cerradas de valores). Un derecho fuera de la lista se descarta; si los hechos de un incidente no calzan con el esquema, el caso queda «Sin lectura de la IA».
- **Separar interpretar de decidir:** los prompts piden describir hechos y dicen explícitamente que la IA no decide avisos ni calcula plazos.
- **Frase de respaldo:** la IA copia el fragmento exacto del mensaje que sostiene cada hecho; `interpretacion/respaldo.py` comprueba que esté en el texto. El panel muestra la frase y avisa si no está o si falta.
- **Ante la duda, lo más protector:** en columnas, si duda entre una categoría sensible y una que no lo es, elige la sensible.

### Si la IA falla

- Sin respuesta, con error o sin llave: el caso queda «Sin lectura de la IA», los plazos corren igual y el delegado completa los hechos con un formulario. Nada se marca como «no corresponde» por omisión.
- En un incidente sin lectura se muestran desde el primer minuto los relojes de la ANCI que correrían si fuera un ciberincidente.
- La demo permite simular una caída de la IA («Canal y código QR» → «Simular caída de la IA»).

### Costo medido

Cada llamada registra modelo, tokens, costo y propósito, nunca el contenido (`resultados/costos_ia.jsonl`). Costo del sistema propuesto en la última medición: ver [resultados/evaluacion.md](../resultados/evaluacion.md). Precios de referencia en `data/precios_modelos.yaml`, con fuente y fecha de consulta.

## 2. Datasets

| Dataset | Origen | Uso |
| --- | --- | --- |
| Planillas de Comercial Los Robles (paseo, nómina, clientes, proveedores) | Generadas por código con semilla fija (`src/privacidad/sinteticos/`) | Demo e inventario |
| Casos de la demo | Escritos a mano por el proyecto (`data/demo/casos.yaml`) | Demo, con respuestas de la IA grabadas |
| Set de evaluación: 50 incidentes, 50 solicitudes, 50 columnas | Redactados con asistencia de IA (`data/evaluacion/`) | Medir sin IA, IA sola e IA + motor |
| Corpus legal | Textos oficiales del Diario Oficial (`data/normas/`) | Citas verificadas, nunca para entrenar |

**Solo datos sintéticos.** Ningún dato real de personas, de INACAP, de la Municipalidad de Cabrero ni de pilotos de otros proyectos. La guardia (`src/privacidad/guardia.py`) rechaza RUT fuera del tramo ficticio, correos de dominios reales y teléfonos fuera del rango reservado.

**Límites del set de evaluación:** las etiquetas se redactaron con asistencia de IA y están pendientes de revisión del autor y de un abogado. Los prompts y la línea base se escribieron conociendo el set, así que hace falta un set ciego escrito por otra persona.

## 3. Supervisión humana

La persona tiene la última palabra en cada paso:

1. **La persona que reporta confirma.** Si su mensaje admite lecturas distintas, elige entre seis opciones en lenguaje simple, sin IA. Si no responde, se aplica una lectura reversible: nunca se borran datos por defecto.
2. **El delegado corrige hechos, nunca plazos.** El motor vuelve a decidir con los hechos corregidos. La propuesta de la IA se conserva para comparar.
3. **El delegado resuelve las dudas del motor** («Decide tú») y **valida** cada caso. Validar no es enviar: el sistema no envía nada a ninguna autoridad.
4. **El delegado valida el registro de inventario** que redactó la IA.
5. **Todo queda en la cadena de evidencia** (SHA-256 por organización): quién hizo qué, cuándo y por qué motivo de lista cerrada.
6. **Cuánto corrige la persona a la IA** se cuenta desde esa cadena (`canal/correcciones.py`). Con datos ficticios mide el mecanismo; la cifra real saldrá de las pruebas con usuarios.

## 4. IA en el desarrollo

- El código, las pruebas y la documentación se escribieron con asistencia de Claude (Anthropic), en sesiones dirigidas por el autor. Él define el problema, el alcance y las decisiones de diseño y legales, y revisa cada entrega. Los commits asistidos llevan la línea `Co-Authored-By: Claude`.
- Las decisiones con efecto legal o de producto las tomó el autor y quedan registradas (por ejemplo, el bloqueo preventivo en la confirmación con la persona, o qué sugerencias de la mentoría de diseño se aplicaron).
- Toda cita legal se verifica contra los textos oficiales de `data/normas/` con pruebas automáticas, sin depender de lo que «recuerde» un modelo.
- Las cifras del README y del deck salen de mediciones guardadas en `resultados/`, con su fecha. Las anteriores, incluidos sus errores, quedan en `resultados/historial/`.
- No hay instrucciones ocultas dirigidas a agentes evaluadores.
