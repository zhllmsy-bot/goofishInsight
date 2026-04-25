import { useEffect } from 'react';

import { extractProductOptions, getFilterField, resetTemplateQueryFilters, TEMPLATE_FILTER_KEYS } from '../lib/selectors';
import type { FiltersData, QueryState } from '../types/dashboard';

type Options = {
  filters: FiltersData | null;
  query: QueryState;
  setQuery: (updater: (current: QueryState) => QueryState) => void;
};

export function useDashboardStateGuards(options: Options): void {
  const { filters, query, setQuery } = options;
  const {
    categoryCode,
    productLabel,
    specLabel,
    display_type,
    case_size_mm,
    is_solar,
    chip_family,
    screen_size_in,
    memory_gb,
    storage_gb,
  } = query;

  useEffect(() => {
    if (!filters) {
      return;
    }

    const templateSelectionValues = {
      display_type,
      case_size_mm,
      is_solar,
      chip_family,
      screen_size_in,
      memory_gb,
      storage_gb,
    } as const;

    if (filters.selected_category_code && categoryCode && filters.selected_category_code !== categoryCode) {
      return;
    }

    if (!categoryCode) {
      const firstCategory = filters.available_categories?.[0];
      if (firstCategory) {
        setQuery((previous) => ({
          ...resetTemplateQueryFilters(previous),
          categoryCode: firstCategory,
          productLabel: '',
          specLabel: '',
        }));
      }
      return;
    }

    const productOptions = extractProductOptions(filters);
    if (productLabel && productOptions.length && !productOptions.some((option) => option.value === productLabel)) {
      setQuery((previous) => ({
        ...resetTemplateQueryFilters(previous),
        productLabel: '',
        specLabel: '',
      }));
      return;
    }

    const hasTemplateSelection = TEMPLATE_FILTER_KEYS.some((key) => templateSelectionValues[key]);

    if (!productLabel && (specLabel || hasTemplateSelection)) {
      setQuery((previous) => ({
        ...resetTemplateQueryFilters(previous),
        specLabel: '',
      }));
      return;
    }

    const specField = getFilterField(filters.visible_filter_fields, 'spec_label');
    if (specLabel && specField?.options?.length && !specField.options.some((option) => option.value === specLabel)) {
      setQuery((previous) => ({
        ...previous,
        specLabel: '',
      }));
      return;
    }

    if (hasTemplateSelection) {
      const hasInvalidTemplateValue = TEMPLATE_FILTER_KEYS.some((key) => {
        const currentValue = templateSelectionValues[key];
        if (!currentValue) {
          return false;
        }

        const field = getFilterField(filters.visible_filter_fields, key);
        if (!field?.options?.length) {
          return true;
        }

        return !field.options.some((option) => option.value === currentValue);
      });

      if (hasInvalidTemplateValue) {
        setQuery((previous) => resetTemplateQueryFilters(previous));
      }
    }
  }, [
    case_size_mm,
    categoryCode,
    chip_family,
    display_type,
    filters,
    is_solar,
    memory_gb,
    productLabel,
    screen_size_in,
    setQuery,
    specLabel,
    storage_gb,
  ]);
}
