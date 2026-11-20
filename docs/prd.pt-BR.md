# PRD — county-campaign-builder

> 🇧🇷 PT-BR | 🇺🇸 [EN](prd.md) · Status: Aprovado em 2026-11-19 (Portão 1) · Versão 1.0 · Iniciado em 2026-11-19

## 0. Enquadramento (Etapa 0, fechado em 2026-11-19)
- **Nome provisório:** county-campaign-builder
- **Problema em uma frase:** escalar campanhas locais de lead gen (motivated sellers e roofing) em muitos condados dos EUA sem cair em copy genérico, com cada afirmação local de fonte checada e a conta do leilão verificada pelo código.
- **Tipo:** demo de portfólio (`fgm9000`) pensada para a candidatura à vaga "Marketing AI & Automation Builder" da Property Leads. Inglês primeiro. Pode ficar privada até o envio.
- **Repositório:** `C:\Users\fabio\development\county-campaign-builder` (junto das outras demos, fora do Google Drive).
- **Relação com o briefing-scout:** reaproveita o motor (grafo, verificador de citação, regras de setor, evals, esteira). O briefing-scout continua intacto.

## 1. Contexto e problema
- **História principal da demo:** o mesmo workflow roda em **3 condados lado a lado** e termina numa tabela comparativa: o que muda de um condado para outro (gatilhos, perguntas, anúncios) e em qual deles a conta do leilão não fecha. Prova escala e decisão, não só a qualidade de um pacote.

- **Verticais:** **motivated seller** (cash offer) como principal e **roof replacement** como segunda configuração do mesmo motor. A troca é só de configuração (perguntas, regras, gatilhos), sem mudar código, para provar que o workflow é reutilizável.

- **Operador e avaliador:** ver a seção 2.

## 2. Objetivo e proposta de valor
Para times de lead gen que precisam lançar campanhas locais em muitos condados dos EUA, o county-campaign-builder transforma dados públicos de cada condado num pacote de campanha pronto para revisão: perguntas de qualificação, anúncios, landing page, SMS e e-mails. Cada número local é conferido contra a fonte, a conta do leilão é calculada pelo código e o que só um humano pode julgar sai marcado. Usar o ChatGPT sozinho dá copy genérico, sem fonte verificável e sem saber se a campanha fecha a conta.

- **Competência que a demo prova** (na linguagem da vaga): transformar um problema de negócio ambíguo num workflow de IA em várias etapas; checar fatos e cálculos da IA; construir um processo reutilizável que outras pessoas sigam; explicar onde a IA ajuda e onde precisa de um humano.
- **Avaliador alvo:** quem contrata na Property Leads, provavelmente alguém de marketing ou operações, não um engenheiro. Por isso a primeira tela fala de negócio (custo por lead, lance) e o playbook não exige programação.
- **Operador na história:** o próprio "Marketing AI & Automation Builder", ou alguém do time de marketing que usa o workflow.

## 3. Escopo
### 3.1 Dentro do MVP
Para cada condado, o pacote entrega:
- RF-01 — Brief local: fatos do condado com fonte checada (ver seção 7).
- RF-02 — Perguntas de qualificação do formulário da landing page, por vertical (separar o lead que vira negócio do que não vira).
- RF-03 — Anúncio de pesquisa do Google (RSA): 8 títulos e 3 descrições.
- RF-04 — Topo da landing page: título, subtítulo e CTA.
- RF-05 — 3 SMS de speed-to-lead (primeiros minutos depois do cadastro).
- RF-06 — Sequência de e-mail de follow-up (decisão do Fabio em 2026-11-19; tamanho exato a fechar).
- RF-07 — Conta do leilão: CPL estimado contra o lance do condado, com as premissas visíveis.
- RF-08 — Tabela comparativa dos 3 condados (seção 1).

