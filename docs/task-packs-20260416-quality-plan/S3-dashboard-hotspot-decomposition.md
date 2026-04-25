# S3 Dashboard 热点组件拆分收口

Status: Proposed
Priority: P2
Source: `DashboardPage.tsx` 与 `ListingsPanel.tsx` 仍是 React 侧热点大文件，容易成为后续改动冲突中心

## 启动条件

- `T13` 与 `T14` 已完成
- Dashboard API/config 相关改动已在 `T12` 稳定

## 目标

把 Dashboard 高频路径中的两个热点文件拆成更稳定的编排层与子组件层，降低后续继续做 UX、a11y、测试时的冲突面。

## 独占文件

- [DashboardPage.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardPage.tsx)
- [ListingsPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ListingsPanel.tsx)
- `apps/dashboard-react/src/features/dashboard/components/DashboardQuickJump.tsx`（new）
- `apps/dashboard-react/src/features/dashboard/components/ListingCard.tsx`（new）
- `apps/dashboard-react/src/features/dashboard/components/ListingControls.tsx`（new）
- `apps/dashboard-react/src/features/dashboard/lib/listingViewModel.ts`（new）
- `apps/dashboard-react/src/features/dashboard/styles/listing-panel.css`（new）

## 范围

- 把 `DashboardQuickJump` 从页面文件中抽出。
- 把 Listing 卡片、排序筛选、偏好动作从 `ListingsPanel.tsx` 中拆出。
- 让页面文件只保留数据编排与事件桥接。
- 允许新增局部样式文件，不回写 `dashboard.css`。

## 不做

- 不改 dashboard API schema
- 不改 sidebar / reference / runtime 组件
- 不做大范围视觉重设计

## 交付物

- 两个热点文件显著瘦身
- 列表卡片与控制条可单独测试
- 后续新增功能不必再堆回单文件

## 验证

```bash
cd <repo-root>/apps/dashboard-react && npm run build
```

## 完成定义

- `DashboardPage.tsx` 主要负责组合，不再内嵌大块 UI 细节
- `ListingsPanel.tsx` 主要负责组装，不再承载全部卡片细节与排序逻辑
- 新子组件边界与命名可长期维持
