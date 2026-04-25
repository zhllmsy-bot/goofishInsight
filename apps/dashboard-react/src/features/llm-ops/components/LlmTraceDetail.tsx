import { Link, useLocation } from 'react-router-dom';

import { formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspacePath, readInitialQuery } from '../../dashboard/lib/urlState';
import type { LlmTraceDetail as LlmTraceDetailModel } from '../types/llmOps';
import { CodeBlock, LatencyBar, MessageCard, TokenBar } from './LlmOpsTraceBlocks';

type LlmTraceDetailProps = {
  trace: LlmTraceDetailModel | null;
};

function getTraceStatusPillClass(status: string | null | undefined) {
  if (status === 'success') {
    return 'is-success';
  }
  if (status === 'error') {
    return 'is-error';
  }
  return '';
}

export function LlmTraceDetail(props: LlmTraceDetailProps) {
  const location = useLocation();
  const workspaceQuery = readInitialQuery(location.search);

  if (!props.trace) {
    return (
      <article className="llm-trace-detail-card">
        <p className="panel-subtitle">还没有可展示的 LLM trace。</p>
      </article>
    );
  }

  return (
    <article className="llm-trace-detail-card">
      <div className="llm-trace-meta-bar">
        <div className="llm-trace-meta-bar-left">
          <h3 className="llm-trace-title">{props.trace.model || '-'}</h3>
          <div className="llm-trace-meta-pills">
            <span className="soft-pill small">{props.trace.provider || '-'}</span>
            <span className="soft-pill small">{props.trace.method || '-'}</span>
            <span className={`soft-pill small ${getTraceStatusPillClass(props.trace.status)}`}>
              {props.trace.status || '-'}
            </span>
            <span className="soft-pill small">{formatRelative(props.trace.generated_at || null)}</span>
          </div>
        </div>
        <div className="llm-trace-meta-bar-right">
          {props.trace.item_id ? (
            <Link
              className="llm-trace-item-link"
              to={buildWorkspacePath(`/items/${props.trace.item_id}`, workspaceQuery)}
            >
              查看商品详情 →
            </Link>
          ) : null}
        </div>
      </div>

      <div className="llm-trace-metrics">
        <div className="llm-metric-card">
          <div className="llm-metric-label">Token 消耗</div>
          <TokenBar usage={props.trace.usage} />
        </div>
        <div className="llm-metric-card">
          <div className="llm-metric-label">响应延迟</div>
          <LatencyBar latencyMs={props.trace.latency_ms} />
        </div>
      </div>

      {props.trace.error ? <div className="llm-trace-error">{props.trace.error}</div> : null}

      <section className="llm-trace-messages-section">
        <div className="llm-trace-section-header">
          <h4>Messages</h4>
          <span className="panel-subtitle">{props.trace.message_count} 条消息</span>
        </div>
        {(props.trace.messages ?? []).length ? (
          props.trace.messages.map((message) => (
            <MessageCard
              key={`${message.role}:${message.index}`}
              message={message}
              reasoningContent={message.role === 'assistant' ? props.trace?.reasoning_content : undefined}
            />
          ))
        ) : (
          <p className="panel-subtitle">这条 trace 没有 messages 内容。</p>
        )}
      </section>

      <section className="llm-trace-code-section">
        <div className="llm-trace-section-header">
          <h4>Technical Details</h4>
        </div>
        <div className="llm-trace-code-grid">
          <CodeBlock title="Request Headers" content={props.trace.request_headers_json} language="json" />
          <CodeBlock title="Request Payload" content={props.trace.request_payload_json} open language="json" />
          <CodeBlock title="Response Payload" content={props.trace.response_payload_json} language="json" />
          <CodeBlock title="Raw Trace" content={props.trace.raw_json} language="json" />
        </div>
      </section>
    </article>
  );
}
