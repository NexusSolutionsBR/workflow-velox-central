# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Velox é um pipeline fullstack para atendimentos de socorro em pista. O operador informa a URL de uma sessão da Helena CRM + número da ficha; o sistema busca todas as mensagens, transcreve áudios, envia imagens ao Google Drive e gera um relatório técnico formal via agente de IA (Agno). O operador revisa o relatório no Quadro de Revisão.

O projeto é em **pt-BR**. Prompts, logs, mensagens de erro e textos da UI estão em português — manter ao editar.

## Run / build / dev commands

```bash
# Subir tudo (backend, celery_worker, frontend, redis)
docker compose up -d --build

# Logs do worker (stream mais útil)
docker compose logs -f celery_worker

# Criar usuário (CLI interativo)
docker compose exec backend python -m app.scripts.create_user

# Debug do Google Drive
docker compose exec backend python -m app.scripts.debug_gdrive

# Lint / build do frontend
cd frontend && npm run lint
cd frontend && npm run build
```

Endpoints: frontend em `http://localhost:5173`, FastAPI em `http://localhost:3000`, Swagger em `http://localhost:3000/docs`. Todas as rotas da API têm prefixo `/api` (ex: `http://localhost:3000/api/sessions/start`).

---

## Arquitetura

### Split FastAPI + Celery

A imagem do backend é única mas sobe como **dois serviços**:

- **`backend`** — servidor FastAPI. Endpoints em `app/api/{auth,sessions,center,audit}.py` são finos: validam input, persistem `SessionRecord` no SQLite e despacham tasks via `.delay(...)`.
- **`celery_worker`** — consome a fila Redis (`main-queue`) e executa as tasks pesadas em `app/services/tasks.py`.

Ambos acessam o mesmo **PostgreSQL** via SQLModel (`app/core/database.py`), configurado por `DATABASE_URL` (o `docker-compose.yml` injeta `postgresql://velox:...@postgres:5432/velox` em ambos os serviços). O default `sqlite:///./dev.db` em `config.py` só é usado se `DATABASE_URL` não estiver definida. O schema é criado automaticamente no startup do FastAPI (`lifespan` em `app/main.py`), seguido de **migrações incrementais** via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (colunas adicionadas após a criação inicial das tabelas).

O Redis serve dois propósitos: broker/backend do Celery **e** armazenamento temporário de logs de pipeline e do `raw_content`.

### Pipeline de processamento (`process_session`)

Fluxo disparado pelo `POST /api/sessions/start`:

```
Helena API → mensagens paginadas → ordenadas por createdAt
  ↓
Loop de mensagens:
  TEXT  → [DD/MM/YYYY HH:MM:SS] [operador|prestador] texto
  AUDIO → download + Whisper transcription (se do_transcribe=True)
          → [DD/MM/YYYY HH:MM:SS] [operador|prestador] ÁUDIO (Transcrito): ...
  IMAGE → referência na timeline + upload ao Drive (se do_upload_images=True)
  ↓
raw_content salvo no Redis (TTL 7 dias) E na coluna session.raw_content (permanente)
Status → COMPLETED
  ↓
[opcional] Relatório com IA (se do_summary=True)
  ↓
[se do_upload_images=True] Upload de imagens ao Drive
  ↓
[se do_upload_images=True] Agenda sync_session_images (countdown=AUTO_SYNC_DELAY_SECONDS)
                            + cria ScheduledSync(status="PENDING") no SQLite
```

O Celery task é síncrono na boundary do Celery mas envolve um pipeline async via `asyncio.run(...)` — necessário porque os downloads usam `httpx` com streaming assíncrono.

### Filtro de mensagens BOT

Mensagens com `origin: "BOT"` são respostas automáticas do chatbot pré-atendimento. O pipeline detecta a **última** mensagem com esse campo antes de processar:

- `raw_content:{session_id}` (Redis) → timeline **completa** (todas as mensagens, incluindo BOT) — usada no export `.txt` e no relatório HTML
- `ai_content:{session_id}` (Redis, TTL 7d) → timeline apenas das mensagens **após** a última mensagem do bot — usada exclusivamente para `generate_summary()`

