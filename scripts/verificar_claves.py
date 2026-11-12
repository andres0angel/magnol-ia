"""Comprueba que las claves funcionan de verdad: token de Telegram, LLM de Groq y voz a texto.

    python scripts/verificar_claves.py

Le manda al LLM frases en lenguaje natural que las reglas solas no entienden, y muestra quién las
interpretó: "reglas", "hibrido" (el LLM ayudó) o el error si la clave no sirve.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import httpx  # noqa: E402

from magnolia.config import config  # noqa: E402
from magnolia.nlu import hibrido, llm, reglas  # noqa: E402

FRASES = [
    "buenas tardes, quisiera mirar qué tengo programado con ustedes",
    "mija, a mi mamá le está doliendo mucho la rodilla y quisiera que la viera alguien el martes temprano",
    "ya no voy a poder ir a lo del dentista, me sale un viaje",
]


def main() -> None:
    print("1. Telegram")
    if not config.telegram_token:
        print("   — sin TELEGRAM_TOKEN")
    else:
        try:
            r = httpx.get(f"https://api.telegram.org/bot{config.telegram_token}/getMe", timeout=15).json()
            print(f"   ✅ token válido: @{r['result']['username']}" if r.get("ok") else f"   ❌ token rechazado: {r}")
        except Exception as e:
            print(f"   ❌ no se pudo verificar: {e}")

    print("\n2. LLM (Groq)")
    if not config.llm_activo:
        print("   — sin LLM_API_KEY: el bot solo entiende con reglas")
    else:
        print(f"   modelo: {config.llm_modelo}")
        for frase in FRASES:
            regla = reglas.interpretar(frase, "inicio", config.hoy())
            directo = llm.interpretar(frase, "inicio", config.hoy())
            final = hibrido.interpretar(frase, "inicio", config.hoy())
            if directo is None:
                print(f"   ❌ el LLM no respondió (clave inválida, sin internet o sin cuota). Frase: {frase!r}")
                continue
            extra = ", ".join(f"{c}={getattr(final, c)}" for c in ("especialidad", "dia_semana", "franja", "fecha")
                              if getattr(final, c))
            print(f"   «{frase}»\n      reglas solas: {regla.intencion} → bot: {final.intencion} ({final.fuente})"
                  + (f", {extra}" if extra else ""))

    print("\n3. Voz a texto")
    from magnolia.voz.stt import Transcriptor

    print(f"   modo: {Transcriptor().modo}  (api = notas de voz con Whisper en Groq; ninguno = no entiende audios)")


if __name__ == "__main__":
    main()
