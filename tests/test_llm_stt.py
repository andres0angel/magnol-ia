"""Prueba el camino del LLM y de la voz a texto con una API falsa (compatible con OpenAI)."""
import json
from datetime import date

import httpx
import pytest

from magnolia.config import config
from magnolia.nlu import hibrido, llm

HOY = date(2026, 11, 12)
_ClienteReal = httpx.Client


def api_falsa(monkeypatch, manejador):
    transporte = httpx.MockTransport(manejador)
    monkeypatch.setattr(httpx, "Client", lambda **kw: _ClienteReal(transport=transporte, **kw))
    monkeypatch.setattr(config, "llm_api_key", "clave-de-prueba")


def respuesta_chat(datos):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(datos)}}]})


def test_reglas_seguras_no_llaman_al_llm(monkeypatch):
    llamadas = []
    api_falsa(monkeypatch, lambda req: llamadas.append(req) or respuesta_chat({"intencion": "agendar"}))
    r = hibrido.interpretar("quiero una cita con el odontólogo", "inicio", HOY)
    assert r.fuente == "reglas" and r.especialidad == "odontologia" and not llamadas


def test_llm_resuelve_lo_que_las_reglas_no_entienden(monkeypatch):
    def manejador(req):
        cuerpo = json.loads(req.content)
        assert req.url.path.endswith("/chat/completions")
        assert cuerpo["temperature"] == 0 and cuerpo["response_format"] == {"type": "json_object"}
        assert "jueves 2026-11-12" in cuerpo["messages"][0]["content"]
        return respuesta_chat({"intencion": "consultar", "especialidad": None, "fecha": None})
    api_falsa(monkeypatch, manejador)
    r = hibrido.interpretar("ando perdida, no sé qué día me toca ir", "inicio", HOY)
    assert r.intencion == "consultar" and r.fuente == "hibrido"


def test_salida_del_llm_se_valida(monkeypatch):
    api_falsa(monkeypatch, lambda req: respuesta_chat({
        "intencion": "agendar", "especialidad": "neurocirugia_cuantica", "fecha": "2020-01-01",
        "franja": "noche", "opcion": 9, "documento": "abc"}))
    r = llm.interpretar("algo raro", "inicio", HOY)
    assert r.intencion == "agendar"
    assert r.especialidad is None and r.fecha is None and r.franja is None and r.opcion is None and r.documento is None


def test_proveedor_sin_response_format(monkeypatch):
    intentos = []

    def manejador(req):
        cuerpo = json.loads(req.content)
        intentos.append("response_format" in cuerpo)
        if "response_format" in cuerpo:
            return httpx.Response(400, json={"error": "no soportado"})
        return respuesta_chat({"intencion": "cancelar"})
    api_falsa(monkeypatch, manejador)
    assert llm.interpretar("ya no voy pues", "inicio", HOY).intencion == "cancelar"
    assert intentos == [True, False]


@pytest.mark.parametrize("fallo", [lambda req: httpx.Response(429, json={"error": "cuota"}),
                                   lambda req: (_ for _ in ()).throw(httpx.ConnectError("sin internet"))])
def test_si_el_llm_falla_siguen_las_reglas(monkeypatch, fallo):
    api_falsa(monkeypatch, fallo)
    r = hibrido.interpretar("ando perdida, no sé qué día me toca ir", "inicio", HOY)
    assert r.fuente == "reglas"


def test_voz_a_texto_por_api(monkeypatch, tmp_path):
    from magnolia.voz.stt import Transcriptor

    def manejador(req):
        assert req.url.path.endswith("/audio/transcriptions")
        cuerpo = req.content.decode(errors="ignore")
        assert 'name="language"' in cuerpo and "whisper-large-v3-turbo" in cuerpo and "odontolog" in cuerpo
        return httpx.Response(200, json={"text": " Quiero una cita con el médico. "})
    api_falsa(monkeypatch, manejador)
    monkeypatch.setattr(config, "stt_api_key", "clave")
    monkeypatch.setattr(config, "stt_modo", "api")
    audio = tmp_path / "nota.ogg"
    audio.write_bytes(b"OggS-falso")
    assert Transcriptor().transcribir(audio) == "Quiero una cita con el médico."


def test_saludo_largo_se_le_pasa_al_llm(monkeypatch):
    from datetime import date

    from magnolia.nlu import hibrido, llm
    from magnolia.nlu.tipos import Interpretacion

    llamadas = []

    def falso(texto, contexto, hoy):
        llamadas.append(texto)
        return Interpretacion(intencion="consultar", confianza=0.9, fuente="llm")

    monkeypatch.setattr(llm, "interpretar", falso)
    r = hibrido.interpretar("buenas tardes, quisiera mirar qué tengo programado", "inicio", date(2026, 11, 12))
    assert r.intencion == "consultar" and llamadas
    llamadas.clear()
    assert hibrido.interpretar("buenas tardes", "inicio", date(2026, 11, 12)).intencion == "saludo"
    assert not llamadas  # un saludo corto no gasta una llamada al LLM
