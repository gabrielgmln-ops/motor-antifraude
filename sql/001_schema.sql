-- sql/001_schema.sql
-- Esquema das decisões do motor antifraude.
-- Executado automaticamente pelo PostgreSQL na primeira inicialização do volume;
-- o repositório Python também roda este mesmo DDL (é idempotente).

CREATE TABLE IF NOT EXISTS decisoes (
    -- A própria transação é a chave: reprocessar a mesma mensagem não duplica a decisão
    transacao_id     TEXT PRIMARY KEY,
    conta_id         TEXT          NOT NULL,
    -- NUMERIC guarda valor exato; dinheiro nunca é armazenado como ponto flutuante
    valor            NUMERIC(18,2) NOT NULL CHECK (valor > 0),
    moeda            CHAR(3)       NOT NULL DEFAULT 'BRL',
    ocorrida_em      TIMESTAMPTZ   NOT NULL,
    classificacao    TEXT          NOT NULL
                     CHECK (classificacao IN ('APROVADA', 'SUSPEITA', 'BLOQUEADA')),
    regras_disparadas TEXT[]       NOT NULL DEFAULT '{}',
    score_anomalia   NUMERIC(8,5),
    -- Rótulo vindo apenas dos dados sintéticos; em produção seria preenchido depois (chargeback)
    rotulo_fraude    BOOLEAN,
    decidida_em      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Recarregar o histórico por conta quando o motor reinicia
CREATE INDEX IF NOT EXISTS idx_decisoes_conta_data ON decisoes (conta_id, ocorrida_em DESC);
-- Listagem das decisões mais recentes no painel
CREATE INDEX IF NOT EXISTS idx_decisoes_decidida_em ON decisoes (decidida_em DESC);
