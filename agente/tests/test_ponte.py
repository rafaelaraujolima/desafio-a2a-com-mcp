import json

import pytest

from agente_salas.mcp_http import ClienteMcp
from agente_salas.ponte import Ponte
from agente_salas.tarefas import Estado, TaskStore

TP = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
CONF = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
LIVRE = "reservar sala=sala-aquario inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
FUSCA = "reservar sala=sala-fusca inicio=2026-11-03T16:00:00-03:00 fim=2026-11-03T17:00:00-03:00 responsavel=Jennifer"


@pytest.fixture
def ponte(servidor):
    mcp = ClienteMcp(servidor.url)
    p = Ponte(mcp, TaskStore())
    p.mcp_teste = mcp
    return p


def textos(task):
    return [p["text"] for m in task.historico for p in m["parts"]]


def artifact(task):
    return json.loads(task.artifacts[0]["parts"][0]["text"])


async def test_sala_livre_completa_com_artifact(ponte):
    t = await ponte.iniciar(LIVRE, TP)
    assert t.estado == Estado.COMPLETED
    assert t.artifacts[0]["name"] == "reserva"
    a = artifact(t)
    assert a["sala"] == "sala-aquario" and a["responsavel"] == "Doc" and a["politica"] == "2026-11-01"
    assert a["reserva"].startswith("res-")


async def test_conflito_pausa_com_linha_exata(ponte):
    t = await ponte.iniciar(CONF, TP)
    assert t.estado == Estado.INPUT_REQUIRED
    assert t.status_msg["parts"][0]["text"] == "alternativas: sala-fusca, sala-mirante"


async def test_continuacao_escolha_conclui(ponte):
    t = await ponte.iniciar(CONF, TP)
    t = await ponte.continuar(t, "escolha=sala-mirante", TP)
    assert t.estado == Estado.COMPLETED and artifact(t)["sala"] == "sala-mirante"


async def test_recusar_cancela(ponte):
    t = await ponte.iniciar(CONF, TP)
    t = await ponte.continuar(t, "escolha=recusar", TP)
    assert t.estado == Estado.CANCELED and not t.artifacts


async def test_escolha_fora_do_enum_mantem_pausa(ponte):
    t = await ponte.iniciar(CONF, TP)
    t = await ponte.continuar(t, "escolha=sala-aquario", TP)
    assert t.estado == Estado.INPUT_REQUIRED
    assert t.status_msg["parts"][0]["text"] == "alternativas: sala-fusca, sala-mirante"
    t = await ponte.continuar(t, "escolha=sala-fusca", TP)
    assert t.estado == Estado.COMPLETED


async def test_sala_inexistente_failed(ponte):
    t = await ponte.iniciar(LIVRE.replace("sala-aquario", "sala-inexistente"), TP)
    assert t.estado == Estado.FAILED
    assert any("Sala inexistente: sala-inexistente" in x for x in textos(t))


async def test_duas_tasks_pausadas_nao_trocam_estado(ponte):
    a = await ponte.iniciar(CONF, TP)
    b = await ponte.iniciar(FUSCA, TP)
    assert a.estado == b.estado == Estado.INPUT_REQUIRED
    b = await ponte.continuar(b, "escolha=sala-mirante", TP)
    a = await ponte.continuar(a, "escolha=sala-fusca", TP)
    assert artifact(a)["sala"] == "sala-fusca" and artifact(a)["responsavel"] == "Marty"
    assert artifact(b)["sala"] == "sala-mirante" and artifact(b)["responsavel"] == "Jennifer"


async def test_retry_usa_id_diferente_e_ordem_dos_metodos(ponte, servidor):
    t = await ponte.iniciar(CONF, TP)
    await ponte.continuar(t, "escolha=sala-fusca", TP)
    linhas = [l for l in servidor.stderr().splitlines() if l.startswith("[mcp]")]
    metodos = [l.split()[1] for l in linhas]
    assert metodos == ["metodo=tools/list", "metodo=resources/read", "metodo=tools/call", "metodo=tools/call"]
    ids = [l.split("id=")[1].split()[0] for l in linhas if "tools/call" in l]
    assert len(set(ids)) == 2
    trace = TP.split("-")[1]
    assert all(trace in l for l in linhas)


async def test_nenhuma_resposta_contem_request_state(ponte):
    t = await ponte.iniciar(CONF, TP)
    assert t.pausa.request_state
    assert t.pausa.request_state not in json.dumps(t.para_a2a())
    assert "pausa" not in t.para_a2a()


async def test_texto_invalido_failed(ponte):
    t = await ponte.iniciar("oi", TP)
    assert t.estado == Estado.FAILED
    assert any("Pedido invalido" in x for x in textos(t))


async def test_mcp_fora_do_ar_failed():
    p = Ponte(ClienteMcp("http://127.0.0.1:1"), TaskStore())
    t = await p.iniciar(LIVRE, TP)
    assert t.estado == Estado.FAILED
