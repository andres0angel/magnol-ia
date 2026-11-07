from datetime import date, time

import pytest

from magnolia.nlu.fechas import extraer_tiempo
from magnolia.nlu.normalizar import normalizar

HOY = date(2026, 11, 12)  # jueves


@pytest.mark.parametrize("frase,fecha,franja", [
    ("mañana", date(2026, 11, 13), None),
    ("mañana por la mañana", date(2026, 11, 13), "manana"),
    ("pasado mañana", date(2026, 11, 14), None),
    ("el lunes", date(2026, 11, 16), None),
    ("el jueves", date(2026, 11, 19), None),  # hoy es jueves: el próximo
    ("la otra semana en la tarde", date(2026, 11, 16), "tarde"),
    ("el 25", date(2026, 11, 25), None),
    ("el 3", date(2026, 12, 3), None),  # el 3 ya pasó este mes
    ("el tres de diciembre", date(2026, 12, 3), None),
    ("dentro de quince días", date(2026, 11, 27), None),
    ("a principios de enero", date(2027, 1, 1), None),
    ("por la mañana", None, "manana"),
])
def test_fechas(frase, fecha, franja):
    t = extraer_tiempo(normalizar(frase), HOY)
    assert t.fecha == fecha
    assert t.franja == franja


def test_asap_y_hora():
    assert extraer_tiempo(normalizar("lo más pronto posible"), HOY).asap
    assert extraer_tiempo(normalizar("a las dos y media"), HOY).hora == time(14, 30)
    assert extraer_tiempo(normalizar("a las ocho"), HOY).hora == time(8, 0)
