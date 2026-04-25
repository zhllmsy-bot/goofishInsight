# T15 LLM Ops 组件拆分与常量提取

Status: Done
Priority: P2
Source: `LlmOpsPage.tsx` 仍偏大，`LlmOpsTraceBlocks.tsx` 含多处未命名阈值和重复交互逻辑
Done At: 2026-04-16

## 目标

把 LLM Ops 页面继续拆成稳定的子组件与常量文件，降低后续修改 trace 详情、usage 面板、消息块时的冲突概率。

## 独占文件

- [LlmOpsPage.tsx](<repo-root>/apps/dashboard-react/src/features/llm-ops/components/LlmOpsPage.tsx)
- [LlmOpsTraceBlocks.tsx](<repo-root>/apps/dashboard-react/src/features/llm-ops/components/LlmOpsTraceBlocks.tsx)
- [llm-ops.css](<repo-root>/apps/dashboard-react/src/features/llm-ops/styles/llm-ops.css)
- `apps/dashboard-react/src/features/llm-ops/components/LlmTraceList.tsx`（new）
- `apps/dashboard-react/src/features/llm-ops/components/LlmTraceDetail.tsx`（new）
- `apps/dashboard-react/src/features/llm-ops/components/LlmUsageSummary.tsx`（new）
- `apps/dashboard-react/src/features/llm-ops/lib/constants.ts`（new）

## 范围

- 从 `LlmOpsPage.tsx` 中拆出 trace 列表、trace 详情、usage summary。
- 把延迟阈值、复制提示持续时间、token 条长度阈值等提取为命名常量。
- 合并重复的复制反馈与展开/收起交互模式。
- 保持当前数据结构和页面视觉基调不变。

## 不做

- 不改 LLM Ops API schema
- 不接入新的状态管理库
- 不改 Dashboard 全局样式文件

## 交付物

- 页面文件明显瘦身
- 常量可单独维护
- 后续新增 trace 详情卡片不会再堆回单个大文件

## 验证

```bash
cd <repo-root>/apps/dashboard-react && npm run build
```

## 完成定义

- `LlmOpsPage.tsx` 只保留页面编排
- `LlmOpsTraceBlocks.tsx` 不再承载页面级状态和多个阈值魔法数字
- 新子组件职责边界清晰

## 实际验收（2026-04-16）

- `apps/dashboard-react && npm run build` 通过
