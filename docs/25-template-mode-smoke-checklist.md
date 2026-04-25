# 模板化模式 Smoke Checklist

Status: Active  
Updated: 2026-04-11  
Workspace: `<repo-root>`

## 1. 启动与健康

推荐先跑自动 smoke：

- `python -m goofish_insight.cli smoke-template-mode --category-code apple_computer`
- 报告查看：
  - `reports/latest-template-mode-smoke.json`

1. 后端监听：
   - `lsof -nP -iTCP:8791 -sTCP:LISTEN`
2. 核心接口可达：
   - `GET /api/dashboard/section/filters`
   - `GET /api/dashboard/section/pricing`
   - `GET /api/buy/opportunities`
   - `GET /api/buy/template-monitoring`

通过标准：
- 以上接口均返回 `200`
- 无 5xx 或模板字段缺失异常

## 2. 模板合同与开关

1. 检查开关：
   - `GET /api/buy/template-monitoring`
2. 确认返回 `featureFlags`：
   - `priceTemplateContractEnabled`
   - `priceTemplateDashboardEnabled`
   - `priceTemplateOpportunityEnabled`
   - `priceTemplateTrendEnabled`
   - `priceTemplateAlertStrictMode`

通过标准：
- 开关值与当前灰度计划一致
- `baseline.tierCounts` 与 `opportunity.tierCounts` 可读

## 3. 首页模板工作流

1. 打开首页，选择一个型号但不补全核心字段。
2. 观察价格区：不得显示误导性指导价，只显示缺失字段说明。
3. 补全模板核心字段后再次观察：
   - 仅当前模板价格线显示
   - `guidance_ready` 才显示完整指导语义
4. 检查选择器选项质量：
   - 规格/模板芯片不出现空白按钮
   - 同值选项不会重复渲染

通过标准：
- 模板不完整时不展示可执行价格
- 完整模板时价格与模板键一致
- 选择器项可读且无空白/重复

## 4. 趋势严格归属

1. 选择同型号不同内存规格（如 16G 与 32G）分别查看趋势。
2. 对比趋势卡标题与数据点范围。

通过标准：
- 不同模板规格趋势不混算
- 过渡回放样本只显示 `reference_only` 语义

## 5. 机会与提醒门控

1. 刷新机会池：
   - `python -m goofish_insight.cli refresh-buy-opportunities --category-code apple_computer`
2. 抽样检查机会 payload：
   - `matchedTemplateKey`
   - `templateAvailabilityTier`
   - `templateMatchErrorType`
3. 干跑提醒：
   - `python -m goofish_insight.cli emit-buy-alerts --dry-run`

通过标准：
- `degraded_product/degraded_brand` 不得进入主提醒
- `templateAvailabilityTier != guidance_ready` 不触发 alert（严格模式下）

## 6. 反馈闭环与校准

1. 查询反馈质量：
   - `GET /api/buy/feedback-quality`
2. 查询校准建议：
   - `GET /api/buy/feedback-calibration`
3. 检查工作台侧栏：
   - “反馈校准”
   - “校准动作建议”

通过标准：
- 能看到分层反馈统计与拒绝原因
- 能产出模板字段/阈值/排序建议（样本不足可返回 0 建议）

## 7. 通过判定

仅当以下条件同时满足才允许继续灰度：

1. 所有关键接口 `200` 且无异常日志
2. 首页不再出现混合规格价格展示
3. 趋势不混算，提醒不越权
4. 反馈与校准链路可查询
