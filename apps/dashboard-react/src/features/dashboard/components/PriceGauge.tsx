import { gaugePosition, formatCurrency } from '../lib/formatters';
import type { PricingRow } from '../types/dashboard';

export function PriceGauge(props: { itemPrices?: number[]; row: PricingRow }) {
  const minimum = Math.min(props.row.safe_buy_price, props.row.normal_buy_price, props.row.market_mid_price);
  const maximum = Math.max(props.row.safe_buy_price, props.row.normal_buy_price, props.row.market_mid_price);
  const padding = Math.max((maximum - minimum) * 0.35, maximum * 0.06, 1);
  const rangeMin = Math.max(0, minimum - padding);
  const rangeMax = maximum + padding;
  const safePosition = gaugePosition(props.row.safe_buy_price, rangeMin, rangeMax);
  const normalPosition = gaugePosition(props.row.normal_buy_price, rangeMin, rangeMax);
  const marketPosition = gaugePosition(props.row.market_mid_price, rangeMin, rangeMax);
  const itemPricePoints = (props.itemPrices ?? [])
    .filter((price) => Number.isFinite(price))
    .slice(0, 80)
    .map((price, index) => ({
      key: `${price}:${index}`,
      price,
      left: gaugePosition(price, rangeMin, rangeMax),
      top: (index % 3) * 4,
    }));
  const distributionLabel = itemPricePoints.length
    ? `挂牌分布 ${itemPricePoints.length} 条，最低 ${formatCurrency(Math.min(...itemPricePoints.map((point) => point.price)))}，最高 ${formatCurrency(
        Math.max(...itemPricePoints.map((point) => point.price)),
      )}`
    : '暂无挂牌分布';

  return (
    <div aria-label="价格标尺" className="price-gauge">
      <div className="price-gauge-track" />
      <div className="price-gauge-range buy" style={{ left: `${safePosition}%`, width: `${Math.max(normalPosition - safePosition, 2)}%` }} />
      <div className="price-gauge-range watch" style={{ left: `${normalPosition}%`, width: `${Math.max(marketPosition - normalPosition, 2)}%` }} />
      {itemPricePoints.length ? (
        <div className="price-gauge-distribution" aria-label={`当前挂牌价格分布，共 ${itemPricePoints.length} 个点`}>
          {itemPricePoints.map((point) => (
            <span
              aria-label={`挂牌价 ${formatCurrency(point.price)}`}
              className="price-gauge-dot"
              key={point.key}
              style={{ left: `${point.left}%`, top: `${point.top}px` }}
              title={`挂牌价 ${formatCurrency(point.price)}`}
            />
          ))}
        </div>
      ) : null}
      <div className="price-marker buy" style={{ left: `${safePosition}%` }}>
        <strong>{formatCurrency(props.row.safe_buy_price)}</strong>
        <span>安全</span>
      </div>
      <div className="price-marker watch" style={{ left: `${normalPosition}%` }}>
        <strong>{formatCurrency(props.row.normal_buy_price)}</strong>
        <span>正常</span>
      </div>
      <div className="price-marker market" style={{ left: `${marketPosition}%` }}>
        <strong>{formatCurrency(props.row.market_mid_price)}</strong>
        <span>中位</span>
      </div>
      <div className="price-axis">
        <span>{formatCurrency(rangeMin)}</span>
        <span>{formatCurrency(rangeMax)}</span>
      </div>
      <p className="price-gauge-summary">{distributionLabel}</p>
    </div>
  );
}
