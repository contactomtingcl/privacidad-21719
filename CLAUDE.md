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

## Estado al 17 de octubre de 2026

Hecho: corpus legal indexado (107 artículos) con verificador de citas, guardia de datos
sintéticos, detección y enmascarado, inventario con IA (11 campos del DS 662), motor de
reglas (Agencia, titulares, ANCI, plazos de solicitudes), interpretación con IA de
solicitudes e incidentes, set de 150 casos y evaluación en tres niveles (iteración 2:
IA + motor 76/77 deberes detectados; iteración 3 del 12 oct con frase de respaldo: 76/77, solicitudes
98%). 416 pruebas (5 omitidas sin segno) en verde.

Canal de reporte (primera versión, 10 oct): enlace firmado y QR (segno), confirmación al
titular con menú fijo y, sin respuesta a los 5 días, lectura reversible: oposición + bloqueo
temporal, nunca supresión por defecto (regla `confirmacion_titular`, pendiente de revisión legal), modo reservado con Fernet (llave en archivo/variable, nunca en
el repositorio), Starlette + Jinja2, casos en sqlite3. Criterio: librerías estándar y
probadas antes que código propio. `segno` no se instala aquí (sin PyPI): sus pruebas se
omiten localmente y corren en CI; la llave simétrica implica que quien administra el servidor
puede abrir identidades reservadas (declarado en el README).

Enrutamiento y evidencia (11 oct): `data/canal/enrutamiento.yaml` define delegado y áreas
ficticias por organización; `canal/enrutamiento.py` asigna sin IA (delegado siempre, área por
palabras o por tipo, reservado solo al delegado) con porqué y urgencia desde los plazos del
motor. `canal/evidencia.py`: cadena SHA-256 (hashlib) en la misma base sqlite, anotada en la
misma transacción que el caso, disparadores contra cambios y borrados, sin datos personales,
comando `evidencia` para verificar. Límite declarado: borrar el final de la cadena solo se
detecta con la huella final guardada aparte (`--cabeza`).

Panel del delegado (11 oct, diseño aprobado por Matías tras tres auditorías contra la rúbrica):
`src/privacidad/panel/` montado en `/panel` del mismo programa. Starlette + Jinja2 + htmx 2.0.11
guardado en el repositorio (sin eval), fuentes locales, CSP sin código en línea, tema oscuro y
claro, animaciones solo CSS con "reducir movimiento". Acciones en `canal/delegado.py` (corregir
hechos con motivo de lista cerrada, resolver "revisar", validar, abrir identidad con contraseña).
Usuarios con scrypt (`panel/usuarios.py`), comando `usuario`. Demo: `servir --demo` con
`data/demo/casos.yaml` (respuestas grabadas) y alteración real sobre una copia. Para revisar las
pantallas: levantar la demo y tomar capturas con Playwright (Chromium en /opt/pw-browsers).

Borradores de reporte (11 oct): `src/privacidad/reportes/` arma con código, sin IA, un borrador
para la Agencia (art. 14 sexies) y otro para la ANCI (alerta 3 h, actualización 72 h, informe
final) cuando el deber es "sí" o "revisar". Lo que no se sabe queda «[Completar: …]». El de la
ANCI no recibe texto, resumen ni identidad, y `revisar_datos_personales` lo bloquea si aparece un
RUT, correo, teléfono o fecha numérica. En el panel: `/panel/caso/{id}/borrador/{agencia|anci}`,
descarga en texto y «Marcar como revisado» (evento `borrador_revisado` con la huella del texto
escrita con letras, para que la evidencia no la confunda con un teléfono). Nuevas fuentes en
`reglas.yaml` (contenido de los reportes), versión 2026-10-11.

Frase de respaldo (12 oct): la IA copia el fragmento del mensaje que sostiene cada hecho
(incidentes) o derecho (solicitudes); `interpretacion/respaldo.py` verifica que esté en el texto
enmascarado. `Caso.respaldos_ia` guarda las frases; la evidencia solo cuenta cuántas y cuántas
verificadas. Panel: «Se basó en…», aviso si no está en el mensaje o si un dato afirmado no trae
frase (`afirmados_incidente`). Medición: 179/179 frases verificadas en incidentes, 52/52 en
solicitudes; 156/161 hechos afirmados con frase. Costo por incidente subió de US$0,006 a 0,008.

