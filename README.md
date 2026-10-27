# Motor Antifraude

Motor antifraude em tempo real que consome eventos de transação da **Ledger API** (Java/Spring)
via Kafka, aplica regras e um modelo de anomalia (IsolationForest) e classifica cada transação
como **APROVADA**, **SUSPEITA** ou **BLOQUEADA**. As decisões são gravadas no PostgreSQL e um
painel mostra precisão e recall sobre dados **sintéticos** rotulados.

> Apenas dados sintéticos. Dinheiro sempre em `Decimal` (string no JSON, `NUMERIC` no banco).
> Segredos somente por variável de ambiente (`.env`, nunca versionado).

## Arquitetura

```
Ledger API ──► Kafka: transacoes.eventos ──► consumidor ──► MotorAntifraude
                     (chave = conta_id)                     ├─ MotorRegras (p99, madrugada, rajada)
                                                            ├─ IsolationForest (features adimensionais)
                                                            └─ classificar()
                                               │
                         ┌─────────────────────┴───────────────────┐
                         ▼                                         ▼
               PostgreSQL: decisoes                 Kafka: antifraude.decisoes
                         │
                         ▼
               FastAPI: /metricas  /decisoes  /painel
```

| Módulo | Responsabilidade |
|---|---|
| `dominio.py` | Contrato do evento, `Transacao`, `Decisao`, conversão segura para `Decimal` |
| `estado.py` | Histórico recente por conta, em memória (recarregado do banco ao reiniciar) |
| `regras.py` | Regras puras: valor > p99 da conta, 0h–5h local, mais de N transações em M min |
| `modelo_anomalia.py` | Features, treino, calibração do limiar, salvar/carregar o IsolationForest |
| `classificador.py` | Política que une regras + modelo |
| `motor.py` | Orquestra a decisão (mesmo código no Kafka e na avaliação offline) |
| `repositorio.py` | PostgreSQL (idempotente) e versão em memória |
| `consumidor.py` | Laço Kafka at-least-once com commit manual |
| `metricas.py` / `api.py` | Precisão, recall, matriz de confusão e painel HTML |

### Política de classificação

| Sinais | Resultado |
|---|---|
| nenhum | APROVADA |
| 1 regra **ou** só o modelo | SUSPEITA |
| 2+ regras **ou** 1 regra + modelo | BLOQUEADA |

### Contrato do evento (Ledger API → `transacoes.eventos`)

```json
{
  "transacao_id": "3f2b9c1e-...",
  "conta_id": "conta-0042",
  "valor": "1234.56",
  "moeda": "BRL",
  "ocorrida_em": "2026-10-01T14:03:00+00:00"
}
```

`valor` é **string** (preserva os centavos) e `ocorrida_em` precisa de fuso. No lado Spring,
serialize o `BigDecimal` como string (`@JsonFormat(shape = STRING)`) e use a conta como chave
da mensagem, para manter a ordem das transações de cada conta.

## Como rodar (Windows / PowerShell)

```powershell
Copy-Item .env.example .env          # ajuste a senha
docker compose up -d                 # Kafka + PostgreSQL
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/verificar_infra.py    # cria tabela e tópicos
python scripts/treinar_modelo.py     # treina e salva modelos/isolation_forest.joblib
```

### Avaliação offline (sem Kafka)

```powershell
python scripts/avaliar_offline.py
```

### Fluxo em tempo real

```powershell
# terminal 1: o motor
python -m antifraude.consumidor
# terminal 2: o painel
uvicorn antifraude.api:app --reload
# terminal 3: simular a Ledger API publicando transações
python scripts/gerar_transacoes.py --kafka --semente 7
```

Abra http://localhost:8000/painel.

Também é possível subir o motor e a API em contêineres (o modelo precisa estar treinado antes):

```powershell
docker compose --profile app up -d --build
```

## Testes

```powershell
pytest --cov                 # unitários + cobertura mínima de 85%
pytest -m integracao         # exigem PostgreSQL com POSTGRES_DB terminando em _teste
ruff check src tests scripts
```

O CI (GitHub Actions) roda lint, unitários com cobertura, integração com um PostgreSQL de serviço
e a avaliação offline completa.

## Resultados de referência (semente de treino 42, avaliação semente 7)

| Visão | Precisão | Recall |
|---|---|---|
| Sinalizadas (SUSPEITA + BLOQUEADA) | 27,1% | 82,7% |
| Somente BLOQUEADA | 88,4% | 38,0% |

(18.890 transações, 300 fraudes, `python scripts/avaliar_offline.py`.)

Leitura: o motor encaminha para revisão a maioria das fraudes, e quando bloqueia raramente erra.
A precisão das sinalizadas é limitada por construção: a regra de p99 marca cerca de 1% das
transações legítimas de cada conta.

## Limitações conhecidas

- O estado por conta fica na memória de um processo. Com várias réplicas, cada uma conhece só
  as contas das partições que consome (por isso a chave da mensagem é a conta).
- Mensagens inválidas são registradas em log e descartadas; em produção iriam para uma fila de
  mensagens mortas (DLQ).
- Latência medida em torno de 8 ms por transação (dominada pelo IsolationForest).
- O arquivo do modelo usa joblib/pickle: carregue apenas modelos treinados por você.
