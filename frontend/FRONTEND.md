# FRONTEND — Referência Técnica

SPA React + TypeScript + Vite. Design dark com glassmorphism.

---

## Estrutura de Arquivos

```
frontend/src/
├── pages/
│   ├── Login.tsx          # Autenticação — armazena token no localStorage
│   ├── Dashboard.tsx      # Página principal de processamento de ocorrências
│   ├── Audit.tsx          # Listagem de logs de auditoria com busca e expansão
│   ├── Audit.css
│   ├── PendingTasks.tsx   # Tarefas de sincronização agendadas (countdown em tempo real)
│   └── PendingTasks.css
├── components/
│   ├── Layout.tsx         # Wrapper com sidebar, navegação e badge de tarefas
│   └── Layout.css
├── App.tsx                # React Router — define as rotas
├── App.css
├── index.css              # Variáveis CSS globais e reset
└── main.tsx               # Ponto de entrada
```

---

## Roteamento (`App.tsx`)

| Rota | Componente | Proteção |
|---|---|---|
| `/login` | `Login` | Pública |
| `/dashboard` | `Dashboard` | `Layout` (JWT obrigatório) |
| `/auditoria` | `Audit` | `Layout` |
| `/tarefas-pendentes` | `PendingTasks` | `Layout` |
| `*` | Redirect `/login` | — |

Rotas protegidas são filhas de `<Route element={<Layout />}>`. O `Layout` renderiza o `<Outlet />` no conteúdo principal.

---

## Componentes

### `Layout.tsx`

Sidebar persistente com:
- Navegação: Dashboard, Auditoria, Tarefas Pendentes
- **Badge de contagem** no item "Tarefas Pendentes" — faz polling `GET /sessions/scheduled-syncs` a cada 30s e exibe a quantidade de tarefas `PENDING` em vermelho
- Botão Sair (limpa `localStorage`)
- Toggle mobile (hamburger) com overlay

**Classes CSS relevantes:**
- `.nav-item` / `.nav-item.active` — item de menu
- `.nav-badge` — badge vermelho no item de menu
- `.sidebar`, `.sidebar.open` — sidebar responsiva

---

## Páginas

### `Dashboard.tsx`

Página principal. Estado gerenciado localmente com `useState`.

**Fluxo principal:**
1. Operador preenche URL + Ficha + opções
2. `POST /sessions/start` → recebe `sessionId`
3. Polling `GET /sessions/{id}/status` a cada 2s (via `setInterval`)
4. Logs exibidos em painel com scroll automático
5. Ao completar: ações disponíveis

**Estado principal:**

| Estado | Tipo | Descrição |
|---|---|---|
| `url` | string | URL da sessão Helena |
| `ficha` | string | Número da ficha |
| `sessionId` | string | ID retornado pelo backend |
| `status` | string | Status atual da sessão |
| `summary` | string | Texto do resumo (editável) |
| `hasRawContent` | boolean | Se existe timeline no Redis |
| `logs` | string[] | Logs do pipeline em tempo real |
| `options` | object | `do_transcribe`, `do_upload_images`, `do_summary` |

**Handlers disponíveis:**

| Handler | Endpoint | Descrição |
|---|---|---|
| `handleStart` | POST `/sessions/start` | Inicia pipeline |
| `handleStop` | POST `/sessions/{id}/cancel` | Cancela |
| `handleSummarize` | POST `/sessions/{id}/summarize` | Gera resumo com IA |
| `handleClearSummary` | DELETE `/sessions/{id}/summary` | Apaga resumo |
| `handleSyncImages` | POST `/sessions/{id}/sync-images` | Sincroniza imagens |
| `handleSaveDraft` | PUT `/sessions/{id}/summary` | Salva rascunho editado |
| `handleViewPdf` | `window.open(report-html?token=...)` | Abre relatório HTML em nova aba |
| `handleExport` | GET `/sessions/{id}/export` | Download `.txt` |
| `handleInsertMGM` | POST `/center/mgm` | Envia para Center API |
| `handleDebugMessages` | GET `/sessions/{id}/debug-messages` | Download JSON de debug |

**Quadro de Revisão** (aparece quando `status === 'COMPLETED' && summary`):
- `<textarea>` editável com o resumo
- Botões: **Salvar Rascunho**, **Visualizar PDF**, **Inserir MGM (Center)**

**Indicador de Progresso** (sidebar direita): passos `PENDING → PROCESSING → SYNCING → SUMMARIZING → COMPLETED`

---

### `PendingTasks.tsx`

Lista as sincronizações automáticas agendadas (`PENDING`).

**Interface:**
```typescript
interface ScheduledSync {
  id: string;
  sessionId: string;
  ficha: string;
  contactName: string | null;
  runAt: string;      // ISO 8601 UTC
  status: string;
  createdAt: string;
}
```

**Componente `Countdown`:** atualiza a cada 1s com `setInterval`. Exibe `Xh YYm ZZs`. Mostra "Pronto para rodar" quando `diff <= 0`.

**Ações:**
- Botão **Cancelar**: `DELETE /sessions/scheduled-syncs/{id}` → remove da lista com estado `removing`
- Botão **Atualizar**: recarrega a lista

**Colunas da tabela:** Ficha, ID do Chat (truncado), Contato, Agendado Para, Tempo Restante, Status, Ação.

---

### `Audit.tsx`

Tabela de logs de auditoria com busca por ficha/sessão/ação e expansão de detalhes por linha.

---

## Comunicação com o Backend

Todas as páginas criam uma instância do axios com o token do `localStorage`:

```typescript
const api = axios.create({
  baseURL: 'http://localhost:3000',
  headers: { Authorization: `Bearer ${token}` },
});
```

A URL base está hardcoded como `http://localhost:3000`. Não há proxy Vite configurado.

**Exceção — `/report-html`:** o JWT é passado como query param pois a aba é aberta diretamente pelo browser:
```typescript
window.open(`http://localhost:3000/sessions/${sessionId}/report-html?token=${token}`, '_blank');
```

---

## Variáveis CSS Globais (`index.css`)

| Variável | Uso |
|---|---|
| `--primary` | Cor principal (laranja Velox `#ff9800`) |
| `--danger` | Vermelho para erros/cancelamentos |
| `--text-muted` | Texto secundário |
| `--border` | Bordas dos painéis |

Classes utilitárias reutilizadas:
- `.glass-panel` — painel com glassmorphism
- `.card` — card com padding/border-radius
- `.btn`, `.btn-primary`, `.btn-accent`, `.btn-danger` — botões padronizados
- `.input-control` — campos de formulário
- `.log-panel` — painel de terminal com scroll
- `.log-line`, `.log-line.error`, `.log-line.ok` — linhas de log coloridas
- `.spin` — animação de rotação (ícone de loading)

---

## Convenções

- Todo texto de UI em **pt-BR**
- `localStorage`: `token` (JWT), `user` (objeto JSON do usuário)
- Polling com `setInterval` armazenado em `intervalRef` (limpeza no unmount via `useEffect` cleanup)
- `alert()` para erros e confirmações simples (sem biblioteca de toast)
- Nenhuma biblioteca de estado global (sem Redux/Zustand) — tudo em `useState` local
- Ícones: `lucide-react`
- Sem proxy Vite — CORS aberto no backend

---

## Comandos

```bash
# Desenvolvimento (via Docker)
docker compose up -d frontend

# Lint
cd frontend && npm run lint

# Build de produção
cd frontend && npm run build
```

Frontend exposto em `http://localhost:5173`.
