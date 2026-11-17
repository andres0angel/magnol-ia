"""Comprensión con un LLM vía cualquier API compatible con OpenAI (Groq, Gemini, OpenRouter...).

Decisión de diseño: el LLM SOLO interpreta (devuelve un JSON con intención y datos); nunca redacta lo
que se le dice al paciente. Las respuestas salen de plantillas revisadas, así no hay riesgo de que
invente horarios, diagnósticos o consejos médicos. Todo lo que devuelve se valida contra el catálogo.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time, timedelta

import httpx

from ..catalogo import especialidades
from ..config import config
from .tipos import INTENCIONES, Interpretacion

log = logging.getLogger(__name__)

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

PROMPT = """Eres el módulo de comprensión de Magnol-IA, un asistente por voz que ayuda a ADULTOS MAYORES
en Colombia (Medellín) a gestionar citas médicas. El texto viene de un reconocedor de voz: puede tener
errores, muletillas ("mija", "pues", "ve") y expresiones paisas. Tu ÚNICA tarea es devolver un JSON.

Hoy es {dia_semana} {hoy}. Contexto del diálogo: {contexto}.
{descripcion_contexto}

Intenciones posibles: {intenciones}
- agendar: quiere sacar una cita nueva (aunque sea para otra persona).
- consultar: quiere saber cuándo/dónde es su cita.
- cancelar: ya no va a ir / quiere anular la cita.
- reprogramar: quiere cambiar/mover/correr/aplazar una cita existente.
- informar: solo da un dato (especialidad, fecha o franja) que se le pidió.
- elegir_opcion: escoge una de las opciones ofrecidas (opcion = 1 o 2).
- otras_opciones: ninguna de las opciones le sirve o pide otra fecha/hora.
- afirmar / negar: responde sí o no.
- dar_documento: dice su número de cédula (devuélvelo solo con dígitos).
- urgencia: síntomas graves (dolor de pecho, no poder respirar, desmayo, ideas de hacerse daño).
- humano: quiere hablar con una persona.  - repetir: no entendió o pide repetir.
- ayuda, saludo, despedida, fuera_alcance (resultados, historia clínica, pagos, medicamentos), desconocido.

Especialidades (usa SOLO estos códigos o null): {especialidades}
"El de la presión", "control de la diabetes", "el doctor", "el médico" -> medicina_general.
"Los dientes", "la muela", "la plancha" -> odontologia. "Los ojos", "la vista" -> optometria.

Responde SOLO con este JSON (sin texto adicional):
{{"intencion": "...", "especialidad": null, "fecha": null, "asap": false, "franja": null,
  "hora": null, "opcion": null, "documento": null, "dia_semana": null}}
