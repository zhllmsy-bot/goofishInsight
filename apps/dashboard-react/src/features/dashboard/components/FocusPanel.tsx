import { Link } from 'react-router-dom';

import { formatCurrency } from '../lib/formatters';
import { buildWorkspaceLocation } from '../lib/urlState';
import { useDashboardUiStore } from '../store/dashboardUiStore';
import type { FocusCard } from '../types/dashboard';

export function FocusPanel(props: { cards: FocusCard[]; variant?: 'compact' | 'default' }) {
  const query = useDashboardUiStore((state) => state.query);
  const buyWorkbenchTarget = buildWorkspaceLocation('/buy/opportunities', query);
  const runtimeTarget = buildWorkspaceLocation('/runtime', query);
  const visibleCards = props.cards.filter((card) => !card.empty);
  const isCompact = props.variant === 'compact';

  return (
    <section className={`panel focus-panel ${isCompact ? 'is-compact' : ''}`}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">机会榜</p>
          <h2>同品类优先方向</h2>
          <p className="panel-subtitle">{isCompact ? '当前还没锁定具体组合，先把这个品类里更值得先看的方向露出来。' : '这里不再重复当前选中组合的价格卡，而是把同一品类里更值得先看的方向排出来。'}</p>
        </div>
        <span className="soft-pill is-accent">{visibleCards.length} 个方向</span>
      </div>
      <div className="focus-grid">
        {visibleCards
          .slice(0, isCompact ? 2 : visibleCards.length)
          .map((card, index) => (
            <article className={`focus-card ${card.tone ?? 'watch'}`} key={`${card.title}:${card.label}`}>
              <div className="focus-head">
                <div>
                  <p className="eyebrow">#{index + 1} {card.title}</p>
                  <h3>{card.label}</h3>
                </div>
                <span className="focus-state">{card.focus_state_label ?? '观察中'}</span>
              </div>
              <p className="focus-caption">{card.caption}</p>
              <div className="focus-profit">
                <strong>{card.estimated_profit_label ?? '-'}</strong>
                <span>至少要过 {formatCurrency(card.required_profit_amount)}</span>
              </div>
              <div className="focus-price-row is-muted">
                <span>安全 {formatCurrency(card.safe_buy_price)}</span>
                <span>正常 {formatCurrency(card.normal_buy_price)}</span>
                <span>市场 {formatCurrency(card.market_mid_price)}</span>
              </div>
              <div className="focus-actions">
                <Link to={buyWorkbenchTarget}>去买方工作台</Link>
                <Link to={runtimeTarget}>
                  打开运行控制
                </Link>
              </div>
              {!!card.dimensions?.length && (
                <div className="chip-row">
                  {card.dimensions.map((dimension) => (
                    <span className="filter-tag" key={dimension}>
                      {dimension}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
      </div>
    </section>
  );
}
