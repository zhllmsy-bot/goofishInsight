# C10 Runtime 与 resident 能力统一产品面

Status: In Progress (runtime health + collect run landed, 2026-04-22)
Priority: P1

## 目标

把 runtime 页面从“操作 launchd / resident 的技术页”推进成“运营真正可用的运行面”，并与 analyzer / collect / model / feed / batch 的真实状态保持一致。

## 为什么现在做

现在 runtime 已经在 React 里，但更像技术控制板，和产品工作流、异常恢复、任务上下文还没有形成真正闭环。

## 范围

1. 明确 runtime 分组与主工作流关系。
2. 补从 dashboard / progress / onboarding / buy 回到 runtime 的上下文。
3. 增加更适合运营使用的状态摘要、异常优先级与建议动作。

## 不做

1. 不重写底层 launchd 管理实现。
2. 不改 resident 本身部署方式。

## 建议写文件范围

- [RuntimePage.tsx](<repo-root>/apps/dashboard-react/src/features/runtime/components/RuntimePage.tsx)
- `apps/dashboard-react/src/features/runtime/components/**`
- `apps/collector/src/goofish_insight/application/services/runtime_*`

## 验证

```bash
npm run test -w @goofish/dashboard-react
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.collector.tests.test_runtime_controls
```

## 完成定义

1. runtime 不是孤立页，而是主工作区的一部分。
2. 用户能从 runtime 直接看懂哪里坏了、先动什么、动完是否恢复。

## 2026-04-22 增量成果

1. 运行脚本、launchd、CLI 的 `PYTHONPATH` 已统一补上 analyzer/schema 路径，修复 analyzer 依赖漂移启动失败。
2. DB migration 已补齐 `home_feed_item_decision` 缺表与 `category_validation_status` 长度溢出问题，运行面可持续写入。
3. attached-browser batch collect 已完成一轮实跑：`collect-batch --only-task garmin-fenix --parallel-tabs 1`，`show-health` 最新多条 run 连续 `status=completed` 且 `pages_succeeded=5`。
