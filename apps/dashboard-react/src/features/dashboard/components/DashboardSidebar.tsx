import { useNavigate } from 'react-router-dom';

import { categoryLabel, formatRelative, statusLabel } from '../lib/formatters';
import { buildWorkspaceLocation } from '../lib/urlState';
import type { HeroData, QueryState } from '../types/dashboard';
import type { RuntimeSummary } from '../../runtime/lib/runtimeViewModel';

type DashboardSidebarProps = {
  availableCategories: string[];
  hero: HeroData | null;
  query: QueryState;
  onCategorySelect: (categoryCode: string) => void;
  onPricingScopeChange: (pricingScope: QueryState['pricingScope']) => void;
  onResetSelection: () => void;
  runtimeSummary?: RuntimeSummary;
};

export function DashboardSidebar(props: DashboardSidebarProps) {
  const navigate = useNavigate();
  const selectedScopeLabel = props.query.productLabel
    ? props.query.specLabel
      ? `${props.query.productLabel} / ${props.query.specLabel}`
      : props.query.productLabel
    : '未选择组合';
  const runtimeSummary = props.runtimeSummary;
  const hasRuntimeAttention = runtimeSummary && runtimeSummary.attentionCount > 0;

  return (
    <aside className="sidebar">
      <div className="sidebar-card sidebar-brand-card">
        <h2>买方交易终端</h2>
        <p>BUY-SIDE TERMINAL</p>
      </div>

      <div className="sidebar-card sidebar-selection-card">
        <div className="status-row">
          <span>当前品类</span>
          <strong>{categoryLabel(props.query.categoryCode)}</strong>
        </div>
        <div className="status-row">
          <span>当前组合</span>
          <strong>{selectedScopeLabel}</strong>
        </div>
        <button className="quick-pill" type="button" onClick={props.onResetSelection}>
          清空组合筛选
        </button>
      </div>

      {runtimeSummary ? (
        <button
          className={`sidebar-card sidebar-runtime-card ${hasRuntimeAttention ? 'is-warn' : 'is-ok'}`}
          type="button"
          onClick={() => void navigate(buildWorkspaceLocation('/ops/runtime', props.query))}
        >
          <div className="status-row">
            <span>常驻链路</span>
            <strong className={hasRuntimeAttention ? 'text-warn' : 'text-ok'}>
              {runtimeSummary.runningCount}/{runtimeSummary.totalCount} 在线
            </strong>
          </div>
          {hasRuntimeAttention ? (
            <div className="status-row">
              <span>待处理</span>
              <strong className="text-warn">
                {runtimeSummary.stoppedCount} 停止 / {runtimeSummary.degradedCount} 降级
              </strong>
            </div>
          ) : null}
          <small className="sidebar-runtime-link">查看运行控制台 →</small>
        </button>
      ) : null}

      <div className="sidebar-quick-filters">
        <button
          aria-pressed={props.query.pricingScope === 'actionable'}
          className={`quick-pill ${props.query.pricingScope === 'actionable' ? 'is-active' : ''}`}
          type="button"
          onClick={() => props.onPricingScopeChange('actionable')}
        >
          只看机会成立
        </button>
        <button
          aria-pressed={props.query.pricingScope === 'all'}
          className={`quick-pill ${props.query.pricingScope === 'all' ? 'is-active' : ''}`}
          type="button"
          onClick={() => props.onPricingScopeChange('all')}
        >
          查看全部
        </button>
      </div>

      <nav className="sidebar-tree" aria-label="品类导航">
        <ul className="sidebar-tree-list">
          {props.availableCategories.map((categoryCode) => {
            const isActive = categoryCode === props.query.categoryCode;
            return (
              <li className="sidebar-tree-group" key={categoryCode}>
                <button
                  aria-current={isActive ? 'true' : undefined}
                  className={`sidebar-tree-category ${isActive ? 'is-active' : ''}`}
                  type="button"
                  onClick={() => props.onCategorySelect(categoryCode)}
                >
                  <span>{categoryLabel(categoryCode)}</span>
                  <small>{isActive ? '当前工作区' : '切换该品类'}</small>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <details className="sidebar-preferences">
        <summary>偏好设置</summary>
        <div className="sidebar-preference-grid">
          <span className="filter-tag">窗口 {props.query.pricingFreshnessDays} 天</span>
          {props.query.productLabel ? <span className="filter-tag">{props.query.productLabel}</span> : null}
          {props.query.specLabel ? <span className="filter-tag">{props.query.specLabel}</span> : null}
        </div>
      </details>

      <div className="sidebar-card sidebar-status-card">
        <div className="status-row">
          <span>自动刷新</span>
          <strong>{statusLabel(props.hero?.overview?.latest_run?.status)}</strong>
        </div>
        <div className="status-row">
          <span>登录态</span>
          <strong>{statusLabel(props.hero?.overview?.browser_session?.auth_state)}</strong>
        </div>
        <div className="status-row">
          <span>最近刷新</span>
          <strong>{formatRelative(props.hero?.overview?.latest_seen)}</strong>
        </div>
      </div>
    </aside>
  );
}
