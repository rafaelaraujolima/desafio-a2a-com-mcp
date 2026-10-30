# A Ponte: agente A2A com MCP por dentro

Central de Salas da Hill Valley Tech, em Python. Dois processos separados:

- **Servidor MCP** (`servidor-mcp/`), porta `7301`, endpoint `/mcp`, Streamable HTTP, SDK `mcp==2.3.0`, revisão `2026-07-28`.
- **Agente** (`agente/`), porta `7300`: host MCP por dentro, servidor A2A v1.0 (JSON-RPC 2.0 sobre HTTP) por fora, em `/a2a`, com o card em `/.well-known/agent-card.json`.

## Como rodar

Requer Python 3.10+. A partir de um clone limpo, na raiz do repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e servidor-mcp -e agente

# a chave do requestState vem do ambiente (>= 32 bytes); nunca fica no codigo nem no repo
export REQUEST_STATE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
                                      # PowerShell: $env:REQUEST_STATE_SECRET = python -c "import secrets; print(secrets.token_hex(32))"
```

Terminal 1, servidor MCP (o stderr mostra método, id e `traceparent` de cada request):

```bash
python -m central_salas
```

Terminal 2, agente (use o mesmo venv):

```bash
python -m agente_salas
```

Terminal 3, validador (reinicie os dois processos antes de cada execução; as reservas ficam em memória):

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

Variáveis opcionais: `PORTA_MCP` (7301), `PORTA_AGENTE` (7300), `URL_MCP` (`http://127.0.0.1:7301`), `URL_AGENTE`.
Testes automatizados: `pytest` na raiz (sobe o servidor MCP real como subprocesso).

## Onde a ponte acontece

Em [agente/src/agente_salas/ponte.py](agente/src/agente_salas/ponte.py). O `input_required` do MCP vira `TASK_STATE_INPUT_REQUIRED` em `Ponte._pausar`: ele lê a única chave de `inputRequests`, extrai o enum de alternativas, guarda chave e `requestState` **na própria Task** (`Task.pausa`, em `tarefas.py`) e responde `alternativas: id1, id2`. O `requestState` volta ao servidor em `Ponte._retomar`: a continuação `escolha=<id>` (ou `recusar`) repete o `tools/call` com **id JSON-RPC novo**, `inputResponses` com a mesma chave e o `requestState` ecoado sem modificação. Como o estado pausado é da Task, duas Tasks pausadas ao mesmo tempo não trocam de `requestState`. O agente fala MCP com um cliente HTTP/JSON-RPC próprio (`mcp_http.py`) e não com o cliente do SDK, porque o callback de elicitation do SDK responderia sozinho e a Task nunca pausaria.

## Decisões técnicas

- **Proteção do `requestState`:** `RequestStateSecurity` do SDK (AES-256-GCM, autenticado e cifrado), com a chave vinda de `REQUEST_STATE_SECRET`; o processo recusa subir se faltar ou tiver menos de 32 bytes. O estado carrega o pedido inteiro, então o retry funciona após reiniciar o servidor (mesma chave). Adulterado, expirado ou selado com outra chave resulta em `-32602`; argumentos do retry que divergem dos selados não têm efeito.
- **Validade:** 600 s (10 min), dentro da faixa de 5 a 30 min.
- **MRTR no servidor:** um resolver (`Resolve`/`Elicit` do SDK) devolve a elicitation em form mode com `sala` restrita às alternativas (capacidade ≥ a pedida, máx. 3, por capacidade e depois `id`). Não há callback: a resposta termina com `resultType: input_required`.
- **Estado das Tasks:** em memória no agente (`TaskStore`), perdido ao reiniciar o agente. Estados terminais são definitivos e `SendMessage` sobre Task terminal retorna erro JSON-RPC (`-32002`); Task inexistente, `-32001`.
- **Agente determinístico:** sem LLM, pedido em formato fixo. Cada Task faz `tools/list` e leitura de `politica://uso` antes do `tools/call` (sem lista hardcoded), e propaga o trace-id do `traceparent` do cliente A2A em todos os requests MCP.
- **Dependências:** `mcp==2.3.0` traz `httpx2`, não `httpx`; o agente e os testes fixam `httpx==0.28.1` explicitamente.

## Saída do validador

```text
trace-id desta execucao: f26bd74572452dac1e19afeb7d7dd372
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes
```
