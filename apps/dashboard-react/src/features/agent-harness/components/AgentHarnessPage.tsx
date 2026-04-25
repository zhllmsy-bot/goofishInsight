import { Fragment, useMemo } from 'react';

import type { AgentHarnessEvent, AgentHarnessTask } from '../types/agentHarness';
import { useAgentHarnessState } from '../hooks/useAgentHarnessData';
import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';

import '../../dashboard/styles/dashboard.css';
import '../styles/agent-harness.css';

function toneClass(tone: string) {
  return `agent-tone is-${tone}`;
}

function partitionTasks(tasks: AgentHarnessTask[]) {
  return {
    active: tasks.filter((task) => task.status === 'running' || task.status === 'in_review'),
    queued: tasks.filter((task) => task.status === 'queued'),
    blocked: tasks.filter((task) => task.status === 'blocked'),
  };
}

function TaskCard(props: { task: AgentHarnessTask }) {
  const { task } = props;

  return (
    <article className={`agent-task-card ${task.tone}`}>
      <div className="agent-task-head">
        <div>
          <p className="eyebrow">{task.scope}</p>
          <h3>{task.title}</h3>
        </div>
        <div className="pill-row">
          <span className={`soft-pill ${toneClass(task.tone)}`}>{task.status}</span>
          <span className="soft-pill">{task.priority}</span>
          <span className="soft-pill">{task.owner}</span>
        </div>
      </div>
      <p className="agent-task-summary">{task.summary}</p>
      <div className="agent-progress-row" aria-label={`${task.title} 当前进度`}>
        <div className="agent-progress-bar">
          <div className={`agent-progress-fill ${task.tone}`} style={{ width: `${task.progress}%` }} />
        </div>
        <strong>{task.progress}%</strong>
      </div>

      <div className="agent-task-grid">
        <section>
          <p className="eyebrow">Why</p>
          <p>{task.rationale}</p>
        </section>
        <section>
          <p className="eyebrow">风险</p>
          <p>{task.risk}</p>
        </section>
      </div>

      <div className="agent-task-meta-grid">
        <section>
          <p className="eyebrow">Acceptance</p>
          <ul className="agent-inline-list">
            {task.acceptanceCriteria.map((item) => (
              <li key={`${task.key}:${item}`}>{item}</li>
            ))}
          </ul>
        </section>
        <section>
          <p className="eyebrow">写集</p>
          <ul className="agent-inline-list">
            {task.files.map((file) => (
              <li key={`${task.key}:${file}`}>{file}</li>
            ))}
          </ul>
        </section>
      </div>

      <div className="agent-task-footer">
        <div className="pill-row">
          {task.middlewareFocus.map((item) => (
            <span className="soft-pill" key={`${task.key}:${item}`}>
              {item}
            </span>
          ))}
        </div>
        <p className="agent-task-updated">最近更新 {task.updatedAtRelative}</p>
      </div>

      {task.dependencies.length ? (
        <div className="agent-dependency-row">
          <span className="eyebrow">依赖</span>
          <div className="pill-row">
            {task.dependencies.map((dependency) => (
              <span className="soft-pill" key={`${task.key}:${dependency}`}>
                {dependency}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function EventItem(props: { event: AgentHarnessEvent }) {
  const { event } = props;

  return (
    <article className={`agent-event-card ${event.tone}`}>
      <div className="agent-event-head">
        <div>
          <p className="eyebrow">{event.kind}</p>
          <h3>{event.title}</h3>
        </div>
        <span className={`soft-pill ${toneClass(event.tone)}`}>{event.atRelative}</span>
      </div>
      <p>{event.detail}</p>
    </article>
  );
}

export function AgentHarnessPage() {
  const { snapshot, error, isLoading } = useAgentHarnessState();
  const taskPartitions = useMemo(() => partitionTasks(snapshot?.tasks ?? []), [snapshot?.tasks]);

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack agent-harness-page">
            <PageHero
              description="把 DeerFlow 的 Lead Agent / middleware / subtask fan-out 先投影成一个可运营控制台，回答三件事：为什么挑这个任务、谁在做、下一轮要不要继续并行。"
              eyebrow="Agent Harness"
              title="多 Agent 并行修复控制台"
              meta={
                snapshot ? (
                  <>
                    <span className="soft-pill">{snapshot.metrics.taskCount} 个任务</span>
                    <span className="soft-pill is-accent">{snapshot.metrics.runningCount} 个执行中</span>
                    <span className={`soft-pill ${snapshot.metrics.blockedCount ? 'is-warn' : ''}`}>
                      {snapshot.metrics.blockedCount} 个阻塞
                    </span>
                  </>
                ) : null
              }
            >
              {snapshot ? (
                <Fragment>
                  <span className="soft-pill">{snapshot.workspace.name}</span>
                  <span className="soft-pill">{snapshot.workspace.executionMode}</span>
                  <span className="soft-pill">并行预算 {snapshot.metrics.parallelismBudget}</span>
                  <span className="soft-pill">最近决策 {snapshot.leadRun.lastDecisionRelative}</span>
                </Fragment>
              ) : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !snapshot ? (
              <section className="panel">
                <p className="eyebrow">Agent Harness</p>
                <h2>正在同步 DeerFlow pilot 状态...</h2>
                <p className="panel-subtitle">首轮加载会把 lead run、子任务、middleware 与事件流一起拉起。</p>
              </section>
            ) : null}

            {snapshot ? (
              <Fragment>
                <section className="panel agent-lead-panel">
                  <div className="agent-lead-head">
                    <div>
                      <p className="eyebrow">Lead Agent</p>
                      <h2>{snapshot.leadRun.title}</h2>
                      <p className="panel-subtitle">{snapshot.leadRun.goal}</p>
                    </div>
                    <div className="agent-lead-metrics">
                      <div className="agent-kpi-card">
                        <span>Loop</span>
                        <strong>
                          {snapshot.leadRun.iteration}/{snapshot.leadRun.maxIterations}
                        </strong>
                      </div>
                      <div className="agent-kpi-card">
                        <span>State</span>
                        <strong>{snapshot.leadRun.loopState}</strong>
                      </div>
                      <div className="agent-kpi-card">
                        <span>中间件</span>
                        <strong>{snapshot.metrics.activeMiddlewares}</strong>
                      </div>
                      <div className="agent-kpi-card">
                        <span>Human Gate</span>
                        <strong>{snapshot.leadRun.humanGate}</strong>
                      </div>
                    </div>
                  </div>

                  <div className="agent-lead-columns">
                    <section className="agent-rationale-panel">
                      <p className="eyebrow">决策理由</p>
                      <ul className="agent-inline-list">
                        {snapshot.leadRun.rationale.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                    <section className="agent-rationale-panel">
                      <p className="eyebrow">下一步</p>
                      <ul className="agent-inline-list">
                        {snapshot.nextActions.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                  </div>
                </section>

                <section className="agent-grid-shell">
                  <div className="agent-main-stack">
                    <section className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="eyebrow">SubAgents</p>
                          <h2>当前活跃任务</h2>
                        </div>
                        <div className="pill-row">
                          <span className="soft-pill">{taskPartitions.active.length} 个活跃</span>
                          <span className="soft-pill">{taskPartitions.queued.length} 个待执行</span>
                        </div>
                      </div>
                      <div className="agent-task-stack">
                        {taskPartitions.active.map((task) => (
                          <TaskCard key={task.key} task={task} />
                        ))}
                      </div>
                    </section>

                    <section className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="eyebrow">Backlog</p>
                          <h2>待执行与阻塞任务</h2>
                        </div>
                      </div>
                      <div className="agent-backlog-grid">
                        <div className="agent-backlog-column">
                          <h3>Queued</h3>
                          <div className="agent-mini-card-list">
                            {taskPartitions.queued.map((task) => (
                              <TaskCard key={task.key} task={task} />
                            ))}
                          </div>
                        </div>
                        <div className="agent-backlog-column">
                          <h3>Blocked</h3>
                          <div className="agent-mini-card-list">
                            {taskPartitions.blocked.map((task) => (
                              <TaskCard key={task.key} task={task} />
                            ))}
                          </div>
                        </div>
                      </div>
                    </section>
                  </div>

                  <aside className="agent-side-stack">
                    <section className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="eyebrow">Middleware</p>
                          <h2>上下文与风控栈</h2>
                        </div>
                      </div>
                      <div className="agent-middleware-list">
                        {snapshot.middlewareStack.map((middleware) => (
                          <article className="agent-middleware-card" key={middleware.name}>
                            <div className="agent-middleware-head">
                              <strong>{middleware.name}</strong>
                              <span className="soft-pill">{middleware.layer}</span>
                            </div>
                            <p>{middleware.purpose}</p>
                          </article>
                        ))}
                      </div>
                    </section>

                    <section className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="eyebrow">Event Stream</p>
                          <h2>为什么现在这样排队</h2>
                        </div>
                      </div>
                      <div className="agent-event-list">
                        {snapshot.events.map((event) => (
                          <EventItem event={event} key={event.id} />
                        ))}
                      </div>
                    </section>
                  </aside>
                </section>
              </Fragment>
            ) : null}
          </div>
        </div>
      </main>
    </AppFrame>
  );
}
