import { LISTING_SECTION_META } from './constants';
import { formatCurrency, formatDeltaCurrency, formatNumber } from './formatters';
import type {
  FilterField,
  FilterOption,
  FiltersData,
  Item,
  ListingDecision,
  ListingGroup,
  PricingRow,
  QueryState,
} from '../types/dashboard';

export const TEMPLATE_FILTER_KEYS = [
  'display_type',
  'case_size_mm',
  'is_solar',
  'chip_family',
  'screen_size_in',
  'memory_gb',
  'storage_gb',
] as const;

type TemplateFilterKey = (typeof TEMPLATE_FILTER_KEYS)[number];

export function getFilterField(fields: FilterField[] | undefined, key: string): FilterField | null {
  return fields?.find((field) => field.key === key) ?? null;
}

export function extractProductOptions(filters: FiltersData | null | undefined): FilterOption[] {
  return sanitizeFilterOptions(getFilterField(filters?.visible_filter_fields, 'product_label')?.options ?? []);
}

export function extractTemplateFilterFields(fields: FilterField[] | undefined): FilterField[] {
  if (!fields?.length) {
    return [];
  }

  return fields
    .filter((field) => TEMPLATE_FILTER_KEYS.includes(field.key as TemplateFilterKey))
    .sort((left, right) => {
      const leftRequired = left.pricingRole === 'required' ? 0 : 1;
      const rightRequired = right.pricingRole === 'required' ? 0 : 1;
      if (leftRequired !== rightRequired) {
        return leftRequired - rightRequired;
      }
      return (
        TEMPLATE_FILTER_KEYS.indexOf(left.key as TemplateFilterKey) -
        TEMPLATE_FILTER_KEYS.indexOf(right.key as TemplateFilterKey)
      );
    });
}

export function templateQueryValue(query: QueryState, filterKey: string): string {
  if (!TEMPLATE_FILTER_KEYS.includes(filterKey as TemplateFilterKey)) {
    return '';
  }
  return query[filterKey as TemplateFilterKey];
}

export function updateTemplateQueryValue(query: QueryState, filterKey: string, value: string): QueryState {
  if (!TEMPLATE_FILTER_KEYS.includes(filterKey as TemplateFilterKey)) {
    return query;
  }
  return {
    ...query,
    [filterKey]: value,
  };
}

export function resetTemplateQueryFilters(query: QueryState): QueryState {
  return {
    ...query,
    display_type: '',
    case_size_mm: '',
    is_solar: '',
    chip_family: '',
    screen_size_in: '',
    memory_gb: '',
    storage_gb: '',
  };
}

export function sanitizeFilterOptions(options: FilterOption[]): FilterOption[] {
  const seen = new Set<string>();
  const sanitized: FilterOption[] = [];
  options.forEach((option) => {
    const value = normalizeOptionText(option.value);
    const label = normalizeOptionText(option.label) || value;
    const summaryLabel = normalizeOptionText(option.summaryLabel);
    if (!value || !label) {
      return;
    }
    const key = `${value}::${label}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    sanitized.push(summaryLabel ? { value, label, summaryLabel } : { value, label });
  });
  return sanitized;
}

function normalizeOptionText(value: unknown): string {
  return String(value ?? '').trim();
}

export function buildListingGroups(items: Item[], pricingRow: PricingRow | null): ListingGroup[] {
  const grouped = new Map<ListingDecision['kind'], Array<{ item: Item; decision: ListingDecision }>>();

  items.forEach((item) => {
    const decision = classifyListing(item.price, pricingRow);
    const bucket = grouped.get(decision.kind) ?? [];
    bucket.push({ item, decision });
    grouped.set(decision.kind, bucket);
  });

  const order: ListingDecision['kind'][] = pricingRow ? ['buy', 'watch', 'market', 'high'] : ['neutral'];
  return order
    .map((key) => {
      const rows = (grouped.get(key) ?? []).slice(0, LISTING_SECTION_META[key].max);
      if (!rows.length) {
        return null;
      }
      return {
        key,
        title: LISTING_SECTION_META[key].title,
        countLabel: `${formatNumber(grouped.get(key)?.length)} 个${LISTING_SECTION_META[key].badge}`,
        rows,
      };
    })
    .filter((group): group is ListingGroup => group !== null);
}

export function countGroupRows(groups: ListingGroup[], kind: ListingDecision['kind']): string {
  const group = groups.find((entry) => entry.key === kind);
  return group ? String(group.rows.length) : '0';
}

function classifyListing(price: number, pricingRow: PricingRow | null): ListingDecision {
  if (!pricingRow) {
    return {
      kind: 'neutral',
      label: '最新挂牌',
      note: '等待价格线',
      deltaLabel: '暂无对照',
      deltaKind: 'muted',
    };
  }

  if (price <= pricingRow.safe_buy_price) {
    return {
      kind: 'buy',
      label: '机会成立',
      note: `低于安全收货价 ${formatCurrency(pricingRow.safe_buy_price)}`,
      deltaLabel: `↓ ${formatDeltaCurrency(pricingRow.safe_buy_price - price)}`,
      deltaKind: 'profit',
    };
  }

  if (price <= pricingRow.normal_buy_price) {
    return {
      kind: 'watch',
      label: '可以谈',
      note: `已进入正常收货线 ${formatCurrency(pricingRow.normal_buy_price)}`,
      deltaLabel: `↑ ${formatDeltaCurrency(price - pricingRow.safe_buy_price)}`,
      deltaKind: 'watch',
    };
  }

  if (price <= pricingRow.market_mid_price) {
    return {
      kind: 'market',
      label: '贴盘观察',
      note: `接近市场中位价 ${formatCurrency(pricingRow.market_mid_price)}`,
      deltaLabel: '接近中位价',
      deltaKind: 'market',
    };
  }

  return {
    kind: 'high',
    label: '偏高',
    note: `高于正常收货线 ${formatCurrency(pricingRow.normal_buy_price)}`,
    deltaLabel: `↑ ${formatDeltaCurrency(price - pricingRow.normal_buy_price)}`,
    deltaKind: 'loss',
  };
}
