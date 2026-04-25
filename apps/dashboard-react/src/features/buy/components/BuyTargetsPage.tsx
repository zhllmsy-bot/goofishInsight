import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMemo } from 'react';

import { TerminalScreen } from '../../../shared/components/TerminalScreen';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { useBuyTargets } from '../hooks/useBuyWorkbench';

import '../../dashboard/styles/dashboard.css';
import '../styles/buy-workbench.css';
import type { BuyWatchTarget } from '../types/buy';

export function BuyTargetsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const query = readInitialQuery(location.search);
  const categoryCode = query.categoryCode;
  const { watchTargets, error, isLoading, isRefreshing } = useBuyTargets(categoryCode, 200);
  const summary = watchTargets?.summary;
  const targets = watchTargets?.watchTargets ?? [];

  const opportunityTarget = useMemo(() => buildWorkspaceLocation('/buy/opportunities', query), [query]);
  const baselineTarget = useMemo(() => buildWorkspaceLocation('/buy/baselines', query), [query]);
  const dashboardTarget = useMemo(() => buildWorkspaceLocation('/', query), [query]);
  const runtimeTarget = useMemo(() => buildWorkspaceLocation('/runtime', query), [query]);

  return (
    <TerminalScreen>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack buy-workbench-page">
            <PageHero
              eyebrow="Watch Targets"
              title="买入目标管理"
              description="管理每个品类对应的买入目标（预算上限、目标内存、风控等级），机会队列会依据这些目标进行匹配。"
              meta={
                <>
                  <span className="soft-pill">{formatNumber(summary?.watchTargetCount)} 个目标</span>
                  <span className="soft-pill is-accent">{formatNumber(summary?.activeWatchTargetCount)} 个生效中</span>
                </>
              }
            >
              <Link className="nav-pill" to={opportunityTarget}>
                回机会队列
              </Link>
              <Link className="nav-pill" to={baselineTarget}>
                看价格基线
              </Link>
              <Link className="nav-pill" to={dashboardTarget}>
                回到看板
              </Link>
              <button
                className="nav-pill"
                type="button"
                onClick={() => {
                  navigate(runtimeTarget);
                }}
              >
                打开运行后台
              </button>
              {isRefreshing ? <span className="soft-pill">正在刷新</span> : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !watchTargets ? (
              <section className="panel">
                <p className="eyebrow">Buy Targets</p>
                <h2>正在加载目标配置...</h2>
                <p className="panel-subtitle">加载后会显示目标状态、预算上限和风控参数，优先支持可直接匹配的 ACTIVE 目标。</p>
              </section>
            ) : null}

            <section className="panel buy-side-panel">
              <div className="buy-panel-header panel-header">
                <div>
                  <p className="eyebrow">Watch Target Pool</p>
                  <h2>监控目标池</h2>
                  <p className="panel-subtitle">默认目标会在机会生成时自动补齐，建议按预算和地区建立补充目标。</p>
                </div>
                <span className="soft-pill">共 {formatNumber(targets.length)} 条</span>
              </div>

              {targets.length ? (
                <div className="buy-opportunity-list">
                  {targets.map((target: BuyWatchTarget) => (
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
                        <strong>
                          预算上限：{formatCurrency(target.budgetCeiling)}
                        </strong>
                        <small>
                          内存：{formatNumber(target.desiredMemoryGb)} GB · 存储：{formatNumber(target.desiredStorageGb)} GB
                        </small>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="buy-empty-state">当前暂无目标。运行机会任务时会自动创建默认目标。</p>
              )}
            </section>
          </div>
        </div>
      </main>
    </TerminalScreen>
  );
}
