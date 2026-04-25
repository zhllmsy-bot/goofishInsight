# 模板化模式分层回滚说明

Status: Active  
Updated: 2026-04-11  
Workspace: `<repo-root>`

## 1. 回滚原则

1. 只回滚出问题的层，不做“一键推倒”。
2. 先保交易可用，再恢复精细能力。
3. 每一步回滚后都要执行最小 smoke（接口 + 首页 + 提醒）。

## 2. 可控开关

通过环境变量控制：

- `PRICE_TEMPLATE_CONTRACT_ENABLED`
- `PRICE_TEMPLATE_DASHBOARD_ENABLED`
- `PRICE_TEMPLATE_OPPORTUNITY_ENABLED`
- `PRICE_TEMPLATE_TREND_ENABLED`
- `PRICE_TEMPLATE_ALERT_STRICT_MODE`

修改后重启后端服务：

- `launchctl kickstart -k gui/$(id -u)/com.admin.goofish-dashboard-backend-8791`

## 3. 分层回滚路径

### L1：仅放松提醒严格门控

适用场景：
- 模板匹配短时异常导致提醒显著下降

操作：
- `PRICE_TEMPLATE_ALERT_STRICT_MODE=false`

影响：
- 仅提醒侧放宽，首页与机会池模板口径不变

### L2：回滚机会模板严格模式

适用场景：
- 机会池大量降级为 `REFERENCE_ONLY` 且业务确认误杀

操作：
- `PRICE_TEMPLATE_OPPORTUNITY_ENABLED=false`

影响：
- 机会状态恢复宽松口径
- 反馈校准仍可继续采集

### L3：回滚趋势模板严格过滤

适用场景：
- 模板快照覆盖不足，趋势页可读性大幅下降

操作：
- `PRICE_TEMPLATE_TREND_ENABLED=false`

影响：
- 趋势恢复非模板严格聚合
- 首页价格合同逻辑不变

### L4：回滚首页模板合同

适用场景：
- 模板合同解析异常，首页出现大量不可用状态

操作：
- `PRICE_TEMPLATE_CONTRACT_ENABLED=false`

影响：
- 合同切回 legacy 模式
- 模板强约束暂时失效

### L5：页面模板模式总开关

适用场景：
- 首页模板交互存在严重线上问题，需要快速止损

操作：
- `PRICE_TEMPLATE_DASHBOARD_ENABLED=false`

影响：
- 首页可切回旧展示流程（若前端已接线）

## 4. 推荐回滚顺序

1. 先 `ALERT_STRICT_MODE`  
2. 再 `OPPORTUNITY_ENABLED`  
3. 再 `TREND_ENABLED`  
4. 最后才 `CONTRACT_ENABLED`

说明：
- 每次只动一个开关，观察 15-30 分钟核心指标后再继续。

## 5. 最小验证命令

1. 开关状态与 tier 分布：
   - `GET /api/buy/template-monitoring`
2. 机会池：
   - `GET /api/buy/opportunities?limit=20`
3. 首页：
   - `GET /dashboard`
4. 提醒干跑：
   - `python -m goofish_insight.cli emit-buy-alerts --dry-run`

通过标准：
- 无 5xx
- 首页可正常展示
- 机会与提醒量级回到预期范围
