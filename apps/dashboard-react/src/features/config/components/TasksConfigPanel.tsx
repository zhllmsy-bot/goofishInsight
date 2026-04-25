import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { formatRelative } from '../../dashboard/lib/formatters';
import { useCategoryConfigs, useTaskConfigs, useUpsertTaskConfig } from '../hooks/useConfigData';
import type { TaskConfigItem } from '../api/configSchemas';

type FeedbackState = {
  tone: 'neutral' | 'success' | 'error' | 'pending';
  message: string;
};

export function TasksConfigPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [operatorId, setOperatorId] = useState('admin');
  const [feedback, setFeedback] = useState<FeedbackState>({
    tone: 'neutral',
    message: '选择左侧任务查看详情，或直接操作保存。',
  });

  const categoriesQuery = useCategoryConfigs();
  const tasksQuery = useTaskConfigs({
    status: statusFilter || undefined,
    categoryCode: categoryFilter || undefined,
  });
  const upsertMutation = useUpsertTaskConfig();

  const tasks = tasksQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];
  const selectedItem = tasks.find((t) => t.id === selectedId) ?? tasks[0] ?? null;

  const handleUpsert = async (apply: boolean) => {
    if (!selectedItem) return;
    setFeedback({ tone: 'pending', message: apply ? '正在正式保存...' : '正在预演保存...' });
    try {
      const payload = buildTaskPayload(selectedItem);
      const result = await upsertMutation.mutateAsync({ operatorId, payload, apply });
      setFeedback({
        tone: 'success',
        message: apply
          ? `正式保存完成：${result.task?.taskKey ?? '-'}`
          : `预演完成：${result.changes?.length ?? 0} 项变更`,
      });
      if (apply) {
        void queryClient.invalidateQueries({ queryKey: ['config', 'tasks'] });
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
            <p className="eyebrow">Tasks</p>
            <h3>采集任务</h3>
          </div>
          <span className="soft-pill">{tasks.length} 项</span>
        </div>
        <div className="config-filter-bar">
          <label className="config-filter-field">
            <span>Status</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">全部</option>
              <option value="active">active</option>
              <option value="paused">paused</option>
              <option value="disabled">disabled</option>
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
              void queryClient.invalidateQueries({ queryKey: ['config', 'tasks'] });
            }}
          >
            刷新
          </button>
        </div>
        {tasksQuery.isLoading && !tasksQuery.data ? (
          <p className="config-empty-state">正在载入任务配置...</p>
        ) : tasks.length === 0 ? (
          <p className="config-empty-state">暂无任务配置</p>
        ) : (
          <div className="config-list-scroll">
            {tasks.map((item) => (
              <button
                className={`config-list-card ${item.id === (selectedItem?.id ?? null) ? 'is-active' : ''}`}
                key={item.id ?? item.taskKey ?? Math.random()}
                type="button"
                onClick={() => setSelectedId(item.id ?? null)}
              >
                <span className="config-list-card-title">{item.displayName ?? item.taskKey ?? '-'}</span>
                <div className="config-list-card-meta">
                  <span className={`soft-pill ${item.status === 'active' ? 'is-accent' : ''}`}>
                    {item.status ?? '-'}
                  </span>
                  {item.categoryCode ? (
                    <span className="soft-pill">{item.categoryCode}</span>
                  ) : null}
                  <span className="soft-pill">{(item.queries ?? []).length} queries</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </article>

      <article className="panel">
        <div className="panel-header tight">
          <div>
            <p className="eyebrow">Task Detail</p>
            <h3>{selectedItem?.displayName ?? selectedItem?.taskKey ?? '任务详情'}</h3>
          </div>
        </div>
        {selectedItem ? (
          <div className="config-detail-section">
            <dl className="config-detail-fact-grid">
              <FactItem label="Task Key" value={selectedItem.taskKey} />
              <FactItem label="Display Name" value={selectedItem.displayName} />
              <FactItem label="Task Type" value={selectedItem.taskType} />
              <FactItem label="Profile Key" value={selectedItem.profileKey} />
              <FactItem label="Parallel Tabs" value={String(selectedItem.parallelTabs ?? '-')} />
              <FactItem label="Paging Limit" value={String(selectedItem.pagingLimit ?? '-')} />
              <FactItem label="Status" value={selectedItem.status} />
              <FactItem label="Category" value={selectedItem.categoryCode} />
              <FactItem label="Business Domain" value={selectedItem.businessDomain} />
              <FactItem label="Updated" value={formatRelative(selectedItem.updatedAt)} />
            </dl>

            {(selectedItem.queries ?? []).length > 0 ? (
              <details open>
                <summary>Queries ({(selectedItem.queries ?? []).length})</summary>
                <pre className="item-detail-raw-block">
                  {JSON.stringify(selectedItem.queries, null, 2)}
                </pre>
              </details>
            ) : null}

            {(selectedItem.brandLexicon ?? []).length > 0 ||
            (selectedItem.modelLexicon ?? []).length > 0 ||
            (selectedItem.configLexicon ?? []).length > 0 ? (
              <details>
                <summary>Lexicons</summary>
                <div className="config-detail-section">
                  {(selectedItem.brandLexicon ?? []).length > 0 ? (
                    <div>
                      <p className="eyebrow">Brand Lexicon ({(selectedItem.brandLexicon ?? []).length})</p>
                      <div className="pill-row">
                        {(selectedItem.brandLexicon ?? []).map((term) => (
                          <span className="soft-pill" key={term}>{term}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {(selectedItem.modelLexicon ?? []).length > 0 ? (
                    <div>
                      <p className="eyebrow">Model Lexicon ({(selectedItem.modelLexicon ?? []).length})</p>
                      <div className="pill-row">
                        {(selectedItem.modelLexicon ?? []).map((term) => (
                          <span className="soft-pill" key={term}>{term}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {(selectedItem.configLexicon ?? []).length > 0 ? (
                    <div>
                      <p className="eyebrow">Config Lexicon ({(selectedItem.configLexicon ?? []).length})</p>
                      <div className="pill-row">
                        {(selectedItem.configLexicon ?? []).map((term) => (
                          <span className="soft-pill" key={term}>{term}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
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
          <p className="config-empty-state">先在左侧选择一个任务查看详情。</p>
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

function buildTaskPayload(item: TaskConfigItem): Record<string, unknown> {
  return {
    id: item.id,
    taskKey: item.taskKey,
    displayName: item.displayName,
    taskType: item.taskType,
    profileKey: item.profileKey,
    parallelTabs: item.parallelTabs,
    pagingLimit: item.pagingLimit,
    status: item.status,
    categoryCode: item.categoryCode,
    categoryId: item.categoryId,
    businessDomain: item.businessDomain,
    queries: item.queries,
    brandLexicon: item.brandLexicon,
    modelLexicon: item.modelLexicon,
    configLexicon: item.configLexicon,
  };
}
