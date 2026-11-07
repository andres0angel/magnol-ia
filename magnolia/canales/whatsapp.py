"""Canal WhatsApp (Meta Cloud API), listo para cuando la IPS cliente asuma el costo del canal.

Desde el 1 de octubre de 2026 Meta cobra las respuestas del negocio (mensajes de servicio) y exige un
método de pago; por eso el MVP gratuito corre en Telegram. Este adaptador usa el mismo núcleo y se
probó con mensajes simulados de Meta.

    uvicorn magnolia.canales.whatsapp:app --port 8000
    cloudflared tunnel --url http://localhost:8000     # URL pública https gratis para el webhook
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import tempfile
from collections import OrderedDict
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ..config import config
from ..dialogo import GestorDialogo, Respuesta

log = logging.getLogger("magnolia.whatsapp")
CANAL = "whatsapp"
app = FastAPI(title="Magnol-IA WhatsApp")
_estado: dict = {}
_vistos: OrderedDict[str, None] = OrderedDict()  # Meta reintenta los webhooks: evitar procesar dos veces
_bloqueo = asyncio.Lock()


def _gestor() -> GestorDialogo:
    if "gestor" not in _estado:
        from ..voz.stt import Transcriptor
        from ..voz.tts import Sintetizador
        _estado.update(gestor=GestorDialogo(), stt=Transcriptor(), tts=Sintetizador())
    return _estado["gestor"]


def _graph(ruta: str) -> str:
    return f"https://graph.facebook.com/{config.whatsapp_api_version}/{ruta.lstrip('/')}"


def _auth() -> dict:
    return {"Authorization": f"Bearer {config.whatsapp_token}"}


@app.get("/webhook")
async def verificar(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == config.whatsapp_verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="token de verificación inválido")


def firma_valida(cuerpo: bytes, firma: str | None) -> bool:
    if not config.whatsapp_app_secret:
        return True  # en desarrollo se puede omitir; en producción configure WHATSAPP_APP_SECRET
    if not firma or not firma.startswith("sha256="):
        return False
    esperada = hmac.new(config.whatsapp_app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma[7:])


def extraer_mensajes(payload: dict) -> list[dict]:
    """Convierte el JSON de Meta en una lista simple: {id, de, tipo, texto|audio_id}."""
    salida = []
    for entrada in payload.get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value", {})
            for m in valor.get("messages", []) or []:
                item = {"id": m.get("id"), "de": m.get("from"), "tipo": m.get("type")}
                if m.get("type") == "text":
                    item["texto"] = m["text"]["body"]
                elif m.get("type") == "audio":
                    item["audio_id"] = m["audio"]["id"]
                elif m.get("type") == "interactive":
                    inter = m["interactive"]
                    respuesta = inter.get("button_reply") or inter.get("list_reply") or {}
                    item["texto"] = respuesta.get("title", "")
                elif m.get("type") == "button":
                    item["texto"] = m["button"].get("text", "")
                else:
                    continue
                salida.append(item)
    return salida


@app.post("/webhook")
async def recibir(request: Request, tareas: BackgroundTasks):
    cuerpo = await request.body()
    if not firma_valida(cuerpo, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="firma inválida")
    for msg in extraer_mensajes(await request.json()):
        if msg["id"] in _vistos:
            continue
        _vistos[msg["id"]] = None
        while len(_vistos) > 1000:
            _vistos.popitem(last=False)
        tareas.add_task(procesar_mensaje, msg)  # responder 200 rápido; Meta exige < 10 s
    return {"ok": True}


async def procesar_mensaje(msg: dict) -> None:
    gestor = _gestor()
    stt, tts = _estado["stt"], _estado["tts"]
    es_voz = msg["tipo"] == "audio"
    texto = msg.get("texto")
    if es_voz:
        ruta = await descargar_audio(msg["audio_id"])
        texto = await asyncio.to_thread(stt.transcribir, ruta) if ruta else None
        if ruta:
            Path(ruta).unlink(missing_ok=True)
        if not texto:
            await enviar_texto(msg["de"], "No le alcancé a entender el audio. ¿Me lo repite un poquito más despacio?")
            return
    async with _bloqueo:
        resp: Respuesta = await asyncio.to_thread(gestor.procesar, CANAL, msg["de"], texto, es_voz)
    await enviar_respuesta(msg["de"], resp)
    if config.responder_voz == "siempre" or (config.responder_voz == "espejo" and es_voz):
        audio = await tts.sintetizar(resp.texto)
        if audio:
            await enviar_audio(msg["de"], audio)
            Path(audio).unlink(missing_ok=True)


async def descargar_audio(media_id: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            meta = (await c.get(_graph(media_id), headers=_auth())).json()
            datos = await c.get(meta["url"], headers=_auth())
            datos.raise_for_status()
        ruta = tempfile.mkstemp(suffix=".ogg", prefix="wa_")[1]
        Path(ruta).write_bytes(datos.content)
        return ruta
    except Exception as e:
        log.warning("No se pudo descargar el audio %s: %s", media_id, e)
        return None


async def _enviar(cuerpo: dict) -> None:
    cuerpo = {"messaging_product": "whatsapp", **cuerpo}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(_graph(f"{config.whatsapp_phone_id}/messages"), headers=_auth(), json=cuerpo)
        if r.status_code >= 400:
            log.warning("WhatsApp respondió %s: %s", r.status_code, r.text[:300])


async def enviar_texto(para: str, texto: str) -> None:
    await _enviar({"to": para, "type": "text", "text": {"body": texto}})


def cuerpo_respuesta(para: str, resp: Respuesta) -> dict:
    """Si hay hasta 3 opciones, se envían como botones (máx. 20 caracteres cada uno, regla de Meta)."""
    if resp.botones and len(resp.botones) <= 3 and len(resp.texto) <= 1024:
        botones = [{"type": "reply", "reply": {"id": f"b{n}", "title": b[:20]}} for n, b in enumerate(resp.botones)]
        return {"to": para, "type": "interactive",
                "interactive": {"type": "button", "body": {"text": resp.texto}, "action": {"buttons": botones}}}
    return {"to": para, "type": "text", "text": {"body": resp.texto}}


async def enviar_respuesta(para: str, resp: Respuesta) -> None:
    await _enviar(cuerpo_respuesta(para, resp))


async def enviar_audio(para: str, ruta: Path) -> None:
    tipo = "audio/ogg" if str(ruta).endswith(".ogg") else "audio/mpeg"
    async with httpx.AsyncClient(timeout=30) as c:
        with open(ruta, "rb") as f:
            r = await c.post(_graph(f"{config.whatsapp_phone_id}/media"), headers=_auth(),
                             data={"messaging_product": "whatsapp", "type": tipo}, files={"file": (Path(ruta).name, f, tipo)})
        if r.status_code >= 400:
            log.warning("No se pudo subir el audio: %s", r.text[:300])
            return
    await _enviar({"to": para, "type": "audio", "audio": {"id": r.json()["id"]}})
