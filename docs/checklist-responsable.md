# Checklist de ejecución responsable

Entregable 07 de ProductIA: privacidad, seguridad, sesgo y accesibilidad, más una evaluación de impacto breve. Estado al 17 de octubre de 2026.

Cada punto dice su estado y dónde se comprueba. **Hecho** = está en el código y tiene prueba o se puede ver en la demo. **Parcial** = existe con un límite declarado. **Pendiente** = aún no está.

## Privacidad

| Punto | Estado | Evidencia |
| --- | --- | --- |
| Solo datos sintéticos; la guardia rechaza lo que podría ser real | Hecho | `src/privacidad/guardia.py`, `tests/test_guardia.py` |
| La IA recibe texto enmascarado (RUT, correos, teléfonos y fechas como marcadores) | Hecho | `src/privacidad/deteccion.py`, `interpretacion/comun.py` |
| La IA nunca ve los valores de una planilla (solo encabezados y forma) | Hecho | `inventario/actividad.py` (`muestras_seguras`) |
| La planilla subida no se guarda: queda solo el registro y un resumen sin valores | Hecho | `inventario/servicio.py`, `tests/test_inventario_panel.py` |
| Minimización: versión mínima de cada planilla con lo que decidiría el motor si se filtrara | Hecho | `/panel/inventario/{id}` |
| La cadena de evidencia no guarda datos personales | Hecho | `canal/evidencia.py`, `tests/test_canal_evidencia.py` |
| El reporte a la ANCI no lleva datos personales (art. 27, Ley 21.663) y se bloquea si aparece uno | Hecho | `reportes/borradores.py`, `tests/test_reportes.py` |
| Los avisos a las áreas no llevan el mensaje ni datos de personas | Hecho | `canal/avisos.py`, `tests/test_avisos.py` |
| Modo reservado: nombre y contacto cifrados (Fernet); el caso va solo al delegado | Parcial | Llave simétrica: quien administra el servidor puede abrirla (README) |
| Nunca se borran datos de una persona sin su confirmación expresa | Hecho | `canal/confirmacion.py`, `tests/test_canal_confirmacion.py` |
| Bloqueo preventivo mientras la persona aclara qué pidió | Hecho, pendiente de revisión legal | Regla `confirmacion_titular` en `data/reglas/reglas.yaml` |
| Política de conservación de casos en modo real | Pendiente | En la demo las copias se borran tras 2 días sin uso |

## Seguridad

| Punto | Estado | Evidencia |
| --- | --- | --- |
| Contraseñas con scrypt, comparación en tiempo constante, límite de intentos | Hecho | `panel/usuarios.py`, `tests/test_panel_usuarios.py` |
| Sesión firmada, `HttpOnly`, `SameSite=Strict`, `Secure`, expira por inactividad | Hecho | `panel/web.py` |
| CSRF en cada formulario y revisión de `Origin` | Hecho | `tests/test_panel_web.py` |
| Política de contenido estricta, sin código dentro de las páginas; htmx sin `eval` | Hecho | Una prueba revisa cada plantilla |
| Un delegado solo ve su organización (un caso ajeno responde 404) | Hecho | `canal/delegado.py` |
| Enlaces del canal y de proveedores firmados (sales distintas) | Hecho | `canal/enlaces.py`, `canal/cascada.py` |
| Evidencia encadenada (SHA-256) por organización, con disparadores contra cambios y borrados | Parcial | Borrar el final de la cadena solo se detecta con la huella final guardada aparte |
| Errores inesperados sin detalles técnicos en pantalla | Hecho | `tests/test_imagen_publicada.py` |
| La llave de la API nunca en el repositorio | Hecho | Secreto de GitHub y de Render |
| Segundo factor de ingreso | Pendiente | Plan a 90 días |
| Sello de tiempo externo (RFC 3161) | Pendiente | Plan a 90 días |
| Servidor en Chile para datos reales | Pendiente | Hoy en Render, EE. UU.; plan: región Santiago de Google Cloud |

## Sesgo y equidad

Riesgo principal: que la IA lea peor los mensajes de quienes escriben distinto (sin tildes, con errores, con modismos, de forma muy breve o muy emotiva), y que eso cambie lo que se tramita.

