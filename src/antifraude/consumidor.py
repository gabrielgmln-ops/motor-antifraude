# src/antifraude/consumidor.py
"""Consumidor Kafka: lê transações, decide, grava e publica a decisão.

Garantia de entrega: "pelo menos uma vez" (at-least-once).
  - enable.auto.commit = false: o offset só é confirmado DEPOIS de gravar no banco.
  - Se o processo cair entre gravar e confirmar, a mensagem volta; o INSERT com
    ON CONFLICT DO NOTHING torna o reprocessamento inofensivo (idempotência).

Execução: python -m antifraude.consumidor
"""

import logging
import signal
from dataclasses import dataclass

from confluent_kafka import Consumer, KafkaError, Message, Producer

from antifraude.config import Configuracao, obter_configuracao
from antifraude.dominio import Decisao, ErroEventoInvalido, Transacao
from antifraude.estado import MAX_EVENTOS_POR_CONTA
from antifraude.motor import MotorAntifraude
from antifraude.repositorio import Repositorio, RepositorioPostgres

log = logging.getLogger("antifraude.consumidor")


@dataclass
class Estatisticas:
    processadas: int = 0
    duplicadas: int = 0
    invalidas: int = 0


def processar_mensagem(valor: bytes, motor: MotorAntifraude, repositorio: Repositorio,
                       estatisticas: Estatisticas) -> Decisao | None:
    """Lógica de uma mensagem, isolada do Kafka para poder ser testada sem broker.

    Retorna a decisão, ou None quando a mensagem é inválida ou já foi processada.
    """
    try:
        transacao = Transacao.de_json(valor)
    except ErroEventoInvalido as erro:
        # Mensagem envenenada: registrar e seguir, para não travar a partição inteira
        estatisticas.invalidas += 1
        log.error("Mensagem descartada: %s", erro)
        return None

    decisao = motor.avaliar(transacao)
    if not repositorio.salvar(decisao):
        estatisticas.duplicadas += 1
        log.info("Transação %s já decidida anteriormente", transacao.transacao_id)
        return None

    estatisticas.processadas += 1
    return decisao


def _criar_consumidor(cfg: Configuracao) -> Consumer:  # pragma: no cover - exige broker
    return Consumer({
        "bootstrap.servers": cfg.kafka_bootstrap_servers,
        "group.id": cfg.kafka_grupo_consumidor,
        "enable.auto.commit": False,
        # Grupo novo começa do início do tópico: nenhuma transação fica sem decisão
        "auto.offset.reset": "earliest",
    })


def executar() -> None:  # pragma: no cover - laço de infraestrutura, coberto pelo teste manual
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = obter_configuracao()

    repositorio = RepositorioPostgres(cfg.dsn_postgres)
    repositorio.criar_schema()

    motor = MotorAntifraude.com_modelo_em_disco(cfg)
    motor.estado.carregar(repositorio.historico_recente(MAX_EVENTOS_POR_CONTA))
    log.info("Estado reconstruído para %d contas", len(motor.estado))

    consumidor = _criar_consumidor(cfg)
    produtor = Producer({"bootstrap.servers": cfg.kafka_bootstrap_servers})
    consumidor.subscribe([cfg.kafka_topico_transacoes])
    estatisticas = Estatisticas()

    rodando = True

    def parar(*_: object) -> None:
        nonlocal rodando
        rodando = False

    # Ctrl+C ou "docker stop" encerram com elegância (fecha o consumidor e sai do grupo)
    signal.signal(signal.SIGINT, parar)
    signal.signal(signal.SIGTERM, parar)

    log.info("Consumindo %s", cfg.kafka_topico_transacoes)
    try:
        while rodando:
            mensagem: Message | None = consumidor.poll(1.0)
            if mensagem is None:
                continue
            if mensagem.error():
                if mensagem.error().code() != KafkaError._PARTITION_EOF:
                    log.error("Erro do Kafka: %s", mensagem.error())
                continue

            decisao = processar_mensagem(mensagem.value(), motor, repositorio, estatisticas)
            if decisao is not None:
                produtor.produce(cfg.kafka_topico_decisoes, key=decisao.transacao.conta_id,
                                 value=decisao.para_json())
                produtor.poll(0)
                if decisao.classificacao != "APROVADA":
                    log.info("%s %s %s %s", decisao.classificacao, decisao.transacao.conta_id,
                             decisao.transacao.valor, ",".join(decisao.regras_disparadas))

            # Confirma o offset só depois que a decisão está no banco
            consumidor.commit(message=mensagem, asynchronous=False)

            if estatisticas.processadas and estatisticas.processadas % 1000 == 0:
                log.info("Progresso: %s", estatisticas)
    finally:
        produtor.flush(10)
        consumidor.close()
        log.info("Encerrado. %s", estatisticas)


if __name__ == "__main__":  # pragma: no cover
    executar()
