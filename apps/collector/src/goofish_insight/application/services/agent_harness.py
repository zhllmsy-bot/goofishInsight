from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ...settings import get_settings


@dataclass(frozen=True)
class AgentHarnessTaskSeed:
    key: str
    title: str
    owner: str
    status: str
    priority: str
    scope: str
    summary: str
    rationale: str
    acceptance_criteria: list[str]
    dependencies: list[str]
    files: list[str]
    middleware_focus: list[str]
    started_offset_minutes: int
    updated_offset_minutes: int
    progress: int
    risk: str


TASK_SEEDS: tuple[AgentHarnessTaskSeed, ...] = (
    AgentHarnessTaskSeed(
        key="narrative-sync",
        title="统一 README / PRD / SPEC 的北极星叙事",
        owner="lead-agent",
        status="in_review",
        priority="high",
        scope="docs",
        summary="先消除产品目标漂移，避免后续 agent 在两套目标之间来回修补。",
        rationale="现状评估已经确认 README 仍然停留在 PoC 叙事，而 PRD/SPEC 已经进入价格指导助手阶段；这会直接影响任务优先级判断。",
        acceptance_criteria=[
            "README、PRD、SPEC 对产品定位的描述一致",
            "补一份 DeerFlow pilot 设计文档，明确为何先做控制台和任务闭环",
        ],
        dependencies=[],
        files=[
            "README.md",
            "SPEC.md",
            "docs/18-reliable-price-assistant-prd.md",
        ],
        middleware_focus=["SummarizationMiddleware", "MemoryMiddleware", "TodoMiddleware"],
        started_offset_minutes=38,
        updated_offset_minutes=6,
        progress=82,
        risk="如果叙事不统一，后续自动拆任务会持续跑偏。",
    ),
    AgentHarnessTaskSeed(
        key="baseline-primary-key",
        title="把 templateKey 升成正式 baseline 主键",
        owner="pricing-fixer",
        status="running",
        priority="critical",
        scope="collector-backend",
        summary="定价链路要先有稳定主键，后续 alert、feedback、watch target 才能真正共享一个实体。",
        rationale="当前 baseline 仍部分依赖 view:label 这种展示型 key，会影响聚合、迁移和回流归因。",
        acceptance_criteria=[
            "baseline 统一读写 templateKey / pricing_selector_json",
            "opportunity、baseline、watch target 共用同一选择器",
            "补回归测试覆盖 key 迁移",
        ],
        dependencies=["narrative-sync"],
        files=[
            "apps/collector/src/goofish_insight/application/services/buy_price_baselines.py",
            "apps/collector/src/goofish_insight/application/services/buy_opportunities.py",
            "apps/collector/src/goofish_insight/application/services/pricing_templates.py",
        ],
        middleware_focus=["GuardrailMiddleware", "SandboxAuditMiddleware", "LoopDetectionMiddleware"],
        started_offset_minutes=31,
        updated_offset_minutes=2,
        progress=46,
        risk="这是后续自动修复是否可并行的分水岭，主键不稳会让多个 agent 修同一实体时互相踩归因。",
    ),
    AgentHarnessTaskSeed(
        key="feedback-execution",
        title="把 calibration recommendation 升级成可执行回写",
        owner="feedback-fixer",
        status="queued",
        priority="high",
        scope="buy-feedback",
        summary="把建议型闭环变成执行型闭环，让反馈能真正改阈值和排序策略。",
        rationale="目前系统能产出 calibration suggestion，但还不能自动形成策略变更候选，这会让闭环停在人工解释阶段。",
        acceptance_criteria=[
            "生成可执行 calibration patch payload",
            "记录提案状态、审核结论和回滚信息",
            "为后续人工审批或自动执行保留审计线索",
        ],
        dependencies=["baseline-primary-key"],
        files=[
            "apps/collector/src/goofish_insight/application/services/buy_feedback.py",
            "apps/collector/src/goofish_insight/application/services/pricing_thresholds.py",
        ],
        middleware_focus=["GuardrailMiddleware", "ClarificationMiddleware", "ToolErrorHandlingMiddleware"],
        started_offset_minutes=0,
        updated_offset_minutes=0,
        progress=0,
        risk="如果直接自动回写，没有审计和审批面板就会放大策略漂移风险。",
    ),
    AgentHarnessTaskSeed(
        key="buy-workbench-gap",
        title="补齐 buy targets / baselines / opportunity detail 工作流",
        owner="frontend-fixer",
        status="running",
        priority="high",
        scope="dashboard-react",
        summary="把当前只有机会页的工作台，补成真正能运营 watch target 和 baseline 的决策界面。",
        rationale="现有 React 页面更多像单点操作台，还不是完整的买方运营面板。",
        acceptance_criteria=[
            "新增 targets、baseline、detail 三类页面入口",
            "关键对象都能看到为什么被推荐、当前状态和可执行动作",
            "移动到 React 主导航而不是依赖旧页面兜底",
        ],
        dependencies=["narrative-sync"],
        files=[
            "apps/dashboard-react/src/features/buy/components/BuyWorkbenchPage.tsx",
            "apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx",
        ],
        middleware_focus=["TitleMiddleware", "ThreadDataMiddleware", "DeferredToolFilterMiddleware"],
        started_offset_minutes=19,
        updated_offset_minutes=4,
        progress=33,
        risk="前端工作流不补齐，后端再强也只能停留在内部分析工具。",
    ),
    AgentHarnessTaskSeed(
        key="roi-funnel-loop",
        title="补齐 ROI / 漏斗指标闭环",
        owner="analytics-fixer",
        status="blocked",
        priority="medium",
        scope="analytics",
        summary="把提醒是否带来收益这件事从文档口径变成系统事实。",
        rationale="商业结果闭环目前只在 spec 里定义了 watch_to_open_rate 等指标，系统里还缺完整实现与监控面板。",
        acceptance_criteria=[
            "定义漏斗事件来源与归因口径",
            "dashboard 能展示提醒到成交的关键转化",
            "机会页能回显该机会的收益证明状态",
        ],
        dependencies=["baseline-primary-key", "feedback-execution"],
        files=[
            "docs/16-buy-side-implementation-spec.md",
            "apps/collector/src/goofish_insight/application/services/buy_alerts.py",
        ],
        middleware_focus=["MemoryMiddleware", "SummarizationMiddleware", "TodoMiddleware"],
        started_offset_minutes=0,
        updated_offset_minutes=14,
        progress=12,
        risk="依赖上游主键和反馈闭环，否则收益归因无法稳定落到同一对象。",
    ),
)


