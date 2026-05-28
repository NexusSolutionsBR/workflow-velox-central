import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { History as HistoryIcon, Search, ChevronLeft, ChevronRight, ExternalLink, RefreshCw, CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react';
import './History.css';

interface SessionItem {
  sessionId: string;
  ficha: string;
  status: string;
  contactName: string | null;
  operatorName: string | null;
  hasSummary: boolean;
  hasRawContent: boolean;
  createdAt: string;
}

interface Pagination {
  total: number;
  page: number;
  perPage: number;
  pages: number;
  items: SessionItem[];
}

const STATUS_LABELS: Record<string, string> = {
  COMPLETED: 'Concluído',
  PROCESSING: 'Processando',
  SUMMARIZING: 'Resumindo',
  SYNCING: 'Sincronizando',
  ERROR: 'Erro',
  CANCELLED: 'Cancelado',
  PENDING: 'Pendente',
};

const StatusBadge = ({ status }: { status: string }) => {
  const label = STATUS_LABELS[status] ?? status;
  const icons: Record<string, React.ReactElement> = {
    COMPLETED: <CheckCircle size={12} />,
    ERROR: <XCircle size={12} />,
    CANCELLED: <XCircle size={12} />,
    PROCESSING: <RefreshCw size={12} className="spin" />,
    SUMMARIZING: <RefreshCw size={12} className="spin" />,
    SYNCING: <RefreshCw size={12} className="spin" />,
    PENDING: <Clock size={12} />,
  };
  return (
    <span className={`status-badge status-${status.toLowerCase()}`}>
      {icons[status] ?? <AlertCircle size={12} />}
      {label}
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

export const History = () => {
  const [data, setData] = useState<Pagination | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [fichaFilter, setFichaFilter] = useState('');
  const [fichaInput, setFichaInput] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    if (!localStorage.getItem('user')) navigate('/login');
  }, [navigate]);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page, per_page: 20 };
      if (fichaFilter) params.ficha = fichaFilter;
      if (statusFilter) params.status = statusFilter;
      const res = await api.get('/sessions', { params });
      setData(res.data);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }, [page, fichaFilter, statusFilter]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const handleSearch = () => {
    setPage(1);
    setFichaFilter(fichaInput.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  const handleOpen = (sessionId: string) => {
    navigate(`/dashboard?sessionId=${encodeURIComponent(sessionId)}`);
  };

  return (
    <div className="history-container">
      <div className="history-header">
        <div>
          <h1 className="history-title">
            <HistoryIcon size={22} />
            Fichas
          </h1>
          <p className="history-subtitle">
            {data ? `${data.total} atendimento${data.total !== 1 ? 's' : ''} registrado${data.total !== 1 ? 's' : ''}` : 'Carregando...'}
          </p>
        </div>
        <button className="btn-refresh" onClick={fetchHistory} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'spin' : ''} />
          Atualizar
        </button>
      </div>

      {/* Filtros */}
      <div className="history-filters">
        <div className="filter-search">
          <input
            className="filter-input"
            type="text"
            placeholder="Buscar por ficha..."
            value={fichaInput}
            onChange={e => setFichaInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="btn-search" onClick={handleSearch}>
            <Search size={15} />
          </button>
        </div>
        <select
          className="filter-select"
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <option value="">Todos os status</option>
          <option value="COMPLETED">Concluído</option>
          <option value="ERROR">Erro</option>
          <option value="CANCELLED">Cancelado</option>
          <option value="PROCESSING">Processando</option>
        </select>
      </div>

      {/* Tabela */}
      <div className="history-table-wrapper">
        {loading && !data ? (
          <div className="empty-state">
            <RefreshCw size={28} className="spin" />
            <span>Carregando...</span>
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="empty-state">
            <HistoryIcon size={32} />
            <span>Nenhum atendimento encontrado</span>
          </div>
        ) : (
          <table className="history-table">
            <thead>
              <tr>
                <th>Ficha</th>
                <th>Contato</th>
                <th>Status</th>
                <th>Operador</th>
                <th>Data</th>
                <th>Resumo</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map(item => (
                <tr key={item.sessionId}>
                  <td className="ficha-cell">{item.ficha || '—'}</td>
                  <td>{item.contactName || <span className="text-muted">—</span>}</td>
                  <td><StatusBadge status={item.status} /></td>
                  <td>{item.operatorName || <span className="text-muted">—</span>}</td>
                  <td className="date-cell">{formatDate(item.createdAt)}</td>
                  <td>
                    {item.hasSummary ? (
                      <span className="summary-badge">Gerado</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td>
                    <button
                      className="btn-open"
                      onClick={() => handleOpen(item.sessionId)}
                      title="Abrir atendimento"
                    >
                      <ExternalLink size={14} />
                      Abrir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Paginação */}
      {data && data.pages > 1 && (
        <div className="pagination">
          <button
            className="page-btn"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1 || loading}
          >
            <ChevronLeft size={16} />
          </button>
          <span className="page-info">
            Página {data.page} de {data.pages}
          </span>
          <button
            className="page-btn"
            onClick={() => setPage(p => Math.min(data.pages, p + 1))}
            disabled={page === data.pages || loading}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
};
