import { useNavigate } from 'react-router-dom';

import { DashboardSidebar } from './DashboardSidebar';
import { DashboardSkeleton } from './DashboardQuickJump';
import { FocusPanel } from './FocusPanel';
import { ListingsPanel } from './ListingsPanel';
import { OpportunityActionPanel } from './OpportunityActionPanel';
import { PricingPanel } from './PricingPanel';
import { ReferencePanel } from './ReferencePanel';
import { SelectionPanel } from './SelectionPanel';
import { TerminalScreen } from '../../../shared/components/TerminalScreen';
import { useDashboardDerivedState, useDashboardPrimaryState, useDashboardReferenceState, useDashboardUrlSync } from '../hooks/useDashboardData';
import { useDashboardStateGuards } from '../hooks/useDashboardStateGuards';
import { categoryLabel, formatNumber, formatRelative } from '../lib/formatters';
import { resetTemplateQueryFilters, updateTemplateQueryValue } from '../lib/selectors';
import { buildWorkspaceLocation } from '../lib/urlState';
import { useDashboardUiStore } from '../store/dashboardUiStore';
import { useBuyWorkbench } from '../../buy/hooks/useBuyWorkbench';
import { useRuntimeControlState } from '../../runtime/hooks/useRuntimeData';
import { deriveRuntimeSummary } from '../../runtime/lib/runtimeViewModel';

import '../styles/dashboard.css';

