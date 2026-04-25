import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMemo } from 'react';

import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber, formatPercent } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { useBuyBaselines } from '../hooks/useBuyWorkbench';
import type { BuyBaseline } from '../types/buy';

import '../../dashboard/styles/dashboard.css';
import '../styles/buy-workbench.css';

export function BuyBaselinesPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const query = readInitialQuery(location.search);
  const categoryCode = query.categoryCode;
  const { baselines, error, isLoading, isRefreshing } = useBuyBaselines(categoryCode, 200);
  const summary = baselines?.summary;
  const rows = baselines?.baselines ?? [];

  const opportunityTarget = useMemo(() => buildWorkspaceLocation('/buy/opportunities', query), [query]);
  const targetTarget = useMemo(() => buildWorkspaceLocation('/buy/targets', query), [query]);
  const dashboardTarget = useMemo(() => buildWorkspaceLocation('/', query), [query]);
  const runtimeTarget = useMemo(() => buildWorkspaceLocation('/ops/runtime', query), [query]);

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack buy-workbench-page">
            <PageHero
              eyebrow="Price Baselines"
              title="价格基线管理"
              description="查看每个型号和配置下的合理价/买入线，支持按时间窗口快速回放历史基线，辅助决策是否继续刷新。"
              meta={
                <>
                  <span className="soft-pill">{formatNumber(summary?.baselineCount)} 个基线</span>
                  {summary?.baselineDateFrom && summary?.baselineDateTo ? (
                    <span className="soft-pill is-accent">
                      {summary.baselineDateFrom} ~ {summary.baselineDateTo}
                    </span>
                  ) : null}
                </>
              }
            >
              <Link className="nav-pill" to={opportunityTarget}>
                回机会队列
              </Link>
              <Link className="nav-pill" to={targetTarget}>
                看买入目标
              </Link>
              <Link className="nav-pill" to={dashboardTarget}>
                回到看板
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
              {isRefreshing ? <span className="soft-pill">正在刷新</span> : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !baselines ? (
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
                  <h2>价格基线列表</h2>
                  <p className="panel-subtitle">当前展示最新 {formatNumber(summary?.baselineCount)} 条基线，便于快速识别样本不足的盲区。</p>
                </div>
                <span className="soft-pill">共 {formatNumber(rows.length)} 条</span>
              </div>

              {rows.length ? rows.map((baseline: BuyBaseline) => (
                <article className="mini-card" key={baseline.id}>
                  <strong>{baseline.baselineKey}</strong>
                  <small>
                    fair {formatCurrency(baseline.fairPrice)} · buy {formatCurrency(baseline.buyCeiling)} · n={formatNumber(baseline.sampleSize)}
                  </small>
                  <small>置信度 {formatPercent((baseline.confidence ?? 0) * 100, 1)}</small>
                  <small>{baseline.baselineDate ?? '-'}</small>
                  <small>{baseline.explanation?.readinessSummary ?? '-'}</small>
                </article>
              )) : (
                <p className="buy-empty-state">当前没有基线。先从运行后台执行 build-buy-baselines。</p>
              )}
            </section>
          </div>
        </div>
      </main>
    </AppFrame>
  );
}
