import { formatRelative } from '../../dashboard/lib/formatters';
import { formatLatency, formatTokens } from '../lib/formatTrace';
import type { LlmTraceSection } from '../types/llmOps';

type LlmTraceListProps = {
  traces: LlmTraceSection['traces'];
  selectedTraceKey: string;
  onSelectTraceKey: (traceKey: string) => void;
};

function getTraceStatusTone(status: string | null | undefined) {
  if (status === 'success') {
    return 'success';
  }
  if (status === 'error') {
    return 'error';
  }
  return 'broken';
}

export function LlmTraceList(props: LlmTraceListProps) {
  const traces = props.traces ?? [];

  if (!traces.length) {
    return (
      <article className="llm-trace-empty-card">
        <p className="panel-subtitle">还没有 trace 文件。先触发一次模型调用即可。</p>
      </article>
    );
  }

  return (
    <div className="llm-trace-list-compact">
      {traces.map((trace) => (
        <button
          className={`llm-trace-list-item-compact ${trace.trace_key === props.selectedTraceKey ? 'active' : ''}`}
          key={trace.trace_key}
          type="button"
          onClick={() => props.onSelectTraceKey(trace.trace_key)}
        >
          <div className="llm-trace-list-head-compact">
            <div className="llm-trace-id">{trace.trace_key.slice(-12)}</div>
            <div className="llm-trace-badges">
              <span className={`status-dot ${getTraceStatusTone(trace.status)}`} />
              <span className="soft-pill small">{trace.model || '-'}</span>
            </div>
          </div>
          <div className="llm-trace-meta-compact">
            <span>{formatRelative(trace.generated_at || null)}</span>
            <span className="llm-trace-latency">{formatLatency(trace.latency_ms)}</span>
            <span className="llm-trace-tokens">{formatTokens(trace.usage)}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
