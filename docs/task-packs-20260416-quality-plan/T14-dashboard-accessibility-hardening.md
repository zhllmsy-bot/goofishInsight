# T14 Dashboard 可访问性语义补强

Status: Done
Priority: P2
Source: Dashboard 交互控件语义不完整，tabs/tree/navigation 的 a11y 质量不足

## 目标

优先修复最影响键盘导航和读屏器理解的语义缺口，让导航树、参考面板 tabs、顶部导航和运行控制快捷区都具备明确语义。

## 独占文件

- [ReferencePanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ReferencePanel.tsx)
- [DashboardSidebar.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardSidebar.tsx)
- [DashboardHeader.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx)
- [RuntimeControlGrid.tsx](<repo-root>/apps/dashboard-react/src/features/runtime/components/RuntimeControlGrid.tsx)
- [dashboard.css](<repo-root>/apps/dashboard-react/src/features/dashboard/styles/dashboard.css)
- [runtime.css](<repo-root>/apps/dashboard-react/src/features/runtime/styles/runtime.css)

## 范围

- 为参考面板 tabs 补齐 `role="tablist" / role="tab" / role="tabpanel"`、`aria-selected`、`aria-controls`、键盘切换。
- 为侧栏树状导航补齐层级语义、当前项标记和键盘焦点样式。
- 为顶部导航和 runtime 快捷动作补齐可读标签。
- 明确焦点态样式，避免键盘导航“有语义没视觉”。

## 不做

- 不改 `DashboardPage.tsx`
- 不改 `ListingsPanel.tsx`
- 不在本任务里改图片资源或补所有 alt 文案

## 交付物

- tabs、tree、nav 三类核心控件达到可用语义标准
- 键盘操作路径可跑通
- 焦点态具备明显可视反馈

## 验证

```bash
cd <repo-root>/apps/dashboard-react && npm run build
```

## 完成定义

- `ReferencePanel` 的按钮不再只是“长得像 tabs”
- 侧栏当前选中项与展开项可被辅助技术识别
- 关键交互区可通过键盘完成切换和触发
