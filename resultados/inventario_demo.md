# Inventario con IA: planillas de la demo

Datos sintéticos de Comercial Los Robles. Generado por `python -m ora_privacidad.inventario.demo_ia`.

Costo total de IA: US$0.0006

## paseo_fin_de_anio.xlsx

> Planilla que pidió Recursos Humanos a los trabajadores para organizar el paseo de fin de año con sus hijos e hijas. La comparte con el proveedor Eventos Laja SpA.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Nombre trabajador | Nombre | calculado | — |
| RUT trabajador | Identificador nacional (RUT o RUN) | calculado | — |
| Área | Datos laborales y previsionales | calculado | — |
| Nombre hijo/a | Nombre | calculado | — |
| RUT hijo/a | Identificador nacional (RUT o RUN) | calculado | — |
| Fecha de nacimiento hijo/a | Fecha de nacimiento | calculado | — |
| Alergias o condiciones médicas | Salud | calculado | — |
| Celular apoderado | Teléfono | calculado | — |
| Correo apoderado | Correo electrónico | calculado | — |
| Talla polera | no_personal | ia | — |

- **fines** (pendiente): None
- **base_licitud** (pendiente): None
- **categorias_titulares** (pendiente): None
- **destinatarios** (pendiente): None
- **plazo_supresion** (pendiente): None

**Alertas**

- [media] IA no disponible para proponer la actividad (BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'tool_choice: type "tool" and "any" are not supported for this model.'}, 'request_id': 'req_011CfuA3gxzJsYkLnJnV4yXG'})
- [alta] La planilla tiene datos sensibles (salud). Requieren consentimiento expreso del titular, salvo excepción legal.
- [alta] Hay datos de 61 niños o niñas menores de 14 años: se requiere consentimiento de sus padres o representantes legales, y ante una filtración hay que avisar a cada titular a través de ellos.
- [alta] Hay 13 adolescentes menores de 16 años con datos sensibles: requieren consentimiento de sus padres o representantes legales.
- [media] El campo «ambito_territorial» quedó pendiente de completar.
- [media] El campo «categorias_titulares» quedó pendiente de completar.
- [media] El campo «fines» quedó pendiente de completar.
- [media] El campo «fuente» quedó pendiente de completar.
- [media] El campo «base_licitud» quedó pendiente de completar.
- [media] El campo «destinatarios» quedó pendiente de completar.
- [media] El campo «transferencias_internacionales» quedó pendiente de completar.
- [media] El campo «plazo_supresion» quedó pendiente de completar.
- [media] El campo «decisiones_automatizadas» quedó pendiente de completar.

Costo IA: US$0.0002

## nomina_trabajadores.xlsx

> Nómina para calcular y pagar remuneraciones y cotizaciones. La procesa el proveedor Remuneraciones del Sur SpA.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Nombre completo | Nombre | calculado | — |
| RUT | Identificador nacional (RUT o RUN) | calculado | — |
| Cargo | Datos laborales y previsionales | calculado | — |
| Área | Datos laborales y previsionales | calculado | — |
| Fecha de ingreso | Datos laborales y previsionales | calculado | — |
| Sueldo base | Datos económicos o financieros | calculado | — |
| Banco | Datos económicos o financieros | calculado | — |
| Número de cuenta | Datos económicos o financieros | calculado | — |
| AFP | Datos laborales y previsionales | calculado | — |
| Previsión de salud | Previsión de salud (Isapre o Fonasa) | calculado | — |
| Afiliado sindicato | Afiliación sindical o gremial | calculado | — |
| Días de licencia médica último año | Salud | calculado | — |

- **fines** (pendiente): None
- **base_licitud** (pendiente): None
- **categorias_titulares** (pendiente): None
- **destinatarios** (pendiente): None
- **plazo_supresion** (pendiente): None

**Alertas**

