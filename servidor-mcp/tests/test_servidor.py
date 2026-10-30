import json

from central_salas.dominio import localizar_dados


def t(h, m=0):
    return f"2026-11-03T{h:02d}:{m:02d}:00-03:00"


def args(sala="sala-aquario", ini=(9,), fim=(10,), resp="Doc"):
    return {"sala": sala, "inicio": t(*ini), "fim": t(*fim), "responsavel": resp}


def test_tools_list_tem_3_tools_com_input_schema_objeto(servidor):
    st, body = servidor.rpc("tools/list")
    assert st == 200
    tools = {x["name"]: x for x in body["result"]["tools"]}
    assert set(tools) == {"listar_salas", "consultar_disponibilidade", "reservar_sala"}
    assert all(x["inputSchema"]["type"] == "object" for x in tools.values())
    assert body["result"]["resultType"] == "complete"


def test_listar_salas_structured_e_texto_iguais(servidor):
    _, body = servidor.chamar("listar_salas", {})
    res = body["result"]
    assert len(res["structuredContent"]["salas"]) == 5
    assert json.loads(res["content"][0]["text"]) == res["structuredContent"]
    _, lista = servidor.rpc("tools/list")
    ls = next(x for x in lista["result"]["tools"] if x["name"] == "listar_salas")
    assert "outputSchema" in ls


def test_reservar_livre(servidor):
    _, body = servidor.chamar("reservar_sala", args())
    res = body["result"]
    assert res["resultType"] == "complete"
    assert res["isError"] is False
    sc = res["structuredContent"]
    assert sc["reserva"] == "res-0003" and sc["reservado"] is True
    assert sc["politica"] == "2026-11-01" and sc["sala"] == "sala-aquario"


MENSAGENS = [
    (args(sala="sala-x"), "Sala inexistente: sala-x"),
    (args(ini=(7,), fim=(8,)), "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"),
    (args(ini=(9,), fim=(12,)), "Duracao acima do limite: a politica permite no maximo 2 horas"),
    (args(ini=(10,), fim=(9,)), "Intervalo invalido: fim deve ser posterior a inicio"),
]


def test_erros_de_execucao_reservar_e_consultar(servidor):
    for a, msg in MENSAGENS:
        for tool, ar in (("reservar_sala", a), ("consultar_disponibilidade", {k: a[k] for k in ("sala", "inicio", "fim")})):
            _, body = servidor.chamar(tool, ar)
            res = body["result"]
            assert res["isError"] is True, (tool, msg)
            assert msg in res["content"][0]["text"]


def test_consultar_conflito(servidor):
    _, body = servidor.chamar("consultar_disponibilidade", args("sala-garagem", (14,), (15,)))
    sc = body["result"]["structuredContent"]
    assert sc["livre"] is False and sc["conflitos"][0]["id"] == "res-0001"


def test_tool_inexistente_recusada(servidor):
    _, body = servidor.chamar("nao_existe", {})
    assert body.get("error", {}).get("code") == -32602 or body["result"]["isError"] is True


def test_resource_politica(servidor):
    _, body = servidor.rpc("resources/read", {"uri": "politica://uso"})
    c = body["result"]["contents"][0]
    assert c["mimeType"] == "text/markdown"
    assert c["text"] == (localizar_dados() / "politica-de-uso.md").read_text(encoding="utf-8")


def test_resource_inexistente_32602(servidor):
    _, body = servidor.rpc("resources/read", {"uri": "politica://nada"})
    assert body["error"]["code"] == -32602


def test_sem_protocol_version_400(servidor):
    st, body = servidor.rpc("tools/list", meta="sem-versao")
    assert st == 400 and body["error"]["code"] == -32602


def test_sem_meta_400(servidor):
    st, body = servidor.rpc("tools/list", meta=False)
    assert st == 400 and body["error"]["code"] == -32602


def test_stderr_registra_metodo_id_traceparent(servidor):
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    servidor.rpc("tools/list", traceparent=tp, id=4242)
    linha = next(l for l in servidor.stderr().splitlines() if "4242" in l)
    assert "tools/list" in linha and tp in linha
