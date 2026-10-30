import httpx
import pytest

from agente_salas.a2a import criar_app
from agente_salas.ponte import TaskTerminal
from agente_salas.tarefas import Estado, Task, TaskStore


class PonteFalsa:
    def __init__(self, store):
        self.store = store

    async def iniciar(self, texto, traceparent, message_id=None):
        t = self.store.criar()
        t.registrar_usuario(texto, message_id)
        t.finalizar(Estado.COMPLETED, "ok")
        return t

    async def continuar(self, task, texto, traceparent=None, message_id=None):
        raise TaskTerminal("Task ja terminou")


@pytest.fixture
def cli():
    store = TaskStore()
    app = criar_app(PonteFalsa(store), store, "http://127.0.0.1:7300")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def envio(texto, task_id=None, id=1):
    msg = {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": texto}]}
    if task_id:
        msg["taskId"] = task_id
    return {"jsonrpc": "2.0", "id": id, "method": "SendMessage", "params": {"message": msg}}


async def test_card(cli):
    r = await cli.get("/.well-known/agent-card.json")
    c = r.json()
    assert r.status_code == 200
    i = c["supportedInterfaces"][0]
    assert i == {"url": "http://127.0.0.1:7300/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
    assert [s["id"] for s in c["skills"]] == ["reservar-sala"]


async def test_send_message_abre_task(cli):
    r = (await cli.post("/a2a", json=envio("x"))).json()
    t = r["result"]["task"]
    assert t["id"] and t["contextId"] and t["status"]["state"] == "TASK_STATE_COMPLETED"


async def test_get_task_reflete_estado(cli):
    t = (await cli.post("/a2a", json=envio("x"))).json()["result"]["task"]
    body = {"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": t["id"]}}
    g = (await cli.post("/a2a", json=body)).json()["result"]["task"]
    assert g["id"] == t["id"] and g["status"]["state"] == "TASK_STATE_COMPLETED"


async def test_send_message_em_task_terminal_e_erro(cli):
    t = (await cli.post("/a2a", json=envio("x"))).json()["result"]["task"]
    r = (await cli.post("/a2a", json=envio("escolha=x", task_id=t["id"]))).json()
    assert "error" in r


async def test_task_inexistente_em_send_message_nao_cria_task(cli):
    r = (await cli.post("/a2a", json=envio("escolha=x", task_id="task-nao-existe"))).json()
    assert r["error"]["code"] == -32001


async def test_get_task_inexistente(cli):
    body = {"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": "nada"}}
    assert (await cli.post("/a2a", json=body)).json()["error"]["code"] == -32001


async def test_json_invalido_e_metodo_desconhecido(cli):
    r = await cli.post("/a2a", content=b"{nao json", headers={"content-type": "application/json"})
    assert r.json()["error"]["code"] == -32700
    r = await cli.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "Outro", "params": {}})
    assert r.json()["error"]["code"] == -32601
