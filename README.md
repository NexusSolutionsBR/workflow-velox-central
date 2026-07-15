# Velox

Pipeline fullstack para processamento de atendimentos de socorro em pista. O operador informa a URL de uma sessão da Helena CRM e o número da ficha; o sistema busca as mensagens, transcreve áudios, envia imagens ao Google Drive, gera um relatório técnico via IA e insere as ocorrências no Center.

O projeto é em **pt-BR** — prompts, logs, mensagens de erro e textos da UI estão em português.

---

## Funcionalidades

- **Pipeline de atendimento** — busca de mensagens, transcrição de áudios (Whisper), upload de imagens ao Drive e geração de relatório técnico via IA.
- **Logs em tempo real** — o operador acompanha o pipeline pelo painel de terminal (polling a cada 2s).
- **Quadro de Revisão** — editor do relatório com salvar rascunho, visualizar PDF e inserir a ocorrência no Center (MGM).
- **Re-checagem automática de imagens** — após concluir, agenda um novo sync para reenviar imagens que chegarem depois (padrão: 3h).
- **Tarefas Pendentes** (`/tarefas-pendentes`) — lista os syncs agendados com contagem regressiva, permitindo cancelar ou executar agora.
- **Histórico de Fichas** (`/fichas`) — busca paginada por todas as sessões já processadas.
- **Auditoria** (`/auditoria`, ADMIN) — registro de todas as requests às rotas sensíveis.

---

## Requisitos

- Docker e Docker Compose
- Nginx (para produção)
- Acesso às APIs: Helena CRM, OpenAI, Google Drive, Center

---

## Configuração

Copie o arquivo de exemplo e preencha as variáveis:

```bash
cp .env.example .env
```

### Variáveis obrigatórias

| Variável | Descrição |
|---|---|
| `JWT_SECRET` | Chave secreta para assinar tokens JWT — use uma string longa e aleatória |
| `POSTGRES_PASSWORD` | Senha do banco de dados |
| `HELENA_API_KEY` | Chave da API Helena CRM |
| `OPENAI_API_KEY` | Chave da API OpenAI (transcrição + IA) |
| `VITE_API_URL` | URL base da API acessível pelo browser |
| `ALLOWED_ORIGINS` | Origem permitida pelo CORS (mesma URL do frontend) |

### Variáveis de portas

| Variável | Padrão | Descrição |
|---|---|---|
| `PORT_BACKEND` | `3000` | Porta exposta do FastAPI |
| `PORT_FRONTEND` | `5173` | Porta exposta do frontend |
| `PORT_POSTGRES` | `5432` | Porta exposta do PostgreSQL |
| `PORT_REDIS` | `6379` | Porta exposta do Redis |

### Variáveis opcionais

| Variável | Padrão | Descrição |
|---|---|---|
| `COOKIE_SECURE` | `false` | Flag `Secure` no cookie de auth — `true` em produção/HTTPS |
| `ENABLE_DOCS` | `false` | Expõe `/docs`, `/redoc` e `/openapi.json` — manter `false` em produção |
| `AI_PROVIDER` | `openai` | Provider de IA: `openai`, `google` ou `anthropic` |
| `AI_CHAT_MODEL` | `gpt-4o` | Modelo de chat usado na geração do relatório |
| `AI_TRANSCRIPTION_MODEL` | `whisper-1` | Modelo de transcrição (STT é sempre OpenAI Whisper) |
| `AUTO_SYNC_DELAY_SECONDS` | `10800` | Atraso da re-checagem automática de imagens (3h) |
| `GDRIVE_IMAGE_INTERVAL_MINUTES` | `5` | Duração da janela do filtro de imagens |
| `GDRIVE_IMAGE_MAX_PER_INTERVAL` | `1` | Máx. de imagens por janela |

### Google Drive

Dois métodos de autenticação (use um). A ordem de prioridade no código é: OAuth user → Service Account → mock.

**OAuth user (recomendado):** funciona com qualquer conta Google, inclusive pessoal.
1. Configure `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET` e `GOOGLE_DRIVE_REFRESH_TOKEN`
2. Gere o `refresh_token` rodando: `docker compose exec backend python -m app.scripts.oauth_setup`
3. Configure `GOOGLE_DRIVE_ROOT_FOLDER_ID` com o ID da pasta raiz

