# Velox — Workflow de Relatórios de Atendimento

Pipeline fullstack para geração automatizada de relatórios técnicos de atendimentos de socorro em pista.

## O que faz

1. Operador informa a URL de uma sessão da Helena CRM + número da ficha
2. O sistema busca todas as mensagens da sessão (texto, áudio, imagem)
3. Transcreve áudios via OpenAI Whisper
4. Envia imagens ao Google Drive (com filtro de intervalo para evitar duplicatas)
5. Gera um relatório técnico formal via agente de IA (Agno)
6. Operador revisa o relatório no Quadro de Revisão

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Vite + TypeScript |
| Backend | FastAPI (Python) |
| Worker | Celery |
| Broker / Cache | Redis |
| Banco de dados | SQLite (via SQLModel) |
| IA — Relatório | Agno (OpenAI / Gemini / Anthropic) |
| IA — Transcrição | OpenAI Whisper |
| Armazenamento | Google Drive (Service Account ou OAuth) |

---

## Subir o projeto

```bash
docker compose up -d --build
```

| Serviço | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:3000 |
| Swagger | http://localhost:3000/docs |

### Criar usuário

```bash
docker compose exec backend python -m app.scripts.create_user
```

---

## Configuração (`.env`)

Copie `.env.example` para `.env` e preencha:

```env
# Aplicação
JWT_SECRET=troque_por_um_segredo_forte

# Helena CRM (fonte das mensagens)
HELENA_API_URL=https://api.helena.run/chat/v1/message
HELENA_API_KEY=sua_chave_aqui

# Center API (destino do relatório)
CENTER_API_URL=https://api.center.example/v1/mgm
CENTER_API_KEY=sua_chave_aqui

# Google Drive — Service Account (recomendado para Shared Drive)
GOOGLE_SERVICE_ACCOUNT_FILE=/app/app/service-account.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=id_da_pasta_raiz

# Google Drive — OAuth (alternativa, funciona com conta pessoal)
# GOOGLE_DRIVE_CLIENT_ID=
# GOOGLE_DRIVE_CLIENT_SECRET=
# GOOGLE_DRIVE_REFRESH_TOKEN=

# Filtro de imagens: até X fotos a cada N minutos (evita duplicatas em rajada)
GDRIVE_IMAGE_INTERVAL_MINUTES=5
GDRIVE_IMAGE_MAX_PER_INTERVAL=1

# IA
AI_PROVIDER=openai          # openai | google | anthropic
AI_CHAT_MODEL=gpt-4o
AI_TRANSCRIPTION_MODEL=whisper-1

OPENAI_API_KEY=
GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
```

> O sistema funciona sem nenhuma chave configurada — Google Drive, transcrição, resumo e Center API operam em modo mock (sem gravar nada de verdade).

---

## Fluxo de status

```
PENDING → PROCESSING → COMPLETED
                    ↘ ERROR
                    ↘ CANCELLED

COMPLETED → SUMMARIZING → COMPLETED   ("Resumir Relatório")
COMPLETED → SYNCING     → COMPLETED   ("Enviar Novas Imagens")
```

---

## Endpoints principais

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/auth/login` | Login, retorna JWT |
| POST | `/sessions/start` | Inicia processamento de uma sessão |
| GET | `/sessions/{id}/status` | Status + logs em tempo real |
| POST | `/sessions/{id}/cancel` | Cancela processamento em andamento |
| POST | `/sessions/{id}/summarize` | Gera relatório com IA (manual) |
| DELETE | `/sessions/{id}/summary` | Apaga o resumo gerado |
| POST | `/sessions/{id}/sync-images` | Envia imagens novas ao Drive |
| GET | `/sessions/{id}/export` | Exporta relatório completo (.txt) |
| GET | `/sessions/{id}/debug-messages` | Exporta mensagens brutas em JSON (debug) |
| POST | `/center/mgm` | Envia relatório para Center API |

---

## Agente de IA

O relatório é gerado por um único **ReportAgent** via Agno (`generate_summary`).

O agente recebe a timeline formatada com identificação de remetente e produz diretamente o relatório no formato final:

```
DD/MM/YYYY HH:MM | SEÇÃO: DESCRIÇÃO EM MAIÚSCULO
```

### Formato da timeline enviada ao agente

```
[15/04/2026 20:55:51] [operador] texto da mensagem
[15/04/2026 21:00:09] [prestador] texto da mensagem
[15/04/2026 21:34:58] [prestador] ÁUDIO (Transcrito): transcrição do áudio
[15/04/2026 21:35:10] IMAGEM: foto_local.jpg
```

- `[operador]` = `direction: TO_HUB`
- `[prestador]` = `direction: FROM_HUB`
- Timestamp com segundos (`HH:MM:SS`), fuso Cuiabá
- Fallback: `createdAt || timestamp`

---

## Google Drive — filtro de imagens

O upload de imagens usa uma janela deslizante para evitar envio de fotos duplicadas enviadas em rajada pelo operador de campo.

| Variável | Padrão | Descrição |
|---|---|---|
| `GDRIVE_IMAGE_INTERVAL_MINUTES` | `5` | Duração da janela de tempo em minutos |
| `GDRIVE_IMAGE_MAX_PER_INTERVAL` | `1` | Máximo de imagens permitidas por janela |

Exemplos:
- `MAX=1, INTERVAL=5` → 1 foto a cada 5 min
- `MAX=2, INTERVAL=5` → até 2 fotos a cada 5 min
- `MAX=3, INTERVAL=10` → até 3 fotos a cada 10 min

Em caso de rate limit da API do Drive (erro 429) ou erro temporário (500/503), o sistema retenta automaticamente com backoff exponencial (até 5 tentativas, espera de 1s → 2s → 4s → 8s → 16s + jitter).

---

## Opções do pipeline

Ao iniciar uma sessão, o operador pode escolher:

| Opção | Padrão | Descrição |
|---|---|---|
| Transcrever áudios | ativo | Usa Whisper para transcrever áudios da sessão |
| Enviar imagens ao Drive | ativo | Upload com filtro de intervalo configurável |
| Gerar resumo com IA | inativo | Chama o agente automaticamente ao fim do pipeline |

O relatório também pode ser gerado manualmente após o processamento via botão **Resumir Relatório**, e apagado via **Limpar Resumo** para re-geração.

---

## Debug

### Google Drive

```bash
docker compose exec backend python -m app.scripts.debug_gdrive
```

### Mensagens da sessão (JSON)

Após o pipeline concluir, o botão **Debug JSON** no frontend baixa um arquivo com todas as mensagens texto da sessão no mesmo formato que o agente recebe — útil para comparar com outras fontes.

Ou via API diretamente:

```
GET http://localhost:3000/sessions/{SESSION_ID}/debug-messages
Authorization: Bearer {token}
```
