"""Operaciones sobre la agenda simulada de la IPS: es lo que en producción sería la integración con el
software de citas de cada IPS (vía API, HL7/FHIR o base de datos)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .catalogo import especialidades


@dataclass
class Paciente:
    id: int
    documento: str
    nombres: str
    apellidos: str
    sexo: str
    eps: str
    sede_id: str


@dataclass
class Opcion:
    cupo_id: int
    inicio: datetime
    sede_id: str
    sede_nombre: str
    sede_direccion: str
    profesional: str
    genero: str
    especialidad: str


@dataclass
class Cita:
    id: int
    especialidad: str
    inicio: datetime
    sede_id: str
    sede_nombre: str
    sede_direccion: str
    profesional: str
    genero: str
    cupo_id: int


class Agenda:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    # ---------- pacientes
    def paciente_por_documento(self, documento: str) -> Paciente | None:
        f = self.con.execute("SELECT * FROM pacientes WHERE documento=?", (documento.lstrip("0"),)).fetchone()
        return self._paciente(f)

    def paciente(self, paciente_id: int) -> Paciente | None:
        return self._paciente(self.con.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,)).fetchone())

    @staticmethod
    def _paciente(f) -> Paciente | None:
        if not f:
            return None
        return Paciente(id=f["id"], documento=f["documento"], nombres=f["nombres"], apellidos=f["apellidos"],
                        sexo=f["sexo"], eps=f["eps"], sede_id=f["sede_id"])

    def paciente_por_canal(self, canal: str, usuario_id: str) -> Paciente | None:
        f = self.con.execute("SELECT paciente_id FROM canal_usuarios WHERE canal=? AND usuario_id=?", (canal, usuario_id)).fetchone()
        return self.paciente(f["paciente_id"]) if f else None

    def vincular(self, canal: str, usuario_id: str, paciente_id: int, ahora: datetime) -> None:
        self.con.execute("INSERT OR REPLACE INTO canal_usuarios VALUES (?,?,?,?)",
                         (canal, usuario_id, paciente_id, ahora.isoformat(timespec="seconds")))

    def desvincular(self, canal: str, usuario_id: str) -> None:
        self.con.execute("DELETE FROM canal_usuarios WHERE canal=? AND usuario_id=?", (canal, usuario_id))

    # ---------- sedes y órdenes
    def sede(self, sede_id: str) -> sqlite3.Row:
        return self.con.execute("SELECT * FROM sedes WHERE id=?", (sede_id,)).fetchone()

    def sedes_para(self, paciente: Paciente, especialidad: str) -> list[str]:
        """Orden de búsqueda: la sede del paciente, su unidad hospitalaria de referencia y luego las demás."""
        esp = especialidades()[especialidad]
        propia = self.sede(paciente.sede_id)
        orden: list[str] = []
        if not esp.solo_unidad_hospitalaria or propia["tipo"] == "UH":
            orden.append(propia["id"])
        if propia["uh_referencia"] and propia["uh_referencia"] not in orden:
            orden.append(propia["uh_referencia"])
        return orden

    def ordenes_activas(self, paciente_id: int, hoy: date) -> list[str]:
        """Especialidades con orden vigente, de la más antigua a la más reciente."""
        filas = self.con.execute(
            "SELECT especialidad, min(fecha_emision) AS emision FROM ordenes WHERE paciente_id=? AND estado='activa' "
            "AND vigente_hasta>=? GROUP BY especialidad ORDER BY emision", (paciente_id, hoy.isoformat())).fetchall()
        return [f["especialidad"] for f in filas]

    def orden_activa(self, paciente_id: int, especialidad: str, hoy: date) -> int | None:
        f = self.con.execute(
            "SELECT id FROM ordenes WHERE paciente_id=? AND especialidad=? AND estado='activa' AND vigente_hasta>=? "
            "ORDER BY fecha_emision LIMIT 1", (paciente_id, especialidad, hoy.isoformat())).fetchone()
        return f["id"] if f else None

    # ---------- búsqueda de cupos
    def buscar_opciones(self, paciente: Paciente, especialidad: str, ahora: datetime, desde: date | None = None,
                        franja: str | None = None, hora: time | None = None, excluir: list[int] | tuple = (),
                        n: int = 2, ampliar: bool = True, excluir_dias: set[date] | None = None) -> list[Opcion]:
        """Hasta n opciones en días distintos (para que elegir sea fácil), empezando por la sede del paciente."""
        ahora = ahora.replace(tzinfo=None)  # la agenda se guarda en hora local de Bogotá, sin zona
        minimo = max(ahora + timedelta(hours=2), datetime.combine(desde, time(0)) if desde else ahora)
        sedes = self.sedes_para(paciente, especialidad)
        condiciones = ["c.especialidad=?", "c.estado='libre'", "c.inicio>=?"]
        params: list = [especialidad, minimo.isoformat(timespec="minutes")]
        if franja == "manana":
            condiciones.append("time(c.inicio) < '12:00'")
        elif franja == "tarde":
            condiciones.append("time(c.inicio) >= '12:00'")
        if hora:
            condiciones.append("time(c.inicio) >= ?")
            params.append(hora.strftime("%H:%M"))
        if excluir:
            condiciones.append(f"c.id NOT IN ({','.join('?' * len(excluir))})")
            params.extend(excluir)
        sql = ("SELECT c.id, c.inicio, c.sede_id, s.nombre AS sede_nombre, s.direccion_hablada, p.nombre AS prof, "
               "p.genero FROM cupos c JOIN sedes s ON s.id=c.sede_id JOIN profesionales p ON p.id=c.profesional_id "
               f"WHERE {' AND '.join(condiciones)} AND c.sede_id=? ORDER BY c.inicio LIMIT 60")
        candidatos = []
        for prioridad, sede_id in enumerate(sedes):
            for f in self.con.execute(sql, (*params, sede_id)):
                candidatos.append((prioridad, f))
        if ampliar and not candidatos:  # ninguna en sus sedes: buscar en toda la red
            sql_red = sql.replace(" AND c.sede_id=?", "")
            candidatos = [(9, f) for f in self.con.execute(sql_red, params)]
        # ordenar por fecha, pero preferir la sede propia si la diferencia es de 2 días o menos
        candidatos.sort(key=lambda pf: (datetime.fromisoformat(pf[1]["inicio"]) + timedelta(days=2 * pf[0])))
        elegidas: list[Opcion] = []
        dias_usados: set[date] = set(excluir_dias or ())
        for _, f in candidatos:
            inicio = datetime.fromisoformat(f["inicio"])
            if inicio.date() in dias_usados:
                continue
            elegidas.append(Opcion(cupo_id=f["id"], inicio=inicio, sede_id=f["sede_id"], sede_nombre=f["sede_nombre"],
                                   sede_direccion=f["direccion_hablada"], profesional=f["prof"], genero=f["genero"],
                                   especialidad=especialidad))
            dias_usados.add(inicio.date())
            if len(elegidas) == n:
                break
        return elegidas

    # ---------- citas
    def citas_futuras(self, paciente_id: int, ahora: datetime) -> list[Cita]:
        filas = self.con.execute(
            "SELECT ci.id, ci.especialidad, ci.inicio, ci.sede_id, ci.cupo_id, s.nombre AS sede_nombre, "
            "s.direccion_hablada, p.nombre AS prof, p.genero FROM citas ci JOIN sedes s ON s.id=ci.sede_id "
            "JOIN profesionales p ON p.id=ci.profesional_id WHERE ci.paciente_id=? AND ci.estado='programada' "
            "AND ci.inicio>=? ORDER BY ci.inicio", (paciente_id, ahora.replace(tzinfo=None).isoformat(timespec="minutes"))).fetchall()
        return [Cita(id=f["id"], especialidad=f["especialidad"], inicio=datetime.fromisoformat(f["inicio"]),
                     sede_id=f["sede_id"], sede_nombre=f["sede_nombre"], sede_direccion=f["direccion_hablada"],
                     profesional=f["prof"], genero=f["genero"], cupo_id=f["cupo_id"]) for f in filas]

    def reservar(self, paciente_id: int, cupo_id: int, canal: str, ahora: datetime, orden_id: int | None = None) -> int | None:
        """Reserva atómica: si otra persona tomó el cupo un segundo antes, devuelve None."""
        con = self.con
        con.execute("BEGIN IMMEDIATE")
        try:
            cur = con.execute("UPDATE cupos SET estado='ocupado' WHERE id=? AND estado='libre'", (cupo_id,))
            if cur.rowcount != 1:
                con.execute("ROLLBACK")
                return None
            c = con.execute("SELECT * FROM cupos WHERE id=?", (cupo_id,)).fetchone()
            cur = con.execute(
                "INSERT INTO citas (paciente_id,cupo_id,especialidad,sede_id,profesional_id,inicio,estado,canal,orden_id,creada_en) "
                "VALUES (?,?,?,?,?,?,'programada',?,?,?)",
                (paciente_id, cupo_id, c["especialidad"], c["sede_id"], c["profesional_id"], c["inicio"], canal, orden_id,
                 ahora.isoformat(timespec="seconds")))
            if orden_id:
                con.execute("UPDATE ordenes SET estado='usada' WHERE id=?", (orden_id,))
            con.execute("COMMIT")
            return cur.lastrowid
        except Exception:
            con.execute("ROLLBACK")
            raise

    def cancelar(self, cita_id: int, paciente_id: int, ahora: datetime, nuevo_estado: str = "cancelada") -> bool:
        con = self.con
        con.execute("BEGIN IMMEDIATE")
        try:
            c = con.execute("SELECT * FROM citas WHERE id=? AND paciente_id=? AND estado='programada'", (cita_id, paciente_id)).fetchone()
            if not c:
                con.execute("ROLLBACK")
                return False
            con.execute("UPDATE citas SET estado=?, modificada_en=? WHERE id=?", (nuevo_estado, ahora.isoformat(timespec="seconds"), cita_id))
            con.execute("UPDATE cupos SET estado='libre' WHERE id=?", (c["cupo_id"],))  # el cupo vuelve a quedar disponible
            if c["orden_id"]:
                con.execute("UPDATE ordenes SET estado='activa' WHERE id=?", (c["orden_id"],))
            con.execute("COMMIT")
            return True
        except Exception:
            con.execute("ROLLBACK")
            raise

    def reprogramar(self, cita_id: int, paciente_id: int, nuevo_cupo_id: int, canal: str, ahora: datetime) -> int | None:
        orden = self.con.execute("SELECT orden_id FROM citas WHERE id=?", (cita_id,)).fetchone()
        orden_id = orden["orden_id"] if orden else None  # la orden pasa de la cita vieja a la nueva
        nueva = self.reservar(paciente_id, nuevo_cupo_id, canal, ahora)
        if nueva is None:
            return None
        self.cancelar(cita_id, paciente_id, ahora, nuevo_estado="reprogramada")
        if orden_id:
            self.con.execute("UPDATE citas SET orden_id=? WHERE id=?", (orden_id, nueva))
            self.con.execute("UPDATE ordenes SET estado='usada' WHERE id=?", (orden_id,))
        return nueva

    # ---------- bitácora
    def registrar_evento(self, **campos) -> None:
        cols = ",".join(campos)
        self.con.execute(f"INSERT INTO eventos ({cols}) VALUES ({','.join('?' * len(campos))})", tuple(campos.values()))