A `summarize_session` (acionamento manual) também prioriza `ai_content` com fallback para `raw_content`.

Se não houver nenhuma mensagem `origin=BOT`, ambos os conteúdos são idênticos.

### Formato da timeline (raw_content)

Cada linha segue o padrão:
```
[DD/MM/YYYY HH:MM:SS] [operador] texto
[DD/MM/YYYY HH:MM:SS] [prestador] ÁUDIO (Transcrito): transcrição
[DD/MM/YYYY HH:MM:SS] IMAGEM: nome_arquivo.jpg
```

- `direction: TO_HUB` → `[operador]`
- `direction: FROM_HUB` → `[prestador]`
- Timestamp com segundos, fuso `America/Cuiaba`
- Fallback de timestamp: `createdAt || timestamp`
- Mensagens ordenadas por `createdAt` antes do loop

### Tasks Celery disponíveis

| Task | Gatilho | Descrição |
|---|---|---|
| `process_session` | `POST /api/sessions/start` | Pipeline completo (busca + mídias + agendamento auto-sync) |
| `summarize_session` | `POST /api/sessions/{id}/summarize` | Gera relatório com IA a partir do raw_content |
| `sync_session_images` | `POST /api/sessions/{id}/sync-images` ou agendamento automático | Re-busca mensagens, envia imagens novas ao Drive, marca ScheduledSync como COMPLETED |

### Status da sessão

```
PENDING → PROCESSING → COMPLETED
                    ↘ ERROR
                    ↘ CANCELLED

COMPLETED → SUMMARIZING → COMPLETED  (ao clicar "Resumir Relatório")
COMPLETED → SYNCING     → COMPLETED  (ao clicar "Enviar Novas Imagens" ou execução automática)
```

### Agente de IA (`app/agents/summarizer_agent.py`)

**Agente único** via Agno (`generate_summary`):

- **ReportAgent** — recebe a timeline com identificação de remetente (`[operador]`/`[prestador]`) e produz diretamente o relatório no formato final:
  ```
  N. DD/MM/YYYY, HH:MM:SS — SEÇÃO: DESCRIÇÃO EM MAIÚSCULO
  ```
  Regras: granularidade cronológica (um evento por linha), timestamps extraídos da timeline de origem (nunca inventados), atribuição correta de sujeitos, linguagem técnica formal em maiúsculo.

O provider de IA é configurado via `.env` (`AI_PROVIDER` + `AI_CHAT_MODEL`). Imports dos providers são lazy em `llm_factory.py` — apenas o provider configurado é carregado.

`TranscriberAgent` (`transcriber_agent.py`) usa exclusivamente OpenAI Whisper para STT.

### Google Drive (`app/services/gdrive.py`)

Suporta dois métodos de autenticação (nessa ordem):
1. **OAuth user** — `GOOGLE_DRIVE_CLIENT_ID` + `GOOGLE_DRIVE_CLIENT_SECRET` + `GOOGLE_DRIVE_REFRESH_TOKEN`
2. **Service Account** — `GOOGLE_SERVICE_ACCOUNT_FILE` (caminho do JSON)

Se nenhum estiver configurado: modo mock (retorna IDs falsos, nada é enviado).

`gdrive.py` só faz as chamadas brutas à API do Drive (`find_or_create_folder`, `_make_public`, `upload_file`). A **orquestração e o filtro de imagens ficam em `app/services/tasks.py`** (`_upload_images_from_messages`), não em `gdrive.py`.

**Filtro de intervalo de imagens** (em `tasks.py`): janela deslizante controlada por duas variáveis:
- `GDRIVE_IMAGE_INTERVAL_MINUTES` (padrão: 5) — duração da janela em minutos
- `GDRIVE_IMAGE_MAX_PER_INTERVAL` (padrão: 1) — máximo de imagens por janela

Implementado com `deque(maxlen=max_per_interval)` em `_upload_images_from_messages`. A janela fica cheia quando `len(upload_window) >= max_per_interval`; a próxima imagem só é aceita se `img_dt - upload_window[0] >= interval`. Delta negativo (imagens fora de ordem) é ignorado.

