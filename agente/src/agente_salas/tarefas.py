"""Task A2A: identidade, estado e produto. O estado pausado (requestState) vive aqui, por Task."""
import asyncio
import secrets
from dataclasses import dataclass, field
from enum import Enum


class Estado(str, Enum):
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    COMPLETED = "TASK_STATE_COMPLETED"
    CANCELED = "TASK_STATE_CANCELED"
    FAILED = "TASK_STATE_FAILED"


TERMINAIS = {Estado.COMPLETED, Estado.CANCELED, Estado.FAILED}


def _novo_id(prefixo: str) -> str:
    return f"{prefixo}-{secrets.token_hex(6)}"


@dataclass
class Pausa:
    """O que a ponte guarda ao receber input_required. requestState e opaco: so guardar e ecoar."""

    argumentos: dict
    chave_input: str
    request_state: str
    alternativas: list[str]


@dataclass
class Task:
    id: str = field(default_factory=lambda: _novo_id("task"))
    context_id: str = field(default_factory=lambda: _novo_id("ctx"))
    estado: Estado = Estado.SUBMITTED
    status_msg: dict | None = None
    historico: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    pausa: Pausa | None = None
    politica: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def registrar_usuario(self, texto: str, message_id: str | None = None) -> None:
        msg = {"messageId": message_id or _novo_id("msg"), "role": "ROLE_USER", "parts": [{"text": texto}]}
        if self.historico:  # continuacao: a mensagem referencia a Task
            msg["taskId"] = self.id
        self.historico.append(msg)

    def mudar(self, estado: Estado, texto: str | None = None) -> None:
        """Transicao de estado. Estado terminal e definitivo."""
        if self.estado in TERMINAIS:
            raise RuntimeError(f"Task {self.id} ja esta em estado terminal")
        self.estado = estado
        self.status_msg = None
        if texto is not None:
            self.status_msg = {
                "messageId": _novo_id("msg"),
                "role": "ROLE_AGENT",
                "parts": [{"text": texto}],
                "taskId": self.id,
                "contextId": self.context_id,
            }
            self.historico.append(self.status_msg)

    def finalizar(self, estado: Estado, texto: str) -> None:
        self.mudar(estado, texto)
        self.pausa = None

    def para_a2a(self) -> dict:
        status = {"state": self.estado.value}
        if self.status_msg:
            status["message"] = self.status_msg
        return {
            "id": self.id,
            "contextId": self.context_id,
            "status": status,
            "history": self.historico,
            "artifacts": self.artifacts,
        }


class TaskStore:
    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def criar(self) -> Task:
        t = Task()
        self._tasks[t.id] = t
        return t

    def obter(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)
