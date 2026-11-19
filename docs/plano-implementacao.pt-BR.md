# Plano de Implementação — county-campaign-builder

> Base: PRD v1.0 (aprovado em 2026-11-19) · ADRs 001 a 008 (aprovados em 2026-11-19) · Padrão Mestre de Engenharia
> Status: Aprovado em 2026-11-19 (Portão 3) · Progresso: [controle-progresso.pt-BR.md](controle-progresso.pt-BR.md) · Data alvo: **2026-11-26** · Ponto de corte: **2026-11-22** (fim da Fase 4)

## Resumo das decisões
| Ramo | Decisão | Segue o padrão? | ADR |
|------|---------|-----------------|-----|
| Linguagem e tooling | Python 3.12, uv, Ruff, mypy strict, Pytest, Pydantic v2 | Sim | 001 |
| LLM | Anthropic: Haiku 5.5 (dados, qualificação, SMS, e-mail) e Sonnet 5.5 (anúncios e LP) | Não | 001 |
| Orquestração | LangGraph com fan-out (`Send`) e nó de comparação | Não | 001 |
| Núcleo | Verificador numérico, conta do leilão no código, compliance, regeneração única, revisão humana | Sim (disciplina) | 002 |
| Hospedagem | Cloud Run novo, mesmas proteções, sem netguard | Parcial | 003 |
| Avaliação | DeepEval com 5 métricas novas + G-Eval do copy (juiz Opus) | Não | 004 |
| Página | Estática, em inglês, com o semáforo na primeira tela | Sim | 005 |
| Dados | Tabela de todos os condados via ETL em Polars | Não | 006 |
| Reuso | Copiar e adaptar o motor do briefing-scout | — | 007 |
| Playbook | Markdown + `.xlsx` com fórmulas (openpyxl) | Novo | 008 |

## Regras de execução
- **Autoria:** commits só do Fabio, sem trailers de IA; um commit por fase.
- **Qualidade:** zero supressões; catraca local desde a Fase 1.
- **Delegação:**
  - o Opus orquestra, desenha contratos e prompts e revisa todo diff;
  - o Sonnet faz o código com lógica;
  - o Haiku faz o mecânico (cópias do briefing-scout, fixtures, traduções).
- **Controle:** `docs/controle-progresso.pt-BR.md` atualizado a cada fase, e o guia de estudo fora do repositório também.

## Fases

### Fase 1 — Esqueleto reaproveitado e spikes (19/11 e 20/11)
- **Entregáveis:**
  - repositório com `pyproject` (+ polars, openpyxl), catraca, workflows (com `permissions`), `.gitattributes`, Dockerfile, e `limits`, `settings`, `llm` e a base de `api`, copiados e adaptados do briefing-scout;
  - `docs/spikes.pt-BR.md`.
- **Spikes:**
  1. as colunas reais do CSV de detalhes da NOAA (FIPS do condado, `EVENT_TYPE`, `MAGNITUDE` do granizo), conferidas no PDF de formato;
  2. as tabelas do ACS em nível de condado (B25035, B25003, B25002, B25077), com a chave do Census;
  3. o fan-out com `Send` passando no `mypy --strict`;
  4. o texto oficial de TCPA (consentimento e opt-out em SMS), do Fair Housing Act (linguagem discriminatória em anúncios) e da política de Housing do Google Ads.
- **Pronto quando:** catraca verde com o esqueleto; os 4 spikes respondidos com evidência.
- **Commit:** `chore: bootstrap from the briefing-scout engine and record spikes`
- **Execução:**
  - Haiku: cópias e adaptações mecânicas;
  - Opus: spikes 1, 2 e 4;
  - Sonnet: spike 3.
- **Base:** ADRs 001, 006 e 007.

### Fase 2 — ETL dos condados (20/11)
- **Entregáveis:** `scripts/build_county_table.py` (Polars); a lógica de agregação em `src/` com teste sobre amostras versionadas; `data/counties.parquet` com a data de corte e a fonte de cada coluna.
- **Pronto quando:** a tabela tem os ~3.200 condados; os valores de Dallas, Pinellas e Cook conferem à mão com a fonte; **a narrativa dos 3 condados é confirmada ou algum condado é trocado** (PRD, seção 11).
- **Commit:** `feat: add county data pipeline from NOAA and Census`
- **Execução:**
  - Sonnet: o ETL e os testes;
  - Opus: a conferência manual e a decisão sobre a narrativa.
- **Base:** ADR 006.

### Fase 3 — Contratos e domínio (21/11)
- **Entregáveis:**
  - `models.py`: entrada, fatos numéricos, correções, ativos com status, economia, revisão humana, comparação;
  - `domain/`: verificador numérico, `economics.py`, limites de caracteres, regras de compliance;
  - `config/verticals/` (motivated seller e roofing): perguntas obrigatórias, regras e gatilhos;
  - `config/compliance.json`, conferido no texto oficial do spike 4.
- **Pronto quando:** 100% de cobertura em `models` e `domain`.
- **Commit:** `feat: add contracts, numeric verifier, auction math and compliance rules`
- **Execução:**
  - Opus: os contratos e as regras (conferência legal);
  - Sonnet: o domínio e os testes.
- **Base:** ADR 002.

