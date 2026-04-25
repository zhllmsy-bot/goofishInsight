import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { formatRelative } from '../../dashboard/lib/formatters';
import { useCategoryConfigs, useUpsertCategoryConfig } from '../hooks/useConfigData';
import type { CategoryConfigItem } from '../api/configSchemas';

type FeedbackState = {
  tone: 'neutral' | 'success' | 'error' | 'pending';
  message: string;
};

export function CategoriesConfigPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [operatorId, setOperatorId] = useState('admin');
  const [feedback, setFeedback] = useState<FeedbackState>({
    tone: 'neutral',
    message: '选择左侧大类查看详情，或直接操作保存。',
  });

  const categoriesQuery = useCategoryConfigs({ status: statusFilter || undefined });
  const upsertMutation = useUpsertCategoryConfig();

  const categories = categoriesQuery.data ?? [];
  const selectedItem = categories.find((c) => c.id === selectedId) ?? categories[0] ?? null;

  const handleUpsert = async (apply: boolean) => {
    if (!selectedItem) return;
    setFeedback({ tone: 'pending', message: apply ? '正在正式保存...' : '正在预演保存...' });
    try {
      const payload = buildCategoryPayload(selectedItem);
      const result = await upsertMutation.mutateAsync({ operatorId, payload, apply });
      setFeedback({
        tone: 'success',
        message: apply
          ? `正式保存完成：${result.category?.code ?? '-'}`
          : `预演完成：${result.changes?.length ?? 0} 项变更`,
      });
      if (apply) {
        void queryClient.invalidateQueries({ queryKey: ['config', 'categories'] });
      }
    } catch (error) {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '保存失败',
      });
    }
  };

  return (
    <div className="config-panel-grid">
      <article className="panel">
        <div className="panel-header tight">
          <div>
            <p className="eyebrow">Category Tree</p>
            <h3>大类列表</h3>
          </div>
          <span className="soft-pill">{categories.length} 项</span>
        </div>
        <div className="config-filter-bar">
          <label className="config-filter-field">
            <span>Status</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">全部</option>
              <option value="ACTIVE">ACTIVE</option>
              <option value="INACTIVE">INACTIVE</option>
              <option value="ARCHIVED">ARCHIVED</option>
            </select>
          </label>
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ['config', 'categories'] });
            }}
          >
            刷新
          </button>
        </div>
        {categoriesQuery.isLoading && !categoriesQuery.data ? (
          <p className="config-empty-state">正在载入大类配置...</p>
        ) : categories.length === 0 ? (
          <p className="config-empty-state">暂无大类配置</p>
        ) : (
          <div className="config-list-scroll">
            {categories.map((item, index) => (
              <button
                className={`config-list-card ${item.id === (selectedItem?.id ?? null) ? 'is-active' : ''}`}
                key={item.id ?? item.code ?? `category-${index}`}
                type="button"
                onClick={() => setSelectedId(item.id ?? null)}
              >
                <span className="config-list-card-title">{item.name ?? item.code ?? '-'}</span>
                <div className="config-list-card-meta">
                  <span className={`soft-pill ${item.status === 'ACTIVE' ? 'is-accent' : ''}`}>
                    {item.status ?? '-'}
                  </span>
                  {item.activeTemplateId ? (
                    <span className="soft-pill">已绑定模板</span>
                  ) : (
                    <span className="soft-pill is-warning">未绑定模板</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </article>

      <article className="panel">
        <div className="panel-header tight">
          <div>
            <p className="eyebrow">Category Runtime</p>
            <h3>{selectedItem?.name ?? selectedItem?.code ?? '大类详情'}</h3>
          </div>
        </div>
        {selectedItem ? (
          <div className="config-detail-section">
            <dl className="config-detail-fact-grid">
              <FactItem label="Code" value={selectedItem.code} />
              <FactItem label="Name" value={selectedItem.name} />
              <FactItem label="Path" value={selectedItem.path} />
              <FactItem label="Level" value={String(selectedItem.level ?? '-')} />
              <FactItem label="Status" value={selectedItem.status} />
              <FactItem label="Runtime Status" value={selectedItem.runtimeStatus} />
              <FactItem label="Prompt Profile" value={selectedItem.promptProfile} />
              <FactItem label="Active Template" value={selectedItem.activeTemplateId ?? '未绑定'} />
              <FactItem label="Extractor" value={selectedItem.extractorProfile} />
              <FactItem label="Validator" value={selectedItem.validatorProfile} />
              <FactItem label="LLM Provider" value={selectedItem.llmProviderOverride} />
              <FactItem label="LLM Model" value={selectedItem.llmModelOverride} />
              <FactItem label="Updated" value={formatRelative(selectedItem.updatedAt)} />
            </dl>

            {selectedItem.runtimeMetadata && Object.keys(selectedItem.runtimeMetadata).length > 0 ? (
              <details>
                <summary>Runtime Metadata (JSON)</summary>
                <pre className="item-detail-raw-block">
                  {JSON.stringify(selectedItem.runtimeMetadata, null, 2)}
                </pre>
              </details>
            ) : null}

            <div className="config-filter-bar">
              <label className="config-filter-field">
                <span>Operator</span>
                <input value={operatorId} onChange={(e) => setOperatorId(e.target.value)} />
              </label>
            </div>
            <div className="config-action-row">
              <button
                className="secondary-button"
                type="button"
                onClick={() => void handleUpsert(false)}
                disabled={upsertMutation.isPending}
              >
                预演保存
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => void handleUpsert(true)}
                disabled={upsertMutation.isPending}
              >
                正式保存
              </button>
            </div>
            <p className={`config-feedback is-${feedback.tone}`}>{feedback.message}</p>
          </div>
        ) : (
          <p className="config-empty-state">先在左侧选择一个大类查看详情。</p>
        )}
      </article>
    </div>
  );
}

function FactItem(props: { label: string; value: string | null | undefined }) {
  return (
    <div className="config-detail-fact">
      <dt>{props.label}</dt>
      <dd>{props.value || '-'}</dd>
    </div>
  );
}

function buildCategoryPayload(item: CategoryConfigItem): Record<string, unknown> {
  return {
    id: item.id,
    code: item.code,
    name: item.name,
    path: item.path,
    level: item.level,
    status: item.status,
    promptProfile: item.promptProfile,
    activeTemplateId: item.activeTemplateId,
    extractorProfile: item.extractorProfile,
    validatorProfile: item.validatorProfile,
    llmProviderOverride: item.llmProviderOverride,
    llmModelOverride: item.llmModelOverride,
    runtimeStatus: item.runtimeStatus,
    runtimeMetadata: item.runtimeMetadata,
  };
}
