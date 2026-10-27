# scripts/avaliar_offline.py
"""Roda o motor completo sobre dados sintéticos, sem Kafka nem banco, e imprime as métricas.

Útil para calibrar regras e modelo antes de subir a infraestrutura.
Uso: python scripts/avaliar_offline.py [--semente 7] [--sem-modelo]
"""

import argparse
import json

from antifraude.config import obter_parametros_regras
from antifraude.gerador import gerar_transacoes
from antifraude.metricas import calcular_metricas
from antifraude.motor import MotorAntifraude
from antifraude.repositorio import RepositorioMemoria


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semente", type=int, default=7)
    parser.add_argument("--sem-modelo", action="store_true", help="avaliar apenas as regras")
    args = parser.parse_args()

    parametros = obter_parametros_regras()
    motor = MotorAntifraude(parametros) if args.sem_modelo \
        else MotorAntifraude.com_modelo_em_disco(parametros)
    repositorio = RepositorioMemoria()

    for transacao in gerar_transacoes(semente=args.semente):
        repositorio.salvar(motor.avaliar(transacao))

    relatorio = calcular_metricas(repositorio.contagens_rotuladas())
    print(json.dumps(relatorio.para_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
