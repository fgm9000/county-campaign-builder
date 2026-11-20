# Runbook de Deploy e Operação — county-campaign-builder

> 🇧🇷 PT-BR · Baseado na [ADR 003](decisions/003-cloud-run-security.pt-BR.md) e na [ADR 006](decisions/006-county-data-pipeline.pt-BR.md)

---

## 1. Visão geral e arquitetura de segurança

O `county-campaign-builder` é publicado como um serviço **Google Cloud Run** (`county-campaign-builder`, região `us-central1`) no projeto GCP compartilhado `fgm9000-portfolio`, construído e implantado via GitHub Actions.

### Desenho de segurança e isolamento

- **Projeto GCP compartilhado:** `fgm9000-portfolio` (região `us-central1`).
- **Autenticação keyless (WIF):** o CI do GitHub Actions autentica no GCP usando o pool compartilhado `github-pool` e um provider OIDC dedicado (`github-county-campaign-builder`), restrito estritamente ao repositório `fgm9000/county-campaign-builder` e ao branch `refs/heads/main` (`assertion.repository == 'fgm9000/county-campaign-builder' && assertion.ref == 'refs/heads/main'`). Nenhuma chave JSON de service account é gerada ou armazenada no GitHub.
- **Separação estrita de identidades (mínimo privilégio):**
  - **Conta de runtime:** `county-campaign-runtime@fgm9000-portfolio.iam.gserviceaccount.com`
    - **Zero papéis no nível do projeto.**
    - Recebe apenas `roles/secretmanager.secretAccessor` nos **dois segredos** de produção (`anthropic-api-key` e `county-campaign-live-access-code`).
  - **Conta de deploy:** `county-campaign-deploy@fgm9000-portfolio.iam.gserviceaccount.com`
    - `roles/run.developer` no projeto (não `roles/run.admin`, evitando conceder `run.services.setIamPolicy`).
    - `roles/artifactregistry.writer` restrito apenas ao repositório `county-campaign-builder` no Artifact Registry.
    - `roles/iam.serviceAccountUser` restrito apenas à conta `county-campaign-runtime`.
    - `roles/iam.workloadIdentityUser` vinculado à identidade federada do repositório `fgm9000/county-campaign-builder`.
    - **Não possui acesso aos segredos** no Secret Manager.
- **Segredos e dados fora de produção:**
  - `anthropic-api-key` → injetado como variável de ambiente `ANTHROPIC_API_KEY`.
  - `county-campaign-live-access-code` → injetado como variável de ambiente `LIVE_ACCESS_CODE`.
  - **A chave da U.S. Census API (`CENSUS_API_KEY`) NÃO vai para produção:** conforme a ADR 006, os dados do Census ACS e da NOAA Storm Events já vêm pré-computados em `data/counties.parquet` dentro da imagem Docker (somente leitura). O runtime nunca consulta a API do Census nem busca URLs livres externas (apenas chama a API da Anthropic).
- **Configuração do serviço Cloud Run (`county-campaign-builder`):**
  - Recursos: `--memory=512Mi`, `--cpu=1`, `--timeout=120` (necessário para o streaming SSE em `/v1/campaigns/stream`), `--min-instances=0`, `--max-instances=1`, `--concurrency=10`.
  - Exposição e proteção: `--no-invoker-iam-check` (URL pública para o playground estático no GitHub Pages), com `FAKE_MODEL=0`, proteção por código de acesso no cabeçalho `X-Access-Code` (comparação em tempo constante via `hmac.compare_digest` + bloqueio após 5 erros/min por IP), validação estrita de código FIPS contra `data/counties.parquet`, rate limit por IP (`5 req/min`) e cota diária global (`50 req/dia`), além de `hide_input_in_errors=True` e logs JSON sem PII.

---

## 2. Pré-requisitos

### Ferramentas e permissões necessárias

1. **`gcloud` CLI** instalada, atualizada e autenticada com uma conta que possua permissão no projeto `fgm9000-portfolio` para habilitar APIs, criar service accounts, configurar bindings de IAM, gerenciar Artifact Registry, criar providers de WIF e gerenciar segredos no Secret Manager (ex.: dono do projeto ou administrador de IAM/Segurança):

