# tests/test_gerador_estado.py
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from antifraude.estado import EstadoContas
from antifraude.gerador import gerar_transacoes


def test_gerador_e_reprodutivel():
    a = gerar_transacoes(n_contas=10, dias=5, semente=1)
    b = gerar_transacoes(n_contas=10, dias=5, semente=1)
    assert a == b
    assert a != gerar_transacoes(n_contas=10, dias=5, semente=2)


def test_gerador_produz_dinheiro_decimal_ordenado_e_rotulado():
    transacoes = gerar_transacoes(n_contas=50, dias=30, semente=3, taxa_fraude_dia=0.05)
    assert all(isinstance(t.valor, Decimal) and t.valor > 0 for t in transacoes)
    assert all(t.valor == t.valor.quantize(Decimal("0.01")) for t in transacoes)
    assert all(t.rotulo_fraude is not None for t in transacoes)
    instantes = [t.ocorrida_em for t in transacoes]
    assert instantes == sorted(instantes)
    assert len({t.transacao_id for t in transacoes}) == len(transacoes)
    fraudes = Counter(t.rotulo_fraude for t in transacoes)
    assert 0 < fraudes[True] < fraudes[False]


def test_estado_registra_limita_e_carrega(fabrica_transacao):
    estado = EstadoContas(max_por_conta=3)
    for i in range(5):
        estado.registrar(fabrica_transacao(valor=f"{i + 1}.00", minutos=i))
    historico = estado.historico("conta-teste")
    assert [v for _, v in historico] == [Decimal("3.00"), Decimal("4.00"), Decimal("5.00")]
    assert len(estado) == 1

    agora = datetime(2026, 1, 1, tzinfo=UTC)
    estado.carregar({"outra": [(agora, Decimal("2")), (agora - timedelta(hours=1), Decimal("1"))]})
    assert [v for _, v in estado.historico("outra")] == [Decimal("1"), Decimal("2")]
