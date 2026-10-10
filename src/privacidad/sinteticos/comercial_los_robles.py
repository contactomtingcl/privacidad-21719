"""Datos ficticios de "Comercial Los Robles", la empresa mediana de la demo.

Todo es sintético y determinista (misma semilla, mismos datos): nombres de listas
cerradas, RUT del tramo reservado, correos en dominios .example y móviles
+56 9 0000 XXXX. Cada archivo pasa por la guardia antes de guardarse.

Planillas que genera:

- paseo_fin_de_anio.xlsx: la planilla del caso de la demo. Recursos Humanos pidió
  nombre, RUT, fecha de nacimiento y alergias de los hijos de los trabajadores.
- nomina_trabajadores.xlsx: remuneraciones, previsión y afiliación sindical.
- clientes_marketing.csv: base de clientes para publicidad.
- proveedores.csv: proveedores y qué datos de la empresa reciben.
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

from .. import guardia

NOMBRES_F = [
    "Ana",
    "Camila",
    "Valentina",
    "Javiera",
    "Catalina",
    "Francisca",
    "Constanza",
    "Daniela",
    "Fernanda",
    "Isidora",
    "Antonia",
    "Florencia",
    "Josefa",
    "Martina",
    "Sofía",
    "Agustina",
    "Emilia",
    "Trinidad",
    "Paula",
    "Carolina",
    "Macarena",
    "Bárbara",
    "Rocío",
    "Ignacia",
]
NOMBRES_M = [
    "Pedro",
    "Juan",
    "Diego",
    "Matías",
    "Benjamín",
    "Vicente",
    "Tomás",
    "Joaquín",
    "Felipe",
    "Martín",
    "Agustín",
    "Lucas",
    "Maximiliano",
    "Cristóbal",
    "Sebastián",
    "Nicolás",
    "Gaspar",
    "Bastián",
    "Ignacio",
    "Rodrigo",
    "Andrés",
    "Pablo",
    "Gonzalo",
    "Esteban",
]
APELLIDOS = [
    "González",
    "Muñoz",
    "Rojas",
    "Díaz",
    "Pérez",
    "Soto",
    "Contreras",
    "Silva",
    "Martínez",
    "Sepúlveda",
    "Morales",
    "Rodríguez",
    "López",
    "Fuentes",
    "Hernández",
    "Torres",
    "Araya",
    "Flores",
    "Espinoza",
    "Valenzuela",
    "Castillo",
    "Tapia",
    "Reyes",
    "Gutiérrez",
    "Castro",
    "Pizarro",
    "Álvarez",
    "Vásquez",
    "Sánchez",
    "Fernández",
    "Ramírez",
    "Carrasco",
]
AREAS = ["Ventas", "Bodega", "Administración", "Recursos Humanos", "Logística", "Atención"]
CARGOS = {
    "Ventas": ["Vendedor", "Jefe de ventas", "Ejecutivo comercial"],
    "Bodega": ["Bodeguero", "Jefe de bodega", "Operario"],
    "Administración": ["Contador", "Asistente administrativo", "Gerente general"],
    "Recursos Humanos": ["Analista de personas", "Jefe de recursos humanos"],
    "Logística": ["Conductor", "Coordinador logístico"],
    "Atención": ["Cajero", "Ejecutivo de atención"],
}
COMUNAS = ["Los Ángeles", "Cabrero", "Nacimiento", "Mulchén", "Laja", "Yumbel", "Santa Bárbara"]
BANCOS = ["BancoEstado", "Banco de Chile", "Santander", "BCI", "Scotiabank"]
AFPS = ["Capital", "Cuprum", "Habitat", "Modelo", "PlanVital", "Provida", "Uno"]
PREVISION = [
    "Fonasa",
    "Fonasa",
    "Fonasa",
    "Isapre Banmédica",
    "Isapre Colmena",
    "Isapre Cruz Blanca",
]
ALERGIAS = ["Maní", "Lactosa", "Celiaquía", "Asma", "Huevo", "Picadura de abeja", "Mariscos"]
TALLAS = ["4", "6", "8", "10", "12", "14", "S", "M", "L"]
DOMINIO = "losrobles.example"

REFERENCIA = date(2026, 10, 10)
HIJOS_TOTAL = 84
HIJOS_MENORES_DE_14 = 61


class _Generador:
    def __init__(self, semilla: int) -> None:
        self.rng = random.Random(semilla)
        self._ruts = 0
        self._moviles = 0

    def rut(self) -> str:
        self._ruts += 1
        return guardia.rut_sintetico(self._ruts * 7919)

    def movil(self) -> str:
        self._moviles += 1
        return guardia.movil_sintetico(self._moviles)

    def persona(self) -> tuple[str, str]:
        nombre = self.rng.choice(self.rng.choice([NOMBRES_F, NOMBRES_M]))
        return nombre, f"{self.rng.choice(APELLIDOS)} {self.rng.choice(APELLIDOS)}"

    def fecha_con_edad(self, edad: int) -> date:
        """Fecha de nacimiento tal que la persona tenga `edad` años en REFERENCIA."""
        ultimo_cumple = date(REFERENCIA.year - edad, REFERENCIA.month, REFERENCIA.day)
        return ultimo_cumple - timedelta(days=self.rng.randint(1, 364))

    def correo(self, nombre: str, apellidos: str) -> str:
        base = f"{nombre}.{apellidos.split()[0]}".lower()
        base = base.translate(str.maketrans("áéíóúñ", "aeioun"))
        return f"{base}{self.rng.randint(1, 99)}@{DOMINIO}"


def _trabajadores(g: _Generador, n: int = 120) -> list[dict]:
    filas = []
    for _ in range(n):
        nombre, apellidos = g.persona()
        area = g.rng.choice(AREAS)
        filas.append(
            {
                "nombre": nombre,
                "apellidos": apellidos,
                "rut": g.rut(),
                "area": area,
                "cargo": g.rng.choice(CARGOS[area]),
                "movil": g.movil(),
                "correo": g.correo(nombre, apellidos),
            }
        )
    return filas


def _edades_hijos(g: _Generador) -> list[int]:
    edades = [g.rng.randint(1, 13) for _ in range(HIJOS_MENORES_DE_14)]
    edades += [g.rng.randint(14, 17) for _ in range(HIJOS_TOTAL - HIJOS_MENORES_DE_14)]
    g.rng.shuffle(edades)
    return edades


def _guardar_xlsx(ruta: Path, encabezados: list[str], filas: list[list]) -> None:
    guardia.exigir_sintetico(filas)
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append(encabezados)
    for fila in filas:
        ws.append(fila)
    fijo = datetime(2026, 10, 10)
    wb.properties.created = wb.properties.modified = fijo  # archivo reproducible
    wb.save(ruta)


def _guardar_csv(ruta: Path, encabezados: list[str], filas: list[list]) -> None:
    guardia.exigir_sintetico(filas)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(encabezados)
        w.writerows(filas)


def generar(directorio: Path, semilla: int = 2026) -> dict[str, Path]:
    """Genera las cuatro planillas en `directorio` y devuelve sus rutas."""
    directorio.mkdir(parents=True, exist_ok=True)
    g = _Generador(semilla)
    trabajadores = _trabajadores(g)
    rutas: dict[str, Path] = {}

    # 1. Planilla del paseo: una fila por hijo o hija.
    con_hijos = g.rng.sample(trabajadores, 55)
    padres = [con_hijos[i % len(con_hijos)] for i in range(HIJOS_TOTAL)]
    filas = []
    for padre, edad in zip(padres, _edades_hijos(g), strict=True):
        nombre_hijo = g.rng.choice(g.rng.choice([NOMBRES_F, NOMBRES_M]))
        alergia = g.rng.choice(ALERGIAS) if g.rng.random() < 0.18 else "Ninguna"
        filas.append(
            [
                f"{padre['nombre']} {padre['apellidos']}",
                padre["rut"],
                padre["area"],
                f"{nombre_hijo} {padre['apellidos']}",
                g.rut(),
                g.fecha_con_edad(edad).strftime("%d/%m/%Y"),
                alergia,
                padre["movil"],
                padre["correo"],
                g.rng.choice(TALLAS),
            ]
        )
    rutas["paseo"] = directorio / "paseo_fin_de_anio.xlsx"
    _guardar_xlsx(
        rutas["paseo"],
        [
            "Nombre trabajador",
            "RUT trabajador",
            "Área",
            "Nombre hijo/a",
            "RUT hijo/a",
            "Fecha de nacimiento hijo/a",
            "Alergias o condiciones médicas",
            "Celular apoderado",
            "Correo apoderado",
            "Talla polera",
        ],
        filas,
    )

    # 2. Nómina de remuneraciones.
    filas = []
    for t in trabajadores:
        ingreso = REFERENCIA - timedelta(days=g.rng.randint(60, 4000))
        filas.append(
            [
                f"{t['nombre']} {t['apellidos']}",
                t["rut"],
                t["cargo"],
                t["area"],
                ingreso.strftime("%d/%m/%Y"),
                g.rng.randrange(560_000, 2_800_000, 5_000),
                g.rng.choice(BANCOS),
                f"{g.rng.randint(10_000_000, 99_999_999)}",
                g.rng.choice(AFPS),
                g.rng.choice(PREVISION),
                "Sí" if g.rng.random() < 0.35 else "No",
                g.rng.choice([0, 0, 0, 0, 2, 5, 7, 14, 30]),
            ]
        )
    rutas["nomina"] = directorio / "nomina_trabajadores.xlsx"
    _guardar_xlsx(
        rutas["nomina"],
        [
            "Nombre completo",
            "RUT",
            "Cargo",
            "Área",
            "Fecha de ingreso",
            "Sueldo base",
            "Banco",
            "Número de cuenta",
            "AFP",
            "Previsión de salud",
            "Afiliado sindicato",
            "Días de licencia médica último año",
        ],
        filas,
    )

    # 3. Clientes para publicidad.
    filas = []
    for _ in range(300):
        nombre, apellidos = g.persona()
        ultima = REFERENCIA - timedelta(days=g.rng.randint(1, 700))
        filas.append(
            [
                f"{nombre} {apellidos}",
                g.correo(nombre, apellidos),
                g.movil(),
                g.rng.choice(COMUNAS),
                ultima.strftime("%Y-%m-%d"),
                g.rng.randrange(15_000, 900_000, 1_000),
                "Sí" if g.rng.random() < 0.6 else "No",
            ]
        )
    rutas["clientes"] = directorio / "clientes_marketing.csv"
    _guardar_csv(
        rutas["clientes"],
        [
            "Nombre",
            "Correo",
            "Celular",
            "Comuna",
            "Fecha última compra",
            "Monto compras 2026",
            "Acepta publicidad",
        ],
        filas,
    )

    # 4. Proveedores y los datos que reciben (base de la red de cascada).
    proveedores = [
        ("Remuneraciones del Sur SpA", "Cálculo de sueldos", "Nómina de trabajadores"),
        (
            "Transportes Biobío Ltda.",
            "Despacho a clientes",
            "Nombre, dirección y celular de clientes",
        ),
        ("Publicidad Austral SpA", "Envío de campañas", "Correo y celular de clientes"),
        ("Eventos Laja SpA", "Organización del paseo", "Planilla del paseo de fin de año"),
        ("Contabilidad Integral Ltda.", "Contabilidad", "Nómina y facturas"),
        ("Nube Segura SpA", "Respaldo de archivos", "Todas las planillas"),
    ]
    filas = []
    for razon, servicio, datos in proveedores:
        nombre, apellidos = g.persona()
        filas.append(
            [
                razon,
                g.rut(),
                servicio,
                datos,
                f"{nombre} {apellidos}",
                g.correo(nombre, apellidos),
                g.movil(),
            ]
        )
    rutas["proveedores"] = directorio / "proveedores.csv"
    _guardar_csv(
        rutas["proveedores"],
        [
            "Razón social",
            "RUT empresa",
            "Servicio",
            "Datos que recibe",
            "Contacto",
            "Correo contacto",
            "Celular contacto",
        ],
        filas,
    )
    return rutas
