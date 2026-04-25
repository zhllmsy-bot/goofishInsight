import { useMemo, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { TerminalScreen } from '../../../shared/components/TerminalScreen';
import { PageHero } from '../../../shared/components/PageHero';
import { formatPercent, formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation } from '../../dashboard/lib/urlState';
import { useDashboardUiStore } from '../../dashboard/store/dashboardUiStore';
import {
  fetchOnboardingCoverage,
  fetchOnboardingQueue,
  postOnboardingDiscovery,
  postOnboardingDraft,
  postOnboardingPersist,
  postOnboardingQueueStatus,
  postOnboardingQueueSync,
  type OnboardingFilters,
  type OnboardingQueueItem,
} from '../api/onboardingApi';
import type { OnboardingDraft } from '../api/onboardingSchemas';
import { DraftEditor } from './DraftEditor';

import '../../dashboard/styles/dashboard.css';
import '../../progress/styles/progress.css';
import '../styles/onboarding.css';

const DEFAULT_FILTERS: OnboardingFilters = {
  operatorId: 'admin',
  sourceKeyword: '',
  taskKey: 'xianyu-onboarding-discovery',
  businessDomain: '',
  profileKey: 'chrome-attached',
  discoveryPages: 1,
  status: '',
  itemScanLimit: 2000,
  includeClosed: false,
};

const DISCOVERY_KEY = ['onboarding', 'discovery'] as const;

type FeedbackState = {
  tone: 'neutral' | 'success' | 'error';
  message: string;
};

export function OnboardingPage() {
  const queryClient = useQueryClient();
  const workspaceQuery = useDashboardUiStore((state) => state.query);
  const [filters, setFilters] = useState<OnboardingFilters>(DEFAULT_FILTERS);
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState>({
    tone: 'neutral',
    message: '同步、发现、草稿生成和正式落库现在都留在 React 主壳里处理。',
  });
  const [pendingPersistPayload, setPendingPersistPayload] = useState<Record<string, unknown> | null>(null);

  const dashboardTarget = useMemo(
    () => buildWorkspaceLocation('/', workspaceQuery),
    [workspaceQuery],
  );

  const coverageQuery = useQuery({
    queryKey: ['onboarding', 'coverage', filters.sourceKeyword, filters.businessDomain, filters.itemScanLimit],
    queryFn: ({ signal }) => fetchOnboardingCoverage(filters, signal),
  });
  const queueQuery = useQuery({
    queryKey: ['onboarding', 'queue', filters.status, filters.includeClosed],
    queryFn: ({ signal }) => fetchOnboardingQueue(filters, signal),
  });

  const queueItems = queueQuery.data?.items ?? [];
  const selectedQueueItem =
    queueItems.find((item) => item.id === selectedQueueId) ??
    queueItems[0] ??
    null;

  const discoveryMutation = useMutation({
    mutationKey: DISCOVERY_KEY,
    mutationFn: () => postOnboardingDiscovery(filters),
    onSuccess: (result) => {
      setFeedback({
        tone: 'success',
        message: `发现完成：run ${result.run?.runId ?? '-'}，成功 ${result.run?.pagesSucceeded ?? 0}/${result.run?.pagesAttempted ?? 0} 页。`,
      });
    },
    onError: (error) => {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '发现失败',
      });
    },
  });

  const syncMutation = useMutation({
    mutationFn: () => postOnboardingQueueSync(filters),
    onSuccess: async (result) => {
      setFeedback({
        tone: 'success',
        message: `队列已同步：新增 ${result.createdCount ?? 0}，解决 ${result.resolvedCount ?? 0}。`,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['onboarding', 'coverage'] }),
        queryClient.invalidateQueries({ queryKey: ['onboarding', 'queue'] }),
      ]);
    },
    onError: (error) => {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '同步失败',
      });
    },
  });

  const draftMutation = useMutation({
    mutationFn: (item: OnboardingQueueItem) => postOnboardingDraft(filters, item),
    onSuccess: () => {
      setFeedback({
        tone: 'success',
        message: '草稿已生成。可以编辑属性、调整分类元数据，然后预演或正式创建。',
      });
    },
    onError: (error) => {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '草稿生成失败',
      });
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) =>
      postOnboardingQueueStatus({
        operatorId: filters.operatorId,
        queueId: selectedQueueItem?.id,
        status,
      }),
    onSuccess: async (result, status) => {
      setFeedback({
        tone: 'success',
        message: `状态已更新为 ${status}。`,
      });
      await queryClient.invalidateQueries({ queryKey: ['onboarding', 'queue'] });
      if (result.queue && typeof result.queue.id === 'string') {
        setSelectedQueueId(result.queue.id);
      }
    },
    onError: (error) => {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '状态更新失败',
      });
    },
  });

  const persistMutation = useMutation({
    mutationFn: (input: { payload: Record<string, unknown>; apply: boolean }) => {
      return postOnboardingPersist({
        operatorId: filters.operatorId,
        payload: input.payload,
        apply: input.apply,
      });
    },
    onSuccess: (result, input) => {
      setFeedback({
        tone: 'success',
        message: input.apply
          ? `正式创建完成：template ${result.templateId ?? '-'}。`
          : `Dry-run 完成：预计会写入 ${result.mappingCount ?? 0} 条映射。`,
      });
      if (input.apply) {
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ['onboarding', 'coverage'] }),
          queryClient.invalidateQueries({ queryKey: ['onboarding', 'queue'] }),
        ]);
      }
    },
    onError: (error) => {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : '落库失败',
      });
    },
  });

  const isBusy =
    coverageQuery.isFetching ||
    queueQuery.isFetching ||
    discoveryMutation.isPending ||
    syncMutation.isPending ||
    draftMutation.isPending ||
    statusMutation.isPending ||
    persistMutation.isPending;

  const handleBuildPersistPayload = useCallback(
    (payload: Record<string, unknown>) => {
      setPendingPersistPayload(payload);
      void persistMutation.mutateAsync({ payload, apply: false });
    },
    [persistMutation],
  );

  const handleApplyPersist = useCallback(() => {
    if (!pendingPersistPayload) {
      if (!draftMutation.data) {
        setFeedback({ tone: 'error', message: '请先生成草稿' });
        return;
      }
      setFeedback({ tone: 'error', message: '请先预演创建后再正式创建' });
      return;
    }
    void persistMutation.mutateAsync({ payload: pendingPersistPayload, apply: true });
  }, [pendingPersistPayload, draftMutation.data, persistMutation]);

  const draftData: OnboardingDraft | null = draftMutation.data ?? null;

  return (
    <TerminalScreen>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack progress-page onboarding-page">
            <PageHero
              eyebrow="Category Onboarding"
              title="闲鱼品类开通工作台"
              description="未映射 raw cate 的同步、发现、草稿编辑和正式落库全部在 React 主壳完成，主运营面不再分叉到旧模板页。"
              meta={
                <>
                  <span className="soft-pill">{queueItems.length} 个 queue 项</span>
                  <span className="soft-pill is-accent">
                    coverage {formatPercent(Number(coverageQuery.data?.coverage?.rawSignalCoverageRatio ?? 0))}
                  </span>
                  <span className="soft-pill">{filters.businessDomain || '全部业务域'}</span>
                </>
              }
            >
              <Link className="nav-pill" to={dashboardTarget}>
                返回看板
              </Link>
              {isBusy ? <span className="soft-pill">处理中</span> : null}
            </PageHero>

            <section className="panel onboarding-control-panel-react">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">操作入口</p>
                  <h2>同步与筛选</h2>
                </div>
              </div>
              <div className="onboarding-filter-grid-react">
                <Field label="Operator">
                  <input
                    value={filters.operatorId}
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, operatorId: event.target.value }));
                    }}
                  />
                </Field>
                <Field label="关键词">
                  <input
                    placeholder="例如：macbookpro14寸m1max"
                    value={filters.sourceKeyword}
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, sourceKeyword: event.target.value }));
                    }}
                  />
                </Field>
                <Field label="Task Key">
                  <input
                    value={filters.taskKey}
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, taskKey: event.target.value }));
                    }}
                  />
                </Field>
                <Field label="业务域">
                  <input
                    placeholder="例如：apple_m_series"
                    value={filters.businessDomain}
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, businessDomain: event.target.value }));
                    }}
                  />
                </Field>
                <Field label="Profile">
                  <input
                    value={filters.profileKey}
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, profileKey: event.target.value }));
                    }}
                  />
                </Field>
                <Field label="Discovery Pages">
                  <input
                    min={1}
                    max={5}
                    type="number"
                    value={filters.discoveryPages}
                    onChange={(event) => {
                      setFilters((current) => ({
                        ...current,
                        discoveryPages: Math.max(1, Number(event.target.value || 1)),
                      }));
                    }}
                  />
                </Field>
                <Field label="队列状态">
                  <select
                    value={filters.status}
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, status: event.target.value }));
                    }}
                  >
                    <option value="">待办中</option>
                    <option value="PENDING">PENDING</option>
                    <option value="IN_PROGRESS">IN_PROGRESS</option>
                    <option value="RESOLVED">RESOLVED</option>
                    <option value="IGNORED">IGNORED</option>
                  </select>
                </Field>
                <Field label="Item Scan Limit">
                  <input
                    min={1}
                    max={5000}
                    type="number"
                    value={filters.itemScanLimit}
                    onChange={(event) => {
                      setFilters((current) => ({
                        ...current,
                        itemScanLimit: Math.max(1, Number(event.target.value || 1)),
                      }));
                    }}
                  />
                </Field>
                <label className="onboarding-checkbox-field-react">
                  <span>包含已关闭</span>
                  <input
                    checked={filters.includeClosed}
                    type="checkbox"
                    onChange={(event) => {
                      setFilters((current) => ({ ...current, includeClosed: event.target.checked }));
                    }}
                  />
                </label>
              </div>
              <div className="onboarding-action-row-react">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => {
                    void discoveryMutation.mutateAsync();
                  }}
                >
                  开始发现
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => {
                    void syncMutation.mutateAsync();
                  }}
                >
                  同步队列
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => {
                    void Promise.all([
                      queryClient.invalidateQueries({ queryKey: ['onboarding', 'coverage'] }),
                      queryClient.invalidateQueries({ queryKey: ['onboarding', 'queue'] }),
                    ]);
                  }}
                >
                  刷新视图
                </button>
              </div>
              <p className={`onboarding-feedback-react is-${feedback.tone}`}>{feedback.message}</p>
            </section>

            <section className="progress-stats-grid">
              <MetricCard
                eyebrow="Items"
                value={String(coverageQuery.data?.counts?.totalItems ?? '-')}
                subtitle="当前筛选下的 Xianyu 商品总量"
              />
              <MetricCard
                eyebrow="Raw Response"
                value={String(coverageQuery.data?.counts?.itemsWithCurrentRawResponse ?? '-')}
                subtitle="仍保留原始响应，可回填 raw cate"
              />
              <MetricCard
                eyebrow="Backfill"
                value={String(coverageQuery.data?.counts?.backfillCandidateItems ?? '-')}
                subtitle="仍可从 RawResponse 补录的商品数"
              />
              <MetricCard
                eyebrow="Coverage"
                value={formatPercent(Number(coverageQuery.data?.coverage?.rawSignalCoverageRatio ?? 0))}
                subtitle="raw cate signal 覆盖率"
              />
            </section>

            <section className="progress-two-column">
              <article className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Queue</p>
                    <h2>待开通 raw cate</h2>
                  </div>
                  <span className="soft-pill">{queueItems.length} 项</span>
                </div>
                <div className="onboarding-queue-list-react">
                  {queueItems.length ? (
                    queueItems.map((item) => {
                      const isSelected = item.id === (selectedQueueItem?.id ?? null);
                      return (
                        <button
                          className={`onboarding-queue-card-react ${isSelected ? 'is-active' : ''}`}
                          key={item.id ?? item.matchKey ?? Math.random()}
                          type="button"
                          onClick={() => {
                            setSelectedQueueId(item.id ?? null);
                          }}
                        >
                          <div className="onboarding-queue-card-head-react">
                            <span className={`soft-pill ${queueTone(item.status)}`}>{item.status ?? '-'}</span>
                            <strong>{item.itemCountSnapshot ?? 0}</strong>
                          </div>
                          <h3>{item.matchKey ?? '-'}</h3>
                          <p className="panel-subtitle">{item.xianyuCCatId ?? item.xianyuCatId ?? item.xianyuTbCatId ?? '-'}</p>
                          <p className="panel-subtitle">{(item.sampleTitles ?? []).slice(0, 2).join(' / ') || '暂无样本标题'}</p>
                          <div className="pill-row">
                            <span className="soft-pill">{(item.businessDomains ?? []).join(', ') || '未标注业务域'}</span>
                            <span className="soft-pill">{formatRelative(item.updatedAt ?? null)}</span>
                          </div>
                        </button>
                      );
                    })
                  ) : (
                    <div className="buy-empty-state">当前没有待办项，可以先点击"同步队列"。</div>
                  )}
                </div>
              </article>

              <article className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Detail</p>
                    <h2>Queue Detail</h2>
                  </div>
                  {selectedQueueItem ? (
                    <div className="pill-row">
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => {
                          void statusMutation.mutateAsync('IN_PROGRESS');
                        }}
                      >
                        标记处理中
                      </button>
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => {
                          void statusMutation.mutateAsync('IGNORED');
                        }}
                      >
                        标记忽略
                      </button>
                      <button
                        className="primary-button"
                        type="button"
                        onClick={() => {
                          void statusMutation.mutateAsync('PENDING');
                        }}
                      >
                        恢复待办
                      </button>
                    </div>
                  ) : null}
                </div>
                {selectedQueueItem ? (
                  <div className="page-stack">
                    <div className="item-detail-fact-grid compact">
                      <ItemFact label="Match Key" value={selectedQueueItem.matchKey} />
                      <ItemFact label="状态" value={selectedQueueItem.status} />
                      <ItemFact label="Owner" value={selectedQueueItem.ownerOperatorId} />
                      <ItemFact label="样本数" value={String(selectedQueueItem.itemCountSnapshot ?? '-')} />
                    </div>
                    <div>
                      <p className="eyebrow">样本标题</p>
                      <div className="pill-row">
                        {(selectedQueueItem.sampleTitles ?? []).map((title) => (
                          <span className="soft-pill" key={title}>{title}</span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="eyebrow">候选 Match Keys</p>
                      <div className="pill-row">
                        {readStringArray(selectedQueueItem.metadata?.candidateMatchKeys).map((value) => (
                          <span className="soft-pill" key={value}>{value}</span>
                        ))}
                      </div>
                    </div>
                    <pre className="item-detail-raw-block">
                      {JSON.stringify(selectedQueueItem.resolvedMapping ?? {}, null, 2)}
                    </pre>
                  </div>
                ) : (
                  <p className="panel-subtitle">选择左侧 queue 项后，这里会展示 raw cate、样本标题、状态和候选 match keys。</p>
                )}
              </article>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Draft Editor</p>
                  <h2>属性草稿与模板确认</h2>
                </div>
                <div className="pill-row">
                  <button
                    className="secondary-button"
                    disabled={!selectedQueueItem}
                    type="button"
                    onClick={() => {
                      if (selectedQueueItem) {
                        void draftMutation.mutateAsync(selectedQueueItem);
                      }
                    }}
                  >
                    生成草稿
                  </button>
                  {pendingPersistPayload ? (
                    <button
                      className="primary-button"
                      type="button"
                      onClick={handleApplyPersist}
                    >
                      正式创建
                    </button>
                  ) : null}
                </div>
              </div>

              {draftData ? (
                <DraftEditor
                  draft={draftData}
                  onBuildPersistPayload={handleBuildPersistPayload}
                />
              ) : (
                <p className="panel-subtitle">先从左侧选择一个 queue 项，再点击"生成草稿"。草稿生成后可以逐字段编辑属性、调整分类元数据、管理枚举选项，然后预演或正式创建。</p>
              )}
            </section>
          </div>
        </div>
      </main>
    </TerminalScreen>
  );
}

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <label className="progress-filter-field onboarding-field-react">
      <span>{props.label}</span>
      {props.children}
    </label>
  );
}

function MetricCard(props: { eyebrow: string; value: string; subtitle: string }) {
  return (
    <article className="progress-stat-card">
      <p className="eyebrow">{props.eyebrow}</p>
      <strong>{props.value}</strong>
      <p className="panel-subtitle">{props.subtitle}</p>
    </article>
  );
}

function ItemFact(props: { label: string; value: string | null | undefined }) {
  return (
    <div className="item-detail-fact">
      <dt>{props.label}</dt>
      <dd>{props.value || '-'}</dd>
    </div>
  );
}

function readStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function queueTone(status: string | null | undefined) {
  if (status === 'IN_PROGRESS' || status === 'RESOLVED') {
    return 'is-accent';
  }
  if (status === 'IGNORED') {
    return 'is-warning';
  }
  return '';
}
