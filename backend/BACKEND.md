# BACKEND — Referência Técnica

Sistema backend do Velox: FastAPI + Celery + SQLite + Redis.

---

## Estrutura de Arquivos

```
backend/
├── app/
│   ├── agents/
│   │   ├── __init__.py            # Re-exporta transcribe_audio, generate_summary
│   │   ├── llm_factory.py         # Fábrica de modelos Agno (OpenAI / Google / Anthropic)
│   │   ├── summarizer_agent.py    # ReportAgent — gera relatório técnico formal
│   │   └── transcriber_agent.py   # TranscriberAgent — transcrição Whisper (OpenAI)
│   ├── api/
│   │   ├── auth.py                # POST /api/auth/login, /api/auth/logout
│   │   ├── audit.py               # GET /api/audit — logs de auditoria paginados
│   │   ├── center.py              # POST /api/center/mgm — integração Center API
│   │   └── sessions.py            # Todos os endpoints de sessão (ver tabela abaixo)
│   ├── core/
│   │   ├── audit.py               # AuditLogMiddleware — loga todas as requests silenciosamente
│   │   ├── celery_app.py          # Instância do Celery com broker Redis
│   │   ├── config.py              # Settings — lê variáveis do .env
│   │   ├── database.py            # SQLModel engine + get_session dependency
│   │   └── security.py            # JWT HS256, bcrypt, CurrentUserDep, DbSessionDep
│   ├── models/
│   │   ├── __init__.py
│   │   └── domain.py              # Todos os modelos SQLModel (tabelas)
│   ├── scripts/
│   │   ├── create_user.py         # CLI interativo para criar usuário
│   │   ├── debug_agents.py        # Teste dos agentes de IA
│   │   ├── debug_gdrive.py        # Teste da integração Google Drive
│   │   ├── debug_velox.py         # Teste da Helena API
│   │   └── oauth_setup.py         # Fluxo OAuth para obter refresh token do Drive
│   ├── services/
│   │   ├── gdrive.py              # Upload ao Google Drive (OAuth / Service Account / mock)
│   │   ├── tasks.py               # Tasks Celery: process_session, summarize_session, sync_session_images
│   │   └── velox.py               # fetch_session_messages — paginação Helena API
│   └── main.py                    # App FastAPI, lifespan, routers, CORS, middleware
├── Dockerfile
└── requirements.txt
```

---

## Modelos de Banco de Dados (`domain.py`)

Banco SQLite em `backend/dev.db`. Criado automaticamente no startup via `SQLModel.metadata.create_all(engine)`.

### `User` (`user`)
| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID PK | Identificador |
| `name` | str | Nome |
| `email` | str unique | E-mail (login) |
| `password` | str | Hash bcrypt |
| `role` | str | `OPERATOR` (padrão) |
| `created_at` | datetime | UTC |

### `SessionRecord` (`session`)
| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID PK | Identificador interno |
| `session_id` | str unique | ID extraído da URL Helena |
| `ficha` | str | Número da ficha |
| `status` | str | `PENDING / PROCESSING / COMPLETED / ERROR / CANCELLED / SUMMARIZING / SYNCING` |
| `task_id` | str | ID da task Celery ativa |
| `created_at` | datetime | UTC |

### `MediaFile` (`media_file`)
| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID PK | — |
| `session_id` | FK → session | — |
| `file_id` | str unique | ID do arquivo na Helena |
| `type` | str | `IMAGE / AUDIO / VIDEO` |
| `url` | str | Drive ID após upload |
| `status` | str | `PENDING / UPLOADED / FAILED` |
| `hash` | str | Hash para deduplicação |

### `Summary` (`summary`)
| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID PK | — |
| `session_id` | FK → session unique | — |
| `original_summary` | str | Texto gerado pela IA |
| `edited_summary` | str? | Texto editado pelo operador (rascunho) |
| `created_at` | datetime | UTC |

### `ScheduledSync` (`scheduled_sync`)
| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID PK | — |
| `session_id` | FK → session | — |
| `ficha` | str | Número da ficha |
| `contact_name` | str? | Nome do contato extraído das mensagens (senderName etc.) |
| `task_id` | str unique | ID Celery para `revoke()` |
| `run_at` | datetime | Quando a task executará (UTC) |
| `status` | str | `PENDING / COMPLETED / CANCELLED` |
| `created_at` | datetime | UTC |

> Criada automaticamente ao reiniciar. Populada após `_async_process_session` quando `do_upload_images=True`.

### `AuditLog` (`audit_log`)
Preenchida pelo `AuditLogMiddleware` em cada request para `/sessions`, `/center`, `/auth`.

---

## Endpoints da API

