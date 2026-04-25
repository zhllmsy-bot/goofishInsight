import { Link } from 'react-router-dom';

import { PriceGauge } from '../../../shared/components/business';
import { formatCurrency, formatNumber, formatPercent } from '../lib/formatters';
import { buildWorkspaceLocation } from '../lib/urlState';
import { useDashboardUiStore } from '../store/dashboardUiStore';
import type { PricingData, PricingRow } from '../types/dashboard';

function PriceCard(props: { hint: string; label: string; tone: 'safe' | 'watch' | 'market'; value: number }) {
  return (
    <article className={`price-card ${props.tone}`}>
      <div className="price-card-label">
        <span aria-hidden="true" className="price-dot" />
        <span>{props.label}</span>
      </div>
      <strong>{formatCurrency(props.value)}</strong>
      <small>{props.hint}</small>
    </article>
  );
}

type PricingPanelProps = {
  itemPrices?: (number | { price: number; title?: string; sellerName?: string; seenAt?: string })[];
  pricing: PricingData | null;
  pricingRow: PricingRow | null;
  pricingScope: 'actionable' | 'all';
  onPricingScopeChange: (scope: 'actionable' | 'all') => void;
};

const FIELD_LABELS: Record<string, string> = {
  model_name: '型号',
  brand_name: '品牌',
  chip_family: '芯片',
  memory_gb: '内存',
  storage_gb: '硬盘',
  screen_size_in: '屏幕尺寸',
  case_size_mm: '表径',
  display_type: '屏幕类型',
  is_solar: '太阳能',
  mount_system: '卡口',
  sensor_format: '画幅',
  focal_length_range: '焦段',
  max_aperture: '最大光圈',
};

const AVAILABILITY_LABELS: Record<string, string> = {
  incomplete: '模板未选完整',
  blocked: '证据不足',
  reference_only: '仅供参考',
  guidance_ready: '可指导',
};

const BLOCK_REASON_LABELS: Record<string, string> = {
  template_incomplete: '还缺核心属性，暂时不能给模板价。',
  insufficient_seller_samples: '卖家样本还不够，先别把它当成指导价。',
  insufficient_unique_sellers: '卖家分散度不够，先只做参考。',
  insufficient_exact_spec_ratio: '精确规格命中比例不够，暂不输出可靠价格。',
  insufficient_reliability_score: '可靠度还没过线，先不要按它收货。',
  stale_pricing_evidence: '价格证据已经偏旧，先等新样本。',
};

function humanizeField(field: string) {
  return FIELD_LABELS[field] ?? field;
}

function buildEmptyPricingCopy(pricing: PricingData | null) {
  const contract = pricing?.pricing_contract;
  const availability = pricing?.pricing_availability ?? pricing?.pricing_panel?.selected_pricing_availability;
  const availabilityTier = availability?.availabilityTier ?? null;
  const missingFields = contract?.templateCompleteness?.missingFields ?? contract?.missingPricingFields ?? [];
  const missingLabel = missingFields.map(humanizeField).join(' / ');

  if (availabilityTier === 'incomplete') {
    return {
      title: '先补齐价格模板',
      subtitle: missingLabel
        ? `还缺 ${missingLabel}，继续往下补齐后再看当前模板的收货价和走势。`
        : '还缺核心属性，先把模板选完整再看价格。',
    };
  }

  if (availabilityTier === 'reference_only') {
    return {
      title: '当前模板只有参考价',
      subtitle: '这组模板还没有达到指导价门槛，下面的挂牌先按参考模式阅读。',
    };
  }

  if (availabilityTier === 'blocked') {
    return {
      title: '当前模板证据还不够',
      subtitle:
        BLOCK_REASON_LABELS[availability?.pricingBlockReason ?? ''] ??
        '样本和可靠度还没过线，暂不展示误导性的收货价。',
    };
  }

  return {
    title: '当前还没有稳定价格带',
    subtitle: '先在上方选一组有效组合并补全核心属性，这里才会出现对应模板的收货价。',
  };
}

