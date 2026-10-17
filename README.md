# Privacidad 21.719

> Nombre de trabajo; el nombre definitivo se decide antes de la entrega.

Cumplimiento operativo de la Ley 21.719 para empresas medianas y municipios. Proyecto para el Desafío 1 de **ProductIA 2026** (Soho).

Privacidad 21.719 sabe qué datos personales tiene una organización, recibe en minutos los reportes de titulares, trabajadores y proveedores, decide plazos y deberes legales con reglas verificables y deja la evidencia armada.

> **Principio de diseño:** la IA interpreta, el motor de reglas decide y la persona valida. Ningún plazo ni deber legal depende de la respuesta de un modelo de IA.

## Inicio rápido

**Demo publicada (sin instalar nada):** https://privacidad-21719.onrender.com/panel/ — solo datos ficticios, sin contraseña. Cada visitante recibe su propia copia de los casos. El servicio puede tardar cerca de un minuto en despertar.

**En tu computador** (Python 3.12 o superior):

```bash
git clone https://github.com/contactomtingcl/privacidad-21719 && cd privacidad-21719
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m privacidad.canal secreto                       # crea el secreto de los enlaces
export PRIVACIDAD_SECRETO_ENLACES="$(cat secreto-enlaces.key)"
python -m privacidad.canal servir --demo --datos casos-demo
# abre http://127.0.0.1:8080/panel/
```

Funciona sin conexión y sin llave de IA: la demo usa respuestas de la IA grabadas. Con `ANTHROPIC_API_KEY` configurada, los reportes nuevos los lee la IA real. Pruebas: `pytest -q` (o `PYTHONPATH=src python -m unittest discover -s tests -t .`).

**Recorrido sugerido (5 minutos):**

