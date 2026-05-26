import {
  useState, useCallback, useRef, useEffect, useMemo,
  type ChangeEvent, type DragEvent,
} from 'react';
import {
  Plus, AlignLeft, Trash2, ChevronUp, ChevronDown, GripVertical,
} from 'lucide-react';
import './ReportLineEditor.css';

/* ─── Tipos ─── */

interface ReportLine {
  id: string;
  date: string;
  time: string;
  type: 'PÚBLICA' | 'INTERNA';
  description: string;
  raw?: string;           // fallback para linhas não-parseadas
}

interface Props {
  value: string;
  onChange: (v: string) => void;
}

/* ─── Helpers ─── */

let _idSeq = 0;
const uid = () => `rle-${Date.now()}-${++_idSeq}`;

const LINE_RE =
  /^(\d+)\.\s+(\d{2}\/\d{2}\/\d{4}),?\s+(\d{2}:\d{2}:\d{2})\s*—\s*(PÚBLICA|INTERNA)\s*—\s*(.+)$/;

function parseLine(raw: string): ReportLine {
  const m = raw.match(LINE_RE);
  if (m) {
    return {
      id: uid(),
      date: m[2],
      time: m[3],
      type: m[4] as 'PÚBLICA' | 'INTERNA',
      description: m[5].trim(),
    };
  }
  return {
    id: uid(),
    date: '',
    time: '',
    type: 'PÚBLICA',
    description: '',
    raw: raw.trim(),
  };
}

function parseText(text: string): ReportLine[] {
  if (!text.trim()) return [];

  // Divide o texto respeitando tópicos multi-linha.
  // Um novo tópico começa quando a linha inicia com "NÚMERO."
  const topicRe = /^(\d+)\.\s/;
  const rawLines = text.split('\n');
  const topics: string[] = [];
  let buffer = '';

  for (const line of rawLines) {
    if (topicRe.test(line)) {
      if (buffer) topics.push(buffer.trim());
      buffer = line;
    } else if (buffer) {
      buffer += ' ' + line.trim();
    } else {
      // Linha avulsa antes do primeiro tópico
      if (line.trim()) topics.push(line.trim());
    }
  }
  if (buffer) topics.push(buffer.trim());

  return topics.map(parseLine);
}

function serializeLine(line: ReportLine, idx: number): string {
  if (line.raw !== undefined) return line.raw;
  const num = idx + 1;
  return `${num}. ${line.date}, ${line.time} — ${line.type} — ${line.description}`;
}

function serializeAll(lines: ReportLine[]): string {
  return lines.map((l, i) => serializeLine(l, i)).join('\n\n');
}

/* ─── Auto-resize textarea ─── */

function useAutoResize(value: string) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return ref;
}

function AutoTextarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useAutoResize(String(props.value ?? ''));
  return <textarea ref={ref} rows={1} {...props} />;
}

/* ─── Componente Principal ─── */