| Punto | Estado | Evidencia |
| --- | --- | --- |
| La IA no decide deberes ni plazos: un error de lectura no cambia la ley aplicada, cambia los hechos, que el delegado ve y corrige | Hecho | Motor de reglas; panel |
| Si el mensaje admite lecturas distintas, se le pregunta a la persona con un menú fijo y lenguaje simple, sin IA | Hecho | `canal/confirmacion.py` |
| Sin respuesta, lectura reversible y protectora (nunca borrar) | Hecho | Regla `confirmacion_titular` |
| Cada hecho muestra la frase del mensaje en que se basa; si falta, se avisa | Hecho | `interpretacion/respaldo.py` |
| Ante la duda en una columna, la IA elige la categoría sensible | Hecho | Prompt `SISTEMA_COLUMNAS` |
| Medición por grupo de escritura (formal, informal, con errores) | Pendiente | El set de 150 casos no está segmentado así |
| Set ciego escrito por otra persona | Pendiente | Declarado en el README |
| Revisión de las etiquetas por el autor y un abogado | Pendiente | Declarado en el README |

## Accesibilidad

| Punto | Estado | Evidencia |
| --- | --- | --- |
| Idioma de la página declarado (`lang="es"`) y enlace «Saltar al contenido» | Hecho | Plantillas `base.html` |
| Uso completo con teclado y foco visible | Hecho | `panel.css` (`:focus-visible`) |
| La urgencia se escribe además de colorearse; los íconos acompañan al texto, nunca lo reemplazan | Hecho | Panel |
| Animaciones solo CSS, que se apagan con «reducir movimiento» | Hecho | `panel.css` (`prefers-reduced-motion`) |
| Mensajes de estado y error anunciados a lectores de pantalla (`role="status"` / `role="alert"`) | Hecho | Plantillas |
| Tema claro y oscuro | Hecho | Menú lateral |
| Lenguaje simple: el texto legal solo en «Ver fuente legal»; el canal explica para quién es cada opción con un ejemplo | Hecho | Auditoría de comprensión del 17 de octubre |
| Uso en celular (canal por QR y menú compacto del panel) | Hecho | Demo |
| Contraste de colores medido según WCAG AA (4,5:1; 3:1 en texto grande) | Hecho | `scripts/revisar_pantallas.py`, 17 oct: todas las pantallas de la demo en computador y celular, temas claro y oscuro; ningún texto bajo el mínimo (salvo un instante durante una animación) |
| Sin desplazamiento lateral en el celular (390 px) | Hecho | Misma revisión; la bandeja pasa a tarjetas en el celular |
| Prueba con lector de pantalla | Pendiente | — |

## Evaluación de impacto (breve)

El producto trata datos personales de quienes reportan (nombre, contacto y lo que escriben) y describe incidentes que pueden afectar a otras personas.

| Riesgo | Probabilidad | Impacto | Medida | Riesgo que queda |
| --- | --- | --- | --- | --- |
| La IA lee mal un incidente y el motor decide que no hay que avisar | Media | Alto | Frase de respaldo visible; el delegado corrige y valida; medición IA + motor (ver `resultados/evaluacion.md`) | Bajo con validación humana; la cifra real saldrá de las pruebas con usuarios |
| Se borran datos que la persona no pidió borrar | Baja | Alto | Nunca se suprime sin confirmación expresa; lectura reversible | Muy bajo |
| Se expone la identidad de quien reporta en modo reservado | Baja | Alto | Cifrado; solo al delegado; abrirla pide contraseña y motivo, y queda en la evidencia | Medio mientras la llave sea simétrica |
| Datos personales llegan al proveedor de IA | Media | Medio | Enmascarado de RUT, correos, teléfonos y fechas; las planillas nunca envían valores | Los nombres escritos dentro del relato no se detectan; revisar condiciones del proveedor antes de un piloto con datos reales |
| Se altera la evidencia para ocultar un incumplimiento | Baja | Alto | Cadena SHA-256 por organización y disparadores | Borrar el final solo se detecta con la huella guardada aparte (sello de tiempo en el plan) |
| Un plazo mal calculado por un feriado nuevo | Baja | Medio | Feriados 2026–2027 verificados; fuera de ese rango, «fecha estimada» | Leyes o elecciones nuevas exigen actualizar el calendario |
| El delegado confía de más en el sistema | Media | Medio | Botón Validar desactivado mientras haya dudas; validar no es enviar; «Ya lo envié» por cada deber | Depende de la capacitación |

Conclusión: el diseño mantiene a una persona en cada decisión con efecto legal y deja todo registrado. Antes de un piloto con datos reales faltan: revisión legal de las reglas propias, servidor en Chile, política de conservación, llave asimétrica para el modo reservado y medición con usuarios.
