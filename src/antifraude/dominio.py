# src/antifraude/dominio.py
"""Tipos do domínio: transação recebida da Ledger API e decisão do motor.

Contrato do evento JSON (tópico transacoes.eventos):
    {
      "transacao_id": "c0a8...",          # identificador único (UUID)
      "conta_id": "conta-0042",
      "valor": "1234.56",                 # STRING, para não perder precisão
      "moeda": "BRL",
      "ocorrida_em": "2026-10-01T14:03:00+00:00",
      "rotulo_fraude": true               # opcional: só existe em dados sintéticos
    }
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from enum import StrEnum

# Duas casas decimais; arredondamento bancário (meio para o par)
CENTAVOS = Decimal("0.01")


class ErroEventoInvalido(ValueError):
    """O evento recebido não respeita o contrato acima."""


class Classificacao(StrEnum):
    APROVADA = "APROVADA"
    SUSPEITA = "SUSPEITA"
    BLOQUEADA = "BLOQUEADA"


def para_dinheiro(valor: str | int | Decimal) -> Decimal:
    """Converte para Decimal com 2 casas. Recusa float de propósito."""
    if isinstance(valor, float):
        raise TypeError("Dinheiro não pode vir como float; envie string ou Decimal")
    try:
        convertido = Decimal(str(valor)).quantize(CENTAVOS, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as erro:
        raise ErroEventoInvalido(f"valor monetário inválido: {valor!r}") from erro
    if not convertido.is_finite() or convertido <= 0:
        raise ErroEventoInvalido(f"valor deve ser positivo: {valor!r}")
    return convertido


@dataclass(frozen=True, slots=True)
class Transacao:
    transacao_id: str
    conta_id: str
    valor: Decimal
    ocorrida_em: datetime
    moeda: str = "BRL"
    rotulo_fraude: bool | None = None

    @classmethod
    def de_dict(cls, dados: dict) -> "Transacao":
        """Valida e constrói a transação a partir do dicionário do evento."""
        try:
            ocorrida_em = datetime.fromisoformat(dados["ocorrida_em"])
            transacao = cls(
                transacao_id=str(dados["transacao_id"]),
                conta_id=str(dados["conta_id"]),
                valor=para_dinheiro(dados["valor"]),
                ocorrida_em=ocorrida_em,
                moeda=str(dados.get("moeda", "BRL")),
                rotulo_fraude=dados.get("rotulo_fraude"),
            )
        except (KeyError, TypeError, ValueError) as erro:
            raise ErroEventoInvalido(f"evento inválido: {erro}") from erro
        if ocorrida_em.tzinfo is None:
            # Sem fuso não dá para saber se foi de madrugada; recusamos em vez de chutar
            raise ErroEventoInvalido("ocorrida_em precisa ter fuso horário")
        return transacao

    @classmethod
    def de_json(cls, bruto: bytes | str) -> "Transacao":
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as erro:
            raise ErroEventoInvalido(f"JSON malformado: {erro}") from erro
        if not isinstance(dados, dict):
            raise ErroEventoInvalido("o evento deve ser um objeto JSON")
        return cls.de_dict(dados)

    def para_dict(self) -> dict:
        dados: dict[str, object] = {
            "transacao_id": self.transacao_id,
            "conta_id": self.conta_id,
            "valor": str(self.valor),  # Decimal vira string, nunca número JSON
            "moeda": self.moeda,
            "ocorrida_em": self.ocorrida_em.isoformat(),
        }
        if self.rotulo_fraude is not None:
            dados["rotulo_fraude"] = self.rotulo_fraude
        return dados

    def para_json(self) -> str:
        return json.dumps(self.para_dict())


@dataclass(frozen=True, slots=True)
class Decisao:
    transacao: Transacao
    classificacao: Classificacao
    regras_disparadas: tuple[str, ...] = field(default_factory=tuple)
    # Score do IsolationForest (negativo = mais anômalo); None se não houver modelo
    score_anomalia: Decimal | None = None

    def para_json(self) -> str:
        return json.dumps(
            {
                "transacao_id": self.transacao.transacao_id,
                "conta_id": self.transacao.conta_id,
                "valor": str(self.transacao.valor),
                "classificacao": self.classificacao.value,
                "regras_disparadas": list(self.regras_disparadas),
                "score_anomalia": None if self.score_anomalia is None
                else str(self.score_anomalia),
            }
        )
