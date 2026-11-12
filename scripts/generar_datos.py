"""Genera la base de datos del MVP: sedes REALES + pacientes, profesionales, agendas y citas SINTÉTICOS calibrados con datos reales.

Qué es real (datos/reales/, ver FUENTES.md):
  - Sedes: código REPS, dirección, comuna, barrio, coordenadas y horario de atención de cada centro de salud.
  - Unidad hospitalaria de referencia: la más cercana con coordenadas reales (scripts/preparar_sedes.py).
  - Días de espera: los de la propia Metrosalud en 2023 (medicina general 3 días calendario ≈ 2 hábiles,
    odontología 3,3 ≈ 2, ginecología 14,5 ≈ 10). La agenda se calibra para que el primer cupo libre aparezca ahí.
  - Tamaño de la plantilla: consultorios reales de Metrosalud (115 de medicina general, 129 unidades odontológicas).
  - Pacientes: edad y sexo según la pirámide DANE 2026 de Medellín (60+); EPS y régimen según la población
    asignada a Metrosalud (75 % Savia Salud subsidiado, 10 % contributivo, 15 % población pobre no asegurada).
Qué es sintético: personas, nombres, cédulas, profesionales, cupos, órdenes y citas.

Uso:
    python scripts/generar_datos.py                    # agenda desde hoy, 40 días hábiles
    python scripts/generar_datos.py --desde 2026-11-12 --pacientes 800 --semilla 7
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

import holidays
from faker import Faker

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from magnolia.bitacora import respaldar_si_hay  # noqa: E402
from magnolia.catalogo import especialidades  # noqa: E402
from magnolia.config import config  # noqa: E402
from magnolia.db import conectar, crear_esquema  # noqa: E402
from magnolia.textos import direccion_hablada  # noqa: E402

DATOS = RAIZ / "datos"

# Profesionales por tipo de sede. Calibrado para sumar lo que reporta Metrosalud (informe de empalme, oct-2023):
# 115 consultorios de medicina general y 129 unidades odontológicas en 10 UH y 41 centros de salud con citas.
# 41 CS x 2 + 10 UH x 4 ≈ 122 médicos generales; 41 x 2 + 10 x 3,5 ≈ 117 odontólogos.
PLANTILLA = {
    "CS": {"medicina_general": (1, 3), "odontologia": (1, 3)},
    "UH": {"medicina_general": (3, 5), "odontologia": (3, 4), "medicina_interna": (1, 1), "optometria": (1, 1),
           "nutricion": (1, 1), "psicologia": (1, 1), "ginecologia": (1, 1)},
}
ESPECIALISTAS_DIAS_SEMANA = 3          # especialistas atienden 3 días a la semana (supuesto: rotan entre UH)
# Consulta externa en las unidades hospitalarias (supuesto: el horario "24 horas" del REPS es el de urgencias)
JORNADA_UH = [(time(7, 0), time(12, 0)), (time(13, 0), time(16, 0))]
ALMUERZO = (time(12, 0), time(13, 0))  # supuesto: pausa de mediodía en los centros de salud

# Población asignada a Metrosalud (informe de empalme, sep-2023) y nota de la Alcaldía (2022) para el contributivo
EPS_REGIMEN_PESOS = {
    ("Savia Salud", "subsidiado"): 0.75,
    ("Savia Salud", "contributivo"): 0.08,
    ("Nueva EPS", "contributivo"): 0.01,      # el 2 % restante del contributivo se reparte (supuesto)
    ("Sura", "contributivo"): 0.01,
    ("Sin EPS - población pobre no asegurada (Distrito de Medellín)", "no asegurado"): 0.15,
}

DEMO = [
    dict(documento="43527891", nombres="María Ofelia", apellidos="Restrepo de Gómez", sexo="F", edad=74,
         eps="Savia Salud", regimen="subsidiado", sede="050010217815", telefono="3104567812"),
    dict(documento="8345678", nombres="José Aníbal", apellidos="Zapata Ríos", sexo="M", edad=81,
         eps="Nueva EPS", regimen="subsidiado", sede="050010217808", telefono="3157894561"),
    dict(documento="32456789", nombres="Rosa Elena", apellidos="Cardona Muñoz", sexo="F", edad=68,
         eps="Sura", regimen="contributivo", sede="050010217804", telefono="3006543217"),
    # Cédulas fáciles de recordar para probar (siempre iguales)
    dict(documento="123", nombres="Luz Marina", apellidos="Ospina Vélez", sexo="F", edad=70,
         eps="Savia Salud", regimen="subsidiado", sede="050010217833", telefono="3012345678"),     # sin citas ni órdenes
    dict(documento="000", nombres="Jesús Antonio", apellidos="Henao Patiño", sexo="M", edad=77,
         eps="Savia Salud", regimen="subsidiado", sede="050010217820", telefono="3023456789"),     # una cita de medicina general
    dict(documento="12345", nombres="Gloria Inés", apellidos="Mejía Arango", sexo="F", edad=66,
         eps="Savia Salud", regimen="contributivo", sede="050010217821", telefono="3034567890"),   # orden de medicina interna
]


def dias_habiles(desde: date, n: int) -> list[date]:
    festivos = holidays.country_holidays("CO", years=range(desde.year, desde.year + 2))
    dias, d = [], desde
    while len(dias) < n:
        if d.weekday() < 5 and d not in festivos:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def cargar_sedes() -> list[dict]:
    """Sedes reales: REPS (teléfono) + archivo georreferenciado que arma scripts/preparar_sedes.py."""
    with open(DATOS / "reales" / "reps_sedes_metrosalud_medellin.csv", encoding="utf-8") as f:
        reps = {r["codigo_habilitacion_sede"]: r for r in csv.DictReader(f)}
    with open(DATOS / "reales" / "sedes_metrosalud_georreferenciadas.csv", encoding="utf-8") as f:
        geo = list(csv.DictReader(f))
    sedes = []
    for g in geo:
        r = reps[g["codigo_habilitacion_sede"]]
        sedes.append(dict(id=g["codigo_habilitacion_sede"], nombre_reps=r["nombre_sede"], nombre=g["nombre_corto"],
                          tipo=g["tipo"], uh_referencia=g["uh_referencia"], direccion=r["direccion_sede"],
                          direccion_hablada=direccion_hablada(r["direccion_sede"]), telefono=r["telefono_sede"],
                          comuna=g["comuna"], barrio=g["barrio"], latitud=float(g["latitud"]), longitud=float(g["longitud"]),
                          jornadas=jornadas_sede(g)))
    return sedes


def _horas(texto: str) -> tuple[int, int] | None:
    """'07 a 16' -> (7, 16); '00 a 24' o '24 HORAS' -> (0, 24); cerrado o sin dato -> None."""
    t = texto.strip().upper()
    if "24 HORAS" in t:
        return 0, 24
    partes = t.split(" A ")
    if len(partes) != 2 or not all(p.strip().isdigit() for p in partes):
        return None
    a, b = int(partes[0]), int(partes[1])
    return (a, b) if b > a else None


def jornadas_sede(g: dict) -> dict[int, list[tuple[time, time]]]:
    """Bloques de consulta por día hábil (0 = lunes) a partir del horario REAL de la sede (Gobernación de Antioquia)."""
    resultado: dict[int, list[tuple[time, time]]] = {}
    for dia, nombre in enumerate(["lunes", "martes", "miercoles", "jueves", "viernes"]):
        h = _horas(g[f"horario_{nombre}"])
        if h is None:
            continue
        if g["tipo"] == "UH" or h == (0, 24):
            resultado[dia] = JORNADA_UH
            continue
        abre, cierra = time(h[0]), time(min(h[1], 23))
        bloques = [(abre, min(cierra, ALMUERZO[0]))]
        if cierra > ALMUERZO[1]:
            bloques.append((ALMUERZO[1], cierra))
        resultado[dia] = [b for b in bloques if b[1] > b[0]]
    return resultado


def numero_cedula(rng: random.Random, sexo: str, edad: int) -> str:
    # Rangos aproximados de cédulas antiguas expedidas en Antioquia (solo para que se vean verosímiles)
    if sexo == "F":
        return str(rng.randint(21_000_000, 43_999_999) if edad >= 60 else rng.randint(1_000_000_000, 1_040_000_000))
    return str(rng.choice([rng.randint(3_300_000, 15_999_999), rng.randint(70_000_000, 71_999_999)]))


def cargar_piramide() -> list[tuple[int, int, int, int]]:
    """Pirámide DANE 2026 de Medellín, 60 años y más: (edad_min, edad_max, mujeres, hombres)."""
    with open(DATOS / "reales" / "poblacion_medellin_60mas_2026.csv", encoding="utf-8") as f:
        return [(int(r["edad_min"]), int(r["edad_max"]), int(r["mujeres"]), int(r["hombres"])) for r in csv.DictReader(f)]


def sexo_y_edad(rng: random.Random, piramide: list[tuple[int, int, int, int]]) -> tuple[str, int]:
    """Muestra (sexo, edad) con las proporciones reales de la población de 60+ de Medellín."""
    celdas = [(s, mn, mx) for mn, mx, _, _ in piramide for s in ("F", "M")]
    pesos = [m if s == "F" else h for mn, mx, m, h in piramide for s in ("F", "M")]
    s, mn, mx = rng.choices(celdas, weights=pesos)[0]
    return s, rng.randint(mn, mx)


def generar(args) -> None:
    rng = random.Random(args.semilla)
    fake = Faker("es_CO")
    fake.seed_instance(args.semilla)
    desde = date.fromisoformat(args.desde) if args.desde else config.hoy()
    ruta_db = Path(args.db)
    respaldo = respaldar_si_hay(ruta_db, DATOS / "bitacoras")  # no perder las conversaciones de las pruebas
    if respaldo and not getattr(args, "silencioso", False):
        print(f"Bitácora anterior guardada en {respaldo}")
    if ruta_db.exists():
        ruta_db.unlink()
    for sufijo in ("-wal", "-shm"):
        Path(str(ruta_db) + sufijo).unlink(missing_ok=True)
    con = conectar(ruta_db)
    crear_esquema(con)
    con.execute("BEGIN")

    # --- Sedes (reales) y especialidades (catálogo)
    sedes = cargar_sedes()
    con.executemany("INSERT INTO sedes VALUES (:id,:nombre_reps,:nombre,:tipo,:uh_referencia,:direccion,:direccion_hablada,"
                    ":telefono,:comuna,:barrio,:latitud,:longitud)", sedes)
    jornadas = {s["id"]: s["jornadas"] for s in sedes}
    esps = especialidades()
    con.executemany("INSERT INTO especialidades VALUES (?,?,?,?,?,?,?)", [
        (e.codigo, e.nombre, int(e.disponible), int(e.solo_unidad_hospitalaria), int(e.requiere_orden),
         e.duracion_min, e.dias_espera_objetivo) for e in esps.values()])

    # --- Profesionales (sintéticos)
    profesionales = []
    for s in sedes:
        for esp, (mn, mx) in PLANTILLA[s["tipo"]].items():
            for _ in range(rng.randint(mn, mx)):
                genero = rng.choices(["F", "M"], weights=[0.6, 0.4])[0]
                nombre = (fake.first_name_female() if genero == "F" else fake.first_name_male()).split()[0] + " " + fake.last_name()
                abiertos = sorted(jornadas[s["id"]])  # días hábiles en que la sede atiende (horario real)
                dias_trabajo = abiertos if esp in ("medicina_general", "odontologia") else \
                    sorted(rng.sample(abiertos, min(ESPECIALISTAS_DIAS_SEMANA, len(abiertos))))
                profesionales.append(dict(id=len(profesionales) + 1, nombre=nombre, genero=genero, especialidad=esp,
                                          sede_id=s["id"], dias=dias_trabajo))
    con.executemany("INSERT INTO profesionales VALUES (:id,:nombre,:genero,:especialidad,:sede_id)", profesionales)

    # --- Cupos: cada uno con un número aleatorio fijo; luego se calibra la ocupación por especialidad
    dias = dias_habiles(desde, args.dias_habiles)
    cupos = []  # (prof, sede, esp, inicio, fin, k_dia, u)
    for p in profesionales:
        dur = timedelta(minutes=esps[p["especialidad"]].duracion_min)
        for k, d in enumerate(dias):
            if d.weekday() not in p["dias"]:
                continue
            for ini, fin in jornadas[p["sede_id"]][d.weekday()]:
                t = datetime.combine(d, ini)
                while t + dur <= datetime.combine(d, fin):
                    cupos.append([p["id"], p["sede_id"], p["especialidad"], t, t + dur, k, rng.random()])
                    t += dur

    def ocupacion(k: int, T: int) -> float:
        if k < T:
            return 0.9993                      # prácticamente lleno: solo cupos liberados por cancelaciones
        return max(0.35, 0.92 - 0.05 * (k - T))

    def espera_promedio(lista, T) -> float:
        primero = {}
        for c in lista:
            if c[6] >= ocupacion(c[5], T):
                clave = c[1]
                primero[clave] = min(primero.get(clave, 10**6), c[5])
        return statistics.mean(primero.values()) if primero else float("inf")

    por_esp = defaultdict(list)
    for c in cupos:
        por_esp[c[2]].append(c)
    calibracion = []
    T_esp = {}
    for esp, lista in por_esp.items():
        objetivo = esps[esp].dias_espera_objetivo
        mejor = min(range(0, args.dias_habiles), key=lambda T: abs(espera_promedio(lista, T) - objetivo))
        T_esp[esp] = mejor
        calibracion.append(dict(especialidad=esp, dias_espera_objetivo=objetivo,
                                dias_espera_simulados=round(espera_promedio(lista, mejor), 2),
                                parametro_T=mejor, cupos_totales=len(lista)))

    filas_cupos = []
    for i, c in enumerate(cupos, 1):
        estado = "ocupado" if c[6] < ocupacion(c[5], T_esp[c[2]]) else "libre"
        filas_cupos.append((i, c[0], c[1], c[2], c[3].isoformat(timespec="minutes"), c[4].isoformat(timespec="minutes"), estado))
    con.executemany("INSERT INTO cupos VALUES (?,?,?,?,?,?,?)", filas_cupos)

    # --- Pacientes (sintéticos) + 3 pacientes de demostración con datos fijos
    # Generador aparte para pacientes y órdenes: así las cédulas no cambian según el día en que se genere la agenda
    rng = random.Random(args.semilla + 1)
    fake.seed_instance(args.semilla + 1)
    pesos_sede = [3 if s["tipo"] == "UH" else 1 for s in sedes]  # supuesto: las UH tienen más población adscrita
    piramide = cargar_piramide()
    eps_regimen, pesos_eps = list(EPS_REGIMEN_PESOS), list(EPS_REGIMEN_PESOS.values())
    pacientes, usados = [], set()
    for d in DEMO:
        nacimiento = date(desde.year - d["edad"], 3, 14)
        pacientes.append(dict(id=len(pacientes) + 1, tipo_documento="CC", documento=d["documento"], nombres=d["nombres"],
                              apellidos=d["apellidos"], sexo=d["sexo"], fecha_nacimiento=nacimiento.isoformat(),
                              telefono=d["telefono"], eps=d["eps"], regimen=d["regimen"], sede_id=d["sede"]))
        usados.add(d["documento"])
    while len(pacientes) < args.pacientes + len(DEMO):
        sexo, edad = sexo_y_edad(rng, piramide)
        doc = numero_cedula(rng, sexo, edad)
        if doc in usados:
            continue
        usados.add(doc)
        nombres = fake.first_name_female() if sexo == "F" else fake.first_name_male()
        apellidos = f"{fake.last_name()} {fake.last_name()}"
        nacimiento = desde - timedelta(days=edad * 365 + rng.randint(0, 364))
        eps, regimen = rng.choices(eps_regimen, weights=pesos_eps)[0]
        pacientes.append(dict(id=len(pacientes) + 1, tipo_documento="CC", documento=doc, nombres=nombres, apellidos=apellidos,
                              sexo=sexo, fecha_nacimiento=nacimiento.isoformat(), telefono=f"3{rng.randint(0, 2)}{rng.randint(0, 9)}{rng.randint(1_000_000, 9_999_999)}",
                              eps=eps, regimen=regimen, sede_id=rng.choices(sedes, weights=pesos_sede)[0]["id"]))
    con.executemany("INSERT INTO pacientes VALUES (:id,:tipo_documento,:documento,:nombres,:apellidos,:sexo,:fecha_nacimiento,:telefono,:eps,:regimen,:sede_id)", pacientes)

    # --- Órdenes de remisión vigentes (necesarias para especialistas)
    ordenes = []
    for p in pacientes[len(DEMO):]:
        if rng.random() < 0.20:
            esp = rng.choices(["medicina_interna", "nutricion", "psicologia", "ginecologia"], weights=[0.45, 0.2, 0.15, 0.2])[0]
            if esp == "ginecologia" and p["sexo"] == "M":
                esp = "medicina_interna"
            emision = desde - timedelta(days=rng.randint(1, 30))
            ordenes.append((len(ordenes) + 1, p["id"], esp, emision.isoformat(), (emision + timedelta(days=90)).isoformat(), "activa"))
    ordenes.append((len(ordenes) + 1, 1, "medicina_interna", (desde - timedelta(days=10)).isoformat(),
                    (desde + timedelta(days=80)).isoformat(), "activa"))  # demo: doña María tiene orden de medicina interna
    ordenes.append((len(ordenes) + 1, 6, "medicina_interna", (desde - timedelta(days=5)).isoformat(),
                    (desde + timedelta(days=85)).isoformat(), "activa"))  # cédula 12345: doña Gloria
    con.executemany("INSERT INTO ordenes VALUES (?,?,?,?,?,?)", ordenes)

    # --- Citas ya programadas (por call center) para ~15 % de los pacientes y para los demo
    ahora_txt = datetime.combine(desde, time(6, 0)).isoformat(timespec="minutes")

    def reservar_cupo(paciente_id: int, sede_id: str, esp: str, k_min: int, hora_pref: time | None = None) -> bool:
        fila = con.execute(
            "SELECT id, profesional_id, inicio FROM cupos WHERE especialidad=? AND sede_id=? AND estado='libre' AND inicio>=? "
            "ORDER BY (CASE WHEN ? IS NOT NULL AND time(inicio)=? THEN 0 ELSE 1 END), inicio LIMIT 1",
            (esp, sede_id, datetime.combine(dias[min(k_min, len(dias) - 1)], time(0)).isoformat(timespec="minutes"),
             hora_pref.strftime("%H:%M") if hora_pref else None, hora_pref.strftime("%H:%M") if hora_pref else None)).fetchone()
        if not fila:
            return False
        con.execute("UPDATE cupos SET estado='ocupado' WHERE id=?", (fila["id"],))
        con.execute("INSERT INTO citas (paciente_id,cupo_id,especialidad,sede_id,profesional_id,inicio,estado,canal,creada_en) "
                    "VALUES (?,?,?,?,?,?,'programada','call_center',?)",
                    (paciente_id, fila["id"], esp, sede_id, fila["profesional_id"], fila["inicio"], ahora_txt))
        return True

    reservar_cupo(1, "050010217815", "medicina_general", 3, time(8, 20))     # doña María
    reservar_cupo(2, "050010217808", "odontologia", 5, time(9, 0))           # don José: dos citas
    reservar_cupo(2, "050010217808", "medicina_general", 9, time(14, 0))
    reservar_cupo(5, "050010217820", "medicina_general", 4, time(9, 0))      # cédula 000: don Jesús
    for p in pacientes[len(DEMO):]:
        if rng.random() < 0.15:
            esp = rng.choices(["medicina_general", "odontologia"], weights=[0.75, 0.25])[0]
            reservar_cupo(p["id"], p["sede_id"], esp, rng.randint(2, 25))

    con.execute("INSERT INTO metadatos VALUES ('generado_en', ?)", (datetime.now().isoformat(timespec="seconds"),))
    con.execute("INSERT INTO metadatos VALUES ('agenda_desde', ?)", (desde.isoformat(),))
    con.execute("INSERT INTO metadatos VALUES ('agenda_hasta', ?)", (dias[-1].isoformat(),))
    con.execute("INSERT INTO metadatos VALUES ('semilla', ?)", (str(args.semilla),))
    con.execute("COMMIT")

    if getattr(args, "exportar", True):
        exportar_csv(con, calibracion)
    if getattr(args, "silencioso", False):
        con.close()
        return
    libres = con.execute("SELECT COUNT(*) FROM cupos WHERE estado='libre'").fetchone()[0]
    print(f"Base creada en {ruta_db}")
    print(f"  Agenda: {dias[0]} a {dias[-1]} ({len(dias)} días hábiles, sin festivos)")
    print(f"  {len(sedes)} sedes reales | {len(profesionales)} profesionales | {len(pacientes)} pacientes | "
          f"{len(filas_cupos):,} cupos ({libres:,} libres) | {len(ordenes)} órdenes".replace(",", "."))
    print("  Calibración (días hábiles hasta el primer cupo libre, promedio por sede):")
    for c in sorted(calibracion, key=lambda c: c["especialidad"]):
        print(f"    {c['especialidad']:<18} objetivo {c['dias_espera_objetivo']:>3}  simulado {c['dias_espera_simulados']:>6}")
    print("  Pacientes de demostración (cédulas para probar):")
    for d in DEMO:
        print(f"    {d['documento']:>10}  {d['nombres']} {d['apellidos']} ({d['edad']} años, {d['eps']})")
    con.close()


def exportar_csv(con, calibracion) -> None:
    salida = DATOS / "sinteticos"
    salida.mkdir(exist_ok=True)
    consultas = {
        "sedes.csv": "SELECT * FROM sedes",
        "profesionales.csv": "SELECT * FROM profesionales",
        "pacientes.csv": "SELECT * FROM pacientes",
        "ordenes.csv": "SELECT * FROM ordenes",
        "citas.csv": "SELECT * FROM citas",
        "cupos_por_semana.csv": "SELECT especialidad, strftime('%Y-%W', inicio) AS semana, "
                                "SUM(estado='libre') AS libres, SUM(estado='ocupado') AS ocupados FROM cupos GROUP BY 1,2 ORDER BY 1,2",
    }
    for nombre, sql in consultas.items():
        cur = con.execute(sql)
        cols = [c[0] for c in cur.description]
        with open(salida / nombre, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(cur.fetchall())
    with open(salida / "resumen_calibracion.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(calibracion[0].keys()))
        w.writeheader()
        w.writerows(calibracion)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", help="primer día de la agenda (AAAA-MM-DD); por defecto hoy")
    ap.add_argument("--dias-habiles", type=int, default=40)
    ap.add_argument("--pacientes", type=int, default=1500)
    ap.add_argument("--semilla", type=int, default=13)
    ap.add_argument("--db", default=str(config.db_path))
    generar(ap.parse_args())
