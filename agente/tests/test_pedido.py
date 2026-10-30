import pytest

from agente_salas.pedido import PedidoInvalido, parse_escolha, parse_reserva

TXT = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"


def test_parse_reserva_formato_do_card():
    assert parse_reserva(TXT) == {
        "sala": "sala-garagem",
        "inicio": "2026-11-03T14:00:00-03:00",
        "fim": "2026-11-03T15:00:00-03:00",
        "responsavel": "Marty",
    }


def test_responsavel_com_espaco():
    assert parse_reserva(TXT + " McFly")["responsavel"] == "Marty McFly"


@pytest.mark.parametrize("texto", ["oi", "reservar sala=x", "reservar sala=x inicio=a fim=b", ""])
def test_reserva_invalida(texto):
    with pytest.raises(PedidoInvalido):
        parse_reserva(texto)


def test_parse_escolha():
    assert parse_escolha("escolha=sala-mirante") == "sala-mirante"
    assert parse_escolha(" escolha=recusar ") == "recusar"


@pytest.mark.parametrize("texto", ["escolha=", "sala-mirante", ""])
def test_escolha_invalida(texto):
    with pytest.raises(PedidoInvalido):
        parse_escolha(texto)
