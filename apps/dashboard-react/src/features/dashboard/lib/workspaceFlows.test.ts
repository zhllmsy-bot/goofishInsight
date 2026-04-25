import { describe, expect, it } from 'vitest';

import { buildWorkspaceLocation, buildWorkspacePath, buildWorkspaceSearch, readInitialQuery } from './urlState';

describe('workspace flow contracts', () => {
  it('preserves dashboard selection across buy workbench round-trip', () => {
    const query = readInitialQuery(
      '?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );

    const buyTarget = buildWorkspaceLocation('/buy/opportunities', query);
    const backToDashboard = buildWorkspacePath('/', query);

    expect(buyTarget.pathname).toBe('/buy/opportunities');
    expect(buyTarget.search).toContain('category_code=apple_computer');
    expect(buyTarget.search).toContain('product_label=MacBook+Pro+%2F+M5');
    expect(buyTarget.search).toContain('spec_label=16G+%2F+512G');

    expect(backToDashboard).toBe(
      '/?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );
  });

  it('preserves dashboard selection across runtime round-trip', () => {
    const query = readInitialQuery(
      '?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );

    const runtimeSearch = buildWorkspaceSearch(query);
    const runtimeTarget = buildWorkspacePath('/runtime', query);
    const backToDashboard = buildWorkspaceLocation('/', query);

    expect(runtimeSearch).toBe(
      '?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );
    expect(runtimeTarget).toBe(
      '/runtime?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );
    expect(backToDashboard).toEqual({
      pathname: '/',
      search:
        '?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    });
  });

  it('preserves dashboard selection across item detail round-trip', () => {
    const query = readInitialQuery(
      '?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );

    const itemDetailTarget = buildWorkspacePath('/items/abc123', query);
    const backToDashboard = buildWorkspacePath('/', query);

    expect(itemDetailTarget).toBe(
      '/items/abc123?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );
    expect(backToDashboard).toBe(
      '/?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );
  });

  it('preserves dashboard selection across onboarding round-trip', () => {
    const query = readInitialQuery(
      '?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );

    const onboardingTarget = buildWorkspacePath('/onboarding/xianyu', query);
    const queueTarget = buildWorkspacePath('/onboarding/xianyu/queue', query);
    const draftTarget = buildWorkspacePath('/onboarding/xianyu/draft', query);
    const backToDashboard = buildWorkspacePath('/', query);

    expect(onboardingTarget).toBe(
      '/onboarding/xianyu?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );
    expect(queueTarget).toBe(
      '/onboarding/xianyu/queue?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );
    expect(draftTarget).toBe(
      '/onboarding/xianyu/draft?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );
    expect(backToDashboard).toBe(
      '/?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );
  });

  it('builds consistent workspace search string for BFF mode compatibility', () => {
    const query = readInitialQuery(
      '?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );

    const searchString = buildWorkspaceSearch(query);

    expect(searchString).toBe(
      '?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );
  });
});