- RF-09 — Revisão humana por pacote: lista `needs human review` com o motivo de cada item (seção 8).
- RF-10 — Playbook não-código:
  - Markdown com os prompts reutilizáveis de cada etapa, o guia de uso no Claude ou no ChatGPT e a checklist de revisão;
  - planilha `.xlsx` da conta do leilão, com as fórmulas visíveis.

  Os dois são gerados a partir da mesma fonte que o código usa, para não divergirem.

### 3.2 Fora do escopo
- Imagens, vídeo e afiliados: próximos passos no README.
- Segmentação de campanha (CEP, perfil): a demo gera texto e conta, não configura público. Por isso a política de Housing entra como regra de texto.

## 4. Fluxo principal
**Condados da demo gravada**, escolhidos pelo contraste:
| Condado | O que os dados mostram (2020–2024 e ACS 2020–2024) | Semáforo esperado |
|---|---|---|
| Dallas County, TX | 102 relatos de granizo ≥ 1"; imóveis mais novos (1983); 42,7% quitados | 🟢 fecha |
| Pinellas County, FL | 18 eventos tropicais; vacância de 17,6%; 48,9% quitados; imóveis de 1977 | 🟡 no limite |
| Cook County, IL | 455 relatos de vento e 94 de granizo; imóveis mais antigos (1961); 31,2% dos donos há mais de 25 anos | 🔴 ótimos gatilhos, mas o clique de metrópole não fecha a conta |

**Revisão de 2026-11-20 (Fase 2):** a narrativa inicial dizia "Cook com poucos eventos de clima", e os dados mostraram o contrário. Cook continua o vermelho, agora pelo motivo mais instrutivo: a IA o recomendaria pelos gatilhos, e o código o reprova pela conta do leilão. O CPC continua sendo premissa do operador, dita como tal na tela.

**Passos:**
1. O operador informa o condado (código FIPS), a vertical, o lance por lead e as **premissas** de CPC e conversão da landing page (faixa mínima e máxima).
2. O código busca os agregados do condado (NOAA e ACS) e monta as fontes.
3. O LLM transforma os dados em gatilhos de mensagem, cada um citando o número e a fonte.
4. O código confere cada número contra a fonte; o que não bate é corrigido ou removido, e a correção fica visível.
5. O LLM gera as perguntas de qualificação, o anúncio, o topo da LP, os SMS e os e-mails.
6. O código aplica limites de caracteres, TCPA, Fair Housing e as regras da vertical; o que falha é regenerado uma vez e, se persistir, sai reprovado.
7. O código calcula a conta do leilão e o semáforo; monta a lista de revisão humana.
8. Com os 3 condados, o código monta a tabela comparativa.

**A conta do leilão (só no código):**
- CPL = CPC ÷ conversão da LP.
- CPC máximo que fecha = lance × conversão.
- Semáforo: verde se o CPL no pior caso da faixa cabe no lance; amarelo se só cabe no melhor caso; vermelho se não cabe em nenhum.

Exemplo de entrada (ilustrativo; o contrato final sai na Fase 2):
```json
{
  "county_fips": "48113",
  "vertical": "motivated_seller",
  "bid_per_lead_usd": 125,
  "cpc_usd": {"min": 4.5, "max": 9.0},
  "landing_cvr": {"min": 0.06, "max": 0.10}
}
```
Exemplo de saída (trecho ilustrativo):
```json
{
  "county": "Dallas County, TX",
  "facts": [{"claim": "34 hail reports of 1 inch or larger in 2025", "value": 34, "source": "NOAA Storm Events", "status": "verified"}],
  "corrections": [{"llm_value": 41, "source_value": 34, "field": "hail_reports_2025"}],
  "unit_economics": {"cpl_best_usd": 45.0, "cpl_worst_usd": 150.0, "max_cpc_usd": 7.5, "verdict": "yellow"},
  "needs_human_review": [{"item": "headline_5", "reason": "Promises a 7-day close; confirm the offer terms with the buyer"}]
}
```

