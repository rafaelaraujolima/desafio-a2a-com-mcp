"""A ponte: traduz o input_required do MCP em pausa de Task A2A, e a retomada em retry MCP."""
import json

import httpx

from .mcp_http import ClienteMcp, McpErro
from .pedido import PedidoInvalido, parse_escolha, parse_reserva
from .tarefas import TERMINAIS, Estado, Pausa, Task, TaskStore


class TaskTerminal(Exception):
    pass


class EstadoInvalido(Exception):
    pass


class Ponte:
    def __init__(self, mcp: ClienteMcp, store: TaskStore):
        self.mcp = mcp
        self.store = store

    async def iniciar(self, texto: str, traceparent: str | None, message_id: str | None = None) -> Task:
        task = self.store.criar()
        task.registrar_usuario(texto, message_id)
        task.mudar(Estado.WORKING)
        try:
            argumentos = parse_reserva(texto)
            await self._descobrir(task, traceparent)
            resultado = await self._chamar_reserva(argumentos, traceparent)
            self._tratar(task, resultado, argumentos)
        except Exception as e:  # noqa: BLE001 - qualquer falha vira FAILED, o agente segue de pe
            self._falhar(task, e)
        return task

    async def continuar(
        self, task: Task, texto: str, traceparent: str | None = None, message_id: str | None = None
    ) -> Task:
        async with task.lock:
            if task.estado in TERMINAIS:
                raise TaskTerminal(f"Task {task.id} ja terminou ({task.estado.value})")
            if task.estado != Estado.INPUT_REQUIRED or task.pausa is None:
                raise EstadoInvalido(f"Task {task.id} nao esta aguardando resposta")
            task.registrar_usuario(texto, message_id)
            try:
                await self._retomar(task, parse_escolha(texto), traceparent)
            except Exception as e:  # noqa: BLE001
                self._falhar(task, e)
            return task

    # ------------------------------------------------------------------ MCP
    async def _descobrir(self, task: Task, traceparent: str | None) -> None:
        """tools/list em runtime antes do 1o tools/call; versao da politica vem do resource."""
        tools = await self.mcp.chamar("tools/list", {}, traceparent=traceparent)
        if "reservar_sala" not in {t["name"] for t in tools["tools"]}:
            raise McpErro(-32601, "Servidor MCP nao oferece a tool reservar_sala", 200)
        r = await self.mcp.chamar(
            "resources/read", {"uri": "politica://uso"}, traceparent=traceparent, nome="politica://uso"
        )
        primeira = r["contents"][0]["text"].splitlines()[0]
        task.politica = primeira.split(":", 1)[1].strip()

    async def _chamar_reserva(self, argumentos: dict, traceparent: str | None, **extra) -> dict:
        return await self.mcp.chamar(
            "tools/call",
            {"name": "reservar_sala", "arguments": argumentos, **extra},
            traceparent=traceparent,
            nome="reservar_sala",
        )

    # ------------------------------------------------------- resultado -> Task
    def _tratar(self, task: Task, resultado: dict, argumentos: dict) -> None:
        if resultado.get("resultType") == "input_required":
            self._pausar(task, resultado, argumentos)
            return
        texto_erro = next((c["text"] for c in resultado.get("content", []) if c.get("type") == "text"), "")
        if resultado.get("isError"):
            task.finalizar(Estado.FAILED, texto_erro or "Erro na ferramenta de reserva")
            return
        sc = resultado.get("structuredContent") or {}
        if sc.get("reservado") is False:
            task.finalizar(Estado.CANCELED, "Reserva recusada pelo cliente.")
            return
        reserva = {k: sc.get(k) for k in ("reserva", "sala", "inicio", "fim", "responsavel")}
        reserva["politica"] = task.politica
        task.artifacts.append(
            {
                "artifactId": f"art-{task.id[5:]}",
                "name": "reserva",
                "parts": [{"text": json.dumps(reserva)}],
            }
        )
        task.finalizar(Estado.COMPLETED, f"Reserva {reserva['reserva']} confirmada na {reserva['sala']}.")

    def _pausar(self, task: Task, resultado: dict, argumentos: dict) -> None:
        """PONTE (ida): input_required do MCP vira TASK_STATE_INPUT_REQUIRED.

        Guarda a chave do inputRequest e o requestState (opaco) na propria Task.
        """
        chave, pedido = next(iter(resultado["inputRequests"].items()))
        prop = pedido["params"]["requestedSchema"]["properties"]["sala"]
        alternativas = prop["enum"] if "enum" in prop else [prop["const"]]
        task.pausa = Pausa(argumentos, chave, resultado["requestState"], list(alternativas))
        task.mudar(Estado.INPUT_REQUIRED, "alternativas: " + ", ".join(alternativas))

    async def _retomar(self, task: Task, escolha: str, traceparent: str | None) -> None:
        """PONTE (volta): repete o tools/call (id novo) com inputResponses + requestState ecoado."""
        pausa = task.pausa
        if escolha == "recusar":
            resposta = {"action": "decline"}
        elif escolha in pausa.alternativas:
            resposta = {"action": "accept", "content": {"sala": escolha}}
        else:  # fora do enum: mantem a pausa e repete a lista
            task.mudar(Estado.INPUT_REQUIRED, "alternativas: " + ", ".join(pausa.alternativas))
            return
        resultado = await self._chamar_reserva(
            pausa.argumentos,
            traceparent,
            inputResponses={pausa.chave_input: resposta},
            requestState=pausa.request_state,
        )
        self._tratar(task, resultado, pausa.argumentos)

    def _falhar(self, task: Task, e: Exception) -> None:
        if task.estado in TERMINAIS:
            return
        if isinstance(e, PedidoInvalido):
            msg = str(e)
        elif isinstance(e, McpErro):
            msg = f"Erro do servidor MCP: {e.mensagem}"
        elif isinstance(e, httpx.HTTPError):
            msg = "Servidor MCP indisponivel"
        else:
            msg = f"Erro interno do agente: {type(e).__name__}"
        task.finalizar(Estado.FAILED, msg)
