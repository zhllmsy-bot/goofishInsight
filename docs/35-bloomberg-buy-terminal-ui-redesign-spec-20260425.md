# Bloomberg 级买方情报终端 UI 重设计技术方案

Status: Historical v1, superseded by [39-goofish-insight-ui-constitution-v2-20260426.md](./39-goofish-insight-ui-constitution-v2-20260426.md)
Updated: 2026-04-25
Workspace: `<repo-root>`

Related:

- [23-best-practice-architecture-implementation-spec.md](<repo-root>/docs/23-best-practice-architecture-implementation-spec.md)
- [32-dashboard-ui-design-system-migration-todolist-20260425.md](<repo-root>/docs/32-dashboard-ui-design-system-migration-todolist-20260425.md)
- [36-bloomberg-buy-terminal-ui-redesign-todolist-20260425.md](<repo-root>/docs/36-bloomberg-buy-terminal-ui-redesign-todolist-20260425.md)

## 1. 目标

把 Goofish Insight dashboard 从通用 SaaS 仪表盘升级为买方决策终端。

首个标杆页是 `/` 今日机会台。它必须优先帮助操作员在同一屏内判断：

- 买入
- 观察
- 跳过
- 打开证据
- 回写反馈或成交

本轮不全站重写，先把 foundation token 与今日机会台做成后续页面的 UI benchmark。Current implementation must follow the v2 constitution when this v1 draft differs.

## 2. 美学参照系

正向参照：

- Bloomberg Terminal：信息密度、右对齐数字、行内价格量尺、专业冷感
- Linear：键盘优先、超薄边框、命令面板、少装饰
- Arc Browser：侧边栏和顶部命令入口共同承担导航
- Notion Calendar：冷灰暗色、字重和 surface 阶梯表达层级
- Raycast：`⌘K` 是全局第一入口，主要动作两键内可达

反向参照：

- 不使用 Ant Design / Material / shadcn 默认模板作为视觉终点
- 不做大卡片堆叠、大留白、渐变背景、装饰性光效
- 不把配置页做成数据库字段表单

## 3. 视觉硬约束

### 3.1 色彩

Light 默认主题：

| Token | Value | 用途 |
|---|---|---|
| `bg-canvas` | `#FAFAF9` | App 底 |
| `bg-panel` | `#FFFFFF` | 主面板 |
| `bg-subtle` | `#F4F4F2` | hover / 区块底 |
| `bg-muted` | `#EAEAE7` | 分隔条 |
| `border-hair` | `#E5E5E2` | 1px 发丝边 |
| `text-primary` | `#1A1A17` | 主文字 |
| `text-secondary` | `#60605B` | 次文字 |
| `text-tertiary` | `#9A9A92` | 标签 |
| `accent` | `#0066FF` | 唯一强调色 |
| `up` | `#0A7F3F` | 涨 / 正向 |
| `down` | `#C8342B` | 跌 / 风险 |

Dark 主题：

| Token | Value |
|---|---|
| `bg-canvas` | `#0E0E0C` |
| `bg-panel` | `#161613` |
| `bg-subtle` | `#1E1E1B` |
| `bg-muted` | `#28282A` |
| `border-hair` | `#2E2E2B` |
| `text-primary` | `#EDEDE8` |
| `text-secondary` | `#A5A59E` |
| `text-tertiary` | `#6C6C66` |
| `accent` | `#3B8AFF` |
| `up` | `#3FBF6A` |
| `down` | `#EA5B52` |

现有代码变量继续用 `--surface-* / --ink-* / --brand-* / --signal-*` 承接，但值必须映射到上述集合，不新增任意色。

### 3.2 字体与数字

- Sans：`Inter Variable`, `PingFang SC`, system fallback
- Mono：`JetBrains Mono Variable`, `SF Mono`, monospace
- 所有数字使用 `--font-num = --font-mono` 与 tabular nums
- SKU、型号、baseline key、schema 版本用 mono
- 标题字重 560，正文 420，数字 500-520
- v2 constitution is the active typography contract. In this execution environment, code must also obey the active frontend harness rule that forbids negative tracking.