Prefixos registrados em `main.py`:

| Prefixo | Arquivo | Tags |
|---|---|---|
| `/auth` | `api/auth.py` | auth |
| `/sessions` | `api/sessions.py` | sessions |
| `/center` | `api/center.py` | center |
| `/audit` | `api/audit.py` | audit |

### `/sessions` — todos os endpoints

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| POST | `/sessions/start` | JWT | Inicia pipeline completo |
| POST | `/sessions/{id}/cancel` | JWT | Cancela task Celery ativa |
| POST | `/sessions/{id}/summarize` | JWT | Dispara geração de resumo com IA |
| POST | `/sessions/{id}/sync-images` | JWT | Re-sincroniza imagens ao Drive |
| GET | `/sessions/{id}/status` | JWT | Status + logs + resumo |
| GET | `/sessions/{id}/export` | JWT | Download `.txt` (resumo + timeline) |
| DELETE | `/sessions/{id}/summary` | JWT | Apaga resumo do banco |
| PUT | `/sessions/{id}/summary` | JWT | Salva rascunho editado (`summaryText`) |
| GET | `/sessions/{id}/report-html` | `?token=` | HTML otimizado para PDF (abre em nova aba) |
| GET | `/sessions/scheduled-syncs` | JWT | Lista sincronizações agendadas (`PENDING`) |
| DELETE | `/sessions/scheduled-syncs/{id}` | JWT | Cancela sync agendado (revoke + CANCELLED) |
| GET | `/sessions/{id}/debug-messages` | JWT | JSON com mensagens texto brutas |

> **Atenção de roteamento:** `/scheduled-syncs` (rota estática) é definido após os parâmetros `/{session_id}/...` no arquivo, mas não há conflito porque todos os outros endpoints têm segmentos literais de sufixo (`/status`, `/cancel`, etc.).

> **`/report-html`:** O JWT é passado como `?token=` (query param) pois a página é aberta diretamente pelo browser. A função `_get_user_from_token_param` valida o token manualmente sem o `oauth2_scheme`.

---

## Tasks Celery (`services/tasks.py`)

Broker e backend: Redis (`REDIS_URL`). Fila: `main-queue` (padrão).

### `process_session(session_id, ficha, do_transcribe, do_upload_images, do_summary)`
Pipeline completo. Fluxo interno em `_async_process_session`:
1. `fetch_session_messages` — paginação Helena API
2. Ordena por `createdAt`
3. Detecta `last_bot_idx`: índice da última mensagem com `origin == "BOT"` (chatbot pré-atendimento)
4. Loop de mensagens: TEXT → linha timeline; AUDIO → Whisper; IMAGE → referência
   - Acumula `chronological_content` (todas as mensagens)
   - Acumula `ai_content` (apenas mensagens após `last_bot_idx`)
5. Salva `raw_content:{id}` (completo) e `ai_content:{id}` (pós-bot) no Redis (TTL 7 dias)
6. Se `do_summary=True`: chama `generate_summary(ai_content or chronological_content)`
7. Marca `SessionRecord.status = COMPLETED`
8. Se `do_upload_images=True`: faz upload e **agenda `sync_session_images` em `AUTO_SYNC_DELAY_SECONDS` segundos**, criando `ScheduledSync`

### Separação `raw_content` vs `ai_content`

| Chave Redis | Conteúdo | Usado por |
|---|---|---|
| `raw_content:{session_id}` | Timeline completa (inclui BOT) | Export `.txt`, relatório HTML, fallback da IA |
| `ai_content:{session_id}` | Apenas mensagens após o último BOT | `generate_summary()` em ambas as tasks |

### `summarize_session(session_id)`
Lê `raw_content` do Redis → `generate_summary()` → salva/atualiza `Summary` → status `COMPLETED`.

### `sync_session_images(session_id, ficha)`
Re-busca mensagens → `_upload_images_from_messages` → status `COMPLETED` + marca `ScheduledSync` PENDING como `COMPLETED`.

### Logs em tempo real
`_log(session_id, msg)` faz `rpush` em `pipeline_logs:{session_id}` (TTL 24h). Lido pelo endpoint `/status`.

### Filtro de intervalo de imagens
`GDRIVE_IMAGE_INTERVAL_MINUTES` + `GDRIVE_IMAGE_MAX_PER_INTERVAL` — janela deslizante com `deque(maxlen=max_per_interval)` em `_upload_images_from_messages`.

---

## Agentes de IA (`agents/`)

### `generate_summary(content: str) → str`
Chama `ReportAgent` (Agno) com instruções extensas para gerar relatório técnico formal. Retorna texto simulado se `is_ai_configured()` for falso.

