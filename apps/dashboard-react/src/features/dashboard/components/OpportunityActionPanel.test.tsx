import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { OpportunityActionPanel } from './OpportunityActionPanel';
import { DEFAULT_QUERY_STATE } from '../lib/urlState';
import type { QueryState } from '../types/dashboard';
import type { BuyWorkbench } from '../../buy/types/buy';

const query: QueryState = {
  ...DEFAULT_QUERY_STATE,
  categoryCode: 'apple_computer',
  productLabel: 'MacBook Pro / M5',
  specLabel: '16G / 512G',
  pricingScope: 'actionable',
  pricingFreshnessDays: '30',
};

const workbench: BuyWorkbench = {
  categoryCode: 'apple_computer',
  summary: {
    opportunityCount: 12,
    baselineCount: 48,
    watchTargetCount: 6,
    todayOpportunityCount: 4,
    alertHitRate: 0.72,
    alertCount: 18,
    alertHitCount: 13,
    feedbackCount: 9,
    acceptCount: 5,
    rejectCount: 2,
    calibrationRecommendationCount: 3,
  },
  opportunities: [
    {
      id: 'opp-1',
      itemIdRef: 'item-1',
      title: 'MacBook Pro M5 Pro 16G 512G',
      itemId: 'item-1',
      listingUrl: 'https://example.com/item-1',
      region: '上海',
      status: 'OPEN',
      decision: null,
      currentPrice: 6999,
      fairPrice: 7600,
      buyCeiling: 7200,
      discountRate: 0.08,
      opportunityScore: 68,
      riskScore: 12,
      exactSpecReady: true,
      specConfidence: 0.94,
      baselineMatchLevel: 'exact',
      baselineMatchKey: 'mbp-m5-16-512',
      lastDetectedAt: '2026-04-23T00:00:00Z',
      explanation: {
        readinessSummary: '低于买入线，可以先联系再核对成色。',
        reviewGateSummary: '通过',
        specGateSummary: '通过',
        missingRequiredFields: [],
        confidenceSummary: '高置信',
        reliabilityScore: 92,
      },
      specContract: {
        status: 'complete',
      },
    },
  ],
  baselines: [],
  watchTargets: [],
  feedbackQuality: {
    feedbackCount: 9,
    opportunityCount: 12,
  },
  feedbackCalibration: {
    windowDays: 30,
    recommendations: {
      totalRecommendationCount: 3,
    },
  },
};

describe('OpportunityActionPanel', () => {
  it('keeps buy queue and evidence links anchored to the current workspace query', () => {
    render(
      <MemoryRouter>
        <OpportunityActionPanel error={null} isLoading={false} query={query} workbench={workbench} />
      </MemoryRouter>,
    );

    const buyLink = screen.getByRole('link', { name: '打开机会队列' });
    const evidenceLink = screen.getByRole('link', { name: '看证据' });

    const buyUrl = new URL(buyLink.getAttribute('href') ?? '/', 'http://localhost');
    const evidenceUrl = new URL(evidenceLink.getAttribute('href') ?? '/', 'http://localhost');

    expect(screen.getByRole('heading', { name: '先处理今天最值得看的机会' })).toBeInTheDocument();
    expect(screen.getByText('低于买入线，可以先联系再核对成色。')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(buyUrl.pathname).toBe('/');
    expect(evidenceUrl.pathname).toBe('/items/item-1');

    [buyUrl, evidenceUrl].forEach((url) => {
      expect(url.searchParams.get('category_code')).toBe('apple_computer');
      expect(url.searchParams.get('product_label')).toBe('MacBook Pro / M5');
      expect(url.searchParams.get('spec_label')).toBe('16G / 512G');
      expect(url.searchParams.get('pricing_scope')).toBe('actionable');
      expect(url.searchParams.get('pricing_freshness_days')).toBe('30');
    });
  });
});
