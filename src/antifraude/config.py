# src/antifraude/config.py
"""Configuração central lida de variáveis de ambiente (ou do arquivo .env).

Nenhum segredo fica no código: se uma variável obrigatória faltar,
a aplicação falha ao iniciar com uma mensagem clara.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ParametrosRegras(BaseSettings):
    """Limiares das regras de negócio. Não contém segredos, por isso tem padrões."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    regra_rajada_max_transacoes: int = 4
    regra_rajada_janela_minutos: int = 10
    regra_percentil_min_historico: int = 20
    regra_madrugada_inicio: int = 0
    regra_madrugada_fim: int = 5
    fuso_horario: str = "America/Sao_Paulo"
    caminho_modelo: str = "modelos/isolation_forest.joblib"


class Configuracao(ParametrosRegras):
    """Parâmetros de infraestrutura do motor antifraude."""

    # --- PostgreSQL (obrigatórios, sem valor padrão para a senha) ---
    postgres_user: str
    postgres_password: SecretStr  # SecretStr evita que a senha apareça em logs e prints
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Kafka ---
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topico_transacoes: str = "transacoes.eventos"
    kafka_topico_decisoes: str = "antifraude.decisoes"
    kafka_grupo_consumidor: str = "motor-antifraude"

    @property
    def dsn_postgres(self) -> str:
        """Monta a string de conexão do psycopg; a senha só é revelada aqui."""
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password.get_secret_value()}"
        )


@lru_cache
def obter_configuracao() -> Configuracao:
    """Retorna uma instância única (cacheada) da configuração completa."""
    return Configuracao()


@lru_cache
def obter_parametros_regras() -> ParametrosRegras:
    """Só os parâmetros de regra: usado onde não há banco (avaliação offline, testes)."""
    return ParametrosRegras()
