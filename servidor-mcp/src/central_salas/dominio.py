"""Regras de sala e politica de uso. Sem nada de protocolo aqui."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

FUSO = timezone(timedelta(hours=-3))
MSG_JANELA = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
MSG_DURACAO = "Duracao acima do limite: a politica permite no maximo 2 horas"
MSG_INVALIDO = "Intervalo invalido: fim deve ser posterior a inicio"
MSG_SEM_ALTERNATIVAS = "Sem alternativas disponiveis no intervalo"


class ErroDominio(Exception):
    """A mensagem e o texto exato devolvido ao cliente."""


def localizar_dados() -> Path:
    for pasta in Path(__file__).resolve().parents:
        if (pasta / "dados" / "salas.json").is_file():
            return pasta / "dados"
    raise FileNotFoundError("Pasta dados/ nao encontrada")


def _parse(valor: str) -> datetime:
    try:
        dt = datetime.fromisoformat(valor)
    except (ValueError, TypeError):
        raise ErroDominio(f"{MSG_INVALIDO} (data invalida: {valor})") from None
    if dt.tzinfo is None:
        raise ErroDominio(f"{MSG_INVALIDO} (data sem fuso horario: {valor})")
    return dt


class Repositorio:
    def __init__(self, dados_dir: Path):
        self._dir = Path(dados_dir)
        self._salas = json.loads((self._dir / "salas.json").read_text(encoding="utf-8"))
        self._reservas = json.loads((self._dir / "reservas.json").read_text(encoding="utf-8"))
        self._politica = (self._dir / "politica-de-uso.md").read_text(encoding="utf-8")
        self._proximo = 3

    def salas(self) -> list[dict]:
        return [dict(s) for s in self._salas]

    def politica_texto(self) -> str:
        return self._politica

    def politica_versao(self) -> str:
        return self._politica.splitlines()[0].split(":", 1)[1].strip()

    def validar(self, sala: str, inicio: str, fim: str) -> tuple[datetime, datetime]:
        if not any(s["id"] == sala for s in self._salas):
            raise ErroDominio(f"Sala inexistente: {sala}")
        ini, end = _parse(inicio), _parse(fim)
        if end <= ini:
            raise ErroDominio(MSG_INVALIDO)
        for dt in (ini, end):
            local = dt.astimezone(FUSO)
            minutos = local.hour * 60 + local.minute
            if minutos < 8 * 60 or minutos > 20 * 60 or local.date() != ini.astimezone(FUSO).date():
                raise ErroDominio(MSG_JANELA)
        if end - ini > timedelta(hours=2):
            raise ErroDominio(MSG_DURACAO)
        return ini, end

    def conflitos(self, sala: str, ini: datetime, fim: datetime) -> list[dict]:
        return [
            {k: r[k] for k in ("id", "inicio", "fim", "responsavel")}
            for r in self._reservas
            if r["sala"] == sala
            and ini < datetime.fromisoformat(r["fim"])
            and fim > datetime.fromisoformat(r["inicio"])
        ]

    def alternativas(self, sala: str, ini: datetime, fim: datetime) -> list[str]:
        capacidade = next(s["capacidade"] for s in self._salas if s["id"] == sala)
        livres = [
            s for s in self._salas
            if s["id"] != sala and s["capacidade"] >= capacidade
            and not self.conflitos(s["id"], ini, fim)
        ]
        livres.sort(key=lambda s: (s["capacidade"], s["id"]))
        return [s["id"] for s in livres[:3]]

    def criar(self, sala: str, inicio: str, fim: str, responsavel: str) -> dict:
        reserva_id = f"res-{self._proximo:04d}"
        self._proximo += 1
        self._reservas.append(
            {"id": reserva_id, "sala": sala, "inicio": inicio, "fim": fim, "responsavel": responsavel}
        )
        return {
            "reserva": reserva_id, "sala": sala, "inicio": inicio, "fim": fim,
            "responsavel": responsavel, "politica": self.politica_versao(),
        }
