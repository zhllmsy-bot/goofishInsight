# Camera Market Expansion TodoList

更新时间：2026-04-07

## 目标

- 为 `camera_body` 大类补齐可执行基础设施，并录入当前第一批热门机身 Top 20。
- 为 `camera_interchangeable_lens` 大类补齐尼康镜头 Top 20。
- 触发一轮 batch collect，观察 crawl run、items 入库、category/template 解析是否正常。
- 在执行过程中持续回顾，动态增补步骤，直到链路闭环。

## 当前基线

- `camera_interchangeable_lens` 已存在，runtime profile 和 active template 已存在，但型号库为空。
- `camera_body` 在代码兼容层和定价展示层已预留，但数据库里尚未创建 category/runtime/template 实体。
- resident dashboard 正常；resident batch collect 当前未加载；`chrome-attached` 的 9223 CDP 端口可用。
- 当前 `CategoryModelCatalog` 为空，说明这次导入不会覆盖既有型号库，但也意味着所有批量 seed 都要确保可回放。

## 执行清单

- [x] Step 1. 补完批量 seed 前的基础能力
  - [x] 1.1 为 `camera_body` 补上 runtime default / prompt instruction / UI preset，避免新增大类时仍然是半残状态。
  - [x] 1.2 优化型号库批量导入链路：导入时按 category 聚合同步，避免每条型号都触发一次 task sync。
  - [x] 1.3 回归相关服务测试，确认没有打坏现有 lens / apple / garmin 配置流。

- [x] Step 2. 建立 `camera_body` 大类生产基础设施
  - [x] 2.1 创建或恢复 `camera_body` category。
  - [x] 2.2 基于现有属性池建立 `camera_body` template，并绑定 active runtime template。
  - [x] 2.3 复查 runtime profile、template items、prompt profile 是否一致。

- [x] Step 3. 准备可复用 seed 资产
  - [x] 3.1 新增可复用的 camera market seed 数据文件，包含机身 Top 20 与尼康镜头 Top 20。
  - [x] 3.2 新增可复用 seed 脚本，支持 dry-run / apply。
  - [x] 3.3 复查 seed 输出是否会正确同步 task queries / lexicons。

- [x] Step 4. 执行 seed
  - [x] 4.1 导入 `camera_body` Top 20。
  - [x] 4.2 导入 `camera_interchangeable_lens` Nikon Top 20。
  - [x] 4.3 核对型号库数量、自动生成任务、query 数量、lexicon 数量。

- [ ] Step 5. 启动 batch collect 并观察入库
  - [x] 5.1 用 `collect-search / collect-batch` 对机身任务做多轮真实采样，确认 exact-model query 首页/前三页都被低价配件和租赁噪音占满。
  - [x] 5.2 用 `collect-search / collect-batch` 对镜头任务做真实采样，确认完整型号 query 可以稳定产出有效镜头样本。
  - [x] 5.3 观察 crawl runs、pages_succeeded、风控情况，并验证手动中断后 run 不再残留为 `running`。
  - [x] 5.4 观察 items 入库数量、resolved category/template、异常样本，并把噪音样本特征沉淀为准入规则。
  - [x] 5.5 清理历史遗留的 stale `running` crawl runs，恢复健康观测口径。

- [x] Step 6. 回顾与动态修正
  - [x] 6.1 回顾本轮新增的任务、模板、型号是否符合业务语义。
  - [x] 6.2 动态补充 alias / query 生成规则：
    - `camera_body` 改为中文 alias 优先。
    - `camera_interchangeable_lens` 改为“品牌 + 焦距/光圈 shorthand”单短词 query，例如 `尼康 Z 50 1.2`、`尼康 Z 24-70 2.8`。
  - [x] 6.3 针对 batch collect 暴露的流程问题补规则并执行：
    - 增加按大类的 ingest gate，拦截低价配件 / 服务 / 租赁噪音。
    - 增加镜头 numeric signature 校验，过滤错焦段错光圈结果。
    - 修复手动中断后的 run finalize 路径。

- [ ] Step 7. 机身采集策略重构
  - [ ] 7.1 为 `camera_body` 设计不同于镜头的 query strategy，不能继续依赖“具体型号 + 机身/单机/微单”直搜。
  - [ ] 7.2 评估是否改成“品牌/系列级 query + 型号词典识别”或“搜索筛选/排序增强”。
  - [ ] 7.3 在新策略验证前，不将 `camera_body` 全量 batch collect 视为生产可用。

## 动态回顾记录

- [x] Review A. 基线确认后，决定先恢复 `camera_body` 基础设施，再导入 Top 20。
- [x] Review B. 完成 seed 能力改造后，已补 `camera_body` 的 runtime default / prompt instruction / UI preset / AI template 默认布局。
- [x] Review C. 完成 batch collect 后，确认 query 规则必须分大类收敛，不能继续统一拼词。
- [x] Review D. 镜头类验证出“完整型号 query + alias + signature gate”可行，适合继续生产化。
- [x] Review F. 根据最新业务要求，镜头 batch collect query 进一步收敛为“品牌 + 焦距/光圈 shorthand”唯一入口，不再使用完整型号词。
- [x] Review E. 机身类验证出问题不在模板和属性，而在闲鱼搜索入口本身，需单独做 query strategy 重构。