## 5. Diferencial técnico (Regra dos 30 segundos)
Na primeira tela, duas coisas lado a lado:
1. **A tabela dos 3 condados com o semáforo da conta do leilão.** Um condado em vermelho, com a conta à mostra: "com CPC de US$ 9 e conversão de 6%, o lead custa US$ 150; o lance é US$ 125: não fecha". A conta é do código, nunca do LLM.
2. **Um número que a IA errou e o código corrigiu.** Por exemplo: "a IA escreveu 41 relatos de granizo; a NOAA registra 34". Mostra o verificador numérico contra a fonte estruturada.

Os dois juntos são o "check AI-generated facts, calculations, and recommendations" da vaga. As checagens de compliance (TCPA, Fair Housing, limites de caracteres) aparecem dentro de cada pacote.

## 6. Requisitos não funcionais
**Modos de acesso** (o mesmo modelo do briefing-scout):
- **Público:** página com os 3 condados gravados, custo zero.
- **Ao vivo:** com código de acesso, roda um condado escolhido na hora (o "escolham um condado" da entrevista).

| ID | Requisito | Alvo | Fonte/hipótese |
|----|-----------|------|----------------|
| RNF-01 | Custo por condado ao vivo | ≤ US$ 0,30 | Hipótese: há mais texto gerado que no briefing-scout (~US$ 0,05); medir na Fase 4 |
| RNF-02 | Tempo por condado ao vivo | ≤ 90 s, com progresso por etapa | Hipótese, a medir |
| RNF-03 | Teto mensal no provedor | US$ 30 (o mesmo do console da Anthropic) | Decisão anterior do Fabio |
| RNF-04 | Proteções do modo ao vivo | Código de acesso, rate limit, logs sem PII | Reaproveitadas do briefing-scout |
| RNF-05 | Idioma | Interface e saídas em inglês (mercado americano); docs PT/EN | Etapa 0 |

## 7. Dados e privacidade
- **Fatos locais vêm de dados públicos estruturados, não de busca web:**
  - **Motivated seller, sinais principais (Census ACS):** idade dos imóveis, vacância, proporção de imóveis alugados (donos-investidores), donos há mais de 25 anos (B25038) e imóveis quitados (B25081). Incluídos na Fase 2, a pedido do Fabio, porque o clima é gatilho secundário para quem vende.
  - **Clima (NOAA Storm Events):** gatilho principal de roofing e ângulo secundário de motivated seller (imóvel danificado por tempestade vendido no estado em que está).
  - Execução hipotecária e impostos atrasados seriam os melhores sinais, mas são dados pagos (ATTOM e afins): ficam como próximo passo. O código baixa os números; o LLM só escreve a partir deles; o verificador confere também os **números** citados.
- **Snapshot versionado** dos dados dos 3 condados, para o CI e a página pública funcionarem sem rede.
- Disponibilidade, formato, licença e limites das duas fontes: a confirmar na fonte na Etapa 2.

- **PII:** nenhuma. Os dados são agregados públicos por condado; o modo ao vivo não recebe dados de pessoas, e os logs seguem o padrão sem PII do briefing-scout.

## 8. Uso de IA
**Divisão de trabalho, explícita na demo:**
| Quem | Faz o quê |
|---|---|
| IA (LLM) | Interpreta os dados do condado em gatilhos de mensagem; escreve perguntas, anúncios, LP, SMS e e-mails |
| Código | Busca e agrega os dados; confere números e fontes; calcula a conta do leilão; aplica limites de caracteres, TCPA e Fair Housing |
| Humano | Revisa o que o código não consegue verificar |

- **Revisão humana obrigatória por pacote:** cada item que o código não verifica (promessa de oferta, ângulo contra concorrente, tom, adequação local) sai marcado `needs human review`, com o motivo. É a frase "when human judgment is needed" da vaga, transformada em funcionalidade.
- **Falha do LLM:** um número que não bate com a fonte é corrigido ou removido pelo código; texto que fere limite ou regra é reprovado e regenerado uma vez, e se persistir sai marcado como reprovado (nunca entregue como aprovado). A conta do leilão nunca depende do LLM.
- **Métricas de eval:** a definir na Etapa 2 (candidatos: precisão numérica contra a fonte, conformidade das regras, cobertura das perguntas de qualificação e uma rubrica de qualidade do copy).

