import React, { useState } from 'react';
import { FileText, ExternalLink, Loader2, FolderOpen } from 'lucide-react';
import './FichaReport.css';

export const FichaReport: React.FC = () => {
  const [ficha, setFicha] = useState('');
  const [driveUrl, setDriveUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleGenerate = () => {
    if (!ficha.trim()) {
      setError('Informe o número da ficha');
      return;
    }

    setError('');
    setLoading(true);

    // Montar URL do relatório com token de autenticação via cookie
    const params = new URLSearchParams({ ficha: ficha.trim() });
    if (driveUrl.trim()) {
      params.append('drive_folder_url', driveUrl.trim());
    }

    const reportUrl = `${import.meta.env.VITE_API_URL}/sessions/report-by-ficha?${params.toString()}`;

    // Abrir em nova aba — o cookie httpOnly vai junto automaticamente
    window.open(reportUrl, '_blank');

    setLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleGenerate();
    }
  };

  return (
    <div className="ficha-report-container">
      <div className="ficha-report-header">
        <FileText size={28} className="header-icon" />
        <div>
          <h1>Relatório por Ficha</h1>
          <p className="header-subtitle">
            Gere um relatório com dados do Center e ocorrências usando apenas o número da ficha
          </p>
        </div>
      </div>

      <div className="ficha-report-card glass-panel">
        <div className="card-inner">
          <div className="input-section">
            <div className="input-group">
              <label htmlFor="ficha-input">
                <FileText size={14} />
                Número da Ficha
              </label>
              <input
                id="ficha-input"
                type="text"
                className="input-control"
                placeholder="Ex: 85741"
                value={ficha}
                onChange={(e) => { setFicha(e.target.value); setError(''); }}
                onKeyDown={handleKeyDown}
                autoFocus
              />
            </div>

            <div className="input-group">
              <label htmlFor="drive-input">
                <FolderOpen size={14} />
                Link do Google Drive <span className="optional-tag">(opcional)</span>
              </label>
              <input
                id="drive-input"
                type="url"
                className="input-control"
                placeholder="https://drive.google.com/drive/folders/..."
                value={driveUrl}
                onChange={(e) => setDriveUrl(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <button
            className="btn btn-primary generate-btn"
            onClick={handleGenerate}
            disabled={loading || !ficha.trim()}
          >
            {loading ? (
              <>
                <Loader2 size={18} className="spin" />
                Gerando...
              </>
            ) : (
              <>
                <ExternalLink size={18} />
                Gerar Relatório
              </>
            )}
          </button>

          <div className="info-box">
            <p>
              O relatório será aberto em uma nova aba com os dados cadastrais da ficha,
              ocorrências registradas no Center e o link do Google Drive (se informado).
              Use <strong>Ctrl+P</strong> para salvar como PDF.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
