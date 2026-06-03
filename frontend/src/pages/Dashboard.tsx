import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import {
  CheckCircle, Circle, Play, Send,
  Square, FileText, RefreshCw, Loader, Bug, Save, Printer, ArrowLeft, FolderOpen,
} from 'lucide-react';
import { ReportLineEditor } from '../components/ReportLineEditor';

const STEPS = [
  { id: 'PENDING', label: 'Aguardando Início' },
  { id: 'PROCESSING', label: 'Processando Mídias' },
  { id: 'SYNCING', label: 'Sincronizando Imagens' },
  { id: 'SUMMARIZING', label: 'Gerando Resumo com IA' },
  { id: 'INSERTING', label: 'Inserindo no Center' },
  { id: 'COMPLETED', label: 'Pronto para Revisão' },
];

const ACTIVE_STATUSES = ['PROCESSING', 'SUMMARIZING', 'SYNCING', 'INSERTING'];
const TERMINAL_STATUSES = ['COMPLETED', 'ERROR', 'CANCELLED'];

export const Dashboard = () => {
  const [url, setUrl] = useState('');
  const [ficha, setFicha] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [status, setStatus] = useState('PENDING');
  const [summary, setSummary] = useState('');
  const [hasRawContent, setHasRawContent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [options, setOptions] = useState({ do_transcribe: true, do_upload_images: true, do_summary: true, do_insert_center: false });
  const [centerInserted, setCenterInserted] = useState(false);
  const [centerDuplicate, setCenterDuplicate] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [driveFolderUrl, setDriveFolderUrl] = useState<string | null>(null);
  const [fromHistory, setFromHistory] = useState(false);

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const logEndRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Botão Debug JSON visível apenas para administradores
  const isAdmin = (() => {
    try {
      const raw = localStorage.getItem('user');
      return raw ? JSON.parse(raw).role === 'ADMIN' : false;
    } catch {
      return false;
    }
  })();

  useEffect(() => {
    if (!localStorage.getItem('user')) navigate('/login');
  }, [navigate]);

  useEffect(() => {
    const sid = searchParams.get('sessionId');
    if (!sid) return;
    let cancelled = false;
    setFromHistory(true);
    api.get(`/sessions/${sid}/status`).then(res => {
      if (cancelled) return;
      const d = res.data;
      setSessionId(d.sessionId);
      setFicha(d.ficha || '');
      setStatus(d.status);
      setHasRawContent(d.hasRawContent ?? false);
      setCenterInserted(d.centerInserted ?? false);
      setCenterDuplicate(d.centerDuplicate ?? false);
      setErrorMessage(d.errorMessage ?? null);
      setDriveFolderUrl(d.driveFolderUrl ?? null);
      if (d.summary?.editedSummary) setSummary(d.summary.editedSummary);
      else if (d.summary?.originalSummary) setSummary(d.summary.originalSummary);
      if (ACTIVE_STATUSES.includes(d.status)) startPolling(d.sessionId);
    }).catch(() => {
      if (!cancelled) navigate('/fichas');
    });
    return () => { cancelled = true; };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);
  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current); }, []);

  const isActive = ACTIVE_STATUSES.includes(status);

  const startPolling = (sid: string) => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    let stableCount = 0;
    let lastLogCount = -1;
    intervalRef.current = setInterval(async () => {
      try {
        const res = await api.get(`/sessions/${sid}/status`);
        const data = res.data;
        const logs: string[] = data.logs ?? [];
        setLogs(logs);
        setStatus(data.status);
        setHasRawContent(data.hasRawContent ?? false);
        setCenterInserted(data.centerInserted ?? false);
        setCenterDuplicate(data.centerDuplicate ?? false);
        setErrorMessage(data.errorMessage ?? null);
        setDriveFolderUrl(data.driveFolderUrl ?? null);
        if (data.summary?.editedSummary) setSummary(data.summary.editedSummary);
        if (TERMINAL_STATUSES.includes(data.status)) {
          if (logs.length === lastLogCount) {
            stableCount++;
          } else {
            stableCount = 0;
          }
          lastLogCount = logs.length;
          // Para só quando o log ficar estável por 3 ciclos (6s) após status terminal
          if (stableCount >= 3) {
            clearInterval(intervalRef.current!);
            intervalRef.current = null;
          }
        }
      } catch {
        clearInterval(intervalRef.current!);
        intervalRef.current = null;
      }
    }, 2000);
  };

  const handleStart = async () => {
    if (!url || !ficha) return alert('Preencha URL e Ficha');
    setLoading(true);
    setLogs([]);
    setSummary('');
    setHasRawContent(false);
    try {
      const res = await api.post('/sessions/start', { url, ficha, ...options });
      const sid = res.data.sessionId;
      setSessionId(sid);
      setStatus('PROCESSING');
      startPolling(sid);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao iniciar');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      await api.post(`/sessions/${sessionId}/cancel`);
      setStatus('CANCELLED');
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao cancelar');
    }
  };

  const handleSummarize = async () => {
    try {
      await api.post(`/sessions/${sessionId}/summarize`);
      setStatus('SUMMARIZING');
      startPolling(sessionId);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao iniciar resumo');
    }
  };

  const handleClearSummary = async () => {
    try {
      await api.delete(`/sessions/${sessionId}/summary`);
      setSummary('');
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao apagar resumo');
    }
  };

  const handleSyncImages = async () => {
    try {
      await api.post(`/sessions/${sessionId}/sync-images`);
      setStatus('SYNCING');
      startPolling(sessionId);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao sincronizar imagens');
    }
  };

  const handleDebugMessages = async () => {
    try {
      const res = await api.get(`/sessions/${sessionId}/debug-messages`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `debug_${sessionId}.json`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao buscar mensagens de debug');
    }
  };

  const handleSaveDraft = async () => {
    try {
      await api.put(`/sessions/${sessionId}/summary`, { summaryText: summary });
      alert('Rascunho salvo com sucesso!');
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao salvar rascunho');
    }
  };

  const handleViewPdf = () => {
    window.open(`${api.defaults.baseURL}/sessions/${sessionId}/report-html`, '_blank');
  };

  const handleViewPdfPublico = () => {
    window.open(`${api.defaults.baseURL}/sessions/${sessionId}/report-html?public_only=true`, '_blank');
  };

  const handleInsertMGM = async () => {
    if (!confirm('⚠️ ATENÇÃO\n\nAPAGUE AS OCORRÊNCIAS DA FICHA ANTES DE INSERI-LAS AUTOMATICAMENTE.\n\nDeseja continuar?')) return;
    try {
      await api.post('/center/mgm', { sessionId, summaryText: summary });
      alert('MGM inserido com sucesso!');
    } catch {
      alert('Erro ao inserir MGM');
    }
  };

  const handleReset = () => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    setStatus('PENDING');
    setSessionId('');
    setLogs([]);
    setSummary('');
    setHasRawContent(false);
    setCenterInserted(false);
    setCenterDuplicate(false);
    setUrl('');
    setFicha('');
    setOptions({ do_transcribe: true, do_upload_images: true, do_summary: true, do_insert_center: false });
  };

  const toggleOption = (key: keyof typeof options) =>
    setOptions(prev => ({ ...prev, [key]: !prev[key] }));

  const logClass = (line: string) => {
    if (line.includes('ERRO') || line.includes('FALHA')) return 'log-line error';
    if (line.includes('OK') || line.includes('Concluído') || line.includes('Gerado')) return 'log-line ok';
    return 'log-line';
  };

  const stepIndex = STEPS.findIndex(s => s.id === status);

  return (
    <div className="app-container">
      <div className="content">
        <div className="dashboard-grid">

          {/* Coluna Principal */}
          <div>
            <div className="glass-panel card">
              {fromHistory && (
                <button
                  style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: 'var(--text-muted, #888)', cursor: 'pointer', fontSize: '0.85rem', marginBottom: '12px', padding: 0 }}
                  onClick={() => navigate('/fichas')}
                >
                  <ArrowLeft size={15} /> Voltar às Fichas
                </button>
              )}
              <h2 className="card-title">{fromHistory ? `Atendimento — Ficha ${ficha || sessionId}` : 'Nova Ocorrência'}</h2>

              {fromHistory && driveFolderUrl && !driveFolderUrl.includes('mock') && (
                <a
                  href={driveFolderUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--primary, #3b82f6)', textDecoration: 'none', fontSize: '0.9rem', marginTop: '-4px', marginBottom: '12px', wordBreak: 'break-all' }}
                >
                  <FolderOpen size={15} />
                  Pasta de imagens no Google Drive
                </a>
              )}

              {!fromHistory && (
                <>
                  <div className="input-group">
                    <label>URL do Velox</label>
                    <input type="text" className="input-control"
                      placeholder="https://app.velox.run/chat?sessionId=..."
                      value={url} onChange={e => setUrl(e.target.value)} disabled={isActive} />
                  </div>

                  <div className="input-group">
                    <label>Número da Ficha</label>
                    <input type="text" className="input-control"
                      placeholder="Ex: 12345"
                      value={ficha} onChange={e => setFicha(e.target.value)} disabled={isActive} />
                  </div>

                  <div className="input-group">
                    <label>Opções do Pipeline</label>
                    <div className="options-group">
                      <label className="option-item">
                        <input type="checkbox" checked={options.do_transcribe}
                          onChange={() => toggleOption('do_transcribe')} disabled={isActive} />
                        Transcrever áudios
                      </label>
                      <label className="option-item">
                        <input type="checkbox" checked={options.do_upload_images}
                          onChange={() => toggleOption('do_upload_images')} disabled={isActive} />
                        Enviar imagens ao Drive
                      </label>
                      <label className="option-item">
                        <input type="checkbox" checked={options.do_summary}
                          onChange={() => toggleOption('do_summary')} disabled={isActive} />
                        Gerar resumo com IA
                      </label>
                      <label className="option-item">
                        <input type="checkbox" checked={options.do_insert_center}
                          onChange={() => toggleOption('do_insert_center')} disabled={isActive} />
                        Inserir no Center
                      </label>
                    </div>
                  </div>
                </>
              )}

              <div className="start-row">
                {isActive ? (
                  <>
                    <button className="btn btn-primary" disabled>
                      <Loader size={18} className="spin" />
                      {status === 'PROCESSING' && 'Processando...'}
                      {status === 'SUMMARIZING' && 'Resumindo...'}
                      {status === 'SYNCING' && 'Sincronizando...'}
                      {status === 'INSERTING' && 'Inserindo no Center...'}
                    </button>
                    <button className="btn btn-danger" onClick={handleStop}>
                      <Square size={18} /> Parar
                    </button>
                  </>
                ) : !fromHistory ? (
                  <button className="btn btn-primary"
                    onClick={TERMINAL_STATUSES.includes(status) ? handleReset : handleStart}
                    disabled={loading || (status === 'PENDING' && (!url || !ficha))}>
                    <Play size={18} />
                    {TERMINAL_STATUSES.includes(status) ? 'Nova Ocorrência' : 'Iniciar Processamento'}
                  </button>
                ) : null}
              </div>

              {/* Painel de Logs */}
              {(logs.length > 0 || isActive) && (
                <div className="log-panel">
                  {logs.length === 0 && <span className="log-line">Aguardando logs...</span>}
                  {logs.map((line, idx) => (
                    <div key={idx} className={logClass(line)}>{line}</div>
                  ))}
                  <div ref={logEndRef} />
                </div>
              )}
            </div>

            {/* Ações pós-processamento */}
            {status === 'COMPLETED' && (
              <div className="glass-panel card" style={{ marginTop: '24px' }}>
                <h2 className="card-title">Ações</h2>
                <div className="actions-row" style={{ flexWrap: 'wrap' }}>
                  {!summary && hasRawContent && (
                    <button className="btn btn-primary" onClick={handleSummarize}>
                      <FileText size={18} /> Resumir Relatório
                    </button>
                  )}
                  {summary && (
                    <button className="btn btn-danger" onClick={handleClearSummary}>
                      <FileText size={18} /> Limpar Resumo
                    </button>
                  )}
                  {summary && (
                    <>
                      <button className="btn" style={{ background: 'rgba(79,110,247,0.15)', border: '1px solid rgba(79,110,247,0.4)', color: '#7fa4ff' }} onClick={handleViewPdf}>
                        <Printer size={18} /> Visualizar PDF
                      </button>
                      <button className="btn" style={{ background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.35)', color: '#34d399' }} onClick={handleViewPdfPublico}>
                        <Printer size={18} /> PDF Público
                      </button>
                    </>
                  )}
                  <button className="btn" style={{ background: 'rgba(255,255,255,0.1)' }} onClick={handleSyncImages}>
                    <RefreshCw size={18} /> Enviar Novas Imagens
                  </button>
                  {isAdmin && (
                    <button className="btn" style={{ background: 'rgba(255,255,255,0.05)', border: '1px dashed var(--border)' }} onClick={handleDebugMessages}>
                      <Bug size={18} /> Debug JSON
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Editor de resumo */}
            {status === 'COMPLETED' && summary && (
              <div className="glass-panel card" style={{ marginTop: '24px' }}>
                <h2 className="card-title">Quadro de Revisão</h2>

                {centerDuplicate && !centerInserted && (
                  <div style={{ background: 'rgba(234,179,8,0.12)', border: '1px solid rgba(234,179,8,0.35)', borderRadius: '8px', padding: '10px 14px', marginBottom: '16px', fontSize: '0.85rem', color: '#facc15' }}>
                    Ocorrência duplicada encontrada no Center para esta ficha. Revise o relatório e clique em "Inserir MGM" para inserir mesmo assim.
                  </div>
                )}
                {centerInserted && (
                  <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: '8px', padding: '10px 14px', marginBottom: '16px', fontSize: '0.85rem', color: '#4ade80' }}>
                    Ocorrência inserida no Center com sucesso.
                  </div>
                )}

                <ReportLineEditor value={summary} onChange={setSummary} />
                <div className="actions-row" style={{ marginTop: '16px', flexWrap: 'wrap' }}>
                  <button className="btn btn-accent" onClick={handleSaveDraft}>
                    <Save size={18} /> Salvar Rascunho
                  </button>
                  <button className="btn btn-accent" onClick={handleInsertMGM}>
                    <Send size={18} /> {centerDuplicate && !centerInserted ? 'Inserir MGM mesmo assim' : 'Inserir MGM (Center)'}
                  </button>
                </div>
              </div>
            )}

            {status === 'ERROR' && (
              <div className="glass-panel card" style={{ marginTop: '24px', borderColor: 'var(--danger)' }}>
                <h2 className="card-title" style={{ color: 'var(--danger)' }}>Erro no processamento</h2>
                {errorMessage
                  ? <p style={{ color: 'var(--danger)', fontSize: '0.9rem', marginTop: '8px', wordBreak: 'break-word' }}>{errorMessage}</p>
                  : <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Verifique os logs acima para detalhes.</p>
                }
              </div>
            )}

            {status === 'CANCELLED' && (
              <div className="glass-panel card" style={{ marginTop: '24px', borderColor: 'var(--text-muted)' }}>
                <h2 className="card-title" style={{ color: 'var(--text-muted)' }}>Processamento cancelado</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Clique em "Nova Ocorrência" para recomeçar.</p>
              </div>
            )}
          </div>

          {/* Sidebar — Progresso */}
          <div className="glass-panel card">
            <h2 className="card-title">Progresso</h2>
            <div style={{ marginTop: '24px' }}>
              {STEPS.map((step, idx) => {
                const isCompleted = stepIndex > idx || status === 'COMPLETED';
                const isActive = idx === stepIndex && ACTIVE_STATUSES.includes(status);

                return (
                  <div key={step.id} className="tracker-step">
                    <div className={`step-indicator ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}>
                      {isCompleted
                        ? <CheckCircle size={14} color="#fff" />
                        : <Circle size={10} color={isActive ? 'var(--primary)' : 'var(--text-muted)'} />}
                    </div>
                    <div className={`step-label ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}>
                      {step.label}
                    </div>
                  </div>
                );
              })}

              {status === 'ERROR' && (
                <p style={{ color: 'var(--danger)', fontSize: '0.85rem', marginTop: '16px' }}>
                  Erro durante o processamento.
                </p>
              )}
              {status === 'CANCELLED' && (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '16px' }}>
                  Cancelado pelo usuário.
                </p>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};
