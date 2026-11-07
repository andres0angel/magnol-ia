import hashlib
import hmac
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from magnolia.canales import whatsapp
from magnolia.config import config
from magnolia.dialogo import Respuesta

PAYLOAD_AUDIO = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
    "messaging_product": "whatsapp", "messages": [
        {"from": "573001234567", "id": "wamid.A1", "type": "audio", "audio": {"id": "media123", "mime_type": "audio/ogg; codecs=opus"}},
        {"from": "573001234567", "id": "wamid.A2", "type": "text", "text": {"body": "quiero una cita"}},
        {"from": "573001234567", "id": "wamid.A3", "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "b0", "title": "Sí"}}},
    ]}}]}]}


def test_extraer_mensajes():
    m = whatsapp.extraer_mensajes(PAYLOAD_AUDIO)
    assert [x["tipo"] for x in m] == ["audio", "text", "interactive"]
    assert m[0]["audio_id"] == "media123" and m[1]["texto"] == "quiero una cita" and m[2]["texto"] == "Sí"


def test_verificacion_webhook(monkeypatch):
    monkeypatch.setattr(config, "whatsapp_verify_token", "secreto")
    c = TestClient(whatsapp.app)
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "secreto", "hub.challenge": "42"}).text == "42"
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "malo", "hub.challenge": "42"}).status_code == 403


def test_firma_y_deduplicacion(monkeypatch):
    import json
    monkeypatch.setattr(config, "whatsapp_app_secret", "s3cr3t")
    procesados = []

    async def falso(msg):
        procesados.append(msg["id"])
    monkeypatch.setattr(whatsapp, "procesar_mensaje", falso)
    whatsapp._vistos.clear()
    cuerpo = json.dumps(PAYLOAD_AUDIO).encode()
    firma = "sha256=" + hmac.new(b"s3cr3t", cuerpo, hashlib.sha256).hexdigest()
    c = TestClient(whatsapp.app)
    assert c.post("/webhook", content=cuerpo, headers={"x-hub-signature-256": "sha256=mala", "content-type": "application/json"}).status_code == 401
    assert c.post("/webhook", content=cuerpo, headers={"x-hub-signature-256": firma, "content-type": "application/json"}).status_code == 200
    c.post("/webhook", content=cuerpo, headers={"x-hub-signature-256": firma, "content-type": "application/json"})  # reintento de Meta
    assert procesados == ["wamid.A1", "wamid.A2", "wamid.A3"]


def test_botones_whatsapp():
    cuerpo = whatsapp.cuerpo_respuesta("57300", Respuesta("¿Se la agendo?", ["Sí", "No"]))
    assert cuerpo["type"] == "interactive" and len(cuerpo["interactive"]["action"]["buttons"]) == 2
    assert whatsapp.cuerpo_respuesta("57300", Respuesta("Hola"))["type"] == "text"


def test_teclado_telegram():
    from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

    from magnolia.canales.telegram_bot import BotTelegram
    assert isinstance(BotTelegram._teclado(["Sí", "No"]), ReplyKeyboardMarkup)
    assert isinstance(BotTelegram._teclado([]), ReplyKeyboardRemove)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="requiere ffmpeg")
def test_conversion_a_nota_de_voz(tmp_path):
    from magnolia.voz.tts import Sintetizador
    mp3 = tmp_path / "tono.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(mp3)], check=True)
    ogg = Sintetizador()._a_ogg(mp3)
    assert ogg.suffix == ".ogg" and ogg.stat().st_size > 0
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(ogg)],
                          capture_output=True, text=True).stdout.strip()
    assert info == "opus"


def test_textos_hablados():
    from datetime import date, datetime

    from magnolia.textos import direccion_hablada, fecha_hablada, hora_hablada
    assert direccion_hablada("CL 2B # 79 - 100") == "Calle 2B número 79 - 100"
    assert direccion_hablada("KR 51 A # 100 - 80") == "Carrera 51 A número 100 - 80"
    assert hora_hablada(datetime(2026, 1, 1, 14, 20)) == "a las 2 y 20 de la tarde"
    assert hora_hablada(datetime(2026, 1, 1, 13, 0)) == "a la 1 de la tarde"
    assert fecha_hablada(date(2026, 11, 13), date(2026, 11, 12)) == "mañana viernes 13 de noviembre"
