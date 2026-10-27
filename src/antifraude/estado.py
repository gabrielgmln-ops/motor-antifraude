# src/antifraude/estado.py
"""Estado em memória por conta: histórico recente de (instante, valor).

As regras e o modelo precisam conhecer o passado da conta. Esse histórico vive em
memória para a decisão ser rápida (sem ir ao banco a cada transação) e é recarregado
do PostgreSQL quando o motor reinicia (ver repositorio.historico_recente).
"""

from collections import deque
from datetime import datetime
from decimal import Decimal

from antifraude.dominio import Transacao

# Quantos eventos guardar por conta: suficiente para um percentil 99 estável
MAX_EVENTOS_POR_CONTA = 500

Evento = tuple[datetime, Decimal]


class EstadoContas:
    def __init__(self, max_por_conta: int = MAX_EVENTOS_POR_CONTA) -> None:
        self._max_por_conta = max_por_conta
        self._historicos: dict[str, deque[Evento]] = {}

    def historico(self, conta_id: str) -> deque[Evento]:
        """Eventos anteriores da conta, do mais antigo para o mais recente."""
        if conta_id not in self._historicos:
            # deque com maxlen descarta automaticamente o evento mais antigo
            self._historicos[conta_id] = deque(maxlen=self._max_por_conta)
        return self._historicos[conta_id]

    def registrar(self, transacao: Transacao) -> None:
        self.historico(transacao.conta_id).append((transacao.ocorrida_em, transacao.valor))

    def carregar(self, historicos: dict[str, list[Evento]]) -> None:
        """Repõe o estado a partir de dados persistidos (ordem cronológica)."""
        for conta_id, eventos in historicos.items():
            fila = self.historico(conta_id)
            fila.clear()
            fila.extend(sorted(eventos))

    def __len__(self) -> int:
        return len(self._historicos)
