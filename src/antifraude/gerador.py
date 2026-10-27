# src/antifraude/gerador.py
"""Gerador de transações SINTÉTICAS com fraudes rotuladas.

Nenhum dado real é usado. Cada conta recebe um "perfil" (ticket médio e ritmo de uso)
e, sobre esse comportamento normal, injetamos três tipos de fraude conhecidos:

  valor_alto -> um único valor muito acima do padrão da conta (cartão clonado, golpe)
  madrugada  -> valor moderadamente alto entre 1h e 4h (conta invadida enquanto o dono dorme)
  rajada     -> 5 a 8 transações em poucos minutos (teste de cartão / esvaziamento de conta)

O rótulo fica em Transacao.rotulo_fraude e só serve para medir precisão e recall.
A semente fixa torna o conjunto reprodutível (mesma semente = mesmos dados).
"""

import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from antifraude.dominio import CENTAVOS, Transacao

FUSO_PADRAO = ZoneInfo("America/Sao_Paulo")

# Peso relativo de cada hora do dia para clientes legítimos (pouquíssimo de madrugada)
PESOS_HORA_NORMAL = [
    0.2, 0.1, 0.1, 0.1, 0.1, 0.3,   # 0h-5h
    1.0, 2.5, 4.0, 5.0, 5.5, 6.0,   # 6h-11h
    7.0, 6.5, 5.5, 5.5, 5.5, 6.0,   # 12h-17h
    6.5, 6.5, 6.0, 5.0, 3.5, 1.5,   # 18h-23h
]
TIPOS_FRAUDE = ("valor_alto", "madrugada", "rajada")


@dataclass(frozen=True)
class PerfilConta:
    conta_id: str
    ticket_medio: Decimal
    transacoes_por_dia: float


def _dinheiro(rng: random.Random, media: Decimal, dispersao: float = 0.6) -> Decimal:
    """Sorteia um valor em torno da média.

    A distribuição log-normal é contínua (o random só sorteia float); o resultado é
    imediatamente convertido para CENTAVOS INTEIROS e então para Decimal. O float não
    sai desta função e nunca participa de soma ou comparação de dinheiro.
    """
    fator = rng.lognormvariate(0.0, dispersao)
    centavos = max(1, round(int(media * 100) * fator))
    return (Decimal(centavos) / 100).quantize(CENTAVOS)


def _instante(rng: random.Random, dia: date, horas: range | list[int],
              pesos: list[float] | None = None) -> datetime:
    """Instante aleatório no dia, em horário local, convertido para UTC."""
    hora = rng.choices(list(horas), weights=pesos)[0]
    local = datetime(dia.year, dia.month, dia.day, hora, rng.randrange(60), rng.randrange(60),
                     tzinfo=FUSO_PADRAO)
    return local.astimezone(ZoneInfo("UTC"))


def _id(rng: random.Random) -> str:
    # UUID derivado do gerador semeado (uuid4 usaria aleatoriedade do sistema)
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def criar_perfis(rng: random.Random, n_contas: int) -> list[PerfilConta]:
    perfis = []
    for i in range(n_contas):
        ticket = (Decimal(rng.randrange(30_00, 1_500_00)) / 100).quantize(CENTAVOS)
        perfis.append(PerfilConta(f"conta-{i:04d}", ticket, rng.uniform(1.0, 5.0)))
    return perfis


def _fraude(rng: random.Random, perfil: PerfilConta, dia: date, tipo: str) -> list[Transacao]:
    if tipo == "valor_alto":
        quando = _instante(rng, dia, range(24), PESOS_HORA_NORMAL)
        valor = _dinheiro(rng, perfil.ticket_medio * rng.randrange(15, 41), 0.2)
        return [Transacao(_id(rng), perfil.conta_id, valor, quando, rotulo_fraude=True)]

    if tipo == "madrugada":
        quando = _instante(rng, dia, [1, 2, 3, 4])
        valor = _dinheiro(rng, perfil.ticket_medio * rng.randrange(3, 9), 0.3)
        return [Transacao(_id(rng), perfil.conta_id, valor, quando, rotulo_fraude=True)]

    # rajada: várias transações de valor parecido, poucos segundos ou minutos entre elas
    inicio = _instante(rng, dia, range(24), PESOS_HORA_NORMAL)
    transacoes = []
    quando = inicio
    for _ in range(rng.randrange(5, 9)):
        quando = quando + timedelta(seconds=rng.randrange(10, 50))
        valor = _dinheiro(rng, perfil.ticket_medio * Decimal("0.8"), 0.3)
        transacoes.append(Transacao(_id(rng), perfil.conta_id, valor, quando, rotulo_fraude=True))
    return transacoes


def gerar_transacoes(n_contas: int = 200, dias: int = 30, taxa_fraude_dia: float = 0.02,
                     semente: int = 42, primeiro_dia: date = date(2026, 9, 1)) -> list[Transacao]:
    """Gera o conjunto completo, em ordem cronológica (como chegaria pela Ledger API).

    taxa_fraude_dia: probabilidade de uma conta sofrer um ataque em um dia qualquer.
    """
    rng = random.Random(semente)
    perfis = criar_perfis(rng, n_contas)
    transacoes: list[Transacao] = []

    for perfil in perfis:
        for d in range(dias):
            dia = primeiro_dia + timedelta(days=d)

            # Comportamento normal: quantidade ~ Poisson aproximada por Bernoulli por "slot"
            quantidade = sum(1 for _ in range(10) if rng.random() < perfil.transacoes_por_dia / 10)
            for _ in range(quantidade):
                valor = _dinheiro(rng, perfil.ticket_medio)
                quando = _instante(rng, dia, range(24), PESOS_HORA_NORMAL)
                transacoes.append(
                    Transacao(_id(rng), perfil.conta_id, valor, quando, rotulo_fraude=False)
                )

            # Fraude (rara), só depois de alguns dias: o golpista não chega no 1º dia da conta
            if d >= 3 and rng.random() < taxa_fraude_dia:
                transacoes.extend(_fraude(rng, perfil, dia, rng.choice(TIPOS_FRAUDE)))

    transacoes.sort(key=lambda t: (t.ocorrida_em, t.transacao_id))
    return transacoes
