# 靠谱二手价格指导助手技术说明书

Status: Draft v1  
Updated: 2026-04-10  
Workspace: `<repo-root>`

Related:

- [18-reliable-price-assistant-prd.md](<repo-root>/docs/18-reliable-price-assistant-prd.md)
- [16-buy-side-implementation-spec.md](<repo-root>/docs/16-buy-side-implementation-spec.md)
- [17-buy-side-implementation-todolist.md](<repo-root>/docs/17-buy-side-implementation-todolist.md)
- [08-architecture-refactor-spec.md](<repo-root>/docs/08-architecture-refactor-spec.md)
- [product-attribute-system/README.md](<repo-root>/docs/product-attribute-system/README.md)
- [dashboard-react-architecture.md](<repo-root>/docs/dashboard-react-architecture.md)

## 1. 文档目的

这份文档用于把产品目标落到当前代码库的技术现实上，回答三个问题：

1. 当前项目已经具备哪些能力
2. 当前技术架构距离“靠谱价格指导助手”还差什么
3. 后续应该按什么技术路径收口，而不是继续在页面层反复修补

本说明书不是抽象架构蓝图，而是基于 2026-04-10 当前仓库状态写的 `as-is + to-be` 技术合同。

## 2. 当前项目现状

## 2.1 总体结论

当前项目已经不是 PoC。

它已经具备一套真实运行的本地系统：

- 持续采集目标品类挂牌
- 做规格抽取与 review gate
- 形成 `product/spec` 两层价格聚合
- 生成 baseline 与 buy opportunity
- 提供本地 dashboard、runtime、LLM DevOps 和买入机会页

但从“靠谱价格”这个目标看，当前仍处于：

`采集与分析能力较强，价格对象定义尚未完全收口`

的阶段。

当前最大偏差不是服务是否能跑，而是：

`系统默认仍容易把型号当作价格单位，而不是把可定价模板当作价格单位。`

## 2.2 当前运行面

截至 2026-04-10，本地运行面实际为：

- Python/FastAPI 后端：`127.0.0.1:8791`
- React + Nest 新 dashboard 服务：`127.0.0.1:3030`
- 旧 `8787` dashboard 已停用，不再作为主入口

已确认：

- `GET /healthz` on `3030` 返回 `{"ok":true,"frontendReady":true}`
- `GET /healthz` on `8791` 返回 `{"ok":true}`

这代表当前前端壳层和后端数据源均处于可用状态。

## 2.3 当前应用结构

### Python 主应用

主应用位于：

- `apps/collector/src/goofish_insight`

当前入口工厂：

- [webapp.py](<repo-root>/apps/collector/src/goofish_insight/webapp.py)

已挂载路由：

- dashboard
- buy
- config
- onboarding
- catalog_preview
- mobile_overlay
- progress

这说明当前后端仍是一个模块化单体应用，而不是微服务拆分。

### 新 dashboard 前端

新前端为 React + Nest 双层壳：

- React 路由入口：[App.tsx](<repo-root>/apps/dashboard-react/src/app/App.tsx)
- Nest 壳入口：[app.controller.ts](<repo-root>/apps/dashboard-nest/src/app.controller.ts)

当前 React 已落地页面：

- `/` 看板首页
- `/llm-devops`
- `/runtime`

当前仍回退到旧后端页面的入口：

- `回刷进度`
- `品类开通`

说明前台壳层已切新，但并未完成全站统一收口。

## 2.4 当前业务域落地程度

从买方域看，当前项目已落地以下关键能力：

### 已落地的数据表

见 [models.py](<repo-root>/apps/collector/src/goofish_insight/models.py)：

- `buy_watch_target`
- `buy_price_baseline`
- `buy_opportunity`
- `buy_opportunity_risk`
- `buy_alert_event`
- `buy_decision_feedback`

### 已落地的服务

- baseline 构建：
  [buy_price_baselines.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_price_baselines.py)
- 机会刷新：
  [buy_opportunities.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_opportunities.py)
- 提醒：
  [buy_alerts.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_alerts.py)
- 反馈：
  [buy_feedback.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_feedback.py)
- 买方工作台：
  [buy_dashboard.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_dashboard.py)

