# Inventario con IA: planillas de la demo

Datos sintéticos de Comercial Los Robles. Generado por `python -m privacidad.inventario.demo_ia`.

Costo total de IA: US$0.0695

## paseo_fin_de_anio.xlsx

> Planilla que pidió Recursos Humanos a los trabajadores para organizar el paseo de fin de año con sus hijos e hijas. La comparte con el proveedor Eventos Laja SpA.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Nombre trabajador | Nombre | calculado | Sí |
| RUT trabajador | Identificador nacional (RUT o RUN) | calculado | No: Para inscribir y contactar al trabajador basta con su nombre. El RUT es un identificador que no se necesita para la finalidad descrita. |
| Área | Datos laborales y previsionales | calculado | No: El área de trabajo no es necesaria para organizar un paseo familiar. No aporta a la finalidad y no debería compartirse con el proveedor. |
| Nombre hijo/a | Nombre | calculado | Sí |
| RUT hijo/a | Identificador nacional (RUT o RUN) | calculado | No: No se necesita el RUT de niños y niñas para organizar el paseo. Es un dato de menores que se puede evitar. Solo se justificaría si la descripción indicara, por ejemplo, un seguro, y hoy no lo indica. |
| Fecha de nacimiento hijo/a | Fecha de nacimiento | calculado | Sí |
| Alergias o condiciones médicas | Salud | calculado | Sí |
| Celular apoderado | Teléfono | calculado | Sí |
| Correo apoderado | Correo electrónico | calculado | Sí |
| Talla polera | no_personal | ia | — |

- **fines** (ia): ['Organizar el paseo de fin de año para los trabajadores y sus hijos e hijas (inscripción, logística, alimentación, contacto con el apoderado y entrega de polera)']
- **base_licitud** (ia): consentimiento_expreso
- **categorias_titulares** (ia): ['Trabajadores de la organización', 'Hijos e hijas de los trabajadores (todos menores de 18 años; 61 menores de 14 años)', 'Apoderados (personas de contacto)']
- **destinatarios** (ia): ['Eventos Laja SpA (proveedor que recibe la planilla)', 'Recursos Humanos de la organización (quien organiza la actividad)']
- **plazo_supresion** (ia): no informado

**Alertas**

- [alta] Hay datos de 61 niños o niñas menores de 14 años: se requiere consentimiento de sus padres o representantes legales, y ante una filtración hay que avisar a cada titular a través de ellos.
- [alta] Hay 13 adolescentes menores de 16 años con datos sensibles: requieren consentimiento de sus padres o representantes legales.
- [media] La columna «RUT trabajador» parece innecesaria: Para inscribir y contactar al trabajador basta con su nombre. El RUT es un identificador que no se necesita para la finalidad descrita.
- [media] La columna «Área» parece innecesaria: El área de trabajo no es necesaria para organizar un paseo familiar. No aporta a la finalidad y no debería compartirse con el proveedor.
- [media] La columna «RUT hijo/a» parece innecesaria: No se necesita el RUT de niños y niñas para organizar el paseo. Es un dato de menores que se puede evitar. Solo se justificaría si la descripción indicara, por ejemplo, un seguro, y hoy no lo indica.

Costo IA: US$0.0261

## nomina_trabajadores.xlsx

> Nómina para calcular y pagar remuneraciones y cotizaciones. La procesa el proveedor Remuneraciones del Sur SpA.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Nombre completo | Nombre | calculado | Sí |
| RUT | Identificador nacional (RUT o RUN) | calculado | Sí |
| Cargo | Datos laborales y previsionales | calculado | Sí |
| Área | Datos laborales y previsionales | calculado | Sí |
| Fecha de ingreso | Datos laborales y previsionales | calculado | Sí |
| Sueldo base | Datos económicos o financieros | calculado | Sí |
| Banco | Datos económicos o financieros | calculado | Sí |
| Número de cuenta | Datos económicos o financieros | calculado | Sí |
| AFP | Datos laborales y previsionales | calculado | Sí |
| Previsión de salud | Previsión de salud (Isapre o Fonasa) | calculado | Sí |
| Afiliado sindicato | Afiliación sindical o gremial | calculado | No: Es un dato sensible (afiliación sindical) y no se necesita para calcular ni pagar remuneraciones y cotizaciones, según la descripción. Si hubiera descuento de cuota sindical, la organización debería informarlo y justificarlo. |
| Días de licencia médica último año | Salud | calculado | No: Es un dato sensible (salud). Para la nómina solo serían pertinentes los días de licencia del período que se liquida, no el historial de todo el último año. |

