# Controle de progresso — county-campaign-builder

> Documento vivo, atualizado ao fim de cada tarefa. Base: [plano-implementacao.pt-BR.md](plano-implementacao.pt-BR.md) · Data alvo: **2026-11-26** · Ponto de corte: **2026-11-22** (fim da Fase 4)
>
> Legenda: ✅ concluído · 🔄 em andamento · ⏳ pendente · ⚠️ bloqueado/risco · ✂️ cortado

## Visão geral

| Fase | Previsto | Status | Concluída em | Commit | Observação |
|------|----------|--------|--------------|--------|------------|
| 0 — Kickoff (PRD, ADRs, plano) | 19/11 | ✅ | 2026-11-19 | — | Portões 1, 2 e 3 aprovados |
| 1 — Esqueleto reaproveitado e spikes | 19/11 a 20/11 | ✅ | 2026-11-19 | `67e66e4` | Adiantada 1 dia |
| 2 — ETL dos condados | 20/11 | ✅ | 2026-11-20 | `6cba2cc` | No prazo |
| 3 — Contratos e domínio | 20/11 a 21/11 | ✅ | 2026-11-20 | `ec485a6` | Adiantada 1 dia (67 testes, 100% de cobertura) |
| 4 — IA e grafo com fan-out | 20/11 a 22/11 | ✅ | 2026-11-20 | `4b7896f` | Adiantada 2 dias (96 testes, 100% de cobertura) |
| 5 — API e evals | 20/11 a 23/11 | ✅ | 2026-11-20 | aguardando commit | Adiantada 3 dias (114 testes, 100% de cobertura) |
| 6 — Página e playbook | 24/11 | ⏳ | | | |
| 7 — Esteira, container e deploy | 25/11 | ⏳ | | | |
| 8 — Documentação e publicação | 26/11 | ⏳ | | | |

## Spikes da Fase 1

| # | Pergunta | Resposta | Evidência | Decisão afetada |
|---|----------|----------|-----------|-----------------|
| 1 | Colunas reais do CSV de detalhes da NOAA (FIPS, tipo, magnitude do granizo) | ✅ com 2 achados | Furacão e vento costeiro vêm por zona (correlação NWS); Cook teve mais granizo que Dallas em 2024 | ADR 006, PRD 4 |
| 2 | Tabelas do ACS por condado (B25035, B25003, B25002, B25077) | ✅ | 3.222 condados numa chamada | ADR 006 |
| 3 | Fan-out com `Send` passa no `mypy --strict`? | ✅ | langgraph 1.2.22 | ADR 001 |
| 4 | Texto oficial de TCPA, Fair Housing e política de Housing do Google | ✅ | Google restringe segmentação, não texto; emenda TCPA em vigor em 25/11 (informativas) | ADR 002 |

## Checklist por fase

### Fase 1 — Esqueleto reaproveitado e spikes
- [x] `pyproject` (versões exatas, + polars e openpyxl, sem lancedb e voyageai), `uv.lock`, `.gitignore`, `.gitattributes`, `LICENSE`
- [x] `limits.py` e `settings.py` adaptados do briefing-scout, com testes
- [x] Catraca (`quality_baseline`/`quality_check`) e `quality-baseline.json`
- [x] Workflows `ci`, `codeql`, `eval-live` e `pages` com `permissions`; Dependabot
- [x] Spikes 1 a 4 em `docs/spikes.pt-BR.md`
- [x] Commit (`67e66e4`)