MIDDLEWARE_STACK: tuple[dict[str, str], ...] = (
    {
        "name": "SummarizationMiddleware",
        "layer": "L1",
        "purpose": "消息窗口达到阈值时压缩上下文，保住 Lead Agent 的决策带宽。",
    },
    {
        "name": "SubagentLimitMiddleware",
        "layer": "L2",
        "purpose": "限制一次并行 fan-out 数量，避免多个修复任务抢同一文件写集。",
    },
    {
        "name": "MemoryMiddleware",
        "layer": "L3",
        "purpose": "把高置信事实沉淀到下一轮注入，减少重复分析同一问题。",
    },
    {
        "name": "DeferredToolFilterMiddleware",
        "layer": "L4",
        "purpose": "按需暴露工具和技能，降低 prompt 面噪音。",
    },
    {
        "name": "GuardrailMiddleware",
        "layer": "Safety",
        "purpose": "拦住高风险动作，要求先给出 why、影响面和回滚面。",
    },
    {
        "name": "SandboxAuditMiddleware",
        "layer": "Safety",
        "purpose": "审计 shell / patch 动作，把执行证据写进任务事件流。",
    },
    {
        "name": "LoopDetectionMiddleware",
        "layer": "Loop",
        "purpose": "检测 stuck / oscillation / no-op 循环，必要时中止并上报人工。",
    },
    {
        "name": "ClarificationMiddleware",
        "layer": "Loop",
        "purpose": "当信息缺失会改变结论时转为待确认，而不是盲改代码。",
    },
)


def _status_tone(status: str) -> str:
    return {
        "running": "active",
        "in_review": "review",
        "queued": "queued",
        "blocked": "blocked",
        "done": "done",
    }.get(status, "queued")