### 3.3 字号

| Token | Size / Line | Weight | 用途 |
|---|---|---|---|
| `display` | 28 / 32 | 520 | 焦点价格 |
| `h1` | 18 / 26 | 560 | 页面/面板标题 |
| `body` | 13 / 20 | 420 | 正文、表格 |
| `caption` | 11 / 16 | 440 | 标签、辅助 |
| `mono` | 12 / 18 | 500 | ID、代码 |

### 3.4 间距与圆角

间距只用：

`2 / 4 / 8 / 12 / 16 / 24`

内部 padding 不超过 24px。兼容旧 token 名时，`--space-8` 及以上不得超过 24px。

圆角只用：

`0 / 4 / 6 / 10`

- 按钮和输入框：4
- 普通分组：6
- 浮层：10
- 禁止大于 10px 的新圆角

### 3.5 边框与阴影

- 默认层级使用 1px 发丝边和 surface 阶梯
- 全站常规 UI 不使用阴影
- 浮层保留视觉层级能力，但应优先使用 border + surface，阴影只作为例外

### 3.6 动效

- 状态反馈：120ms
- Sheet / Drawer 空间连续性：200ms
- 禁止页面入场动画、卡片入场动画、hover 上浮、hover 放大

## 4. 今日机会台合同

### 4.1 信息架构

首屏结构：

1. 56px 级顶部全局栏：`⌘K Search / category / date / new count / live`
2. 左侧紧凑品类树：Apple / Camera / Garmin
3. 主工作区：Today opportunity queue
4. 行内机会列表：每行 56px，一屏至少 10 条
5. 右侧 Sheet 详情：点击行或 Enter 打开，不离开上下文
6. 下方辅助区：反馈校准、数据价值、watch targets、baselines

### 4.2 机会行

每行必须表达：

- title / SKU fingerprint
- current price，display 级、mono、右对齐
- discount vs fair/P50，使用 up/down + 形状或符号双编码
- score / risk
- P15/P35/P50 或当前可用 baseline proxy
- inline signal bar
- sample/confidence/tier/schema proxy
- listed time ago，30s 本地刷新
- hidden-on-hover actions：open detail / contacted / skip / purchased

禁止把机会渲染成大卡片。

### 4.3 详情 Sheet

点击行、`Enter`、或命令面板动作打开右侧 480-560px Sheet。

Sheet 必须包含：

- 标题与 SKU 指纹
- 当前价格与相对 fair/P50 差异
- score / risk / spec confidence
- 90-day trend 区域占位或 sparkline
- condition/evidence 摘要
- baseline/schema 摘要
- actions：Open on Goofish / Watch / Skip / Mark bought

详情页路由可保留作为深链，但主流程不得跳页。

### 4.4 键盘

- `⌘K`：全局命令入口
- `J/K`：机会列表上下移动
- `Enter`：打开当前行 Sheet
- `A`：标记联系或感兴趣
- `D`：跳过
- `G O`：今日机会
- `G M`：市场大盘
- `G C`：配置后台

输入框、textarea、select、contenteditable 聚焦时不得劫持这些快捷键。

## 5. 配置页后续合同

配置页最终应升级为三层路径：

1. UI 模式：Inline Table Editor，单元格原地编辑
2. YAML 模式：同一份 category template 可用 YAML 编辑
3. GitOps 模式：`config/categories/*.yaml` 走 PR / CI / audit

本轮只把 spec 固化，配置页完整改造进入后续 todo，避免影响今日机会台标杆实现。

## 6. 验收标准

- 今日机会台首屏能看到至少 8 条机会行
- 主题 token 映射到规定色彩集合
- 常规 UI 无阴影
- 数字全部 mono + tabular nums
- 圆角不超过 10px
- 内部间距不超过 24px
- `⌘K`、`J/K`、`Enter`、`A/D`、`G O/M/C` 可用
- 详情用 Sheet 打开
- 机会行不是大卡片
- Light / Dark 均可读
- `npm run design-system:check -w @goofish/dashboard-react` 通过
- 相关 React tests 通过
- 若时间允许，跑 `npm run verify-baseline`
