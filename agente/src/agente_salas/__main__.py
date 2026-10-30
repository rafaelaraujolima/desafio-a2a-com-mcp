import os

import uvicorn

from .a2a import criar_app
from .mcp_http import ClienteMcp
from .ponte import Ponte
from .tarefas import TaskStore


def main() -> None:
    porta = int(os.environ.get("PORTA_AGENTE", "7300"))
    url_base = os.environ.get("URL_AGENTE", f"http://127.0.0.1:{porta}")
    store = TaskStore()
    ponte = Ponte(ClienteMcp(os.environ.get("URL_MCP", "http://127.0.0.1:7301")), store)
    uvicorn.run(criar_app(ponte, store, url_base), host="127.0.0.1", port=porta, log_level="info")


main()
