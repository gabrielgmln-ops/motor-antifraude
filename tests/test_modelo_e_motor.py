# tests/test_modelo_e_motor.py
import math
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from antifraude.dominio import Classificacao
from antifraude.gerador import gerar_transacoes
from antifraude.metricas import calcular_metricas
from antifraude.modelo_anomalia import (
    NOMES_FEATURES,
    DetectorAnomalia,
    extrair_features,
    extrair_matriz,
)
from antifraude.motor import MotorAntifraude
from antifraude.regras import VALOR_ACIMA_P99
from antifraude.repositorio import RepositorioMemoria

SP = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(scope="module")
def detector() -> DetectorAnomalia:
    """Treina uma vez para o módulo inteiro (o treino leva alguns segundos)."""
    from antifraude.config import ParametrosRegras

    matriz = extrair_matriz(gerar_transacoes(n_contas=60, dias=20, semente=11),
                            ParametrosRegras(_env_file=None))
    return DetectorAnomalia.treinar(matriz)


def test_features_sem_historico(fabrica_transacao):
    features = extrair_features(fabrica_transacao(), [], SP)
    assert len(features) == len(NOMES_FEATURES)
    assert features[0] == 0.0
    assert features[3] == 0.0
    assert features[4] == pytest.approx(math.log1p(24 * 60))


def test_features_com_historico(fabrica_transacao):
    anterior = fabrica_transacao(valor="100.00", minutos=0)
    atual = fabrica_transacao(valor="1000.00", minutos=5)
    historico = [(anterior.ocorrida_em, anterior.valor)]
    features = extrair_features(atual, historico, SP)
    assert features[0] == pytest.approx(math.log(10))  # 10x a mediana
    assert features[3] == 1.0                          # uma transação nos últimos 10 min
    assert features[4] == pytest.approx(math.log1p(5))


def test_detector_pontua_extremo_como_anomalo(detector):
    normal = [0.0, 0.0, -1.0, 0.0, math.log1p(600)]
    extremo = [math.log(40), 0.7, 0.7, 7.0, math.log1p(0.2)]
    assert detector.pontuar(extremo) < detector.pontuar(normal)
    assert detector.eh_anomalo(detector.pontuar(extremo))
    assert isinstance(detector.pontuar(normal), Decimal)


def test_salvar_e_carregar_modelo(detector, tmp_path):
    caminho = tmp_path / "sub" / "modelo.joblib"
    detector.salvar(caminho)
    carregado = DetectorAnomalia.carregar(caminho)
    amostra = [0.5, 0.1, 0.9, 1.0, 2.0]
    assert carregado.pontuar(amostra) == detector.pontuar(amostra)
    assert carregado.limiar == detector.limiar


def test_carregar_recusa_versao_de_features_diferente(tmp_path):
    import joblib

    caminho = tmp_path / "antigo.joblib"
    joblib.dump({"modelo": None, "limiar": 0.0, "versao_features": 0}, caminho)
    with pytest.raises(ValueError):
        DetectorAnomalia.carregar(caminho)


def test_motor_sem_modelo_em_disco(parametros, tmp_path):
    parametros.caminho_modelo = str(tmp_path / "inexistente.joblib")
    motor = MotorAntifraude.com_modelo_em_disco(parametros)
    assert motor.detector is None


def test_motor_com_modelo_em_disco(parametros, detector, tmp_path):
    parametros.caminho_modelo = str(tmp_path / "m.joblib")
    detector.salvar(parametros.caminho_modelo)
    assert MotorAntifraude.com_modelo_em_disco(parametros).detector is not None


def test_motor_registra_historico_e_detecta_valor_alto(parametros, fabrica_transacao):
    motor = MotorAntifraude(parametros)
    # Uma transação por dia, sempre às 14h (fora da madrugada e sem rajada)
    for i in range(25):
        decisao = motor.avaliar(fabrica_transacao(valor="80.00", minutos=i * 1440))
        assert decisao.classificacao is Classificacao.APROVADA
    decisao = motor.avaliar(fabrica_transacao(valor="9000.00", minutos=25 * 1440))
    assert decisao.regras_disparadas == (VALOR_ACIMA_P99,)
    assert decisao.classificacao is Classificacao.SUSPEITA
    assert decisao.score_anomalia is None
    assert len(motor.estado.historico("conta-teste")) == 26


def test_ponta_a_ponta_tem_desempenho_minimo(parametros, detector):
    """Guarda de regressão: o motor completo precisa manter precisão e recall razoáveis."""
    motor = MotorAntifraude(parametros, detector)
    repositorio = RepositorioMemoria()
    for transacao in gerar_transacoes(n_contas=40, dias=20, semente=99):
        repositorio.salvar(motor.avaliar(transacao))
    relatorio = calcular_metricas(repositorio.contagens_rotuladas())
    assert relatorio.total_fraudes > 20
    assert relatorio.sinalizadas.recall >= 0.7
    assert relatorio.sinalizadas.precisao >= 0.2
    assert relatorio.bloqueadas.precisao >= 0.7
