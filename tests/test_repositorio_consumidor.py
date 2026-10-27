# tests/test_repositorio_consumidor.py
from decimal import Decimal

from antifraude.consumidor import Estatisticas, processar_mensagem
from antifraude.dominio import Classificacao, Decisao
from antifraude.motor import MotorAntifraude
from antifraude.repositorio import RepositorioMemoria


def test_repositorio_memoria_e_idempotente(fabrica_transacao):
    repositorio = RepositorioMemoria()
    decisao = Decisao(fabrica_transacao(rotulo_fraude=False), Classificacao.APROVADA)
    assert repositorio.salvar(decisao) is True
    assert repositorio.salvar(decisao) is False
    assert repositorio.contagens_rotuladas() == {(False, Classificacao.APROVADA): 1}


def test_repositorio_memoria_recentes_e_historico(fabrica_transacao):
    repositorio = RepositorioMemoria()
    for i in range(5):
        repositorio.salvar(Decisao(fabrica_transacao(valor=f"{i + 1}.00", minutos=i),
                                   Classificacao.APROVADA))
    recentes = repositorio.listar_recentes(2)
    assert [r["valor"] for r in recentes] == [Decimal("5.00"), Decimal("4.00")]
    historico = repositorio.historico_recente(por_conta=3)
    assert [v for _, v in historico["conta-teste"]] == [Decimal("3.00"), Decimal("4.00"),
                                                         Decimal("5.00")]


def test_processar_mensagem_valida_e_duplicada(parametros, fabrica_transacao):
    motor, repositorio, estatisticas = MotorAntifraude(parametros), RepositorioMemoria(), \
        Estatisticas()
    mensagem = fabrica_transacao(rotulo_fraude=False).para_json().encode()

    decisao = processar_mensagem(mensagem, motor, repositorio, estatisticas)
    assert decisao is not None and decisao.classificacao is Classificacao.APROVADA

    # Reentrega (at-least-once): não grava de novo
    assert processar_mensagem(mensagem, motor, repositorio, estatisticas) is None
    assert estatisticas == Estatisticas(processadas=1, duplicadas=1, invalidas=0)


def test_processar_mensagem_invalida_nao_derruba(parametros):
    estatisticas = Estatisticas()
    resultado = processar_mensagem(b"{lixo", MotorAntifraude(parametros), RepositorioMemoria(),
                                   estatisticas)
    assert resultado is None
    assert estatisticas.invalidas == 1
