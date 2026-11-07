"""Extracción de fechas, franjas y horas en español coloquial (texto ya normalizado).

Devuelve siempre la fecha *desde la cual* la persona quiere la cita. Ejemplos con hoy = jueves 12/11/2026:
  "manana"                -> 2026-11-13
  "el lunes"              -> 2026-11-16
  "la otra semana"        -> 2026-11-16 (lunes siguiente)
  "el 25"                 -> 2026-11-25
  "a principios de diciembre" -> 2026-12-01
  "lo mas pronto"         -> asap
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

ASAP = re.compile(
    r"\b(lo mas pronto|lo antes posible|cuanto antes|la que haya|lo que haya|lo mas rapido|"
    r"cualquier dia|la mas cercana|la mas pronto|lo primero que haya|pronto posible|ya mismo|"
    r"la primera que haya|la que este disponible|rapidito|prontico|lo mas rapido posible)\b"
)
FRANJA_MANANA = re.compile(r"\b(por|en|de) la manana\b|\bmananita\b|\btemprano\b|\bantes del almuerzo\b|\bantes de mediodia\b")
FRANJA_TARDE = re.compile(r"\b(por|en|de) la tarde\b|\bmas tarde\b|\bdespues del almuerzo\b|\bdespues de mediodia\b|\bpor la tardecita\b")
SEMANA_SIGUIENTE = re.compile(
    r"\b(la otra semana|la proxima semana|la semana entrante|la semana que viene|la siguiente semana|"
    r"proxima semana|otra semana|semana entrante)\b"
)
HORA = re.compile(r"\b(?:a las|las|a la|tipo|como a las|despues de las|desde las)\s+(\d{1,2}|una)(?:\s*(?::|y)\s*(media|cuarto|\d{1,2}))?")


@dataclass
class Tiempo:
    fecha: date | None = None
    asap: bool = False
    franja: str | None = None   # "manana" | "tarde"
    hora: time | None = None


def _siguiente_dia_semana(hoy: date, dia: int) -> date:
    delta = (dia - hoy.weekday()) % 7
    return hoy + timedelta(days=delta or 7)


def _mes_con_anio(hoy: date, mes: int, dia: int = 1) -> date | None:
    anio = hoy.year if mes >= hoy.month else hoy.year + 1
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def extraer_franja(t: str) -> str | None:
    tarde, manana = FRANJA_TARDE.search(t), FRANJA_MANANA.search(t)
    if tarde and manana:  # "por la mañana porque en la tarde no puedo": gana la primera mencionada
        return "manana" if manana.start() < tarde.start() else "tarde"
    if tarde:
        return "tarde"
    if manana:
        return "manana"
    m = HORA.search(t)
    if m:
        h = 1 if m.group(1) == "una" else int(m.group(1))
        return "tarde" if 1 <= h <= 5 or h >= 12 else "manana"
    return None


def extraer_hora(t: str) -> time | None:
    m = HORA.search(t)
    if not m:
        return None
    h = 1 if m.group(1) == "una" else int(m.group(1))
    minutos = 0
    if m.group(2) == "media":
        minutos = 30
    elif m.group(2) == "cuarto":
        minutos = 15
    elif m.group(2):
        minutos = int(m.group(2))
    if 1 <= h <= 5 or "de la tarde" in t:  # la IPS atiende de 7 a. m. a 5 p. m.
        h = h + 12 if h < 12 else h
    if not (0 <= h <= 23 and 0 <= minutos <= 59):
        return None
    return time(h, minutos)


def extraer_fecha(t: str, hoy: date) -> tuple[date | None, bool]:
    """Devuelve (fecha, asap)."""
    if ASAP.search(t):
        return None, True
    # quitar las franjas para que "por la manana" no se lea como "mañana"
    sin_franja = re.sub(r"\b(por|en|de) la manana\b|\bla mananita\b|\bmananita\b", " ", t)

    if re.search(r"\bpasado manana\b", sin_franja):
        return hoy + timedelta(days=2), False
    if re.search(r"\bmanana\b", sin_franja):
        return hoy + timedelta(days=1), False
    if re.search(r"\bhoy\b", sin_franja):
        return hoy, False

    m = re.search(r"\b(?:dentro de|en|de aqui a)\s+(\d{1,2}|una|un)\s+(dias|dia|semanas|semana)\b", sin_franja)
    if m:
        n = 1 if m.group(1) in ("una", "un") else int(m.group(1))
        dias = n * 7 if m.group(2).startswith("semana") else n
        return hoy + timedelta(days=dias), False

    m = re.search(r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\b", sin_franja)
    if m:
        dia, mes = int(m.group(1)), MESES[m.group(2)]
        f = _mes_con_anio(hoy, mes, dia) if 1 <= dia <= 31 else None
        if f and f < hoy:
            f = _mes_con_anio(hoy.replace(year=hoy.year + 1), mes, dia)
        return f, False

    m = re.search(r"\b(principios|comienzos|inicios|mediados|finales|fin) de (" + "|".join(MESES) + r")\b", sin_franja)
    if m:
        mes = MESES[m.group(2)]
        dia = {"mediados": 15, "finales": 22, "fin": 22}.get(m.group(1), 1)
        f = _mes_con_anio(hoy, mes, dia)
        return (max(f, hoy) if f else None), False
    m = re.search(r"\b(?:para|en|el mes de|pa)\s+(" + "|".join(MESES) + r")\b", sin_franja)
    if m:
        f = _mes_con_anio(hoy, MESES[m.group(1)], 1)
        return (max(f, hoy) if f else None), False

    m = re.search(r"\b(?:el|del|para el|el dia|dia)\s+(\d{1,2})\b(?!\s*(?:de la|dias|semanas|y media|:))", sin_franja)
    if m and not re.search(r"\b(?:a las|las)\s+" + m.group(1) + r"\b", sin_franja):
        dia = int(m.group(1))
        if 1 <= dia <= 31:
            try:
                f = hoy.replace(day=dia)
            except ValueError:
                f = None
            if f is None or f < hoy:
                siguiente = (hoy.replace(day=1) + timedelta(days=32)).replace(day=1)
                try:
                    f = siguiente.replace(day=dia)
                except ValueError:
                    f = None
            return f, False

    if SEMANA_SIGUIENTE.search(sin_franja):
        return hoy + timedelta(days=7 - hoy.weekday()), False

    for nombre, dia in DIAS.items():
        if re.search(r"\b" + nombre + r"\b", sin_franja):
            return _siguiente_dia_semana(hoy, dia), False

    if re.search(r"\bfin(ales)? de mes\b", sin_franja):
        f = hoy.replace(day=22)
        return max(f, hoy), False
    return None, False


def extraer_tiempo(t: str, hoy: date) -> Tiempo:
    fecha, asap = extraer_fecha(t, hoy)
    return Tiempo(fecha=fecha, asap=asap, franja=extraer_franja(t), hora=extraer_hora(t))
