"""Configuración leída de variables de entorno (archivo .env en la raíz del proyecto)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent

try:  # python-dotenv es opcional
    from dotenv import dotenv_values, load_dotenv

    _ARCHIVO_ENV = RAIZ / ".env"
    load_dotenv(_ARCHIVO_ENV)  # las variables del sistema ganan sobre el archivo...
    # ...salvo que estén vacías: en Colab, una celda ejecutada antes de poner las claves deja TELEGRAM_TOKEN=""
    # en el entorno, y los programas que se lanzan después lo heredan y ocultarían el token del archivo.
    for _clave, _valor in dotenv_values(_ARCHIVO_ENV).items():
        if _valor and not os.environ.get(_clave, "").strip():
            os.environ[_clave] = _valor
except ImportError:  # pragma: no cover
    pass


def _env(nombre: str, defecto: str = "") -> str:
    return os.environ.get(nombre, defecto).strip()


def _bool(nombre: str, defecto: bool) -> bool:
    valor = _env(nombre)
    if not valor:
        return defecto
    return valor.lower() in {"1", "true", "si", "sí", "yes", "on"}


@dataclass
class Config:
    ips_nombre: str = field(default_factory=lambda: _env("IPS_NOMBRE", "la IPS piloto"))
    modo_demo: bool = field(default_factory=lambda: _bool("MODO_DEMO", True))
    linea_atencion: str = field(default_factory=lambda: _env("LINEA_ATENCION", ""))
    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", str(RAIZ / "datos" / "magnolia.db"))))
    zona: ZoneInfo = field(default_factory=lambda: ZoneInfo(_env("ZONA_HORARIA", "America/Bogota")))
    fecha_simulada: str = field(default_factory=lambda: _env("FECHA_SIMULADA"))  # AAAA-MM-DD o AAAA-MM-DDTHH:MM
    minutos_sesion: int = field(default_factory=lambda: int(_env("MINUTOS_SESION", "30")))
    # Verificación de identidad: con True pide el año de nacimiento en vez de mostrar el nombre (más privado)
    verificar_nacimiento: bool = field(default_factory=lambda: _bool("VERIFICAR_NACIMIENTO", False))

    # Comprensión con LLM (opcional). Cualquier API compatible con OpenAI: Groq, Gemini, OpenRouter...
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "https://api.groq.com/openai/v1"))
    llm_modelo: str = field(default_factory=lambda: _env("LLM_MODELO", "llama-3.3-70b-versatile"))
    llm_timeout: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT", "8")))

    # Voz a texto
    stt_modo: str = field(default_factory=lambda: _env("STT_MODO", "auto"))  # auto | api | local | ninguno
    stt_api_key: str = field(default_factory=lambda: _env("STT_API_KEY") or _env("LLM_API_KEY"))
    stt_base_url: str = field(default_factory=lambda: _env("STT_BASE_URL", "https://api.groq.com/openai/v1"))
    stt_modelo: str = field(default_factory=lambda: _env("STT_MODELO", "whisper-large-v3-turbo"))
    stt_modelo_local: str = field(default_factory=lambda: _env("STT_MODELO_LOCAL", "small"))

    # Texto a voz
    tts_modo: str = field(default_factory=lambda: _env("TTS_MODO", "edge"))  # edge | gtts | ninguno
    tts_voz: str = field(default_factory=lambda: _env("TTS_VOZ", "es-CO-SalomeNeural"))
    tts_velocidad: str = field(default_factory=lambda: _env("TTS_VELOCIDAD", "-10%"))
    responder_voz: str = field(default_factory=lambda: _env("RESPONDER_VOZ", "espejo"))  # siempre | espejo | nunca
    mostrar_transcripcion: bool = field(default_factory=lambda: _bool("MOSTRAR_TRANSCRIPCION", True))

    # Canales
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_TOKEN"))
    whatsapp_token: str = field(default_factory=lambda: _env("WHATSAPP_TOKEN"))
    whatsapp_phone_id: str = field(default_factory=lambda: _env("WHATSAPP_PHONE_ID"))
    whatsapp_verify_token: str = field(default_factory=lambda: _env("WHATSAPP_VERIFY_TOKEN", "magnolia-verifica"))
    whatsapp_app_secret: str = field(default_factory=lambda: _env("WHATSAPP_APP_SECRET"))
    whatsapp_api_version: str = field(default_factory=lambda: _env("WHATSAPP_API_VERSION", "v21.0"))

    def ahora(self) -> datetime:
        if self.fecha_simulada:
            texto = self.fecha_simulada
            if "T" not in texto:
                texto += "T07:00"
            return datetime.fromisoformat(texto).replace(tzinfo=self.zona)
        return datetime.now(self.zona)

    def hoy(self) -> date:
        return self.ahora().date()

    @property
    def llm_activo(self) -> bool:
        return bool(self.llm_api_key)


config = Config()
