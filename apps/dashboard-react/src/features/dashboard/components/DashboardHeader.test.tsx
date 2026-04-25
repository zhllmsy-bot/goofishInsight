import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
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

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-probe">{location.pathname}{location.search}</output>;
}

describe('DashboardHeader', () => {
  afterEach(() => {
    resetDashboardStore();
    window.localStorage.clear();
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

    const todayOpportunityHref = readHref('前往今日机会');
    const marketHref = readHref('前往市场大盘');
    const watchHref = readHref('打开关注与基线');
    const opsHref = readHref('前往运维后台');
    const configHref = readHref('打开配置后台');

    expect(todayOpportunityHref.pathname).toBe('/');
    expect(marketHref.pathname).toBe('/market');
    expect(watchHref.pathname).toBe('/watch');
    expect(opsHref.pathname).toBe('/ops');
    expect(configHref.pathname).toBe('/config/categories');

    [todayOpportunityHref, marketHref, watchHref, opsHref, configHref].forEach((href) => {
      expect(href.searchParams.get('category_code')).toBe('garmin_watch');
      expect(href.searchParams.get('product_label')).toBe('Fenix 7 Pro');
      expect(href.searchParams.get('spec_label')).toBe('47mm');
      expect(href.searchParams.get('pricing_scope')).toBe('actionable');
      expect(href.searchParams.get('pricing_freshness_days')).toBe('60');
    });
  });

  it('opens global search dialog and jumps by typed id', () => {
    render(
      <MemoryRouter initialEntries={['/market?category_code=apple_computer&product_label=MacBook']}>
        <Routes>
          <Route
            element={
              <>
                <LocationProbe />
                <DashboardHeader />
              </>
            }
            path="*"
          />
        </Routes>
      </MemoryRouter>,
    );

    const searchButton = screen.getByRole('button', { name: '打开全局搜索' });
    fireEvent.click(searchButton);

    const input = screen.getByLabelText('输入关键字');
    fireEvent.change(input, {
      target: { value: 'opp-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '立即跳转' }));

    const location = screen.getByTestId('location-probe');
    expect(location.textContent).toContain('/opportunity/opp-1');
    expect(location.textContent).toContain('category_code=apple_computer');

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(screen.getByLabelText('输入关键字')).toBeInTheDocument();
  });

  it('cycles theme and persists in localStorage', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <DashboardHeader />
      </MemoryRouter>,
    );

    const themeButton = screen.getByRole('button', { name: '切换主题' });
    expect(document.documentElement.getAttribute('data-theme') ?? 'system').toBe('system');

    fireEvent.click(themeButton);
    expect(window.localStorage.getItem('goofish-theme-mode')).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    fireEvent.click(themeButton);
    expect(window.localStorage.getItem('goofish-theme-mode')).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('supports G-prefixed keyboard navigation', () => {
    act(() => {
      useDashboardUiStore.setState({
        query: {
          ...DEFAULT_QUERY_STATE,
          categoryCode: 'apple_computer',
        },
        referenceTab: 'trend',
      });
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            element={
              <>
                <LocationProbe />
                <DashboardHeader />
              </>
            }
            path="*"
          />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 'm' });
    expect(screen.getByTestId('location-probe').textContent).toContain('/market');
    expect(screen.getByTestId('location-probe').textContent).toContain('category_code=apple_computer');

    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 'c' });
    expect(screen.getByTestId('location-probe').textContent).toContain('/config/categories');

    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 'o' });
    expect(screen.getByTestId('location-probe').textContent).toContain('/?category_code=apple_computer');
  });
});
