# T11 Buy 页迁移与反馈联动

Status: Done
Priority: P2
Source Todo: W4 + W10 buy 页部分
Done At: 2026-04-15

## 目标

让 buy 页不再是孤立的 Jinja 入口，并把“感兴趣/不感兴趣”动作灰度联动到反馈或告警候选链路。

## 独占文件

- [buy_feedback.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_feedback.py)
- [buy_opportunities.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_opportunities.py)
- [buy_alerts.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_alerts.py)
- [buy.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/buy.py)
- [buy_opportunities.html](<repo-root>/apps/web/templates/buy_opportunities.html)

## 范围

- buy 页从孤立页向统一动作路径收拢
- 兴趣动作灰度联动到告警候选或反馈链路
- 保证反馈还能继续进入 analyzer 统计输入

## 交付物

- 高频页面不再割裂
- W4/W10 buy 页相关项推进

## 实际验收（2026-04-15）

- `buy_feedback`、`buy_opportunities`、`buy_alerts` 和 `outreach_outcomes` 已串起“动作 - 反馈 - 告警候选”闭环。
- `apps.collector.tests.test_buy_*` 与 `apps.collector.tests.test_outreach_outcomes_service` 已通过。
- buy 页已不再是孤立入口，反馈能继续进入 analyzer 统计输入链路。

## 验证

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_outreach_outcomes_service
```
