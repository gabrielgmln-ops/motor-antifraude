# src/antifraude/motor.py
"""Orquestrador: uma transação entra, uma decisão sai.

É o mesmo código usado pelo consumidor Kafka e pela avaliação offline,
garantindo que a métrica medida é a do motor que roda de verdade.
"""

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from antifraude.classificador import classificar
from antifraude.config import ParametrosRegras
from antifraude.dominio import Decisao, Transacao
from antifraude.estado import EstadoContas
from antifraude.modelo_anomalia import DetectorAnomalia, extrair_features
from antifraude.regras import MotorRegras

log = logging.getLogger(__name__)


class MotorAntifraude:
    def __init__(self, parametros: ParametrosRegras, detector: DetectorAnomalia | None = None,
                 estado: EstadoContas | None = None) -> None:
        self.regras = MotorRegras(parametros)
        self.detector = detector
        self.estado = estado if estado is not None else EstadoContas()
        self._fuso = ZoneInfo(parametros.fuso_horario)

    @classmethod
    def com_modelo_em_disco(cls, parametros: ParametrosRegras) -> "MotorAntifraude":
        """Carrega o modelo se existir; sem ele, o motor funciona só com regras."""
        caminho = Path(parametros.caminho_modelo)
        if caminho.exists():
            log.info("Modelo de anomalia carregado de %s", caminho)
            return cls(parametros, DetectorAnomalia.carregar(caminho))
        log.warning("Modelo não encontrado em %s; operando apenas com regras", caminho)
        return cls(parametros)

    def avaliar(self, transacao: Transacao) -> Decisao:
        historico = self.estado.historico(transacao.conta_id)

        # 1) Regras olham apenas o passado (o histórico ainda não contém a transação atual)
        regras = self.regras.avaliar(transacao, historico)

        # 2) Modelo de anomalia (opcional)
        score = None
        anomalo = False
        if self.detector is not None:
            score = self.detector.pontuar(extrair_features(transacao, historico, self._fuso))
            anomalo = self.detector.eh_anomalo(score)

        # 3) Só agora a transação passa a fazer parte do histórico da conta
        self.estado.registrar(transacao)

        return Decisao(transacao, classificar(regras, anomalo), regras, score)
