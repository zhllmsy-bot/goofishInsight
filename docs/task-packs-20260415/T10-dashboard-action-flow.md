# T10 Dashboard 高频动作路径

Status: Done
Priority: P2
Source Todo: W10 完成定义中的 React 侧部分

## 目标

缩短“选型号 -> 看价格 -> 做动作”的高频路径，不改 API 合同，只改组件编排和交互层。

## 独占文件

- [DashboardHeader.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx)
- [DashboardPage.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardPage.tsx)
- [DashboardSidebar.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardSidebar.tsx)
- [PriceGauge.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/PriceGauge.tsx)
- [ListingsPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ListingsPanel.tsx)
- [FocusPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/FocusPanel.tsx)
- [ReferencePanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ReferencePanel.tsx)
- [RuntimeControlGrid.tsx](<repo-root>/apps/dashboard-react/src/features/runtime/components/RuntimeControlGrid.tsx)
- [dashboard.css](<repo-root>/apps/dashboard-react/src/features/dashboard/styles/dashboard.css)

## 范围

- 高频动作减少跨页跳转
- 关键动作尽量收敛到单屏或相邻区域
- 不动 API schema

## 交付物

- W10 完成定义中的 React 高频路径收口

## 执行记录（2026-04-15）

- 已将“选型号 -> 看价格 -> 做动作”收敛到首页同一动作带：`SelectionPanel + PricingPanel + ListingsPanel` 形成连续操作区，减少跨区切换。
- 侧栏新增当前选择摘要与“一键清空型号筛选”，降低回退操作成本。
- 价格区新增快捷动作（机会筛选切换 + 运行控制入口），列表区新增流程提示与运行控制快捷入口。
- Focus/Trend 卡片补齐相邻动作链接（买方工作台、运行控制），让“判断 -> 执行”在同屏闭环。
- RuntimeControlGrid 增加每组前两个动作的快捷按钮，缩短常见操作路径。
- 样式层补齐高频动作区视觉分组和链接/快捷操作样式，保持不改 API schema。

## 实际验证（2026-04-15）

```bash
cd apps/dashboard-react && npm run build
```

- 结果：通过（`tsc -b && vite build` 成功）。

## 验证

```bash
cd apps/dashboard-react && npm run build
```
