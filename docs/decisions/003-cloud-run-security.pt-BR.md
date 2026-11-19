# ADR 003 — Cloud Run e segurança

> 🇧🇷 PT-BR | 🇺🇸 [EN](003-cloud-run-security.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
O modo ao vivo roda um condado escolhido na entrevista (PRD, seção 6). A infraestrutura do briefing-scout no `fgm9000-portfolio` (pool WIF, padrão de contas e segredos, deploy) já está provada.

## Decisão
Serviço Cloud Run novo, `county-campaign-builder`, no mesmo projeto e com o mesmo desenho:
- conta de runtime sem papel no projeto, com acesso só aos seus segredos;
- conta de deploy com `run.developer`, `artifactregistry.writer` no repositório e `serviceAccountUser` só sobre o runtime;
- provider WIF próprio, restrito ao repositório e à `main`;
- `--min-instances=0 --max-instances=1 --memory=512Mi --timeout=120`;
- segredos: Anthropic e código de acesso. O Census não entra em produção (ADR 006);
- proteções reaproveitadas: código de acesso com limite de tentativas erradas, rate limit por IP, logs sem PII, `hide_input_in_errors`.

**Diferença do briefing-scout:** a entrada ao vivo é um código FIPS de condado e números, não uma URL. O netguard não é necessário, porque o servidor não busca nada externo além do LLM; a validação de entrada é o FIPS existir na tabela.

## Divergência do padrão
Nenhuma além do `--timeout=120` (SSE), já aceito no briefing-scout. O bootstrap do serviço pelo dono do projeto é previsto no runbook (a conta de deploy não liga o `--no-invoker-iam-check`).

## Consequências
- Positivas: infraestrutura repetida e documentada; superfície de ataque menor (sem URL livre).
- Negativas: mais um serviço no projeto compartilhado.
- Impacto no plano: Fase 8.

## Critério de revisão
Partida a frio acima de 15 s ou RAM acima de 400 MB.
