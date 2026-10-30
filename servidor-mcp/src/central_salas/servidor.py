"""Servidor MCP da Central de Salas: tools, resource e log de requests."""
import sys
from typing import Annotated, Literal

from mcp.server.elicitation import AcceptedElicitation, ElicitationResult
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.server.request_state import RequestStateSecurity
from pydantic import BaseModel, Field, create_model

from .dominio import MSG_SEM_ALTERNATIVAS, ErroDominio, Repositorio


class EscolhaBase(BaseModel):
    sala: str


class SalaOut(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaDeSalas(BaseModel):
    salas: list[SalaOut]


class ConflitoOut(BaseModel):
    id: str
    inicio: str
    fim: str
    responsavel: str


class Disponibilidade(BaseModel):
    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class ReservaOut(BaseModel):
    reserva: str | None = None
    reservado: bool = True
    sala: str | None = None
    inicio: str | None = None
    fim: str | None = None
    responsavel: str | None = None
    politica: str | None = None
    motivo: str | None = None


def _logar_request(ctx_method, ctx_id, params) -> None:
    meta = (params or {}).get("_meta") or {}
    print(
        f"[mcp] metodo={ctx_method} id={ctx_id} traceparent={meta.get('traceparent', '-')}",
        file=sys.stderr,
        flush=True,
    )


async def _log_middleware(ctx, call_next):
    _logar_request(ctx.method, ctx.request_id, ctx.params)
    return await call_next(ctx)


def criar_servidor(repo: Repositorio, segredo: str) -> MCPServer:
    servidor = MCPServer(
        "central-de-salas",
        version="1.0.0",
        middleware=[_log_middleware],
        # AES-256-GCM do SDK; chave so do ambiente; vale 10 min (faixa exigida: 5 a 30).
        request_state_security=RequestStateSecurity(keys=[segredo], ttl=600),
    )

    def validar(sala: str, inicio: str, fim: str):
        try:
            return repo.validar(sala, inicio, fim)
        except ErroDominio as e:
            raise ToolError(str(e)) from None

    @servidor.tool(description="Lista todas as salas com capacidade e recursos.")
    def listar_salas() -> ListaDeSalas:
        return ListaDeSalas(salas=[SalaOut(**s) for s in repo.salas()])

    @servidor.tool(description="Diz se uma sala esta livre no intervalo, e quais reservas conflitam.")
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> Disponibilidade:
        ini, end = validar(sala, inicio, fim)
        conflitos = repo.conflitos(sala, ini, end)
        return Disponibilidade(sala=sala, livre=not conflitos, conflitos=conflitos)

    def escolha_de_sala(sala: str, inicio: str, fim: str):
        """Resolver: no conflito, termina a resposta pedindo a escolha (MRTR), sem callback."""
        ini, end = validar(sala, inicio, fim)
        if not repo.conflitos(sala, ini, end):
            return EscolhaBase(sala=sala)  # livre: nada a perguntar, segue na sala pedida
        alternativas = repo.alternativas(sala, ini, end)
        if not alternativas:
            raise ToolError(MSG_SEM_ALTERNATIVAS)
        schema = create_model(
            "EscolhaDeSala",
            __base__=EscolhaBase,
            sala=(Literal[tuple(alternativas)], Field(description="Sala alternativa escolhida", title="Sala")),
        )
        return Elicit("A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.", schema)

    @servidor.tool(description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.")
    def reservar_sala(
        sala: str,
        inicio: str,
        fim: str,
        responsavel: str,
        escolha: Annotated[ElicitationResult[EscolhaBase], Resolve(escolha_de_sala)],
    ) -> ReservaOut:
        if not isinstance(escolha, AcceptedElicitation):  # decline ou cancel
            return ReservaOut(reservado=False, motivo="recusado")
        destino = escolha.data.sala
        validar(destino, inicio, fim)
        return ReservaOut(**repo.criar(destino, inicio, fim, responsavel))

    @servidor.resource("politica://uso", mime_type="text/markdown")
    def politica() -> str:
        return repo.politica_texto()

    return servidor