**Service Account (legado):** só funciona se a pasta raiz estiver num Drive Compartilhado (Google Workspace). Em conta pessoal o upload falha com `storageQuotaExceeded`.
1. Gere um arquivo JSON de conta de serviço no Google Cloud Console
2. Coloque o arquivo em `backend/service-account.json`
3. Configure `GOOGLE_SERVICE_ACCOUNT_FILE=/app/app/service-account.json`

Se nenhum estiver configurado, o sistema opera em modo mock (IDs falsos, nada é enviado).

A frequência de upload é controlada por uma janela deslizante: `GDRIVE_IMAGE_INTERVAL_MINUTES` (padrão: 5) e `GDRIVE_IMAGE_MAX_PER_INTERVAL` (padrão: 1).

### Center API

Cada operação usa um identificador diferente com a mesma URL base:

| Variável | Operação |
|---|---|
| `CENTER_IDENTIFICADOR_FICHA` | Consulta de ficha |
| `CENTER_IDENTIFICADOR_OCORRENCIAS` | Consulta de ocorrências |
| `CENTER_IDENTIFICADOR_INSERCAO` | Inserção de ocorrências |
| `CENTER_USUARIO_PARAMETRO` | ID do usuário no Center |

Se os identificadores não estiverem configurados, o sistema opera em modo mock.

---

## Desenvolvimento

```bash
# Subir todos os serviços
docker compose up -d --build

# Acompanhar logs do worker Celery
docker compose logs -f celery_worker

# Criar usuário operador
docker compose exec backend python -m app.scripts.create_user

# Debug do Google Drive
docker compose exec backend python -m app.scripts.debug_gdrive
```

Acesse:
- Frontend: http://localhost:5173
- API: http://localhost:3000
- Swagger: http://localhost:3000/docs — **só disponível com `ENABLE_DOCS=true`** (desligado por padrão)

---

## Produção

### 1. Configure o `.env`

```env
VITE_API_URL=https://workflow.nexussolutions.com.br/api
ALLOWED_ORIGINS=https://workflow.nexussolutions.com.br
JWT_SECRET=<string aleatória longa>
POSTGRES_PASSWORD=<senha forte>
```

> `VITE_API_URL` é embutida no bundle JavaScript em tempo de build — deve apontar para a URL pública da API antes de buildar.

### 2. Suba os containers

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 3. Configure o Nginx

O Nginx deve fazer proxy reverso para:

| Rota | Container |
|---|---|
| `/` (frontend) | `localhost:${PORT_FRONTEND}` (padrão: 5173) |
| `/auth`, `/sessions`, `/center`, `/audit` (API) | `localhost:${PORT_BACKEND}` (padrão: 3000) |

Exemplo de bloco de localização para a API:
```nginx
location ~* ^/(auth|sessions|center|audit) {
    proxy_pass http://localhost:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Comandos úteis em produção

```bash
# Verificar status dos containers
docker compose -f docker-compose.prod.yml ps

# Logs da API
docker compose -f docker-compose.prod.yml logs -f backend

# Logs do worker
docker compose -f docker-compose.prod.yml logs -f celery_worker

# Criar usuário
docker compose -f docker-compose.prod.yml exec backend python -m app.scripts.create_user

# Restartar apenas o backend após mudança de configuração
docker compose -f docker-compose.prod.yml up -d --build backend celery_worker
```

---

## Arquitetura

```
Helena CRM → mensagens → pipeline Celery
                ↓
        transcrição (Whisper)
        upload de imagens (Google Drive)
        relatório IA (Agno/OpenAI)
        inserção no Center
                ↓
        operador revisa no Quadro de Revisão
```

- **Backend**: FastAPI — valida inputs, persiste no banco, despacha tasks
- **Celery Worker**: executa o pipeline pesado (downloads, transcrição, IA)
- **Redis**: broker do Celery + armazenamento temporário de logs e conteúdo
- **PostgreSQL**: sessões, resumos, arquivos de mídia, auditoria
- **Frontend**: React + Vite — dashboard do operador

---

## Estrutura

```
.
├── backend/
│   ├── app/
│   │   ├── api/          # Endpoints FastAPI
│   │   ├── agents/       # Agentes de IA (Agno)
│   │   ├── core/         # Config, segurança, banco, Celery
│   │   ├── models/       # Modelos SQLModel
│   │   ├── scripts/      # Utilitários CLI
│   │   └── services/     # Pipeline, Drive, Center, tasks Celery
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   └── pages/
│   ├── Dockerfile           # Desenvolvimento
│   └── Dockerfile.prod      # Build estático para produção
├── docker-compose.yml       # Desenvolvimento
├── docker-compose.prod.yml  # Produção
└── .env
```
