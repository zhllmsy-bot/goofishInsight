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

describe('BuyOpportunityDetailPage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('shows outcome proof and ROI evidence when purchase feedback is available', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.pathname === '/api/buy/opportunities/opp-1') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          opportunity: {
            id: 'opp-1',
            title: 'MacBook Pro M5 Pro 16G 512G',
            itemId: 'xy-101',
            status: 'PURCHASED',
            decision: 'purchased',
            currentPrice: 6999,
            fairPrice: 7600,
            buyCeiling: 7200,
            opportunityScore: 82,
            riskScore: 9,
            firstDetectedAt: '2026-04-24T01:00:00+00:00',
            lastDetectedAt: '2026-04-24T02:00:00+00:00',
            explanation: {
              readinessSummary: '可以买',
              reviewGateSummary: '通过',
              specGateSummary: '通过',
            },
            matchedFieldValues: {},
            feedbackSummary: {
              feedbackAction: 'accept',
              feedbackLabel: 'purchased',
            },
          },
          outcomeProof: {
            alertEventCount: 1,
            openFeedbackCount: 1,
            contactFeedbackCount: 1,
            purchaseFeedbackCount: 1,
            hasOpenEvidence: true,
            hasPurchaseEvidence: true,
            hasRoiEvidence: true,
            purchasePrice: 6800,
            expectedResalePrice: 7600,
            estimatedProfit: 800,
            estimatedRoiRate: 0.1176,
          },
          risks: [],
          alertEvents: [],
          feedbackEntries: [],
          itemDetail: null,
        });
      }

      if (url.pathname === '/api/buy/feedback' && init?.method === 'POST') {
        return jsonResponse({
          opportunityId: 'opp-1',
          feedbackLabel: 'detail_opened',
          feedbackType: 'engagement',
          status: 'PURCHASED',
          decision: 'purchased',
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/opportunity/opp-1?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'MacBook Pro M5 Pro 16G 512G' })).toBeInTheDocument();
    });

    expect(screen.getByText(/提醒 1 · 打开 1 · 联系 1 · 成交 1/)).toBeInTheDocument();
    expect(screen.getByText(/买入价 ¥6,800 · 预估转售价 ¥7,600/)).toBeInTheDocument();
    expect(screen.getByText(/预估利润 ¥800 · ROI 11.8%/)).toBeInTheDocument();
    await waitFor(() => {
      const engagementCall = fetchMock.mock.calls.find(([, callInit]) => {
        if (callInit?.method !== 'POST') {
          return false;
        }
        const payload = JSON.parse(requestBodyText(callInit.body)) as Record<string, unknown>;
        return payload.feedbackType === 'engagement' && payload.feedbackLabel === 'detail_opened';
      });
      expect(engagementCall).toBeDefined();
    });
  });

  it('requires purchase outcome fields before marking an opportunity purchased', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.pathname === '/api/buy/opportunities/opp-1') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          opportunity: {
            id: 'opp-1',
            title: 'MacBook Pro M5 Pro 16G 512G',
            itemId: 'xy-101',
            status: 'OPEN',
            decision: null,
            currentPrice: 6999,
            fairPrice: 7600,
            buyCeiling: 7200,
            opportunityScore: 82,
            riskScore: 9,
            firstDetectedAt: '2026-04-24T01:00:00+00:00',
            lastDetectedAt: '2026-04-24T02:00:00+00:00',
            explanation: {
              readinessSummary: '可以买',
              reviewGateSummary: '通过',
              specGateSummary: '通过',
            },
            matchedFieldValues: {},
          },
          outcomeProof: {
            alertEventCount: 1,
            openFeedbackCount: 1,
            contactFeedbackCount: 0,
            purchaseFeedbackCount: 0,
            hasOpenEvidence: true,
            hasPurchaseEvidence: false,
            hasRoiEvidence: false,
          },
          risks: [],
          alertEvents: [],
          feedbackEntries: [],
          itemDetail: null,
        });
      }

      if (url.pathname === '/api/buy/feedback' && init?.method === 'POST') {
        const payload = JSON.parse(requestBodyText(init.body)) as Record<string, unknown>;
        if (payload.feedbackType === 'engagement') {
          return jsonResponse({
            opportunityId: 'opp-1',
            feedbackLabel: 'detail_opened',
            feedbackType: 'engagement',
            status: 'OPEN',
            decision: null,
          });
        }

        expect(payload).toMatchObject({
          opportunityId: 'opp-1',
          feedbackLabel: 'purchased',
          purchasePrice: '6900',
          expectedResalePrice: '7800',
          feedbackNote: '配件齐全，轻微划痕',
        });
        return jsonResponse({
          opportunityId: 'opp-1',
          feedbackLabel: 'purchased',
          feedbackType: 'decision',
          status: 'PURCHASED',
          decision: 'purchased',
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/opportunity/opp-1?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '已成交' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '已成交' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: '实际买入价' }), {
      target: { value: '6900' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: '预估转售价' }), {
      target: { value: '7800' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: '成交备注' }), {
      target: { value: '配件齐全，轻微划痕' },
    });

    expect(screen.getByText(/预估利润 ¥900 · ROI 13.0%/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认成交并记录 ROI' }));

    await waitFor(() => {
      expect(screen.getByText(/已回写成交：PURCHASED · purchased，ROI 证据已进入结果漏斗。/)).toBeInTheDocument();
    });
  });
});