def _format_relative_minutes(now: datetime, earlier: datetime) -> str:
    delta = max(int((now - earlier).total_seconds() // 60), 0)
    if delta < 1:
        return "刚刚"
    if delta < 60:
        return f"{delta} 分钟前"
    hours = delta // 60
    minutes = delta % 60
    if minutes == 0:
        return f"{hours} 小时前"
    return f"{hours} 小时 {minutes} 分前"


def _build_task_payload(now: datetime, seed: AgentHarnessTaskSeed) -> dict[str, Any]:
    started_at = now - timedelta(minutes=seed.started_offset_minutes)
    updated_at = now - timedelta(minutes=seed.updated_offset_minutes)
    return {
        "key": seed.key,
        "title": seed.title,
        "owner": seed.owner,
        "status": seed.status,
        "tone": _status_tone(seed.status),
        "priority": seed.priority,
        "scope": seed.scope,
        "summary": seed.summary,
        "rationale": seed.rationale,
        "acceptanceCriteria": seed.acceptance_criteria,
        "dependencies": seed.dependencies,
        "files": seed.files,
        "middlewareFocus": seed.middleware_focus,
        "startedAt": started_at.isoformat(),
        "updatedAt": updated_at.isoformat(),
        "updatedAtRelative": _format_relative_minutes(now, updated_at),
        "progress": seed.progress,
        "risk": seed.risk,
    }


def build_agent_harness_snapshot() -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)
    tasks = [_build_task_payload(now, seed) for seed in TASK_SEEDS]
    running_count = sum(1 for task in tasks if task["status"] == "running")
    queued_count = sum(1 for task in tasks if task["status"] == "queued")
    blocked_count = sum(1 for task in tasks if task["status"] == "blocked")
    completed_count = sum(1 for task in tasks if task["status"] == "done")
    review_count = sum(1 for task in tasks if task["status"] == "in_review")
    event_entries = [
        {
            "id": "evt-001",
            "kind": "decompose",
            "tone": "info",
            "title": "Lead Agent 完成第一轮任务拆分",
            "detail": "把商业化成熟度缺口拆成 5 个独立写集，前端、反馈、ROI 任务可并行推进。",
            "at": (now - timedelta(minutes=21)).isoformat(),
            "atRelative": _format_relative_minutes(now, now - timedelta(minutes=21)),
        },
        {
            "id": "evt-002",
            "kind": "review",
            "tone": "review",
            "title": "README / PRD / SPEC 目标漂移被提升为首要任务",
            "detail": "叙事不统一会让后续每个 agent 的优先级判断失真，因此先锁定北极星再扩任务池。",
            "at": (now - timedelta(minutes=17)).isoformat(),
            "atRelative": _format_relative_minutes(now, now - timedelta(minutes=17)),
        },
        {
            "id": "evt-003",
            "kind": "execute",
            "tone": "active",
            "title": "pricing-fixer 正在治理 baseline 主键",
            "detail": "当前 task 绑定了 buy_price_baselines / buy_opportunities / pricing_templates 三个文件域，避免其他 agent 进入同一写集。",
            "at": (now - timedelta(minutes=9)).isoformat(),
            "atRelative": _format_relative_minutes(now, now - timedelta(minutes=9)),
        },
        {
            "id": "evt-004",
            "kind": "risk",
            "tone": "blocked",
            "title": "ROI 漏斗任务被标记为 blocked",
            "detail": "商业结果闭环依赖 templateKey 和 feedback execution 两个前置任务完成，否则收益归因会失真。",
            "at": (now - timedelta(minutes=5)).isoformat(),
            "atRelative": _format_relative_minutes(now, now - timedelta(minutes=5)),
        },
        {
            "id": "evt-005",
            "kind": "platform",
            "tone": "info",
            "title": "当前 pilot 运行在静态 snapshot 模式",
            "detail": "本轮先把 DeerFlow 风格的控制平面落进 goofish-insight，下一步再接真实队列、worktree 和执行器。",
            "at": (now - timedelta(minutes=2)).isoformat(),
            "atRelative": _format_relative_minutes(now, now - timedelta(minutes=2)),
        },
    ]
    lead_rationale = [
        "先修产品叙事漂移，再让并行 agent 接手具体写集，避免每个 worker 各自理解目标。",
        "先治理 templateKey 这类主键问题，再推进 feedback / ROI，不然多个闭环都会共享脆弱标识。",
        "把 blocked 任务直接展示出来，控制台要回答的不只是正在做什么，还要回答为什么现在不做。",
    ]

    return {
        "updatedAt": now.isoformat(),
        "workspace": {
            "name": "goofish-insight",
            "path": str(settings.base_dir),
            "executionMode": "deerflow-pilot",
            "sandboxMode": "isolated-worktree-planned",
        },
        "leadRun": {
            "id": "lead-run-2026-04-17-01",
            "title": "Goofish Insight 商业化闭环改造",
            "status": "executing",
            "goal": "把现状评估收敛成可执行的多 agent 并行任务图，并为后续真实 agent 执行准备控制台与审计面。",
            "summary": "当前先落 DeerFlow 风格 control plane：任务拆分、why、事件流、middleware 视角。真实 repair executor 下一步接入。",
            "iteration": 1,
            "maxIterations": 6,
            "loopState": "executing",
            "humanGate": "仅在高风险配置回写或 GUI 操作时升级人工确认",
            "lastDecisionAt": (now - timedelta(minutes=3)).isoformat(),
            "lastDecisionRelative": _format_relative_minutes(now, now - timedelta(minutes=3)),
            "rationale": lead_rationale,
        },
        "metrics": {
            "taskCount": len(tasks),
            "runningCount": running_count,
            "queuedCount": queued_count,
            "blockedCount": blocked_count,
            "reviewCount": review_count,
            "completedCount": completed_count,
            "parallelismBudget": 3,
            "activeMiddlewares": len(MIDDLEWARE_STACK),
        },
        "middlewareStack": list(MIDDLEWARE_STACK),
        "tasks": tasks,
        "events": event_entries,
        "nextActions": [
            "接入真实队列和 worktree allocator，让每个 task 拿到独立分支和写集锁。",
            "把 feedback execution 任务升级成可审核 patch proposal，而不是只有 recommendation 文本。",
            "把 ROI funnel 事件源接到 dashboard，形成提醒到收益的证据链。",
        ],
    }
