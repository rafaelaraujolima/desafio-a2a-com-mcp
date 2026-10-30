"""Superficie A2A v1.0 (JSON-RPC 2.0 sobre HTTP): Agent Card, SendMessage e GetTask."""
import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .ponte import EstadoInvalido, TaskTerminal

TASK_NAO_ENCONTRADA = -32001
TASK_TERMINAL = -32002
OPERACAO_INVALIDA = -32004


def _card(url_base: str) -> dict:
    return {
        "name": "Central de Salas",
        "description": "Reserva salas de reuniao da Hill Valley Tech.",
        "provider": {"organization": "Hill Valley Tech", "url": "https://hillvalley.example"},
        "version": "1.0.0",
        "supportedInterfaces": [
            {"url": f"{url_base}/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "capabilities": {"streaming": False, "pushNotifications": False, "extendedAgentCard": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "reservar-sala",
                "name": "Reservar sala",
                "description": "Reserva uma sala em um intervalo. Se houver conflito, pergunta qual alternativa usar.",
                "tags": ["salas", "agenda"],
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"],
                "examples": [
                    "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 "
                    "fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
                ],
            }
        ],
    }


def _erro(id_, codigo: int, mensagem: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensagem}})


def criar_app(ponte, store, url_base: str) -> Starlette:
    async def card(_: Request):
        return JSONResponse(_card(url_base))

    async def a2a(req: Request):
        try:
            corpo = json.loads(await req.body())
            metodo, params, id_ = corpo["method"], corpo.get("params") or {}, corpo.get("id")
        except (ValueError, KeyError, TypeError):
            return _erro(None, -32700, "JSON invalido")
        traceparent = req.headers.get("traceparent")

        if metodo == "GetTask":
            task = store.obter(params.get("id", ""))
            if task is None:
                return _erro(id_, TASK_NAO_ENCONTRADA, "Task nao encontrada")
            return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"task": task.para_a2a()}})

        if metodo == "SendMessage":
            msg = params.get("message") or {}
            partes = msg.get("parts") or []
            texto = partes[0].get("text", "") if partes else ""
            if msg.get("taskId"):
                task = store.obter(msg["taskId"])
                if task is None:
                    return _erro(id_, TASK_NAO_ENCONTRADA, "Task nao encontrada")
                try:
                    task = await ponte.continuar(task, texto, traceparent, msg.get("messageId"))
                except TaskTerminal as e:
                    return _erro(id_, TASK_TERMINAL, str(e))
                except EstadoInvalido as e:
                    return _erro(id_, OPERACAO_INVALIDA, str(e))
            else:
                task = await ponte.iniciar(texto, traceparent, msg.get("messageId"))
            return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"task": task.para_a2a()}})

        return _erro(id_, -32601, f"Metodo nao suportado: {metodo}")

    return Starlette(
        routes=[
            Route("/.well-known/agent-card.json", card, methods=["GET"]),
            Route("/a2a", a2a, methods=["POST"]),
        ]
    )