1. **Inventario de datos** → «Analizar» junto a `paseo_fin_de_anio.xlsx`: columnas clasificadas, 61 menores de 14 años calculados por código, registro con los 11 campos del Decreto 662 y la **versión mínima** de la planilla, con lo que decidiría el motor si se filtrara.
2. **Bandeja** → el caso «Planilla del paseo enviada a un proveedor por error»: hechos propuestos por la IA con la frase en que se basó, deberes decididos por el motor con su artículo, la sugerencia «¿Es esta planilla?», los borradores para la Agencia y la ANCI, «Validar decisión» y «Ya lo envié».
3. **Canal y código QR** → abre el canal (o escanea el QR con el teléfono) y envía un reporte: aparece solo en la bandeja.
4. **Registro de lo actuado** → «Simular una alteración»: la cadena SHA-256 detecta el cambio.
5. **Simulador de escenarios** → el mismo incidente con la ley vigente y con la postergación en trámite (Boletín 18.623-07), lado a lado.
6. **Proveedores (red)** → «Abrir el canal del proveedor» y reporta un incidente: llega un caso a cada organización cliente (cambia de organización arriba), cada una con sus plazos.
7. **Canal y código QR** → «Simular caída de la IA» y envía un reporte: no se pierde, queda «Sin lectura de la IA» con los plazos corriendo.

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
| Borradores de reporte a la Agencia y a la ANCI, armados desde el caso sin IA | Primera versión ([cómo funcionan](#borradores-de-reporte)) |
| Cifra de correcciones del delegado, contada desde la evidencia | Primera versión ([cómo se cuenta](#cuánto-corrige-la-persona-a-la-ia)) |
| «Ya lo envié»: el caso sigue abierto hasta enviar todo lo que corresponde | Primera versión |
| Avisos a cada destino (correo con smtplib o bandeja simulada) y «Derivar a…» | Primera versión |
| Operadores de importancia vital (Ley 21.663): 24 h y plan de acción en 7 días | Primera versión |
| Simulador de escenarios: ley vigente frente a la postergación (Boletín 18.623-07) | Primera versión |
| Inventario en el panel: subir planilla, registro del DS 662 y versión mínima con el motor | Primera versión |
| Riesgo de infracción por planilla (leve, grave o gravísima) con su artículo | Primera versión |
| Red de cascada: un proveedor reporta una vez y cada cliente recibe su caso | Primera versión ([cómo funciona](#red-de-cascada)) |
| Avisos por Telegram (opcional) y simulación de caída de la IA en la demo | Primera versión |

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

Cada opción trae un ícono, para quién es y un ejemplo de una línea, sin instrucciones largas. Antes de enviar, la pantalla dice qué pasa después y promete solo lo que el sistema hace: el código de seguimiento, que el mensaje llega de inmediato a la persona encargada de protección de datos y, si se ejerce un derecho, el plazo legal de respuesta (30 días corridos, prorrogables una vez por 30; ambos se leen de `data/reglas/reglas.yaml`, con su fuente verificada en el art. 11).

Cómo funciona:

- **La IA propone, el motor decide, la persona confirma.** Si el mensaje de un titular puede leerse de más de una forma, la persona elige entre seis opciones en lenguaje simple (sin IA en ese paso). El plazo legal corre desde que ingresó el mensaje, nunca desde la confirmación.
- **Si no responde**, pasados 5 días se tramita con una lectura reversible: nunca se borran datos por defecto. Una supresión pasa a oposición más bloqueo temporal de esos datos, y se le avisa que puede pedir la supresión cuando quiera.
- **Bloqueo preventivo desde el ingreso.** El bloqueo temporal tiene 2 días hábiles y la espera dura 5 días: si se aplicara al terminar la espera, nacería vencido. Por eso, cuando la lectura por defecto incluiría un bloqueo, este se aplica apenas llega el mensaje y la persona lo ve en su página de seguimiento. Si aclara que no lo pide, se levanta y el panel le indica al delegado que vuelva a usar esos datos; si no responde, sigue.
- Los 5 días, la lectura reversible y el bloqueo preventivo son decisiones de diseño, no exigencias de la ley: están en `data/reglas/reglas.yaml` (regla `confirmacion_titular`) y **pendientes de revisión legal** (por ejemplo, si el plazo de un bloqueo que la persona no pidió de forma expresa corre desde el ingreso).
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
- Los avisos salen por correo solo si se configura un servidor (`PRIVACIDAD_SMTP_HOST`, `PRIVACIDAD_SMTP_PUERTO`, `PRIVACIDAD_SMTP_USUARIO`, `PRIVACIDAD_SMTP_CONTRASENA`); sin él, y en la demo, quedan en una bandeja de salida simulada. Por Telegram salen solo si se configura `PRIVACIDAD_TELEGRAM_TOKEN` y el destino tiene chat. No se publica una cifra de rendimiento del canal: no hay medición.
- El servidor no registra IP ni el contenido de los mensajes. La demo está publicada con HTTPS (ver «Publicación en internet»); falta un dominio propio y un límite de envíos por persona.
- **Días hábiles:** los feriados nacionales de 2026 y 2027 están verificados (`data/reglas/feriados.yaml`, con sus fuentes). Fuera de ese rango, o si una ley nueva o una elección agrega un feriado, el plazo se muestra como fecha estimada hasta actualizar el calendario. No incluye feriados regionales.

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

- **Una cadena por organización:** cada una numera sus anotaciones desde 1 y cada anotación apunta a la anterior de la misma organización. El delegado verifica solo la suya, no ve cuánta actividad tienen otras y su huella final solo cambia cuando su organización registra algo.
- El caso y sus anotaciones se guardan en la misma transacción: o quedan ambos o ninguno.
- La aplicación no permite acortar ni reescribir la historia de un caso, y la base de datos rechaza cambios y borrados en la evidencia.
- Las anotaciones no llevan datos personales: si un evento trae un RUT, un correo o un teléfono, no se guarda.
- `python -m privacidad.canal evidencia --carpeta casos-demo [--org ORGANIZACION]` revisa la cadena de una organización (o la de cada una) y la compara con la historia de cada caso. Termina con la huella final de cada organización.

Límites conocidos:

- Quien tenga acceso directo al archivo puede quitar las protecciones de la base de datos. Lo que no puede es alterar la evidencia sin que la revisión lo detecte, con una excepción: **si borra las últimas anotaciones (y los casos a los que pertenecen), la cadena que queda sigue siendo coherente.** Para detectarlo hay que guardar la huella final de la organización fuera del servidor y revisar con `--org ORGANIZACION --cabeza HUELLA`. El sello de tiempo previsto en el roadmap automatiza ese paso.
- Las cadenas de todas las organizaciones viven en la misma base del prototipo (separadas por organización). Una base por organización queda para la versión con PostgreSQL.

## Panel del delegado

El panel vive en el mismo programa que el canal, en la dirección `/panel`. Sus pantallas principales (además del Inventario y el Simulador, descritos más abajo):

- **Bandeja:** los casos ordenados por urgencia, con el plazo más cercano corriendo en vivo. Cada 5 segundos revisa si llegó algo nuevo: un reporte enviado por el código QR aparece solo, con un aviso. Arriba, tres cifras con nombres exactos: «Casos con fecha límite legal» (separa los vencidos de los que vencen en menos de 3 horas), «Por validar» (incluye, con su aviso, los que la IA no pudo leer) y «Validados» (no «resueltos»: el sistema no envía nada a las autoridades). Si el plazo más cercano venció, la pantalla dice que el deber sigue y ofrece el paso siguiente (por ejemplo, el borrador para la ANCI). El estado del registro de lo actuado va en el botón «Ver registro», y si no calza aparece una alarma. Un caso validado sigue en la bandeja («Falta enviar») hasta que el delegado registra cada envío.
- **Ficha del caso:** arriba, qué te toca hacer; lo que llegó (tal como lo leyó la IA, con los datos tapados), los hechos que propuso la IA, lo que decidió el motor con su artículo, «Lo que tienes que enviar», a quién le llegó (con el estado de cada aviso y el texto que salió) y el registro de lo actuado.
- **Registro de lo actuado:** revisa la cadena de la organización, muestra las últimas anotaciones de la organización y la cifra de correcciones (ver abajo).

Lo que puede hacer el delegado, siempre con la regla "la IA interpreta, el motor decide, la persona valida":

- **Corregir hechos**, nunca plazos: el motor vuelve a decidir desde que se supo del incidente. La propuesta de la IA se conserva para comparar.
- **Resolver dudas:** lo que el motor deja en «Decide tú» se decide con «Corresponde» o «No corresponde» y un motivo.
- **Validar:** el botón aparece desactivado con lo que falta mientras quede una duda o falten los hechos; si después se corrige algo, la validación se anula y queda anotado. Validar no es enviar: el sistema no envía nada a las autoridades.
- **«Ya lo envié»:** por cada cosa que corresponde (aviso a la Agencia, a cada persona, cada paso de la ANCI, la respuesta a una solicitud), el delegado registra el canal y la hora. La urgencia deja de contarlo.
- **«Derivar a…»:** suma un área al caso con un motivo de lista cerrada. Le llega un aviso sin el mensaje ni datos de personas (en un reservado, tampoco la identidad).
- **Abrir una identidad reservada:** pide de nuevo la contraseña y un motivo, y queda en la evidencia.

Cada acción deja un evento en la cadena con el usuario y un motivo de una lista cerrada. Las notas libres quedan solo en el caso, nunca en la cadena.

### Probarlo

```bash
python -m privacidad.canal servir --demo --datos casos-demo          # demo: sin contraseña, con casos ficticios
python -m privacidad.canal usuario --datos casos-demo --org municipalidad-piloto --usuario delegado-muni
python -m privacidad.canal servir --datos casos-demo                 # modo real: pide usuario y contraseña
```

La **demo** carga casos ficticios (`data/demo/casos.yaml`) por el mismo canal que un reporte real, con las respuestas de la IA grabadas (cada evento las marca como `respuesta-grabada`). Funciona sin conexión y sin costo, muestra un aviso visible y no abre identidades reservadas. Su botón "Simular una alteración" cambia de verdad una copia de la base y corre la misma verificación; la base real no se toca.

Cada participante de la demo recibe **su propia copia limpia** de los casos (una «sala», `src/privacidad/panel/salas.py`): lo que corrige o valida uno no lo ve el siguiente. El enlace y el QR que muestra su panel llevan `?sala=…`, así que un reporte enviado desde el teléfono llega a la misma copia. «Reiniciar la sesión de demo» entrega una copia nueva. Las salas son copias desechables de datos ficticios: se borran enteras tras 2 días sin uso o al pasar de 200.

### Seguridad

- Contraseñas guardadas como huella **scrypt** (`hashlib`, biblioteca estándar) con sal propia; comparación en tiempo constante. Un usuario inexistente tarda lo mismo que uno real.
- Tras 5 intentos fallidos en 15 minutos, el usuario se bloquea 15 minutos.
- Sesión en una cookie firmada solo para `/panel`, `HttpOnly`, `SameSite=Strict` y `Secure` con HTTPS. Expira a los 30 minutos sin uso y a las 8 horas en total; la revisión automática de la bandeja no la mantiene viva.
- Cada formulario y cada llamada de htmx lleva un código propio de la sesión (CSRF) y se revisa la cabecera `Origin`.
- Política de contenido estricta: solo scripts, estilos y fuentes del mismo panel, sin código escrito dentro de las páginas (una prueba lo revisa en cada plantilla). htmx corre sin `eval`.
- Un delegado solo alcanza su organización; un caso ajeno responde 404, igual que uno inexistente.

### Diseño y accesibilidad

Tema oscuro y claro (botón en el menú lateral, lejos de las acciones importantes), uso completo con teclado, urgencia escrita además de coloreada y el lenguaje de la ley solo en "Ver fuente legal". Las animaciones son solo CSS, muestran cambios que ya ocurrieron (un caso que llega, un plazo que se recalcula, la cadena que se revisa) y se apagan si el equipo pide "reducir movimiento". La ficha se puede imprimir como expediente.

Librerías y recursos incluidos en el repositorio, sin cargar nada de internet: [htmx 2.0.11](https://htmx.org) (licencia 0BSD), fuentes IBM Plex Sans y Mono y Space Grotesk (SIL Open Font License), con sus licencias en `src/privacidad/panel/estaticos/`, e íconos de [Lucide](https://lucide.dev) (licencia ISC), con la suya en `src/privacidad/iconos/svg/`. Los íconos acompañan siempre a un texto; nunca lo reemplazan.

### Cuánto corrige la persona a la IA

La pantalla Evidencia y el comando `python -m privacidad.canal correcciones --carpeta casos-demo [--org ORGANIZACION]` cuentan, **solo desde la cadena de evidencia y después de verificarla**:

- de los incidentes que la IA leyó, cuántos terminaron con algún hecho distinto de lo que propuso la IA (cambiar un hecho y devolverlo a lo que dijo la IA no cuenta) y qué hechos fueron;
- cuántos por el motivo «La IA leyó mal el mensaje» (los demás motivos, como información nueva, no son errores de la IA);
- cuántas correcciones hicieron que el motor decidiera distinto sobre avisar a la Agencia, a las personas o a la ANCI;
- cuántos casos validó el delegado sin corregir nada;
- aparte: incidentes que la IA no pudo leer y el delegado completó, dudas del motor resueltas, y lecturas de solicitudes confirmadas o corregidas por la propia persona.

Si la cadena no calza, la cifra no se calcula. Límite: con datos ficticios mide el mecanismo, no el acierto real de la IA. **Todavía no hay una cifra medida para el deck**: saldrá de las pruebas con usuarios, guardada con su fecha.

### Límites conocidos

- Un solo rol (delegado). La vista para cada área (solo sus casos, nunca los reservados) queda para después.
- En la demo, cada sala vive en la carpeta de datos del servidor: si el hosting reinicia sin disco persistente, las salas abiertas se pierden y la siguiente visita parte con una copia nueva.
- Sin segundo factor de ingreso. El límite de intentos vive en memoria: se reinicia con el servidor.
- La cookie de sesión va firmada, no cifrada: contiene el usuario y la organización (no la contraseña ni datos de casos).
- En la demo, la llave del modo reservado se crea en memoria al arrancar y se pierde al detenerlo.

## Inventario de datos

En `/panel/inventario` se sube una planilla (.xlsx o .csv, hasta 2 MB) o se analiza una de ejemplo (`data/sinteticos/comercial-los-robles/`).

- Pasa por la guardia de datos sintéticos, se perfila (edades y menores calculados por código) y **se descarta**: queda solo el registro de la actividad (11 campos del Decreto 662, columnas y alertas) y un resumen sin valores.
- La IA ve los encabezados y la forma de los valores, nunca los valores. Las planillas de ejemplo usan la respuesta de la IA grabada en `resultados/inventario_demo.json` (se reconocen por su huella SHA-256); las alertas se calculan siempre con código.
- **Versión mínima:** quita las columnas que el registro marca como innecesarias y el motor vuelve a decidir qué habría que hacer si la planilla se filtrara. En la base de clientes de ejemplo, sin las columnas de compras deja de corresponder avisar a cada persona; en la del paseo se quita el RUT de los niños, pero los deberes siguen (hay datos de salud y de menores).
- El delegado valida el registro. La ficha de un caso sugiere la planilla que el mensaje parece nombrar, sin cambiar ningún hecho ni deber.

## Red de cascada

Un proveedor que trata datos de varias organizaciones (en la demo, «Remuneraciones del Sur SpA», ficticio) reporta un incidente **una sola vez** desde su enlace firmado, con un formulario cerrado y sin IA: servicios afectados, qué ocurrió, si afectó sistemas y si se interrumpió el servicio.

- Cada organización cliente que usa un servicio afectado recibe **su propio caso**, con los datos que ella le entrega al proveedor (`data/canal/proveedores.yaml`), y su motor decide con su perfil: la empresa privada no tiene reloj de la ANCI; el municipio y la clínica sí.
- El plazo de cada cliente corre desde que le llega el reporte. Ningún cliente ve el caso de otro; el proveedor ve a quién llegó, no sus decisiones.
- En el producto, la relación proveedor-cliente sale del inventario de cada organización y del contrato de encargo; en la demo está escrita a mano.

## Simulador de escenarios

En `/panel/simulador` se compara un incidente (de ejemplo o de un caso real de la bandeja) con la ley vigente y con el proyecto de postergación, según la fecha en que se supo, el tipo de organización y si es operador de importancia vital o empresa de menor tamaño.

- Lo que corresponde hacer no cambia: lo decide el motor. Cambia desde cuándo es exigible (Ley 21.719: 1 de diciembre de 2026 vigente; 1 de diciembre de 2027 en el proyecto) y qué sanción se arriesga (arts. 34 ter k, 34 quáter f, 35 y 44, y la amonestación del primer año del artículo sexto transitorio; Ley 21.663 arts. 38 y 40). Todas las citas se verifican contra el corpus.
- El reporte a la ANCI (Ley 21.663) ya es exigible y ningún escenario lo cambia.
- El proyecto (Boletín 18.623-07, en trámite en el Senado) se cita desde un extracto guardado en `data/normas/proyectos/`, con su enlace oficial, y la pantalla dice que no es ley. Reglas en `data/reglas/escenarios.yaml`.

## Borradores de reporte

Cuando el motor decide que corresponde avisar a la Agencia o a la ANCI (o lo deja en «Revisar»), la ficha del caso ofrece un borrador para cada una. El delegado lo abre, lo revisa, lo completa y lo envía por el canal oficial: **el sistema no envía nada a ninguna autoridad**.

- **Se arman con código, sin IA** (`src/privacidad/reportes/`): costo cero y siempre el mismo texto para el mismo caso. Usan los hechos vigentes (los del delegado si los corrigió) y los vencimientos que calculó el motor.
- **No inventan:** lo que el sistema no sabe queda marcado «[Completar: …]» y se lista al costado.
- **Agencia (art. 14 sexies):** responsable y contacto del delegado, naturaleza de la vulneración, efectos, categorías de datos, número aproximado de personas afectadas, medidas adoptadas y si corresponde avisar a cada persona.
- **ANCI (arts. 9 y 27 de la Ley 21.663):** alerta temprana (3 horas), actualización (72 horas) e informe final (15 días corridos desde la alerta), cada uno con su vencimiento y los elementos que pide la ley.
- **Sin datos personales en el reporte a la ANCI** (art. 27): el borrador nunca recibe el texto del reporte, el resumen de la IA ni la identidad de quien reportó; se arma solo con valores de lista cerrada, cifras y fechas escritas en palabras. Antes de mostrarlo, el código revisa que no queden RUT, correos, teléfonos ni fechas numéricas; si encuentra uno, no lo entrega y dice de qué tipo era (sin mostrarlo). El de la Agencia sigue la misma regla, con una sola excepción: el correo institucional del delegado.
- **Revisión con evidencia:** «Marcar como revisado» anota en la cadena la huella SHA-256 del texto revisado (no el texto), cuántos campos quedaban por completar y el usuario. Si después cambian los hechos, el borrador cambia y la ficha avisa que hay que revisarlo de nuevo.
- Se puede descargar como texto, copiar o imprimir.

Límites conocidos:

- El formato oficial de cada reporte lo fijan la Agencia y el reglamento de la Ley 21.663, que no están en el corpus: el borrador ordena el contenido que piden las leyes y hay que traspasarlo al formulario que corresponda.
- No se modelan los operadores de importancia vital (actualización en 24 horas y plan de acción en 7 días, art. 9).
- La revisión automática detecta RUT, correos, teléfonos y fechas; no reconoce nombres. Por eso el borrador de la ANCI no recibe ningún texto libre, y lo que el delegado agregue al completarlo queda bajo su responsabilidad (el borrador se lo recuerda).
- No hay una cifra medida del tiempo que ahorra; no se publicará hasta medirla con usuarios.

## Publicación en internet

El prototipo se publica en [Render](https://render.com) a partir de este repositorio, con la configuración en `render.yaml` y la imagen en `Dockerfile`:

- Arranca en **modo demo** (casos ficticios, sin contraseña) y se publica solo cuando las pruebas de GitHub pasan.
- Los casos y la cadena de evidencia quedan en un disco persistente de 1 GB; los secretos los genera Render o se pegan en su panel, nunca en el repositorio.
- Corre detrás del proxy de Render, que entrega HTTPS: la opción `--detras-de-proxy` le indica al programa que confíe en sus cabeceras `X-Forwarded-*`.
- Costo: US$7 al mes por el servidor siempre encendido y US$0,25 al mes por el disco (precios de Render, octubre de 2026).

Límites: el servidor está en Estados Unidos (región Virginia). Para un piloto con datos reales, el plan es moverlo a la región de Santiago de Google Cloud. Con disco persistente, cada despliegue deja el sitio sin servicio unos segundos. La imagen corre como administrador del contenedor porque Render no documenta los permisos del disco.

## Evaluación

El sistema se mide con 150 casos ficticios etiquetados (`data/evaluacion/`): 50 reportes de incidentes, 50 mensajes de titulares y 50 columnas de planillas. Se comparan tres niveles: reglas por palabras clave sin IA, la IA decidiendo sola con el texto legal a la vista, y el sistema propuesto (la IA interpreta y el motor de reglas decide).

Resultado de la iteración 3, del 12 de octubre, ya con la frase de respaldo ([detalle](resultados/evaluacion.md)):

| Métrica | Sin IA | IA sola | IA + motor |
| --- | --- | --- | --- |
| Incidentes: deberes de aviso detectados | 62/77 | 69/77 | 76/77 |
| Incidentes: casos con los tres deberes correctos | 58% | 30% | 96% |
| Solicitudes: derecho identificado correctamente | 84% | 96% | 98% |
| Solicitudes: plazo de respuesta correcto | 40/43 | 40/43 | 43/43 |
| Columnas: sensibles detectadas | 4/11 | 11/11 | 11/11 |

Costo de IA del sistema propuesto: US$0,008 por incidente (era US$0,006 antes de pedir la frase de respaldo) y menos de US$0,001 por solicitud. Cuando la IA decide sola, deja como "revisar" 27 de los 37 casos en que el aviso a la Agencia es obligatorio: no se equivoca hacia el "no", pero no decide.

Límites: las etiquetas fueron redactadas con asistencia de IA y están pendientes de revisión del autor y de un abogado; las instrucciones a la IA y la línea base se escribieron conociendo el set, por lo que se agregará un set ciego escrito por otra persona. Las mediciones anteriores, con sus errores, están en [`resultados/historial/`](resultados/historial/). Entre la iteración 2 y la 3 las cifras de solicitudes subieron un poco (de 96% a 98%), pero con una sola corrida no se puede atribuir ese cambio a la frase de respaldo: la IA no responde siempre igual y la columna «IA sola», que no cambió, también se movió.

### Frase de respaldo

La IA copia el fragmento del mensaje en que apoya cada hecho o derecho, y el código comprueba que ese fragmento esté en el texto enmascarado que recibió (`src/privacidad/interpretacion/respaldo.py`; ignora mayúsculas, tildes y puntuación, y exige palabras completas). La frase no decide nada. En el panel, cada hecho muestra su frase; si no está en el mensaje, o si la IA afirmó un dato sin citar ninguna, se le avisa al delegado.

| Iteración 3 | Incidentes | Solicitudes |
| --- | --- | --- |
| Frases encontradas en el mensaje | 179/179 | 52/52 |
| Hechos o derechos afirmados con frase verificada | 156/161 (96,9%) | 52/52 |

Límite: que la frase esté en el mensaje no prueba que la conclusión sea correcta, solo que la IA se apoyó en algo que la persona escribió. El caso queda con las frases; la cadena de evidencia guarda solo cuántas hubo y cuántas se verificaron.

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