### Fase 4 — Camada de IA e grafo com fan-out (21/11 e 22/11)
- **Entregáveis:** `prompt.py` (os prompts que o playbook reutiliza), `llm.py` (Haiku e Sonnet com saída estruturada; modelo falso por cenário), `graph.py` (subgrafo por condado, `Send` e `compare_counties`, regeneração única e degradação); os 3 cenários falsos, com uma armadilha numérica plantada; a execução real com custo e tempo medidos.
- **Pronto quando:** os 3 condados de ponta a ponta com o modelo falso (a armadilha aparece em `corrections`); uma execução real medida contra o RNF-01 e o RNF-02.
- **Commit:** `feat: add county campaign graph with fan-out and Anthropic clients`
- **Execução:**
  - Opus: os prompts e a revisão;
  - Sonnet: o código.
- **Base:** ADRs 001 e 002.
- **Checkpoint de corte (22/11):** se atrasar, aplicar os cortes do PRD nesta ordem: e-mail, planilha, modo ao vivo.

### Fase 5 — API e evals (23/11)
- **Entregáveis:** a API adaptada (`POST /v1/campaigns` e `/stream`, com eventos por condado e etapa, código de acesso, rate limit, validação do FIPS); `evals/` com as 5 métricas e o G-Eval live; rodada live com relatório.
- **Pronto quando:** testes de API (401, 429, FIPS inválido, ordem do SSE), evals fake verdes e rodada live registrada.
- **Commit:** `feat: add API with SSE and DeepEval suites`
- **Execução:**
  - Sonnet: a API e as suítes;
  - Opus: a rubrica e o diagnóstico da rodada live.
- **Base:** ADRs 003 e 004.

### Fase 6 — Página e playbook (24/11)
- **Entregáveis:**
  - `web/` em inglês, com o semáforo e o número corrigido na primeira tela e `examples.json` com teste de drift;
  - `playbook/README.md`, `playbook/auction-math.xlsx` e `scripts/build_playbook.py`, com teste de que os prompts do playbook são os mesmos do código.
- **Pronto quando:** revisão no navegador (desktop e 375 px); a planilha abre no Excel ou no Google Sheets com as fórmulas funcionando.
- **Commit:** `feat: add playground and non-code playbook`
- **Execução:**
  - Sonnet: o `app.js`, o script da planilha e o playbook;
  - Haiku: HTML e CSS a partir da base do briefing-scout;
  - Opus: os textos e a revisão visual.
- **Base:** ADRs 005 e 008.

### Fase 7 — Esteira, container e deploy (25/11)
- **Entregáveis:** CI completo; recursos no GCP pelo runbook (conta de runtime, conta de deploy, WIF, 2 segredos); o deploy e os smoke tests.
- **Pronto quando:** CI verde no GitHub (privado), serviço no ar com 401 sem código e um condado real rodando ao vivo.
- **Commit:** `build: add CI, container and Cloud Run deploy`
- **Execução:**
  - Opus: os comandos de GCP (com o OK do Fabio em cada passo);
  - Haiku: os ajustes de workflow.
- **Base:** ADR 003.

### Fase 8 — Documentação e publicação (26/11)
- **Entregáveis:** README em inglês e português (com a divisão IA, código e humano em destaque), arquitetura, runbook, PRD e ADRs em inglês; repositório público, Pages, teste de 30 segundos; guia de estudo fechado.
- **Pronto quando:** o link está pronto para a candidatura.
- **Commit:** `docs: add bilingual documentation and publish`
- **Execução:**
  - Opus: o README;
  - Haiku: as traduções e a checagem de links.
- **Base:** Padrão Mestre, seção 6.

> **Divergência do roteiro de 9 fases:** a ordem foi comprimida para 1 semana (API com evals; página com playbook; esteira com deploy). Entram a Fase 2 (ETL, ADR 006) e o playbook (ADR 008).

## Paralelização
- **Fase 1:** as cópias do Haiku rodam em paralelo com os spikes.
- **Fase 3:** a conferência legal do Opus roda em paralelo com o `economics.py` e o verificador numérico do Sonnet.
- **Fase 6:** HTML e CSS (Haiku) rodam em paralelo com o script da planilha (Sonnet).

## Riscos e pontos frágeis
| Risco | Origem | Mitigação | Gatilho de revisão |
|-------|--------|-----------|--------------------|
| Prazo de 1 semana | PRD, seção 10 | Motor reaproveitado; cortes em ordem | Fase 4 depois de 22/11 |
| Chave do Census atrasar | ADR 006 | ETL da NOAA primeiro; o ACS entra assim que a chave chegar | Fim da Fase 1 sem chave |
| Narrativa dos condados não se confirmar | PRD, seção 11 | Trocar o condado antes de gravar | Fase 2 |
| Regras legais mal interpretadas | ADR 002 | Texto oficial no spike 4; a demo diz que não é aconselhamento jurídico | Spike 4 |
| Rate limit da API com 3 condados em paralelo | ADR 001 | Limite de concorrência no fan-out | Primeira execução real |
| Avaliador não técnico | PRD, seção 2 | Primeira tela de negócio; playbook sem código | Teste de 30 s |

## Fora deste plano
Imagens, vídeo, afiliados, segmentação de campanha, integração com CRM ou Google Ads e gravação de resultados.
