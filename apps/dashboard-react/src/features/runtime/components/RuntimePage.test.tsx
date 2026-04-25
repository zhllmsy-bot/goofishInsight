import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderDashboardApp } from '../../../test/renderApp';
import { requestBodyText, requestUrl } from '../../../test/fetchMock';

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('RuntimePage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('preserves workspace filters and returns from runtime to dashboard', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/dashboard/runtime/status') {
        expect(url.searchParams.get('category_code')).toBe('garmin_watch');
        return jsonResponse({
          updatedAt: '2026-04-21T01:00:00Z',
          groups: [
            {
              key: 'home_feed',
              title: '首页采集',
              description: '附着浏览器首页流采集',
              status: 'running',
              checks: [{ label: 'CDP', ok: true, detail: 'ok' }],
              stats: [{ label: '最近刷新', value: '10s' }],
              actions: [{ action: 'restart', label: '重启', tone: 'warn' }],
            },
          ],
        });
      }

      if (url.pathname.startsWith('/api/dashboard/sections/')) {
        return jsonResponse({});
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp(
      '/runtime?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '本机常驻任务指挥台' })).toBeInTheDocument();
    });
    expect(screen.getByText('作用域 Garmin手表 (garmin_watch)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '← 回到交易工作台' }));

    await waitFor(() => {
      expect(window.location.pathname).toBe('/');
      expect(window.location.search).toContain('category_code=garmin_watch');
      expect(window.location.search).toContain('product_label=Fenix+7+Pro');
      expect(window.location.search).toContain('spec_label=47mm');
      expect(window.location.search).toContain('pricing_scope=actionable');
      expect(window.location.search).toContain('pricing_freshness_days=60');
    });
  });

  it('submits runtime buy jobs actions with the current category scope', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/dashboard/runtime/status') {
        return jsonResponse({
          updatedAt: '2026-04-21T01:00:00Z',
          groups: [
            {
              key: 'buy_jobs',
              title: 'Buy Jobs',
              description: '买方链路控制',
              status: 'running',
              checks: [{ label: '基线更新记录', ok: true, detail: 'ok' }],
              stats: [{ label: '类目作用域', value: 'Apple电脑 (apple_computer)' }],
              actions: [{ action: 'build-buy-baselines', label: '生成买方基线', tone: 'secondary' }],
            },
          ],
        });
      }

      if (url.pathname === '/api/dashboard/runtime/actions') {
        const body = JSON.parse(requestBodyText(init?.body)) as {
          target?: string;
          action?: string;
          categoryCode?: string;
        };
        expect(body.target).toBe('buy_jobs');
        expect(body.action).toBe('build-buy-baselines');
        expect(body.categoryCode).toBe('apple_computer');
        return jsonResponse({
          ok: true,
          target: 'buy_jobs',
          action: 'build-buy-baselines',
          actionResult: {
            action: 'build-buy-baselines',
            categoryCode: 'apple_computer',
            exit_code: 0,
            result: { baselineCount: 12 },
          },
          runtime: {
            updatedAt: '2026-04-21T01:01:00Z',
            groups: [
              {
                key: 'buy_jobs',
                title: 'Buy Jobs',
                description: '买方链路控制',
                status: 'running',
                checks: [{ label: '基线更新记录', ok: true, detail: 'ok' }],
                stats: [{ label: '类目作用域', value: 'Apple电脑 (apple_computer)' }],
                actions: [{ action: 'build-buy-baselines', label: '生成买方基线', tone: 'secondary' }],
              },
            ],
          },
        });
      }

      if (url.pathname.startsWith('/api/dashboard/sections/')) {
        return jsonResponse({});
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/runtime?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Buy Jobs 快捷动作：生成买方基线' })).toBeInTheDocument();
    });
    expect(screen.getByText('作用域 Apple电脑 (apple_computer)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Buy Jobs 快捷动作：生成买方基线' }));

    await waitFor(() => {
      expect(screen.getAllByText('生成买方基线 已提交，状态已刷新。').length).toBeGreaterThanOrEqual(1);
    });
  });
});
