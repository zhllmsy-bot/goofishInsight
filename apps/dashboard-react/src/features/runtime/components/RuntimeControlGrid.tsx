import type { RuntimeAction, RuntimeFeedback, RuntimeGroup } from '../types/runtime';
import { getRuntimeActionButtonClass, runtimeStatusLabel, runtimeStatusTone } from '../lib/runtimeViewModel';

type RuntimeControlGridProps = {
  groups: RuntimeGroup[];
  pendingTarget: string;
  pendingAction: string;
  feedbackByGroup: Record<string, RuntimeFeedback | undefined>;
  onRunAction: (group: RuntimeGroup, action: RuntimeAction) => Promise<void>;
};

export function RuntimeControlGrid(props: RuntimeControlGridProps) {
  if (!props.groups.length) {
    return (
      <section className="panel runtime-controls-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">运行单元</p>
            <h2>服务控制台</h2>
          </div>
        </div>
        <p className="panel-subtitle">还没有拿到运行单元状态，稍后会自动补上。</p>
      </section>
    );
  }

  return (
    <section className="panel runtime-controls-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">运行单元</p>
          <h2>服务控制台</h2>
        </div>
      </div>

      <div className="runtime-service-grid">
        {props.groups.map((group) => {
          const feedback = props.feedbackByGroup[group.key];
          const isPending = props.pendingTarget === group.key;

          return (
            <article className="runtime-service-card" key={group.key}>
              <div className="runtime-service-head">
                <div>
                  <p className="eyebrow">{group.title}</p>
                  <h3>{group.title}</h3>
                </div>
                <span className={`runtime-status-badge ${runtimeStatusTone(group.status)}`}>
                  {runtimeStatusLabel(group.status)}
                </span>
              </div>

              <p className="panel-subtitle">{group.description}</p>
              <div aria-label={`${group.title} 快捷动作`} className="runtime-hot-actions" role="group">
                {group.actions.slice(0, 2).map((action) => (
                  <button
                    aria-label={`${group.title} 快捷动作：${action.label}`}
                    className={getRuntimeActionButtonClass(action.tone)}
                    disabled={isPending}
                    key={`hot:${group.key}:${action.action}`}
                    type="button"
                    onClick={() => {
                      void props.onRunAction(group, action);
                    }}
                  >
                    快捷：{isPending && props.pendingAction === action.action ? '执行中...' : action.label}
                  </button>
                ))}
              </div>

              <div className="runtime-service-stats">
                {group.stats.map((stat) => (
                  <div className="runtime-service-stat" key={`${group.key}:${stat.label}`}>
                    <span>{stat.label}</span>
                    <strong>{stat.value}</strong>
                  </div>
                ))}
              </div>

              <div className="runtime-check-list">
                {group.checks.map((check) => (
                  <div className={`runtime-check-item ${check.ok ? 'ok' : 'warn'}`} key={`${group.key}:${check.label}`}>
                    <span>{check.label}</span>
                    <strong>{check.detail}</strong>
                  </div>
                ))}
              </div>

              <div aria-label={`${group.title} 全量动作`} className="runtime-actions-row" role="group">
                {group.actions.map((action) => (
                  <button
                    aria-label={`${group.title}：${action.label}`}
                    className={getRuntimeActionButtonClass(action.tone)}
                    disabled={isPending}
                    key={`${group.key}:${action.action}`}
                    type="button"
                    onClick={() => {
                      void props.onRunAction(group, action);
                    }}
                  >
                    {isPending && props.pendingAction === action.action ? '执行中...' : action.label}
                  </button>
                ))}
              </div>

              {feedback?.message ? (
                <p aria-atomic="true" aria-live="polite" className={`runtime-inline-feedback ${feedback.kind}`} role="status">
                  {feedback.message}
                </p>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
