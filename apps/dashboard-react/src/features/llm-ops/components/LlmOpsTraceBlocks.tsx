import { useCallback, useEffect, useRef, useState } from 'react';

import { formatNumber } from '../../dashboard/lib/formatters';
import { formatLatency, type TokenUsage } from '../lib/formatTrace';
import {
  LLM_TRACE_COPY_FEEDBACK_DURATION_MS,
  LLM_TRACE_LATENCY_BAR_MAX_MS,
  LLM_TRACE_LATENCY_MEDIUM_THRESHOLD_MS,
  LLM_TRACE_LATENCY_SLOW_THRESHOLD_MS,
  LLM_TRACE_MESSAGE_ROLE_LABELS,
  LLM_TRACE_TOKEN_BAR_MAX_TOKENS,
} from '../lib/constants';

type MessageCardProps = {
  message: {
    role: string;
    index: number;
    content_text?: string | null;
  };
  reasoningContent?: string;
};

function useCopyFeedback(durationMs = LLM_TRACE_COPY_FEEDBACK_DURATION_MS) {
  const [isCopied, setIsCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
      }
    },
    [],
  );

  const triggerCopyFeedback = useCallback(() => {
    setIsCopied(true);
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => {
      setIsCopied(false);
      timeoutRef.current = null;
    }, durationMs);
  }, [durationMs]);

  return {
    isCopied,
    triggerCopyFeedback,
  };
}

export function TokenBar({
  usage,
  maxTokens = LLM_TRACE_TOKEN_BAR_MAX_TOKENS,
}: { usage: TokenUsage | null | undefined; maxTokens?: number }) {
  if (!usage) return null;
  const input = usage.input_tokens ?? 0;
  const output = usage.output_tokens ?? 0;
  const total = usage.total_tokens ?? (input + output);
  if (total === 0) return null;

  const inputPercent = Math.min((input / maxTokens) * 100, 100);
  const outputPercent = Math.min((output / maxTokens) * 100, 100);

  return (
    <div className="llm-token-bar">
      <div className="llm-token-bar-track">
        <div className="llm-token-bar-input" style={{ width: `${inputPercent}%` }} />
        <div className="llm-token-bar-output" style={{ width: `${outputPercent}%`, left: `${inputPercent}%` }} />
      </div>
      <div className="llm-token-bar-labels">
        <span className="llm-token-bar-input-label">In: {formatNumber(input)}</span>
        <span className="llm-token-bar-total">{formatNumber(total)}</span>
        <span className="llm-token-bar-output-label">Out: {formatNumber(output)}</span>
      </div>
    </div>
  );
}

export function LatencyBar({ latencyMs }: { latencyMs: number | null | undefined }) {
  if (latencyMs === null || latencyMs === undefined) return null;
  const percent = Math.min((latencyMs / LLM_TRACE_LATENCY_BAR_MAX_MS) * 100, 100);
  let colorClass = 'llm-latency-fast';
  if (latencyMs > LLM_TRACE_LATENCY_SLOW_THRESHOLD_MS) colorClass = 'llm-latency-slow';
  else if (latencyMs > LLM_TRACE_LATENCY_MEDIUM_THRESHOLD_MS) colorClass = 'llm-latency-medium';

  return (
    <div className="llm-latency-bar">
      <div className="llm-latency-track">
        <div className={`llm-latency-fill ${colorClass}`} style={{ width: `${percent}%` }} />
      </div>
      <span className="llm-latency-value">{formatLatency(latencyMs)}</span>
    </div>
  );
}

export function CodeBlock({
  title,
  content,
  open = false,
  language = 'json',
}: {
  title: string;
  content: string | undefined;
  open?: boolean;
  language?: string;
}) {
  const { isCopied, triggerCopyFeedback } = useCopyFeedback();

  const handleCopy = async () => {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      triggerCopyFeedback();
    } catch {
      // Clipboard access is best effort in local operator pages.
    }
  };

  return (
    <details className="llm-code-panel" open={open}>
      <summary className="llm-code-panel-header">
        <span className="llm-code-panel-title">{title}</span>
        <span className="llm-code-panel-lang">{language}</span>
        <button
          className="llm-code-panel-copy"
          type="button"
          onClick={(event) => {
            event.preventDefault();
            void handleCopy();
          }}
        >
          {isCopied ? '已复制' : '复制'}
        </button>
      </summary>
      <pre className={`llm-code-block language-${language}`}>
        <code>{content || '暂无内容'}</code>
      </pre>
    </details>
  );
}

export function MessageCard({ message, reasoningContent }: MessageCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const { isCopied, triggerCopyFeedback } = useCopyFeedback();

  const handleCopy = async () => {
    if (!message.content_text) return;
    try {
      await navigator.clipboard.writeText(message.content_text);
      triggerCopyFeedback();
    } catch {
      // Clipboard access is best effort in local operator pages.
    }
  };

  const roleLabel = LLM_TRACE_MESSAGE_ROLE_LABELS[message.role as keyof typeof LLM_TRACE_MESSAGE_ROLE_LABELS] ?? message.role;

  return (
    <article className="llm-message-card">
      <div className="llm-message-header">
        <button
          className="llm-message-toggle"
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <span className={`llm-message-chevron ${isExpanded ? 'expanded' : ''}`}>▶</span>
          <strong>{roleLabel}</strong>
        </button>
        <div className="llm-message-actions">
          <span className="soft-pill">#{message.index}</span>
          <button
            className="llm-message-copy"
            type="button"
            onClick={() => void handleCopy()}
          >
            {isCopied ? '已复制' : '复制'}
          </button>
        </div>
      </div>
      {isExpanded && (
        <div className="llm-message-content">
          {reasoningContent && message.role === 'assistant' && (
            <div className="llm-reasoning-block">
              <div className="llm-reasoning-label">推理过程 (reasoning_content)</div>
              <pre className="llm-reasoning-content">{reasoningContent}</pre>
            </div>
          )}
          <pre className="llm-code-block"><code>{message.content_text || ''}</code></pre>
        </div>
      )}
    </article>
  );
}
