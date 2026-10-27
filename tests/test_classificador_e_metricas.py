# tests/test_classificador_e_metricas.py
import pytest

from antifraude.classificador import classificar
from antifraude.dominio import Classificacao, Decisao
from antifraude.metricas import MatrizConfusao, calcular_metricas, contar_decisoes

A, S, B = Classificacao.APROVADA, Classificacao.SUSPEITA, Classificacao.BLOQUEADA


@pytest.mark.parametrize(
    ("regras", "anomalo", "esperado"),
    [
        ((), False, A),
        ((), True, S),
        (("R1",), False, S),
        (("R1",), True, B),
        (("R1", "R2"), False, B),
        (("R1", "R2", "R3"), True, B),
    ],
)
def test_politica_de_classificacao(regras, anomalo, esperado):
    assert classificar(regras, anomalo) is esperado


def test_calcular_metricas():
    contagens = {
        (True, B): 6,   # fraude bloqueada
        (True, S): 2,   # fraude marcada como suspeita
        (True, A): 2,   # fraude que passou
        (False, S): 8,  # legítima incomodada
        (False, A): 82,
    }
    r = calcular_metricas(contagens)

    assert r.total_rotuladas == 100
    assert r.total_fraudes == 10
    assert r.por_classificacao == {"APROVADA": 84, "SUSPEITA": 10, "BLOQUEADA": 6}
    # Sinalizadas: VP=8, FP=8, FN=2
    assert r.sinalizadas.precisao == 0.5
    assert r.sinalizadas.recall == 0.8
    assert r.sinalizadas.f1 == pytest.approx(0.6154, abs=1e-4)
    # Só bloqueadas: VP=6, FP=0, FN=4
    assert r.bloqueadas.precisao == 1.0
    assert r.bloqueadas.recall == 0.6
    assert r.para_dict()["sinalizadas"]["verdadeiro_positivo"] == 8


def test_metricas_sem_dados_nao_dividem_por_zero():
    m = MatrizConfusao(0, 0, 0, 0)
    assert m.precisao is None and m.recall is None and m.f1 is None
    assert MatrizConfusao(0, 3, 4, 0).f1 is None  # precisão e recall zero


def test_contar_decisoes_ignora_sem_rotulo(fabrica_transacao):
    decisoes = [
        Decisao(fabrica_transacao(rotulo_fraude=True), B),
        Decisao(fabrica_transacao(rotulo_fraude=False), A),
        Decisao(fabrica_transacao(rotulo_fraude=None), A),
    ]
    assert contar_decisoes(decisoes) == {(True, B): 1, (False, A): 1}
