# tests/test_integracao_postgres.py
"""Testes contra um PostgreSQL real. Rodam com: pytest -m integracao

Exigem as variáveis POSTGRES_* (o CI as define junto com um serviço de banco).
"""

from decimal import Decimal

import psycopg
import pytest

from antifraude.config import Configuracao
from antifraude.dominio import Classificacao, Decisao
from antifraude.repositorio import RepositorioPostgres

pytestmark = pytest.mark.integracao


@pytest.fixture
def repositorio():
    cfg = Configuracao()
    # Proteção: o teste apaga a tabela, então só roda em banco cujo nome termina em _teste
    if not cfg.postgres_db.endswith("_teste"):
        pytest.skip("POSTGRES_DB precisa terminar em '_teste' para rodar a integração")
    repo = RepositorioPostgres(cfg.dsn_postgres)
    repo.criar_schema()
    with psycopg.connect(cfg.dsn_postgres) as conexao:
        conexao.execute("TRUNCATE decisoes")
    return repo


def test_salvar_e_idempotencia(repositorio, fabrica_transacao):
    decisao = Decisao(fabrica_transacao(valor="1234.56", rotulo_fraude=True),
                      Classificacao.BLOQUEADA, ("VALOR_ACIMA_P99",), Decimal("-0.12345"))
    assert repositorio.salvar(decisao) is True
    assert repositorio.salvar(decisao) is False

    linha = repositorio.listar_recentes(1)[0]
    assert linha["valor"] == Decimal("1234.56")  # NUMERIC volta como Decimal, sem perda
    assert linha["regras_disparadas"] == ["VALOR_ACIMA_P99"]
    assert repositorio.contagens_rotuladas() == {(True, Classificacao.BLOQUEADA): 1}


def test_historico_recente_por_conta(repositorio, fabrica_transacao):
    for i in range(5):
        repositorio.salvar(Decisao(fabrica_transacao(valor=f"{i + 1}.00", minutos=i),
                                   Classificacao.APROVADA))
    historico = repositorio.historico_recente(por_conta=2)
    assert sorted(v for _, v in historico["conta-teste"]) == [Decimal("4.00"), Decimal("5.00")]
