import { useDashboardUiStore } from '../../dashboard/store/dashboardUiStore';
import { formatNumber } from '../../dashboard/lib/formatters';
import { useLlmOpsState } from '../hooks/useLlmOpsData';
import { PageHero } from '../../../shared/components/PageHero';
import { AppFrame } from '../../../shared/components/AppFrame';
import { LlmTraceDetail } from './LlmTraceDetail';
import { LlmTraceList } from './LlmTraceList';
import { LlmUsageSummary } from './LlmUsageSummary';

import '../styles/llm-ops.css';
import '../../dashboard/styles/dashboard.css';

export function LlmOpsPage() {
  const query = useDashboardUiStore((state) => state.query);
  const {
    selectedTraceKey,
    setSelectedTraceKey,
    traceSection,
    traceDetail,
    usageWorkers,
  } = useLlmOpsState({ categoryCode: query.categoryCode });

  const usageSummary = usageWorkers?.usage_summary;

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack llm-ops-page">
            <PageHero
              description="LLM 调用追踪与 Token 消耗分析"
              eyebrow="LLM DevOps"
              title="Prompt / Request / Response / Tokens"
              meta={
                <>
                  <span className={`soft-pill ${traceSection?.trace_enabled ? 'is-accent' : ''}`}>
                    {traceSection?.trace_enabled ? 'Trace 写入中' : 'Trace 已关闭'}
                  </span>
                  <span className="soft-pill">{formatNumber(traceSection?.trace_count)} 条 trace</span>
                </>
              }
            />

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">LLM Trace</p>
                  <h2>最近模型调用</h2>
                </div>
                <div className="pill-row">
                  <span className="soft-pill">{traceSection?.trace_dir || '-'}</span>
                </div>
              </div>
              <div className="llm-ops-grid">
                <LlmTraceList
                  onSelectTraceKey={setSelectedTraceKey}
                  selectedTraceKey={selectedTraceKey}
                  traces={traceSection?.traces}
                />
                <LlmTraceDetail trace={traceDetail} />
              </div>
            </section>

            <LlmUsageSummary usageSummary={usageSummary} workerRuns={usageWorkers?.worker_runs} />
          </div>
        </div>
      </main>
    </AppFrame>
  );
}