```bash
gcloud auth list
gcloud config set project fgm9000-portfolio
```

2. **`gh` CLI** (GitHub CLI) instalada e autenticada na conta `fgm9000`, com permissão para criar/configurar variáveis e segredos no repositório `fgm9000/county-campaign-builder`:

```bash
gh auth status
```

3. **Inspeção inicial do projeto e do pool WIF compartilhado (`github-pool`):**

```bash
# Confirme o número do projeto (necessário na string do principalSet e do WIF provider)
gcloud projects describe fgm9000-portfolio --format='value(projectNumber)'

# Confirme que o pool compartilhado github-pool existe
gcloud iam workload-identity-pools list \
  --project=fgm9000-portfolio --location=global

# Liste os providers existentes e use um existente como referência de mapeamento, se desejar
gcloud iam workload-identity-pools providers list \
  --project=fgm9000-portfolio --location=global \
  --workload-identity-pool="github-pool"
```

Defina as variáveis de sessão abaixo no seu terminal (Bash / Git Bash) antes de executar os blocos da seção 3:

```bash
PROJECT_ID="fgm9000-portfolio"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
REGION="us-central1"
WIF_POOL="github-pool"
WIF_PROVIDER="github-county-campaign-builder"
GITHUB_REPO="fgm9000/county-campaign-builder"
SERVICE_NAME="county-campaign-builder"
ARTIFACT_REPO="county-campaign-builder"
RUNTIME_SA_NAME="county-campaign-runtime"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA_NAME="county-campaign-deploy"
DEPLOY_SA="${DEPLOY_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

> **Dica:** se usar PowerShell, adapte a sintaxe de variáveis (`$PROJECT_ID = "fgm9000-portfolio"`, etc.) ou rode os comandos em **Git Bash** / **WSL**, mantendo a proteção de leitura mascarada para segredos (seção 3.6).

---

## 3. Passo a passo de criação de recursos (`gcloud`)

Todos os passos abaixo são **idempotentes**: se o recurso já existir, o comando apenas confirma ou reaplica o binding de IAM sem efeitos colaterais.

### 3.1 Habilitar as APIs necessárias

```bash
# Garante que Cloud Run, Artifact Registry, Secret Manager, IAM e IAM Credentials estejam ativos
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"
```

### 3.2 Criar o repositório Docker no Artifact Registry

O workflow `.github/workflows/deploy.yml` publica imagens em `us-central1-docker.pkg.dev/fgm9000-portfolio/county-campaign-builder/county-campaign-builder:<sha>`.

```bash
# Cria o repositório Docker dedicado ao county-campaign-builder apenas se ainda não existir
gcloud artifacts repositories describe "$ARTIFACT_REPO" \
  --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1 \
|| gcloud artifacts repositories create "$ARTIFACT_REPO" \
  --project="$PROJECT_ID" --location="$REGION" \
  --repository-format=docker \
  --description="Imagens Docker do county-campaign-builder"
```

### 3.3 Criar a conta de serviço de runtime (`county-campaign-runtime`)

Esta conta é a identidade do contêiner em execução. **Não conceda nenhum papel no nível do projeto a ela** — o acesso aos dois segredos será concedido diretamente em cada segredo no passo 3.6.

```bash
# Cria a conta de serviço de runtime (sem papéis no projeto)
gcloud iam service-accounts describe "$RUNTIME_SA" \
  --project="$PROJECT_ID" >/dev/null 2>&1 \
|| gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="county-campaign-builder runtime"
```

### 3.4 Criar a conta de serviço de deploy (`county-campaign-deploy`) e seus papéis

Esta é a conta assumida pelo GitHub Actions via WIF. Os papéis seguem o princípio de menor privilégio:

```bash
# Cria a conta de serviço usada pelo GitHub Actions no deploy
gcloud iam service-accounts describe "$DEPLOY_SA" \
  --project="$PROJECT_ID" >/dev/null 2>&1 \
|| gcloud iam service-accounts create "$DEPLOY_SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="county-campaign-builder deploy (GitHub Actions)"

