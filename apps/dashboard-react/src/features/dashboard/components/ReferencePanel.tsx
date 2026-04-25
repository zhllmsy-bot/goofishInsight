import { useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';

import { formatCurrency, formatNumber, formatPercent, formatRelative } from '../lib/formatters';
import { buildWorkspaceLocation } from '../lib/urlState';
import type { CalibrationData, InsightsData, PricingData, QueryState, ReferenceTab, TrendCard } from '../types/dashboard';

type ReferencePanelProps = {
  calibration: CalibrationData | null;
  insights: InsightsData | null;
  pricing: PricingData | null;
  query: QueryState;
  referenceTab: ReferenceTab;
  onReferenceTabChange: (tab: ReferenceTab) => void;
};

const AVAILABILITY_LABELS: Record<string, string> = {
  incomplete: '模板未完整',
  blocked: '证据不足',
  reference_only: '仅供参考',
  guidance_ready: '可指导',
};

const REFERENCE_TAB_ORDER: ReferenceTab[] = ['trend', 'calibration'];

export function ReferencePanel(props: ReferencePanelProps) {
  const runtimeTarget = buildWorkspaceLocation('/runtime', props.query);
  const tabIdPrefix = useId();
  const tabRefs = useRef<Record<ReferenceTab, HTMLButtonElement | null>>({
    trend: null,
    calibration: null,
  });
  const scopedTrendCards = getScopedTrendCards(props.insights?.domain_trend_cards ?? [], props.query);
  const hasScopedSelection = Boolean(props.query.productLabel);
  const availabilityTier =
    props.pricing?.pricing_availability?.availabilityTier ?? props.pricing?.pricing_panel?.selected_pricing_availability?.availabilityTier;
  const scopedTrendTitle = props.query.productLabel
    ? props.query.specLabel
      ? `${props.query.productLabel} / ${props.query.specLabel}`
      : props.query.productLabel
    : props.insights?.overview?.scope_label ?? '全部业务域';
  const tabIds = {
    trend: `${tabIdPrefix}-trend-tab`,
    calibration: `${tabIdPrefix}-calibration-tab`,
  };
  const panelIds = {
    trend: `${tabIdPrefix}-trend-panel`,
    calibration: `${tabIdPrefix}-calibration-panel`,
  };

  function handleReferenceTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentTab: ReferenceTab): void {
    const currentIndex = REFERENCE_TAB_ORDER.indexOf(currentTab);
    let nextTab: ReferenceTab | null = null;

    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextTab = REFERENCE_TAB_ORDER[(currentIndex + 1) % REFERENCE_TAB_ORDER.length];
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextTab = REFERENCE_TAB_ORDER[(currentIndex - 1 + REFERENCE_TAB_ORDER.length) % REFERENCE_TAB_ORDER.length];
    } else if (event.key === 'Home') {
      nextTab = REFERENCE_TAB_ORDER[0];
    } else if (event.key === 'End') {
      nextTab = REFERENCE_TAB_ORDER[REFERENCE_TAB_ORDER.length - 1];
    }

    if (!nextTab) {
      return;
    }

    event.preventDefault();
    props.onReferenceTabChange(nextTab);
    tabRefs.current[nextTab]?.focus();
  }

  return (
    <section className="panel reference-panel">
      <div className="reference-header">
        <div aria-label="参考面板切换" className="reference-tabs" role="tablist">
          <button
            aria-controls={panelIds.trend}
            aria-selected={props.referenceTab === 'trend'}
            className={`reference-tab ${props.referenceTab === 'trend' ? 'is-active' : ''}`}
            id={tabIds.trend}
            ref={(node) => {
              tabRefs.current.trend = node;
            }}
            role="tab"
            type="button"
            onClick={() => props.onReferenceTabChange('trend')}
            onKeyDown={(event) => handleReferenceTabKeyDown(event, 'trend')}
            tabIndex={props.referenceTab === 'trend' ? 0 : -1}
          >
            价格趋势
          </button>
          <button
            aria-controls={panelIds.calibration}
            aria-selected={props.referenceTab === 'calibration'}
            className={`reference-tab ${props.referenceTab === 'calibration' ? 'is-active' : ''}`}
            id={tabIds.calibration}
            ref={(node) => {
              tabRefs.current.calibration = node;
            }}
            role="tab"
            type="button"
            onClick={() => props.onReferenceTabChange('calibration')}
            onKeyDown={(event) => handleReferenceTabKeyDown(event, 'calibration')}
            tabIndex={props.referenceTab === 'calibration' ? 0 : -1}
          >
            历史成交校准
          </button>
        </div>
      </div>

      <section
        aria-labelledby={tabIds.trend}
        className="reference-view"
        hidden={props.referenceTab !== 'trend'}
        id={panelIds.trend}
        role="tabpanel"
      >
        <div className="panel-header">
          <div>
            <p className="eyebrow">价格趋势</p>
            <h2>{scopedTrendTitle} 参考面</h2>
            <p className="panel-subtitle">
              {hasScopedSelection
                ? '已经切到具体组合后，这里只展示当前上下文能精确命中的趋势，不再混进别的组合。'
                : '看完价格线和最新挂牌，再用这里确认趋势和市场节奏。'}
            </p>
          </div>
          <div className="pill-row">
            <span className="soft-pill">近 {formatNumber(props.insights?.overview?.window_days)} 天</span>
            <span className="soft-pill">{formatPercent(props.insights?.overview?.stale_ratio, 1)} 疑似失活</span>
            {availabilityTier && availabilityTier !== 'guidance_ready' ? (
              <span className="soft-pill is-warning">当前模板 {AVAILABILITY_LABELS[availabilityTier] ?? availabilityTier}</span>
            ) : null}
          </div>
        </div>
        <div className="pill-row reference-summary">
          <span className="soft-pill">最近刷新 {formatRelative(props.insights?.overview?.latest_seen)}</span>
          <span className="soft-pill">活跃挂牌 {formatNumber(props.insights?.overview?.active_items)}</span>
          <span className="soft-pill">卖家覆盖 {formatNumber(props.insights?.overview?.total_sellers)}</span>
          <Link className="soft-pill reference-action-link" to={runtimeTarget}>
            去运行控制确认链路
          </Link>
        </div>
        {scopedTrendCards.length ? (
          <div className="trend-grid">
            {scopedTrendCards.map((card) => (
              <article className="trend-card" key={card.label}>
                <div className="trend-head">
                  <div>
                    <h3>{card.label}</h3>
                    <p>{card.domain_label}</p>
                  </div>
                  <span className="soft-pill">{card.change_label}</span>
                </div>
                <TrendChart card={card} />
                <div className="trend-foot">
                  <span>价格带 {card.latest_range_label}</span>
                  <span>最新样本 {formatNumber(card.latest_sample_count)}</span>
                  <span>活跃卖家 {formatNumber(card.seller_sample_count)}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <article className="trend-empty-card">
            <h3>当前组合暂无稳定趋势卡</h3>
            <p className="panel-subtitle">当前筛选已经收窄到具体组合，所以这里不再用同类其他组合来替代展示。</p>
          </article>
        )}
      </section>

      <section
        aria-labelledby={tabIds.calibration}
        className="reference-view"
        hidden={props.referenceTab !== 'calibration'}
        id={panelIds.calibration}
        role="tabpanel"
      >
        <div className="panel-header">
          <div>
            <p className="eyebrow">成交校准</p>
            <h2>挂牌与真实成交对照</h2>
            <p className="panel-subtitle">用移动端抓到的真实成交锚点，校正收货线和出货预期。</p>
          </div>
          <div className="pill-row">
            <span className="soft-pill">{formatNumber(props.calibration?.mobile_market_panel?.captured_model_count)} 个模型</span>
            <span className="soft-pill is-accent">最近同步 {formatRelative(props.calibration?.mobile_market_panel?.latest_captured_at)}</span>
          </div>
        </div>
        <div className="calibration-grid">
          {(props.calibration?.mobile_market_panel?.rows ?? []).slice(0, 4).map((row) => (
            <article className="calibration-card" key={row.model_name}>
              <div className="trend-head">
                <div>
                  <h3>{row.model_name}</h3>
                  <p>{row.domain_label}</p>
                </div>
                <span className="soft-pill">{row.calibration_label}</span>
              </div>
              <div className="calibration-stats">
                <div>
                  <span>挂牌锚点</span>
                  <strong>{formatCurrency(row.listed_avg_price)}</strong>
                </div>
                <div>
                  <span>成交锚点</span>
                  <strong>{formatCurrency(row.sold_anchor_price)}</strong>
                </div>
                <div>
                  <span>成交线索</span>
                  <strong>{formatNumber(row.visible_record_count)} 条</strong>
                </div>
              </div>
              <p className="focus-caption">{row.calibration_detail}</p>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function getScopedTrendCards(cards: TrendCard[], query: QueryState): TrendCard[] {
  if (!query.productLabel) {
    return cards.slice(0, 3);
  }

  if (query.specLabel) {
    const normalizedSpec = normalizeLabel(query.specLabel);
    const exactSpecMatches = cards.filter((card) => normalizeLabel(card.label) === normalizedSpec);
    if (exactSpecMatches.length) {
      return exactSpecMatches.slice(0, 3);
    }
  }

  const normalizedTarget = normalizeLabel(query.productLabel);
  const exactMatches = cards.filter((card) => normalizeLabel(card.label) === normalizedTarget);
  if (exactMatches.length) {
    return exactMatches.slice(0, 3);
  }

  const prefixMatches = cards.filter((card) => {
    const current = normalizeLabel(card.label);
    return current.startsWith(normalizedTarget) || normalizedTarget.startsWith(current);
  });
  return prefixMatches.slice(0, 3);
}

function normalizeLabel(value: string): string {
  return value.replace(/\s+/g, '').toLowerCase();
}

function TrendChart(props: { card: TrendCard }) {
  const [hoverPointIndex, setHoverPointIndex] = useState<number | null>(null);
  const width = props.card.chart_width ?? 320;
  const height = props.card.chart_height ?? 180;
  const hoverPoint = hoverPointIndex === null ? null : (props.card.trend_points ?? [])[hoverPointIndex] ?? null;
  const tooltipX = Math.min(Math.max(hoverPoint?.center_x ?? 0, 90), Math.max(width - 90, 90));
  const tooltipY = Math.max((hoverPoint?.mid_y ?? 0) - 28, 24);
  const tooltipLabel = String(hoverPoint?.tooltip ?? '').slice(0, 42);

  return (
    <svg
      aria-label={props.card.aria_label ?? props.card.label}
      className={`trend-chart ${props.card.change_class ?? 'watch'}`}
      role="img"
      viewBox={`0 0 ${width} ${height}`}
      onMouseLeave={() => setHoverPointIndex(null)}
    >
      {(props.card.price_ticks ?? []).map((tick, index) => (
        <g key={`price-${index}`}>
          <line
            className="trend-grid-line"
            x1="54"
            x2={width - 18}
            y1={tick.y ?? 0}
            y2={tick.y ?? 0}
          />
          <text className="trend-axis-text" x="8" y={(tick.y ?? 0) + 4}>
            {tick.label}
          </text>
        </g>
      ))}
      <path className="trend-range-line" d={props.card.trend_upper_path ?? ''} fill="none" />
      <path className="trend-range-line" d={props.card.trend_lower_path ?? ''} fill="none" />
      <path className="trend-line" d={props.card.trend_line_path ?? ''} fill="none" />
      {(props.card.trend_points ?? []).map((point, index) => (
        <circle
          aria-label={point.tooltip ?? undefined}
          className="trend-point-core"
          cx={point.center_x ?? 0}
          cy={point.mid_y ?? 0}
          key={`point-${index}`}
          r="4.5"
          tabIndex={0}
          onBlur={() => setHoverPointIndex(null)}
          onFocus={() => setHoverPointIndex(index)}
          onMouseEnter={() => setHoverPointIndex(index)}
        />
      ))}
      {(props.card.date_ticks ?? []).map((tick, index) => (
        <text
          className="trend-axis-text"
          key={`date-${index}`}
          textAnchor="middle"
          x={tick.x ?? 0}
          y={height - 8}
        >
          {tick.label}
        </text>
      ))}
      {tooltipLabel ? (
        <g className="trend-tooltip" pointerEvents="none">
          <rect className="trend-tooltip-box" height="28" rx="7" width="166" x={tooltipX - 83} y={tooltipY - 24} />
          <text className="trend-tooltip-text" textAnchor="middle" x={tooltipX} y={tooltipY - 6}>
            {tooltipLabel}
          </text>
        </g>
      ) : null}
    </svg>
  );
}
