import { useMemo, useState, useCallback } from 'react';
import type { OnboardingDraft } from '../api/onboardingSchemas';
import { formatPercent } from '../../dashboard/lib/formatters';
import { initializeDraftAttributeRows, parseDraftOptionsText, type DraftAttributeRow } from '../utils/onboardingUtils';
import { ReuseSuggestion } from './ReuseSuggestion';
import { DraftAttributeRowEditor } from './DraftAttributeRowEditor';

type DraftEditorProps = {
  draft: OnboardingDraft;
  onBuildPersistPayload: (payload: Record<string, unknown>) => void;
};

type CategoryMeta = {
  requestId: string;
  categoryCode: string;
  categoryName: string;
  categoryPath: string;
  categoryLevel: number;
  templateVersion: number;
};

function readString(value: unknown, fallback: string = ''): string {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  return fallback;
}

function readNumber(value: unknown, fallback: number = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

export function DraftEditor({ draft, onBuildPersistPayload }: DraftEditorProps) {
  const analysis = draft.analysis ?? null;
  const payload = draft.payload ?? null;
  const reuseSuggestion = draft.reuseSuggestion ?? payload?.reuseSuggestion ?? null;

  const catalog = payload?.catalog;
  const category = catalog?.category;
  const template = catalog?.template;
  const catalogAttributes = useMemo(() => catalog?.attributes ?? [], [catalog?.attributes]);
  const templateItems = useMemo(() => template?.items ?? [], [template?.items]);

  const initialRows = useMemo(
    () => initializeDraftAttributeRows(analysis, catalogAttributes, templateItems),
    [analysis, catalogAttributes, templateItems],
  );

  const [rows, setRows] = useState<DraftAttributeRow[]>(initialRows);
  const [categoryMeta, setCategoryMeta] = useState<CategoryMeta>({
    requestId: readString(payload?.requestId, 'xianyu-onboarding-request'),
    categoryCode: readString(category?.code),
    categoryName: readString(category?.name),
    categoryPath: readString(category?.path),
    categoryLevel: readNumber(category?.level, 2),
    templateVersion: readNumber(template?.version, 1),
  });
  const [reuseEnabled, setReuseEnabled] = useState(true);

  const handleRowChange = useCallback((index: number, update: Partial<DraftAttributeRow>) => {
    setRows((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...update };
      return next;
    });
  }, []);

  const selection = draft.selection ?? {};
  const matchedProfiles = analysis?.categoryHints ?? [];
  const sampleTitles = analysis?.sampleTitles ?? [];

  const activeRows = rows.filter((row) => row.enabled && row.code && row.name);
  const canPersist = activeRows.length > 0;

  const buildPersistPayload = useCallback((): Record<string, unknown> => {
    if (!payload) {
      throw new Error('请先生成草稿');
    }
    if (!activeRows.length) {
      throw new Error('至少保留一个有效属性');
    }

    if (reuseEnabled && reuseSuggestion?.category?.id && reuseSuggestion?.template?.id) {
      return {
        requestId: categoryMeta.requestId,
        categoryId: readString(reuseSuggestion.category.id),
        templateId: readString(reuseSuggestion.template.id),
        mappings: (payload.mappings ?? []).map((mapping) => ({ ...mapping })),
      };
    }

    const sortedRows = [...activeRows].sort(
      (left, right) => left.sortNo - right.sortNo || left.code.localeCompare(right.code, 'zh-CN'),
    );

    return {
      requestId: categoryMeta.requestId,
      catalog: {
        requestId: categoryMeta.requestId,
        category: {
          code: categoryMeta.categoryCode || readString(category?.code),
          name: categoryMeta.categoryName || readString(category?.name),
          path: categoryMeta.categoryPath || readString(category?.path),
          level: categoryMeta.categoryLevel || readNumber(category?.level, 2),
          status: readString(category?.status, 'ACTIVE'),
        },
        attributes: sortedRows.map((row) => ({
          scopeType: 'PLATFORM',
          scopeId: 'platform',
          code: row.code,
          name: row.name,
          dataType: row.dataType,
          valueScope: row.valueScope,
          isMulti: row.isMulti,
          unit: row.unit || null,
          status: 'DRAFT',
          options: row.dataType === 'ENUM' ? parseDraftOptionsText(row.optionsText) : [],
        })),
        template: {
          version: categoryMeta.templateVersion || readNumber(template?.version, 1),
          status: readString(template?.status, 'DRAFT'),
          items: sortedRows.map((row) => ({
            attributeCode: row.code,
            isRequired: row.isRequired,
            isSale: row.isSale,
            isFilter: row.isFilter,
            isSearch: row.isSearch,
            isDisplay: row.isDisplay,
            sortNo: row.sortNo,
          })),
        },
      },
      mappings: (payload.mappings ?? []).map((mapping) => ({ ...mapping })),
    };
  }, [payload, activeRows, reuseEnabled, reuseSuggestion, categoryMeta, category, template]);

  const handlePreview = useCallback(() => {
    const persistPayload = buildPersistPayload();
    onBuildPersistPayload(persistPayload);
  }, [buildPersistPayload, onBuildPersistPayload]);

  return (
    <div className="onboarding-draft-summary-react">
      <div className="pill-row">
        <span className="soft-pill">样本 {analysis?.sampleCount ?? '-'}</span>
        <span className="soft-pill">Raw {readString(selection.xianyuCCatId || selection.xianyuCatId || selection.xianyuTbCatId)}</span>
        <span className="soft-pill is-accent">Mappings {(payload?.mappings ?? []).length}</span>
      </div>

      <p className="onboarding-hint-text">
        这份草稿来自当前 queue 项的真实样本。你可以调整分类元数据、勾选有效属性，并在落库前先做 dry-run 预演。
      </p>

      {matchedProfiles.length ? (
        <div className="pill-row">
          {matchedProfiles.map((profile, i) => (
            <span className="soft-pill" key={i}>
              {String(profile.name ?? '')} · {formatPercent(Number(profile.confidence ?? 0))}
            </span>
          ))}
        </div>
      ) : null}

      {sampleTitles.length ? (
        <div className="pill-row">
          {sampleTitles.map((title, i) => (
            <span className="soft-pill" key={i}>{title}</span>
          ))}
        </div>
      ) : null}

      <ReuseSuggestion
        reuseSuggestion={reuseSuggestion}
        analysis={analysis}
        reuseEnabled={reuseEnabled}
        onReuseToggle={setReuseEnabled}
      />

      <div className="onboarding-draft-meta">
        <label className="onboarding-field-react">
          <span>Request ID</span>
          <input
            type="text"
            value={categoryMeta.requestId}
            onChange={(event) => {
              setCategoryMeta((prev) => ({ ...prev, requestId: event.target.value }));
            }}
          />
        </label>
        <label className="onboarding-field-react">
          <span>Category Code</span>
          <input
            type="text"
            value={categoryMeta.categoryCode}
            onChange={(event) => {
              setCategoryMeta((prev) => ({ ...prev, categoryCode: event.target.value }));
            }}
          />
        </label>
        <label className="onboarding-field-react wide-field">
          <span>Category Name</span>
          <input
            type="text"
            value={categoryMeta.categoryName}
            onChange={(event) => {
              setCategoryMeta((prev) => ({ ...prev, categoryName: event.target.value }));
            }}
          />
        </label>
        <label className="onboarding-field-react wide-field">
          <span>Category Path</span>
          <input
            type="text"
            value={categoryMeta.categoryPath}
            onChange={(event) => {
              setCategoryMeta((prev) => ({ ...prev, categoryPath: event.target.value }));
            }}
          />
        </label>
        <label className="onboarding-field-react">
          <span>Level</span>
          <input
            type="number"
            min={1}
            max={9}
            value={categoryMeta.categoryLevel}
            onChange={(event) => {
              setCategoryMeta((prev) => ({ ...prev, categoryLevel: Number(event.target.value || 2) }));
            }}
          />
        </label>
        <label className="onboarding-field-react">
          <span>Template Version</span>
          <input
            type="number"
            min={1}
            max={999}
            value={categoryMeta.templateVersion}
            onChange={(event) => {
              setCategoryMeta((prev) => ({ ...prev, templateVersion: Number(event.target.value || 1) }));
            }}
          />
        </label>
      </div>

      <div className="onboarding-draft-list">
        {rows.map((row, index) => (
          <DraftAttributeRowEditor
            key={row.code || index}
            row={row}
            index={index}
            onChange={handleRowChange}
          />
        ))}
      </div>

      <div className="onboarding-draft-actions">
        <button
          className="secondary-button"
          disabled={!canPersist}
          type="button"
          onClick={() => {
            handlePreview();
          }}
        >
          预演创建
        </button>
        <button
          className="primary-button"
          disabled={!canPersist}
          type="button"
          onClick={() => {
            handlePreview();
          }}
        >
          正式创建
        </button>
      </div>
    </div>
  );
}
