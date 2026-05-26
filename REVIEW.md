# Revisão de Código — Velox Pipeline
**Data:** 26/05/2026

---

## 1. Bugs Confirmados

### BUG 1 — Interval Leak no Dashboard
**Arquivo:** `frontend/src/pages/Dashboard.tsx`
**Problema:** Se o operador abre duas fichas rapidamente via histórico, o `useEffect` que carrega a sessão existente chama `startPolling()` antes do intervalo anterior ser limpo. Múltiplos `setInterval` ficam rodando em paralelo.
**Impacto:** Requisições duplicadas ao backend, UI pode piscar ou exibir dados inconsistentes, consumo crescente de memória na aba do browser.

---

### BUG 2 — `img_dt` Extraído mas Nunca Usado
**Arquivo:** `backend/app/services/tasks.py`, função `_upload_images_from_messages` (~linha 93)
**Problema:** A variável `img_dt` é calculada a partir do `createdAt` da imagem, mas nunca é usada no código. A docstring da função menciona "filtro de intervalo" (`GDRIVE_IMAGE_INTERVAL_MINUTES` / `GDRIVE_IMAGE_MAX_PER_INTERVAL`), mas o filtro não está implementado — só verifica se a imagem já foi enviada antes.
**Impacto:** Feature documentada e configurável via `.env` que não funciona. Código morto que gera confusão.

---

### BUG 3 — Sync Falho Marcado como COMPLETED
**Arquivo:** `backend/app/services/tasks.py`, função `_async_sync_images`
**Problema:** O bloco `finally` chama `_set_status(session_id, "COMPLETED")` incondicionalmente. Se uma exceção for lançada durante a sincronização, o status da sessão é marcado como COMPLETED mesmo com a operação tendo falhado.
**Impacto:** Operador vê "Concluído" e assume que imagens foram sincronizadas quando nada foi feito.

---

### BUG 4 — Audit Middleware Não Loga Payload
**Arquivo:** `backend/app/core/audit.py`
**Problema:** O middleware nunca extrai o body da requisição. Os campos `payload`, `session_id` e `ficha` na tabela `audit_log` sempre ficam `NULL` para requisições vindas do middleware. Só o endpoint explícito de auditoria teria esses dados se populados manualmente.
**Impacto:** Auditoria praticamente inútil para investigações — não é possível saber o que foi enviado em cada chamada.

---

### BUG 5 — `ScheduledSync.run_at` Exibido em UTC na UI
**Arquivo:** `frontend/src/pages/PendingTasks.tsx`
**Problema:** `ScheduledSync.run_at` é salvo em UTC no banco (`tasks.py`), mas a função `formatDate()` no frontend exibe sem converter para o fuso local. A contagem regressiva (`Countdown`) usa `Date.now()` e calcula corretamente, mas o campo "Agendado Para" mostra horário errado (3–4h a menos que o horário real local).
**Impacto:** Operador vê horário de sincronização errado, gera confusão operacional.

---

### BUG 6 — `raw_content` Antigo Pode Vazar Entre Execuções
**Arquivo:** `backend/app/services/tasks.py`, início do pipeline
**Problema:** Ao reiniciar o processamento de uma sessão, o código deleta `pipeline_logs` e `ai_content` do Redis, mas **não deleta `raw_content`**. Se o novo pipeline falhar antes de salvar o `raw_content`, o Redis ainda terá o conteúdo da execução anterior (por até 7 dias). O `summarize_session` pode então gerar um resumo com conteúdo desatualizado.
**Impacto:** Resumos gerados com dados de uma execução anterior, sem o operador perceber.

---

## 2. Problemas de UX para o Operador

### UX 1 — Nenhum Feedback sobre Imagens com Falha
O campo `MediaFile.status` pode ser `"FAILED"` no banco quando um upload ao Drive falha, mas essa informação nunca chega à interface. O operador não tem como saber quantas imagens foram enviadas, quantas falharam ou quais precisam de retry. A única forma de descobrir é lendo os logs de terminal na tela.

---

### UX 2 — Botão "Resumir Relatório" Falha Silenciosamente
Se o `raw_content` expirou no Redis (após 7 dias) e o operador clica em "Resumir Relatório", o backend tenta buscar do banco como fallback. Se o banco também não tiver (sessões antigas pré-migração), a task falha e o status volta para COMPLETED sem nenhuma mensagem de erro clara na UI.

---

