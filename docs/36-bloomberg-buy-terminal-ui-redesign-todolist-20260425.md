# Bloomberg 级买方情报终端 UI 重设计 Todo

Status: Active
Updated: 2026-04-25
Spec: [35-bloomberg-buy-terminal-ui-redesign-spec-20260425.md](<repo-root>/docs/35-bloomberg-buy-terminal-ui-redesign-spec-20260425.md)

## 执行日志

- 2026-04-25：启动 UI benchmark 重设计。先建立 spec 与 todo，再执行 foundation token 与 `/` 今日机会台标杆页。

## Phase 0：合同冻结

- [x] 固化 Bloomberg / Linear / Notion Calendar / Raycast 参照系
- [x] 明确“不全站大改，先做今日机会台标杆页”
- [x] 明确 dashboard React 继续遵守 token-only、Light/Dark 同步和 `AppFrame`
- [x] 明确标题字距因上层 UI 约束保持 `0`

## Phase 1：Foundation Token

- [x] 收口字体：sans + mono + 数字 mono
- [x] 收口字号：display / h1 / body / caption / mono
- [x] 收口间距：2 / 4 / 8 / 12 / 16 / 24
- [x] 收口圆角：0 / 4 / 6 / 10
- [x] Light 主题映射到 Bloomberg 白模色表
- [x] Dark 主题映射到冷灰色表
- [x] 常规阴影变量归零
- [x] 检查 shared UI primitive 是否仍引入大圆角、阴影或过大 padding

## Phase 2：今日机会台标杆页

- [x] 移除 `/` 首屏 SaaS hero 和副驾驶大卡片
- [x] 改成顶部状态条 + 左侧品类树 + 主机会队列
- [x] 机会从大卡片改成 dense row
- [x] 每行突出 current price、discount、score、risk、baseline proxy、signal bar
- [x] 行内数字全部 mono + tabular nums
- [x] 一屏至少能看到 8 条机会
- [x] Hover 或 focus 时出现动作，不破坏行高
- [x] 保留反馈回写：联系、跳过、成交、打开原始商品
- [x] 保留 purchase outcome inline form
- [x] 空态、加载态、错误态适配终端风格

## Phase 3：详情 Sheet

- [x] 点击行打开右侧 Sheet，不跳出列表上下文
- [x] `Enter` 打开当前选中机会 Sheet
- [x] Sheet 显示价格、discount、score、risk、spec confidence、baseline/schema 摘要
- [x] Sheet actions 覆盖 Open on Goofish / Watch / Skip / Mark bought
- [x] Sheet 宽度控制在 480-560px，移动端占满宽
- [x] 移除详情 Sheet 内不必要的新页跳转主动作

## Phase 4：键盘与命令入口

- [x] `⌘K` 全局搜索入口已存在
- [x] `J/K` 机会列表导航已存在
- [x] `A/D` 快捷反馈已存在
- [x] `Enter` 打开详情 Sheet 已存在
- [x] 新增 `G O` 跳今日机会
- [x] 新增 `G M` 跳市场大盘
- [x] 新增 `G C` 跳配置后台
- [x] 快捷键在输入控件聚焦时不触发

## Phase 5：辅助区收敛

- [x] 数据价值区从大面板改成 dense summary
- [x] 反馈校准区保留可操作性，但降噪为表格/行式布局
- [x] Watch targets / price baselines 改为紧凑列表
- [x] 保留现有 API 合同，不为 UI 改造改后端

## Phase 6：配置页后续设计

- [ ] 为配置页 Inline Table Editor 写单独 spec
- [ ] 为 YAML view / UI view 等价转换写单独 spec
- [ ] 评估 `config/categories/*.yaml` GitOps 存储路径
- [ ] 后续再实施配置页，不阻塞今日机会台 benchmark

## Phase 7：验证

- [x] `npm run design-system:check -w @goofish/dashboard-react`
- [x] `npm run typecheck -w @goofish/dashboard-react`
- [x] `npm run test -w @goofish/dashboard-react -- BuyWorkbenchPage`
- [x] `npm run design-system:audit -w @goofish/dashboard-react`
- [x] Light 视觉检查
- [x] Dark 视觉检查
- [x] 视口检查：桌面至少 8 行，移动端无文字重叠
- [x] 若时间允许，`npm run verify-baseline`

## 验收清单

- [x] 今日机会台首屏像“买方情报终端”，不是 SaaS hero/card dashboard
- [x] 全站 token 没有任意新增色
- [x] 常规 UI 无阴影
- [x] 机会行是 dense row，不是卡片
- [x] 数字使用 mono + tabular nums
- [x] Sheet 保留上下文
- [x] 键盘主路径可用
- [x] 反馈和成交回写测试仍通过
- [x] 设计检查、类型检查、相关测试通过
