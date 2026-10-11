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
| Canal de reporte (QR o enlace), confirmación al titular y modo reservado | Primera versión ([cómo usarlo](#canal-de-reporte)) |
| Enrutamiento de reportes al delegado y al área dueña de los datos | Primera versión ([cómo funciona](#enrutamiento-y-evidencia)) |
| Registro de evidencia encadenado (SHA-256) con verificación | Primera versión ([cómo funciona](#enrutamiento-y-evidencia)) |
| Panel del delegado: bandeja en vivo, ficha del caso, correcciones, validación y evidencia | Primera versión ([cómo usarlo](#panel-del-delegado)) |

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

El canal de reporte tiene su propia guía más abajo.

## Canal de reporte

Cada organización tiene un enlace propio, firmado, que se reparte también como código QR. Quien lo abre elige si quiere ejercer un derecho sobre sus datos o avisar de un incidente, y recibe un código de seguimiento para volver.

Cómo funciona, en cuatro reglas:

- **La IA propone, el motor decide, la persona confirma.** Si el mensaje de un titular puede leerse de más de una forma, la persona elige entre seis opciones en lenguaje simple (sin IA en ese paso). El plazo legal corre desde que ingresó el mensaje, nunca desde la confirmación.
- **Si no responde**, pasados 5 días se tramita con una lectura reversible: nunca se borran datos por defecto. Una supresión pasa a oposición más bloqueo temporal de esos datos, y se le avisa que puede pedir la supresión cuando quiera. Los 5 días y este criterio son una decisión de diseño, no una exigencia de la ley: están en `data/reglas/reglas.yaml` (regla `confirmacion_titular`) y **pendientes de revisión legal**.
- **Si la IA falla**, el caso queda "requiere revisión", el reloj corre igual y nada se marca como "sin deber". En un incidente se muestran desde el primer minuto los relojes de la ANCI que correrían si fuera un ciberincidente.
- **Modo reservado**, solo para avisos de incidente: el nombre y el contacto se guardan cifrados. Si no hay llave configurada, el canal rechaza el reporte en vez de guardarlo sin cifrar. Quien ejerce un derecho debe identificarse (art. 11), por eso ahí no existe.

Se usan librerías estándar y probadas en vez de código propio: `segno` (código QR), `cryptography` (Fernet, para el modo reservado), `itsdangerous` (enlaces firmados), `sqlite3` (casos), Starlette con Jinja2 (pantallas con escape automático) y `babel` (fechas en español).

### Probarlo en tu computador

```bash
pip install -e ".[dev]"
python -m privacidad.canal secreto      # crea el secreto de los enlaces (no se muestra en pantalla)
python -m privacidad.canal llave        # crea la llave del modo reservado (no se muestra en pantalla)
export PRIVACIDAD_SECRETO_ENLACES="$(cat secreto-enlaces.key)"
export PRIVACIDAD_LLAVE_RESERVADA_ARCHIVO=llave-reservada.key
python -m privacidad.canal servir --datos casos-demo     # imprime un enlace por organización
python -m privacidad.canal enlace --org comercial-los-robles   # guarda el QR en canal-comercial-los-robles.svg
python -m privacidad.canal identidad --carpeta casos-demo --caso CODIGO   # el delegado abre una identidad reservada
python -m privacidad.canal evidencia --carpeta casos-demo                 # revisa que la evidencia no se haya alterado
```

Sin `ANTHROPIC_API_KEY` el canal funciona igual y deja los casos en revisión; con ella, la IA interpreta el texto ya enmascarado. Los archivos `*.key` y la carpeta `casos-demo/` están en `.gitignore`: nunca se suben.

### Límites conocidos

- **Llave simétrica:** con Fernet, quien administra el servidor y tiene la llave puede abrir las identidades reservadas. Las pantallas lo dicen así ("solo se abren con una llave de acceso restringido"), no "solo el delegado". Pasar a un esquema donde el servidor solo pueda cifrar (llave pública del delegado) queda en el roadmap.
- El cifrado protege los campos de nombre y contacto. Si la persona escribe su nombre dentro del relato, ese texto no se cifra; los nombres no se detectan automáticamente.
- El código QR depende de `segno`; en entornos sin acceso a PyPI sus pruebas se omiten y solo corren en la integración continua.
- Aún no hay avisos por correo o Telegram: el enrutamiento decide quién recibe cada caso y el delegado lo ve en el panel, pero las áreas todavía no reciben nada. No se publica una cifra de rendimiento del canal: no hay medición.
- El servidor no registra IP ni el contenido de los mensajes, pero la publicación en internet (dominio, HTTPS, límite de envíos) aún no está hecha.

## Enrutamiento y evidencia

### A quién le llega cada caso

Las reglas están en `data/canal/enrutamiento.yaml` y se aplican con código, sin IA:

- **El delegado de protección de datos recibe todos los casos** y valida cada decisión.
- **Un área recibe el caso** si el mensaje menciona una de sus palabras (por ejemplo, "paseo" o "nómina" para Recursos Humanos, "publicidad" para Marketing; se compara sin mayúsculas ni tildes), o si atiende ese tipo de reporte: Compras recibe los avisos de proveedores e Informática los posibles ciberincidentes. Si ninguna área coincide, el delegado decide a quién derivarlo.
- **Modo reservado:** el caso va solo al delegado. Las áreas que coincidían quedan como sugerencia para que él decida, así nadie del área puede deducir quién reportó.
- **Urgencia según los plazos del motor:** "inmediata" si un plazo vence en menos de 24 horas o ya venció (por ejemplo, la alerta de 3 horas a la ANCI); "alta" si corresponde avisar a la Agencia, si un plazo vence en menos de 3 días o si la IA no pudo leer un incidente; "normal" en el resto.

Cada destino y la urgencia traen su porqué en lenguaje simple. Las palabras y los umbrales son una decisión de diseño del proyecto, no una exigencia de la ley. Los cargos y correos son ficticios y pasan por la guardia de datos sintéticos.

### Registro de evidencia encadenado

Todo lo que le pasa a un caso (ingreso, lectura de la IA, confirmación del titular, enrutamiento) queda anotado en un registro donde cada anotación lleva la huella SHA-256 de la anterior (`hashlib`, de la biblioteca estándar de Python). Si alguien cambia o borra una anotación, las huellas dejan de calzar.

- El caso y sus anotaciones se guardan en la misma transacción: o quedan ambos o ninguno.
- La aplicación no permite acortar ni reescribir la historia de un caso, y la base de datos rechaza cambios y borrados en la evidencia.
- Las anotaciones no llevan datos personales: si un evento trae un RUT, un correo o un teléfono, no se guarda.
- `python -m privacidad.canal evidencia --carpeta casos-demo` revisa la cadena completa y la compara con la historia de cada caso. Termina con la huella final.

Límites conocidos:

- Quien tenga acceso directo al archivo puede quitar las protecciones de la base de datos. Lo que no puede es alterar la evidencia sin que la revisión lo detecte, con una excepción: **si borra las últimas anotaciones (y los casos a los que pertenecen), la cadena que queda sigue siendo coherente.** Para detectarlo hay que guardar la huella final fuera del servidor y revisar con `--cabeza HUELLA`. El sello de tiempo previsto en el roadmap automatiza ese paso.
- La cadena es una sola para todas las organizaciones del prototipo; cada organización con su propia cadena queda para la versión con PostgreSQL.

## Panel del delegado

El panel vive en el mismo programa que el canal, en la dirección `/panel`. Tiene tres pantallas:

- **Bandeja:** los casos ordenados por urgencia, con el plazo más cercano corriendo en vivo. Cada 5 segundos revisa si llegó algo nuevo: un reporte enviado por el código QR aparece solo, con un aviso.
- **Ficha del caso:** lo que llegó (tal como lo leyó la IA, con los datos tapados), los hechos que propuso la IA, lo que decidió el motor con su artículo, a quién se envió y por qué, y la línea de tiempo con la huella de cada anotación.
- **Evidencia:** revisa la cadena completa y muestra las últimas anotaciones de la organización.

Lo que puede hacer el delegado, siempre con la regla "la IA interpreta, el motor decide, la persona valida":

- **Corregir hechos**, nunca plazos: el motor vuelve a decidir desde que se supo del incidente. La propuesta de la IA se conserva para comparar.
- **Resolver dudas:** lo que el motor deja en "Revisar" se decide con un sí o un no y un motivo.
- **Validar:** no se puede mientras quede una duda; si después se corrige algo, la validación se anula y queda anotado.
- **Abrir una identidad reservada:** pide de nuevo la contraseña y un motivo, y queda en la evidencia.

Cada acción deja un evento en la cadena con el usuario y un motivo de una lista cerrada. Las notas libres quedan solo en el caso, nunca en la cadena.

### Probarlo

```bash
python -m privacidad.canal servir --demo --datos casos-demo          # demo: sin contraseña, con casos ficticios
python -m privacidad.canal usuario --datos casos-demo --org municipalidad-piloto --usuario delegado-muni
python -m privacidad.canal servir --datos casos-demo                 # modo real: pide usuario y contraseña
```

La **demo** carga casos ficticios (`data/demo/casos.yaml`) por el mismo canal que un reporte real, con las respuestas de la IA grabadas (cada evento las marca como `respuesta-grabada`). Funciona sin conexión y sin costo, muestra un aviso visible y no abre identidades reservadas. Su botón "Simular una alteración" cambia de verdad una copia de la base y corre la misma verificación; la base real no se toca.

### Seguridad

- Contraseñas guardadas como huella **scrypt** (`hashlib`, biblioteca estándar) con sal propia; comparación en tiempo constante. Un usuario inexistente tarda lo mismo que uno real.
- Tras 5 intentos fallidos en 15 minutos, el usuario se bloquea 15 minutos.
- Sesión en una cookie firmada solo para `/panel`, `HttpOnly`, `SameSite=Strict` y `Secure` con HTTPS. Expira a los 30 minutos sin uso y a las 8 horas en total; la revisión automática de la bandeja no la mantiene viva.
- Cada formulario y cada llamada de htmx lleva un código propio de la sesión (CSRF) y se revisa la cabecera `Origin`.
- Política de contenido estricta: solo scripts, estilos y fuentes del mismo panel, sin código escrito dentro de las páginas (una prueba lo revisa en cada plantilla). htmx corre sin `eval`.
- Un delegado solo alcanza su organización; un caso ajeno responde 404, igual que uno inexistente.

### Diseño y accesibilidad

Tema oscuro y claro (botón de sol), uso completo con teclado, urgencia escrita además de coloreada y el lenguaje de la ley solo en "Ver fuente legal". Las animaciones son solo CSS, muestran cambios que ya ocurrieron (un caso que llega, un plazo que se recalcula, la cadena que se revisa) y se apagan si el equipo pide "reducir movimiento". La ficha se puede imprimir como expediente.

Librerías y recursos incluidos en el repositorio, sin cargar nada de internet: [htmx 2.0.11](https://htmx.org) (licencia 0BSD), fuentes IBM Plex Sans y Mono y Space Grotesk (SIL Open Font License). Sus licencias están junto a los archivos, en `src/privacidad/panel/estaticos/`.

### Límites conocidos

- Un solo rol (delegado). La vista para cada área (solo sus casos, nunca los reservados) queda para después.
- Sin segundo factor de ingreso. El límite de intentos vive en memoria: se reinicia con el servidor.
- La cookie de sesión va firmada, no cifrada: contiene el usuario y la organización (no la contraseña ni datos de casos).
- La IA todavía no indica en qué frase del mensaje se basó cada hecho; está planificado, con verificación por código.
- En la demo, la llave del modo reservado se crea en memoria al arrancar y se pierde al detenerlo.

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