**Retry com backoff** (em `upload_file`): retenta automaticamente em erros HTTP 429/500/503 **e em erros de rede transitórios** (`socket.timeout`, `TimeoutError`, `ConnectionError`, `OSError`) com espera exponencial (2^attempt + jitter, até 5 tentativas). Os erros de rede não são `HttpError` e antes escapavam do retry quebrando o pipeline. Falha definitiva somente se esgotar as tentativas.

**Tolerância a falha de upload no pipeline** (em `tasks.py`): o upload de imagens em `process_session` roda dentro de `try/except` — se o Drive falhar (ex: timeout), o atendimento **permanece `COMPLETED`** (os dados já estão íntegros) e o sync automático agendado tentará reenviar as imagens depois.

### Re-checagem Automática de Imagens (ScheduledSync)

Ao final de `process_session` (quando `do_upload_images=True`), o sistema agenda automaticamente `sync_session_images` para rodar após `AUTO_SYNC_DELAY_SECONDS` (padrão: 10800s = 3h):

```python
scheduled_task = sync_session_images.apply_async(args=[session_id, ficha], countdown=delay)
# + persiste ScheduledSync(status="PENDING") no SQLite
```

Quando `sync_session_images` conclui (incluso via agendamento automático), todos os `ScheduledSync` com `status="PENDING"` para aquela sessão são marcados como `COMPLETED` no bloco `finally`.

Para cancelar antes da execução: `DELETE /api/sessions/scheduled-syncs/{id}` — chama `celery_app.control.revoke(task_id, terminate=True)` e marca `CANCELLED`.

**Teste local:** adicionar `AUTO_SYNC_DELAY_SECONDS=10` no `.env` para simular em 10 segundos.

