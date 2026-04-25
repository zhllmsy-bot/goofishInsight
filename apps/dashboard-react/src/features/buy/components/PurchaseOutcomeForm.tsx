import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';

import { formatCurrency, formatPercent } from '../../dashboard/lib/formatters';

type PurchaseOutcomePayload = {
  purchasePrice: string;
  expectedResalePrice: string;
  feedbackNote?: string;
};

type PurchaseOutcomeFormProps = {
  currentPrice?: number | null;
  fairPrice?: number | null;
  buyCeiling?: number | null;
  isPending?: boolean;
  onCancel: () => void;
  onSubmit: (payload: PurchaseOutcomePayload) => void | Promise<void>;
};

function initialMoneyValue(value: number | null | undefined): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return '';
  }
  return String(Math.round(numeric));
}

function parseMoney(value: string): number | null {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

export function PurchaseOutcomeForm(props: PurchaseOutcomeFormProps) {
  const [purchasePrice, setPurchasePrice] = useState(() => initialMoneyValue(props.currentPrice ?? props.buyCeiling));
  const [expectedResalePrice, setExpectedResalePrice] = useState(() => initialMoneyValue(props.fairPrice ?? props.buyCeiling));
  const [feedbackNote, setFeedbackNote] = useState('');
  const [error, setError] = useState('');
  const preview = useMemo(() => {
    const purchase = parseMoney(purchasePrice);
    const resale = parseMoney(expectedResalePrice);
    if (purchase === null || resale === null) {
      return null;
    }
    const estimatedProfit = resale - purchase;
    return {
      estimatedProfit,
      estimatedRoiRate: estimatedProfit / purchase,
    };
  }, [expectedResalePrice, purchasePrice]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (parseMoney(purchasePrice) === null || parseMoney(expectedResalePrice) === null) {
      setError('请填写有效的买入价和预估转售价，成交反馈需要能沉淀 ROI 证据。');
      return;
    }
    setError('');
    void props.onSubmit({
      purchasePrice,
      expectedResalePrice,
      feedbackNote: feedbackNote.trim() || undefined,
    });
  }

  return (
    <form className="purchase-outcome-form" onSubmit={handleSubmit}>
      <div className="purchase-outcome-grid">
        <label>
          <span>实际买入价</span>
          <input
            min="1"
            inputMode="decimal"
            name="purchasePrice"
            type="number"
            value={purchasePrice}
            onChange={(event) => {
              setPurchasePrice(event.target.value);
            }}
          />
        </label>
        <label>
          <span>预估转售价</span>
          <input
            min="1"
            inputMode="decimal"
            name="expectedResalePrice"
            type="number"
            value={expectedResalePrice}
            onChange={(event) => {
              setExpectedResalePrice(event.target.value);
            }}
          />
        </label>
      </div>
      <label className="purchase-outcome-note">
        <span>成交备注</span>
        <textarea
          name="feedbackNote"
          placeholder="可记录成色、卖家风险、议价过程或后续复盘点。"
          rows={3}
          value={feedbackNote}
          onChange={(event) => {
            setFeedbackNote(event.target.value);
          }}
        />
      </label>
      <div className="purchase-outcome-preview">
        <span>当前价 {formatCurrency(props.currentPrice)}</span>
        <span>买入线 {formatCurrency(props.buyCeiling)}</span>
        <span>合理价 {formatCurrency(props.fairPrice)}</span>
        {preview ? (
          <strong>
            预估利润 {formatCurrency(preview.estimatedProfit)} · ROI {formatPercent(preview.estimatedRoiRate * 100, 1)}
          </strong>
        ) : (
          <strong>填写价格后预览利润和 ROI</strong>
        )}
      </div>
      {error ? <p className="buy-feedback-result is-error">{error}</p> : null}
      <div className="buy-feedback-actions">
        <button className="quick-pill is-active" disabled={props.isPending} type="submit">
          {props.isPending ? '记录中...' : '确认成交并记录 ROI'}
        </button>
        <button className="quick-pill" disabled={props.isPending} type="button" onClick={props.onCancel}>
          取消
        </button>
      </div>
    </form>
  );
}
