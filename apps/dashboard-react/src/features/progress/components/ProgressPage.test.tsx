import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderDashboardApp } from '../../../test/renderApp';
import { requestUrl } from '../../../test/fetchMock';

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ProgressPage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('keeps workspace query and renders progress data inside React shell', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      expect(url.searchParams.get('category_code')).toBe('garmin_watch');
      expect(url.searchParams.get('product_label')).toBe('Fenix 7 Pro');
      expect(url.searchParams.get('spec_label')).toBe('47mm');

      if (url.pathname === '/api/progress/sections/header') {
        return jsonResponse({
          selected_category_code: 'garmin_watch',
          available_categories: ['garmin_watch'],
          review_overview: {
            domain_count: 1,
            reviewed_total: 12,
            review_target_total: 20,
            completion_percent: 60,
            last_reviewed_at: '2026-04-19T01:00:00Z',
          },
          current_ai_provider: 'openai',
          current_ai_model: 'gpt-5.4',
        });
      }
      if (url.pathname === '/api/progress/sections/overview') {
        return jsonResponse({
          review_overview: {
            domain_count: 1,
            pending_review_count: 3,
            in_progress_count: 2,
            pending_audit_count: 1,
            reviewed_valid_count: 10,
            reviewed_invalid_count: 2,
            reviewed_total: 12,
            review_target_total: 20,
            completion_percent: 60,
            last_reviewed_at: '2026-04-19T01:00:00Z',
          },
          review_progress_rows: [
            {
              business_domain: 'garmin_watch',
              label: 'Garmin 手表',
              active_items: 30,
              total_items: 50,
              pending_review_count: 3,
              in_progress_count: 2,
              pending_audit_count: 1,
              reviewed_valid_count: 10,
              reviewed_invalid_count: 2,
              completion_percent: 60,
              last_reviewed_at: '2026-04-19T01:00:00Z',
            },
          ],
        });
      }
      if (url.pathname === '/api/progress/sections/usage-workers') {
        return jsonResponse({
          usage_summary: {
            file_count: 2,
            request_count: 9,
            total_tokens: 8000,
            input_tokens: 5000,
            output_tokens: 3000,
            recent_usage_runs: [],
          },
          worker_runs: [],
        });
      }
      if (url.pathname === '/api/progress/sections/audits') {
        return jsonResponse({
          audit_queue_rows: [],
          invalid_reason_rows: [],
        });
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp(
      '/progress?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );

    expect(screen.getByRole('button', { name: '打开运行控制' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('回刷进度工作台')).toBeInTheDocument();
    });

    expect(screen.getByText('Garmin手表')).toBeInTheDocument();
    expect(screen.getByText('总体完成率')).toBeInTheDocument();
  });
});