export const ReportLineEditor = ({ value, onChange }: Props) => {
  const [rawMode, setRawMode] = useState(false);
  const [lines, setLines] = useState<ReportLine[]>(() => parseText(value));
  const dragSrc = useRef<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);

  // Sync externo → interno (quando o summary muda fora do componente, ex: polling)
  const lastSerialised = useRef(value);
  useEffect(() => {
    if (value !== lastSerialised.current) {
      setLines(parseText(value));
      lastSerialised.current = value;
    }
  }, [value]);

  // Propaga mudanças para cima
  const propagate = useCallback((next: ReportLine[]) => {
    setLines(next);
    const s = serializeAll(next);
    lastSerialised.current = s;
    onChange(s);
  }, [onChange]);

  /* ── Edição de campo ── */

  const updateField = useCallback(
    (id: string, field: keyof ReportLine, val: string) => {
      setLines(prev => {
        const next = prev.map(l =>
          l.id === id ? { ...l, [field]: val, ...(field !== 'raw' ? { raw: undefined } : {}) } : l,
        );
        const s = serializeAll(next);
        lastSerialised.current = s;
        onChange(s);
        return next;
      });
    },
    [onChange],
  );

  const toggleType = useCallback(
    (id: string) => {
      setLines(prev => {
        const next = prev.map(l =>
          l.id === id ? { ...l, type: (l.type === 'PÚBLICA' ? 'INTERNA' : 'PÚBLICA') as 'PÚBLICA' | 'INTERNA', raw: undefined } : l,
        );
        const s = serializeAll(next);
        lastSerialised.current = s;
        onChange(s);
        return next;
      });
    },
    [onChange],
  );

  /* ── Reordenar ── */

  const move = useCallback(
    (from: number, to: number) => {
      if (to < 0 || to >= lines.length) return;
      const next = [...lines];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      propagate(next);
    },
    [lines, propagate],
  );

  /* ── Adicionar / Remover ── */

  const addLine = useCallback(() => {
    const now = new Date();
    const dd = String(now.getDate()).padStart(2, '0');
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const yyyy = now.getFullYear();
    const hh = String(now.getHours()).padStart(2, '0');
    const mi = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');

    const newLine: ReportLine = {
      id: uid(),
      date: `${dd}/${mm}/${yyyy}`,
      time: `${hh}:${mi}:${ss}`,
      type: 'PÚBLICA',
      description: '',
    };
    propagate([...lines, newLine]);
  }, [lines, propagate]);

  const removeLine = useCallback(
    (id: string) => {
      propagate(lines.filter(l => l.id !== id));
    },
    [lines, propagate],
  );

  /* ── Drag & Drop ── */

  const handleDragStart = (e: DragEvent, idx: number) => {
    dragSrc.current = idx;
    e.dataTransfer.effectAllowed = 'move';
    // Need to set data for Firefox
    e.dataTransfer.setData('text/plain', String(idx));
  };

  const handleDragOver = (e: DragEvent, idx: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(idx);
  };

  const handleDragLeave = () => setDragOver(null);

  const handleDrop = (e: DragEvent, idx: number) => {
    e.preventDefault();
    setDragOver(null);
    if (dragSrc.current !== null && dragSrc.current !== idx) {
      move(dragSrc.current, idx);
    }
    dragSrc.current = null;
  };

  const handleDragEnd = () => {
    dragSrc.current = null;
    setDragOver(null);
  };

  /* ── Toggle raw mode ── */

  const handleToggleRaw = () => {
    if (rawMode) {
      // Volta ao modo estruturado: re-parseia o texto
      setLines(parseText(value));
    }
    setRawMode(r => !r);
  };

  /* ── Contagem ── */
  const structuredCount = useMemo(
    () => lines.filter(l => l.raw === undefined).length,
    [lines],
  );

  /* ── Render ── */

  return (
    <div className="rle-container">
      {/* Toolbar */}
      <div className="rle-toolbar">
        <div className="rle-toolbar-left">
          <span className="rle-count">
            {structuredCount} movimentação{structuredCount !== 1 ? 'ões' : ''}
          </span>
        </div>
        <div className="rle-toolbar-right">
          <button
            type="button"
            className={`rle-btn-toolbar ${rawMode ? 'active' : ''}`}
            onClick={handleToggleRaw}
            title={rawMode ? 'Voltar ao editor estruturado' : 'Editar como texto bruto'}
          >
            <AlignLeft size={14} />
            Texto Bruto
          </button>
          {!rawMode && (
            <button
              type="button"
              className="rle-btn-toolbar"
              onClick={addLine}
              title="Adicionar nova linha"
            >
              <Plus size={14} />
              Nova Linha
            </button>
          )}
        </div>
      </div>

      {rawMode ? (
        /* Modo texto bruto */
        <textarea
          className="rle-raw-textarea"
          value={value}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
        />
      ) : (
        /* Modo estruturado */
        <div className="rle-list">
          {lines.length === 0 && (
            <div className="rle-empty">
              Nenhuma movimentação. Clique em "Nova Linha" para adicionar.
            </div>
          )}

          {lines.map((line, idx) => {
            const isRaw = line.raw !== undefined;
            const typeClass = isRaw ? 'raw' : line.type === 'INTERNA' ? 'interna' : 'publica';

            return (
              <div
                key={line.id}
                className={`rle-card${dragSrc.current === idx ? ' dragging' : ''}${dragOver === idx ? ' drag-over' : ''}`}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, idx)}
              >
                {/* Faixa colorida + número + drag handle */}
                <div
                  className={`rle-color-strip ${typeClass}`}
                  draggable
                  onDragStart={(e) => handleDragStart(e, idx)}
                  onDragEnd={handleDragEnd}
                  title="Arraste para reordenar"
                >
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                    <GripVertical size={14} style={{ opacity: 0.4 }} />
                    <span className="rle-number">{idx + 1}</span>
                  </div>
                </div>

                {/* Corpo */}
                <div className="rle-card-body">
                  {isRaw ? (
                    /* Linha não parseada */
                    <AutoTextarea
                      className="rle-raw-input"
                      value={line.raw}
                      onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
                        updateField(line.id, 'raw', e.target.value)
                      }
                      placeholder="Texto livre..."
                    />
                  ) : (
                    <>
                      {/* Linha 1: timestamp | tipo */}
                      <div className="rle-field-row">
                        <input
                          className="rle-input timestamp"
                          value={`${line.date}, ${line.time}`}
                          onChange={(e: ChangeEvent<HTMLInputElement>) => {
                            const parts = e.target.value.split(/,\s*/);
                            updateField(line.id, 'date', parts[0] || '');
                            if (parts[1] !== undefined) updateField(line.id, 'time', parts[1].trim());
                          }}
                          placeholder="DD/MM/YYYY, HH:MM:SS"
                        />
                        <span className="rle-separator" />
                        <button
                          type="button"
                          className={`rle-type-badge ${line.type === 'INTERNA' ? 'interna' : 'publica'}`}
                          onClick={() => toggleType(line.id)}
                          title="Clique para alternar PÚBLICA / INTERNA"
                        >
                          {line.type}
                        </button>
                      </div>

                      {/* Linha 2: descrição */}
                      <AutoTextarea
                        className="rle-description"
                        value={line.description}
                        onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
                          updateField(line.id, 'description', e.target.value)
                        }
                        placeholder="Descrição do evento..."
                      />
                    </>
                  )}
                </div>

                {/* Ações */}
                <div className="rle-actions">
                  <button
                    type="button"
                    className="rle-action-btn"
                    onClick={() => move(idx, idx - 1)}
                    disabled={idx === 0}
                    title="Mover para cima"
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    type="button"
                    className="rle-action-btn"
                    onClick={() => move(idx, idx + 1)}
                    disabled={idx === lines.length - 1}
                    title="Mover para baixo"
                  >
                    <ChevronDown size={14} />
                  </button>
                  <button
                    type="button"
                    className="rle-action-btn delete"
                    onClick={() => removeLine(line.id)}
                    title="Remover linha"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
