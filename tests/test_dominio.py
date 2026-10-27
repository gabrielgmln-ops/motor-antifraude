# tests/test_dominio.py
import json
from decimal import Decimal

import pytest

from antifraude.dominio import Classificacao, Decisao, ErroEventoInvalido, Transacao, para_dinheiro

EVENTO_VALIDO = {
    "transacao_id": "abc",
    "conta_id": "conta-1",
    "valor": "1234.565",
    "ocorrida_em": "2026-10-01T14:03:00+00:00",
}


def test_para_dinheiro_usa_arredondamento_bancario():
    # Meio para o par: 0.125 -> 0.12 e 0.135 -> 0.14
    assert para_dinheiro("0.125") == Decimal("0.12")
    assert para_dinheiro("0.135") == Decimal("0.14")


def test_para_dinheiro_recusa_float():
    with pytest.raises(TypeError):
        para_dinheiro(10.5)


@pytest.mark.parametrize("valor", ["0", "-5", "abc", "NaN", "Infinity"])
def test_para_dinheiro_recusa_valores_invalidos(valor):
    with pytest.raises(ErroEventoInvalido):
        para_dinheiro(valor)


def test_de_json_valido_preserva_decimal():
    transacao = Transacao.de_json(json.dumps(EVENTO_VALIDO))
    assert transacao.valor == Decimal("1234.56")
    assert isinstance(transacao.valor, Decimal)
    assert transacao.moeda == "BRL"
    assert transacao.rotulo_fraude is None


@pytest.mark.parametrize(
    "bruto",
    [
        b"nao e json",
        b"[1, 2]",
        json.dumps({**EVENTO_VALIDO, "ocorrida_em": "2026-10-01T14:03:00"}),  # sem fuso
        json.dumps({k: v for k, v in EVENTO_VALIDO.items() if k != "conta_id"}),
        json.dumps({**EVENTO_VALIDO, "ocorrida_em": "ontem"}),
    ],
)
def test_de_json_recusa_eventos_invalidos(bruto):
    with pytest.raises(ErroEventoInvalido):
        Transacao.de_json(bruto)


def test_ida_e_volta_json_mantem_valor_como_string(fabrica_transacao):
    original = fabrica_transacao(valor="99.90", rotulo_fraude=True)
    dados = json.loads(original.para_json())
    assert dados["valor"] == "99.90"
    assert Transacao.de_dict(dados) == original


def test_decisao_para_json(fabrica_transacao):
    decisao = Decisao(fabrica_transacao(), Classificacao.SUSPEITA, ("REGRA",), Decimal("-0.1"))
    dados = json.loads(decisao.para_json())
    assert dados["classificacao"] == "SUSPEITA"
    assert dados["score_anomalia"] == "-0.1"
    sem_score = json.loads(Decisao(fabrica_transacao(), Classificacao.APROVADA).para_json())
    assert sem_score["score_anomalia"] is None
