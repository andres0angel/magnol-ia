"""Catálogo de especialidades y sinónimos coloquiales (datos/catalogos/especialidades.csv)."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import RAIZ
from .nlu.normalizar import normalizar

RUTA = RAIZ / "datos" / "catalogos" / "especialidades.csv"


@dataclass
class Especialidad:
    codigo: str
    nombre: str
    disponible: bool
    solo_unidad_hospitalaria: bool
    requiere_orden: bool
    duracion_min: int
    dias_espera_objetivo: int
    portafolio_metrosalud: bool = True                           # la red real presta el servicio (informe de empalme 2023)
    sinonimos: list[str] = field(default_factory=list)          # específicos
    sinonimos_genericos: list[str] = field(default_factory=list)  # "doctor", "médico"...


@lru_cache(maxsize=1)
def especialidades() -> dict[str, Especialidad]:
    resultado: dict[str, Especialidad] = {}
    with open(RUTA, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            codigo = fila["codigo"].replace("_generico", "")
            sinonimos = [normalizar(s) for s in fila["sinonimos"].split("|") if s.strip()]
            esp = resultado.get(codigo)
            if esp is None:
                esp = Especialidad(
                    codigo=codigo,
                    nombre=fila["nombre"],
                    disponible=fila["disponible"] == "1",
                    solo_unidad_hospitalaria=fila["solo_unidad_hospitalaria"] == "1",
                    requiere_orden=fila["requiere_orden"] == "1",
                    duracion_min=int(fila["duracion_min"]),
                    dias_espera_objetivo=int(fila["dias_espera_objetivo"]),
                    portafolio_metrosalud=fila.get("portafolio_metrosalud", "1") == "1",
                )
                resultado[codigo] = esp
            if fila["generico"] == "1":
                esp.sinonimos_genericos.extend(sinonimos)
            else:
                esp.sinonimos.extend(sinonimos)
    return resultado


def buscar_especialidad(texto_normalizado: str) -> str | None:
    """Devuelve el código de la especialidad mencionada. Los sinónimos específicos ganan a los genéricos
    ("la doctora de los dientes" -> odontología, no medicina general) y el más largo gana."""
    mejor: tuple[int, int, str] | None = None  # (prioridad, largo, codigo)
    for esp in especialidades().values():
        for prioridad, lista in ((2, esp.sinonimos), (1, esp.sinonimos_genericos)):
            for sin in lista:
                if re.search(r"\b" + re.escape(sin) + r"\b", texto_normalizado):
                    candidato = (prioridad, len(sin), esp.codigo)
                    if mejor is None or candidato[:2] > mejor[:2]:
                        mejor = candidato
    return mejor[2] if mejor else None


def nombre(codigo: str) -> str:
    return especialidades()[codigo].nombre


def disponibles() -> list[Especialidad]:
    return [e for e in especialidades().values() if e.disponible]
