from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, time

INTENCIONES = (
    "agendar", "consultar", "cancelar", "reprogramar", "saludo", "despedida", "ayuda", "humano",
    "afirmar", "negar", "repetir", "urgencia", "fuera_alcance", "informar", "elegir_opcion",
    "otras_opciones", "dar_documento", "menu", "desconocido",
)

# Lo que el diálogo espera en cada estado; orienta a las reglas y al LLM.
CONTEXTOS = (
    "inicio", "esperando_especialidad", "esperando_fecha", "esperando_opcion",
    "esperando_confirmacion", "esperando_documento", "esperando_cita",
)


@dataclass
class Interpretacion:
    intencion: str = "desconocido"
    confianza: float = 0.0
    especialidad: str | None = None
    fecha: date | None = None
    asap: bool = False
    franja: str | None = None
    hora: time | None = None
    opcion: int | None = None
    documento: str | None = None
    dia_semana: int | None = None   # "la del martes" -> 1 (para elegir entre opciones ofrecidas)
    fuente: str = "reglas"
    texto: str = ""

    def como_dict(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat() if self.fecha else None
        d["hora"] = self.hora.strftime("%H:%M") if self.hora else None
        return d