# Permite criar/atualizar revisões do Cloud Run (sem run.admin, evitando setIamPolicy amplo)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/run.developer" \
  --condition=None

# Permite enviar imagens Docker apenas para o repositório county-campaign-builder
gcloud artifacts repositories add-iam-policy-binding "$ARTIFACT_REPO" \
  --project="$PROJECT_ID" --location="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/artifactregistry.writer"

# Permite atuar apenas como a conta de runtime do serviço (e nenhuma outra SA do projeto)
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/iam.serviceAccountUser"
```

> **Nota sobre o bootstrap inicial com `--no-invoker-iam-check`:** como `roles/run.developer` não inclui `run.services.setIamPolicy`, a **primeira criação** do serviço pelo CI com `--no-invoker-iam-check` pode falhar por permissão de IAM. Se isso ocorrer, o dono do projeto cria o serviço uma única vez (ver seção 5.1) usando a conta `county-campaign-runtime` e as mesmas flags; os deploys subsequentes pelo CI atualizarão as revisões normalmente sem precisar elevar a conta de deploy para `roles/run.admin`.

### 3.5 Criar o WIF Provider e vincular ao repositório `fgm9000/county-campaign-builder`

O pool `github-pool` já existe no projeto. Crie um provider OIDC exclusivo para este repositório e restrito à branch `main`:

```bash
# Cria o WIF provider restrito ao repositório fgm9000/county-campaign-builder e à branch main
gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" \
  --project="$PROJECT_ID" --location=global \
  --workload-identity-pool="$WIF_POOL" >/dev/null 2>&1 \
|| gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
  --project="$PROJECT_ID" --location=global \
  --workload-identity-pool="$WIF_POOL" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == 'fgm9000/county-campaign-builder' && assertion.ref == 'refs/heads/main'"

# Autoriza tokens federados desse repositório a assumir a conta county-campaign-deploy
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}"
```

> **Importante:** mantenha `assertion.ref == 'refs/heads/main'` na condição (e **não** `assertion.sub`, que varia conforme o evento/workflow e pode quebrar deploys disparados por `workflow_run`).

### 3.6 Criar/reaproveitar os segredos no Secret Manager e liberar acesso ao runtime

Os dois segredos mapeados pelo `deploy.yml` são:
1. `anthropic-api-key` → variável `ANTHROPIC_API_KEY` (pode ser reaproveitado se já existir no projeto `fgm9000-portfolio`, ou criado agora).
2. `county-campaign-live-access-code` → variável `LIVE_ACCESS_CODE` (código dedicado para este serviço).

#### a) Gerar um código de acesso forte

Gere um código aleatório (32 caracteres URL-safe) e guarde-o no seu gerenciador de senhas. **Nunca** salve esse código no repositório:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

#### b) Criar ou verificar os segredos sem expor valores no histórico do shell

Evite passar valores via `--data-file` com echo ou argumento literal, para não gravar chaves no histórico do shell (`~/.bash_history` ou PSReadLine).

**Verificando `anthropic-api-key` (reaproveitando se já existir):**

```bash
# Verifica se anthropic-api-key já existe no projeto
if gcloud secrets describe anthropic-api-key --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Segredo anthropic-api-key já existe no projeto; será reaproveitado."
else
  read -rs -p "Valor de anthropic-api-key: " VALOR; echo
  ARQ=$(mktemp)
  printf '%s' "$VALOR" > "$ARQ"
  gcloud secrets create anthropic-api-key \
    --project="$PROJECT_ID" \
    --replication-policy=automatic \
    --data-file="$ARQ"
  rm -f "$ARQ"; unset VALOR
fi
```

**Criando `county-campaign-live-access-code` (ou adicionando nova versão):**

Em Git Bash / Linux / macOS:

```bash
read -rs -p "Valor de county-campaign-live-access-code: " VALOR; echo
ARQ=$(mktemp)
printf '%s' "$VALOR" > "$ARQ"
if gcloud secrets describe county-campaign-live-access-code --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets versions add county-campaign-live-access-code \
    --project="$PROJECT_ID" --data-file="$ARQ"