## 9. Métricas de sucesso
- **Candidatura:** a demo é enviada com a candidatura até 2026-11-26, com link público, README em inglês e um vídeo curto opcional.
- **30 segundos:** quem avalia vê o semáforo e o número corrigido sem rolar a página.
- **Qualidade:** evals verdes no CI; nenhum número publicado sem bater com a fonte; 100% dos ativos dentro dos limites e das regras, ou marcados como reprovados.
- **Reuso:** a segunda vertical (roofing) roda só com configuração nova, sem mudança de código.

## 10. Restrições, prazo e dependências
- **Data alvo:** demo pronta para enviar com a candidatura em **2026-11-26** (1 semana, decisão do Fabio em 2026-11-19).

- **Orçamento:** US$ 30 por mês no provedor de LLM, o mesmo teto; Cloud Run no projeto compartilhado `fgm9000-portfolio`.
- **Dependências externas:** NOAA Storm Events e Census ACS (dados), provedor de LLM.
- **Corte de escopo se o prazo apertar, nesta ordem:** (1) a sequência de e-mail; (2) a planilha `.xlsx`, que fica só no Markdown; (3) o modo ao vivo, ficando só os cenários gravados.

## 11. Hipóteses e questões em aberto
| Item | Hipótese adotada | Critério de revisão |
|------|------------------|---------------------|
| Fontes NOAA e Census | Há agregados por condado acessíveis, com licença de uso livre | Confirmar na fonte na Etapa 2 |
| Narrativa dos 3 condados | Dallas fecha, Pinellas no limite, Cook não fecha | Conferir com os dados reais antes de gravar |
| Premissas de CPC e conversão | O operador informa faixas; a demo usa valores ilustrativos e diz isso na tela | Não apresentar como dado de mercado |
| Regras TCPA e Fair Housing | Checagens de texto (opt-out, linguagem discriminatória) | Conferir no texto oficial antes de virar configuração |
| Custo e tempo por condado | ≤ US$ 0,30 e ≤ 90 s | Primeira medição real |
| Prazo de 1 semana | Cabe com o motor reaproveitado | Revisar no fim da fase de domínio |

## 12. Pré-decisões de stack a confirmar na Etapa 2
- Reaproveitar do briefing-scout: grafo LangGraph, `domain.py` (verificador de citação, regras de setor), contratos Pydantic, catraca, evals DeepEval, esteira e deploy.
- Fontes públicas candidatas: NOAA Storm Events (granizo e vento por condado) e Census ACS (idade dos imóveis, ocupação pelo dono). Disponibilidade, formato e limites a confirmar na fonte.
- Entregável não-código: playbook (prompts e templates reutilizáveis) + planilha da conta do leilão.
- Modo ao vivo para qualquer condado sem baixar NOAA na hora: avaliar pré-calcular os agregados de **todos os ~3.200 condados** (NOAA + ACS) numa tabela pequena versionada, para o ao vivo não depender de API externa de dados.

## Contexto da vaga (referência)
"Marketing AI & Automation Builder", Property Leads, remoto América do Sul, US$ 3.000–4.500/mês. Pontos que a demo precisa provar, nas palavras da vaga:
- "Turn an ambiguous business problem into a structured, multi-step AI workflow."
- "Check AI-generated facts, calculations, and recommendations rather than accepting them at face value."
- "Build reusable processes that consistently produce useful outputs."
- "Explain where AI adds value, where it struggles, and when human judgment is needed."
- Domínios: motivated seller leads (negócio principal; métrica "lead-to-deal ratio"), roofing e home services, afiliados.
- "Advanced coding skills… are not required": o avaliador provavelmente não é engenheiro.
