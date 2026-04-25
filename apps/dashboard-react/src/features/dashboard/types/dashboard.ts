import type { z } from 'zod';

import {
  calibrationDataSchema,
  filterFieldSchema,
  filterOptionSchema,
  filtersDataSchema,
  focusCardSchema,
  focusDataSchema,
  heroDataSchema,
  insightsDataSchema,
  itemSchema,
  itemsDataSchema,
  pricingDataSchema,
  pricingRowSchema,
  trendCardSchema,
} from '../api/dashboardSchemas';

export type FilterOption = z.infer<typeof filterOptionSchema>;
export type FilterField = z.infer<typeof filterFieldSchema>;
export type FiltersData = z.infer<typeof filtersDataSchema>;
export type HeroData = z.infer<typeof heroDataSchema>;
export type PricingRow = z.infer<typeof pricingRowSchema>;
export type PricingData = z.infer<typeof pricingDataSchema>;
export type Item = z.infer<typeof itemSchema>;
export type ItemsData = z.infer<typeof itemsDataSchema>;
export type FocusCard = z.infer<typeof focusCardSchema>;
export type FocusData = z.infer<typeof focusDataSchema>;
export type TrendCard = z.infer<typeof trendCardSchema>;
export type InsightsData = z.infer<typeof insightsDataSchema>;
export type CalibrationData = z.infer<typeof calibrationDataSchema>;

export type QueryState = {
  categoryCode: string;
  productLabel: string;
  specLabel: string;
  display_type: string;
  case_size_mm: string;
  is_solar: string;
  chip_family: string;
  screen_size_in: string;
  memory_gb: string;
  storage_gb: string;
  pricingScope: 'actionable' | 'all';
  pricingFreshnessDays: string;
};

export type DashboardSectionMap = {
  hero: HeroData;
  filters: FiltersData;
  pricing: PricingData;
  items: ItemsData;
  focus: FocusData;
  insights: InsightsData;
  calibration: CalibrationData;
};

export type DashboardSectionName = keyof DashboardSectionMap;

export type ReferenceTab = 'trend' | 'calibration';

export type ListingDecision = {
  kind: 'buy' | 'watch' | 'market' | 'high' | 'neutral';
  label: string;
  note: string;
  deltaLabel: string;
  deltaKind: 'profit' | 'watch' | 'market' | 'loss' | 'muted';
};

export type ListingRow = {
  item: Item;
  decision: ListingDecision;
};

export type ListingGroup = {
  key: ListingDecision['kind'];
  title: string;
  countLabel: string;
  rows: ListingRow[];
};

export type DashboardPrimaryState = {
  hero: HeroData | null;
  filters: FiltersData | null;
  pricing: PricingData | null;
  items: ItemsData | null;
  focus: FocusData | null;
  loading: boolean;
  error: string | null;
};

export type DashboardReferenceState = {
  insights: InsightsData | null;
  calibration: CalibrationData | null;
};

export type DashboardQueryUpdater = QueryState | ((current: QueryState) => QueryState);
