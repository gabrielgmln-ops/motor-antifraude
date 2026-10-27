# tests/test_regras.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from antifraude.regras import (
    HORARIO_MADRUGADA,
    RAJADA_TRANSACOES,
    VALOR_ACIMA_P99,
    MotorRegras,
    horario_madrugada,
    percentil,
    rajada,
    valor_acima_p99,
)

SP = ZoneInfo("America/Sao_Paulo")


def test_percentil_nearest_rank():
    valores = [Decimal(i) for i in range(1, 101)]  # 1..100
    assert percentil(valores, 99) == Decimal(99)
    assert percentil(valores, 100) == Decimal(100)
    assert percentil([Decimal("5")], 99) == Decimal("5")


@pytest.mark.parametrize("p", [0, 101])
def test_percentil_recusa_p_fora_do_intervalo(p):
    with pytest.raises(ValueError):
        percentil([Decimal(1)], p)


def test_percentil_recusa_lista_vazia():
    with pytest.raises(ValueError):
        percentil([], 99)


def test_valor_acima_p99():
    historico = [Decimal(i) for i in range(1, 101)]
    assert valor_acima_p99(Decimal("99.01"), historico, 20)
    assert not valor_acima_p99(Decimal("99"), historico, 20)  # igual ao p99 não dispara


def test_valor_acima_p99_nao_dispara_com_pouco_historico():
    assert not valor_acima_p99(Decimal("1000000"), [Decimal("10")] * 19, 20)


@pytest.mark.parametrize(
    ("hora_local", "esperado"),
    [(0, True), (3, True), (4, True), (5, False), (23, False), (12, False)],
)
def test_horario_madrugada_usa_hora_local(hora_local, esperado):
    local = datetime(2026, 10, 5, hora_local, 30, tzinfo=SP)
    # O motor recebe em UTC; a regra precisa converter para o fuso configurado
    assert horario_madrugada(local.astimezone(UTC), SP, 0, 5) is esperado


def test_rajada_conta_a_transacao_atual():
    agora = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    anteriores = [agora - timedelta(minutes=m) for m in (1, 2, 3)]
    # 3 anteriores + a atual = 4 -> não é "mais de 4"
    assert not rajada(agora, anteriores, 4, timedelta(minutes=10))
    # 4 anteriores + a atual = 5 -> dispara
    assert rajada(agora, anteriores + [agora - timedelta(minutes=4)], 4, timedelta(minutes=10))


def test_rajada_ignora_eventos_fora_da_janela():
    agora = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    antigos = [agora - timedelta(minutes=m) for m in (10, 11, 30, 60)]
    assert not rajada(agora, antigos, 1, timedelta(minutes=10))


def test_motor_regras_combina_todas(parametros, fabrica_transacao):
    motor = MotorRegras(parametros)
    madrugada = datetime(2026, 10, 5, 2, 0, tzinfo=SP)
    historico = [(madrugada - timedelta(minutes=1 + i * 0.1), Decimal("50.00"))
                 for i in range(30)]
    historico.sort()
    transacao = fabrica_transacao(valor="5000.00", instante=madrugada)

    assert motor.avaliar(transacao, historico) == (
        VALOR_ACIMA_P99, HORARIO_MADRUGADA, RAJADA_TRANSACOES
    )


def test_motor_regras_sem_sinal(parametros, fabrica_transacao):
    assert MotorRegras(parametros).avaliar(fabrica_transacao(), []) == ()