### 已落地的 CLI

见 [pricing.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/pricing.py)：

- `build-buy-baselines`
- `refresh-buy-opportunities`
- 提醒与反馈相关命令

### 已落地的 Web 入口

见 [buy.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/buy.py)：

- `GET /buy/opportunities`
- `GET /api/buy/opportunities`
- `POST /api/buy/feedback`

### 已落地的阶段进度

根据 [17-buy-side-implementation-todolist.md](<repo-root>/docs/17-buy-side-implementation-todolist.md)：

- Apple baseline 已写入 895 条
- Garmin baseline 已写入 498 条
- Apple 与 Garmin 首批机会已各生成 200 条
- dashboard inbox 提醒已写入

这说明“买方域”已经不只是设计，而是有真实运行数据。

## 3. 当前架构判断

## 3.1 当前方向并未完全走偏

从技术能力上看，项目已经有不少对路的部分：

- category / runtime profile / template / model catalog 已经形成配置主轴
- specs 抽取会读取 runtime profile 和 active template
- pricing records 已经带出结构化字段，如 `chip_family`、`memory_gb`、`storage_gb`
- pricing 已支持 `brand / product / spec` 三层聚合
- review gate 对进入价格池的样本有较保守门槛
- buy baseline / buy opportunity 已经在落地

换句话说，系统的“发动机”不差。

## 3.2 当前真正的偏差

当前最大的偏差发生在“默认价格对象”层，而不是“服务是否可跑”层。

具体表现为：

1. dashboard 默认仍偏向 `product` 视图  
   见 [dashboard.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/dashboard.py)

2. 前端交互上，`spec` 仍像“附加筛选”，而不是“必须选完整才能给价的模板对象”

3. 趋势图与价格卡一度允许在未完全收窄到模板时展示结果，容易产生“不同规格混价”的误解

4. buy baseline 虽然支持 `brand/product/spec` 全视图，但尚未形成“模板优先，产品级只作回退”的强约束

因此，当前系统问题不在于“没有做价格”，而在于：

`已经有价格引擎，但尚未把模板级价格对象上升为所有页面和接口的默认合同。`

## 4. 技术目标

本项目下一阶段的技术目标不是继续加页面，而是把系统重构为：

`一个以模板级价格为中心的二手价格指导系统`

技术上必须满足以下四个条件：

1. 价格对象固定为 `Priceable Template`
2. 模板不完整时禁止给价
3. 所有走势和挂牌判断都必须绑定到当前模板
4. 价格结论必须附带可靠性证据

## 5. 目标技术架构

## 5.1 架构总览

建议架构继续保持“模块化单体 + 前端壳”的方向，不做微服务拆分。

目标结构：

```text
采集与事实层
  crawl tasks / items / snapshots / enrichments

规格与模板层
  category / runtime profile / template / model catalog
  pricingKeyFields / template completeness rules

价格与机会层
  pricing records
  template baselines
  buy opportunities
  alert / feedback / calibration

展示与操作层
  React dashboard shell
  runtime / llm devops / progress / onboarding
  buy workbench
```

## 5.2 运行单元

建议明确以下运行单元：

### Unit A：Collector / Web Backend

职责：

- FastAPI Web
- dashboard sections
- buy APIs
- runtime control APIs
- config / onboarding / progress APIs

当前实现：

- `apps/collector/src/goofish_insight`

### Unit B：Dashboard Shell

职责：

- React 页面
- Nest 静态托管与 API proxy

当前实现：

- `apps/dashboard-react`
- `apps/dashboard-nest`

### Unit C：Buy Jobs

职责：

- baseline 构建
- opportunity 刷新
- alert 触发
- feedback 汇总与校准

当前实现状态：

- baseline / opportunity / alert 已有服务和 CLI
- scheduler / resident runtime 契约仍未完全固定

### Unit D：Review / Calibration

职责：

- review gate
- calibration 数据集
- 价格可靠性和模型输出校准

当前实现：

- `domain/review/*`
- `application/services/review_*`
- `application/services/review_calibration.py`

## 5.3 分层职责

### 配置主轴

主配置链保持为：

`category -> category_runtime_profile -> active_template -> model catalog`

