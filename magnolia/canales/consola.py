"""Simulador de conversación en la terminal (sin Telegram ni WhatsApp).

    python -m magnolia.canales.consola
    python -m magnolia.canales.consola --fecha 2026-11-12T09:00     # simular otra fecha
    python -m magnolia.canales.consola --guion "hola" "43527891" "sí" "quiero una cita con el médico"

Escriba /voz ruta.ogg para probar el reconocimiento de voz con un audio, /reiniciar o /salir.
"""
from __future__ import annotations

import argparse
import logging
import textwrap

from ..config import config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", help="fecha/hora simulada AAAA-MM-DDTHH:MM")
    ap.add_argument("--usuario", default="consola-1")
    ap.add_argument("--guion", nargs="*", help="mensajes a enviar en orden (modo no interactivo)")
    ap.add_argument("--depurar", action="store_true", help="mostrar intención detectada")
    args = ap.parse_args()
    if args.fecha:
        config.fecha_simulada = args.fecha
    logging.basicConfig(level=logging.INFO if args.depurar else logging.WARNING)

    from ..dialogo import GestorDialogo
    gestor = GestorDialogo()

    def turno(texto: str, es_voz: bool = False) -> None:
        r = gestor.procesar("consola", args.usuario, texto, es_voz=es_voz)
        if args.depurar:
            ev = gestor.con.execute("SELECT intencion, fuente_nlu FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
            print(f"   [intención: {ev['intencion']} | {ev['fuente_nlu']}]")
        print("\n".join(textwrap.wrap("Magnol-IA: " + r.texto, 100, subsequent_indent="           ")))
        if r.botones:
            print("           [" + "] [".join(r.botones) + "]")
        print()

    print(f"Magnol-IA (consola) — fecha: {config.ahora():%Y-%m-%d %H:%M} — LLM: {'activo' if config.llm_activo else 'apagado (solo reglas)'}\n")
    if args.guion:
        for msg in args.guion:
            print(f"Usted: {msg}")
            turno(msg)
        return
    while True:
        try:
            texto = input("Usted: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto == "/salir":
            break
        if texto == "/reiniciar":
            gestor.reiniciar("consola", args.usuario, olvidar_paciente=True)
            print("(conversación reiniciada)\n")
            continue
        if texto.startswith("/voz "):
            from ..voz.stt import Transcriptor
            transcrito = Transcriptor().transcribir(texto[5:].strip())
            print(f"   (le entendí: «{transcrito}»)")
            if transcrito:
                turno(transcrito, es_voz=True)
            continue
        turno(texto)


if __name__ == "__main__":
    main()
