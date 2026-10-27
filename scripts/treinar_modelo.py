# scripts/treinar_modelo.py
"""Treina o IsolationForest com dados sintéticos e salva em modelos/.

O treino usa a semente 42; a avaliação (avaliar_offline.py) usa outra semente,
para medir o modelo em contas e dias que ele nunca viu.

Uso: python scripts/treinar_modelo.py [--taxa-anomalia 0.03]
"""

import argparse

from antifraude.config import obter_parametros_regras
from antifraude.gerador import gerar_transacoes
from antifraude.modelo_anomalia import NOMES_FEATURES, DetectorAnomalia, extrair_matriz


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--taxa-anomalia", type=float, default=0.03)
    args = parser.parse_args()

    parametros = obter_parametros_regras()
    transacoes = gerar_transacoes(semente=args.semente)
    matriz = extrair_matriz(transacoes, parametros)
    print(f"Matriz de treino: {matriz.shape[0]} linhas x {matriz.shape[1]} features")
    print(f"Features: {', '.join(NOMES_FEATURES)}")

    # Treino NÃO supervisionado: os rótulos não são usados aqui
    detector = DetectorAnomalia.treinar(matriz, taxa_anomalia=args.taxa_anomalia,
                                        semente=args.semente)
    detector.salvar(parametros.caminho_modelo)
    print(f"Limiar calibrado: {detector.limiar:.5f}")
    print(f"Modelo salvo em {parametros.caminho_modelo}")


if __name__ == "__main__":
    main()
