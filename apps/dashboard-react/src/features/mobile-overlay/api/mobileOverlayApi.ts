import type { OverlayAnalyzeRequest, OverlayAnalyzeResponse, OverlayHealthzResponse } from '../types/mobileOverlay';
import {
  overlayAnalyzeResponseSchema,
  overlayHealthzResponseSchema,
} from './mobileOverlaySchemas';
import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';

export async function fetchOverlayHealthz(signal?: AbortSignal): Promise<OverlayHealthzResponse> {
  return overlayHealthzResponseSchema.parse(
    await fetchJson(dashboardApiUrl('/api/mobile-overlay/healthz'), {
      errorPrefix: '/api/mobile-overlay/healthz',
      signal,
    }),
  );
}

export async function postOverlayAnalyze(
  payload: OverlayAnalyzeRequest,
  signal?: AbortSignal,
): Promise<OverlayAnalyzeResponse> {
  return overlayAnalyzeResponseSchema.parse(
    await fetchJson(dashboardApiUrl('/api/mobile-overlay/analyze'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      errorPrefix: '/api/mobile-overlay/analyze',
      signal,
    }),
  );
}

export function overlayHealthzQueryKey() {
  return ['mobile-overlay', 'healthz'] as const;
}