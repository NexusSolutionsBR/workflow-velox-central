import { useState, useEffect, Fragment } from 'react';
import api from '../api';
import { RefreshCw, Search, ChevronDown, ChevronUp, AlertCircle, FileText } from 'lucide-react';
import './Audit.css';

interface AuditLog {
  id: string;
  user_id: string | null;
  user_name: string | null;
  action: string;
  endpoint: string | null;
  session_id: string | null;
  ficha: string | null;
  status: string;
  error: string | null;
  ip: string | null;
  payload: any | null;
  created_at: string;
}

export const Audit = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  


  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/audit', { params: { limit: 1000 } });
      setLogs(res.data.data || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Erro ao carregar logs de auditoria');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const getStatusBadgeClass = (status: string) => {
    if (status === 'SUCCESS' || status === 'COMPLETED') return 'badge-success';
    if (status === 'ERROR' || status === 'FATAL') return 'badge-error';
    if (status === 'PENDING' || status === 'PROCESSING') return 'badge-warning';
    return 'badge-info';
  };

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }).format(date);
    } catch {
      return dateString;
    }
  };

  const filteredLogs = logs.filter(log => {
    const searchLower = searchTerm.toLowerCase();
    return (
      (log.ficha && log.ficha.toLowerCase().includes(searchLower)) ||
      (log.session_id && log.session_id.toLowerCase().includes(searchLower)) ||
      (log.action && log.action.toLowerCase().includes(searchLower))
    );
  });

  return (
    <div className="audit-container">
      <div className="audit-header">
        <div>
          <h1 className="page-title">Auditoria de Logs</h1>
          <p className="page-subtitle">Acompanhe as operações, resumos e possíveis falhas na API</p>
        </div>
        <button className="btn btn-primary" onClick={fetchLogs} disabled={loading}>
          <RefreshCw size={18} className={loading ? 'spin' : ''} />
          Atualizar
        </button>
      </div>

      <div className="glass-panel audit-panel">
        <div className="audit-controls">
          <div className="search-box">
            <Search size={18} className="search-icon" />
            <input 
              type="text" 
              placeholder="Buscar por ficha, sessão ou ação..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="search-input"
            />
          </div>
        </div>

        {error && (
          <div className="error-alert">
            <AlertCircle size={20} />
            {error}
          </div>
        )}

        <div className="table-responsive">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Data/Hora</th>
                <th>Operador</th>
                <th>Ficha</th>
                <th>Sessão</th>
                <th>Ação</th>
                <th>Status</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8">Carregando logs...</td>
                </tr>
              ) : filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8">Nenhum log encontrado.</td>
                </tr>
              ) : (
                filteredLogs.map(log => (
                  <Fragment key={log.id}>
                    <tr className={`audit-row ${expandedId === log.id ? 'expanded' : ''}`} onClick={() => toggleExpand(log.id)}>
                      <td>{formatDate(log.created_at)}</td>
                      <td>{log.user_name || 'Não autenticado'}</td>
                      <td className="font-mono">{log.ficha || '-'}</td>
                      <td className="font-mono" title={log.session_id || ''}>
                        {log.session_id ? log.session_id.substring(0, 8) + '...' : '-'}
                      </td>
                      <td>{log.action}</td>
                      <td>
                        <span className={`status-badge ${getStatusBadgeClass(log.status)}`}>
                          {log.status}
                        </span>
                      </td>
                      <td>
                        <button className="btn-icon" onClick={(e) => { e.stopPropagation(); toggleExpand(log.id); }}>
                          {expandedId === log.id ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                        </button>
                      </td>
                    </tr>
                    {expandedId === log.id && (
                      <tr className="audit-details-row">
                        <td colSpan={7}>
                          <div className="audit-details">
                            <div className="details-grid">
                              {log.error && (
                                <div className="detail-section error">
                                  <h4><AlertCircle size={16} /> Erro</h4>
                                  <pre>{log.error}</pre>
                                </div>
                              )}
                              
                              <div className="detail-section">
                                <h4><FileText size={16} /> Detalhes da Requisição</h4>
                                <ul>
                                  <li><strong>IP:</strong> {log.ip || '-'}</li>
                                  <li><strong>Endpoint:</strong> {log.endpoint || '-'}</li>
                                  <li><strong>Sessão Completa:</strong> {log.session_id || '-'}</li>
                                  <li><strong>Usuário ID:</strong> {log.user_id || '-'}</li>
                                </ul>
                              </div>

                              {log.payload && (
                                <div className="detail-section full-width">
                                  <h4>Payload / Dados</h4>
                                  <pre className="json-pre">{JSON.stringify(log.payload, null, 2)}</pre>
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
