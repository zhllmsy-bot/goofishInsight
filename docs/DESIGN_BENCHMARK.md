# 设计参照与视觉基准（Design Benchmark）

> 目的：防止 dashboard 在“技术实现”过程中漂移到无识别度风格；每次大改都回归本文件。

## 参照系（外部）

本项目不复刻外观，仅借鉴信息密度、层次、导航和密集数据面表达节奏。

- **Bloomberg Terminal（官方站点）**  
  参照点：信息优先级、表格式密度、告警与数据标注方式。
- **Linear（官方站点）**  
  参照点：命令式导航、布局稳定性、快捷键优先语义。
- **Notion（官方站点）**  
  参照点：日常审美约束与交互清晰度（尤其是列表/筛选信息条）

## 参照规范（需长期保持）

1. **第一屏可决策性**  
   首屏必须先给机会，不给“空说明”。空态、欢迎说明、教学页均不是运营入口。
2. **密度优先，干扰最小**  
   同屏信息超过 8 条机会后仍可快速扫描；低价值装饰不得抢占主视觉。
3. **可解释性优先于花哨**  
   价格线、置信度、样本计数、Schema 版本与异常原因需固定显示。
4. **统一主题系统**  
   严禁新增任意裸色值；所有颜色、间距、圆角、阴影均通过 token 表达。
5. **键盘第一类交互**  
   J/K、G-系列、Enter、A/D、ESC 等主路径要有可见状态和快捷说明。

## Dashboard 验收入口

每次发布前至少执行一次：

1. `npm run design-system:check -w @goofish/dashboard-react`
2. `npm run design-system:audit -w @goofish/dashboard-react`
3. `npm run verify-baseline`
4. 机会页截图人工审读（Dark / Light）：确认主信息密度与可读性
5. 关键路径截图（今日机会台、机会详情抽屉、配置页）：保存在本地会议记录中

## 自有审计清单（必须逐项更新）

每次新增视觉组件前，记录：

- 组件用途（信息优先级）
- 目标 token（颜色/间距/字号/圆角）
- 是否需要支持 Light + Dark
- 与 `OpportunityCard`/`AnalyticsCard`/`KpiTile`/`PriceGauge` 关系
- 键盘状态流是否破坏 tab 顺序
- 触发该组件的业务动作与退出动作

## 资产与截图要求

- 任何最终设计参考图建议使用“本项目截图”或内部演示截图；不引入版权争议较高的外部 UI 图片。
- 新截图文件建议统一放到 `docs/design-benchmarks/`，命名格式：
  - `dashboard-opportunity-YYYYMMDD-dark.png`
  - `dashboard-opportunity-YYYYMMDD-light.png`
  - `dashboard-config-YYYYMMDD.png`

## 版本约束

- 本基准用于 v1.0 前冻结，任何偏离都需在对应 PR 说明中给出“参照系差异”理由。
- 设计系统优先级高于页面级微调，统一交给设计 token 与复合组件层解决。
