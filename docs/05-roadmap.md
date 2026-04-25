# 路线图

Status: Active
Updated: 2026-04-24

## 当前产品定义

Goofish Insight 当前不是泛化的“闲鱼采集平台”。

项目当前阶段的固定产品定义是：

`围绕目标品类持续采集公开供给，建立合理价与买入机会判断，并把结果沉淀为可执行的买方决策工作台。`

当前优先服务的核心场景：

- 持续发现值得关注的低价二手商品
- 给出合理价、买入上限与风险解释
- 让操作者在工作台里完成关注、联系、购买和反馈
- 用反馈持续校准机会识别与阈值

## 产品阶段

## Phase 0：方向冻结

- 固定项目方向为“二手买入决策助手”
- 固定首批目标品类为 `apple_computer` 与 `garmin_watch`
- 固定核心输出为：
  - 合理价
  - 买入上限
  - 机会分
  - 风险提示
  - 提醒与反馈

## Phase 1：事实层稳定

- 稳定批量搜索采集与首页 feed 监控
- 保持 `items` 与 `item_snapshots` 的历史可追溯
- 稳定 `enrich-specs` 主链，确保规格结果可进入价格资格判断
- 保持 review / cleaning 只处理歧义与低置信样本

## Phase 2：合理价成型

- 产出配置级 `fair_price`
- 产出 `buy_ceiling`
- 明确价格资格合同与样本回退策略
- 稳定 baseline 重建链路

## Phase 3：机会池成型

- 产出 `buy_opportunity`
- 明确 `discount_rate`、`risk_score`、`opportunity_score`
- 让每条机会都能追溯到 baseline 与规格依据
- 建立提醒冷却与 alert hit rate 统计

## Phase 4：买方工作台成型

- 实现买入目标页、机会列表页、机会详情页、价格基线页
- 在 dashboard 首页加入今日机会入口
- 支持 `dismiss / contacted / purchased / not_worth_it` 反馈动作
- 让 runtime control 可直接驱动 buy jobs

## Phase 5：反馈闭环与分析层收口

- 让人工反馈真正回流到阈值与评分校准
- 把 `fair price / opportunity / calibration` 主链迁入 `apps/analyzer`
- 保持 `collector` 聚焦事实采集、配置与 runtime control

## Phase 6：运行平面产品化

- 为 resident 单元建立统一 start / stop / status / logs 合同
- 保持 buy jobs 为按需分析单元，而不是默认 resident
- 把健康检查统一到 dashboard runtime control
- 把“能不能安全停、能不能真实反映状态”作为主产品能力

## 当前建议的最短路径

1. 先保证事实层、规格链路和价格资格合同稳定
2. 再持续提升 baseline 与 opportunity 的可信度
3. 优先增强反馈闭环，而不是继续扩泛页面或泛采集
4. 最后再把 resident runtime 和运营平面做成稳定产品能力

## 明确不优先做的事

- 不把项目重新拉回“泛采集平台”叙事
- 不优先扩全站级无人值守采集
- 不优先做自动聊天、自动砍价、自动下单
- 不为了统一运行面而把所有一次性作业都做成 resident
