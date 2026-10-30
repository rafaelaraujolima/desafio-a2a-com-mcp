"""Cliente MCP cru (JSON-RPC sobre HTTP). Sem sessao: cada request leva tudo que precisa."""
import secrets

import httpx

VERSAO = "2026-07-28"
CAPABILITIES = {"elicitation": {"form": {}}}


class McpErro(Exception):
    def __init__(self, codigo: int, mensagem: str, http_status: int):
        super().__init__(f"MCP {codigo}: {mensagem}")
        self.codigo, self.mensagem, self.http_status = codigo, mensagem, http_status


def nova_traceparent(recebida: str | None) -> str:
    """Mantem o trace-id do cliente A2A (se houver); o span-id e sempre novo."""
    trace_id = recebida.split("-")[1] if recebida and len(recebida.split("-")) == 4 else secrets.token_hex(16)
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


class ClienteMcp:
    def __init__(self, base_url: str, caminho: str = "/mcp", http: httpx.AsyncClient | None = None):
        self._url = base_url.rstrip("/") + caminho
        self._http = http or httpx.AsyncClient(timeout=15)
        self._proximo_id = 0
        self.ids_usados: list[int] = []

    async def chamar(self, metodo: str, params: dict, *, traceparent: str | None, nome: str | None = None) -> dict:
        self._proximo_id += 1
        id_ = self._proximo_id
        self.ids_usados.append(id_)
        meta = {
            "io.modelcontextprotocol/protocolVersion": VERSAO,
            "io.modelcontextprotocol/clientInfo": {"name": "agente-central-de-salas", "version": "1.0.0"},
            "io.modelcontextprotocol/clientCapabilities": CAPABILITIES,
            "traceparent": nova_traceparent(traceparent),
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": VERSAO,
            "Mcp-Method": metodo,
        }
        if metodo in ("tools/call", "resources/read"):
            headers["Mcp-Name"] = nome or ""
        corpo = {"jsonrpc": "2.0", "id": id_, "method": metodo, "params": {**params, "_meta": meta}}
        resp = await self._http.post(self._url, json=corpo, headers=headers)
        dados = resp.json()
        if "error" in dados:
            e = dados["error"]
            raise McpErro(e.get("code", 0), e.get("message", ""), resp.status_code)
        return dados["result"]
