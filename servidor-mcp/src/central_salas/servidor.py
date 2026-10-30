"""Servidor MCP da Central de Salas: tools, resource e log de requests."""
from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from .dominio import ErroDominio, Repositorio


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
        "central-de-salas", version="1.0.0", middleware=[_log_middleware]
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

    @servidor.tool(description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.")
    def reservar_sala(sala: str, inicio: str, fim: str, responsavel: str) -> ReservaOut:
        ini, end = validar(sala, inicio, fim)
        return ReservaOut(**repo.criar(sala, inicio, fim, responsavel))

    @servidor.resource("politica://uso", mime_type="text/markdown")
    def politica() -> str:
        return repo.politica_texto()

    return servidor
