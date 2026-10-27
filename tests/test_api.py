# tests/test_api.py
import pytest
from fastapi.testclient import TestClient

from antifraude.api import app, obter_repositorio
from antifraude.dominio import Classificacao, Decisao
from antifraude.repositorio import RepositorioMemoria


@pytest.fixture
def cliente(fabrica_transacao):
    repositorio = RepositorioMemoria()
    repositorio.salvar(Decisao(fabrica_transacao(valor="10.00", rotulo_fraude=False),
                               Classificacao.APROVADA))
    repositorio.salvar(Decisao(fabrica_transacao(valor="5000.00", rotulo_fraude=True),
                               Classificacao.BLOQUEADA, ("VALOR_ACIMA_P99", "HORARIO_MADRUGADA")))
    # O repositório real (Postgres) é trocado por um em memória só durante o teste
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_saude(cliente):
    assert cliente.get("/saude").json()["status"] == "ok"


def test_metricas(cliente):
    dados = cliente.get("/metricas").json()
    assert dados["total_rotuladas"] == 2
    assert dados["sinalizadas"]["precisao"] == 1.0
    assert dados["sinalizadas"]["recall"] == 1.0


def test_decisoes_serializa_valor_como_string(cliente):
    dados = cliente.get("/decisoes", params={"limite": 10}).json()
    assert dados[0]["valor"] == "5000.00"
    assert cliente.get("/decisoes", params={"limite": 0}).status_code == 422


def test_painel_html(cliente):
    resposta = cliente.get("/painel")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "Precisão" in resposta.text
    assert "R$ 5000.00" in resposta.text
    assert "VALOR_ACIMA_P99, HORARIO_MADRUGADA" in resposta.text