这是当前项目里最值得保留的设计轴。

### 领域主轴

买方域未来应固定为：

`template baseline -> opportunity -> alert -> feedback -> calibration`

而不是继续由 dashboard 页面来反推业务对象。

### 唯一真相源与优先级

后续实现必须明确“谁说了算”，避免同一语义在多个地方重复定义。

建议固定如下优先级：

1. `CategoryAttrTemplate` / active template metadata
   - 定义 `pricingKeyFields`
   - 定义字段顺序
   - 定义必填字段
   - 定义模板 key 拼接规则
   - 定义模板完整度规则
2. `CategoryRuntimeProfile`
   - 只负责选择当前 active template
   - 负责 dashboard 的默认展示字段和 UI 偏好
   - 不负责重新定义主价格字段集合
3. `pricing_templates` 服务层
   - 读取 active template metadata
   - 合并默认阈值与模板覆盖项
   - 输出最终可执行合同
4. 前端页面
   - 只消费后端返回的模板合同
   - 不自行推导“哪些字段必须选满才能给价”

换句话说：

`模板定义价格语义，runtime profile 只定义运行和展示语义。`

若两者冲突，应以 active template metadata 为准。

进一步约束：

- `runtime override` 可以改变“当前选用哪一个 template”
- `runtime override` 可以改变“默认展开哪些字段、默认显示哪些面板”
- `runtime override` 不可以改变：
  - `pricingKeyFields`
  - 必填字段集合
  - `templateKey` 拼接规则
  - 模板完整度规则
  - 默认给价阈值本身

也就是说，`runtime override` 只能切换模板，不得改写模板价格语义。

## 6. 核心领域模型

## 6.1 当前已有领域对象

### Category

业务品类根对象，已存在。

### CategoryRuntimeProfile

承载类目级运行配置、active template 和 dashboard filter layout。

### CategoryAttrTemplate

承载类目模板与属性约束。

### CategoryModelCatalog

承载型号库。

### Pricing Record

由 `load_pricing_records()` 产出，是定价分析的中间事实层。

包含：

- product_label
- spec_label
- chip_family
- memory_gb
- storage_gb
- display_type
- case_size_mm
- screen_size_in
- spec_confidence
- exact_spec_ready

### BuyPriceBaseline

当前已落地，用于保存某个价格分组的基线结果。

### BuyOpportunity

当前已落地，用于保存命中的价格机会。

## 6.2 需要强化的新领域对象

### Priceable Template

这是当前架构中最需要正式化的对象。

建议新增统一语义：

- `pricing_template_key`
- `pricing_template_label`
- `pricing_key_fields`
- `template_completeness_status`

其中：

- `pricing_template_key` 用于唯一标识某个可定价模板
- `pricing_key_fields` 用于声明该品类哪些字段决定主价格
- `template_completeness_status` 用于判断是否允许给价

### Template Contract

建议把 `Priceable Template` 进一步 formalize 为后端统一输出的合同对象：

- `templateKey`
- `templateLabel`
- `pricingKeyFields`
- `resolvedFieldValues`
- `missingRequiredFields`
- `completenessStatus`
- `availabilityTier`
- `thresholdProfile`

其中：

- `completenessStatus` 只回答“字段是否选完整”
- `availabilityTier` 回答“即使字段完整，当前样本是否足以支持价格指导”

建议枚举值：

- `incomplete`
- `blocked`
- `reference_only`
- `guidance_ready`

补充约束：

- `guidance_ready` 只允许用于“已命中明确模板”的结果
- `reference_only` 可用于“模板完整但样本或历史不足，只可参考不可指导”的结果
- `blocked` 用于“字段完整，但当前证据不足或归属不稳定”
- `incomplete` 用于“核心定价字段未选完整”

### Listing Adjustment Factors

建议明确把以下因素从主模板中剥离：

- 成色
- 配件
- 保修
- 箱说
- 电池健康
- 颜色

这些因素应只用于单条挂牌修正和机会解释，不应定义主价格模板。

## 7. 价格链路现状与改造要求

## 7.1 当前价格链路

当前价格主链路大致为：