Publicado (11 oct) en Render: https://privacidad-21719.onrender.com (panel en /panel/, canal y
QR en /panel/canal). `render.yaml` + `Dockerfile`; se publica solo tras pasar la CI (checksPass).
Plan 0.5c-512mb + disco 1 GB = US$7,25/mes, región Virginia. Secretos en el panel de Render
(ANTHROPIC_API_KEY la pegó Matías). Dominio propio: comprarlo cuando se decida el nombre (~24 oct).
Desde aquí la dirección se revisa con WebFetch (curl al dominio está bloqueado por el proxy).

Claridad tras la mentora de Diseño (17 oct, Andrea Vásquez; decisión de Matías: se aplica solo
lo que mejora la comprensión sin cambiar lógica ni exactitud legal). Bandeja: «Casos con fecha
límite legal» (vencidos aparte de los que vencen en <3 h), «Por validar» (= por validar + sin
lectura de la IA), «Validados» (nunca «resueltos»: el sistema no envía nada); evidencia como botón
con estado y alarma si no calza; tema en el menú lateral; filtro solo «Urgencia según plazo»;
si el plazo venció, «el deber sigue» + borrador ANCI. Canal: ícono, para quién y ejemplo por opción;
«Qué pasa después de enviar» con 30 días + prórroga leídos de `reglas.yaml` (`fuente_prorroga`,
versión 2026-10-17). Íconos de Lucide (ISC) en `src/privacidad/iconos/`. No aplicado: tope de
vencidos (sin base legal), «casos pendientes»/«resueltos» (inexactos). Pendiente: ficha del caso
(menos texto, primero decisión y plazo), paleta de marca con el nombre definitivo.

Cifra de correcciones (17 oct): `canal/correcciones.py` cuenta desde la cadena verificada
(corregidos frente a la IA, motivo, cambió un deber, validados sin corrección, completados sin
IA, confirmaciones de titulares). Pantalla Evidencia y comando `correcciones`. Aún sin cifra
medida: sale de las pruebas con usuarios. Ojo: la demo pública es compartida; las correcciones
de un participante las ve el siguiente (falta reiniciar casos entre pruebas).

Auditoría de comprensión del delegado (17 oct, artifact "Auditoría de comprensión del delegado
— Privacidad 21.719"): 6 graves (G1-G6), 13 de lenguaje (I1-I13), 5 menores. Decisiones de
Matías: entran «Ya lo envié» por deber (validar no es enviar; el caso sigue en la bandeja hasta
enviar lo que corresponde) y «Derivar a…» un área (mismo correo que los avisos; reservados sin
identidad). Criterio: un texto o botón de una función planificada para la versión final se
conserva («Se envió a» se queda porque vienen los avisos); se cambia solo si no llegará.

Pendiente técnico, en orden: (sáb 17) registro de evidencia por organización + copia limpia de
la demo por participante + textos y diseño de la auditoría; (dom 18) «Ya lo envié», formulario
vacío si la IA no leyó, cómo responder a la persona; (19-20) avisos por correo/Telegram a los
destinos + «Derivar a…»; completar el motor
(perfiles, operadores de importancia vital, simulador). Si se cumple la puerta de calidad del 23 de octubre:
red de cascada y sello de tiempo. Rediseño contrafactual e impacto de proyectos de ley entran
seguro.

Hallazgo del 11 oct, sin resolver: si el titular no responde, la lectura por defecto agrega
un bloqueo temporal cuyo plazo (2 días hábiles desde el ingreso) normalmente ya venció. El
enrutamiento lo marca como urgencia inmediata; falta decidir si se acorta la espera o se
aplica el bloqueo desde el ingreso. Va a la revisión legal.

Limitaciones conocidas: etiquetas del set sin revisión del autor ni de un abogado; falta
un set ciego escrito por otra persona; feriados de `data/reglas/feriados.yaml` sin
verificar en una fuente oficial.
