import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { categoryLabel, formatNumber, formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation } from '../../dashboard/lib/urlState';
import { useDashboardUiStore } from '../../dashboard/store/dashboardUiStore';
import type { RuntimeAction, RuntimeActivityEntry, RuntimeFeedback, RuntimeGroup } from '../types/runtime';
import { deriveRuntimeSummary, getRuntimeHeadline } from '../lib/runtimeViewModel';
import { useRuntimeControlState } from '../hooks/useRuntimeData';
import { RuntimeActionCenter } from './RuntimeActionCenter';
import { RuntimeActivityFeed } from './RuntimeActivityFeed';
import { RuntimeControlGrid } from './RuntimeControlGrid';
import { TerminalScreen } from '../../../shared/components/TerminalScreen';
import { PageHero } from '../../../shared/components/PageHero';

import '../../dashboard/styles/dashboard.css';
import '../styles/runtime.css';

function requiresRuntimeActionConfirmation(action: RuntimeAction) {
  return action.action === 'stop' || action.action === 'restart' || action.tone === 'danger';
}

export function RuntimePage() {
  const query = useDashboardUiStore((state) => state.query);
  const { runtime, error, isLoading, pendingAction, pendingTarget, runAction } = useRuntimeControlState(
    query.categoryCode,
  );
  const [feedbackByGroup, setFeedbackByGroup] = useState<Record<string, RuntimeFeedback>>({});
  const [activityEntries, setActivityEntries] = useState<RuntimeActivityEntry[]>([]);
  const navigate = useNavigate();
  const dashboardTarget = buildWorkspaceLocation('/', query);

  const summary = useMemo(() => deriveRuntimeSummary(runtime), [runtime]);
  const scopedCategoryLabel = useMemo(() => {
    const buyJobsScope = runtime?.groups
      ?.find((group) => group.key === 'buy_jobs')
      ?.stats.find((stat) => stat.label === '类目作用域')?.value;
    if (buyJobsScope && buyJobsScope !== '全部类目') {
      return buyJobsScope;
    }
    if (!query.categoryCode) {
      return null;
    }
    return `${categoryLabel(query.categoryCode)} (${query.categoryCode})`;
  }, [query.categoryCode, runtime]);

  const handleRunAction = async (group: RuntimeGroup, action: RuntimeAction) => {
    if (requiresRuntimeActionConfirmation(action)) {
      const confirmed = window.confirm(
        `确认对「${group.title}」执行「${action.label}」吗？这个操作可能会中断当前采集、分析或模型任务。`,
      );
      if (!confirmed) {
        return;
      }
    }

    setFeedbackByGroup((current) => ({
      ...current,
      [group.key]: {
        kind: 'pending',
        message: `正在执行 ${action.label}...`,
      },
    }));

    try {
      await runAction({
        target: group.key,
        action: action.action,
        categoryCode: query.categoryCode || undefined,
      });

      const successMessage = `${action.label} 已提交，状态已刷新。`;
      const successEntry: RuntimeActivityEntry = {
        id: `${group.key}:${action.action}:${Date.now()}`,
        groupKey: group.key,
        groupTitle: group.title,
        actionLabel: action.label,
        status: 'success',
        message: successMessage,
        createdAt: new Date().toISOString(),
      };
      setFeedbackByGroup((current) => ({
        ...current,
        [group.key]: {
          kind: 'success',
          message: successMessage,
        },
      }));
      setActivityEntries((current) => [
        successEntry,
        ...current,
      ].slice(0, 8));
    } catch (mutationError) {
      const failureMessage = mutationError instanceof Error ? mutationError.message : '未知错误';
      const failureEntry: RuntimeActivityEntry = {
        id: `${group.key}:${action.action}:${Date.now()}`,
        groupKey: group.key,
        groupTitle: group.title,
        actionLabel: action.label,
        status: 'error',
        message: failureMessage,
        createdAt: new Date().toISOString(),
      };
      setFeedbackByGroup((current) => ({
        ...current,
        [group.key]: {
          kind: 'error',
          message: `执行失败：${failureMessage}`,
        },
      }));
      setActivityEntries((current) => [
        failureEntry,
        ...current,
      ].slice(0, 8));
    }
  };

  return (
    <TerminalScreen>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack">
            <nav className="runtime-breadcrumb">
              <button
                className="runtime-breadcrumb-link"
                type="button"
                onClick={() => navigate(dashboardTarget)}
              >
                ← 回到交易工作台
              </button>
              {summary.attentionCount === 0 ? (
                <span className="runtime-breadcrumb-status is-ok">所有链路在线</span>
              ) : (
                <span className="runtime-breadcrumb-status is-warn">
                  {summary.attentionCount} 条链路需要处理
                </span>
              )}
            </nav>

            <PageHero
              description="这个页面只回答三件事：现在哪条链路坏了、建议先动哪一步、动作执行后有没有真的恢复。技术细节保留，但放在决策之后。"
              eyebrow="运行控制"
              title="本机常驻任务指挥台"
              meta={
                <>
                  {scopedCategoryLabel ? <span className="soft-pill">作用域 {scopedCategoryLabel}</span> : null}
                  <span className="soft-pill">{summary.totalCount} 个运行单元</span>
                  <span className="soft-pill is-accent">{summary.runningCount} 个在线</span>
                  <span className={`soft-pill ${summary.attentionCount ? 'is-warn' : ''}`}>
                    {summary.attentionCount} 个待处理
                  </span>
                </>
              }
            >
              <span className="soft-pill">{getRuntimeHeadline(summary)}</span>
              <span className="soft-pill">最近刷新 {formatRelative(runtime?.updatedAt)}</span>
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !runtime ? (
              <section className="panel">
                <p className="eyebrow">运行状态</p>
                <h2>正在同步本机常驻任务...</h2>
                <p className="panel-subtitle">首轮加载会把当前 launchd / 模型 / review runtime 状态收齐，然后开始自动刷新。</p>
              </section>
            ) : null}

            <section className="panel runtime-summary-panel">
              <div className="runtime-summary-grid">
                <article className="runtime-summary-card">
                  <p className="eyebrow">需要处理</p>
                  <strong>{formatNumber(summary.attentionCount)}</strong>
                  <p className="panel-subtitle">
                    已停 {formatNumber(summary.stoppedCount)} / 部分可用 {formatNumber(summary.degradedCount)}
                  </p>
                </article>
                <article className="runtime-summary-card">
                  <p className="eyebrow">当前在线</p>
                  <strong>{formatNumber(summary.runningCount)}</strong>
                  <p className="panel-subtitle">总共 {formatNumber(summary.totalCount)} 个运行单元</p>
                </article>
                <article className="runtime-summary-card">
                  <p className="eyebrow">刷新节奏</p>
                  <strong>20s</strong>
                  <p className="panel-subtitle">后台自动回看，不用手动刷整页</p>
                </article>
              </div>
            </section>

            {summary.attentionCount === 0 && runtime ? (
              <section className="panel runtime-all-clear-panel">
                <div className="runtime-all-clear-content">
                  <p className="eyebrow">运行状态</p>
                  <h3>所有常驻链路都在线</h3>
                  <p className="panel-subtitle">
                    采集、模型、review、dashboard 各链路均正常运行。你可以回到交易工作台继续关注价格和机会。
                  </p>
                  <button
                    className="runtime-button runtime-button-primary"
                    type="button"
                    onClick={() => navigate(dashboardTarget)}
                  >
                    回到交易工作台
                  </button>
                </div>
              </section>
            ) : null}

            <RuntimeActionCenter
              feedbackByGroup={feedbackByGroup}
              groups={summary.priorityGroups}
              pendingAction={pendingAction}
              pendingTarget={pendingTarget}
              updatedAt={runtime?.updatedAt}
              onRunAction={handleRunAction}
            />

            <RuntimeControlGrid
              feedbackByGroup={feedbackByGroup}
              groups={runtime?.groups ?? []}
              pendingAction={pendingAction}
              pendingTarget={pendingTarget}
              onRunAction={handleRunAction}
            />

            <RuntimeActivityFeed entries={activityEntries} />
          </div>
        </div>
      </main>
    </TerminalScreen>
  );
}
