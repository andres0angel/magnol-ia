"""Cómo se dicen las cosas: fechas, horas, direcciones y profesionales en lenguaje hablado y sencillo."""
from __future__ import annotations

import re
from datetime import date, datetime

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

TITULO_PROFESIONAL = {
    "medicina_general": ("el doctor", "la doctora"),
    "medicina_interna": ("el doctor", "la doctora"),
    "ginecologia": ("el doctor", "la doctora"),
    "odontologia": ("el odontólogo", "la odontóloga"),
    "optometria": ("el optómetra", "la optómetra"),
    "nutricion": ("el nutricionista", "la nutricionista"),
    "psicologia": ("el psicólogo", "la psicóloga"),
}


def fecha_hablada(d: date, hoy: date) -> str:
    base = f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"
    if d == hoy:
        return f"hoy {base}"
    if (d - hoy).days == 1:
        return f"mañana {base}"
    return f"el {base}"


def hora_hablada(dt: datetime) -> str:
    h, m = dt.hour, dt.minute
    if h == 12 and m == 0:
        return "a las 12 del mediodía"
    momento = "de la mañana" if h < 12 else "de la tarde"
    h12 = h if h <= 12 else h - 12
    articulo = "a la" if h12 == 1 else "a las"
    if m == 0:
        return f"{articulo} {h12} {momento}"
    if m == 30:
        return f"{articulo} {h12} y media {momento}"
    return f"{articulo} {h12} y {m} {momento}"


def profesional_hablado(nombre: str, genero: str, especialidad: str) -> str:
    masc, fem = TITULO_PROFESIONAL.get(especialidad, ("el doctor", "la doctora"))
    return f"{fem if genero == 'F' else masc} {nombre}"


_ABREVIATURAS = [
    (r"\b(CLL|CL|CALLE)\b\.?", "Calle"), (r"\b(KR|CRA|CR|CARRERA|KRA)\b\.?", "Carrera"),
    (r"\b(DG|DIAG)\b\.?", "Diagonal"), (r"\b(TV|TR|TRANSV)\b\.?", "Transversal"),
    (r"\bAV\b\.?", "Avenida"), (r"\bED\b\.?", "edificio"), (r"\bKM\b", "kilómetro"),
]


def direccion_hablada(direccion: str) -> str:
    d = direccion.upper()
    for patron, reemplazo in _ABREVIATURAS:
        d = re.sub(patron, reemplazo, d)
    d = re.sub(r"\s*(#|N°|Nº|NO\.|N)\s*(?=\d)", " número ", d)
    d = re.sub(r"\s*-\s*", " - ", d)
    d = re.sub(r"\s+", " ", d).strip()
    # vuelve a minúsculas las palabras, conserva letras sueltas de placas (A, B, BB, SUR)
    palabras = []
    for p in d.split(" "):
        if p in ("Calle", "Carrera", "Diagonal", "Transversal", "Avenida", "número", "edificio", "kilómetro"):
            palabras.append(p)
        elif re.fullmatch(r"\d+[A-Z]{0,3}", p) or re.fullmatch(r"[A-Z]{1,2}", p):
            palabras.append(p)
        else:
            palabras.append(p.capitalize() if p != "SUR" else "Sur")
    return " ".join(palabras)


def tratamiento(nombres: str, sexo: str) -> str:
    """'doña María', 'don José': trato respetuoso habitual con adultos mayores en Antioquia."""
    primer = nombres.split()[0].capitalize()
    return f"{'doña' if sexo == 'F' else 'don'} {primer}"


def para_voz(texto: str) -> str:
    """Limpia el texto antes de convertirlo en audio (sin viñetas ni símbolos)."""
    t = re.sub(r"[*_•#>`]", "", texto)
    t = t.replace("\n", ". ").replace("..", ".")
    return re.sub(r"\s+", " ", t).strip()