```text
items
  -> specs / runtime template enrich
  -> review gate
  -> load_pricing_records
  -> aggregate_pricing_view(brand/product/spec)
  -> dashboard pricing panel
  -> buy_price_baseline
  -> buy_opportunity
```

当前优点：

- 价格样本有 review gate
- 支持按 `spec` 聚合
- baseline 和 opportunity 已接上

当前缺点：

- `product` 视图仍在多处作为默认视图
- 前台没有把“模板未完成”当作明确状态
- baseline 仍允许大量非模板优先的回退逻辑

## 7.2 改造后的价格链路

目标链路应改为：

```text
items
  -> specs / runtime template enrich
  -> review gate
  -> template field resolve
  -> template completeness check
  -> template-level pricing records
  -> template baseline
  -> listing-to-template match
  -> opportunity scoring
  -> dashboard / workbench / alerts
```

### 关键变化

变化不在采集层，而在价格对象解析层：

1. 先确定当前挂牌属于哪个模板
2. 再决定这个模板是否可定价
3. 再做模板级 baseline
4. 最后把挂牌对比到该 baseline

## 7.3 给价合同

任何 API 或页面输出价格前，必须满足：

1. `pricingKeyFields` 已解析
2. 所需字段已完整
3. 样本数达到下限
4. 卖家数达到下限
5. exact spec ratio 或模板置信度达到下限
6. 趋势窗口内存在有效活跃样本

否则必须返回：

- `pricingAvailable = false`
- `pricingBlockReason`

而不是回退输出混合价格。

### 默认阈值与所有权

为了避免后端、前端和 buy jobs 各自使用不同口径，必须固定默认阈值和责任归属。

默认建议：

- `templateComplete = true`
- `sellerSampleCount >= 3`
- `uniqueSellerCount >= 2`
- `exactSpecRatio >= 0.65`
- `reliabilityScore >= 60`
- `latestSeenAt` 在近 14 天内

满足以上条件，可进入：

- `availabilityTier = reference_only`

若要进入可执行买入指导状态，还需满足：

- `sellerSampleCount >= 5`
- `uniqueSellerCount >= 3`
- `exactSpecRatio >= 0.80`
- `reliabilityScore >= 70`

满足后进入：

- `availabilityTier = guidance_ready`

若字段未完整：

- `availabilityTier = incomplete`

若字段完整但样本或可信度不足：

- `availabilityTier = blocked`

阈值所有权建议：

1. 全局默认值由 `pricing_templates` 服务层维护
2. 品类或模板级覆盖项由 active template metadata 提供
3. 前端只消费后端计算结果，不自行实现阈值逻辑

### `availabilityTier` 的强约束

`availabilityTier` 不是展示字段，而是后续链路的强门控。

后续系统必须遵守：

1. dashboard 首页是否展示价格指导，以 `availabilityTier` 为准
2. baseline 是否可进入“指导价基线”，以 `availabilityTier` 为准
3. buy opportunity 是否可进入主机会池，以 `availabilityTier` 为准
4. alert 是否允许触发，以 `availabilityTier` 为准

具体约束：

- `guidance_ready`
  - 可进入首页主价格区
  - 可参与主机会池
  - 可触发提醒
- `reference_only`
  - 可展示参考价和参考趋势
  - 不可进入主机会池
  - 不可触发提醒
- `blocked`
  - 不展示指导价
  - 不进入主机会池
  - 不触发提醒
- `incomplete`
  - 不展示指导价
  - 不进入主机会池
  - 不触发提醒

`opportunityScore` 和 `riskScore` 只能在已通过 `availabilityTier` 门控后使用。

它们的作用是：

- 对可进入候选池的对象做排序
- 对同层级对象做相对优先级判断

而不是把 `blocked` 或降级匹配对象“重新抬回”主机会池。

### 给价结果结构

建议把当前单一的 `pricingAvailable` 扩展为：

- `pricingAvailable`
- `availabilityTier`
- `pricingBlockReason`
- `pricingEvidence`

其中 `pricingEvidence` 至少包含：

- `sellerSampleCount`
- `uniqueSellerCount`
- `exactSpecRatio`
- `reliabilityScore`
- `latestSeenAt`
- `windowDays`

这样页面和买方工作台使用的是同一套证据，而不是各自拼装解释。

