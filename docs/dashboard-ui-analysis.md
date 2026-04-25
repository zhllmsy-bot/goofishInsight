# Goofish Insight 看板系统 UI 详细分析文档

> 生成时间: 2026-04-09
> 用途: 供 Gemini 进行 UI 优化参考

---

## 一、系统架构概述

### 1.1 技术栈
- **后端**: FastAPI + Jinja2 模板
- **前端**: 原生 JavaScript (无框架)
- **样式**: 自定义 CSS (dashboard.css)
- **数据加载**: 异步 JSON API + 前端渲染

### 1.2 页面加载模式
系统使用两种页面渲染模式:

| 模式 | 页面 | 说明 |
|------|------|------|
| **异步区块加载** | dashboard, progress, runtime | 页面壳先渲染，各区块通过 API 异步加载 |
| **服务端渲染** | buy_opportunities, item_detail, 配置中心 | 完整 HTML 服务端渲染 |

---

## 二、首页 (/) - dashboard.html

### 2.1 页面布局结构

```
┌─────────────────────────────────────────────────────────────────┐
│  HERO PANEL (async)                                             │
│  - 标题: "闲鱼选品与收货看板"                                     │
│  - 副标题: 决策看板说明                                          │
│  - 元信息: 自动刷新倒计时 / 当前大类 / 登录态 / 最近刷新时间        │
├─────────────────────────────────────────────────────────────────┤
│  FILTERS PANEL (async)                                          │
│  - 大类选择下拉框                                                │
│  - 动态规格筛选字段 (根据大类变化)                                │
│  - 定价视图 / 显示范围 / 窗口天数 / 心跳阈值 / 最少样本数           │
│  - 价格分组条数 / 商品条数                                        │
│  - 应用筛选按钮 + 清空筛选链接                                    │
├─────────────────────────────────────────────────────────────────┤
│  TAB 切换栏                                                      │
│  [市场大盘与行情] [选品图库] [AI 运行日志]                        │
├─────────────────────────────────────────────────────────────────┤
│  TAB 内容区 (三选一显示)                                          │
│                                                                 │
│  ┌─────────────────────────────┬─────────────────────────────┐  │
│  │  MARKET TAB (默认)          │                             │  │
│  │  ┌───────────────────────┐  │  PRICING PANEL (async)      │  │
│  │  │ FOCUS CARDS (async)   │  │  - 收货区间浏览器表格        │  │
│  │  │ - 焦点机会卡片网格      │  │  - 定价池门控统计           │  │
│  │  └───────────────────────┘  │                             │  │
│  │  ┌───────────────────────┐  │  CALIBRATION PANEL (async)  │  │
│  │  │ INSIGHTS (async)      │  │  - 真实成交校准表格         │  │
│  │  │ - 心跳监测统计         │  │  - 商品量榜单               │  │
│  │  │ - 品类趋势折线图网格    │  │                             │  │
│  │  └───────────────────────┘  │                             │  │
│  └─────────────────────────────┴─────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  GALLERY TAB                                              │  │
│  │  ITEMS PANEL (async) - 商品卡片网格                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────┬─────────────────────────────┐  │
│  │  DEBUG TAB                  │                             │  │
│  │  ┌───────────────────────┐  │  LLM TRACES (async)         │  │
│  │  │ OPS PANEL (async)     │  │  - Trace 列表 + 详情面板    │  │
│  │  │ - 运行概况统计行       │  │                             │  │
│  │  │ - 业务概览卡片网格     │  │                             │  │
│  │  │ - 最近运行列表         │  │                             │  │
│  │  └───────────────────────┘  │                             │  │
│  └─────────────────────────────┴─────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 各区块详细内容

#### 2.2.1 HERO Section (`/api/dashboard/sections/hero`)

**展示内容:**
- 主标题: "闲鱼选品与收货看板"
- 副标题说明: 首页优先展示心跳状态、当前收货区间和品类波动趋势
- 元信息标签:
  - 自动刷新倒计时 (60秒)
  - 当前选中大类名称 (如 "Apple电脑")
  - 浏览器登录态 (已登录/需要登录/未知/异常)
  - 最近刷新时间 (相对时间，如 "5分钟前")

**数据来源:**
- `overview.browser_session.auth_state` - 登录态
- `overview.latest_seen` - 最近活动时间
- `selected_category_code` / `selected_domain` - 当前选中大类

---

#### 2.2.2 FILTERS Section (`/api/dashboard/sections/filters`)

**展示内容:**

| 字段 | 类型 | 说明 |
|------|------|------|
| 大类 | 下拉选择 | 全部 / 具体大类 (apple_computer, garmin_watch 等) |
| 动态规格字段 | 下拉选择 | 根据大类动态生成 (型号、芯片、内存、硬盘、表盘尺寸、太阳能等) |
| 定价视图 | 下拉选择 | 按产品分组 / 按规格分组 |
| 显示范围 | 下拉选择 | 只看机会成立 / 查看全部 |
| 看板窗口 | 下拉选择 | 14天 / 30天 / 45天 / 60天 / 90天 |
| 心跳阈值 | 下拉选择 | 1天 / 2天 / 3天 / 5天 / 7天 / 10天 / 14天 |
| 最少样本 | 下拉选择 | 3 / 4 / 5 / 6 / 8 / 10 |
| 价格分组条数 | 下拉选择 | 6 / 12 / 18 / 24 / 36 / 48 |
| 商品条数 | 下拉选择 | 12 / 24 / 36 / 60 / 90 / 120 |

**交互:**
- 切换大类会自动清空 product_label 和 spec_label 筛选
- 点击"应用筛选"提交表单刷新页面
- 点击"清空筛选"返回首页

---

#### 2.2.3 FOCUS Section (`/api/dashboard/sections/focus`)

**展示内容:**
焦点机会卡片网格，每张卡片包含:

| 字段 | 说明 |
|------|------|
| eyebrow | 卡片类型标签 |
| 标题 | 产品名称或规格组合 |
| 副标题 | product_label (与标题不同时显示) |
| 状态标签 | 机会状态 (如 "建议关注" / "观望" / "机会成立") |
| 说明文字 | 当前市场情况描述 |
| 安全收货价 | P15 价格 (更保守的收货线) |
| 正常收货价 | P35 价格 (正常可谈收货线) |
| 市场中位价 | P50 价格 |
| 预估利润空间 | 计算的利润区间 |
| 规格维度标签 | 如芯片、内存、硬盘等 |

**卡片状态样式:**
- `actionable` (绿色) - 机会成立
- `watch` (黄色) - 建议观望
- `attention` (红色) - 需要关注

---

#### 2.2.4 INSIGHTS Section (`/api/dashboard/sections/insights`)

**展示内容分为两部分:**

**A. 心跳监测面板**

统计卡片 (4个):
- 近窗样本 - 总数 / 卖家数
- 当前活跃 - 在心跳线内的商品数
- 疑似失活 - 超过心跳线未出现的商品数 / 占比
- 近窗首现 - 首次出现在窗口内的商品数

表格列:
- 业务域
- 心跳状态 (信号标签 + 失活占比)
- 近窗样本数
- 当前活跃数
- 疑似失活数
- 近窗首现数
- 平均标价
- 最近出现时间

**B. 品类趋势面板**

每个品类一张趋势卡片，包含:
- 标题: 品类名称
- 副标题: 业务域 + 窗口天数 + 最新中位价
- 状态标签: 变化趋势 (上涨/下跌/持平) + 波动率
- **SVG 折线图** - 可点击放大
  - Y轴: 价格刻度线
  - X轴: 日期刻度
  - 两条范围线 (上下区间)
  - 一条趋势线
  - 数据点 (带 tooltip)
- 底部统计: 最新价格带 / 最新样本数 / 近3日均样本 / 当前活跃样本 / 日切片数

**趋势图交互:**
- 点击趋势图区域弹出 Modal 放大查看
- Modal 支持: 点击遮罩关闭 / 右上角关闭按钮 / Esc 键关闭

---

#### 2.2.5 PRICING Section (`/api/dashboard/sections/pricing`)

**展示内容:**

**A. 定价池门控统计 (7个统计卡片)**
1. 当前视图 - 产品/规格视图标签
2. 基础候选池 - 业务域+时间窗口内的活跃挂牌样本数
3. 通过 Review Gate - 数量 / 占比
4. 最终利润池 - 数量 / 占比
5. Gate 拦截 - 数量 / 占比
6. 机会成立分组 - 数量 / 总分组数
7. 已启用筛选 - 筛选条件数量

**B. 拦截原因标签行**
- 显示各类拦截原因及数量 (如 pending_audit, invalid, valid_but_below_profit 等)

**C. 收货区间浏览器表格**

列定义:
| 列名 | 内容 |
|------|------|
| 业务域 | 大类名称 (中文映射) |
| 分组 | 产品名/规格组合 + 副标签 |
| 安全收货价 | P15 价格 + 说明 |
| 正常收货价 | P35 价格 + 说明 |
| 市场中位价 | P50 价格 + 说明 |
| 预估利润空间 | 利润区间 + 毛利率 |
| 样本 | 卖家样本数 / 独立卖家数 |
| 可靠度 | 可靠度分数 + 等级标签 + 机会标签 |
| 规格维度 | 维度标签 + 规格覆盖率 |

---

#### 2.2.6 CALIBRATION Section (`/api/dashboard/sections/calibration`)

**展示内容:**

**A. Android 行情页成交纪录面板**

统计卡片 (4个):
- 已校准模型 - 数量 / 业务域数
- 可直接比对 - 同时有挂牌均价和真实成交锚点的数量
- 真实成交纪录 - 总记录数 / 有记录的模型数
- 区间/均价覆盖 - 有成交区间数 / 有7日均价数

表格列:
| 列名 | 内容 |
|------|------|
| 业务域 | 大类名称 |
| 型号 | 模型名称 + 查询词 |
| 当前挂牌锚点 | 均价 / 挂牌数 / 卖家数 |
| 真实成交锚点 | 锚定价 + 来源 + 成交区间 + 7日均价 |
| 成交线索 | 可见记录数 + 证据标签 + 首条标题 |
| 校准判断 | 判断标签 (贴盘/高估/低估/待观察) + 详细说明 |
| 最近同步 | 相对时间 |

**B. 商品量榜单**

表格列:
- 业务域
- 型号
- 商品数
- 卖家数
- 均价
- 真实成交锚点 (价格/来源/记录数/时间)
- 校准 (标签/说明)
- 最近出现时间

---

#### 2.2.7 ITEMS Section (`/api/dashboard/sections/items`) - 选品图库

**展示内容:**
商品卡片网格，每张卡片:
- 缩略图 (点击跳转详情页)
- 业务域标签
- 价格
- 标题 (点击跳转详情页)
- 显示名称 (标准化型号)
- 条件标签 (最多3个)
- 心跳状态标签
- 视频/广告标记
- 地区 / 卖家名 / 最近时间
- 操作链接: 打开闲鱼 / 原始响应

---

#### 2.2.8 OPS Section (`/api/dashboard/sections/ops`) - AI 运行日志

**展示内容:**

**A. 运行概况统计行 (4个紧凑卡片)**
- 近窗样本 / 当前活跃
- 疑似失活 / 近窗首现
- 最近任务 / 状态 / 页数
- 最近活动 / 登录更新时间

**B. 业务概览卡片网格**
每个业务域一个卡片:
- 业务域名称
- 心跳状态标签
- 活跃商品数
- 近窗总数 / 失活数 / 新增数
- 平均价格 / 最近时间

**C. 最近运行列表**
每行显示:
- 任务显示名
- 业务域 / 任务key
- 状态标签
- 成功页数/尝试页数
- 开始时间 (相对)

---

#### 2.2.9 LLM TRACES Section (`/api/dashboard/sections/llm-traces`)

**展示内容:**

**A. 头部信息**
- Trace 写入状态 (写入中/已关闭)
- Trace 总数
- Trace 目录路径

**B. 左右分栏布局**

左侧 - Trace 列表:
- 模型名称
- 状态标签 (成功/异常/损坏)
- Provider / 时间
- System 预览 (前100字符)
- User 预览 (前100字符)
- Error 信息 (如有)

右侧 - Trace 详情:
- 模型 / Provider / Method / 状态
- 时间 / 文件名 / 消息数 / URL
- Error 详情 (如有)
- Messages 列表 (role + content)
- Request Headers / Request Payload / Response Payload / Raw JSON (可折叠)

**交互:**
- 点击左侧列表项切换右侧详情
- 详情代码块可折叠

---

## 三、买入机会页 (/buy/opportunities) - buy_opportunities.html

### 3.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  HERO PANEL                                                     │
│  - 标题: "买入机会工作台"                                         │
│  - 副标题: Buy-Side Decision Desk                               │
│  - 统计数字: 当前机会数 / 提醒命中率 / 监控目标数                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┬─────────────────────┐  │
│  │  机会池表格                          │  监控目标列表        │  │
│  │  - 商品 (标题/地区/匹配级别)          │  - 目标名称          │  │
│  │  - 价格                              │  - profile/status    │  │
│  │  - 合理价                            │  - 冷却时间          │  │
│  │  - 买入线                            │                      │  │
│  │  - 机会分/风险分                      │  最新价格基线        │  │
│  │  - 状态 · 决策                        │  - baselineKey       │  │
│  │                                      │  - fair/buy 价格     │  │
│  │  (空状态提示运行命令)                 │  - sampleSize        │  │
│  └─────────────────────────────────────┴─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 数据字段

**机会池表格列:**
| 列 | 字段 | 说明 |
|----|------|------|
| 商品 | title, region, baselineMatchLevel | 标题、地区、匹配级别 |
| 价格 | currentPrice | 当前价格 |
| 合理价 | fairPrice | 计算合理价 |
| 买入线 | buyCeiling | 最高可买入价格 |
| 机会/风险 | opportunityScore, riskScore | 机会分 / 风险分 |
| 状态 | status, decision | 状态 + 人工决策 |

**监控目标卡片:**
- targetName, profileKey, status, notifyCooldownMinutes

**价格基线卡片:**
- baselineKey, fairPrice, buyCeiling, sampleSize

---

## 四、回刷进度页 (/progress) - progress.html

### 4.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER (async)                                                 │
│  - 标题: "LLM 二次清洗进度"                                       │
│  - 元信息: 自动刷新 / 大类 / AI Provider / Model / 最近完成时间   │
├─────────────────────────────────────────────────────────────────┤
│  筛选面板 (大类选择)                                              │
├─────────────────────────────────────────────────────────────────┤
│  OVERVIEW (async)                                               │
│  - 统计卡片: 完成率 / 待回刷 / 处理中 / 待审队列 / 已判无效        │
│  - 业务域进度卡片网格                                             │
├─────────────────────────────────────────────────────────────────┤
│  USAGE-WORKERS (async)                                          │
│  - Token 消耗统计                                                 │
│  - Usage 表格 (按业务域/管线/文件)                                │
│  - Worker 运行卡片网格                                            │
├─────────────────────────────────────────────────────────────────┤
│  AUDITS (async)                                                 │
│  - 待审分歧表格                                                   │
│  - 最近剔除原因表格                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 各区块详细内容

#### 4.2.1 OVERVIEW Section

**统计卡片 (5个):**
1. 总体完成率 - 百分比 / 已完成/目标总数
2. 待回刷 - 数量 / 说明
3. 处理中 - 数量 / 说明
4. 待审队列 - 数量 / 说明
5. 已判无效 - 数量 / 说明

**业务域进度卡片:**
- eyebrow: 业务域代码
- 标题: 业务域名称
- 完成率百分比 + 进度条
- 5个指标: 待回刷 / 处理中 / 已通过 / 待审 / 已剔除
- 底部: active数 / total数 / 最近review时间

#### 4.2.2 USAGE-WORKERS Section

**Token 消耗统计卡片 (7个):**
1. 累计 Tokens - 输入/输出
2. 垃圾命中
3. 低置信过滤
4. 高置信保留
5. 二次复审
6. 二次救回
7. 二次未解

**Usage 表格列:**
业务域 / 管线 / 文件名 / 请求数 / 样本数 / 输入Tokens / 输出Tokens / 总Tokens / 垃圾 / 低置信 / 高置信 / 二次复审 / 二次救回 / 二次未解 / 缓存 / 时间

**Worker 卡片:**
- 业务域 / 领域标签
- 管线类型 / 活跃状态
- 并发数 / batch大小 / pending数 / 更新时间
- Provider / Model
- 最近事件列表 (标题 + 摘要)
- 日志文件名

#### 4.2.3 AUDITS Section

**待审分歧表格列:**
业务域 / 商品(标题+ID) / 原因 / 模型结论 / 置信度 / 字段变更数 / 时间

**剔除原因表格列:**
业务域 / 原因 / 数量 / 最近时间

---

## 五、运行控制页 (/runtime) - runtime.html

### 5.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  HERO PANEL                                                     │
│  - 标题: "本机常驻任务控制台"                                     │
│  - 副标题: 运维动作说明                                          │
│  - 元信息: 自动刷新20秒 / 白名单动作标记                          │
├─────────────────────────────────────────────────────────────────┤
│  RUNTIME CONTROLS (async)                                       │
│  - 服务卡片网格 (每个服务一个卡片)                                 │
│  - 每个卡片: 标题/状态/描述/统计/检查项/操作按钮/反馈              │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 服务卡片结构

每个服务卡片包含:
- eyebrow + 标题
- 状态标签 (运行中/部分可用/已停止)
- 描述文字
- 统计网格 (label-value 对)
- 检查项列表 (label + detail，带 ok/warn 样式)
- 操作按钮行 (主按钮/次按钮)
- 反馈文本区

**支持的服务:**
- market_collectors - 首页 Feed 和搜索采集
- home_feed - 首页 Feed 监控
- batch_collect - 批量采集
- local_model - 本机模型
- vlm_runtime - 72B 视觉模型
- review_runtime - Review V3 常驻

**操作按钮:**
- start / restart / stop
- enable_message_mode / enable_dry_run
- switch_to_qwen3_30b / switch_to_qwen25_32b
- start_vlm / stop_vlm / restart_vlm

---

## 六、品类开通页 (/onboarding/xianyu) - xianyu_onboarding.html

### 6.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  HERO PANEL                                                     │
│  - 标题: "Xianyu Raw Cate Onboarding"                           │
│  - 副标题: 页面用途说明                                          │
│  - 状态标签: Phase 2 / Queue + Draft + Persist                  │
├─────────────────────────────────────────────────────────────────┤
│  操作入口面板 (表单)                                              │
│  - Operator / 关键词 / Task Key / 业务域 / Profile               │
│  - Discovery Pages / 队列状态 / Item Scan Limit                  │
│  - 包含已关闭复选框                                              │
│  - 按钮: 开始发现 / 同步队列 / 刷新视图                           │
│  - 反馈文本区                                                    │
├─────────────────────────────────────────────────────────────────┤
│  覆盖率统计网格 (async)                                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────┬─────────────────────────────┐  │
│  │  待开通 raw cate 队列 (async) │  Queue Detail 面板          │  │
│  │  - 列表形式                  │  - 选择后展示详情            │  │
│  │  - 总数标签                  │  - 默认提示文本              │  │
│  └─────────────────────────────┴─────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  Draft Editor 面板                                              │
│  - 标题: 属性草稿与模板确认                                       │
│  - 按钮: 生成草稿 / 预演创建 / 正式创建                            │
│  - 内容区: 默认提示 / 草稿展示                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、商品详情页 (/items/{id}) - item_detail.html

### 7.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  DETAIL HERO                                                    │
│  - eyebrow: 业务域 · 任务名                                      │
│  - 标题: 商品标题                                                │
│  - 元信息行: 价格标签 / 地区 / 最近时间                            │
│  - 操作按钮: 返回看板 / 打开闲鱼原页                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┬─────────────────────┐  │
│  │  商品信息面板                        │  卖家与快照面板      │  │
│  │  - 图片网格 (多张)                   │  - 卖家信息          │  │
│  │  - 商品属性列表 (ID/品牌/型号/芯片   │  - 快照历史表格      │  │
│  │    /内存/硬盘/发布时间/首次入库      │    (时间/价格/地区   │  │
│  │    /最近看到/来源关键词)             │     /页码/关键词)    │  │
│  │  - Spec 详情 (状态/置信度/抽取方式   │                      │  │
│  │    /产品线/标准型号/代际/表盘尺寸    │                      │  │
│  │    /太阳能/显示类型/屏幕尺寸/芯片    │                      │  │
│  │    /CPU/GPU/内存/硬盘/需复核)        │                      │  │
│  │  - 标签行 (condition/edition/video  │                      │  │
│  │    /ad)                            │                      │  │
│  └─────────────────────────────────────┴─────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  原始响应面板                                                    │
│  - 标题: Evidence chain / 原始响应                               │
│  - JSON 按钮 (跳转原始响应 API)                                   │
│  - 原始响应内容代码块                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 八、配置中心页面

### 8.1 统一布局模式

所有配置页面使用相同布局:

```
┌─────────────────────────────────────────────────────────────────┐
│  HERO PANEL                                                     │
│  - eyebrow: 配置类型                                             │
│  - 标题: 配置页面名称                                             │
│  - 副标题: 页面用途说明                                           │
│  - 状态标签: Phase 2 / 功能标签                                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────┬─────────────────────────────┐  │
│  │  左侧边栏                    │  右侧主内容区                │  │
│  │  - 列表面板 (async)          │  - Context Banner            │  │
│  │    * 总数标签                │    * eyebrow / 标题 / 说明   │  │
│  │    * 列表项                  │    * Tab 导航 (4个)          │  │
│  │  - 操作面板 (表单)           │  - AI Assist 面板 (大类页)   │  │
│  │    * 筛选字段                │  - Workflow Studio (大类页)  │  │
│  │    * 操作按钮                │  - Editor Summary 面板       │  │
│  │    * 反馈区                  │    * 标题 / 摘要文本         │  │
│  │  - 配置导航子菜单             │    * 操作按钮                │  │
│  └─────────────────────────────┴─────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  Modal 弹窗 (编辑抽屉)                                            │
│  - backdrop + dialog 结构                                         │
│  - header: eyebrow + 标题 + 关闭按钮                              │
│  - content: 表单字段网格                                          │
│  - footer: 操作按钮行                                             │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 各配置页面内容

