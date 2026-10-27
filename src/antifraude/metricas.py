# src/antifraude/metricas.py
"""Precisão e recall sobre dados sintéticos rotulados.

Positivo = "o motor sinalizou" (SUSPEITA ou BLOQUEADA).
  precisão = das transações sinalizadas, quantas eram fraude de fato
  recall   = das fraudes reais, quantas o motor sinalizou
Também calculamos a mesma visão considerando apenas BLOQUEADA, que é a decisão
com impacto direto no cliente (transação negada).

A entrada são CONTAGENS agregadas, para que o banco faça o GROUP BY e a API não
precise trazer milhões de linhas para a memória.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass

from antifraude.dominio import Classificacao, Decisao

# Chave da contagem: (rótulo verdadeiro, classificação do motor)
Contagens = Mapping[tuple[bool, Classificacao], int]


@dataclass(frozen=True)
class MatrizConfusao:
    verdadeiro_positivo: int
    falso_positivo: int
    falso_negativo: int
    verdadeiro_negativo: int

    @property
    def precisao(self) -> float | None:
        sinalizadas = self.verdadeiro_positivo + self.falso_positivo
        return None if sinalizadas == 0 else round(self.verdadeiro_positivo / sinalizadas, 4)

    @property
    def recall(self) -> float | None:
        fraudes = self.verdadeiro_positivo + self.falso_negativo
        return None if fraudes == 0 else round(self.verdadeiro_positivo / fraudes, 4)

    @property
    def f1(self) -> float | None:
        p, r = self.precisao, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return round(2 * p * r / (p + r), 4)

    def para_dict(self) -> dict:
        return {**asdict(self), "precisao": self.precisao, "recall": self.recall, "f1": self.f1}


@dataclass(frozen=True)
class RelatorioMetricas:
    total_rotuladas: int
    total_fraudes: int
    por_classificacao: dict[str, int]
    sinalizadas: MatrizConfusao
    bloqueadas: MatrizConfusao

    def para_dict(self) -> dict:
        return {
            "total_rotuladas": self.total_rotuladas,
            "total_fraudes": self.total_fraudes,
            "por_classificacao": self.por_classificacao,
            "sinalizadas": self.sinalizadas.para_dict(),
            "bloqueadas": self.bloqueadas.para_dict(),
        }


def _matriz(contagens: Contagens, positivas: set[Classificacao]) -> MatrizConfusao:
    vp = fp = fn = vn = 0
    for (fraude, classificacao), n in contagens.items():
        sinalizou = classificacao in positivas
        if fraude and sinalizou:
            vp += n
        elif not fraude and sinalizou:
            fp += n
        elif fraude:
            fn += n
        else:
            vn += n
    return MatrizConfusao(vp, fp, fn, vn)


def calcular_metricas(contagens: Contagens) -> RelatorioMetricas:
    por_classificacao = {c.value: 0 for c in Classificacao}
    for (_, classificacao), n in contagens.items():
        por_classificacao[classificacao.value] += n
    return RelatorioMetricas(
        total_rotuladas=sum(contagens.values()),
        total_fraudes=sum(n for (fraude, _), n in contagens.items() if fraude),
        por_classificacao=por_classificacao,
        sinalizadas=_matriz(contagens, {Classificacao.SUSPEITA, Classificacao.BLOQUEADA}),
        bloqueadas=_matriz(contagens, {Classificacao.BLOQUEADA}),
    )


def contar_decisoes(decisoes: Iterable[Decisao]) -> Counter:
    """Equivalente em memória do GROUP BY do PostgreSQL (ignora decisões sem rótulo)."""
    return Counter(
        (d.transacao.rotulo_fraude, d.classificacao)
        for d in decisoes
        if d.transacao.rotulo_fraude is not None
    )