### UX 3 — Inserir MGM Não Valida a Resposta da API
`handleInsertMGM()` exibe "MGM inserido com sucesso!" para qualquer resposta HTTP 2xx da Center API. Se a API retornar `{"success": false, "error": "ficha não encontrada"}` com status 200, o operador recebe feedback positivo falso. O mock de fallback (quando `CENTER_API_KEY` não está configurado) também retorna sucesso simulado sem nenhuma indicação visual.

---

### UX 4 — Sem Rastreabilidade de Edições no Resumo
Vários operadores podem editar o mesmo resumo. Não há registro de quem fez a última edição, quando foi feita, nem histórico de versões anteriores. Se um operador sobrescrever o trabalho de outro, não há como recuperar.

---

### UX 5 — Status "ERROR" ou "CANCELLED" Sem Detalhes
Quando uma sessão termina com status `ERROR`, o operador vê apenas o badge vermelho na página Fichas. Não há botão para ver o motivo do erro, nem possibilidade de reprocessar diretamente da tela de histórico — é preciso criar uma nova sessão do zero no Dashboard.

---

## 3. Código que Não Faz Sentido / Inconsistências

### C1 — `_is_cancelled()` e `_set_status()` Abrem Conexão Nova a Cada Chamada
**Arquivo:** `backend/app/services/tasks.py`
Essas duas funções utilitárias abrem um `with Session(engine)` independente a cada invocação. `_is_cancelled()` é chamada a cada 20 mensagens dentro do loop principal. Em sessões com 500+ mensagens, isso gera dezenas de conexões desnecessárias ao banco durante o processamento.

---

### C2 — `_log()` Silencia Exceções de Redis Completamente
**Arquivo:** `backend/app/services/tasks.py`
```python
except Exception:
    pass
```
Se o Redis cair durante o processamento, todos os logs de pipeline são descartados silenciosamente. O operador vê a tela de logs em branco sem nenhuma indicação do que aconteceu.

---

### C3 — `handleViewPdf()` com URL Hardcoded
**Arquivo:** `frontend/src/pages/Dashboard.tsx`
```javascript
window.open(`http://localhost:3000/sessions/${sessionId}/report-html`, '_blank');
```
A URL base está hardcoded em `localhost:3000`. Se o sistema for acessado de outra máquina na rede ou em produção, o PDF não abre. Todos os outros endpoints já usam `api.create({ baseURL: '...' })`, mas esse ficou esquecido.

---

### C4 — Audit Page Usa `localStorage.getItem('token')` (Token Não Existe)
**Arquivo:** `frontend/src/pages/Audit.tsx`
```javascript
const token = localStorage.getItem('token');
const api = axios.create({
  headers: { Authorization: `Bearer ${token}` },
});
```
O sistema usa cookie `httpOnly` para autenticação desde a migração de segurança. O `localStorage.getItem('token')` sempre retorna `null`. A página de auditoria funcionava apenas por acidente (o cookie era enviado pelo browser via `withCredentials` no axios global, mas o header `Authorization: Bearer null` era ignorado).

---

### C5 — Filtro de Status no Histórico Hardcoded no Frontend
**Arquivo:** `frontend/src/pages/History.tsx`
Os valores do `<select>` de filtro de status estão fixos no código. Se um novo status for adicionado no backend, o dropdown não atualiza automaticamente. Melhor buscar os valores distintos da API ou sincronizar com uma constante compartilhada.

---

### C6 — `contact_name` em `ScheduledSync` e `SessionRecord` Duplicado
**Arquivo:** `backend/app/models/domain.py`
O campo `contact_name` existe tanto em `ScheduledSync` quanto em `SessionRecord`. A lógica de extração é idêntica em ambos os lugares. Um refactoring simples centralizaria isso.

---

## 4. Melhorias de Alto Valor para o Operador

### M1 — Painel de Status das Imagens
Mostrar na tela de resultado: quantas imagens foram encontradas, quantas enviadas ao Drive, quantas falharam, com botão de retry individual por imagem. Usar os dados já existentes na tabela `media_file`.

---

### M2 — Reprocessar Sessão com Erro Direto do Histórico
Na página Fichas, sessões com status `ERROR` ou `CANCELLED` deveriam ter um botão "Reprocessar" que leva ao Dashboard com a URL e ficha já preenchidas (usar `session_url` já salvo no banco).

---

### M3 — Rastreabilidade de Edições no Resumo
Adicionar campos `edited_by` (FK para `user`) e `edited_at` (datetime) na tabela `summary`. Exibir "Última edição por [Nome] às [hora]" no Quadro de Revisão. Opcional: histórico de versões com diff.

---

### M4 — Validação Antes de Enviar ao Center
Antes de habilitar o botão "Inserir MGM", validar no frontend:
- Relatório tem pelo menos N linhas
- Há timestamps no conteúdo
- Resposta da Center API é inspecionada antes de exibir "sucesso"

---

### M5 — Notificação Quando Sync Automático Concluir
Quando o `sync_session_images` agendado (3h depois) terminar, o operador não recebe nenhum aviso. Uma notificação visual na interface (badge ou toast) avisando "Sincronização da ficha 12345 concluída" melhoraria muito o acompanhamento.

---

### M6 — Busca por Nome do Contato na Página Fichas
Atualmente a busca é apenas por número de ficha. Permitir buscar pelo `contact_name` (nome do prestador) seria mais intuitivo em operações do dia a dia.

---

## 5. Melhorias Técnicas

### T1 — Retry com Backoff em Downloads
`_download_file()` não tem retry. Se a Helena API retorna 429 (rate limit) ou 503, a imagem é perdida definitivamente. O `upload_file()` do Google Drive já tem retry com backoff exponencial — o mesmo padrão deveria ser aplicado nos downloads.

---

### T2 — Limpar `raw_content` do Redis ao Reiniciar Pipeline
No início de `_async_process_session`, adicionar:
```python
_redis.delete(f"raw_content:{session_id}")
```
Junto com os deletes de `pipeline_logs` e `ai_content` que já existem. Evita que conteúdo de execução anterior vaze para resumos da nova execução.

---

### T3 — Audit Middleware Capturar Body da Requisição
Para que `session_id`, `ficha` e `payload` sejam populados na tabela `audit_log`, o middleware precisa ler o body da requisição. Requer cachear o body (`request._body = body`) para que o route handler também possa lê-lo depois.

---

### T4 — Connection Pooling Explícito no SQLAlchemy
Configurar `pool_pre_ping=True`, `pool_size=10` e `max_overflow=20` no `create_engine()`. Combinado com o refactoring de C1 (passar sessão como parâmetro), reduz drasticamente a quantidade de conexões abertas durante o processamento.

---

### T5 — `handleViewPdf()` Usar URL Relativa
Substituir `http://localhost:3000` por `window.location.origin.replace('5173', '3000')` ou, melhor, centralizar a `API_BASE_URL` em uma constante/variável de ambiente do Vite (`VITE_API_URL`).