#### 8.2.1 大类配置 (/config/categories)

**左侧列表:** Category Tree - 大类代码 + 名称 + 状态

**Workflow Studio (4步):**
1. 维护属性池 → 新建属性按钮 / 进入属性页链接
2. 创建模板 → 新建模板按钮 / 进入模板页链接
3. 绑定 Active 模板 → 绑定按钮 / 进入型号库链接
4. 维护具体品类 → 进入型号库按钮 / 型号数量标签

**Modal 类型:**
- 新建属性 (Step 1)
- 新建模板 (Step 2)
- 绑定模板 (Step 3)
- Category Editor (基础信息编辑)
- AI Assist (自然语言建类)

**AI Assist Modal 字段:**
- 自然语言描述输入
- 生成的 Category Code/Name/Path
- Prompt Profile / Extractor Profile / Validator Profile
- LLM Provider/Model Override
- 属性列表 (可增删)
- 模板属性 (可增删)
- 高级设置折叠区

#### 8.2.2 属性配置 (/config/attributes)

**左侧列表:** Attributes - 属性代码 + 名称 + 数据类型

**Modal 字段:**
- Code / Name / Data Type / Value Scope / Unit / Status
- Is Multi 复选框
- 通用属性复选框 (全类目自动注入)
- 高级设置: Scope Type / Scope Id
- Enum Options 文本域 (每行 `code|name`)

