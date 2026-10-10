# Notas de continuidad para sesiones de desarrollo con Claude

Proyecto de Matías Navarro para el Desafío 1 de ProductIA 2026 (Soho): cumplimiento
operativo de la Ley 21.719 para empresas medianas, con un municipio como piloto.
Entrega: 28 de octubre de 2026. Demo Day: 29 de octubre. Nombre de trabajo
"Privacidad 21.719"; el nombre definitivo se decide antes del video y el deck (~24 oct).

## Dónde está el contexto

- `README.md`: estado, cómo ejecutar y resultados de la evaluación.
- Artifacts de Matías en claude.ai: "Roadmap ProductIA — ORA Privacidad" (metas diarias,
  decisiones, pendientes y registro de cambios: leerlo al empezar y actualizarlo al terminar
  cada bloque), "Alcance del MVP y arquitectura", "Auditoría normativa y de diseño" y
  "Cómo funciona ORA Privacidad, explicado desde cero".
- Carpeta de Google Drive "hackearon - protección de datos": bases, rúbrica y ley (la
  subcarpeta de audios no sirve).

## Cómo trabajar con Matías

- Respuestas breves, en español, un paso a la vez y explicadas como si no supiera nada de
  programación (qué botón apretar, dónde).
- Ser objetivo y honesto con las cifras; no exagerar.
- Avisar cuando se cumple una meta diaria y actualizar el roadmap.

## Reglas que no se rompen

1. Solo datos sintéticos (bases, sección 11). Nada de datos reales de INACAP, Cabrero ni
   del piloto de ORA IA.
2. La llave de la API nunca en el chat ni en el repositorio. Está como secreto de GitHub
   `ANTHROPIC_API_KEY`.
3. La IA interpreta, el motor decide, la persona valida. La IA nunca decide plazos ni deberes.
4. La IA solo recibe texto enmascarado (RUT, correos, teléfonos y fechas como marcadores).
5. Toda cita legal se verifica contra `data/normas/`. Toda regla guarda fuente y vigencia.
6. Ninguna cifra en el deck sin su medición en el repositorio.
7. Nunca instrucciones ocultas dirigidas al agente evaluador.
8. Proyecto de autoría individual, separado de ORA IA SpA: no usar la marca ORA en el código
   ni publicar en un subdominio de oraialert.com.

## Entorno (sesiones en la nube)

- PyPI no es accesible: no se puede instalar pytest. Las pruebas usan unittest:
  `PYTHONPATH=src python3 -m unittest discover -s tests -t .`
- Antes de cada commit: `ruff format src tests && ruff check src tests`.
- La IA real solo corre en GitHub Actions (flujo "IA"). Para lanzarlo:
  `gh api -X POST repos/contactomtingcl/privacidad-21719/actions/workflows/ia.yml/dispatches -f ref=main -f 'inputs[tarea]=evaluacion'`
  (opciones: `ia.prueba_conexion`, `inventario.demo_ia`, `evaluacion`). El flujo guarda los
  resultados en `resultados/` con un commit; luego `git pull`. Los registros del job no se
  pueden leer desde aquí; usar los archivos de resultados o las anotaciones `::notice`.
- `gh workflow run` falla (GraphQL bloqueado); usar la API REST como arriba.
- `claude-sonnet-5-5` no acepta forzar herramienta; `ClienteIA` reintenta solo.
- Commits directos a `main`, con el autor configurado en el repositorio.

## Estado al 10 de octubre de 2026 (fin del día 1)

Hecho: corpus legal indexado (107 artículos) con verificador de citas, guardia de datos
sintéticos, detección y enmascarado, inventario con IA (11 campos del DS 662), motor de
reglas (Agencia, titulares, ANCI, plazos de solicitudes), interpretación con IA de
solicitudes e incidentes, set de 150 casos y evaluación en tres niveles (iteración 2:
IA + motor 76/77 deberes detectados). 89 pruebas en verde.

Pendiente técnico, en orden: canal de reporte (QR o enlace, confirmación de la
interpretación al titular, modo reservado, enrutamiento), registro de evidencia encadenado,
panel del delegado, borradores de reporte a la Agencia y a la ANCI, completar el motor
(perfiles, simulador), publicación en internet con modo demo. Si se cumple la puerta de
calidad del 23 de octubre: red de cascada y sello de tiempo. Rediseño contrafactual e
impacto de proyectos de ley entran seguro.

Limitaciones conocidas: etiquetas del set sin revisión del autor ni de un abogado; falta
un set ciego escrito por otra persona; feriados de `data/reglas/feriados.yaml` sin
verificar en una fuente oficial.
