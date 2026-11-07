"""Conversar con Magnol-IA dentro de un cuaderno (Google Colab o Jupyter), con la respuesta también en audio.

    from magnolia.canales.cuaderno import chatear
    chatear()                 # escriba "salir" para terminar, "reiniciar" para empezar de nuevo
    chatear(voz=False)        # solo texto

Sirve para probar el diálogo sin Telegram. Para probar notas de voz de verdad, use el bot de Telegram.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import textwrap

CANAL = "cuaderno"


def _audio(texto: str):
    """Genera el audio de la respuesta (MP3, que todos los navegadores reproducen) o None."""
    from ..voz.tts import Sintetizador

    tts = Sintetizador()
    if not tts.disponible:
        return None
    # Los cuadernos ya tienen un ciclo asyncio corriendo: el audio se genera en otro hilo
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as hilo:
        return hilo.submit(asyncio.run, tts.sintetizar(texto, formato="mp3")).result()


def chatear(voz: bool = True, usuario: str = "cuaderno-1") -> None:
    from ..config import config
    from ..dialogo import GestorDialogo

    try:
        from IPython.display import Audio, display
    except ImportError:  # fuera de un cuaderno: solo texto
        voz, display, Audio = False, None, None

    gestor = GestorDialogo()
    print(f"Magnol-IA — fecha: {config.ahora():%Y-%m-%d %H:%M} — comprensión: "
          f"{'reglas + LLM' if config.llm_activo else 'solo reglas'} — escriba 'salir' para terminar\n")
    while True:
        try:
            texto = input("Usted: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto.lower() in {"salir", "/salir"}:
            break
        if texto.lower() in {"reiniciar", "/reiniciar"}:
            gestor.reiniciar(CANAL, usuario, olvidar_paciente=True)
            print("(conversación reiniciada)\n")
            continue
        r = gestor.procesar(CANAL, usuario, texto)
        print("\n".join(textwrap.wrap("Magnol-IA: " + r.texto, 100, subsequent_indent="           ")))
        if r.botones:
            print("           [" + "] [".join(r.botones) + "]")
        if voz:
            ruta = _audio(r.texto)
            if ruta:
                display(Audio(filename=str(ruta)))
        print()