#### 8.2.3 模板配置 (/config/templates)

**左侧列表:** Templates - 模板ID + 版本 + 状态 + 所属大类

**Modal 字段:**
- Bound Category 选择
- Version / Status / Bind As Active Template 复选框
- 高级设置: Effective At / Published By / Compare To Template / Prompt Profile
- Template Items 文本域 (每行 `attributeCode|required|sale|filter|search|display|sortNo`)

**操作按钮:** 预览差异 / 预演保存 / 正式保存

#### 8.2.4 型号库配置 (/config/models)

**左侧列表:** Models - 型号代码 + 名称 + 品牌

**Modal 字段:**
- Bound Category 选择
- Brand Name / Series Name / Model Code / Model Name / Status
- Aliases 文本域 (每行 `aliasText|aliasType`)
- 高级设置: Import/Export JSON

**操作按钮:** 预演保存 / 正式保存 / 导出JSON / 导入JSON

#### 8.2.5 任务配置 (/config/tasks)

**左侧列表:** Tasks - 任务key + 显示名 + 状态

**表单字段:**
- Bound Category 选择
- Task Key / Display Name / Task Type / Profile Key
- Parallel Tabs / Paging Limit / Status
- 高级设置: Business Domain
- Queries 文本域 (每行 `query|pages|priority`)
- Brand/Model/Config Lexicon 文本域

