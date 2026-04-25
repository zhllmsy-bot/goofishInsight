import { useMemo, useState } from 'react';

import { gaugePosition, formatCurrency } from '../lib/formatters';
import type { PricingRow } from '../types/dashboard';

type PriceSample =
  | number
  | {
      price: number;
      title?: string;
      sellerName?: string;
      seenAt?: string;
    };

type GaugePoint = {
  key: string;
  price: number;
  left: number;
  top: number;
  title: string;
  sellerName: string;
  seenAt: string;
  isCurrent: boolean;
};

type PriceGaugeProps = {
  itemPrices?: PriceSample[];
  row: PricingRow;
  currentPrice?: number | null;
};

const UNKNOWN_LABEL = '-';

function normalizePriceSample(sample: PriceSample, index: number, rangeMin: number, rangeMax: number): GaugePoint | null {
  const source = typeof sample === 'number' ? { price: sample } : sample;
  const price = Number(source.price);

  if (!Number.isFinite(price)) {
    return null;
  }

  const rawKey =
    typeof sample === 'number'
      ? `price-${sample}`
      : `${source.price}-${source.title ?? ''}-${source.sellerName ?? ''}-${source.seenAt ?? ''}`;

  return {
    key: `${rawKey}:${index}`,
    price,
    left: gaugePosition(price, rangeMin, rangeMax),
    top: (index % 3) * 4,
    title: source.title?.trim() || '挂牌商品',
    sellerName: source.sellerName?.trim() || UNKNOWN_LABEL,
    seenAt: source.seenAt?.trim() || UNKNOWN_LABEL,
    isCurrent: false,
  };
}

export function PriceGauge(props: PriceGaugeProps) {
  const [activePoint, setActivePoint] = useState<GaugePoint | null>(null);
  const minimum = Math.min(props.row.safe_buy_price, props.row.normal_buy_price, props.row.market_mid_price);
  const maximum = Math.max(props.row.safe_buy_price, props.row.normal_buy_price, props.row.market_mid_price);
  const padding = Math.max((maximum - minimum) * 0.35, maximum * 0.06, 1);
  const rangeMin = Math.max(0, minimum - padding);
  const rangeMax = maximum + padding;
  const safePosition = gaugePosition(props.row.safe_buy_price, rangeMin, rangeMax);
  const normalPosition = gaugePosition(props.row.normal_buy_price, rangeMin, rangeMax);
  const marketPosition = gaugePosition(props.row.market_mid_price, rangeMin, rangeMax);

  const currentPrice =
    typeof props.currentPrice === 'number' && Number.isFinite(props.currentPrice)
      ? props.currentPrice
      : props.row.market_mid_price;

  const itemPricePoints = useMemo(() => {
    const parsed = (props.itemPrices ?? [])
      .slice(0, 80)
      .map((sample, index) => normalizePriceSample(sample, index, rangeMin, rangeMax))
      .filter((sample): sample is GaugePoint => sample !== null);

    if (!parsed.length || !Number.isFinite(currentPrice)) {
      return parsed;
    }

    const currentIndex = parsed.reduce(
      (nearestIndex, point, index) => {
        const nearestPoint = parsed[nearestIndex];
        const nearestGap = Math.abs(nearestPoint.price - currentPrice);
        const currentGap = Math.abs(point.price - currentPrice);
        return currentGap < nearestGap ? index : nearestIndex;
      },
      0,
    );

    return parsed.map((point, index) => ({
      ...point,
      isCurrent: index === currentIndex,
    }));
  }, [currentPrice, props.itemPrices, rangeMax, rangeMin]);

  const distributionLabel = itemPricePoints.length
    ? `挂牌分布 ${itemPricePoints.length} 条，最低 ${formatCurrency(Math.min(...itemPricePoints.map((point) => point.price)))}，最高 ${formatCurrency(
        Math.max(...itemPricePoints.map((point) => point.price)),
      )}`
    : '暂无挂牌分布';

  const currentMarker = itemPricePoints.find((point) => point.isCurrent);
  const pointTooltipStyle =
    activePoint !== null
      ? {
          left: `calc(${activePoint.left}% - 12px)`,
          top: `${10 - activePoint.top}px`,
        }
      : undefined;

  return (
    <div aria-label="价格标尺" className="price-gauge">
      <div className="price-gauge-track" />
      <div className="price-gauge-range buy" style={{ left: `${safePosition}%`, width: `${Math.max(normalPosition - safePosition, 2)}%` }} />
      <div className="price-gauge-range watch" style={{ left: `${normalPosition}%`, width: `${Math.max(marketPosition - normalPosition, 2)}%` }} />

      {itemPricePoints.length ? (
        <div
          className="price-gauge-distribution"
          aria-label={`当前挂牌价格分布，共 ${itemPricePoints.length} 个点`}
          onMouseLeave={() => {
            setActivePoint(null);
          }}
        >
          {itemPricePoints.map((point) => (
            <span
              aria-label={`挂牌价 ${formatCurrency(point.price)}；卖家 ${point.sellerName}`}
              className={`price-gauge-dot ${point.isCurrent ? 'is-current' : ''}`}
              key={point.key}
              onBlur={() => {
                setActivePoint(null);
              }}
              onFocus={() => {
                setActivePoint(point);
              }}
              onMouseEnter={() => {
                setActivePoint(point);
              }}
              onMouseLeave={() => {
                setActivePoint(null);
              }}
              role="button"
              style={{
                left: `${point.left}%`,
                top: `${point.top}px`,
                opacity: point.isCurrent ? 1 : 0.3,
              }}
              tabIndex={0}
            />
          ))}

          {activePoint ? (
            <div className="price-gauge-point-popover" style={pointTooltipStyle}>
              <p className="price-gauge-popover-title">{activePoint.title}</p>
              <p>{formatCurrency(activePoint.price)}</p>
              <p>卖家：{activePoint.sellerName}</p>
              <p>{activePoint.seenAt === UNKNOWN_LABEL ? '时间：未知' : `时间：${activePoint.seenAt}`}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {currentMarker ? <div className="price-gauge-current" style={{ left: `${currentMarker.left}%` }} /> : null}

      <div className="price-marker buy" style={{ left: `${safePosition}%` }}>
        <strong>{formatCurrency(props.row.safe_buy_price)}</strong>
        <span>
          <span aria-hidden="true" className="marker-shape marker-shape-safe" />
          P15 / 安全
        </span>
      </div>
      <div className="price-marker watch" style={{ left: `${normalPosition}%` }}>
        <strong>{formatCurrency(props.row.normal_buy_price)}</strong>
        <span>
          <span aria-hidden="true" className="marker-shape marker-shape-watch" />
          P35 / 正常
        </span>
      </div>
      <div className="price-marker market" style={{ left: `${marketPosition}%` }}>
        <strong>{formatCurrency(props.row.market_mid_price)}</strong>
        <span>
          <span aria-hidden="true" className="marker-shape marker-shape-market" />
          P50 / 中位
        </span>
      </div>

      <div className="price-axis">
        <span>{formatCurrency(rangeMin)}</span>
        <span>{formatCurrency(rangeMax)}</span>
      </div>
      <p className="price-gauge-summary">{distributionLabel}</p>
    </div>
  );
}
