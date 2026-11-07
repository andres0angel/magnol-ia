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