#### 8.2.6 Raw Cate Policy (/config/raw-cate-policy)

**左侧列表:** Policies - 匹配条件 + 策略模式

**表单字段:**
- Match Scope / Xianyu C Cat Id / Xianyu Cat Id / Xianyu Tb Cat Id
- Raw Category Name / Policy Mode
- Category Id / Category Code / Template Id / Template Override Id
- Status / Resolution Source

---

## 九、前端渲染机制

### 9.1 异步区块加载流程

```javascript
1. DOMContentLoaded 触发
2. setupAsyncSections() 初始化
   - 为每个 [data-async-section] 预留高度
   - 绑定重试按钮事件
3. refreshSections() 加载数据
   - 高优先级区块并行加载
   - 普通优先级区块并行加载
4. loadSection(container) 单个区块加载
   - 显示骨架屏 (已预渲染在 HTML 中)
   - fetch API 获取 JSON
   - 调用对应 renderer 函数生成 HTML
   - 插入容器并释放高度限制
```

### 9.2 Renderer 函数映射

| Renderer Name | 对应函数 | 说明 |
|--------------|----------|------|
| dashboard-hero | renderDashboardHero | 首页 Hero |
| dashboard-filters | renderDashboardFilters | 筛选面板 |
| dashboard-focus | renderDashboardFocus | 焦点机会卡片 |
| dashboard-insights | renderDashboardInsights | 心跳+趋势 |
| dashboard-pricing | renderDashboardPricing | 定价分析 |
| dashboard-calibration | renderDashboardCalibration | 真实成交校准 |
| dashboard-items | renderDashboardItems | 商品图库 |
| dashboard-ops | renderDashboardOps | 运行概况 |
| dashboard-llm-traces | renderDashboardLlmTraces | LLM调用追踪 |
| runtime-controls-page | renderRuntimeControlsPage | 运行控制 |
| progress-header | renderProgressHeader | 回刷头部 |
| progress-overview | renderProgressOverview | 回刷概览 |
| progress-usage-workers | renderProgressUsageWorkers | Token消耗+Worker |
| progress-audits | renderProgressAudits | 待审+剔除 |

