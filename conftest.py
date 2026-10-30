"""Fixtures compartilhadas: sobem o servidor MCP real como subprocesso."""
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parent
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "testes", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}},
}


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServidorMcp:
    def __init__(self, segredo: str | None = None, porta: int | None = None):
        self.segredo = segredo or secrets.token_hex(32)
        self.porta = porta or porta_livre()
        self.url = f"http://127.0.0.1:{self.porta}"
        self.proc = None
        self.log = RAIZ / f".servidor-{self.porta}.log"
        self._id = 100

    def iniciar(self):
        env = {**os.environ, "REQUEST_STATE_SECRET": self.segredo, "PORTA_MCP": str(self.porta)}
        self._arq = open(self.log, "ab")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "central_salas"], env=env, stderr=self._arq, stdout=self._arq
        )
        for _ in range(100):
            if self.proc.poll() is not None:
                raise RuntimeError("servidor MCP morreu: " + self.log.read_text(errors="replace")[-1500:])
            try:
                socket.create_connection(("127.0.0.1", self.porta), timeout=0.2).close()
                return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("servidor MCP nao subiu: " + self.log.read_text(errors="replace"))

    def parar(self):
        if self.proc:
            if os.name == "nt":  # o launcher do venv gera um filho: matar a arvore
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.terminate()
            self.proc.wait(timeout=10)
            self.proc = None
            self._arq.close()

    def stderr(self) -> str:
        return self.log.read_text(errors="replace")

    def rpc(self, metodo, params=None, *, meta=True, caps=True, traceparent=None, id=None, nome=None):
        params = dict(params or {})
        if meta:
            m = {k: v for k, v in META.items()}
            if meta == "sem-versao":
                del m["io.modelcontextprotocol/protocolVersion"]
            if caps:
                m["io.modelcontextprotocol/clientCapabilities"] = {"elicitation": {"form": {}}}
            else:
                m["io.modelcontextprotocol/clientCapabilities"] = {}
            if traceparent:
                m["traceparent"] = traceparent
            params["_meta"] = m
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": metodo,
        }
        if metodo in ("tools/call", "resources/read"):
            headers["Mcp-Name"] = nome or params.get("name") or params.get("uri")
        self._id += 1
        corpo = {"jsonrpc": "2.0", "id": id or self._id, "method": metodo, "params": params}
        r = httpx.post(self.url + "/mcp", json=corpo, headers=headers, timeout=10)
        return r.status_code, r.json()

    def chamar(self, nome, argumentos, **kw):
        extra = kw.pop("extra", {})
        return self.rpc("tools/call", {"name": nome, "arguments": argumentos, **extra}, **kw)


@pytest.fixture
def servidor():
    s = ServidorMcp().iniciar()
    yield s
    s.parar()
    s.log.unlink(missing_ok=True)
