"""Normalización de texto en español tal como llega de un reconocedor de voz o de un teclado.

- minúsculas y sin tildes (la ñ se vuelve n para comparar de forma estable)
- corrige errores típicos de escritura/transcripción ("kiero una sita" -> "quiero una cita")
- convierte números dichos en palabras a dígitos ("cuarenta y tres millones ..." -> "43...")
- une números con separadores ("8.345.678" o "32 456 789" -> "8345678", "32456789")
"""
from __future__ import annotations

import re
import unicodedata

UNIDADES = {
    "cero": 0, "uno": 1, "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiun": 21,
    "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28,
    "veintinueve": 29, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600, "setecientos": 700, "setecientas": 700,
    "ochocientos": 800, "ochocientas": 800, "novecientos": 900, "novecientas": 900,
}
MULTIPLICADORES = {"mil": 1_000, "millon": 1_000_000, "millones": 1_000_000}
DIGITOS_SUELTOS = {"cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"}

# Correcciones de palabras completas (errores de ortografía o del reconocedor de voz)
CORRECCIONES = {
    "kiero": "quiero", "qiero": "quiero", "quero": "quiero", "sita": "cita", "sitas": "citas",
    "jeneral": "general", "pa": "para", "q": "que", "xq": "porque",
    "porfa": "por favor", "porfavor": "por favor", "nesecito": "necesito", "nececito": "necesito",
    "ola": "hola", "grasias": "gracias", "ajam": "aja", "aha": "aja",
    "sii": "si", "noo": "no", "dotor": "doctor", "dotora": "doctora",
    "sedula": "cedula", "kancelar": "cancelar", "medico": "medico",
}


def quitar_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _es_numero(tok: str) -> bool:
    return tok in UNIDADES or tok in MULTIPLICADORES


def _valor(tokens: list[str]) -> int:
    """Valor de una secuencia de palabras numéricas: 'setenta y un millones doscientos mil' -> 71200000."""
    total, actual = 0, 0
    for tok in tokens:
        if tok in UNIDADES:
            actual += UNIDADES[tok]
        elif tok == "mil":
            actual = max(actual, 1) * 1_000
        elif tok in ("millon", "millones"):
            total += max(actual, 1) * 1_000_000
            actual = 0
    return total + actual


def _numero_inicia(tokens: list[str], i: int) -> bool:
    """'un'/'una' solo cuentan como número si van seguidos de mil/millón (p. ej. 'un millón')."""
    tok = tokens[i]
    if tok in ("un", "una"):
        sig = tokens[i + 1] if i + 1 < len(tokens) else ""
        return sig in MULTIPLICADORES
    return _es_numero(tok)


def palabras_a_numeros(texto: str) -> str:
    tokens = texto.split()
    salida: list[str] = []
    i = 0
    while i < len(tokens):
        if not _numero_inicia(tokens, i):
            salida.append(tokens[i])
            i += 1
            continue
        # Secuencia de dígitos sueltos dichos uno por uno: "tres dos cuatro cinco..."
        j = i
        while j < len(tokens) and tokens[j] in DIGITOS_SUELTOS:
            j += 1
        if j - i >= 3:
            salida.append("".join(str(UNIDADES[t]) for t in tokens[i:j]))
            i = j
            continue
        # Número compuesto: "cuarenta y tres millones quinientos ..."
        grupo = [tokens[i]]
        j = i + 1
        while j < len(tokens):
            tok = tokens[j]
            if _es_numero(tok) and tok not in ("un", "una"):
                grupo.append(tok)
                j += 1
            elif tok in ("un", "una") and j + 1 < len(tokens) and tokens[j + 1] in MULTIPLICADORES:
                grupo.append(tok)
                j += 1
            elif tok == "y" and j + 1 < len(tokens) and tokens[j + 1] in UNIDADES and UNIDADES[tokens[j + 1]] < 10 \
                    and grupo and grupo[-1] in UNIDADES and 20 <= UNIDADES[grupo[-1]] <= 90:
                j += 1  # "cuarenta y tres": la 'y' une decenas con unidades
            else:
                break
        salida.append(str(_valor(grupo)))
        i = j
    return " ".join(salida)


_SEPARADORES = re.compile(r"\b\d{1,3}(?:[ .,]\d{3})+\b")


def unir_numeros_separados(texto: str) -> str:
    return _SEPARADORES.sub(lambda m: re.sub(r"[ .,]", "", m.group(0)), texto)


def normalizar(texto: str) -> str:
    """Devuelve una versión del texto lista para aplicar reglas."""
    t = texto.lower()
    t = t.replace("ñ", "n")
    t = quitar_tildes(t)
    t = unir_numeros_separados(t)
    t = re.sub(r"[^a-z0-9#: ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    tokens = [CORRECCIONES.get(tok, tok) for tok in t.split()]
    # vocales repetidas al alargar la palabra hablando: "nooo", "siii", "bueeeno"
    tokens = [re.sub(r"([aeiou])\1{2,}", r"\1", tok) for tok in tokens]
    t = " ".join(tokens)
    t = palabras_a_numeros(t)
    return t
