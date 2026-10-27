# src/antifraude/api.py
"""API de métricas e painel simples (HTML gerado no servidor, sem front-end separado).

Execução: uvicorn antifraude.api:app --reload
  GET /saude      -> verificação de vida
  GET /metricas   -> precisão, recall e matriz de confusão em JSON
  GET /decisoes   -> últimas decisões gravadas
  GET /painel     -> página HTML com as mesmas métricas (atualiza a cada 10 s)
"""

from functools import lru_cache
from html import escape
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse

from antifraude import __version__
from antifraude.config import obter_configuracao
from antifraude.metricas import MatrizConfusao, calcular_metricas
from antifraude.repositorio import Repositorio, RepositorioPostgres

app = FastAPI(title="Motor Antifraude", version=__version__)


@lru_cache
def obter_repositorio() -> Repositorio:  # pragma: no cover - substituído nos testes
    return RepositorioPostgres(obter_configuracao().dsn_postgres)


RepositorioDep = Annotated[Repositorio, Depends(obter_repositorio)]


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok", "versao": __version__}


@app.get("/metricas")
def metricas(repositorio: RepositorioDep) -> dict:
    return calcular_metricas(repositorio.contagens_rotuladas()).para_dict()


@app.get("/decisoes")
def decisoes(repositorio: RepositorioDep,
             limite: Annotated[int, Query(ge=1, le=500)] = 50) -> list[dict]:
    # jsonable_encoder transforma Decimal em número JSON; convertemos antes para string
    linhas = repositorio.listar_recentes(limite)
    for linha in linhas:
        linha["valor"] = str(linha["valor"])
        if linha.get("score_anomalia") is not None:
            linha["score_anomalia"] = str(linha["score_anomalia"])
    return jsonable_encoder(linhas)


def _percentual(valor: float | None) -> str:
    return "—" if valor is None else f"{valor * 100:.1f}%"


def _bloco_matriz(titulo: str, m: MatrizConfusao) -> str:
    return f"""
    <section>
      <h2>{escape(titulo)}</h2>
      <div class="kpis">
        <div><span>Precisão</span><strong>{_percentual(m.precisao)}</strong></div>
        <div><span>Recall</span><strong>{_percentual(m.recall)}</strong></div>
        <div><span>F1</span><strong>{_percentual(m.f1)}</strong></div>
      </div>
      <table>
        <tr><th></th><th>Sinalizou</th><th>Não sinalizou</th></tr>
        <tr><th>Fraude</th><td>{m.verdadeiro_positivo}</td><td>{m.falso_negativo}</td></tr>
        <tr><th>Legítima</th><td>{m.falso_positivo}</td><td>{m.verdadeiro_negativo}</td></tr>
      </table>
    </section>"""


@app.get("/painel", response_class=HTMLResponse)
def painel(repositorio: RepositorioDep) -> str:
    r = calcular_metricas(repositorio.contagens_rotuladas())
    recentes = repositorio.listar_recentes(15)
    linhas = "".join(
        f"<tr class='{escape(d['classificacao'].lower())}'><td>{escape(str(d['conta_id']))}</td>"
        f"<td class='num'>R$ {escape(str(d['valor']))}</td>"
        f"<td>{escape(d['classificacao'])}</td>"
        f"<td>{escape(', '.join(d['regras_disparadas']) or '—')}</td>"
        f"<td>{'fraude' if d['rotulo_fraude'] else 'legítima'}</td></tr>"
        for d in recentes
    )
    distribuicao = " · ".join(f"{k}: {v}" for k, v in r.por_classificacao.items())
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>Painel Antifraude</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 960px;
         padding: 0 1rem; color: #1b1f24; background: #f6f7f9; }}
  h1 {{ margin-bottom: .2rem; }} .sub {{ color: #57606a; margin-top: 0; }}
  section {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
            padding: 1rem 1.25rem; margin: 1rem 0; }}
  .kpis {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
  .kpis span {{ display: block; color: #57606a; font-size: .85rem; }}
  .kpis strong {{ font-size: 1.8rem; font-variant-numeric: tabular-nums; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: .75rem; }}
  th, td {{ text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #eaeef2; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.bloqueada td {{ color: #b42318; }} tr.suspeita td {{ color: #9a6700; }}
</style></head><body>
<h1>Motor Antifraude</h1>
<p class="sub">{r.total_rotuladas} decisões rotuladas · {r.total_fraudes} fraudes sintéticas ·
{escape(distribuicao)}</p>
{_bloco_matriz("Sinalizadas (SUSPEITA + BLOQUEADA)", r.sinalizadas)}
{_bloco_matriz("Somente BLOQUEADA", r.bloqueadas)}
<section><h2>Últimas decisões</h2>
<table><tr><th>Conta</th><th class="num">Valor</th><th>Classificação</th><th>Regras</th>
<th>Rótulo</th></tr>{linhas}</table></section>
</body></html>"""