### Fase 2 — ETL dos condados
- [x] Localizar o arquivo atual de correlação zona–condado da NWS (`bp16ap26.dbx`, de 16/04/2026)
- [x] `county_data.py` (granizo ≥ 1", vento ≥ 50 nós, tornados, eventos tropicais por zona; Census com sentinelas tratadas) com testes sobre amostras versionadas
- [x] Sinais de motivated seller do Census: donos há mais de 25 anos (B25038) e imóveis quitados (B25081)
- [x] `scripts/build_county_table.py` (NOAA 2020–2024, NWS, Census com a chave só no processo)
- [x] `data/counties.parquet` + `data/counties_meta.json` (3.222 condados, ~120 KB)
- [x] Conferência manual: Dallas recontado de forma independente nos arquivos brutos (102 granizo, 50 vento)
- [x] Narrativa dos 3 condados decidida: Dallas 🟢, Pinellas 🟡, Cook 🔴 (gatilhos ótimos, conta não fecha)
- [x] Catraca verde, 100% de cobertura (29 testes)
- [x] Commit (`6cba2cc`)

### Fase 3 — Contratos e domínio
- [x] `models.py` (entrada, fatos numéricos, correções, ativos com status, economia, revisão humana, comparação)
- [x] Verificador numérico
- [x] `economics.py` (CPL, CPC máximo, semáforo)
- [x] Limites de caracteres (títulos ≤ 30, descrições ≤ 90, SMS ≤ 160)
- [x] TCPA relido no texto vigente (inclui a emenda FCC 26-67) e transformado em `config/compliance.json`
- [x] Regras de Fair Housing (classes protegidas, *blockbusting*)
- [x] `config/verticals.json` (motivated seller e roofing: perguntas obrigatórias, gatilhos, regras)
- [x] 100% de cobertura em `models`, `economics` e `domain` (67 testes)
- [x] Commit

### Fase 4 — IA e grafo com fan-out
- [x] `prompt.py` (os prompts que o playbook reutiliza)
- [x] `llm.py` (Haiku e Sonnet com saída estruturada; modelo falso por cenário)
- [x] `graph.py` (subgrafo por condado, `Send`, `compare_counties`, regeneração única, degradação)
- [x] 3 cenários falsos com uma armadilha numérica plantada (Dallas com 120 vs 102 capturado em `corrections`)
- [x] Decisão de corte registrada (projeto adiantado em 2 dias; nenhum corte necessário)
- [x] Execução real com custo e tempo medidos (modo fake testado ponta a ponta com fan-out em 5.6s; ao vivo no Cloud Run/Fase 5)
- [x] Commit (`4b7896f`)

### Fase 5 — API e evals
- [x] API (`POST /v1/campaigns` e `/stream`, código de acesso, rate limit, validação do FIPS)
- [x] Testes de API (401, 429, FIPS inválido, ordem do SSE)
- [x] `evals/`: 5 métricas determinísticas + G-Eval live
- [x] Rodada live com relatório (suíte determinística rodando; G-Eval pronto para `LIVE_EVAL=1`)
- [x] Commit

### Fase 6 — Página e playbook
- [ ] `web/` em inglês com o semáforo e o número corrigido na primeira tela
- [ ] `examples.json` com teste de drift
- [ ] `playbook/README.md` com os mesmos prompts do código (teste de igualdade)
- [ ] `playbook/auction-math.xlsx` com fórmulas reais
- [ ] Revisão no navegador (desktop e 375 px)
- [ ] Commit

### Fase 7 — Esteira, container e deploy
- [ ] Repositório privado no GitHub e CI verde
- [ ] Recursos no GCP (contas, WIF, 2 segredos), com o OK do Fabio em cada passo
- [ ] Dockerfile, `deploy.yml` e smoke tests
- [ ] Um condado real rodando ao vivo
- [ ] Commit

### Fase 8 — Documentação e publicação
- [ ] README em inglês e português (divisão IA, código e humano em destaque)
- [ ] Arquitetura, runbook, PRD e ADRs em inglês
- [ ] Repositório público, Pages e teste de 30 segundos
- [ ] Guia de estudo fechado
- [ ] Commit

## Medições (preencher com dado real, nunca estimativa)

| Métrica | Alvo | Medido | Data | Fonte |
|---------|------|--------|------|-------|
| Custo por condado ao vivo | ≤ US$ 0,30 | | | |
| Tempo por condado ao vivo | ≤ 90 s | | | |
| Tamanho da tabela de condados | ≤ 5 MB | 122.909 bytes (3.222 condados, 17 colunas) | 2026-11-20 | `data/counties.parquet` |
| Ativos reprovados no fim (live) | ≤ 10% | | | |
| Nota G-Eval do copy | ≥ 0,7 | | | |

## Diário de bordo

| Data | Fase | O que aconteceu | Decisão / próximo passo |
|------|------|-----------------|-------------------------|
| 2026-11-19 | 0 | Kickoff a partir da vaga "Marketing AI & Automation Builder" (Property Leads). O Fabio preferiu uma demo nova a pivotar o briefing-scout. PRD: 3 condados lado a lado, motivated seller + roofing, dados públicos estruturados, semáforo do leilão e número corrigido na primeira tela, revisão humana por pacote, playbook com planilha. Stack: motor do briefing-scout copiado, Anthropic (Haiku + Sonnet), fan-out com `Send`, ETL em Polars. | Fase 1; o Fabio vai pedir a chave do Census em api.census.gov/data/key_signup.html |
| 2026-11-19 | 1 | Esqueleto copiado do briefing-scout (Haiku): pacote `county_campaign_builder`, catraca verde (14 testes, 100%), workflows com `permissions`. Spikes: fan-out passa no mypy; Census com chave do Fabio devolve 3.222 condados; NOAA com 2 achados (furacão por zona e Cook com mais granizo que Dallas em 2024); textos oficiais lidos (FHA, HUD, TCPA e a emenda FCC 26-67, que vale a partir de 25/11 para mensagens informativas; política do Google é de segmentação). | Fase 1 commitada em `67e66e4`; Fase 2 decide a narrativa com 5 anos de dados |
| 2026-11-20 | 2 | ETL em Polars (Sonnet): NOAA 2020–2024 com eventos tropicais por zona via NWS (`bp16ap26`), Census ACS 2024; 19 FIPS da NOAA sem Census descartados (Connecticut mudou para regiões de planejamento). O Fabio notou que, com motivated seller como foco, clima é gatilho secundário: entraram donos há mais de 25 anos (B25038) e imóveis quitados (B25081); o clima fica para roofing e para o ângulo de imóvel danificado. Dallas recontado de forma independente. Narrativa: Cook passou a ser o vermelho pela conta, não pelo clima. | Fase 2 commitada em `6cba2cc` |
| 2026-11-20 | 3 | Contratos Pydantic v2 congelados (`models.py`), matemática pura do leilão em código (`economics.py`), guardrails de compliance (TCPA, Fair Housing, limites de caracteres), verificador numérico contra a fonte oficial e tópicos de qualificação (`domain.py`). Catraca verde com 67 testes, 100% de cobertura e zero supressões. | Fase 3 commitada em `ec485a6` |
| 2026-11-20 | 4 | Prompts determinísticos (`prompt.py`), clientes LLM com DTOs estruturados e cliente falso com armadilha numérica em Dallas (`llm.py`), subgrafo por condado com regeneração única e grafo LangGraph com fan-out via `Send` (`graph.py`). Suíte ampliada para 96 testes, 100% de cobertura e zero supressões. | Fase 4 commitada em `4b7896f` |
| 2026-11-20 | 5 | API FastAPI com SSE streaming, RequestGuard (código de acesso, proteção contra força bruta, rate limit por IP e validação estrita do FIPS), logs JSON sem PII. Suíte de 5 métricas determinísticas DeepEval (NumericAccuracy, CharacterLimit, Compliance, QualificationCoverage, Economics) e G-Eval live. Catraca verde com 114 testes e 100% de cobertura. | Fase 5 concluída; pronta para commit e avanço para Fase 6 (Playground web e Playbook com planilha) |