### `transcribe_audio(file_path: str) → str`
Usa OpenAI Whisper (`whisper-1`). Retorna texto stub se `OPENAI_API_KEY` não configurada.

### `llm_factory.get_model()`
Lazy imports por provider:
- `AI_PROVIDER=openai` → `agno.models.openai.OpenAIChat`
- `AI_PROVIDER=google` → `agno.models.google.Gemini`
- `AI_PROVIDER=anthropic` → `agno.models.anthropic.Anthropic`

---

## Google Drive (`services/gdrive.py`)

Ordem de autenticação:
1. OAuth user: `GOOGLE_DRIVE_CLIENT_ID` + `GOOGLE_DRIVE_CLIENT_SECRET` + `GOOGLE_DRIVE_REFRESH_TOKEN`
2. Service Account: `GOOGLE_SERVICE_ACCOUNT_FILE`
3. Mock (sem credenciais): retorna IDs falsos, pipeline não quebra

Retry automático em 429/500/503: backoff exponencial `2^attempt + jitter`, até 5 tentativas.

Pasta raiz no Drive: `GOOGLE_DRIVE_ROOT_FOLDER_ID` (padrão `root`). Subpasta criada com o número da ficha.

---

## Configuração (`core/config.py`)

| Variável | Padrão | Descrição |
|---|---|---|
| `APP_PORT` | `3000` | Porta FastAPI |
| `JWT_SECRET` | `super-secret-key` | Assinar JWTs |
| `DATABASE_URL` | `sqlite:///./dev.db` | Banco de dados |
| `REDIS_URL` | `redis://redis:6379/0` | Broker Celery + logs |
| `HELENA_API_URL` | — | Endpoint mensagens Helena |
| `HELENA_API_KEY` | — | Bearer token Helena |
| `CENTER_API_URL` | — | Endpoint Center API |
| `CENTER_API_KEY` | — | Bearer token Center (mock se vazio) |
| `AI_PROVIDER` | `openai` | `openai / google / anthropic` |
| `AI_CHAT_MODEL` | `gpt-4o` | Modelo de chat |
| `AI_TRANSCRIPTION_MODEL` | `whisper-1` | Modelo STT |
| `OPENAI_API_KEY` | — | Chave OpenAI |
| `GOOGLE_API_KEY` | — | Chave Google Gemini |
| `ANTHROPIC_API_KEY` | — | Chave Anthropic |
| `GOOGLE_DRIVE_CLIENT_ID` | — | OAuth Drive |
| `GOOGLE_DRIVE_CLIENT_SECRET` | — | OAuth Drive |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | — | OAuth Drive |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | — | Service Account JSON path |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | `root` | Pasta raiz no Drive |
| `GDRIVE_IMAGE_INTERVAL_MINUTES` | `5` | Janela de intervalo por imagem |
| `GDRIVE_IMAGE_MAX_PER_INTERVAL` | `1` | Máx. imagens por janela |
| `AUTO_SYNC_DELAY_SECONDS` | `10800` | Delay da re-checagem automática (3h). Reduzir para `10` em testes |

---

## Segurança e Auditoria

- **JWT HS256** sem refresh token. Expiração: 1 dia (padrão).
- **bcrypt** para hash de senha.
- **`AuditLogMiddleware`**: loga silenciosamente todas as requests auditáveis; não aborta em token inválido (enforcement é por rota).
- **`CurrentUserDep`**: lê Bearer token do header `Authorization`.
- **`_get_user_from_token_param`**: variante que lê JWT do query param `?token=` (usada exclusivamente em `/report-html`).

---

## Comandos úteis

```bash
# Subir tudo
docker compose up -d --build

# Logs do worker em tempo real
docker compose logs -f celery_worker

# Criar usuário
docker compose exec backend python -m app.scripts.create_user

# Testar Google Drive
docker compose exec backend python -m app.scripts.debug_gdrive

# Testar Helena API
docker compose exec backend python -m app.scripts.debug_velox

# Testar agentes de IA
docker compose exec backend python -m app.scripts.debug_agents

# OAuth Drive — obter refresh token
docker compose exec backend python -m app.scripts.oauth_setup
```

---

## Convenções

- `markdown=False` nos agentes Agno — obrigatório para texto puro.
- Imports lazy em `llm_factory.py` — só o provider ativo é carregado.
- `asyncio.run(...)` nas tasks Celery — ponte entre Celery síncrono e pipeline async.
- `raw_content` no Redis (TTL 7d) — fonte primária para geração de resumo.
- Mocks ativos sem credenciais: Drive, Center, Transcriber, AI — pipeline nunca quebra por falta de chave.
- Todos os textos/logs em **pt-BR**.