### Endpoints de sessão

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/sessions` | Lista paginada de sessões (filtros `ficha`, `status`, `page`, `per_page`) — alimenta a página `/fichas` |
| POST | `/api/sessions/start` | Inicia pipeline |
| GET | `/api/sessions/{id}/status` | Status + logs + resumo |
| POST | `/api/sessions/{id}/cancel` | Cancela |
| POST | `/api/sessions/{id}/summarize` | Gera relatório com IA |
| DELETE | `/api/sessions/{id}/summary` | Apaga resumo do banco |
| PUT | `/api/sessions/{id}/summary` | Salva rascunho editado (`summaryText`) |
| GET | `/api/sessions/{id}/report-html` | Página HTML otimizada para impressão/PDF (auth via cookie httpOnly; `?public_only=true` reenumera só linhas não-vazias) |
| POST | `/api/sessions/{id}/sync-images` | Sincroniza imagens novas |
| GET | `/api/sessions/{id}/export` | Download .txt (resumo + timeline) |
| GET | `/api/sessions/{id}/debug-messages` | JSON com mensagens texto brutas para debug |
| GET | `/api/sessions/scheduled-syncs` | Lista sincronizações automáticas pendentes |
| POST | `/api/sessions/scheduled-syncs/{id}/run-now` | Executa um sync agendado imediatamente |
| DELETE | `/api/sessions/scheduled-syncs/{id}` | Cancela sincronização agendada |

> **Roteamento:** `/scheduled-syncs` (rota estática) é processado corretamente por FastAPI mesmo declarado após `/{session_id}/...`, pois todos os demais endpoints têm sufixos literais (`/status`, `/cancel`, etc.) e não há ambiguidade.

> **`/report-html`:** usa `CurrentUserDep` (cookie httpOnly). A página é aberta em nova aba via `window.open` e o browser envia o cookie automaticamente — **não** passar o JWT em `?token=` (vetor de vazamento via URL/logs/referer).

### Logs em tempo real

Logs do pipeline são escritos no Redis (`pipeline_logs:{session_id}`, lista, TTL 24h) via `_log()` em `tasks.py`. O endpoint `/sessions/{id}/status` lê essa lista e retorna o array `logs` para o frontend exibir no painel de terminal em tempo real.

### Auth e auditoria

- JWT (HS256) emitido por `/api/auth/login`, validado pela dep `CurrentUserDep` (`app/core/security.py`). Sem refresh token.
- `AuditLogMiddleware` (`app/core/audit.py`) loga silenciosamente todas as requests em `/api/sessions`, `/api/center` e `/api/auth` na tabela `audit_log`. Não aborta em token inválido — a enforcement é por rota.

### Frontend (`frontend/src/pages/Dashboard.tsx`)

Fluxo do operador:

1. Preenche URL da sessão + ficha
2. Seleciona opções: transcrever áudios / enviar imagens / gerar resumo com IA
3. Clica **Iniciar Processamento** → `POST /api/sessions/start`
4. Frontend faz polling `GET /api/sessions/{id}/status` a cada 2s, exibe logs em tempo real
5. Botão **Parar** disponível durante processamento → `POST /api/sessions/{id}/cancel`
6. Quando `COMPLETED`, aparecem:
   - **Resumir Relatório** (se sem resumo) → `POST /api/sessions/{id}/summarize`
   - **Limpar Resumo** (se com resumo) → `DELETE /api/sessions/{id}/summary`
   - **Exportar Relatório** → `GET /api/sessions/{id}/export` (download `.txt`)
   - **Enviar Novas Imagens** → `POST /api/sessions/{id}/sync-images`
   - **Debug JSON** → `GET /api/sessions/{id}/debug-messages` (download `.json`)
7. Com resumo: **Quadro de Revisão** com editor de texto e três ações:
   - **Salvar Rascunho** → `PUT /api/sessions/{id}/summary` — persiste edições no banco antes de qualquer envio
   - **Visualizar PDF** → abre `GET /api/sessions/{id}/report-html?token=...` em nova aba; o browser dispara `window.print()` automaticamente
   - **Inserir MGM (Center)** → `POST /api/center/mgm`

### Frontend — Página de Tarefas Pendentes (`frontend/src/pages/PendingTasks.tsx`)

Nova página em `/tarefas-pendentes`:
- Tabela com todas as `ScheduledSync` de status `PENDING`
- Colunas: Ficha, ID do Chat (truncado), Contato, Agendado Para, **Contagem Regressiva** (atualiza a cada 1s), Status, Ação
- Botão **Cancelar** chama `DELETE /api/sessions/scheduled-syncs/{id}`
- Menu lateral exibe badge vermelho com a contagem em tempo real (polling a cada 30s)

### Frontend — Página de Histórico de Fichas (`frontend/src/pages/History.tsx`)

Página em `/fichas`:
- Lista paginada de todas as `SessionRecord` (consome `GET /api/sessions`)
- Filtros por `ficha` e `status`; mostra operador, contato, se há resumo (`hasSummary`) e raw_content (`hasRawContent`)
- Ponto de entrada para reabrir/revisar atendimentos anteriores

### Rotas do frontend (`App.tsx`)

| Rota | Página | Acesso |
|---|---|---|
| `/login` | `Login` | Público |
| `/dashboard` | `Dashboard` | Autenticado |
| `/tarefas-pendentes` | `PendingTasks` | Autenticado |
| `/fichas` | `History` | Autenticado |
| `/auditoria` | `Audit` | ADMIN (redireciona para `/dashboard` se não-admin) |

A URL base da API vem de `VITE_API_URL` (inclui o prefixo `/api`). Sem proxy Vite; CORS configurado via `ALLOWED_ORIGINS` no backend.

---

## Banco de Dados

### Tabelas existentes

| Tabela | Modelo | Descrição |
|---|---|---|
| `user` | `User` | Operadores do sistema |
| `session` | `SessionRecord` | Registro de cada pipeline executado |
| `media_file` | `MediaFile` | Imagens/áudios processados por sessão |
| `summary` | `Summary` | Resumo original e editado por sessão |
| `scheduled_sync` | `ScheduledSync` | Tarefas de re-checagem automática agendadas |
| `audit_log` | `AuditLog` | Log de todas as requests auditáveis |

### `SessionRecord` — campos relevantes
- `session_id` (unique): ID da sessão Helena (extraído da URL)
- `raw_content` (Text): timeline completa persistida (fallback quando o Redis expira)
- `session_url`: URL original da sessão Helena
- `drive_folder_url`: link público da pasta da ficha no Drive
- `contact_name`: nome do prestador/contato
- `center_inserted` / `center_duplicate`: estado da inserção no Center
- `error_message`: motivo da falha em syncs/pipeline

> Colunas adicionadas após a criação inicial das tabelas (`drive_folder_url`, `center_inserted`, `center_duplicate`, `error_message`, e `contact_name`/`error_message` em `scheduled_sync`) são aplicadas via migrações incrementais no `lifespan` de `main.py`.

### `ScheduledSync` — campos relevantes
- `task_id` (unique): ID Celery usado para `revoke()` no cancelamento
- `run_at`: datetime UTC de execução agendada
- `contact_name`: extraído do primeiro `FROM_HUB` com campo `senderName`/`contactName`/`contact.name`/`sender.name`; `null` se não encontrado

---

## Convenções a preservar

- **Sem mock de fallback no velox.py** — erros da Helena API aparecem nos logs diretamente.
- **Google Drive mock** — se sem credenciais, retorna IDs falsos sem quebrar o pipeline. Preservar.
- **Center API mock** — se `CENTER_API_KEY` não configurada, retorna sucesso simulado.
- **Transcriber mock** — se `OPENAI_API_KEY` não configurada, retorna texto stub.
- **`markdown=False`** nos agentes Agno — obrigatório para não quebrar o contrato de texto puro do relatório.
- **Imports lazy** em `llm_factory.py` — não importar todos os providers no topo; só o provider ativo é carregado.
- **Todos os logs e strings de UI em português.**
- **Estilo de dependências** do FastAPI: `Annotated` (`CurrentUserDep`, `DbSessionDep`).
- **raw_content** — armazenado em **dois lugares**: Redis com TTL de 7 dias (`_CONTENT_TTL`, acesso rápido) **e** na coluna `session.raw_content` (permanente). Reconstruído a cada re-execução do pipeline. O agente consome esse conteúdo para gerar o relatório; `summarize_session` usa o Redis e cai para a coluna do banco quando o TTL expira.
- **ScheduledSync** — só é criado quando `do_upload_images=True`. Não criar se o usuário desativou upload.
- **`/api/sessions/{id}/report-html`** usa `CurrentUserDep` (cookie httpOnly) — a página é aberta em nova aba via `window.open` e o browser envia o cookie automaticamente. Não voltar a passar o JWT em `?token=` (vetor de vazamento via URL/logs/referer).

### Segurança (preservar)

- **Auth via cookie httpOnly (browser) + token no corpo (uso externo)** — `/api/auth/login` define o cookie `httponly`/`samesite=lax`/`secure` (`COOKIE_SECURE`) E devolve `access_token` no corpo para clientes/integrações fora do browser. O frontend usa exclusivamente o cookie e **nunca** guarda o token no localStorage.
- **`AuthGateMiddleware` (main.py)** — porta de entrada para `/api`: sem token JWT válido, devolve **`401` uniforme** independentemente de a rota existir ou do método HTTP. Impede que `405`/`404` vazem a existência de endpoints para quem não tem token. O token é lido do cookie `access_token` **ou** do header `Authorization: Bearer` (uso externo). Rotas públicas: `/api/auth/login`, `/api/auth/logout` e preflight `OPTIONS`. Registrado "dentro" de CORS/Security para que o 401 carregue os headers necessários. Não remover — os `Depends` por rota continuam como defesa em profundidade (validação de usuário no banco + roles).
- **Docs desligadas por padrão** — `/docs`, `/redoc` e `/openapi.json` só existem quando `ENABLE_DOCS=true`. Mantém a superfície da API oculta de quem não tem token. Habilitar apenas em dev.
- **`/api/audit` é ADMIN-only** — usa `require_role(["ADMIN"])`. Não relaxar para OPERATOR (expõe IPs e ações de todos).
- **Headers de segurança** — `SecurityHeadersMiddleware` em `main.py` aplica `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` e `Cache-Control` a todas as respostas.
- **Escaping no `report-html`** — todo valor dinâmico passa por `html.escape()` (`_fill_template`, summary, drive_url). Nunca interpolar input do usuário sem escapar.

---

## Documentação adicional

- Referência técnica do backend: [`backend/BACKEND.md`](backend/BACKEND.md)
- Referência técnica do frontend: [`frontend/FRONTEND.md`](frontend/FRONTEND.md)
