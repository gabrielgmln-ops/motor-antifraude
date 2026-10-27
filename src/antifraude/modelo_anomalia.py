# src/antifraude/modelo_anomalia.py
"""Detecção de anomalia com IsolationForest.

Sobre Decimal x float: dinheiro é sempre Decimal no domínio, nas regras e no banco.
O scikit-learn, porém, só trabalha com float. Por isso o modelo nunca recebe o valor
em reais: recebe grandezas ADIMENSIONAIS derivadas (logaritmo da razão valor/mediana,
seno/cosseno da hora, contagens). Nenhum valor monetário é calculado em float.
"""

import math
import statistics
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from antifraude.config import ParametrosRegras
from antifraude.dominio import Transacao
from antifraude.estado import EstadoContas, Evento

# Muda quando a lista de features mudar; impede carregar um modelo incompatível
VERSAO_FEATURES = 1
NOMES_FEATURES = (
    "log_razao_valor_mediana",
    "hora_seno",
    "hora_cosseno",
    "transacoes_ultimos_10min",
    "log_minutos_desde_ultima",
)
MINUTOS_SEM_HISTORICO = 24 * 60  # conta sem histórico: tratamos como "um dia sem uso"
SCORE_CASAS = Decimal("0.00001")


def extrair_features(transacao: Transacao, historico: Sequence[Evento],
                     fuso: ZoneInfo) -> list[float]:
    """Transforma transação + histórico anterior em um vetor numérico."""
    valores = [v for _, v in historico]
    if valores:
        # A divisão acontece em Decimal; só a razão (sem unidade) vira float
        mediana = statistics.median(valores)
        razao = float(transacao.valor / mediana)
        log_razao = math.log(razao)
    else:
        log_razao = 0.0

    hora_local = transacao.ocorrida_em.astimezone(fuso)
    # Hora em círculo: 23h e 0h ficam próximas, o que um número de 0 a 23 não expressa
    fracao_dia = (hora_local.hour * 60 + hora_local.minute) / (24 * 60)
    hora_seno = math.sin(2 * math.pi * fracao_dia)
    hora_cosseno = math.cos(2 * math.pi * fracao_dia)

    inicio_janela = transacao.ocorrida_em - timedelta(minutes=10)
    recentes = sum(1 for t, _ in historico if t > inicio_janela)

    if historico:
        minutos = (transacao.ocorrida_em - historico[-1][0]).total_seconds() / 60
    else:
        minutos = MINUTOS_SEM_HISTORICO
    log_minutos = math.log1p(max(minutos, 0.0))

    return [log_razao, hora_seno, hora_cosseno, float(recentes), log_minutos]


def extrair_matriz(transacoes: Iterable[Transacao], parametros: ParametrosRegras) -> np.ndarray:
    """Percorre as transações em ordem, como o motor faria, e monta a matriz de features."""
    fuso = ZoneInfo(parametros.fuso_horario)
    estado = EstadoContas()
    linhas = []
    for transacao in transacoes:
        linhas.append(extrair_features(transacao, estado.historico(transacao.conta_id), fuso))
        estado.registrar(transacao)
    return np.array(linhas, dtype=float)


class DetectorAnomalia:
    def __init__(self, modelo: IsolationForest, limiar: float) -> None:
        self.modelo = modelo
        # Score abaixo do limiar = anomalia
        self.limiar = limiar

    @classmethod
    def treinar(cls, matriz: np.ndarray, taxa_anomalia: float = 0.03,
                semente: int = 42) -> "DetectorAnomalia":
        """Treina sem rótulos (não supervisionado) e calibra o limiar pela taxa desejada.

        taxa_anomalia=0.03 significa: no máximo ~3% das transações de treino seriam
        consideradas anômalas. É um parâmetro de negócio (custo de revisão manual).
        """
        # 100 árvores: bom equilíbrio entre estabilidade do score e latência por transação
        modelo = IsolationForest(n_estimators=100, contamination="auto", random_state=semente)
        modelo.fit(matriz)
        scores = modelo.decision_function(matriz)
        limiar = float(np.percentile(scores, taxa_anomalia * 100))
        return cls(modelo, limiar)

    def pontuar(self, features: list[float]) -> Decimal:
        score = self.modelo.decision_function(np.array([features], dtype=float))[0]
        return Decimal(str(score)).quantize(SCORE_CASAS)

    def eh_anomalo(self, score: Decimal) -> bool:
        return score < Decimal(str(self.limiar))

    def salvar(self, caminho: str | Path) -> None:
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "modelo": self.modelo,
                "limiar": self.limiar,
                "versao_features": VERSAO_FEATURES,
                "treinado_em": datetime.now().isoformat(timespec="seconds"),
            },
            caminho,
        )

    @classmethod
    def carregar(cls, caminho: str | Path) -> "DetectorAnomalia":
        """Carrega um modelo salvo por este projeto.

        Atenção: joblib usa pickle, que executa código ao desserializar.
        Só carregue arquivos gerados por você mesmo, nunca de fontes externas.
        """
        pacote = joblib.load(caminho)
        if pacote.get("versao_features") != VERSAO_FEATURES:
            raise ValueError("modelo treinado com outra versão de features; treine novamente")
        return cls(pacote["modelo"], pacote["limiar"])
