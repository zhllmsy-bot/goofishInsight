import { Link, useLocation } from 'react-router-dom';

import type { ListingPreferenceValue } from '../api/dashboardApi';
import { formatCurrency, formatRelative, legacyLink } from '../lib/formatters';
import { buildWorkspacePath, readInitialQuery } from '../lib/urlState';
import type { ListingDecision, Item } from '../types/dashboard';

type ListingCardProps = {
  item: Item;
  decision: ListingDecision;
  localPreference?: ListingPreferenceValue;
  isPendingPreference: boolean;
  onPreference: (itemId: string, preference: ListingPreferenceValue) => void;
};

export function ListingCard(props: ListingCardProps) {
  const location = useLocation();
  const workspaceQuery = readInitialQuery(location.search);
  const itemDetailTarget = buildWorkspacePath(`/items/${props.item.item_id}`, workspaceQuery);

  return (
    <article className={`listing-card ${props.decision.kind} ${props.localPreference === 'interested' ? 'is-interested' : ''}`}>
      {props.item.image_url ? (
        <img alt={props.item.title} className="listing-thumb" src={props.item.image_url} />
      ) : (
        <div className="listing-thumb placeholder">暂无图片</div>
      )}
      <div className="listing-body">
        <div className="listing-topline">
          <span className={`decision-pill ${props.decision.kind}`}>{props.decision.label}</span>
          <span className="listing-time">{formatRelative(props.item.last_seen_at)}</span>
        </div>
        <div className="listing-price-row">
          <strong className="listing-price">{formatCurrency(props.item.price)}</strong>
          <span className={`delta-pill ${props.decision.deltaKind}`}>{props.decision.deltaLabel}</span>
        </div>
        <div className="listing-model">{props.item.display_name ?? props.item.domain_label ?? '未知型号'}</div>
        <a className="listing-title" href={props.item.listing_url ?? legacyLink(`/items/${props.item.item_id}`)} rel="noreferrer" target="_blank">
          {props.item.title}
        </a>
        <div className="listing-note">{props.decision.note}</div>
        <div className="listing-meta">
          <span>{props.item.region || '未知地区'}</span>
          <span>{props.item.seller_name || props.item.seller_id || '未知卖家'}</span>
          <span>{props.item.heartbeat_label || '状态未知'}</span>
        </div>
        <div className="listing-links">
          <a href={props.item.listing_url ?? legacyLink(`/items/${props.item.item_id}`)} rel="noreferrer" target="_blank">
            打开闲鱼
          </a>
          <Link to={itemDetailTarget}>查看详情</Link>
        </div>
        <div className="listing-actions">
          <button
            className={`listing-action-button ${props.localPreference === 'interested' ? 'is-active' : ''}`}
            disabled={props.isPendingPreference}
            type="button"
            onClick={() => props.onPreference(props.item.item_id, 'interested')}
          >
            {props.localPreference === 'interested' ? '已感兴趣' : '标记感兴趣'}
          </button>
          <button
            className="listing-action-button is-muted"
            disabled={props.isPendingPreference}
            type="button"
            onClick={() => props.onPreference(props.item.item_id, 'not_interested')}
          >
            不感兴趣
          </button>
        </div>
      </div>
    </article>
  );
}