## 8. 页面与交互技术合同

## 8.1 首页

首页职责：

- 展示品类 -> 型号 -> 模板属性
- 展示当前模板价格与走势
- 展示当前模板对应挂牌

首页不应再默认承担：

- 系统诊断
- LLM 调试
- 与当前模板无关的同类趋势展示

### 首页技术要求

1. 左侧只负责 `category -> product model`
2. 右侧顶部先展示模板属性选择器
3. 只有模板完整时才请求或展示价格区
4. 趋势图只显示当前模板走势
5. 挂牌卡片必须先匹配模板再分类

## 8.2 LLM DevOps

职责：

- 定位 specs / review / prompt / response 问题
- 解释模板识别错误和 review 偏差

这页是“价格可信度调试台”，不是首页的一部分。

## 8.3 Runtime

职责：

- 管采集、模型、review、worker 和后台动作

这页是运行面，不输出业务价格判断。

## 8.4 Buy Opportunities Workbench

当前已存在 SSR 工作台，但后续应逐步对齐模板级视图。

具体要求：

- baselineMatchLevel 必须优先为 `spec/template`
- product 级回退应显式标注
- 机会卡必须展示所命中的模板 key 与 baseline 证据

## 9. API 技术要求

## 9.1 当前 API 状态

当前 dashboard sections API 结构已拆分较清晰：

- `hero`
- `filters`
- `pricing`
- `items`
- `focus`
- `insights`
- `calibration`

当前 Nest 负责透传这些 sections API，并托管 React build。

## 9.2 新增或增强的 API 合同

建议下一阶段引入以下明确契约：

### Contract A：模板属性元信息

返回：

- 当前 category 的 `pricingKeyFields`
- 字段顺序
- 是否为必选定价字段
- 每个字段当前可选项

### Contract B：模板完整度

返回：

- `templateCompletenessStatus`
- `missingPricingFields`
- `resolvedTemplateKey`
- `resolvedTemplateLabel`
- `resolvedFieldValues`
- `availabilityTier`

### Contract C：模板级价格

返回：

- `pricingAvailable`
- `pricingTemplateKey`
- `pricingTemplateLabel`
- `safeBuyPrice`
- `normalBuyPrice`
- `marketMidPrice`
- `sampleSize`
- `sellerCount`
- `reliabilityScore`
- `pricingEvidence`
- `availabilityTier`
- `pricingBlockReason`

### Contract D：模板级趋势

只返回当前模板对应的趋势，不允许同类替代。

趋势合同至少包含：

- `templateKey`
- `windowDays`
- `pointCount`
- `trendQualityOk`
- `trendQualityReason`
- `latestRangeLabel`
- `dailyCandles`

### Contract E：挂牌模板匹配结果

每条 listing 至少应返回：

- `matchedTemplateKey`
- `matchConfidence`
- `baselineMatchLevel`
- `priceDecision`
- `priceDelta`
- `matchedFieldValues`
- `matchReason`

并建议固定 `baselineMatchLevel` 枚举：

- `template`
- `selector`
- `spec`
- `degraded_product`
- `degraded_brand`

其中：

- `template / selector / spec`
  允许进入 `guidance_ready` 判定
- `degraded_product / degraded_brand`
  只允许输出参考性结果
  不允许触发主机会池和提醒

### Contract F：模板属性来源说明

为了便于诊断，后端应返回当前模板合同来自何处：

- `templateSource = active_template`
- `templateSource = runtime_override`
- `templateSource = fallback_legacy`

在正式收口后，应尽量把 `fallback_legacy` 压到最低，只保留兼容期使用。

补充说明：

- `active_template`
  - 表示合同直接来自当前 active template metadata
- `runtime_override`
  - 表示当前 session 或运行态切换到了另一份 template
  - 但合同语义仍来自该 template metadata，而不是 runtime 自定义字段
- `fallback_legacy`
  - 仅允许在兼容期输出
  - 一旦命中该来源，结果默认不得进入 `guidance_ready`

## 10. 数据模型改造要求

## 10.1 保留现有买方域表

以下表应保留并继续使用：

- `buy_watch_target`
- `buy_price_baseline`
- `buy_opportunity`
- `buy_opportunity_risk`
- `buy_alert_event`
- `buy_decision_feedback`

