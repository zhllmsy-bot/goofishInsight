# T3 Webhook 告警通道

Status: Done
Priority: P1
Source Todo: W3 + Phase 2 webhook 项
Done At: 2026-04-15

## 目标

在现有 dashboard/no-op dispatcher 基础上，打通至少一种外部 webhook 通道。

## 独占文件

- [alert_dispatcher.py](<repo-root>/apps/collector/src/goofish_insight/application/services/alert_dispatcher.py)
- [alert_router.py](<repo-root>/apps/collector/src/goofish_insight/application/services/alert_router.py)
- [notification_delivery.py](<repo-root>/apps/collector/src/goofish_insight/application/services/notification_delivery.py)
- [settings.py](<repo-root>/apps/collector/src/goofish_insight/settings.py)
- [test_alert_dispatcher_service.py](<repo-root>/apps/collector/tests/test_alert_dispatcher_service.py)
- [test_notification_delivery_service.py](<repo-root>/apps/collector/tests/test_notification_delivery_service.py)

## 范围

- 增加 webhook sender
- 加入 timeout、状态码判定、provider message id
- 支持 dry-run、本地 mock endpoint 测试
- 路由层拆清 dashboard/no-op/webhook

## 交付物

- 发现机会后可以主动通知
- 失败可重试、成功可回查、日志可追踪

## 实际验收（2026-04-15）

- `alert_router.py` 已实现 webhook 路由解析、超时控制、签名头和非 2xx 失败判定。
- `alert_dispatcher.py` 已支持 dashboard / webhook / dry-run 三类投递路径，并保留可追踪的 delivery 元数据。
- `apps.collector.tests.test_alert_dispatcher_service` 与 `apps.collector.tests.test_notification_delivery_service` 已通过。

## 验证

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_alert_dispatcher_service \
  apps.collector.tests.test_notification_delivery_service
```
