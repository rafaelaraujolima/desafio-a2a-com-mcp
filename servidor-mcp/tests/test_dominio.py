import pytest

from central_salas.dominio import ErroDominio, Repositorio, localizar_dados

JANELA = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
DURACAO = "Duracao acima do limite: a politica permite no maximo 2 horas"
INVALIDO = "Intervalo invalido: fim deve ser posterior a inicio"


def t(h, m=0):
    return f"2026-11-03T{h:02d}:{m:02d}:00-03:00"


@pytest.fixture
def repo():
    return Repositorio(localizar_dados())


def test_sala_inexistente(repo):
    with pytest.raises(ErroDominio) as e:
        repo.validar("sala-x", t(9), t(10))
    assert str(e.value) == "Sala inexistente: sala-x"


def test_janela(repo):
    with pytest.raises(ErroDominio) as e:
        repo.validar("sala-aquario", t(7), t(8))
    assert str(e.value) == JANELA
    with pytest.raises(ErroDominio) as e:
        repo.validar("sala-aquario", t(19), t(20, 30))
    assert str(e.value) == JANELA


def test_fim_as_20h_e_permitido(repo):
    repo.validar("sala-aquario", t(19), t(20))


def test_duracao(repo):
    with pytest.raises(ErroDominio) as e:
        repo.validar("sala-aquario", t(9), t(12))
    assert str(e.value) == DURACAO


def test_intervalo_invertido_e_vazio(repo):
    for ini, fim in [(t(10), t(9)), (t(10), t(10))]:
        with pytest.raises(ErroDominio) as e:
            repo.validar("sala-aquario", ini, fim)
        assert str(e.value) == INVALIDO


@pytest.mark.parametrize("ini", ["amanha", "2026-11-03T09:00:00"])
def test_data_sem_timezone_ou_nao_iso(repo, ini):
    with pytest.raises(ErroDominio) as e:
        repo.validar("sala-aquario", ini, t(10))
    assert str(e.value).startswith("Intervalo invalido")


def test_conflito_garagem(repo):
    ini, fim = repo.validar("sala-garagem", t(14), t(15))
    assert [c["id"] for c in repo.conflitos("sala-garagem", ini, fim)] == ["res-0001"]


def test_alternativas_garagem_ordem(repo):
    ini, fim = repo.validar("sala-garagem", t(14), t(15))
    assert repo.alternativas("sala-garagem", ini, fim) == ["sala-fusca", "sala-mirante"]


def test_alternativas_max_3_e_desempate(repo):
    # aquario(4) pedido: porao 6, fusca 12, garagem 12, mirante 20 -> max 3
    ini, fim = repo.validar("sala-aquario", t(9), t(10))
    assert repo.alternativas("sala-aquario", ini, fim) == ["sala-porao", "sala-fusca", "sala-garagem"]


def test_criar_incrementa_id_e_afeta_conflitos(repo):
    r = repo.criar("sala-aquario", t(9), t(10), "Doc")
    assert r["reserva"] == "res-0003"
    assert r["politica"] == "2026-11-01"
    ini, fim = repo.validar("sala-aquario", t(9), t(10))
    assert len(repo.conflitos("sala-aquario", ini, fim)) == 1
    assert repo.criar("sala-porao", t(9), t(10), "Doc")["reserva"] == "res-0004"


def test_politica_versao(repo):
    assert repo.politica_versao() == "2026-11-01"