## 10.2 需要补强的字段语义

建议优先通过 `payload` 和运行配置补强，而不是立刻大规模改表。

优先补强：

- baseline payload 中显式写入 `pricingTemplateKey`
- opportunity payload 中显式写入 `matchedTemplateKey`
- active template metadata 中新增 `pricingKeyFields`
- runtime profile 中仅引用当前 active template 与展示偏好，不重复定义 `pricingKeyFields`

待语义稳定后，再决定是否升级为正式字段。

### Watch Target v2 语义

当前 `BuyWatchTarget` 的正式字段更偏 Apple 电脑场景：

- `desired_memory_gb`
- `desired_storage_gb`
- `desired_region`

这对 Garmin、相机、镜头等品类不够通用。

因此建议明确分两阶段：

#### 阶段 A：兼容期

沿用现有表结构，但在 `metadata_json` 中新增：

- `pricingSelector`
- `pricingTemplateKey`
- `pricingSelectorVersion`

其中 `pricingSelector` 为结构化模板偏好，例如：

```json
{
  "chip_family": "M4",
  "memory_gb": 16,
  "storage_gb": 256
}
```

兼容期补充规则：

- `pricingSelector` 可以是完整模板选择器，也可以是部分选择器
- 完整选择器可对应唯一模板
- 部分选择器只代表“观察范围”，不代表可直接给价模板

例如：

- `{"chip_family":"M4","memory_gb":16,"storage_gb":256}`
  - 属于完整模板选择器
- `{"memory_gb":16}`
  - 属于部分选择器，只能表达“看 16G 这一层”

因此：

- 部分选择器允许存在于 watch target
- 但部分选择器不能直接产出 `guidance_ready` 价格指导或提醒

#### 阶段 B：正式期

在语义稳定后，将以下字段提升为正式列或统一结构列：

- `pricing_template_key`
- `pricing_selector_json`

并将 `desired_memory_gb / desired_storage_gb` 降级为兼容字段。

## 10.3 baseline 键规范

当前 `BuyPriceBaseline.baseline_key` 由 `view:label` 生成，已能工作，但仍偏展示语义。

建议下一阶段逐步升级为：

- `template:{stable_key}`

其中 `stable_key` 应由核心定价字段稳定拼接，而不是直接依赖展示 label。

### baseline 迁移策略

为避免一次性重写全部历史数据，建议采用双写迁移：

#### 阶段 A：双写

- 保留现有 `baseline_key = view:label`
- 同时在 `payload.pricingTemplate` 中写入：
  - `templateKey`
  - `templateLabel`
  - `resolvedFieldValues`

#### 阶段 B：读优先切换

- baseline 匹配优先读取 `templateKey`
- 只有缺失时才回退 `view:label`

#### 阶段 C：正式收口

- 将 `templateKey` 升为正式字段
- `view:label` 仅作历史兼容

### opportunity 迁移策略

`BuyOpportunity` 应同步采用相同策略：

#### 阶段 A

在 `payload` 中新增：

- `matchedTemplateKey`
- `matchedTemplateLabel`
- `matchedFieldValues`
- `templateAvailabilityTier`

#### 阶段 B

匹配顺序改为：

1. `templateKey`
2. 显式模板选择器
3. `spec`
4. `product`
5. `brand`

并且：

- `product`
- `brand`

只能作为显式降级状态，不再伪装成模板级命中。

并增加强约束：

- 若 `baselineMatchLevel in {degraded_product, degraded_brand}`
  - `templateAvailabilityTier` 最高只能为 `reference_only`
  - `BuyOpportunity.status` 不得进入主机会状态
  - 不得写入 `BuyAlertEvent`

建议增加一种显式状态用于兼容期：

- `REFERENCE_ONLY`

用于保存“有一定参考价值，但不足以进入主机会池”的结果。

## 11. 当前代码模块与未来职责

## 11.1 继续保留的核心模块

### 价格计算

- [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)

继续承载：

- pricing record 生成
- `aggregate_pricing_view`
- 可靠度与机会分计算

后续应逐步把“模板解析”和“模板完整度检查”收进去。

