import type { ListingPreferenceValue } from '../api/dashboardApi';
import type { ListingGroup, ListingRow } from '../types/dashboard';

export type ListingSortMode = 'opportunity' | 'price_asc' | 'latest';

export function buildRegionOptions(groups: ListingGroup[]): string[] {
  return Array.from(
    new Set(
      groups
        .flatMap((group) => group.rows)
        .map(({ item }) => normalizeListingRegion(item.region))
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right, 'zh-CN'));
}

export function buildDisplayListingGroups(
  groups: ListingGroup[],
  sortMode: ListingSortMode,
  regionFilter: string,
  preferences: Record<string, ListingPreferenceValue>,
): ListingGroup[] {
  return groups
    .map((group) => {
      const rows = group.rows
        .filter(({ item }) => !regionFilter || normalizeListingRegion(item.region) === regionFilter)
        .filter(({ item }) => (preferences[item.item_id] ?? normalizeListingPreference(item.listing_preference)) !== 'not_interested')
        .sort((left, right) => compareListingRows(left, right, sortMode));

      if (!rows.length) {
        return null;
      }

      return {
        ...group,
        rows,
        countLabel: regionFilter ? `${rows.length}/${group.rows.length} 个` : group.countLabel,
      };
    })
    .filter((group): group is ListingGroup => group !== null);
}

export function compareListingRows(left: ListingRow, right: ListingRow, sortMode: ListingSortMode): number {
  if (sortMode === 'latest') {
    return listingTimestamp(right) - listingTimestamp(left);
  }
  return left.item.price - right.item.price;
}

export function listingTimestamp(row: ListingRow): number {
  if (!row.item.last_seen_at) {
    return 0;
  }
  const timestamp = new Date(row.item.last_seen_at).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function normalizeListingRegion(region: string | null | undefined): string {
  return String(region ?? '').trim();
}

export function normalizeListingPreference(value: string | null | undefined): ListingPreferenceValue | undefined {
  return value === 'interested' || value === 'not_interested' ? value : undefined;
}
