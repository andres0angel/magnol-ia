"""Canal Telegram: 100 % gratuito, acepta notas de voz y funciona sin servidor público (long polling).

    python -m magnolia.canales.telegram_bot

Requiere TELEGRAM_TOKEN en .env (se obtiene gratis hablando con @BotFather en Telegram).
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ..config import config
from ..dialogo import GestorDialogo, Respuesta
from ..voz.stt import Transcriptor
from ..voz.tts import Sintetizador

log = logging.getLogger("magnolia.telegram")
CANAL = "telegram"


class BotTelegram:
    def __init__(self):
        self.gestor = GestorDialogo()
        self.stt = Transcriptor()
        self.tts = Sintetizador()
        self._bloqueo = asyncio.Lock()  # SQLite + sesiones en memoria: un turno a la vez es suficiente para el MVP

    @staticmethod
    def _teclado(botones: list[str]):
        if not botones:
            return ReplyKeyboardRemove()
        filas = [[KeyboardButton(b)] for b in botones]  # un botón por fila: grandes y fáciles de tocar
        return ReplyKeyboardMarkup(filas, resize_keyboard=True, one_time_keyboard=True)

    async def _responder(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE, texto_usuario: str, es_voz: bool) -> None:
        chat_id = update.effective_chat.id
        usuario = str(update.effective_user.id)
        async with self._bloqueo:
            resp: Respuesta = await asyncio.to_thread(self.gestor.procesar, CANAL, usuario, texto_usuario, es_voz)
        await ctx.bot.send_message(chat_id, resp.texto, reply_markup=self._teclado(resp.botones))
        enviar_voz = config.responder_voz == "siempre" or (config.responder_voz == "espejo" and es_voz)
        if enviar_voz and self.tts.disponible:
            await ctx.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
            audio = await self.tts.sintetizar(resp.texto)
            if audio:
                try:
                    with open(audio, "rb") as f:
                        await ctx.bot.send_voice(chat_id, voice=f)
                finally:
                    Path(audio).unlink(missing_ok=True)

    async def inicio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self.gestor.reiniciar(CANAL, str(update.effective_user.id))
        await self._responder(update, ctx, "hola", es_voz=False)

    async def olvidar(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self.gestor.reiniciar(CANAL, str(update.effective_user.id), olvidar_paciente=True)
        await update.message.reply_text("Listo, olvidé con qué cédula estaba hablando. Escriba o diga hola para empezar.",
                                        reply_markup=ReplyKeyboardRemove())

    async def ayuda(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._responder(update, ctx, "ayuda", es_voz=False)

    async def texto(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._responder(update, ctx, update.message.text, es_voz=False)

    async def voz(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if not self.stt.disponible:
            await update.message.reply_text("Por ahora no puedo escuchar audios. ¿Me lo puede escribir?")
            return
        await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
        archivo = await (update.message.voice or update.message.audio).get_file()
        ruta = Path(tempfile.mkstemp(suffix=".ogg", prefix="tg_")[1])
        try:
            await archivo.download_to_drive(ruta)
            texto = await asyncio.to_thread(self.stt.transcribir, ruta)
        finally:
            ruta.unlink(missing_ok=True)
        if not texto:
            await update.message.reply_text("No le alcancé a entender el audio. ¿Me lo repite un poquito más despacio?")
            return
        if config.mostrar_transcripcion:
            await update.message.reply_text(f"🗣️ Le entendí: «{texto}»")
        await self._responder(update, ctx, texto, es_voz=True)

    def ejecutar(self) -> None:
        if not config.telegram_token:
            raise SystemExit("Falta TELEGRAM_TOKEN en el archivo .env (créelo con @BotFather en Telegram).")
        app = Application.builder().token(config.telegram_token).build()
        app.add_handler(CommandHandler("start", self.inicio))
        app.add_handler(CommandHandler("ayuda", self.ayuda))
        app.add_handler(CommandHandler("olvidar", self.olvidar))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.voz))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.texto))
        log.info("Magnol-IA en Telegram | voz a texto: %s | texto a voz: %s | LLM: %s",
                 self.stt.modo, self.tts.modo, "sí" if config.llm_activo else "no (solo reglas)")
        print("Bot de Telegram corriendo. Ctrl+C para detener.")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    BotTelegram().ejecutar()


if __name__ == "__main__":
    main()
