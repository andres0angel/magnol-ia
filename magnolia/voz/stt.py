"""Voz a texto. Tres caminos, todos gratuitos:

1. API Whisper compatible con OpenAI (por defecto Groq: whisper-large-v3-turbo, plan gratuito sin tarjeta).
2. faster-whisper en el propio computador (sin internet, sin cuenta; más lento en CPU).
3. Ninguno: el bot pide que escriban.

Se le pasa a Whisper un "prompt" con vocabulario del dominio (especialidades, sedes, "cédula") para
que reconozca mejor palabras como "odontología" o "Belén Rincón" dichas por personas mayores.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..config import config

log = logging.getLogger(__name__)

VOCABULARIO = ("Cita médica, cédula, medicina general, odontología, medicina interna, optometría, nutricionista, "
               "psicóloga, ginecología, Metrosalud, Belén, Manrique, Castilla, Santa Cruz, Buenos Aires, San Javier. "
               "Sí señora, no señor, mija, la primera, la segunda, la otra semana, por la mañana, en la tarde.")


class Transcriptor:
    def __init__(self):
        modo = config.stt_modo
        if modo == "auto":
            if config.stt_api_key:
                modo = "api"
            else:
                try:
                    import faster_whisper  # noqa: F401
                    modo = "local"
                except ImportError:
                    modo = "ninguno"
        self.modo = modo
        self._modelo_local = None
        log.info("Voz a texto: %s", self.modo)

    @property
    def disponible(self) -> bool:
        return self.modo in ("api", "local")

    def transcribir(self, ruta: str | Path) -> str | None:
        ruta = Path(ruta)
        try:
            if self.modo == "api":
                return self._api(ruta)
            if self.modo == "local":
                return self._local(ruta)
        except Exception as e:
            log.warning("No se pudo transcribir %s: %s", ruta.name, e)
            if self.modo == "api":  # si la API falla (sin internet, cuota), intentar local
                try:
                    return self._local(ruta)
                except Exception:
                    return None
        return None

    def _api(self, ruta: Path) -> str | None:
        url = config.stt_base_url.rstrip("/") + "/audio/transcriptions"
        with open(ruta, "rb") as f, httpx.Client(timeout=30) as cliente:
            resp = cliente.post(
                url, headers={"Authorization": f"Bearer {config.stt_api_key}"},
                files={"file": (ruta.name, f, "audio/ogg")},
                data={"model": config.stt_modelo, "language": "es", "prompt": VOCABULARIO,
                      "response_format": "json", "temperature": "0"})
            resp.raise_for_status()
            return (resp.json().get("text") or "").strip() or None

    def _local(self, ruta: Path) -> str | None:
        if self._modelo_local is None:
            from faster_whisper import WhisperModel  # descarga el modelo la primera vez (~460 MB el "small")
            self._modelo_local = WhisperModel(config.stt_modelo_local, device="cpu", compute_type="int8")
        segmentos, _ = self._modelo_local.transcribe(str(ruta), language="es", initial_prompt=VOCABULARIO,
                                                     vad_filter=True, beam_size=5)
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        return texto or None
