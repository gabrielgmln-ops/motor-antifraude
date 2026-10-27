# scripts/verificar_infra.py
"""Verifica se PostgreSQL e Kafka estão no ar, cria a tabela e os tópicos do projeto.

Uso: python scripts/verificar_infra.py
Pode ser executado várias vezes: o que já existir é mantido.
"""

import sys

import psycopg
from confluent_kafka.admin import AdminClient, NewTopic

from antifraude.config import obter_configuracao
from antifraude.repositorio import RepositorioPostgres

# Partições: 3 permitem até 3 consumidores paralelos no mesmo grupo
NUM_PARTICOES = 3
FATOR_REPLICACAO = 1  # um único broker no ambiente local


def verificar_postgres() -> bool:
    cfg = obter_configuracao()
    try:
        with psycopg.connect(cfg.dsn_postgres, connect_timeout=5) as conexao:
            versao = conexao.execute("SELECT version()").fetchone()[0]
        RepositorioPostgres(cfg.dsn_postgres).criar_schema()
        print(f"[OK] PostgreSQL conectado: {versao.split(',')[0]}")
        print("[OK] Tabela 'decisoes' disponível")
        return True
    except psycopg.OperationalError as erro:
        print(f"[FALHA] PostgreSQL indisponível: {erro}")
        return False


def verificar_kafka() -> bool:
    cfg = obter_configuracao()
    admin = AdminClient({"bootstrap.servers": cfg.kafka_bootstrap_servers})

    try:
        metadados = admin.list_topics(timeout=10)
    except Exception as erro:  # confluent-kafka lança KafkaException genérica
        print(f"[FALHA] Kafka indisponível: {erro}")
        return False

    print(f"[OK] Kafka conectado: {len(metadados.brokers)} broker(s)")

    desejados = [cfg.kafka_topico_transacoes, cfg.kafka_topico_decisoes]
    faltantes = [t for t in desejados if t not in metadados.topics]

    if faltantes:
        novos = [NewTopic(t, num_partitions=NUM_PARTICOES, replication_factor=FATOR_REPLICACAO)
                 for t in faltantes]
        # create_topics é assíncrono: devolve um "future" por tópico
        for topico, futuro in admin.create_topics(novos).items():
            try:
                futuro.result()
                print(f"[OK] Tópico criado: {topico}")
            except Exception as erro:
                print(f"[FALHA] Não foi possível criar {topico}: {erro}")
                return False

    for topico in desejados:
        print(f"[OK] Tópico disponível: {topico}")
    return True


def main() -> int:
    print("Verificando infraestrutura do Motor Antifraude")
    resultados = [verificar_postgres(), verificar_kafka()]
    if all(resultados):
        print("Infraestrutura pronta.")
        return 0
    print("Infraestrutura com problemas. Confira 'docker compose ps'.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
