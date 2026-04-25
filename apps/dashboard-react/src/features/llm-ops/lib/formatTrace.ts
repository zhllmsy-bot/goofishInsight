import { formatNumber } from '../../dashboard/lib/formatters';
import { LLM_TRACE_LATENCY_SECONDS_THRESHOLD_MS } from './constants';

export type TokenUsage = {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
};

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < LLM_TRACE_LATENCY_SECONDS_THRESHOLD_MS) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatTokens(usage: TokenUsage | null | undefined): string {
  if (!usage) return '-';
  const input = usage.input_tokens ?? 0;
  const output = usage.output_tokens ?? 0;
  if (input === 0 && output === 0) return '-';
  return `${formatNumber(input)} -> ${formatNumber(output)}`;
}
