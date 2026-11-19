# ADR 001 — Stack e tooling

> 🇧🇷 PT-BR | 🇺🇸 [EN](001-stack-and-tooling.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
Prazo de 1 semana (PRD, seção 10). O motor do briefing-scout já resolve grafo, verificação, API, proteções, evals e esteira (ADR 007). As fontes locais são estruturadas (ADR 006), então não há busca web: as chamadas de LLM são de interpretação e de geração com saída estruturada.

## Opções consideradas
| Ramo | Opção | Prós | Contras |
|------|-------|------|---------|
| S1 | **Python 3.12 (padrão)** | Reuso integral do motor | Sem linguagem nova |
| S6 | **Anthropic: Haiku 5.5 + Sonnet 5.5** | Reusa o cliente e os evals; modelos fortes em copy | Repete o provedor do briefing-scout |
| S6 | OpenAI (GPT) | Repertório novo; a vaga cita "ChatGPT" | Cliente, modelo falso e evals refeitos na semana |
| S6 | Anthropic com Opus no copy | Qualidade máxima | Custo e latência por condado |
| S7 | **LangGraph com fan-out (`Send`)** | Condados em paralelo; evidência nova | Atenção ao rate limit da API |
| S7 | LangGraph linear | Reuso direto | ~3× mais lento |

## Decisão
- **S1, S2 e S4:** Python 3.12, uv, Ruff, mypy `--strict`, Pytest e Pydantic v2.
- **S6:** API da Anthropic. `claude-haiku-5-5` interpreta os dados do condado e escreve perguntas, SMS e e-mails; `claude-sonnet-5-5` escreve os anúncios e o topo da LP. Saída estruturada em todas as chamadas.
- **S7:** LangGraph com **fan-out via `Send`**: um subgrafo por condado, em paralelo, e um nó de redução que monta a tabela comparativa.
- **S3:** FastAPI com SSE, com eventos por condado e por etapa.
- **S5:** sem banco. Tabela pré-calculada de todos os condados (ADR 006).
- **S8:** DeepEval (ADR 004). **S13:** logs JSON sem PII.
- **Novo:** Polars no ETL (ADR 006) e openpyxl na planilha do playbook (ADR 008).

## Justificativa
Com fontes estruturadas e 1 semana, trocar de provedor de LLM custaria o cliente, o modelo falso e os evals sem ganho de produto. A evidência nova da demo vem do fan-out, do ETL de dados públicos em Polars, do verificador numérico e do playbook com planilha, que é o que essa vaga avalia.

## Divergência do padrão
| Item | Padrão | Decisão | O que se perde / compensação |
|------|--------|---------|-------------------------------|
| Provedor | OpenRouter | Anthropic direto | Troca de modelo deixa de ser livre; `ModelClient` continua `Protocol` com modelo falso |
| Orquestração | Pipeline próprio | LangGraph com fan-out | Mais dependências; nós continuam funções puras testáveis |
| Avaliação | Promptfoo | DeepEval | Ver ADR 004 |

## Consequências
- Positivas: reuso alto; tempo dos 3 condados perto do de um.
- Negativas / dívidas: a mesma dependência de provedor do briefing-scout.
- Impacto no plano: Fases 1, 3 e 4.

## Critério de revisão
Custo medido acima de US$ 0,30 por condado, ou o copy do Sonnet reprovado no G-Eval: reavaliar a divisão de modelos.
