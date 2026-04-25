import { formatRelative } from '../../dashboard/lib/formatters';
import type { RuntimeAction, RuntimeFeedback, RuntimeGroup } from '../types/runtime';
import {
  getRecommendedRuntimeAction,
  getRuntimeActionButtonClass,
  getRuntimePriorityCopy,
  runtimeStatusLabel,
  runtimeStatusTone,
} from '../lib/runtimeViewModel';

type RuntimeActionCenterProps = {
  groups: RuntimeGroup[];
  pendingTarget: string;
  pendingAction: string;
  feedbackByGroup: Record<string, RuntimeFeedback | undefined>;
  updatedAt: string | undefined;
  onRunAction: (group: RuntimeGroup, action: RuntimeAction) => Promise<void>;
};

export function RuntimeActionCenter(props: RuntimeActionCenterProps) {
  if (!props.groups.length) {
    return (
      <section className="panel runtime-action-center">
        <div className="panel-header">
          <div>
            <p className="eyebrow">当前建议</p>
            <h2>现在没有需要先手处理的链路</h2>
          </div>
          <span className="soft-pill is-accent">最近刷新 {formatRelative(props.updatedAt)}</span>
        </div>
        <p className="panel-subtitle">所有运行单元都处在可用状态，日常只需要关注自动刷新即可。</p>
      </section>
    );
  }

  return (
    <section className="panel runtime-action-center">
      <div className="panel-header">
        <div>
          <p className="eyebrow">当前建议</p>
          <h2>先处理这几条链路</h2>
        </div>
        <span className="soft-pill">最近刷新 {formatRelative(props.updatedAt)}</span>
      </div>

      <div className="runtime-priority-grid">
        {props.groups.map((group) => {
          const recommendedAction = getRecommendedRuntimeAction(group);
          const feedback = props.feedbackByGroup[group.key];
          const isPending = props.pendingTarget === group.key;

          return (
            <article className={`runtime-priority-card ${runtimeStatusTone(group.status)}`} key={group.key}>
              <div className="runtime-priority-head">
                <div>
                  <p className="eyebrow">{group.title}</p>
                  <h3>{runtimeStatusLabel(group.status)}</h3>
                </div>
                <span className={`runtime-status-badge ${runtimeStatusTone(group.status)}`}>优先处理</span>
              </div>
              <p className="runtime-priority-copy">{getRuntimePriorityCopy(group)}</p>
              <div className="pill-row">
                {group.checks.map((check) => (
                  <span className={`soft-pill ${check.ok ? '' : 'is-warn'}`} key={`${group.key}:${check.label}`}>
                    {check.label}
                  </span>
                ))}
              </div>
              {recommendedAction ? (
                <button
                  className={getRuntimeActionButtonClass(recommendedAction.tone)}
                  disabled={isPending}
                  type="button"
                  onClick={() => {
                    void props.onRunAction(group, recommendedAction);
                  }}
                >
                  {isPending && props.pendingAction === recommendedAction.action ? '执行中...' : recommendedAction.label}
                </button>
              ) : null}
              {feedback?.message ? (
                <p className={`runtime-inline-feedback ${feedback.kind}`}>{feedback.message}</p>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
