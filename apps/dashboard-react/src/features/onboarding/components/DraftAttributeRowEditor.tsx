import { useCallback } from 'react';
import type { DraftAttributeRow } from '../utils/onboardingUtils';
import { suggestAttributeCode, formatOptionLines } from '../utils/onboardingUtils';

type DraftAttributeRowProps = {
  row: DraftAttributeRow;
  index: number;
  onChange: (index: number, update: Partial<DraftAttributeRow>) => void;
};

function displaySampleValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '-';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

export function DraftAttributeRowEditor({ row, index, onChange }: DraftAttributeRowProps) {
  const handleFieldChange = useCallback(
    (field: keyof DraftAttributeRow, value: unknown) => {
      const update: Partial<DraftAttributeRow> = { [field]: value };
      if (field === 'name') {
        const newName = String(value || '');
        update.suggestedCode = suggestAttributeCode(newName, row.code);
      }
      if (field === 'dataType') {
        const newType = String(value || '').toUpperCase();
        if (newType === 'ENUM' && !row.optionsText.trim()) {
          const sourceOptions = row.options.length ? row.options : (row.sampleValues.map((v, i) => ({
            optionCode: String(v).trim().toLowerCase().replaceAll(/[^a-z0-9]+/g, '_').slice(0, 48) || `option_${i + 1}`,
            optionName: String(v),
            sortNo: (i + 1) * 10,
            status: 'ACTIVE',
          })));
          update.optionsText = formatOptionLines(sourceOptions);
        }
      }
      onChange(index, update);
    },
    [index, row, onChange],
  );

  const handleApplyCodeSuggestion = useCallback(() => {
    onChange(index, { code: row.suggestedCode });
  }, [index, row.suggestedCode, onChange]);

  const handleFillEnumFromSamples = useCallback(() => {
    const sourceOptions = row.options.length ? row.options : (row.sampleValues.map((v, i) => ({
      optionCode: String(v).trim().toLowerCase().replaceAll(/[^a-z0-9]+/g, '_').slice(0, 48) || `option_${i + 1}`,
      optionName: String(v),
      sortNo: (i + 1) * 10,
      status: 'ACTIVE',
    })));
    onChange(index, { optionsText: formatOptionLines(sourceOptions) });
  }, [index, row, onChange]);

  return (
    <article className={`onboarding-draft-row ${row.enabled ? '' : 'is-disabled'}`}>
      <div className="onboarding-draft-row-head">
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.enabled}
            onChange={(event) => {
              handleFieldChange('enabled', event.target.checked);
            }}
          />
          <span>启用属性</span>
        </label>
        <div className="pill-row">
          <span className="soft-pill">命中 {row.observedCount}</span>
          <span className="soft-pill">{row.dataType}</span>
          <span className="soft-pill">{row.valueScope}</span>
          {row.profileSuggested ? <span className="soft-pill is-warning">Profile</span> : null}
        </div>
      </div>

      <div className="onboarding-draft-row-grid">
        <label className="onboarding-field-react">
          <span>Code</span>
          <input
            type="text"
            value={row.code}
            onChange={(event) => {
              handleFieldChange('code', event.target.value);
            }}
          />
          <span className="draft-helper">建议 {suggestAttributeCode(row.name, row.code)}</span>
          <button
            className="secondary-button small-button"
            type="button"
            onClick={handleApplyCodeSuggestion}
          >
            使用建议
          </button>
        </label>
        <label className="onboarding-field-react">
          <span>Name</span>
          <input
            type="text"
            value={row.name}
            onChange={(event) => {
              handleFieldChange('name', event.target.value);
            }}
          />
        </label>
        <label className="onboarding-field-react">
          <span>Data Type</span>
          <select
            value={row.dataType}
            onChange={(event) => {
              handleFieldChange('dataType', event.target.value);
            }}
          >
            <option value="TEXT">TEXT</option>
            <option value="NUMBER">NUMBER</option>
            <option value="BOOLEAN">BOOLEAN</option>
            <option value="ENUM">ENUM</option>
            <option value="JSON">JSON</option>
          </select>
        </label>
        <label className="onboarding-field-react">
          <span>Value Scope</span>
          <select
            value={row.valueScope}
            onChange={(event) => {
              handleFieldChange('valueScope', event.target.value);
            }}
          >
            <option value="SPU">SPU</option>
            <option value="SKU">SKU</option>
          </select>
        </label>
        <label className="onboarding-field-react">
          <span>Unit</span>
          <input
            type="text"
            value={row.unit ?? ''}
            onChange={(event) => {
              handleFieldChange('unit', event.target.value || null);
            }}
          />
        </label>
        <label className="onboarding-field-react">
          <span>Sort No</span>
          <input
            type="number"
            min={0}
            value={row.sortNo}
            onChange={(event) => {
              handleFieldChange('sortNo', Number(event.target.value || 0));
            }}
          />
        </label>
      </div>

      {row.dataType === 'ENUM' ? (
        <div className="onboarding-draft-enum">
          <div className="onboarding-draft-enum-head">
            <span className="eyebrow">枚举选项</span>
            <button
              className="secondary-button small-button"
              type="button"
              onClick={handleFillEnumFromSamples}
            >
              用样例生成
            </button>
          </div>
          <textarea
            rows={4}
            className="draft-textarea"
            value={row.optionsText}
            onChange={(event) => {
              handleFieldChange('optionsText', event.target.value);
            }}
          />
          <p className="onboarding-hint-text">
            每行填写 <code>optionCode|optionName</code>。切到 <code>ENUM</code> 时会带着这些值一起落库。
          </p>
        </div>
      ) : null}

      <div className="onboarding-draft-row-flags">
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.isMulti}
            onChange={(event) => {
              handleFieldChange('isMulti', event.target.checked);
            }}
          />
          <span>多值</span>
        </label>
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.isRequired}
            onChange={(event) => {
              handleFieldChange('isRequired', event.target.checked);
            }}
          />
          <span>必填</span>
        </label>
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.isSale}
            onChange={(event) => {
              handleFieldChange('isSale', event.target.checked);
            }}
          />
          <span>销售属性</span>
        </label>
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.isFilter}
            onChange={(event) => {
              handleFieldChange('isFilter', event.target.checked);
            }}
          />
          <span>可筛选</span>
        </label>
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.isSearch}
            onChange={(event) => {
              handleFieldChange('isSearch', event.target.checked);
            }}
          />
          <span>可搜索</span>
        </label>
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={row.isDisplay}
            onChange={(event) => {
              handleFieldChange('isDisplay', event.target.checked);
            }}
          />
          <span>可展示</span>
        </label>
      </div>

      <div className="onboarding-draft-samples">
        <span className="eyebrow">样例值</span>
        <div className="pill-row">
          {row.sampleValues.length ? (
            row.sampleValues.map((value, i) => (
              <span className="soft-pill" key={i}>{displaySampleValue(value)}</span>
            ))
          ) : (
            <span className="soft-pill">暂无</span>
          )}
        </div>
      </div>
    </article>
  );
}