- [media] IA no disponible para proponer la actividad (BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'tool_choice: type "tool" and "any" are not supported for this model.'}, 'request_id': 'req_011CfuA3hx2hQCmdTWF9WQce'})
- [alta] La planilla tiene datos sensibles (afiliación sindical o gremial, salud). Requieren consentimiento expreso del titular, salvo excepción legal.
- [informativa] Contiene datos económicos o financieros: ante una filtración hay que avisar también a cada titular.
- [media] El campo «ambito_territorial» quedó pendiente de completar.
- [media] El campo «categorias_titulares» quedó pendiente de completar.
- [media] El campo «fines» quedó pendiente de completar.
- [media] El campo «fuente» quedó pendiente de completar.
- [media] El campo «base_licitud» quedó pendiente de completar.
- [media] El campo «destinatarios» quedó pendiente de completar.
- [media] El campo «transferencias_internacionales» quedó pendiente de completar.
- [media] El campo «plazo_supresion» quedó pendiente de completar.
- [media] El campo «decisiones_automatizadas» quedó pendiente de completar.

Costo IA: US$0.0000

## clientes_marketing.csv

> Base de clientes para enviar ofertas y publicidad por correo y celular. Las campañas las envía el proveedor Publicidad Austral SpA.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Nombre | Nombre | calculado | — |
| Correo | Correo electrónico | calculado | — |
| Celular | Teléfono | calculado | — |
| Comuna | Dirección o comuna | calculado | — |
| Fecha última compra | Preferencias y comportamiento de compra | calculado | — |
| Monto compras 2026 | Datos económicos o financieros | calculado | — |
| Acepta publicidad | Preferencias y comportamiento de compra | calculado | — |

- **fines** (pendiente): None
- **base_licitud** (pendiente): None
- **categorias_titulares** (pendiente): None
- **destinatarios** (pendiente): None
- **plazo_supresion** (pendiente): None

**Alertas**

- [media] IA no disponible para proponer la actividad (BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'tool_choice: type "tool" and "any" are not supported for this model.'}, 'request_id': 'req_011CfuA3imt91uFieUgePW8Q'})
- [informativa] Contiene datos económicos o financieros: ante una filtración hay que avisar también a cada titular.
- [media] El campo «ambito_territorial» quedó pendiente de completar.
- [media] El campo «categorias_titulares» quedó pendiente de completar.
- [media] El campo «fines» quedó pendiente de completar.
- [media] El campo «fuente» quedó pendiente de completar.
- [media] El campo «base_licitud» quedó pendiente de completar.
- [media] El campo «destinatarios» quedó pendiente de completar.
- [media] El campo «transferencias_internacionales» quedó pendiente de completar.
- [media] El campo «plazo_supresion» quedó pendiente de completar.
- [media] El campo «decisiones_automatizadas» quedó pendiente de completar.

Costo IA: US$0.0000

## proveedores.csv

> Registro de proveedores y de sus personas de contacto comerciales.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Razón social | persona_juridica | ia | — |
| RUT empresa | persona_juridica | ia | — |
| Servicio | no_personal | ia | — |
| Datos que recibe | no_personal | ia | — |
| Contacto | Nombre | ia | — |
| Correo contacto | Correo electrónico | calculado | — |
| Celular contacto | Teléfono | calculado | — |

- **fines** (pendiente): None
- **base_licitud** (pendiente): None
- **categorias_titulares** (pendiente): None
- **destinatarios** (pendiente): None
- **plazo_supresion** (pendiente): None

**Alertas**

- [media] IA no disponible para proponer la actividad (BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'tool_choice: type "tool" and "any" are not supported for this model.'}, 'request_id': 'req_011CfuA3su4pho8YRMjgJdLd'})
- [media] El campo «ambito_territorial» quedó pendiente de completar.
- [media] El campo «categorias_titulares» quedó pendiente de completar.
- [media] El campo «fines» quedó pendiente de completar.
- [media] El campo «fuente» quedó pendiente de completar.
- [media] El campo «base_licitud» quedó pendiente de completar.
- [media] El campo «destinatarios» quedó pendiente de completar.
- [media] El campo «transferencias_internacionales» quedó pendiente de completar.
- [media] El campo «plazo_supresion» quedó pendiente de completar.
- [media] El campo «decisiones_automatizadas» quedó pendiente de completar.

Costo IA: US$0.0004