else
  gcloud secrets create county-campaign-live-access-code \
    --project="$PROJECT_ID" \
    --replication-policy=automatic \
    --data-file="$ARQ"
fi
rm -f "$ARQ"; unset VALOR
```

Alternativa equivalente no **PowerShell 7** (com entrada mascarada):

```powershell
$projeto = 'fgm9000-portfolio'
$nome = 'county-campaign-live-access-code'
$valor = Read-Host -MaskInput "Valor de $nome"
$arq = Join-Path $env:TEMP "$nome.tmp"
[System.IO.File]::WriteAllText($arq, $valor)   # grava sem quebra de linha

gcloud secrets describe $nome --project=$projeto *> $null
if ($LASTEXITCODE -eq 0) {
  gcloud secrets versions add $nome --project=$projeto --data-file=$arq
} else {
  gcloud secrets create $nome --project=$projeto --replication-policy=automatic --data-file=$arq
}

Remove-Item $arq -Force
Remove-Variable valor
```

#### c) Conceder `roles/secretmanager.secretAccessor` somente à conta de runtime

```bash
# Libera leitura dos dois segredos apenas para county-campaign-runtime (nunca no projeto)
for SEGREDO in anthropic-api-key county-campaign-live-access-code; do
  gcloud secrets add-iam-policy-binding "$SEGREDO" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

> **Lembrete:** não há segredo para `CENSUS_API_KEY`. Conforme a ADR 006, a tabela de condados (`data/counties.parquet`) é gerada offline via `scripts/build_county_table.py` e empacotada como arquivo estático na imagem Docker.

---

## 4. Configuração das variáveis e segredos no GitHub

O workflow `.github/workflows/deploy.yml` lê três variáveis obrigatórias (`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`), uma variável opcional de CORS (`CORS_ORIGINS`) e o segredo `LIVE_ACCESS_CODE` (usado no smoke test pós-deploy). Além disso, `.github/workflows/eval-live.yml` usa o segredo `ANTHROPIC_API_KEY`.

### 4.1 Variáveis do repositório (`gh variable set`)

```bash
# ID do projeto GCP
gh variable set GCP_PROJECT_ID -R "$GITHUB_REPO" -b "$PROJECT_ID"

# Caminho completo do provider WIF criado no passo 3.5
gh variable set GCP_WIF_PROVIDER -R "$GITHUB_REPO" \
  -b "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"

# Conta de serviço de deploy assumida via WIF
gh variable set GCP_SERVICE_ACCOUNT -R "$GITHUB_REPO" -b "$DEPLOY_SA"

# Origem permitida pelo CORS (apenas esquema + host, sem caminho ou barra final)
gh variable set CORS_ORIGINS -R "$GITHUB_REPO" -b "https://fgm9000.github.io"
```

Confira as variáveis gravadas:

```bash
gh variable list -R "$GITHUB_REPO"
```

### 4.2 Segredos do repositório (`gh secret set`)

Passe o comando **sem `-b`** para que o `gh` solicite o valor em prompt oculto (sem gravar no histórico do shell):

```bash
# Usado pelo step "Post-deploy smoke test" do deploy.yml (deve bater com county-campaign-live-access-code)
gh secret set LIVE_ACCESS_CODE -R "$GITHUB_REPO"

# Usado pelo workflow manual eval-live.yml (evals ao vivo)
gh secret set ANTHROPIC_API_KEY -R "$GITHUB_REPO"
```

Confira os nomes dos segredos cadastrados:

```bash
gh secret list -R "$GITHUB_REPO"
```

---

## 5. Primeiro deploy e verificação via smoke test (`scripts/smoke_test.py`)

### 5.1 Disparo do deploy via GitHub Actions

O workflow `deploy.yml` dispara automaticamente após o workflow `CI` concluir com sucesso na branch `main`, ou manualmente via `workflow_dispatch` (o arquivo `.github/workflows/deploy.yml` já precisa estar na `main`):

```bash
# Dispara o workflow de deploy manualmente
gh workflow run deploy.yml -R "$GITHUB_REPO"

# Acompanha a execução mais recente até concluir
RUN_ID=$(gh run list -R "$GITHUB_REPO" --workflow=deploy.yml \
  --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" -R "$GITHUB_REPO" --exit-status
```