### 9.3 数据格式化工具函数

| 函数 | 用途 |
|------|------|
| formatNumber | 数字格式化，支持小数位 |
| formatCurrency | 货币格式化，≥1万显示为 x.xxw |
| formatPercent | 百分比格式化 |
| formatRelative | 相对时间 (x秒前/x分钟前/x小时前/x天前) |
| formatDateTime | 日期时间格式化 (MM-DD HH:mm:ss) |
| domainLabel | 业务域代码转中文标签 |
| authStateLabel | 登录态转中文 |
| runStatusLabel | 任务状态转中文 |
| reliabilityTierLabel | 可靠度等级转中文 |
| runtimeStatusLabel | 运行状态转中文 |

---

## 十、样式系统

### 10.1 核心 CSS 类

**布局类:**
- `.page-shell` - 页面外壳
- `.main-content` - 主内容区
- `.async-page` - 异步页面容器
- `.async-section-stack` - 异步区块堆叠

**面板类:**
- `.hero-panel` - Hero 面板
- `.panel` - 标准面板
- `.compact-panel` - 紧凑面板
- `.filters-panel` - 筛选面板
- `.async-skeleton` - 骨架屏

**组件类:**
- `.eyebrow` - 小标题/标签
- `.status-pill` - 状态标签
- `.tag` - 普通标签
- `.signal-pill` - 信号标签 (actionable/watch/attention)
- `.reliability-pill` - 可靠度标签 (high/medium/watch/low)
- `.focus-card` - 焦点卡片
- `.stat-card` - 统计卡片
- `.domain-card` - 业务域卡片
- `.trend-card` - 趋势卡片

