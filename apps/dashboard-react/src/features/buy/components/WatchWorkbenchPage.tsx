import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../shared/components/ui/tabs';
import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { useBuyBaselines, useBuyTargets } from '../hooks/useBuyWorkbench';
import type { BuyBaseline, BuyWatchTarget } from '../types/buy';

import '../../dashboard/styles/dashboard.css';
import '../styles/buy-workbench.css';

type WatchTab = 'targets' | 'baselines';

const TABS: Array<{ value: WatchTab; label: string; hint: string }> = [
  { value: 'targets', label: '关注目标', hint: '监控目标' },
  { value: 'baselines', label: '价格基线', hint: '历史买入与合理价参考' },
];

export function WatchWorkbenchPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const query = readInitialQuery(location.search);
  const categoryCode = query.categoryCode;
  const { watchTargets, error: watchError, isLoading: watchLoading, isRefreshing: isTargetsRefreshing } = useBuyTargets(categoryCode, 200);
  const { baselines, error: baselineError, isLoading: baselinesLoading, isRefreshing: isBaselinesRefreshing } = useBuyBaselines(categoryCode, 200);
  const [activeTab, setActiveTab] = useState<WatchTab>('targets');

  const opportunityTarget = useMemo(() => buildWorkspaceLocation('/', query), [query]);
  const marketTarget = useMemo(() => buildWorkspaceLocation('/market', query), [query]);
  const runtimeTarget = useMemo(() => buildWorkspaceLocation('/ops/runtime', query), [query]);

  const watchSummary = watchTargets?.summary;
  const targetRows = watchTargets?.watchTargets ?? [];
  const baselineSummary = baselines?.summary;
  const baselineRows: BuyBaseline[] = baselines?.baselines ?? [];

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack buy-workbench-page">
            <PageHero
              eyebrow="Watch & Baseline"
              title="关注与基线管理"
              description="把目标清单和价格基线放在同一入口里维护，支持按类目快速回到机会决策台，避免切分裂。"
              meta={
                <>
                  <span className="soft-pill">{formatNumber(watchSummary?.watchTargetCount)} 个关注目标</span>
                  <span className="soft-pill is-accent">{formatNumber(watchSummary?.activeWatchTargetCount)} 个生效中</span>
                  <span className="soft-pill">{formatNumber(baselineSummary?.baselineCount)} 条基线</span>
                </>
              }
            >
              <Link className="nav-pill" to={opportunityTarget}>
                回机会台
              </Link>
              <Link className="nav-pill" to={marketTarget}>
                回市场大盘
              </Link>
              <button
                className="nav-pill"
                type="button"
                onClick={() => {
                  void navigate(runtimeTarget);
                }}
              >
                打开运行后台
              </button>
              {watchSummary ? <span className="soft-pill">目标 {formatNumber(watchSummary?.watchTargetCount)}</span> : null}
              {isTargetsRefreshing || isBaselinesRefreshing ? <span className="soft-pill">正在刷新</span> : null}
            </PageHero>

            {watchError ? <div className="error-banner">{watchError}</div> : null}
            {baselineError ? <div className="error-banner">{baselineError}</div> : null}

            <Tabs className="panel" onValueChange={(value) => setActiveTab(value as WatchTab)} value={activeTab}>
              <TabsList>
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value} className="soft-pill">
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="targets">
                {watchLoading && !watchTargets ? (
                  <section className="panel">
                    <p className="eyebrow">Watch Targets</p>
                    <h2>正在加载目标配置...</h2>
                    <p className="panel-subtitle">加载后会显示目标状态、预算上限和风控参数，优先支持可直接匹配的 ACTIVE 目标。</p>
                  </section>
                ) : null}

                <section className="panel buy-side-panel">
                  <div className="buy-panel-header panel-header">
                    <div>
                      <p className="eyebrow">Watch Target Pool</p>
                      <h2>{TABS[0].hint}</h2>
                      <p className="panel-subtitle">默认目标会在机会生成时自动补齐，建议按预算和地区建立补充目标。</p>
                    </div>
                    <span className="soft-pill">共 {formatNumber(targetRows.length)} 条</span>
                  </div>

                  {targetRows.length ? (
                    <div className="buy-opportunity-list">
                      {targetRows.map((target: BuyWatchTarget) => (
                        <article className="buy-opportunity-card" key={target.id}>
                          <div className="buy-opportunity-head">
                            <div>
                              <h3>{target.targetName}</h3>
                              <p className="panel-subtitle">
                                {target.profileKey ?? '-'} · {target.status ?? '-'} · 冷却 {formatNumber(target.notifyCooldownMinutes)}m
                              </p>
                            </div>
                            <div className="buy-score-pair">
                              <span className="soft-pill is-accent">风控 {target.riskTolerance ?? '-'}</span>
                              <span className="soft-pill">配置 {target.desiredRegion ?? '-'}</span>
                            </div>
                          </div>

                          <div className="mini-card">
                            <strong>预算上限：{formatCurrency(target.budgetCeiling)}</strong>
                            <small>内存：{formatNumber(target.desiredMemoryGb)} GB · 存储：{formatNumber(target.desiredStorageGb)} GB</small>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="buy-empty-state">当前暂无目标。运行机会任务时会自动创建默认目标。</p>
                  )}
                </section>
              </TabsContent>

              <TabsContent value="baselines">
                {baselinesLoading && !baselines ? (
                  <section className="panel">
                    <p className="eyebrow">Price Baselines</p>
                    <h2>正在加载价格基线...</h2>
                    <p className="panel-subtitle">加载后会显示 baseline key、样本规模、置信度和参考区间。</p>
                  </section>
                ) : null}

                <section className="panel buy-side-panel">
                  <div className="buy-panel-header panel-header">
                    <div>
                      <p className="eyebrow">Baseline Library</p>
                      <h2>{TABS[1].hint}</h2>
                      <p className="panel-subtitle">当前展示最新 {formatNumber(baselineSummary?.baselineCount)} 条基线。</p>
                    </div>
                    <span className="soft-pill">共 {formatNumber(baselineRows.length)} 条</span>
                  </div>

                  {baselineRows.length ? (
                    baselineRows.map((baseline: BuyBaseline) => (
                      <article className="mini-card" key={baseline.id}>
                        <strong>{baseline.baselineKey}</strong>
                        <small>fair {formatCurrency(baseline.fairPrice)} · buy {formatCurrency(baseline.buyCeiling)} · n={formatNumber(baseline.sampleSize)}</small>
                        <small>置信度 {Math.round((baseline.confidence ?? 0) * 100)}%</small>
                        <small>{baseline.explanation?.readinessSummary ?? '-'}</small>
                      </article>
                    ))
                  ) : (
                    <p className="buy-empty-state">当前没有基线。先从运行后台执行 build-buy-baselines。</p>
                  )}
                </section>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </main>
    </AppFrame>
  );
}