---

### T6 — Implementar o Filtro de Intervalo de Imagens
A variável `img_dt` já é extraída mas nunca usada. O filtro de janela deslizante (`GDRIVE_IMAGE_INTERVAL_MINUTES` / `GDRIVE_IMAGE_MAX_PER_INTERVAL`) está documentado no CLAUDE.md e configurável via `.env`, mas não está implementado no loop de upload. Completar a implementação com `deque(maxlen=max_per_interval)`.

---

### T7 — Página de Auditoria com Filtros e Paginação
O endpoint `/audit` carrega até 1000 registros de uma vez. Com uso contínuo, a tabela vai crescer e a página vai travar. Adicionar paginação server-side e filtros por data, operador e status.

---

## Resumo de Prioridades

### Atacar imediatamente (bugs que afetam dados)
1. **BUG 6** — Limpar `raw_content` antigo ao reiniciar pipeline (5 min)
2. **BUG 3** — Não marcar sync como COMPLETED em caso de exceção (10 min)
3. **BUG 1** — Corrigir interval leak no Dashboard (15 min)
4. **C4** — Corrigir `localStorage.getItem('token')` na Audit page (5 min)
5. **C3** — Corrigir URL hardcoded no `handleViewPdf()` (5 min)

### Maior valor para o operador (próximo sprint)
6. **M1** — Painel de status das imagens com retry
7. **M2** — Botão "Reprocessar" no histórico para sessões com erro
8. **M3** — Rastreabilidade de edições no resumo
9. **UX 3** — Validar resposta do MGM antes de exibir sucesso
10. **M6** — Busca por nome do contato na página Fichas

### Melhorias técnicas (backlog)
11. **T1** — Retry com backoff em downloads
12. **T3** — Audit middleware capturar body
13. **T4** — Connection pooling + refactoring de sessões de banco
14. **T6** — Implementar filtro de intervalo de imagens
15. **T7** — Paginação server-side na auditoria
