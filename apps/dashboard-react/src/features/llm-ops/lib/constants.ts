export const LLM_TRACE_COPY_FEEDBACK_DURATION_MS = 2000;
export const LLM_TRACE_TOKEN_BAR_MAX_TOKENS = 8000;
export const LLM_TRACE_LATENCY_BAR_MAX_MS = 10000;
export const LLM_TRACE_LATENCY_SECONDS_THRESHOLD_MS = 1000;
export const LLM_TRACE_LATENCY_MEDIUM_THRESHOLD_MS = 1000;
export const LLM_TRACE_LATENCY_SLOW_THRESHOLD_MS = 3000;

export const LLM_TRACE_MESSAGE_ROLE_LABELS = {
  system: 'System Prompt',
  user: 'User Prompt',
  assistant: 'Assistant Response',
} as const;
