# C03 Onboarding React 深度收口

Status: Proposed
Priority: P0

## 目标

把当前已经进 React 壳层的 onboarding 页面，从“只把壳迁过去”推进到“真正替代旧模板交互”。

## 为什么现在做

现在 `/onboarding/xianyu` 已经走 React 壳，但页面内容只覆盖了队列、发现、简化草稿展示，旧模板里最关键的逐字段编辑、复用模板决策、枚举编辑、preview/apply 工作流还留在 `apps/web/static/onboarding-shell.js`。

## 主要问题证据

- 当前 React onboarding 只展示简化版结果：[OnboardingPage.tsx](<repo-root>/apps/dashboard-react/src/features/onboarding/components/OnboardingPage.tsx)
- 旧模板 JS 仍承载完整草稿编辑器：[onboarding-shell.js](<repo-root>/apps/web/static/onboarding-shell.js)

## 范围

1. 把 queue detail、draft editor、reuse suggestion、enum 编辑、preview/apply 迁入 React。
2. 保留现有 `/api/onboarding/xianyu/*` 接口合同。
3. 删除对旧 `onboarding-shell.js` 的主路径依赖。
4. 为 onboarding 核心交互补测试。

## 不做

1. 不改 raw cate mapping 核心算法。
2. 不改 discovery 采集底层。

## 建议写文件范围

- [OnboardingPage.tsx](<repo-root>/apps/dashboard-react/src/features/onboarding/components/OnboardingPage.tsx)
- [onboardingApi.ts](<repo-root>/apps/dashboard-react/src/features/onboarding/api/onboardingApi.ts)
- `apps/dashboard-react/src/features/onboarding/hooks/**`（new）
- `apps/dashboard-react/src/features/onboarding/components/**`（new）
- [onboarding-shell.js](<repo-root>/apps/web/static/onboarding-shell.js)

## 验证

```bash
npm run test -w @goofish/dashboard-react
npm run typecheck -w @goofish/dashboard-react
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.collector.tests.test_onboarding_entrypoints apps.collector.tests.test_xianyu_category_mapping_service
```

## 完成定义

1. React onboarding 能完整完成 `queue -> draft -> preview -> apply`。
2. 旧模板 JS 不再承担主链路编辑职责。
3. Onboarding 成为真正的 React 运营面，而不是过渡壳。
