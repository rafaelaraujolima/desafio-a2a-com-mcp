import json

import httpx
import pytest

from agente_salas.mcp_http import ClienteMcp, McpErro, nova_traceparent

TP = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def cliente(resposta=None, status=200):
    vistos = []

    def handler(req: httpx.Request):
        vistos.append((req.headers, json.loads(req.content)))
        corpo = resposta or {"jsonrpc": "2.0", "id": vistos[-1][1]["id"], "result": {"ok": True}}
        return httpx.Response(status, json=corpo)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ClienteMcp("http://mcp", http=http), vistos


async def test_headers_e_meta_batem_com_o_corpo():
    c, vistos = cliente()
    await c.chamar("tools/call", {"name": "reservar_sala", "arguments": {}}, traceparent=TP, nome="reservar_sala")
    h, corpo = vistos[0]
    assert h["mcp-protocol-version"] == "2026-07-28"
    assert h["mcp-method"] == "tools/call" == corpo["method"]
    assert h["mcp-name"] == "reservar_sala"
    meta = corpo["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert meta["io.modelcontextprotocol/clientCapabilities"] == {"elicitation": {"form": {}}}


async def test_tools_list_nao_envia_mcp_name():
    c, vistos = cliente()
    await c.chamar("tools/list", {}, traceparent=None)
    assert "mcp-name" not in vistos[0][0]


async def test_traceparent_mantem_trace_id_e_troca_span_id():
    c, vistos = cliente()
    await c.chamar("tools/list", {}, traceparent=TP)
    novo = vistos[0][1]["params"]["_meta"]["traceparent"]
    assert novo.split("-")[1] == TP.split("-")[1]
    assert novo.split("-")[2] != TP.split("-")[2]


def test_traceparent_gera_quando_ausente():
    assert len(nova_traceparent(None).split("-")[1]) == 32


async def test_ids_diferentes_a_cada_chamada():
    c, vistos = cliente()
    await c.chamar("tools/list", {}, traceparent=None)
    await c.chamar("tools/list", {}, traceparent=None)
    assert len(set(c.ids_usados)) == 2


async def test_erro_vira_mcperro():
    c, _ = cliente({"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "ruim"}}, status=400)
    with pytest.raises(McpErro) as e:
        await c.chamar("tools/list", {}, traceparent=None)
    assert e.value.codigo == -32602 and e.value.http_status == 400


async def test_result_repassado_intacto():
    r = {"jsonrpc": "2.0", "id": 1, "result": {"resultType": "input_required", "requestState": "v1.xyz"}}
    c, _ = cliente(r)
    assert (await c.chamar("tools/call", {"name": "x"}, traceparent=None, nome="x"))["requestState"] == "v1.xyz"