**表格类:**
- `.data-table` - 数据表格
- `.table-wrap` - 表格包装器
- `.table-scroll` - 可滚动表格

**表单类:**
- `.filter-field` - 筛选字段
- `.wide-field` / `.narrow-field` - 字段宽度
- `.primary-button` / `.secondary-button` - 按钮样式

### 10.2 响应式断点

系统使用 CSS Grid 和 Flexbox 实现响应式布局，主要布局模式:
- 桌面: 左右分栏 (主内容 + 侧边栏)
- 平板/手机: 单列堆叠

---

## 十一、API 端点汇总

### 11.1 Dashboard API

| 端点 | 说明 |
|------|------|
| GET /api/dashboard/sections/hero | Hero 区块数据 |
| GET /api/dashboard/sections/filters | 筛选器配置数据 |
| GET /api/dashboard/sections/focus | 焦点机会卡片 |
| GET /api/dashboard/sections/insights | 心跳+趋势数据 |
| GET /api/dashboard/sections/pricing | 定价分析数据 |
| GET /api/dashboard/sections/calibration | 真实成交校准 |
| GET /api/dashboard/sections/items | 商品列表 |
| GET /api/dashboard/sections/ops | 运行概况 |
| GET /api/dashboard/sections/llm-traces | LLM Trace 列表 |
| GET /api/dashboard/llm-traces/{key} | Trace 详情 |
| GET /api/dashboard/runtime/status | Runtime 状态 |
| POST /api/dashboard/runtime/actions | 执行 Runtime 动作 |

### 11.2 Progress API

| 端点 | 说明 |
|------|------|
| GET /api/progress/sections/header | 头部数据 |
| GET /api/progress/sections/overview | 概览统计 |
| GET /api/progress/sections/usage-workers | Token+Worker |
| GET /api/progress/sections/audits | 待审+剔除 |

---

## 十二、待优化点记录

基于用户反馈:

1. **首页价格信息展示** - 用户反馈"展示的很垃圾"，需要重新设计价格信息的呈现方式
2. **趋势图交互** - 已支持点击放大，但可能需要更丰富的交互
3. **筛选器布局** - 当前 auto-fit 网格可能需要改为更明确的 12 栏控制面板

---

*文档结束*
