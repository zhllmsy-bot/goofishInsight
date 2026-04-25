import { useMemo, useState } from 'react';

import { postListingPreference } from '../api/dashboardApi';
import type { ListingPreferenceValue } from '../api/dashboardApi';
import { countGroupRows } from '../lib/selectors';
import { ListingCard } from './ListingCard';
import { ListingControls } from './ListingControls';
import { buildDisplayListingGroups, buildRegionOptions, normalizeListingPreference, type ListingSortMode } from '../lib/listingViewModel';
import type { ListingGroup, PricingData, PricingRow } from '../types/dashboard';

type ListingsPanelProps = {
  compact?: boolean;
  listingGroups: ListingGroup[];
  pricing: PricingData | null;
  pricingRow: PricingRow | null;
  selectedProductLabel: string;
  onOpenRuntime: () => void;
};

export function ListingsPanel(props: ListingsPanelProps) {
  const [sortMode, setSortMode] = useState<ListingSortMode>('opportunity');
  const [regionFilter, setRegionFilter] = useState('');
  const [localPreferences, setLocalPreferences] = useState<Record<string, ListingPreferenceValue>>({});
  const [pendingPreferenceItemIds, setPendingPreferenceItemIds] = useState<Record<string, boolean>>({});
  const [actionMessage, setActionMessage] = useState('');
  const availabilityTier = props.pricing?.pricing_availability?.availabilityTier ?? props.pricing?.pricing_panel?.selected_pricing_availability?.availabilityTier;
  const subtitle = props.pricingRow
    ? `当前对照 ${props.pricingRow.label} 的收货线来标记机会。`
    : availabilityTier === 'reference_only'
      ? '当前模板只有参考层级，下面先按时间展示挂牌，不把它误标成可收价。'
      : availabilityTier === 'blocked'
        ? '当前模板证据不足，下面只展示最新挂牌，等待样本充足后再判断价格机会。'
        : '当前还没有稳定价格线，因此先按时间展示最新挂牌。';
  const regionOptions = useMemo(() => buildRegionOptions(props.listingGroups), [props.listingGroups]);
  const displayGroups = useMemo(
    () => buildDisplayListingGroups(props.listingGroups, sortMode, regionFilter, localPreferences),
    [localPreferences, props.listingGroups, regionFilter, sortMode],
  );
  const visibleRowCount = displayGroups.reduce((count, group) => count + group.rows.length, 0);

  async function handlePreference(itemId: string, preference: ListingPreferenceValue): Promise<void> {
    const previousPreference = localPreferences[itemId];
    setActionMessage('');
    setLocalPreferences((current) => ({
      ...current,
      [itemId]: preference,
    }));
    setPendingPreferenceItemIds((current) => ({ ...current, [itemId]: true }));

    try {
      await postListingPreference({
        itemId,
        preference,
        reason: preference === 'interested' ? 'dashboard_card_interest' : 'dashboard_card_not_interested',
      });
      setActionMessage(preference === 'interested' ? '已标记感兴趣。' : '已标记不感兴趣，本页先隐藏。');
    } catch (error) {
      setLocalPreferences((current) => {
        const next = { ...current };
        if (previousPreference) {
          next[itemId] = previousPreference;
        } else {
          delete next[itemId];
        }
        return next;
      });
      setActionMessage(error instanceof Error ? `偏好保存失败：${error.message}` : '偏好保存失败。');
    } finally {
      setPendingPreferenceItemIds((current) => {
        const next = { ...current };
        delete next[itemId];
        return next;
      });
    }
  }

  return (
    <section className={`panel listing-panel ${props.compact ? 'is-compact' : ''}`}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">最新在售</p>
          <h2>今天先看这些刚刷到的商品</h2>
          <p className="panel-subtitle">{subtitle}</p>
        </div>
        <div className="pill-row">
          <span className="soft-pill is-accent">{countGroupRows(props.listingGroups, 'buy')} 个低价机会</span>
          <span className="soft-pill">{countGroupRows(props.listingGroups, 'watch')} 个可谈标的</span>
        </div>
      </div>

      <div className="listing-flow-actions">
        <span className="flow-label">{props.selectedProductLabel ? `当前组合：${props.selectedProductLabel}` : '未选择组合，列表按当前品类展示'}</span>
        <button className="quick-pill" type="button" onClick={props.onOpenRuntime}>
          运行控制
        </button>
      </div>

      {!props.compact || visibleRowCount > 0 ? (
        <ListingControls
          regionFilter={regionFilter}
          regionOptions={regionOptions}
          sortMode={sortMode}
          onRegionFilterChange={setRegionFilter}
          onSortModeChange={setSortMode}
        />
      ) : null}
      {actionMessage ? <div className="listing-action-message">{actionMessage}</div> : null}

      {displayGroups.length ? (
        <div className="listing-stack">
          {displayGroups.map((group) => (
            <section className="listing-group" key={group.key}>
              <div className="listing-group-header">
                <h3>{group.title}</h3>
                <span className="soft-pill">{group.countLabel}</span>
              </div>
              <div className="listing-grid">
                {group.rows.map(({ item, decision }) => (
                  <ListingCard
                    key={item.item_id}
                    decision={decision}
                    isPendingPreference={Boolean(pendingPreferenceItemIds[item.item_id])}
                    item={item}
                    localPreference={localPreferences[item.item_id] ?? normalizeListingPreference(item.listing_preference)}
                    onPreference={(itemId, preference) => void handlePreference(itemId, preference)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className="listing-empty-state">当前筛选下没有挂牌，切回全部地区再看看。</div>
      )}
    </section>
  );
}