export function DashboardPage() {
  const navigate = useNavigate();
  const query = useDashboardUiStore((state) => state.query);
  const referenceTab = useDashboardUiStore((state) => state.referenceTab);
  const setQuery = useDashboardUiStore((state) => state.setQuery);
  const setReferenceTab = useDashboardUiStore((state) => state.setReferenceTab);

  useDashboardUrlSync(query);

  const primaryState = useDashboardPrimaryState(query);
  const referenceState = useDashboardReferenceState(query);
  const buyWorkbenchState = useBuyWorkbench(query.categoryCode, 6);
  const { runtime } = useRuntimeControlState();
  const { productField, specField, templateFields, pricingRow, listingGroups } = useDashboardDerivedState(primaryState);
  const showInitialSkeleton = primaryState.loading && !primaryState.filters && !primaryState.pricing;
  const overview = primaryState.hero?.overview;
  const activeListingCount = overview?.active_items ?? referenceState.insights?.overview?.active_items;
  const sellerCount = referenceState.insights?.overview?.total_sellers;
  const visibleListingCount = primaryState.items?.items?.length ?? 0;
  const focusCount = (primaryState.focus?.market_focus_cards ?? []).filter((card) => !card.empty).length;
  const opportunityCount = listingGroups.reduce(
    (count, group) => count + (group.key === 'buy' || group.key === 'watch' ? group.rows.length : 0),
    0,
  );
  const hasSelectedCombination = Boolean(query.productLabel);
  const showPricingFirst = Boolean(pricingRow);
  const showCategoryFocus = !hasSelectedCombination && focusCount > 0;
  const runtimeTarget = buildWorkspaceLocation('/runtime', query);
  const runtimeSummary = deriveRuntimeSummary(runtime);
  void runtimeSummary;
  const selectedScopeLabel = query.productLabel
    ? query.specLabel
      ? `${query.productLabel} / ${query.specLabel}`
      : query.productLabel
    : '';
  const selectionTitle = selectedScopeLabel || categoryLabel(query.categoryCode);
  const selectionSubtitle = hasSelectedCombination
    ? query.specLabel
      ? `${query.specLabel} / 最近刷新 ${formatRelative(overview?.latest_seen)} / 作为机会解释层使用`
      : `当前选中组合 / 最近刷新 ${formatRelative(overview?.latest_seen)} / 作为机会解释层使用`
    : '先从上面的有效组合按钮里选一组“品类 + 核心参数”，下面的证据面才会围绕这组组合解释为什么机会成立或不成立。';
  const marketKpis = hasSelectedCombination
    ? [
        { label: '活跃挂牌', value: formatNumber(activeListingCount) },
        { label: '卖家覆盖', value: formatNumber(sellerCount) },
        { label: '当前列表', value: formatNumber(visibleListingCount) },
        { label: '机会/可谈', value: formatNumber(opportunityCount), tone: 'accent' as const },
      ]
    : [
        { label: '有效组合', value: formatNumber(productField?.options?.length ?? 0) },
        { label: '当前品类', value: categoryLabel(query.categoryCode) },
        { label: '最近刷新', value: formatRelative(overview?.latest_seen) },
        { label: '跨型号方向', value: formatNumber(focusCount), tone: 'accent' as const },
      ];

  useDashboardStateGuards({
    filters: primaryState.filters,
    query,
    setQuery,
  });

  return (
    <TerminalScreen>
      <div className="app-shell">
        <DashboardSidebar
          availableCategories={primaryState.filters?.available_categories ?? []}
          hero={primaryState.hero}
          query={query}
          runtimeSummary={runtimeSummary}
          onCategorySelect={(categoryCode) =>
            setQuery((previous) => ({
              ...resetTemplateQueryFilters(previous),
              categoryCode,
              productLabel: '',
              specLabel: '',
            }))
          }
          onPricingScopeChange={(pricingScope) =>
            setQuery((previous) => ({
              ...previous,
              pricingScope,
            }))
          }
          onResetSelection={() =>
            setQuery((previous) => ({
              ...resetTemplateQueryFilters(previous),
              productLabel: '',
              specLabel: '',
            }))
          }
        />

        <main className="workspace">
          <div className="workspace-scroll">
            {primaryState.error ? <div className="error-banner">{primaryState.error}</div> : null}

            {runtimeSummary.attentionCount > 0 ? (
              <button
                className="runtime-health-banner"
                type="button"
                onClick={() => navigate(runtimeTarget)}
              >
                <span className="runtime-health-dot" />
                {runtimeSummary.stoppedCount > 0
                  ? `${runtimeSummary.stoppedCount} 条常驻链路已停止`
                  : `${runtimeSummary.degradedCount} 条常驻链路部分可用`}
                <span className="runtime-health-action">去运行控制台处理 →</span>
              </button>
            ) : null}

            {showInitialSkeleton ? (
              <DashboardSkeleton />
            ) : (
              <>
                <OpportunityActionPanel
                  error={buyWorkbenchState.error}
                  isLoading={buyWorkbenchState.isLoading}
                  query={query}
                  workbench={buyWorkbenchState.workbench}
                />

                <SelectionPanel
                  productOptions={productField?.options ?? []}
                  query={query}
                  specOptions={specField?.options ?? []}
                  templateFields={templateFields}
                  onProductSelect={(productLabel) =>
                    setQuery((previous) => ({
                      ...resetTemplateQueryFilters(previous),
                      productLabel,
                      specLabel: '',
                    }))
                  }
                  onSpecSelect={(specLabel) =>
                    setQuery((previous) => ({
                      ...previous,
                      specLabel,
                    }))
                  }
                  onTemplateFilterSelect={(filterKey, value) =>
                    setQuery((previous) => updateTemplateQueryValue(previous, filterKey, value))
                  }
                />

                <section className="market-overview-panel">
                  <div>
                    <p className="eyebrow">Evidence Workspace</p>
                    <h2>{selectionTitle}</h2>
                    <p className="panel-subtitle">{selectionSubtitle}</p>
                  </div>
                  <div className="market-kpi-row" aria-label="当前市场概览">
                    {marketKpis.map((kpi) => (
                      <div className={`market-kpi ${kpi.tone === 'accent' ? 'is-accent' : ''}`} key={kpi.label}>
                        <span>{kpi.label}</span>
                        <strong>{kpi.value}</strong>
                      </div>
                    ))}
                  </div>
                </section>

                {hasSelectedCombination ? (
                  <>
                    {showPricingFirst ? (
                      <>
                        <PricingPanel
                          itemPrices={primaryState.items?.items?.map((item) => item.price) ?? []}
                          pricing={primaryState.pricing}
                          pricingRow={pricingRow}
                          pricingScope={query.pricingScope}
                          onPricingScopeChange={(pricingScope) =>
                            setQuery((previous) => ({
                              ...previous,
                              pricingScope,
                            }))
                          }
                        />
                        <ListingsPanel
                          compact={false}
                          listingGroups={listingGroups}
                          pricing={primaryState.pricing}
                          pricingRow={pricingRow}
                          selectedProductLabel={selectedScopeLabel}
                          onOpenRuntime={() => navigate(runtimeTarget)}
                        />
                      </>
                    ) : (
                      <>
                        <ListingsPanel
                          compact={false}
                          listingGroups={listingGroups}
                          pricing={primaryState.pricing}
                          pricingRow={pricingRow}
                          selectedProductLabel={selectedScopeLabel}
                          onOpenRuntime={() => navigate(runtimeTarget)}
                        />
                        <PricingPanel
                          itemPrices={primaryState.items?.items?.map((item) => item.price) ?? []}
                          pricing={primaryState.pricing}
                          pricingRow={pricingRow}
                          pricingScope={query.pricingScope}
                          onPricingScopeChange={(pricingScope) =>
                            setQuery((previous) => ({
                              ...previous,
                              pricingScope,
                            }))
                          }
                        />
                      </>
                    )}
                    <FocusPanel cards={primaryState.focus?.market_focus_cards ?? []} />
                    <ReferencePanel
                      calibration={referenceState.calibration}
                      insights={referenceState.insights}
                      pricing={primaryState.pricing}
                      query={query}
                      referenceTab={referenceTab}
                      onReferenceTabChange={setReferenceTab}
                    />
                  </>
                ) : showCategoryFocus ? (
                  <FocusPanel cards={primaryState.focus?.market_focus_cards ?? []} variant="compact" />
                ) : null}
              </>
            )}
          </div>
        </main>
      </div>
    </TerminalScreen>
  );
}
