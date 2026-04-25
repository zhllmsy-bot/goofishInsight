import { startTransition, useDeferredValue, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';
import { categoryLabel, formatNumber, formatPercent, formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation } from '../../dashboard/lib/urlState';
import { useDashboardUiStore } from '../../dashboard/store/dashboardUiStore';
import { useProgressPage } from '../hooks/useProgressData';

import '../../dashboard/styles/dashboard.css';
import '../../llm-ops/styles/llm-ops.css';
import '../styles/progress.css';

export function ProgressPage() {
  const navigate = useNavigate();
  const query = useDashboardUiStore((state) => state.query);
  const setQuery = useDashboardUiStore((state) => state.setQuery);
  const deferredQuery = useDeferredValue(query);
  const { header, overview, usageWorkers, audits, error, isLoading, isRefreshing } = useProgressPage(deferredQuery);

  const selectedCategory = header?.selected_category_code || deferredQuery.categoryCode || query.categoryCode;
  const availableCategories = header?.available_categories ?? [];
  const reviewOverview = overview?.review_overview ?? header?.review_overview;
  const progressRows = overview?.review_progress_rows ?? [];
  const usageSummary = usageWorkers?.usage_summary;
  const usageRuns = usageSummary?.recent_usage_runs ?? [];
  const workerRuns = usageWorkers?.worker_runs ?? [];
  const auditQueueRows = audits?.audit_queue_rows ?? [];
  const invalidReasonRows = audits?.invalid_reason_rows ?? [];
  const runtimeTarget = useMemo(
    () => buildWorkspaceLocation('/ops/runtime', query),
    [query],
  );

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack progress-page">
            <PageHero
              eyebrow="Review Progress"
              title="回刷进度工作台"
              description="进度、usage、worker 和待审分歧现在统一留在 React 主路径里，不再从主工作区跳回旧版 Jinja 页。"
              meta={
                <>
                  <span className="soft-pill">{selectedCategory ? categoryLabel(selectedCategory) : '全部品类'}</span>
                  <span className="soft-pill is-accent">{header?.current_ai_provider ?? '-'} / {header?.current_ai_model ?? '-'}</span>
                  <span className="soft-pill">最近完成 {formatRelative(reviewOverview?.last_reviewed_at ?? null)}</span>
                </>
              }
            >
              <label className="progress-filter-field">
                <span>查看品类</span>
                <select
                  aria-label="选择回刷进度品类"
                  value={query.categoryCode}
                  onChange={(event) => {
                    const nextCategoryCode = event.target.value;
                    startTransition(() => {
                      setQuery((previous) => ({
                        ...previous,
                        categoryCode: nextCategoryCode,
                      }));
                    });
                  }}
                >
                  <option value="">全部</option>
                  {availableCategories.map((categoryCode) => (
                    <option key={categoryCode} value={categoryCode}>
                      {categoryLabel(categoryCode)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="nav-pill"
                type="button"
                onClick={() => {
                  void navigate(runtimeTarget);
                }}
              >
                打开运行控制
              </button>
              {isRefreshing ? <span className="soft-pill">正在刷新</span> : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !header ? (
              <section className="panel">
                <p className="eyebrow">Progress</p>
                <h2>正在汇总回刷进度与 worker 状态...</h2>
                <p className="panel-subtitle">首轮会合并 overview、usage 和审计队列，完成后就可以留在同一套 React 工作流里继续切换。</p>
              </section>
            ) : null}

            <section className="progress-stats-grid">
              <ProgressMetricCard
                eyebrow="总体完成率"
                subtitle={`已完成 ${formatNumber(reviewOverview?.reviewed_total)} / ${formatNumber(reviewOverview?.review_target_total)}`}
                value={formatPercent(reviewOverview?.completion_percent, 1)}
              />
              <ProgressMetricCard
                eyebrow="待回刷"
                subtitle="仍在 active 队列里等待领取"
                value={formatNumber(reviewOverview?.pending_review_count)}
              />
              <ProgressMetricCard
                eyebrow="处理中"
                subtitle="当前被 worker claim 的商品"
                value={formatNumber(reviewOverview?.in_progress_count)}
              />
              <ProgressMetricCard
                eyebrow="待审队列"
                subtitle="LLM 有分歧，暂不自动落库"
                value={formatNumber(reviewOverview?.pending_audit_count)}
              />
              <ProgressMetricCard
                eyebrow="已判无效"
                subtitle="广告、配件、回收或其他无效样本"
                value={formatNumber(reviewOverview?.reviewed_invalid_count)}
              />
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Domain Progress</p>
                  <h2>业务域进度</h2>
                </div>
                <div className="pill-row">
                  <span className="soft-pill">{formatNumber(reviewOverview?.domain_count)} 个业务域</span>
                  <span className="soft-pill is-accent">{formatNumber(reviewOverview?.reviewed_valid_count)} valid</span>
                </div>
              </div>
              <div className="progress-domain-grid">
                {progressRows.length ? (
                  progressRows.map((row) => {
                    const tone = row.completion_percent && row.completion_percent >= 80 ? 'is-good' : row.completion_percent && row.completion_percent >= 40 ? 'is-mid' : 'is-watch';
                    return (
                      <article className="progress-domain-card" key={row.business_domain}>
                        <div className="progress-domain-head">
                          <div>
                            <p className="eyebrow">{row.business_domain}</p>
                            <h3>{row.label}</h3>
                          </div>
                          <span className={`soft-pill ${tone}`}>{formatPercent(row.completion_percent, 1)}</span>
                        </div>
                        <div aria-label="completion" className="progress-meter">
                          <span className={`progress-fill ${tone}`} style={{ width: `${row.completion_percent ?? 0}%` }} />
                        </div>
                        <div className="progress-domain-kpis">
                          <ProgressMiniStat label="待回刷" value={formatNumber(row.pending_review_count)} />
                          <ProgressMiniStat label="处理中" value={formatNumber(row.in_progress_count)} />
                          <ProgressMiniStat label="已通过" value={formatNumber(row.reviewed_valid_count)} />
                          <ProgressMiniStat label="待审" value={formatNumber(row.pending_audit_count)} />
                          <ProgressMiniStat label="已剔除" value={formatNumber(row.reviewed_invalid_count)} />
                        </div>
                        <p className="panel-subtitle">
                          active {formatNumber(row.active_items)} · total {formatNumber(row.total_items)} · 最近 review {formatRelative(row.last_reviewed_at)}
                        </p>
                      </article>
                    );
                  })
                ) : (
                  <article className="progress-domain-card is-empty">
                    <p className="panel-subtitle">当前条件下没有可展示的回刷进度。</p>
                  </article>
                )}
              </div>
            </section>

            <section className="progress-two-column">
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Token Usage</p>
                    <h2>模型消耗</h2>
                  </div>
                  <div className="pill-row">
                    <span className="soft-pill">{formatNumber(usageSummary?.file_count)} 个批次</span>
                    <span className="soft-pill is-accent">{formatNumber(usageSummary?.request_count)} 次请求</span>
                  </div>
                </div>
                <div className="progress-stats-grid compact">
                  <ProgressMetricCard
                    eyebrow="累计 Tokens"
                    subtitle={`输入 ${formatNumber(usageSummary?.input_tokens)} / 输出 ${formatNumber(usageSummary?.output_tokens)}`}
                    value={formatNumber(usageSummary?.total_tokens)}
                  />
                  <ProgressMetricCard
                    eyebrow="垃圾命中"
                    subtitle="规则预筛或 LLM 命中的垃圾样本"
                    value={formatNumber(usageSummary?.garbage_hit_count)}
                  />
                  <ProgressMetricCard
                    eyebrow="低置信过滤"
                    subtitle="模型返回但低于 90 分的样本"
                    value={formatNumber(usageSummary?.low_confidence_filtered_count)}
                  />
                  <ProgressMetricCard
                    eyebrow="二次救回"
                    subtitle={`二次复审 ${formatNumber(usageSummary?.second_pass_requested_count)} / 未解 ${formatNumber(usageSummary?.second_pass_unresolved_count)}`}
                    value={formatNumber(usageSummary?.second_pass_rescued_count)}
                  />
                </div>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>业务域</th>
                        <th>管线</th>
                        <th>文件</th>
                        <th>请求</th>
                        <th>样本</th>
                        <th>总 Tokens</th>
                        <th>缓存</th>
                        <th>时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageRuns.length ? (
                        usageRuns.map((row) => (
                          <tr key={`${row.file_name}:${row.generated_at ?? '-'}`}>
                            <td>{row.domain_label ?? '-'}</td>
                            <td>{row.pipeline ?? '-'}</td>
                            <td><strong>{row.file_name}</strong></td>
                            <td>{formatNumber(row.request_count)}</td>
                            <td>{formatNumber(row.requested_item_count)}</td>
                            <td>{formatNumber(row.total_tokens)}</td>
                            <td>{formatNumber(row.cached_tokens)}</td>
                            <td>{formatRelative(row.generated_at)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="empty-cell" colSpan={8}>
                            还没有 usage 统计文件。
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Worker Runs</p>
                    <h2>最近 Worker / Result Runs</h2>
                  </div>
                </div>
                <div className="llm-worker-grid">
                  {workerRuns.length ? (
                    workerRuns.map((run) => (
                      <article className="llm-worker-card" key={`${run.log_name}:${run.updated_at ?? '-'}`}>
                        <div className="llm-worker-head">
                          <div>
                            <strong>{run.log_name ?? '-'}</strong>
                            <p className="panel-subtitle">
                              {run.pipeline ?? '-'} / {run.domain_label ?? '-'}
                            </p>
                          </div>
                          <span className="soft-pill">{formatRelative(run.updated_at)}</span>
                        </div>
                        <div className="pill-row">
                          <span className="soft-pill">provider {run.ai_provider ?? '-'}</span>
                          <span className="soft-pill">model {run.ai_model ?? '-'}</span>
                          <span className="soft-pill">workers {formatNumber(run.worker_count)}</span>
                        </div>
                        <div className="llm-worker-events">
                          {(run.recent_events ?? []).map((event, index) => (
                            <div className="llm-worker-event" key={`${run.log_name}:${event.event ?? index}`}>
                              <strong>{event.title ?? event.event ?? '-'}</strong>
                              <span>{event.summary ?? '-'}</span>
                            </div>
                          ))}
                        </div>
                      </article>
                    ))
                  ) : (
                    <article className="llm-worker-card">
                      <p className="panel-subtitle">还没有 worker run 可展示。</p>
                    </article>
                  )}
                </div>
              </section>
            </section>

            <section className="progress-two-column">
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Audit Queue</p>
                    <h2>待审分歧</h2>
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>业务域</th>
                        <th>商品</th>
                        <th>原因</th>
                        <th>模型结论</th>
                        <th>置信度</th>
                        <th>字段变更</th>
                        <th>时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditQueueRows.length ? (
                        auditQueueRows.map((row) => (
                          <tr key={`${row.item_id ?? '-'}:${row.reviewed_at ?? '-'}`}>
                            <td>{row.domain_label ?? '-'}</td>
                            <td>
                              <strong>{row.title ?? '-'}</strong>
                              <br />
                              <span className="panel-subtitle">{row.item_id ?? '-'}</span>
                            </td>
                            <td>{row.audit_reason ?? '-'}</td>
                            <td>{[row.decision_status, row.invalid_reason].filter(Boolean).join(' / ') || '-'}</td>
                            <td>{typeof row.confidence === 'number' ? formatPercent(row.confidence, 1) : '-'}</td>
                            <td>{formatNumber(row.field_change_count)}</td>
                            <td>{formatRelative(row.reviewed_at)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="empty-cell" colSpan={7}>
                            当前没有待审分歧。
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Invalid Reasons</p>
                    <h2>最近剔除原因</h2>
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>业务域</th>
                        <th>原因</th>
                        <th>数量</th>
                        <th>最近时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invalidReasonRows.length ? (
                        invalidReasonRows.map((row) => (
                          <tr key={`${row.business_domain ?? '-'}:${row.reason ?? '-'}`}>
                            <td>{row.domain_label ?? '-'}</td>
                            <td><strong>{row.reason ?? '-'}</strong></td>
                            <td>{formatNumber(row.item_count)}</td>
                            <td>{formatRelative(row.last_reviewed_at)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="empty-cell" colSpan={4}>
                            还没有 invalid reason 统计。
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </section>
          </div>
        </div>
      </main>
    </AppFrame>
  );
}

function ProgressMetricCard(props: {
  eyebrow: string;
  value: string;
  subtitle: string;
}) {
  return (
    <article className="progress-metric-card">
      <p className="eyebrow">{props.eyebrow}</p>
      <strong>{props.value}</strong>
      <p className="panel-subtitle">{props.subtitle}</p>
    </article>
  );
}

function ProgressMiniStat(props: { label: string; value: string }) {
  return (
    <div className="progress-mini-stat">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}