- **fines** (ia): ['Calcular y pagar las remuneraciones de los trabajadores', 'Calcular y pagar las cotizaciones asociadas a las remuneraciones']
- **base_licitud** (ia): contrato
- **categorias_titulares** (ia): ['Trabajadores de la organización']
- **destinatarios** (ia): ['Remuneraciones del Sur SpA (proveedor que procesa la nómina)']
- **plazo_supresion** (ia): no informado

**Alertas**

- [alta] La planilla tiene datos sensibles (afiliación sindical o gremial, salud). Requieren consentimiento expreso del titular, salvo excepción legal.
- [media] La columna «Afiliado sindicato» parece innecesaria: Es un dato sensible (afiliación sindical) y no se necesita para calcular ni pagar remuneraciones y cotizaciones, según la descripción. Si hubiera descuento de cuota sindical, la organización debería informarlo y justificarlo.
- [media] La columna «Días de licencia médica último año» parece innecesaria: Es un dato sensible (salud). Para la nómina solo serían pertinentes los días de licencia del período que se liquida, no el historial de todo el último año.
- [informativa] Contiene datos económicos o financieros: ante una filtración hay que avisar también a cada titular.

Costo IA: US$0.0218

## clientes_marketing.csv

> Base de clientes para enviar ofertas y publicidad por correo y celular. Las campañas las envía el proveedor Publicidad Austral SpA.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Nombre | Nombre | calculado | Sí |
| Correo | Correo electrónico | calculado | Sí |
| Celular | Teléfono | calculado | Sí |
| Comuna | Dirección o comuna | calculado | No: La publicidad se envía por correo y celular, así que la ubicación no es necesaria. Solo sería pertinente si hay ofertas segmentadas por zona, y eso no se informó. |
| Fecha última compra | Preferencias y comportamiento de compra | calculado | No: No es necesaria para enviar publicidad en general. Solo sería pertinente si la organización segmenta por actividad reciente, y eso no se informó. |
| Monto compras 2026 | Datos económicos o financieros | calculado | No: Para enviar ofertas y publicidad no hace falta conocer cuánto compró cada cliente. Solo sería pertinente si la organización describe una segmentación por nivel de compra, y eso no se informó. |
| Acepta publicidad | Preferencias y comportamiento de compra | calculado | Sí |

- **fines** (ia): ['Enviar ofertas y publicidad a clientes por correo electrónico y celular']
- **base_licitud** (ia): consentimiento
- **categorias_titulares** (ia): ['Clientes']
- **destinatarios** (ia): ['Publicidad Austral SpA (proveedor que envía las campañas)']
- **plazo_supresion** (ia): no informado

**Alertas**

- [media] La columna «Comuna» parece innecesaria: La publicidad se envía por correo y celular, así que la ubicación no es necesaria. Solo sería pertinente si hay ofertas segmentadas por zona, y eso no se informó.
- [media] La columna «Fecha última compra» parece innecesaria: No es necesaria para enviar publicidad en general. Solo sería pertinente si la organización segmenta por actividad reciente, y eso no se informó.
- [media] La columna «Monto compras 2026» parece innecesaria: Para enviar ofertas y publicidad no hace falta conocer cuánto compró cada cliente. Solo sería pertinente si la organización describe una segmentación por nivel de compra, y eso no se informó.
- [informativa] Contiene datos económicos o financieros: ante una filtración hay que avisar también a cada titular.

Costo IA: US$0.0112

## proveedores.csv

> Registro de proveedores y de sus personas de contacto comerciales.

| Columna | Categoría | Origen | ¿Necesaria? |
| --- | --- | --- | --- |
| Razón social | persona_juridica | ia | — |
| RUT empresa | persona_juridica | ia | — |
| Servicio | no_personal | ia | — |
| Datos que recibe | no_personal | ia | — |
| Contacto | Nombre | ia | Sí |
| Correo contacto | Correo electrónico | calculado | Sí |
| Celular contacto | Teléfono | calculado | Sí |

- **fines** (ia): ['Mantener un registro de proveedores y de sus personas de contacto comerciales para gestionar la relación comercial']
- **base_licitud** (ia): interes_legitimo
- **categorias_titulares** (ia): ['Personas de contacto comerciales de los proveedores']
- **destinatarios** (ia): ['no informado']
- **plazo_supresion** (ia): no informado

**Alertas**

- Ninguna

Costo IA: US$0.0105