#### Bootstrap pelo dono do projeto (caso o primeiro deploy falhe em `--no-invoker-iam-check`)

Se o passo `Deploy to Google Cloud Run` falhar na primeira criação do serviço por falta da permissão `run.services.setIamPolicy` na conta `county-campaign-deploy`, o dono do projeto deve executar o bootstrap inicial uma única vez usando a imagem já enviada ao Artifact Registry:

```bash
# Substitua <IMAGE_TAG> pelo SHA do commit publicado no passo "Build and push container image"
IMAGE_TAG="<SHA_DO_COMMIT>"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"

gcloud run deploy "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE_URI" \
  --platform=managed \
  --service-account="$RUNTIME_SA" \
  --min-instances=0 \
  --max-instances=1 \
  --concurrency=10 \
  --memory=512Mi \
  --cpu=1 \
  --timeout=120 \
  --no-invoker-iam-check \
  --labels=app=county-campaign-builder \
  --set-env-vars="FAKE_MODEL=0,CORS_ORIGINS=https://fgm9000.github.io" \
  --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,LIVE_ACCESS_CODE=county-campaign-live-access-code:latest"
```

Após esse bootstrap único, rode novamente `gh workflow run deploy.yml -R "$GITHUB_REPO"` para validar o ciclo completo (build + deploy + smoke test automático).

### 5.2 Verificação manual com `scripts/smoke_test.py`

O `deploy.yml` já executa `scripts/smoke_test.py` automaticamente ao final de cada deploy. Para rodar a verificação manualmente a partir da sua máquina:

1. Obtenha a URL do serviço:

```bash
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')
echo "$SERVICE_URL"
```

2. Execute o smoke test oficial com entrada mascarada do código de acesso:

```bash
read -rs -p "Código de acesso (LIVE_ACCESS_CODE): " LIVE_CODE; echo
uv run python scripts/smoke_test.py --url "$SERVICE_URL" --code "$LIVE_CODE"
unset LIVE_CODE
```

O script valida, em sequência:
- `GET /health` → HTTP `200` com `{"status": "ok"}`.
- `POST /v1/campaigns` **sem** cabeçalho `X-Access-Code` → HTTP `401` (confirma que a proteção do modo ao vivo está ativa).
- `POST /v1/campaigns` **com** `X-Access-Code` (condado padrão `48113` — Dallas County, TX) → HTTP `200` e payload `CountyCampaign` válido (`status="success"`, `unit_economics.verdict` válido e `assets`).
- `POST /v1/campaigns/stream` **com** `X-Access-Code` → HTTP `200`, `Content-Type: text/event-stream`, iniciando com evento `progress` e encerrando com evento `done` contendo o `CountyCampaign` válido.

*(Se quiser testar uma instância local rodando com `FAKE_MODEL=1`, passe `--fake-mode` para pular a checagem de `401`.)*

### 5.3 Conectar o front-end estático (`web/config.json`) e publicar o GitHub Pages

1. Edite `web/config.json` informando a URL do Cloud Run **sem barra no final** (o campo lido pelo `web/app.js` é `apiUrl`):

```json
{
  "apiUrl": "https://<URL_DO_SERVICO>"
}
```

2. Faça commit e push para `main` (o workflow `.github/workflows/pages.yml` dispara automaticamente quando há alterações em `web/**`, desde que o repositório esteja **público**):

```bash
git add web/config.json
git commit -m "chore: configure live API URL for GitHub Pages"
git push origin main
```

3. Confirme que o GitHub Pages está configurado com origem em GitHub Actions:

```bash
gh api -X POST "repos/${GITHUB_REPO}/pages" -f build_type=workflow \
|| gh api "repos/${GITHUB_REPO}/pages"
```

---

## 6. Operação, monitoramento de custos e desligamento do modo ao vivo

### 6.1 Logs e observabilidade

Os logs da aplicação são emitidos em JSON estruturado de linha única (sem PII e sem valores de segredos):

