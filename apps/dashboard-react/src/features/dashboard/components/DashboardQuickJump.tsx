import { useMemo, useState } from 'react';

import { categoryLabel } from '../lib/formatters';
import { resetTemplateQueryFilters } from '../lib/selectors';
import type { FilterOption, QueryState } from '../types/dashboard';

type QuickJumpOption = {
  key: string;
  label: string;
  hint: string;
  query: QueryState;
  searchText: string;
};

type DashboardQuickJumpProps = {
  availableCategories: string[];
  productsByCategory: Record<string, FilterOption[]>;
  productOptions: FilterOption[];
  query: QueryState;
  specOptions: FilterOption[];
  onJump: (query: QueryState) => void;
};

export function DashboardQuickJump(props: DashboardQuickJumpProps) {
  const [draft, setDraft] = useState('');
  const [message, setMessage] = useState('');
  const options = useMemo(() => buildQuickJumpOptions(props), [props]);
  const previewOptions = useMemo(() => {
    const normalizedDraft = normalizeQuickJumpText(draft);
    if (!normalizedDraft) {
      return options.slice(0, 4);
    }
    return options.filter((option) => quickJumpMatches(option.searchText, draft)).slice(0, 4);
  }, [draft, options]);

  function applyJump(rawValue: string): void {
    const match = options.find((option) => quickJumpMatches(option.searchText, rawValue));
    if (!match) {
      setMessage('没找到匹配项，可以试试输入完整型号或先在左侧展开品类。');
      return;
    }
    props.onJump(match.query);
    setDraft(match.label);
    setMessage(`已定位：${match.label}`);
  }

  return (
    <section className="quick-jump-panel" aria-label="型号快速定位">
      <div className="quick-jump-copy">
        <p className="eyebrow">Search</p>
        <h3>快速定位型号</h3>
      </div>
      <form
        className="quick-jump-form"
        onSubmit={(event) => {
          event.preventDefault();
          applyJump(draft);
        }}
      >
        <input
          aria-label="搜索型号或规格"
          list="dashboard-quick-jump-options"
          placeholder="输入型号、芯片、内存、硬盘..."
          type="search"
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setMessage('');
          }}
        />
        <datalist id="dashboard-quick-jump-options">
          {previewOptions.map((option) => (
            <option key={option.key} value={option.label}>
              {option.hint}
            </option>
          ))}
        </datalist>
        <button className="quick-pill is-active" type="submit">
          定位
        </button>
      </form>
      <div className="quick-jump-suggestions" aria-label="常用型号">
        {previewOptions.map((option) => (
          <button
            className="quick-jump-suggestion"
            key={option.key}
            type="button"
            onClick={() => {
              props.onJump(option.query);
              setDraft(option.label);
              setMessage(`已定位：${option.label}`);
            }}
          >
            <span>{option.label}</span>
            <small>{option.hint}</small>
          </button>
        ))}
      </div>
      {message ? <p className="quick-jump-message">{message}</p> : null}
    </section>
  );
}

export function DashboardSkeleton() {
  return (
    <section className="dashboard-skeleton" aria-label="看板加载中">
      <div className="skeleton-card skeleton-card-wide" />
      <div className="skeleton-grid">
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
    </section>
  );
}

function buildQuickJumpOptions(props: DashboardQuickJumpProps): QuickJumpOption[] {
  const options: QuickJumpOption[] = [];
  const seen = new Set<string>();
  const pushOption = (option: Omit<QuickJumpOption, 'searchText'>) => {
    if (seen.has(option.key)) {
      return;
    }
    seen.add(option.key);
    options.push({
      ...option,
      searchText: normalizeQuickJumpText(`${option.label} ${option.hint}`),
    });
  };

  for (const categoryCode of props.availableCategories) {
    const productOptions =
      categoryCode === props.query.categoryCode && props.productOptions.length
        ? props.productOptions
        : props.productsByCategory[categoryCode] ?? [];
    for (const product of productOptions) {
      pushOption({
        key: `${categoryCode}::${product.value}`,
        label: product.label,
        hint: categoryLabel(categoryCode),
        query: {
          ...resetTemplateQueryFilters(props.query),
          categoryCode,
          productLabel: product.value,
          specLabel: '',
        },
      });
    }
  }

  if (props.query.categoryCode && props.query.productLabel && props.specOptions.length) {
    for (const spec of props.specOptions) {
      pushOption({
        key: `${props.query.categoryCode}::${props.query.productLabel}::${spec.value}`,
        label: spec.label,
        hint: `${categoryLabel(props.query.categoryCode)} / ${props.query.productLabel}`,
        query: {
          ...props.query,
          specLabel: spec.value,
        },
      });
    }
  }

  return options;
}

function quickJumpMatches(searchText: string, rawValue: string): boolean {
  const normalizedValue = normalizeQuickJumpText(rawValue);
  if (!normalizedValue) {
    return false;
  }
  if (searchText.includes(normalizedValue)) {
    return true;
  }
  return rawValue
    .trim()
    .split(/\s+/)
    .map(normalizeQuickJumpText)
    .filter(Boolean)
    .every((token) => searchText.includes(token));
}

function normalizeQuickJumpText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '');
}
