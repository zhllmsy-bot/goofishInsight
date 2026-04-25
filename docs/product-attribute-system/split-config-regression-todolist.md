# 拆表配置链路回归 TodoList

更新时间：2026-04-08

## 工作规则

- 先回归整个大类/属性/模板/型号/任务链路，再逐项修复。
- 每完成一项，都要补自检或回归测试。
- 如果修复过程中发现新的结构性问题，先更新本文件，再继续。
- 优先解决会导致配置错绑、任务错跑、模板错配的隐性问题，其次再优化交互便利性。

## 初始结论

- [x] 首页/详情页的宽屏和长文本爆开问题已单独收口，本轮主线转回拆表链路本身。
- [x] 回归模板绑定属性时的 scope 歧义问题。
  当前 `template_config` 和 `catalog_template_version` 都是按 `attributeCode` 直接查 `attribute_definition`，拆表后如果未来出现跨 scope 同 code，会有错绑风险。
- [x] 回归任务 `category` 与 `businessDomain` 双写可能漂移的问题。
  当前任务页和服务层仍允许在已绑定 `categoryId/categoryCode` 时带入独立 `businessDomain`，容易出现同一任务的类目和域不一致。
- [x] 回归型号库同步对“未绑 category_id 的旧任务”是否会漏同步或误建重复任务。
  当前 `task_model_catalog_sync` 只按 `category_id` 找任务，需要确认 legacy 任务是否会漏掉，并决定是否顺手回填。
- [x] 评估“添加大类绑定具体品类”当前交互是否足够顺手，并做必要优化。
  当前型号抽屉还暴露 `categoryId/categoryCode` 原始输入，实际体验上不够像“从大类进入后直接维护具体品类”。
- [x] 跑一轮针对配置链路的回归测试，并根据结果动态增删 todo。

## 动态追加区

- [x] 旁路补查：模板版本化入口 `catalog_template_version` 与主模板编辑入口共用同一套属性解析约束，避免只修主路径、旁路继续漏。
- [x] 数据现状核实：真实库里当前没有跨 scope 重复 `attribute_code`；`category_id is null` 的任务只剩 onboarding 发现任务，不会和生产大类同步链路冲突。
- [x] 继续优化：型号页把“大类绑定”改成选择式上下文，不再要求操作者手填原始 `categoryId/categoryCode`。
- [x] 继续优化：模板页、任务页也统一成选择式大类绑定。
  模板页改成 `Category Filter + Bound Category` 选择模式；任务页改成 `Bound Category` 选择后自动镜像 canonical `businessDomain`，只有非绑定系统任务才需要手填 domain。
- [x] 结构性补洞：`crawl_runs` 存在大量历史 `running` 脏状态。
  这不是拆表本身导致的 schema 问题，但会污染看板健康口径，也会让 resident batch collect 的运行态越来越不可信。本轮已补自动回收：创建新 run 前会自动把超过 10 分钟仍处于 `running` 的旧 run 改成 `cancelled`。

## 当前结论

- 主风险已收口：模板/模板版本的属性解析不再默默按 `attributeCode` 错绑；如果未来出现跨 scope 同 code，会明确报错并要求显式 `attributeId`。
- 任务一致性已收口：已绑定 category 的任务会把 `businessDomain` 归一到 canonical category code，并拒绝跨类目误填。
- 型号同步已补 legacy 兜底：即使旧任务还没填 `category_id`，只要 domain 能解析回当前大类，也会被同步并顺手回填。
- 型号页主路径已顺手：大类筛选和抽屉绑定都改成选择式上下文，当前大类进入时会自动预绑定。
- 模板页与任务页主路径也已统一：模板和任务都不再要求操作者手填原始 `categoryId/categoryCode`；任务在绑定大类时会同步镜像 canonical `businessDomain`。
- 运行态脏数据已补自愈：真实库里这次清掉了 `110` 条超过 10 分钟仍为 `running` 的历史 run；当前只剩 resident batch 正在执行的活跃 run，`stale_over_10m = 0`。

## 后续候选

- 非阻塞：模板页当前是 textarea 编排，尚未把 `attributeId` 显式带入编辑器；当未来真的出现跨 scope 同 code 属性时，可以继续升级为结构化模板项编辑器。
- 非阻塞：任务页当前仍是“列表 + 右侧内嵌编辑器”模式，和模板/型号的抽屉式编辑不完全一致；如果后续继续打磨 B 端交互，可以再统一成同一套工作台样式。