```bash
# Últimas 50 linhas de log do serviço
gcloud run services logs read "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --limit=50

# Apenas erros (severity >= ERROR)
gcloud run services logs read "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --limit=50 \
  --log-filter='severity>=ERROR'
```

### 6.2 Monitoramento de custos e teto de US$ 30/mês na Anthropic

1. **Teto mensal na Anthropic (obrigatório antes de compartilhar o código de acesso):**
   - Configure o limite mensal de gasto (**spend limit**) de **US$ 30/mês** diretamente no console da Anthropic (`console.anthropic.com`, em *Billing / Spend Limits*).
   - O GCP **não** controla nem enxerga o consumo da API da Anthropic. Configure e confirme o valor salvo de US$ 30 antes de distribuir qualquer código de acesso.
2. **Camadas de proteção contra abuso na própria API:**
   - Código de acesso obrigatório em `/v1/campaigns` e `/v1/campaigns/stream` (`X-Access-Code`).
   - Bloqueio de força bruta: máximo de `5` tentativas inválidas de código por minuto por IP (`MAX_FAILED_CODES_PER_MINUTE=5`).
   - Rate limit por IP (`RATE_LIMIT_PER_MINUTE=5`) e cota diária global em UTC (`DAILY_QUOTA=50` requisições/dia por instância; como `--max-instances=1`, há no máximo uma instância ativa).
3. **Custo de infraestrutura GCP:**
   - **Cloud Run:** `--min-instances=0` garante custo zero quando ocioso; cobrança apenas durante requisições ativas (`512Mi`, `1` vCPU).
   - **Artifact Registry:** cada deploy envia uma nova imagem com tag `<sha>`. Configure uma política de limpeza para reter apenas as últimas versões e evitar acúmulo de armazenamento. Crie um arquivo `politica-limpeza.json` **fora do repositório**:

   ```json
   [
     {"name": "manter-ultimas", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 5}},
     {"name": "apagar-antigas", "action": {"type": "Delete"}, "condition": {"olderThan": "604800s"}}
   ]
   ```

   Aplique (use `--dry-run` antes, se desejar simular):

   ```bash
   gcloud artifacts repositories set-cleanup-policies "$ARTIFACT_REPO" \
     --project="$PROJECT_ID" --location="$REGION" \
     --policy=politica-limpeza.json
   ```

### 6.3 Rotação do código de acesso ou da chave da Anthropic

O Cloud Run resolve a referência `:latest` dos segredos **no momento em que uma nova revisão é criada**, não a cada requisição. Portanto, toda rotação exige: (1) adicionar nova versão no Secret Manager e (2) publicar uma nova revisão do serviço.

```bash
# 1. Grava nova versão do código de acesso sem expor no histórico
read -rs -p "Novo código de acesso: " NOVO_CODIGO; echo
ARQ=$(mktemp)
printf '%s' "$NOVO_CODIGO" > "$ARQ"
unset NOVO_CODIGO

gcloud secrets versions add county-campaign-live-access-code \
  --project="$PROJECT_ID" --data-file="$ARQ"
rm -f "$ARQ"

# 2. Cria uma nova revisão para resolver :latest
gcloud run services update "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" \
  --update-env-vars="ACCESS_CODE_ROTATED_AT=$(date +%Y%m%d%H%M)"
```

Em seguida:
- Atualize o segredo `LIVE_ACCESS_CODE` no GitHub (`gh secret set LIVE_ACCESS_CODE -R "$GITHUB_REPO"`) para que os próximos deploys não falhem no smoke test.
- Desabilite a versão anterior do segredo no GCP (`gcloud secrets versions list county-campaign-live-access-code --project="$PROJECT_ID"` lista os números de versão; use `gcloud secrets versions disable <VERSAO> --secret=county-campaign-live-access-code --project="$PROJECT_ID"`).
- Se rotacionar `anthropic-api-key`, atualize também o segredo `ANTHROPIC_API_KEY` no GitHub (`gh secret set ANTHROPIC_API_KEY -R "$GITHUB_REPO"`).

### 6.4 Como desligar o modo ao vivo se necessário

