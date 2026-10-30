"""Formatos fixos de entrada do agente. Sem interpretacao de linguagem natural."""
import re


class PedidoInvalido(Exception):
    pass


_RESERVA = re.compile(
    r"^reservar\s+sala=(?P<sala>\S+)\s+inicio=(?P<inicio>\S+)\s+fim=(?P<fim>\S+)\s+responsavel=(?P<responsavel>.+)$"
)
_ESCOLHA = re.compile(r"^escolha=(?P<valor>\S+)$")


def parse_reserva(texto: str) -> dict:
    m = _RESERVA.match((texto or "").strip())
    if not m:
        raise PedidoInvalido(
            "Pedido invalido. Use: reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>"
        )
    return {k: v.strip() for k, v in m.groupdict().items()}


def parse_escolha(texto: str) -> str:
    m = _ESCOLHA.match((texto or "").strip())
    if not m:
        raise PedidoInvalido("Resposta invalida. Use: escolha=<id da sala> ou escolha=recusar")
    return m["valor"]
