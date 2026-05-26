import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Clock, RefreshCw, Trash2, AlertCircle, Play, CheckCircle, XCircle } from 'lucide-react';
import './PendingTasks.css';

interface ScheduledSync {
  id: string;
  sessionId: string;
  ficha: string;
  contactName: string | null;
  runAt: string;
  status: string;
  createdAt: string;
}

const Countdown = ({ targetDate }: { targetDate: string }) => {
  const [timeLeft, setTimeLeft] = useState('');

  useEffect(() => {
    const update = () => {
      const diff = new Date(targetDate).getTime() - Date.now();
      if (diff <= 0) {
        setTimeLeft('Aguardando execução');
        return;
      }
      const hrs = Math.floor(diff / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${hrs}h ${String(mins).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`);
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [targetDate]);

  return <span className="countdown-text">{timeLeft}</span>;
};

const STATUS_CONFIG: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
  PENDING:   { label: 'Pendente',  className: 'badge-pending',   icon: <Clock size={11} /> },
  COMPLETED: { label: 'Concluída', className: 'badge-completed', icon: <CheckCircle size={11} /> },
  FAILED:    { label: 'Falhou',    className: 'badge-failed',    icon: <XCircle size={11} /> },
  CANCELLED: { label: 'Cancelada', className: 'badge-cancelled', icon: <XCircle size={11} /> },
};

const StatusBadge = ({ status }: { status: string }) => {
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: 'badge-pending', icon: null };
  return (
    <span className={`sync-status-badge ${cfg.className}`}>
      {cfg.icon}{cfg.label}
    </span>
  );
};

const formatDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
};

export const PendingTasks = () => {
  const [tasks, setTasks] = useState<ScheduledSync[]>([]);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const navigate = useNavigate();

  const api = axios.create({ baseURL: 'http://localhost:3000', withCredentials: true });

  useEffect(() => {
    if (!localStorage.getItem('user')) navigate('/login');
  }, [navigate]);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const res = await api.get(`/sessions/scheduled-syncs${params}`);
      setTasks(res.data);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const handleCancel = async (id: string) => {
    if (!confirm('Cancelar esta sincronização agendada?')) return;
    setActing(id);
    try {
      await api.delete(`/sessions/scheduled-syncs/${id}`);
      setTasks(prev => prev.map(t => t.id === id ? { ...t, status: 'CANCELLED' } : t));
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao cancelar tarefa');
    } finally {
      setActing(null);
    }
  };

  const handleRunNow = async (id: string) => {
    if (!confirm('Iniciar a coleta de imagens agora, antes do prazo?')) return;
    setActing(id);
    try {
      await api.post(`/sessions/scheduled-syncs/${id}/run-now`);
      setTasks(prev => prev.map(t => t.id === id ? { ...t, status: 'COMPLETED' } : t));
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao iniciar coleta');
    } finally {
      setActing(null);
    }
  };

  const pendingCount = tasks.filter(t => t.status === 'PENDING').length;

  return (
    <div className="app-container">
      <div className="content">
        <div className="pending-tasks-container">
          <div className="pending-tasks-header">
            <div>
              <h1 className="pending-tasks-title">
                <Clock size={22} />
                Tarefas
              </h1>
              <p className="pending-tasks-subtitle">
                {pendingCount > 0
                  ? `${pendingCount} pendente${pendingCount !== 1 ? 's' : ''} — ${tasks.length} no total`
                  : `${tasks.length} registro${tasks.length !== 1 ? 's' : ''} no histórico`}
              </p>
            </div>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <select
                className="filter-select-sync"
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
              >
                <option value="">Todos</option>
                <option value="PENDING">Pendentes</option>
                <option value="COMPLETED">Concluídas</option>
                <option value="FAILED">Falhou</option>
                <option value="CANCELLED">Canceladas</option>
              </select>
              <button className="btn-refresh" onClick={fetchTasks} disabled={loading}>
                <RefreshCw size={16} className={loading ? 'spin' : ''} />
                Atualizar
              </button>
            </div>
          </div>

          {!loading && tasks.length === 0 ? (
            <div className="empty-state">
              <AlertCircle size={40} opacity={0.3} />
              <p>{statusFilter ? 'Nenhum registro com este status.' : 'Nenhuma sincronização registrada.'}</p>
            </div>
          ) : (
            <div className="tasks-table-wrapper">
              <table className="tasks-table">
                <thead>
                  <tr>
                    <th>Ficha</th>
                    <th>Contato</th>
                    <th>Agendado Para</th>
                    <th>Tempo Restante</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map(task => (
                    <tr key={task.id} className={acting === task.id ? 'row-removing' : ''}>
                      <td><strong>{task.ficha || <span className="text-muted">—</span>}</strong></td>
                      <td>{task.contactName || <span className="text-muted">—</span>}</td>
                      <td>{formatDate(task.runAt)}</td>
                      <td>
                        {task.status === 'PENDING'
                          ? <Countdown targetDate={task.runAt} />
                          : <span className="text-muted">—</span>}
                      </td>
                      <td><StatusBadge status={task.status} /></td>
                      <td>
                        {task.status === 'PENDING' ? (
                          <div className="action-buttons">
                            <button
                              className="btn-run-now"
                              onClick={() => handleRunNow(task.id)}
                              disabled={acting === task.id}
                              title="Executar imediatamente"
                            >
                              <Play size={13} />
                              Coletar Agora
                            </button>
                            <button
                              className="btn-cancel"
                              onClick={() => handleCancel(task.id)}
                              disabled={acting === task.id}
                              title="Cancelar sincronização"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
