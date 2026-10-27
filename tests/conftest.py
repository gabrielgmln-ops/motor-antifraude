# tests/conftest.py
"""Fixtures compartilhadas pelos testes."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from antifraude.config import ParametrosRegras
from antifraude.dominio import Transacao

# Segunda-feira, 14h em São Paulo (17h UTC): horário comercial, fora da madrugada
INSTANTE_BASE = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)


@pytest.fixture
def parametros() -> ParametrosRegras:
    # _env_file=None: os testes não dependem do .env de quem está rodando
    return ParametrosRegras(_env_file=None)


@pytest.fixture
def fabrica_transacao():
    """Cria transações com valores padrão, sobrescrevendo só o que o teste precisa."""
    contador = iter(range(1_000_000))

    def _criar(valor: str = "100.00", minutos: float = 0, conta_id: str = "conta-teste",
               instante: datetime | None = None, rotulo_fraude: bool | None = None) -> Transacao:
        quando = instante or INSTANTE_BASE + timedelta(minutes=minutos)
        return Transacao(
            transacao_id=f"tx-{next(contador)}",
            conta_id=conta_id,
            valor=Decimal(valor),
            ocorrida_em=quando,
            rotulo_fraude=rotulo_fraude,
        )

    return _criar
