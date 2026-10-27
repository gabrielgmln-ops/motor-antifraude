# scripts/gerar_transacoes.py
"""Gera transações sintéticas e as grava em CSV e/ou publica no Kafka.

Exemplos:
  python scripts/gerar_transacoes.py --csv dados/transacoes.csv
  python scripts/gerar_transacoes.py --kafka --semente 7
"""

import argparse
import csv
from collections import Counter
from pathlib import Path

from antifraude.gerador import gerar_transacoes


def gravar_csv(transacoes, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=["transacao_id", "conta_id", "valor",
                                                       "moeda", "ocorrida_em", "rotulo_fraude"])
        escritor.writeheader()
        for t in transacoes:
            escritor.writerow(t.para_dict())


def publicar_kafka(transacoes) -> None:  # pragma: no cover - exige broker
    from confluent_kafka import Producer

    from antifraude.config import obter_configuracao

    cfg = obter_configuracao()
    produtor = Producer({"bootstrap.servers": cfg.kafka_bootstrap_servers,
                         # Garante que a mensagem foi gravada pelo broker antes de confirmar
                         "acks": "all", "enable.idempotence": True})
    for i, t in enumerate(transacoes, start=1):
        # Chave = conta: todas as transações da conta vão para a mesma partição, em ordem
        produtor.produce(cfg.kafka_topico_transacoes, key=t.conta_id, value=t.para_json())
        if i % 1000 == 0:
            produtor.poll(0)
    pendentes = produtor.flush(30)
    if pendentes:
        raise SystemExit(f"{pendentes} mensagens não confirmadas pelo Kafka")
    print(f"Publicadas {len(transacoes)} mensagens em {cfg.kafka_topico_transacoes}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contas", type=int, default=200)
    parser.add_argument("--dias", type=int, default=30)
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--csv", type=Path, help="caminho do CSV de saída")
    parser.add_argument("--kafka", action="store_true", help="publicar no tópico de transações")
    args = parser.parse_args()

    transacoes = gerar_transacoes(n_contas=args.contas, dias=args.dias, semente=args.semente)
    fraudes = [t for t in transacoes if t.rotulo_fraude]
    contas_atacadas = Counter(t.conta_id for t in fraudes)
    print(f"Geradas {len(transacoes)} transações, {len(fraudes)} fraudulentas "
          f"({len(fraudes) / len(transacoes):.2%}) em {len(contas_atacadas)} contas")

    if args.csv:
        gravar_csv(transacoes, args.csv)
        print(f"CSV gravado em {args.csv}")
    if args.kafka:
        publicar_kafka(transacoes)


if __name__ == "__main__":
    main()
