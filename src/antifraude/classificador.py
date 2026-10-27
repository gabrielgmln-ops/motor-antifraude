# src/antifraude/classificador.py
"""Combina regras e modelo em uma classificação final.

Política (explícita, para o comitê de risco poder auditar):
  BLOQUEADA -> 2 ou mais regras, OU 1 regra confirmada pelo modelo de anomalia
  SUSPEITA  -> exatamente 1 regra, OU apenas o modelo acusou anomalia
  APROVADA  -> nenhum sinal
"""

from antifraude.dominio import Classificacao


def classificar(regras_disparadas: tuple[str, ...], anomalo: bool) -> Classificacao:
    quantidade = len(regras_disparadas)
    if quantidade >= 2 or (quantidade == 1 and anomalo):
        return Classificacao.BLOQUEADA
    if quantidade == 1 or anomalo:
        return Classificacao.SUSPEITA
    return Classificacao.APROVADA