export function PricingPanel(props: PricingPanelProps) {
  const query = useDashboardUiStore((state) => state.query);
  const runtimeTarget = buildWorkspaceLocation('/ops/runtime', query);

  if (!props.pricingRow) {
    const copy = buildEmptyPricingCopy(props.pricing);
    const availability = props.pricing?.pricing_availability ?? props.pricing?.pricing_panel?.selected_pricing_availability;
    const contract = props.pricing?.pricing_contract;
    const evidence = availability?.pricingEvidence;
    const templateKeyPreview = contract?.templateKeyPreview;

    return (
      <section className="panel pricing-panel">
        <div className="empty-pricing">
          <div>
            <p className="eyebrow">核心价格线</p>
            <h2>{copy.title}</h2>
            <p className="panel-subtitle">{copy.subtitle}</p>
          </div>
          <div className="pill-row">
            {availability?.availabilityTier ? (
              <span className="soft-pill is-warning">{AVAILABILITY_LABELS[availability.availabilityTier ?? ''] ?? availability.availabilityTier}</span>
            ) : null}
            <span className="soft-pill">利润池 {formatNumber(props.pricing?.pricing_gate_summary?.pricing_pool_count)}</span>
            <span className="soft-pill">{formatNumber(props.pricing?.pricing_gate_summary?.candidate_count)} 候选</span>
          </div>
        </div>

        <div className="empty-pricing-details">
          {!!contract?.requiredPricingFields?.length && (
            <div className="pill-row">
              {contract.requiredPricingFields.map((field) => (
                <span className="soft-pill" key={field}>
                  需要 {humanizeField(field)}
                </span>
              ))}
            </div>
          )}
          {!!templateKeyPreview && <p className="template-preview">当前模板键：{templateKeyPreview}</p>}
          {evidence ? (
            <div className="pill-row">
              <span className="soft-pill">样本 {formatNumber(evidence.sellerSampleCount)}</span>
              <span className="soft-pill">卖家 {formatNumber(evidence.uniqueSellerCount)}</span>
              <span className="soft-pill">精确命中 {formatPercent(evidence.exactSpecRatio, 1)}</span>
              <span className="soft-pill">可靠度 {formatNumber(evidence.reliabilityScore)}</span>
            </div>
          ) : null}
        </div>
      </section>
    );
  }

  return (
    <section className="panel pricing-panel">
      <div className="pricing-header">
        <div>
          <p className="eyebrow">核心价格线</p>
          <h2>{props.pricingRow.spec_label ?? props.pricingRow.label}</h2>
          <p className="panel-subtitle">
            {props.pricingRow.spec_label ? '当前选中规格' : '当前选中组合'} / 近{' '}
            {formatNumber(props.pricing?.pricing_panel?.freshness_days)} 天活跃样本
          </p>
        </div>
        <div className="margin-pill">
          <span>预估单机毛利</span>
          <strong>
            {formatCurrency(props.pricingRow.estimated_profit_floor)} ~ {formatCurrency(props.pricingRow.estimated_profit_ceiling)}
          </strong>
          <small>{formatPercent(props.pricingRow.normal_margin_pct, 1)} 毛利率</small>
        </div>
      </div>

      <div className="pricing-action-row">
        <button
          className={`quick-pill ${props.pricingScope === 'actionable' ? 'is-active' : ''}`}
          type="button"
          onClick={() => props.onPricingScopeChange('actionable')}
        >
          只看机会成立
        </button>
        <button
          className={`quick-pill ${props.pricingScope === 'all' ? 'is-active' : ''}`}
          type="button"
          onClick={() => props.onPricingScopeChange('all')}
        >
          查看全部挂牌
        </button>
        <Link className="quick-pill pricing-action-link" to={runtimeTarget}>
          打开运行控制
        </Link>
      </div>

      <div className="price-card-grid">
        <PriceCard hint="绝佳买入线 · P15 分位" label="安全收货价" tone="safe" value={props.pricingRow.safe_buy_price} />
        <PriceCard hint="可谈价格线 · P35 分位" label="正常收货价" tone="watch" value={props.pricingRow.normal_buy_price} />
        <PriceCard hint="当前挂牌均价 · P50 分位" label="市场中位价" tone="market" value={props.pricingRow.market_mid_price} />
      </div>

      <PriceGauge itemPrices={props.itemPrices ?? []} row={props.pricingRow} />

      <div className="pill-row">
        <span className="soft-pill is-accent">{props.pricingRow.opportunity_label ?? '观察中'}</span>
        <span className="soft-pill">{formatNumber(props.pricingRow.unique_seller_count)} 个卖家样本</span>
        <span className="soft-pill">可靠度 {formatNumber(props.pricingRow.reliability_score)}</span>
        <span className="soft-pill">安全毛利率 {formatPercent(props.pricingRow.safe_margin_pct, 1)}</span>
      </div>

      {!!props.pricingRow.dimensions?.length && (
        <div className="chip-row">
          {props.pricingRow.dimensions.map((dimension) => (
            <span className="filter-tag" key={dimension}>
              {dimension}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
