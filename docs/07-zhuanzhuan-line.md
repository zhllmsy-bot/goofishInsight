# 转转业务线

## 当前状态

- 已新增独立任务配置文件：`apps/collector/configs/monitor_tasks_zhuanzhuan.json`
- 已定义首批监控对象：
  - Garmin：`forerunner 265`、`forerunner 965`、`fenix 7 pro`、`fenix 8`、`epix pro`、`instinct 3`、`marq 2`、`tactix 8`
  - Apple：`MacBook Air M1/M2/M3`、`MacBook Pro 14`、`Mac mini M4`、`Mac Studio M2 Max / M4 Max / M2 Ultra / M3 Ultra`
- 现有批量入口已经支持按 `source_platform` 分发，避免把转转任务误走闲鱼采集器

## 当前边界

- 现有真实采集器仍然只支持 `xianyu`
- 如果直接用 `monitor_tasks_zhuanzhuan.json` 跑 `collect-batch`，系统会明确跳过 `zhuanzhuan` 任务，而不会误抓闲鱼
- 规格清洗、标准化入库、定价分析这三层可以直接复用

## 下一步

1. 现场确认转转 Web 搜索页和列表页入口
2. 确认转转列表接口是 `XHR / fetch / GraphQL / SSR` 哪一种
3. 补 `zhuanzhuan` 的响应监听和字段映射
4. 接入现有 `items / item_snapshots / item_spec_enrichments` 链路
5. 前端增加平台维度展示和多源对比
