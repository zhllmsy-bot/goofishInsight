import type { RuntimeAction, RuntimeGroup, RuntimeStatus } from '../types/runtime';

export type RuntimeSummary = {
  totalCount: number;
  runningCount: number;
  attentionCount: number;
  stoppedCount: number;
  degradedCount: number;
  priorityGroups: RuntimeGroup[];
};

const STATUS_ORDER: Record<string, number> = {
  stopped: 0,
  degraded: 1,
  running: 2,
};

export function runtimeStatusLabel(status: string): string {
  switch (status) {
    case 'running':
      return '运行中';
    case 'degraded':
      return '部分可用';
    case 'stopped':
      return '已停止';
    default:
      return status || '未知';
  }
}

export function runtimeStatusTone(status: string): 'healthy' | 'warn' | 'stopped' {
  if (status === 'running') {
    return 'healthy';
  }
  if (status === 'degraded') {
    return 'warn';
  }
  return 'stopped';
}

export function deriveRuntimeSummary(runtime: RuntimeStatus | null): RuntimeSummary {
  const groups = runtime?.groups ?? [];
  const stoppedCount = groups.filter((group) => group.status === 'stopped').length;
  const degradedCount = groups.filter((group) => group.status === 'degraded').length;
  const runningCount = groups.filter((group) => group.status === 'running').length;

  return {
    totalCount: groups.length,
    runningCount,
    attentionCount: stoppedCount + degradedCount,
    stoppedCount,
    degradedCount,
    priorityGroups: [...groups]
      .filter((group) => group.status !== 'running')
      .sort((left, right) => {
        const statusGap = (STATUS_ORDER[left.status] ?? 99) - (STATUS_ORDER[right.status] ?? 99);
        if (statusGap !== 0) {
          return statusGap;
        }
        return left.title.localeCompare(right.title, 'zh-CN');
      })
      .slice(0, 3),
  };
}

export function getRuntimeFailingChecks(group: RuntimeGroup) {
  return group.checks.filter((check) => !check.ok);
}

export function getRecommendedRuntimeAction(group: RuntimeGroup): RuntimeAction | null {
  if (!group.actions.length) {
    return null;
  }

  const byName = new Map(group.actions.map((action) => [action.action, action]));
  if (group.status === 'stopped') {
    return byName.get('start') ?? group.actions[0] ?? null;
  }
  if (group.status === 'degraded') {
    return (
      byName.get('restart')
      ?? byName.get('start')
      ?? byName.get('switch_to_qwen3_30b')
      ?? byName.get('start_vlm')
      ?? group.actions.find((action) => action.action !== 'stop')
      ?? group.actions[0]
      ?? null
    );
  }

  return byName.get('restart') ?? group.actions.find((action) => action.action !== 'stop') ?? group.actions[0] ?? null;
}

export function getRuntimeActionButtonClass(tone: string | undefined): string {
  if (tone === 'primary') {
    return 'runtime-button runtime-button-primary';
  }
  if (tone === 'danger') {
    return 'runtime-button runtime-button-danger';
  }
  return 'runtime-button runtime-button-secondary';
}

export function getRuntimePriorityCopy(group: RuntimeGroup): string {
  const failingChecks = getRuntimeFailingChecks(group);
  if (!failingChecks.length) {
    return group.description;
  }
  const [first, second] = failingChecks;
  if (!second) {
    return `${first.label}：${first.detail}`;
  }
  return `${first.label}：${first.detail}；${second.label}：${second.detail}`;
}

export function getRuntimeHeadline(summary: RuntimeSummary): string {
  if (!summary.attentionCount) {
    return '当前常驻链路都在线，可以把注意力放回交易本身。';
  }
  if (summary.stoppedCount && summary.degradedCount) {
    return `现在有 ${summary.stoppedCount} 条链路已停、${summary.degradedCount} 条链路部分可用，先处理停掉的。`;
  }
  if (summary.stoppedCount) {
    return `现在有 ${summary.stoppedCount} 条链路已停止，先把它们拉起来。`;
  }
  return `现在有 ${summary.degradedCount} 条链路部分可用，建议先做一次定点修复。`;
}
