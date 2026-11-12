import csv
from datetime import date
from pathlib import Path

from magnolia.catalogo import buscar_especialidad
from magnolia.nlu import reglas
from magnolia.nlu.normalizar import normalizar

RUTA = Path(__file__).resolve().parent.parent / "datos" / "pruebas" / "frases_adultos_mayores.csv"


def test_precision_intencion_no_retrocede():
    with open(RUTA, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    aciertos = sum(reglas.interpretar(r["frase"], r["contexto"], date(2026, 11, 12)).intencion == r["intencion"] for r in filas)
    assert aciertos / len(filas) >= 0.95


def test_especialidad_especifica_gana_a_generica():
    assert buscar_especialidad(normalizar("con la doctora de los dientes")) == "odontologia"
    assert buscar_especialidad(normalizar("con el doctor")) == "medicina_general"
    assert buscar_especialidad(normalizar("se me cayó la plancha")) == "odontologia"


def test_urgencia_en_cualquier_contexto():
    for ctx in ("inicio", "esperando_confirmacion", "esperando_opcion", "esperando_documento"):
        assert reglas.interpretar("me duele el pecho y no puedo respirar", ctx).intencion == "urgencia"


def test_si_no_dependen_del_contexto():
    assert reglas.interpretar("no", "esperando_confirmacion").intencion == "negar"
    assert reglas.interpretar("la dos", "esperando_opcion").opcion == 2
    assert reglas.interpretar("43527891", "esperando_documento").documento == "43527891"


def test_no_se_no_es_negar():
    for ctx in ("inicio", "esperando_confirmacion"):
        assert reglas.interpretar("eh no sé", ctx).intencion != "negar"
        assert reglas.interpretar("no me acuerdo", ctx).intencion != "negar"
    assert reglas.interpretar("no señora", "esperando_confirmacion").intencion == "negar"


def test_me_la_cancelaron_es_volver_a_agendar_no_cancelar():
    # Frase de la entrevista ENT-002: la IPS le canceló la cita y necesita otra
    from datetime import date

    from magnolia.nlu import reglas

    r = reglas.interpretar("me habían dado una cita y me la cancelaron, necesito que me la vuelvan a dar", "inicio",
                           date(2026, 11, 12))
    assert r.intencion == "agendar"
    assert reglas.interpretar("quiero cancelar mi cita", "inicio", date(2026, 11, 12)).intencion == "cancelar"


def test_cedula_dictada_por_grupos():
    from datetime import date

    from magnolia.nlu import reglas

    for frase in ["2.92.85.772", "29 28 57 72", "29.285.772", "32-456-789", "mi cédula es 43 52 78 91",
                  "veintinueve, doscientos ochenta y cinco, setecientos setenta y dos"]:
        r = reglas.interpretar(frase, "esperando_documento", date(2026, 11, 12))
        assert r.intencion == "dar_documento", frase
        assert r.documento in {"29285772", "32456789", "43527891"}, (frase, r.documento)
