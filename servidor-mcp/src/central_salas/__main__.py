import os
import sys

from .dominio import Repositorio, localizar_dados
from .servidor import criar_servidor


def main() -> None:
    segredo = os.environ.get("REQUEST_STATE_SECRET", "")
    if len(segredo.encode()) < 32:
        sys.exit(
            "REQUEST_STATE_SECRET ausente ou curto demais (minimo 32 bytes). Gere com: "
            'python3 -c "import secrets; print(secrets.token_hex(32))"'
        )
    servidor = criar_servidor(Repositorio(localizar_dados()), segredo)
    servidor.run(
        "streamable-http",
        host="127.0.0.1",
        port=int(os.environ.get("PORTA_MCP", "7301")),
        streamable_http_path="/mcp",
    )


main()
