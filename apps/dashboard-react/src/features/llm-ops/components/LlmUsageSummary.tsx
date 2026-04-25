import { formatNumber, formatRelative } from '../../dashboard/lib/formatters';
import type { UsageWorkersSection } from '../types/llmOps';

type LlmUsageSummaryProps = {
  usageSummary: UsageWorkersSection['usage_summary'];
  workerRuns: UsageWorkersSection['worker_runs'];
};

function UsageMetricCard(props: { eyebrow: string; value: number | undefined; subtitle: string }) {
  return (
    <article className="llm-token-card">
      <p className="eyebrow">{props.eyebrow}</p>
      <strong>{formatNumber(props.value)}</strong>
      <p className="panel-subtitle">{props.subtitle}</p>
    </article>
  );
}

export function LlmUsageSummary(props: LlmUsageSummaryProps) {
  const recentUsageRuns = props.usageSummary?.recent_usage_runs ?? [];
  const workerRuns = props.workerRuns ?? [];

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Token Usage</p>
            <h2>模型消耗</h2>
          </div>
          <div className="pill-row">
            <span className="soft-pill">{formatNumber(props.usageSummary?.file_count)} 个批次</span>
            <span className="soft-pill is-accent">{formatNumber(props.usageSummary?.request_count)} 次请求</span>
          </div>
        </div>

        <div className="llm-token-grid">
          <UsageMetricCard
            eyebrow="累计 Tokens"
            subtitle={`输入 ${formatNumber(props.usageSummary?.input_tokens)} / 输出 ${formatNumber(props.usageSummary?.output_tokens)}`}
            value={props.usageSummary?.total_tokens}
          />
          <UsageMetricCard
            eyebrow="缓存 Tokens"
            subtitle={`最近生成 ${formatRelative(props.usageSummary?.last_generated_at || null)}`}
            value={props.usageSummary?.cached_tokens}
          />
          <UsageMetricCard
            eyebrow="二次复审"
            subtitle={`救回 ${formatNumber(props.usageSummary?.second_pass_rescued_count)} / 未解 ${formatNumber(props.usageSummary?.second_pass_unresolved_count)}`}
            value={props.usageSummary?.second_pass_requested_count}
          />
          <UsageMetricCard
            eyebrow="过滤结果"
            subtitle={`垃圾 ${formatNumber(props.usageSummary?.garbage_hit_count)} / 低置信 ${formatNumber(props.usageSummary?.low_confidence_filtered_count)}`}
            value={props.usageSummary?.high_confidence_kept_count}
          />
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Recent Usage Runs</p>
            <h2>最近消耗批次</h2>
          </div>
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
                <th>输入</th>
                <th>输出</th>
                <th>总 Tokens</th>
                <th>缓存</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {recentUsageRuns.length ? (
                recentUsageRuns.map((row) => (
                  <tr key={`${row.file_name}:${row.generated_at || '-'}`}>
                    <td>{row.domain_label || '-'}</td>
                    <td>{row.pipeline || '-'}</td>
                    <td>
                      <strong>{row.file_name}</strong>
                    </td>
                    <td>{formatNumber(row.request_count)}</td>
                    <td>{formatNumber(row.requested_item_count)}</td>
                    <td>{formatNumber(row.input_tokens)}</td>
                    <td>{formatNumber(row.output_tokens)}</td>
                    <td>{formatNumber(row.total_tokens)}</td>
                    <td>{formatNumber(row.cached_tokens)}</td>
                    <td>{formatRelative(row.generated_at || null)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="empty-cell" colSpan={10}>
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
              <article className="llm-worker-card" key={`${run.log_name}:${run.updated_at || '-'}`}>
                <div className="llm-worker-head">
                  <div>
                    <strong>{run.log_name || '-'}</strong>
                    <p className="panel-subtitle">
                      {run.pipeline || '-'} / {run.domain_label || '-'}
                    </p>
                  </div>
                  <span className="soft-pill">{formatRelative(run.updated_at || null)}</span>
                </div>
                <div className="pill-row">
                  <span className="soft-pill">provider {run.ai_provider || '-'}</span>
                  <span className="soft-pill">model {run.ai_model || '-'}</span>
                  <span className="soft-pill">workers {formatNumber(run.worker_count)}</span>
                </div>
                <div className="llm-worker-events">
                  {(run.recent_events ?? []).map((event, index) => (
                    <div className="llm-worker-event" key={`${run.log_name}:${event.event || index}`}>
                      <strong>{event.title || event.event || '-'}</strong>
                      <span>{event.summary || '-'}</span>
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
    </>
  );
}