### dashboard section 组装

- [dashboard_sections.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_sections.py)

继续承载 section orchestration，但不应继续承担“产品级混价默认逻辑”。

### dashboard filters

- [dashboard_filters.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_filters.py)

后续应从“结构化筛选字段”升级为“定价字段 + 展示字段”双层语义。

## 11.2 需要新增或拆分的模块

建议新增：

- `application/services/pricing_templates.py`
  - 解析模板 key
  - 计算模板完整度
  - 输出模板属性合同
  - 负责 `templateKey` canonicalization

- `application/services/template_trends.py`
  - 只负责模板级走势，不与 domain card 混用

- `application/services/listing_template_match.py`
  - 将 listing 显式匹配到模板

- `application/services/pricing_thresholds.py`
  - 维护默认给价阈值
  - 合并模板级覆盖项
  - 输出 `availabilityTier`

### `templateKey` canonicalization 责任

`templateKey` 的生成必须由单一服务负责，不能在页面、job、baseline、机会链路里各自拼接。

建议固定：

- 唯一实现位置：`pricing_templates.py`
- 输入：
  - template metadata 中定义的字段顺序
  - 已解析字段值
- 输出：
  - 稳定、可比较、可持久化的 `templateKey`

前端、baseline、opportunity、alert 只能消费该 key，不允许自行重建。

## 12. 当前实现与目标之间的缺口

## 12.1 缺口 A：缺少正式的 pricingKeyFields 语义

当前已经有 runtime profile、template、structured filters，但还没有一个统一语义明确指出：

- 哪些字段决定主价格
- 哪些字段必须选满才能给价

这会导致产品和技术都容易把“筛选项”误当成“定价项”。

## 12.2 缺口 B：dashboard 默认视图仍是 product 优先

这会导致技术上已支持 `spec`，但产品上仍容易回落为“型号均价”。

## 12.3 缺口 C：模板级趋势与挂牌匹配尚未彻底收口

当前趋势和 listing 逻辑仍有产品级回退痕迹，需要显式切到模板级。

### 趋势生成口径缺口

当前趋势卡来自产品级 `build_domain_trend_cards()`，以 `product_label` 为主要分组键。

这意味着即使页面上选中了某个模板，底层趋势仍可能来自产品级样本集合。

模板级趋势必须改为独立链路：

1. 先根据当前模板合同解析 `templateKey`
2. 用 `templateKey` 回溯历史 item 集
3. 基于 `ItemSnapshot` 生成日 candle
4. 输出模板级中位价与中间 50% 价带

### 模板级趋势 v1 数据源

考虑当前项目现状，建议 v1 先使用：

- `ItemSnapshot`
- snapshot 时点可回放的模板映射

来构建趋势。

即：

- 每个 snapshot 必须按 `snapshot_at` 对应的模板归属来计入 candle
- 每天按模板汇总出 `median / p25 / p75`

### 历史归属不可随意漂移

趋势的根合同必须是：

`历史 snapshot 属于哪个模板，应按 snapshot 时点的模板归属计算，而不是按今天重新解释。`

否则会出现：

- 模板抽取规则一修，历史趋势整体漂移
- 同一模板的历史 candle 反复重写
- 用户看到的走势不稳定

因此建议：

1. 最理想口径
   - 在 snapshot 写入或离线回刷时，固化当时的 `templateKey`
2. v1 过渡口径
   - 若历史 snapshot 尚未固化 `templateKey`
   - 可用“最接近 snapshot 时点的稳定模板映射”回放
   - 但结果只能进入 `reference_only`
   - 不得支持 `guidance_ready`
3. v2 正式口径
   - 使用物化日 candle 表
   - candle 一旦生成，只能通过显式回刷或重建任务改写

### 模板级趋势 v2 数据源

后续如需更稳的趋势，可新增物化表或批任务：

- `template_daily_price_candle`

按日固化：

- `template_key`
- `date`
- `median_price`
- `p25_price`
- `p75_price`
- `seller_sample_count`
- `listing_count`

v1 先在线聚合，v2 再转物化。

### 趋势可用性与主机会池关系

即使模板价格已达到 `guidance_ready`，若趋势归属仍是过渡回放口径，也只能：

