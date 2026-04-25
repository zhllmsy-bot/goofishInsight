import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { DashboardHeader } from './DashboardHeader';
import { DEFAULT_QUERY_STATE } from '../lib/urlState';
import { useDashboardUiStore } from '../store/dashboardUiStore';

function resetDashboardStore() {
  act(() => {
    useDashboardUiStore.setState({
      query: DEFAULT_QUERY_STATE,
      referenceTab: 'trend',
    });
  });
}

function readHref(label: string): URL {
  const link = screen.getByRole('link', { name: label });
  return new URL(link.getAttribute('href') ?? '/', 'http://localhost');
}

describe('DashboardHeader', () => {
  afterEach(() => {
    resetDashboardStore();
  });

  it('preserves workspace filters across internal routes', () => {
    act(() => {
      useDashboardUiStore.setState({
        query: {
          ...DEFAULT_QUERY_STATE,
          categoryCode: 'garmin_watch',
          productLabel: 'Fenix 7 Pro',
          specLabel: '47mm',
          pricingScope: 'actionable',
          pricingFreshnessDays: '60',
        },
        referenceTab: 'trend',
      });
    });

    render(
      <MemoryRouter initialEntries={['/runtime']}>
        <DashboardHeader />
      </MemoryRouter>,
    );

    const dashboardHref = readHref('前往证据看板');
    const runtimeHref = readHref('前往运行后台');
    const buyHref = readHref('打开机会队列');
    const buyTargetsHref = readHref('打开买入目标页');
    const buyBaselinesHref = readHref('打开价格基线页');
    const progressHref = readHref('打开回刷进度');
    const onboardingHref = readHref('打开品类开通');

    expect(dashboardHref.pathname).toBe('/');
    expect(runtimeHref.pathname).toBe('/runtime');
    expect(buyHref.pathname).toBe('/buy/opportunities');
    expect(buyTargetsHref.pathname).toBe('/buy/targets');
    expect(buyBaselinesHref.pathname).toBe('/buy/baselines');
    expect(progressHref.pathname).toBe('/progress');
    expect(onboardingHref.pathname).toBe('/onboarding/xianyu');

    [dashboardHref, runtimeHref, buyHref, buyTargetsHref, buyBaselinesHref, progressHref, onboardingHref].forEach((href) => {
      expect(href.searchParams.get('category_code')).toBe('garmin_watch');
      expect(href.searchParams.get('product_label')).toBe('Fenix 7 Pro');
      expect(href.searchParams.get('spec_label')).toBe('47mm');
      expect(href.searchParams.get('pricing_scope')).toBe('actionable');
      expect(href.searchParams.get('pricing_freshness_days')).toBe('60');
    });
  });
});
