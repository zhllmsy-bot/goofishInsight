import { formatRelative } from '../../dashboard/lib/formatters';
import type { RuntimeActivityEntry } from '../types/runtime';

type RuntimeActivityFeedProps = {
  entries: RuntimeActivityEntry[];
};

export function RuntimeActivityFeed(props: RuntimeActivityFeedProps) {
  return (
    <section className="panel runtime-activity-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">最近动作</p>
          <h2>操作回声</h2>
        </div>
      </div>

      {props.entries.length ? (
        <div className="runtime-activity-list">
          {props.entries.map((entry) => (
            <article className="runtime-activity-item" key={entry.id}>
              <div>
                <strong>{entry.groupTitle}</strong>
                <p className="panel-subtitle">{entry.actionLabel}</p>
              </div>
              <div className="runtime-activity-meta">
                <span className={`soft-pill ${entry.status === 'success' ? 'is-accent' : 'is-warn'}`}>
                  {entry.status === 'success' ? '已执行' : '失败'}
                </span>
                <span className="panel-subtitle">{formatRelative(entry.createdAt)}</span>
              </div>
              <p className="runtime-activity-copy">{entry.message}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="panel-subtitle">这页会记住你当前会话里的动作结果，方便回头确认刚刚改动过什么。</p>
      )}
    </section>
  );
}
