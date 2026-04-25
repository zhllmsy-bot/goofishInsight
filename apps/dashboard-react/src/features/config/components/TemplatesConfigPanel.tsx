import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { formatRelative } from '../../dashboard/lib/formatters';
import { useCategoryConfigs, useTemplateConfigs, useUpsertTemplateConfig } from '../hooks/useConfigData';
import { previewTemplateConfigDiff } from '../api/configApi';
import type { TemplateConfigItem } from '../api/configSchemas';

type FeedbackState = {
  tone: 'neutral' | 'success' | 'error' | 'pending';
  message: string;
};

export function TemplatesConfigPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [operatorId, setOperatorId] = useState('admin');
  const [diffResult, setDiffResult] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState>({
    tone: 'neutral',
    message: '选择左侧模板查看详情，或直接操作保存。',
  });

  const categoriesQuery = useCategoryConfigs();
  const templatesQuery = useTemplateConfigs({
    status: statusFilter || undefined,
    categoryCode: categoryFilter || undefined,
  });
  const upsertMutation = useUpsertTemplateConfig();

  const templates = templatesQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];
  const selectedItem = templates.find((t) => t.id === selectedId) ?? templates[0] ?? null;

  const handleUpsert = async (apply: boolean) => {
    if (!selectedItem) return;
    setFeedback({ tone: 'pending', message: apply ? '正在正式保存...' : '正在预演保存...' });
    try {
      const payload = buildTemplatePayload(selectedItem);
      const result = await upsertMutation.mutateAsync({ operatorId, payload, apply });
      setFeedback({
        tone: 'success',
        message: apply
          ? `正式保存完成：${result.template?.id ?? '-'}`
          : `预演完成：${result.changes?.length ?? 0} 项变更`,
      });
      if (apply) {
        void queryClient.invalidateQueries({ queryKey: ['config', 'templates'] });
      }
    } catch (error) {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '保存失败',
      });
    }
  };

  const handleDiffPreview = async () => {
    if (!selectedItem) return;
    setFeedback({ tone: 'pending', message: '正在预览差异...' });
    try {
      const result = await previewTemplateConfigDiff(buildTemplatePayload(selectedItem));
      setDiffResult(result.summary ?? JSON.stringify(result.diff, null, 2));
      setFeedback({ tone: 'success', message: '差异预览已生成。' });
    } catch (error) {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '差异预览失败',
      });
    }
  };

  return (
    <div className="config-panel-grid">
      <article className="panel">
        <div className="panel-header tight">
          <div>
            <p className="eyebrow">Templates</p>
            <h3>模板列表</h3>
          </div>
          <span className="soft-pill">{templates.length} 项</span>
        </div>
        <div className="config-filter-bar">
          <label className="config-filter-field">
            <span>Status</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">全部</option>
              <option value="PUBLISHED">PUBLISHED</option>
              <option value="DRAFT">DRAFT</option>
              <option value="RETIRED">RETIRED</option>
            </select>
          </label>
          <label className="config-filter-field">
            <span>Category</span>
            <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
              <option value="">全部大类</option>
              {categories.map((c) => (
                <option key={c.code ?? c.id} value={c.code ?? ''}>
                  {c.name ?? c.code ?? '-'}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ['config', 'templates'] });
            }}
          >
            刷新
          </button>
        </div>
        {templatesQuery.isLoading && !templatesQuery.data ? (
          <p className="config-empty-state">正在载入模板配置...</p>
        ) : templates.length === 0 ? (
          <p className="config-empty-state">暂无模板配置</p>
        ) : (
          <div className="config-list-scroll">
            {templates.map((item) => (
              <button
                className={`config-list-card ${item.id === (selectedItem?.id ?? null) ? 'is-active' : ''}`}
                key={item.id ?? Math.random()}
                type="button"
                onClick={() => setSelectedId(item.id ?? null)}
              >
                <span className="config-list-card-title">
                  {item.categoryCode ?? '-'} v{item.version ?? 1}
                </span>
                <div className="config-list-card-meta">
                  <span className={`soft-pill ${item.status === 'PUBLISHED' ? 'is-accent' : ''}`}>
                    {item.status ?? '-'}
                  </span>
                  <span className="soft-pill">{(item.items ?? []).length} 属性</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </article>

      <article className="panel">
        <div className="panel-header tight">
          <div>
            <p className="eyebrow">Template Detail</p>
            <h3>{selectedItem ? `${selectedItem.categoryCode ?? '-'} v${selectedItem.version ?? 1}` : '模板详情'}</h3>
          </div>
        </div>
        {selectedItem ? (
          <div className="config-detail-section">
            <dl className="config-detail-fact-grid">
              <FactItem label="ID" value={selectedItem.id} />
              <FactItem label="Category" value={selectedItem.categoryCode} />
              <FactItem label="Version" value={String(selectedItem.version ?? '-')} />
              <FactItem label="Status" value={selectedItem.status} />
              <FactItem label="Prompt Profile" value={selectedItem.promptProfile} />
              <FactItem label="Effective At" value={selectedItem.effectiveAt} />
              <FactItem label="Published By" value={selectedItem.publishedBy} />
              <FactItem label="Updated" value={formatRelative(selectedItem.updatedAt)} />
            </dl>

            {(selectedItem.items ?? []).length > 0 ? (
              <details open>
                <summary>Template Items ({(selectedItem.items ?? []).length})</summary>
                <pre className="item-detail-raw-block">
                  {JSON.stringify(selectedItem.items, null, 2)}
                </pre>
              </details>
            ) : null}

            {diffResult ? (
              <details>
                <summary>差异预览</summary>
                <pre className="item-detail-raw-block">{diffResult}</pre>
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
                onClick={() => void handleDiffPreview()}
                disabled={upsertMutation.isPending}
              >
                预览差异
              </button>
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
          <p className="config-empty-state">先在左侧选择一个模板查看详情。</p>
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

function buildTemplatePayload(item: TemplateConfigItem): Record<string, unknown> {
  return {
    id: item.id,
    categoryId: item.categoryId,
    categoryCode: item.categoryCode,
    version: item.version,
    status: item.status,
    promptProfile: item.promptProfile,
    items: item.items,
    effectiveAt: item.effectiveAt,
    publishedBy: item.publishedBy,
  };
}
