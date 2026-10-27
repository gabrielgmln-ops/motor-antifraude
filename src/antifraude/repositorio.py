# src/antifraude/repositorio.py
"""Persistência das decisões.

Duas implementações com a mesma interface (Protocol):
  RepositorioPostgres -> produção/desenvolvimento, PostgreSQL via psycopg 3
  RepositorioMemoria  -> testes e avaliação offline, sem infraestrutura
"""

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from antifraude.dominio import Classificacao, Decisao
from antifraude.estado import Evento
from antifraude.metricas import Contagens, contar_decisoes

# Mesmo DDL de sql/001_schema.sql (sem os comentários). Fica embutido para o pacote
# funcionar instalado sem a pasta sql/, como acontece dentro da imagem Docker.
SCHEMA = """
CREATE TABLE IF NOT EXISTS decisoes (
    transacao_id      TEXT PRIMARY KEY,
    conta_id          TEXT          NOT NULL,
    valor             NUMERIC(18,2) NOT NULL CHECK (valor > 0),
    moeda             CHAR(3)       NOT NULL DEFAULT 'BRL',
    ocorrida_em       TIMESTAMPTZ   NOT NULL,
    classificacao     TEXT          NOT NULL
                      CHECK (classificacao IN ('APROVADA', 'SUSPEITA', 'BLOQUEADA')),
    regras_disparadas TEXT[]        NOT NULL DEFAULT '{}',
    score_anomalia    NUMERIC(8,5),
    rotulo_fraude     BOOLEAN,
    decidida_em       TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_decisoes_conta_data ON decisoes (conta_id, ocorrida_em DESC);
CREATE INDEX IF NOT EXISTS idx_decisoes_decidida_em ON decisoes (decidida_em DESC);
"""


class Repositorio(Protocol):
    def salvar(self, decisao: Decisao) -> bool: ...
    def contagens_rotuladas(self) -> Contagens: ...
    def listar_recentes(self, limite: int) -> list[dict]: ...
    def historico_recente(self, por_conta: int) -> dict[str, list[Evento]]: ...


def _linha(decisao: Decisao) -> dict:
    t = decisao.transacao
    return {
        "transacao_id": t.transacao_id,
        "conta_id": t.conta_id,
        "valor": t.valor,
        "moeda": t.moeda,
        "ocorrida_em": t.ocorrida_em,
        "classificacao": decisao.classificacao.value,
        "regras_disparadas": list(decisao.regras_disparadas),
        "score_anomalia": decisao.score_anomalia,
        "rotulo_fraude": t.rotulo_fraude,
    }


class RepositorioMemoria:
    def __init__(self) -> None:
        self._decisoes: dict[str, Decisao] = {}

    def salvar(self, decisao: Decisao) -> bool:
        """Retorna False se a transação já tinha decisão (idempotência)."""
        chave = decisao.transacao.transacao_id
        if chave in self._decisoes:
            return False
        self._decisoes[chave] = decisao
        return True

    def contagens_rotuladas(self) -> Counter:
        return contar_decisoes(self._decisoes.values())

    def listar_recentes(self, limite: int) -> list[dict]:
        # Dicionários do Python preservam a ordem de inserção: as últimas são as mais novas
        return [_linha(d) for d in list(self._decisoes.values())[-limite:][::-1]]

    def historico_recente(self, por_conta: int) -> dict[str, list[Evento]]:
        historicos: dict[str, list[Evento]] = defaultdict(list)
        for d in self._decisoes.values():
            historicos[d.transacao.conta_id].append((d.transacao.ocorrida_em, d.transacao.valor))
        return {conta: sorted(eventos)[-por_conta:] for conta, eventos in historicos.items()}


class RepositorioPostgres:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conectar(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=5)

    def criar_schema(self) -> None:
        with self._conectar() as conexao:
            conexao.execute(SCHEMA)

    def salvar(self, decisao: Decisao) -> bool:
        # ON CONFLICT DO NOTHING: reentrega da mesma mensagem pelo Kafka não duplica nada
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO decisoes (transacao_id, conta_id, valor, moeda, ocorrida_em,
                    classificacao, regras_disparadas, score_anomalia, rotulo_fraude)
                VALUES (%(transacao_id)s, %(conta_id)s, %(valor)s, %(moeda)s, %(ocorrida_em)s,
                    %(classificacao)s, %(regras_disparadas)s, %(score_anomalia)s,
                    %(rotulo_fraude)s)
                ON CONFLICT (transacao_id) DO NOTHING
                """,
                _linha(decisao),
            )
            return cursor.rowcount == 1

    def contagens_rotuladas(self) -> dict[tuple[bool, Classificacao], int]:
        with self._conectar() as conexao:
            linhas = conexao.execute(
                """
                SELECT rotulo_fraude, classificacao, count(*)
                FROM decisoes
                WHERE rotulo_fraude IS NOT NULL
                GROUP BY rotulo_fraude, classificacao
                """
            ).fetchall()
        return {(rotulo, Classificacao(classe)): n for rotulo, classe, n in linhas}

    def listar_recentes(self, limite: int) -> list[dict]:
        with self._conectar() as conexao:
            conexao.row_factory = dict_row
            return conexao.execute(
                """
                SELECT transacao_id, conta_id, valor, moeda, ocorrida_em, classificacao,
                       regras_disparadas, score_anomalia, rotulo_fraude
                FROM decisoes ORDER BY decidida_em DESC, ocorrida_em DESC LIMIT %s
                """,
                (limite,),
            ).fetchall()

    def historico_recente(self, por_conta: int) -> dict[str, list[Evento]]:
        """Últimos N eventos de cada conta, para reconstruir o estado após reinício."""
        with self._conectar() as conexao:
            linhas = conexao.execute(
                """
                SELECT conta_id, ocorrida_em, valor FROM (
                    SELECT conta_id, ocorrida_em, valor,
                           row_number() OVER (PARTITION BY conta_id
                                              ORDER BY ocorrida_em DESC) AS posicao
                    FROM decisoes
                ) recentes
                WHERE posicao <= %s
                """,
                (por_conta,),
            ).fetchall()
        historicos: dict[str, list[tuple[datetime, Decimal]]] = defaultdict(list)
        for conta_id, ocorrida_em, valor in linhas:
            historicos[conta_id].append((ocorrida_em, valor))
        return dict(historicos)
