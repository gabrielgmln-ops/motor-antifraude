# src/antifraude/regras.py
"""Motor de regras determinísticas.

Cada regra é uma função pura (sem estado próprio), o que torna o teste trivial:
recebe a transação e o histórico anterior da conta e responde sim ou não.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from antifraude.config import ParametrosRegras
from antifraude.dominio import Transacao
from antifraude.estado import Evento

VALOR_ACIMA_P99 = "VALOR_ACIMA_P99"
HORARIO_MADRUGADA = "HORARIO_MADRUGADA"
RAJADA_TRANSACOES = "RAJADA_TRANSACOES"


def percentil(valores: Sequence[Decimal], p: int) -> Decimal:
    """Percentil pelo método nearest-rank, inteiro em Decimal (sem interpolação em float).

    Ex.: 100 valores e p=99 -> o 99º menor valor.
    """
    if not valores:
        raise ValueError("percentil de lista vazia")
    if not 0 < p <= 100:
        raise ValueError("p deve estar em (0, 100]")
    ordenados = sorted(valores)
    posicao = math.ceil(p / 100 * len(ordenados))
    return ordenados[posicao - 1]


def valor_acima_p99(valor: Decimal, valores_anteriores: Sequence[Decimal],
                    min_historico: int) -> bool:
    """Valor estritamente acima do percentil 99 da própria conta.

    Com pouco histórico (conta nova), o percentil não é confiável e a regra não dispara;
    nesse período o modelo de anomalia é a defesa principal.
    """
    if len(valores_anteriores) < min_historico:
        return False
    return valor > percentil(valores_anteriores, 99)


def horario_madrugada(ocorrida_em: datetime, fuso: ZoneInfo, inicio: int, fim: int) -> bool:
    """Hora local no intervalo [inicio, fim). Padrão: 0h00 até 4h59."""
    hora_local = ocorrida_em.astimezone(fuso).hour
    return inicio <= hora_local < fim


def rajada(ocorrida_em: datetime, instantes_anteriores: Sequence[datetime],
           max_transacoes: int, janela: timedelta) -> bool:
    """Mais de N transações (contando a atual) dentro dos últimos M minutos."""
    inicio_janela = ocorrida_em - janela
    na_janela = sum(1 for instante in instantes_anteriores
                    if inicio_janela < instante <= ocorrida_em)
    return na_janela + 1 > max_transacoes


@dataclass(frozen=True)
class MotorRegras:
    parametros: ParametrosRegras

    def avaliar(self, transacao: Transacao, historico: Sequence[Evento]) -> tuple[str, ...]:
        """Devolve os nomes das regras disparadas (tupla vazia = nenhuma)."""
        p = self.parametros
        disparadas: list[str] = []

        if valor_acima_p99(transacao.valor, [v for _, v in historico],
                           p.regra_percentil_min_historico):
            disparadas.append(VALOR_ACIMA_P99)

        if horario_madrugada(transacao.ocorrida_em, ZoneInfo(p.fuso_horario),
                             p.regra_madrugada_inicio, p.regra_madrugada_fim):
            disparadas.append(HORARIO_MADRUGADA)

        if rajada(transacao.ocorrida_em, [t for t, _ in historico],
                  p.regra_rajada_max_transacoes,
                  timedelta(minutes=p.regra_rajada_janela_minutos)):
            disparadas.append(RAJADA_TRANSACOES)

        return tuple(disparadas)
