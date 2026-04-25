# C05 主工作流闭环 E2E 合同测试

Status: Delivered (phase-1, 2026-04-21)
Priority: P0

## 目标

为当前最重要的产品闭环建立跨页面合同测试，防止继续出现“页面迁了，但工作流断了”的问题。

## 必测闭环

1. `看板筛选 -> 商品详情 -> 返回看板`
2. `看板筛选 -> 买方机会 -> 反馈回写 -> 返回看板`
3. `看板筛选 -> runtime -> 返回看板`
4. `看板筛选 -> onboarding -> queue -> draft`
5. `bff` 模式下上述主路径可进入

## 为什么现在做

当前只有局部 query 保持测试和单页面测试，缺少真正按用户路径组织的合同验证。

## 主要问题证据

- 当前测试以页面碎片为主：`apps/dashboard-react/src/features/**/**/*.test.tsx`
- React 与 FastAPI / Nest 的对齐依赖人工判断

## 范围

1. 为 React 主工作流增加 route-level flow tests。
2. 为 FastAPI/Nest 增加路由入口 contract tests。
3. 明确哪些合同只在 FastAPI 模式验证，哪些需要 BFF 双模验证。

## 不做

1. 不上真实浏览器 E2E 基础设施。
2. 不做外部依赖联调。

## 建议写文件范围

- `apps/dashboard-react/src/features/dashboard/lib/workspaceFlows.test.ts`
- `apps/dashboard-react/src/features/onboarding/components/OnboardingPage.test.tsx`
- `apps/collector/tests/test_review_entrypoints.py`
- `apps/collector/tests/test_onboarding_entrypoints.py`
- `apps/dashboard-nest/test/**`

## 验证

```bash
npm run test -w @goofish/dashboard-react
npm run test:e2e -w @goofish/dashboard-nest -- --runInBand
PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src ./.venv/bin/python -m unittest apps.collector.tests.test_review_entrypoints apps.collector.tests.test_onboarding_entrypoints
```

## 完成定义

1. 主工作流有明确 contract tests。
2. 新迁页面如果破坏 query / route / back flow，会被测试直接打断。

## 2026-04-21 落地记录

1. 已补后端主路径合同测试：`apps/collector/tests/test_review_entrypoints.py`
2. 已补前端闭环测试：
   - `apps/dashboard-react/src/features/dashboard/lib/workspaceFlows.test.ts`
   - `apps/dashboard-react/src/features/buy/components/BuyWorkbenchPage.test.tsx`
   - `apps/dashboard-react/src/features/runtime/components/RuntimePage.test.tsx`
3. 已执行并通过：
   - `PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src ./.venv/bin/python -m unittest apps.collector.tests.test_review_entrypoints`
   - `npm run test -w @goofish/dashboard-react -- BuyWorkbenchPage RuntimePage workspaceFlows`
