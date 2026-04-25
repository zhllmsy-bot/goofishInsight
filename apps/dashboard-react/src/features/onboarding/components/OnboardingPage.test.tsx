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

describe('OnboardingPage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('renders onboarding workspace inside React shell and keeps workspace query', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/onboarding/xianyu/coverage') {
        return jsonResponse({
          counts: {
            totalItems: 12,
            itemsWithCurrentRawResponse: 10,
            backfillCandidateItems: 4,
          },
          coverage: {
            rawSignalCoverageRatio: 0.625,
          },
          filters: {
            sourceKeyword: 'fenix 8',
          },
        });
      }

      if (url.pathname === '/api/onboarding/xianyu/queue') {
        return jsonResponse({
          total: 1,
          items: [
            {
              id: 'queue-1',
              matchKey: 'C_CAT:126854525',
              status: 'PENDING',
              xianyuCCatId: '126854525',
              itemCountSnapshot: 5,
              sampleTitles: ['Garmin Fenix 8 Sapphire'],
              businessDomains: ['garmin_watch'],
              updatedAt: '2026-04-19T01:00:00Z',
              ownerOperatorId: 'alice',
              metadata: {
                candidateMatchKeys: ['CAT_TB:50025387:50014945'],
              },
              resolvedMapping: {
                categoryCode: 'garmin_watch',
              },
            },
          ],
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp(
      '/onboarding/xianyu?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '闲鱼品类开通工作台' })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getAllByText('Garmin Fenix 8 Sapphire').length).toBeGreaterThan(0);
    });

    expect(screen.getByRole('link', { name: '返回看板' })).toHaveAttribute(
      'href',
      expect.stringContaining('product_label=Fenix+7+Pro'),
    );
    expect(screen.getAllByText('C_CAT:126854525').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Garmin Fenix 8 Sapphire').length).toBeGreaterThan(0);
  });

  it('renders queue items with status and detail panel', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/onboarding/xianyu/coverage') {
        return jsonResponse({
          counts: { totalItems: 5, itemsWithCurrentRawResponse: 3, backfillCandidateItems: 1 },
          coverage: { rawSignalCoverageRatio: 0.6 },
          filters: {},
        });
      }

      if (url.pathname === '/api/onboarding/xianyu/queue') {
        return jsonResponse({
          total: 2,
          items: [
            {
              id: 'queue-1',
              matchKey: 'C_CAT:126854525',
              status: 'PENDING',
              xianyuCCatId: '126854525',
              itemCountSnapshot: 5,
              sampleTitles: ['Garmin Fenix 8 Sapphire'],
              businessDomains: ['garmin_watch'],
              updatedAt: '2026-04-19T01:00:00Z',
              ownerOperatorId: 'alice',
              metadata: { candidateMatchKeys: ['CAT_TB:50025387:50014945'] },
              resolvedMapping: { categoryCode: 'garmin_watch' },
            },
            {
              id: 'queue-2',
              matchKey: 'C_CAT:999999999',
              status: 'IN_PROGRESS',
              xianyuCCatId: '999999999',
              itemCountSnapshot: 3,
              sampleTitles: ['MacBook Pro M5 16G'],
              businessDomains: ['apple_computer'],
              updatedAt: '2026-04-19T02:00:00Z',
              ownerOperatorId: 'bob',
              metadata: {},
              resolvedMapping: null,
            },
          ],
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/onboarding/xianyu');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '闲鱼品类开通工作台' })).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText('2 项')).toBeInTheDocument();
    });

    expect(screen.getAllByText('PENDING').length).toBeGreaterThan(0);
    expect(screen.getAllByText('IN_PROGRESS').length).toBeGreaterThan(0);
  });

  it('renders draft editor after generating draft from queue item', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/onboarding/xianyu/coverage') {
        return jsonResponse({
          counts: { totalItems: 5, itemsWithCurrentRawResponse: 3, backfillCandidateItems: 1 },
          coverage: { rawSignalCoverageRatio: 0.6 },
          filters: {},
        });
      }

      if (url.pathname === '/api/onboarding/xianyu/queue') {
        return jsonResponse({
          total: 1,
          items: [
            {
              id: 'queue-1',
              matchKey: 'C_CAT:126854525',
              status: 'PENDING',
              xianyuCCatId: '126854525',
              xianyuCatId: '50025387',
              xianyuTbCatId: '50014945',
              itemCountSnapshot: 5,
              sampleTitles: ['Garmin Fenix 8 Sapphire'],
              businessDomains: ['garmin_watch'],
              updatedAt: '2026-04-19T01:00:00Z',
              ownerOperatorId: 'alice',
              metadata: { candidateMatchKeys: ['CAT_TB:50025387:50014945'] },
              resolvedMapping: { categoryCode: 'garmin_watch' },
            },
          ],
        });
      }

      if (url.pathname === '/api/onboarding/xianyu/draft') {
        return jsonResponse({
          selection: { xianyuCatId: '50025387', xianyuTbCatId: '50014945' },
          analysis: {
            sampleCount: 5,
            attributeObservations: [
              {
                attributeCode: 'display_type',
                attributeName: '屏幕类型',
                sampleValues: ['AMOLED', 'AMOLED', 'MIP'],
                selected: true,
              },
            ],
            selectedAttributeCodes: ['display_type'],
            categoryHints: [{ name: 'Garmin 手表', confidence: 0.9 }],
            sampleTitles: ['Garmin Fenix 8 Sapphire'],
          },
          payload: {
            requestId: 'req-draft-1',
            catalog: {
              category: { code: 'garmin_watch', name: 'Garmin 手表', path: '手表/Garmin', level: 2 },
              attributes: [],
              template: { version: 1, items: [] },
            },
            mappings: [{ matchScope: 'CAT_TB', xianyuCatId: '50025387', xianyuTbCatId: '50014945' }],
          },
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/onboarding/xianyu');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '闲鱼品类开通工作台' })).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText('C_CAT:126854525').length).toBeGreaterThan(0);
    });

    const draftButton = screen.getByRole('button', { name: '生成草稿' });
    expect(draftButton).toBeInTheDocument();
  });

  it('renders coverage metrics from API response', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/onboarding/xianyu/coverage') {
        return jsonResponse({
          counts: { totalItems: 100, itemsWithCurrentRawResponse: 80, backfillCandidateItems: 20 },
          coverage: { rawSignalCoverageRatio: 0.8 },
          filters: { sourceKeyword: 'fenix' },
        });
      }

      if (url.pathname === '/api/onboarding/xianyu/queue') {
        return jsonResponse({ total: 0, items: [] });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/onboarding/xianyu');

    await waitFor(() => {
      expect(screen.getByText('100')).toBeInTheDocument();
    });
    expect(screen.getByText('80')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });
});