- fecha: "AAAA-MM-DD" desde la cual quiere la cita (p. ej. "la otra semana" = lunes siguiente), o null.
- asap: true si quiere "lo más pronto posible".  - franja: "manana", "tarde" o null.
- hora: "HH:MM" en 24 h si dijo una hora, o null.  - dia_semana: 0=lunes..6=domingo si elige "la del martes".
"""

DESCRIPCION_CONTEXTO = {
    "inicio": "El asistente acaba de preguntar en qué puede ayudar.",
    "esperando_especialidad": "El asistente preguntó con qué especialidad quiere la cita.",
    "esperando_fecha": "El asistente preguntó para cuándo quiere la cita.",
    "esperando_opcion": "El asistente ofreció dos citas (primera y segunda) y espera que elija.",
    "esperando_confirmacion": "El asistente pidió confirmar con sí o no.",
    "esperando_documento": "El asistente pidió el número de cédula.",
    "esperando_cita": "El asistente preguntó cuál de las citas existentes (primera o segunda).",
}


def _extraer_json(texto: str) -> dict | None:
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _validar(datos: dict, texto: str, hoy: date) -> Interpretacion:
    r = Interpretacion(texto=texto, fuente="llm", confianza=0.8)
    intencion = str(datos.get("intencion") or "desconocido")
    r.intencion = intencion if intencion in INTENCIONES else "desconocido"
    esp = datos.get("especialidad")
    r.especialidad = esp if esp in especialidades() else None
    try:
        f = date.fromisoformat(str(datos.get("fecha"))) if datos.get("fecha") else None
        r.fecha = f if f and hoy <= f <= hoy + timedelta(days=365) else None
    except ValueError:
        r.fecha = None
    r.asap = bool(datos.get("asap"))
    r.franja = datos.get("franja") if datos.get("franja") in ("manana", "tarde") else None
    try:
        r.hora = time.fromisoformat(str(datos.get("hora"))) if datos.get("hora") else None
    except ValueError:
        r.hora = None
    try:
        op = int(datos.get("opcion")) if datos.get("opcion") is not None else None
        r.opcion = op if op in (1, 2, 3) else None
    except (TypeError, ValueError):
        r.opcion = None
    doc = re.sub(r"\D", "", str(datos.get("documento") or ""))
    r.documento = doc if 5 <= len(doc) <= 11 else None
    try:
        ds = int(datos.get("dia_semana")) if datos.get("dia_semana") is not None else None
        r.dia_semana = ds if ds is not None and 0 <= ds <= 6 else None
    except (TypeError, ValueError):
        r.dia_semana = None
    return r


# Si el modelo configurado se retira (Groq retiró llama-3.3-70b-versatile en 2026), se prueban estos en orden
MODELOS_RESPALDO = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_modelo_activo: str | None = None


def _candidatos() -> list[str]:
    lista = [_modelo_activo] if _modelo_activo else []
    for m in [config.llm_modelo, *MODELOS_RESPALDO]:
        if m not in lista:
            lista.append(m)
    return lista


def _cuerpo(modelo: str, sistema: str, texto: str) -> dict:
    cuerpo = {
        "model": modelo,
        "temperature": 0,
        "max_tokens": 200,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
        "response_format": {"type": "json_object"},
    }
    if "gpt-oss" in modelo:  # modelos que razonan: poco razonamiento y espacio para él
        cuerpo["reasoning_effort"] = "low"
        cuerpo["max_tokens"] = 1024
    return cuerpo


def interpretar(texto: str, contexto: str, hoy: date | None = None) -> Interpretacion | None:
    """Devuelve None si no hay clave o la API falla (el sistema sigue con reglas)."""
    if not config.llm_activo:
        return None
    hoy = hoy or config.hoy()
    esp = ", ".join(f"{e.codigo} ({e.nombre}{'' if e.disponible else ', no disponible en la red'})"
                    for e in especialidades().values())
    sistema = PROMPT.format(
        dia_semana=DIAS_ES[hoy.weekday()], hoy=hoy.isoformat(), contexto=contexto,
        descripcion_contexto=DESCRIPCION_CONTEXTO.get(contexto, ""), intenciones=", ".join(INTENCIONES),
        especialidades=esp,
    )
    url = config.llm_base_url.rstrip("/") + "/chat/completions"
    cabeceras = {"Authorization": f"Bearer {config.llm_api_key}"}
    inicio = datetime.now()
    global _modelo_activo
    contenido = None
    try:
        with httpx.Client(timeout=config.llm_timeout) as cliente:
            for modelo in _candidatos():
                cuerpo = _cuerpo(modelo, sistema, texto)
                resp = cliente.post(url, json=cuerpo, headers=cabeceras)
                if resp.status_code == 400 and "response_format" in cuerpo:  # proveedor sin modo JSON
                    cuerpo.pop("response_format")
                    resp = cliente.post(url, json=cuerpo, headers=cabeceras)
                if resp.status_code == 404:  # modelo retirado: probar el siguiente
                    log.warning("El modelo %s ya no existe en el proveedor; se prueba otro", modelo)
                    continue
                resp.raise_for_status()
                if _modelo_activo != modelo:
                    log.info("LLM: usando el modelo %s", modelo)
                    _modelo_activo = modelo
                contenido = resp.json()["choices"][0]["message"]["content"]
                break
            else:
                raise RuntimeError("ninguno de los modelos configurados está disponible")
    except Exception as e:  # red caída, cuota agotada (429), clave inválida...
        log.warning("LLM no disponible (%s); se usan solo reglas", e)
        return None
    datos = _extraer_json(contenido or "")
    if not datos:
        log.warning("El LLM no devolvió JSON válido: %r", contenido)
        return None
    r = _validar(datos, texto, hoy)
    log.info("LLM %.0f ms -> %s", (datetime.now() - inicio).total_seconds() * 1000, r.intencion)
    return r
