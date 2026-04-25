import { categoryLabel } from '../lib/formatters';
import { sanitizeFilterOptions, templateQueryValue } from '../lib/selectors';
import type { FilterField, FilterOption, QueryState } from '../types/dashboard';

type SelectionPanelProps = {
  productOptions: FilterOption[];
  query: QueryState;
  specOptions: FilterOption[];
  templateFields: FilterField[];
  onProductSelect: (productLabel: string) => void;
  onSpecSelect: (specLabel: string) => void;
  onTemplateFilterSelect: (filterKey: string, value: string) => void;
};

export function SelectionPanel(props: SelectionPanelProps) {
  const comboOptions = sanitizeFilterOptions(props.productOptions);
  const specOptions = sanitizeFilterOptions(props.specOptions);
  const hasTemplateFilters = props.query.productLabel && props.templateFields.length > 0;
  const missingRequiredFieldLabels = props.templateFields
    .filter((field) => field.pricingRole === 'required' && !templateQueryValue(props.query, field.key))
    .map((field) => field.label || field.key);
  const title = `${categoryLabel(props.query.categoryCode)} 有效组合`;
  const subtitle = !props.query.productLabel
    ? '左侧先选品类，这里再点一组“品类 + 核心参数”的有效组合，右侧所有价格线、挂牌和趋势都会跟着收敛。'
    : missingRequiredFieldLabels.length
      ? `当前组合是 ${props.query.productLabel}，还差 ${missingRequiredFieldLabels.join(' / ')}，补齐后价格线会自动收窄。`
      : `当前组合是 ${props.query.productLabel}，继续按模板条件缩小价格池。`;

  return (
    <section className="panel selection-panel">
      <div className="selection-panel-copy">
        <p className="eyebrow">有效组合</p>
        <h2>{title}</h2>
        <p className="panel-subtitle">{subtitle}</p>
      </div>
      <div className="selection-panel-body">
        <div className="selection-filter-group selection-filter-group-stack">
          <div className="selection-filter-header">
            <span>组合按钮</span>
            <span className="selection-filter-role">{comboOptions.length} 个有效组合</span>
          </div>
          {comboOptions.length ? (
            <div className="selection-combo-grid" role="list" aria-label="有效参数组合">
              {comboOptions.map((option) => (
                <button
                  aria-pressed={option.value === props.query.productLabel}
                  className={`selection-combo-card ${option.value === props.query.productLabel ? 'is-active' : ''}`}
                  key={option.value}
                  type="button"
                  onClick={() => props.onProductSelect(option.value)}
                >
                  <strong>{option.label}</strong>
                  <small>{option.summaryLabel || '当前品类下可命中的有效参数组合'}</small>
                </button>
              ))}
            </div>
          ) : (
            <div className="selection-empty-state">当前品类还没有可用组合，先切别的品类看看。</div>
          )}
        </div>

        {props.query.productLabel && specOptions.length ? (
          <div className="selection-filter-group selection-filter-group-stack">
            <div className="selection-filter-header">
              <span>精确规格</span>
              <span>{props.query.productLabel}</span>
            </div>
            <div className="chip-row">
              <button
                className={`selection-chip ${!props.query.specLabel ? 'is-active' : ''}`}
                type="button"
                onClick={() => props.onSpecSelect('')}
              >
                全部规格
              </button>
              {specOptions.map((option) => (
                <button
                  className={`selection-chip ${option.value === props.query.specLabel ? 'is-active' : ''}`}
                  key={option.value}
                  type="button"
                  onClick={() => props.onSpecSelect(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {hasTemplateFilters ? (
          <div className="selection-filters">
            {props.templateFields.map((field) => {
              const currentValue = templateQueryValue(props.query, field.key);
              const options = sanitizeFilterOptions(field.options ?? []);
              if (!options.length) {
                return null;
              }
              return (
                <div className="selection-filter-group" key={field.key}>
                  <div className="selection-filter-header">
                    <span>{field.label || field.key}</span>
                    {field.pricingRole === 'required' ? <span className="selection-filter-role">核心</span> : null}
                  </div>
                  <div className="chip-row">
                    <button
                      className={`selection-chip ${!currentValue ? 'is-active' : ''}`}
                      type="button"
                      onClick={() => props.onTemplateFilterSelect(field.key, '')}
                    >
                      全部
                    </button>
                    {options.map((option) => (
                      <button
                        className={`selection-chip ${option.value === currentValue ? 'is-active' : ''}`}
                        key={`${field.key}:${option.value}`}
                        type="button"
                        onClick={() => props.onTemplateFilterSelect(field.key, option.value)}
                      >
                        {option.label || option.value || '未标注'}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </section>
  );
}