Os cenários pré-computados do GitHub Pages (`web/examples.json`) funcionam de forma 100% estática e não dependem do Cloud Run. Caso precise interromper o modo ao vivo por segurança ou controle de custos, escolha uma das opções abaixo (da menos para a mais drástica):

1. **Rotacionar `county-campaign-live-access-code` para um valor secreto não compartilhado (recomendado):**
   - Execute o procedimento da seção 6.3 com um novo valor aleatório e não o divulgue.
   - Todas as chamadas a `/v1/campaigns` e `/v1/campaigns/stream` passam a receber HTTP `401` imediatamente (sem gastar tokens da Anthropic), enquanto `/health` continua respondendo `200`.
   - > **Não remova `ANTHROPIC_API_KEY` ou `LIVE_ACCESS_CODE` com `FAKE_MODEL=0`:** o `Settings` valida a presença de ambos na inicialização; sem um deles, o contêiner falha ao subir e o `/health` para de responder.

2. **Reativar a exigência de IAM no Cloud Run (bloqueio na borda do Google):**
   - Como o serviço usa `--no-invoker-iam-check`, remover `allUsers` não tem efeito; é preciso reabilitar `--invoker-iam-check`:

   ```bash
   gcloud run services update "$SERVICE_NAME" \
     --project="$PROJECT_ID" --region="$REGION" \
     --invoker-iam-check
   ```

   - Qualquer requisição sem token IAM do Google (incluindo `/health`) passa a receber HTTP `403`.
   - Para impedir que o próximo deploy do CI reabra o endpoint, desative temporariamente o workflow de deploy:

   ```bash
   gh workflow disable deploy.yml -R "$GITHUB_REPO"
   ```

3. **Excluir o serviço Cloud Run:**
   - Remove completamente a superfície exposta (os logs históricos continuam disponíveis no Cloud Logging). Recriar o serviço posteriormente exigirá o bootstrap inicial (seção 5.1) caso o deploy use `--no-invoker-iam-check`.

   ```bash
   gcloud run services delete "$SERVICE_NAME" \
     --project="$PROJECT_ID" --region="$REGION"
   ```

### 6.5 Troubleshooting rápido

| Sintoma | Causa provável | Como verificar e corrigir |
|---|---|---|
| `google-github-actions/auth` falha com `403` ou `unauthorized_client` | Divergência no repositório/branch do provider WIF ou no `principalSet` | Confira `gh variable list -R fgm9000/county-campaign-builder`, inspecione o provider `github-county-campaign-builder` (`gcloud iam workload-identity-pools providers describe ...`) e valide `attribute.repository/fgm9000/county-campaign-builder`. |
| Erro de permissão ao ler segredo no startup | `county-campaign-runtime` sem `roles/secretmanager.secretAccessor` em um dos 2 segredos | Rode `gcloud secrets get-iam-policy anthropic-api-key --project=fgm9000-portfolio` e o mesmo para `county-campaign-live-access-code`, refazendo o binding do passo 3.6c se faltar. |
| Primeiro deploy falha em `--no-invoker-iam-check` | `roles/run.developer` não inclui `run.services.setIamPolicy` na criação inicial | Execute o bootstrap único pelo dono do projeto (seção 5.1) sem elevar a conta de deploy para `roles/run.admin`. |
| Navegador bloqueia chamadas por CORS | Origem ausente em `CORS_ORIGINS` ou configurada com caminho/barra final | Garanta `CORS_ORIGINS=https://fgm9000.github.io` (sem `/county-campaign-builder` e sem `/` no final) e atualize a revisão. |
| Smoke test falha no `401` ou retorna `401` com código válido | `secrets.LIVE_ACCESS_CODE` no GitHub diferente do segredo `county-campaign-live-access-code:latest` no GCP, ou revisão antiga | Atualize o segredo no GitHub ou crie uma nova revisão no Cloud Run para resolver `:latest` (seção 6.3). |
| Partida a frio acima de 15 s ou uso de RAM acima de 400 MB | Violação do critério de revisão da ADR 003 | Verifique métricas e logs no Cloud Run (`county-campaign-builder`) e reabra a ADR 003 se o comportamento persistir. |