- 展示价格指导
- 将趋势标记为 `reference_only`

若某条机会依赖趋势信号做优先级放大，则必须要求：

- 模板趋势来自 snapshot 时点归属或正式 candle 表

否则该机会只能按“无强趋势加成”处理。

## 12.4 缺口 D：buy workbench 仍是第一版

已有机会工作台，但还未完全成为“模板级价格工作台”。

## 13. 实施路线

## Phase 0：合同冻结

输出：

- 本说明书
- 各品类 `pricingKeyFields` 设计表

完成标准：

- 各品类明确主价格字段
- 产品、后端、前端对“模板才是价格对象”达成一致

## Phase 1：后端模板合同落地

工作：

- 为 active template metadata 增加 `pricingKeyFields`
- 新增模板完整度判断
- dashboard filters / pricing API 输出模板合同字段
- 固定默认给价阈值与模板级覆盖规则
- 固定 `templateKey` canonicalization 唯一实现
- 固定 `baselineMatchLevel` 枚举与降级语义

完成标准：

- 后端可明确返回“为什么当前不给价”
- 同一模板合同可被 dashboard、baseline、opportunity 复用
- `runtime_override` 不再拥有改写价格语义的能力

## Phase 2：dashboard 首页收口

工作：

- 右侧从 `spec label` chip 改为模板属性选择器
- 模板不完整时禁止展示价格卡
- 趋势只显示当前模板

完成标准：

- 首页不再出现“不同规格混价”的业务错误

## Phase 3：baseline / opportunity 收口

工作：

- baseline 以模板为主对象
- opportunity 先做模板匹配再评分
- product 级回退仅作为显式降级状态
- watch target 支持结构化 `pricingSelector`
- `reference_only` 与主机会池彻底分流

完成标准：

- 机会实体与 baseline 实体都能追溯到明确模板
- product / brand 回退不再冒充模板命中
- 非模板级命中不再触发提醒

## Phase 4：反馈与校准闭环

工作：

- 记录模板匹配错误
- 记录人工纠错原因
- 调整模板字段权重和 baseline 门槛

完成标准：

- 人工反馈可以反向修正价格可靠性

## 14. 验证与验收

## 14.1 技术验收问题

每次迭代都必须回答：

1. 这里输出的价格是否对应唯一模板
2. 模板字段是否选完整
3. 样本、卖家、可靠度是否足够
4. 趋势是否与当前模板严格一致
5. listing 是否先匹配模板再比较价格

## 14.2 测试建议

至少新增：

- 模板 key 生成单测
- 模板完整度判断单测
- baseline 匹配顺序单测
- listing -> template match 单测
- dashboard 首页模板未完整时的渲染测试

## 14.3 运行验证

本地 smoke 最少应覆盖：

- `8791 /healthz`
- `3030 /healthz`
- dashboard 首页能否显示模板缺失状态
- spec/template 价格 API 是否仅返回当前模板
- buy opportunity 是否带 baseline match level

## 15. 风险与取舍

### 风险 1：短期会让“有价格可看”的页面变少

因为一旦模板未完整就不给价，页面会出现更多空状态。

但这是正确取舍，优先保证价格靠谱，而不是保证页面热闹。

### 风险 2：各品类模板字段设计成本会上升

这是必要成本。没有这一步，后续所有页面和基线都容易继续混价。

### 风险 3：历史 baseline 与机会数据需要兼容迁移

建议先通过 payload 兼容，等模板 key 稳定后再做正式迁移。

## 16. 最终结论

结合当前项目现状，可以下一个明确结论：

1. 当前系统已经具备构建“靠谱二手价格指导助手”的核心技术基础
2. 当前最重要的问题不是缺前端，也不是缺运行能力，而是价格对象默认抽象还未收口
3. 下一阶段应优先做“模板级价格合同”而不是继续做页面修饰

后续技术工作必须围绕一句话展开：

`系统只对明确模板、且证据足够的商品给出价格指导。`

这句话应同时约束：

- 配置层
- 定价层
- baseline 层
- opportunity 层
- dashboard 首页
- buy workbench

只有当这条技术合同稳定成立，本项目才真正从“强分析平台”走到“靠谱价格助手”。
