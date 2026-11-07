"""Texto a voz gratuito, con voz colombiana y un poco más lenta (más fácil de seguir para adultos mayores).

- edge-tts: voces neuronales de Microsoft Edge, incluye es-CO-SalomeNeural y es-CO-GonzaloNeural. Gratis, sin cuenta.
- gTTS: respaldo (voz de Google Translate).
La salida se convierte a OGG/Opus con ffmpeg, que es el formato de "nota de voz" de Telegram y WhatsApp.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import config
from ..textos import para_voz

log = logging.getLogger(__name__)


class Sintetizador:
    def __init__(self):
        self.modo = config.tts_modo
        self.ffmpeg = shutil.which("ffmpeg")
        if not self.ffmpeg:
            log.warning("No se encontró ffmpeg: las respuestas de voz se enviarán como MP3")

    @property
    def disponible(self) -> bool:
        return self.modo in ("edge", "gtts")

    async def sintetizar(self, texto: str, formato: str = "ogg") -> Path | None:
        """Devuelve la ruta de un .ogg (o .mp3 si no hay ffmpeg o si formato='mp3'), o None si no se pudo."""
        if not self.disponible:
            return None
        texto = para_voz(texto)
        mp3 = Path(tempfile.mkstemp(suffix=".mp3", prefix="magnolia_")[1])
        try:
            if self.modo == "edge":
                try:
                    await self._edge(texto, mp3)
                except Exception as e:
                    log.warning("edge-tts falló (%s); uso gTTS", e)
                    await asyncio.to_thread(self._gtts, texto, mp3)
            else:
                await asyncio.to_thread(self._gtts, texto, mp3)
        except Exception as e:
            log.warning("No se pudo generar el audio: %s", e)
            mp3.unlink(missing_ok=True)
            return None
        if formato == "mp3":
            return mp3
        return await asyncio.to_thread(self._a_ogg, mp3)

    async def _edge(self, texto: str, destino: Path) -> None:
        import edge_tts

        await edge_tts.Communicate(texto, config.tts_voz, rate=config.tts_velocidad).save(str(destino))

    @staticmethod
    def _gtts(texto: str, destino: Path) -> None:
        from gtts import gTTS

        gTTS(texto, lang="es", tld="com.mx", slow=False).save(str(destino))

    def _a_ogg(self, mp3: Path) -> Path:
        if not self.ffmpeg:
            return mp3
        ogg = mp3.with_suffix(".ogg")
        r = subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "48000",
                            "-c:a", "libopus", "-b:a", "32k", "-application", "voip", str(ogg)], capture_output=True)
        if r.returncode != 0:
            log.warning("ffmpeg no pudo convertir a OGG: %s", r.stderr.decode(errors="ignore")[:200])
            return mp3
        mp3.unlink(missing_ok=True)
        return ogg
