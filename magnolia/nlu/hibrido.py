"""Comprensión híbrida: primero reglas (gratis, instantáneo); el LLM solo cuando las reglas dudan.

En la prueba con frases nunca vistas, 8 de cada 11 errores de las reglas fueron casos en que ellas
mismas dijeron "no sé" (desconocido o baja confianza). Esos son justamente los que se envían al LLM.
"""
from __future__ import annotations

from datetime import date

from . import llm, reglas
from .tipos import Interpretacion

UMBRAL = 0.7
CAMPOS = ("especialidad", "fecha", "franja", "hora", "opcion", "documento", "dia_semana")


def _suficiente(r: Interpretacion, contexto: str) -> bool:
    if r.intencion == "desconocido" or r.confianza < UMBRAL:
        return False
    if contexto == "esperando_documento" and r.intencion == "dar_documento":
        return bool(r.documento)
    return True


def interpretar(texto: str, contexto: str = "inicio", hoy: date | None = None) -> Interpretacion:
    r = reglas.interpretar(texto, contexto, hoy)
    if _suficiente(r, contexto):
        return r
    l = llm.interpretar(texto, contexto, hoy)
    if l is None or l.intencion == "desconocido":
        return r
    # El LLM decide la intención; los extractores deterministas (fechas, cédula) completan lo que falte.
    for campo in CAMPOS:
        if getattr(l, campo) is None and getattr(r, campo) is not None:
            setattr(l, campo, getattr(r, campo))
    l.asap = l.asap or r.asap
    l.fuente = "hibrido"
    return l
